"""
tests/test_percorso_voluto.py
Fase 5.5b, "Percorso voluto": dai punti cliccati alle proposte di policy. Su lift e stairs
(Esami_IDC) senza policy, i percorsi chiesti dalle tracce devono dare le policy delle soluzioni:
- stairs: as4r2 -> 1.0.0.0/24 lungo H, F, B: i tre MED 20 sui link I, E, C;
- lift: as300r1 -> K via AS400 e -> L via AS500: local-preference 150 su as300r1;
  as100r1 -> K senza il link B, con il filtro in AS100: prefix-list deny su as100r1.
Le proposte, applicate con calcola_policy come fa la GUI, scrivono le stesse righe dei lab fatti
dal terminale (lift_mio, stairs_mio). A lab acceso (tabelle simulate) dove la strada è già quella
voluta non si propone niente.
"""
import os
import re
import shutil
import tempfile
import unittest

import _comune as c
from core import operazioni as op
from core.modifiche import scrivi_piano
from gui import dati
from gui import percorso_voluto as pv

_POLICY = re.compile(r'^\s*(route-map |set |match |access-list |ip prefix-list |neighbor \S+ (route-map|prefix-list) )')
D = lambda n: {'tipo': 'dev', 'nome': n}
LAN = lambda n: {'tipo': 'lan', 'nome': n}


def _senza_policy(tmp, lab):
    p = os.path.join(tmp, lab)
    shutil.copytree(os.path.join(c.FIXTURE_LABS, lab), p)
    for f in os.listdir(p):
        if f.endswith('.xml'):
            os.remove(os.path.join(p, f))
    for r in os.listdir(p):
        f = os.path.join(p, r, 'etc', 'frr', 'frr.conf')
        if os.path.exists(f):
            with open(f, encoding='utf-8') as fh:
                righe = [l for l in fh.read().split('\n') if not _POLICY.match(l)]
            with open(f, 'w', encoding='utf-8', newline='\n') as fh:
                fh.write('\n'.join(righe))
    return p


def _proposte(p, punti, vieta=(), tabelle=None):
    lab, stato = dati.leggi_lab(c.core, p), c.core.leggi_stato(p)
    return pv.proponi(pv.analizza(lab, punti), stato, vieta, tabelle)


def _righe_policy(p, router):
    with open(os.path.join(p, router, 'etc', 'frr', 'frr.conf'), encoding='utf-8') as f:
        return [l.strip() for l in f.read().split('\n') if _POLICY.match(l)]


