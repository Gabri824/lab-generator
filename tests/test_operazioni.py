"""
tests/test_operazioni.py
Le Opzioni come dati (src/core/operazioni.py): la strada della GUI (calcola_X + scrivi_piano)
deve produrre esattamente gli stessi file della strada del terminale (le operazioni in
tests/operazioni/, con i risultati in tests/attesi/operazioni/*.diff).
"""
import os
import shutil
import tempfile
import unittest

import _comune as c
from core import operazioni as op
from core.modifiche import scrivi_piano

# operazione del terminale -> (lab, calcolo equivalente con gli stessi parametri)
CASI = {
    'costo_ospf': ('papillon_mio', lambda st: op.calcola_costo_ospf(st, 'r1', 'eth1', 50)),
    'auto_cost_aggiungi': ('hourglass_test', lambda st: op.calcola_auto_cost(st, 'AS40')),
    'auto_cost_togli': ('papillon_mio', lambda st: op.calcola_auto_cost(st, 'AS20', togli=True)),
    'loopback_router': ('galaxy_mio', lambda st: op.calcola_loopback(st, 'as2r1', '2.255.0.1')),
    'loopback_ibgp': ('smile_test', lambda st: op.calcola_loopback(st, 'rabe1', '2.2.2.22')),
    'loopback_host': ('papillon_mio', lambda st: op.calcola_loopback(st, 'client', '9.9.9.9')),
    'network_bgp_aggregato': ('candy_test', lambda st: op.calcola_network_bgp(st, 'as10r1', ['110.0.0.0/16'], True)),
    'network_bgp': ('candy_test', lambda st: op.calcola_network_bgp(st, 'as20r1', ['20.0.0.0/8'])),
    'ibgp_full_mesh': ('galaxy_mio', lambda st: op.calcola_ibgp(st, '2')),
    'default_originate': ('candy_test', lambda st: op.calcola_default_originate(st, 'as10r1', ['192.168.0.2'], True)),
    'default_rip': ('garden_umbrella_mio', lambda st: op.calcola_default_igp(st, 'rip', 'as6r1')),
    'default_ospf': ('papillon_mio', lambda st: op.calcola_default_igp(st, 'ospf', 'r3', ha_default=True)),
    'redistribuzione_togli': ('hourglass_test', lambda st: op.calcola_redistribuzione(st, 'r4', False)),
    'redistribuzione_rimetti': ('tennis_test', lambda st: op.calcola_redistribuzione(st, 'as2r1', True)),
    'redistribuzione_route_map': ('hourglass_test',
                                  lambda st: op.calcola_redistribuzione_route_map(st, 'r3', '10.2.0.0/30')),
    'resolver': ('tennis_test', lambda st: op.calcola_resolver(st, 'web_srv', '1.0.0.2')),
    'resolver_manuale': ('tennis_test', lambda st: op.calcola_resolver(st, 'pc', '9.9.9.9')),
    'delega_dns': ('tennis_test', lambda st: op.calcola_delega_dns(st, 'root', 'org', '', '20.1.0.9')),
    'policy_prefix_list': ('candy_test', lambda st: op.calcola_policy(
        st, 'as20r1', '192.168.0.10', 'prefix_list', direzione='out', reti=['20.0.0.0/8'])),
    'policy_prefix_list_nuovo_neighbor': ('candy_test', lambda st: op.calcola_policy(
        st, 'as20r1', '192.168.0.99', 'prefix_list', direzione='in', reti=['1.0.0.0/8'], asn_nuovo='99')),
    'policy_prefix_list_aggiunge': ('candy_test', lambda st: op.calcola_policy(
        st, 'as10r1', '192.168.0.2', 'prefix_list', direzione='in', reti=['170.0.0.0/24'])),
    'policy_local_pref': ('candy_test', lambda st: op.calcola_policy(st, 'as40r1', '192.168.0.1', 'local_pref', valore=120)),
    'policy_local_pref_reti': ('candy_test', lambda st: op.calcola_policy(
        st, 'as40r1', '192.168.0.5', 'local_pref', valore=130, reti=['20.0.0.0/8'])),
    'policy_local_pref_sostituisce': ('candy_test', lambda st: op.calcola_policy(
        st, 'as50r1', '192.168.0.21', 'local_pref', valore=150)),
    'policy_med': ('candy_test', lambda st: op.calcola_policy(st, 'as30r1', '192.168.0.14', 'med', valore=20)),
    'policy_access_list': ('candy_test', lambda st: op.calcola_policy(
        st, 'as60r1', '192.168.0.18', 'access_list', reti=['10.0.0.0/8'])),
    'cpp_provider': ('candy_test', lambda st: op.calcola_cpp(
        st, 'as10r1', 'as40r1', '192.168.0.2', '40', 'provider', ['110.0.0.0/24'])),
    'cpp_customer': ('candy_test', lambda st: op.calcola_cpp(st, 'as40r1', 'as10r1', '192.168.0.1', '10', 'customer')),
    'cpp_peer': ('candy_test', lambda st: op.calcola_cpp(
        st, 'as20r1', 'as50r1', '192.168.0.10', '50', 'peer', ['20.0.0.0/8'])),
    'cpp_vicino_esterno': ('candy_test', lambda st: op.calcola_cpp(st, 'as30r1', 'esterno', '9.9.9.9', '999', 'customer')),
    # Modifica dispositivo: aggiornano anche l'XML dopo la scrittura (op.dopo_scrittura)
    'ip_interfaccia': ('candy_test', lambda st: op.calcola_ip_interfaccia(st, 'as10r1', 'eth1', '110.0.0.5')),
    'ip_cambia_rete_lan': ('candy_test', lambda st: op.calcola_ip_interfaccia(st, 'as10r1', 'eth0', '192.168.50.1/30')),
    'ip_cambia_rete_solo': ('candy_test', lambda st: op.calcola_ip_interfaccia(
        st, 'as10r1', 'eth0', '192.168.50.1/30', solo_questo=True)),
    'rinumera_lan': ('candy_test', lambda st: op.calcola_rinumera_lan(st, 'A', '192.168.100.0/30')),
    'sposta_interfaccia': ('papillon_mio', lambda st: op.calcola_sposta_interfaccia(
        st, 'client', 'eth0', 'B', '20.20.2.10/24')),
    'sposta_lan_nuova': ('papillon_mio', lambda st: op.calcola_sposta_interfaccia(st, 'client', 'eth0', 'Z')),
    'cambia_gateway': ('papillon_mio', lambda st: op.calcola_gateway(st, 'client', '20.20.1.254')),
    'gateway_fuori_rete': ('papillon_mio', lambda st: op.calcola_gateway(st, 'client', '10.9.9.9', forza=True)),
    'cambia_as': ('candy_test', lambda st: op.calcola_as(st, 'as10r1', '11')),
    'aggiungi_ospf': ('candy_test', lambda st: op.calcola_aggiungi_protocollo(st, 'as10r1', 'ospf')),
    'aggiungi_ospf_stub': ('candy_test', lambda st: op.calcola_aggiungi_protocollo(
        st, 'as20r1', 'ospf', area='1.1.1.1', stub=True)),
    'aggiungi_ospf_abr': ('candy_test', lambda st: op.calcola_aggiungi_protocollo(
        st, 'as10r1', 'ospf', reti=['192.168.0.0/30', '110.0.0.0/24'],
        aree={'192.168.0.0/30': '0.0.0.0', '110.0.0.0/24': '2.2.2.2'}, aree_stub=[])),
    'aggiungi_bgp': ('papillon_mio', lambda st: op.calcola_aggiungi_protocollo(st, 'r1', 'bgp', asn='20')),
    'aggiungi_bgp_sessioni': ('papillon_mio', lambda st: op.calcola_aggiungi_protocollo(st, 'r2', 'bgp', asn='20')),
    'togli_rip': ('garden_umbrella_mio', lambda st: op.calcola_togli_protocollo(st, 'as6r1', 'rip')),
    'togli_ospf': ('papillon_mio', lambda st: op.calcola_togli_protocollo(st, 'r3', 'ospf')),
    'togli_bgp': ('candy_test', lambda st: op.calcola_togli_protocollo(st, 'as10r1', 'bgp')),
    'rinomina': ('candy_test', lambda st: op.calcola_rinomina(st, 'as40r1', 'core1')),
    'aggiungi_router': ('candy_test', lambda st: op.calcola_aggiungi_dispositivo(st, 'router', {
        'name': 'as90r1', 'protocols': ['bgp'], 'asn': '90',
        'interfaces': [{'name': 'eth0', 'lan': 'L', 'ip': '110.0.0.9/24'}, {'name': 'eth1', 'lan': 'Q', 'ip': '190.0.0.1/24'}]})),
    'aggiungi_host': ('papillon_mio', lambda st: op.calcola_aggiungi_dispositivo(st, 'host', {
        'name': 'pc2', 'interfaces': [{'name': 'eth0', 'lan': 'A', 'ip': '20.20.1.20/24'}],
        'gateway': '20.20.1.1', 'gw_dev': 'eth0', 'ip': '20.20.1.20/24', 'lan': 'A'})),
    'aggiungi_dns': ('tennis_test', lambda st: op.calcola_aggiungi_dispositivo(st, 'dns', {
        'name': 'ns_org', 'ip': '20.1.0.9/24', 'gateway': '20.1.0.1', 'lan': 'G', 'dns': True, 'forwarders': None,
        'zones': None, 'root_type': 'hint', 'allow_recursion': None, 'dnssec_validation': False, 'delegations': []})),
    'togli_dispositivo': ('candy_test', lambda st: op.calcola_togli_dispositivo(st, 'as80r1')),
    'aggiungi_interfaccia': ('candy_test', lambda st: op.calcola_aggiungi_interfaccia(st, 'as10r1', 'Q', '190.0.0.1/24')),
    'togli_interfaccia': ('candy_test', lambda st: op.calcola_togli_interfaccia(st, 'as50r1', 'eth1')),
}


