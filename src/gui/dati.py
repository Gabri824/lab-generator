"""Lettura di un lab Kathará dai suoi file (lab.conf, *.startup, frr.conf, bind).

Non modifica nulla: produce i dati che la pagina usa per disegnare la topologia,
il riepilogo e i controlli. Le funzioni di analisi di frr.conf e i controlli
sono quelli del generatore (`gen` = modulo labGenerator).
"""
import ipaddress
import os
import re

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


def _tipo(d, startup):
    p = d['presenti']
    if p['frr_conf'] or 'frr' in (d['immagine'] or ''):
        return 'router'
    if p['dir_bind'] or 'named' in startup:
        return 'dns'
    if p['dir_www'] or 'apache2' in startup:
        return 'www'
    return 'host'


def _zone_dns(d):
    """[(zona, tipo)] da named.conf (anche se include named.conf.local)."""
    zone = []
    for chiave in ('named_conf', 'named_conf_local'):
        testo = d['testi'].get(chiave) or ''
        for m in re.finditer(r'zone\s+"([^"]+)"\s*(?:IN\s*)?\{([^}]*)\}', testo, re.S):
            t = re.search(r'type\s+(\w+)', m.group(2))
            zone.append((m.group(1), t.group(1) if t else '?'))
    return zone


def leggi_lab(gen, lab_path, stato=None):
    """Dispositivi, LAN, riepilogo e controlli di un lab.

    I file vengono letti una volta sola dal lettore unico (core/stato.py)."""
    if stato is None:
        stato = gen.leggi_stato(lab_path)
    dispositivi = {}
    for nome, sd in stato['dispositivi'].items():
        startup = sd['testi'].get('startup') or ''
        cfg, riferimenti = None, []
        if sd['frr']:
            righe_frr = gen.righe_testo(sd["testi"]["frr_conf"])
            cfg = gen._analizza_frr(righe_frr)
            riferimenti = gen.riferimenti_frr(righe_frr)
        # solo le chiavi numeriche: le altre sono opzioni di lab.conf (es. r1[ipv6]=...)
        interfacce = [{'dev': it['dev'], 'lan': it['lan'], 'ip': it['ip']} for it in sd['interfacce']]
        asn = (cfg or {}).get('asn')
        if not asn:
            m = re.match(r'as(\d+)r', nome, re.I)
            asn = m.group(1) if m else None
        dispositivi[nome] = {
            'nome': nome,
            'immagine': sd['immagine'],
            'tipo': _tipo(sd, startup),
            'asn': asn,
            'interfacce': interfacce,
            'loopback': list(sd['loopback']),
            'gateway': sd['startup']['gateway']['via'] if sd['startup']['gateway'] else None,
            'demoni': [x for x in sd['demoni'] if x != 'zebra'],
            'nameserver': list(sd['nameserver']),
            'zone': _zone_dns(sd),
            'riferimenti_frr': riferimenti,
            '_cfg': cfg,
        }

    # LAN: membri e subnet
    lan = {}
    for d in dispositivi.values():
        for it in d['interfacce']:
            l = lan.setdefault(it['lan'], {'nome': it['lan'], 'subnet': '', 'membri': []})
            l['membri'].append(d['nome'])
            if it['ip'] and not l['subnet']:
                try:
                    l['subnet'] = str(ipaddress.ip_interface(it['ip']).network)
                except ValueError:
                    pass

    # router interni senza BGP e senza "asN" nel nome (es. r1..r7 di hour-glass): prendono
    # l'AS di un vicino sulla stessa LAN che usa lo stesso IGP, a catena
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

    # gruppo (AS) degli host: quello dell'unico AS dei router sulle loro LAN
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
        d['deleghe'] = _deleghe(stato['dispositivi'][d['nome']], owner)
    for d in dispositivi.values():
        _dettaglio_interfacce(d, dispositivi, lan, owner)
    for d in dispositivi.values():
        del d['_cfg']

    return {
        'nome': os.path.basename(os.path.normpath(lab_path)),
        'dispositivi': list(dispositivi.values()),
        'lan': sorted(lan.values(), key=lambda l: l['nome']),
        'avvisi_topologia': gen.controlla_topologia(lab_path, stato),
        'avvisi_config': gen.controlli_configurazione(lab_path, stato),
        'xml': os.path.exists(os.path.join(lab_path, os.path.basename(os.path.normpath(lab_path)) + '.xml')),
    }


