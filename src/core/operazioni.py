"""
src/core/operazioni.py
Le Opzioni del laboratorio come dati: per ognuna `opzioni_X(stato)` (cosa si può scegliere) e
`calcola_X(stato, ...)` (il piano di modifica, senza scrivere nulla).

Terminale e GUI usano le stesse funzioni: il terminale fa le domande e passa il piano a
_applica_modifiche (anteprima, conferma, copia di sicurezza, scrittura); la GUI mostrerà
l'anteprima e scriverà con scrivi_piano.

Ogni calcola_X fa girare la logica di scrittura di sempre dentro i file in memoria
(file_utils.file_virtuali): il risultato è identico a quello che si otteneva scrivendo
direttamente, ma il disco non cambia finché il piano non viene confermato. I messaggi di esito
stampati dalla logica ("✅ ...") vengono raccolti in piano['messaggi'], da mostrare dopo la
scrittura.
"""
import contextlib
import io
import ipaddress
import os
import re

from .analyzer import _analizza_frr, isole_ospf
from .file_utils import (
    _comandi_nodo,
    _esiste_file,
    _indici_nodo,
    _inizio_blocco,
    _inserisci_nel_blocco,
    _leggi_righe,
    _leggi_testo,
    _righe_file,
    _rimuovi_righe,
    _scrivi_righe,
    _scrivi_testo,
    append_frr_stanza,
    file_virtuali,
    insert_lines_into_protocol_block,
)
from .modifiche import nuovo_piano
from .net_frr import (
    _ip_verso,
    _norm_net,
    _reti_peering,
    add_ibgp_loopback_neighbors,
    default_bgp_aggregate,
)


class ErroreOperazione(Exception):
    """I parametri non permettono l'operazione; il messaggio spiega perché (testo per l'utente)."""


def routers_dello_stato(stato):
    """Router nel formato dei dati del wizard/XML, ricavati dai file (non dall'XML)."""
    from .persistence import dati_da_stato
    return dati_da_stato(stato)[0]


def _frr(stato, router):
    return os.path.join(stato['percorso'], router, 'etc', 'frr', 'frr.conf')


@contextlib.contextmanager
def _in_memoria(stato):
    """Esegue la logica di scrittura nei file in memoria; raccoglie quello che stampa."""
    out = io.StringIO()
    with file_virtuali(stato['percorso']) as fs, contextlib.redirect_stdout(out):
        yield fs, out


def _piano(titolo, fs, out, note=None, vuoto=None):
    """Piano dai file in memoria. Le righe stampate che iniziano con ⚠️ diventano note (da leggere
    prima di confermare); le altre sono i messaggi di esito, da mostrare dopo la scrittura."""
    note = list(note or [])
    messaggi = []
    for r in out.getvalue().split('\n'):
        if r.lstrip().startswith('⚠️'):
            note.append(r.lstrip()[len('⚠️'):].strip())
        else:
            messaggi.append(r)
    while messaggi and not messaggi[-1].strip():
        messaggi.pop()
    piano = nuovo_piano(titolo, fs.modifiche(), note)
    piano['messaggi'] = messaggi
    piano['vuoto'] = vuoto          # messaggio da dare se il piano non cambia nulla
    return piano


# ----------------------------------------------------------------------------- 1. costo OSPF

def opzioni_costo_ospf(stato):
    """{router: [interfacce]} dei router con OSPF."""
    return {n: [it['dev'] for it in d['interfacce']]
            for n, d in stato['dispositivi'].items() if d['frr'] and d['frr']['ospf']}


_RE_COSTO = re.compile(r'^(\s*(?:ip\s+)?ospf\s+cost\s+)(\d+)(\s*)$')


def _blocchi_interfaccia(righe, interfaccia):
    """[(inizio, fine)] dei blocchi 'interface <interfaccia>' del frr.conf (fine esclusa)."""
    from .file_utils import _fine_blocco
    rx = re.compile(rf'^interface\s+{re.escape(interfaccia)}\s*$')
    return [(k, _fine_blocco(righe, k)) for k, l in enumerate(righe) if rx.match(l)]


def _righe_costo(righe, interfaccia):
    """Indici delle righe 'ospf cost N' dentro i blocchi dell'interfaccia."""
    return [k for a, b in _blocchi_interfaccia(righe, interfaccia) for k in range(a + 1, b) if _RE_COSTO.match(righe[k])]


def calcola_costo_ospf(stato, router, interfaccia, costo):
    """Costo OSPF di un'interfaccia. Se l'interfaccia ha già un costo si cambia il numero nella sua
    riga; se ha un blocco 'interface' senza costo la riga va dentro quel blocco; altrimenti si
    aggiunge il blocco in fondo al frr.conf."""
    costo = int(costo)
    if not 1 <= costo <= 65535:
        raise ErroreOperazione('Il costo OSPF deve essere un intero da 1 a 65535.')
    rel = os.path.join(router, 'etc', 'frr', 'frr.conf')
    path = os.path.join(stato['percorso'], rel)
    righe = _righe_file(path) if os.path.isfile(path) else None
    if righe is not None:
        gia = _righe_costo(righe, interfaccia)
        blocchi = _blocchi_interfaccia(righe, interfaccia)
        if gia:
            vecchi = sorted({_RE_COSTO.match(righe[k]).group(2) for k in gia})
            if vecchi == [str(costo)]:
                return _piano_diretto(f"Costo OSPF di {router} {interfaccia}", {}, vuoto=f"Il costo è già {costo}.")
            nuove = list(righe)
            for k in gia:
                nuove[k] = _RE_COSTO.sub(lambda m: f"{m.group(1)}{costo}{m.group(3)}", nuove[k])
            note = [f"C'erano {len(gia)} righe di costo per {interfaccia} (blocchi ripetuti): ora dicono tutte {costo}."] if len(gia) > 1 else []
            return _piano_diretto(f"Costo OSPF di {router} {interfaccia}: {' / '.join(vecchi)} -> {costo}",
                                  {rel: (righe, nuove)}, note)
        if blocchi:
            _, fine = blocchi[-1]
            nuove = righe[:fine] + [f"    ospf cost {costo}"] + righe[fine:]
            return _piano_diretto(f"Costo OSPF di {router} {interfaccia}: {costo}", {rel: (righe, nuove)})
    if costo < 1:
        raise ErroreOperazione('Il costo OSPF deve essere un intero ≥ 1.')
    with _in_memoria(stato) as (fs, out):
        if append_frr_stanza(stato['percorso'], router, f"interface {interfaccia}\n    ospf cost {costo}\n"):
            print(f"✅ Costo impostato su {router} {interfaccia} = {costo} (append su frr.conf).")
    return _piano(f"Costo OSPF di {router} {interfaccia}: {costo}", fs, out)


def calcola_togli_costo_ospf(stato, router, interfaccia):
    """Toglie il costo OSPF scritto per l'interfaccia (torna quello predefinito); un blocco
    'interface' rimasto vuoto sparisce con la sua riga vuota."""
    rel = os.path.join(router, 'etc', 'frr', 'frr.conf')
    path = os.path.join(stato['percorso'], rel)
    if not os.path.isfile(path):
        raise ErroreOperazione(f"{router} non ha frr.conf.")
    righe = _righe_file(path)
    gia = set(_righe_costo(righe, interfaccia))
    if not gia:
        return _piano_diretto(f"Togli il costo OSPF di {router} {interfaccia}", {},
                              vuoto=f"{interfaccia} non ha un costo scritto: usa già quello predefinito.")
    vuoti = {a for a, b in _blocchi_interfaccia(righe, interfaccia)
             if all(k in gia or not righe[k].strip() for k in range(a + 1, b))}
    togli = set(gia)
    for a in vuoti:
        togli.add(a)
        if a > 0 and not righe[a - 1].strip():          # la riga vuota che separava il blocco
            togli.add(a - 1)
    nuove = [l for k, l in enumerate(righe) if k not in togli]
    while nuove and not nuove[-1].strip():
        nuove.pop()
    vecchi = sorted({_RE_COSTO.match(righe[k]).group(2) for k in gia})
    return _piano_diretto(f"Togli il costo OSPF di {router} {interfaccia} ({' / '.join(vecchi)})", {rel: (righe, nuove)})


# ----------------------------------------------------------------------------- 10. auto-cost

def opzioni_auto_cost(stato):
    """[{'etichetta', 'router', 'con_auto_cost', 'costi'}] per ogni gruppo OSPF (AS) del lab."""
    out = []
    for et, rs, cfgs in isole_ospf(stato['percorso'], stato):
        out.append({'etichetta': et, 'router': rs,
                    'con_auto_cost': [r for r in rs if cfgs[r]['auto_cost']],
                    'costi': [f"{r} {c}" for r in rs for c in cfgs[r]['costi']]})
    return out


def calcola_auto_cost(stato, etichetta, togli=False):
    """auto-cost reference-bandwidth 100 su tutti i router OSPF del gruppo (togli=True: lo toglie)."""
    gruppo = next((g for g in opzioni_auto_cost(stato) if g['etichetta'] == etichetta), None)
    if gruppo is None:
        raise ErroreOperazione(f"Nessun gruppo OSPF {etichetta} nel lab.")
    rs = gruppo['router']
    with _in_memoria(stato) as (fs, out):
        for r in rs:
            _rimuovi_righe(_frr(stato, r), lambda l: l.strip().startswith('auto-cost reference-bandwidth'))
            if not togli:
                insert_lines_into_protocol_block(_frr(stato, r), proto='ospf', lines=['auto-cost reference-bandwidth 100'])
        if togli:
            print(f"✅ Tolto da {', '.join(rs)}: il costo predefinito torna quello senza auto-cost (misurato con Kathará: 10).")
        else:
            print("✅ Fatto. Controlla con la GUI (show ip ospf interface: il costo di ogni interfaccia) e con Test -> Verifica percorso.")
    titolo = f"{'Togli' if togli else 'Aggiungi'} auto-cost reference-bandwidth 100 su {etichetta}"
    return _piano(titolo, fs, out)


# ----------------------------------------------------------------------------- 3. loopback

def _aggiungi_riga_startup(path, riga):
    """Mette 'riga' nello startup prima di 'systemctl start', o in fondo. False se c'era già."""
    testo = _leggi_testo(path)
    lines = [] if testo is None else [l + '\n' for l in testo.split('\n')]
    if lines and lines[-1] == '\n':
        lines.pop()
    elif lines:
        lines[-1] = lines[-1][:-1]
    if any(l.strip() == riga for l in lines):
        return False
    idx = next((i for i, l in enumerate(lines) if re.match(r'^\s*systemctl start\b', l)), None)
    if idx is None:
        if lines and not lines[-1].endswith('\n'):
            lines[-1] = lines[-1] + '\n'
        lines.append(riga + '\n')
    else:
        lines.insert(idx, riga + '\n')
    _scrivi_testo(path, ''.join(lines))
    return True


def opzioni_loopback(stato):
    """Dispositivi a cui si può aggiungere una loopback, con tipo e loopback già presenti."""
    return {n: {'tipo': d['tipo'], 'loopback': list(d['loopback'])} for n, d in stato['dispositivi'].items()}


def calcola_loopback(stato, dispositivo, ip, area=None):
    """Loopback /32 su un dispositivo; sui router anche la network negli IGP e l'iBGP su loopback."""
    d = stato['dispositivi'].get(dispositivo)
    if d is None:
        raise ErroreOperazione(f"Dispositivo {dispositivo} non trovato.")
    ipcidr = ip.split('/')[0] + '/32'
    startup = os.path.join(stato['percorso'], f"{dispositivo}.startup")
    riga = f"ip address add {ipcidr} dev lo"
    note = []
    with _in_memoria(stato) as (fs, out):
        if d['tipo'] != 'router':
            if _aggiungi_riga_startup(startup, riga):
                print(f"✅ Loopback {ipcidr} aggiunta a {dispositivo} (startup).")
            else:
                print(f'⚠️ Loopback {ipcidr} già presente nello startup di {dispositivo}.')
        else:
            routers = routers_dello_stato(stato)
            lbs = routers.setdefault(dispositivo, {}).setdefault('loopbacks', [])
            if ipcidr in lbs:
                note.append('Loopback già presente nei dati del router.')
            else:
                lbs.append(ipcidr)
            _aggiungi_riga_startup(startup, riga)
            fpath = _frr(stato, dispositivo)
            if _esiste_file(fpath):
                if d['frr']['ospf']:
                    a = routers[dispositivo].get('ospf_area') or area or '0.0.0.0'
                    insert_lines_into_protocol_block(fpath, proto='ospf', lines=[f"network {ipcidr} area {a}"])
                if d['frr']['rip']:
                    insert_lines_into_protocol_block(fpath, proto='rip', lines=[f"network {ipcidr}"])
                try:
                    add_ibgp_loopback_neighbors(stato['percorso'], routers)
                except Exception:
                    pass
                print(f"\n\n✅ Loopback {ipcidr} aggiunta a router {dispositivo} (startup aggiornato).\n")
            else:
                print(f"⚠️ frr.conf non trovato per {dispositivo}; è stata aggiornata solo la startup (se esistente).")
    return _piano(f"Loopback {ipcidr} su {dispositivo}", fs, out, note)


