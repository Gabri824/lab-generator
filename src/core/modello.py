"""
src/core/modello.py
Regole di un lab da creare, separate dalle domande del terminale.

Il "modello" di un lab ha la forma dei dati che il wizard costruisce e che stanno nell'XML:

    {'nome': 'rossimario',
     'routers': {'r1': {'protocols': [...], 'asn': '100', 'interfaces': [{'name', 'lan', 'ip'}],
                        'ospf_area', 'ospf_area_stub', 'igp_networks', 'igp_redistribute_bgp',
                        'static_routes': [{'network', 'via', 'dev'}], ...}},
     'hosts': [{'name', 'interfaces', 'gateway', 'gw_dev', ...},           # host
               {'name', 'ip', 'gateway', 'lan', 'dns': True, 'zones', 'root_type',
                'allow_recursion', 'dnssec_validation', 'delegations'}],     # server DNS
     'wwws': [{'name', 'ip', 'gateway', 'lan'}],
     'resolver': 'dns2' | None}

- Le funzioni `errore_*` controllano un singolo valore e restituiscono il messaggio d'errore (lo
  stesso che stampa il terminale, senza simboli) oppure None. Il terminale le usa a ogni
  domanda, la GUI mentre si scrive.
- `completa_lab` mette i valori proposti (quelli che il terminale usa premendo Invio).
- `valida_lab` controlla tutto il modello e restituisce i problemi, ognuno col suo campo:
  gli "errore" bloccano la creazione come nel wizard, gli "avviso" no.

Il modulo non importa nulla dal resto del core in cima al file (cli_io lo usa), quindi le
funzioni di rete di net_frr si caricano dentro le funzioni che le usano. Nessun messaggio
contiene emoji: possono non essere stampabili su alcuni terminali.
"""
import copy
import ipaddress
import re

# ----------------------------------------------------------------------------- regole semplici

PROTOCOLLI = ('bgp', 'ospf', 'rip', 'statico')
TIPI_RECORD = ('A', 'NS', 'CNAME', 'DELEGATION')


def nome_kathara_valido(nome):
    """Nomi dei dispositivi in lab.conf: solo minuscole, cifre e '_'."""
    return bool(re.fullmatch(r"[a-z0-9_]+", nome or ''))


def correggi_nome_kathara(nome):
    """Proposta di nome valido: minuscolo, caratteri vietati sostituiti da '_'."""
    return re.sub(r"[^a-z0-9_]", "_", (nome or '').strip().lower()) or 'dispositivo'


def asn_valido(s):
    return s.isdigit() and 1 <= int(s) <= 4294967295


def area_valida(s):
    """Area OSPF: un numero (0) o il formato x.x.x.x (0.0.0.0)."""
    if s.isdigit():
        return int(s) <= 4294967295
    try:
        ipaddress.IPv4Address(s)
        return True
    except ValueError:
        return False


def _completa_ottetti(tok):
    """Forma abbreviata di bind ('0/0', '10/8', '192.168/16') -> con tutti e quattro gli ottetti."""
    ip, _, pref = tok.partition('/')
    parti = ip.split('.')
    if 1 <= len(parti) < 4 and all(x.isdigit() for x in parti):
        ip = '.'.join(parti + ['0'] * (4 - len(parti)))
    return f"{ip}/{pref}"


def parse_reti(s):
    """'10.0.0.0/8, 20.1.0.0/16' -> ['10.0.0.0/8', '20.1.0.0/16']. Accetta anche la forma abbreviata
    di bind usata nelle soluzioni del corso ('allow-recursion { 0/0; }' = 0.0.0.0/0)."""
    out = []
    for tok in s.replace(',', ' ').split():
        if '/' not in tok:
            raise ValueError(f"manca la maschera in '{tok}' (es. 10.0.0.0/8)")
        n = str(ipaddress.ip_network(_completa_ottetti(tok), strict=False))
        if n not in out:
            out.append(n)
    return out


# ----------------------------------------------------------------------------- un valore alla volta

def errore_nome_lab(s):
    if re.fullmatch(r"[a-z0-9_-]+", s or ''):
        return None
    return ("Nome non valido. Usa solo lettere minuscole, numeri, '_' e '-' (es. bgp_es1). "
            "Niente spazi, accenti, '/' o '.'.")


