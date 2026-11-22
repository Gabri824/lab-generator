"""
tests/test_api.py
Interfaccia del server della GUI (src/gui/api.py), con richieste HTTP vere a un server locale.

- Le operazioni fatte con anteprima + applica producono gli stessi file della strada del
  terminale (tests/attesi/operazioni/*.diff).
- Anteprima e applica sono legate dalle impronte: se un file cambia in mezzo non si scrive nulla.
- Il server rifiuta operazioni e parametri non previsti, dispositivi inesistenti, percorsi,
  richieste senza X-Lab-Gen o con un Host diverso, corpi troppo grandi.
- Lab nuovi: controllo del modello, anteprima in una cartella temporanea, creazione.
"""
import http.client
import json
import os
import shutil
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

import _comune as c
from core import supporto
from gui import server

# operazione -> (lab, operazione, parametri JSON); stessi valori di test_operazioni.CASI
CASI = {
    'costo_ospf': ('papillon_mio', 'costo_ospf', {'router': 'r1', 'interfaccia': 'eth1', 'costo': 50}),
    'auto_cost_togli': ('papillon_mio', 'auto_cost', {'etichetta': 'AS20', 'togli': True}),
    'loopback_router': ('galaxy_mio', 'loopback', {'dispositivo': 'as2r1', 'ip': '2.255.0.1'}),
    'network_bgp_aggregato': ('candy_test', 'network_bgp',
                              {'router': 'as10r1', 'reti': ['110.0.0.0/16'], 'togli_coperte': True}),
    'ibgp_full_mesh': ('galaxy_mio', 'ibgp', {'asn': '2'}),
    'default_originate': ('candy_test', 'default_originate',
                          {'router': 'as10r1', 'scelti': ['192.168.0.2'], 'solo': True}),
    'default_ospf': ('papillon_mio', 'default_igp', {'proto': 'ospf', 'router': 'r3', 'ha_default': True}),
    'redistribuzione_route_map': ('hourglass_test', 'redistribuzione_route_map',
                                  {'router': 'r3', 'rete': '10.2.0.0/30'}),
    'resolver': ('tennis_test', 'resolver', {'dispositivo': 'web_srv', 'ip': '1.0.0.2'}),
    'delega_dns': ('tennis_test', 'delega_dns', {'server': 'root', 'zona': 'org', 'ns': '', 'ip': '20.1.0.9'}),
    'policy_local_pref_reti': ('candy_test', 'policy', {
        'router': 'as40r1', 'neighbor': '192.168.0.5', 'tipo': 'local_pref', 'valore': 130,
        'reti': ['20.0.0.0/8']}),
    'cpp_provider': ('candy_test', 'cpp', {
        'router': 'as10r1', 'vicino': 'as40r1', 'ip': '192.168.0.2', 'asn': '40', 'relazione': 'provider',
        'reti_out': ['110.0.0.0/24']}),
    'ip_cambia_rete_lan': ('candy_test', 'ip_interfaccia',
                           {'dispositivo': 'as10r1', 'dev': 'eth0', 'nuovo': '192.168.50.1/30'}),
    'rinumera_lan': ('candy_test', 'rinumera_lan', {'lan': 'A', 'nuova_rete': '192.168.100.0/30'}),
    'sposta_interfaccia': ('papillon_mio', 'sposta_interfaccia',
                           {'dispositivo': 'client', 'dev': 'eth0', 'nuova_lan': 'B', 'nuovo_ip': '20.20.2.10/24'}),
    'cambia_as': ('candy_test', 'as', {'router': 'as10r1', 'nuovo': '11'}),
    'aggiungi_ospf_abr': ('candy_test', 'aggiungi_protocollo', {
        'router': 'as10r1', 'proto': 'ospf', 'reti': ['192.168.0.0/30', '110.0.0.0/24'],
        'aree': {'192.168.0.0/30': '0.0.0.0', '110.0.0.0/24': '2.2.2.2'}, 'aree_stub': []}),
    'togli_bgp': ('candy_test', 'togli_protocollo', {'router': 'as10r1', 'proto': 'bgp'}),
    'rinomina': ('candy_test', 'rinomina', {'vecchio': 'as40r1', 'nuovo': 'core1'}),
    'aggiungi_router': ('candy_test', 'aggiungi_dispositivo', {'tipo': 'router', 'dati': {
        'name': 'as90r1', 'protocols': ['bgp'], 'asn': '90',
        'interfaces': [{'name': 'eth0', 'lan': 'L', 'ip': '110.0.0.9/24'},
                       {'name': 'eth1', 'lan': 'Q', 'ip': '190.0.0.1/24'}]}}),
    'togli_dispositivo': ('candy_test', 'togli_dispositivo', {'nome': 'as80r1'}),
    'aggiungi_interfaccia': ('candy_test', 'aggiungi_interfaccia', {'nome': 'as10r1', 'lan': 'Q', 'ip': '190.0.0.1/24'}),
    'togli_interfaccia': ('candy_test', 'togli_interfaccia', {'nome': 'as50r1', 'dev': 'eth1'}),
}

