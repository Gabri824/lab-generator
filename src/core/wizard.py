"""
src/core/wizard.py
Wizard interattivo a passi per la creazione di un nuovo laboratorio (router, host, www, DNS).
"""
import os

from .analyzer import stampa_controllo_topologia
from .cli_io import (
    chiedi_aree_ospf,
    esegui_passi,
    input,
    input_area,
    input_asn,
    input_destinazione,
    input_int,
    input_lan,
    input_non_vuoto,
    input_reti,
    parse_reti,
    print_menu,
    valida_gateway,
    valida_ip_cidr,
    valida_ip_senza_cidr,
    valida_protocols,
)
from .modello import (
    errore_allow_recursion,
    errore_gateway_host,
    errore_interfaccia,
    errore_ip_usato,
    problemi_di,
    valida_lab,
)
from .net_frr import (
    default_igp_networks,
    iface_for_nexthop,
)
from .persistence import _chiedi_nome
from .routing_ops import menu_post_creazione


def _chiedi_ip_libero(prompt, usati, altri):
    """IP/CIDR non ancora assegnato né nel lab (usati) né nel dispositivo corrente (altri)."""
    while True:
        ip = valida_ip_cidr(prompt)
        e = errore_ip_usato(ip, set(usati) | set(altri))
        if e:
            print(f"❌ {e}")
            continue
        return ip


def _ifaces_stato(st):
    """Interfacce del dispositivo in costruzione, solo quelle entro n_if."""
    return [
        {'name': f"eth{k}", 'lan': st['if'][k]['lan'], 'ip': st['if'][k]['ip']}
        for k in range(st.get('n_if', 0))
    ]


def _altri_ip(st, idx):
    return {
        v['ip'].split('/')[0] for k, v in st.get('if', {}).items()
        if k != idx and k < st.get('n_if', 0) and v.get('ip')
    }


def _passo_lan(idx, prompt):
    def f(st):
        st.setdefault('if', {}).setdefault(idx, {})['lan'] = input_lan(prompt)
    return f


def _passo_ip(idx, prompt, used_ips):
    def f(st):
        st.setdefault('if', {}).setdefault(idx, {})['ip'] = _chiedi_ip_libero(prompt, used_ips, _altri_ip(st, idx))
    return f


def _registra_ifaces(ctx, name, interfaces):
    for it in interfaces:
        ctx['used_ips'].add(it['ip'].split('/')[0])
    ctx['used_names'].add(name)


def _avvisi(ctx, tipo, nome, dati):
    """Righe 'Avviso: ...' per il riepilogo di un dispositivo: i controlli di modello.py sul lab
    costruito finora, compreso il dispositivo che si sta confermando. Non bloccano."""
    routers, hosts, wwws = dict(ctx['routers']), list(ctx['hosts']), list(ctx['wwws'])
    if tipo == 'router':
        routers[nome] = dati
    elif tipo == 'www':
        wwws.append(dati)
    else:
        hosts.append(dati)
    problemi = valida_lab({'routers': routers, 'hosts': hosts, 'wwws': wwws}, parziale=True)
    return [f"Avviso: {p['messaggio']}" for p in problemi_di(problemi, nome) if p['gravita'] == 'avviso']


def wizard_conteggi():
    def passo(chiave, prompt):
        def f(st):
            st[chiave] = input_int(prompt, 0)
        return f

    passi = [
        passo('n_router', "Numero di router: "),
        passo('n_host', "Numero di host/PC: "),
        passo('n_www', "Numero di server WWW: "),
        passo('n_dns', "Numero di host DNS: ")
    ]
    st = esegui_passi(
        "numero di dispositivi",
        lambda st: passi,
        lambda st: [
            f"router: {st['n_router']}   host: {st['n_host']}   "
            f"www: {st['n_www']}   dns: {st['n_dns']}"
        ]
    )
    return st['n_router'], st['n_host'], st['n_www'], st['n_dns']


