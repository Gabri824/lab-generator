"""
tests/strumenti/confronta_gui.py
Confronta due risultati di prova_gui.mjs (per esempio la pagina prima e dopo un rifacimento).

Toglie solo quello che cambia a ogni esecuzione (orari, durate, tempi dei ping, uptime delle
sessioni BGP, conteggi di righe dell'output) e mostra le differenze passo per passo.

    python tests/strumenti/confronta_gui.py prima.json dopo.json
Esce con 1 se ci sono differenze.
"""
import difflib
import json
import re
import sys

VARIABILI = [
    (re.compile(r'\b\d\d:\d\d:\d\d\b'), 'hh:mm:ss'),            # orari e uptime
    (re.compile(r'\b\d+(?:\.\d+)?\s?ms\b'), 'N ms'),              # tempi dei ping
    (re.compile(r'\bOK in \d+s\b'), 'OK in Ns'),                  # durate nel registro
    (re.compile(r'media \d+(?:\.\d+)?'), 'media N'),
    (re.compile(r'\b\d{8}-\d{6}\b'), 'AAAAMMGG-hhmmss'),          # copie di sicurezza
]


def normalizza(x):
    if isinstance(x, str):
        for r, s in VARIABILI:
            x = r.sub(s, x)
        return x
    if isinstance(x, dict):
        return {k: normalizza(v) for k, v in x.items() if k != 'righe'}   # righe dell'output: variano
    if isinstance(x, list):
        return [normalizza(v) for v in x]
    return x


def righe(v):
    return json.dumps(normalizza(v), ensure_ascii=False, indent=1, sort_keys=True).replace('\\n', '\n').replace('\\t', '\t').split('\n')


def main(a, b):
    with open(a, encoding='utf-8') as f:
        prima = json.load(f)
    with open(b, encoding='utf-8') as f:
        dopo = json.load(f)
    diversi = 0
    for passo in list(dict.fromkeys(list(prima['passi']) + list(dopo['passi']))):
        if passo == 'larghezze':
            continue
        d = list(difflib.unified_diff(righe(prima['passi'].get(passo)), righe(dopo['passi'].get(passo)), 'prima', 'dopo', lineterm='', n=1))
        if d:
            diversi += 1
            print(f"== {passo}: diverso")
            print('\n'.join(d[2:60]))
        else:
            print(f"== {passo}: uguale")
    for nome, e in (('prima', prima), ('dopo', dopo)):
        if e.get('errori'):
            print(f"errori nella console ({nome}): " + '; '.join(e['errori']))
    return 1 if diversi else 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:3]))
