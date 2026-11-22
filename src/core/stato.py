"""
src/core/stato.py
Lettore unico di un lab Kathará: legge ogni file una volta sola e restituisce il modello completo.

È l'unico punto del programma che apre i file di configurazione di un lab per ricavarne lo stato.
Terminale e GUI vedono così esattamente la stessa cosa. Ogni elemento del modello ricorda in quale
file e in quale riga si trova ("dove"); le righe che il lettore non riconosce finiscono in
"non_comprese", così le modifiche future possono lasciarle intatte.

Il modello conserva anche il testo dei file letti (chiave "testi"): i lettori di prima
(analyzer.leggi_dispositivi, gui/dati.leggi_lab, persistence.rebuild_lab_metadata_and_export)
ricavano da lì i loro risultati, con le loro regole, senza riaprire i file.
"""
import ipaddress
import os
import re

from .templates import _RE_APACHE, _RE_GW, _RE_IP_ADD

# ----------------------------------------------------------------------------- file

FILE_DISPOSITIVO = {
    # chiave -> percorso relativo alla cartella del dispositivo
    'frr_conf': ('etc', 'frr', 'frr.conf'),
    'daemons': ('etc', 'frr', 'daemons'),
    'vtysh_conf': ('etc', 'frr', 'vtysh.conf'),
    'resolv_conf': ('etc', 'resolv.conf'),
    'named_conf': ('etc', 'bind', 'named.conf'),
    'named_conf_local': ('etc', 'bind', 'named.conf.local'),
    'named_conf_options': ('etc', 'bind', 'named.conf.options'),
    'index_html': ('var', 'www', 'html', 'index.html'),
}


def _testo(path):
    """Contenuto di un file di testo (None se manca). Gli a capo sono sempre '\\n'."""
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except OSError:
        return None


def righe(testo):
    """Righe di un testo come le restituisce _leggi_righe (split su '\\n'); [] se il file manca."""
    return testo.split('\n') if testo is not None else []


# ----------------------------------------------------------------------------- lab.conf

def parse_lab_conf_for_nodes(lab_path):
    """Parse `lab.conf` per ricavare nodi, mapping interfacce->LAN e immagini."""
    nodes = {}
    conf_path = os.path.join(lab_path, 'lab.conf')
    if not os.path.exists(conf_path):
        return nodes, None
    lab_conf_text = None
    try:
        with open(conf_path, 'r', encoding='utf-8') as f:
            lab_conf_text = f.read()
    except Exception:
        return nodes, None

    lines = [L.strip() for L in lab_conf_text.splitlines() if L.strip() and not L.strip().startswith('#')]
    p = re.compile(r"^\s*(?P<name>[^\[\s]+)\s*\[\s*(?P<idx>[^\]]+)\s*\]\s*=\s*(?:\"(?P<qval>.*)\"|(?P<val>[^#]*))")
    for L in lines:
        m = p.match(L)
        if not m:
            continue
        name = m.group('name')
        idx = m.group('idx')
        val = m.group('qval') if m.group('qval') is not None else m.group('val')
        val = val.strip()
        node = nodes.setdefault(name, {'interfaces': {}, 'image': ''})
        if idx == 'image':
            node['image'] = val.strip('"')
        else:
            try:
                node['interfaces'][int(idx)] = val
            except Exception:
                node['interfaces'][idx] = val
    return nodes, lab_conf_text


# ----------------------------------------------------------------------------- startup

_RE_ROUTE = re.compile(r'\s*ip\s+route\s+add\s+(\S+)(?:\s+via\s+(\S+))?(?:\s+dev\s+(\S+))?\s*$')
_RE_SERVIZIO = re.compile(
    r'\s*(?:systemctl\s+start\s+(\S+)|/etc/init\.d/(\S+)\s+start|service\s+(\S+)\s+start)\s*$')


