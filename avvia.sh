#!/bin/bash
# Avvio del Lab Generator su Linux, senza permessi di amministratore.
#
#   bash /media/$USER/<CHIAVETTA>/avvia.sh            menu nel terminale
#   bash /media/$USER/<CHIAVETTA>/avvia.sh --gui      GUI nel browser
#
# Si lancia con "bash", quindi funziona anche se la chiavetta non conserva il
# permesso di esecuzione. Copia il programma in ~/.labgenerator, crea i lab in
# ~/labs (per un'altra cartella: LABS=/percorso bash avvia.sh) e prova in ordine:
#   1. eseguibile in un file      2. lo stesso con TMPDIR nella home (/tmp bloccato)
#   3. versione a cartella        4. sorgenti con python3 (>= 3.8)
# Le opzioni (--gui, --porta, --from-xml, ...) passano al programma.
set -u
QUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HOME/.labgenerator"
LABS="${LABS:-$HOME/labs}"
ERR="$DEST/ultimo_errore.txt"
msg() { echo "[avvia] $*"; }

echo "----- Lab Generator - versione portabile modificata (basata sul lavoro di sciro24) -----"
if [ ! -d "$QUI/linux" ]; then
    msg "Non trovo la cartella linux/ accanto ad avvia.sh ($QUI): copia tutta la cartella della chiavetta."
    exit 1
fi

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

# 1. copia nella home (la chiavetta non conserva i permessi): aggiornata a ogni avvio
mkdir -p "$DEST" "$LABS" || { msg "Non riesco a creare $DEST o $LABS"; exit 1; }
cp -f "$QUI/linux/labGenerator" "$DEST/" && chmod +x "$DEST/labGenerator"
rm -rf "$DEST/labGenerator-dir" "$DEST/sorgente"
cp -r "$QUI/linux/labGenerator-dir" "$DEST/" && chmod +x "$DEST/labGenerator-dir/labGenerator"
[ -d "$QUI/sorgente" ] && cp -r "$QUI/sorgente" "$DEST/"
cd "$LABS" || exit 1
msg "I lab vengono creati in: $LABS"

# 2. tentativi: ognuno viene provato con --help (veloce, non tocca niente) prima di partire
prova() { "$@" --help > /dev/null 2> "$ERR"; }
motivo() {
    if grep -q "GLIBC_" "$ERR"; then echo "sistema troppo vecchio (glibc)"
    elif grep -qi "failed to map segment\|permission denied\|error while loading" "$ERR"; then echo "esecuzione bloccata (cartella montata 'noexec')"
    else head -1 "$ERR"; fi
}

if prova "$DEST/labGenerator"; then
    exec "$DEST/labGenerator" "$@"
fi
msg "Il file unico non parte: $(motivo)"

mkdir -p "$DEST/tmp"
if TMPDIR="$DEST/tmp" prova "$DEST/labGenerator"; then
    msg "Uso il file unico con TMPDIR=$DEST/tmp (/tmp non permette di eseguire programmi)."
    export TMPDIR="$DEST/tmp"
    exec "$DEST/labGenerator" "$@"
fi

if prova "$DEST/labGenerator-dir/labGenerator"; then
    msg "Uso la versione a cartella."
    exec "$DEST/labGenerator-dir/labGenerator" "$@"
fi
msg "Nemmeno la versione a cartella parte: $(motivo)"

if command -v python3 > /dev/null 2>&1 && [ -f "$DEST/sorgente/labGenerator.py" ]; then
    if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'; then
        msg "Uso i sorgenti con $(python3 --version 2>&1)."
        exec python3 "$DEST/sorgente/labGenerator.py" "$@"
    fi
    msg "python3 c'e' ma e' troppo vecchio ($(python3 --version 2>&1)): serve almeno 3.8."
else
    msg "python3 non disponibile."
fi
msg "Nessuna versione e' partita. Ultimo errore (anche in $ERR):"
cat "$ERR"
exit 1
