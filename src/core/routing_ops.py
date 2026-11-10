"""
src/core/routing_ops.py
Operazioni del menu Opzioni Laboratorio: policy BGP, costi OSPF, iBGP, loopback, ridistribuzione, DNS.
"""
import datetime
import ipaddress
import os
import re
import shutil

from .analyzer import (
    _analizza_frr,
    collect_lab_ips,
    generate_ping_oneliner,
    isole_ospf,
    riepilogo_configurazione,
)
from .cli_io import (
    Annullato,
    _chiedi_asn,
    _chiedi_direzione,
    _chiedi_int,
    _chiedi_ip,
    _chiedi_reti,
    _si,
    input,
    input_area,
    input_asn,
    input_int,
    input_non_vuoto,
    input_reti,
    parse_reti,
    print_menu,
    select_interface,
    select_router,
    valida_ip_senza_cidr,
)
from .device_editor import modifica_dispositivo_menu
from .file_utils import (
    _applica_modifiche,
    _append_righe,
    _comandi_nodo,
    _indici_nodo,
    _inizio_blocco,
    _inserisci_nel_blocco,
    _leggi_righe,
    _righe_file,
    _rimuovi_righe,
    _scrivi_righe,
    append_frr_stanza,
    insert_lines_into_protocol_block,
)
from .generators import _righe_delega, _soa_root
from .net_frr import (
    _collega_al_neighbor,
    _ip_verso,
    _neighbor_presente,
    _norm_net,
    _rete_di_ip,
    _reti_del_router,
    _reti_peering,
    _scrivi_route_map,
    add_ibgp_loopback_neighbors,
    default_bgp_aggregate,
)
from .persistence import (
    correggi_nomi_lab,
    load_lab_from_xml,
    rebuild_lab_metadata_and_export,
)


def aggiungi_relazioni_bgp_menu(base_path, routers):
    print("\n=== Aggiungi relazioni BGP (manuale) ===")
    if not routers:
        print("Nessun router disponibile.")
        return
    while True:
        print("\nRouter disponibili:")
        for rn, r in routers.items():
            print(f" - {rn} (ASN: {r.get('asn', '-')})")
        src = input("Router sorgente (vuoto per uscire): ").strip()
        if not src:
            break
        if src not in routers:
            print("Router sorgente non valido.")
            continue
        dst = input("Router destinazione: ").strip()
        if dst not in routers:
            print("Router destinazione non valido.")
            continue
        if "bgp" not in routers[src]["protocols"] or "bgp" not in routers[dst]["protocols"]:
            print("Entrambi i router devono avere BGP abilitato.")
            continue
        rel = input("Tipo relazione (peer/provider/customer): ").strip().lower()
        if rel not in ("peer", "provider", "customer"):
            print("Tipo relazione non valido.")
            continue
        neigh_ip = valida_ip_senza_cidr("IP neighbor verso dst (es. 10.0.0.2): ")
        aggiungi_policy = input("Aggiungere prefix-list / route-map (s/N)? ").strip().lower().startswith("s")
        lp_map = {"peer": 100, "provider": 80, "customer": 120}
        local_pref = lp_map[rel]
        fpath = os.path.join(base_path, src, "etc", "frr", "frr.conf")
        neighbor_lines = [
            f"neighbor {neigh_ip} remote-as {routers[dst]['asn']}",
            f"neighbor {neigh_ip} description {rel}_{dst}"
        ]
        insert_lines_into_protocol_block(fpath, proto='bgp', asn=None, lines=neighbor_lines)

        if aggiungi_policy:
            policy = [
                f"neighbor {neigh_ip} prefix-list {rel}_{dst}_in in",
                f"neighbor {neigh_ip} prefix-list {rel}_{dst}_out out",
                "",
                f"ip prefix-list {rel}_{dst}_in permit any",
                f"ip prefix-list {rel}_{dst}_out permit any",
                "",
                f"route-map pref_{dst}_in permit 10",
                f"    set local-preference {local_pref}",
                "",
                f"neighbor {neigh_ip} route-map pref_{dst}_in in"
            ]
            with open(fpath, 'a', encoding='utf-8', newline='\n') as f:
                for line in policy:
                    f.write(line + "\n")
        print(f"Relazione BGP ({rel}) aggiunta su {src} verso {dst} (neighbor {neigh_ip}).")


def assegna_costo_interfaccia(base_path, routers):
    print('\n--- Assegna costo OSPF su una interfaccia di un router ---')
    target = select_router(routers, prompt='Seleziona il router su cui impostare il costo OSPF:')
    if not target:
        print('Operazione annullata.')
        return
    prot = routers.get(target, {}).get('protocols', [])
    if 'ospf' not in prot:
        print(f"⚠️ Il router {target} non ha OSPF abilitato (protocols: {prot}). Abilita OSPF prima di impostare il costo.")
        return
    iface = select_interface(routers[target])
    if not iface:
        print('Interfaccia non selezionata. Annullato.')
        return
    costo = input_int(f'Inserisci il costo OSPF desiderato per {iface} (intero ≥ 1): ', 1)
    stanza = f"interface {iface}\n    ospf cost {costo}\n"
    if append_frr_stanza(base_path, target, stanza):
        print(f"✅ Costo impostato su {target} {iface} = {costo} (append su frr.conf).")


def aggiungi_network_bgp(base_path, routers):
    """Aggiunge una o più `network` al blocco router bgp."""
    print('\n--- Aggiungi network BGP ---')
    bgp_routers = {k: v for k, v in routers.items() if 'bgp' in v.get('protocols', [])}
    target = select_router(bgp_routers, prompt='Seleziona il router BGP:')
    if not target:
        print('Operazione annullata.')
        return
    fpath = os.path.join(base_path, target, 'etc', 'frr', 'frr.conf')
    if not os.path.exists(fpath):
        print(f"frr.conf non trovato per {target}: {fpath}")
        return
    proposta = default_bgp_aggregate(target, routers[target])
    reti = input_reti(
        f"Reti da annunciare in BGP, separate da virgola (invio = {', '.join(proposta)}): ",
        default=proposta
    )
    presenti, in_bgp = set(), False
    for l in _leggi_righe(fpath):
        s = l.strip()
        if s.startswith('router '):
            in_bgp = s.startswith('router bgp')
        elif l and not l[0].isspace():
            in_bgp = False
        elif in_bgp and s.startswith('network ') and len(s.split()) >= 2:
            presenti.add(_norm_net(s.split()[1]))
    nuove = [r for r in reti if r not in presenti]
    if not nuove:
        print('Tutte le reti indicate sono già annunciate.')
        return
    insert_lines_into_protocol_block(fpath, proto='bgp', asn=None, lines=[f"network {r}" for r in nuove])
    routers[target].setdefault('bgp_extra_networks', []).extend(nuove)
    print(f"✅ {target}: aggiunte in BGP {', '.join(nuove)}")

    aggregati = [ipaddress.ip_network(r) for r in nuove]
    peering = _reti_peering(target, routers)
    coperte = sorted(
        p for p in presenti
        if p not in peering
        and any(ipaddress.ip_network(p) != a and ipaddress.ip_network(p).subnet_of(a) for a in aggregati)
    )
    if coperte:
        ans = input(
            f"Le reti {', '.join(coperte)} sono già contenute nell'aggregato. "
            f"Toglierle da BGP e annunciare solo l'aggregato? (s/N): "
        ).strip().lower()
        if ans.startswith('s'):
            out, in_bgp = [], False
            for l in _leggi_righe(fpath):
                s = l.strip()
                if s.startswith('router '):
                    in_bgp = s.startswith('router bgp')
                elif l and not l[0].isspace():
                    in_bgp = False
                elif in_bgp and s.startswith('network ') and len(s.split()) == 2 and _norm_net(s.split()[1]) in coperte:
                    continue
                out.append(l)
            _scrivi_righe(fpath, out)
            print(f"✅ {target}: tolte da BGP {', '.join(coperte)}")