def analizza_startup(rel, testo):
    """Indirizzi, gateway, rotte statiche e servizi avviati di un file .startup."""
    out = {'file': rel, 'ip': [], 'gateway': None, 'statiche': [], 'servizi': [], 'non_comprese': []}
    for n, raw in enumerate(righe(testo), 1):
        s = raw.strip()
        if not s or s.startswith('#'):
            continue
        m = _RE_IP_ADD.match(raw)
        if m:
            out['ip'].append({'ip': m.group(1), 'dev': m.group(2), 'riga': n})
            continue
        m = _RE_GW.match(raw)
        if m:
            # come i lettori di prima: vale l'ultima riga di default
            dev = re.search(r'\bdev\s+(\S+)', raw)
            out['gateway'] = {'via': m.group(1) or m.group(2), 'dev': dev.group(1) if dev else None, 'riga': n}
            continue
        m = _RE_ROUTE.match(raw)
        if m and m.group(1) != 'default':
            out['statiche'].append({'rete': m.group(1), 'via': m.group(2), 'dev': m.group(3), 'riga': n})
            continue
        m = _RE_SERVIZIO.match(raw)
        if m:
            out['servizi'].append({'nome': m.group(1) or m.group(2) or m.group(3), 'riga': n})
            continue
        out['non_comprese'].append({'file': rel, 'riga': n, 'testo': s})
    return out


# ----------------------------------------------------------------------------- frr.conf

# righe note che il modello non descrive in dettaglio: non sono "non comprese"
_FRR_NOTE_GLOBALI = re.compile(
    r'(password|enable password|log|debug|hostname|service|line|end|exit|frr|agentx|'
    r'ip forwarding|ipv6 forwarding|bgp as-path|bgp community-list|ip community-list|'
    r'ipv6 prefix-list|vrf)\b')
_FRR_NOTE_BLOCCO = {
    'bgp': re.compile(r'(no )?(bgp|timers|maximum-paths|aggregate-address|distance|address-family|'
                      r'exit-address-family)\b'),
    'ospf': re.compile(r'(no )?(ospf router-id|router-id|passive-interface|timers|default-metric|'
                       r'distance|maximum-paths|log-adjacency-changes)\b'),
    'rip': re.compile(r'(no )?(version|timers|passive-interface|neighbor|default-metric|distance)\b'),
    'interface': re.compile(r'(no )?(description|ip address|link-detect|shutdown|ip ospf (?!cost)|'
                            r'ip rip|bandwidth)\b'),
    'route-map': re.compile(r'(on-match|call|description|continue)\b'),
}


def _nuovo_frr(rel):
    return {
        'file': rel,
        'bgp': None, 'ospf': None, 'rip': None,
        'interfacce': {},          # dev -> {'costo_ospf': N, 'riga'}
        'prefix_list': {},         # nome -> [{'azione', 'rete', 'resto', 'riga'}]
        'access_list': {},         # nome -> [{'azione', 'rete', 'riga'}]
        'route_map': {},           # nome -> [{'azione', 'seq', 'match', 'set', 'riga'}]
        'statiche': [],            # [{'rete', 'via', 'riga'}]  (ip route di FRR)
        'altre': [],               # righe note non descritte nel dettaglio
        'non_comprese': [],
    }


def _blocco_router(tipo, n, asn=None):
    b = {'riga': n, 'network': [], 'redistribute': [], 'default_information': []}
    if tipo == 'bgp':
        b.update({'asn': asn, 'neighbor': {}})
    elif tipo == 'ospf':
        b.update({'stub': [], 'auto_cost': None})
    else:
        b.update({'route': []})
    return b


def _neighbor(bgp, ip):
    return bgp['neighbor'].setdefault(ip, {
        'remote_as': None, 'descrizione': None, 'update_source': None,
        'default_originate': None, 'policy': [], 'righe': []})