# ----------------------------------------------------------------------------- 6. network BGP

def _network_bgp(righe):
    presenti, in_bgp = set(), False
    for l in righe:
        s = l.strip()
        if s.startswith('router '):
            in_bgp = s.startswith('router bgp')
        elif l and not l[0].isspace():
            in_bgp = False
        elif in_bgp and s.startswith('network ') and len(s.split()) >= 2:
            presenti.add(_norm_net(s.split()[1]))
    return presenti


def opzioni_network_bgp(stato, router=None, reti=None):
    """Router BGP con la proposta di aggregato e le network già annunciate; con `router` e `reti`
    anche le network già annunciate che quelle reti coprirebbero ('coperte', come chiede il terminale)."""
    routers = routers_dello_stato(stato)
    out = {}
    for n, d in stato['dispositivi'].items():
        if d['frr'] and d['frr']['bgp'] and (router is None or n == router):
            out[n] = {'proposta': default_bgp_aggregate(n, routers[n]),
                      'presenti': sorted(_network_bgp(_righe_file(_frr(stato, n))))}
    if router in out and reti:
        try:
            out[router]['coperte'] = reti_coperte(stato, router, [str(ipaddress.ip_network(r, strict=False)) for r in reti])
        except ValueError:
            raise ErroreOperazione('Rete non valida: scrivila come 20.20.0.0/16.')
    return out


def reti_coperte(stato, router, reti):
    """Network già annunciate (non di peering) contenute negli aggregati che si stanno aggiungendo."""
    presenti = _network_bgp(_righe_file(_frr(stato, router)))
    nuove = [r for r in reti if r not in presenti]
    aggregati = [ipaddress.ip_network(r) for r in nuove]
    peering = _reti_peering(router, routers_dello_stato(stato))
    return sorted(
        p for p in presenti
        if p not in peering
        and any(ipaddress.ip_network(p) != a and ipaddress.ip_network(p).subnet_of(a) for a in aggregati)
    )


def calcola_network_bgp(stato, router, reti, togli_coperte=False):
    """Aggiunge `reti` al blocco router bgp; con togli_coperte toglie le reti contenute negli aggregati."""
    fpath = _frr(stato, router)
    presenti = _network_bgp(_righe_file(fpath))
    nuove = [r for r in reti if r not in presenti]
    coperte = reti_coperte(stato, router, reti) if togli_coperte else []
    with _in_memoria(stato) as (fs, out):
        if nuove:
            insert_lines_into_protocol_block(fpath, proto='bgp', asn=None, lines=[f"network {r}" for r in nuove])
            print(f"✅ {router}: aggiunte in BGP {', '.join(nuove)}")
        if coperte:
            righe_out, in_bgp = [], False
            for l in _leggi_righe(fpath):
                s = l.strip()
                if s.startswith('router '):
                    in_bgp = s.startswith('router bgp')
                elif l and not l[0].isspace():
                    in_bgp = False
                elif in_bgp and s.startswith('network ') and len(s.split()) == 2 and _norm_net(s.split()[1]) in coperte:
                    continue
                righe_out.append(l)
            _scrivi_righe(fpath, righe_out)
            print(f"✅ {router}: tolte da BGP {', '.join(coperte)}")
    piano = _piano(f"Network BGP su {router}: {', '.join(reti)}", fs, out,
                   vuoto='Tutte le reti indicate sono già annunciate.')
    piano['aggiunte'] = nuove
    return piano


# ----------------------------------------------------------------------------- 7. iBGP full-mesh

def opzioni_ibgp(stato):
    """{asn: [router]} degli AS con almeno due router BGP."""
    per_as = {}
    for rn, rd in routers_dello_stato(stato).items():
        if 'bgp' in rd.get('protocols', []) and str(rd.get('asn', '')).strip():
            per_as.setdefault(str(rd['asn']).strip(), []).append(rn)
    return {a: ns for a, ns in per_as.items() if len(ns) >= 2}


def calcola_ibgp(stato, asn):
    """Sessioni iBGP mancanti tra tutti i router BGP dell'AS (full mesh)."""
    candidati = opzioni_ibgp(stato)
    if asn not in candidati:
        raise ErroreOperazione('Selezione non valida.')
    routers = routers_dello_stato(stato)
    membri = candidati[asn]
    with _in_memoria(stato) as (fs, out):
        aggiunte = 0
        for x in membri:
            fpath = _frr(stato, x)
            presenti = set(re.findall(r'neighbor (\S+) remote-as', '\n'.join(_leggi_righe(fpath))))
            nuove = []
            for y in membri:
                if y == x:
                    continue
                ips_y = {str(ipaddress.ip_interface(it['ip']).ip) for it in routers[y].get('interfaces', []) if it.get('ip')}
                if presenti & ips_y:
                    continue
                ip = _ip_verso(routers, y, x, asn)
                if ip:
                    nuove += [f"neighbor {ip} remote-as {asn}", f"neighbor {ip} description iBGP {y}"]
            if nuove:
                insert_lines_into_protocol_block(fpath, proto='bgp', asn=None, lines=nuove)
                aggiunte += len(nuove) // 2
                print(f"✅ {x}: " + ', '.join(l.split()[1] for l in nuove if 'remote-as' in l))
        if aggiunte:
            print(f"Sessioni iBGP aggiunte: {aggiunte}")
    return _piano(f"Sessioni iBGP nell'AS {asn}", fs, out, vuoto='Tutte le sessioni iBGP erano già presenti.')


# ----------------------------------------------------------------------------- 12. default route

def opzioni_default_originate(stato, router):
    """Neighbor BGP di un router: [(ip, asn, nome, tipo, ha_già_default)] e il cfg di frr.conf."""
    cfg = _analizza_frr(_righe_file(_frr(stato, router)))
    if not cfg['asn'] or not cfg['neighbors']:
        raise ErroreOperazione(f"{router} non ha neighbor BGP in frr.conf: crea prima le sessioni.")
    return cfg


def calcola_default_originate(stato, router, scelti, solo=False, extra=(), owner=None):
    """'neighbor X default-originate' verso i neighbor scelti; con solo=True anche la prefix-list
    che lascia passare solo la default (più le reti `extra`)."""
    rel = os.path.join(router, 'etc', 'frr', 'frr.conf')
    fpath = os.path.join(stato['percorso'], rel)
    extra = list(extra)
    owner = owner or {}
    with file_virtuali(stato['percorso']):
        vecchie = _righe_file(fpath)
    cfg = _analizza_frr(vecchie)
    nuove, note = list(vecchie), []
    righe_bgp = []
    for ip in scelti:
        if ip not in cfg['default_orig']:
            righe_bgp.append(f"neighbor {ip} default-originate")
        if solo:
            pl = f"SOLO_DEFAULT_{ip.replace('.', '_')}"
            for t_, nome, direz in cfg['link'].get(ip, []):
                if t_ == 'prefix-list' and direz == 'out' and nome != pl:
                    note.append(
                        f"{ip} aveva già 'prefix-list {nome} out': FRR ne usa una sola per direzione, "
                        f"la sostituisco con {pl}."
                    )
                    nuove = [l for l in nuove if ' '.join(l.split()) != f"neighbor {ip} prefix-list {nome} out"]
            nuove = [l for l in nuove if not l.strip().startswith(f"ip prefix-list {pl} ")]
            if f"neighbor {ip} prefix-list {pl} out" not in (' '.join(l.split()) for l in nuove):
                righe_bgp.append(f"neighbor {ip} prefix-list {pl} out")
            nuove += [''] + [f"ip prefix-list {pl} permit {r}" for r in ['0.0.0.0/0'] + extra]
    if righe_bgp:
        ins = _inserisci_nel_blocco(nuove, r'router bgp\b', righe_bgp)
        if ins is None:
            raise ErroreOperazione(f"{router}: manca il blocco 'router bgp' in frr.conf.")
        nuove = ins
    pulite = []
    for l in nuove:
        if not l.strip() and pulite and not pulite[-1].strip():
            continue
        pulite.append(l)
    while pulite and not pulite[-1].strip():
        pulite.pop()
    annunciate = {_norm_net(n) for n in cfg['bgp_networks']}
    for r in extra:
        if _norm_net(r) not in annunciate:
            note.append(
                f"{r} non è tra le network BGP di {router}: la prefix-list la lascia passare, ma per "
                f"annunciarla serve anche Opzioni 6 (network {r})."
            )
    note.append(
        "default-originate da solo basta: 'network 0.0.0.0/0' non serve (slide 044). "
        "Se il testo o la soluzione lo vogliono comunque: Opzioni 6."
    )
    if not solo:
        note.append(
            "I neighbor ricevono la default IN PIÙ alle altre rotte. Se il testo dice 'just the "
            "default route', rispondi s alla domanda 'SOLO la default'."
        )
    piano = nuovo_piano(f"Default route da {router} verso {', '.join(owner.get(i, i) for i in scelti)}",
                        {rel: (vecchie, pulite)}, note)
    piano['messaggi'], piano['vuoto'] = [], None
    return piano


def opzioni_default_igp(stato, proto):
    """Router che hanno il blocco 'router <proto>' in frr.conf."""
    rx = rf'router {proto}\b'
    cand = []
    for d in sorted(os.listdir(stato['percorso'])):
        f = os.path.join(stato['percorso'], d, 'etc', 'frr', 'frr.conf')
        if os.path.isfile(f) and _inizio_blocco(_righe_file(f), rx) is not None:
            cand.append(d)
    return cand


def calcola_default_igp(stato, proto, router, modo='1', reti=('0.0.0.0/0',), ha_default=False):
    """Default route in RIP (modo '1' = route <rete>, '2' = default-information originate) o in
    OSPF (default-information originate, con 'always' se il router non ha una default sua)."""
    nome_p = proto.upper()
    rx = rf'router {proto}\b'
    rel = os.path.join(router, 'etc', 'frr', 'frr.conf')
    with file_virtuali(stato['percorso']):
        vecchie = _righe_file(os.path.join(stato['percorso'], rel))
    originali = list(vecchie)
    blocco = _comandi_nodo(vecchie, _inizio_blocco(vecchie, rx))
    note = []
    if proto == 'rip':
        if modo == '1':
            nuove = [f"route {r}" for r in reti if f"route {r}" not in blocco]
        else:
            nuove = [] if 'default-information originate' in blocco else ['default-information originate']
    else:
        riga = 'default-information originate' + ('' if ha_default else ' always')
        if riga in blocco:
            nuove = []
        else:
            togli = {
                k for k in _indici_nodo(vecchie, _inizio_blocco(vecchie, rx))
                if vecchie[k].strip().startswith('default-information originate')
            }
            vecchie = [l for k, l in enumerate(vecchie) if k not in togli]
            nuove = [riga]
        if not ha_default:
            note.append("'always' = OSPF annuncia la default anche se il router non ne ha una.")
    righe = _inserisci_nel_blocco(vecchie, rx, nuove) if nuove else originali
    piano = nuovo_piano(f"Default route in {nome_p} su {router}", {rel: (originali, righe)}, note)
    piano['messaggi'] = []
    piano['vuoto'] = f"{router}: è già tutto presente in router {proto}, niente da fare."
    return piano


# ----------------------------------------------------------------------------- 4. ridistribuzione

def opzioni_redistribuzione(stato):
    """Router con BGP e OSPF/RIP: {router: {igp: [righe redistribute]}}."""
    out = {}
    for n, d in stato['dispositivi'].items():
        f = d['frr']
        if f and f['bgp'] and (f['ospf'] or f['rip']):
            out[n] = {p: [r['testo'] for r in f[p]['redistribute']] for p in ('ospf', 'rip') if f[p]}
    return out