def wizard_router(i, ctx):
    used_ips = ctx['used_ips']

    def p_nome(st):
        st['nome'] = _chiedi_nome('router', f"r{i}", ctx['used_names'])
        print(f"--- Configurazione router {st['nome']} ---")

    def p_proto(st):
        st['protocols'] = valida_protocols(
            f"Protocolli attivi su {st['nome']} (bgp/ospf/rip/statico, separati da virgola): "
        )

    def p_asn(st):
        st['asn'] = input_asn("Numero AS BGP: ")

    def p_area(st):
        first = ctx['first_ospf_area']
        if first is None:
            ans = input_non_vuoto(
                "Questo è il primo router OSPF. Appartiene alla backbone (area 0.0.0.0)? (s/N): "
            ).strip().lower()
            if ans.startswith('s'):
                st['ospf_area'], st['ospf_stub'] = '0.0.0.0', False
            else:
                st['ospf_area'] = input_area("Inserisci l'area OSPF di questo router (es. 1.1.1.1): ")
                st['ospf_stub'] = True
        else:
            first_stub = ctx['first_ospf_stub']
            ans = input_area(
                f"Area OSPF per {st['nome']} (vuoto -> default {first}{' stub' if first_stub else ''}): ",
                default=''
            )
            if ans:
                st['ospf_area'] = ans
                st['ospf_stub'] = input_non_vuoto("Marcare quest'area come stub? (s/N): ").strip().lower().startswith('s')
            else:
                st['ospf_area'], st['ospf_stub'] = first, first_stub

    def p_nif(st):
        st['n_if'] = input_int("Numero interfacce: ", 1)

    def p_igp(st):
        nome_igp = '/'.join(p.upper() for p in ('ospf', 'rip') if p in st['protocols'])
        proposta = default_igp_networks(
            st['nome'],
            {'asn': st.get('asn', '') if 'bgp' in st['protocols'] else '', 'interfaces': _ifaces_stato(st)}
        )
        st['igp_networks'] = input_reti(
            f"Network {nome_igp} da annunciare, separate da virgola (invio = {', '.join(proposta)}): ",
            default=proposta
        )

    def p_aree(st):
        st['ospf_aree'], st['ospf_aree_stub'] = chiedi_aree_ospf(st['igp_networks'], st['ospf_area'], st['ospf_stub'])

    def p_redbgp(st):
        nome_igp = '/'.join(p.upper() for p in ('ospf', 'rip') if p in st['protocols'])
        r = input(f"Iniettare in {nome_igp} le rotte imparate da BGP (redistribute bgp)? (S/n): ").strip().lower()
        st['igp_redistribute_bgp'] = not r.startswith('n')

    def p_nstatic(st):
        st['n_static'] = input_int("Numero di rotte statiche (0 se nessuna): ", 0)

    def p_static(si):
        def f(st):
            print(f"Rotta statica #{si + 1}:")
            net = input_destinazione("  Destinazione (es. 30.0.0.0/24, oppure default): ")
            via = valida_gateway("  Via / next-hop (es. 10.0.0.13): ")
            ifaces = _ifaces_stato(st)
            auto_dev = iface_for_nexthop(ifaces, via) or ifaces[0]['name']
            dev = input(f"  Interfaccia (vuoto -> {auto_dev}): ").strip()
            r = {"network": net, "via": via}
            if dev:
                r['dev'] = dev
            st.setdefault('static', {})[si] = r
        return f

    def passi(st):
        out = [p_nome, p_proto]
        protos = st.get('protocols', [])
        if 'bgp' in protos:
            out.append(p_asn)
        if 'ospf' in protos:
            out.append(p_area)
        out.append(p_nif)
        for idx in range(st.get('n_if', 0)):
            out.append(_passo_lan(idx, f"  LAN associata a eth{idx} (es. A): "))
            out.append(_passo_ip(idx, f"  IP per eth{idx} (es. 10.0.{i}.{idx}/24): ", used_ips))
        if 'ospf' in protos or 'rip' in protos:
            out.append(p_igp)
            if 'ospf' in protos and len(st.get('igp_networks') or []) > 1:
                out.append(p_aree)
            if 'bgp' in protos:
                out.append(p_redbgp)
        if 'statico' in protos:
            out.append(p_nstatic)
            out += [p_static(si) for si in range(st.get('n_static', 0))]
        return out

    def statiche(st):
        return [st['static'][k] for k in range(st.get('n_static', 0))] if 'statico' in st['protocols'] else []

    def dati(st):
        protos = st['protocols']
        rdata = {
            "protocols": protos,
            "asn": st.get('asn', '') if 'bgp' in protos else '',
            "interfaces": _ifaces_stato(st)
        }
        if 'statico' in protos:
            rdata['static_routes'] = statiche(st)
        if 'ospf' in protos:
            rdata['ospf_area'] = st['ospf_area']
            rdata['ospf_area_stub'] = st['ospf_stub']
            if st.get('ospf_aree') and len(st.get('igp_networks') or []) > 1:
                rdata['ospf_aree'] = st['ospf_aree']
                rdata['ospf_aree_stub'] = st['ospf_aree_stub']
        if 'ospf' in protos or 'rip' in protos:
            rdata['igp_networks'] = st['igp_networks']
            if 'bgp' in protos and not st.get('igp_redistribute_bgp', True):
                rdata['igp_redistribute_bgp'] = False
        return rdata

    def riepilogo(st):
        protos = st['protocols']
        righe = [
            f"router {st['nome']}   protocolli: {' '.join(protos)}"
            + (f"   AS {st['asn']}" if 'bgp' in protos else '')
        ]
        if 'ospf' in protos:
            righe.append(f"OSPF area {st['ospf_area']}{' (stub)' if st['ospf_stub'] else ''}")
            if st.get('ospf_aree') and len(st.get('igp_networks') or []) > 1:
                righe.append("router di confine: " + ', '.join(f"{r} area {a}" for r, a in st['ospf_aree'].items())
                             + (f"; stub: {', '.join(st['ospf_aree_stub'])}" if st['ospf_aree_stub'] else ''))
        for it in _ifaces_stato(st):
            righe.append(f"{it['name']}   LAN {it['lan']:<4} {it['ip']}")
        if 'ospf' in protos or 'rip' in protos:
            righe.append(
                f"network IGP: {', '.join(st['igp_networks'])}"
                + (
                    f"   redistribute bgp: {'sì' if st.get('igp_redistribute_bgp', True) else 'NO'}"
                    if 'bgp' in protos else ''
                )
            )
        for r in statiche(st):
            righe.append(f"rotta {r['network']} via {r['via']}" + (f" dev {r['dev']}" if r.get('dev') else ''))
        return righe + _avvisi(ctx, 'router', st['nome'], dati(st))

    st = esegui_passi(f"router n.{i}", passi, riepilogo)

    name, protos = st['nome'], st['protocols']
    rdata = dati(st)
    interfaces = rdata['interfaces']
    if 'ospf' in protos and ctx['first_ospf_area'] is None:
        ctx['first_ospf_area'], ctx['first_ospf_stub'] = st['ospf_area'], st['ospf_stub']
    _registra_ifaces(ctx, name, interfaces)
    ctx['routers'][name] = rdata


