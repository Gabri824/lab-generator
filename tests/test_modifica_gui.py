"""
tests/test_modifica_gui.py
Modalità Modifica della GUI: stessi file del terminale.
- Fase 5.2: un dispositivo aggiunto dalla GUI (dati costruiti da proposte.datiDispositivo, come li
  manda il modulo) dà gli stessi file del terminale (Opzioni 13, domande del wizard), per router,
  host, server web e DNS (il primo DNS del lab è 'root', master per '.'). Il terminale risponde in
  base al testo di ogni domanda: una domanda nuova fa fallire il test.
- Fasi 5.3, 5.4 e 5.5: per ogni scenario BGP, DNS e policy del terminale (tests/operazioni/*.txt) la stessa
  modifica con i parametri costruiti dalla GUI dà esattamente il diff atteso del terminale.
"""
import builtins
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import _comune as c
from core import operazioni as op
from core.modifiche import scrivi_piano
from core.routing_ops import menu_dispositivi

NUMERO = {'router': '1', 'host': '2', 'www': '3', 'dns': '4'}

# (lab, tipo, valori del modulo della GUI, risposte del terminale per pezzo di domanda)
CASI = {
    'router_ospf': ('papillon_mio', 'router', {'nome': 'r8', 'lan': 'A', 'ip': '20.20.1.8/24', 'ospf': True, 'area': '0.0.0.0'},
                    {'Nome router': 'r8', 'Protocolli attivi': 'ospf', 'Area OSPF': '', 'Numero interfacce': '1',
                     'LAN associata': 'A', 'IP per': '20.20.1.8/24', 'Network OSPF': ''}),
    'router_rip': ('papillon_mio', 'router', {'nome': 'r9', 'lan': 'L', 'ip': '30.30.1.9/24', 'rip': True},
                   {'Nome router': 'r9', 'Protocolli attivi': 'rip', 'Numero interfacce': '1',
                    'LAN associata': 'L', 'IP per': '30.30.1.9/24', 'Network RIP': ''}),
    'host': ('papillon_mio', 'host', {'nome': 'pc2', 'lan': 'A', 'ip': '20.20.1.20/24', 'gateway': '20.20.1.1'},
             {'Nome host': 'pc2', 'Numero interfacce': '1', 'IP per': '20.20.1.20/24', 'LAN associata': 'A', 'Gateway': '20.20.1.1'}),
    'www': ('papillon_mio', 'www', {'nome': 'www2', 'lan': 'A', 'ip': '20.20.1.30/24', 'gateway': '20.20.1.1'},
            {'Nome webserver': 'www2', 'IP per': '20.20.1.30/24', 'Gateway': '20.20.1.1', 'LAN associata': 'A'}),
    'dns_root': ('papillon_mio', 'dns', {'nome': 'root', 'lan': 'A', 'ip': '20.20.1.31/24', 'gateway': '20.20.1.1'},
                 {'IP per': '20.20.1.31/24', 'Gateway': '20.20.1.1', 'LAN associata': 'A', 'Zone da delegare': ''}),
    'dns_secondo': ('tennis_test', 'dns', {'nome': 'ns_org', 'lan': 'G', 'ip': '20.1.0.9/24', 'gateway': '20.1.0.1'},
                    {'Nome host DNS': 'ns_org', 'IP per': '20.1.0.9/24', 'Gateway': '20.1.0.1', 'LAN associata': 'G',
                     'Aggiungere zone': '', "Tipo server per '.'": '', 'allow-recursion': '', 'DNSSEC': ''}),
}
COMUNI = [('Confermi le modifiche', 's'), ('Confermi?', ''), ('resolver del lab', ''), ('sessioni BGP', '')]


def _copia(tmp, lab, sotto):
    p = os.path.join(tmp, sotto, lab)
    shutil.copytree(os.path.join(c.FIXTURE_LABS, lab), p)
    for f in os.listdir(p):
        if f.endswith('.xml'):
            os.remove(os.path.join(p, f))
    return p


def _dal_terminale(p, tipo, risposte):
    menu = iter([NUMERO[tipo], '0'])
    domande = []

    def rispondi(prompt=''):
        domande.append(prompt)
        if 'Seleziona (numero)' in prompt:
            return next(menu)
        for chiave, r in list(risposte.items()) + COMUNI:
            if chiave in prompt:
                return r
        raise AssertionError(f"Domanda del terminale non prevista: {prompt!r}")
    with c.silenzio(), mock.patch.object(builtins, 'input', rispondi):
        menu_dispositivi(p, {})
    return domande