def aggiungi_delega_dns(base_path):
    """Aggiunge al server root (master per '.') la delega di una zona."""
    print('\n--- Aggiungi delega DNS sul root ---')
    dns = []
    for d in sorted(os.listdir(base_path)):
        nc = os.path.join(base_path, d, 'etc', 'bind', 'named.conf')
        if os.path.isfile(nc):
            testo = ' '.join(' '.join(_leggi_righe(nc)).split())
            master = re.search(r'zone "\." \{ type master;', testo) is not None
            dns.append((d, master))
    if not dns:
        print('Nessun server DNS (etc/bind/named.conf) nel lab.')
        return
    print_menu('Server DNS del lab:', [f"{d}{'  (root: master per .)' if m else ''}" for d, m in dns])
    sel = input('Seleziona il server root (numero o nome, vuoto per annullare): ').strip()
    if not sel:
        print('Operazione annullata.')
        return
    scelto = (
        dns[int(sel) - 1] if sel.isdigit() and 1 <= int(sel) <= len(dns)
        else next((x for x in dns if x[0] == sel), None)
    )
    if not scelto:
        print('Selezione non valida.')
        return
    nome, master = scelto
    if not master:
        print(
            f"⚠️ {nome} non è il root (in named.conf la zona '.' non è 'type master'): "
            f"le deleghe dei domini di primo livello vanno sul root."
        )
        return
    zona = input('Zona da delegare (es. com, vuoto per annullare): ').strip().strip('.')
    if not zona:
        print('Operazione annullata.')
        return
    ns = input(f"Nameserver di {zona} (invio = dns.{zona}): ").strip().rstrip('.') or f"dns.{zona}"
    ip = valida_ip_senza_cidr(f"IP di {ns} (es. 20.1.0.3): ")
    fpath = os.path.join(base_path, nome, 'etc', 'bind', 'db.root')
    righe = _leggi_righe(fpath)
    if not any('SOA' in l for l in righe):
        serial = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d') + '01'
        righe = _soa_root(serial) + righe
        print("ℹ️ db.root non aveva il SOA (necessario per un master): aggiunto.")
    gia = any(l.split()[:1] == [f"{zona}."] and 'NS' in l.split() for l in righe if l.strip())
    if gia:
        print(f"⚠️ La zona {zona} è già delegata in {nome}/etc/bind/db.root.")
        _scrivi_righe(fpath, righe)
        return
    _scrivi_righe(fpath, [l for l in righe] + _righe_delega(zona, ns, ip))
    print(f"✅ {nome}: delegata la zona {zona} a {ns} ({ip}).")


def aggiungi_ibgp_full_mesh(base_path, routers):
    """Crea le sessioni iBGP mancanti tra tutti i router BGP di uno stesso AS (full mesh)."""
    print("\n--- Aggiungi sessioni iBGP (full mesh nell'AS) ---")
    per_as = {}
    for rn, rd in routers.items():
        if 'bgp' in rd.get('protocols', []) and str(rd.get('asn', '')).strip():
            per_as.setdefault(str(rd['asn']).strip(), []).append(rn)
    candidati = {a: ns for a, ns in per_as.items() if len(ns) >= 2}
    if not candidati:
        print('Nessun AS con almeno due router BGP.')
        return
    elenco = sorted(candidati, key=lambda a: int(a) if a.isdigit() else 0)
    print_menu('AS con più router BGP:', [f"AS{a}: {', '.join(candidati[a])}" for a in elenco])
    sel = input("Seleziona l'AS (numero nella lista o numero AS, vuoto per annullare): ").strip()
    if not sel:
        print('Operazione annullata.')
        return
    if sel.isdigit() and 1 <= int(sel) <= len(elenco) and sel not in candidati:
        sel = elenco[int(sel) - 1]
    if sel not in candidati:
        print('Selezione non valida.')
        return
    membri = candidati[sel]
    print("⚠️ Controlla il testo: alcuni esercizi vietano l'iBGP (es. butterfly).")
    aggiunte = 0
    for x in membri:
        fpath = os.path.join(base_path, x, 'etc', 'frr', 'frr.conf')
        presenti = set(re.findall(r'neighbor (\S+) remote-as', '\n'.join(_leggi_righe(fpath))))
        nuove = []
        for y in membri:
            if y == x:
                continue
            ips_y = {
                str(ipaddress.ip_interface(it['ip']).ip)
                for it in routers[y].get('interfaces', []) if it.get('ip')
            }
            if presenti & ips_y:
                continue
            ip = _ip_verso(routers, y, x, sel)
            if ip:
                nuove += [f"neighbor {ip} remote-as {sel}", f"neighbor {ip} description iBGP {y}"]
        if nuove:
            insert_lines_into_protocol_block(fpath, proto='bgp', asn=None, lines=nuove)
            aggiunte += len(nuove) // 2
            print(f"✅ {x}: " + ', '.join(l.split()[1] for l in nuove if 'remote-as' in l))
    print(f"Sessioni iBGP aggiunte: {aggiunte}" if aggiunte else 'Tutte le sessioni iBGP erano già presenti.')