def wizard_host(h, ctx):
    used_ips = ctx['used_ips']

    def p_nome(st):
        st['nome'] = _chiedi_nome('host', f"host{h}", ctx['used_names'])
        print(f"--- Configurazione host {st['nome']} ---")

    def p_nif(st):
        st['n_if'] = input_int(f"Numero interfacce per {st['nome']}: ", 1)

    def p_gw(st):
        while True:
            gw = valida_gateway(f"Gateway di default per {st['nome']} (invio per nessuno): ", opzionale=True)
            e = errore_gateway_host(gw, _ifaces_stato(st), st['nome'])
            if e:
                print(f"❌ {e}")
                continue
            st['gw'] = gw
            return

    def p_gwdev(st):
        nomi = [it['name'] for it in _ifaces_stato(st)]
        auto = iface_for_nexthop(_ifaces_stato(st), st['gw']) or nomi[0]
        if len(nomi) == 1:
            st['gw_dev'] = nomi[0]
            print(f"Interfaccia per il gateway: {nomi[0]}")
            return
        while True:
            dev = input(f"Interfaccia per il gateway {st['gw']} (default {auto}): ").strip() or auto
            e = errore_interfaccia(dev, nomi, st['nome'])
            if not e:
                st['gw_dev'] = dev
                return
            print(f"❌ {e}")

    def passi(st):
        out = [p_nome, p_nif]
        for idx in range(st.get('n_if', 0)):
            out.append(_passo_ip(idx, f"    IP per eth{idx} (es. 192.168.10.{h}/24): ", used_ips))
            out.append(_passo_lan(idx, f"    LAN associata a eth{idx} (es. A): "))
        out.append(p_gw)
        if st.get('gw'):
            out.append(p_gwdev)
        return out

    def dati(st):
        interfaces = _ifaces_stato(st)
        return {
            "name": st['nome'], "interfaces": interfaces, "gateway": st.get('gw', ''),
            "gw_dev": st.get('gw_dev', '') if st.get('gw') else '',
            "ip": interfaces[0]['ip'], "lan": interfaces[0]['lan']
        }

    def riepilogo(st):
        righe = [f"host {st['nome']}"]
        righe += [f"{it['name']}   LAN {it['lan']:<4} {it['ip']}" for it in _ifaces_stato(st)]
        righe.append(
            f"default gateway: {st['gw']} dev {st['gw_dev']}"
            if st.get('gw') else "default gateway: nessuno"
        )
        return righe + _avvisi(ctx, 'host', st['nome'], dati(st))

    st = esegui_passi(f"host n.{h}", passi, riepilogo)

    hdata = dati(st)
    name, interfaces = hdata['name'], hdata['interfaces']
    _registra_ifaces(ctx, name, interfaces)
    ctx['hosts'].append(hdata)