class TestStessiFileDelTerminale(unittest.TestCase):

    def test_calcola_e_scrivi(self):
        for nome, (lab, calcola) in CASI.items():
            with self.subTest(operazione=nome), tempfile.TemporaryDirectory() as tmp:
                p = os.path.join(tmp, lab)
                shutil.copytree(os.path.join(c.FIXTURE_LABS, lab), p)
                prima = c.leggi_albero(p)
                piano = calcola(c.core.leggi_stato(p))
                self.assertEqual(prima, c.leggi_albero(p), 'calcolare non deve cambiare nulla')
                self.assertTrue(scrivi_piano(p, piano)['scritto'])
                with c.silenzio():
                    op.dopo_scrittura(p, piano)
                with open(os.path.join(c.ATTESI, 'operazioni', nome + '.diff'), encoding='utf-8', newline='') as f:
                    self.assertEqual(f.read(), c.diff_testo(prima, c.leggi_albero(p)))

    def test_elenco_delle_operazioni(self):
        for nome, (opzioni, calcola) in op.OPERAZIONI.items():
            self.assertTrue(callable(opzioni) and callable(calcola), nome)

    def test_parametri_sbagliati(self):
        st = c.core.leggi_stato(os.path.join(c.FIXTURE_LABS, 'galaxy_mio'))
        with self.assertRaises(op.ErroreOperazione):
            op.calcola_ibgp(st, '999')
        with self.assertRaises(op.ErroreOperazione):
            op.calcola_costo_ospf(st, 'as2r1', 'eth0', 0)
        with self.assertRaises(op.ErroreOperazione):
            op.calcola_auto_cost(st, 'AS999')
        tennis = c.core.leggi_stato(os.path.join(c.FIXTURE_LABS, 'tennis_test'))
        with self.assertRaises(op.ErroreOperazione):
            op.calcola_delega_dns(tennis, 'ns_com', 'org', '', '1.2.3.4')     # non è il root
        with self.assertRaises(op.ErroreOperazione):
            op.calcola_resolver(tennis, 'pc', '1.2.3')

    def test_policy_parametri_sbagliati(self):
        candy = c.core.leggi_stato(os.path.join(c.FIXTURE_LABS, 'candy_test'))
        with self.assertRaises(op.ErroreOperazione):     # neighbor nuovo senza AS
            op.calcola_policy(candy, 'as20r1', '192.168.0.99', 'prefix_list', direzione='in', reti=['1.0.0.0/8'])
        with self.assertRaises(op.ErroreOperazione):
            op.calcola_policy(candy, 'as20r1', '192.168.0.10', 'prefix_list', direzione='su', reti=['1.0.0.0/8'])
        with self.assertRaises(op.ErroreOperazione):
            op.calcola_cpp(candy, 'as10r1', 'as40r1', '192.168.0.2', '40', 'amico')
        papillon = c.core.leggi_stato(os.path.join(c.FIXTURE_LABS, 'papillon_mio'))
        with self.assertRaises(op.ErroreOperazione):     # r1 non ha BGP
            op.calcola_policy(papillon, 'r1', '20.20.2.2', 'med', valore=5)

    def test_modifica_dispositivo_parametri_sbagliati(self):
        candy = c.core.leggi_stato(os.path.join(c.FIXTURE_LABS, 'candy_test'))
        with self.assertRaises(op.ErroreOperazione):     # IP già usato da as40r1
            op.calcola_ip_interfaccia(candy, 'as10r1', 'eth0', '192.168.0.2/30')
        with self.assertRaises(op.ErroreOperazione):     # indirizzo di rete
            op.calcola_ip_interfaccia(candy, 'as10r1', 'eth1', '110.0.0.0/24')
        with self.assertRaises(op.ErroreOperazione):
            op.calcola_as(candy, 'as10r1', '10')
        with self.assertRaises(op.ErroreOperazione):     # BGP c'è già
            op.calcola_aggiungi_protocollo(candy, 'as10r1', 'bgp', asn='10')
        with self.assertRaises(op.ErroreOperazione):
            op.calcola_gateway(candy, 'as10r1', '192.168.0.2')     # router
        papillon = c.core.leggi_stato(os.path.join(c.FIXTURE_LABS, 'papillon_mio'))
        with self.assertRaises(op.ErroreOperazione):     # fuori rete senza forza
            op.calcola_gateway(papillon, 'client', '10.9.9.9')
        with self.assertRaises(op.ErroreOperazione):
            op.calcola_righe(papillon, 'lab.conf', ['x'])

    def test_rinomina(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, 'candy_test')
            shutil.copytree(os.path.join(c.FIXTURE_LABS, 'candy_test'), p)
            st = c.core.leggi_stato(p)
            with self.assertRaises(op.ErroreOperazione):
                op.calcola_rinomina(st, 'as40r1', 'Core-1')          # non valido per Kathará
            with self.assertRaises(op.ErroreOperazione):
                op.calcola_rinomina(st, 'as40r1', 'as10r1')          # già usato
            with open(os.path.join(p, 'as40r1', 'immagine.bin'), 'wb') as f:
                f.write(b'\xff\xfe\x00binario')
            with self.assertRaises(op.ErroreOperazione):              # file non di testo nella cartella
                op.calcola_rinomina(st, 'as40r1', 'core1')
            os.remove(os.path.join(p, 'as40r1', 'immagine.bin'))
            scrivi_piano(p, op.calcola_rinomina(st, 'as40r1', 'core1'))
            self.assertFalse(os.path.exists(os.path.join(p, 'as40r1')), 'la cartella vecchia non resta')
            self.assertTrue(os.path.isfile(os.path.join(p, 'core1', 'etc', 'frr', 'frr.conf')))

    def test_rinomina_della_pagina_web(self):
        """La pagina index.html scritta dal generatore segue il nome nuovo del server web; una pagina
        cambiata a mano resta com'è (con una nota se cita ancora il nome vecchio)."""
        from core.generators import pagina_www
        casi = [
            (pagina_www('server'), pagina_www('web1'), False),                                  # del generatore
            (pagina_www('server') + '\n', pagina_www('web1'), False),                          # con l'a capo finale
            ('<html><body><h1>Benvenuti su server</h1></body></html>', None, True),         # scritta a mano, col nome
            ('<html><body><h1>Benvenuti</h1></body></html>', None, False),                  # scritta a mano, senza nome
        ]
        for prima, attesa, nota in casi:
            with self.subTest(pagina=prima), tempfile.TemporaryDirectory() as tmp:
                p = os.path.join(tmp, 'papillon_mio')
                shutil.copytree(os.path.join(c.FIXTURE_LABS, 'papillon_mio'), p)
                with open(os.path.join(p, 'server', 'var', 'www', 'html', 'index.html'), 'w', encoding='utf-8') as f:
                    f.write(prima)
                piano = op.calcola_rinomina(c.core.leggi_stato(p), 'server', 'web1')
                scrivi_piano(p, piano)
                with open(os.path.join(p, 'web1', 'var', 'www', 'html', 'index.html'), encoding='utf-8') as f:
                    self.assertEqual(attesa or prima.strip(), f.read().strip())
                self.assertEqual(nota, any('index.html non aggiornato' in n for n in piano['note']), piano['note'])

    def test_correzione_dei_nomi_non_validi(self):
        """correggi_nomi_lab usa la rinomina: 'as60-r1' (non valido) diventa 'as60_r1' ovunque."""
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, 'candy_test')
            shutil.copytree(os.path.join(c.FIXTURE_LABS, 'candy_test'), p)
            os.rename(os.path.join(p, 'as60r1'), os.path.join(p, 'as60-r1'))
            os.rename(os.path.join(p, 'as60r1.startup'), os.path.join(p, 'as60-r1.startup'))
            with open(os.path.join(p, 'lab.conf'), encoding='utf-8') as f:
                testo = f.read()
            with open(os.path.join(p, 'lab.conf'), 'w', encoding='utf-8') as f:
                f.write(testo.replace('as60r1[', 'as60-r1['))
            with c.silenzio():
                self.assertTrue(c.core.correggi_nomi_lab(p, interactive=False))
            st = c.core.leggi_stato(p)
            self.assertIn('as60_r1', st['dispositivi'])
            self.assertNotIn('as60-r1', st['dispositivi'])
            self.assertFalse(os.path.exists(os.path.join(p, 'as60-r1')))
            vicino = st['dispositivi']['as50r1']['frr']['bgp']['neighbor']['192.168.0.17']
            self.assertEqual('as60_r1', vicino['dispositivo'])

    def test_dispositivi_e_interfacce_parametri_sbagliati(self):
        candy = c.core.leggi_stato(os.path.join(c.FIXTURE_LABS, 'candy_test'))
        with self.assertRaises(op.ErroreOperazione):     # nome già usato
            op.calcola_aggiungi_dispositivo(candy, 'host', {'name': 'as10r1', 'interfaces': [
                {'lan': 'Q', 'ip': '190.0.0.10/24'}]})
        with self.assertRaises(op.ErroreOperazione):     # IP già usato
            op.calcola_aggiungi_dispositivo(candy, 'host', {'name': 'pc1', 'interfaces': [
                {'lan': 'A', 'ip': '192.168.0.1/30'}]})
        with self.assertRaises(op.ErroreOperazione):     # IP fuori dalla rete della LAN A
            op.calcola_aggiungi_interfaccia(candy, 'as20r1', 'A', '10.0.0.1/24')
        with self.assertRaises(op.ErroreOperazione):     # l'unica interfaccia
            op.calcola_togli_interfaccia(c.core.leggi_stato(os.path.join(c.FIXTURE_LABS, 'papillon_mio')), 'client', 'eth0')
        with self.assertRaises(op.ErroreOperazione):
            op.calcola_togli_dispositivo(candy, 'inesistente')

    def test_piano_vuoto(self):
        tennis = c.core.leggi_stato(os.path.join(c.FIXTURE_LABS, 'tennis_test'))
        piano = op.calcola_delega_dns(tennis, 'root', 'com', '', '20.1.0.3')    # com è già delegata
        self.assertEqual({}, piano['modifiche'])
        self.assertIn('già delegata', piano['vuoto'])