def calcola_redistribuzione(stato, router, attiva):
    """Toglie (attiva=False) o rimette (attiva=True) 'redistribute bgp' nei blocchi OSPF/RIP."""
    d = stato['dispositivi'].get(router)
    if not d or not d['frr']:
        raise ErroreOperazione(f"{router} non ha frr.conf.")
    fpath = _frr(stato, router)
    with _in_memoria(stato) as (fs, out):
        righe, blocco, presente = [], None, set()
        for l in _leggi_righe(fpath):
            s = l.strip()
            if s.startswith('router '):
                blocco = s.split()[1]
            elif l and not l[0].isspace():
                blocco = None
            if blocco in ('ospf', 'rip') and s == 'redistribute bgp':
                presente.add(blocco)
                if not attiva:
                    continue
            righe.append(l)
        protos = [p for p in ('ospf', 'rip') if d['frr'][p]]
        if attiva:
            mancanti = [p for p in protos if p not in presente]
            for p in mancanti:
                insert_lines_into_protocol_block(fpath, proto=p, asn=None, lines=['redistribute bgp'])
            print(f"✅ {router}: redistribute bgp "
                  + (f"aggiunto in {', '.join(mancanti)}." if mancanti else "era già presente."))
        else:
            _scrivi_righe(fpath, righe)
            print(f"✅ {router}: redistribute bgp "
                  + (f"tolto da {', '.join(sorted(presente))}." if presente else "non era presente."))
    return _piano(f"{'Rimetti' if attiva else 'Togli'} redistribute bgp su {router}", fs, out,
                  vuoto=f"✅ {router}: redistribute bgp " + ("era già presente." if attiva else "non era presente."))


def calcola_redistribuzione_route_map(stato, router, rete):
    """'redistribute bgp route-map eBGP': in OSPF/RIP solo le rotte con next-hop nella rete del neighbor."""
    d = stato['dispositivi'].get(router)
    fpath = _frr(stato, router)
    if not d or not d['frr']:
        raise ErroreOperazione(f"File {fpath} non trovato.")
    prefix = str(ipaddress.ip_network(rete, strict=False))
    global_conf = [
        f"ip prefix-list myNeighbors permit {prefix} le 32",
        "",
        "route-map eBGP permit 10",
        "    match ip next-hop prefix-list myNeighbors",
        ""
    ]
    redist_cmd = "redistribute bgp route-map eBGP"
    with _in_memoria(stato) as (fs, out):
        _scrivi_testo(fpath, (_leggi_testo(fpath) or '') + "\n\n" + ''.join(l + "\n" for l in global_conf))
        cur = [l + '\n' for l in (_leggi_testo(fpath) or '').split('\n')]
        cur[-1] = cur[-1][:-1]
        kept = [l for l in cur if l.strip() != 'redistribute bgp']
        if len(kept) != len(cur):
            _scrivi_testo(fpath, ''.join(kept))
        applied = False
        for p in ('rip', 'ospf'):
            if d['frr'][p] and insert_lines_into_protocol_block(fpath, proto=p, lines=['', redist_cmd]):
                print(f"✅ Aggiunto '{redist_cmd}' a router {p}.")
                applied = True
        if applied:
            print(f"✅ Configurazione completata su {router}.")
        else:
            print("❌ Impossibile applicare la ridistribuzione (protocollo IGP non trovato nel file?).")
    return _piano(f"Redistribute bgp con route-map eBGP su {router} (next-hop in {prefix})", fs, out)


# ----------------------------------------------------------------------------- 5. resolver

def opzioni_resolver(stato):
    """Dispositivi del lab (cartelle e startup) e server DNS candidati come nameserver [(nome, ip)]."""
    base = stato['percorso']
    dir_items = [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)) and not d.startswith('.')]
    startup = [os.path.splitext(fn)[0] for fn in os.listdir(base)
               if fn.endswith('.startup') and os.path.isfile(os.path.join(base, fn))]
    items = sorted(dict.fromkeys(dir_items + startup))
    candidati = []
    for d in items:
        if not os.path.isfile(os.path.join(base, d, 'etc', 'bind', 'named.conf')):
            continue
        for line in _righe_file(os.path.join(base, f"{d}.startup")):
            m = re.match(r'\s*ip\s+a(?:ddr(?:ess)?)?\s+add\s+(\S+)\s+dev\s+(\S+)', line)
            if m and m.group(2) != 'lo':
                candidati.append((d, m.group(1).split('/')[0]))
                break
    return {'dispositivi': items, 'candidati': candidati}


def calcola_resolver(stato, dispositivo, ip):
    """etc/resolv.conf del dispositivo con 'nameserver <ip>'."""
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        raise ErroreOperazione('IP non valido. Nessuna modifica effettuata.')
    dest = os.path.join(stato['percorso'], dispositivo, 'etc', 'resolv.conf')
    with _in_memoria(stato) as (fs, out):
        _scrivi_testo(dest, f"nameserver {ip}\n")
        print(f"✅ Wrote {dest} with nameserver {ip}")
    return _piano(f"Resolver di {dispositivo}: {ip}", fs, out)


# ----------------------------------------------------------------------------- 9. delega DNS

def opzioni_delega_dns(stato):
    """Server DNS del lab [(nome, è_il_root)]: il root è master per la zona '.'."""
    out = []
    for d in sorted(os.listdir(stato['percorso'])):
        nc = os.path.join(stato['percorso'], d, 'etc', 'bind', 'named.conf')
        if os.path.isfile(nc):
            testo = ' '.join(' '.join(_leggi_righe(nc)).split())
            out.append((d, re.search(r'zone "\." \{ type master;', testo) is not None))
    return out


def calcola_delega_dns(stato, server, zona, ns, ip):
    """Delega di una zona sul server root: record NS e glue A in db.root."""
    from .generators import _righe_delega, _soa_root
    master = dict(opzioni_delega_dns(stato)).get(server)
    if master is None:
        raise ErroreOperazione('Selezione non valida.')
    if not master:
        raise ErroreOperazione(
            f"⚠️ {server} non è il root (in named.conf la zona '.' non è 'type master'): "
            f"le deleghe dei domini di primo livello vanno sul root.")
    zona = zona.strip().strip('.')
    ns = (ns or '').strip().rstrip('.') or f"dns.{zona}"
    fpath = os.path.join(stato['percorso'], server, 'etc', 'bind', 'db.root')
    note, gia_msg = [], f"⚠️ La zona {zona} è già delegata in {server}/etc/bind/db.root."
    with _in_memoria(stato) as (fs, out):
        righe = _leggi_righe(fpath)
        if not any('SOA' in l for l in righe):
            import datetime
            serial = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d') + '01'
            righe = _soa_root(serial) + righe
            note.append("db.root non aveva il SOA (necessario per un master): aggiunto.")
        gia = any(l.split()[:1] == [f"{zona}."] and 'NS' in l.split() for l in righe if l.strip())
        if gia:
            _scrivi_righe(fpath, righe)
            print(gia_msg)
        else:
            _scrivi_righe(fpath, list(righe) + _righe_delega(zona, ns, ip))
            print(f"✅ {server}: delegata la zona {zona} a {ns} ({ip}).")
    return _piano(f"Delega della zona {zona} su {server}", fs, out, note,
                  vuoto=gia_msg if gia else None)


# ----------------------------------------------------------------------------- 2. policy BGP

def opzioni_policy(stato, router):
    """Neighbor BGP di un router: {ip: {'remote_as', 'descrizione', 'dispositivo', 'policy'}}."""
    d = stato['dispositivi'].get(router)
    if not d or not (d['frr'] and d['frr']['bgp']):
        raise ErroreOperazione(f"⚠️ Il router {router} non ha BGP abilitato.")
    return {ip: {k: nb.get(k) for k in ('remote_as', 'descrizione', 'dispositivo', 'policy')}
            for ip, nb in d['frr']['bgp']['neighbor'].items()}


_RE_RELAZIONE = re.compile(r'^(provider|customer|peer)', re.I)
_INVERSA = {'provider': 'customer', 'customer': 'provider', 'peer': 'peer'}


def _bgp(stato, nome):
    d = stato['dispositivi'].get(nome)
    return d['frr']['bgp'] if d and d['frr'] and d['frr']['bgp'] else None


def _relazione_scritta(bgp, ip):
    """Relazione Customer-Provider-Peer verso il neighbor `ip`, dal nome delle sue prefix-list
    (provider_X_in del programma, providerIn delle soluzioni del corso); None se non c'è."""
    for p in (bgp['neighbor'].get(ip) or {}).get('policy', []):
        m = p['tipo'] == 'prefix-list' and _RE_RELAZIONE.match(p['nome'])
        if m:
            return m.group(1).lower()
    return None


def opzioni_policy_bgp(stato, router):
    """Per la GUI (Opzioni 2 del terminale): i neighbor del router con le policy già scritte e la
    relazione Customer-Provider-Peer ('relazione_da': 'qui' se è scritta su questo router, 'vicino'
    se è ricavata, rovesciata, da quella scritta sull'altro), le reti
    annunciate nel lab (da scegliere per prefix-list, access-list e local-preference) e la proposta
    per le prefix-list in uscita verso provider e peer: come nelle soluzioni del corso
    (pear-to-pear) le reti proprie, i link con i clienti e le reti dei clienti; non i link con
    provider e peer."""
    neighbor = opzioni_policy(stato, router)
    bgp = _bgp(stato, router)
    ip_di = {}
    for n, d in stato['dispositivi'].items():
        for it in d['interfacce']:
            if it['ip']:
                ip_di.setdefault(n, []).append(it['ip'])
    for ip, nb in neighbor.items():
        rel = _relazione_scritta(bgp, ip)
        nb['relazione_da'] = 'qui' if rel else None
        altro = _bgp(stato, nb['dispositivo']) if nb['dispositivo'] else None
        if rel is None and altro:
            mio = next((i for i, x in altro['neighbor'].items() if x.get('dispositivo') == router
                        or i in [a.split('/')[0] for a in ip_di.get(router, [])]), None)
            r2 = _relazione_scritta(altro, mio) if mio else None
            rel = _INVERSA[r2] if r2 else None
            nb['relazione_da'] = 'vicino' if rel else None
        nb['relazione'] = rel
    clienti = {nb['dispositivo'] for nb in neighbor.values() if nb['relazione'] == 'customer' and nb['dispositivo']}

    def con_chi(rete, di):
        """Router BGP di un altro AS (rispetto a `di`) con un indirizzo nella rete: è un link.
        I router dello stesso AS e quelli senza BGP non contano (l'aggregato dell'AS è una rete propria)."""
        try:
            net = ipaddress.ip_network(rete, strict=False)
        except ValueError:
            return []
        mio = stato['dispositivi'][di]['asn']
        return sorted(n for n, ips in ip_di.items() if n != di and stato['dispositivi'][n]['asn']
                      and stato['dispositivi'][n]['asn'] != mio
                      and any(ipaddress.ip_interface(i).ip in net for i in ips))

    reti = []
    for x in bgp['network']:
        con = con_chi(x['rete'], router)
        tipo = 'link' if con else 'propria'
        reti.append({'rete': x['rete'], 'tipo': tipo, 'con': con,
                     'proposta': tipo == 'propria' or any(n in clienti for n in con)})
    for cl in sorted(clienti):
        for x in (_bgp(stato, cl) or {'network': []})['network']:
            if x['rete'] not in [r['rete'] for r in reti] and not con_chi(x['rete'], cl):
                reti.append({'rete': x['rete'], 'tipo': 'cliente', 'con': [cl], 'proposta': True})
    reti_lab = []
    for n in sorted(stato['dispositivi']):
        b = _bgp(stato, n)
        for x in (b['network'] if b else []):
            reti_lab.append({'rete': x['rete'], 'router': n, 'asn': b['asn']})
    return {'asn': bgp['asn'], 'neighbor': neighbor, 'reti': reti, 'reti_lab': reti_lab}


