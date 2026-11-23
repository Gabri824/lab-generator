"""
tests/test_diagnosi.py
Diagnostica di frr.conf (core/frr_autofix.py) e la sua
operazione correggi_frr: sui lab di prova solo i problemi veri; un refuso, un riferimento a una
route-map sbagliato e un demone spento vengono trovati e la correzione li toglie (storia e
annulla come le altre operazioni); il terminale (Opzioni 15) scrive gli stessi file della GUI.
"""
import builtins
import os
import re
import shutil
import tempfile
import unittest
from unittest import mock

import _comune as c
from core import operazioni as op
from core import routing_ops
from core.modifiche import scrivi_piano


def _copia(tmp, lab):
    p = os.path.join(tmp, lab)
    shutil.copytree(os.path.join(c.FIXTURE_LABS, lab), p)
    return p


def _leggi(f):
    with open(f, encoding='utf-8') as fh:
        return fh.read()


def _cambia(p, rel, prima, dopo):
    f = os.path.join(p, rel)
    t = _leggi(f)
    n = re.sub(prima, dopo, t, flags=re.M)
    assert n != t, (rel, prima)
    with open(f, 'w', encoding='utf-8') as fh:
        fh.write(n)


def _problemi(p, dev):
    return op.opzioni_correggi_frr(c.core.leggi_stato(p), dev)


def _applica(p, dev, x, j=0):
    piano = op.calcola_correggi_frr(c.core.leggi_stato(p), dev, x['regola'], x['riga'], x['messaggio'], j)
    scrivi_piano(p, piano)
    with c.silenzio():
        op.dopo_scrittura(p, piano)
    return piano


class TestSoloProblemiVeri(unittest.TestCase):

    def test_lab_di_prova(self):
        atteso = {'test_laboratorio': {'frr.invalid_prefix_entry', 'frr.ref_undefined'},
                  'butterfly_test': {'bgp.missing_ibgp'}, 'galaxy_mio': {'bgp.missing_ibgp'}}
        for lab in c.elenco_lab():
            with self.subTest(lab=lab):
                st = c.core.leggi_stato(os.path.join(c.FIXTURE_LABS, lab))
                trovate = {x['regola'] for n in st['dispositivi'] for x in op.opzioni_correggi_frr(st, n)}
                self.assertEqual(atteso.get(lab, set()), trovate)


class TestCorrezioni(unittest.TestCase):

    def test_riferimento_sbagliato_e_annulla(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _copia(tmp, 'stairs_mio')
            prima = _leggi(os.path.join(p, 'as1r2/etc/frr/frr.conf'))
            _cambia(p, 'as1r2/etc/frr/frr.conf', r'neighbor 10\.0\.0\.6 route-map LOCALMED_OUT_10_0_0_6 out', 'neighbor 10.0.0.6 route-map LOCALMED_OUT out')
            ps = _problemi(p, 'as1r2')
            x = next(x for x in ps if x['regola'] in ('frr.ref_typo', 'frr.ref_undefined'))
            j = next(j for j, cc in enumerate(x['correzioni']) if 'LOCALMED_OUT_10_0_0_6' in cc['etichetta'] and 'Usa' in cc['etichetta'])
            _applica(p, 'as1r2', x, j)
            self.assertEqual(prima, _leggi(os.path.join(p, 'as1r2/etc/frr/frr.conf')))
            self.assertEqual([], [y for y in _problemi(p, 'as1r2') if y['gravita'] == 'errore'])
            # annulla come le altre operazioni
            piano = op.calcola_annulla(c.core.leggi_stato(p))
            scrivi_piano(p, piano)
            with c.silenzio():
                op.dopo_scrittura(p, piano)
            self.assertIn('route-map LOCALMED_OUT out', _leggi(os.path.join(p, 'as1r2/etc/frr/frr.conf')))

    def test_refuso_e_demone(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _copia(tmp, 'lift_mio')
            _cambia(p, 'as300r1/etc/frr/frr.conf', r'^(\s*)neighbor 1\.0\.0\.9 remote-as 100', r'\1neigbor 1.0.0.9 remote-as 100')
            x = next(x for x in _problemi(p, 'as300r1') if x['regola'] == 'frr.typo_cmd')
            _applica(p, 'as300r1', x)
            self.assertIn('neighbor 1.0.0.9 remote-as 100', _leggi(os.path.join(p, 'as300r1/etc/frr/frr.conf')))
            _cambia(p, 'as10r1/etc/frr/daemons', r'^ripd=yes', 'ripd=no')
            x = next(x for x in _problemi(p, 'as10r1') if x['regola'] == 'daemon.disabled')
            _applica(p, 'as10r1', x)
            self.assertRegex(_leggi(os.path.join(p, 'as10r1/etc/frr/daemons')), r'(?m)^ripd=yes')

    def test_problema_non_piu_presente(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _copia(tmp, 'lift_mio')
            with self.assertRaisesRegex(op.ErroreOperazione, 'rifai la diagnostica'):
                op.calcola_correggi_frr(c.core.leggi_stato(p), 'as300r1', 'frr.typo_cmd', 20, 'niente', 0)


class TestTerminale(unittest.TestCase):

    def test_stessi_file_della_gui(self):
        with tempfile.TemporaryDirectory() as tmp:
            g, t = os.path.join(tmp, 'g'), os.path.join(tmp, 't')
            for x in (g, t):
                os.makedirs(x)
                p = _copia(x, 'lift_mio')
                _cambia(p, 'as300r1/etc/frr/frr.conf', r'^(\s*)neighbor 1\.0\.0\.9 remote-as 100', r'\1neigbor 1.0.0.9 remote-as 100')
            pg, pt = os.path.join(g, 'lift_mio'), os.path.join(t, 'lift_mio')
            x = next(x for x in _problemi(pg, 'as300r1') if x['regola'] == 'frr.typo_cmd')
            _applica(pg, 'as300r1', x)
            nomi = sorted(c.core.leggi_stato(pt)['dispositivi'])
            k = 1 + [y['regola'] for y in _problemi(pt, 'as300r1')].index('frr.typo_cmd')
            risposte = iter([str(nomi.index('as300r1') + 1), f'{k}a', 's', '', '0'])
            with c.silenzio(), mock.patch.object(builtins, 'input', lambda *a: next(risposte)):
                routing_ops.menu_diagnostica(pt)
            self.assertEqual(c.leggi_albero(pg), c.leggi_albero(pt))


if __name__ == '__main__':
    unittest.main()