def analizza_frr(rel, testo):
    """Modello strutturato di un frr.conf, con la riga di ogni elemento.

    Come il resto del programma (_analizza_frr, riferimenti_frr), il blocco corrente cambia
    solo alle righe 'router', 'interface' e 'route-map'; prefix-list, access-list e neighbor
    sono riconosciuti ovunque, indipendentemente dall'indentazione.
    """
    cfg = _nuovo_frr(rel)
    blocco, rm, iface = None, None, None

    def non_compresa(n, s):
        cfg['non_comprese'].append({'file': rel, 'riga': n, 'testo': s})

    for n, raw in enumerate(righe(testo), 1):
        s = ' '.join(raw.split())
        if not s or s.startswith('!') or s.startswith('#'):
            continue

        m = re.match(r'router (bgp|ospf|rip)\b ?(\d*)$', s)
        if m:
            tipo = m.group(1)
            blocco, rm, iface = tipo, None, None
            if tipo == 'bgp':
                cfg['bgp'] = cfg['bgp'] or _blocco_router('bgp', n, m.group(2))
                cfg['bgp']['asn'] = m.group(2)
            elif cfg[tipo] is None:
                cfg[tipo] = _blocco_router(tipo, n)
            continue
        m = re.match(r'interface (\S+)$', s)
        if m:
            blocco, rm, iface = 'interface', None, m.group(1)
            cfg['interfacce'].setdefault(iface, {'costo_ospf': None, 'riga': n})
            continue
        m = re.match(r'route-map (\S+) (permit|deny) (\d+)$', s)
        if m:
            blocco, iface = 'route-map', None
            rm = {'azione': m.group(2), 'seq': int(m.group(3)), 'match': [], 'set': [], 'riga': n}
            cfg['route_map'].setdefault(m.group(1), []).append(rm)
            continue

        # righe globali, valide in qualunque punto del file
        m = re.match(r'ip prefix-list (\S+) (?:seq \d+ )?(permit|deny) (\S+)(.*)$', s)
        if m:
            cfg['prefix_list'].setdefault(m.group(1), []).append(
                {'azione': m.group(2), 'rete': m.group(3), 'resto': m.group(4).strip(), 'riga': n})
            continue
        if re.match(r'ip prefix-list \S+ description ', s):
            cfg['altre'].append({'riga': n, 'testo': s})
            continue
        m = re.match(r'(?:ip )?access-list (\S+) (?:seq \d+ )?(permit|deny) (\S+)$', s)
        if m:
            cfg['access_list'].setdefault(m.group(1), []).append(
                {'azione': m.group(2), 'rete': m.group(3), 'riga': n})
            continue
        m = re.match(r'ip route (\S+) (\S+)$', s)
        if m:
            cfg['statiche'].append({'rete': m.group(1), 'via': m.group(2), 'riga': n})
            continue
        m = re.match(r'neighbor (\S+) (.+)$', s)
        if m and cfg['bgp'] is not None and blocco != 'rip':
            ip, t = m.group(1), m.group(2).split()
            nb = _neighbor(cfg['bgp'], ip)
            nb['righe'].append(n)
            if t[0] == 'remote-as' and len(t) >= 2:
                nb['remote_as'] = t[1]
            elif t[0] == 'description':
                nb['descrizione'] = ' '.join(t[1:])
            elif t[0] == 'update-source' and len(t) >= 2:
                nb['update_source'] = t[1]
            elif t[0] == 'default-originate':
                nb['default_originate'] = {
                    'route_map': t[2] if len(t) >= 3 and t[1] == 'route-map' else None, 'riga': n}
            elif t[0] in ('prefix-list', 'route-map', 'filter-list', 'distribute-list') and len(t) >= 3:
                nb['policy'].append({'tipo': t[0], 'nome': t[1], 'verso': t[2], 'riga': n})
            else:
                cfg['altre'].append({'riga': n, 'testo': s})
            continue

        if blocco == 'route-map' and rm is not None:
            m = re.match(r'(match|set) (.+)$', s)
            if m:
                rm[m.group(1)].append(m.group(2))
                continue
        if blocco == 'interface':
            m = re.match(r'(?:ip )?ospf cost (\d+)$', s)
            if m:
                cfg['interfacce'][iface].update({'costo_ospf': int(m.group(1)), 'riga_costo': n})
                continue
        if blocco in ('bgp', 'ospf', 'rip'):
            b = cfg[blocco]
            m = re.match(r'network (\S+)(?: area (\S+))?$', s)
            if m:
                voce = {'rete': m.group(1), 'riga': n}
                if blocco == 'ospf':
                    voce['area'] = m.group(2)
                b['network'].append(voce)
                continue
            m = re.match(r'redistribute (.+)$', s)
            if m:
                b['redistribute'].append({'testo': m.group(1), 'riga': n})
                continue
            if s.startswith('default-information originate') and blocco != 'bgp':
                b['default_information'].append({'testo': s, 'riga': n})
                continue
            if blocco == 'ospf':
                m = re.match(r'auto-cost reference-bandwidth (\d+)$', s)
                if m:
                    b['auto_cost'] = {'valore': int(m.group(1)), 'riga': n}
                    continue
                m = re.match(r'area (\S+) stub\b', s)
                if m:
                    b['stub'].append({'area': m.group(1), 'riga': n})
                    continue
            if blocco == 'rip':
                m = re.match(r'route (\S+)$', s)
                if m:
                    b['route'].append({'rete': m.group(1), 'riga': n})
                    continue

        if _FRR_NOTE_GLOBALI.match(s) or (blocco in _FRR_NOTE_BLOCCO and _FRR_NOTE_BLOCCO[blocco].match(s)):
            cfg['altre'].append({'riga': n, 'testo': s})
            continue
        non_compresa(n, s)
    return cfg