def wizard_www(w, ctx):
    def p_nome(st):
        st['nome'] = _chiedi_nome('webserver', f"www{w}", ctx['used_names'])
        print(f"--- Configurazione webserver {st['nome']} ---")

    def p_ip(st):
        st['ip'] = _chiedi_ip_libero(f"IP per {st['nome']} (es. 10.10.{w}.1/24): ", ctx['used_ips'], set())

    def p_gw(st):
        st['gw'] = valida_gateway(f"Gateway per {st['nome']} (es. 10.10.{w}.254): ")

    def p_lan(st):
        st['lan'] = input_lan("LAN associata (es. Z): ")

    def dati(st):
        return {"name": st['nome'], "ip": st['ip'], "gateway": st['gw'], "lan": st['lan']}

    st = esegui_passi(
        f"webserver n.{w}",
        lambda st: [p_nome, p_ip, p_gw, p_lan],
        lambda st: [
            f"webserver {st['nome']}   eth0   LAN {st['lan']:<4} {st['ip']}",
            f"default gateway: {st['gw']}"
        ] + _avvisi(ctx, 'www', st['nome'], dati(st))
    )

    name = st['nome']
    _registra_ifaces(ctx, name, [{'lan': st['lan'], 'ip': st['ip']}])
    ctx['wwws'].append(dati(st))


def _chiedi_zone():
    """Zone authoritative per un host DNS (domande annidate: un unico passo)."""
    zones = {}
    nz = input_int("Numero di zone da creare su questo host: ", 0)
    for zi in range(1, nz + 1):
        zname = input_non_vuoto(f"  Nome zona {zi} (nome Host DNS in questione): ")
        print(f"  Creazione zona '{zname}': inserisci i record desiderati.")
        records = {}
        nr = input_int(f"  Quanti record vuoi aggiungere nella zona '{zname}'? ", 0)
        for r in range(1, nr + 1):
            print(f"    Record {r} (formati supportati: A, NS, CNAME, DELEGATION)")
            rtype = input_non_vuoto("      Tipo record (A/NS/CNAME/DELEGATION): ").strip().upper()
            if rtype == 'A':
                h = input_non_vuoto("      Nome host (es. dns.it): ")
                rip = valida_ip_cidr("      IP (es. 10.20.1.10/24): ")
                records[h] = rip.split('/')[0]
            elif rtype == 'NS':
                h = input_non_vuoto("      Nome delegato (es. @ per la zona): ")
                nsname = input_non_vuoto("      Nome del nameserver (es. dns.example.local.): ")
                glue = valida_gateway("      Glue IP per il nameserver (opzionale, invio per saltare): ", opzionale=True)
                rec = {'type': 'NS', 'ns': nsname}
                if glue:
                    rec['glue'] = glue
                records[h] = rec
            elif rtype == 'CNAME':
                h = input_non_vuoto("      Nome alias (es. ftp): ")
                target = input_non_vuoto("      Target canonical name (es. www): ")
                records[h] = {'type': 'CNAME', 'target': target}
            elif rtype == 'DELEGATION':
                child = input_non_vuoto("      Nome sottodominio da delegare (es. sub): ")
                nsname = input_non_vuoto("      Nameserver per la delega (es. ns.sub.example.local.): ")
                ns_ip = valida_gateway("      Glue IP per il nameserver (opzionale): ", opzionale=True)
                rec = {'type': 'DELEGATION', 'zone': child, 'ns': nsname}
                if ns_ip:
                    rec['ns_ip'] = ns_ip
                records[child] = rec
            else:
                print("      Tipo record non riconosciuto, salto questo record.")
        zones[zname] = records
    return zones


