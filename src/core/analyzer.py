"""
src/core/analyzer.py
Analisi statica di frr.conf, diagnostica topologia/configurazione/DNS, riepilogo e generazione test ping.
"""
import difflib
import ipaddress
import os
import re

from .cli_io import correggi_nome_kathara, input, nome_kathara_valido
from .file_utils import _leggi_righe
from .net_frr import _as_number, _contiene, _norm_net, _strip_cidr
from .persistence import parse_lab_conf_for_nodes
from .templates import _RE_APACHE, _RE_GW, _RE_IP_ADD


def collect_lab_ips(lab_path, routers=None):
    """Raccoglie gli endpoint del lab: tutti gli IP associati a interfacce."""
    endpoints = []
    seen = set()
    if routers:
        for rname, rdata in routers.items():
            for iface in rdata.get('interfaces', []):
                ip = _strip_cidr(iface.get('ip'))
                if ip:
                    key = (ip, rname, iface.get('name'))
                    if key not in seen:
                        seen.add(key)
                        endpoints.append({'ip': ip, 'name': rname, 'iface': iface.get('name')})

    try:
        for fname in os.listdir(lab_path):
            if not fname.endswith('.startup'):
                continue
            node_name = fname[:-8]
            fpath = os.path.join(lab_path, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    for L in f:
                        if 'ip address add' in L:
                            parts = L.strip().split()
                            if len(parts) >= 4:
                                ip = _strip_cidr(parts[3])
                                iface = None
                                if 'dev' in parts:
                                    try:
                                        dev_idx = parts.index('dev')
                                        if dev_idx + 1 < len(parts):
                                            iface = parts[dev_idx + 1]
                                    except Exception:
                                        iface = None
                                key = (ip, node_name, iface)
                                if ip and key not in seen:
                                    seen.add(key)
                                    endpoints.append({'ip': ip, 'name': node_name, 'iface': iface})
            except Exception:
                continue
    except Exception:
        pass

    return endpoints


def generate_ping_oneliner(endpoints):
    """Genera una one-liner bash che esegue `ping -c 1` su ogni endpoint."""
    if not endpoints:
        return ''
    toks = []
    for e in endpoints:
        ip = e.get('ip')
        name = e.get('name') or ''
        iface = e.get('iface') or ''
        token = f"{ip}|{name}|{iface}"
        toks.append(f'"{token}"')
    recs = ' '.join(toks)
    cmd = (
        "for rec in " + recs + "; do IFS='|' read -r ip name iface <<< \"$rec\"; "
        "out=$(ping -c 1 \"$ip\" 2>&1); "
        "loss=$(echo \"$out\" | awk -F',' '/packet loss/ {print $3}' | awk '{print $1}'); "
        "if [ -z \"$loss\" ]; then echo -e \"[!] $ip ($name $iface): no reply\"; else "
        "loss_num=$(echo \"$loss\" | tr -d '%'); "
        "if [ \"$loss_num\" = \"0\" ]; then echo -e \"[OK] $ip ($name $iface): $loss packet loss\"; else echo -e \"[!] $ip ($name $iface): $loss packet loss\"; fi; fi; done"
    )
    return cmd


def _analizza_frr(righe):
    """Estrae da frr.conf ciò che serve al riepilogo, indipendentemente dall'indentazione."""
    cfg = {
        'asn': None, 'bgp_networks': [], 'neighbors': {}, 'descr': {}, 'link': {},
        'igp': {}, 'redistribute': {}, 'costi': [], 'prefix_lists': {}, 'access_lists': {},
        'route_maps': {}, 'auto_cost': None, 'default_orig': {}, 'default_igp': [], 'rip_route': []
    }
    blocco, rm, iface = None, None, None
    for raw in righe:
        s = ' '.join(raw.split())
        if not s or s.startswith('!'):
            continue
        m = re.match(r'router (bgp|ospf|rip)\b ?(\d*)', s)
        if m:
            blocco, rm, iface = m.group(1), None, None
            if blocco == 'bgp':
                cfg['asn'] = m.group(2)
            cfg['igp'].setdefault(blocco, []) if blocco != 'bgp' else None
            continue
        m = re.match(r'interface (\S+)', s)
        if m:
            blocco, rm, iface = 'interface', None, m.group(1)
            continue
        m = re.match(r'ip prefix-list (\S+) (?:seq \d+ )?(permit|deny) (\S+)', s)
        if m:
            cfg['prefix_lists'].setdefault(m.group(1), []).append((m.group(2), m.group(3)))
            continue
        m = re.match(r'(?:ip )?access-list (\S+) (?:seq \d+ )?(permit|deny) (\S+)', s)
        if m:
            cfg['access_lists'].setdefault(m.group(1), []).append((m.group(2), m.group(3)))
            continue
        m = re.match(r'route-map (\S+) (permit|deny) (\d+)', s)
        if m:
            blocco, rm = 'route-map', {'azione': m.group(2), 'seq': int(m.group(3)), 'match': [], 'set': []}
            cfg['route_maps'].setdefault(m.group(1), []).append(rm)
            continue
        if blocco == 'route-map' and rm is not None and re.match(r'(match|set) ', s):
            rm['match' if s.startswith('match') else 'set'].append(s.split(' ', 1)[1])
            continue
        if blocco == 'interface' and 'ospf cost' in s:
            cfg['costi'].append(f"{iface} {s.split()[-1]}")
            continue
        m = re.match(r'neighbor (\S+) (.*)', s)
        if m:
            ip, resto = m.groups()
            t = resto.split()
            if t[0] == 'remote-as':
                cfg['neighbors'][ip] = t[1]
            elif t[0] == 'description':
                cfg['descr'][ip] = ' '.join(t[1:])
            elif t[0] == 'default-originate':
                cfg['default_orig'][ip] = t[2] if len(t) >= 3 and t[1] == 'route-map' else ''
            elif t[0] in ('prefix-list', 'route-map', 'filter-list', 'distribute-list') and len(t) >= 3:
                cfg['link'].setdefault(ip, []).append((t[0], t[1], t[2]))
            continue
        if s.startswith('network '):
            p = s.split()
            if blocco == 'bgp':
                cfg['bgp_networks'].append(p[1])
            elif blocco in ('ospf', 'rip'):
                cfg['igp'][blocco].append(p[1] + (f" area {p[3]}" if len(p) >= 4 and p[2] == 'area' else ''))
            continue
        m = re.match(r'auto-cost reference-bandwidth (\d+)', s)
        if m and blocco == 'ospf':
            cfg['auto_cost'] = m.group(1)
            continue
        m = re.match(r'area (\S+) stub', s)
        if m and blocco == 'ospf':
            cfg['igp']['ospf'].append(f"area {m.group(1)} stub")
            continue
        if blocco in ('ospf', 'rip') and (
            s.startswith('default-information originate') or (blocco == 'rip' and s == 'route 0.0.0.0/0')
        ):
            cfg['default_igp'].append(f"{blocco.upper()} {s}")
            continue
        if blocco == 'rip' and re.match(r'route \S+$', s):
            cfg['rip_route'].append(s.split()[1])
            continue
        if s.startswith('redistribute ') and blocco in ('ospf', 'rip', 'bgp'):
            cfg['redistribute'].setdefault(blocco, []).append(s.split(' ', 1)[1])
    return cfg


def _descrivi_lista(voci):
    """[('deny','a'),('deny','b'),('permit','any')] -> 'deny a, b; permit any'"""
    parti, cur, nets = [], None, []
    for azione, rete in voci:
        if azione != cur and cur is not None:
            parti.append(f"{cur} {', '.join(nets)}")
            nets = []
        cur = azione
        nets.append(rete)
    if cur:
        parti.append(f"{cur} {', '.join(nets)}")
    return '; '.join(parti)


def _descrivi_route_map(cfg, nome):
    voci = []
    for e in sorted(cfg['route_maps'].get(nome, []), key=lambda x: x['seq']):
        reti = []
        for mt in e['match']:
            m = re.match(r'ip address prefix-list (\S+)', mt)
            if m:
                reti += [r for a, r in cfg['prefix_lists'].get(m.group(1), []) if a == 'permit']
                continue
            m = re.match(r'ip address (\S+)', mt)
            if m:
                acl = cfg['access_lists'].get(m.group(1), [])
                reti.append(f"[access-list {m.group(1)}: {_descrivi_lista(acl) or 'non definita!'}]")
                continue
            reti.append(mt)
        dove = f"per {', '.join(reti)}" if reti else "su tutte"
        if e['azione'] == 'deny':
            voci.append(f"scarta {', '.join(reti) if reti else 'tutte'}")
        elif e['set']:
            voci.append(f"{', '.join(e['set'])} {dove}")
        elif reti:
            voci.append(f"accetta solo {', '.join(reti)}")
        else:
            voci.append("le altre invariate")
    return '; '.join(voci) if voci else '(route-map non definita!)'


def controlla_topologia(lab_path):
    """Cerca refusi di LAN/IP leggendo lab.conf e gli startup del lab."""
    nodes, _ = parse_lab_conf_for_nodes(lab_path)
    avvisi = [
        f"Nome '{n}' non valido per Kathará (solo lettere minuscole, cifre e _): il lab non si "
        f"avvierà. Apri il lab dal menu 5 (Opzioni): propone di rinominarlo in "
        f"'{correggi_nome_kathara(n)}' senza perdere le altre modifiche."
        for n in sorted(nodes) if not nome_kathara_valido(n)
    ]
    per_lan = {}
    for node, meta in nodes.items():
        ips = {}
        for l in _leggi_righe(os.path.join(lab_path, f"{node}.startup")):
            m = re.match(r'\s*ip\s+a(?:ddr(?:ess)?)?\s+add\s+(\S+)\s+dev\s+(\S+)', l)
            if m:
                ips.setdefault(m.group(2), m.group(1))
        for idx, lan in meta.get('interfaces', {}).items():
            dev = f"eth{idx}"
            try:
                iface = ipaddress.ip_interface(ips[dev]) if dev in ips else None
            except ValueError:
                iface = None
            per_lan.setdefault(lan, []).append((node, dev, iface))
    subnet_lan = {}
    for lan, membri in sorted(per_lan.items()):
        reti = {str(i.network) for _, _, i in membri if i is not None}
        chi = ', '.join(f"{n} {d} {i or '(senza IP)'}" for n, d, i in membri)
        if len(reti) > 1:
            avvisi.append(f"LAN {lan}: interfacce in subnet diverse ({chi})")
        for r in reti:
            subnet_lan.setdefault(r, set()).add(lan)
        corte = [i for _, _, i in membri if i is not None and i.network.prefixlen >= 30]
        if corte and len(membri) == 1:
            avvisi.append(
                f"LAN {lan}: link {corte[0].network} con un solo dispositivo ({chi}). "
                f"Manca l'altro estremo o il nome della LAN è sbagliato?"
            )
        elif corte and len(membri) > 2:
            avvisi.append(f"LAN {lan}: link {corte[0].network} con {len(membri)} dispositivi ({chi})")

    con_switch = {lan for lan, membri in per_lan.items() if any(i is None for _, _, i in membri)}
    for rete, lans in sorted(subnet_lan.items()):
        if len(lans) > 1 and not (lans & con_switch):
            avvisi.append(
                f"Subnet {rete} usata su LAN diverse ({', '.join(sorted(lans))}): "
                f"probabile nome di LAN sbagliato"
            )
    return avvisi


def stampa_controllo_topologia(lab_path):
    avvisi = controlla_topologia(lab_path)
    if avvisi:
        print("\n⚠️ Controllo topologia: possibili errori di LAN/IP")
        for a in avvisi:
            print(f"   - {a}")
        print("   (correggi l'XML e reimportalo, oppure modifica lab.conf e gli startup)")
    else:
        print("\n✅ Controllo topologia: LAN e subnet coerenti.")
    return avvisi


def _voce_prefix_list(resto):
    """'permit 1.0.0.0/8 le 24' -> (azione, rete, ge, le); None se FRR scarterebbe la riga."""
    m = re.fullmatch(r'(?:seq \d+ )?(permit|deny) (any|\S+/\d+)(?: ge (\d+))?(?: le (\d+))?', resto)
    if not m:
        return None
    if m.group(2) != 'any':
        try:
            ipaddress.ip_network(m.group(2), strict=False)
        except ValueError:
            return None
    return m.group(1), m.group(2), int(m.group(3) or 0), int(m.group(4) or 0)


def _esito_prefix_list(voci, rete):
    """Azione della prima voce che corrisponde alla rete; None = nessuna (viene scartata)."""
    try:
        r = ipaddress.ip_network(rete, strict=False)
    except ValueError:
        return 'deny'
    for azione, p, ge, le in voci:
        if p == 'any':
            return azione
        n = ipaddress.ip_network(p, strict=False)
        if ge or le:
            if r.subnet_of(n) and (ge or n.prefixlen) <= r.prefixlen <= (le or 32):
                return azione
        elif r == n:
            return azione
    return None


def riferimenti_frr(righe):
    """Route-map, prefix-list e access-list di un frr.conf: usate ma non definite (errore)
    o definite ma non usate (avviso)."""
    definiti = {'route-map': {}, 'prefix-list': {}, 'access-list': {}}
    usi = []
    voci_pl, scartate, reti_bgp, blocco = {}, [], [], None
    vicini = set()
    for n, raw in enumerate(righe, 1):
        s = ' '.join(raw.split())
        if not s or s.startswith('!'):
            continue
        m = re.match(r'(router|interface|route-map)\b', s)
        if m:
            blocco = 'bgp' if s.startswith('router bgp') else m.group(1)
        m = re.match(r'network (\S+)$', s)
        if m and blocco == 'bgp':
            reti_bgp.append((n, m.group(1)))
        m = re.match(r'route-map (\S+) (permit|deny) \d+$', s)
        if m:
            definiti['route-map'].setdefault(m.group(1), n)
            continue
        m = re.match(r'ip prefix-list (\S+) (.*)', s)
        if m:
            nome, resto = m.groups()
            if not resto.startswith('description'):
                voce = _voce_prefix_list(resto)
                if voce:
                    definiti['prefix-list'].setdefault(nome, n)
                    voci_pl.setdefault(nome, []).append(voce)
                else:
                    scartate.append((n, s, nome, resto.split()[-1]))
            continue
        m = re.match(r'(?:ip )?access-list (\S+) ', s)
        if m:
            definiti['access-list'].setdefault(m.group(1), n)
            continue
        m = re.match(r'neighbor (\S+) remote-as ', s)
        if m:
            vicini.add(m.group(1))
            continue
        m = re.match(r'neighbor (\S+) (route-map|prefix-list) (\S+) (in|out)\b', s)
        if m:
            usi.append((n, s, m.group(2), m.group(3), ('neighbor', m.group(1), m.group(4))))
            continue
        m = re.match(r'neighbor (\S+) distribute-list (\S+) (in|out)\b', s)
        if m:
            usi.append((n, s, 'access-list', m.group(2), ('neighbor', m.group(1), m.group(3))))
            continue
        m = re.match(r'match ip address prefix-list (\S+)', s)
        if m:
            usi.append((n, s, 'prefix-list', m.group(1), ('match',)))
            continue
        m = re.match(r'match ip address (\S+)$', s)
        if m:
            usi.append((n, s, 'access-list', m.group(1), ('match',)))
            continue
        m = re.match(r'distribute-list (?:prefix (\S+)|(\S+)) (in|out)\b', s)
        if m:
            usi.append((n, s, 'prefix-list' if m.group(1) else 'access-list', m.group(1) or m.group(2), ('altro',)))
            continue
        m = re.search(r'\broute-map (\S+)', s)
        if m:
            usi.append((n, s, 'route-map', m.group(1), ('altro',)))
    usati = {(tipo, nome) for _, _, tipo, nome, _ in usi}
    art = {'route-map': 'la ', 'prefix-list': 'la ', 'access-list': "l'"}
    out = []
    for n, s, nome, valore in scartate:
        proposta = next((r for _, r in reti_bgp if _contiene(r, valore)), None)
        out.append({
            'riga': n, 'testo': s, 'gravita': 'errore',
            'messaggio': (
                f"'{valore}' non è valido in una prefix-list (serve una rete con la maschera): "
                f"FRR scarta la riga." + (f" Forse intendevi {proposta}?" if proposta else '')
            )
        })
    for n, s, tipo, nome, ctx in usi:
        if nome in definiti[tipo]:
            continue
        if ctx[0] == 'neighbor':
            effetto = (
                f"FRR non dà errori e la sessione resta Established, ma "
                f"{'da' if ctx[2] == 'in' else 'verso'} {ctx[1]} non passa nessuna rotta."
            )
        elif ctx[0] == 'match':
            effetto = "questa voce della route-map non troverà mai corrispondenze (il suo 'set' non si applica)."
        else:
            effetto = "il riferimento non porta a niente."
        simili = difflib.get_close_matches(nome, list(definiti[tipo]), n=1, cutoff=0.6)
        forse = f" Forse intendevi {simili[0]} (riga {definiti[tipo][simili[0]]})?" if simili else ''
        if any(x[2] == nome for x in scartate):
            forse = ' Tutte le sue righe sono scartate: correggile.'
        out.append({
            'riga': n, 'testo': s, 'gravita': 'errore',
            'messaggio': f"{art[tipo]}{tipo} {nome} non è definita: {effetto}{forse}"
        })

    liste_out = {
        c[1]: nome for _, _, tipo, nome, c in usi
        if tipo == 'prefix-list' and c[0] == 'neighbor' and c[2] == 'out'
    }

    def verso_cliente(ip):
        voci = voci_pl.get(liste_out[ip]) if ip in liste_out else [('permit', 'any', 0, 0)]
        return bool(voci) and all(v[:2] == ('permit', 'any') for v in voci)

    for n, s, tipo, nome, ctx in usi:
        if tipo == 'prefix-list' and ctx[0] == 'neighbor' and ctx[2] == 'out' and nome in voci_pl:
            for riga, rete in reti_bgp:
                capi = [ip for ip in vicini if _contiene(rete, ip)]
                if capi and not any(verso_cliente(ip) for ip in capi):
                    continue
                if _esito_prefix_list(voci_pl[nome], rete) is None:
                    out.append({
                        'riga': n, 'testo': s, 'gravita': 'avviso',
                        'messaggio': (
                            f"questo router annuncia {rete} (riga {riga}), ma la prefix-list {nome} "
                            f"non la lascia passare verso {ctx[1]}: se il testo vuole annunciarla, aggiungila."
                        )
                    })
    for tipo, nomi in definiti.items():
        for nome, n in nomi.items():
            if (tipo, nome) not in usati:
                out.append({
                    'riga': n, 'testo': f"{tipo} {nome}", 'gravita': 'avviso',
                    'messaggio': (
                        f"{art[tipo]}{tipo} {nome} è definita ma non è usata da nessuna parte "
                        f"(nome scritto diverso dove dovrebbe essere usata?)."
                    )
                })
    return sorted(out, key=lambda x: x['riga'])


def isole_ospf(lab_path):
    """Domini OSPF del lab: router OSPF collegati da LAN e dello stesso AS."""
    nodes, _ = parse_lab_conf_for_nodes(lab_path)
    cfg = {}
    for n in nodes:
        f = os.path.join(lab_path, n, 'etc', 'frr', 'frr.conf')
        if os.path.exists(f):
            c = _analizza_frr(_leggi_righe(f))
            if 'ospf' in c['igp']:
                cfg[n] = c
    as_di = {n: str(c['asn'] or '') for n, c in cfg.items()}
    vicini = {n: set() for n in cfg}
    lan_membri = {}
    for n, meta in nodes.items():
        for lan in meta.get('interfaces', {}).values():
            lan_membri.setdefault(lan, []).append(n)
    for membri in lan_membri.values():
        rs = [m for m in membri if m in cfg]
        for a in rs:
            vicini[a].update(b for b in rs if b != a and (not as_di[a] or not as_di[b] or as_di[a] == as_di[b]))
    isole, visti = [], set()
    for start in sorted(cfg):
        if start in visti:
            continue
        isola, coda = {start}, [start]
        while coda:
            for y in vicini[coda.pop()]:
                if y not in isola:
                    isola.add(y)
                    coda.append(y)
        visti |= isola
        asn = (
            next((as_di[n] for n in sorted(isola) if as_di[n]), '')
            or next((str(_as_number(n, {})) for n in sorted(isola) if _as_number(n, {})), '')
        )
        isole.append((f"AS{asn}" if asn else 'OSPF', sorted(isola), {n: cfg[n] for n in isola}))
    return isole


def _file_bind(lab_path, nome, f):
    """Percorso locale di un file citato in named.conf."""
    if f.startswith('/'):
        return os.path.join(lab_path, nome, *f.strip('/').split('/'))
    return os.path.join(lab_path, nome, 'etc', 'bind', *f.split('/'))


def _zone_bind(lab_path, nome):
    """[{'zona', 'tipo', 'file'}] dichiarate in named.conf e named.conf.local."""
    zone = []
    for f in ('named.conf', 'named.conf.local'):
        testo = '\n'.join(_leggi_righe(os.path.join(lab_path, nome, 'etc', 'bind', f)))
        for m in re.finditer(r'zone\s+"([^"]+)"\s*(?:IN\s*)?\{(.*?)\}\s*;', testo, re.S):
            t = re.search(r'\btype\s+(\w+)', m.group(2))
            fl = re.search(r'\bfile\s+"([^"]+)"', m.group(2))
            zone.append({
                'zona': m.group(1).rstrip('.').lower() or '.',
                'tipo': t.group(1) if t else '?',
                'file': _file_bind(lab_path, nome, fl.group(1)) if fl else None
            })
    return zone


def _nome_assoluto(nome, origine):
    if nome == '@':
        return origine or '.'
    if nome.endswith('.'):
        return nome.rstrip('.').lower() or '.'
    return f"{nome}.{origine}".lower() if origine else nome.lower()


def _record_dns(path, zona):
    """[(nome, tipo, valore)] di un file di zona, con i nomi assoluti."""
    origine = '' if zona == '.' else zona.lower()
    tipi = ('A', 'NS', 'SOA', 'CNAME', 'MX', 'PTR', 'AAAA', 'TXT')
    out, ultimo, in_par = [], origine or '.', False
    for raw in _leggi_righe(path):
        riga = raw.split(';', 1)[0]
        if in_par:
            in_par = ')' not in riga
            continue
        if '(' in riga and ')' not in riga:
            in_par = True
        m = re.match(r'\s*\$ORIGIN\s+(\S+)', riga)
        if m:
            origine = m.group(1).rstrip('.').lower()
            continue
        if not riga.strip() or riga.lstrip().startswith('$'):
            continue
        tok = riga.split()
        i = next((k for k, t in enumerate(tok) if t.upper() in tipi), None)
        if i is None or i + 1 >= len(tok):
            continue
        if riga[:1].isspace() or i == 0 or tok[0].upper() == 'IN' or tok[0].isdigit():
            nome = ultimo
        else:
            nome = _nome_assoluto(tok[0], origine)
        ultimo = nome
        out.append((nome, tok[i].upper(), tok[i + 1]))
    return out


def leggi_dispositivi(lab_path):
    """Tutti i dispositivi del lab letti dai file: tipo, interfacce, gateway, resolver, zone DNS, demoni FRR e AS."""
    nodes, _ = parse_lab_conf_for_nodes(lab_path)
    disp = {}
    for nome, meta in sorted(nodes.items()):
        startup = _leggi_righe(os.path.join(lab_path, f"{nome}.startup"))
        ips, gw = {}, None
        for riga in startup:
            m = _RE_IP_ADD.match(riga)
            if m:
                ips.setdefault(m.group(2), []).append(m.group(1))
            m = _RE_GW.match(riga)
            if m:
                gw = (m.group(1) or m.group(2)).split('/')[0]
        d = os.path.join(lab_path, nome)
        testo = '\n'.join(startup)
        frr = os.path.join(d, 'etc', 'frr', 'frr.conf')
        if os.path.exists(frr) or 'frr' in (meta.get('image') or ''):
            tipo = 'router'
        elif os.path.isfile(os.path.join(d, 'etc', 'bind', 'named.conf')) or re.search(r'\bnamed\b', testo):
            tipo = 'dns'
        elif os.path.isdir(os.path.join(d, 'var', 'www')) or 'apache2' in testo:
            tipo = 'www'
        else:
            tipo = 'host'
        interfacce = [
            {'dev': f"eth{i}", 'idx': i, 'lan': lan, 'ip': (ips.get(f"eth{i}") or [''])[0]}
            for i, lan in sorted((k, v) for k, v in meta.get('interfaces', {}).items() if isinstance(k, int))
        ]
        demoni = re.findall(
            r'^\s*(bgpd|ospfd|ripd)\s*=\s*yes',
            '\n'.join(_leggi_righe(os.path.join(d, 'etc', 'frr', 'daemons'))),
            re.M
        )
        cfg = _analizza_frr(_leggi_righe(frr)) if os.path.exists(frr) else None
        resolv = '\n'.join(_leggi_righe(os.path.join(d, 'etc', 'resolv.conf')))
        altri_ip = [
            (dev, ip) for dev, lista in ips.items() for ip in lista
            if dev != 'lo' and not any(it['dev'] == dev for it in interfacce)
        ]
        disp[nome] = {
            'nome': nome, 'tipo': tipo, 'interfacce': interfacce, 'loopback': ips.get('lo', []),
            'altri_ip': altri_ip, 'gateway': gw, 'apache': bool(_RE_APACHE.search(testo)),
            'nameserver': re.findall(r'^\s*nameserver\s+(\S+)', resolv, re.M),
            'zone': _zone_bind(lab_path, nome) if tipo == 'dns' else [],
            'demoni': demoni, 'asn': (cfg or {}).get('asn'), 'frr': os.path.exists(frr)
        }
    return disp


def _proprietari(disp):
    """IP -> (dispositivo, interfaccia, LAN); per le loopback la LAN è None."""
    out = {}
    for d in disp.values():
        for it in d['interfacce']:
            if it['ip']:
                out[it['ip'].split('/')[0]] = (d['nome'], it['dev'], it['lan'])
        for lb in d['loopback']:
            out.setdefault(lb.split('/')[0], (d['nome'], 'lo', None))
        for dev, ip in d.get('altri_ip', []):
            out.setdefault(ip.split('/')[0], (d['nome'], dev, None))
    return out


def _segmenti(disp):
    """LAN -> segmento: le LAN unite da uno switch sono lo stesso segmento Ethernet."""
    seg = {it['lan']: it['lan'] for d in disp.values() for it in d['interfacce']}

    def radice(x):
        while seg[x] != x:
            x = seg[x]
        return x

    for d in disp.values():
        if (
            d['tipo'] != 'router' and len(d['interfacce']) > 1
            and not d.get('altri_ip') and not any(it['ip'] for it in d['interfacce'])
        ):
            prima = radice(d['interfacce'][0]['lan'])
            for it in d['interfacce'][1:]:
                seg[radice(it['lan'])] = prima
    return {l: radice(l) for l in seg}


def _deleghe_dns(d, disp):
    """[(file, zona_padre, figlia, nameserver, ip_glue)] delle deleghe scritte nelle zone master di d."""
    out = []
    for z in d['zone']:
        if z['tipo'] != 'master' or not z['file']:
            continue
        rec = _record_dns(z['file'], z['zona'])
        a = {}
        for n, t, v in rec:
            if t == 'A':
                a.setdefault(n, []).append(v)
        for n, t, v in rec:
            if t == 'NS' and n != z['zona']:
                ns = _nome_assoluto(v, z['zona'] if z['zona'] != '.' else '')
                for ip in a.get(ns, []) or [None]:
                    out.append((os.path.basename(z['file']), z['zona'], n, ns, ip))
    return out


def controlli_host(lab_path, disp=None):
    """Controlli su pc, www e dns: [(dispositivo, messaggio)]."""
    disp = disp or leggi_dispositivi(lab_path)
    own = _proprietari(disp)
    seg = _segmenti(disp)
    master = {}
    for d in disp.values():
        for z in d['zone']:
            if z['tipo'] == 'master':
                master.setdefault(z['zona'], set()).add(d['nome'])
    out = []
    for n in sorted(disp):
        d = disp[n]
        if d['tipo'] != 'router' and d['gateway']:
            gw = d['gateway']
            reti = []
            for lan, ip in [(it['lan'], it['ip']) for it in d['interfacce']] + [(None, ip) for _, ip in d['altri_ip']]:
                try:
                    reti.append((ipaddress.ip_interface(ip).network, lan))
                except ValueError:
                    pass
            try:
                gwip = ipaddress.ip_address(gw)
            except ValueError:
                gwip = None
                out.append((n, f"il gateway '{gw}' non è un indirizzo IP valido."))
            if gwip is not None:
                dentro = [lan for rete, lan in reti if gwip in rete]
                chi = own.get(gw)
                if reti and not dentro:
                    out.append((
                        n,
                        f"il gateway {gw} non è nella rete delle sue interfacce "
                        f"({', '.join(str(r) for r, _ in reti)}): il dispositivo non lo raggiunge."
                    ))
                elif chi is None:
                    out.append((n, f"il gateway {gw} non è l'IP di nessun dispositivo del lab (refuso?)."))
                elif chi[0] == n:
                    out.append((n, f"il gateway {gw} è un suo stesso indirizzo."))
                elif (
                    chi[2] is not None and None not in dentro
                    and seg.get(chi[2]) not in {seg.get(l) for l in dentro}
                ):
                    out.append((
                        n,
                        f"il gateway {gw} è di {chi[0]}, che è sulla LAN {chi[2]}: non è sulla "
                        f"stessa LAN del dispositivo ({', '.join(dentro)})."
                    ))
                elif disp[chi[0]]['tipo'] != 'router' and len(disp[chi[0]]['interfacce']) < 2:
                    out.append((n, f"il gateway {gw} è di {chi[0]}, che non è un router."))
        for ns in d['nameserver']:
            chi = own.get(ns)
            if chi is None:
                out.append((n, f"resolv.conf: il nameserver {ns} non è l'IP di nessun dispositivo del lab."))
            elif disp[chi[0]]['tipo'] != 'dns':
                out.append((n, f"resolv.conf: il nameserver {ns} è di {chi[0]}, che non è un server DNS."))
        if d['tipo'] == 'www' and not d['apache']:
            out.append((n, "server www senza 'systemctl start apache2' nello startup: il sito non risponde."))
        for z in d['zone']:
            if z['tipo'] not in ('master', 'hint') or not z['file'] or not os.path.isfile(z['file']):
                continue
            rec = _record_dns(z['file'], z['zona'])
            fname = os.path.basename(z['file'])
            if z['tipo'] == 'hint':
                ns = {_nome_assoluto(v, '') for nn, t, v in rec if t == 'NS'}
                for nn, t, v in rec:
                    if t == 'A' and nn in ns:
                        chi = own.get(v)
                        if not chi or chi[0] not in master.get('.', set()):
                            out.append((
                                n,
                                f"{fname}: il root server {nn} ha IP {v}, che "
                                + (
                                    f"è di {chi[0]}, non del root del lab" if chi
                                    else "non è di nessun dispositivo del lab"
                                )
                                + (f" ({', '.join(sorted(master['.']))})." if master.get('.') else '.')
                            ))
                continue
            glue = set()
            for _f, padre, figlia, nsn, ip in _deleghe_dns({'zone': [z]}, disp):
                if ip is None:
                    continue
                glue.add((nsn, ip))
                chi = own.get(ip)
                servono = master.get(figlia, set())
                if not chi or chi[0] not in servono:
                    out.append((
                        n,
                        f"{fname}: delega di {figlia} a {nsn} ({ip}), ma {ip} "
                        + (
                            f"è di {chi[0]}, che non è master di {figlia}" if chi
                            else "non è di nessun dispositivo del lab"
                        )
                        + (f" (lo è {', '.join(sorted(servono))})." if servono else '.')
                    ))
            for nn, t, v in rec:
                if t == 'A' and (nn, v) not in glue and v not in own:
                    out.append((n, f"{fname}: il record {nn} A {v} punta a un IP che nessun dispositivo del lab ha."))
    return out


def stampa_host_e_server(lab_path, disp=None):
    """Riepilogo di pc, www e dns: IP e LAN, gateway, resolver, apache2, zone e deleghe."""
    disp = disp or leggi_dispositivi(lab_path)
    altri = [d for d in disp.values() if d['tipo'] != 'router']
    if not altri:
        return
    own = _proprietari(disp)

    def chi(ip):
        return own.get(ip, ('?',))[0]

    print("\n--- Host e server ---")
    larg = max(len(d['nome']) for d in altri)
    for d in sorted(altri, key=lambda x: (['host', 'www', 'dns'].index(x['tipo']), x['nome'])):
        ifs = ', '.join(
            f"{it['ip'] or '(senza IP)'} (LAN {it['lan']})" for it in d['interfacce']
        ) or '(nessuna interfaccia)'
        parti = [
            f"{d['nome']:<{larg}}  {d['tipo']:<4}  {ifs}",
            f"gw {d['gateway']} ({chi(d['gateway'])})" if d['gateway'] else "gw -"
        ]
        if d['nameserver']:
            parti.append('resolver ' + ', '.join(f"{ns} ({chi(ns)})" for ns in d['nameserver']))
        if d['tipo'] == 'www':
            parti.append('apache2 avviato' if d['apache'] else 'apache2 NON avviato')
        if d['zone']:
            parti.append('zone: ' + ', '.join(f"{z['zona']} ({z['tipo']})" for z in d['zone']))
        print('   '.join(parti))
        for _f, padre, figlia, ns, ip in _deleghe_dns(d, disp):
            print(
                f"{'':<{larg}}        delega {figlia} -> {ns} {ip or '(senza glue)'}"
                + (f" ({chi(ip)})" if ip else '')
            )


def controlli_configurazione(lab_path):
    """Cerca le dimenticanze tipiche leggendo solo i file del lab."""
    nodes, _ = parse_lab_conf_for_nodes(lab_path)
    ips, rotte, default_statica = {}, {}, {}
    for node in nodes:
        for l in _leggi_righe(os.path.join(lab_path, f"{node}.startup")):
            m = re.match(r'\s*ip\s+a(?:ddr(?:ess)?)?\s+add\s+(\S+)\s+dev\s+(\S+)', l)
            if m:
                try:
                    ips.setdefault((node, m.group(2)), ipaddress.ip_interface(m.group(1)))
                except ValueError:
                    pass
            if re.match(r'\s*(ip\s+route\s+add|route\s+add)\b', l):
                rotte[node] = True
                if re.match(r'\s*(ip\s+route\s+add|route\s+add)\s+(-net\s+)?(default|0\.0\.0\.0/0)\b', l):
                    default_statica[node] = True
    cfg = {}
    for node in nodes:
        f = os.path.join(lab_path, node, 'etc', 'frr', 'frr.conf')
        if os.path.exists(f):
            cfg[node] = _analizza_frr(_leggi_righe(f))
    owner = {str(i.ip): n for (n, _), i in ips.items()}
    lan_membri = {}
    for node, meta in nodes.items():
        for idx, lan in meta.get('interfaces', {}).items():
            lan_membri.setdefault(lan, []).append((node, f"eth{idx}"))
    avvisi = []

    # 1. reti interne non annunciate
    igp = {n for n, c in cfg.items() if c['igp']}
    vicini = {n: set() for n in cfg}
    for membri in lan_membri.values():
        rs = [n for n, _ in membri if n in cfg]
        for a in rs:
            vicini[a].update(r for r in rs if r != a)
    visti = set()
    for start in sorted(igp):
        if start in visti:
            continue
        isola, coda = {start}, [start]
        while coda:
            x = coda.pop()
            for y in vicini[x]:
                if y in isola or y not in igp:
                    continue
                if cfg[x]['asn'] and cfg[y]['asn'] and cfg[x]['asn'] != cfg[y]['asn']:
                    continue
                isola.add(y)
                coda.append(y)
        visti |= isola
        bordo = [n for n in isola if cfg[n]['asn']]
        if not bordo:
            continue
        annunciate = []
        for b in bordo:
            for n in cfg[b]['bgp_networks']:
                try:
                    annunciate.append(ipaddress.ip_network(n, strict=False))
                except ValueError:
                    pass
        mancanti = set()
        for membri in lan_membri.values():
            rs = [n for n, _ in membri if n in cfg]
            if not rs or any(r not in isola for r in rs):
                continue
            for n, dev in membri:
                i = ips.get((n, dev))
                if i and not any(i.ip in a for a in annunciate):
                    mancanti.add(str(i.network))
        if mancanti:
            asn = cfg[bordo[0]]['asn']
            proposta = next(
                (e.split()[0] for b in bordo for p in ('ospf', 'rip')
                 for e in cfg[b]['igp'].get(p, []) if not e.startswith('area')),
                ''
            )
            avvisi.append(
                f"AS{asn}: reti interne non annunciate in BGP ({', '.join(sorted(mancanti))}). "
                f"Gli altri AS non le raggiungono -> Opzioni 6 su {', '.join(sorted(bordo))}"
                + (f" (es. {proposta})" if proposta else '')
                + ", a meno che il testo dica che non devono essere visibili."
            )

    # 2. iBGP incompleto
    per_as = {}
    for n, c in cfg.items():
        if c['asn']:
            per_as.setdefault(c['asn'], []).append(n)
    ips_di = {}
    for (n, _), i in ips.items():
        ips_di.setdefault(n, set()).add(str(i.ip))
    for asn, rs in sorted(per_as.items()):
        if len(rs) < 2:
            continue
        mancano = []
        for a in sorted(rs):
            senza = [b for b in sorted(rs) if b != a and not (set(cfg[a]['neighbors']) & ips_di.get(b, set()))]
            if senza:
                mancano.append(f"{a} -> {', '.join(senza)}")
        if mancano:
            avvisi.append(
                f"AS{asn}: sessioni iBGP mancanti ({'; '.join(mancano)}). "
                f"Se il testo le chiede -> Opzioni 7; se le vieta (es. butterfly) va bene così."
            )

    # 3. neighbor con IP inesistente o remote-as sbagliato
    for n, c in sorted(cfg.items()):
        for ip, ras in c['neighbors'].items():
            peer = owner.get(ip)
            if peer is None:
                avvisi.append(f"{n}: neighbor {ip} non corrisponde a nessun IP del lab (refuso?).")
            elif peer in cfg and cfg[peer]['asn'] and cfg[peer]['asn'] != ras:
                avvisi.append(f"{n}: neighbor {ip} ({peer}) ha remote-as {ras}, ma {peer} è in AS{cfg[peer]['asn']}.")

    # 4. route-map / prefix-list / access-list usate ma non definite, o definite ma non usate
    for n in sorted(cfg):
        for x in riferimenti_frr(_leggi_righe(os.path.join(lab_path, n, 'etc', 'frr', 'frr.conf'))):
            avvisi.append(f"{n} (frr.conf riga {x['riga']}): {x['messaggio']}")

    # 5. host senza gateway
    for n in sorted(nodes):
        if n not in cfg and n in ips_di and not rotte.get(n):
            avvisi.append(f"{n}: nessun default gateway, non raggiungerà nulla fuori dalla sua LAN.")

    # 6. costi OSPF espliciti senza auto-cost
    for et, rs, cfgs in isole_ospf(lab_path):
        costi = [f"{r} {c}" for r in rs for c in cfgs[r]['costi']]
        senza = [r for r in rs if not cfgs[r]['auto_cost']]
        if costi and senza:
            avvisi.append(
                f"{et}: costi OSPF espliciti ({', '.join(costi)}), ma in kathara/frr il costo predefinito "
                f"delle altre interfacce è 10000, non 10: il costo indicato renderà quel link il più "
                f"conveniente invece del più caro. Se il testo chiede percorsi che dipendono da questo "
                f"costo -> Opzioni 10 su {et} (verifica con la GUI: show ip ospf interface / Verifica percorso)."
            )

    # 7. pc, www e dns
    for n, msg in controlli_host(lab_path):
        avvisi.append(f"{n}: {msg}")

    # 8. router che generano la default route
    for n in sorted(cfg):
        c, cosa = cfg[n], []
        if c['default_orig']:
            cosa.append('default-originate verso ' + ', '.join(f"{ip} ({owner.get(ip, '?')})" for ip in c['default_orig']))
        if any(_norm_net(x) == '0.0.0.0/0' for x in c['bgp_networks'] if '/' in x):
            cosa.append('network 0.0.0.0/0 in BGP')
        cosa += c['default_igp']
        if default_statica.get(n):
            cosa.append('default statica nello startup')
        if cosa:
            avvisi.append(
                f"{n}: genera la default route ({'; '.join(cosa)}). Tienila solo se il testo la chiede: "
                f"molti testi dicono 'No router announces the default route'."
            )
    return avvisi


def stampa_controlli_configurazione(lab_path):
    avvisi = controlli_configurazione(lab_path)
    if avvisi:
        print("\n⚠️ Controlli: possibili dimenticanze (verifica con il testo)")
        for a in avvisi:
            print(f"   - {a}")
    else:
        print("✅ Controlli: nessuna dimenticanza trovata.")
    return avvisi


def _problemi_di(nome, avvisi):
    return [a for a in avvisi if re.search(rf'(?<![\w-]){re.escape(nome)}(?![\w-])', a)]


def riepilogo_configurazione(base_path, routers):
    """Stampa per ogni router: AS, network BGP, IGP, costi OSPF e policy collegate."""
    owner = {}
    for rn, rd in routers.items():
        for it in rd.get('interfaces', []):
            if it.get('ip'):
                owner[it['ip'].split('/')[0]] = rn
    print('\n=== Riepilogo configurazione ===')
    avvisi = stampa_controllo_topologia(base_path) + stampa_controlli_configurazione(base_path)
    for rn in routers:
        fpath = os.path.join(base_path, rn, 'etc', 'frr', 'frr.conf')
        if not os.path.exists(fpath):
            continue
        cfg = _analizza_frr(_leggi_righe(fpath))
        protos = ' '.join(routers[rn].get('protocols', []))
        print(f"\n{rn}" + (f" (AS{cfg['asn']})" if cfg['asn'] else '') + f"   [{protos}]")
        for igp in ('ospf', 'rip'):
            if igp in cfg['igp']:
                red = cfg['redistribute'].get(igp, [])
                print(
                    f"  {igp.upper()}: {', '.join(cfg['igp'][igp]) or '-'}"
                    + (f"   redistribute {', '.join(red)}" if red else '')
                    + (f"   auto-cost {cfg['auto_cost']}" if igp == 'ospf' and cfg['auto_cost'] else '')
                )
        if cfg['costi']:
            print(f"  costo OSPF: {', '.join(cfg['costi'])}")
        if cfg['default_igp']:
            print(f"  default route nell'IGP: {', '.join(cfg['default_igp'])}")
        if cfg['rip_route']:
            print(f"  RIP route (reti iniettate): {', '.join(cfg['rip_route'])}")
        if cfg['asn']:
            print(f"  network BGP: {', '.join(cfg['bgp_networks']) or '-'}")
            for ip, asn in cfg['neighbors'].items():
                chi = owner.get(ip) or cfg['descr'].get(ip, '?')
                tipo = 'iBGP' if asn == cfg['asn'] else 'eBGP'
                link = list(cfg['link'].get(ip, []))
                if ip in cfg['default_orig']:
                    link.insert(0, ('default-originate', cfg['default_orig'][ip], 'out'))
                if not link:
                    print(f"  {ip:<15} {chi:<10} AS{asn:<5} {tipo}  nessuna policy")
                    continue
                for i, (t, nome, direz) in enumerate(link):
                    if t == 'prefix-list':
                        cosa = (
                            f"prefix-list {_descrivi_lista(cfg['prefix_lists'][nome])}"
                            if nome in cfg['prefix_lists'] else f"prefix-list {nome} (non definita!)"
                        )
                    elif t == 'route-map':
                        cosa = f"route-map {_descrivi_route_map(cfg, nome)}"
                    elif t == 'default-originate':
                        cosa = "manda la default route (default-originate)" + (
                            f" se la route-map {nome} lo permette" if nome else ''
                        )
                    else:
                        cosa = f"{t} {nome}"
                    testa = f"  {ip:<15} {chi:<10} AS{asn:<5} {tipo}" if i == 0 else ' ' * 37
                    print(f"{testa}  {direz:<3}: {cosa}")
    disp = leggi_dispositivi(base_path)
    stampa_host_e_server(base_path, disp)
    print(
        "\nControlla ogni frase del testo: filtri (deny), preferenze (local-preference),"
        " MED (metric), network annunciate, costi OSPF, gateway e resolver dei pc, deleghe DNS."
    )
    citati = [n for n in sorted(disp) if _problemi_di(n, avvisi)]
    if citati:
        print(f"\nDispositivi citati nei controlli: {', '.join(citati)}")
        s = input("Vuoi correggere un dispositivo adesso? (nome, Invio = no): ").strip()
        if s in disp:
            from .device_editor import modifica_dispositivo_menu
            modifica_dispositivo_menu(base_path, routers, s)
        elif s:
            print(f"'{s}' non è un dispositivo del lab: puoi usare Opzioni 11.")