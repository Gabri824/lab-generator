"""
tests/test_stato.py
Test del lettore unico (src/core/stato.py).

- Sui lab prodotti dal generatore ogni riga di .startup e frr.conf viene riconosciuta.
- Il modello strutturato di frr.conf contiene le stesse informazioni dell'analizzatore di prima
  (_analizza_frr), su ogni frr.conf dei lab reali, degli scenari e (con LABGEN_ESERCIZI) delle
  soluzioni ufficiali.
- Il modello completo di ogni lab reale è uguale alla fotografia in tests/attesi/stato/.
"""
import json
import os
import re
import unittest

import _comune as c
from core import _analizza_frr
from core.stato import leggi_stato, righe

SUGGERIMENTO = "\n(se la modifica è voluta: python tests/strumenti/aggiorna_attesi.py stato)"


def _lab_del_generatore():
    """Lab reali e lab prodotti dagli scenari del wizard (già salvati in tests/attesi/scenari/)."""
    out = [(lab, os.path.join(c.FIXTURE_LABS, lab)) for lab in c.elenco_lab()]
    out += [(s, os.path.join(c.ATTESI, 'scenari', s)) for s in c.elenco_scenari()]
    return out


def piatto(m):
    """Il modello strutturato di un frr.conf nel formato di _analizza_frr."""
    o = {'asn': None, 'bgp_networks': [], 'neighbors': {}, 'descr': {}, 'link': {}, 'igp': {},
         'redistribute': {}, 'costi': [], 'prefix_lists': {}, 'access_lists': {}, 'route_maps': {},
         'auto_cost': None, 'default_orig': {}, 'default_igp': [], 'rip_route': []}
    b = m['bgp']
    if b:
        o['asn'] = b['asn']
        o['bgp_networks'] = [x['rete'] for x in b['network']]
        for ip, nb in b['neighbor'].items():
            if nb['remote_as'] is not None:
                o['neighbors'][ip] = nb['remote_as']
            if nb['descrizione'] is not None:
                o['descr'][ip] = nb['descrizione']
            if nb['default_originate']:
                o['default_orig'][ip] = nb['default_originate']['route_map'] or ''
            if nb['policy']:
                o['link'][ip] = [(p['tipo'], p['nome'], p['verso']) for p in nb['policy']]
        if b['redistribute']:
            o['redistribute']['bgp'] = [x['testo'] for x in b['redistribute']]
    for t in ('ospf', 'rip'):
        x = m[t]
        if not x:
            continue
        voci = [v['rete'] + (f" area {v['area']}" if v.get('area') else '') for v in x['network']]
        if t == 'ospf':
            voci += [f"area {s['area']} stub" for s in x['stub']]
            if x['auto_cost']:
                o['auto_cost'] = str(x['auto_cost']['valore'])
        o['igp'][t] = voci
        if x['redistribute']:
            o['redistribute'][t] = [r['testo'] for r in x['redistribute']]
        o['default_igp'] += [f"{t.upper()} {d['testo']}" for d in x['default_information']]
        if t == 'rip':
            o['default_igp'] += ['RIP route 0.0.0.0/0' for r in x['route'] if r['rete'] == '0.0.0.0/0']
            o['rip_route'] = [r['rete'] for r in x['route']]
    o['costi'] = [f"{dev} {v['costo_ospf']}" for dev, v in m['interfacce'].items() if v['costo_ospf'] is not None]
    o['prefix_lists'] = {k: [(e['azione'], e['rete']) for e in v] for k, v in m['prefix_list'].items()}
    o['access_lists'] = {k: [(e['azione'], e['rete']) for e in v] for k, v in m['access_list'].items()}
    o['route_maps'] = {k: [{'azione': e['azione'], 'seq': e['seq'], 'match': e['match'], 'set': e['set']}
                           for e in v] for k, v in m['route_map'].items()}
    return o


def _confrontabile(o):
    """Stessa forma per i due modelli: tuple come liste, ordine delle voci IGP irrilevante."""
    o = json.loads(json.dumps(o))
    o['igp'] = {k: sorted(v) for k, v in o['igp'].items()}
    o['default_igp'] = sorted(o['default_igp'])
    o['costi'] = sorted(o['costi'])
    return o


