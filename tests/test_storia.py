"""
tests/test_storia.py
Annullare le modifiche (core/storia.py, operazione 'annulla') e ripristinare una copia di sicurezza:
- ogni operazione di prova del motore, applicata e poi annullata, lascia il lab identico a prima;
- più modifiche si annullano in ordine inverso; la rinomina rimette anche il disegno della GUI;
- un file cambiato dopo la modifica blocca l'annullamento senza scrivere nulla;
- stessa storia dal terminale (che normalizza le righe) e dalla GUI;
- lab ricreato o ripristinato da una copia: la storia si svuota.
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
from core import storia
from core.file_utils import _esegui_piano, elenco_copie, ripristina
from core.modifiche import scrivi_piano
from core.supporto import cartella_supporto, percorso_disegno
from test_operazioni import CASI


def _applica(p, piano):
    scrivi_piano(p, piano)
    with c.silenzio():
        op.dopo_scrittura(p, piano)


def _annulla(p):
    _applica(p, op.calcola_annulla(c.core.leggi_stato(p)))


class TestAnnullaOgniOperazione(unittest.TestCase):

    def test_torna_identico(self):
        for nome, (lab, calcola) in CASI.items():
            with self.subTest(operazione=nome), tempfile.TemporaryDirectory() as tmp:
                p = os.path.join(tmp, lab)
                shutil.copytree(os.path.join(c.FIXTURE_LABS, lab), p)
                prima = c.leggi_albero(p)
                _applica(p, calcola(c.core.leggi_stato(p)))
                self.assertNotEqual(prima, c.leggi_albero(p))
                self.assertEqual(1, len(storia.voci(p)))
                _annulla(p)
                self.assertEqual(prima, c.leggi_albero(p), 'dopo annulla il lab è com\'era')
                self.assertEqual([], storia.voci(p), "l'annullamento toglie la voce")


class TestStoria(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.lab = os.path.join(self._tmp.name, 'papillon_mio')
        shutil.copytree(os.path.join(c.FIXTURE_LABS, 'papillon_mio'), self.lab)
        for f in os.listdir(self.lab):
            if f.endswith('.xml'):
                os.remove(os.path.join(self.lab, f))

    def tearDown(self):
        self._tmp.cleanup()

    def st(self):
        return c.core.leggi_stato(self.lab)

    def test_ordine_inverso_e_rinomina(self):
        os.makedirs(cartella_supporto(self.lab), exist_ok=True)
        with open(percorso_disegno(self.lab), 'w', encoding='utf-8') as f:
            json.dump({'versione': 1, 'posizioni': {'d:r1': {'x': 1, 'y': 2}}, 'zone': []}, f)
        prima = c.leggi_albero(self.lab)
        _applica(self.lab, op.calcola_costo_ospf(self.st(), 'r1', 'eth1', 20))
        dopo_costo = c.leggi_albero(self.lab)
        _applica(self.lab, op.calcola_rinomina(self.st(), 'r1', 'core1'))
        with open(percorso_disegno(self.lab), encoding='utf-8') as f:
            self.assertIn('d:core1', json.load(f)['posizioni'])
        self.assertEqual(['Rinomina r1 -> core1', 'Costo OSPF di r1 eth1: 20'],
                         [v['titolo'] for v in storia.riassunto(self.lab)])
        inverso = op.calcola_annulla(self.st())
        self.assertEqual({os.path.join('core1', 'etc', 'frr', 'frr.conf'): os.path.join('r1', 'etc', 'frr', 'frr.conf')},
                         {a: b for a, b in inverso['spostati'].items() if a.endswith('frr.conf')},
                         "nell'anteprima i file tornano al posto di prima (spostati, non tolti e rifatti)")
        _applica(self.lab, inverso)
        self.assertEqual(dopo_costo, c.leggi_albero(self.lab))
        with open(percorso_disegno(self.lab), encoding='utf-8') as f:
            self.assertEqual({'d:r1': {'x': 1, 'y': 2}}, json.load(f)['posizioni'], 'il disegno torna al nome vecchio')
        _annulla(self.lab)
        self.assertEqual(prima, c.leggi_albero(self.lab))
        with self.assertRaises(op.ErroreOperazione):
            op.calcola_annulla(self.st())

    def test_file_cambiato_dopo(self):
        _applica(self.lab, op.calcola_costo_ospf(self.st(), 'r1', 'eth1', 20))
        frr = os.path.join(self.lab, 'r1', 'etc', 'frr', 'frr.conf')
        with open(frr, 'a', encoding='utf-8') as f:
            f.write('! scritto a mano\n')
        attuale = c.leggi_albero(self.lab)
        with self.assertRaises(op.ErroreOperazione) as e:
            op.calcola_annulla(self.st())
        self.assertIn('r1/etc/frr/frr.conf', str(e.exception))
        self.assertIn('copia di sicurezza', str(e.exception))
        self.assertEqual(attuale, c.leggi_albero(self.lab), 'non scrive nulla')
        self.assertEqual(1, len(storia.voci(self.lab)), 'la voce resta')

    def test_dal_terminale(self):
        """Dal terminale (_esegui_piano con la conferma) la modifica entra nella stessa storia e si
        annulla dal menu 14 delle Opzioni."""
        from core.routing_ops import menu_annulla
        prima = c.leggi_albero(self.lab)
        risposte = iter(['s'])
        with c.silenzio(), mock.patch.object(builtins, 'input', lambda *a: next(risposte)):
            self.assertTrue(_esegui_piano(self.lab, op.calcola_costo_ospf(self.st(), 'r2', 'eth1', 30)))
        self.assertEqual(1, len(storia.voci(self.lab)))
        risposte = iter(['1', 's'])
        with c.silenzio(), mock.patch.object(builtins, 'input', lambda *a: next(risposte)):
            self.assertTrue(menu_annulla(self.lab))
        self.assertEqual(prima, c.leggi_albero(self.lab))

    def test_limite(self):
        with mock.patch.object(storia, 'MASSIMO', 3):
            for k in range(5):
                _applica(self.lab, op.calcola_costo_ospf(self.st(), 'r1', 'eth1', 10 + k))
            self.assertEqual(['Costo OSPF di r1 eth1: 13 -> 14', 'Costo OSPF di r1 eth1: 12 -> 13', 'Costo OSPF di r1 eth1: 11 -> 12'],
                             [v['titolo'] for v in storia.riassunto(self.lab)])

    def test_storia_illeggibile(self):
        os.makedirs(cartella_supporto(self.lab), exist_ok=True)
        with open(storia.percorso_storia(self.lab), 'w') as f:
            f.write('{non json')
        self.assertEqual([], storia.voci(self.lab))
        _applica(self.lab, op.calcola_costo_ospf(self.st(), 'r1', 'eth1', 20))
        self.assertEqual(1, len(storia.voci(self.lab)), 'una storia rotta si riparte da capo')

    def test_fuori_dal_lab(self):
        _applica(self.lab, op.calcola_costo_ospf(self.st(), 'r1', 'eth1', 20))
        self.assertFalse(storia.percorso_storia(self.lab).startswith(self.lab + os.sep))
        self.assertTrue(os.path.isfile(storia.percorso_storia(self.lab)))

    def test_ripristino_svuota(self):
        _applica(self.lab, op.calcola_costo_ospf(self.st(), 'r1', 'eth1', 20))   # fa anche la copia
        dopo = c.leggi_albero(self.lab)
        copie = elenco_copie(self.lab)
        self.assertEqual(1, len(copie))
        with self.assertRaises(ValueError):
            ripristina(self.lab, '../../etc')
        prima_del = ripristina(self.lab, copie[0])
        self.assertNotIn('ospf cost 20', c.leggi_albero(self.lab)['r1/etc/frr/frr.conf'])
        self.assertEqual([], storia.voci(self.lab))
        self.assertEqual(dopo, c.leggi_albero(prima_del), 'lo stato di prima del ripristino è salvato')

    def test_lab_ricreato_svuota(self):
        _applica(self.lab, op.calcola_costo_ospf(self.st(), 'r1', 'eth1', 20))
        modello = {'routers': {'r1': {'protocols': ['ospf'], 'interfaces': [{'name': 'eth0', 'lan': 'A', 'ip': '10.0.0.1/24'}]}},
                   'hosts': [], 'wwws': []}
        with c.silenzio():
            e = c.core.genera_lab(self._tmp.name, 'papillon_mio', modello, sovrascrivi=True)
        self.assertTrue(e['creato'], e)
        self.assertEqual([], storia.voci(self.lab))


if __name__ == '__main__':
    unittest.main()
