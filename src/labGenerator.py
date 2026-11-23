#!/usr/bin/env python3
"""
src/labGenerator.py
Entry-point principale del Kathará Lab Generator (CLI + GUI).
"""
import argparse
import os
import sys

# Garantisce che la cartella src/ sia sempre nel path di ricerca (Linux e Windows)
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import core
from core import (
    archivio_menu,
    collect_lab_ips,
    correggi_nomi_importati,
    esegui_wizard_nuovo_lab,
    generate_ping_oneliner,
    input_lab_name,
    input_non_vuoto,
    load_lab_from_json,
    leggi_resolver,
    load_lab_from_xml,
    opzioni_laboratorio_menu,
    print_menu,
    rebuild_lab_metadata_and_export,
    scegli_lab,
    recreate_lab_from_data,
    stampa_controllo_topologia,
)


def avvia_gui(base, porta=8765):
    """GUI web locale (gui/): topologia, riepilogo, comandi Kathará e test nel browser."""
    from gui import server
    server.avvia(base, core, porta)


def main():
    # Terminali non UTF-8 (es. LANG=C sui PC del laboratorio, output reindirizzato
    # su Windows): le emoji nei messaggi farebbero crashare print().
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except Exception:
            pass

    parser = argparse.ArgumentParser(description='Generatore Kathará')
    parser.add_argument('--from-xml', help='Percorso file XML da importare per creare il lab')
    parser.add_argument('--from-json', help='Percorso file JSON da importare per creare il lab')
    parser.add_argument('--regen-xml', help='Percorso della directory del lab per rigenerare il file XML')
    parser.add_argument('--out', '--output', dest='out', help='Cartella in cui creare i lab (default: cartella corrente)')
    parser.add_argument('--force', action='store_true', help='Con --from-xml/--from-json: sovrascrive un lab già esistente')
    parser.add_argument('--gui', action='store_true', help='Apre la GUI nel browser (topologia, riepilogo, comandi Kathará, test)')
    parser.add_argument('--porta', type=int, default=8765, help='Porta della GUI su 127.0.0.1 (default 8765)')
    args, ignote = parser.parse_known_args()
    if ignote:
        # prima venivano ignorate in silenzio (es. un --output scritto male faceva partire la GUI
        # sulla cartella corrente): ora si dice quali, e si continua
        print(f"⚠️ Opzioni non riconosciute, ignorate: {' '.join(ignote)} (python3 labGenerator.py --help)")

    base = os.path.abspath(os.path.expanduser(args.out)) if args.out else os.getcwd()
    os.makedirs(base, exist_ok=True)

    if args.gui:
        avvia_gui(base, args.porta)
        return

    if args.regen_xml:
        if not os.path.isfile(os.path.join(args.regen_xml, 'lab.conf')):
            print(f"❌ In {args.regen_xml} non c'è un lab.conf: non è un lab di Kathará.")
            return
        out = rebuild_lab_metadata_and_export(args.regen_xml)
        if out:
            print(f"✅ XML rigenerato: {out}")
        else:
            print("❌ Rigenerazione XML fallita.")
        return

    if args.from_xml or args.from_json:
        if args.from_xml:
            lab_name, routers, hosts, wwws, lab_conf_text = load_lab_from_xml(args.from_xml)
        else:
            lab_name, routers, hosts, wwws, lab_conf_text = load_lab_from_json(args.from_json)
        if os.path.exists(os.path.join(base, lab_name)) and not args.force:
            print(f"❌ Il lab '{lab_name}' esiste già in {base}. Usa --force per sovrascriverlo.")
            sys.exit(1)
        routers, lab_conf_text = correggi_nomi_importati(routers, hosts, wwws, lab_conf_text, interactive=False)
        lab_path = recreate_lab_from_data(lab_name, base, routers, hosts, wwws, lab_conf_text,
                                          resolver=leggi_resolver(args.from_xml or args.from_json))
        print(f"✅ Lab '{lab_name}' creato (non-interattivo) in: {lab_path}")
        stampa_controllo_topologia(lab_path)
        return

    print(f"\nI lab verranno creati in: {base}")

    while True:
        print("\n\n----- Katharà Lab Generator - versione portabile -----\n")
        print("Scegli una modalità:\n")
        print("  1) Crea nuovo Laboratorio")
        print("  2) Importa file XML/JSON")
        print("  3) Genera file XML")
        print("  4) Testa Funzionamento (PING, pagine web e apache2, nomi DNS)")
        print("  5) Opzioni Laboratorio")
        print("  6) Interfaccia grafica (browser)")
        print("  7) Crea archivio per la consegna")
        print("  0) Esci\n")
        print("--------------------------------------------------------\n")

        mode = input_non_vuoto("Digita un'opzione (0-7): ").strip()
        if not mode:
            continue
        if mode == '0':
            print('Uscita.')
            return
        if mode == '1':
            lab_name = input_lab_name("Nome del laboratorio (es. bgp_es1): ")
            esegui_wizard_nuovo_lab(base, lab_name)
            return
        if mode == '2':
            file_path = input_non_vuoto("Percorso del file XML/JSON da importare: ").strip().strip('"')
            if not os.path.exists(file_path) and os.path.exists(os.path.join(base, file_path)):
                file_path = os.path.join(base, file_path)
            if not os.path.exists(file_path):
                print(f"File non trovato: {file_path}")
                continue
            ext = os.path.splitext(file_path)[1].lower()
            try:
                if ext == '.xml':
                    lab_name, routers, hosts, wwws, lab_conf_text = load_lab_from_xml(file_path)
                elif ext == '.json':
                    lab_name, routers, hosts, wwws, lab_conf_text = load_lab_from_json(file_path)
                else:
                    try:
                        lab_name, routers, hosts, wwws, lab_conf_text = load_lab_from_xml(file_path)
                    except Exception:
                        lab_name, routers, hosts, wwws, lab_conf_text = load_lab_from_json(file_path)
                corretti = correggi_nomi_importati(routers, hosts, wwws, lab_conf_text)
                if corretti is None:
                    continue
                routers, lab_conf_text = corretti
                lab_path = recreate_lab_from_data(lab_name, base, routers, hosts, wwws, lab_conf_text,
                                                  confirm=True, resolver=leggi_resolver(file_path))
                if not lab_path:
                    continue
                print(f"✅ Lab '{lab_name}' creato da file in: {lab_path}")
                stampa_controllo_topologia(lab_path)
                return
            except Exception as e:
                print('Errore importando il file:', e)
                continue
        if mode == '3':
            target = input_non_vuoto("Percorso della directory del lab da cui rigenerare l'XML: ")
            if not os.path.isdir(target):
                print(f"Directory non trovata: {target}")
                continue
            out = rebuild_lab_metadata_and_export(target)
            if out:
                print(f"✅ XML rigenerato: {out}")
            else:
                print("❌ Rigenerazione XML fallita.")
            return
        if mode == '4':
            print_menu('Cosa vuoi provare?', ['Ping: comando da incollare sulle macchine del lab',
                                              'Pagine web e apache2 (links dal client)',
                                              'Risoluzione di un nome (catena DNS, dig dal client)'], [('0', 'Indietro')])
            scelta = input_non_vuoto('Scelta: ').strip()
            if scelta == '3':
                target = scegli_lab(base)
                if target:
                    from gui.terminale_web import testa_risoluzione
                    testa_risoluzione(target)
                continue
            if scelta == '2':
                target = scegli_lab(base)
                if target:
                    from gui.terminale_web import testa_pagine_web
                    testa_pagine_web(target)
                continue
            if scelta != '1':
                continue
            target = input_non_vuoto('Percorso della directory del lab per generare il comando ping: ')
            if not os.path.isdir(target):
                print(f"Directory non trovata: {target}")
                continue
            ips = collect_lab_ips(target)
            if not ips:
                print('Nessun IP trovato nella directory del lab. Controlla che ci siano file .startup o i router con interfacce.')
                continue
            cmd = generate_ping_oneliner(ips)
            print('\n=== Comando ping generato (copia/incolla sulle macchine del lab) ===\n\n')
            print(cmd)
            print('\n\n=== Fine comando ===\n')
            continue
        if mode == '5':
            opzioni_laboratorio_menu(base)
            continue
        if mode == '6':
            avvia_gui(base, args.porta)
            continue
        if mode == '7':
            target = scegli_lab(base)
            if target:
                archivio_menu(target)
            continue
        print('Scelta non valida, riprova.')


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        try:
            print()
        except Exception:
            pass
        try:
            if os.name == 'nt':
                os.system('cls')
            else:
                os.system('clear')
        except Exception:
            pass
        try:
            sys.exit(0)
        except Exception:
            os._exit(0)