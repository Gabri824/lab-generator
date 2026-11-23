"""
tests/test_da_lab.py
Fase 5.7, "Parti da un lab esistente":
- ogni lab di prova (e, con LABGEN_ESERCIZI, ogni soluzione ufficiale) diventa una bozza che dà lo
  stesso modello del lab (editor/da_lab.js con la disposizione della Topologia), senza errori;
- creato senza toccare la bozza, il nuovo lab è identico al lab di partenza (righe delle Opzioni
  comprese); con un host in più nella bozza ci sono l'host nuovo e tutte le righe di prima;
- router con sole rotte statiche (crab) e resolver di un solo dispositivo (palabra, tennis) nel
  modello; il resolver di un dispositivo scritto dal modello è identico all'Opzione 5 del terminale.
"""
import copy
import ipaddress
import json
import os
import shutil
import subprocess
import tempfile
import unittest

import _comune as c
from core import operazioni as op
from core.modifiche import scrivi_piano
from core.persistence import modello_da_stato
from core.unione import leggi_albero
from gui import api


def _bozza(p):
    r = api.lab_come_modello(None, {'cartella': p})
    o = subprocess.run(['node', os.path.join(c.TESTS, 'js', 'da_lab_dati.mjs')], input=json.dumps(r), capture_output=True, text=True, timeout=120)
    if o.returncode:
        raise AssertionError(o.stderr)
    return r, json.loads(o.stdout)


def _anteprima(p, modello, m0, nomi=None):
    a = api.anteprima_lab({'nome': 'nuovo', 'modello': modello, 'origine': {'cartella': p, 'modello': m0, 'nomi': nomi or {}}})
    return a, {x['file']: x['testo'] for x in a['file']}


