#!/usr/bin/env python3
"""
confronta_lab.py - confronta un lab generato con la soluzione di un esercizio.

Uso:
    python tools/confronta_lab.py <lab_generato> <cartella_esercizio> [--policy]

<cartella_esercizio> è una cartella di esercizi/lab-bgp/, es. lab-bgp/2017-12-15-candy,
che contiene solution/lab/ (o solution/lab.zip) e, se c'è, autocorrection/correction.json.

Controlli "base" (devono essere tutti OK):
  - topologia: domini di collisione (confrontati come gruppi di interfacce,
    i nomi delle LAN possono essere diversi), nodi, immagini
  - IP delle interfacce
  - demoni FRR attivi (e named/apache2 avviati nello startup)
  - BGP: ASN, neighbor (IP + remote-as), network annunciate
  - IGP: network RIP/OSPF, aree, stub, redistribute
Policy (prefix-list, route-map, access-list, local-preference, metric) sono
riportate come INFO: si fanno a mano dal menu Opzioni e i nomi possono differire.
Con --policy vengono stampate le righe di policy di entrambe le versioni.

Solo libreria standard. Codice di uscita: 0 se tutti i controlli base sono OK, 1 altrimenti.
"""
import argparse
import ipaddress
import json
import os
import re
import sys
import tempfile
import zipfile

OK, KO, INFO = "[OK]  ", "[KO]  ", "[INFO]"