# ----------------------------------------------------------------------------- bind

_RE_ZONA = re.compile(r'zone\s+"([^"]+)"\s*(?:IN\s*)?\{(.*?)\}\s*;', re.S)
_TIPI_RECORD = ('A', 'NS', 'SOA', 'CNAME', 'MX', 'PTR', 'AAAA', 'TXT')


def _file_bind(nome, f):
    """Percorso relativo al lab di un file citato in named.conf."""
    if f.startswith('/'):
        return '/'.join([nome] + f.strip('/').split('/'))
    return '/'.join([nome, 'etc', 'bind'] + f.split('/'))


def _nome_assoluto(nome, origine):
    if nome == '@':
        return origine or '.'
    if nome.endswith('.'):
        return nome.rstrip('.').lower() or '.'
    return f"{nome}.{origine}".lower() if origine else nome.lower()


def record_dns_dettaglio(testo, zona):
    """Record di un file di zona: [{'nome' (assoluto), 'scritto', 'tipo', 'valore', 'riga'}].

    'scritto' è il nome com'è nel file ('@', 'www', 'dns.com.'); per le righe che continuano il
    nome precedente è quello della riga prima."""
    origine = '' if zona == '.' else zona.lower()
    out, ultimo, scritto, in_par = [], origine or '.', '@', False
    for n, raw in enumerate(righe(testo), 1):
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
        i = next((k for k, t in enumerate(tok) if t.upper() in _TIPI_RECORD), None)
        if i is None or i + 1 >= len(tok):
            continue
        if riga[:1].isspace() or i == 0 or tok[0].upper() == 'IN' or tok[0].isdigit():
            nome = ultimo
        else:
            nome, scritto = _nome_assoluto(tok[0], origine), tok[0]
        ultimo = nome
        out.append({'nome': nome, 'scritto': scritto, 'tipo': tok[i].upper(), 'valore': tok[i + 1], 'riga': n})
    return out


def record_dns(testo, zona):
    """[(nome, tipo, valore)] di un file di zona, con i nomi assoluti."""
    return [(r['nome'], r['tipo'], r['valore']) for r in record_dns_dettaglio(testo, zona)]