def wizard_dns(d, ctx):
    forza_root = d == 1 and 'root' not in ctx['used_names']
    if forza_root:
        print("\nNome host DNS forzato per il primo DNS: 'root' (server root/master)")
    elif d == 1:
        print("Nome 'root' è già stato usato. Inserisci un nome alternativo per il primo DNS.")

    def p_nome(st):
        st['nome'] = _chiedi_nome('host DNS', f"dns{d}", ctx['used_names'])

    def p_ip(st):
        print(f"--- Configurazione host DNS {st['nome']} ---")
        st['ip'] = _chiedi_ip_libero(f"IP per {st['nome']} (es. 10.20.{d}.10/24): ", ctx['used_ips'], set())

    def p_gw(st):
        st['gw'] = valida_gateway(f"Gateway per {st['nome']} (es. 10.20.{d}.1): ")

    def p_lan(st):
        st['lan'] = input_lan("LAN associata (es. A): ")

    def p_zone(st):
        add_z = input("Aggiungere zone authoritative su questo host? (s/N): ").strip().lower()
        st['zones'] = _chiedi_zone() if add_z.startswith('s') else None

    def p_root_type(st):
        c = input("Tipo server per '.' ? (m=master / h=hint / n=nessuno) [h]: ").strip().lower()
        st['root_type'] = 'master' if c == 'm' else (None if c == 'n' else 'hint')

    def p_rec(st):
        ar = input("Il server fa da resolver (allow-recursion)? (s/N): ").strip().lower()
        if not ar.startswith('s'):
            st['allow_recursion'] = None
            return
        while True:
            reti = input("  Da quali reti? (invio = any, es. 10.0.0.0/24): ").strip()
            if not reti or reti.lower() == 'any':
                st['allow_recursion'] = 'any'
                return
            e = errore_allow_recursion(reti)
            if not e:
                st['allow_recursion'] = '; '.join(parse_reti(reti))
                return
            print(f"❌ {e}")

    def p_dnssec(st):
        dv = input("Vuoi disabilitare DNSSEC validation ?  (s/N): ").strip().lower()
        st['dnssec_validation'] = dv.startswith('s')

    def p_deleghe(st):
        zone = input("Zone da delegare dal root, separate da virgola (es. com, it; invio = nessuna): ")
        deleghe = []
        for z in [t.strip().strip('.') for t in zone.replace(',', ' ').split() if t.strip('.')]:
            ns = input(f"  Nameserver di {z} (invio = dns.{z}): ").strip().rstrip('.') or f"dns.{z}"
            ip = valida_ip_senza_cidr(f"  IP di {ns} (es. 20.1.0.3): ")
            deleghe.append({'zone': z, 'ns': ns, 'ip': ip})
        st['delegations'] = deleghe

    def passi(st):
        if forza_root:
            st['nome'] = 'root'
            out = []
        else:
            out = [p_nome]
        out += [p_ip, p_gw, p_lan]
        if st.get('nome') == 'root':
            out.append(p_deleghe)
        else:
            out += [p_zone, p_root_type]
            if st.get('root_type') == 'master':
                out.append(p_deleghe)
            out += [p_rec, p_dnssec]
        return out

    def dati(st):
        name, ip, gw, lan = st['nome'], st['ip'], st['gw'], st['lan']
        if name == 'root':
            zones, root_type, allow_recursion, dnssec_validation = None, 'master', None, False
        else:
            zones, root_type = st.get('zones'), st.get('root_type')
            allow_recursion, dnssec_validation = st.get('allow_recursion'), st.get('dnssec_validation', False)
        delegations = (st.get('delegations') or []) if root_type == 'master' else []
        return {
            "name": name, "ip": ip, "gateway": gw, "lan": lan, "dns": True,
            "forwarders": None, "zones": zones, 'root_type': root_type,
            'allow_recursion': allow_recursion, 'dnssec_validation': dnssec_validation,
            'delegations': delegations
        }

    def riepilogo(st):
        righe = [f"DNS {st['nome']}   eth0   LAN {st['lan']:<4} {st['ip']}   gateway {st['gw']}"]
        if st['nome'] == 'root':
            righe.append("server root (master per '.')")
        else:
            righe.append(
                f"tipo per '.': {st.get('root_type') or 'nessuno'}   "
                f"allow-recursion: {st.get('allow_recursion') or 'no'}   "
                f"dnssec-validation no: {'sì' if st.get('dnssec_validation') else 'no'}"
            )
            for z, recs in (st.get('zones') or {}).items():
                righe.append(f"zona {z}: {len(recs)} record")
        if st['nome'] == 'root' or st.get('root_type') == 'master':
            dl = st.get('delegations') or []
            righe.append(
                "deleghe: " + (
                    ', '.join(f"{x['zone']} -> {x['ns']} ({x['ip']})" for x in dl)
                    if dl else "nessuna (attenzione: senza deleghe nessun dominio si risolve)"
                )
            )
        return righe + _avvisi(ctx, 'dns', st['nome'], dati(st))

    st = esegui_passi(f"host DNS n.{d}", passi, riepilogo)

    ddata = dati(st)
    _registra_ifaces(ctx, ddata['name'], [{'lan': ddata['lan'], 'ip': ddata['ip']}])
    ctx['hosts'].append(ddata)