# -------------------------
# Lettura lab
# -------------------------
def read_text(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except OSError:
        return None


def parse_lab_conf(text):
    """Ritorna (interfacce, immagini): {nodo: {idx: lan}}, {nodo: immagine}."""
    ifaces, images = {}, {}
    p = re.compile(r'^\s*([^\[\s#]+)\s*\[\s*([^\]]+?)\s*\]\s*=\s*"?([^"#\s]*)"?')
    for line in (text or '').splitlines():
        m = p.match(line)
        if not m:
            continue
        node, key, val = m.groups()
        if key == 'image':
            images[node] = val
        elif key.isdigit():
            ifaces.setdefault(node, {})[int(key)] = val
    return ifaces, images


def parse_startup(text):
    """Ritorna (ip per interfaccia {ethN: ip/cidr}, servizi avviati, rotte)."""
    ips, services, routes = {}, set(), []
    for line in (text or '').splitlines():
        s = line.strip()
        m = re.match(r'(?:ip\s+a(?:ddr(?:ess)?)?\s+add|ifconfig)\s+', s)
        if m:
            toks = s.split()
            if toks[0] == 'ifconfig' and len(toks) >= 3:
                ips.setdefault(toks[1], toks[2])
            elif 'dev' in toks:
                ip = toks[3] if len(toks) > 3 else ''
                dev = toks[toks.index('dev') + 1] if toks.index('dev') + 1 < len(toks) else ''
                ips.setdefault(dev, ip)
            continue
        m = re.match(r'(?:systemctl\s+start|/etc/init\.d/(\S+)\s+start|service\s+(\S+)\s+start)\s*(\S*)', s)
        if m:
            services.add((m.group(1) or m.group(2) or m.group(3)).strip())
            continue
        if s.startswith('ip route add') or s.startswith('route add'):
            routes.append(' '.join(s.split()))
    return ips, services, routes


def parse_daemons(text):
    d = {}
    for line in (text or '').splitlines():
        m = re.match(r'^\s*(\w+)\s*=\s*(yes|no)\b', line)
        if m:
            d[m.group(1)] = m.group(2) == 'yes'
    return d


POLICY_START = re.compile(r'^(ip\s+prefix-list|route-map|access-list|ip\s+access-list|bgp\s+community-list|ip\s+as-path)\b')


def norm_net(s):
    try:
        return str(ipaddress.ip_network(s, strict=False))
    except ValueError:
        return s


def parse_frr(text):
    """Estrae i dati rilevanti da frr.conf, indipendentemente dall'indentazione."""
    cfg = {
        'asn': None, 'neighbors': {}, 'bgp_networks': set(), 'bgp_redistribute': set(),
        'rip_networks': set(), 'rip_redistribute': set(),
        'ospf_networks': set(), 'ospf_stub': set(), 'ospf_redistribute': set(),
        'ospf_cost': set(), 'policy': [], 'has_bgp': False, 'has_rip': False, 'has_ospf': False,
    }
    block = None        # 'bgp' | 'rip' | 'ospf' | 'interface:<n>' | 'policy' | None
    for raw in (text or '').splitlines():
        s = ' '.join(raw.split())
        if not s or s.startswith('!'):
            continue
        m = re.match(r'^router bgp (\d+)', s)
        if m:
            block, cfg['asn'], cfg['has_bgp'] = 'bgp', m.group(1), True
            continue
        if s.startswith('router rip'):
            block, cfg['has_rip'] = 'rip', True
            continue
        if s.startswith('router ospf'):
            block, cfg['has_ospf'] = 'ospf', True
            continue
        m = re.match(r'^interface (\S+)', s)
        if m:
            block = 'interface:' + m.group(1)
            continue
        if POLICY_START.match(s):
            cfg['policy'].append(s)
            block = 'policy' if s.startswith('route-map') else block
            continue
        if block == 'policy' and re.match(r'^(set|match|on-match|call|continue)\b', s):
            cfg['policy'].append('    ' + s)
            continue
        if block and block.startswith('interface:') and s.startswith('ospf cost'):
            cfg['ospf_cost'].add(f"{block.split(':', 1)[1]} {s}")
            continue
        m = re.match(r'^neighbor (\S+) (.*)$', s)
        if m:
            ip, rest = m.groups()
            if rest.startswith('remote-as'):
                cfg['neighbors'][ip] = rest.split()[1]
            elif re.match(r'(prefix-list|route-map|filter-list|distribute-list)\b', rest):
                cfg['policy'].append(s)
            elif rest.startswith('update-source'):
                cfg['neighbors'].setdefault(ip + ' (update-source)', rest.split()[1])
            continue
        if s.startswith('network '):
            parts = s.split()
            if block == 'bgp':
                cfg['bgp_networks'].add(norm_net(parts[1]))
            elif block == 'rip':
                cfg['rip_networks'].add(norm_net(parts[1]))
            elif block == 'ospf':
                area = parts[3] if len(parts) >= 4 and parts[2] == 'area' else '?'
                cfg['ospf_networks'].add(f"{norm_net(parts[1])} area {area}")
            continue
        m = re.match(r'^area (\S+) stub', s)
        if m and block == 'ospf':
            cfg['ospf_stub'].add(m.group(1))
            continue
        if s.startswith('redistribute '):
            key = {'bgp': 'bgp_redistribute', 'rip': 'rip_redistribute', 'ospf': 'ospf_redistribute'}.get(block)
            if key:
                cfg[key].add(s)
            continue
    return cfg


def load_lab(path):
    """Carica un lab da cartella. Ritorna dict con topologia e nodi."""
    conf_text = read_text(os.path.join(path, 'lab.conf'))
    ifaces, images = parse_lab_conf(conf_text)
    nodes = {}
    names = set(ifaces) | set(images)
    for fn in os.listdir(path):
        if fn.endswith('.startup'):
            names.add(fn[:-len('.startup')])
    for n in names:
        ips, services, routes = parse_startup(read_text(os.path.join(path, f'{n}.startup')))
        frr_dir = os.path.join(path, n, 'etc', 'frr')
        frr_text = read_text(os.path.join(frr_dir, 'frr.conf'))
        nodes[n] = {
            'dir': os.path.join(path, n),
            'ips': ips, 'services': services, 'routes': routes,
            'daemons': parse_daemons(read_text(os.path.join(frr_dir, 'daemons'))),
            'frr': parse_frr(frr_text) if frr_text is not None else None,
            'files': sorted(os.path.relpath(os.path.join(r, f), os.path.join(path, n)).replace('\\', '/')
                            for r, _, fs in os.walk(os.path.join(path, n)) for f in fs)
            if os.path.isdir(os.path.join(path, n)) else [],
        }
    return {'ifaces': ifaces, 'images': images, 'nodes': nodes, 'has_conf': conf_text is not None}


def find_solution(ex_dir):
    sol = os.path.join(ex_dir, 'solution', 'lab')
    if os.path.isfile(os.path.join(sol, 'lab.conf')):
        return sol, None
    z = os.path.join(ex_dir, 'solution', 'lab.zip')
    if os.path.isfile(z):
        tmp = tempfile.TemporaryDirectory()
        with zipfile.ZipFile(z) as zf:
            zf.extractall(tmp.name)
        for root, _, files in os.walk(tmp.name):
            if 'lab.conf' in files:
                return root, tmp
    return None, None


def load_correction(ex_dir):
    p = os.path.join(ex_dir, 'autocorrection', 'correction.json')
    txt = read_text(p)
    if not txt or not txt.strip():
        return None
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        return None


# -------------------------
# Report
# -------------------------
class Report:
    def __init__(self):
        self.fail = 0
        self.ok = 0
        self.info = 0

    def section(self, title):
        print(f"\n=== {title} ===")

    def check(self, cond, msg, detail=None):
        if cond:
            self.ok += 1
            print(f"{OK} {msg}")
        else:
            self.fail += 1
            print(f"{KO} {msg}")
            if detail:
                for d in detail:
                    print(f"         {d}")

    def note(self, msg, detail=None):
        self.info += 1
        print(f"{INFO} {msg}")
        for d in detail or []:
            print(f"         {d}")


def diff_sets(gen, exp, label_gen='in più nel generato', label_exp='mancano nel generato'):
    out = []
    miss = sorted(set(exp) - set(gen))
    extra = sorted(set(gen) - set(exp))
    if miss:
        out.append(f"{label_exp}: {', '.join(miss)}")
    if extra:
        out.append(f"{label_gen}: {', '.join(extra)}")
    return out


def igp_coverage(ips, networks):
    """Insieme di 'ethX[ area A]' coperti dalle network IGP (RIP: senza area)."""
    nets = []
    for entry in networks:
        parts = entry.split()
        try:
            nets.append((ipaddress.ip_network(parts[0].rstrip('.').replace('./', '/'), strict=False),
                         parts[2] if len(parts) >= 3 else ''))
        except ValueError:
            continue
    out = set()
    for dev, ip in ips.items():
        try:
            addr = ipaddress.ip_interface(ip).ip
        except ValueError:
            continue
        for net, area in nets:
            if addr in net:
                out.add(f"{dev} ({ip}){' area ' + area if area else ''}")
                break
    return out


def collision_domains(ifaces):
    doms = {}
    for node, m in ifaces.items():
        for idx, lan in m.items():
            doms.setdefault(lan, set()).add(f"{node}[{idx}]")
    return {frozenset(v): k for k, v in doms.items()}


def allinea_nomi(gen, sol):
    """Nodi con nome diverso ma stessi IP (es. 'ns-com' nella figura, 'com' nella
    soluzione): rinomina i nodi del lab generato con il nome della soluzione."""
    def firma(lab, n):
        return frozenset(ip.split('/')[0] for ip in lab['nodes'][n]['ips'].values())
    sol_solo = [n for n in sol['nodes'] if n not in gen['nodes']]
    alias = {}
    for g in [n for n in gen['nodes'] if n not in sol['nodes']]:
        fg = firma(gen, g)
        cand = [s for s in sol_solo if fg and firma(sol, s) == fg and s not in alias.values()]
        if len(cand) == 1:
            alias[g] = cand[0]
    for old, new in alias.items():
        for key in ('nodes', 'ifaces', 'images'):
            if old in gen[key]:
                gen[key][new] = gen[key].pop(old)
    return alias


def _bind_zone_files(node_dir):
    """basename del file di zona -> nome della zona, da etc/bind/named.conf."""
    testo = read_text(os.path.join(node_dir, 'etc', 'bind', 'named.conf')) or ''
    out = {}
    for zona, corpo in re.findall(r'zone\s+"([^"]+)"\s*\{(.*?)\};', testo, re.S):
        m = re.search(r'file\s+"([^"]+)"', corpo)
        if m:
            out[os.path.basename(m.group(1))] = '' if zona == '.' else zona.strip('.').lower()
    return out


def _zone_conf(node_dir):
    testo = read_text(os.path.join(node_dir, 'etc', 'bind', 'named.conf')) or ''
    return {(z.strip('.') or '.', (re.search(r'type\s+(\w+)', c) or [None, '?'])[1])
            for z, c in re.findall(r'zone\s+"([^"]+)"\s*\{(.*?)\};', testo, re.S)}


def record_dns(path, origine):
    """Record di un file di zona come insieme di (nome, tipo, valore) normalizzati
    (nomi assoluti in minuscolo senza punto finale; '@' = origine; SOA ignorato)."""
    def assoluto(nome):
        nome = nome.strip().lower()
        if nome == '@':
            return origine or '.'
        if nome.endswith('.'):
            return nome.rstrip('.') or '.'
        return f"{nome}.{origine}" if origine else nome
    out, in_soa, ultimo = set(), False, origine or '.'
    for raw in (read_text(path) or '').splitlines():
        riga = raw.split(';')[0]
        s = riga.strip()
        if not s or s.startswith('$'):
            continue
        if in_soa:
            in_soa = ')' not in s
            continue
        t = s.split()
        if 'SOA' in [x.upper() for x in t]:
            in_soa = '(' in s and ')' not in s
            continue
        nome = ultimo if riga[:1].isspace() else assoluto(t.pop(0))
        ultimo = nome
        t = [x for x in t if x.upper() != 'IN' and not x.isdigit()]
        if len(t) < 2:
            continue
        tipo, valore = t[0].upper(), ' '.join(t[1:])
        if tipo in ('NS', 'CNAME', 'PTR'):
            valore = assoluto(valore)
        out.add(f"{nome} {tipo} {valore}")
    return out


def compare(gen, sol, corr, rep, show_policy):
    test = (corr or {}).get('test', {})
    default_image = (corr or {}).get('default_image', 'kathara/base')

    alias = allinea_nomi(gen, sol)
    if alias:
        rep.note('nodi con nome diverso dalla soluzione, abbinati per IP',
                 [', '.join(f"{a} = {b}" for a, b in sorted(alias.items()))])

    # ---- Topologia
    rep.section('Topologia (lab.conf)')
    rep.check(gen['has_conf'], 'lab.conf presente')
    gnodes, snodes = set(gen['ifaces']), set(sol['ifaces'])
    rep.check(gnodes == snodes, f"nodi ({len(snodes)} attesi)", diff_sets(gnodes, snodes))
    gd, sd = collision_domains(gen['ifaces']), collision_domains(sol['ifaces'])
    bad = []
    for members, lan in sd.items():
        if members not in gd:
            bad.append(f"dominio {lan} atteso {{{', '.join(sorted(members))}}} non trovato uguale")
    for members, lan in gd.items():
        if members not in sd:
            bad.append(f"dominio {lan} generato {{{', '.join(sorted(members))}}} non presente nella soluzione")
    rep.check(not bad, f"domini di collisione ({len(sd)} attesi, confronto per interfacce)", bad)
    renamed = [f"{sd[m]} -> {gd[m]}" for m in sd if m in gd and sd[m] != gd[m]]
    if renamed:
        rep.note('LAN con nome diverso (va bene, conta il collegamento)', [', '.join(renamed)])
    # Le soluzioni spesso omettono [image] e si affidano all'immagine di default
    # (default_image di correction.json, di solito kathara/frr). Si confronta
    # l'immagine effettiva; per i nodi non-router senza immagine esplicita nella
    # soluzione va bene qualsiasi immagine (kathara/base ha apache2 e named).
    bad, loose = [], []
    for n in sorted(snodes & gnodes):
        exp = sol['images'].get(n) or default_image
        got = gen['images'].get(n) or default_image
        is_router = bool(sol['nodes'].get(n, {}).get('frr'))
        if exp == got:
            continue
        if not is_router and n not in sol['images']:
            loose.append(f"{n}: {got}")
            continue
        bad.append(f"{n}: atteso {exp}, generato {got}")
    rep.check(not bad, f"immagini dei router (default soluzione: {default_image})", bad)
    if loose:
        rep.note('immagine dei nodi non-router non specificata nella soluzione', [', '.join(loose)])

    common = sorted(set(gen['nodes']) & set(sol['nodes']) & (gnodes | snodes))

    # ---- IP
    rep.section('Indirizzi IP')
    ip_map = test.get('ip_mapping') or {}
    bad = []
    for n in common:
        # attesi: IP della soluzione, aggiornati da ip_mapping (che a volte è
        # incompleto). Le chiavi di ip_mapping sono "0", "eth0" oppure "lo".
        exp = dict(sol['nodes'][n]['ips'])
        for k, v in (ip_map.get(n) or {}).items():
            k = str(k)
            exp[k if (k.startswith('eth') or not k.isdigit()) else f"eth{k}"] = v
        got = gen['nodes'][n]['ips']
        for dev in sorted(set(exp) | set(got)):
            e, g = exp.get(dev), got.get(dev)
            if e is None or g is None or ipaddress.ip_interface(e) != ipaddress.ip_interface(g):
                bad.append(f"{n} {dev}: atteso {e}, generato {g}")
    rep.check(not bad, 'IP di tutte le interfacce', bad)

    # ---- Demoni / servizi
    rep.section('Demoni e servizi')
    bad = []
    corr_daemons = test.get('daemons') or {}
    for n in common:
        gdm, gsrv = gen['nodes'][n]['daemons'], gen['nodes'][n]['services']
        if n in corr_daemons:
            for d in corr_daemons[n]:
                want = not d.startswith('!')
                name = d.lstrip('!')
                if name.endswith('d') and name in ('bgpd', 'ospfd', 'ripd', 'zebra', 'ospf6d', 'isisd', 'staticd'):
                    have = gdm.get(name, False)
                else:
                    have = name in gsrv
                if have != want:
                    bad.append(f"{n}: {name} {'deve' if want else 'NON deve'} essere attivo")
        else:
            sdm = sol['nodes'][n]['daemons']
            for name in ('bgpd', 'ospfd', 'ripd'):
                if sdm.get(name, False) != gdm.get(name, False):
                    bad.append(f"{n}: {name} atteso {sdm.get(name, False)}, generato {gdm.get(name, False)}")
            for srv in sol['nodes'][n]['services'] - gsrv:
                bad.append(f"{n}: servizio '{srv}' non avviato nello startup")
    rep.check(not bad, 'demoni FRR e servizi', bad)

    # ---- BGP
    rep.section('BGP')
    peerings = ((test.get('protocols') or {}).get('bgpd') or {}).get('peerings') or {}
    corr_nets = ((test.get('protocols') or {}).get('bgpd') or {}).get('networks') or {}
    # IP -> router che lo possiede: i neighbor si confrontano per router vicino,
    # perché un router (es. iBGP) può essere raggiunto da IP diversi
    owner = {}
    for lab in (sol, gen):
        for node, nd in lab['nodes'].items():
            for ip in nd['ips'].values():
                owner.setdefault(ip.split('/')[0], node)

    # Numeri AS diversi ma coerenti (es. figura AS100/200/300, soluzione 1/2/3):
    # se ogni ASN generato corrisponde sempre allo stesso ASN della soluzione, lo traduciamo
    asn_map, coerente = {}, True
    for n in common:
        sf, gf = sol['nodes'][n]['frr'], gen['nodes'][n]['frr']
        if sf and gf and sf['asn'] and gf['asn']:
            if asn_map.setdefault(gf['asn'], sf['asn']) != sf['asn']:
                coerente = False
    if not coerente or len(set(asn_map.values())) != len(asn_map):
        asn_map = {}
    if any(k != v for k, v in asn_map.items()):
        rep.note('numeri AS diversi dalla soluzione ma coerenti: confronto con la corrispondenza',
                 [', '.join(f"AS{k} -> AS{v}" for k, v in sorted(asn_map.items()) if k != v)])

    def tr(asn):
        return asn_map.get(asn, asn)

    def by_router(neigh, tradurre=False):
        return {f"{owner.get(ip, ip)} remote-as {tr(asn) if tradurre else asn}"
                for ip, asn in neigh.items() if '(' not in ip}

    for n in common:
        sf, gf = sol['nodes'][n]['frr'], gen['nodes'][n]['frr']
        if not sf or not sf['has_bgp']:
            if gf and gf['has_bgp']:
                rep.check(False, f"{n}: BGP configurato ma la soluzione non lo usa")
            continue
        if not gf or not gf['has_bgp']:
            rep.check(False, f"{n}: manca 'router bgp'")
            continue
        det = []
        if sf['asn'] != tr(gf['asn']):
            det.append(f"ASN atteso {sf['asn']}, generato {gf['asn']}")
        exp_n = {k: v for k, v in sf['neighbors'].items()}
        got_n = gf['neighbors']
        got_routers = {owner.get(ip, ip) for ip in got_n}
        if n in peerings:
            missing = [f"{ip} ({owner.get(ip, '?')})" for ip in peerings[n] if owner.get(ip, ip) not in got_routers]
            if missing:
                det.append(f"peering mancanti (correction.json): {', '.join(missing)}")
        det += [d.replace('mancano', 'neighbor mancanti').replace('in più', 'neighbor in più')
                for d in diff_sets(by_router(got_n, tradurre=True), by_router(exp_n))]
        rep.check(not det, f"{n}: router bgp {gf['asn']} - neighbor", det)
        if not det and set(got_n) != set(exp_n):
            rep.note(f"{n}: stessi vicini ma con IP diversi (es. iBGP verso un'altra interfaccia)",
                     diff_sets(set(got_n), set(exp_n)))
        det = diff_sets(gf['bgp_networks'], sf['bgp_networks'])
        if n in corr_nets:
            miss = [x for x in corr_nets[n] if norm_net(x) not in gf['bgp_networks']]
            if miss:
                det.append(f"network richieste da correction.json mancanti: {', '.join(miss)}")
        rep.check(not det, f"{n}: network annunciate ({len(sf['bgp_networks'])} attese)", det)
        if sf['bgp_redistribute'] != gf['bgp_redistribute']:
            rep.check(False, f"{n}: redistribute in BGP", diff_sets(gf['bgp_redistribute'], sf['bgp_redistribute']))

    # ---- IGP
    rep.section('IGP (RIP / OSPF)')
    any_igp = False
    for n in common:
        sf, gf = sol['nodes'][n]['frr'] or parse_frr(''), gen['nodes'][n]['frr'] or parse_frr('')
        for proto, keys in (('rip', ('rip_networks', 'rip_redistribute')),
                            ('ospf', ('ospf_networks', 'ospf_stub', 'ospf_redistribute', 'ospf_cost'))):
            if not sf[f'has_{proto}'] and not gf[f'has_{proto}']:
                continue
            any_igp = True
            if sf[f'has_{proto}'] != gf[f'has_{proto}']:
                rep.check(False, f"{n}: router {proto} {'mancante' if sf[f'has_{proto}'] else 'non previsto dalla soluzione'}")
                continue
            for k in keys:
                if not (sf[k] or gf[k]):
                    continue
                label = k.replace('_', ' ')
                if k in ('rip_networks', 'ospf_networks'):
                    # conta quali interfacce entrano nell'IGP (e in quale area), non come
                    # è scritta la rete: 20.0.0.0/8 e 20.20.0.0/16 possono essere equivalenti
                    ips = gen['nodes'][n]['ips'] or sol['nodes'][n]['ips']
                    cs, cg = igp_coverage(ips, sf[k]), igp_coverage(ips, gf[k])
                    rep.check(cs == cg, f"{n}: {label} (interfacce coperte)", diff_sets(cg, cs))
                    if cs == cg and sf[k] != gf[k]:
                        rep.note(f"{n}: {label} scritte diversamente ma equivalenti",
                                 [f"soluzione: {', '.join(sorted(sf[k]))}", f"generato : {', '.join(sorted(gf[k]))}"])
                elif k.endswith('_redistribute') and sf[k] <= gf[k] and gf[k] - sf[k] <= {'redistribute connected'}:
                    # 'redistribute connected' in più: le soluzioni lo mettono quasi sempre
                    # (39 router RIP+BGP su 42), non toglie raggiungibilità
                    rep.note(f"{n}: {label}: 'redistribute connected' in più rispetto alla soluzione (innocuo)")
                else:
                    rep.check(sf[k] == gf[k], f"{n}: {label}", diff_sets(gf[k], sf[k]))
    if not any_igp:
        print(f"{INFO} nessun IGP nel lab")

    # ---- Rotte statiche
    s_routes = {n: sol['nodes'][n]['routes'] for n in common if sol['nodes'][n]['routes']}
    g_routes = {n: gen['nodes'][n]['routes'] for n in common if gen['nodes'][n]['routes']}
    if s_routes or g_routes:
        rep.section('Rotte statiche / default negli startup')
        for n in sorted(set(s_routes) | set(g_routes)):
            rep.check(sorted(s_routes.get(n, [])) == sorted(g_routes.get(n, [])), n,
                      diff_sets(g_routes.get(n, []), s_routes.get(n, [])))

    # ---- File extra (DNS, www, resolv.conf, ...)
    rep.section('File dei nodi (oltre a etc/frr)')
    if not any(f for n in common for f in sol['nodes'][n]['files'] + gen['nodes'][n]['files']
               if not f.startswith('etc/frr/')):
        print(f"{INFO} nessun file extra (DNS, www, resolv.conf) nel lab")
    for n in common:
        sfiles = [f for f in sol['nodes'][n]['files'] if not f.startswith('etc/frr/')]
        gfiles = [f for f in gen['nodes'][n]['files'] if not f.startswith('etc/frr/')]
        if sfiles or gfiles:
            rep.check(set(sfiles) <= set(gfiles), f"{n}: {', '.join(sfiles) or '(nessuno)'}",
                      diff_sets(gfiles, sfiles))
        # DNS: contenuto di named.conf, named.conf.options e dei file di zona
        sdir, gdir = sol['nodes'][n]['dir'], gen['nodes'][n]['dir']
        if not os.path.isfile(os.path.join(sdir, 'etc', 'bind', 'named.conf')):
            continue
        zs, zg = _zone_conf(sdir), _zone_conf(gdir)
        rep.check(zs == zg, f"{n}: zone in named.conf ({', '.join(f'{z} {t}' for z, t in sorted(zs))})",
                  diff_sets({f'{z} {t}' for z, t in zg}, {f'{z} {t}' for z, t in zs}))
        fs, fg = _bind_zone_files(sdir), _bind_zone_files(gdir)
        zona_file_g = {z: f for f, z in fg.items()}
        for fname, zona in sorted(fs.items()):
            gname = zona_file_g.get(zona)
            rs = record_dns(os.path.join(sdir, 'etc', 'bind', fname), zona)
            rg = record_dns(os.path.join(gdir, 'etc', 'bind', gname), zona) if gname else set()
            rep.check(rs <= rg, f"{n}: record della zona '{zona or '.'}' ({len(rs)} attesi)",
                      [d for d in diff_sets(rg, rs) if d.startswith('mancano')])
            if rs <= rg and rg - rs:
                rep.note(f"{n}: record in più nella zona '{zona or '.'}'", [', '.join(sorted(rg - rs))])
        opt_s = ' '.join((read_text(os.path.join(sdir, 'etc', 'bind', 'named.conf.options')) or '').split())
        opt_g = ' '.join((read_text(os.path.join(gdir, 'etc', 'bind', 'named.conf.options')) or '').split())
        if 'dnssec-validation no' in opt_s:
            rep.check('dnssec-validation no' in opt_g, f"{n}: dnssec-validation no")
        rec_s = re.search(r'allow-recursion \{([^}]*)\}', opt_s)
        rec_g = re.search(r'allow-recursion \{([^}]*)\}', opt_g)
        if rec_s and not rec_g:
            rep.check(False, f"{n}: allow-recursion mancante (soluzione: {rec_s.group(1).strip()})")
        elif rec_s and rec_g and rec_s.group(1).split() != rec_g.group(1).split():
            rep.note(f"{n}: allow-recursion diverso (soluzione: {rec_s.group(1).strip()}, "
                     f"generato: {rec_g.group(1).strip()})")

    # ---- Policy (solo informativo)
    rep.section('Policy BGP (da fare a mano, solo INFO)')
    for n in common:
        sp = (sol['nodes'][n]['frr'] or {}).get('policy') or []
        gp = (gen['nodes'][n]['frr'] or {}).get('policy') or []
        if not sp and not gp:
            continue
        msg = f"{n}: soluzione {len(sp)} righe di policy, generato {len(gp)}"
        if show_policy:
            rep.note(msg, ['-- soluzione:'] + sp + ['-- generato:'] + (gp or ['(nessuna)']))
        else:
            rep.note(msg)

    if test.get('kernel_routes') or test.get('reachability'):
        print(f"\n{INFO} kernel_routes / reachability di correction.json richiedono il lab avviato "
              f"(kathara lstart + kathara-lab-checker): non verificati qui.")


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except Exception:
            pass
    ap = argparse.ArgumentParser(description='Confronta un lab generato con la soluzione di un esercizio.')
    ap.add_argument('lab', help='cartella del lab generato (contiene lab.conf)')
    ap.add_argument('esercizio', help='cartella dell\'esercizio (contiene solution/ e autocorrection/)')
    ap.add_argument('--policy', action='store_true', help='mostra le righe di policy di soluzione e generato')
    args = ap.parse_args()

    if not os.path.isfile(os.path.join(args.lab, 'lab.conf')):
        print(f"lab.conf non trovato in {args.lab}")
        return 2
    sol_path, tmp = find_solution(args.esercizio)
    if not sol_path:
        print(f"Soluzione non trovata in {args.esercizio}/solution")
        return 2
    corr = load_correction(args.esercizio)

    print(f"Lab generato : {os.path.abspath(args.lab)}")
    print(f"Soluzione    : {os.path.abspath(sol_path)}")
    print(f"correction.json: {'usato' if corr else 'assente o vuoto (confronto solo con la soluzione)'}")

    rep = Report()
    compare(load_lab(args.lab), load_lab(sol_path), corr, rep, args.policy)
    if tmp:
        tmp.cleanup()

    print(f"\nRisultato: {rep.ok} OK, {rep.fail} KO, {rep.info} INFO")
    return 0 if rep.fail == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
