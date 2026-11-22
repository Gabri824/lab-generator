"""
Menu 4 del terminale, "Pagine web e apache2": stampa i comandi da incollare (core/web.py) e, se
Kathará c'è e il lab è acceso, chiede se eseguirli da qui. Usa le stesse funzioni della GUI
(kathara.verifica_web), quindi esiti e spiegazioni sono uguali; apache2 si avvia solo se l'utente
risponde 's'.
"""
import os

from core import web
from core.cli_io import _si, input, print_menu
from core.stato import leggi_stato

from . import kathara as kt


class _Stampa:
    """Al posto del lavoro della GUI: le righe vanno sul terminale."""
    risultato = None

    def scrivi(self, testo):
        for riga in str(testo).rstrip('\n').splitlines():
            print('  ' + riga)


def _scegli_client(clienti, stato):
    host = [n for n in clienti if stato['dispositivi'][n].get('tipo') == 'host']
    proposto = (host or clienti)[0]
    print_menu('Da quale dispositivo apro le pagine?', clienti)
    while True:
        s = input(f"Numero (Invio = {proposto}): ").strip()
        if not s:
            return proposto
        if s.isdigit() and 1 <= int(s) <= len(clienti):
            return clienti[int(s) - 1]
        print(f"Scegli un numero da 1 a {len(clienti)}.")


def testa_pagine_web(lab_path, kathara=None):
    """Ritorna il risultato dell'ultima verifica (None se non si è eseguito niente)."""
    stato = leggi_stato(lab_path)
    print('\n' + web.comandi_da_incollare(stato) + '\n')
    server = web.server_web(stato)
    if not server:
        return None
    kathara = kathara or kt.trova_kathara()
    if not kathara:
        print("Kathará non trovato: incolla i comandi a mano sui dispositivi del lab.")
        return None
    nome = os.path.basename(os.path.normpath(lab_path))
    accesi = set(kt.stato_lab(kathara, os.path.dirname(os.path.normpath(lab_path)), [nome]).get(nome, []))
    clienti = [n for n in web.client_web(stato) if n in accesi]
    if not accesi:
        print("Il lab non è acceso: avvialo (kathara lstart) per eseguire i comandi da qui.")
        return None
    if not clienti:
        print("Nessun host o server acceso da cui aprire le pagine.")
        return None
    if not _si("Li eseguo adesso? (s/N): "):
        return None
    client = _scegli_client(clienti, stato)
    while True:
        lav = _Stampa()
        print(f"\nPagine web da {client}:")
        kt.verifica_web(kathara, lab_path, stato, client, lav)
        r = lav.risultato
        spenti = [x['nome'] for x in r['server'] if x['attivo'] is False]
        if not spenti or not _si(f"apache2 è spento su {', '.join(spenti)}: lo avvio (systemctl start apache2)? (s/N): "):
            return r
        for n in spenti:
            rc, out = kt.esegui(kt.kexec(kathara, lab_path, n, ['systemctl', 'start', 'apache2']), timeout=60)
            print(f"  {n}: " + ('apache2 avviato' if rc == 0 else 'avvio non riuscito\n' + out.strip()))
        print("Ricontrollo le pagine...")
