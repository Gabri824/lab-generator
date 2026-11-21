"""
tests/test_golden.py
Test di confronto: il codice attuale deve produrre esattamente i file salvati in tests/attesi/.

Se un test fallisce dopo una modifica voluta, controllare le differenze e, se sono giuste,
aggiornare i file attesi con tests/strumenti/aggiorna_attesi.py.

Esecuzione:  python -m unittest discover tests
Soluzioni ufficiali (facoltativo):  LABGEN_ESERCIZI=<percorso>/lab-bgp python -m unittest discover tests
"""
import json
import os
import unittest

import _comune as c

SUGGERIMENTO = "\n(se la modifica è voluta: python tests/strumenti/aggiorna_attesi.py)"


def _leggi(path):
    with open(path, encoding='utf-8', newline='') as fh:
        return fh.read()


class TestLettura(unittest.TestCase):
    """I tre lettori dei file restituiscono gli stessi dati di prima."""

    def test_lab_reali(self):
        for lab in c.elenco_lab():
            with self.subTest(lab=lab):
                atteso = os.path.join(c.ATTESI, 'lettura', lab + '.json')
                self.assertTrue(os.path.isfile(atteso), f"manca {atteso}" + SUGGERIMENTO)
                ottenuto = c.produci_lettura(os.path.join(c.FIXTURE_LABS, lab))
                self.assertEqual(_leggi(atteso), ottenuto, f"lettura di {lab} cambiata" + SUGGERIMENTO)

    def test_soluzioni_ufficiali_leggibili(self):
        """Le soluzioni scritte a mano dai docenti si leggono senza errori."""
        esercizi = c.cartella_esercizi()
        if not esercizi:
            self.skipTest(f"{c.VAR_ESERCIZI} non impostata")
        for nome, sol, tmp in c.soluzioni_lette(esercizi):
            with self.subTest(esercizio=nome):
                try:
                    with c.silenzio():
                        c.core.leggi_dispositivi(sol)
                        c.dati.leggi_lab(c.core, sol)
                finally:
                    if tmp:
                        tmp.cleanup()


class TestRigenerazione(unittest.TestCase):
    """Ricreare un lab dal suo XML produce gli stessi file di prima."""

    def test_lab_reali(self):
        for lab in c.elenco_lab():
            with self.subTest(lab=lab):
                cartella = os.path.join(c.ATTESI, 'rigenerazione', lab)
                self.assertTrue(os.path.isdir(cartella), f"manca {cartella}" + SUGGERIMENTO)
                diff = c.differenze_alberi(c.leggi_albero(cartella),
                                           c.produci_rigenerazione(os.path.join(c.FIXTURE_LABS, lab)))
                self.assertEqual('', diff, f"rigenerazione di {lab} cambiata:\n{diff}" + SUGGERIMENTO)


class TestOpzioni(unittest.TestCase):
    """La differenza tra lab rigenerato e lab reale (il lavoro fatto con le Opzioni) è ancora quella.

    È l'obiettivo che terminale e GUI dovranno saper riprodurre: se cambia, o è cambiata la
    rigenerazione o è cambiato un lab in tests/fixtures/.
    """

    def test_lab_reali(self):
        for lab in c.elenco_lab():
            with self.subTest(lab=lab):
                atteso = os.path.join(c.ATTESI, 'opzioni', lab + '.diff')
                self.assertTrue(os.path.isfile(atteso), f"manca {atteso}" + SUGGERIMENTO)
                path = os.path.join(c.FIXTURE_LABS, lab)
                ottenuto = c.produci_diff_opzioni(path, c.produci_rigenerazione(path))
                self.assertEqual(_leggi(atteso), ottenuto, f"differenza delle Opzioni di {lab} cambiata" + SUGGERIMENTO)


class TestScenari(unittest.TestCase):
    """Il wizard del terminale, con le risposte di tests/scenari/, produce gli stessi file di prima."""

    def test_scenari(self):
        scenari = c.elenco_scenari()
        self.assertTrue(scenari, 'nessuno scenario in tests/scenari/')
        for s in scenari:
            with self.subTest(scenario=s):
                cartella = os.path.join(c.ATTESI, 'scenari', s)
                self.assertTrue(os.path.isdir(cartella), f"manca {cartella}" + SUGGERIMENTO)
                diff = c.differenze_alberi(c.leggi_albero(cartella), c.produci_scenario(s))
                self.assertEqual('', diff, f"scenario {s} cambiato:\n{diff}" + SUGGERIMENTO)


class TestSoluzioni(unittest.TestCase):
    """Confronto con le soluzioni ufficiali: i controlli base falliti (KO) sono gli stessi di prima.

    Alcuni KO sono noti e non dipendono dal generatore (refusi nelle soluzioni, scelte diverse di
    aggregati o di indirizzi): il test segnala solo se l'elenco cambia.
    """

    def test_ko_invariati(self):
        esercizi = c.cartella_esercizi()
        if not esercizi:
            self.skipTest(f"{c.VAR_ESERCIZI} non impostata")
        atteso_path = os.path.join(c.ATTESI, 'soluzioni.json')
        self.assertTrue(os.path.isfile(atteso_path), f"manca {atteso_path}" + SUGGERIMENTO)
        attesi = json.loads(_leggi(atteso_path))
        for lab, voce in sorted(attesi.items()):
            with self.subTest(lab=lab):
                es = os.path.join(esercizi, voce['esercizio'])
                if not os.path.isdir(es):
                    self.skipTest(f"esercizio {voce['esercizio']} non trovato")
                ko = c.produci_ko_soluzione(os.path.join(c.FIXTURE_LABS, lab), es)
                self.assertEqual(voce['ko'], ko, f"KO di {lab} rispetto a {voce['esercizio']} cambiati")


if __name__ == '__main__':
    unittest.main()
