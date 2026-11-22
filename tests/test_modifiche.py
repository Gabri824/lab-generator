"""
tests/test_modifiche.py
Test del piano di modifica (src/core/modifiche.py): anteprima, scrittura sicura e conflitti.
"""
import os
import shutil
import stat
import tempfile
import unittest

import _comune as c
import builtins

from core.file_utils import _applica_modifiche, _righe_file
from core.modifiche import Conflitto, anteprima, nuovo_piano, scrivi_piano

LAB = 'candy_test'


class TestPianoDiModifica(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = self._tmp.name
        self.lab = os.path.join(self.base, LAB)
        shutil.copytree(os.path.join(c.FIXTURE_LABS, LAB), self.lab)

    def tearDown(self):
        self._tmp.cleanup()

    def righe(self, rel):
        return _righe_file(os.path.join(self.lab, rel))

    def copie(self):
        d = os.path.join(self.base, '.backup_labgenerator', LAB)
        return sorted(os.listdir(d)) if os.path.isdir(d) else []

    def file_temporanei(self):
        return [f for _, _, files in os.walk(self.base) for f in files if f.endswith('.labgen-tmp')]

    def piano_tipo(self):
        """Un file modificato, uno nuovo e uno eliminato."""
        frr = os.path.join('as10r1', 'etc', 'frr', 'frr.conf')
        vecchie = self.righe(frr)
        nuove = [l.replace('network 110.0.0.0/24', 'network 110.0.0.0/16') for l in vecchie]
        return nuovo_piano('Prova', {
            frr: (vecchie, nuove),
            'nuovo.startup': (None, ['ip address add 10.9.9.9/24 dev eth0']),
            'as80r1.startup': (self.righe('as80r1.startup'), None),
        }, note=['una nota']), frr, nuove

    def test_piano_vuoto_non_scrive(self):
        rel = 'as10r1.startup'
        piano = nuovo_piano('Niente', {rel: (self.righe(rel), self.righe(rel))})
        self.assertEqual({}, piano['modifiche'])
        self.assertFalse(scrivi_piano(self.lab, piano)['scritto'])
        self.assertEqual([], self.copie())

    def test_scrittura(self):
        piano, frr, nuove = self.piano_tipo()
        esito = scrivi_piano(self.lab, piano)
        self.assertTrue(esito['scritto'])
        self.assertEqual(nuove, self.righe(frr))
        self.assertEqual(['ip address add 10.9.9.9/24 dev eth0'], self.righe('nuovo.startup'))
        self.assertFalse(os.path.exists(os.path.join(self.lab, 'as80r1.startup')))
        self.assertEqual(['as10r1/etc/frr/frr.conf', 'as80r1.startup', 'nuovo.startup'], esito['file'])
        # la copia di sicurezza è fuori dal lab e contiene il lab com'era prima
        self.assertEqual(1, len(self.copie()))
        self.assertTrue(esito['copia'].startswith(os.path.join(self.base, '.backup_labgenerator')))
        self.assertTrue(os.path.isfile(os.path.join(esito['copia'], 'as80r1.startup')))
        self.assertEqual([], self.file_temporanei())

    @unittest.skipIf(os.name == 'nt', 'permessi di esecuzione solo su Linux e macOS')
    def test_startup_eseguibili(self):
        rel = 'as10r1.startup'
        path = os.path.join(self.lab, rel)
        os.chmod(path, 0o755)
        piano = nuovo_piano('Prova', {
            rel: (self.righe(rel), self.righe(rel) + ['# riga aggiunta']),
            'nuovo.startup': (None, ['# nuovo']),
        })
        scrivi_piano(self.lab, piano)
        for p in (path, os.path.join(self.lab, 'nuovo.startup')):
            self.assertTrue(os.stat(p).st_mode & stat.S_IXUSR, f"{p} non è più eseguibile")

    def test_conflitto_blocca_tutto(self):
        piano, frr, _ = self.piano_tipo()
        # l'altra interfaccia cambia il file dopo il calcolo del piano
        with open(os.path.join(self.lab, frr), 'a', encoding='utf-8') as f:
            f.write('! modificato dalla GUI\n')
        prima = c.leggi_albero(self.lab)
        with self.assertRaises(Conflitto) as e:
            scrivi_piano(self.lab, piano)
        self.assertEqual([frr], e.exception.file)
        self.assertEqual(prima, c.leggi_albero(self.lab), 'nessun file deve cambiare')
        self.assertEqual([], self.copie(), 'nessuna copia di sicurezza')

    def test_conflitto_file_nuovo_gia_creato(self):
        piano = nuovo_piano('Prova', {'nuovo.startup': (None, ['# nuovo'])})
        with open(os.path.join(self.lab, 'nuovo.startup'), 'w', encoding='utf-8') as f:
            f.write('# creato nel frattempo\n')
        with self.assertRaises(Conflitto):
            scrivi_piano(self.lab, piano)

    def test_anteprima(self):
        piano, frr, _ = self.piano_tipo()
        ant = {f['file']: f for f in anteprima(piano)}
        self.assertEqual(['as10r1/etc/frr/frr.conf', 'as80r1.startup', 'nuovo.startup'], sorted(ant))
        self.assertEqual('modificato', ant['as10r1/etc/frr/frr.conf']['stato'])
        self.assertEqual('nuovo', ant['nuovo.startup']['stato'])
        self.assertEqual('eliminato', ant['as80r1.startup']['stato'])
        righe = ant['as10r1/etc/frr/frr.conf']['righe']
        self.assertEqual([('-', 16, '    network 110.0.0.0/24'), ('+', 16, '    network 110.0.0.0/16')],
                         [(r['segno'], r['numero'], r['testo']) for r in righe])
        self.assertTrue(all(r['segno'] == '+' for r in ant['nuovo.startup']['righe']))
        self.assertTrue(all(r['segno'] == '-' for r in ant['as80r1.startup']['righe']))


    def test_anteprima_dei_file_spostati(self):
        rel = 'as80r1.startup'
        righe = self.righe(rel)
        piano = nuovo_piano('Sposta', {rel: (righe, None), 'nuovo.startup': (None, righe + ['# in più'])},
                            spostati={rel: 'nuovo.startup'})
        ant = anteprima(piano)
        self.assertEqual(1, len(ant))
        self.assertEqual(('nuovo.startup', 'spostato', 'as80r1.startup'), (ant[0]['file'], ant[0]['stato'], ant[0]['da']))
        self.assertEqual([('+', len(righe) + 1, '# in più')], [(r['segno'], r['numero'], r['testo']) for r in ant[0]['righe']])

    def test_terminale_file_cambiato_durante_la_conferma(self):
        """Mentre il terminale aspetta 'Confermi?', il file viene cambiato altrove: non scrive nulla."""
        rel = 'as10r1.startup'
        path = os.path.join(self.lab, rel)
        vecchie = self.righe(rel)

        def risposta(prompt=''):
            with open(path, 'a', encoding='utf-8') as f:
                f.write('# aggiunta dalla GUI\n')
            return 's'

        vero, builtins.input = builtins.input, risposta
        try:
            with c.silenzio() as out:
                scritto = _applica_modifiche(self.lab, {rel: (vecchie, vecchie + ['# dal terminale'])}, 'Prova')
        finally:
            builtins.input = vero
        self.assertFalse(scritto)
        self.assertIn('Nel frattempo sono cambiati: as10r1.startup', out.getvalue())
        self.assertEqual(vecchie + ['# aggiunta dalla GUI'], self.righe(rel))
        self.assertEqual([], self.copie())


    def test_file_in_memoria(self):
        """Dentro file_virtuali gli aiutanti di scrittura non toccano il disco."""
        from core.file_utils import _rimuovi_righe, append_frr_stanza, file_virtuali, insert_lines_into_protocol_block
        frr = os.path.join(self.lab, 'as10r1', 'etc', 'frr', 'frr.conf')
        prima = c.leggi_albero(self.lab)
        with file_virtuali(self.lab) as fs:
            insert_lines_into_protocol_block(frr, proto='bgp', lines=['network 9.9.9.0/24'])
            append_frr_stanza(self.lab, 'as10r1', 'interface eth0\n    ospf cost 7\n')
            _rimuovi_righe(frr, lambda l: 'debug bgp keepalives' in l)
            modifiche = fs.modifiche()
        self.assertEqual(prima, c.leggi_albero(self.lab), 'il disco non deve cambiare')
        rel = os.path.join('as10r1', 'etc', 'frr', 'frr.conf')
        self.assertEqual([rel], list(modifiche))
        vecchie, nuove = modifiche[rel]
        self.assertEqual(self.righe(rel), vecchie)
        self.assertIn('    network 9.9.9.0/24', nuove)
        self.assertIn('    ospf cost 7', nuove)
        self.assertNotIn('debug bgp keepalives', nuove)
        # le stesse operazioni fatte sul disco danno le stesse righe
        insert_lines_into_protocol_block(frr, proto='bgp', lines=['network 9.9.9.0/24'])
        append_frr_stanza(self.lab, 'as10r1', 'interface eth0\n    ospf cost 7\n')
        _rimuovi_righe(frr, lambda l: 'debug bgp keepalives' in l)
        self.assertEqual(nuove, self.righe(rel))


if __name__ == '__main__':
    unittest.main()