def calcola_policy(stato, router, neighbor, tipo, direzione=None, reti=(), valore=None, asn_nuovo=None):
    """Policy BGP verso un neighbor. tipo:
    - 'prefix_list': deny delle `reti` in `direzione` (in/out) + permit any;
    - 'local_pref': local-preference `valore` in ingresso (solo sulle `reti`, se date);
    - 'med': metric `valore` in uscita;
    - 'access_list': scarta le `reti` in ingresso (access-list + route-map).
    Se il neighbor non esiste ancora serve asn_nuovo: viene creato."""
    from .net_frr import _collega_al_neighbor, _neighbor_presente, _scrivi_route_map
    from .file_utils import _append_righe
    opzioni_policy(stato, router)
    if tipo not in ('prefix_list', 'local_pref', 'med', 'access_list'):
        raise ErroreOperazione(f"Tipo di policy non previsto: {tipo}")
    fpath = _frr(stato, router)
    reti = list(reti or [])
    tag = neighbor.replace('.', '_')
    with _in_memoria(stato) as (fs, out):
        if not _neighbor_presente(fpath, neighbor):
            if not asn_nuovo:
                raise ErroreOperazione(f"Il neighbor {neighbor} non è configurato su {router}: serve il suo AS.")
            insert_lines_into_protocol_block(fpath, proto='bgp', asn=None,
                                             lines=[f"neighbor {neighbor} remote-as {asn_nuovo}"])
        if tipo == 'prefix_list':
            if direzione not in ('in', 'out'):
                raise ErroreOperazione("Direzione: 'in' oppure 'out'.")
            pl_name = f"PL_{router}_{tag}_{direzione}"
            pat = re.compile(rf"^\s*ip prefix-list {re.escape(pl_name)} deny (\S+)")
            prev = [m.group(1) for m in map(pat.match, _leggi_righe(fpath)) if m]
            tutte = prev + [r for r in reti if r not in prev]
            _rimuovi_righe(fpath, lambda l: l.strip().startswith(f"ip prefix-list {pl_name} "))
            _append_righe(fpath, [f"ip prefix-list {pl_name} deny {r}" for r in tutte]
                          + [f"ip prefix-list {pl_name} permit any"])
            _collega_al_neighbor(fpath, neighbor, 'prefix-list', pl_name, direzione)
            print(f"✅ {router}: prefix-list {pl_name} ({direzione}, neighbor {neighbor}): "
                  f"deny {', '.join(tutte)} + permit any.")
            titolo = f"Prefix-list {pl_name} su {router}"
        elif tipo == 'local_pref':
            rm_name, pl_name = f"PREF_IN_{tag}", f"PREF_IN_{tag}_NETS"
            if reti:
                stanza = [
                    f"route-map {rm_name} permit 10",
                    f"    match ip address prefix-list {pl_name}",
                    f"    set local-preference {valore}",
                    f"route-map {rm_name} permit 20",
                    ""
                ] + [f"ip prefix-list {pl_name} permit {r}" for r in reti]
            else:
                stanza = [f"route-map {rm_name} permit 10", f"    set local-preference {valore}"]
            _scrivi_route_map(fpath, rm_name, stanza, pl_name)
            _collega_al_neighbor(fpath, neighbor, 'route-map', rm_name, 'in')
            print(f"✅ {router}: route-map {rm_name} (neighbor {neighbor}, in): local-preference {valore} "
                  f"{'per ' + ', '.join(reti) if reti else 'su tutte le rotte'}.")
            titolo = f"Local preference {valore} da {neighbor} su {router}"
        elif tipo == 'med':
            rm_name = f"LOCALMED_OUT_{tag}"
            _scrivi_route_map(fpath, rm_name, [f"route-map {rm_name} permit 10", f"    set metric {valore}"])
            _collega_al_neighbor(fpath, neighbor, 'route-map', rm_name, 'out')
            print(f"✅ {router}: route-map {rm_name} (neighbor {neighbor}, out): metric {valore}.")
            titolo = f"MED {valore} verso {neighbor} su {router}"
        else:
            contenuto = '\n'.join(_leggi_righe(fpath))
            acl_id = 10
            while re.search(rf"access-list {acl_id}\b", contenuto):
                acl_id += 10
            rm_name = f"FILTER_IN_{tag}"
            stanza = (
                [f"access-list {acl_id} deny {r}" for r in reti]
                + [f"access-list {acl_id} permit any", "", f"route-map {rm_name} permit 10",
                   f"    match ip address {acl_id}"]
            )
            _scrivi_route_map(fpath, rm_name, stanza)
            _collega_al_neighbor(fpath, neighbor, 'route-map', rm_name, 'in')
            print(f"✅ {router}: access-list {acl_id} (deny {', '.join(reti)}) e route-map {rm_name} "
                  f"(neighbor {neighbor}, in).")
            titolo = f"Access-list su {router} da {neighbor}"
    return _piano(titolo, fs, out)


def calcola_cpp(stato, router, vicino, ip, asn, relazione, reti_out=()):
    """Customer-Provider-Peer (regole di Gao-Rexford) verso un vicino:
    - provider / peer: accetta tutto, annuncia solo `reti_out` (le proprie e quelle dei clienti);
    - customer: accetta e annuncia tutto.
    Se il neighbor non esiste ancora viene creato con l'AS `asn`."""
    if relazione not in ('provider', 'customer', 'peer'):
        raise ErroreOperazione('Scelta non valida.')
    fpath = _frr(stato, router)
    if not _esiste_file(fpath):
        raise ErroreOperazione(f"File {fpath} non trovato.")
    reti_out = list(reti_out or [])
    note = []
    pl_in, pl_out = f"{relazione}_{vicino}_in", f"{relazione}_{vicino}_out"
    with _in_memoria(stato) as (fs, out):
        if f"neighbor {ip} remote-as" not in (_leggi_testo(fpath) or ''):
            note.append(f"Neighbor {ip} non presente su {router}: lo aggiungo (AS {asn}).")
            if not insert_lines_into_protocol_block(fpath, proto='bgp', asn=None, lines=[
                    f"neighbor {ip} remote-as {asn}", f"neighbor {ip} description {vicino}"]):
                raise ErroreOperazione("❌ Errore nell'inserimento del neighbor.")
        lines_to_append = [f"ip prefix-list {pl_in} permit any"]
        if relazione == 'customer':
            lines_to_append.append(f"ip prefix-list {pl_out} permit any")
        else:
            lines_to_append += [f"ip prefix-list {pl_out} permit {r}" for r in reti_out]
            if not reti_out:
                note.append(f"Nessuna rete: {router} non annuncerà niente a {vicino}.")
        neigh_lines = ["", f"neighbor {ip} prefix-list {pl_in} in", f"neighbor {ip} prefix-list {pl_out} out"]
        if insert_lines_into_protocol_block(fpath, proto='bgp', asn=None, lines=neigh_lines):
            _scrivi_testo(fpath, (_leggi_testo(fpath) or '') + '\n' + ''.join(l + '\n' for l in lines_to_append) + '\n')
            print(f"✅ Configurazione {relazione.upper()} applicata su {router} verso {vicino}.")
        else:
            print(f"❌ Errore applicando la configurazione neighbor su {router}.")
    return _piano(f"{relazione.capitalize()} {vicino} su {router}", fs, out, note)


# ----------------------------------------------------------------------------- 11. modifica dispositivo
#
# Dopo la scrittura l'XML dei metadati (in .labgenerator/<lab>/) si rigenera dai file (dopo_scrittura).

def _dispositivi(stato):
    from .analyzer import leggi_dispositivi
    return leggi_dispositivi(stato['percorso'], stato)


def _piano_diretto(titolo, modifiche, note=None, vuoto=None, spostati=None):
    piano = nuovo_piano(titolo, modifiche, note, spostati)
    piano.update(messaggi=[], vuoto=vuoto)
    return piano


def dopo_scrittura(lab_path, piano=None, routers=None):
    """Da chiamare dopo la scrittura di un piano (GUI e terminale): rigenera dai file l'XML dei
    metadati, fuori dal lab; dopo una rinomina sposta anche la posizione del dispositivo nel disegno
    salvato dalla GUI (.labgenerator/<lab>/disegno.json), così la Topologia resta com'era; registra
    la modifica nella storia (per annullarla), o la toglie se il piano era un annullamento."""
    from . import storia
    from .persistence import rigenera_xml
    from .supporto import rinomina_nel_disegno
    rigenera_xml(lab_path)
    if piano and piano.get('rinomina'):
        rinomina_nel_disegno(lab_path, *piano['rinomina'])
    if piano and piano.get('modifiche'):
        if piano.get('annulla'):
            storia.togli(lab_path, piano['annulla'])
        else:
            storia.registra(lab_path, piano)


def _calcola_sostituzione(stato, ip_map, iface_map, net_map, titolo, extra=None, note=None):
    """IP, IP/maschera e reti sostituiti in tutti i file di testo del lab."""
    from .device_editor import _piano_sostituzioni, _reti_da_controllare, _sostituzione_ip
    lab = stato['percorso']
    f = _sostituzione_ip(ip_map, iface_map, net_map)
    modifiche = _piano_sostituzioni(lab, f)
    for rel, (v, n) in (extra or {}).items():
        modifiche[rel] = (v, [f(x) for x in n])
    coppie = [(ipaddress.ip_network(a), ipaddress.ip_network(b)) for a, b in net_map.items()]
    note = list(note or []) + (_reti_da_controllare(lab, modifiche, coppie) if coppie else [])
    return _piano_diretto(titolo, modifiche, note)


def _interfaccia(disp, dispositivo, dev):
    d = disp.get(dispositivo)
    if d is None:
        raise ErroreOperazione(f"Dispositivo {dispositivo} non trovato.")
    it = next((x for x in d['interfacce'] if x['dev'] == dev), None)
    if it is None:
        raise ErroreOperazione(f"{dispositivo} non ha l'interfaccia {dev}.")
    return d, it


def _controlla_ip(nuovo, own, propri=(), dentro=None):
    """Stesse regole delle domande del terminale (_chiedi_nuovo_ip)."""
    if nuovo.network.prefixlen < 31 and nuovo.ip in (nuovo.network.network_address, nuovo.network.broadcast_address):
        raise ErroreOperazione(f"{nuovo.ip} è l'indirizzo di rete o di broadcast di {nuovo.network}.")
    if dentro is not None and nuovo.network != dentro:
        raise ErroreOperazione(f"Deve essere nella rete {dentro}.")
    chi = own.get(str(nuovo.ip))
    if chi and str(nuovo.ip) not in propri:
        raise ErroreOperazione(f"{nuovo.ip} è già usato da {chi[0]} ({chi[1]}).")


def opzioni_ip_interfaccia(stato, dispositivo):
    """Interfacce del dispositivo con IP e LAN, e per ognuna gli altri membri della LAN."""
    from .device_editor import _membri_lan
    disp = _dispositivi(stato)
    return {it['dev']: {'ip': it['ip'], 'lan': it['lan'],
                        'altri': [(n, x['ip']) for n, x in _membri_lan(disp, it['lan'])
                                  if not (n == dispositivo and x['dev'] == it['dev']) and x['ip']]}
            for it in disp[dispositivo]['interfacce']}


def calcola_ip_interfaccia(stato, dispositivo, dev, nuovo, solo_questo=False):
    """Nuovo IP di un'interfaccia, sostituito ovunque compare. Se esce dalla rete della LAN e la LAN
    ha altri dispositivi: con solo_questo=False si rinumera tutta la LAN (calcola_rinumera_lan)."""
    from .device_editor import _membri_lan, _proprietari
    disp = _dispositivi(stato)
    d, it = _interfaccia(disp, dispositivo, dev)
    if not it['ip']:
        raise ErroreOperazione(f"{dev} non ha un IP nello startup: aggiungilo con la modifica a righe.")
    vecchio = ipaddress.ip_interface(it['ip'])
    nuovo = str(nuovo)
    try:
        nuovo = ipaddress.ip_interface(nuovo if '/' in nuovo else f"{nuovo}/{vecchio.network.prefixlen}")
    except ValueError:
        raise ErroreOperazione("Formato non valido: x.x.x.x/yy (es. 10.0.0.5/24).")
    if nuovo == vecchio:
        return _piano_diretto(f"IP di {dispositivo} {dev}", {}, vuoto='Nessuna modifica.')
    _controlla_ip(nuovo, _proprietari(disp), propri=(str(vecchio.ip),))
    altri = [(n, x) for n, x in _membri_lan(disp, it['lan']) if not (n == dispositivo and x['dev'] == dev) and x['ip']]
    if nuovo.network != vecchio.network and altri and not solo_questo:
        return calcola_rinumera_lan(stato, it['lan'], nuovo.network, {(dispositivo, dev): nuovo})
    net_map = {str(vecchio.network): str(nuovo.network)} if nuovo.network != vecchio.network and not altri else {}
    return _calcola_sostituzione(
        stato, {str(vecchio.ip): str(nuovo.ip)}, {str(vecchio): str(nuovo)}, net_map,
        f"IP di {dispositivo} {dev}: {vecchio} -> {nuovo}")