def errore_nome_dispositivo(s):
    if nome_kathara_valido(s):
        return None
    return f"'{s}' non è valido per Kathará (solo lettere minuscole, cifre e _)."


def errore_nome_usato(s, usati):
    return f"Nome '{s}' già usato. Scegli un altro." if s in usati else None


def errore_lan(s):
    if (s or '').isalnum():
        return None
    return "Nome LAN non valido. Usa solo lettere e numeri (es. A o A1). Evita punti o indirizzi IP."


def errore_ip_cidr(s):
    s = (s or '').strip()
    if '/' not in s:
        return "Inserisci la maschera usando '/' alla fine (es. 192.168.1.1/24)"
    try:
        ipaddress.ip_interface(s)
        return None
    except ValueError:
        return "Formato non valido. Usa x.x.x.x/yy (es. 192.168.1.1/24)"


def errore_ip_usato(ip_cidr, usati):
    ip = ip_cidr.split('/')[0]
    return f"Errore: l'IP {ip} è già stato assegnato. Scegli un altro IP." if ip in usati else None


def errore_ip(s):
    """IP senza maschera obbligatoria (gateway, next-hop): accetta anche x.x.x.x/yy."""
    try:
        ipaddress.ip_address((s or '').strip().split('/')[0])
        return None
    except ValueError:
        return "IP non valido (es. 10.0.0.1)"


def errore_ipv4(s):
    """IP senza maschera, solo IPv4 scritto per intero (glue delle deleghe del root)."""
    try:
        ipaddress.ip_address((s or '').strip())
        return None
    except ValueError:
        return "IP non valido. Inserisci un IPv4 (es. 10.0.0.2)"


def errore_asn(s):
    return None if asn_valido((s or '').strip()) else "Numero AS non valido: solo cifre (es. 20)."


def errore_area(s):
    return None if area_valida((s or '').strip()) else \
        "Area OSPF non valida: un numero (es. 0) o x.x.x.x (es. 1.1.1.1)."


def errore_protocolli(s):
    """s: testo come lo si scrive ('bgp, ospf') oppure lista."""
    toks = s if isinstance(s, list) else [t for t in (s or '').strip().lower().replace(',', ' ').split() if t]
    if not toks:
        return "Inserisci almeno un protocollo (bgp/ospf/rip/statico)."
    if all(t in PROTOCOLLI for t in toks):
        return None
    return "Usa solo: bgp ospf rip statico"


def errore_reti(s):
    """Una o più reti con maschera, separate da virgola (testo o lista)."""
    try:
        parse_reti(s if isinstance(s, str) else ' '.join(s))
        return None
    except ValueError as e:
        return f"Rete non valida: {e}"


def errore_destinazione(s):
    """Destinazione di una rotta statica: una rete con maschera oppure 'default'."""
    s = (s or '').strip()
    if s.lower() == 'default':
        return None
    try:
        reti = parse_reti(s)
    except ValueError as e:
        return f"Rete non valida: {e}"
    return None if len(reti) == 1 else "Inserisci una sola rete."


def errore_gateway_host(gw, interfacce, nome):
    """Il gateway di un host deve stare nella subnet di una sua interfaccia."""
    from .net_frr import iface_for_nexthop
    if not gw or iface_for_nexthop(interfacce, gw):
        return None
    reti = ', '.join(str(ipaddress.ip_interface(it['ip']).network) for it in interfacce)
    return (f"{gw} non è in nessuna subnet di {nome} ({reti}): "
            f"il gateway è l'IP del router sulla stessa LAN dell'host.")


def errore_interfaccia(dev, nomi, nome):
    return None if dev in nomi else f"{nome} non ha l'interfaccia {dev} (ha: {', '.join(nomi)})."


def errore_allow_recursion(s):
    s = (s or '').strip()
    if not s or s.lower() == 'any':
        return None
    try:
        parse_reti(s.replace(';', ' '))
        return None
    except ValueError as e:
        return f"Rete non valida: {e}"


# ----------------------------------------------------------------------------- modello intero