class TestLettoreUnico(unittest.TestCase):

    def test_righe_tutte_riconosciute(self):
        """Nei lab del generatore non ci sono righe che il lettore non capisce."""
        for nome, path in _lab_del_generatore():
            with self.subTest(lab=nome):
                nc = leggi_stato(path)['non_comprese']
                self.assertEqual([], nc, f"righe non riconosciute in {nome}")

    def test_interfacce_coerenti_con_startup(self):
        """Ogni 'ip address add ... dev ethN' compare sull'interfaccia giusta, con la sua LAN."""
        for nome, path in _lab_del_generatore():
            st = leggi_stato(path)
            for dn, d in st['dispositivi'].items():
                with self.subTest(lab=nome, dispositivo=dn):
                    for it in d['interfacce']:
                        self.assertEqual((d['ip_per_dev'].get(it['dev']) or [''])[0], it['ip'])
                        self.assertIn(dn, st['lan'][it['lan']]['membri'])
                        if it['ip']:
                            self.assertEqual(dn, st['proprietari'][it['ip'].split('/')[0]])

    def _confronta_frr(self, nome, path):
        for dn, d in leggi_stato(path)['dispositivi'].items():
            if not d['frr']:
                continue
            with self.subTest(lab=nome, dispositivo=dn):
                atteso = _confrontabile(_analizza_frr(righe(d['testi']['frr_conf'])))
                self.assertEqual(atteso, _confrontabile(piatto(d['frr'])))

    def test_frr_come_analizzatore_di_prima(self):
        for nome, path in _lab_del_generatore():
            self._confronta_frr(nome, path)

    def test_soluzioni_ufficiali(self):
        """Le soluzioni scritte a mano si leggono e il modello di frr.conf non perde nulla."""
        esercizi = c.cartella_esercizi()
        if not esercizi:
            self.skipTest(f"{c.VAR_ESERCIZI} non impostata")
        for nome, sol, tmp in c.soluzioni_lette(esercizi):
            try:
                self._confronta_frr(nome, sol)
            finally:
                if tmp:
                    tmp.cleanup()

    def test_router_di_confine_delle_soluzioni(self):
        """Puzzle, the-thing e clouds: dai file della soluzione al modello e di nuovo a frr.conf,
        le network OSPF con le loro aree e le aree stub di ogni router restano quelle."""
        esercizi = c.cartella_esercizi()
        igp = os.path.join(os.path.dirname(esercizi), 'lab-rip-ospf') if esercizi else None
        if not igp or not os.path.isdir(igp):
            self.skipTest(f"{c.VAR_ESERCIZI} non impostata o manca lab-rip-ospf accanto")
        import ipaddress
        import tempfile
        from core.generators import crea_router_files
        from core.persistence import dati_da_stato

        def ospf(testo):
            reti = sorted((str(ipaddress.ip_network(r, strict=False)), a)
                          for r, a in re.findall(r'^\s*network\s+(\S+)\s+area\s+(\S+)', testo, re.M))
            return reti, sorted(re.findall(r'^\s*area\s+(\S+)\s+stub', testo, re.M))
        for es in ('2020-11-27-puzzle', '2020-11-27-the-thing', '2022-11-04-clouds'):
            sol = os.path.join(igp, es, 'solution', 'lab')
            routers = dati_da_stato(leggi_stato(sol))[0]
            confine = [n for n, rd in routers.items() if rd.get('ospf_aree')]
            self.assertTrue(confine, f"{es}: nessun router di confine riconosciuto")
            with tempfile.TemporaryDirectory() as tmp:
                for n, rd in routers.items():
                    if 'ospf' not in rd['protocols']:
                        continue
                    with self.subTest(esercizio=es, router=n), c.silenzio():
                        crea_router_files(tmp, n, rd)
                        with open(os.path.join(sol, n, 'etc', 'frr', 'frr.conf'), encoding='utf-8') as f:
                            atteso = ospf(f.read())
                        with open(os.path.join(tmp, n, 'etc', 'frr', 'frr.conf'), encoding='utf-8') as f:
                            self.assertEqual(atteso, ospf(f.read()))

    def test_fotografia_del_modello(self):
        for lab in c.elenco_lab():
            with self.subTest(lab=lab):
                atteso = os.path.join(c.ATTESI, 'stato', lab + '.json')
                self.assertTrue(os.path.isfile(atteso), f"manca {atteso}" + SUGGERIMENTO)
                with open(atteso, encoding='utf-8', newline='') as fh:
                    self.assertEqual(fh.read(), c.produci_stato(os.path.join(c.FIXTURE_LABS, lab)),
                                     f"modello di {lab} cambiato" + SUGGERIMENTO)


if __name__ == '__main__':
    unittest.main()