def proposta_rinumera_lan(stato, lan, nuova_rete, fissi=None):
    """Nuovi IP proposti per i membri della LAN nella nuova rete (stessa parte host).

    Restituisce (rete vecchia, membri [(nome, interfaccia)], {(nome, dev): ip o None}); None vuol
    dire che l'IP proposto non va bene (occupato o fuori rete) e va scelto."""
    from .device_editor import _membri_lan, _proprietari, _rete_lan
    disp = _dispositivi(stato)
    own = _proprietari(disp)
    membri = [(n, x) for n, x in _membri_lan(disp, lan) if x['ip']]
    vecchia = _rete_lan(disp, lan)
    if not vecchia:
        raise ErroreOperazione(f"La LAN {lan} non ha IP da cambiare.")
    nuova_rete = ipaddress.ip_network(str(nuova_rete), strict=False)
    occupati = {ip for ip, (n, dev, l) in own.items() if l != lan}
    nuovi = {}
    for n, x in membri:
        k, v = (n, x['dev']), ipaddress.ip_interface(x['ip'])
        if fissi and k in fissi:
            nuovi[k] = ipaddress.ip_interface(str(fissi[k]))
            continue
        cand, off = None, int(v.ip) - int(vecchia.network_address)
        if 0 <= off < nuova_rete.num_addresses:
            c = ipaddress.ip_interface(f"{ipaddress.ip_address(int(nuova_rete.network_address) + off)}/{nuova_rete.prefixlen}")
            if not (nuova_rete.prefixlen < 31 and c.ip in (nuova_rete.network_address, nuova_rete.broadcast_address)):
                cand = c
        nuovi[k] = None if cand is None or str(cand.ip) in occupati or cand in nuovi.values() else cand
    return vecchia, membri, nuovi


def calcola_rinumera_lan(stato, lan, nuova_rete, assegnati=None):
    """Cambia la rete di una LAN: ogni dispositivo tiene la stessa parte host quando possibile;
    `assegnati` = {(nome, dev): ip} per gli IP scelti a mano."""
    nuova_rete = ipaddress.ip_network(str(nuova_rete), strict=False)
    vecchia, membri, nuovi = proposta_rinumera_lan(stato, lan, nuova_rete, assegnati)
    if nuova_rete == vecchia:
        raise ErroreOperazione('È la stessa rete: niente da fare.')
    mancano = [f"{n} {dev}" for (n, dev), ip in nuovi.items() if ip is None]
    if mancano:
        raise ErroreOperazione(f"Serve un IP in {nuova_rete} per: {', '.join(mancano)}.")
    vecchi = {(n, x['dev']): ipaddress.ip_interface(x['ip']) for n, x in membri}
    return _calcola_sostituzione(
        stato,
        {str(vecchi[k].ip): str(nuovi[k].ip) for k in vecchi},
        {str(vecchi[k]): str(nuovi[k]) for k in vecchi},
        {str(vecchia): str(nuova_rete)},
        f"Rete della LAN {lan}: {vecchia} -> {nuova_rete}")


def calcola_sposta_interfaccia(stato, dispositivo, dev, nuova_lan, nuovo_ip=None):
    """Sposta un'interfaccia su un'altra LAN (lab.conf); con nuovo_ip cambia anche l'indirizzo."""
    from .device_editor import _membri_lan
    disp = _dispositivi(stato)
    d, it = _interfaccia(disp, dispositivo, dev)
    lans = sorted({x['lan'] for dd in disp.values() for x in dd['interfacce']})
    if not (nuova_lan in lans or nuova_lan.isalnum()):
        raise ErroreOperazione("Nome LAN non valido: solo lettere e numeri (es. A o A1).")
    if nuova_lan == it['lan']:
        return _piano_diretto(f"{dispositivo} {dev}", {}, vuoto='È già su quella LAN.')
    lc = 'lab.conf'
    vecchie = _righe_file(os.path.join(stato['percorso'], lc))
    rx = re.compile(rf'^(\s*{re.escape(dispositivo)}\s*\[\s*{it["idx"]}\s*\]\s*=\s*)(\S+?)(\s*)$')
    nuove, trovata = [], False
    for l in vecchie:
        m = rx.match(l)
        if m and not trovata:
            q = '"' if m.group(2).startswith('"') else ''
            l, trovata = f"{m.group(1)}{q}{nuova_lan}{q}", True
        nuove.append(l)
    if not trovata:
        raise ErroreOperazione(f"Non trovo la riga {dispositivo}[{it['idx']}]=... in lab.conf.")
    ip_map, iface_map = {}, {}
    if nuovo_ip:
        v, n_ip = ipaddress.ip_interface(it['ip']), ipaddress.ip_interface(str(nuovo_ip))
        ip_map, iface_map = {str(v.ip): str(n_ip.ip)}, {str(v): str(n_ip)}
    note = [f"Nota: la LAN {it['lan']} resterà senza dispositivi."] if len(_membri_lan(disp, it['lan'])) == 1 else []

    return _calcola_sostituzione(stato, ip_map, iface_map, {}, f"{dispositivo} {dev}: LAN {it['lan']} -> {nuova_lan}",
                                 extra={lc: (vecchie, nuove)}, note=note)


def opzioni_gateway(stato, dispositivo):
    """Router (o dispositivi con più interfacce) sulle LAN del dispositivo: [(ip, nome, dev)]."""
    from .device_editor import _membri_lan
    disp = _dispositivi(stato)
    d = disp[dispositivo]
    cand = []
    for it in d['interfacce']:
        for n, x in _membri_lan(disp, it['lan']):
            if n != dispositivo and x['ip'] and (disp[n]['tipo'] == 'router' or len(disp[n]['interfacce']) > 1):
                cand.append((x['ip'].split('/')[0], n, it['dev']))
    return {'attuale': d['gateway'], 'tipo': d['tipo'], 'candidati': cand}


def calcola_gateway(stato, dispositivo, gw, forza=False):
    """Default gateway di un host, www o dns. forza=True: anche fuori dalla rete delle interfacce."""
    from .templates import _RE_GW, _RE_IP_ADD
    disp = _dispositivi(stato)
    d = disp[dispositivo]
    if d['tipo'] == 'router':
        raise ErroreOperazione("Il default gateway si cambia su pc, www e dns.")
    try:
        gw = str(ipaddress.ip_address(str(gw).split('/')[0]))
    except ValueError:
        raise ErroreOperazione('❌ IP non valido.')
    dev = next((it['dev'] for it in d['interfacce']
                if it['ip'] and ipaddress.ip_address(gw) in ipaddress.ip_interface(it['ip']).network), None)
    if dev is None:
        if not forza:
            raise ErroreOperazione(f"⚠️ {gw} non è nella rete di nessuna interfaccia di {dispositivo}.")
        dev = d['interfacce'][0]['dev'] if d['interfacce'] else 'eth0'
    rel = f"{dispositivo}.startup"
    vecchie = _righe_file(os.path.join(stato['percorso'], rel))
    nuove, fatto = [], False
    for l in vecchie:
        m = _RE_GW.match(l)
        if m and not fatto:
            l, fatto = re.sub(r'(via|gw)\s+\S+', rf'\g<1> {gw}', l, count=1), True
            l = re.sub(r'\bdev\s+\S+', f"dev {dev}", l) if ' dev ' in l else l
        nuove.append(l)
    if not fatto:
        ultimo = max((k for k, l in enumerate(nuove) if _RE_IP_ADD.match(l)), default=-1)
        nuove.insert(ultimo + 1, f"ip route add default via {gw} dev {dev}")
    return _piano_diretto(f"Gateway di {dispositivo}: {d['gateway'] or '-'} -> {gw}", {rel: (vecchie, nuove)})


def calcola_as(stato, router, nuovo):
    """Nuovo AS di un router: 'router bgp' e i 'remote-as' che puntano a lui sugli altri router."""
    from .device_editor import _ip_del_router
    from .modello import asn_valido
    disp = _dispositivi(stato)
    d = disp[router]
    if not d['asn']:
        raise ErroreOperazione(f"{router} non ha 'router bgp': aggiungi BGP con la voce Protocolli.")
    vecchio, nuovo = d['asn'], str(nuovo).strip()
    if not asn_valido(nuovo) or nuovo == vecchio:
        raise ErroreOperazione('❌ AS non valido o uguale a quello attuale.')
    rel = os.path.join(router, 'etc', 'frr', 'frr.conf')
    righe = _righe_file(os.path.join(stato['percorso'], rel))
    modifiche = {rel: (righe, [re.sub(rf'^(\s*router\s+bgp\s+){vecchio}\b', rf'\g<1>{nuovo}', l) for l in righe])}
    miei = _ip_del_router(d)
    for n, dd in disp.items():
        if n == router or not dd['frr']:
            continue
        r2 = os.path.join(n, 'etc', 'frr', 'frr.conf')
        v = _righe_file(os.path.join(stato['percorso'], r2))
        nu = []
        for l in v:
            m = re.match(rf'^(\s*neighbor\s+(\S+)\s+remote-as\s+){vecchio}(\s*)$', l)
            nu.append(f"{m.group(1)}{nuovo}{m.group(3)}" if m and m.group(2) in miei else l)
        modifiche[r2] = (v, nu)
    note = [
        f"{rel.replace(os.sep, '/')} riga {k}: '{l.strip()}' contiene ancora {vecchio}: controllala."
        for k, l in enumerate(righe, 1) if 'as-path' in l and re.search(rf'\b{vecchio}\b', l)
    ]
    if re.match(rf'as{vecchio}r', router):
        note.append(f"Il nome {router} contiene ancora AS{vecchio}: il dispositivo non viene rinominato.")
    return _piano_diretto(f"AS di {router}: {vecchio} -> {nuovo}", modifiche, note)


def opzioni_protocolli(stato, router):
    """Protocolli attivi, e per aggiungere: network proposte, vicini BGP sulle stesse LAN, AS proposto."""
    from .device_editor import _membri_lan
    from .net_frr import default_igp_networks
    disp = _dispositivi(stato)
    d = disp[router]
    if not d['frr']:
        raise ErroreOperazione(f"{router} non ha frr.conf (router solo con rotte statiche): usa la modifica a righe dello startup.")
    attivi = [p for p in ('bgp', 'ospf', 'rip') if f"{p}d" in d['demoni']]
    dati = {'asn': d['asn'] or '', 'interfaces': [{'ip': it['ip']} for it in d['interfacce'] if it['ip']]}
    vicini = []
    for it in d['interfacce']:
        for n2, x in _membri_lan(disp, it['lan']):
            d2 = disp[n2]
            if n2 == router or not x['ip'] or 'bgpd' not in d2['demoni']:
                continue
            vicini.append({'nome': n2, 'ip': x['ip'].split('/')[0], 'asn': d2['asn'], 'mio_ip': it['ip'].split('/')[0]})
    m = re.match(r'as(\d+)r', router)
    return {
        'attivi': attivi,
        'proposta_igp': default_igp_networks(router, dati),
        'proposta_bgp': [_norm_net(it['ip']) for it in d['interfacce'] if it['ip']],
        'vicini_bgp': vicini,
        'asn_proposto': m.group(1) if m else None,
    }