def _interfacce(voce):
    """Interfacce di un dispositivo del modello (www e dns hanno solo ip e lan)."""
    if voce.get('interfaces'):
        return voce['interfaces']
    if voce.get('ip') or voce.get('lan'):
        return [{'name': 'eth0', 'ip': voce.get('ip', ''), 'lan': voce.get('lan', '')}]
    return []


def dispositivi(modello):
    """[(nome, tipo, dati)] nell'ordine del modello: router, host, www, dns."""
    out = [(n, 'router', r) for n, r in (modello.get('routers') or {}).items()]
    for h in modello.get('hosts') or []:
        out.append((h.get('name', ''), 'dns' if h.get('dns') else 'host', h))
    out += [(w.get('name', ''), 'www', w) for w in modello.get('wwws') or []]
    return out


def completa_lab(modello):
    """Copia del modello con i valori proposti dove mancano. Non cambia i valori già scritti."""
    from .net_frr import default_igp_networks, iface_for_nexthop
    m = copy.deepcopy(modello)
    m.setdefault('routers', {})
    m.setdefault('hosts', [])
    m.setdefault('wwws', [])
    m.setdefault('resolver', None)

    usati = set(m['routers']) | {x.get('name') for x in m['hosts'] + m['wwws'] if x.get('name')}

    def nome_libero(base, k):
        while f"{base}{k}" in usati:
            k += 1
        usati.add(f"{base}{k}")
        return f"{base}{k}"

    prima_area = None
    for nome, r in m['routers'].items():
        r.setdefault('protocols', [])
        r.setdefault('asn', '')
        for k, it in enumerate(r.setdefault('interfaces', [])):
            it.setdefault('name', f"eth{k}")
        protos = r['protocols']
        if 'ospf' in protos:
            if prima_area is None:
                r.setdefault('ospf_area', '0.0.0.0')
                r.setdefault('ospf_area_stub', False)
                prima_area = (r['ospf_area'], r['ospf_area_stub'])
            elif not r.get('ospf_area'):
                r['ospf_area'], r['ospf_area_stub'] = prima_area
            else:
                r.setdefault('ospf_area_stub', False)
        if ('ospf' in protos or 'rip' in protos) and not r.get('igp_networks'):
            r['igp_networks'] = default_igp_networks(
                nome, {'asn': r['asn'] if 'bgp' in protos else '', 'interfaces': r['interfaces']})
        for sr in r.get('static_routes') or []:
            if isinstance(sr, dict) and not sr.get('dev') and r['interfaces']:
                sr['dev'] = iface_for_nexthop(r['interfaces'], sr.get('via')) or r['interfaces'][0]['name']

    n_host = n_dns = 0
    for h in m['hosts']:
        if h.get('dns'):
            n_dns += 1
            if not h.get('name'):
                h['name'] = 'root' if n_dns == 1 and 'root' not in usati else nome_libero('dns', n_dns)
                usati.add(h['name'])
            if h['name'] == 'root':
                h.setdefault('root_type', 'master')
            h.setdefault('root_type', 'hint')
            h.setdefault('dnssec_validation', False)
            h.setdefault('allow_recursion', None)
            h.setdefault('zones', None)
            h.setdefault('delegations', [] if h['root_type'] == 'master' else None)
            continue
        n_host += 1
        if not h.get('name'):
            h['name'] = nome_libero('host', n_host)
        if not h.get('interfaces'):
            h['interfaces'] = _interfacce(h)
        for k, it in enumerate(h['interfaces']):
            it.setdefault('name', f"eth{k}")
        if h['interfaces']:
            h.setdefault('ip', h['interfaces'][0].get('ip', ''))
            h.setdefault('lan', h['interfaces'][0].get('lan', ''))
        h.setdefault('gateway', '')
        if h['gateway'] and not h.get('gw_dev') and h['interfaces']:
            h['gw_dev'] = iface_for_nexthop(h['interfaces'], h['gateway']) or h['interfaces'][0]['name']
    for k, w in enumerate(m['wwws'], 1):
        if not w.get('name'):
            w['name'] = nome_libero('www', k)
    return m


def _problema(campo, gravita, messaggio, dispositivi=None):
    p = {'campo': campo, 'gravita': gravita, 'messaggio': messaggio}
    if dispositivi:
        p['dispositivi'] = dispositivi
    return p