def policies_menu(base_path, routers):
    """Sotto-menu per applicare policies BGP ai router del lab."""
    while True:
        items = [
            'Prefix-list: scarta una o più reti da/verso un neighbor (deny ... + permit any)',
            'Local-preference in ingresso (su tutte le rotte o solo su alcune reti)',
            'MED (metric) in uscita',
            'Access-list: scarta una rete in ingresso (via route-map)',
            'Configurazione Customer-Provider-Peer',
            'Default route verso uno o più neighbor (default-originate, anche "solo la default")'
        ]
        print_menu('=== Policies BGP (scegli) ===', items, extra_options=[('0', 'Torna indietro')])
        c = input('Seleziona (numero): ').strip()
        if c == '0':
            break
        if c not in ('1', '2', '3', '4', '5', '6'):
            print('Scelta non valida.')
            continue

        if c == '5':
            aggiungi_customer_provider_wizard(base_path, routers)
            continue
        if c == '6':
            aggiungi_default_originate(base_path, routers)
            continue

        print("(Invio senza scrivere nulla a una domanda = annulla e torna al menu)")
        try:
            src = select_router(routers, prompt='Seleziona il router su cui applicare la policy:')
            if not src:
                raise Annullato()
            if 'bgp' not in routers.get(src, {}).get('protocols', []):
                print(f"⚠️ Il router {src} non ha BGP abilitato.")
                continue
            fpath = os.path.join(base_path, src, 'etc', 'frr', 'frr.conf')
            if not os.path.exists(fpath):
                print(f"frr.conf non trovato per {src}: {fpath}")
                continue

            neigh_ip = _chiedi_ip('IP neighbor (es. 10.0.0.2): ')
            nuovo_asn = None
            if not _neighbor_presente(fpath, neigh_ip):
                print(f"Il neighbor {neigh_ip} non è configurato su {src}.")
                nuovo_asn = _chiedi_asn(f"ASN del neighbor {neigh_ip} (per crearlo): ")
            if c == '1':
                direz = _chiedi_direzione()
                reti = _chiedi_reti('Reti da DENY, separate da virgola (es. 100.0.0.0/8, 100.1.0.0/24): ')
            elif c == '2':
                lp_val = _chiedi_int('Valore local-preference da impostare (es. 110): ', 0)
                reti = _chiedi_reti(
                    'Solo per alcune reti? Inserisci le reti separate da virgola (Invio = tutte le rotte): ',
                    vuoto_ok=True
                )
            elif c == '3':
                m_val = _chiedi_int('Valore metric (MED) da impostare (es. 20): ', 0)
            elif c == '4':
                reti = _chiedi_reti('Rete da bloccare in ingresso (es. 10.0.1.0/24): ')
        except Annullato:
            print('Annullato: nessuna modifica.')
            continue

        if nuovo_asn:
            insert_lines_into_protocol_block(
                fpath, proto='bgp', asn=None,
                lines=[f"neighbor {neigh_ip} remote-as {nuovo_asn}"]
            )
        tag = neigh_ip.replace('.', '_')

        if c == '1':
            pl_name = f"PL_{src}_{tag}_{direz}"
            pat = re.compile(rf"^\s*ip prefix-list {re.escape(pl_name)} deny (\S+)")
            prev = [m.group(1) for m in map(pat.match, _leggi_righe(fpath)) if m]
            tutte = prev + [r for r in reti if r not in prev]
            _rimuovi_righe(fpath, lambda l: l.strip().startswith(f"ip prefix-list {pl_name} "))
            _append_righe(
                fpath,
                [f"ip prefix-list {pl_name} deny {r}" for r in tutte]
                + [f"ip prefix-list {pl_name} permit any"]
            )
            _collega_al_neighbor(fpath, neigh_ip, 'prefix-list', pl_name, direz)
            print(
                f"✅ {src}: prefix-list {pl_name} ({direz}, neighbor {neigh_ip}): "
                f"deny {', '.join(tutte)} + permit any."
            )

        elif c == '2':
            rm_name, pl_name = f"PREF_IN_{tag}", f"PREF_IN_{tag}_NETS"
            if reti:
                stanza = [
                    f"route-map {rm_name} permit 10",
                    f"    match ip address prefix-list {pl_name}",
                    f"    set local-preference {lp_val}",
                    f"route-map {rm_name} permit 20",
                    ""
                ] + [f"ip prefix-list {pl_name} permit {r}" for r in reti]
            else:
                stanza = [f"route-map {rm_name} permit 10", f"    set local-preference {lp_val}"]
            _scrivi_route_map(fpath, rm_name, stanza, pl_name)
            _collega_al_neighbor(fpath, neigh_ip, 'route-map', rm_name, 'in')
            print(
                f"✅ {src}: route-map {rm_name} (neighbor {neigh_ip}, in): local-preference {lp_val} "
                f"{'per ' + ', '.join(reti) if reti else 'su tutte le rotte'}."
            )

        elif c == '3':
            rm_name = f"LOCALMED_OUT_{tag}"
            _scrivi_route_map(fpath, rm_name, [f"route-map {rm_name} permit 10", f"    set metric {m_val}"])
            _collega_al_neighbor(fpath, neigh_ip, 'route-map', rm_name, 'out')
            print(f"✅ {src}: route-map {rm_name} (neighbor {neigh_ip}, out): metric {m_val}.")

        elif c == '4':
            contenuto = '\n'.join(_leggi_righe(fpath))
            acl_id = 10
            while re.search(rf"access-list {acl_id}\b", contenuto):
                acl_id += 10
            rm_name = f"FILTER_IN_{tag}"
            stanza = (
                [f"access-list {acl_id} deny {r}" for r in reti]
                + [f"access-list {acl_id} permit any", "", f"route-map {rm_name} permit 10", f"    match ip address {acl_id}"]
            )
            _scrivi_route_map(fpath, rm_name, stanza)
            _collega_al_neighbor(fpath, neigh_ip, 'route-map', rm_name, 'in')
            print(
                f"✅ {src}: access-list {acl_id} (deny {', '.join(reti)}) e route-map {rm_name} "
                f"(neighbor {neigh_ip}, in)."
            )


def aggiungi_default_originate(base_path, routers):
    """Policies 6: 'neighbor X default-originate' su uno o più vicini di un router BGP."""
    print('\n--- Default route verso un neighbor (default-originate) ---')
    print("(Invio senza scrivere nulla a una domanda = annulla e torna al menu)")
    bgp_routers = {k: v for k, v in routers.items() if 'bgp' in v.get('protocols', [])}
    src = select_router(bgp_routers, prompt='Router che manda la default:')
    if not src:
        print('Annullato: nessuna modifica.')
        return
    rel = os.path.join(src, 'etc', 'frr', 'frr.conf')
    fpath = os.path.join(base_path, rel)
    if not os.path.exists(fpath):
        print(f"frr.conf non trovato per {src}: {fpath}")
        return
    vecchie = _righe_file(fpath)
    cfg = _analizza_frr(vecchie)
    if not cfg['asn'] or not cfg['neighbors']:
        print(f"{src} non ha neighbor BGP in frr.conf: crea prima le sessioni.")
        return
    owner = {}
    for rn, rd in routers.items():
        for it in rd.get('interfaces', []):
            if it.get('ip'):
                owner[it['ip'].split('/')[0]] = rn
    vicini = list(cfg['neighbors'].items())
    ebgp = [ip for ip, a in vicini if a != cfg['asn']]
    voci = []
    for ip, a in vicini:
        chi = owner.get(ip) or cfg['descr'].get(ip, '?')
        gia = '  (ha già default-originate)' if ip in cfg['default_orig'] else ''
        voci.append(f"{ip:<15} {chi:<10} AS{a:<5} {'iBGP' if a == cfg['asn'] else 'eBGP'}{gia}")
    print_menu(f"Neighbor di {src} (AS{cfg['asn']}):", voci)
    while True:
        s = input(
            "A chi mandare la default? Numeri separati da virgola, T = tutti gli eBGP (Invio = annulla): "
        ).strip().lower()
        if not s:
            print('Annullato: nessuna modifica.')
            return
        if s == 't':
            scelti = ebgp
        else:
            scelti, ok = [], True
            for x in s.replace(',', ' ').split():
                if x.isdigit() and 1 <= int(x) <= len(vicini):
                    scelti.append(vicini[int(x) - 1][0])
                elif x in cfg['neighbors']:
                    scelti.append(x)
                else:
                    ok = False
            if not ok:
                print("❌ Scrivi i numeri della lista (es. 1,2) oppure T.")
                continue
        scelti = list(dict.fromkeys(scelti))
        if scelti:
            break
        print("❌ Nessun neighbor eBGP: scegli dai numeri della lista.")
    solo = _si(
        "Questi neighbor devono ricevere SOLO la default (e al massimo poche reti che indichi)? "
        "Es. 'announces just the default route'. (s/N): "
    )
    extra = []
    if solo:
        while True:
            t = input("Reti da annunciare oltre alla default (es. 1.0.0.0/8; Invio = solo la default): ").strip()
            if not t:
                break
            try:
                extra = parse_reti(t)
                break
            except ValueError as e:
                print(f"❌ Rete non valida: {e}")

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
            print(f"{src}: manca il blocco 'router bgp' in frr.conf.")
            return
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
                f"{r} non è tra le network BGP di {src}: la prefix-list la lascia passare, ma per "
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
    _applica_modifiche(
        base_path, {rel: (vecchie, pulite)},
        f"Default route da {src} verso {', '.join(owner.get(i, i) for i in scelti)}",
        note
    )