if __name__ == '__main__':
    unittest.main()


class TestMenuDaiFile(unittest.TestCase):
    """Fase 1.6: il menu Opzioni del terminale ricava i router dai file, non dall'XML."""

    def test_i_file_contano_piu_dell_xml(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, 'papillon_mio')
            shutil.copytree(os.path.join(c.FIXTURE_LABS, 'papillon_mio'), p)
            xml = os.path.join(p, 'papillon_mio.xml')
            with open(xml, encoding='utf-8') as f:
                xml_prima = f.read()
            # BGP aggiunto a r1 solo nei file (strada della GUI senza aggiornare l'XML)
            scrivi_piano(p, op.calcola_aggiungi_protocollo(c.core.leggi_stato(p), 'r1', 'bgp', asn='20'))
            with open(xml, encoding='utf-8') as f:
                self.assertEqual(xml_prima, f.read(), "l'XML non sa di BGP su r1")
            # Policies -> Prefix-list su r1: il router deve risultare con BGP
            stampato = c._con_risposte(['1', 'r1', '', '0'], lambda: c.core.policies_menu(p, None))
            self.assertNotIn('non ha BGP abilitato', stampato)
            self.assertIn('IP neighbor', stampato)

    def test_aprire_le_opzioni_non_crea_l_xml(self):
        with tempfile.TemporaryDirectory() as base:
            p = os.path.join(base, 'papillon_mio')
            shutil.copytree(os.path.join(c.FIXTURE_LABS, 'papillon_mio'), p)
            os.remove(os.path.join(p, 'papillon_mio.xml'))
            prima = c.leggi_albero(p)
            c._con_risposte(['1', '8', '0'], lambda: c.core.opzioni_laboratorio_menu(base))   # apre e fa il Riepilogo
            self.assertFalse(os.path.exists(os.path.join(p, 'papillon_mio.xml')))
            self.assertEqual(prima, c.leggi_albero(p), 'aprire le Opzioni non cambia nessun file')