def calcola_aggiungi_protocollo(stato, router, proto, reti=None, redistribute_bgp=True, area='0.0.0.0',
                                stub=False, asn=None, sessioni=None, inietta=None, anche_sui_vicini=None,
                                aree=None, aree_stub=None):
    """Aggiunge OSPF, RIP o BGP a un router (daemons, blocco in frr.conf).

    OSPF/RIP: `reti` (default: proposta), `redistribute_bgp` se c'è BGP, `area`/`stub` per OSPF;
    router di confine OSPF: `aree` = {rete: area} e `aree_stub` = aree stub.
    BGP: `asn`, `reti` (default: le reti delle interfacce), `sessioni` = nomi dei vicini BGP con cui
    aprire la sessione (default: tutti), `inietta` = IGP attivi in cui mettere 'redistribute bgp'
    (default: tutti), `anche_sui_vicini` = vicini su cui aggiungere il neighbor verso questo router
    (default: tutte le sessioni)."""
    from .file_utils import _set_demone
    from .modello import asn_valido
    from .net_frr import mk_bgp_stanza, mk_ospf_stanza, mk_rip_stanza
    info = opzioni_protocolli(stato, router)
    attivi = info['attivi']
    if proto not in ('bgp', 'ospf', 'rip') or proto in attivi:
        raise ErroreOperazione(f"{proto.upper()} non si può aggiungere a {router}.")
    lab = stato['percorso']
    rel = os.path.join(router, 'etc', 'frr', 'frr.conf')
    reld = os.path.join(router, 'etc', 'frr', 'daemons')
    originali = _righe_file(os.path.join(lab, rel))
    righe = list(originali)
    while righe and not righe[-1].strip():
        righe.pop()
    dm = _righe_file(os.path.join(lab, reld))
    modifiche = {reld: (dm, _set_demone(dm, f"{proto}d", 'yes'))}
    if proto in ('ospf', 'rip'):
        reti = list(reti) if reti else info['proposta_igp']
        redis = ['redistribute connected']
        if 'bgp' in attivi and redistribute_bgp:
            redis.append('redistribute bgp')
        if proto == 'ospf':
            from .modello import errore_area
            for a in [area] + list((aree or {}).values()):
                if errore_area(str(a)):
                    raise ErroreOperazione(f"❌ {errore_area(str(a))}")
            stub = bool(stub) and area not in ('0', '0.0.0.0')
            blocco = mk_ospf_stanza(reti, area, stub, redis, aree, aree_stub).rstrip('\n').split('\n')
        else:
            blocco = mk_rip_stanza(reti, redis).rstrip('\n').split('\n')
        i = _inizio_blocco(righe, r'router bgp\b')
        nuove = righe + [''] + blocco if i is None else righe[:i] + blocco + [''] + righe[i:]
        modifiche[rel] = (originali, nuove)
    else:
        asn = str(asn or info['asn_proposto'] or '')
        if not asn_valido(asn):
            raise ErroreOperazione("❌ Numero AS non valido: solo cifre (es. 20).")
        reti = list(reti) if reti is not None else info['proposta_bgp']
        blocco = mk_bgp_stanza(asn, networks=reti).rstrip('\n').split('\n')
        scelti = []
        for v in info['vicini_bgp']:
            if sessioni is None or v['nome'] in sessioni:
                blocco += [f"    neighbor {v['ip']} remote-as {v['asn']}", f"    neighbor {v['ip']} description Router {v['nome']}"]
                scelti.append(v)
        if not any(l.strip().startswith('debug bgp') for l in righe):
            i = next((k for k, l in enumerate(righe) if l.strip().startswith('log file')), len(righe) - 1)
            righe = righe[:i + 1] + ['', 'debug bgp keepalives', 'debug bgp updates in', 'debug bgp updates out'] + righe[i + 1:]
        for igp in ('ospf', 'rip'):
            if igp in attivi and (inietta is None or igp in inietta):
                con = _inserisci_nel_blocco(righe, rf'router {igp}\b', ['redistribute bgp'])
                righe = con if con is not None else righe
        modifiche[rel] = (originali, righe + [''] + blocco)
        for v in scelti:
            if anche_sui_vicini is None or v['nome'] in anche_sui_vicini:
                r2 = os.path.join(v['nome'], 'etc', 'frr', 'frr.conf')
                vv = _righe_file(os.path.join(lab, r2))
                con = _inserisci_nel_blocco(vv, r'router bgp\b', [f"neighbor {v['mio_ip']} remote-as {asn}",
                                                                   f"neighbor {v['mio_ip']} description Router {router}"])
                if con is not None:
                    modifiche[r2] = (vv, con)
    return _piano_diretto(f"Aggiungi {proto.upper()} a {router}", modifiche)


def calcola_togli_protocollo(stato, router, proto, anche_sui_vicini=True):
    """Toglie OSPF, RIP o BGP da un router; per BGP anche i neighbor che puntano a lui (se richiesto)."""
    from .device_editor import _ip_del_router
    from .file_utils import _fine_blocco, _set_demone
    disp = _dispositivi(stato)
    d = disp[router]
    attivi = opzioni_protocolli(stato, router)['attivi']
    if proto not in attivi:
        raise ErroreOperazione(f"{proto.upper()} non è attivo su {router}.")
    lab = stato['percorso']
    rel = os.path.join(router, 'etc', 'frr', 'frr.conf')
    reld = os.path.join(router, 'etc', 'frr', 'daemons')
    righe = _righe_file(os.path.join(lab, rel))
    dm = _righe_file(os.path.join(lab, reld))
    nuove = list(righe)
    i = _inizio_blocco(nuove, rf'router {proto}\b')
    if i is not None:
        f = _fine_blocco(nuove, i)
        while f < len(nuove) and not nuove[f].strip():
            f += 1
        del nuove[i:f]
    nuove = [l for l in nuove
             if not re.match(rf'\s*redistribute\s+{proto}\b', l)
             and not (proto == 'bgp' and re.match(r'\s*debug\s+bgp\b', l))]
    modifiche = {rel: (righe, nuove), reld: (dm, _set_demone(dm, f"{proto}d", 'no'))}
    note = []
    if proto == 'bgp':
        if anche_sui_vicini:
            modifiche.update(neighbor_verso(stato, router))
        note.append("Route-map e prefix-list del router restano: i controlli le segnaleranno se non sono più usate.")
    return _piano_diretto(f"Togli {proto.upper()} da {router}", modifiche, note)


def neighbor_verso(stato, router):
    """{file: (righe, righe senza i neighbor che puntano agli IP del router)} sugli altri router."""
    from .device_editor import _ip_del_router
    disp = _dispositivi(stato)
    miei = _ip_del_router(disp[router])
    altri = {}
    for n2, d2 in disp.items():
        if n2 == router or not d2['frr']:
            continue
        r2 = os.path.join(n2, 'etc', 'frr', 'frr.conf')
        v = _righe_file(os.path.join(stato['percorso'], r2))
        nu = [l for l in v if not (re.match(r'\s*neighbor\s+(\S+)\s', l) and l.split()[1] in miei)]
        if nu != v:
            altri[r2] = (v, nu)
    return altri


def opzioni_righe(stato, dispositivo):
    """File del dispositivo modificabili a righe (startup, frr.conf, resolv.conf, file di bind)."""
    from .device_editor import _file_modificabili
    return _file_modificabili(stato['percorso'], dispositivo)


def calcola_righe(stato, rel, nuove, vecchie=None):
    """Modifica a righe di un file del dispositivo. vecchie = le righe mostrate quando si è iniziato a
    modificare (se nel frattempo il file è cambiato, la scrittura si ferma per conflitto)."""
    from .device_editor import _file_modificabili
    nome = rel.replace(os.sep, '/').split('/')[0]
    nome = nome[:-len('.startup')] if nome.endswith('.startup') else nome
    if rel not in _file_modificabili(stato['percorso'], nome):
        raise ErroreOperazione(f"{rel.replace(os.sep, '/')} non è un file modificabile di {nome}.")
    if vecchie is None:
        vecchie = _righe_file(os.path.join(stato['percorso'], rel))
    return _piano_diretto(f"Modifica di {rel.replace(os.sep, '/')}", {rel: (list(vecchie), list(nuove))},
                          vuoto='Nessuna modifica da salvare.')


# ----------------------------------------------------------------------------- rinomina dispositivo

def _file_del_dispositivo(lab, nome):
    """Percorsi relativi dei file del dispositivo: la sua cartella e i file '<nome>.*' alla radice."""
    out = []
    cartella = os.path.join(lab, nome)
    for radice, dirs, files in os.walk(cartella):
        dirs.sort()
        out += [os.path.relpath(os.path.join(radice, f), lab) for f in sorted(files)]
    out += sorted(f for f in os.listdir(lab) if f.startswith(nome + '.') and os.path.isfile(os.path.join(lab, f))
                  and not f.endswith('.xml'))
    return out


def _nuovo_percorso(rel, vecchio, nuovo):
    parti = rel.split(os.sep)
    parti[0] = nuovo + parti[0][len(vecchio):]        # 'r1' -> 'core1', 'r1.startup' -> 'core1.startup'
    return os.path.join(*parti)


def calcola_rinomina(stato, vecchio, nuovo):
    """Rinomina un dispositivo: lab.conf, cartella e file del dispositivo, hostname in vtysh.conf, la
    pagina index.html del server web se è ancora quella del generatore, le 'neighbor ... description'
    degli altri router che lo citano e, dopo la scrittura, l'XML."""
    from .generators import pagina_www
    from .modello import correggi_nome_kathara, errore_nome_dispositivo
    lab = stato['percorso']
    nuovo = (nuovo or '').strip()
    if vecchio not in stato['dispositivi']:
        raise ErroreOperazione(f"Dispositivo {vecchio} non trovato.")
    e = errore_nome_dispositivo(nuovo)
    if e:
        raise ErroreOperazione(f"❌ {e} Proposta: {correggi_nome_kathara(nuovo)}")
    if nuovo == vecchio:
        return _piano_diretto(f"Rinomina {vecchio}", {}, vuoto='È già il suo nome.')
    if nuovo in stato['dispositivi'] or os.path.exists(os.path.join(lab, nuovo)) \
            or os.path.exists(os.path.join(lab, f"{nuovo}.startup")):
        raise ErroreOperazione(f"Nome '{nuovo}' già usato. Scegli un altro.")

    parola = re.compile(rf'(?<![\w.-]){re.escape(vecchio)}(?![\w-])')
    modifiche, spostati, note = {}, {}, []
    pagina = f"{vecchio}/var/www/html/index.html"
    lc = 'lab.conf'
    v = _righe_file(os.path.join(lab, lc))
    modifiche[lc] = (v, [re.sub(rf"^(\s*){re.escape(vecchio)}(\s*\[)", rf"\g<1>{nuovo}\g<2>", l) for l in v])

    for rel in _file_del_dispositivo(lab, vecchio):
        try:
            righe = _righe_file(os.path.join(lab, rel))
        except UnicodeDecodeError:
            raise ErroreOperazione(f"{rel.replace(os.sep, '/')} non è un file di testo: rinomina {vecchio} a mano.")
        nuove = list(righe)
        if rel.endswith(os.path.join('etc', 'frr', 'vtysh.conf')):
            nuove = [re.sub(rf'^(\s*hostname\s+){re.escape(vecchio)}(-frr)?\s*$',
                            lambda m: f"{m.group(1)}{nuovo}{m.group(2) or ''}", l) for l in nuove]
        if rel.replace(os.sep, '/') == pagina:
            if '\n'.join(righe).strip() == pagina_www(vecchio):
                nuove = [pagina_www(nuovo)]
            elif parola.search('\n'.join(righe)):
                note.append(f"{pagina} non aggiornato: l'hai modificato tu, il nome {vecchio} scritto dentro resta com'è.")
        modifiche[rel] = (righe, None)
        modifiche[_nuovo_percorso(rel, vecchio, nuovo)] = (None, nuove)
        spostati[rel] = _nuovo_percorso(rel, vecchio, nuovo)

    liste_col_nome = False
    for n, d in stato['dispositivi'].items():
        if not d['frr']:
            continue
        rel = os.path.join(n, 'etc', 'frr', 'frr.conf')
        v = _righe_file(os.path.join(lab, rel))
        liste_col_nome |= bool(re.search(r'(?:prefix-list|route-map)\s+\S*' + re.escape(vecchio), '\n'.join(v)))
        if n == vecchio:
            continue
        nu = [parola.sub(nuovo, l) if re.match(r'\s*neighbor\s+\S+\s+description\s', l) else l for l in v]
        if nu != v:
            modifiche[rel] = (v, nu)
    if liste_col_nome:
        note.append(f"I nomi di prefix-list e route-map che contengono {vecchio} restano uguali: funzionano lo stesso.")
    piano = _piano_diretto(f"Rinomina {vecchio} -> {nuovo}", modifiche, note, spostati=spostati)
    piano['rinomina'] = [vecchio, nuovo]     # dopo la scrittura: anche le posizioni del disegno della GUI
    return piano


# ----------------------------------------------------------------------------- 15. diagnostica e correzione di frr.conf
#
# La diagnostica è in core/frr_autofix.py; le correzioni
# passano da qui, quindi hanno anteprima, impronte, storia (annulla) e sono le stesse da GUI e
# terminale. Le correzioni che erano operazioni del suo ops_api rimandano alle nostre operazioni.

_RIMANDI = {'change_gateway': 'gateway', 'ibgp_full_mesh': 'ibgp', 'fix_names': 'rinomina'}


def _rimando(stato, dispositivo, fx):
    """Correzione che è una nostra operazione: {'operazione', 'parametri'} (None se non c'è)."""
    op, p = fx.get('op'), fx.get('params') or {}
    if op == 'change_gateway':
        return {'operazione': 'gateway', 'parametri': {'dispositivo': p.get('nome') or dispositivo, 'gw': p.get('gateway')}}
    if op == 'ibgp_full_mesh':
        return {'operazione': 'ibgp', 'parametri': {'asn': str(p.get('asn') or '')}}
    if op == 'fix_names':
        from .modello import correggi_nome_kathara
        return {'operazione': 'rinomina', 'parametri': {'vecchio': dispositivo, 'nuovo': correggi_nome_kathara(dispositivo)}}
    return None


