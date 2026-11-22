"""
tests/test_terminale.py
"Apri terminale" della GUI (gui/kathara.apri_terminale) con terminali finti: piccoli script che
scrivono in un file con quali argomenti sono stati lanciati. Nessuna finestra vera.

- Prima il terminale impostato in Kathará (~/.config/kathara.conf), poi $TERMINAL, poi quelli noti.
- Ogni terminale riceve il comando nel modo che si aspetta (foot direttamente, alacritty con -e).
- Un terminale che esce subito con errore non conta: si prova il successivo.
"""
import json
import os
import stat
import tempfile
import unittest
import warnings
from unittest import mock

import _comune  # noqa: F401  (src nel percorso)
from gui import kathara


def _finto(cartella, nome, codice=0, attesa=1.5):
    """Terminale finto: scrive i suoi argomenti in <nome>.args, poi resta aperto o esce con `codice`."""
    p = os.path.join(cartella, nome)
    with open(p, 'w') as f:
        f.write('#!/bin/sh\nPATH=/usr/bin:/bin\n'
                f'printf "%s\\n" "$@" > "{p}.args"\n'
                + (f'exit {codice}\n' if codice else f'sleep {attesa}\n'))
    os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
    return p


def _argomenti(cartella, nome):
    with open(os.path.join(cartella, nome + '.args')) as f:
        return f.read().split('\n')[:-1]


@unittest.skipIf(os.name != 'posix', 'terminali finti scritti per sh')
class TestApriTerminale(unittest.TestCase):

    def setUp(self):
        # i terminali finti restano aperti come quelli veri: non è un processo dimenticato
        warnings.simplefilter('ignore', ResourceWarning)
        self.tmp = tempfile.TemporaryDirectory()
        self.bin = os.path.join(self.tmp.name, 'bin')
        self.casa = os.path.join(self.tmp.name, 'casa')
        os.makedirs(self.bin)
        os.makedirs(os.path.join(self.casa, '.config'))
        self.env = mock.patch.dict(os.environ, {'PATH': self.bin, 'HOME': self.casa, 'TERMINAL': ''})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def configura_kathara(self, terminale):
        with open(os.path.join(self.casa, '.config', 'kathara.conf'), 'w') as f:
            json.dump({'image': 'kathara/base', 'terminal': terminale}, f)

    def apri(self):
        return kathara.apri_terminale('/usr/bin/kathara', '/labs/papillon', 'r1')

    def test_terminale_di_kathara(self):
        # foot viene prima di alacritty nella lista fissa: vince comunque quello scelto in Kathará
        _finto(self.bin, 'foot')
        self.configura_kathara(_finto(self.bin, 'alacritty'))
        ok, msg, comando = self.apri()
        self.assertTrue(ok)
        self.assertIn('alacritty', msg)
        self.assertEqual(['-e', '/usr/bin/kathara', 'connect', '-d', '/labs/papillon', 'r1'], _argomenti(self.bin, 'alacritty'))
        self.assertEqual('kathara connect -d /labs/papillon r1', comando)

    def test_foot_riceve_il_comando_diretto(self):
        self.configura_kathara(_finto(self.bin, 'foot'))
        self.assertTrue(self.apri()[0])
        self.assertEqual(['/usr/bin/kathara', 'connect', '-d', '/labs/papillon', 'r1'], _argomenti(self.bin, 'foot'))

    def test_variabile_terminal_e_opzioni(self):
        # xterm è l'ultimo della lista fissa: con $TERMINAL=xterm viene prima di foot
        _finto(self.bin, 'foot')
        _finto(self.bin, 'xterm')
        os.environ['TERMINAL'] = 'xterm'
        ok, msg, _ = self.apri()
        self.assertTrue(ok)
        self.assertIn('xterm', msg)
        self.assertEqual(['-e', '/usr/bin/kathara', 'connect', '-d', '/labs/papillon', 'r1'], _argomenti(self.bin, 'xterm'))

    def test_ripiego_se_il_terminale_fallisce(self):
        self.configura_kathara(_finto(self.bin, 'rotto', codice=1))
        _finto(self.bin, 'xdg-terminal-exec')
        ok, msg, _ = self.apri()
        self.assertTrue(ok)
        self.assertIn('xdg-terminal-exec', msg)
        self.assertEqual(['/usr/bin/kathara', 'connect', '-d', '/labs/papillon', 'r1'], _argomenti(self.bin, 'xdg-terminal-exec'))

    def test_nessun_terminale(self):
        self.configura_kathara('/non/esiste/foot')
        ok, msg, comando = self.apri()
        self.assertFalse(ok)
        self.assertIn('copia il comando', msg)
        self.assertEqual('kathara connect -d /labs/papillon r1', comando)

    def test_conf_rovinato(self):
        with open(os.path.join(self.casa, '.config', 'kathara.conf'), 'w') as f:
            f.write('{non json')
        _finto(self.bin, 'konsole')
        ok, _, _ = self.apri()
        self.assertTrue(ok)
        self.assertEqual('-e', _argomenti(self.bin, 'konsole')[0])


if __name__ == '__main__':
    unittest.main()
