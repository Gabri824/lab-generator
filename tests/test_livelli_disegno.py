"""
tests/test_livelli_disegno.py
Fase 5.6, livelli del disegno: i dati che la pagina riceve (gui/dati.py) e i segni calcolati da
static/js/livelli.js sui lab d'esame: sigle delle policy (lift, stairs), Customer-Provider-Peer
scritto da una parte sola, default route e ridistribuzione (galaxy), sessioni BGP (anche una
sbagliata), albero DNS e resolver (tennis).
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

import _comune as c
from core import operazioni as op
from core.modifiche import scrivi_piano
from gui import dati


def _segni(p):
    lab = dati.leggi_lab(c.core, p)
    r = subprocess.run(['node', os.path.join(c.TESTS, 'js', 'livelli_dati.mjs')], input=json.dumps({'lab': lab}),
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def _lab(nome):
    return os.path.join(c.FIXTURE_LABS, nome)


@unittest.skipUnless(shutil.which('node'), 'node non installato')
class TestLivelli(unittest.TestCase):

    def test_policy_di_lift_e_stairs(self):
        s = _segni(_lab('lift_mio'))
        self.assertEqual({('as300r1', '1.0.0.14', 'LP 150 in'), ('as300r1', '1.0.0.18', 'LP 150 in'), ('as100r1', '1.0.0.10', 'filtro in')},
                         {(x['router'], x['ip'], x['testo']) for x in s['policy']})
        s = _segni(_lab('stairs_mio'))
        self.assertEqual({'as1r2', 'as2r1', 'as3r2'}, {x['router'] for x in s['policy'] if x['testo'] == 'MED 20 out'})
        self.assertTrue(all(x['stato'] == 'ok' for x in s['sessioni']), [x for x in s['sessioni'] if x['stato'] != 'ok'])
        self.assertIn('iBGP', {x['tipo'] for x in s['sessioni']})

    def test_customer_provider_da_una_parte(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, 'candy_test')
            shutil.copytree(_lab('candy_test'), p)
            scrivi_piano(p, op.calcola_cpp(c.core.leggi_stato(p), 'as10r1', 'as40r1', '192.168.0.2', '40', 'provider', ['110.0.0.0/24']))
            s = _segni(p)
            self.assertIn({'customer': 'as10r1', 'provider': 'as40r1', 'lan': 'A'}, s['cpp'])
            self.assertEqual('filtro in · solo out', next(x['testo'] for x in s['policy'] if x['router'] == 'as10r1'),
                          'la prefix-list verso il provider lascia passare solo le reti scelte')

    def test_default_ridistribuzione_e_sessione_sbagliata(self):
        s = _segni(_lab('galaxy_mio'))
        self.assertEqual(2, len(s['segni']['as1r3']['default']))
        self.assertEqual(['OSPF'], s['segni']['as2r1']['redistribuisce'])
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, 'lift')
            shutil.copytree(_lab('lift_mio'), p)
            f = os.path.join(p, 'as200r1', 'etc', 'frr', 'frr.conf')
            with open(f, encoding='utf-8') as fh:
                testo = fh.read()
            with open(f, 'w', encoding='utf-8') as fh:
                fh.write(testo.replace('neighbor 1.0.0.6 remote-as 300', 'neighbor 1.0.0.6 remote-as 301'))
            ko = [x for x in _segni(p)['sessioni'] if x['stato'] == 'ko']
            self.assertEqual(1, len(ko))
            self.assertIn('remote-as 301', ko[0]['perche'])

    def test_dns_di_tennis(self):
        s = _segni(_lab('tennis_test'))
        self.assertIn({'da': 'root', 'a': 'ns_com', 'zona': 'com', 'ns': 'dns.com', 'ip': '20.1.0.3'}, s['dns'])
        self.assertTrue(any(v.startswith('ns: ') for v in s['resolver'].values()))


if __name__ == '__main__':
    unittest.main()
