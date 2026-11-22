"""
tests/test_bozza.py
Bozza dell'editor grafico (src/gui/static/js/editor/bozza.js) -> modello del wizard -> lab.

- Ogni bozza di tests/bozze/ ridisegna uno scenario del wizard (tests/scenari/): convertita con
  Node e generata per la stessa strada della GUI (api.crea_lab: completa_lab + genera_lab), deve
  dare esattamente i file del wizard (tests/attesi/scenari/<scenario>/).
  ospf_multiarea_statiche non si può disegnare (la LAN A sta in due aree diverse, che valida_lab
  segnala come avviso): al suo posto c'è ospf_abr_statiche, lo stesso lab con la LAN A in una
  sola area e r2 router di confine.
- Le singole regole della bozza sono provate da tests/js/bozza.test.mjs, le azioni dell'editor da
  tests/js/azioni.test.mjs.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

import _comune as c
from gui import api

BOZZE = os.path.join(c.TESTS, 'bozze')


def elenco_bozze():
    return sorted(f[:-5] for f in os.listdir(BOZZE) if f.endswith('.json'))


def converti(nome):
    r = subprocess.run(['node', os.path.join(c.TESTS, 'js', 'converti_bozza.mjs'), os.path.join(BOZZE, nome + '.json')],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


class _Registro:
    def annota(self, *a):
        pass


class _Stato:
    def __init__(self, base):
        self.base = base
        self.lavori = _Registro()


@unittest.skipUnless(shutil.which('node'), 'node non installato')
class TestBozzaComeIlWizard(unittest.TestCase):

    def test_stessi_file_del_wizard(self):
        self.assertEqual({'bgp_ibgp_due_as', 'dns_root_auth_resolver', 'ospf_abr', 'ospf_abr_statiche'}, set(elenco_bozze()))
        for nome in elenco_bozze():
            with self.subTest(bozza=nome), tempfile.TemporaryDirectory() as tmp:
                r = converti(nome)
                self.assertEqual([], [p for p in r['problemi'] if p['gravita'] == 'errore'])
                with c.silenzio():
                    esito = api.crea_lab(_Stato(tmp), {'nome': nome, 'modello': r['modello']})
                self.assertTrue(esito['creato'], esito.get('errori'))
                atteso = c.leggi_albero(os.path.join(c.ATTESI, 'scenari', nome))
                fatto = c.leggi_albero(os.path.join(tmp, nome))
                self.assertEqual(atteso, fatto, c.diff_testo(atteso, fatto))

    def test_ogni_scenario_ha_la_sua_bozza(self):
        """Gli scenari del wizard hanno una bozza, tranne quello non disegnabile."""
        self.assertEqual(set(c.elenco_scenari()) - {'ospf_multiarea_statiche'}, set(elenco_bozze()))


@unittest.skipUnless(shutil.which('node'), 'node non installato')
class TestRegoleDellaBozza(unittest.TestCase):

    def test_node(self):
        for f in ('bozza.test.mjs', 'azioni.test.mjs'):
            with self.subTest(file=f):
                r = subprocess.run(['node', '--test', os.path.join(c.TESTS, 'js', f)], capture_output=True, text=True, timeout=120)
                self.assertEqual(0, r.returncode, r.stdout[-4000:] + r.stderr[-2000:])


if __name__ == '__main__':
    unittest.main()