def _rete_di(ip):
    try:
        return ipaddress.ip_interface(ip).network
    except ValueError:
        return None


def _valida_record(nome, zona, chiave, rec, out):
    campo = f"{nome}.zones.{zona}.{chiave}"
    if isinstance(rec, str):
        e = errore_ip(rec)
        if e:
            out.append(_problema(campo, 'errore', e))
        return
    if not isinstance(rec, dict):
        out.append(_problema(campo, 'errore', 'Record non valido.'))
        return
    tipo = str(rec.get('type', 'A')).upper()
    if tipo not in TIPI_RECORD:
        out.append(_problema(campo, 'errore', f"Tipo di record non previsto: {tipo} (A, NS, CNAME, DELEGATION)."))
        return
    richiesti = {'A': ('ip',), 'NS': ('ns',), 'CNAME': ('target',), 'DELEGATION': ('ns',)}[tipo]
    for k in richiesti:
        if not rec.get(k):
            out.append(_problema(f"{campo}.{k}", 'errore', f"Manca '{k}' nel record {tipo}."))
    for k in ('ip', 'glue', 'ns_ip'):
        if rec.get(k):
            e = errore_ip(rec[k])
            if e:
                out.append(_problema(f"{campo}.{k}", 'errore', e))


def valida_lab(modello, parziale=False):
    """Problemi del modello: [{'campo', 'gravita': 'errore' | 'avviso', 'messaggio'}].

    parziale=True: il lab è ancora in costruzione (wizard), quindi niente avvisi che dipendono
    da dispositivi non ancora inseriti (per esempio il link /30 con un solo estremo)."""
    out = []
    if 'nome' in modello:
        e = errore_nome_lab(modello.get('nome'))
        if e:
            out.append(_problema('lab.nome', 'errore', e))

    tutti = dispositivi(modello)
    visti, ip_di = set(), {}
    for nome, tipo, d in tutti:
        e = errore_nome_dispositivo(nome)
        if e:
            out.append(_problema(f"{nome}.name", 'errore',
                                 f"{e} Proposta: {correggi_nome_kathara(nome)}"))
        elif nome in visti:
            out.append(_problema(f"{nome}.name", 'errore', errore_nome_usato(nome, visti)))
        visti.add(nome)

        ifs = _interfacce(d)
        if not ifs:
            out.append(_problema(f"{nome}.interfaces", 'errore', f"{nome} non ha interfacce."))
        for k, it in enumerate(ifs):
            campo = f"{nome}.interfaces[{k}]"
            e = errore_lan(it.get('lan', ''))
            if e:
                out.append(_problema(f"{campo}.lan", 'errore', e))
            if not (it.get('ip') or '').strip():
                out.append(_problema(f"{campo}.ip", 'errore',
                                     f"{nome} {it.get('name') or f'eth{k}'}: manca l'IP (nello startup non c'è la riga 'ip address add')."))
                continue
            e = errore_ip_cidr(it.get('ip', ''))
            if e:
                out.append(_problema(f"{campo}.ip", 'errore', e))
                continue
            i = ipaddress.ip_interface(it['ip'])
            if str(i.ip) in ip_di:
                out.append(_problema(f"{campo}.ip", 'errore',
                                     errore_ip_usato(it['ip'], ip_di) + f" (lo usa {ip_di[str(i.ip)]})"))
            else:
                ip_di[str(i.ip)] = nome
            if i.network.prefixlen < 31 and i.ip in (i.network.network_address, i.network.broadcast_address):
                out.append(_problema(f"{campo}.ip", 'avviso',
                                     f"{i.ip} è l'indirizzo di rete o di broadcast di {i.network}."))

        if tipo == 'router':
            protos = d.get('protocols') or []
            e = errore_protocolli(protos)
            if e:
                out.append(_problema(f"{nome}.protocols", 'errore', e))
            if 'bgp' in protos:
                e = errore_asn(str(d.get('asn') or ''))
                if e:
                    out.append(_problema(f"{nome}.asn", 'errore', e))
            if 'ospf' in protos:
                area = str(d.get('ospf_area') or '')
                if area:
                    e = errore_area(area)
                    if e:
                        out.append(_problema(f"{nome}.ospf_area", 'errore', e))
                    elif area in ('0', '0.0.0.0') and d.get('ospf_area_stub') and not d.get('ospf_aree'):
                        out.append(_problema(f"{nome}.ospf_area_stub", 'avviso',
                                             "La backbone (area 0.0.0.0) non può essere stub."))
                for rete, a in (d.get('ospf_aree') or {}).items():
                    e = errore_area(str(a)) or errore_reti(rete)
                    if e:
                        out.append(_problema(f"{nome}.ospf_aree.{rete}", 'errore', e))
                for a in d.get('ospf_aree_stub') or []:
                    if str(a) in ('0', '0.0.0.0'):
                        out.append(_problema(f"{nome}.ospf_aree_stub", 'avviso',
                                             "La backbone (area 0.0.0.0) non può essere stub."))
            if d.get('igp_networks'):
                e = errore_reti(d['igp_networks'])
                if e:
                    out.append(_problema(f"{nome}.igp_networks", 'errore', e))
            nomi_if = [it.get('name') for it in ifs]
            for k, sr in enumerate(d.get('static_routes') or []):
                if not isinstance(sr, dict):
                    continue
                campo = f"{nome}.static_routes[{k}]"
                e = errore_destinazione(sr.get('network', ''))
                if e:
                    out.append(_problema(f"{campo}.network", 'errore', e))
                e = errore_ip(sr.get('via', ''))
                if e:
                    out.append(_problema(f"{campo}.via", 'errore', e))
                if sr.get('dev') and sr['dev'] not in nomi_if:
                    out.append(_problema(f"{campo}.dev", 'avviso', errore_interfaccia(sr['dev'], nomi_if, nome)))
            continue

        # host, www, dns
        gw = d.get('gateway') or ''
        if tipo != 'host' and not gw:
            out.append(_problema(f"{nome}.gateway", 'errore', f"Manca il gateway di {nome}."))
        if gw:
            e = errore_ip(gw)
            if e:
                out.append(_problema(f"{nome}.gateway", 'errore', e))
            elif ifs and all(_rete_di(it.get('ip', '')) for it in ifs):
                e = errore_gateway_host(gw.split('/')[0], ifs, nome)
                if e:
                    out.append(_problema(f"{nome}.gateway", 'errore' if tipo == 'host' else 'avviso', e))
        if tipo == 'host' and gw and d.get('gw_dev'):
            nomi_if = [it.get('name') for it in ifs]
            e = errore_interfaccia(d['gw_dev'], nomi_if, nome)
            if e:
                out.append(_problema(f"{nome}.gw_dev", 'errore', e))
        if tipo == 'dns':
            for zona, recs in (d.get('zones') or {}).items():
                if not zona:
                    out.append(_problema(f"{nome}.zones", 'errore', 'Zona senza nome.'))
                for chiave, rec in (recs or {}).items():
                    _valida_record(nome, zona, chiave, rec, out)
            e = errore_allow_recursion(d.get('allow_recursion') or '')
            if e:
                out.append(_problema(f"{nome}.allow_recursion", 'errore', e))
            for k, dl in enumerate(d.get('delegations') or []):
                campo = f"{nome}.delegations[{k}]"
                if not dl.get('zone'):
                    out.append(_problema(f"{campo}.zone", 'errore', 'Delega senza zona.'))
                if dl.get('ip'):
                    e = errore_ipv4(dl['ip'])
                    if e:
                        out.append(_problema(f"{campo}.ip", 'errore', e))

    for n, t, d in tutti:
        if t == 'router' or not isinstance(d, dict) or not d.get('nameserver'):
            continue
        ns = d['nameserver']
        if not isinstance(ns, list):
            out.append(_problema(f"{n}.nameserver", 'errore', 'Il resolver del dispositivo è un elenco di IP.'))
            continue
        for ip in ns:
            e = errore_ipv4(str(ip))
            if e:
                out.append(_problema(f"{n}.nameserver", 'errore', f"Resolver di {n}: {e}"))

    res = modello.get('resolver')
    if res and res not in {n for n, t, _ in tutti if t == 'dns'}:
        out.append(_problema('lab.resolver', 'errore', f"Il resolver {res} non è un server DNS del lab."))

    out += _avvisi_topologia(modello, tutti, ip_di, parziale)
    return out