@unittest.skipUnless(shutil.which('node'), 'node non installato')
class TestDaLab(unittest.TestCase):

    def test_lab_di_prova(self):
        for lab in c.elenco_lab():
            p = os.path.join(c.FIXTURE_LABS, lab)
            with self.subTest(lab=lab):
                r, x = _bozza(p)
                self.assertEqual([], x['differenze'])
                self.assertEqual([], x['errori'])
                a, f = _anteprima(p, x['modello0'], x['modello0'])
                self.assertTrue(a['creabile'], a['errori'])
                self.assertEqual(leggi_albero(p), f, 'senza modifiche il nuovo lab è identico')

    def test_soluzioni_ufficiali(self):
        esercizi = c.cartella_esercizi()
        if not esercizi:
            self.skipTest(f"{c.VAR_ESERCIZI} non impostata")
        for nome, sol, tmp in c.soluzioni_lette(esercizi):
            with self.subTest(esercizio=nome):
                try:
                    r, x = _bozza(sol)
                    if r['senza_ip'] or x['errori']:
                        continue                  # data center senza IPv4, soluzioni con IP sbagliati
                    a, f = _anteprima(sol, x['modello0'], x['modello0'])
                    self.assertEqual(leggi_albero(sol), f)
                finally:
                    if tmp:
                        tmp.cleanup()

    def test_host_in_piu_e_righe_conservate(self):
        p = os.path.join(c.FIXTURE_LABS, 'stairs_mio')
        _, x = _bozza(p)
        m0 = x['modello0']
        m1 = copy.deepcopy(m0)
        m1['hosts'].append({'name': 'pcnuovo', 'interfaces': [{'name': 'eth0', 'lan': 'A', 'ip': '1.0.0.100/24'}], 'gateway': '1.0.0.1'})
        a, f = _anteprima(p, m1, m0)
        self.assertTrue(a['creabile'], a['errori'])
        self.assertIn('pcnuovo.startup', f)
        self.assertIn('pcnuovo[0]=A', f['lab.conf'])
        orig = leggi_albero(p)
        for rel, testo in orig.items():
            for riga in testo.split('\n'):
                self.assertIn(riga, f[rel].split('\n'), f"{rel}: riga persa {riga!r}")
        self.assertIn('set metric 20', f['as1r2/etc/frr/frr.conf'], 'il MED della soluzione resta')

    def test_ip_cambiato_avvisa(self):
        p = os.path.join(c.FIXTURE_LABS, 'lift_mio')
        _, x = _bozza(p)
        m0 = x['modello0']
        m1 = copy.deepcopy(m0)
        for it in m1['routers']['as400r1']['interfaces']:
            if it['ip'] == '1.0.0.14/30':
                it['ip'] = '1.0.0.13/30'
        for it in m1['routers']['as300r1']['interfaces']:
            if it['ip'] == '1.0.0.13/30':
                it['ip'] = '1.0.0.14/30'
        a, f = _anteprima(p, m1, m0)
        self.assertTrue(any('1.0.0.14' in t or '1.0.0.13' in t for t in a['unione']['avvisi']) or
                        'neighbor 1.0.0.14 route-map PREF_IN_1_0_0_14 in' in f['as300r1/etc/frr/frr.conf'])

    def test_crea_con_rinomina(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(os.path.join(c.FIXTURE_LABS, 'lift_mio'), os.path.join(tmp, 'lift'))
            st = type('St', (), {'base': tmp, 'lavori': type('L', (), {'annota': lambda *a: None})(),
                                 'lab_path': lambda self, n: os.path.join(tmp, n)})()
            _, x = _bozza(os.path.join(tmp, 'lift'))
            m0 = x['modello0']
            m1 = json.loads(json.dumps(m0).replace('as100r1', 'as100r9'))
            with c.silenzio():
                r = api.crea_lab(st, {'nome': 'lift2', 'modello': m1,
                                      'origine': {'lab': 'lift', 'modello': m0, 'nomi': {'as100r9': 'as100r1'}}})
            self.assertTrue(r['creato'], r)
            nuovo = leggi_albero(os.path.join(tmp, 'lift2'))
            self.assertIn('route-map FILTER_IN_1_0_0_10 permit 10', nuovo['as100r9/etc/frr/frr.conf'], 'il filtro segue il router rinominato')
            self.assertNotIn('as100r1.startup', nuovo)
            prima = leggi_albero(os.path.join(tmp, 'lift'))['as300r1/etc/frr/frr.conf']
            self.assertEqual(prima.replace('Router as100r1', 'Router as100r9'), nuovo['as300r1/etc/frr/frr.conf'],
                             'cambia solo la descrizione del neighbor rinominato; le local-preference restano')
            self.assertFalse(any(f.endswith('.xml') for f in os.listdir(os.path.join(tmp, 'lift2'))), "l'XML non è nel lab")


class TestModello(unittest.TestCase):

    def test_router_con_sole_statiche(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, 'st')
            os.makedirs(p)
            for nome, testo in {'lab.conf': 'r1[0]="A"\nr1[1]="B"\npc[0]="A"\n',
                                'r1.startup': 'ip address add 10.0.0.1/24 dev eth0\nip address add 10.0.1.1/24 dev eth1\n'
                                              'ip route add 30.0.0.0/24 via 10.0.1.2 dev eth1\n',
                                'pc.startup': 'ip address add 10.0.0.2/24 dev eth0\nip route add default via 10.0.0.1 dev eth0\n'}.items():
                with open(os.path.join(p, nome), 'w') as f:
                    f.write(testo)
            m = modello_da_stato(c.core.leggi_stato(p))
            self.assertEqual(['statico'], m['routers']['r1']['protocols'])
            self.assertEqual([{'network': '30.0.0.0/24', 'via': '10.0.1.2', 'dev': 'eth1'}], m['routers']['r1']['static_routes'])
            self.assertEqual(['pc'], [h['name'] for h in m['hosts']], 'un host con il solo gateway resta un host')

    def test_resolver_di_un_dispositivo_come_l_opzione_5(self):
        m = modello_da_stato(c.core.leggi_stato(os.path.join(c.FIXTURE_LABS, 'tennis_test')))
        pc = next(h for h in m['hosts'] if h['name'] == 'pc')
        self.assertEqual(['1.0.0.2'], pc['nameserver'])
        with tempfile.TemporaryDirectory() as tmp:
            senza = copy.deepcopy(m)
            del next(h for h in senza['hosts'] if h['name'] == 'pc')['nameserver']
            with c.silenzio():
                self.assertTrue(c.core.genera_lab(tmp, 'gui', m)['creato'])
                self.assertTrue(c.core.genera_lab(tmp, 'term', senza)['creato'])
            t = os.path.join(tmp, 'term')
            scrivi_piano(t, op.calcola_resolver(c.core.leggi_stato(t), 'pc', '1.0.0.2'))
            self.assertEqual(leggi_albero(t), leggi_albero(os.path.join(tmp, 'gui')))

    def test_resolver_nell_xml(self):
        from core.persistence import export_lab_to_xml, load_lab_from_xml, percorso_xml
        m = modello_da_stato(c.core.leggi_stato(os.path.join(c.FIXTURE_LABS, 'tennis_test')))
        with tempfile.TemporaryDirectory() as tmp, c.silenzio():
            export_lab_to_xml('x', tmp, m['routers'], m['hosts'], m['wwws'], resolver=m['resolver'], stampa=False)
            xml = percorso_xml(tmp, 'x')
            _, _, hosts, _, _ = load_lab_from_xml(xml)
        self.assertEqual(['1.0.0.2'], next(h for h in hosts if h['name'] == 'pc')['nameserver'])


if __name__ == '__main__':
    unittest.main()
