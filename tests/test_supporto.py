"""
tests/test_supporto.py
File di supporto fuori dal lab (src/core/supporto.py): XML dei metadati in .labgenerator/<lab>/,
rigenerato dai file dopo ogni scrittura; spostamento dell'XML dei lab vecchi; posizioni del disegno
della GUI che seguono la rinomina di un dispositivo.
"""
import builtins
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import _comune as c
from core import operazioni as op
from core.modifiche import scrivi_piano
from core.persistence import load_lab_from_xml
from core.file_utils import _esegui_piano
from core.stato import leggi_stato
from core.supporto import cartella_supporto, percorso_disegno, percorso_xml, rinomina_nel_disegno, sposta_xml_fuori, xml_nel_lab


class TestDisegnoDopoLaRinomina(unittest.TestCase):
    """La Topologia usa le posizioni del disegno salvate con i nomi ('d:<nome>'): una rinomina, dal
    terminale o dalla GUI, sposta la posizione sul nome nuovo."""

    DISEGNO = {'versione': 1, 'posizioni': {'d:as40r1': {'x': 1, 'y': 2}, 'd:as10r1': {'x': 3, 'y': 4}, 'l:A': {'x': 5, 'y': 6}}, 'zone': []}

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.lab = os.path.join(self._tmp.name, 'candy_test')
        shutil.copytree(os.path.join(c.FIXTURE_LABS, 'candy_test'), self.lab)
        os.makedirs(cartella_supporto(self.lab), exist_ok=True)
        with open(percorso_disegno(self.lab), 'w', encoding='utf-8') as f:
            json.dump(self.DISEGNO, f)

    def tearDown(self):
        self._tmp.cleanup()

    def posizioni(self):
        with open(percorso_disegno(self.lab), encoding='utf-8') as f:
            return json.load(f)['posizioni']

    def test_strada_della_gui(self):
        piano = op.calcola_rinomina(leggi_stato(self.lab), 'as40r1', 'core1')
        scrivi_piano(self.lab, piano)
        with c.silenzio():
            op.dopo_scrittura(self.lab, piano)
        self.assertEqual({'d:core1': {'x': 1, 'y': 2}, 'd:as10r1': {'x': 3, 'y': 4}, 'l:A': {'x': 5, 'y': 6}}, self.posizioni())

    def test_strada_del_terminale(self):
        piano = op.calcola_rinomina(leggi_stato(self.lab), 'as40r1', 'core1')
        with c.silenzio(), mock.patch.object(builtins, 'input', lambda *a: 's'):
            self.assertTrue(_esegui_piano(self.lab, piano))
        self.assertIn('d:core1', self.posizioni())
        self.assertNotIn('d:as40r1', self.posizioni())

    def test_terminale_pagina_web(self):
        # dal terminale (stessa conferma 's'): la pagina del generatore segue il nome nuovo
        from core.generators import pagina_www
        with tempfile.TemporaryDirectory() as tmp:
            lab = os.path.join(tmp, 'papillon_mio')
            shutil.copytree(os.path.join(c.FIXTURE_LABS, 'papillon_mio'), lab)
            piano = op.calcola_rinomina(leggi_stato(lab), 'server', 'web1')
            with c.silenzio(), mock.patch.object(builtins, 'input', lambda *a: 's'):
                self.assertTrue(_esegui_piano(lab, piano))
            with open(os.path.join(lab, 'web1', 'var', 'www', 'html', 'index.html'), encoding='utf-8') as f:
                self.assertEqual(pagina_www('web1'), f.read().strip())

    def test_casi_senza_effetto(self):
        self.assertFalse(rinomina_nel_disegno(self.lab, 'nessuno', 'x'))
        self.assertFalse(rinomina_nel_disegno(self.lab, 'as40r1', 'as10r1'), 'il nome nuovo ha già una posizione')
        os.remove(percorso_disegno(self.lab))
        self.assertFalse(rinomina_nel_disegno(self.lab, 'as40r1', 'core1'))
        self.assertFalse(os.path.exists(percorso_disegno(self.lab)), 'senza disegno non se ne crea uno')


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