def _scegli_resolver(hosts):
    """Domanda finale: un DNS del lab come resolver di tutti gli altri? Restituisce il suo nome o None."""
    dns_list = [h for h in hosts if isinstance(h, dict) and h.get('dns')]
    if not dns_list:
        return None
    ask_resolver = input("\nVuoi che uno dei DNS creati sia resolver per gli altri dispositivi? (s/N): ").strip().lower()
    if not ask_resolver.startswith('s'):
        return None
    items = [f"{dh.get('name')} - {(str(dh.get('ip') or '')).split('/')[0]}" for dh in dns_list]
    print_menu('Seleziona il DNS resolver dalla lista seguente:', items)
    resolver_choice = input("Inserisci il nome o il numero del DNS resolver scelto: ").strip()
    scelto = None
    if resolver_choice.isdigit():
        idx = int(resolver_choice) - 1
        if 0 <= idx < len(dns_list):
            scelto = dns_list[idx]
    else:
        scelto = next((dh for dh in dns_list if dh.get('name') == resolver_choice), None)
    resolver_ip = str(scelto.get('ip') or '').split('/')[0] if scelto else ''
    if not resolver_ip:
        print("Scelta del resolver non valida o IP non trovato: nessun resolver impostato.")
        return None
    print(f"\nResolver impostato: nameserver {resolver_ip} -> resolv.conf nelle cartelle dei dispositivi.")
    return scelto.get('name')


def esegui_wizard_nuovo_lab(base, lab_name):
    """Esegue l'intero flusso guidato di creazione di un nuovo laboratorio (Modalità 1).

    Le domande raccolgono il modello del lab; i file vengono scritti solo alla fine, tutti insieme,
    da core/generazione.genera_lab. Se il wizard si interrompe, non resta nulla su disco e un lab
    che si stava sostituendo resta com'era."""
    from .generazione import genera_lab

    lab_path = os.path.join(base, lab_name)
    sovrascrivi = False
    if os.path.exists(lab_path):
        ans = input("Attenzione: esiste già. Sovrascrivere? (s/n): ").strip().lower()
        if ans != "s":
            print("Annullato.")
            return
        sovrascrivi = True
        print("Il lab attuale verrà sostituito solo alla fine, dopo una copia di sicurezza.")

    print("\nSuggerimento: durante la creazione digita '<' per tornare alla domanda precedente")
    print("e '<<' per ricominciare il dispositivo corrente. Alla fine di ogni dispositivo")
    print("vedrai un riepilogo da confermare; i file vengono scritti tutti alla fine.")

    n_router, n_host, n_www, n_dns = wizard_conteggi()

    routers = {}
    hosts = []
    wwws = []
    ctx = {
        'routers': routers, 'hosts': hosts, 'wwws': wwws, 'used_ips': set(), 'used_names': set(),
        'first_ospf_area': None, 'first_ospf_stub': False
    }

    for i in range(1, n_router + 1):
        wizard_router(i, ctx)
    for h in range(1, n_host + 1):
        wizard_host(h, ctx)
    for w in range(1, n_www + 1):
        wizard_www(w, ctx)
    for d in range(1, n_dns + 1):
        wizard_dns(d, ctx)

    resolver = _scegli_resolver(hosts)

    modello = {'routers': routers, 'hosts': hosts, 'wwws': wwws, 'resolver': resolver}
    esito = genera_lab(base, lab_name, modello, sovrascrivi=sovrascrivi)
    if not esito['creato']:
        print("Lab non creato:")
        for p in esito['errori']:
            print(f"  - {p['campo']}: {p['messaggio']}")
        if esito['motivo'] == 'esiste':
            print(f"  - {lab_path} esiste già.")
        return
    for m in esito['messaggi']:
        print(m)
    if esito['copia']:
        print(f"Il lab di prima è salvato in: {esito['copia']}")

    print(f"\n✅ Lab '{lab_name}' creato in: {lab_path}")
    stampa_controllo_topologia(lab_path)
    try:
        menu_post_creazione(lab_path, routers)
    except Exception as e:
        print('Errore durante il menu post-creazione:', e)
