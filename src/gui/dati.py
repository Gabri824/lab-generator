"""Lettura di un lab Kathará dai suoi file (lab.conf, *.startup, frr.conf, bind).

Non modifica nulla: produce i dati che la pagina usa per disegnare la topologia,
il riepilogo, i controlli e i moduli interattivi di modifica/validazione.
"""
import ipaddress
import os
import re

RE_IP = re.compile(r'\s*ip\s+a(?:ddr(?:ess)?)?\s+add\s+(\S+)\s+dev\s+(\S+)')
RE_GW = re.compile(r'\s*(?:ip\s+route\s+add\s+default\s+via\s+(\S+)|route\s+add\s+default\s+gw\s+(\S+))')
RE_NOME = re.compile(r'^[A-Za-z0-9_.-]+$')


def nome_valido(nome):
    return bool(nome) and bool(RE_NOME.match(nome)) and nome not in ('.', '..')


def elenco_lab(base):
    """Cartelle con lab.conf dentro `base`."""
    try:
        return sorted(d for d in os.listdir(base)
                      if nome_valido(d) and os.path.isfile(os.path.join(base, d, 'lab.conf')))
    except OSError:
        return []


def _leggi(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except OSError:
        return None


def _tipo(lab_path, nome, immagine, startup):
    d = os.path.join(lab_path, nome)
    if os.path.exists(os.path.join(d, 'etc', 'frr', 'frr.conf')) or 'frr' in (immagine or ''):
        return 'router'
    if os.path.isdir(os.path.join(d, 'etc', 'bind')) or 'named' in startup:
        return 'dns'
    if os.path.isdir(os.path.join(d, 'var', 'www')) or 'apache2' in startup:
        return 'www'
    return 'host'


def _demoni(lab_path, nome):
    testo = _leggi(os.path.join(lab_path, nome, 'etc', 'frr', 'daemons')) or ''
    return [m.group(1) for m in re.finditer(r'^\s*(\w+d)\s*=\s*yes', testo, re.M) if m.group(1) != 'zebra']


def _zone_dns(lab_path, nome):
    zone = []
    bind = os.path.join(lab_path, nome, 'etc', 'bind')
    for f in ('named.conf', 'named.conf.local'):
        testo = _leggi(os.path.join(bind, f)) or ''
        for m in re.finditer(r'zone\s+"([^"]+)"\s*(?:IN\s*)?\{([^}]*)\}', testo, re.S):
            t = re.search(r'type\s+(\w+)', m.group(2))
            zone.append((m.group(1), t.group(1) if t else '?'))
    return zone


def _isole_ospf_info(gen, lab_path):
    out = []
    try:
        for et, rs, cfgs in gen.isole_ospf(lab_path):
            con = [r for r in rs if cfgs[r].get('auto_cost')]
            costi = [f"{r} {c}" for r in rs for c in cfgs[r].get('costi', [])]
            out.append({
                'etichetta': et,
                'router': rs,
                'auto_cost_tutti': len(con) == len(rs),
                'auto_cost_count': len(con),
                'costi': costi,
            })
    except Exception:
        pass
    return out


def leggi_lab(gen, lab_path):
    """Dispositivi, LAN, riepilogo, controlli, isole OSPF e backup di un lab."""
    nodi, _ = gen.parse_lab_conf_for_nodes(lab_path)
    dispositivi = {}
    for nome, meta in sorted(nodi.items()):
        startup = _leggi(os.path.join(lab_path, f"{nome}.startup")) or ''
        ips, gw = {}, None
        for riga in startup.splitlines():
            m = RE_IP.match(riga)
            if m:
                ips.setdefault(m.group(2), []).append(m.group(1))
            m = RE_GW.match(riga)
            if m:
                gw = m.group(1) or m.group(2)
        cfg, riferimenti = None, []
        frr = os.path.join(lab_path, nome, 'etc', 'frr', 'frr.conf')
        if os.path.exists(frr):
            righe_frr = gen._leggi_righe(frr)
            cfg = gen._analizza_frr(righe_frr)
            riferimenti = gen.riferimenti_frr(righe_frr)
        interfacce = []
        for idx, lan in sorted((k, v) for k, v in meta.get('interfaces', {}).items() if isinstance(k, int)):
            dev = f"eth{idx}"
            interfacce.append({'dev': dev, 'lan': lan, 'ip': (ips.get(dev) or [''])[0]})
        asn = (cfg or {}).get('asn')
        if not asn:
            m = re.match(r'as(\d+)r', nome, re.I)
            asn = m.group(1) if m else None
        resolv = _leggi(os.path.join(lab_path, nome, 'etc', 'resolv.conf')) or ''
        zone = _zone_dns(lab_path, nome)
        dispositivi[nome] = {
            'nome': nome,
            'nome_valido_kathara': gen.nome_kathara_valido(nome),
            'immagine': meta.get('image') or '',
            'tipo': _tipo(lab_path, nome, meta.get('image'), startup),
            'asn': asn,
            'interfacce': interfacce,
            'loopback': ips.get('lo', []),
            'gateway': gw,
            'demoni': _demoni(lab_path, nome),
            'nameserver': re.findall(r'^\s*nameserver\s+(\S+)', resolv, re.M),
            'zone': zone,
            'is_dns_root': any(z[0] == '.' and z[1] == 'master' for z in zone),
            'has_frr': os.path.exists(frr),
            'riferimenti_frr': riferimenti,
            '_cfg': cfg,
        }

    lan = {}
    for d in dispositivi.values():
        for it in d['interfacce']:
            l = lan.setdefault(it['lan'], {'nome': it['lan'], 'subnet': '', 'membri': [], 'avvisi': []})
            l['membri'].append(d['nome'])
            if it['ip'] and not l['subnet']:
                try:
                    l['subnet'] = str(ipaddress.ip_interface(it['ip']).network)
                except ValueError:
                    pass

    cambiato = True
    while cambiato:
        cambiato = False
        for d in dispositivi.values():
            if d['tipo'] != 'router' or d['asn']:
                continue
            igp = {'ospfd', 'ripd'} & set(d['demoni'])
            for it in d['interfacce']:
                vicini = [dispositivi[m] for m in lan[it['lan']]['membri'] if m != d['nome']]
                v = next((v for v in vicini if v['tipo'] == 'router' and v['asn'] and igp & set(v['demoni'])), None)
                if v:
                    d['asn'], cambiato = v['asn'], True
                    break

    for d in dispositivi.values():
        if d['tipo'] == 'router' or d['asn']:
            continue
        gruppi = {dispositivi[m]['asn'] for it in d['interfacce'] for m in lan[it['lan']]['membri']
                  if dispositivi[m]['tipo'] == 'router' and dispositivi[m]['asn']}
        if len(gruppi) == 1:
            d['gruppo'] = gruppi.pop()
    for d in dispositivi.values():
        d.setdefault('gruppo', d['asn'])

    owner = indirizzi(dispositivi)
    for d in dispositivi.values():
        d['riepilogo'] = _riepilogo(gen, d, owner)
    for d in dispositivi.values():
        _dettaglio_interfacce(d, dispositivi, lan, owner)

    avvisi_top = gen.controlla_topologia(lab_path)
    avvisi_cfg = gen.controlli_configurazione(lab_path)
    tutti_avvisi = avvisi_top + avvisi_cfg

    for d in dispositivi.values():
        prob = []
        grav = 'ok'
        for it in d['interfacce']:
            for a in it.get('avvisi', []):
                msg = f"{it['dev']} ({it['lan']}): {a}"
                if msg not in prob:
                    prob.append(msg)
                grav = 'errore'
        for x in d.get('riferimenti_frr', []):
            msg = f"frr.conf riga {x['riga']}: {x['messaggio']}"
            prob.append(msg)
            if x.get('gravita') == 'errore':
                grav = 'errore'
            elif grav == 'ok':
                grav = 'avviso'
        for a in gen._problemi_di(d['nome'], tutti_avvisi):
            if a not in prob and not any(a in p for p in prob):
                prob.append(a)
                if grav == 'ok':
                    grav = 'avviso'
        if not d['nome_valido_kathara']:
            grav = 'errore'
        d['problemi'] = prob
        d['stato_val'] = grav
        del d['_cfg']

    for l in lan.values():
        for a in avvisi_top:
            if re.search(rf'\bLAN\s+{re.escape(l["nome"])}\b', a):
                l['avvisi'].append(a)
        for m in l['membri']:
            for it in dispositivi[m]['interfacce']:
                if it['lan'] == l['nome']:
                    for a in it.get('avvisi', []):
                        if 'subnet diversa' in a or 'senza l\'altro estremo' in a or 'senza IP' in a:
                            msg = f"{m} {it['dev']}: {a}"
                            if msg not in l['avvisi']:
                                l['avvisi'].append(msg)

    nomi_non_validi = [
        {'attuale': n, 'proposto': gen.correggi_nome_kathara(n)}
        for n in sorted(dispositivi)
        if not dispositivi[n]['nome_valido_kathara']
    ]

    return {
        'nome': os.path.basename(os.path.normpath(lab_path)),
        'dispositivi': list(dispositivi.values()),
        'lan': sorted(lan.values(), key=lambda l: l['nome']),
        'avvisi_topologia': avvisi_top,
        'avvisi_config': avvisi_cfg,
        'isole_ospf': _isole_ospf_info(gen, lab_path),
        'nomi_non_validi': nomi_non_validi,
        'backups': gen.ops_api.list_backups(lab_path) if hasattr(gen, 'ops_api') else [],
        'xml': os.path.exists(os.path.join(lab_path, os.path.basename(os.path.normpath(lab_path)) + '.xml')),
    }


def indirizzi(dispositivi):
    owner = {}
    for d in dispositivi.values():
        for ip in [it['ip'] for it in d['interfacce'] if it['ip']] + d['loopback']:
            owner[ip.split('/')[0]] = d['nome']
    return owner


def lan_di_ip(dispositivi, ip):
    for d in dispositivi.values():
        for it in d['interfacce']:
            if it['ip'] and it['ip'].split('/')[0] == ip:
                return it['lan']
    return None


def _riepilogo(gen, d, owner):
    cfg = d['_cfg']
    if not cfg:
        return None
    r = {'igp': [], 'costi': cfg['costi'], 'bgp_networks': cfg['bgp_networks'],
         'redistribute_bgp': cfg['redistribute'].get('bgp', []), 'neighbor': []}
    for igp in ('ospf', 'rip'):
        if igp in cfg['igp']:
            r['igp'].append({'protocollo': igp.upper(), 'voci': cfg['igp'][igp],
                             'redistribute': cfg['redistribute'].get(igp, []),
                             'auto_cost': cfg.get('auto_cost') if igp == 'ospf' else None})
    for ip, asn in cfg['neighbors'].items():
        policy = []
        for t, nome, direz in cfg['link'].get(ip, []):
            if t == 'prefix-list':
                cosa = (f"prefix-list {gen._descrivi_lista(cfg['prefix_lists'][nome])}"
                        if nome in cfg['prefix_lists'] else f"prefix-list {nome} (non definita!)")
            elif t == 'route-map':
                cosa = f"route-map {gen._descrivi_route_map(cfg, nome)}"
            else:
                cosa = f"{t} {nome}"
            policy.append({'direzione': direz, 'nome': nome, 'testo': cosa})
        r['neighbor'].append({'ip': ip, 'chi': owner.get(ip) or cfg['descr'].get(ip, '?'), 'asn': asn,
                              'tipo': 'iBGP' if asn == cfg['asn'] else 'eBGP', 'policy': policy,
                              'default_originate': ip in cfg.get('default_orig', {})})
    return r


def _rete(testo):
    try:
        return ipaddress.ip_network(testo.split()[0], strict=False)
    except (ValueError, IndexError):
        return None


def _dettaglio_interfacce(d, dispositivi, lan, owner):
    cfg = d['_cfg'] or {}
    reti_igp = [(p.upper(), _rete(v)) for p, voci in cfg.get('igp', {}).items()
                for v in voci if not v.startswith('area')]
    costi = dict(c.split() for c in cfg.get('costi', []) if len(c.split()) == 2)
    neigh = (d['riepilogo'] or {}).get('neighbor', [])
    for it in d['interfacce']:
        try:
            iface = ipaddress.ip_interface(it['ip']) if it['ip'] else None
        except ValueError:
            iface = None
        it['vicini'], it['bgp'], it['avvisi'] = [], [], []
        it['igp'] = sorted({p for p, r in reti_igp if r and iface and iface.ip in r})
        it['costo'] = costi.get(it['dev'])
        if iface is None:
            it['avvisi'].append('senza IP' if not it['ip'] else f"IP non valido: {it['ip']}")
        for m in lan[it['lan']]['membri']:
            if m == d['nome']:
                continue
            for x in dispositivi[m]['interfacce']:
                if x['lan'] != it['lan']:
                    continue
                it['vicini'].append({'nome': m, 'ip': x['ip']})
                try:
                    if iface and x['ip'] and ipaddress.ip_interface(x['ip']).network != iface.network:
                        it['avvisi'].append(f"subnet diversa da {m} ({x['ip']})")
                except ValueError:
                    pass
        if not it['vicini'] and iface and iface.network.prefixlen >= 30:
            it['avvisi'].append('link /30 senza l\'altro estremo')
        for n in neigh:
            try:
                if not (iface and ipaddress.ip_address(n['ip']) in iface.network):
                    continue
            except ValueError:
                continue
            it['bgp'].append(n)
            chi = owner.get(n['ip'])
            if chi is None:
                it['avvisi'].append(f"neighbor {n['ip']} non esiste nel lab")
            elif dispositivi[chi]['_cfg'] and dispositivi[chi]['_cfg'].get('asn') and \
                    dispositivi[chi]['_cfg']['asn'] != n['asn']:
                it['avvisi'].append(f"neighbor {n['ip']}: remote-as {n['asn']}, ma {chi} è AS{dispositivi[chi]['_cfg']['asn']}")


def file_dispositivo(lab_path, nome):
    rel = [f"{nome}.startup",
           os.path.join(nome, 'etc', 'frr', 'frr.conf'),
           os.path.join(nome, 'etc', 'frr', 'daemons'),
           os.path.join(nome, 'etc', 'resolv.conf'),
           os.path.join(nome, 'etc', 'bind', 'named.conf'),
           os.path.join(nome, 'etc', 'bind', 'named.conf.options')]
    bind = os.path.join(lab_path, nome, 'etc', 'bind')
    if os.path.isdir(bind):
        rel += [os.path.join(nome, 'etc', 'bind', f) for f in sorted(os.listdir(bind)) if f.startswith('db.')]
    out = []
    for r in rel:
        testo = _leggi(os.path.join(lab_path, r))
        if testo is not None:
            out.append({'file': r.replace(os.sep, '/'), 'testo': testo})
    return out
