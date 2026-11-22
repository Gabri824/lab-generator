#!/usr/bin/env python3
"""
tests/strumenti/aggiorna_attesi.py
Riscrive i file attesi dei test di confronto (tests/attesi/) eseguendo il codice ATTUALE.

Da usare solo di proposito: quando si cambia il comportamento del generatore e si è controllato
che i nuovi file prodotti sono giusti. Dopo l'esecuzione, `git diff tests/attesi` mostra cosa è
cambiato.

Uso:
    python tests/strumenti/aggiorna_attesi.py [lettura] [stato] [rigenerazione] [opzioni] [scenari] [operazioni] [soluzioni]

Senza argomenti aggiorna tutto. "soluzioni" richiede la variabile LABGEN_ESERCIZI con il percorso
di esercizi/lab-bgp; senza, viene saltato.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _comune as c  # noqa: E402

PARTI = ('lettura', 'stato', 'rigenerazione', 'opzioni', 'scenari', 'operazioni', 'soluzioni')


def _scrivi(path, testo):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(testo)


def main(argv):
    parti = argv or list(PARTI)
    for p in parti:
        if p not in PARTI:
            print(f"Parte sconosciuta: {p} (possibili: {', '.join(PARTI)})")
            return 2

    labs = c.elenco_lab()
    for lab in labs:
        path = os.path.join(c.FIXTURE_LABS, lab)
        if 'lettura' in parti:
            _scrivi(os.path.join(c.ATTESI, 'lettura', lab + '.json'), c.produci_lettura(path))
        if 'stato' in parti:
            _scrivi(os.path.join(c.ATTESI, 'stato', lab + '.json'), c.produci_stato(path))
        if 'rigenerazione' in parti or 'opzioni' in parti:
            rig = c.produci_rigenerazione(path)
            if 'rigenerazione' in parti:
                c.scrivi_albero(os.path.join(c.ATTESI, 'rigenerazione', lab), rig)
            if 'opzioni' in parti:
                _scrivi(os.path.join(c.ATTESI, 'opzioni', lab + '.diff'), c.produci_diff_opzioni(path, rig))
    if any(p in parti for p in ('lettura', 'stato', 'rigenerazione', 'opzioni')):
        print(f"lab reali: {len(labs)}")

    if 'scenari' in parti:
        scenari = c.elenco_scenari()
        for s in scenari:
            c.scrivi_albero(os.path.join(c.ATTESI, 'scenari', s), c.produci_scenario(s))
        print(f"scenari: {len(scenari)}")

    if 'operazioni' in parti:
        operazioni = c.elenco_operazioni()
        for n in operazioni:
            diff, stampato = c.produci_operazione(n)
            _scrivi(os.path.join(c.ATTESI, 'operazioni', n + '.diff'), diff)
            _scrivi(os.path.join(c.ATTESI, 'operazioni', n + '.out'), stampato)
        print(f"operazioni: {len(operazioni)}")

    if 'soluzioni' in parti:
        esercizi = c.cartella_esercizi()
        if not esercizi:
            print(f"soluzioni: saltate ({c.VAR_ESERCIZI} non impostata)")
        else:
            dati = {}
            for lab in labs:
                es = c.esercizio_di(lab, esercizi)
                if es:
                    ko = c.produci_ko_soluzione(os.path.join(c.FIXTURE_LABS, lab), es)
                    if ko is not None:
                        dati[lab] = {'esercizio': os.path.basename(es), 'ko': ko}
            _scrivi(os.path.join(c.ATTESI, 'soluzioni.json'),
                    json.dumps(dati, indent=1, ensure_ascii=False, sort_keys=True) + '\n')
            print(f"soluzioni: {len(dati)} lab confrontati")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
