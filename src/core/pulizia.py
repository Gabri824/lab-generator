"""
src/core/pulizia.py
Fase 8.1, pulizia a cascata dei riferimenti orfani. Quando un'operazione toglie un dispositivo,
un'interfaccia o un protocollo (o sposta un'interfaccia) restano nel lab righe che puntano a cose
sparite: neighbor verso IP che non esistono più, route-map e liste rimaste senza uso, gateway e
rotte statiche negli .startup, nameserver in resolv.conf, record A nei file di zona.

`pulisci` lavora sul piano di modifica già calcolato (`{percorso: (righe prima, righe dopo)}`):
aggiunge o aggiorna le voci del piano, senza scrivere nulla su disco. Terminale e GUI passano da
qui perché la chiamano le stesse calcola_X. Solo standard library.
"""
import os
import re

_RE_ROUTE_MAP = re.compile(r'^(\s*)route-map\s+(\S+)\s+(?:permit|deny)\b')
_RE_LISTA = re.compile(r'^\s*(?:ip\s+|ipv6\s+)?(?:prefix-list|access-list)\s+(\S+)\s'
                       r'|^\s*bgp\s+(?:as-path\s+access-list|community-list(?:\s+(?:standard|expanded))?)\s+(\S+)\s')
_RE_NEIGHBOR = re.compile(r'^\s*neighbor\s+(\S+)\s')


def _righe(lab, modifiche, rel):
    """Righe correnti del file (considerando il piano); None se il piano lo elimina o non esiste."""
    if rel in modifiche:
        return None if modifiche[rel][1] is None else list(modifiche[rel][1])
    try:
        with open(os.path.join(lab, rel), encoding='utf-8', newline='') as f:
            testo = f.read()
    except (OSError, UnicodeDecodeError):
        return None
    righe = testo.split('\n')
    if righe and righe[-1] == '':
        righe.pop()
    return righe


def _file_del_lab(lab):
    """Percorsi (relativi, con os.sep) dei file che la pulizia sa ripulire."""
    out = []
    for radice, dirs, files in os.walk(lab):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
        for f in sorted(files):
            rel = os.path.relpath(os.path.join(radice, f), lab)
            parti = rel.split(os.sep)
            if len(parti) == 1 and f.endswith('.startup'):
                out.append(rel)
            elif len(parti) >= 3 and parti[1] == 'etc' and (
                    rel.endswith(os.path.join('frr', 'frr.conf'))
                    or f == 'resolv.conf'
                    or (parti[2] == 'bind' and f.startswith('db.'))):
                out.append(rel)
    return out


def _salva(modifiche, lab, rel, prima, dopo):
    """Registra nel piano il file; se era già nel piano conserva le righe 'prima' originali."""
    if rel in modifiche:
        prima = modifiche[rel][0]
    modifiche[rel] = (prima, dopo)


def _senza_ip(rel, righe, ip_spariti):
    """Righe del file senza i riferimenti agli IP spariti; (nuove, descrizione di cosa è stato tolto)."""
    tolte, nuove = [], []
    nome = rel.replace(os.sep, '/')
    for l in righe:
        s = l.strip()
        togli = False
        if rel.endswith('.startup'):
            m = re.match(r'ip\s+route\s+add\s+.*\bvia\s+(\S+)', s)
            m2 = re.match(r'route\s+add\s+.*\bgw\s+(\S+)', s)
            togli = bool((m and m.group(1) in ip_spariti) or (m2 and m2.group(1) in ip_spariti))
        elif rel.endswith('frr.conf'):
            m = re.match(r'ip\s+route\s+\S+\s+(\d+\.\d+\.\d+\.\d+)\b', s)
            togli = bool((m and m.group(1) in ip_spariti)
                         or ((n := _RE_NEIGHBOR.match(l)) and n.group(1) in ip_spariti))
        elif rel.endswith('resolv.conf'):
            m = re.match(r'nameserver\s+(\S+)', s)
            togli = bool(m and m.group(1) in ip_spariti)
        elif os.sep + 'bind' + os.sep in rel:
            m = re.search(r'\sA\s+(\d+\.\d+\.\d+\.\d+)\s*(?:;.*)?$', l)
            togli = bool(m and m.group(1) in ip_spariti)
        if togli:
            tolte.append(f"{nome}: {' '.join(s.split())}")
        else:
            nuove.append(l)
    return nuove, tolte


