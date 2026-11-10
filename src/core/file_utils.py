"""
src/core/file_utils.py
Funzioni di lettura/scrittura file, manipolazione blocchi FRR, backup e diff con conferma.
"""
import datetime
import difflib
import os
import re
import shutil

from .cli_io import input, print_menu
from .templates import _FRR_GLOBALI


def _leggi_righe(fpath):
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            return f.read().split('\n')
    except OSError:
        return []


def _scrivi_righe(fpath, righe):
    # al massimo una riga vuota consecutiva, file che termina con un a capo
    out = []
    for l in righe:
        if l.strip() == '' and out and out[-1].strip() == '':
            continue
        out.append(l.rstrip())
    with open(fpath, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(out).rstrip('\n') + '\n')


def _righe_file(path):
    """Righe di un file senza la riga vuota creata dall'a capo finale."""
    righe = _leggi_righe(path)
    if righe and righe[-1] == '':
        righe.pop()
    return righe


def _scrivi_esatte(path, righe):
    """Scrive le righe così come sono (a differenza di _scrivi_righe non toglie righe vuote)."""
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(righe) + '\n')


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
    if not os.path.exists(fpath):
        print(f"⚠️ frr.conf non trovato per {router}: {fpath}")
        return False
    with open(fpath, 'a', encoding='utf-8', newline='\n') as f:
        f.write("\n" + stanza + "\n")
    return True


def insert_lines_into_protocol_block(fpath, proto='bgp', asn=None, lines=None):
    """Inserisce `lines` (lista di stringhe, senza newline) dentro la sezione 'router <proto>' di fpath."""
    if lines is None:
        return False
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.readlines()
    except Exception as e:
        print(f"❌ Errore leggendo {fpath}: {e}")
        return False

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
            with open(fpath, 'a', encoding='utf-8', newline='\n') as f:
                if os.path.getsize(fpath) > 0:
                    f.write('\n')
                for l in lines:
                    f.write(l + '\n')
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
        with open(fpath, 'w', encoding='utf-8', newline='\n') as f:
            f.writelines(new_content)
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
    from .persistence import _ricarica_routers

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
    _ricarica_routers(lab_path, routers)
    return True


def _avvisi_lab(lab_path):
    from .analyzer import controlla_topologia, controlli_configurazione
    return set(controlla_topologia(lab_path)) | set(controlli_configurazione(lab_path))


def _stampa_diff(rel, vecchie, nuove):
    print(f"  {rel.replace(os.sep, '/')}")
    sm = difflib.SequenceMatcher(a=vecchie, b=nuove, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        for k in range(i1, i2):
            print(f"    - riga {k + 1:>3}: {vecchie[k].strip()}")
        for k in range(j1, j2):
            print(f"    + riga {k + 1:>3}: {nuove[k].strip()}")


def _applica_modifiche(lab_path, modifiche, titolo, note=None):
    """modifiche = {percorso relativo: (righe vecchie, righe nuove)}. Anteprima, conferma,
    copia di sicurezza, scrittura e controlli prima/dopo. True se ha scritto."""
    modifiche = {r: v for r, v in modifiche.items() if v[0] != v[1]}
    if not modifiche:
        print('Nessuna modifica da fare.')
        return False
    print(f"\n--- {titolo}: anteprima ({len(modifiche)} file) ---")
    for rel in sorted(modifiche):
        _stampa_diff(rel, *modifiche[rel])
    for n in note or []:
        print(f"  ⚠️ {n}")
    if input("\nConfermi le modifiche? (s/N): ").strip().lower() not in ('s', 'si', 'sì'):
        print('Annullato: nessun file modificato.')
        return False
    prima = _avvisi_lab(lab_path)
    copia = copia_di_sicurezza(lab_path)
    for rel, (_, nuove) in modifiche.items():
        _scrivi_esatte(os.path.join(lab_path, rel), nuove)
    print(f"✅ Modifiche scritte. Copia del lab com'era prima: {copia}")
    dopo = _avvisi_lab(lab_path)
    for a in sorted(prima - dopo):
        print(f"   ✔ risolto: {a}")
    for a in sorted(dopo - prima):
        print(f"   ⚠️ nuovo: {a}")
    if not (prima ^ dopo):
        print("   (i controlli dell'opzione 8 danno lo stesso esito di prima)")
    print("   Se il lab è avviato, le modifiche valgono dal prossimo avvio (lclean e poi lstart).")
    return True