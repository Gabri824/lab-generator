"""
src/core/file_utils.py
Funzioni di lettura/scrittura file, manipolazione blocchi FRR, backup e diff con conferma.
"""
import contextlib
import contextvars
import datetime
import os
import re
import shutil

from .cli_io import input, print_menu
from .templates import _FRR_GLOBALI


# --- File in memoria ---
# Dentro `with file_virtuali(lab):` le letture e le scritture fatte con le funzioni qui sotto
# (_leggi_testo, _scrivi_testo, _esiste_file e quelle che le usano) avvengono su una copia in
# memoria: il disco non cambia e le differenze diventano un piano di modifica (core/modifiche.py).
# Così le Opzioni calcolano cosa cambierebbero con la stessa logica che usano per scrivere.
_VIRTUALI = contextvars.ContextVar('file_virtuali', default=None)


class FileVirtuali:
    def __init__(self, base):
        self.base = os.path.abspath(base)
        self.testi = {}         # percorso assoluto -> testo attuale (None = file assente)
        self.originali = {}     # percorso assoluto -> testo sul disco all'inizio (None = assente)

    def _carica(self, path):
        k = os.path.abspath(path)
        if k not in self.testi:
            try:
                with open(k, 'r', encoding='utf-8') as f:
                    testo = f.read()
            except OSError:
                testo = None
            self.testi[k] = self.originali[k] = testo
        return k

    def leggi(self, path):
        return self.testi[self._carica(path)]

    def scrivi(self, path, testo):
        self.testi[self._carica(path)] = testo

    def esiste(self, path):
        k = os.path.abspath(path)
        return self.testi[k] is not None if k in self.testi else os.path.isfile(k)

    def modifiche(self):
        """{percorso relativo al lab: (righe vecchie, righe nuove)} dei file cambiati (None = assente)."""
        def righe(t):
            if t is None:
                return None
            r = t.split('\n')
            if r and r[-1] == '':
                r.pop()
            return r
        return {os.path.relpath(k, self.base): (righe(self.originali[k]), righe(t))
                for k, t in self.testi.items() if t != self.originali[k]}


@contextlib.contextmanager
def file_virtuali(base):
    fs = FileVirtuali(base)
    token = _VIRTUALI.set(fs)
    try:
        yield fs
    finally:
        _VIRTUALI.reset(token)


def _leggi_testo(path):
    """Testo di un file (None se manca), dal disco o dai file in memoria."""
    fs = _VIRTUALI.get()
    if fs is not None:
        return fs.leggi(path)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except OSError:
        return None


def _scrivi_testo(path, testo):
    fs = _VIRTUALI.get()
    if fs is not None:
        fs.scrivi(path, testo)
        return
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(testo)


def _esiste_file(path):
    fs = _VIRTUALI.get()
    return fs.esiste(path) if fs is not None else os.path.exists(path)


def _leggi_righe(fpath):
    testo = _leggi_testo(fpath)
    return testo.split('\n') if testo is not None else []


def _scrivi_righe(fpath, righe):
    # al massimo una riga vuota consecutiva, file che termina con un a capo
    out = []
    for l in righe:
        if l.strip() == '' and out and out[-1].strip() == '':
            continue
        out.append(l.rstrip())
    _scrivi_testo(fpath, '\n'.join(out).rstrip('\n') + '\n')


def _righe_file(path):
    """Righe di un file senza la riga vuota creata dall'a capo finale."""
    righe = _leggi_righe(path)
    if righe and righe[-1] == '':
        righe.pop()
    return righe


def _scrivi_esatte(path, righe):
    """Scrive le righe così come sono (a differenza di _scrivi_righe non toglie righe vuote)."""
    _scrivi_testo(path, '\n'.join(righe) + '\n')


def _rimuovi_righe(fpath, pred):
    righe = _leggi_righe(fpath)
    nuove = [l for l in righe if not pred(l)]
    if len(nuove) != len(righe):
        _scrivi_righe(fpath, nuove)


def _rimuovi_route_map(fpath, rm_name):
    """Toglie tutte le entry 'route-map <rm_name> ...' con le righe match/set che seguono."""
    out, dentro = [], False
    for l in _leggi_righe(fpath):
        s = l.strip()
        if s.startswith(f"route-map {rm_name} "):
            dentro = True
            continue
        if dentro and re.match(r'(match|set|on-match|call|continue)\b', s):
            continue
        dentro = False
        out.append(l)
    _scrivi_righe(fpath, out)


def _append_righe(fpath, righe):
    """Accoda un blocco di righe globali (prefix-list, route-map) separato da una riga vuota."""
    _scrivi_righe(fpath, _leggi_righe(fpath) + [''] + list(righe))


def append_frr_stanza(base_path, router, stanza):
    fpath = os.path.join(base_path, router, "etc", "frr", "frr.conf")
    if not _esiste_file(fpath):
        print(f"⚠️ frr.conf non trovato per {router}: {fpath}")
        return False
    _scrivi_testo(fpath, (_leggi_testo(fpath) or '') + "\n" + stanza + "\n")
    return True