def default_route_menu(base_path, routers):
    """Opzioni 12: tutte le default route in un posto solo (BGP, RIP, OSPF)."""
    while True:
        print_menu('=== Default route ===', [
            'BGP: manda la default a uno o più neighbor (default-originate, come Policies 6)',
            "RIP: annuncia la default (route 0.0.0.0/0) o un'altra rete (route <rete>)",
            'OSPF: annuncia la default (default-information originate)'
        ], extra_options=[('0', 'Torna indietro')])
        c = input('Seleziona (numero): ').strip()
        if c == '0' or not c:
            return
        if c == '1':
            aggiungi_default_originate(base_path, routers)
        elif c in ('2', '3'):
            aggiungi_default_igp(base_path, 'rip' if c == '2' else 'ospf')
        else:
            print('Scelta non valida.')


def aggiungi_default_igp(base_path, proto):
    """Default route in RIP o OSPF, dentro il blocco 'router rip/ospf' del router scelto."""
    nome_p = proto.upper()
    print(f"\n--- Default route in {nome_p} ---")
    rx = rf'router {proto}\b'
    cand = []
    for d in sorted(os.listdir(base_path)):
        f = os.path.join(base_path, d, 'etc', 'frr', 'frr.conf')
        if os.path.isfile(f) and _inizio_blocco(_righe_file(f), rx) is not None:
            cand.append(d)
    if not cand:
        print(f"Nessun router del lab ha il blocco 'router {proto}' in frr.conf.")
        return
    print_menu(f"Router con {nome_p}:", cand)
    s = input("Router (numero o nome, Invio = annulla): ").strip()
    src = cand[int(s) - 1] if s.isdigit() and 1 <= int(s) <= len(cand) else (s if s in cand else None)
    if not src:
        print('Annullato: nessuna modifica.' if not s else 'Router non valido: nessuna modifica.')
        return
    rel = os.path.join(src, 'etc', 'frr', 'frr.conf')
    vecchie = _righe_file(os.path.join(base_path, rel))
    blocco = _comandi_nodo(vecchie, _inizio_blocco(vecchie, rx))
    note = []
    if proto == 'rip':
        print(
            "  1) route <rete>: annuncia la rete (Invio = 0.0.0.0/0, la default), anche se il router non ha "
            "una rotta: come la guida 009 e up-arrow; serve anche per iniettare un'altra rete"
        )
        print(
            "  2) default-information originate: annuncia la default (in FRR la annuncia sempre, come "
            "route 0.0.0.0/0; in 'show ip rip' compare come R(d) invece di R(s))"
        )
        modo = input("Scelta (1/2, Invio = 1): ").strip() or '1'
        if modo == '1':
            while True:
                t = input("Rete da annunciare (Invio = 0.0.0.0/0, la default): ").strip() or '0.0.0.0/0'
                try:
                    reti = parse_reti(t)
                    break
                except ValueError as e:
                    print(f"❌ Rete non valida: {e}")
            nuove = [f"route {r}" for r in reti if f"route {r}" not in blocco]
        elif modo == '2':
            nuove = [] if 'default-information originate' in blocco else ['default-information originate']
        else:
            print('Scelta non valida: nessuna modifica.')
            return
    else:
        ha = _si("Il router ha già una default sua (statica nello startup o imparata da BGP)? (s/N): ")
        riga = 'default-information originate' + ('' if ha else ' always')
        if riga in blocco:
            nuove = []
        else:
            togli = {
                k for k in _indici_nodo(vecchie, _inizio_blocco(vecchie, rx))
                if vecchie[k].strip().startswith('default-information originate')
            }
            vecchie = [l for k, l in enumerate(vecchie) if k not in togli]
            nuove = [riga]
        if not ha:
            note.append("'always' = OSPF annuncia la default anche se il router non ne ha una.")
    if not nuove:
        print(f"{src}: è già tutto presente in router {proto}, niente da fare.")
        return
    righe = _inserisci_nel_blocco(vecchie, rx, nuove)
    _applica_modifiche(
        base_path,
        {rel: (_righe_file(os.path.join(base_path, rel)), righe)},
        f"Default route in {nome_p} su {src}",
        note
    )


