"""
src/gui/percorso_voluto.py
Fase 5.5b, "Percorso voluto" (modalità Modifica della GUI): dai punti cliccati sul disegno
(sorgente, AS o link da attraversare, destinazione) ricava la sequenza di AS e i link fra AS, poi
propone per ogni punto di scelta di BGP una policy della 5.5 (le stesse dell'Opzione 2 del
terminale, quindi gli stessi file):
- un AS ha un'altra uscita verso la destinazione con un AS path non più lungo: local-preference
  in ingresso sulla sessione da usare, solo per la rete di destinazione (lift, as300r1);
- l'AS successivo è raggiungibile da più link e se ne vuole uno: MED in uscita, messo dall'AS
  successivo, sui link da non usare (stairs: "AS1 preferisce ricevere dal link B");
- "le altre strade sono vietate": prefix-list deny in ingresso sulle altre sessioni, per la rete
  di destinazione (lift, as100r1).
A lab spento il ragionamento usa solo i file (AS path più corto, senza le policy già scritte); a
lab acceso le tabelle BGP vere dicono dove la strada è già quella voluta (niente proposta lì).
Non è una garanzia: alla fine "Verifica percorso" (traceroute) dice come va davvero.
"""
import ipaddress
from collections import deque

LOCAL_PREF = 150
MED = 20


class ErrorePercorso(Exception):
    pass


def _net(x):
    try:
        return ipaddress.ip_network(str(x), strict=False)
    except ValueError:
        return None


def _ip(x):
    return str(x or '').split('/')[0]


class _Lab:
    def __init__(self, lab):
        self.disp = {d['nome']: d for d in lab['dispositivi']}
        self.lan = {l['nome']: l for l in lab['lan']}
        self.owner = {_ip(it['ip']): d['nome'] for d in lab['dispositivi'] for it in d['interfacce'] if it['ip']}
        self.sessioni = []          # sessioni eBGP: {router, ip, chi, as, lan}
        for d in lab['dispositivi']:
            if d['tipo'] != 'router' or 'bgpd' not in d['demoni'] or not self.as_di(d['nome']):
                continue
            for nb in (d.get('riepilogo') or {}).get('neighbor', []):
                if nb.get('tipo') != 'eBGP' or not nb.get('asn'):
                    continue
                lan = next((it['lan'] for it in d['interfacce'] if it['ip'] and _net(it['ip'])
                            and ipaddress.ip_address(nb['ip']) in _net(it['ip'])), None)
                self.sessioni.append({'router': d['nome'], 'ip': nb['ip'], 'chi': nb.get('chi') or self.owner.get(nb['ip']),
                                      'as': str(nb['asn']), 'lan': lan})
        self.adiacenti = {}
        for s in self.sessioni:
            a = self.as_di(s['router'])
            self.adiacenti.setdefault(a, set()).add(s['as'])
            self.adiacenti.setdefault(s['as'], set()).add(a)

    def as_di(self, nome):
        g = (self.disp.get(nome) or {}).get('gruppo')
        return str(g) if g not in (None, '', '_') else None

    def distanza(self, da, a, evita):
        """Numero di salti fra AS da `da` ad `a` senza passare dagli AS in `evita`; None se non c'è."""
        if da == a:
            return 0
        visti, coda = {da}, deque([(da, 0)])
        while coda:
            x, d = coda.popleft()
            for y in sorted(self.adiacenti.get(x, ())):
                if y == a:
                    return d + 1
                if y not in visti and y not in evita:
                    visti.add(y)
                    coda.append((y, d + 1))
        return None

    def cammino(self, da, a, evita):
        """AS intermedi del cammino più corto da `da` ad `a` (esclusi gli estremi), o None."""
        prec, coda = {da: None}, deque([da])
        while coda:
            x = coda.popleft()
            if x == a:
                out = []
                while prec[x] is not None and prec[x] != da:
                    x = prec[x]
                    out.append(x)
                return list(reversed(out))
            for y in sorted(self.adiacenti.get(x, ())):
                if y not in prec and (y == a or y not in evita):
                    prec[y] = x
                    coda.append(y)
        return None


def _destinazione(L, punto):
    """(subnet, IP da usare per la verifica) del punto di arrivo."""
    if punto['tipo'] == 'lan':
        l = L.lan.get(punto['nome'])
        if not l or not l['subnet']:
            raise ErrorePercorso(f"La LAN {punto['nome']} non ha una subnet.")
        membri = [L.disp[m] for m in l['membri'] if m in L.disp]
        membri.sort(key=lambda d: d['tipo'] == 'router')         # prima host e server
        ip = next((_ip(it['ip']) for d in membri for it in d['interfacce'] if it['lan'] == l['nome'] and it['ip']), None)
        return _net(l['subnet']), ip
    d = L.disp.get(punto['nome'])
    it = next((it for it in (d or {}).get('interfacce', []) if it['ip']), None)
    if not it:
        raise ErrorePercorso(f"{punto['nome']} non ha un indirizzo IP.")
    return _net(it['ip']), _ip(it['ip'])


