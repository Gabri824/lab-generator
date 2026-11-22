"""
tests/test_supporto.py
File di supporto fuori dal lab (src/core/supporto.py): XML dei metadati in .labgenerator/<lab>/,
rigenerato dai file dopo ogni scrittura; spostamento dell'XML dei lab vecchi.
"""
import os
import shutil
import tempfile
import unittest

import _comune as c
from core import operazioni as op
from core.modifiche import scrivi_piano
from core.persistence import load_lab_from_xml
from core.supporto import cartella_supporto, percorso_xml, sposta_xml_fuori, xml_nel_lab


class TestSupporto(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def copia(self, lab):
        p = os.path.join(self.base, lab)
        shutil.copytree(os.path.join(c.FIXTURE_LABS, lab), p)
        return p

    def test_percorsi(self):
        p = os.path.join(self.base, 'rossimario')
        self.assertEqual(os.path.join(self.base, '.labgenerator', 'rossimario'), cartella_supporto(p))
        self.assertEqual(os.path.join(self.base, '.labgenerator', 'rossimario', 'rossimario.xml'), percorso_xml(p))

    def test_xml_rigenerato_dopo_ogni_scrittura(self):
        p = self.copia('candy_test')
        os.remove(os.path.join(p, 'candy_test.xml'))
        piano = op.calcola_network_bgp(c.core.leggi_stato(p), 'as20r1', ['20.0.0.0/8'])
        scrivi_piano(p, piano)
        op.dopo_scrittura(p, piano)
        self.assertIsNone(xml_nel_lab(p), "nel lab non c'è nessun XML")
        _, routers, _, _, _ = load_lab_from_xml(percorso_xml(p))
        self.assertIn('20.0.0.0/8', routers['as20r1'].get('bgp_extra_networks', []),
                      "l'XML fuori dal lab riporta la network appena aggiunta")

    def test_sposta_xml_di_un_lab_vecchio(self):
        p = self.copia('papillon_mio')
        prima = {k: v for k, v in c.leggi_albero(p).items() if not k.endswith('.xml')}
        with open(os.path.join(p, 'papillon_mio.xml'), encoding='utf-8') as f:
            xml_dentro = f.read()
        fuori, copia = sposta_xml_fuori(p)
        self.assertIsNone(xml_nel_lab(p))
        self.assertEqual(percorso_xml(p), fuori)
        with open(fuori, encoding='utf-8') as f:
            self.assertEqual(xml_dentro, f.read())
        self.assertTrue(os.path.isfile(os.path.join(copia, 'papillon_mio.xml')), 'la copia di sicurezza ha il lab com\'era')
        self.assertEqual(prima, c.leggi_albero(p), 'gli altri file non cambiano')

    def test_le_opzioni_propongono_lo_spostamento(self):
        p = self.copia('papillon_mio')
        stampato = c._con_risposte(['1', 's', '0'], lambda: c.core.opzioni_laboratorio_menu(self.base))
        self.assertIn('va tolto prima della consegna', stampato)
        self.assertIsNone(xml_nel_lab(p))
        self.assertTrue(os.path.isfile(percorso_xml(p)))

    def test_le_opzioni_senza_spostare(self):
        p = self.copia('papillon_mio')
        prima = c.leggi_albero(p)
        c._con_risposte(['1', 'n', '0'], lambda: c.core.opzioni_laboratorio_menu(self.base))
        self.assertEqual(prima, c.leggi_albero(p))
        self.assertFalse(os.path.exists(cartella_supporto(p)))


if __name__ == '__main__':
    unittest.main()