# lab piccolo scritto a mano, nel formato del wizard
MODELLO = {
    'routers': {
        'r1': {'protocols': ['ospf'], 'interfaces': [{'name': 'eth0', 'lan': 'A', 'ip': '10.0.0.1/30'},
                                                     {'name': 'eth1', 'lan': 'B', 'ip': '20.0.0.1/24'}]},
        'r2': {'protocols': ['ospf'], 'interfaces': [{'name': 'eth0', 'lan': 'A', 'ip': '10.0.0.2/30'}]},
    },
    'hosts': [{'name': 'pc1', 'interfaces': [{'name': 'eth0', 'lan': 'B', 'ip': '20.0.0.10/24'}],
               'gateway': '20.0.0.1', 'gw_dev': 'eth0'}],
    'wwws': [],
    'resolver': None,
}


class ServerDiProva(unittest.TestCase):
    """Un server vero su 127.0.0.1 con una cartella dei lab temporanea."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.base = cls.tmp.name
        cls.st = server.Stato(cls.base, None)
        cls.srv = ThreadingHTTPServer(('127.0.0.1', 0), server.Gestore)
        cls.porta = cls.srv.server_address[1]
        server.Gestore.st = cls.st
        server.Gestore.host_ok = {f'127.0.0.1:{cls.porta}'}
        cls.st.server = cls.srv
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def lab(self, nome):
        """Copia nuova di un lab di prova nella cartella dei lab del server."""
        p = os.path.join(self.base, nome)
        shutil.rmtree(p, ignore_errors=True)
        shutil.rmtree(supporto.cartella_supporto(p), ignore_errors=True)
        shutil.copytree(os.path.join(c.FIXTURE_LABS, nome), p)
        return p

    def richiesta(self, metodo, percorso, corpo=None, intestazioni=None, grezzo=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.porta, timeout=60)
        h = {'Host': f'127.0.0.1:{self.porta}', 'X-Lab-Gen': '1', 'Content-Type': 'application/json'}
        h.update(intestazioni or {})
        dati = grezzo if grezzo is not None else (None if corpo is None else json.dumps(corpo).encode('utf-8'))
        try:
            conn.request(metodo, percorso, body=dati, headers=h)
            r = conn.getresponse()
            return r.status, json.loads(r.read().decode('utf-8'))
        finally:
            conn.close()

    def azione(self, **corpo):
        return self.richiesta('POST', '/api/azione', corpo)

    def anteprima_e_applica(self, lab, operazione, parametri):
        codice, ant = self.azione(azione='anteprima', lab=lab, operazione=operazione, parametri=parametri)
        self.assertEqual(200, codice, ant)
        codice, esito = self.azione(azione='applica', lab=lab, operazione=operazione, parametri=parametri,
                                    impronte=ant['impronte'], firma=ant['firma'])
        self.assertEqual(200, codice, esito)
        return ant, esito


class TestOperazioni(ServerDiProva):

    def test_stessi_file_del_terminale(self):
        for nome, (lab, operazione, parametri) in CASI.items():
            with self.subTest(operazione=nome):
                p = self.lab(lab)
                prima = c.leggi_albero(p)
                ant, esito = self.anteprima_e_applica(lab, operazione, parametri)
                self.assertTrue(ant['file'] and esito['scritto'])
                with open(os.path.join(c.ATTESI, 'operazioni', nome + '.diff'), encoding='utf-8', newline='') as f:
                    self.assertEqual(f.read(), c.diff_testo(prima, c.leggi_albero(p)))
                self.assertTrue(os.path.isfile(supporto.percorso_xml(p)), "l'XML si rigenera fuori dal lab")

    def test_elenco_delle_operazioni(self):
        codice, el = self.richiesta('GET', '/api/operazioni')
        self.assertEqual(200, codice)
        self.assertEqual(set(c.core.operazioni.OPERAZIONI), set(el))
        costo = {p['nome']: p for p in el['costo_ospf']['calcola']}
        self.assertEqual({'router', 'interfaccia', 'costo'}, set(costo))
        self.assertTrue(all(p['obbligatorio'] for p in costo.values()))
        self.assertEqual(False, {p['nome']: p for p in el['auto_cost']['calcola']}['togli']['predefinito'])

    def test_opzioni(self):
        self.lab('candy_test')
        codice, r = self.azione(azione='opzioni', lab='candy_test', operazione='rinumera_lan',
                                parametri={'lan': 'A', 'nuova_rete': '192.168.100.0/30'})
        self.assertEqual(200, codice, r)
        vecchia, membri, nuovi = r['opzioni']
        self.assertEqual('192.168.0.0/30', vecchia)
        self.assertEqual({'as10r1', 'as40r1'}, {m[0] for m in membri})
        self.assertIn(['as10r1', 'eth0', '192.168.100.1/30'], nuovi)
        codice, r = self.azione(azione='opzioni', lab='candy_test', operazione='righe', parametri={'dispositivo': 'as10r1'})
        self.assertIn('as10r1/etc/frr/frr.conf', r['opzioni'])
        codice, r = self.azione(azione='opzioni', lab='candy_test', operazione='aggiungi_dispositivo')
        self.assertEqual(200, codice)
        self.assertIn('as10r1', r['opzioni']['nomi'])

    def test_rinumera_con_ip_scelti(self):
        p = self.lab('candy_test')
        self.anteprima_e_applica('candy_test', 'rinumera_lan', {
            'lan': 'A', 'nuova_rete': '192.168.100.0/30', 'assegnati': [['as10r1', 'eth0', '192.168.100.2/30'],
                                                                         ['as40r1', 'eth0', '192.168.100.1/30']]})
        st = c.core.leggi_stato(p)
        self.assertEqual('192.168.100.2/30', st['dispositivi']['as10r1']['ip_per_dev']['eth0'][0])
        self.assertEqual('192.168.100.1/30', st['dispositivi']['as40r1']['ip_per_dev']['eth0'][0])

    def test_modifica_a_righe(self):
        p = self.lab('papillon_mio')
        rel = 'r1/etc/frr/frr.conf'
        with open(os.path.join(p, 'r1', 'etc', 'frr', 'frr.conf'), encoding='utf-8') as f:
            righe = f.read().split('\n')[:-1]
        self.anteprima_e_applica('papillon_mio', 'righe', {'rel': rel, 'nuove': righe + ['! nota'], 'vecchie': righe})
        with open(os.path.join(p, 'r1', 'etc', 'frr', 'frr.conf'), encoding='utf-8') as f:
            self.assertTrue(f.read().endswith('! nota\n'))
        codice, r = self.azione(azione='anteprima', lab='papillon_mio', operazione='righe',
                                parametri={'rel': '../../etc/passwd', 'nuove': ['x']})
        self.assertEqual(422, codice, r)

    def test_piano_vuoto(self):
        self.lab('candy_test')
        par = {'dispositivo': 'as10r1', 'dev': 'eth1', 'nuovo': '110.0.0.1/24'}
        codice, ant = self.azione(azione='anteprima', lab='candy_test', operazione='ip_interfaccia', parametri=par)
        self.assertEqual(200, codice, ant)
        self.assertEqual([], ant['file'])
        self.assertTrue(ant['vuoto'])
        codice, r = self.azione(azione='applica', lab='candy_test', operazione='ip_interfaccia', parametri=par,
                                impronte=ant['impronte'], firma=ant['firma'])
        self.assertEqual((200, False), (codice, r['scritto']))

    def test_registro(self):
        self.lab('papillon_mio')
        self.anteprima_e_applica('papillon_mio', 'costo_ospf', {'router': 'r2', 'interfaccia': 'eth0', 'costo': 7})
        codice, reg = self.richiesta('GET', '/api/registro')
        self.assertTrue(any('Costo OSPF di r2 eth0: 7' in v['operazione'] for v in reg))


class TestConflitti(ServerDiProva):

    PAR = {'router': 'r1', 'interfaccia': 'eth1', 'costo': 50}

    def test_file_cambiato_dopo_l_anteprima(self):
        p = self.lab('papillon_mio')
        codice, ant = self.azione(azione='anteprima', lab='papillon_mio', operazione='costo_ospf', parametri=self.PAR)
        frr = os.path.join(p, 'r1', 'etc', 'frr', 'frr.conf')
        with open(frr, 'a', encoding='utf-8') as f:
            f.write('! modificato a mano\n')
        prima = c.leggi_albero(p)
        codice, r = self.azione(azione='applica', lab='papillon_mio', operazione='costo_ospf', parametri=self.PAR,
                                impronte=ant['impronte'], firma=ant['firma'])
        self.assertEqual(409, codice, r)
        self.assertEqual(['r1/etc/frr/frr.conf'], r['file'])
        self.assertEqual(prima, c.leggi_albero(p), 'con un conflitto non si scrive nulla')

    def test_firma_diversa(self):
        p = self.lab('papillon_mio')
        codice, ant = self.azione(azione='anteprima', lab='papillon_mio', operazione='costo_ospf', parametri=self.PAR)
        prima = c.leggi_albero(p)
        # stessi file, parametri diversi da quelli dell'anteprima: il piano non è quello mostrato
        codice, r = self.azione(azione='applica', lab='papillon_mio', operazione='costo_ospf',
                                parametri=dict(self.PAR, costo=60), impronte=ant['impronte'], firma=ant['firma'])
        self.assertEqual(409, codice, r)
        self.assertEqual(prima, c.leggi_albero(p))

    def test_applica_senza_impronte(self):
        self.lab('papillon_mio')
        codice, r = self.azione(azione='applica', lab='papillon_mio', operazione='costo_ospf', parametri=self.PAR)
        self.assertEqual(400, codice, r)


class TestSicurezza(ServerDiProva):

    def setUp(self):
        self.lab('papillon_mio')

    def anteprima(self, operazione, parametri):
        return self.azione(azione='anteprima', lab='papillon_mio', operazione=operazione, parametri=parametri)

    def test_operazione_e_parametri(self):
        self.assertEqual(400, self.anteprima('rm_rf', {})[0])
        self.assertEqual(400, self.anteprima('__class__', {})[0])
        codice, r = self.anteprima('costo_ospf', {'router': 'r1', 'interfaccia': 'eth1', 'costo': 5, 'stato': {}})
        self.assertEqual(400, codice)
        self.assertIn('stato', r['errore'])
        codice, r = self.anteprima('costo_ospf', {'router': 'r1'})
        self.assertEqual(400, codice)
        self.assertIn('interfaccia', r['errore'])
        self.assertEqual(400, self.anteprima('costo_ospf', ['r1'])[0])

    def test_dispositivi_lan_e_testi(self):
        for router in ('../../x', 'nessuno', '/etc', 5):
            with self.subTest(router=router):
                self.assertEqual(400, self.anteprima('costo_ospf', {'router': router, 'interfaccia': 'eth1', 'costo': 5})[0])
        self.assertEqual(400, self.anteprima('sposta_interfaccia', {
            'dispositivo': 'client', 'dev': 'eth0', 'nuova_lan': 'B\nr9[0]=X'})[0])
        self.assertEqual(400, self.anteprima('costo_ospf', {'router': 'r1', 'interfaccia': 'eth1\n  ip ospf x', 'costo': 5})[0])

    def test_valori_sbagliati_e_operazione_impossibile(self):
        self.assertEqual(422, self.anteprima('costo_ospf', {'router': 'r1', 'interfaccia': 'eth1', 'costo': 'abc'})[0])
        codice, r = self.anteprima('costo_ospf', {'router': 'r1', 'interfaccia': 'eth1', 'costo': 0})
        self.assertEqual(422, codice)
        self.assertIn('costo', r['errore'].lower())

    def test_lab(self):
        for lab in ('..', '../papillon_mio', 'nessuno', ''):
            with self.subTest(lab=lab):
                codice, _ = self.azione(azione='anteprima', lab=lab, operazione='costo_ospf',
                                        parametri={'router': 'r1', 'interfaccia': 'eth1', 'costo': 5})
                self.assertEqual(400, codice)

    def test_intestazioni_e_corpo(self):
        corpo = {'azione': 'opzioni', 'lab': 'papillon_mio', 'operazione': 'costo_ospf'}
        self.assertEqual(200, self.richiesta('POST', '/api/azione', corpo)[0])
        self.assertEqual(403, self.richiesta('POST', '/api/azione', corpo, {'X-Lab-Gen': '0'})[0])
        self.assertEqual(403, self.richiesta('POST', '/api/azione', corpo, {'Host': 'esempio.it'})[0])
        self.assertEqual(403, self.richiesta('GET', '/api/stato_lab?nome=papillon_mio', None, {'Host': 'esempio.it'})[0])
        self.assertEqual(400, self.richiesta('POST', '/api/azione', grezzo=b'{non json')[0])
        self.assertEqual(400, self.richiesta('POST', '/api/azione', grezzo=b'[1, 2]')[0])
        codice, r = self.richiesta('POST', '/api/azione', intestazioni={'Content-Length': str(server.MAX_CORPO + 1)},
                                   grezzo=b'{}')
        self.assertEqual(413, codice, r)


class TestPianoDentroIlLab(unittest.TestCase):
    """Ultima difesa: un piano che toccherebbe file fuori dal lab viene rifiutato prima di scrivere."""

    def test_percorsi(self):
        from core.modifiche import nuovo_piano
        from gui import api
        with tempfile.TemporaryDirectory() as tmp:
            lab = os.path.join(tmp, 'lab')
            os.makedirs(lab)
            api._controlla_piano(lab, nuovo_piano('ok', {os.path.join('r1', 'x.conf'): (None, ['a'])}))
            for rel in (os.path.join('..', 'fuori'), os.path.join(tmp, 'assoluto'), '',
                        os.path.join('r1', '..', '..', 'fuori')):
                with self.subTest(rel=rel), self.assertRaises(api.ErroreApi):
                    api._controlla_piano(lab, nuovo_piano('no', {rel: (None, ['a'])}))
            with self.assertRaises(api.ErroreApi):
                api._controlla_piano(lab, nuovo_piano('no', {'r1': (['a'], None)}, spostati={'r1': '../r1'}))


class TestStatoEDisegno(ServerDiProva):

    def test_stato_lab(self):
        self.lab('candy_test')
        codice, s = self.richiesta('GET', '/api/stato_lab?nome=candy_test')
        self.assertEqual(200, codice, s)
        self.assertEqual('candy_test', s['nome'])
        self.assertIn('as10r1', s['stato']['dispositivi'])
        self.assertNotIn('testi', s['stato']['dispositivi']['as10r1'])
        self.assertEqual('10', s['modello']['routers']['as10r1']['asn'])
        self.assertIsInstance(s['avvisi'], list)
        self.assertIsNone(s['disegno'])
        self.assertEqual(400, self.richiesta('GET', '/api/stato_lab?nome=..')[0])

    def test_salva_disegno(self):
        p = self.lab('candy_test')
        disegno = {'posizioni': {'as10r1': [100, 200]}, 'zoom': 1.5}
        self.assertEqual(200, self.azione(azione='salva_disegno', lab='candy_test', disegno=disegno)[0])
        self.assertEqual(disegno, self.richiesta('GET', '/api/stato_lab?nome=candy_test')[1]['disegno'])
        self.assertFalse(any(f.endswith('.json') for f in os.listdir(p)), 'il disegno sta fuori dal lab')
        self.assertEqual(400, self.azione(azione='salva_disegno', lab='candy_test', disegno=[1])[0])

    def test_sposta_xml(self):
        p = self.lab('candy_test')
        dentro = os.path.join(p, 'candy_test.xml')
        with open(dentro, 'w', encoding='utf-8') as f:
            f.write('<lab/>\n')
        self.assertTrue(self.richiesta('GET', '/api/stato_lab?nome=candy_test')[1]['xml_nel_lab'])
        codice, r = self.azione(azione='sposta_xml', lab='candy_test')
        self.assertEqual(200, codice, r)
        self.assertTrue(r['spostato'])
        self.assertFalse(os.path.exists(dentro))
        self.assertTrue(os.path.isfile(supporto.percorso_xml(p)))
        self.assertFalse(self.azione(azione='sposta_xml', lab='candy_test')[1]['spostato'])


class TestLabNuovi(ServerDiProva):

    def test_valida(self):
        codice, r = self.azione(azione='valida_lab', modello=MODELLO, nome='piccolo')
        self.assertEqual(200, codice, r)
        self.assertEqual([], [p for p in r['problemi'] if p['gravita'] == 'errore'])
        self.assertIn('r1', r['completato']['routers'])
        sbagliato = json.loads(json.dumps(MODELLO))
        sbagliato['routers']['r2']['interfaces'][0]['ip'] = '10.0.0.1/30'      # IP già di r1
        codice, r = self.azione(azione='valida_lab', modello=sbagliato)
        self.assertTrue([p for p in r['problemi'] if p['gravita'] == 'errore'])
        self.assertEqual(400, self.azione(azione='valida_lab', modello={'routers': []})[0])

    def test_anteprima_e_creazione(self):
        codice, ant = self.azione(azione='anteprima_lab', nome='piccolo', modello=MODELLO)
        self.assertEqual(200, codice, ant)
        self.assertTrue(ant['creabile'])
        self.assertFalse(os.path.exists(os.path.join(self.base, 'piccolo')), "l'anteprima non scrive nella cartella dei lab")
        file = {f['file'] for f in ant['file']}
        self.assertTrue({'lab.conf', 'r1.startup', 'r1/etc/frr/frr.conf', 'pc1.startup'} <= file)
        self.assertFalse(any(f.endswith('.xml') for f in file))

        disegno = {'posizioni': {'r1': [10, 20]}}
        codice, r = self.azione(azione='crea_lab', nome='piccolo', modello=MODELLO, disegno=disegno)
        self.assertEqual(200, codice, r)
        self.assertTrue(r['creato'])
        p = os.path.join(self.base, 'piccolo')
        albero = c.leggi_albero(p)
        self.assertEqual({f['file']: c.normalizza(f['testo']) for f in ant['file']}, albero,
                         "si crea esattamente quello che l'anteprima mostra")
        self.assertEqual(disegno, self.richiesta('GET', '/api/stato_lab?nome=piccolo')[1]['disegno'])

        codice, r = self.azione(azione='crea_lab', nome='piccolo', modello=MODELLO)
        self.assertEqual((200, False, True), (codice, r['creato'], r['esiste']))
        codice, r = self.azione(azione='crea_lab', nome='piccolo', modello=MODELLO, sovrascrivi=True)
        self.assertTrue(r['creato'] and r['copia'])

    def test_nomi_non_validi(self):
        self.assertEqual(400, self.azione(azione='crea_lab', nome='../fuori', modello=MODELLO)[0])
        self.assertEqual(400, self.azione(azione='anteprima_lab', nome='Lab 1', modello=MODELLO)[0])
        m = json.loads(json.dumps(MODELLO))
        m['routers']['../r9'] = m['routers'].pop('r2')
        codice, r = self.azione(azione='crea_lab', nome='nomi', modello=m)
        self.assertEqual(422, codice, r)
        self.assertFalse(os.path.exists(os.path.join(self.base, 'nomi')))
        self.assertFalse(os.path.exists(os.path.join(self.base, 'r9')))

    def test_errori_del_modello(self):
        m = json.loads(json.dumps(MODELLO))
        m['routers']['r2']['interfaces'][0]['ip'] = '10.0.0.1/30'
        codice, r = self.azione(azione='crea_lab', nome='doppio', modello=m)
        self.assertEqual(200, codice, r)
        self.assertFalse(r['creato'])
        self.assertEqual('errori', r['motivo'])
        self.assertFalse(os.path.exists(os.path.join(self.base, 'doppio')))


if __name__ == '__main__':
    unittest.main()