def _avvisi_topologia(modello, tutti, ip_di, parziale):
    """Controlli tra dispositivi: subnet della LAN, link /30, gateway, aree OSPF."""
    out = []
    lan = {}
    for nome, tipo, d in tutti:
        for it in _interfacce(d):
            if _rete_di(it.get('ip', '')) and it.get('lan'):
                lan.setdefault(it['lan'], []).append((nome, tipo, d, ipaddress.ip_interface(it['ip'])))
    for l, membri in sorted(lan.items()):
        reti = {str(x[3].network) for x in membri}
        if len(reti) > 1:
            out.append(_problema(f"lan.{l}", 'avviso',
                                 f"LAN {l}: i dispositivi sono in subnet diverse ("
                                 + ', '.join(f"{n} {i}" for n, _, _, i in membri) + ").",
                                 [x[0] for x in membri]))
        if not parziale and len(membri) == 1 and membri[0][3].network.prefixlen >= 30:
            n, _, _, i = membri[0]
            out.append(_problema(f"lan.{l}", 'avviso',
                                 f"LAN {l}: link /{i.network.prefixlen} di {n} ({i}) senza l'altro estremo.", [n]))

    for nome, tipo, d in tutti:
        gw = (d.get('gateway') or '').split('/')[0]
        if tipo != 'router' and gw and not errore_ip(gw) and gw not in ip_di:
            out.append(_problema(f"{nome}.gateway", 'avviso',
                                 f"{nome}: il gateway {gw} non è l'IP di nessun dispositivo del lab."))

    # aree OSPF: due router OSPF sulla stessa LAN devono metterla nella stessa area
    def area_di(d, ip):
        if 'ospf' not in (d.get('protocols') or []):
            return None
        aree = d.get('ospf_aree') or {}
        for n in d.get('igp_networks') or []:
            try:
                if ip in ipaddress.ip_network(n, strict=False):
                    return str(aree.get(n) or d.get('ospf_area') or '0.0.0.0')
            except ValueError:
                continue
        return None

    def backbone(a):
        return a in ('0', '0.0.0.0')

    # con più aree, ogni area diversa dalla 0 tocca la backbone tramite un router di confine
    aree_router = {}
    for nome, tipo, d in tutti:
        if tipo == 'router':
            aree_r = {area_di(d, ipaddress.ip_interface(it['ip']).ip) for it in _interfacce(d) if _rete_di(it.get('ip', ''))}
            aree_r.discard(None)
            if aree_r:
                aree_router[nome] = aree_r
    tutte_le_aree = set().union(*aree_router.values()) if aree_router else set()
    if len(tutte_le_aree) > 1:
        for a in sorted(x for x in tutte_le_aree if not backbone(x)):
            confine = [n for n, ar in aree_router.items() if a in ar and any(backbone(x) for x in ar)]
            if not confine:
                out.append(_problema(f"ospf.area.{a}", 'avviso',
                                     f"L'area OSPF {a} non tocca la backbone: serve un router di confine con una "
                                     f"rete in area 0.0.0.0 e una in area {a}.",
                                     sorted(n for n, ar in aree_router.items() if a in ar)))

    for l, membri in sorted(lan.items()):
        aree = [(n, area_di(d, i.ip)) for n, t, d, i in membri if t == 'router']
        aree = [(n, a) for n, a in aree if a is not None]
        if len({a for _, a in aree}) > 1:
            out.append(_problema(f"lan.{l}", 'avviso',
                                 f"LAN {l}: i router la mettono in aree OSPF diverse ("
                                 + ', '.join(f"{n} area {a}" for n, a in aree)
                                 + "): l'adiacenza OSPF non si forma.", [n for n, _ in aree]))
    return out


def problemi_di(problemi, nome):
    """Problemi che riguardano un dispositivo (campo che inizia col suo nome o LAN che lo coinvolge)."""
    return [p for p in problemi
            if p['campo'].split('.')[0] == nome or nome in p.get('dispositivi', [])]