def analizza(lab, punti):
    """Sequenza di AS, link richiesti e rete BGP di destinazione."""
    if len(punti) < 2:
        raise ErrorePercorso('Servono almeno la sorgente e la destinazione.')
    L = _Lab(lab)
    if punti[0]['tipo'] != 'dev' or punti[0]['nome'] not in L.disp:
        raise ErrorePercorso('Il primo punto è la sorgente: un dispositivo.')
    sub, ip_dest = _destinazione(L, punti[-1])
    candidate = [(n, r) for r, d in L.disp.items() for n in ((d.get('riepilogo') or {}).get('bgp_networks') or [])
                 if _net(n) and sub.subnet_of(_net(n))]
    if not candidate:
        raise ErrorePercorso(f"Nessun router annuncia in BGP una rete che contiene {sub}: senza una network BGP non "
                             f"c'è una scelta di BGP da guidare.")
    lung = max(_net(n).prefixlen for n, _ in candidate)
    rete = next(n for n, _ in candidate if _net(n).prefixlen == lung)
    origini = sorted({L.as_di(r) for n, r in candidate if n == rete and L.as_di(r)})
    as_arrivo = punti[-1]['tipo'] == 'dev' and L.as_di(punti[-1]['nome'])
    origine = as_arrivo if as_arrivo in origini else (origini[0] if origini else None)
    if not origine:
        raise ErrorePercorso(f"Non so a quale AS appartiene chi annuncia {rete}.")

    seq, link, note = [], {}, []

    def aggiungi(a, perche):
        if not a:
            raise ErrorePercorso(f"Non so a quale AS appartiene {perche}.")
        if seq and seq[-1] == a:
            return
        if a in seq:
            raise ErrorePercorso(f"Il percorso passa due volte da AS{a} ({perche}): BGP non lo permette (loop).")
        if seq and a not in L.adiacenti.get(seq[-1], ()):
            mezzo = L.cammino(seq[-1], a, set(seq))
            if mezzo is None:
                raise ErrorePercorso(f"AS{seq[-1]} e AS{a} non sono collegati in BGP: aggiungi i punti in mezzo.")
            note.append(f"Fra AS{seq[-1]} e AS{a} ho messo il cammino più corto: {' '.join('AS' + x for x in mezzo)}.")
            seq.extend(mezzo)
        seq.append(a)

    for p in punti:
        if p['tipo'] == 'dev':
            aggiungi(L.as_di(p['nome']), p['nome'])
        elif p['tipo'] == 'as':
            aggiungi(str(p['nome']), 'AS' + str(p['nome']))
        elif p['tipo'] == 'lan':
            l = L.lan.get(p['nome'])
            ases = sorted({L.as_di(m) for m in (l or {}).get('membri', []) if L.as_di(m)
                           and L.disp[m]['tipo'] == 'router'})
            if len(ases) == 2:
                x, y = ases
                lontano = lambda a: L.distanza(seq[-1], a, set()) if L.distanza(seq[-1], a, set()) is not None else 99
                if seq and (seq[-1] == y or (seq[-1] != x and lontano(y) < lontano(x))):
                    x, y = y, x
                aggiungi(x, 'la LAN ' + p['nome'])
                aggiungi(y, 'la LAN ' + p['nome'])
                link[(x, y)] = p['nome']
            elif len(ases) == 1:
                aggiungi(ases[0], 'la LAN ' + p['nome'])
            else:
                raise ErrorePercorso(f"La LAN {p['nome']} non è un link fra due AS né dentro un AS.")
    if seq[-1] != origine:
        aggiungi(origine, f"chi annuncia {rete}")
    doppi = sorted({a for a in seq if seq.count(a) > 1})
    if doppi:
        raise ErrorePercorso(f"Il percorso passa due volte da AS{doppi[0]}: BGP non lo permette (loop).")
    if len(seq) == 1:
        raise ErrorePercorso(f"Sorgente e destinazione sono nello stesso AS (AS{seq[0]}): dentro un AS la strada la "
                             f"decide l'IGP (per OSPF il costo delle interfacce), non BGP.")
    return {'lab': L, 'sequenza': seq, 'link': link, 'rete': rete, 'origine': origine, 'note': note,
            'sorgente': punti[0]['nome'], 'ip': ip_dest}