class TestStairs(unittest.TestCase):

    def test_tre_med_come_la_soluzione(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _senza_policy(tmp, 'stairs_mio')
            r = _proposte(p, [D('as4r2'), LAN('J'), LAN('H'), LAN('G'), LAN('F'), LAN('D'), LAN('B'), LAN('A')])
            self.assertEqual(['4', '3', '2', '1'], r['sequenza'])
            self.assertEqual('1.0.0.0/24', r['rete'])
            self.assertEqual([('as3r2', '10.0.0.22'), ('as2r1', '10.0.0.10'), ('as1r2', '10.0.0.6')],
                             [(x['parametri']['router'], x['parametri']['neighbor']) for x in r['proposte']])
            self.assertTrue(all(x['parametri']['tipo'] == 'med' and x['parametri']['valore'] == 20 for x in r['proposte']))
            self.assertEqual({'dev': 'as4r2', 'ip': '1.0.0.1', 'atteso': 'H F B'}, r['verifica'])
            for x in r['proposte']:
                piano = op.calcola_policy(c.core.leggi_stato(p), **x['parametri'])
                scrivi_piano(p, piano)
            for router in ('as3r2', 'as2r1', 'as1r2'):
                self.assertEqual(_righe_policy(os.path.join(c.FIXTURE_LABS, 'stairs_mio'), router), _righe_policy(p, router))

    def test_lab_acceso_gia_cosi(self):
        """Tabelle simulate: se un AS usa già il link voluto, lì non si propone niente."""
        with tempfile.TemporaryDirectory() as tmp:
            p = _senza_policy(tmp, 'stairs_mio')
            punti = [D('as4r2'), LAN('H'), LAN('F'), LAN('B'), D('as1r1')]
            buona = lambda nh, asp: [{'best': True, 'aspath': asp, 'nexthop': nh, 'da': nh}]
            tabelle = {'as4r1': buona('10.0.0.17', '3 2 1'), 'as4r2': buona('10.0.0.17', '3 2 1'),
                       'as3r1': buona('10.0.0.9', '2 1'), 'as3r2': buona('10.0.0.9', '2 1'),     # AS3 usa E: non va
                       'as2r1': buona('10.0.0.1', '1'), 'as2r2': buona('10.0.0.1', '1')}
            r = _proposte(p, punti, tabelle=tabelle)
            self.assertEqual('tabelle', r['modo'])
            self.assertEqual([('as2r1', '10.0.0.10')], [(x['parametri']['router'], x['parametri']['neighbor']) for x in r['proposte']])
            self.assertTrue(any('AS4 usa già AS3 sul link H' in n for n in r['note']))


class TestLift(unittest.TestCase):

    def test_local_preference_su_as300r1(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _senza_policy(tmp, 'lift_mio')
            for punti, neighbor, rete in (([D('as300r1'), LAN('G'), LAN('K')], '1.0.0.14', '10.1.0.0/24'),
                                          ([D('as300r1'), LAN('D'), LAN('L')], '1.0.0.18', '10.2.0.0/24')):
                r = _proposte(p, punti)
                self.assertEqual([{'asn_nuovo': None, 'router': 'as300r1', 'neighbor': neighbor, 'tipo': 'local_pref',
                                   'valore': 150, 'reti': [rete]}], [x['parametri'] for x in r['proposte']])
                scrivi_piano(p, op.calcola_policy(c.core.leggi_stato(p), **r['proposte'][0]['parametri']))
            self.assertEqual(_righe_policy(os.path.join(c.FIXTURE_LABS, 'lift_mio'), 'as300r1'), _righe_policy(p, 'as300r1'))

    def test_filtro_solo_dove_chiesto(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _senza_policy(tmp, 'lift_mio')
            punti = [D('as100r1'), LAN('A'), LAN('C'), LAN('G'), LAN('K')]
            r = _proposte(p, punti, vieta=['100'])
            self.assertEqual(['100', '200', '300', '400', '10'], r['sequenza'])
            pl = [x['parametri'] for x in r['proposte'] if x['parametri']['tipo'] == 'prefix_list']
            self.assertEqual([{'asn_nuovo': None, 'router': 'as100r1', 'neighbor': '1.0.0.10', 'tipo': 'prefix_list',
                               'direzione': 'in', 'reti': ['10.1.0.0/24']}], pl, 'il filtro solo in AS100')
            self.assertIn(('as300r1', '1.0.0.14', 'local_pref'),
                          [(x['parametri']['router'], x['parametri']['neighbor'], x['parametri']['tipo']) for x in r['proposte']])
            senza = _proposte(p, punti)
            self.assertEqual(('as100r1', '1.0.0.2', 'local_pref'), tuple(senza['proposte'][0]['parametri'][k] for k in ('router', 'neighbor', 'tipo')),
                             'senza filtro: si preferisce AS200 e B resta di riserva')

    def test_local_preference_gia_scritta_si_somma(self):
        """Una seconda rete sulla stessa sessione non cancella la prima dalla route-map."""
        with tempfile.TemporaryDirectory() as tmp:
            p = _senza_policy(tmp, 'lift_mio')
            r = _proposte(p, [D('as300r1'), LAN('G'), LAN('K')])
            scrivi_piano(p, op.calcola_policy(c.core.leggi_stato(p), **r['proposte'][0]['parametri']))
            r = _proposte(p, [D('as300r1'), LAN('G'), LAN('L')])
            self.assertEqual(['10.1.0.0/24', '10.2.0.0/24'], r['proposte'][0]['parametri']['reti'])
            # e il percorso che va contro una local-preference già scritta lo dice
            r = _proposte(p, [D('as300r1'), LAN('M'), LAN('K')])
            self.assertTrue(any("c'è già una local-preference per 10.1.0.0/24" in n for n in r['note']))


class TestErrori(unittest.TestCase):

    def test_errori(self):
        lab = dati.leggi_lab(c.core, os.path.join(c.FIXTURE_LABS, 'lift_mio'))
        for punti, testo in (([D('as10r1'), LAN('K')], 'stesso AS'),
                             ([LAN('A'), LAN('K')], 'sorgente'),
                             ([D('as100r1')], 'almeno'),
                             ([D('as300r1'), LAN('G'), LAN('C'), LAN('K')], 'due volte')):
            with self.subTest(punti=punti), self.assertRaisesRegex(pv.ErrorePercorso, testo):
                pv.proponi(pv.analizza(lab, punti), c.core.leggi_stato(os.path.join(c.FIXTURE_LABS, 'lift_mio')))


if __name__ == '__main__':
    unittest.main()