def insert_lines_into_protocol_block(fpath, proto='bgp', asn=None, lines=None):
    """Inserisce `lines` (lista di stringhe, senza newline) dentro la sezione 'router <proto>' di fpath."""
    if lines is None:
        return False
    testo = _leggi_testo(fpath)
    if testo is None:
        print(f"❌ Errore leggendo {fpath}: file non trovato")
        return False
    # come readlines(): righe con il loro a capo, divise solo su '\n'
    content = [l + '\n' for l in testo.split('\n')]
    if content and content[-1] == '\n':
        content.pop()
    elif content:
        content[-1] = content[-1][:-1]

    idx = None
    target_start = f'router {proto}'.lower()
    for i, L in enumerate(content):
        s = L.strip().lower()
        if s.startswith(target_start):
            if asn and str(asn) not in L:
                continue
            idx = i
            break

    if idx is None:
        try:
            _scrivi_testo(fpath, testo + ('\n' if testo else '') + ''.join(l + '\n' for l in lines))
            return True
        except Exception as e:
            print(f"❌ Errore scrivendo (append) su {fpath}: {e}")
            return False

    j = idx + 1
    while j < len(content):
        line = content[j]
        if line.startswith(' ') or line.startswith('\t') or line.strip() == '':
            j += 1
            continue
        if line.lstrip().startswith('!'):
            j += 1
            continue
        break

    while j - 1 > idx and content[j - 1].strip() == '':
        j -= 1

    ind_lines = [('    ' + l) for l in lines]

    if j > 0 and not content[j - 1].endswith('\n'):
        content[j - 1] += '\n'

    new_content = content[:j] + [l + '\n' for l in ind_lines] + content[j:]

    try:
        _scrivi_testo(fpath, ''.join(new_content))
        return True
    except Exception as e:
        print(f"❌ Errore scrivendo su {fpath}: {e}")
        return False


def _inizio_blocco(righe, rx):
    return next((k for k, l in enumerate(righe) if re.match(rx, l.strip())), None)


def _fine_blocco(righe, inizio):
    """Indice dopo l'ultima riga del blocco che comincia a `inizio`."""
    fine = inizio + 1
    while fine < len(righe):
        s = righe[fine].strip()
        if s == 'exit':
            fine += 1
            break
        if s.startswith('!') or (s and _FRR_GLOBALI.match(s)):
            break
        fine += 1
    while fine - 1 > inizio and not righe[fine - 1].strip():
        fine -= 1
    return fine


def _inserisci_nel_blocco(righe, rx, nuove):
    i = _inizio_blocco(righe, rx)
    if i is None:
        return None
    f = _fine_blocco(righe, i)
    return righe[:f] + ['    ' + x for x in nuove] + righe[f:]


def _indici_nodo(righe, inizio):
    out = []
    for k in range(inizio + 1, len(righe)):
        s = ' '.join(righe[k].split())
        if not s or s.startswith('!'):
            continue
        if s == 'exit' or _FRR_GLOBALI.match(s):
            break
        out.append(k)
    return out


def _comandi_nodo(righe, inizio):
    """Comandi (spazi normalizzati) del blocco che comincia a `inizio`, letti come FRR."""
    return [' '.join(righe[k].split()) for k in _indici_nodo(righe, inizio)]


def _set_demone(righe, demone, valore):
    out, fatto = [], False
    for l in righe:
        if re.match(rf'\s*{demone}\s*=', l):
            l, fatto = f"{demone}={valore}", True
        out.append(l)
    if not fatto:
        out.append(f"{demone}={valore}")
    return out


def _file_di_testo(lab_path):
    """File di testo del lab (percorsi relativi), esclusi l'XML del generatore e le cartelle nascoste."""
    out = []
    for radice, dirs, files in os.walk(lab_path):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
        for f in sorted(files):
            p = os.path.join(radice, f)
            if radice == lab_path and f.endswith('.xml'):
                continue
            try:
                if os.path.getsize(p) > 512 * 1024:
                    continue
                with open(p, 'r', encoding='utf-8') as fh:
                    fh.read()
            except (OSError, UnicodeDecodeError):
                continue
            out.append(os.path.relpath(p, lab_path))
    return out


# --- Copie di sicurezza e applicazione modifiche con diff ---
def _cartella_copie(lab_path):
    lab = os.path.abspath(lab_path)
    return os.path.join(os.path.dirname(lab), '.backup_labgenerator', os.path.basename(lab))


def copia_di_sicurezza(lab_path, etichetta=''):
    """Copia dell'intero lab in <cartella dei lab>/.backup_labgenerator/<lab>/<data-ora>."""
    base = _cartella_copie(lab_path)
    nome = datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + (f"_{etichetta}" if etichetta else '')
    dest, k = os.path.join(base, nome), 2
    while os.path.exists(dest):
        dest, k = os.path.join(base, f"{nome}_{k}"), k + 1
    shutil.copytree(lab_path, dest)
    return dest