def _nomi_usati(righe):
    """Parole che compaiono nelle righe che non definiscono route-map o liste, e nelle righe 'match'
    e 'neighbor ... route-map/prefix-list' dentro i corpi. Serve per sapere se un nome è usato."""
    usati = set()
    for l in righe:
        if _RE_ROUTE_MAP.match(l) or _RE_LISTA.match(l):
            continue
        usati.update(re.findall(r'[A-Za-z0-9_.-]+', l))
    return usati


def _definizioni(righe):
    """{nome: [(inizio, fine)]} dei blocchi route-map e delle righe di liste."""
    out = {}
    i = 0
    while i < len(righe):
        l = righe[i]
        m = _RE_ROUTE_MAP.match(l)
        if m:
            rientro = len(m.group(1))
            j = i + 1
            while j < len(righe) and righe[j].strip() and not righe[j].strip().startswith('!') \
                    and len(righe[j]) - len(righe[j].lstrip()) > rientro:
                j += 1
            out.setdefault(m.group(2), []).append((i, j))
            i = j
            continue
        m = _RE_LISTA.match(l)
        if m:
            out.setdefault(m.group(1) or m.group(2), []).append((i, i + 1))
        i += 1
    return out


def _togli_orfane(righe, prima):
    """Toglie le route-map e le liste che erano usate in `prima` e ora non lo sono più (a cascata:
    le liste usate solo da una route-map tolta vanno via con lei). (nuove righe, [nomi tolti])"""
    tolti = []
    usati_prima = _nomi_usati(prima)
    while True:
        usati = _nomi_usati(righe)
        defs = _definizioni(righe)
        orfani = [n for n in defs if n in usati_prima and n not in usati]
        if not orfani:
            return righe, tolti
        da_togliere = set()
        for n in orfani:
            for a, b in defs[n]:
                da_togliere.update(range(a, b))
        righe = [l for k, l in enumerate(righe) if k not in da_togliere]
        tolti += sorted(orfani)


def pulisci(stato, modifiche, ip_spariti=()):
    """Completa il piano `modifiche` con la pulizia dei riferimenti orfani. Restituisce le note
    (cosa è stato tolto) da mostrare con l'anteprima.

    ip_spariti: IP (senza maschera) che non esistono più o non sono più raggiungibili: si tolgono i
    neighbor, le rotte statiche e i gateway negli .startup, i nameserver e i record A che li usano.
    In ogni caso si tolgono le route-map e le liste di frr.conf che il piano ha lasciato senza uso."""
    lab = stato['percorso']
    ip_spariti = {str(i) for i in ip_spariti if i}
    note = []
    if ip_spariti:
        for rel in _file_del_lab(lab):
            righe = _righe(lab, modifiche, rel)
            if righe is None:
                continue
            nuove, tolte = _senza_ip(rel, righe, ip_spariti)
            if not tolte:
                continue
            if rel.endswith('resolv.conf') and not any(l.strip() for l in nuove):
                _salva(modifiche, lab, rel, righe, None)
                note.append(f"{rel.replace(os.sep, '/')}: file tolto (non resta nessun nameserver).")
                continue
            _salva(modifiche, lab, rel, righe, nuove)
            note.extend(f"Tolto da {t}" for t in tolte if not t.split(': ', 1)[1].startswith('neighbor'))
    for rel in _file_del_lab(lab):
        if not rel.endswith('frr.conf') or rel not in modifiche or modifiche[rel][1] is None:
            continue
        prima, dopo = modifiche[rel]
        nuove, tolti = _togli_orfane(list(dopo), list(prima))
        if tolti:
            _salva(modifiche, lab, rel, prima, nuove)
            note.append(f"{rel.replace(os.sep, '/')}: tolte le liste e route-map non più usate: " + ', '.join(tolti) + '.')
    return note