def indirizzi(dispositivi):
    """IP (senza maschera) -> nome del dispositivo, loopback comprese."""
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
    """Configurazione in chiaro di un router (come la voce Riepilogo del menu Opzioni)."""
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
            policy.append({'direzione': direz, 'nome': nome, 'testo': cosa, 'breve': _breve(cfg, t, nome)})
        rel = next((m.group(1).lower() for t, nome, _ in cfg['link'].get(ip, [])
                    for m in [_RE_RELAZIONE.match(nome)] if t == 'prefix-list' and m), None)
        r['neighbor'].append({'ip': ip, 'chi': owner.get(ip) or cfg['descr'].get(ip, '?'), 'asn': asn,
                              'tipo': 'iBGP' if asn == cfg['asn'] else 'eBGP', 'policy': policy, 'relazione': rel})
    # segni sul disegno (fase 5.6): chi manda la default e chi ridistribuisce BGP nell'IGP
    r['default'] = ([f"BGP default-originate verso {owner.get(ip, ip)}" for ip in cfg['default_orig']]
                    + [f"{x}" for x in cfg['default_igp']]
                    + [f"RIP route {x}" for x in cfg['rip_route'] if x.startswith('0.0.0.0')]
                    + [f"BGP network {x}" for x in cfg['bgp_networks'] if x.startswith('0.0.0.0/0')])
    r['redistribute_bgp_igp'] = [g['protocollo'] for g in r['igp'] if any(x.split()[:1] == ['bgp'] for x in g['redistribute'])]
    return r


# relazione Customer-Provider-Peer dal nome della prefix-list (provider_X_out del programma,
# providerOut / peerIn delle soluzioni del corso), come operazioni.opzioni_policy_bgp
_RE_RELAZIONE = re.compile(r'^(provider|customer|peer)', re.I)


def _breve(cfg, tipo, nome):
    """Sigla della policy per il disegno: 'LP 150', 'MED 20', 'filtro', 'solo' (prefix-list che
    lascia passare solo alcune reti); '' se non cambia niente (es. permit any)."""
    tag = []
    if tipo == 'prefix-list':
        voci = cfg['prefix_lists'].get(nome, [])
        if any(a == 'deny' for a, _ in voci):
            tag.append('filtro')
        elif voci and not any(a == 'permit' and r == 'any' for a, r in voci):
            tag.append('solo')
    elif tipo == 'route-map':
        for e in cfg['route_maps'].get(nome, []):
            if e['azione'] == 'deny':
                tag.append('filtro')
            for st in e['set']:
                m = re.match(r'(local-preference|metric|as-path prepend)\s+(.+)', st)
                if m:
                    tag.append({'local-preference': 'LP', 'metric': 'MED', 'as-path prepend': 'prepend'}[m.group(1)]
                               + ' ' + m.group(2))
            for mt in e['match']:
                m = re.match(r'ip address (\S+)$', mt)
                if m and any(a == 'deny' for a, _ in cfg['access_lists'].get(m.group(1), [])):
                    tag.append('filtro')
    else:
        tag.append(tipo)
    return ' '.join(dict.fromkeys(tag))


def _deleghe(sd, owner):
    """Deleghe scritte nelle zone master di un server DNS: [{zona, ns, ip, server}]."""
    out = []
    for z in ((sd.get('dns') or {}).get('zone') or []):
        if z['tipo'] != 'master':
            continue
        nome_zona = z['zona'].rstrip('.') or '.'
        glue = {r['nome'].rstrip('.'): r['valore'] for r in z['record'] if r['tipo'] == 'A'}
        for r in z['record']:
            figlia = r['nome'].rstrip('.')
            if r['tipo'] != 'NS' or not figlia or figlia == nome_zona or figlia == '.':
                continue
            ns = r['valore'].rstrip('.')
            ip = glue.get(ns)
            out.append({'zona': figlia, 'da': nome_zona, 'ns': ns, 'ip': ip, 'server': owner.get(ip or '')})
    return out


def _rete(testo):
    try:
        return ipaddress.ip_network(testo.split()[0], strict=False)
    except (ValueError, IndexError):
        return None


def _dettaglio_interfacce(d, dispositivi, lan, owner):
    """Per la tabella delle interfacce aggiunge a ogni interfaccia: chi c'è dall'altra
    parte della LAN, IGP che la copre e costo OSPF, neighbor BGP raggiunti da lì con le
    loro policy, e gli avvisi (subnet diversa dal vicino, neighbor inesistente, ...)."""
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
    """Testo dei file di configurazione principali di un dispositivo."""
    rel = [f"{nome}.startup",
           os.path.join(nome, 'etc', 'frr', 'frr.conf'),
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
