#!/bin/bash
# Avvio del Lab Generator su Linux, senza permessi di amministratore.
#
#   bash /media/$USER/<CHIAVETTA>/avvia.sh            menu nel terminale
#   bash /media/$USER/<CHIAVETTA>/avvia.sh --gui      GUI nel browser
#
set -u
QUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HOME/.labgenerator"
LABS="${LABS:-$HOME/labs}"
ERR="$DEST/ultimo_errore.txt"
msg() { echo "[avvia] $*"; }

echo "----- Lab Generator - versione portabile modificata (basata sul lavoro di sciro24) -----"

# 0. controlli che non dipendono da noi: Kathara usa Docker
if command -v docker > /dev/null 2>&1; then
    if ! uscita=$(docker ps 2>&1); then
        if echo "$uscita" | grep -qi "permission denied"; then
            msg "ATTENZIONE: il tuo utente non puo' usare Docker (non e' nel gruppo 'docker')."
            msg "            Kathara non potra' avviare i lab: chiedi al docente. Il generatore crea comunque i file."
        else
            msg "ATTENZIONE: Docker non risponde: $(echo "$uscita" | head -1)"
        fi
    fi
else
    msg "ATTENZIONE: comando 'docker' non trovato: potrai creare i lab ma non avviarli."
fi
command -v kathara > /dev/null 2>&1 || msg "ATTENZIONE: comando 'kathara' non trovato: potrai creare i lab ma non avviarli."

mkdir -p "$DEST" "$LABS" || { msg "Non riesco a creare $DEST o $LABS"; exit 1; }
cd "$LABS" || exit 1
msg "I lab vengono creati in: $LABS"

prova() { "$@" --help > /dev/null 2> "$ERR"; }

# 1. Se c'è l'eseguibile compilato (scaricato dalla Release), aggiriamo la chiavetta copiandolo in locale
if [ -f "$QUI/labGenerator" ]; then
    cp -f "$QUI/labGenerator" "$DEST/" && chmod +x "$DEST/labGenerator"
    
    if prova "$DEST/labGenerator"; then
        msg "Avvio la versione binaria compilata."
        exec "$DEST/labGenerator" "$@"
    fi
    msg "L'eseguibile non parte (vedi $ERR)."
fi

# 2. Se non c'è l'eseguibile, usiamo il codice sorgente (ora nella cartella src/)
if command -v python3 > /dev/null 2>&1 && [ -f "$QUI/src/labGenerator.py" ]; then
    if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'; then
        msg "Uso i sorgenti con $(python3 --version 2>&1)."
        exec python3 "$QUI/src/labGenerator.py" "$@"
    fi
    msg "python3 c'e' ma e' troppo vecchio ($(python3 --version 2>&1)): serve almeno 3.8."
else
    msg "python3 non disponibile o sorgenti non trovati in src/."
fi

msg "Nessuna versione e' partita. Assicurati di avere l'eseguibile o python3 installato."
exit 1
