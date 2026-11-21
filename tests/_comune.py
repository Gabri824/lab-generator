"""
tests/_comune.py
Funzioni condivise dai test di confronto ("golden") e da strumenti/aggiorna_attesi.py.

Ogni funzione `produci_*` esegue il codice attuale del generatore e restituisce il risultato in
una forma confrontabile (testo o {percorso relativo: contenuto}). I test confrontano questo
risultato con i file in tests/attesi/; aggiorna_attesi.py li riscrive.
"""
import builtins
import contextlib
import difflib
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile

TESTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS)
SRC = os.path.join(REPO, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import core  # noqa: E402
from gui import dati  # noqa: E402

FIXTURE_LABS = os.path.join(TESTS, 'fixtures', 'labs')
SCENARI = os.path.join(TESTS, 'scenari')
ATTESI = os.path.join(TESTS, 'attesi')

# Variabile d'ambiente con il percorso di esercizi/lab-bgp (soluzioni ufficiali, fuori dalla repo)
VAR_ESERCIZI = 'LABGEN_ESERCIZI'

_RE_SERIAL = re.compile(r'\b\d{10}(\s*;\s*serial)')


def elenco_lab():
    return sorted(d for d in os.listdir(FIXTURE_LABS)
                  if os.path.isfile(os.path.join(FIXTURE_LABS, d, 'lab.conf')))


def elenco_scenari():
    if not os.path.isdir(SCENARI):
        return []
    return sorted(f[:-4] for f in os.listdir(SCENARI) if f.endswith('.txt'))


def normalizza(testo):
    """Toglie dal testo ciò che cambia da un giorno all'altro (serial delle zone DNS)."""
    return _RE_SERIAL.sub(r'AAAAMMGGNN\1', testo)


def leggi_albero(cartella, escludi_xml=False):
    """{percorso relativo con '/': contenuto normalizzato} di tutti i file di una cartella."""
    out = {}
    for radice, dirs, files in os.walk(cartella):
        dirs[:] = sorted(d for d in dirs if d != '__pycache__')
        for f in sorted(files):
            if escludi_xml and f.endswith('.xml'):
                continue
            p = os.path.join(radice, f)
            rel = os.path.relpath(p, cartella).replace(os.sep, '/')
            with open(p, 'r', encoding='utf-8', errors='replace', newline='') as fh:
                out[rel] = normalizza(fh.read())
    return out


def scrivi_albero(cartella, albero):
    if os.path.isdir(cartella):
        shutil.rmtree(cartella)
    for rel, testo in albero.items():
        p = os.path.join(cartella, *rel.split('/'))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8', newline='') as fh:
            fh.write(testo)


def differenze_alberi(atteso, ottenuto, max_righe=40):
    """Descrizione leggibile delle differenze tra due alberi ('' se uguali)."""
    righe = []
    for rel in sorted(set(atteso) | set(ottenuto)):
        if rel not in ottenuto:
            righe.append(f"manca: {rel}")
        elif rel not in atteso:
            righe.append(f"in più: {rel}")
        elif atteso[rel] != ottenuto[rel]:
            righe.append(f"diverso: {rel}")
            righe += list(difflib.unified_diff(
                atteso[rel].splitlines(), ottenuto[rel].splitlines(),
                'atteso/' + rel, 'ottenuto/' + rel, lineterm='', n=1))
        if len(righe) > max_righe:
            righe.append('...')
            break
    return '\n'.join(righe)


@contextlib.contextmanager
def silenzio():
    """Raccoglie quello che il generatore stampa, senza mostrarlo."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield buf


def _json(dato, lab_path):
    def enc(o):
        if isinstance(o, (set, frozenset)):
            return sorted(o)
        raise TypeError(f"tipo non serializzabile: {type(o).__name__}")
    testo = json.dumps(dato, indent=1, sort_keys=True, ensure_ascii=False, default=enc)
    # i percorsi assoluti cambiano da una macchina all'altra
    for p in sorted({os.path.abspath(lab_path), lab_path}, key=len, reverse=True):
        testo = testo.replace(json.dumps(p)[1:-1], '<LAB>')
    return testo + '\n'


# ---------------------------------------------------------------- lettura

def produci_lettura(lab_path):
    """Cosa restituiscono oggi i tre lettori dei file, come testo JSON."""
    nome = os.path.basename(os.path.normpath(lab_path))
    with tempfile.TemporaryDirectory() as tmp:
        copia = os.path.join(tmp, nome)
        shutil.copytree(lab_path, copia)
        # rebuild_lab_metadata_and_export riscrive l'XML: la si esegue su una copia
        for f in os.listdir(copia):
            if f.endswith('.xml'):
                os.remove(os.path.join(copia, f))
        with silenzio():
            xml = core.rebuild_lab_metadata_and_export(copia)
            _, routers, hosts, wwws, lab_conf = core.load_lab_from_xml(xml)
            dispositivi = core.leggi_dispositivi(copia)
            gui = dati.leggi_lab(core, copia)
        dato = {
            'rebuild_lab_metadata_and_export': {
                'routers': routers, 'hosts': hosts, 'wwws': wwws, 'lab_conf': lab_conf},
            'leggi_dispositivi': dispositivi,
            'dati.leggi_lab': gui,
        }
        return _json(dato, copia)


# ---------------------------------------------------------------- rigenerazione

def _xml_del_lab(lab_path):
    nome = os.path.basename(os.path.normpath(lab_path))
    p = os.path.join(lab_path, nome + '.xml')
    if os.path.isfile(p):
        return p
    altri = sorted(f for f in os.listdir(lab_path) if f.endswith('.xml'))
    return os.path.join(lab_path, altri[0]) if altri else None


def produci_rigenerazione(lab_path):
    """Il lab ricreato oggi dal suo XML (come l'import del menu principale)."""
    xml = _xml_del_lab(lab_path)
    nome, routers, hosts, wwws, lab_conf = core.load_lab_from_xml(xml)
    with tempfile.TemporaryDirectory() as tmp:
        with silenzio():
            out = core.recreate_lab_from_data(nome, tmp, routers, hosts, wwws, lab_conf_text=lab_conf)
        return leggi_albero(out)


def produci_diff_opzioni(lab_path, rigenerato):
    """Differenza tra il lab rigenerato dall'XML e il lab reale: è il lavoro fatto con le Opzioni."""
    reale = leggi_albero(lab_path, escludi_xml=True)
    rig = {k: v for k, v in rigenerato.items() if not k.endswith('.xml')}
    righe = []
    for rel in sorted(set(reale) | set(rig)):
        a, b = rig.get(rel), reale.get(rel)
        if a == b:
            continue
        righe += difflib.unified_diff(
            (a or '').splitlines(), (b or '').splitlines(),
            'rigenerato/' + rel if a is not None else '/dev/null',
            'reale/' + rel if b is not None else '/dev/null', lineterm='')
    return '\n'.join(righe) + ('\n' if righe else '')


# ---------------------------------------------------------------- scenari del wizard

class ScenarioErrato(AssertionError):
    pass


def leggi_risposte(nome):
    """Risposte di uno scenario: una per riga; riga vuota = Invio; '#' all'inizio = commento."""
    with open(os.path.join(SCENARI, nome + '.txt'), encoding='utf-8') as fh:
        return [r.rstrip('\n') for r in fh if not r.startswith('#')]


def produci_scenario(nome):
    """Esegue il wizard del terminale con le risposte dello scenario e restituisce il lab prodotto."""
    risposte = leggi_risposte(nome)
    dialogo = []

    def finto_input(prompt=''):
        if not risposte:
            raise ScenarioErrato(f"risposte finite alla domanda: {prompt!r}\n" + '\n'.join(dialogo[-10:]))
        r = risposte.pop(0)
        dialogo.append(f"{prompt}{r}")
        return r

    vero_input = builtins.input
    builtins.input = finto_input
    try:
        with tempfile.TemporaryDirectory() as tmp:
            with silenzio() as out:
                core.esegui_wizard_nuovo_lab(tmp, nome)
            stampato = out.getvalue()
            if '❌' in stampato:
                riga = next(r for r in stampato.splitlines() if '❌' in r)
                raise ScenarioErrato(f"il wizard ha rifiutato una risposta: {riga}\n" + '\n'.join(dialogo[-10:]))
            if risposte:
                raise ScenarioErrato(f"risposte non usate: {risposte}")
            return leggi_albero(os.path.join(tmp, nome))
    finally:
        builtins.input = vero_input


# ---------------------------------------------------------------- soluzioni ufficiali

def cartella_esercizi():
    p = os.environ.get(VAR_ESERCIZI)
    return p if p and os.path.isdir(p) else None


def _chiave(nome):
    return re.sub(r'[^a-z0-9]', '', nome.lower())


def esercizio_di(lab, esercizi):
    """Cartella dell'esercizio che corrisponde a un lab ('butterfly_test' -> '2013-12-20-butterfly')."""
    k = _chiave(re.sub(r'_(mio|test)$', '', lab))
    for e in sorted(os.listdir(esercizi)):
        if _chiave(re.sub(r'^\d+-\d+-\d+-', '', e)) == k:
            return os.path.join(esercizi, e)
    return None


def _confronta():
    p = os.path.join(TESTS, 'strumenti', 'confronta_lab.py')
    spec = importlib.util.spec_from_file_location('confronta_lab', p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def produci_ko_soluzione(lab_path, esercizio):
    """Titoli dei controlli base falliti (KO) confrontando il lab con la soluzione ufficiale."""
    cl = _confronta()
    sol, tmp = cl.find_solution(esercizio)
    if not sol:
        return None
    ko = []

    class Raccolta(cl.Report):
        def check(self, cond, msg, detail=None):
            if not cond:
                ko.append(msg)
            super().check(cond, msg, detail)

    try:
        with silenzio():
            cl.compare(cl.load_lab(lab_path), cl.load_lab(sol), cl.load_correction(esercizio), Raccolta(), False)
    finally:
        if tmp:
            tmp.cleanup()
    return ko


def soluzioni_lette(esercizi):
    """Cartelle lab delle soluzioni ufficiali (per provare i lettori su configurazioni scritte a mano)."""
    cl = _confronta()
    for e in sorted(os.listdir(esercizi)):
        sol, tmp = cl.find_solution(os.path.join(esercizi, e))
        if sol:
            yield e, sol, tmp