def opzioni_correggi_frr(stato, dispositivo):
    """Problemi del dispositivo (frr.conf, daemons, startup, gateway, nomi) con le correzioni:
    [{'regola', 'gravita', 'file', 'riga', 'testo', 'messaggio',
      'correzioni': [{'etichetta', 'confidenza', 'rimando': {operazione, parametri} | None}]}].
    Le 'info' (bgp.missing_import_check) non ci sono."""
    from .frr_autofix import diagnosi_dispositivo
    if dispositivo not in stato['dispositivi']:
        raise ErroreOperazione(f"{dispositivo} non è un dispositivo del lab.")
    out = []
    for i in diagnosi_dispositivo(stato['percorso'], dispositivo):
        if i['gravita'] == 'info':
            continue
        corr = []
        for fx in i.get('fixes') or []:
            interna = fx.get('op') == 'apply_diag_fix'
            corr.append({'etichetta': fx.get('etichetta') or (fx.get('params') or {}).get('fix', {}).get('etichetta') or 'Correggi',
                         'confidenza': fx.get('confidenza', 'proposta'),
                         'rimando': None if interna else _rimando(stato, dispositivo, fx)})
        out.append({'regola': i['id_regola'], 'gravita': i['gravita'], 'file': i['file'], 'riga': i['riga'],
                    'testo': i.get('testo'), 'messaggio': i['messaggio'], 'correzioni': corr})
    return out


def calcola_correggi_frr(stato, dispositivo, regola, riga, messaggio, correzione=0):
    """Applica la correzione numero `correzione` del problema (regola, riga, messaggio) del
    dispositivo: un piano come "File a righe". Se il problema non c'è più (file cambiato, altra
    correzione già applicata) si ferma: rifare la diagnostica."""
    from .frr_autofix import applica_fix_testo, diagnosi_dispositivo
    from .file_utils import _leggi_testo, _scrivi_testo, _set_demone, insert_lines_into_protocol_block
    from .templates import DAEMONS_TMPL
    problema = next((i for i in diagnosi_dispositivo(stato['percorso'], dispositivo)
                     if i['id_regola'] == regola and i['riga'] == riga and i['messaggio'] == messaggio), None)
    if problema is None:
        raise ErroreOperazione("Il problema non c'è più (il file è cambiato o è già stato corretto): rifai la diagnostica.")
    fixes = problema.get('fixes') or []
    if not 0 <= int(correzione) < len(fixes):
        raise ErroreOperazione("Correzione non prevista per questo problema.")
    fx = fixes[int(correzione)]
    if fx.get('op') != 'apply_diag_fix':
        r = _rimando(stato, dispositivo, fx)
        raise ErroreOperazione(f"Questa correzione è l'operazione '{r['operazione']}': usala da lì." if r
                               else "Questa correzione non si applica da qui: segui il messaggio.")
    p = fx['params']
    kind, nome = p.get('kind'), p.get('nome') or dispositivo
    base = stato['percorso']
    with _in_memoria(stato) as (fs, out):
        if kind == 'frr_text_fix':
            f = os.path.join(base, nome, 'etc', 'frr', 'frr.conf')
            prima = _leggi_testo(f) or ''
            dopo = applica_fix_testo(prima, p.get('fix') or {})
            if dopo == prima:
                raise ErroreOperazione("La correzione non cambia frr.conf.")
            _scrivi_testo(f, dopo)
        elif kind == 'enable_daemon':
            if p.get('daemon') not in ('zebra', 'bgpd', 'ospfd', 'ripd'):
                raise ErroreOperazione(f"Demone non previsto: {p.get('daemon')}")
            f = os.path.join(base, nome, 'etc', 'frr', 'daemons')
            righe = (_leggi_testo(f) or DAEMONS_TMPL.format(zebra='yes', ripd='no', ospfd='no', bgpd='no')).rstrip('\n').split('\n')
            righe = _set_demone(_set_demone(righe, 'zebra', 'yes'), p['daemon'], 'yes')
            _scrivi_testo(f, '\n'.join(righe) + '\n')
        elif kind in ('add_startup_frr', 'add_startup_apache'):
            servizio = 'frr' if kind == 'add_startup_frr' else 'apache2'
            f = os.path.join(base, f"{nome}.startup")
            righe = [l for l in (_leggi_testo(f) or '').split('\n')]
            while righe and not righe[-1].strip():
                righe.pop()
            righe.append(f"systemctl start {servizio}")
            _scrivi_testo(f, '\n'.join(righe) + '\n')
        elif kind == 'add_peer_neighbor':
            peer, ip = p.get('peer'), p.get('neighbor_ip')
            nuove = [f"neighbor {ip} remote-as {p.get('remote_as')}"]
            if p.get('description'):
                nuove.append(f"neighbor {ip} description {p['description']}")
            if p.get('update_source'):
                nuove.append(f"neighbor {ip} update-source {p['update_source']}")
            if not insert_lines_into_protocol_block(os.path.join(base, peer, 'etc', 'frr', 'frr.conf'), proto='bgp', asn=None, lines=nuove):
                raise ErroreOperazione(f"Non trovo il blocco router bgp di {peer}.")
        else:
            raise ErroreOperazione(f"Correzione non prevista: {kind}")
    return _piano(f"Correggi {dispositivo}: {fx.get('etichetta') or (p.get('fix') or {}).get('etichetta') or problema['messaggio'][:60]}",
                  fs, out, [f"Problema: {problema['messaggio']}"])


# ----------------------------------------------------------------------------- 13. aggiungi / togli un dispositivo

def _modello_dello_stato(stato):
    from .persistence import modello_da_stato
    return modello_da_stato(stato)


def opzioni_aggiungi_dispositivo(stato):
    """Dati per le domande: nomi e IP già usati, area OSPF del primo router OSPF, resolver del lab."""
    m = _modello_dello_stato(stato)
    prima = next((r for r in m['routers'].values() if 'ospf' in r.get('protocols', [])), None)
    usati_ip = {it['ip'].split('/')[0] for d in stato['dispositivi'].values() for it in d['interfacce'] if it['ip']}
    return {
        'modello': m,
        'nomi': set(stato['dispositivi']),
        'ip': usati_ip,
        'prima_area_ospf': (prima.get('ospf_area'), bool(prima.get('ospf_area_stub'))) if prima else (None, False),
        'resolver': m['resolver'],
    }


def _togli_network_interne_di(lab, routers, nome):
    """Come rimuovi_network_bgp_interne, ma solo per il router `nome`."""
    from .net_frr import _as_number
    rdata = routers[nome]
    if 'bgp' not in rdata.get('protocols', []):
        return
    membri = {}
    for rn, rd in routers.items():
        for it in rd.get('interfaces', []):
            if it.get('lan'):
                membri.setdefault(it['lan'], []).append(rn)
    my_as = _as_number(nome, rdata)
    interne = []
    for it in rdata.get('interfaces', []):
        altri = [o for o in membri.get(it.get('lan'), []) if o != nome]
        if altri and not any('bgp' in routers[o].get('protocols', []) and _as_number(o, routers[o]) != my_as for o in altri):
            interne.append(_norm_net(it.get('ip', '')))
    if not interne:
        return
    fpath = os.path.join(lab, nome, 'etc', 'frr', 'frr.conf')
    righe_out, in_bgp = [], False
    for l in _leggi_righe(fpath):
        s = l.strip()
        if s.startswith('router '):
            in_bgp = s.startswith('router bgp')
        elif l and not l[0].isspace():
            in_bgp = False
        elif in_bgp and s.startswith('network ') and len(s.split()) == 2 and _norm_net(s.split()[1]) in interne:
            continue
        righe_out.append(l)
    _scrivi_righe(fpath, righe_out)


def calcola_aggiungi_dispositivo(stato, tipo, dati, sessioni_bgp=True, resolver=True):
    """Aggiunge un dispositivo a un lab esistente.

    tipo: 'router', 'host', 'www' o 'dns'; dati: come nel modello del wizard, con 'name' (per i
    router anche 'protocols', 'asn', 'interfaces', ...). I valori mancanti prendono la proposta di
    completa_lab. Router BGP: con sessioni_bgp, neighbor reciproci con i router BGP sulle sue LAN.
    resolver=True: host, www e dns ricevono il resolver del lab, se il lab ne ha uno."""
    import shutil
    import tempfile
    from .generazione import ip_del_resolver, lab_conf_da_modello
    from .generators import crea_dns_host, crea_host_multi, crea_router_files, crea_www_file
    from .modello import completa_lab, problemi_di, valida_lab
    from .net_frr import add_neighbor_if_missing

    if tipo not in ('router', 'host', 'www', 'dns'):
        raise ErroreOperazione(f"Tipo di dispositivo non previsto: {tipo}")
    lab = stato['percorso']
    dati = dict(dati)
    nome = (dati.get('name') or '').strip()
    attuale = _modello_dello_stato(stato)
    nuovo = {'routers': dict(attuale['routers']), 'hosts': list(attuale['hosts']), 'wwws': list(attuale['wwws'])}
    if tipo == 'router':
        nuovo['routers'][nome] = {k: v for k, v in dati.items() if k != 'name'}
    elif tipo == 'www':
        nuovo['wwws'].append(dati)
    else:
        nuovo['hosts'].append(dict(dati, dns=True) if tipo == 'dns' else dati)
    nuovo = completa_lab(nuovo)
    if not nome or nome in stato['dispositivi'] or os.path.exists(os.path.join(lab, nome)):
        raise ErroreOperazione(f"Nome '{nome}' già usato. Scegli un altro." if nome else 'Manca il nome.')
    errori = [p for p in problemi_di(valida_lab(nuovo), nome) if p['gravita'] == 'errore']
    if errori:
        raise ErroreOperazione('; '.join(f"{p['campo']}: {p['messaggio']}" for p in errori))
    if tipo == 'router':
        dato = nuovo['routers'][nome]
    else:
        dato = next(x for x in (nuovo['wwws'] if tipo == 'www' else nuovo['hosts']) if x.get('name') == nome)

    # i file del dispositivo, generati come nel wizard in una cartella temporanea
    tmp = tempfile.mkdtemp(prefix='.labgen-disp-')
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            if tipo == 'router':
                crea_router_files(tmp, nome, dato, interactive=False)
            elif tipo == 'host':
                crea_host_multi(tmp, nome, dato['interfaces'], dato.get('gateway'), dato.get('gw_dev') or 'eth0')
            elif tipo == 'www':
                crea_www_file(tmp, nome, dato['ip'], dato['gateway'], dato['lan'])
            else:
                root = next((h for h in attuale['hosts'] if h.get('dns') and h.get('root_type') == 'master'), None)
                root_ip = str(root.get('ip') or '').split('/')[0] if root else None
                rt = dato.get('root_type')
                crea_dns_host(tmp, nome, dato['ip'], dato['gateway'], dato['lan'], zones=dato.get('zones'),
                              root_type=rt, root_server_ip=root_ip if rt != 'master' else None,
                              allow_recursion=dato.get('allow_recursion'),
                              dnssec_validation=bool(dato.get('dnssec_validation')),
                              delegations=dato.get('delegations') or [])
        generati = {}
        for radice, _, files in os.walk(tmp):
            for f in files:
                p = os.path.join(radice, f)
                with open(p, 'r', encoding='utf-8') as fh:
                    generati[os.path.relpath(p, tmp)] = fh.read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    blocco = lab_conf_da_modello(
        {'routers': {nome: dato}} if tipo == 'router'
        else {'hosts': [dato]} if tipo in ('host', 'dns') else {'wwws': [dato]})
    note = []
    with _in_memoria(stato) as (fs, out):
        for rel, testo in generati.items():
            _scrivi_testo(os.path.join(lab, rel), testo)
        lc = os.path.join(lab, 'lab.conf')
        prima = (_leggi_testo(lc) or '').rstrip('\n')
        _scrivi_testo(lc, (prima + '\n\n' if prima else '') + blocco)
        ip_res = ip_del_resolver(dict(attuale, hosts=nuovo['hosts']))
        if resolver and tipo != 'router' and ip_res:
            _scrivi_testo(os.path.join(lab, nome, 'etc', 'resolv.conf'), f"nameserver {ip_res}\n")
        if tipo == 'router' and 'bgp' in dato.get('protocols', []):
            routers = dict(nuovo['routers'])
            if sessioni_bgp:
                miei = {it['lan']: it['ip'].split('/')[0] for it in dato['interfaces']}
                for altro, rd in routers.items():
                    if altro == nome or 'bgp' not in rd.get('protocols', []):
                        continue
                    for it in rd.get('interfaces', []):
                        if it.get('lan') in miei and it.get('ip'):
                            add_neighbor_if_missing(lab, nome, it['ip'], rd['asn'], desc=f"Router {altro}")
                            add_neighbor_if_missing(lab, altro, miei[it['lan']], dato['asn'], desc=f"Router {nome}")
                            print(f"✅ Sessione BGP {nome} <-> {altro} (LAN {it['lan']}).")
            _togli_network_interne_di(lab, routers, nome)
        if tipo == 'router' and not any(p in dato.get('protocols', []) for p in ('bgp', 'ospf', 'rip')):
            note.append(f"{nome} ha solo rotte statiche: nessun frr.conf, l'immagine resta kathara/base.")
    piano = _piano(f"Aggiungi {tipo} {nome}", fs, out, note)
    return piano


