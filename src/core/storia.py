"""
src/core/storia.py
Storia delle modifiche di un lab, per annullarle una alla volta (GUI e terminale).

Ogni piano scritto (operazioni.dopo_scrittura, chiamata sia dalla GUI sia dal terminale) lascia
qui il contenuto dei file prima e dopo: l'operazione inversa è esatta. Si annulla dall'ultima,
e solo se i file sono ancora come li ha lasciati quella modifica; altrimenti (file corretti a mano,
scritture fuori dalla storia) resta la copia di sicurezza.

    .labgenerator/<lab>/storia.json   {'versione': 1, 'voci': [voce, ...]}  (la più recente in fondo)
    voce = {'id', 'ora', 'titolo', 'modifiche': {rel: [righe prima | null, righe dopo | null]},
            'spostati': {rel vecchio: rel nuovo}, 'rinomina': [vecchio, nuovo] | null}

I percorsi sono salvati con '/' (la storia vale anche se il lab passa da Linux a Windows).
"""
import datetime
import json
import os
import threading
import uuid

from .modifiche import conflitti, leggi_righe_attuali, nuovo_piano
from .supporto import cartella_supporto

VERSIONE = 1
MASSIMO = 50                      # voci tenute: le più vecchie si perdono (resta la copia di sicurezza)
_LUCCHETTO = threading.Lock()     # leggi-e-riscrivi della storia, uno alla volta (thread del server)


class ErroreStoria(Exception):
    pass


def percorso_storia(lab_path):
    return os.path.join(cartella_supporto(lab_path), 'storia.json')


def _web(rel):
    return rel.replace(os.sep, '/')


def _disco(rel):
    return rel.replace('/', os.sep)


def voci(lab_path):
    """Voci della storia, dalla più vecchia alla più recente ([] se non c'è o non si legge)."""
    try:
        with open(percorso_storia(lab_path), encoding='utf-8') as f:
            d = json.load(f)
    except (OSError, ValueError):
        return []
    v = d.get('voci') if isinstance(d, dict) and d.get('versione') == VERSIONE else None
    return [x for x in v if isinstance(x, dict) and 'id' in x] if isinstance(v, list) else []


def _salva(lab_path, elenco):
    path = percorso_storia(lab_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.labgen-tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump({'versione': VERSIONE, 'voci': elenco[-MASSIMO:]}, f, ensure_ascii=False)
    os.replace(tmp, path)


def registra(lab_path, piano):
    """Dopo la scrittura di un piano: aggiunge la voce. Le righe "dopo" sono rilette dal disco:
    sono quelle davvero scritte, qualunque strada abbia scritto il piano."""
    if not piano.get('modifiche'):
        return None
    modifiche = {_web(rel): [vecchie, leggi_righe_attuali(lab_path, rel)]
                 for rel, (vecchie, _) in piano['modifiche'].items()}
    voce = {
        'id': uuid.uuid4().hex[:12],
        'ora': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'titolo': piano.get('titolo') or 'Modifica',
        'modifiche': modifiche,
        'spostati': {_web(a): _web(b) for a, b in (piano.get('spostati') or {}).items()},
        'rinomina': piano.get('rinomina'),
    }
    with _LUCCHETTO:
        _salva(lab_path, voci(lab_path) + [voce])
    return voce


def togli(lab_path, id_voce):
    """Dopo un annullamento scritto: la voce esce dalla storia."""
    with _LUCCHETTO:
        elenco = voci(lab_path)
        nuove = [v for v in elenco if v['id'] != id_voce]
        if len(nuove) != len(elenco):
            _salva(lab_path, nuove)


def svuota(lab_path):
    """Lab ricreato o ripristinato da una copia: la storia non vale più."""
    try:
        os.remove(percorso_storia(lab_path))
    except OSError:
        pass


def riassunto(lab_path):
    """[{'id', 'ora', 'titolo', 'file'}] dalla più recente: per i menu e per la GUI."""
    return [{'id': v['id'], 'ora': v['ora'], 'titolo': v['titolo'], 'file': sorted(v['modifiche'])}
            for v in reversed(voci(lab_path))]


def piano_inverso(lab_path):
    """Piano che riporta i file a prima dell'ultima modifica della storia.

    ErroreStoria se la storia è vuota o se un file non è più come l'ha lasciato quella modifica."""
    elenco = voci(lab_path)
    if not elenco:
        raise ErroreStoria("Nessuna modifica da annullare: la storia di questo lab è vuota.")
    v = elenco[-1]
    modifiche = {_disco(rel): (dopo, prima) for rel, (prima, dopo) in v['modifiche'].items()}
    spostati = {_disco(b): _disco(a) for a, b in (v.get('spostati') or {}).items()}
    piano = nuovo_piano(f"Annulla: {v['titolo']}", modifiche,
                        [f"Torna com'era prima della modifica delle {v['ora'][11:]}."], spostati)
    cambiati = conflitti(lab_path, piano)
    if cambiati:
        raise ErroreStoria(
            f"Non posso annullare \"{v['titolo']}\": dopo quella modifica è cambiato "
            + ', '.join(_web(r) for r in sorted(cambiati))
            + " (a mano o fuori dal generatore). Per tornare indietro usa una copia di sicurezza.")
    piano['annulla'] = v['id']
    if v.get('rinomina'):
        piano['rinomina'] = list(reversed(v['rinomina']))
    return piano
