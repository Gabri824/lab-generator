"""Interfaccia del server per costruire e modificare i lab dalla GUI (fase 2).

Usa lo stesso motore del terminale (core/): lettore unico, Opzioni come dati, piani di modifica,
regole del modello e generazione. Il server non tiene memoria tra le richieste:

- `anteprima` calcola il piano di un'operazione e restituisce le differenze, le impronte dei file
  letti e la firma del piano;
- `applica` ricalcola il piano con gli stessi parametri sui file di adesso e scrive solo se
  impronte e firma coincidono; altrimenti risponde "conflitto" (409) e non scrive nulla.

Sicurezza: si eseguono solo le operazioni di core.operazioni.OPERAZIONI, con i parametri della
loro firma; il browser manda nomi (lab, dispositivi, LAN), mai percorsi; ogni piano viene
controllato perché tocchi solo file dentro la cartella del lab.
"""
import contextlib
import hashlib
import inspect
import io
import ipaddress
import json
import os
import re
import shutil
import tempfile
import threading

from core import operazioni as op
from core import supporto
from core.file_utils import _avvisi_lab, elenco_copie, ripristina
from core.generazione import genera_lab
from core.modello import completa_lab, errore_lan, errore_nome_lab, nome_kathara_valido, valida_lab
from core.modifiche import Conflitto, anteprima, scrivi_piano
from core.stato import leggi_stato, senza_testi
from core.persistence import modello_da_stato, rigenera_xml
from core.unione import leggi_albero, porta_nel_lab

# Il motore stampa i messaggi (raccolti con redirect_stdout, che vale per tutto il processo) e
# legge e scrive i file del lab: un'operazione alla volta.
MOTORE = threading.Lock()

MAX_DISEGNO = 1024 * 1024           # byte del disegno salvato (JSON)

# parametri che sono nomi di dispositivi già presenti nel lab
PARAMETRI_DISPOSITIVO = {'router', 'dispositivo', 'server', 'vecchio', 'nome'}
# parametri che sono nomi di LAN (già presenti o nuove)
PARAMETRI_LAN = {'lan', 'nuova_lan'}
# parametri {(dispositivo, interfaccia): ip}, in JSON come [[dispositivo, interfaccia, ip], ...]
PARAMETRI_COPPIE = {'assegnati', 'fissi'}

RE_CONTROLLO = re.compile(r'[\x00-\x08\x0a-\x1f\x7f]')


class ErroreApi(Exception):
    """Richiesta da rifiutare: `codice` è lo stato HTTP, `extra` va nella risposta."""

    def __init__(self, messaggio, codice=400, **extra):
        super().__init__(messaggio)
        self.codice = codice
        self.extra = extra


# ----------------------------------------------------------------------------- JSON

