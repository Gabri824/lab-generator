"""
tests/test_generazione.py
Test di genera_lab (src/core/generazione.py): creazione, sostituzione sicura, errori e interruzioni.
"""
import builtins
import os
import shutil
import tempfile
import unittest
from unittest import mock

import _comune as c
from core import generazione
from core.generazione import genera_lab, lab_conf_da_modello
from core.persistence import dati_da_stato, leggi_resolver
from core.supporto import percorso_xml


def _modello_scenario(nome):
    """Modello di uno scenario del wizard, ricavato dai suoi file."""
    stato = c.core.leggi_stato(os.path.join(c.ATTESI, 'scenari', nome))
    r, h, w = dati_da_stato(stato)
    return {'routers': r, 'hosts': h, 'wwws': w, 'resolver': c.core.resolver_da_stato(stato)}


class TestGeneraLab(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def residui(self):
        """Cartelle temporanee rimaste nella cartella dei lab (.labgenerator è quella di supporto)."""
        return [d for d in os.listdir(self.base) if d.startswith('.labgen-tmp-')]

    def copie(self, nome):
        d = os.path.join(self.base, '.backup_labgenerator', nome)
        return sorted(os.listdir(d)) if os.path.isdir(d) else []

    def lab_vecchio(self, nome='prova'):
        """Un lab già esistente da sostituire."""
        p = os.path.join(self.base, nome)
        shutil.copytree(os.path.join(c.FIXTURE_LABS, 'red_baron_test'), p)
        return p, c.leggi_albero(p)

    def test_crea_lab(self):
        esito = genera_lab(self.base, 'prova', _modello_scenario('bgp_ibgp_due_as'))
        self.assertTrue(esito['creato'])
        self.assertEqual([], esito['errori'])
        p = os.path.join(self.base, 'prova')
        for f in ('lab.conf', 'r1.startup', 'r1/etc/frr/frr.conf', 'pc1.startup'):
            self.assertTrue(os.path.isfile(os.path.join(p, f)), f)
        xml = percorso_xml(p)
        self.assertEqual(os.path.join(self.base, '.labgenerator', 'prova', 'prova.xml'), xml)
        self.assertTrue(os.path.isfile(xml), "l'XML sta fuori dal lab")
        self.assertFalse(os.path.exists(os.path.join(p, 'prova.xml')), "e non dentro")
        self.assertIn('Esportato XML: ' + xml, '\n'.join(esito['messaggi']),
                      'i messaggi riportano il percorso finale, non quello temporaneo')
        self.assertEqual([], self.residui())

    def test_lab_esistente_senza_sovrascrivere(self):
        p, prima = self.lab_vecchio()
        esito = genera_lab(self.base, 'prova', _modello_scenario('bgp_ibgp_due_as'))
        self.assertEqual((False, 'esiste'), (esito['creato'], esito['motivo']))
        self.assertEqual(prima, c.leggi_albero(p))
        self.assertEqual([], self.copie('prova'))

    def test_sostituzione_con_copia_di_sicurezza(self):
        p, prima = self.lab_vecchio()
        esito = genera_lab(self.base, 'prova', _modello_scenario('bgp_ibgp_due_as'), sovrascrivi=True)
        self.assertTrue(esito['creato'])
        self.assertTrue(os.path.isfile(os.path.join(p, 'pc1.startup')))
        self.assertFalse(os.path.exists(os.path.join(p, 'r10.startup')), 'i file del lab vecchio non restano')
        self.assertEqual(1, len(self.copie('prova')))
        self.assertEqual(prima, c.leggi_albero(esito['copia']), 'la copia contiene il lab di prima')
        self.assertEqual([], self.residui())

    def test_modello_con_errori(self):
        m = _modello_scenario('bgp_ibgp_due_as')
        m['routers']['r1']['interfaces'][0]['ip'] = '10.0.0.2/24'     # uguale a r2
        esito = genera_lab(self.base, 'prova', m)
        self.assertEqual((False, 'errori'), (esito['creato'], esito['motivo']))
        self.assertTrue(any(p['campo'] == 'r2.interfaces[0].ip' for p in esito['errori']), esito['errori'])
        self.assertFalse(os.path.exists(os.path.join(self.base, 'prova')))
        self.assertEqual([], self.residui())
        # l'import è tollerante: crea comunque
        self.assertTrue(genera_lab(self.base, 'prova', m, tollerante=True)['creato'])

    def test_errore_a_meta_lascia_il_lab_di_prima(self):
        p, prima = self.lab_vecchio()
        with mock.patch.object(generazione, 'auto_generate_bgp_neighbors', side_effect=RuntimeError('guasto')):
            with self.assertRaises(RuntimeError):
                genera_lab(self.base, 'prova', _modello_scenario('bgp_ibgp_due_as'), sovrascrivi=True)
        self.assertEqual(prima, c.leggi_albero(p))
        self.assertEqual([], self.copie('prova'))
        self.assertEqual([], self.residui())

    def test_scambio_finale_fallito_rimette_il_lab_di_prima(self):
        p, prima = self.lab_vecchio()
        vero = os.replace
        chiamate = []

        def replace(a, b):
            chiamate.append((a, b))
            if len(chiamate) == 2:            # il lab nuovo non si riesce a spostare
                raise OSError('file in uso')
            return vero(a, b)

        with mock.patch.object(generazione.os, 'replace', side_effect=replace):
            with self.assertRaises(OSError):
                genera_lab(self.base, 'prova', _modello_scenario('bgp_ibgp_due_as'), sovrascrivi=True)
        self.assertEqual(prima, c.leggi_albero(p))
        self.assertEqual([], self.residui())

    def test_resolver(self):
        esito = genera_lab(self.base, 'prova', _modello_scenario('dns_root_auth_resolver'))
        p = esito['percorso']
        self.assertEqual('resolver', leggi_resolver(percorso_xml(p)))
        for dev in ('host1', 'www1', 'root', 'dns_com', 'resolver'):
            with open(os.path.join(p, dev, 'etc', 'resolv.conf'), encoding='utf-8') as f:
                self.assertEqual('nameserver 10.0.1.53\n', f.read())

    def test_ordine_di_lab_conf(self):
        testo = lab_conf_da_modello(_modello_scenario('dns_root_auth_resolver'))
        ordine = [r.split('[')[0] for r in testo.splitlines() if r.endswith('[image]="kathara/base"')
                  or r.endswith('[image]="kathara/frr"')]
        self.assertEqual(['r1', 'host1', 'www1', 'root', 'dns_com', 'resolver'], ordine)


class TestWizardInterrotto(unittest.TestCase):
    """Se il wizard si ferma a metà, non resta nulla su disco e un lab da sostituire resta com'era."""

    def esegui(self, base, risposte):
        vero, builtins.input = builtins.input, lambda prompt='': risposte.pop(0)
        try:
            with c.silenzio():
                with self.assertRaises(IndexError):        # risposte finite = interruzione
                    c.core.esegui_wizard_nuovo_lab(base, 'prova')
        finally:
            builtins.input = vero

    def test_nessuna_cartella(self):
        with tempfile.TemporaryDirectory() as base:
            # i conteggi e metà del primo router, poi stop
            self.esegui(base, c.leggi_risposte('bgp_ibgp_due_as')[:12])
            self.assertEqual([], os.listdir(base))

    def test_lab_da_sostituire_intatto(self):
        with tempfile.TemporaryDirectory() as base:
            p = os.path.join(base, 'prova')
            shutil.copytree(os.path.join(c.FIXTURE_LABS, 'red_baron_test'), p)
            prima = c.leggi_albero(p)
            self.esegui(base, ['s'] + c.leggi_risposte('bgp_ibgp_due_as')[:12])
            self.assertEqual(prima, c.leggi_albero(p))
            self.assertEqual(['prova'], os.listdir(base))


if __name__ == '__main__':
    unittest.main()