def _js(richiesta):
    r = subprocess.run(['node', os.path.join(c.TESTS, 'js', 'dati_gui.mjs'), json.dumps(richiesta)],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def _dalla_gui(p, tipo, valori):
    dati = _js({'tipo': tipo, 'valori': valori})
    piano = op.calcola_aggiungi_dispositivo(c.core.leggi_stato(p), tipo, dati, sessioni_bgp=True, resolver=True)
    scrivi_piano(p, piano)
    with c.silenzio():
        op.dopo_scrittura(p, piano)
    return dati


@unittest.skipUnless(shutil.which('node'), 'node non installato')
class TestAggiungiComeIlTerminale(unittest.TestCase):

    def test_stessi_file(self):
        for nome, (lab, tipo, valori, risposte) in CASI.items():
            with self.subTest(caso=nome), tempfile.TemporaryDirectory() as tmp:
                t, g = _copia(tmp, lab, 'terminale'), _copia(tmp, lab, 'gui')
                prima = c.leggi_albero(t)
                _dal_terminale(t, tipo, risposte)
                self.assertNotEqual(prima, c.leggi_albero(t), 'il terminale non ha aggiunto niente')
                dati = _dalla_gui(g, tipo, valori)
                self.assertEqual(c.leggi_albero(t), c.leggi_albero(g), f"dati della GUI: {dati}")


def _owner(st):
    return {it['ip'].split('/')[0]: n for n, d in st['dispositivi'].items() for it in d['interfacce'] if it['ip']}


def _neighbors(st, router):
    return op.opzioni_default_originate(st, router)['neighbors']


def _policy(router, neighbor, tipo, valori, asn_nuovo=None):
    return lambda st: dict({'router': router, 'neighbor': neighbor, 'asn_nuovo': asn_nuovo},
                           **_js({'funzione': 'parametriPolicy', 'argomenti': [tipo, valori]}))


def _cpp(router, vicino, relazione, valori=None):
    """Neighbor scelto dall'elenco della GUI (opzioni_policy_bgp); valori 'proposta' = le caselle
    come le spunta la GUI (reti proposte dal motore)."""
    def parametri(st):
        info = op.opzioni_policy_bgp(st, router)
        ip, nb = next((ip, nb) for ip, nb in info['neighbor'].items() if nb['dispositivo'] == vicino)
        v = {'r:' + r['rete']: r['proposta'] for r in info['reti']} if valori == 'proposta' else (valori or {})
        return dict({'router': router, 'vicino': vicino, 'ip': ip, 'asn': nb['remote_as']},
                    **_js({'funzione': 'parametriCpp', 'argomenti': [relazione, v]}))
    return parametri


# scenario del terminale -> (operazione, parametri della GUI calcolati sullo stato del lab)
BGP = {
    'network_bgp_aggregato': ('network_bgp', lambda st: {
        'router': 'as10r1', 'reti': _js({'funzione': 'listaReti', 'argomenti': ['110.0.0.0/16']}), 'togli_coperte': True}),
    'network_bgp': ('network_bgp', lambda st: {
        'router': 'as20r1', 'reti': _js({'funzione': 'listaReti', 'argomenti': ['20.0.0.0/8']}), 'togli_coperte': False}),
    'ibgp_full_mesh': ('ibgp', lambda st: {'asn': '2'}),
    'loopback_router': ('loopback', lambda st: {'dispositivo': 'as2r1', 'ip': '2.255.0.1'}),
    'default_originate': ('default_originate', lambda st: dict(
        {'router': 'as10r1', 'owner': _owner(st)},
        **_js({'funzione': 'parametriDefaultBgp', 'argomenti': [{'n:192.168.0.2': True, 'solo': True, 'extra': ''}, _neighbors(st, 'as10r1')]}))),
    'default_ospf': ('default_igp', lambda st: dict(
        {'router': 'r3', 'proto': 'ospf'}, **_js({'funzione': 'parametriDefaultIgp', 'argomenti': ['ospf', {'ha_default': True}]}))),
    'default_rip': ('default_igp', lambda st: dict(
        {'router': 'as6r1', 'proto': 'rip'}, **_js({'funzione': 'parametriDefaultIgp', 'argomenti': ['rip', {'modo': '1', 'rete': ''}]}))),
    'redistribuzione_route_map': ('redistribuzione_route_map', lambda st: {'router': 'r3', 'rete': '10.2.0.0/30'}),
    'redistribuzione_rimetti': ('redistribuzione', lambda st: {'router': 'as2r1', 'attiva': True}),
    'redistribuzione_togli': ('redistribuzione', lambda st: {'router': 'r4', 'attiva': False}),
    # fase 5.4: le Opzioni 5 e 9 (resolver e delega dal root)
    'resolver': ('resolver', lambda st: {'dispositivo': 'web_srv', 'ip': '1.0.0.2'}),
    'resolver_manuale': ('resolver', lambda st: {'dispositivo': 'pc', 'ip': '9.9.9.9'}),
    'delega_dns': ('delega_dns', lambda st: {'server': 'root', 'zona': 'org', 'ns': 'dns.org', 'ip': '20.1.0.9'}),
    # fase 5.5: le policy dell'Opzione 2 (parametri da proposte.parametriPolicy / parametriCpp)
    'policy_prefix_list': ('policy', _policy('as20r1', '192.168.0.10', 'prefix_list', {'direzione': 'out', 'altre': '20.0.0.0/8'})),
    'policy_prefix_list_aggiunge': ('policy', _policy('as10r1', '192.168.0.2', 'prefix_list', {'direzione': 'in', 'r:170.0.0.0/24': True})),
    'policy_prefix_list_nuovo_neighbor': ('policy', _policy('as20r1', '192.168.0.99', 'prefix_list', {'direzione': 'in', 'altre': '1.0.0.0/8'}, '99')),
    'policy_local_pref': ('policy', _policy('as40r1', '192.168.0.1', 'local_pref', {'valore': 120})),
    'policy_local_pref_reti': ('policy', _policy('as40r1', '192.168.0.5', 'local_pref', {'valore': '130', 'altre': '20.0.0.0/8'})),
    'policy_local_pref_sostituisce': ('policy', _policy('as50r1', '192.168.0.21', 'local_pref', {'valore': 150, 'r:160.0.0.0/24': False})),
    'policy_med': ('policy', _policy('as30r1', '192.168.0.14', 'med', {'valore': 20})),
    'policy_access_list': ('policy', _policy('as60r1', '192.168.0.18', 'access_list', {'altre': '10.0.0.0/8'})),
    'cpp_customer': ('cpp', _cpp('as40r1', 'as10r1', 'customer')),
    'cpp_peer': ('cpp', _cpp('as20r1', 'as50r1', 'peer', {'altre': '20.0.0.0/8'})),
    'cpp_provider': ('cpp', _cpp('as10r1', 'as40r1', 'provider', 'proposta')),
    'cpp_vicino_esterno': ('cpp', lambda st: dict({'router': 'as30r1', 'vicino': 'esterno', 'ip': '9.9.9.9', 'asn': '999'},
                                                  **_js({'funzione': 'parametriCpp', 'argomenti': ['customer', {}]}))),
}


@unittest.skipUnless(shutil.which('node'), 'node non installato')
class TestBgpComeIlTerminale(unittest.TestCase):

    def test_stesso_diff_del_terminale(self):
        for scenario, (operazione, parametri) in BGP.items():
            lab = c.leggi_operazione(scenario)['lab']
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as tmp:
                p = _copia(tmp, lab, 'gui')
                prima = c.leggi_albero(p)
                st = c.core.leggi_stato(p)
                piano = op.OPERAZIONI[operazione][1](st, **parametri(st))
                scrivi_piano(p, piano)
                with c.silenzio():
                    op.dopo_scrittura(p, piano)
                with open(os.path.join(c.ATTESI, 'operazioni', scenario + '.diff'), encoding='utf-8', newline='') as f:
                    self.assertEqual(f.read(), c.diff_testo(prima, c.leggi_albero(p)))



class TestOpzioniPolicy(unittest.TestCase):
    """Fase 5.5: relazioni Customer-Provider-Peer riconosciute (anche con i nomi delle soluzioni del
    corso, es. peerOut) e reti proposte per le prefix-list in uscita."""

    def test_relazioni_e_proposta(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _copia(tmp, 'candy_test', 'gui')
            piano = op.calcola_cpp(c.core.leggi_stato(p), 'as10r1', 'as40r1', '192.168.0.2', '40', 'provider', ['110.0.0.0/24'])
            scrivi_piano(p, piano)
            st = c.core.leggi_stato(p)
            qui = op.opzioni_policy_bgp(st, 'as10r1')['neighbor']['192.168.0.2']
            self.assertEqual(('provider', 'qui'), (qui['relazione'], qui['relazione_da']))
            la = op.opzioni_policy_bgp(st, 'as40r1')
            self.assertEqual(('customer', 'vicino'), (la['neighbor']['192.168.0.1']['relazione'], la['neighbor']['192.168.0.1']['relazione_da']),
                             "l'altro lato si ricava rovesciando quello scritto")
            # as40r1 ha un cliente (as10r1): il link con lui e la sua rete sono proposti, gli altri link no
            proposte = {r['rete']: (r['tipo'], r['proposta']) for r in la['reti']}
            self.assertEqual(('link', True), proposte['192.168.0.0/30'])
            self.assertEqual(('cliente', True), proposte['110.0.0.0/24'])
            self.assertEqual(('link', False), proposte['192.168.0.4/30'])
            self.assertIn({'rete': '160.0.0.0/24', 'router': 'as60r1', 'asn': '60'}, la['reti_lab'])

    def test_nomi_del_corso(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _copia(tmp, 'candy_test', 'gui')
            f = os.path.join(p, 'as20r1', 'etc', 'frr', 'frr.conf')
            with open(f, 'a', encoding='utf-8') as fh:
                fh.write('router bgp 20\n neighbor 192.168.0.10 prefix-list peerOut out\nip prefix-list peerOut permit any\n')
            nb = op.opzioni_policy_bgp(c.core.leggi_stato(p), 'as20r1')['neighbor']['192.168.0.10']
            self.assertEqual('peer', nb['relazione'])


if __name__ == '__main__':
    unittest.main()