def ripristina_copia(lab_path, routers=None, _nome=None):
    from .persistence import rigenera_xml

    base = _cartella_copie(lab_path)
    copie = sorted(
        (d for d in os.listdir(base) if os.path.isfile(os.path.join(base, d, 'lab.conf'))),
        reverse=True
    ) if os.path.isdir(base) else []
    if not copie:
        print('Nessuna copia di sicurezza per questo lab.')
        return False
    print_menu(
        f'Copie di sicurezza di {os.path.basename(os.path.abspath(lab_path))} (la più recente in alto):',
        copie[:15]
    )
    s = input('Numero della copia da ripristinare (Invio = annulla): ').strip()
    if not (s.isdigit() and 1 <= int(s) <= min(len(copie), 15)):
        print('Annullato.')
        return False
    src = os.path.join(base, copie[int(s) - 1])
    if input(f"Il lab tornerà com'era in {copie[int(s) - 1]}. Confermi? (s/N): ").strip().lower() not in ('s', 'si', 'sì'):
        print('Annullato.')
        return False
    attuale = copia_di_sicurezza(lab_path, 'prima_del_ripristino')
    shutil.rmtree(lab_path)
    shutil.copytree(src, lab_path)
    print(f"✅ Lab ripristinato. Lo stato di prima del ripristino è salvato in: {attuale}")
    rigenera_xml(lab_path)
    return True


def _avvisi_lab(lab_path):
    from .analyzer import controlla_topologia, controlli_configurazione
    from .stato import leggi_stato
    stato = leggi_stato(lab_path)          # una lettura sola per tutti i controlli
    return set(controlla_topologia(lab_path, stato)) | set(controlli_configurazione(lab_path, stato))


def _stampa_anteprima(file_ant):
    """Stampa le differenze di un file dell'anteprima (core/modifiche.anteprima)."""
    if file_ant.get('da'):
        print(f"  {file_ant['file']}  (era {file_ant['da']})")
    else:
        print(f"  {file_ant['file']}")
    for r in file_ant['righe']:
        print(f"    {r['segno']} riga {r['numero']:>3}: {r['testo'].strip()}")


def _applica_modifiche(lab_path, modifiche, titolo, note=None, spostati=None):
    """modifiche = {percorso relativo: (righe vecchie, righe nuove)}. Anteprima, conferma,
    copia di sicurezza, scrittura e controlli prima/dopo. True se ha scritto.

    Il calcolo e la scrittura sono in core/modifiche.py; qui restano le domande e le stampe
    del terminale. Se un file cambia mentre si aspetta la conferma, non scrive nulla."""
    from .modifiche import Conflitto, anteprima, nuovo_piano, scrivi_piano

    piano = nuovo_piano(titolo, modifiche, note, spostati)
    if not piano['modifiche']:
        print('Nessuna modifica da fare.')
        return False
    ant = anteprima(piano)
    print(f"\n--- {titolo}: anteprima ({len(ant)} file) ---")
    for f in ant:
        _stampa_anteprima(f)
    for n in piano['note']:
        print(f"  ⚠️ {n}")
    if input("\nConfermi le modifiche? (s/N): ").strip().lower() not in ('s', 'si', 'sì'):
        print('Annullato: nessun file modificato.')
        return False
    try:
        esito = scrivi_piano(lab_path, piano)
    except Conflitto as e:
        print("⚠️ Nel frattempo sono cambiati: " + ', '.join(f.replace(os.sep, '/') for f in e.file))
        print("   (forse dalla GUI o da un editor). Nessuna modifica scritta: riapri l'operazione.")
        return False
    print(f"✅ Modifiche scritte. Copia del lab com'era prima: {esito['copia']}")
    for a in esito['risolti']:
        print(f"   ✔ risolto: {a}")
    for a in esito['nuovi']:
        print(f"   ⚠️ nuovo: {a}")
    if not (esito['risolti'] or esito['nuovi']):
        print("   (i controlli dell'opzione 8 danno lo stesso esito di prima)")
    print("   Se il lab è avviato, le modifiche valgono dal prossimo avvio (lclean e poi lstart).")
    return True


def _esegui_piano(base_path, piano, routers=None):
    """Terminale: anteprima, conferma e scrittura di un piano di core/operazioni.py, poi i messaggi
    di esito e l'XML dei metadati rigenerato dai file. True se ha scritto."""
    if not piano['modifiche']:
        if piano.get('vuoto'):
            print(piano['vuoto'])
        else:
            print('\n'.join(piano.get('messaggi') or []) or 'Nessuna modifica da fare.')
            for n in piano.get('note') or []:
                print(f"⚠️ {n}")
        return False
    if not _applica_modifiche(base_path, piano['modifiche'], piano['titolo'], piano['note'], piano.get('spostati')):
        return False
    for m in piano.get('messaggi') or []:
        print(m)
    from .operazioni import dopo_scrittura
    dopo_scrittura(base_path, piano)   # XML dei metadati allineato ai file e disegno della GUI, fuori dal lab
    return True