def assegna_resolv_conf(base_path):
    """Interattivo per assegnare un file `resolv.conf` a un singolo dispositivo."""
    try:
        dir_items = [
            d for d in os.listdir(base_path)
            if os.path.isdir(os.path.join(base_path, d)) and not d.startswith('.')
        ]
        startup_files = []
        for fn in os.listdir(base_path):
            if fn.endswith('.startup') and os.path.isfile(os.path.join(base_path, fn)):
                startup_files.append(os.path.splitext(fn)[0])
        items = sorted(list(dict.fromkeys(dir_items + startup_files)))
    except Exception:
        print('Errore leggendo la cartella del laboratorio.')
        return

    if not items:
        print('Nessun dispositivo trovato nella cartella del lab.')
        return

    print_menu('Dispositivi trovati nel lab:', items)

    sel = input('Seleziona il dispositivo (numero o nome) o premi INVIO per annullare: ').strip()
    if not sel:
        print('Operazione annullata.')
        return

    target = None
    if sel.isdigit():
        idx = int(sel) - 1
        if 0 <= idx < len(items):
            target = items[idx]
    else:
        if sel in items:
            target = sel

    if not target:
        print('Selezione non valida.')
        return

    device_dir = os.path.join(base_path, target)
    os.makedirs(device_dir, exist_ok=True)
    etc_dir = os.path.join(device_dir, 'etc')
    os.makedirs(etc_dir, exist_ok=True)
    dest_path = os.path.join(etc_dir, 'resolv.conf')

    available_sources = []
    for d in items:
        src = os.path.join(base_path, d, 'etc', 'resolv.conf')
        if os.path.isfile(src):
            available_sources.append((d, src))
    choice = '1'

    try:
        if choice == '1':
            candidate_ns = []
            for d in items:
                if not os.path.isfile(os.path.join(base_path, d, 'etc', 'bind', 'named.conf')):
                    continue
                for line in _leggi_righe(os.path.join(base_path, f"{d}.startup")):
                    m = re.match(r'\s*ip\s+a(?:ddr(?:ess)?)?\s+add\s+(\S+)\s+dev\s+(\S+)', line)
                    if m and m.group(2) != 'lo':
                        candidate_ns.append((d, m.group(1).split('/')[0]))
                        break

            if candidate_ns:
                cand_items = [f"{d} - {ip}" for (d, ip) in candidate_ns]
                print_menu(
                    'Dispositivi candidati come nameserver:',
                    cand_items,
                    extra_options=[('M', 'Inserisci manualmente un IP')]
                )
                selns = input('Seleziona il nameserver (numero) o M per manuale, INVIO per annullare: ').strip()
                if not selns:
                    print('Operazione annullata.')
                    return
                if selns.lower() == 'm':
                    manual = input_non_vuoto("Inserisci l'IP del nameserver (es. 10.0.0.1): ").strip()
                    try:
                        ipaddress.ip_address(manual)
                        ns_ip = manual
                    except Exception:
                        print('IP non valido. Nessuna modifica effettuata.')
                        return
                else:
                    if not selns.isdigit():
                        print('Selezione non valida.')
                        return
                    idx = int(selns) - 1
                    if not (0 <= idx < len(candidate_ns)):
                        print('Selezione non valida.')
                        return
                    ns_ip = candidate_ns[idx][1]
            else:
                print('Nessun IP candidato trovato nelle cartelle dei dispositivi.')
                manual = input_non_vuoto("Inserisci l'IP del nameserver (es. 10.0.0.1): ").strip()
                try:
                    ipaddress.ip_address(manual)
                    ns_ip = manual
                except Exception:
                    print('IP non valido. Nessuna modifica effettuata.')
                    return

            try:
                with open(dest_path, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(f"nameserver {ns_ip}\n")
                print(f"✅ Wrote {dest_path} with nameserver {ns_ip}")
            except Exception as e:
                print('Errore scrivendo il file:', e)

        elif choice == '2':
            print("Inserisci il contenuto di resolv.conf. Termina con una linea contenente solo '.'")
            lines = []
            while True:
                try:
                    ln = input()
                except EOFError:
                    break
                if ln.strip() == '.':
                    break
                lines.append(ln)
            if not lines:
                print('Nessun contenuto inserito. Nessuna modifica effettuata.')
            else:
                with open(dest_path, 'w', encoding='utf-8', newline='\n') as f:
                    f.write('\n'.join(lines).rstrip() + '\n')
                print(f"✅ Contenuto scritto in {dest_path}")

        elif choice == '3' and available_sources:
            src_items = [d for (d, p) in available_sources]
            print_menu('Dispositivi con resolv.conf disponibile:', src_items)
            src_sel = input('Seleziona il dispositivo sorgente (numero) o INVIO per annullare: ').strip()
            if not src_sel:
                print('Operazione annullata.')
                return
            if not src_sel.isdigit():
                print('Selezione non valida.')
                return
            sidx = int(src_sel) - 1
            if not (0 <= sidx < len(available_sources)):
                print('Selezione non valida.')
                return
            src_path = available_sources[sidx][1]
            try:
                shutil.copyfile(src_path, dest_path)
                print(f"✅ Copiato {src_path} -> {dest_path}")
            except Exception as e:
                print('Errore copiando il file:', e)
        else:
            print('Scelta non valida o nessuna sorgente disponibile.')
    except Exception as e:
        print("Errore durante l'impostazione di resolv.conf:", e)


def aggiungi_loopback_menu(base_path, routers):
    """Aggiunge una loopback ad un dispositivo."""
    print('\n--- Aggiungi loopback ad un dispositivo ---')
    router_names = list(routers.keys()) if routers else []
    startup_devices = []
    try:
        for fn in os.listdir(base_path):
            if fn.endswith('.startup'):
                startup_devices.append(fn[:-8])
    except Exception:
        pass

    only_startup = [d for d in startup_devices if d not in router_names]
    items = []
    for r in router_names:
        asn = routers.get(r, {}).get('asn', '')
        items.append(f"{r} (router, ASN: {asn})")
    for d in only_startup:
        items.append(f"{d} (device)")

    if not items:
        print('Nessun dispositivo trovato nella cartella del lab.')
        return

    print_menu('Seleziona il dispositivo su cui aggiungere la loopback:', items)
    sel = input('Seleziona il dispositivo (numero o nome, vuoto per annullare): ').strip()
    if not sel:
        print('Operazione annullata.')
        return

    target = None
    if sel.isdigit():
        idx = int(sel) - 1
        if 0 <= idx < len(items):
            if idx < len(router_names):
                target = router_names[idx]
            else:
                target = only_startup[idx - len(router_names)]
        else:
            print('Selezione non valida.')
            return
    else:
        if sel in router_names or sel in only_startup:
            target = sel
        else:
            print('Selezione non valida.')
            return

    typ = 'r' if target in router_names else 'd'
    if typ.startswith('r'):
        if not target or target not in routers:
            target = select_router(routers, prompt='Seleziona il router a cui aggiungere la loopback:')
            if not target:
                print('Operazione annullata.')
                return
        ip_only = valida_ip_senza_cidr('IP loopback (es. 1.2.3.4): ')
        ipcidr = ip_only + '/32'
        routers.setdefault(target, {}).setdefault('loopbacks', [])
        if ipcidr in routers[target]['loopbacks']:
            print('⚠️ Loopback già presente nei dati del router.')
        else:
            routers[target]['loopbacks'].append(ipcidr)
        startup = os.path.join(base_path, f"{target}.startup")
        try:
            lines = []
            if os.path.exists(startup):
                with open(startup, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            lb_line = f"ip address add {ipcidr} dev lo\n"
            if not any(l.strip() == lb_line.strip() for l in lines):
                insert_idx = None
                for i, l in enumerate(lines):
                    if re.match(r'^\s*systemctl start\b', l):
                        insert_idx = i
                        break
                if insert_idx is None:
                    if lines and not lines[-1].endswith('\n'):
                        lines[-1] = lines[-1] + '\n'
                    lines.append(lb_line)
                else:
                    lines.insert(insert_idx, lb_line)
                with open(startup, 'w', encoding='utf-8', newline='\n') as f:
                    f.writelines(lines)
        except Exception:
            print('⚠️ Impossibile aggiornare lo startup del router (file non trovato).')
        fpath = os.path.join(base_path, target, 'etc', 'frr', 'frr.conf')
        if os.path.exists(fpath):
            protos = routers.get(target, {}).get('protocols', [])
            if 'ospf' in protos:
                area = routers.get(target, {}).get('ospf_area') or input_area(
                    'Area OSPF per annuncio della loopback (es. 0.0.0.0): ', default='0.0.0.0'
                )
                insert_lines_into_protocol_block(fpath, proto='ospf', asn=None, lines=[f"network {ipcidr} area {area}"])
            if 'rip' in protos:
                insert_lines_into_protocol_block(fpath, proto='rip', asn=None, lines=[f"network {ipcidr}"])
            try:
                add_ibgp_loopback_neighbors(base_path, routers)
            except Exception:
                pass
            print(f"\n\n✅ Loopback {ipcidr} aggiunta a router {target} (startup aggiornato).\n")
        else:
            print(f"⚠️ frr.conf non trovato per {target}; è stata aggiornata solo la startup (se esistente).")
        return

    ip_only = valida_ip_senza_cidr('\nIP loopback (es. 1.2.3.4): ')
    ipcidr = ip_only + '/32'
    startup = os.path.join(base_path, f"{target}.startup")
    try:
        lines = []
        if os.path.exists(startup):
            with open(startup, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        lb_line = f"ip address add {ipcidr} dev lo\n"
        if any(l.strip() == lb_line.strip() for l in lines):
            print(f'⚠️ Loopback {ipcidr} già presente nello startup di {target}.')
        else:
            insert_idx = None
            for i, l in enumerate(lines):
                if re.match(r'^\s*systemctl start\b', l):
                    insert_idx = i
                    break
            if insert_idx is None:
                if lines and not lines[-1].endswith('\n'):
                    lines[-1] = lines[-1] + '\n'
                lines.append(lb_line)
            else:
                lines.insert(insert_idx, lb_line)
            with open(startup, 'w', encoding='utf-8', newline='\n') as f:
                f.writelines(lines)
            print(f"✅ Loopback {ipcidr} aggiunta a {target} (startup).")
    except Exception as e:
        print('Errore aggiornando lo startup:', e)


def _chiedi_reti_cpp(routers):
    """Reti per la prefix-list in uscita (Customer-Provider-Peer)."""
    while True:
        s = input('> ').strip()
        if not s:
            return []
        reti = []
        for tok in s.replace(',', ' ').split():
            try:
                if '/' in tok:
                    i = ipaddress.ip_interface(tok)
                    rete, indirizzo = str(i.network), i.ip != i.network.network_address
                else:
                    ipaddress.ip_address(tok)
                    rete, indirizzo = _rete_di_ip(tok, routers), True
            except ValueError:
                print(f"❌ '{tok}' non è una rete valida (es. 20.0.0.0/24). Riscrivi la risposta.")
                break
            if rete is None:
                print(f"❌ Manca la maschera in '{tok}' (es. 20.0.0.0/24). Riscrivi la risposta.")
                break
            if indirizzo and input(
                f"{tok} è l'indirizzo di un router, non una rete. Intendevi {rete}? (S/n): "
            ).strip().lower().startswith('n'):
                print("Riscrivi la risposta.")
                break
            if rete not in reti:
                reti.append(rete)
        else:
            return reti


def aggiungi_customer_provider_wizard(base_path, routers):
    print("\n=== Configurazione Customer-Provider ===")
    target = select_router(routers, prompt="Quale router stiamo configurando? ")
    if not target:
        return

    if "bgp" not in routers.get(target, {}).get("protocols", []):
        print(f"⚠️ Il router {target} non ha BGP abilitato.")
        return

    print(f"\nSeleziona il Neighbor (vicino) di {target}:")
    neigh_name = select_router(routers, prompt="Router vicino:")

    neigh_ip = None
    neigh_asn = None

    if not neigh_name:
        neigh_name = input("Nome del vicino (o invio per uscire): ").strip()
        if not neigh_name:
            return
        neigh_ip = valida_ip_senza_cidr("Inserisci IP del vicino: ")
        neigh_asn = input_asn("ASN del vicino: ")
    else:
        neigh_asn = routers[neigh_name].get('asn')
        ifaces = routers[neigh_name].get('interfaces', [])
        valid_ips = []
        for iface in ifaces:
            ip_cidr = iface.get('ip')
            if ip_cidr:
                valid_ips.append(ip_cidr.split('/')[0])

        if not valid_ips:
            print(f"⚠️ Nessun IP trovato per {neigh_name}.")
            neigh_ip = valida_ip_senza_cidr("Inserisci IP del vicino manualmente: ")
        elif len(valid_ips) == 1:
            neigh_ip = valid_ips[0]
            print(f"✅ IP rilevato per {neigh_name}: {neigh_ip}")
        else:
            print(f"\nIl router {neigh_name} ha più indirizzi IP. Seleziona quello verso {target}:")
            print_menu("IP Disponibili:", valid_ips)
            while True:
                sel = input("Seleziona numero (o premi invio per il primo): ").strip()
                if not sel:
                    neigh_ip = valid_ips[0]
                    break
                if sel.isdigit():
                    idx = int(sel) - 1
                    if 0 <= idx < len(valid_ips):
                        neigh_ip = valid_ips[idx]
                        break
                print("Selezione non valida.")

    if not neigh_ip:
        return

    fpath = os.path.join(base_path, target, "etc", "frr", "frr.conf")
    if not os.path.exists(fpath):
        print(f"File {fpath} non trovato.")
        return

    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()

    if f"neighbor {neigh_ip} remote-as" not in content:
        print(f"Neighbor {neigh_ip} non presente. Lo aggiungo.")
        lines = [
            f"neighbor {neigh_ip} remote-as {neigh_asn}",
            f"neighbor {neigh_ip} description {neigh_name}"
        ]
        if not insert_lines_into_protocol_block(fpath, proto='bgp', asn=None, lines=lines):
            print("❌ Errore nell'inserimento del neighbor.")
            return

    print("\nQual è la relazione economica?")
    print("1) PROVIDER (Il vicino è il mio provider)")
    print("2) CUSTOMER (Il vicino è il mio cliente)")
    print("3) PEER (Siamo alla pari)")
    rel_choice = input("Scelta (1-3): ").strip()

    if rel_choice == '1':
        rel_type = "provider"
    elif rel_choice == '2':
        rel_type = "customer"
    elif rel_choice == '3':
        rel_type = "peer"
    else:
        print("Scelta non valida.")
        return

    pl_in = f"{rel_type}_{neigh_name}_in"
    pl_out = f"{rel_type}_{neigh_name}_out"
    lines_to_append = []

    if rel_type in ("provider", "peer"):
        lines_to_append.append(f"ip prefix-list {pl_in} permit any")
        vietate = "DEI tuoi PEER" if rel_type == "provider" else "DEL tuo PROVIDER"
        proprie = _analizza_frr(_leggi_righe(fpath))['bgp_networks']

        if proprie:
            print(f"\nReti annunciate da {target}: {', '.join(_reti_del_router(target, routers, proprie))}")
            print("(nelle soluzioni del corso i link verso provider e peer non si annunciano a provider e peer;")
            print(" le reti proprie e i link verso i clienti si')")
        print(f"\nInserisci le TUE reti da annunciare al {rel_type} (separate da virgola):")
        print(f"⚠️  ATTENZIONE: NON inserire le reti {vietate}!")
        reti_out = _chiedi_reti_cpp(routers)

        print(f"\nInserisci le reti dei tuoi CLIENTI da annunciare al {rel_type} (separate da virgola, o invio per nessuna):")
        print(f"⚠️  ATTENZIONE: NON inserire le reti {vietate}!")
        reti_out += [r for r in _chiedi_reti_cpp(routers) if r not in reti_out]

        lines_to_append += [f"ip prefix-list {pl_out} permit {r}" for r in reti_out]
        if not reti_out:
            print(f"⚠️  Nessuna rete: {target} non annuncerà niente a {neigh_name}.")

    elif rel_type == "customer":
        lines_to_append.append(f"ip prefix-list {pl_in} permit any")
        lines_to_append.append(f"ip prefix-list {pl_out} permit any")

    neigh_lines = [
        "",
        f"neighbor {neigh_ip} prefix-list {pl_in} in",
        f"neighbor {neigh_ip} prefix-list {pl_out} out"
    ]
    if insert_lines_into_protocol_block(fpath, proto='bgp', asn=None, lines=neigh_lines):
        try:
            with open(fpath, 'a', encoding='utf-8', newline='\n') as f:
                f.write('\n')
                for l in lines_to_append:
                    f.write(l + '\n')
                f.write('\n')
        except Exception as e:
            print(f"❌ Errore scrivendo le prefix-list: {e}")
            return
        print(f"✅ Configurazione {rel_type.upper()} applicata su {target} verso {neigh_name}.")
    else:
        print(f"❌ Errore applicando la configurazione neighbor su {target}.")


def aggiungi_redistribuzione_bgp_igp(base_path, routers):
    print("\n=== Ridistribuzione BGP -> IGP (Route-map) ===")
    candidates = {}
    for rname, rdata in routers.items():
        protos = rdata.get('protocols', [])
        if 'bgp' in protos and ('rip' in protos or 'ospf' in protos):
            candidates[rname] = rdata

    if not candidates:
        print("Nessun router con BGP e (RIP o OSPF) trovato.")
        return

    target = select_router(candidates, prompt="Seleziona router:")
    if not target:
        return

    while True:
        neigh_ip = input("Inserisci la RETE di collegamento con il neighbor BGP (es. 50.7.1.0/24): ").strip()
        if not neigh_ip:
            print("Inserisci un valore.")
            continue
        try:
            net = ipaddress.ip_network(neigh_ip, strict=False)
            prefix = str(net)
            break
        except ValueError:
            print("❌ Formato non valido. Inserisci IP o CIDR (es. 10.0.0.1 o 10.0.0.0/24)")

    global_conf = [
        f"ip prefix-list myNeighbors permit {prefix} le 32",
        "",
        "route-map eBGP permit 10",
        "    match ip next-hop prefix-list myNeighbors",
        ""
    ]

    fpath = os.path.join(base_path, target, "etc", "frr", "frr.conf")
    if not os.path.exists(fpath):
        print(f"File {fpath} non trovato.")
        return

    try:
        with open(fpath, 'a', encoding='utf-8', newline='\n') as f:
            f.write("\n\n")
            for line in global_conf:
                f.write(line + "\n")
    except Exception as e:
        print(f"❌ Errore scrivendo su {fpath}: {e}")
        return

    protos = candidates[target]['protocols']
    redist_cmd = "redistribute bgp route-map eBGP"

    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            cur = f.readlines()
        kept = [l for l in cur if l.strip() != 'redistribute bgp']
        if len(kept) != len(cur):
            with open(fpath, 'w', encoding='utf-8', newline='\n') as f:
                f.writelines(kept)
    except Exception as e:
        print(f"⚠️ Impossibile ripulire 'redistribute bgp' esistente: {e}")

    applied = False
    if 'rip' in protos:
        if insert_lines_into_protocol_block(fpath, proto='rip', lines=['', redist_cmd]):
            print(f"✅ Aggiunto '{redist_cmd}' a router rip.")
            applied = True

    if 'ospf' in protos:
        if insert_lines_into_protocol_block(fpath, proto='ospf', lines=['', redist_cmd]):
            print(f"✅ Aggiunto '{redist_cmd}' a router ospf.")
            applied = True

    if applied:
        print(f"✅ Configurazione completata su {target}.")
    else:
        print("❌ Impossibile applicare la ridistribuzione (protocollo IGP non trovato nel file?).")


def _imposta_redistribute_bgp(base_path, routers, attiva):
    """Toglie (attiva=False) o rimette (attiva=True) 'redistribute bgp' nei blocchi OSPF/RIP."""
    candidati = {
        k: v for k, v in routers.items()
        if 'bgp' in v.get('protocols', []) and ({'ospf', 'rip'} & set(v.get('protocols', [])))
    }
    if not candidati:
        print('Nessun router con BGP e OSPF/RIP.')
        return
    target = select_router(candidati, prompt='Seleziona il router:')
    if not target:
        print('Operazione annullata.')
        return
    fpath = os.path.join(base_path, target, 'etc', 'frr', 'frr.conf')
    out, blocco, presente = [], None, set()
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
        out.append(l)
    protos = [p for p in ('ospf', 'rip') if p in candidati[target]['protocols']]
    if attiva:
        mancanti = [p for p in protos if p not in presente]
        for p in mancanti:
            insert_lines_into_protocol_block(fpath, proto=p, asn=None, lines=['redistribute bgp'])
        print(
            f"✅ {target}: redistribute bgp "
            + (f"aggiunto in {', '.join(mancanti)}." if mancanti else "era già presente.")
        )
    else:
        _scrivi_righe(fpath, out)
        print(
            f"✅ {target}: redistribute bgp "
            + (f"tolto da {', '.join(sorted(presente))}." if presente else "non era presente.")
        )
    routers[target]['igp_redistribute_bgp'] = attiva


def menu_ridistribuzione(base_path, routers):
    while True:
        print_menu('=== Ridistribuzione BGP -> IGP ===', [
            "Togli 'redistribute bgp' da un router (il testo la chiede solo su alcuni router di confine)",
            "Rimetti 'redistribute bgp' su un router",
            "Redistribute bgp con route-map eBGP (solo rotte imparate via eBGP)"
        ], extra_options=[('0', 'Torna indietro')])
        c = input('Seleziona (numero): ').strip()
        if c == '0':
            return
        if c == '1':
            _imposta_redistribute_bgp(base_path, routers, attiva=False)
        elif c == '2':
            _imposta_redistribute_bgp(base_path, routers, attiva=True)
        elif c == '3':
            aggiungi_redistribuzione_bgp_igp(base_path, routers)
        else:
            print('Scelta non valida.')


def imposta_auto_cost(base_path):
    """Opzioni 10: 'auto-cost reference-bandwidth 100' su tutti i router OSPF di un AS."""
    isole = isole_ospf(base_path)
    if not isole:
        print('Nessun router OSPF nel lab.')
        return
    items = []
    for et, rs, cfgs in isole:
        costi = [f"{r} {c}" for r in rs for c in cfgs[r]['costi']]
        con = [r for r in rs if cfgs[r]['auto_cost']]
        stato = (
            'auto-cost già su tutti' if len(con) == len(rs)
            else f"auto-cost su {len(con)}/{len(rs)}" if con else 'senza auto-cost'
        )
        items.append(f"{et}: {', '.join(rs)}  [{stato}]" + (f"  costi espliciti: {', '.join(costi)}" if costi else ''))
    print_menu('Router OSPF del lab (per AS):', items)
    s = input('Su quale AS? (numero, invio = annulla): ').strip()
    if not s.isdigit() or not 1 <= int(s) <= len(isole):
        print('Operazione annullata.')
        return
    et, rs, cfgs = isole[int(s) - 1]
    file_di = {r: os.path.join(base_path, r, 'etc', 'frr', 'frr.conf') for r in rs}
    togli_vecchie = lambda r: _rimuovi_righe(file_di[r], lambda l: l.strip().startswith('auto-cost reference-bandwidth'))
    if all(cfgs[r]['auto_cost'] for r in rs):
        if input(f"{et} ha già 'auto-cost reference-bandwidth' su tutti i router. Toglierlo? (s/N): ").strip().lower() == 's':
            for r in rs:
                togli_vecchie(r)
            print(f"✅ Tolto da {', '.join(rs)}: costo predefinito di nuovo 10000.")
        return
    print(f"Aggiungo 'auto-cost reference-bandwidth 100' a {len(rs)} router di {et}: {', '.join(rs)}.")
    print("Effetto: costo predefinito di ogni interfaccia = 100 / 10 Mbit = 10 (oggi è 10000).")
    print("I costi che hai scritto tu (Opzioni 1) non cambiano.")
    if input('Confermi? (S/n): ').strip().lower() == 'n':
        print('Operazione annullata.')
        return
    for r in rs:
        togli_vecchie(r)
        insert_lines_into_protocol_block(file_di[r], proto='ospf', lines=['auto-cost reference-bandwidth 100'])
    print("✅ Fatto. Controlla con la GUI (show ip ospf interface: 'Cost: 10') e con Test -> Verifica percorso.")


def menu_opzioni_laboratorio(base_path, routers):
    """Sottomenu per opzioni avanzate del laboratorio."""
    while True:
        items = [
            'Imposta costo OSPF',
            'Aggiungi Policies BGP',
            'Aggiungi interfaccia loopback',
            "Ridistribuzione BGP -> IGP (togli/rimetti 'redistribute bgp', route-map eBGP)",
            'Assegna un resolver ad un dispositivo',
            "Aggiungi network BGP (aggregato dell'AS, reti interne, 0.0.0.0/0)",
            'Aggiungi sessioni iBGP (full mesh tra i router BGP dello stesso AS)',
            "Riepilogo configurazione (per controllare il testo dell'esercizio)",
            'Aggiungi delega DNS sul root (es. com -> dns.com)',
            'Costi OSPF predefiniti a 10 (auto-cost reference-bandwidth 100 su un AS)',
            'Modifica un dispositivo (IP, LAN, gateway, protocolli, AS, righe dei file)',
            'Default route (BGP verso un neighbor, RIP, OSPF)'
        ]
        print_menu(
            f'=== Opzioni Laboratorio ({os.path.basename(os.path.normpath(base_path))}) ===',
            items, extra_options=[('0', 'Torna indietro')]
        )
        choice = input('Seleziona (numero): ').strip()
        if choice == '0':
            break
        if choice == '1':
            assegna_costo_interfaccia(base_path, routers)
        elif choice == '2':
            policies_menu(base_path, routers)
        elif choice == '3':
            aggiungi_loopback_menu(base_path, routers)
        elif choice == '4':
            menu_ridistribuzione(base_path, routers)
        elif choice == '5':
            assegna_resolv_conf(base_path)
        elif choice == '6':
            aggiungi_network_bgp(base_path, routers)
        elif choice == '7':
            aggiungi_ibgp_full_mesh(base_path, routers)
        elif choice == '8':
            riepilogo_configurazione(base_path, routers)
        elif choice == '9':
            aggiungi_delega_dns(base_path)
        elif choice == '10':
            imposta_auto_cost(base_path)
        elif choice == '11':
            modifica_dispositivo_menu(base_path, routers)
        elif choice == '12':
            default_route_menu(base_path, routers)
        else:
            print('Scelta non valida, riprova.')


def menu_post_creazione(base_path, routers):
    while True:
        items = [
            'Genera file XML aggiornato',
            'Testa Funzionamento (PING)',
            'Opzioni Laboratorio'
        ]
        print_menu('-------------- Menu post-creazione --------------', items, extra_options=[('0', 'Termina Programma')])
        print('\n--------------------------------------------------')
        print('---- Programma realizzato da sciro24 (Github) ----')
        print('-------- versione portabile modificata -----------')
        print('--------------------------------------------------\n')

        choice = input('Seleziona (numero): ').strip()
        if choice == '0':
            break
        if choice == '1':
            try:
                xmlpath = rebuild_lab_metadata_and_export(base_path)
                if xmlpath:
                    print(f"✅ XML rigenerato: {xmlpath}")
                else:
                    print("❌ Rigenerazione XML non riuscita.")
            except Exception as e:
                print('Errore durante la rigenerazione XML:', e)
        elif choice == '2':
            try:
                ips = collect_lab_ips(base_path, routers)
                if not ips:
                    print('Nessun IP trovato nel lab. Controlla i file .startup o le interfacce dei router.')
                else:
                    cmd = generate_ping_oneliner(ips)
                    print('\n=== Comando ping generato (copia/incolla sulle macchine del lab) ===\n\n')
                    print(cmd)
                    print('\n\n=== Fine comando ===\n')
            except Exception as e:
                print('Errore generando il comando ping:', e)
        elif choice == '3':
            menu_opzioni_laboratorio(base_path, routers)
        else:
            print('Scelta non valida, riprova.')


def scegli_lab(base):
    """Fa scegliere un lab esistente in `base` o tramite percorso."""
    try:
        labs = sorted(d for d in os.listdir(base) if os.path.isfile(os.path.join(base, d, 'lab.conf')))
    except OSError:
        labs = []
    if labs:
        print_menu(f'Lab trovati in {base}:', labs)
        prompt = 'Numero del lab (oppure percorso della cartella, vuoto per annullare): '
    else:
        print(f"Nessun lab trovato in {base}.")
        prompt = 'Percorso della cartella del lab (vuoto per annullare): '
    while True:
        s = input(prompt).strip().strip('"')
        if not s:
            print('Operazione annullata.')
            return None
        if s.isdigit() and labs and 1 <= int(s) <= len(labs):
            return os.path.join(base, labs[int(s) - 1])
        for cand in (s, os.path.join(base, s)):
            if os.path.isfile(os.path.join(cand, 'lab.conf')):
                return cand
        print(f"❌ Nessun lab (cartella con lab.conf) in '{s}'. Riprova.")


def opzioni_laboratorio_menu(base):
    """Opzioni su un lab già creato: chiede la cartella e apre il menu Opzioni."""
    target = scegli_lab(base)
    if not target:
        return
    correggi_nomi_lab(target)
    xmlpath = os.path.join(target, os.path.basename(os.path.normpath(target)) + '.xml')
    try:
        if not os.path.exists(xmlpath):
            xmlpath = rebuild_lab_metadata_and_export(target)
            if not xmlpath:
                print('Impossibile leggere i dati del lab.')
                return
        _, routers_meta, _, _, _ = load_lab_from_xml(xmlpath)
    except Exception as e:
        print('Errore caricando il lab:', e)
        return
    menu_opzioni_laboratorio(target, routers_meta)