def router_da_leggere(analisi):
    """Router BGP degli AS del percorso (tranne l'ultimo): le loro tabelle per la rete dicono la strada di oggi."""
    L = analisi['lab']
    as_ = set(analisi['sequenza'][:-1])
    return sorted(n for n, d in L.disp.items() if d['tipo'] == 'router' and 'bgpd' in d['demoni'] and L.as_di(n) in as_)


def _tag(ip):
    return ip.replace('.', '_')


def _gia(stato, router, nome):
    d = stato['dispositivi'].get(router) or {}
    return (d.get('frr') or {}).get('prefix_list', {}).get(nome) if d.get('frr') else None


def _local_pref_gia(stato, s, rete):
    """La sessione ha già la route-map di local-preference del programma che vale anche per `rete`."""
    d = stato['dispositivi'].get(s['router']) or {}
    frr = d.get('frr') or {}
    if f"PREF_IN_{_tag(s['ip'])}" not in frr.get('route_map', {}):
        return False
    nets = frr.get('prefix_list', {}).get(f"PREF_IN_{_tag(s['ip'])}_NETS")
    return nets is None or any(x['rete'] == rete for x in nets)


def _usa_oggi(L, paths, prossimo, des):
    """(va bene, descrizione) della rotta scelta oggi da un router (tabella BGP del lab acceso)."""
    best = next((p for p in paths or [] if p.get('best')), None)
    if not best:
        return False, 'nessuna rotta'
    primo = (best.get('aspath') or '').split()[:1]
    ips = {s['ip'] for s in des}
    via = {best.get('da'), best.get('nexthop')}
    ok = primo == [prossimo] and (not des or bool(ips & via) or bool({L.owner.get(x) for x in via if x} & {s['router'] for s in des}))
    return ok, f"AS path {best.get('aspath') or '-'} via {best.get('nexthop') or best.get('da')}"