def opzioni_togli_dispositivo(stato, nome):
    """Cosa succede togliendo il dispositivo: chi lo usa come gateway o resolver, neighbor da togliere."""
    from .device_editor import _ip_del_router
    disp = _dispositivi(stato)
    if nome not in disp:
        raise ErroreOperazione(f"Dispositivo {nome} non trovato.")
    miei = _ip_del_router(disp[nome])
    return {
        'neighbor': sorted(r.split(os.sep)[0] for r in neighbor_verso(stato, nome)),
        'gateway_di': sorted(n for n, d in disp.items() if d['gateway'] in miei),
        'resolver_di': sorted(n for n, d in disp.items() if set(d['nameserver']) & miei),
    }


def _togli_righe_lab_conf(righe, nome):
    """lab.conf senza le righe del dispositivo e senza righe vuote doppie dove erano."""
    out = []
    for l in righe:
        if re.match(rf"^\s*{re.escape(nome)}\s*\[", l):
            continue
        if not l.strip() and out and not out[-1].strip():
            continue
        out.append(l)
    while out and not out[-1].strip():
        out.pop()
    return out


def calcola_togli_dispositivo(stato, nome, togli_neighbor=True):
    """Toglie un dispositivo: righe di lab.conf, cartella e file '<nome>.*' e, se richiesto, i
    neighbor degli altri router che puntano ai suoi IP. Gateway e resolver che lo usavano restano:
    vengono segnalati."""
    info = opzioni_togli_dispositivo(stato, nome)
    lab = stato['percorso']
    modifiche = {}
    lc = 'lab.conf'
    v = _righe_file(os.path.join(lab, lc))
    modifiche[lc] = (v, _togli_righe_lab_conf(v, nome))
    for rel in _file_del_dispositivo(lab, nome):
        try:
            modifiche[rel] = (_righe_file(os.path.join(lab, rel)), None)
        except UnicodeDecodeError:
            raise ErroreOperazione(f"{rel.replace(os.sep, '/')} non è un file di testo: togli {nome} a mano.")
    if togli_neighbor:
        modifiche.update(neighbor_verso(stato, nome))
    note = []
    if info['gateway_di']:
        note.append(f"{', '.join(info['gateway_di'])} usava {nome} come gateway: cambialo (Modifica dispositivo).")
    if info['resolver_di']:
        note.append(f"{', '.join(info['resolver_di'])} usava {nome} come resolver: cambialo (Opzioni 5).")
    return _piano_diretto(f"Togli {nome}", modifiche, note)


# ----------------------------------------------------------------------------- aggiungi / togli un'interfaccia

def _file_propri(stato, nome):
    """File di testo del dispositivo in cui compaiono i nomi delle sue interfacce."""
    out = [f"{nome}.startup"]
    for rel in (os.path.join(nome, 'etc', 'frr', 'frr.conf'),):
        if os.path.isfile(os.path.join(stato['percorso'], rel)):
            out.append(rel)
    return out


def calcola_aggiungi_interfaccia(stato, nome, lan, ip):
    """Nuova interfaccia ethN (N = la prima libera) del dispositivo sulla LAN `lan` con IP `ip`."""
    from .device_editor import _proprietari, _rete_lan
    from .modello import errore_ip_cidr, errore_lan
    disp = _dispositivi(stato)
    if nome not in disp:
        raise ErroreOperazione(f"Dispositivo {nome} non trovato.")
    lan = (lan or '').strip().upper()
    e = errore_lan(lan) or errore_ip_cidr(ip)
    if e:
        raise ErroreOperazione(f"❌ {e}")
    nuovo = ipaddress.ip_interface(ip)
    rete = _rete_lan(disp, lan)
    _controlla_ip(nuovo, _proprietari(disp), dentro=rete)
    d = disp[nome]
    idx = max([it['idx'] for it in d['interfacce']], default=-1) + 1
    dev = f"eth{idx}"
    lab = stato['percorso']
    lc = 'lab.conf'
    v = _righe_file(os.path.join(lab, lc))
    ultima = max((k for k, l in enumerate(v) if re.match(rf"^\s*{re.escape(nome)}\s*\[\s*\d+\s*\]", l)), default=None)
    if ultima is None:
        raise ErroreOperazione(f"Non trovo le righe di {nome} in lab.conf.")
    modifiche = {lc: (v, v[:ultima + 1] + [f"{nome}[{idx}]={lan}"] + v[ultima + 1:])}
    rel = f"{nome}.startup"
    st = _righe_file(os.path.join(lab, rel))
    dopo = max((k for k, l in enumerate(st) if re.match(r'\s*ip\s+a(?:ddr(?:ess)?)?\s+add\s', l)), default=-1)
    modifiche[rel] = (st, st[:dopo + 1] + [f"ip address add {nuovo} dev {dev}"] + st[dopo + 1:])
    note = []
    if d['tipo'] == 'router':
        note.append(f"La rete {nuovo.network} non è annunciata da nessun protocollo: se serve, aggiungila in BGP "
                    f"(Opzioni 6) o nelle network dell'IGP (modifica a righe di frr.conf).")
    if rete is None:
        note.append(f"La LAN {lan} è nuova: per ora c'è solo {nome}.")
    return _piano_diretto(f"Aggiungi {dev} a {nome} (LAN {lan}, {nuovo})", modifiche, note)


def calcola_togli_interfaccia(stato, nome, dev, togli_neighbor=True):
    """Toglie un'interfaccia: riga di lab.conf, IP nello startup, rotte e blocco 'interface' che la
    usano. Le interfacce dopo scalano di uno (eth2 -> eth1) in lab.conf, startup e frr.conf. Con
    togli_neighbor tolge anche i neighbor degli altri router che puntavano al suo IP."""
    disp = _dispositivi(stato)
    d, it = _interfaccia(disp, nome, dev)
    if len(d['interfacce']) <= 1:
        raise ErroreOperazione(f"{nome} ha una sola interfaccia: per toglierla togli il dispositivo.")
    idx = it['idx']
    dopo = sorted(x['idx'] for x in d['interfacce'] if x['idx'] > idx)
    lab = stato['percorso']

    def rinumera(l):
        return re.sub(r'\beth(\d+)\b', lambda m: f"eth{int(m.group(1)) - 1}" if int(m.group(1)) in dopo else m.group(0), l)

    modifiche = {}
    lc = 'lab.conf'
    v = _righe_file(os.path.join(lab, lc))
    rx = re.compile(rf"^(\s*{re.escape(nome)}\s*\[\s*)(\d+)(\s*\].*)$")
    nu = []
    for l in v:
        m = rx.match(l)
        if m and int(m.group(2)) == idx:
            continue
        if m and int(m.group(2)) in dopo:
            l = f"{m.group(1)}{int(m.group(2)) - 1}{m.group(3)}"
        nu.append(l)
    modifiche[lc] = (v, nu)
    tolte = []
    rete = ipaddress.ip_interface(it['ip']).network if it['ip'] else None

    def nella_rete(ip):
        try:
            return rete is not None and ipaddress.ip_address(ip) in rete
        except ValueError:
            return False

    coperta = []
    for rel in _file_propri(stato, nome):
        righe = _righe_file(os.path.join(lab, rel))
        out, salta = [], False
        for l in righe:
            s = l.strip()
            if rel.endswith('frr.conf'):
                if re.match(rf'interface {dev}$', s):
                    salta = True
                    continue
                if salta and (l[:1].isspace() and s):
                    continue
                salta = False
                m = re.match(r'neighbor\s+(\S+)\s', s)
                if togli_neighbor and m and nella_rete(m.group(1)):
                    continue
                m = re.match(r'network\s+(\S+)', s)
                if m and rete is not None:
                    try:
                        if rete.subnet_of(ipaddress.ip_network(m.group(1), strict=False)):
                            coperta.append(s)
                    except (ValueError, TypeError):
                        pass
            if re.search(rf'\bdev\s+{dev}\b', l):
                tolte.append(s)
                continue
            out.append(rinumera(l))
        modifiche[rel] = (righe, out)
    if togli_neighbor and it['ip']:
        ip = it['ip'].split('/')[0]
        for n2, d2 in disp.items():
            if n2 == nome or not d2['frr']:
                continue
            r2 = os.path.join(n2, 'etc', 'frr', 'frr.conf')
            vv = _righe_file(os.path.join(lab, r2))
            nn = [l for l in vv if not (re.match(r'\s*neighbor\s+(\S+)\s', l) and l.split()[1] == ip)]
            if nn != vv:
                modifiche[r2] = (vv, nn)
    note = [f"Righe tolte perché usano {dev}: " + '; '.join(tolte)] if len(tolte) > 1 else []
    if coperta:
        note.append(f"In frr.conf di {nome} restano righe che comprendono {rete}: " + '; '.join(coperta)
                    + " (toglile se non servono più).")
    if dopo:
        note.append(f"Le interfacce dopo {dev} scalano di uno: " + ', '.join(f"eth{k} -> eth{k - 1}" for k in dopo) + '.')
    return _piano_diretto(f"Togli {dev} da {nome}", modifiche, note)


# ----------------------------------------------------------------------------- elenco

# nome -> (opzioni, calcola): le operazioni che terminale e GUI possono eseguire
# ----------------------------------------------------------------------------- annulla

def opzioni_annulla(stato):
    """Modifiche della storia, dalla più recente: [{'id', 'ora', 'titolo', 'file'}]."""
    from .storia import riassunto
    return riassunto(stato['percorso'])


def calcola_annulla(stato):
    """Piano che annulla l'ultima modifica della storia (core/storia.py)."""
    from .storia import ErroreStoria, piano_inverso
    try:
        piano = piano_inverso(stato['percorso'])
    except ErroreStoria as e:
        raise ErroreOperazione(str(e))
    piano.update(messaggi=[f"✅ {piano['titolo']}."], vuoto=None)
    return piano


OPERAZIONI = {
    'costo_ospf': (opzioni_costo_ospf, calcola_costo_ospf),
    'togli_costo_ospf': (opzioni_costo_ospf, calcola_togli_costo_ospf),
    'auto_cost': (opzioni_auto_cost, calcola_auto_cost),
    'loopback': (opzioni_loopback, calcola_loopback),
    'network_bgp': (opzioni_network_bgp, calcola_network_bgp),
    'ibgp': (opzioni_ibgp, calcola_ibgp),
    'default_originate': (opzioni_default_originate, calcola_default_originate),
    'default_igp': (opzioni_default_igp, calcola_default_igp),
    'redistribuzione': (opzioni_redistribuzione, calcola_redistribuzione),
    'redistribuzione_route_map': (opzioni_redistribuzione, calcola_redistribuzione_route_map),
    'resolver': (opzioni_resolver, calcola_resolver),
    'delega_dns': (opzioni_delega_dns, calcola_delega_dns),
    'policy': (opzioni_policy_bgp, calcola_policy),
    'cpp': (opzioni_policy_bgp, calcola_cpp),
    'ip_interfaccia': (opzioni_ip_interfaccia, calcola_ip_interfaccia),
    'rinumera_lan': (proposta_rinumera_lan, calcola_rinumera_lan),
    'sposta_interfaccia': (opzioni_ip_interfaccia, calcola_sposta_interfaccia),
    'gateway': (opzioni_gateway, calcola_gateway),
    'as': (opzioni_protocolli, calcola_as),
    'aggiungi_protocollo': (opzioni_protocolli, calcola_aggiungi_protocollo),
    'togli_protocollo': (opzioni_protocolli, calcola_togli_protocollo),
    'righe': (opzioni_righe, calcola_righe),
    'correggi_frr': (opzioni_correggi_frr, calcola_correggi_frr),
    'rinomina': (opzioni_loopback, calcola_rinomina),
    'aggiungi_dispositivo': (opzioni_aggiungi_dispositivo, calcola_aggiungi_dispositivo),
    'togli_dispositivo': (opzioni_togli_dispositivo, calcola_togli_dispositivo),
    'aggiungi_interfaccia': (opzioni_ip_interfaccia, calcola_aggiungi_interfaccia),
    'togli_interfaccia': (opzioni_ip_interfaccia, calcola_togli_interfaccia),
    'annulla': (opzioni_annulla, calcola_annulla),
}
