"""
src/core/unione.py
Fase 5.7, "Parti da un lab esistente": il nuovo lab nasce dal modello della bozza, ma le righe
che il modello non contiene (policy, costi, debug, iptables, pagine web scritte a mano...) non
devono perdersi. Unione a tre vie, file per file:

    nuovo lab = file originali + (file generati dal modello modificato - file generati dal modello iniziale)

- originale: i file del lab di partenza;
- base: i file che il generatore scrive dal modello iniziale della bozza (appena caricata);
- nuovo: i file che il generatore scrive dal modello della bozza com'è adesso.
Se la bozza non è cambiata il nuovo lab è identico all'originale; ogni modifica della bozza
cambia solo le righe che tocca, le altre restano come sono.
Solo standard library; funzioni su dizionari {percorso relativo: testo}, senza scrivere su disco.
"""
import difflib
import ipaddress
import os
import re


def leggi_albero(cartella):
    """{percorso relativo con '/': testo} dei file di testo del lab, senza file nascosti e XML."""
    out = {}
    for radice, dirs, files in os.walk(cartella):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
        for f in sorted(files):
            if f.startswith('.') or f.endswith('.xml'):
                continue
            p = os.path.join(radice, f)
            try:
                with open(p, encoding='utf-8', newline='') as fh:
                    out[os.path.relpath(p, cartella).replace(os.sep, '/')] = fh.read()
            except (UnicodeDecodeError, OSError):
                continue
    return out


def _righe(testo):
    return testo.split('\n')


def unisci(originale, base, nuovo):
    """Applica a `originale` le modifiche che portano da `base` a `nuovo` (testi). Le righe di
    `originale` che `base` non ha restano al loro posto; una riga da togliere che l'originale non
    ha (già diversa) si ignora; le righe nuove vanno dopo l'ultima riga comune che le precede."""
    if base == nuovo:
        return originale
    o, b, n = _righe(originale), _righe(base), _righe(nuovo)
    pos = {}
    for i, j, k in difflib.SequenceMatcher(None, b, o, autojunk=False).get_matching_blocks():
        for t in range(k):
            pos[i + t] = j + t
    togli, metti = set(), {}
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, b, n, autojunk=False).get_opcodes():
        if tag == 'equal':
            continue
        for k in range(i1, i2):
            if k in pos:
                togli.add(pos[k])
        prima = next((pos[k] for k in range(i1 - 1, -1, -1) if k in pos), -1)
        metti.setdefault(prima, []).extend(n[j1:j2])
    out = list(metti.get(-1, []))
    for j, riga in enumerate(o):
        if j not in togli:
            out.append(riga)
        out.extend(metti.get(j, []))
    return '\n'.join(out)


def _rinomina(rel, nomi):
    """Percorso del file nel lab di partenza: cartella e startup del dispositivo con il nome di allora."""
    testa, _, coda = rel.partition('/')
    if coda:
        return nomi.get(testa, testa) + '/' + coda
    if rel.endswith('.startup'):
        return nomi.get(rel[:-8], rel[:-8]) + '.startup'
    return rel


_RE_IP = re.compile(r'\b\d{1,3}(?:\.\d{1,3}){3}\b')


def _ip_di(testi):
    out = set()
    for t in testi:
        for x in _RE_IP.findall(t):
            try:
                out.add(str(ipaddress.ip_address(x)))
            except ValueError:
                pass
    return out


def porta_nel_lab(originale, base, nuovo, nomi=None):
    """File del nuovo lab: `nuovo` con le righe dell'originale che il modello non contiene.

    originale, base, nuovo: {percorso: testo}; nomi: {nome nuovo: nome nel lab di partenza} per i
    dispositivi rinominati nella bozza. Restituisce (file, rapporto) con
    rapporto = {'conservate': {file: [righe dell'originale che il modello non genera]},
                'copiati': [file dell'originale portati così come sono],
                'non_creati': [file che il generatore aggiungerebbe ma l'originale non aveva],
                'avvisi': [righe conservate che citano un IP che nella bozza non c'è più]}."""
    nomi = nomi or {}
    inversi = {v: k for k, v in nomi.items()}
    file, conservate, copiati, non_creati = {}, {}, [], []
    for rel, testo in nuovo.items():
        orig = _rinomina(rel, nomi)
        if orig in originale and orig in base:
            file[rel] = unisci(originale[orig], base[orig], testo)
            if rel == 'lab.conf':
                file[rel] = _nuovi_in_fondo(file[rel], originale[orig], nomi)
            gen = set(_righe(base[orig]))
            extra = [r for r in _righe(originale[orig]) if r.strip() and r not in gen]
            if extra:
                conservate[rel] = extra
        elif orig in base and base[orig] == testo and orig not in originale:
            non_creati.append(rel)          # il lab di partenza non lo aveva e la bozza non lo cambia
        else:
            file[rel] = testo
    # file dell'originale che il generatore non scrive (pagine, file in più): restano, se il
    # dispositivo c'è ancora
    dispositivi_nuovi = {r.split('/')[0] for r in nuovo if '/' in r} | {r[:-8] for r in nuovo if r.endswith('.startup')}
    for orig, testo in originale.items():
        if orig in base:
            continue
        testa = orig.split('/')[0] if '/' in orig else (orig[:-8] if orig.endswith('.startup') else None)
        rel = orig
        if testa is not None:
            nuovo_nome = inversi.get(testa, testa if testa not in nomi.values() else None)
            if nuovo_nome is None or nuovo_nome not in dispositivi_nuovi:
                continue
            rel = _rinomina_al_nuovo(orig, testa, nuovo_nome)
        if rel not in file:
            file[rel] = testo
            copiati.append(rel)
    spariti = _ip_di(base.values()) - _ip_di(nuovo.values())
    avvisi = []
    for rel, righe in conservate.items():
        for r in righe:
            citati = sorted(_ip_di([r]) & spariti)
            if citati:
                avvisi.append(f"{rel}: '{r.strip()}' cita {', '.join(citati)}, che nella bozza non c'è più.")
    return file, {'conservate': conservate, 'copiati': sorted(copiati), 'non_creati': sorted(non_creati), 'avvisi': avvisi}


_RE_LABCONF = re.compile(r'^\s*([A-Za-z0-9_]+)\s*\[')


def _nuovi_in_fondo(testo, originale, nomi):
    """lab.conf: le righe dei dispositivi che il lab di partenza non aveva vanno in fondo (l'unione le
    metterebbe dove le mette il generatore, spesso in cima)."""
    vecchi = {m.group(1) for m in map(_RE_LABCONF.match, originale.split('\n')) if m}
    vecchi |= {k for k, v in nomi.items() if v in vecchi}
    tenute, nuove = [], []
    for r in testo.split('\n'):
        m = _RE_LABCONF.match(r)
        (nuove if m and m.group(1) not in vecchi else tenute).append(r)
    if not nuove:
        return testo
    while tenute and not tenute[-1].strip():
        tenute.pop()
    return '\n'.join(tenute + [''] + nuove) + '\n'


def _rinomina_al_nuovo(rel, vecchio, nuovo):
    if rel.startswith(vecchio + '/'):
        return nuovo + rel[len(vecchio):]
    if rel == vecchio + '.startup':
        return nuovo + '.startup'
    return rel
