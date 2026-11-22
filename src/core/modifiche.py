"""
src/core/modifiche.py
Modifiche ai file di un lab come dati: piano di modifica, anteprima e scrittura sicura.

Un "piano" descrive cosa cambiare senza toccare nulla:

    {'titolo': str,
     'modifiche': {percorso relativo: (righe vecchie, righe nuove)},
     'note': [str],
     'impronte': {percorso relativo: impronta delle righe vecchie}}

righe vecchie = None  -> il file è nuovo (non deve esistere);
righe nuove   = None  -> il file va eliminato.

Né `anteprima` né `scrivi_piano` chiedono o stampano qualcosa: il terminale
(file_utils._applica_modifiche) e la GUI ne usano i risultati ciascuno a modo suo.
"""
import difflib
import hashlib
import os
import shutil

from .file_utils import _avvisi_lab, _righe_file, copia_di_sicurezza


class Conflitto(Exception):
    """Uno o più file sono cambiati dopo che il piano è stato calcolato: nulla è stato scritto."""

    def __init__(self, file):
        self.file = sorted(file)
        super().__init__('file modificati nel frattempo: ' + ', '.join(f.replace(os.sep, '/') for f in self.file))


def impronta(righe):
    """Impronta di un file letto come righe (None = file assente)."""
    if righe is None:
        return None
    return hashlib.sha256('\n'.join(righe).encode('utf-8')).hexdigest()


def leggi_righe_attuali(lab_path, rel):
    """Righe di un file del lab come le legge _righe_file; None se il file non esiste."""
    path = os.path.join(lab_path, rel)
    return _righe_file(path) if os.path.isfile(path) else None


def nuovo_piano(titolo, modifiche=None, note=None, spostati=None):
    """Piano di modifica; le voci che non cambiano nulla vengono tolte.

    spostati = {percorso vecchio: percorso nuovo} per i file che cambiano solo posto (rinomina):
    nel piano sono un file eliminato più uno nuovo, l'anteprima li mostra come spostamento."""
    utili = {rel: (v, n) for rel, (v, n) in (modifiche or {}).items() if v != n}
    return {
        'titolo': titolo,
        'modifiche': utili,
        'note': list(note or []),
        'impronte': {rel: impronta(v) for rel, (v, _) in utili.items()},
        'spostati': dict(spostati or {}),
    }


def anteprima(piano):
    """Differenze del piano, file per file (in ordine di percorso):

    [{'file': 'r1/etc/frr/frr.conf', 'stato': 'modificato' | 'nuovo' | 'eliminato',
      'righe': [{'segno': '-' | '+', 'numero': n, 'testo': riga}]}]"""
    out = []
    spostati = piano.get('spostati') or {}
    da = {n: v for v, n in spostati.items()}
    for rel in sorted(piano['modifiche']):
        if rel in spostati and spostati[rel] in piano['modifiche']:
            continue                                    # compare col percorso nuovo
        vecchie, nuove = piano['modifiche'][rel]
        stato = 'nuovo' if vecchie is None else ('eliminato' if nuove is None else 'modificato')
        origine = None
        if rel in da and da[rel] in piano['modifiche']:
            stato, origine = 'spostato', da[rel].replace(os.sep, '/')
            vecchie = piano['modifiche'][da[rel]][0]
        a, b = vecchie or [], nuove or []
        righe = []
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
            if tag == 'equal':
                continue
            righe += [{'segno': '-', 'numero': k + 1, 'testo': a[k]} for k in range(i1, i2)]
            righe += [{'segno': '+', 'numero': k + 1, 'testo': b[k]} for k in range(j1, j2)]
        voce = {'file': rel.replace(os.sep, '/'), 'percorso': rel, 'stato': stato, 'righe': righe}
        if origine:
            voce['da'] = origine
        out.append(voce)
    return out


def conflitti(lab_path, piano):
    """Percorsi dei file che non sono più come quando il piano è stato calcolato."""
    return [rel for rel, imp in piano['impronte'].items()
            if impronta(leggi_righe_attuali(lab_path, rel)) != imp]


def _scrivi_atomico(path, righe):
    """Scrive le righe (come _scrivi_esatte) passando da un file temporaneo nella stessa cartella."""
    cartella = os.path.dirname(path)
    if cartella:
        os.makedirs(cartella, exist_ok=True)
    tmp = path + '.labgen-tmp'
    try:
        with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(righe) + '\n')
        if os.path.exists(path):
            shutil.copymode(path, tmp)          # gli startup restano eseguibili
        elif path.endswith('.startup'):
            os.chmod(tmp, 0o755)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _togli_cartelle_vuote(lab_path, eliminati):
    """Dopo aver eliminato dei file, toglie le cartelle rimaste vuote (mai la cartella del lab)."""
    radice = os.path.abspath(lab_path)
    for path in eliminati:
        d = os.path.dirname(os.path.abspath(path))
        while d.startswith(radice + os.sep) and os.path.isdir(d) and not os.listdir(d):
            os.rmdir(d)
            d = os.path.dirname(d)


def scrivi_piano(lab_path, piano):
    """Scrive un piano: controllo dei conflitti, copia di sicurezza, scrittura, controlli prima/dopo.

    Solleva Conflitto (senza scrivere nulla) se un file è cambiato dopo il calcolo del piano.
    Restituisce {'scritto', 'copia', 'file', 'risolti', 'nuovi'}."""
    if not piano['modifiche']:
        return {'scritto': False, 'copia': None, 'file': [], 'risolti': [], 'nuovi': []}
    cambiati = conflitti(lab_path, piano)
    if cambiati:
        raise Conflitto(cambiati)
    prima = _avvisi_lab(lab_path)
    copia = copia_di_sicurezza(lab_path)
    eliminati = []
    for rel, (_, nuove) in piano['modifiche'].items():
        path = os.path.join(lab_path, rel)
        if nuove is None:
            if os.path.exists(path):
                os.remove(path)
                eliminati.append(path)
        else:
            _scrivi_atomico(path, nuove)
    _togli_cartelle_vuote(lab_path, eliminati)
    dopo = _avvisi_lab(lab_path)
    return {
        'scritto': True,
        'copia': copia,
        'file': sorted(rel.replace(os.sep, '/') for rel in piano['modifiche']),
        'risolti': sorted(prima - dopo),
        'nuovi': sorted(dopo - prima),
    }
