"""
tests/test_archivio.py
Archivio per la consegna (src/core/archivio.py): solo i file della configurazione.
"""
import os
import shutil
import tarfile
import tempfile
import unittest
import zipfile

import _comune as c
from core.archivio import contenuto_archivio, crea_archivio

LAB = 'tennis_test'
RESIDUI = [
    '.nota.txt',                                  # file nascosto
    '.git/config',                                # cartella nascosta
    'as1r1/etc/frr/frr.conf~',                    # copia di un editor
    'as1r1/etc/frr/.frr.conf.swp',                # file di vim
    '__pycache__/x.pyc',
]


class TestArchivio(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = self._tmp.name
        self.lab = os.path.join(self.base, LAB)
        shutil.copytree(os.path.join(c.FIXTURE_LABS, LAB), self.lab)      # ha l'XML dentro e shared/ vuota
        self.configurazione = sorted(
            f"{LAB}/{rel}" for rel in c.leggi_albero(self.lab) if not rel.endswith('.xml'))
        for rel in RESIDUI:
            p = os.path.join(self.lab, *rel.split('/'))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'w', encoding='utf-8') as f:
                f.write('residuo\n')

    def tearDown(self):
        self._tmp.cleanup()

    def file_archiviati(self, dest):
        if dest.endswith('.zip'):
            return sorted(n for n in zipfile.ZipFile(dest).namelist() if not n.endswith('/'))
        with tarfile.open(dest) as t:
            return sorted(m.name for m in t.getmembers() if m.isfile())

    def test_solo_i_file_della_configurazione(self):
        for formato in ('tar.gz', 'zip'):
            with self.subTest(formato=formato):
                dest, file, comando, esclusi = crea_archivio(self.base, LAB, LAB, formato)
                self.assertEqual(self.configurazione, self.file_archiviati(dest))
                self.assertEqual(self.configurazione, sorted(file))
                for e in (f"{LAB}/{LAB}.xml", f"{LAB}/shared", f"{LAB}/.nota.txt", f"{LAB}/.git",
                          f"{LAB}/as1r1/etc/frr/frr.conf~", f"{LAB}/as1r1/etc/frr/.frr.conf.swp", f"{LAB}/__pycache__"):
                    self.assertIn(e, esclusi)
                self.assertIn(os.path.basename(dest), comando)

    def test_tar_senza_utenti(self):
        dest, *_ = crea_archivio(self.base, LAB, LAB, 'tar.gz')
        with tarfile.open(dest) as t:
            self.assertTrue(all(m.uid == 0 and m.uname == '' for m in t.getmembers()))

    def test_lab_senza_xml_dentro(self):
        os.remove(os.path.join(self.lab, f"{LAB}.xml"))
        _, esclusi = contenuto_archivio(self.base, LAB)
        self.assertNotIn(f"{LAB}/{LAB}.xml", esclusi)

    def test_dal_terminale(self):
        stampato = c._con_risposte(['', ''], lambda: c.core.archivio_menu(self.lab))      # nome e formato proposti
        dest = os.path.join(self.base, f"{LAB}.tar.gz")
        self.assertTrue(os.path.isfile(dest))
        self.assertEqual(self.configurazione, self.file_archiviati(dest))
        self.assertIn('Archivio creato', stampato)
        self.assertIn('Lasciati fuori', stampato)
        stampato = c._con_risposte(['consegna', 'z'], lambda: c.core.archivio_menu(self.lab))
        self.assertTrue(os.path.isfile(os.path.join(self.base, 'consegna.zip')))
        self.assertIn('la cartella si chiamerà tennis_test, non consegna', stampato)


if __name__ == '__main__':
    unittest.main()