def in_json(x):
    """Dati del motore in una forma JSON: insiemi come liste ordinate, indirizzi come testo,
    dizionari con chiavi a coppia (dispositivo, interfaccia) come liste [dispositivo, interfaccia, valore]."""
    if isinstance(x, dict):
        if all(isinstance(k, str) for k in x):
            return {k: in_json(v) for k, v in x.items()}
        if all(isinstance(k, tuple) for k in x):
            return [[*map(in_json, k), in_json(v)] for k, v in x.items()]
        return {str(k): in_json(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [in_json(v) for v in x]
    if isinstance(x, (set, frozenset)):
        return sorted((in_json(v) for v in x), key=str)
    if x is None or isinstance(x, (bool, int, float, str)):
        return x
    if isinstance(x, (ipaddress.IPv4Address, ipaddress.IPv4Network, ipaddress.IPv4Interface,
                      ipaddress.IPv6Address, ipaddress.IPv6Network, ipaddress.IPv6Interface)):
        return str(x)
    return str(x)


def _rel_web(rel):
    return rel.replace(os.sep, '/')


def _rel_disco(rel):
    return rel.replace('/', os.sep)


# ----------------------------------------------------------------------------- operazioni

def elenco_operazioni():
    """{operazione: {'opzioni': [parametri], 'calcola': [{'nome', 'obbligatorio', 'predefinito'}]}}."""
    def parametri(f):
        out = []
        for p in list(inspect.signature(f).parameters.values())[1:]:
            voce = {'nome': p.name, 'obbligatorio': p.default is inspect.Parameter.empty}
            if not voce['obbligatorio']:
                voce['predefinito'] = in_json(p.default)
            out.append(voce)
        return out
    return {nome: {'opzioni': parametri(o), 'calcola': parametri(c)}
            for nome, (o, c) in op.OPERAZIONI.items()}


def _operazione(nome):
    if not isinstance(nome, str) or nome not in op.OPERAZIONI:
        raise ErroreApi(f"Operazione non prevista: {nome}")
    return op.OPERAZIONI[nome]


def _senza_controllo(valore, dove):
    """Nessun testo dei parametri può contenere a capo o caratteri di controllo (spezzerebbero le righe)."""
    if isinstance(valore, str):
        if RE_CONTROLLO.search(valore):
            raise ErroreApi(f"Parametro '{dove}': a capo o caratteri di controllo non ammessi.")
    elif isinstance(valore, dict):
        for k, v in valore.items():
            _senza_controllo(k, dove)
            _senza_controllo(v, dove)
    elif isinstance(valore, list):
        for v in valore:
            _senza_controllo(v, dove)


def _coppie(valore, nome):
    if valore is None:
        return None
    if not isinstance(valore, list) or not all(
            isinstance(x, list) and len(x) == 3 and all(isinstance(y, str) for y in x) for x in valore):
        raise ErroreApi(f"Parametro '{nome}': serve una lista di [dispositivo, interfaccia, ip].")
    return {(d, i): ip for d, i, ip in valore}


def _parametri(f, parametri, stato):
    """Parametri del browser controllati sulla firma di f e sul lab, nella forma del motore."""
    if parametri is None:
        parametri = {}
    if not isinstance(parametri, dict):
        raise ErroreApi("'parametri' deve essere un oggetto.")
    firma = list(inspect.signature(f).parameters.values())[1:]
    ammessi = {p.name for p in firma}
    ignoti = sorted(set(parametri) - ammessi)
    if ignoti:
        raise ErroreApi(f"Parametri non previsti: {', '.join(ignoti)} (ammessi: {', '.join(sorted(ammessi)) or 'nessuno'}).")
    mancano = [p.name for p in firma if p.default is inspect.Parameter.empty and p.name not in parametri]
    if mancano:
        raise ErroreApi(f"Mancano i parametri: {', '.join(mancano)}.")
    out = {}
    for k, v in parametri.items():
        _senza_controllo(v, k)
        if k in PARAMETRI_DISPOSITIVO:
            if not isinstance(v, str) or v not in stato['dispositivi']:
                raise ErroreApi(f"Dispositivo '{v}' non presente nel lab.")
        elif k in PARAMETRI_LAN:
            if not isinstance(v, str) or (v not in stato['lan'] and errore_lan(v)):
                raise ErroreApi(f"LAN '{v}' non valida: {errore_lan(v) if isinstance(v, str) else 'serve un nome'}")
        elif k in PARAMETRI_COPPIE:
            v = _coppie(v, k)
        elif k == 'rel':
            if not isinstance(v, str):
                raise ErroreApi("Parametro 'rel': serve il percorso del file nel lab (con '/').")
            v = _rel_disco(v)
        out[k] = v
    return out


def _dentro(lab_path, rel):
    """True se rel è un percorso relativo che resta dentro la cartella del lab."""
    if not rel or os.path.isabs(rel) or os.path.normpath(rel).split(os.sep)[0] == '..':
        return False
    radice = os.path.realpath(lab_path)
    return os.path.realpath(os.path.join(radice, rel)).startswith(radice + os.sep)


def _controlla_piano(lab_path, piano):
    fuori = [r for r in list(piano['modifiche']) + list((piano.get('spostati') or {}).values())
             if not _dentro(lab_path, r)]
    if fuori:
        raise ErroreApi('Il piano toccherebbe file fuori dal lab: ' + ', '.join(map(_rel_web, fuori)))


def firma_piano(piano):
    """Impronta di tutto il piano (righe vecchie e nuove di ogni file, spostamenti)."""
    dati = {
        'modifiche': {_rel_web(r): [v, n] for r, (v, n) in sorted(piano['modifiche'].items())},
        'spostati': {_rel_web(a): _rel_web(b) for a, b in sorted((piano.get('spostati') or {}).items())},
    }
    return hashlib.sha256(json.dumps(dati, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def _impronte_web(piano):
    return {_rel_web(r): imp for r, imp in piano['impronte'].items()}


def _chiama(f, stato, kw):
    """f(stato, **kw) raccogliendo le stampe; un valore del tipo sbagliato (es. costo 'abc') è un
    errore dell'utente come ErroreOperazione (422), non del programma."""
    with _silenzio():
        try:
            return f(stato, **kw)
        except (TypeError, ValueError) as e:
            raise ErroreApi(f"Valori non validi: {e}", 422)


@contextlib.contextmanager
def _silenzio():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield buf


def _calcola(lab_path, nome_op, parametri):
    """(stato, piano) dell'operazione sui file di adesso; il piano è già controllato."""
    calcola = _operazione(nome_op)[1]
    stato = leggi_stato(lab_path)
    piano = _chiama(calcola, stato, _parametri(calcola, parametri, stato))
    _controlla_piano(lab_path, piano)
    return stato, piano


def opzioni(lab_path, nome_op, parametri):
    f = _operazione(nome_op)[0]
    stato = leggi_stato(lab_path)
    valori = in_json(_chiama(f, stato, _parametri(f, parametri, stato)))
    if nome_op == 'righe':                  # percorsi dei file: sempre con '/'
        valori = [_rel_web(r) for r in valori]
    return {'operazione': nome_op, 'opzioni': valori}


def _voci_anteprima(piano):
    return [{k: v for k, v in voce.items() if k != 'percorso'} for voce in anteprima(piano)]


def calcola_anteprima(lab_path, nome_op, parametri):
    _, piano = _calcola(lab_path, nome_op, parametri)
    return {
        'operazione': nome_op,
        'titolo': piano['titolo'],
        'file': _voci_anteprima(piano),
        'note': piano['note'],
        'vuoto': (piano.get('vuoto') or 'Nessuna modifica.') if not piano['modifiche'] else None,
        'impronte': _impronte_web(piano),
        'firma': firma_piano(piano),
    }


def applica(st, lab_path, nome_op, parametri, impronte, firma):
    """Ricalcola il piano e scrive solo se impronte e firma sono quelle dell'anteprima."""
    if not isinstance(impronte, dict) or not isinstance(firma, str):
        raise ErroreApi("Servono 'impronte' e 'firma' dell'anteprima.")
    _, piano = _calcola(lab_path, nome_op, parametri)
    if not piano['modifiche']:
        return {'scritto': False, 'vuoto': piano.get('vuoto') or 'Nessuna modifica.', 'note': piano['note']}
    attuali = _impronte_web(piano)
    cambiati = sorted(r for r in set(attuali) | set(impronte) if attuali.get(r) != impronte.get(r))
    if cambiati:
        raise ErroreApi('File modificati dopo l\'anteprima: ' + ', '.join(cambiati) + '. Rifai l\'anteprima.',
                        409, file=cambiati)
    if firma != firma_piano(piano):
        raise ErroreApi("Il piano non è più quello dell'anteprima (il lab è cambiato). Rifai l'anteprima.", 409, file=[])
    try:
        esito = scrivi_piano(lab_path, piano)
    except Conflitto as e:
        cambiati = [_rel_web(f) for f in e.file]
        raise ErroreApi(str(e), 409, file=cambiati)
    with _silenzio():
        op.dopo_scrittura(lab_path, piano)
    st.lavori.annota(f"{piano['titolo']} ({supporto.nome_lab(lab_path)})",
                     'scritti: ' + ', '.join(esito['file']), 'OK')
    return {
        'scritto': esito['scritto'],
        'titolo': piano['titolo'],
        'file': esito['file'],
        'copia': esito['copia'],
        'risolti': esito['risolti'],
        'nuovi': esito['nuovi'],
        'messaggi': [m for m in piano.get('messaggi', []) if m.strip()],
        'note': piano['note'],
    }


# ----------------------------------------------------------------------------- stato del lab

def leggi_disegno(lab_path):
    try:
        with open(supporto.percorso_disegno(lab_path), encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def stato_lab(lab_path):
    """Modello completo dei file, modello nel formato del wizard, disegno salvato e avvisi."""
    with MOTORE, _silenzio():
        stato = leggi_stato(lab_path)
        avvisi = sorted(_avvisi_lab(lab_path))
        modello = op._modello_dello_stato(stato)
    return {
        'nome': stato['nome'],
        'stato': in_json(senza_testi(stato)),
        'modello': in_json(modello),
        'disegno': leggi_disegno(lab_path),
        'avvisi': avvisi,
        'xml_nel_lab': bool(stato.get('xml_nel_lab')),
    }


# ----------------------------------------------------------------------------- lab nuovi

def _modello(dati):
    """Modello del browser: {'routers': {nome: {...}}, 'hosts': [...], 'wwws': [...], 'resolver'}."""
    m = dati.get('modello')
    if not isinstance(m, dict):
        raise ErroreApi("'modello' deve essere un oggetto.")
    if not isinstance(m.get('routers', {}), dict):
        raise ErroreApi("'modello.routers' deve essere un oggetto {nome: dati}.")
    for k in ('hosts', 'wwws'):
        if not isinstance(m.get(k, []), list) or not all(isinstance(x, dict) for x in m.get(k, [])):
            raise ErroreApi(f"'modello.{k}' deve essere una lista di oggetti.")
    if not all(isinstance(r, dict) for r in m.get('routers', {}).values()):
        raise ErroreApi("Ogni router di 'modello.routers' deve essere un oggetto.")
    if m.get('resolver') is not None and not isinstance(m['resolver'], str):
        raise ErroreApi("'modello.resolver' deve essere un testo o null.")
    _senza_controllo(m, 'modello')
    ammessi = {'routers', 'hosts', 'wwws', 'resolver'}
    return {k: v for k, v in m.items() if k in ammessi}


def _nomi_sicuri(modello):
    """I nomi dei dispositivi diventano cartelle: si controllano prima di scrivere qualsiasi cosa."""
    nomi = list(modello.get('routers', {})) + [x.get('name') for x in modello.get('hosts', []) + modello.get('wwws', [])]
    sbagliati = [str(n) for n in nomi if not isinstance(n, str) or not nome_kathara_valido(n)]
    if sbagliati:
        raise ErroreApi("Nomi non validi per Kathará (solo minuscole, cifre e _): " + ', '.join(sbagliati), 422)


def _nome_nuovo_lab(dati):
    nome = dati.get('nome')
    e = errore_nome_lab(nome if isinstance(nome, str) else '')
    if e:
        raise ErroreApi(e)
    return nome


def _completo(modello):
    try:
        return completa_lab(modello)
    except (TypeError, ValueError, KeyError, AttributeError) as e:
        raise ErroreApi(f"Modello non valido: {e}")


def controlla_modello(dati):
    """Problemi del modello (errori e avvisi) e il modello con i valori proposti dove mancano."""
    modello = _modello(dati)
    parziale = bool(dati.get('parziale'))
    completo = _completo(modello)
    m = dict(completo)
    if isinstance(dati.get('nome'), str):
        m['nome'] = dati['nome']
    with _silenzio():
        try:
            problemi = valida_lab(m, parziale)
        except (TypeError, ValueError, KeyError, AttributeError) as e:
            raise ErroreApi(f"Modello non valido: {e}")
    return {'problemi': problemi, 'completato': in_json(completo)}


def _albero(cartella):
    out = []
    for radice, dirs, files in os.walk(cartella):
        dirs.sort()
        for f in sorted(files):
            p = os.path.join(radice, f)
            with open(p, encoding='utf-8', errors='replace') as fh:
                out.append({'file': _rel_web(os.path.relpath(p, cartella)), 'testo': fh.read()})
    return out


def anteprima_lab(dati, st=None):
    """Genera il lab in una cartella temporanea e restituisce i file che verrebbero scritti
    (con 'origine': i file del lab di partenza con le modifiche della bozza, fase 5.7)."""
    nome = _nome_nuovo_lab(dati)
    modello = _completo(_modello(dati))
    _nomi_sicuri(modello)
    origine = _origine(st, dati.get('origine'))
    tmp = tempfile.mkdtemp(prefix='labgen-anteprima-')
    unione = None
    try:
        with _silenzio():
            esito = genera_lab(tmp, nome, modello)
        if esito['creato'] and origine:
            nuovi, unione = _unisci_origine(origine, leggi_albero(os.path.join(tmp, nome)))
            file = [{'file': k, 'testo': nuovi[k]} for k in sorted(nuovi)]
        else:
            file = _albero(os.path.join(tmp, nome)) if esito['creato'] else []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {'nome': nome, 'creabile': esito['creato'], 'problemi': esito['problemi'],
            'errori': esito['errori'], 'file': file, 'unione': unione}


# ----------------------------------------------------------------------------- fase 5.7: da un lab esistente

def _cartella_lab(st, x):
    """Percorso di un lab di partenza: {'lab': nome} nella cartella dei lab o {'cartella': percorso}."""
    if not isinstance(x, dict):
        raise ErroreApi("Lab di partenza non valido.")
    if x.get('lab'):
        if st is None:
            raise ErroreApi("Lab di partenza non disponibile.")
        return st.lab_path(str(x['lab']))
    p = x.get('cartella')
    if not isinstance(p, str) or not p.strip():
        raise ErroreApi("Scrivi la cartella del lab di partenza.")
    p = os.path.abspath(os.path.expanduser(p.strip()))
    if not os.path.isfile(os.path.join(p, 'lab.conf')):
        raise ErroreApi(f"In {p} non c'è un lab.conf: non è un lab di Kathará.")
    return p


def lab_come_modello(st, dati):
    """Modello (formato del wizard) di un lab esistente, per partire da lì nell'editor; i file non
    vengono toccati. Con le posizioni del disegno salvato (se c'è) e, per ogni router, se le sue
    network IGP sono quelle che il generatore proporrebbe (nell'editor restano automatiche)."""
    p = _cartella_lab(st, dati)
    with _silenzio():
        stato = leggi_stato(p)
        modello = modello_da_stato(stato)
    senza_ip = [f"{d['nome']} {it['dev']}" for d in stato['dispositivi'].values() for it in d['interfacce'] if not it['ip']]
    proposte = {}
    try:
        vuoto = {**modello, 'routers': {n: {k: v for k, v in r.items() if k != 'igp_networks'} for n, r in modello['routers'].items()}}
        completo = completa_lab(vuoto)
        proposte = {n: list(completo['routers'][n].get('igp_networks') or []) == list(r.get('igp_networks') or [])
                    for n, r in modello['routers'].items()}
    except (TypeError, ValueError, KeyError, AttributeError):
        pass
    disegno = leggi_disegno(p)
    import core
    from . import dati as dati_pagina
    with _silenzio():
        lab = dati_pagina.leggi_lab(core, p, stato)      # per la disposizione della Topologia
    return {'nome': os.path.basename(os.path.normpath(p)), 'percorso': p, 'modello': in_json(modello), 'lab': in_json(lab),
            'posizioni': (disegno or {}).get('posizioni'), 'zone_disegno': (disegno or {}).get('zone'),
            'reti_proposte': proposte, 'senza_ip': senza_ip}


def _origine(st, x):
    """{'percorso', 'file' (originali), 'base' (dal modello iniziale della bozza), 'nomi'} o None."""
    if x is None:
        return None
    if not isinstance(x, dict) or not isinstance(x.get('modello'), dict):
        raise ErroreApi("'origine' deve avere il modello iniziale della bozza.")
    p = _cartella_lab(st, x)
    nomi = x.get('nomi') or {}
    if not isinstance(nomi, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in nomi.items()):
        raise ErroreApi("'origine.nomi' deve essere {nome nuovo: nome di partenza}.")
    m0 = _completo(_modello({'modello': x['modello']}))
    tmp = tempfile.mkdtemp(prefix='labgen-base-')
    try:
        with _silenzio():
            e = genera_lab(tmp, 'base', m0)
        if not e['creato']:
            raise ErroreApi("Il modello iniziale della bozza non genera un lab: " + '; '.join(x.get('messaggio', '') for x in e['errori'][:3]))
        base = leggi_albero(os.path.join(tmp, 'base'))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {'percorso': p, 'file': leggi_albero(p), 'base': base, 'nomi': {k: v for k, v in nomi.items() if k != v}}


def _unisci_origine(origine, nuovi):
    file, rapporto = porta_nel_lab(origine['file'], origine['base'], nuovi, origine['nomi'])
    rapporto['percorso'] = origine['percorso']
    return file, rapporto


def _scrivi_unione(lab_path, file, rapporto):
    """Riscrive il lab appena generato con i file dell'unione; toglie quelli che il lab di partenza
    non aveva e la bozza non cambia."""
    for rel in rapporto['non_creati']:
        q = os.path.join(lab_path, *rel.split('/'))
        if os.path.isfile(q):
            os.remove(q)
            d = os.path.dirname(q)
            while d != lab_path and os.path.isdir(d) and not os.listdir(d):
                os.rmdir(d)
                d = os.path.dirname(d)
    for rel, testo in file.items():
        q = os.path.join(lab_path, *rel.split('/'))
        os.makedirs(os.path.dirname(q), exist_ok=True)
        with open(q, 'w', encoding='utf-8', newline='') as f:
            f.write(testo)


def salva_disegno(lab_path, disegno):
    if not isinstance(disegno, dict):
        raise ErroreApi("'disegno' deve essere un oggetto.")
    testo = json.dumps(disegno, ensure_ascii=False, indent=1)
    if len(testo.encode('utf-8')) > MAX_DISEGNO:
        raise ErroreApi('Disegno troppo grande.', 413)
    path = supporto.percorso_disegno(lab_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.labgen-tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(testo + '\n')
    os.replace(tmp, path)
    return {'salvato': True}


def crea_lab(st, dati):
    """Crea il lab nella cartella dei lab. Se esiste già serve 'sovrascrivi' (dopo la conferma)."""
    nome = _nome_nuovo_lab(dati)
    modello = _completo(_modello(dati))
    _nomi_sicuri(modello)
    disegno = dati.get('disegno')
    if disegno is not None and not isinstance(disegno, dict):
        raise ErroreApi("'disegno' deve essere un oggetto.")
    lab_path = os.path.join(st.base, nome)
    sovrascrivi = dati.get('sovrascrivi') is True
    if os.path.exists(lab_path) and not sovrascrivi:
        return {'nome': nome, 'creato': False, 'esiste': True,
                'messaggio': f"Il lab {nome} esiste già: confermi di sostituirlo? (prima viene fatta una copia di sicurezza)"}
    origine = _origine(st, dati.get('origine'))       # letto prima: può essere lo stesso lab
    esito = genera_lab(st.base, nome, modello, sovrascrivi=sovrascrivi)
    unione = None
    if esito['creato'] and origine:
        file, unione = _unisci_origine(origine, leggi_albero(lab_path))
        _scrivi_unione(lab_path, file, unione)
        with _silenzio():
            rigenera_xml(lab_path)
    if esito['creato']:
        if disegno is not None:
            salva_disegno(lab_path, disegno)
        st.lavori.annota(f"crea lab {nome}", f"{len(_albero(lab_path))} file in {lab_path}", 'OK')
    return {'nome': nome, 'creato': esito['creato'], 'esiste': False, 'percorso': esito['percorso'],
            'problemi': esito['problemi'], 'errori': esito['errori'], 'copia': esito['copia'],
            'motivo': esito['motivo'], 'messaggi': esito['messaggi'], 'unione': unione}


def sposta_xml(st, lab_path):
    fuori, copia = supporto.sposta_xml_fuori(lab_path)
    if fuori:
        st.lavori.annota(f"sposta XML fuori dal lab ({supporto.nome_lab(lab_path)})", fuori, 'OK')
    return {'spostato': bool(fuori), 'xml': fuori, 'copia': copia}


# ----------------------------------------------------------------------------- smistamento

# azioni di questo modulo; quelle con True lavorano su un lab esistente (campo 'lab')
# ----------------------------------------------------------------------------- copie di sicurezza

def _data_copia(nome):
    """'20261122-170750_prima_del_ripristino' -> '2026-11-22 17:07:50 (prima del ripristino)'."""
    m = re.match(r'(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})(?:_(\d+))?(?:_(.*))?$', nome)
    if not m:
        return nome
    g = m.groups()
    testo = f"{g[0]}-{g[1]}-{g[2]} {g[3]}:{g[4]}:{g[5]}"
    return testo + (f" ({g[7].replace('_', ' ')})" if g[7] else '')


def copie(lab_path):
    return {'copie': [{'nome': n, 'quando': _data_copia(n)} for n in elenco_copie(lab_path)]}


def ripristina_copia(st, lab_path, nome):
    if not isinstance(nome, str) or nome not in elenco_copie(lab_path):
        raise ErroreApi(f"Copia di sicurezza non trovata: {nome}")
    prima = ripristina(lab_path, nome)
    st.lavori.annota(f"Ripristino di {supporto.nome_lab(lab_path)} dalla copia {_data_copia(nome)}",
                     f"copia dello stato di prima: {prima}", 'OK')
    return {'ripristinato': nome, 'quando': _data_copia(nome), 'copia_di_prima': prima}


AZIONI = {
    'opzioni': True,
    'anteprima': True,
    'applica': True,
    'sposta_xml': True,
    'copie': True,
    'ripristina': True,
    'salva_disegno': True,
    'valida_lab': False,
    'anteprima_lab': False,
    'crea_lab': False,
    'lab_come_modello': False,
}


def esegui(st, tipo, dati):
    """POST /api/azione per le azioni di AZIONI. Gli errori del motore (ErroreOperazione) vanno
    al chiamante, che risponde 422."""
    lab_path = st.lab_path(dati.get('lab', '')) if AZIONI[tipo] else None
    with MOTORE:
        if tipo == 'opzioni':
            return opzioni(lab_path, dati.get('operazione'), dati.get('parametri'))
        if tipo == 'anteprima':
            return calcola_anteprima(lab_path, dati.get('operazione'), dati.get('parametri'))
        if tipo == 'applica':
            return applica(st, lab_path, dati.get('operazione'), dati.get('parametri'),
                           dati.get('impronte'), dati.get('firma'))
        if tipo == 'copie':
            return copie(lab_path)
        if tipo == 'ripristina':
            return ripristina_copia(st, lab_path, dati.get('copia'))
        if tipo == 'sposta_xml':
            return sposta_xml(st, lab_path)
        if tipo == 'salva_disegno':
            return salva_disegno(lab_path, dati.get('disegno'))
        if tipo == 'valida_lab':
            return controlla_modello(dati)
        if tipo == 'anteprima_lab':
            return anteprima_lab(dati, st)
        if tipo == 'lab_come_modello':
            return lab_come_modello(st, dati)
        if tipo == 'crea_lab':
            return crea_lab(st, dati)
    raise ErroreApi('Azione non prevista')