def zone_dichiarate(nome, testi):
    """[{'zona', 'tipo', 'file'}] da named.conf e named.conf.local ('file' relativo al lab)."""
    zone = []
    for chiave in ('named_conf', 'named_conf_local'):
        testo = '\n'.join(righe(testi.get(chiave)))
        for m in _RE_ZONA.finditer(testo):
            t = re.search(r'\btype\s+(\w+)', m.group(2))
            fl = re.search(r'\bfile\s+"([^"]+)"', m.group(2))
            zone.append({
                'zona': m.group(1).rstrip('.').lower() or '.',
                'tipo': t.group(1) if t else '?',
                'file': _file_bind(nome, fl.group(1)) if fl else None,
            })
    return zone


def _opzioni_bind(testo):
    t = testo or ''
    m = re.search(r'allow-recursion\s*\{([^}]*)\}', t)
    f = re.search(r'forwarders\s*\{([^}]*)\}', t)
    d = re.search(r'dnssec-validation\s+(\w+)', t)
    return {
        'allow_recursion': [x.strip() for x in m.group(1).split(';') if x.strip()] if m else None,
        'forwarders': [x.strip() for x in f.group(1).split(';') if x.strip()] if f else None,
        'dnssec_validation': d.group(1) if d else None,
    }


# ----------------------------------------------------------------------------- dispositivo

def tipo_dispositivo(d):
    """Tipo di un dispositivo (stessa regola di analyzer.leggi_dispositivi)."""
    testo = d['testi'].get('startup') or ''
    if d['presenti']['frr_conf'] or 'frr' in (d['immagine'] or ''):
        return 'router'
    if d['presenti']['named_conf'] or re.search(r'\bnamed\b', testo):
        return 'dns'
    if d['presenti']['dir_www'] or 'apache2' in testo:
        return 'www'
    return 'host'


def _leggi_dispositivo(lab_path, nome, meta):
    base = os.path.join(lab_path, nome)
    rel_startup = f"{nome}.startup"
    testi = {'startup': _testo(os.path.join(lab_path, rel_startup))}
    for chiave, parti in FILE_DISPOSITIVO.items():
        testi[chiave] = _testo(os.path.join(base, *parti))
    presenti = {k: testi[k] is not None for k in FILE_DISPOSITIVO}
    presenti.update({
        'startup': testi['startup'] is not None,
        'dir_bind': os.path.isdir(os.path.join(base, 'etc', 'bind')),
        'dir_www': os.path.isdir(os.path.join(base, 'var', 'www')),
    })

    d = {
        'nome': nome,
        'immagine': meta.get('image') or '',
        'lab_conf': dict(meta.get('interfaces', {})),   # come in lab.conf, anche chiavi non numeriche
        'testi': testi,
        'presenti': presenti,
    }
    d['tipo'] = tipo_dispositivo(d)

    st = analizza_startup(rel_startup, testi['startup'])
    d['startup'] = st
    ip_per_dev = {}
    for x in st['ip']:
        ip_per_dev.setdefault(x['dev'], []).append(x['ip'])
    d['ip_per_dev'] = ip_per_dev

    d['interfacce'] = [
        {'dev': f"eth{i}", 'idx': i, 'lan': lan, 'ip': (ip_per_dev.get(f"eth{i}") or [''])[0]}
        for i, lan in sorted((k, v) for k, v in d['lab_conf'].items() if isinstance(k, int))
    ]
    d['loopback'] = ip_per_dev.get('lo', [])
    d['altri_ip'] = [(dev, ip) for dev, lista in ip_per_dev.items() for ip in lista
                     if dev != 'lo' and not any(it['dev'] == dev for it in d['interfacce'])]
    d['gateway'] = st['gateway']['via'].split('/')[0] if st['gateway'] else None
    d['apache'] = bool(_RE_APACHE.search('\n'.join(righe(testi['startup']))))
    d['demoni'] = re.findall(r'^\s*(\w+d)\s*=\s*yes', testi['daemons'] or '', re.M)

    rel_frr = f"{nome}/etc/frr/frr.conf"
    d['frr'] = analizza_frr(rel_frr, testi['frr_conf']) if presenti['frr_conf'] else None
    d['asn'] = d['frr']['bgp']['asn'] if d['frr'] and d['frr']['bgp'] else None

    d['nameserver'] = re.findall(r'^\s*nameserver\s+(\S+)', testi['resolv_conf'] or '', re.M)

    d['dns'] = None
    if presenti['named_conf'] or presenti['named_conf_local']:
        zone = zone_dichiarate(nome, testi)
        for z in zone:
            zt = _testo(os.path.join(lab_path, *z['file'].split('/'))) if z['file'] else None
            testi['zona:' + z['zona']] = zt
            z['record'] = record_dns_dettaglio(zt, z['zona']) if zt is not None else []
        d['dns'] = dict(_opzioni_bind(testi['named_conf_options']), zone=zone)
        d['dns']['root'] = any(z['zona'] == '.' and z['tipo'] == 'master' for z in zone)

    d['non_comprese'] = st['non_comprese'] + (d['frr']['non_comprese'] if d['frr'] else [])
    return d