def proponi(analisi, stato, vieta=(), tabelle=None):
    """Proposte di policy (parametri di calcola_policy) per ogni punto di scelta del percorso.
    vieta: AS in cui le altre strade sono vietate (prefix-list deny invece della local-preference)."""
    vieta = {str(x) for x in (vieta or ())}
    L, seq, rete = analisi['lab'], analisi['sequenza'], analisi['rete']
    note, proposte, viste = list(analisi['note']), [], set()

    def proponi_una(par, titolo, perche, as_):
        chiave = (par['router'], par['neighbor'], par['tipo'], par.get('direzione'))
        if chiave in viste:
            return
        viste.add(chiave)
        proposte.append({'operazione': 'policy', 'parametri': dict({'asn_nuovo': None}, **par),
                         'titolo': titolo, 'perche': perche, 'as': as_})

    def deny(s, X, perche):
        nome = f"PL_{s['router']}_{_tag(s['ip'])}_in"
        if any(x['azione'] == 'deny' and x['rete'] == rete for x in (_gia(stato, s['router'], nome) or [])):
            note.append(f"AS{X}: {s['router']} scarta già {rete} da {s['chi'] or s['ip']}.")
            return
        proponi_una({'router': s['router'], 'neighbor': s['ip'], 'tipo': 'prefix_list', 'direzione': 'in', 'reti': [rete]},
                    f"Prefix-list su {s['router']}: scarta {rete} da {s['chi'] or s['ip']}", perche, X)

    for i in range(len(seq) - 1):
        X, Y = seq[i], seq[i + 1]
        uscite = [s for s in L.sessioni if L.as_di(s['router']) == X]
        lan = analisi['link'].get((X, Y))
        des = [s for s in uscite if s['as'] == Y and (lan is None or s['lan'] == lan)]
        if not des:
            raise ErrorePercorso(f"Nessuna sessione eBGP fra AS{X} e AS{Y}" + (f" sul link {lan}." if lan else '.'))
        paralleli = [s for s in uscite if s['as'] == Y and s not in des]
        prima = set(seq[:i + 1])
        l_voluto = len(seq) - 1 - i
        alternative = []
        for s in uscite:
            if s['as'] != Y and s['as'] not in prima:
                d = L.distanza(s['as'], seq[-1], prima)
                if d is not None:
                    alternative.append((s, 1 + d))
        verso = f"AS{Y}" + (f" sul link {lan}" if lan else '')
        oggi_ok, oggi = None, []
        if tabelle is not None:
            esiti = [(r, _usa_oggi(L, tabelle.get(r), Y, des if (lan or paralleli) else []))
                     for r in sorted({s['router'] for s in uscite})]
            oggi_ok = all(ok for _, (ok, _) in esiti)
            oggi = [f"{r}: {t}" for r, (_, t) in esiti]
            if oggi_ok and X not in vieta:
                note.append(f"AS{X} usa già {verso} per {rete} (tabelle del lab acceso: {'; '.join(oggi)}): niente da fare.")
                continue
        corte = [(s, l) for s, l in alternative if l <= l_voluto]
        for s, _ in alternative:
            if _local_pref_gia(stato, s, rete):
                note.append(f"Attenzione: su {s['router']} c'è già una local-preference per {rete} da {s['chi'] or s['ip']} "
                            f"(AS{s['as']}): va contro questo percorso. Controllala con 'File a righe' o Annulla.")
        if X in vieta:
            for s, l in alternative:
                deny(s, X, f"Le altre strade sono vietate: AS{X} non deve arrivare a {rete} passando da AS{s['as']} "
                           f"(link {s['lan']}), nemmeno come riserva.")
            for s in paralleli:
                deny(s, X, f"Le altre strade sono vietate: AS{X} deve usare il link {lan}, non {s['lan']}.")
            if not alternative and not paralleli:
                note.append(f"AS{X}: l'unica uscita verso {rete} è già {verso}.")
            continue
        if corte or (oggi_ok is False and alternative):
            perche = (f"AS{X} ha anche " + ', '.join(f"l'uscita verso AS{s['as']} (AS path di {l})" for s, l in alternative)
                      + f"; quella voluta, {verso}, ha un AS path di {l_voluto}. La local-preference più alta vince "
                      f"prima della lunghezza dell'AS path e si propaga in iBGP a tutto AS{X}.")
            if oggi:
                perche += ' Oggi: ' + '; '.join(oggi) + '.'
            for s in des:
                tag = _tag(s['ip'])
                gia = _gia(stato, s['router'], f"PREF_IN_{tag}_NETS")
                reti = [rete]
                if gia:
                    reti = [x['rete'] for x in gia if x['azione'] == 'permit' and x['rete'] != rete] + [rete]
                proponi_una({'router': s['router'], 'neighbor': s['ip'], 'tipo': 'local_pref', 'valore': LOCAL_PREF, 'reti': reti},
                            f"Local-preference {LOCAL_PREF} su {s['router']} da {s['chi'] or s['ip']} per {rete}",
                            perche + (f" Le reti che la route-map aveva già restano: {', '.join(reti[:-1])}." if len(reti) > 1 else ''), X)
            continue
        if paralleli:
            for s in paralleli:
                mio_ip = next((_ip(it['ip']) for it in L.disp[s['router']]['interfacce'] if it['lan'] == s['lan'] and it['ip']), None)
                if not s['chi'] or not mio_ip:
                    note.append(f"AS{X}: non trovo il router di AS{Y} sul link {s['lan']}: metti tu il MED.")
                    continue
                proponi_una({'router': s['chi'], 'neighbor': mio_ip, 'tipo': 'med', 'valore': MED},
                            f"MED {MED} su {s['chi']} verso {s['router']} (link {s['lan']})",
                            f"AS{X} arriva ad AS{Y} anche dal link {s['lan']}: AS{Y} lo annuncia con un MED più alto, così "
                            f"AS{X} preferisce il link {lan} (fra annunci dello stesso AS vince il MED più basso). Il MED vale "
                            f"per tutte le rotte annunciate su quel link." + (' Oggi: ' + '; '.join(oggi) + '.' if oggi else ''), X)
            continue
        if oggi_ok is False:
            note.append(f"AS{X} non usa {verso} per {rete} ({'; '.join(oggi)}) ma non vedo altre uscite: controlla le "
                        f"policy già scritte e le sessioni.")
        elif alternative:
            note.append(f"AS{X}: BGP sceglie già {verso}, AS path più corto ({l_voluto} contro "
                        f"{min(l for _, l in alternative)}), se nessuna policy già scritta lo cambia.")
        else:
            note.append(f"AS{X}: l'unica uscita verso {rete} è {verso}.")
    if not proposte:
        note.append('Nessuna policy da proporre.')
    return {'sequenza': seq, 'rete': rete, 'origine': analisi['origine'], 'note': note, 'proposte': proposte,
            'link': [{'da': x, 'a': y, 'lan': l} for (x, y), l in analisi['link'].items()],
            'modo': 'tabelle' if tabelle is not None else 'file',
            'verifica': {'dev': analisi['sorgente'], 'ip': analisi['ip'],
                         'atteso': ' '.join(l for l in [analisi['link'].get((seq[i], seq[i + 1])) for i in range(len(seq) - 1)] if l)}}