# ----------------------------------------------------------------------------- lab

def _lan(dispositivi):
    """LAN: membri (in ordine di dispositivo) e subnet dalla prima interfaccia con un IP."""
    lan = {}
    for d in dispositivi.values():
        for it in d['interfacce']:
            l = lan.setdefault(it['lan'], {'nome': it['lan'], 'subnet': '', 'membri': [], 'interfacce': []})
            l['membri'].append(d['nome'])
            l['interfacce'].append({'dispositivo': d['nome'], 'dev': it['dev'], 'ip': it['ip']})
            if it['ip'] and not l['subnet']:
                try:
                    l['subnet'] = str(ipaddress.ip_interface(it['ip']).network)
                except ValueError:
                    pass
    return lan


def _proprietari(dispositivi):
    """IP (senza maschera) -> dispositivo, loopback comprese."""
    owner = {}
    for d in dispositivi.values():
        for ip in [it['ip'] for it in d['interfacce'] if it['ip']] + d['loopback']:
            owner[ip.split('/')[0]] = d['nome']
    return owner


def _sessioni_bgp(dispositivi, owner):
    """Per ogni neighbor: dispositivo dall'altra parte e tipo di sessione (eBGP / iBGP)."""
    for d in dispositivi.values():
        bgp = d['frr'] and d['frr']['bgp']
        if not bgp:
            continue
        for ip, nb in bgp['neighbor'].items():
            nb['dispositivo'] = owner.get(ip)
            nb['tipo'] = None if nb['remote_as'] is None else ('iBGP' if nb['remote_as'] == bgp['asn'] else 'eBGP')


def leggi_stato(lab_path):
    """Modello completo di un lab letto dai suoi file."""
    nodi, lab_conf = parse_lab_conf_for_nodes(lab_path)
    dispositivi = {nome: _leggi_dispositivo(lab_path, nome, meta) for nome, meta in sorted(nodi.items())}
    owner = _proprietari(dispositivi)
    _sessioni_bgp(dispositivi, owner)
    nome_lab = os.path.basename(os.path.normpath(lab_path))
    return {
        'nome': nome_lab,
        'percorso': lab_path,
        'ordine_lab_conf': list(nodi),
        'lab_conf': lab_conf,
        'dispositivi': dispositivi,
        'lan': _lan(dispositivi),
        'proprietari': owner,
        'xml_nel_lab': os.path.exists(os.path.join(lab_path, nome_lab + '.xml')),
        'non_comprese': [x for d in dispositivi.values() for x in d['non_comprese']],
    }


def senza_testi(stato):
    """Copia del modello senza i testi dei file (per salvarlo o mandarlo alla GUI)."""
    out = dict(stato)
    out['dispositivi'] = {n: {k: v for k, v in d.items() if k != 'testi'} for n, d in stato['dispositivi'].items()}
    return out
