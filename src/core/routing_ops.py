"""
src/core/routing_ops.py
Operazioni del menu Opzioni Laboratorio: policy BGP, costi OSPF, iBGP, loopback, ridistribuzione, DNS.
"""
import ipaddress
import os

from .analyzer import (
    leggi_dispositivi,
    _analizza_frr,
    collect_lab_ips,
    generate_ping_oneliner,
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
    _esegui_piano,
    _leggi_righe,
    _righe_file,
    insert_lines_into_protocol_block,
)
from .net_frr import (
    _neighbor_presente,
    _rete_di_ip,
    _reti_del_router,
)
from . import operazioni
from .stato import leggi_stato
from .persistence import (
    correggi_nomi_lab,
    rebuild_lab_metadata_and_export,
)


def routers_dai_file(base_path):
    """Router del lab ricavati dai file (lettore unico), non dall'XML: protocolli, AS, interfacce."""
    return operazioni.routers_dello_stato(leggi_stato(base_path))


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
    stato = leggi_stato(base_path)
    attuale = next((it['costo'] for it in _costi_interfacce(stato, target) if it['dev'] == iface), None)
    print(f"Costo attuale di {iface}: {attuale if attuale else 'quello predefinito (nessun costo scritto)'}")
    while True:
        costo = input_int(f'Costo OSPF per {iface} (da 1 a 65535; 0 = togli il costo scritto): ', 0)
        if costo <= 65535:
            break
        print('Il costo massimo è 65535.')
    if costo == 0:
        _esegui_piano(base_path, operazioni.calcola_togli_costo_ospf(stato, target, iface))
    else:
        _esegui_piano(base_path, operazioni.calcola_costo_ospf(stato, target, iface, costo))


def _costi_interfacce(stato, router):
    """[{'dev', 'costo'}] del router: il costo scritto nel frr.conf (None se non c'è)."""
    d = stato['dispositivi'].get(router) or {}
    interfacce = ((d.get('frr') or {}).get('interfacce') or {})
    return [{'dev': it['dev'], 'costo': (interfacce.get(it['dev']) or {}).get('costo_ospf')} for it in d.get('interfacce', [])]


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
    stato = leggi_stato(base_path)
    info = operazioni.opzioni_network_bgp(stato, target)[target]
    proposta = info['proposta']
    reti = None
    while reti is None:
        s = input(f"Reti da annunciare in BGP, separate da virgola (invio = {', '.join(proposta)}"
                  + ("; T = togli una network, C = cambia una network" if info['presenti'] else '') + "): ").strip()
        if s.lower() in ('t', 'c') and info['presenti']:
            _cambia_network_bgp(base_path, stato, target, info['presenti'], togli=s.lower() == 't')
            return
        if not s:
            reti = list(proposta)
            continue
        try:
            reti = parse_reti(s)
        except ValueError as e:
            print(f"❌ Rete non valida: {e}")
    if not [r for r in reti if r not in info['presenti']]:
        print('Tutte le reti indicate sono già annunciate.')
        return
    coperte = operazioni.reti_coperte(stato, target, reti)
    togli = False
    if coperte:
        ans = input(
            f"Le reti {', '.join(coperte)} sono già contenute nell'aggregato. "
            f"Toglierle da BGP e annunciare solo l'aggregato? (s/N): "
        ).strip().lower()
        togli = ans.startswith('s')
    _esegui_piano(base_path, operazioni.calcola_network_bgp(stato, target, reti, togli_coperte=togli))


def _cambia_network_bgp(base_path, stato, router, presenti, togli):
    """Toglie o cambia una network già annunciata in BGP (la modifica passa anche in prefix-list e
    access-list se nessun altro router la annuncia)."""
    presenti = sorted(presenti)
    print_menu(f"Network BGP annunciate da {router}:", presenti)
    s = input(f"Quale {'togliere' if togli else 'cambiare'} (numero o rete, Invio = annulla): ").strip()
    if not s:
        print('Annullato.')
        return
    rete = presenti[int(s) - 1] if s.isdigit() and 1 <= int(s) <= len(presenti) else s
    nuova = None
    if not togli:
        nuova = input(f"Nuova rete al posto di {rete} (Invio = annulla): ").strip()
        if not nuova:
            print('Annullato.')
            return
    try:
        piano = operazioni.calcola_network_bgp(stato, router, [rete], azione='rimuovi' if togli else 'modifica', nuova_rete=nuova)
    except operazioni.ErroreOperazione as e:
        print(e)
        return
    _esegui_piano(base_path, piano)


def menu_dns(base_path):
    """Opzioni 9: delega sul root e, su un server DNS già creato, zona nuova, record A, ricorsione."""
    while True:
        print_menu('=== DNS ===', ['Delega una zona sul root (es. com -> dns.com)', 'Aggiungi una zona a un server DNS',
                                   'Aggiungi, cambia o togli un record A', 'Ricorsione (resolver) e dnssec-validation no'],
                   extra_options=[('0', 'Torna indietro')])
        c = input('Seleziona (numero): ').strip()
        if c == '0' or not c:
            return
        if c == '1':
            aggiungi_delega_dns(base_path)
        elif c in ('2', '3', '4'):
            _dns_server(base_path, c)
        else:
            print('Scelta non valida.')


def _dns_server(base_path, c):
    stato = leggi_stato(base_path)
    server = sorted(n for n, d in stato['dispositivi'].items() if d.get('dns'))
    if not server:
        print('Il lab non ha server DNS.')
        return
    print_menu('Server DNS:', server)
    s = input('Seleziona (numero o nome, Invio = annulla): ').strip()
    nome = server[int(s) - 1] if s.isdigit() and 1 <= int(s) <= len(server) else (s if s in server else None)
    if not nome:
        print('Annullato.')
        return
    info = operazioni.opzioni_dns(stato, nome)
    print(f"{nome} ({info['ip'] or 'senza IP'}): zone " + (', '.join(f"{z['zona']} ({z['tipo']})" for z in info['zone']) or 'nessuna'))
    try:
        if c == '2':
            zona = input('Zona da aggiungere (es. com; Invio = annulla): ').strip()
            if not zona:
                print('Annullato.')
                return
            rec = {}
            while True:
                h = input('Record A da mettere subito, nome (es. web; Invio = nessun altro): ').strip()
                if not h:
                    break
                rec[h] = input(f'IP di {h}: ').strip()
            piano = operazioni.calcola_zona_dns(stato, nome, zona, rec)
        elif c == '3':
            master = [z['zona'] for z in info['zone'] if z['tipo'] == 'master' and z['zona'] != '.']
            if not master:
                print(f"{nome} non è master di nessuna zona: prima aggiungila (voce 2).")
                return
            for z in info['zone']:
                if z['zona'] in master:
                    print(f"  {z['zona']}: " + (', '.join(f"{r[0]} -> {r[2]}" for r in z['record'] if r[1] == 'A') or 'nessun record A'))
            zona = master[0] if len(master) == 1 else input(f"Zona ({', '.join(master)}): ").strip()
            host = input('Nome (es. web; Invio = annulla): ').strip()
            if not host:
                print('Annullato.')
                return
            ip = input(f'IP di {host} (T = togli i suoi record A): ').strip()
            piano = (operazioni.calcola_record_dns(stato, nome, zona, host, togli=True) if ip.lower() == 't'
                     else operazioni.calcola_record_dns(stato, nome, zona, host, ip))
        else:
            print(f"Adesso: allow-recursion {', '.join(info['ricorsione']) if info['ricorsione'] else 'non scritta'}, "
                  f"dnssec-validation {info['dnssec'] or 'non scritta'}.")
            ric = _si('Fa da resolver (allow-recursion)? (S/n): ', True)
            reti = input('Reti ammesse (es. 10.0.0.0/24; Invio = any): ').strip() if ric else ''
            dn = _si('dnssec-validation no? (S/n): ', True)
            piano = operazioni.calcola_ricorsione_dns(stato, nome, ric, reti, dn)
    except operazioni.ErroreOperazione as e:
        print(e)
        return
    _esegui_piano(base_path, piano)


def aggiungi_delega_dns(base_path):
    """Aggiunge al server root (master per '.') la delega di una zona."""
    print('\n--- Aggiungi delega DNS sul root ---')
    stato = leggi_stato(base_path)
    dns = operazioni.opzioni_delega_dns(stato)
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
    _esegui_piano(base_path, operazioni.calcola_delega_dns(stato, nome, zona, ns, ip))


def aggiungi_ibgp_full_mesh(base_path, routers):
    """Crea le sessioni iBGP mancanti tra tutti i router BGP di uno stesso AS (full mesh)."""
    print("\n--- Aggiungi sessioni iBGP (full mesh nell'AS) ---")
    stato = leggi_stato(base_path)
    candidati = operazioni.opzioni_ibgp(stato)
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
    print("⚠️ Controlla il testo: alcuni esercizi vietano l'iBGP (es. butterfly).")
    _esegui_piano(base_path, operazioni.calcola_ibgp(stato, sel))


def policies_menu(base_path, routers):
    """Sotto-menu per applicare policies BGP ai router del lab."""
    while True:
        routers = routers_dai_file(base_path)    # anche le modifiche fatte dalla GUI o a mano
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

        tipo = {'1': 'prefix_list', '2': 'local_pref', '3': 'med', '4': 'access_list'}[c]
        try:
            piano = operazioni.calcola_policy(
                leggi_stato(base_path), src, neigh_ip, tipo,
                direzione=direz if c == '1' else None,
                reti=reti if c in ('1', '2', '4') else (),
                valore={'2': lp_val if c == '2' else None, '3': m_val if c == '3' else None}.get(c),
                asn_nuovo=nuovo_asn
            )
        except operazioni.ErroreOperazione as e:
            print(e)
            continue
        _esegui_piano(base_path, piano)


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

    try:
        piano = operazioni.calcola_default_originate(leggi_stato(base_path), src, scelti, solo, extra, owner)
    except operazioni.ErroreOperazione as e:
        print(e)
        return
    _esegui_piano(base_path, piano)


def default_route_menu(base_path, routers):
    """Opzioni 12: tutte le default route in un posto solo (BGP, RIP, OSPF)."""
    while True:
        routers = routers_dai_file(base_path)    # anche le modifiche fatte dalla GUI o a mano
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
    stato = leggi_stato(base_path)
    cand = operazioni.opzioni_default_igp(stato, proto)
    if not cand:
        print(f"Nessun router del lab ha il blocco 'router {proto}' in frr.conf.")
        return
    print_menu(f"Router con {nome_p}:", cand)
    s = input("Router (numero o nome, Invio = annulla): ").strip()
    src = cand[int(s) - 1] if s.isdigit() and 1 <= int(s) <= len(cand) else (s if s in cand else None)
    if not src:
        print('Annullato: nessuna modifica.' if not s else 'Router non valido: nessuna modifica.')
        return
    modo, reti, ha = '1', ['0.0.0.0/0'], False
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
        elif modo != '2':
            print('Scelta non valida: nessuna modifica.')
            return
    else:
        ha = _si("Il router ha già una default sua (statica nello startup o imparata da BGP)? (s/N): ")
    _esegui_piano(base_path, operazioni.calcola_default_igp(stato, proto, src, modo, reti, ha))


def _ip_manuale():
    manual = input_non_vuoto("Inserisci l'IP del nameserver (es. 10.0.0.1): ").strip()
    try:
        ipaddress.ip_address(manual)
        return manual
    except ValueError:
        print('IP non valido. Nessuna modifica effettuata.')
        return None


def assegna_resolv_conf(base_path):
    """Interattivo per assegnare un file `resolv.conf` a un singolo dispositivo."""
    try:
        stato = leggi_stato(base_path)
        info = operazioni.opzioni_resolver(stato)
    except Exception:
        print('Errore leggendo la cartella del laboratorio.')
        return
    items = info['dispositivi']
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
    elif sel in items:
        target = sel
    if not target:
        print('Selezione non valida.')
        return

    candidate_ns = info['candidati']
    if candidate_ns:
        print_menu(
            'Dispositivi candidati come nameserver:',
            [f"{d} - {ip}" for (d, ip) in candidate_ns],
            extra_options=[('M', 'Inserisci manualmente un IP'), ('N', 'Togli il resolver (nessun nameserver)')]
        )
        selns = input('Seleziona il nameserver (numero), M per manuale, N per toglierlo, INVIO per annullare: ').strip()
        if not selns:
            print('Operazione annullata.')
            return
        if selns.lower() == 'n':
            _esegui_piano(base_path, operazioni.calcola_resolver(stato, target, ''))
            return
        if selns.lower() == 'm':
            ns_ip = _ip_manuale()
        elif selns.isdigit() and 0 <= int(selns) - 1 < len(candidate_ns):
            ns_ip = candidate_ns[int(selns) - 1][1]
        else:
            print('Selezione non valida.')
            return
    else:
        print('Nessun IP candidato trovato nelle cartelle dei dispositivi.')
        ns_ip = _ip_manuale()
    if ns_ip:
        _esegui_piano(base_path, operazioni.calcola_resolver(stato, target, ns_ip))


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
            target = router_names[idx] if idx < len(router_names) else only_startup[idx - len(router_names)]
        else:
            print('Selezione non valida.')
            return
    elif sel in router_names or sel in only_startup:
        target = sel
    else:
        print('Selezione non valida.')
        return

    stato = leggi_stato(base_path)
    if stato['dispositivi'].get(target, {}).get('tipo') == 'router':
        ip_only = valida_ip_senza_cidr('IP loopback (es. 1.2.3.4): ')
    else:
        ip_only = valida_ip_senza_cidr('\nIP loopback (es. 1.2.3.4): ')
    _esegui_piano(base_path, operazioni.calcola_loopback(stato, target, ip_only))


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

    if f"neighbor {neigh_ip} remote-as" not in '\n'.join(_leggi_righe(fpath)):
        print(f"Neighbor {neigh_ip} non presente: verrà aggiunto.")

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

    reti_out = []
    if rel_type in ("provider", "peer"):
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

    try:
        piano = operazioni.calcola_cpp(leggi_stato(base_path), target, neigh_name, neigh_ip, neigh_asn,
                                       rel_type, reti_out)
    except operazioni.ErroreOperazione as e:
        print(e)
        return
    _esegui_piano(base_path, piano)


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
            ipaddress.ip_network(neigh_ip, strict=False)
            break
        except ValueError:
            print("❌ Formato non valido. Inserisci IP o CIDR (es. 10.0.0.1 o 10.0.0.0/24)")
    try:
        piano = operazioni.calcola_redistribuzione_route_map(leggi_stato(base_path), target, neigh_ip)
    except operazioni.ErroreOperazione as e:
        print(e)
        return
    _esegui_piano(base_path, piano)


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
    _esegui_piano(base_path, operazioni.calcola_redistribuzione(leggi_stato(base_path), target, attiva))


def menu_ridistribuzione(base_path, routers):
    while True:
        routers = routers_dai_file(base_path)    # anche le modifiche fatte dalla GUI o a mano
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
    stato = leggi_stato(base_path)
    gruppi = operazioni.opzioni_auto_cost(stato)
    if not gruppi:
        print('Nessun router OSPF nel lab.')
        return
    items = []
    for g in gruppi:
        rs, con = g['router'], g['con_auto_cost']
        stato_g = (
            'auto-cost già su tutti' if len(con) == len(rs)
            else f"auto-cost su {len(con)}/{len(rs)}" if con else 'senza auto-cost'
        )
        items.append(f"{g['etichetta']}: {', '.join(rs)}  [{stato_g}]"
                     + (f"  costi espliciti: {', '.join(g['costi'])}" if g['costi'] else ''))
    print_menu('Router OSPF del lab (per AS):', items)
    s = input('Su quale AS? (numero, invio = annulla): ').strip()
    if not s.isdigit() or not 1 <= int(s) <= len(gruppi):
        print('Operazione annullata.')
        return
    g = gruppi[int(s) - 1]
    et, rs = g['etichetta'], g['router']
    if len(g['con_auto_cost']) == len(rs):
        if input(f"{et} ha già 'auto-cost reference-bandwidth' su tutti i router. Toglierlo? (s/N): ").strip().lower() == 's':
            _esegui_piano(base_path, operazioni.calcola_auto_cost(stato, et, togli=True))
        return
    print(f"Aggiungo 'auto-cost reference-bandwidth 100' a {len(rs)} router di {et}: {', '.join(rs)}.")
    print("Effetto: tutti i router del gruppo calcolano il costo predefinito allo stesso modo (100 Mbit diviso la")
    print("velocità del link; misurato con Kathará: 1 invece di 10). Controlla con show ip ospf interface.")
    print("I costi che hai scritto tu (Opzioni 1) non cambiano.")
    _esegui_piano(base_path, operazioni.calcola_auto_cost(stato, et))


def _aggiungi_dispositivo(base_path, routers, tipo):
    """Aggiunge un dispositivo con le stesse domande del wizard (nomi e IP del lab già noti)."""
    from .wizard import wizard_dns, wizard_host, wizard_router, wizard_www
    stato = leggi_stato(base_path)
    info = operazioni.opzioni_aggiungi_dispositivo(stato)
    m = info['modello']
    area, stub = info['prima_area_ospf']
    ctx = {'routers': dict(m['routers']), 'hosts': list(m['hosts']), 'wwws': list(m['wwws']),
           'used_ips': set(info['ip']), 'used_names': set(info['nomi']),
           'first_ospf_area': area, 'first_ospf_stub': stub}
    print("(Domande come nella creazione: '<' torna indietro, '<<' ricomincia il dispositivo.)")
    if tipo == 'router':
        prima = set(ctx['routers'])
        wizard_router(len(prima) + 1, ctx)
        nome = next(n for n in ctx['routers'] if n not in prima)
        dati = dict(ctx['routers'][nome], name=nome)
    elif tipo == 'host':
        wizard_host(sum(1 for h in m['hosts'] if not h.get('dns')) + 1, ctx)
        dati = ctx['hosts'][-1]
    elif tipo == 'www':
        wizard_www(len(m['wwws']) + 1, ctx)
        dati = ctx['wwws'][-1]
    else:
        wizard_dns(sum(1 for h in m['hosts'] if h.get('dns')) + 1, ctx)
        dati = ctx['hosts'][-1]
    sessioni, resolver = True, True
    if tipo == 'router' and 'bgp' in dati.get('protocols', []):
        sessioni = _si("Aprire le sessioni BGP con i router BGP sulle sue LAN (da entrambi i lati)? (S/n): ", True)
    if tipo != 'router' and info['resolver']:
        resolver = _si(f"Usare anche qui il resolver del lab ({info['resolver']})? (S/n): ", True)
    try:
        piano = operazioni.calcola_aggiungi_dispositivo(stato, tipo, dati, sessioni_bgp=sessioni, resolver=resolver)
    except operazioni.ErroreOperazione as e:
        print(e)
        return
    _esegui_piano(base_path, piano, routers)


def _togli_dispositivo(base_path, routers):
    from .device_editor import _scegli_dispositivo
    disp = leggi_dispositivi(base_path)
    nome = _scegli_dispositivo(disp, 'Dispositivo da togliere')
    if not nome:
        print('Annullato.')
        return
    stato = leggi_stato(base_path)
    info = operazioni.opzioni_togli_dispositivo(stato, nome)
    togli = True
    if info['neighbor']:
        togli = _si(f"Tolgo anche le righe 'neighbor' che puntano a {nome} su {', '.join(info['neighbor'])}? (S/n): ", True)
    pulisci = True
    if info['gateway_di'] or info['resolver_di']:
        chi = sorted(set(info['gateway_di']) | set(info['resolver_di']))
        pulisci = _si(f"{', '.join(chi)} usa {nome} come gateway o resolver: tolgo anche quelle righe "
                      f"(rotta di default, nameserver, record DNS)? (S/n): ", True)
    _esegui_piano(base_path, operazioni.calcola_togli_dispositivo(
        stato, nome, togli_neighbor=togli, pulisci_riferimenti=pulisci), routers)


def menu_dispositivi(base_path, routers):
    """Opzioni 13: aggiungere o togliere un dispositivo da un lab già creato."""
    while True:
        routers = routers_dai_file(base_path)    # anche le modifiche fatte dalla GUI o a mano
        print_menu('=== Aggiungi o togli un dispositivo ===', [
            'Aggiungi un router', 'Aggiungi un host/PC', 'Aggiungi un server WWW', 'Aggiungi un server DNS',
            'Togli un dispositivo'
        ], extra_options=[('0', 'Torna indietro')])
        c = input('Seleziona (numero): ').strip()
        if c == '0' or not c:
            return
        if c in ('1', '2', '3', '4'):
            _aggiungi_dispositivo(base_path, routers, {'1': 'router', '2': 'host', '3': 'www', '4': 'dns'}[c])
        elif c == '5':
            _togli_dispositivo(base_path, routers)
        else:
            print('Scelta non valida.')


def menu_opzioni_laboratorio(base_path, routers):
    """Sottomenu per opzioni avanzate del laboratorio."""
    while True:
        routers = routers_dai_file(base_path)    # anche le modifiche fatte dalla GUI o a mano
        items = [
            'Imposta costo OSPF',
            'Aggiungi Policies BGP',
            'Aggiungi interfaccia loopback',
            "Ridistribuzione BGP -> IGP (togli/rimetti 'redistribute bgp', route-map eBGP)",
            'Assegna un resolver ad un dispositivo',
            "Aggiungi network BGP (aggregato dell'AS, reti interne, 0.0.0.0/0)",
            'Aggiungi sessioni iBGP (full mesh tra i router BGP dello stesso AS)',
            "Riepilogo configurazione (per controllare il testo dell'esercizio)",
            'DNS: delega sul root, zona nuova, record A, ricorsione e DNSSEC',
            'Costi OSPF predefiniti uguali su un AS (auto-cost reference-bandwidth 100)',
            'Modifica un dispositivo (IP, LAN, gateway, protocolli, AS, righe dei file)',
            'Default route (BGP verso un neighbor, RIP, OSPF)',
            'Aggiungi o togli un dispositivo',
            "Annulla l'ultima modifica o ripristina una copia di sicurezza",
            'Diagnostica e correggi frr.conf (refusi, blocchi, riferimenti, demoni)',
            'Azzera il routing (tiene topologia, IP, demoni, pc/WWW/DNS)'
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
            diagnostica_lab(base_path)
        elif choice == '9':
            menu_dns(base_path)
        elif choice == '10':
            imposta_auto_cost(base_path)
        elif choice == '11':
            modifica_dispositivo_menu(base_path, routers)
        elif choice == '12':
            default_route_menu(base_path, routers)
        elif choice == '13':
            menu_dispositivi(base_path, routers)
        elif choice == '14':
            menu_annulla(base_path)
        elif choice == '15':
            menu_diagnostica(base_path)
        elif choice == '16':
            azzera_routing(base_path)
        else:
            print('Scelta non valida, riprova.')


def _stampa_diagnosi(nome, problemi):
    print(f"\n{nome}: " + (f"{len(problemi)} problemi" if len(problemi) != 1 else "1 problema") if problemi else f"\n{nome}: nessun problema.")
    for k, x in enumerate(problemi, 1):
        dove = f"{x['file']} riga {x['riga']}" if x.get('riga') else x['file']
        print(f"  {k}. [{x['gravita']}] {dove}: {x['messaggio']}")
        for j, c in enumerate(x['correzioni']):
            extra = f"  (operazione: {c['rimando']['operazione']})" if c['rimando'] else ''
            print(f"       {k}{'abcdefghij'[j]}) {c['etichetta']}{extra}")


def diagnostica_lab(base_path):
    """Riepilogo (Opzioni 8): la diagnostica di frr.conf di ogni dispositivo, solo da leggere."""
    stato = leggi_stato(base_path)
    trovati = 0
    for nome in sorted(stato['dispositivi']):
        try:
            problemi = operazioni.opzioni_correggi_frr(stato, nome)
        except operazioni.ErroreOperazione:
            continue
        if problemi:
            _stampa_diagnosi(nome, problemi)
            trovati += len(problemi)
    print(f"\nDiagnostica frr.conf: {trovati} problemi in tutto." if trovati else "\nDiagnostica frr.conf: nessun problema trovato.")
    if trovati:
        print("Per correggerli: Opzioni 15.")


def menu_diagnostica(base_path):
    """Opzioni 15: diagnostica di frr.conf (core/frr_autofix.py) e
    correzione con la stessa operazione della GUI (correggi_frr): anteprima, conferma, annulla."""
    while True:
        stato = leggi_stato(base_path)
        nomi = sorted(stato['dispositivi'])
        print_menu('Diagnostica di quale dispositivo?', nomi, extra_options=[('0', 'Torna indietro')])
        s = input('Seleziona (numero): ').strip()
        if s == '0' or not s:
            return
        if not s.isdigit() or not 1 <= int(s) <= len(nomi):
            print('Scelta non valida.')
            continue
        nome = nomi[int(s) - 1]
        while True:
            stato = leggi_stato(base_path)
            problemi = operazioni.opzioni_correggi_frr(stato, nome)
            _stampa_diagnosi(nome, problemi)
            if not problemi:
                break
            sicuri = operazioni.opzioni_correggi_frr_sicuri(stato, nome)
            r = input("Correzione da applicare (es. 1a"
                      + (f", S = tutti i {len(sicuri)} fix sicuri di frr.conf" if sicuri else '')
                      + ", Invio = nessuna): ").strip().lower()
            if not r:
                break
            if r == 's' and sicuri:
                try:
                    piano = operazioni.calcola_correggi_frr_sicuri(stato, nome)
                except operazioni.ErroreOperazione as e:
                    print(e)
                    continue
                _esegui_piano(base_path, piano)
                continue
            if len(r) < 2 or not r[:-1].isdigit() or not 1 <= int(r[:-1]) <= len(problemi) \
                    or 'abcdefghij'.find(r[-1]) < 0 or 'abcdefghij'.find(r[-1]) >= len(problemi[int(r[:-1]) - 1]['correzioni']):
                print('Scelta non valida (numero del problema + lettera della correzione).')
                continue
            x, j = problemi[int(r[:-1]) - 1], 'abcdefghij'.find(r[-1])
            c = x['correzioni'][j]
            try:
                if c['rimando']:
                    piano = operazioni.OPERAZIONI[c['rimando']['operazione']][1](stato, **c['rimando']['parametri'])
                else:
                    piano = operazioni.calcola_correggi_frr(stato, nome, x['regola'], x['riga'], x['messaggio'], j)
            except operazioni.ErroreOperazione as e:
                print(e)
                continue
            _esegui_piano(base_path, piano)


def azzera_routing(base_path):
    """Opzioni 16: reset del routing di tutti i router o di uno (stessa operazione della GUI)."""
    stato = leggi_stato(base_path)
    info = operazioni.opzioni_reset_routing(stato)
    if not info['router']:
        print('Il lab non ha router.')
        return
    print("\nL'operazione toglie da frr.conf network, neighbor, redistribute, policy e costi, e le rotte statiche degli .startup dei router.")
    print("Restano lab.conf, IP, loopback, demoni abilitati e tutti i pc, server WWW e DNS.")
    print_menu('Su quale router?', ['Tutti i router'] + info['router'], extra_options=[('0', 'Torna indietro')])
    s = input('Seleziona (numero): ').strip()
    if s == '0' or not s:
        return
    if not s.isdigit() or not 1 <= int(s) <= len(info['router']) + 1:
        print('Scelta non valida.')
        return
    r = None if s == '1' else info['router'][int(s) - 2]
    try:
        piano = operazioni.calcola_reset_routing(stato, r)
    except operazioni.ErroreOperazione as e:
        print(e)
        return
    _esegui_piano(base_path, piano)


def menu_annulla(base_path):
    """Annulla l'ultima modifica della storia (stessa operazione della GUI) o ripristina una copia."""
    from .file_utils import ripristina_copia
    from .operazioni import ErroreOperazione, calcola_annulla
    from .stato import leggi_stato
    from .storia import riassunto
    ultime = riassunto(base_path)
    if ultime:
        print("\nUltime modifiche (la più recente in alto):")
        for v in ultime[:5]:
            print(f"  {v['ora']}  {v['titolo']}")
    else:
        print("\nNessuna modifica registrata per questo lab (la storia parte dalle modifiche fatte con le "
              "Opzioni o con la GUI).")
    print_menu('Cosa vuoi fare?', ["Annulla l'ultima modifica", 'Ripristina il lab da una copia di sicurezza'],
               extra_options=[('0', 'Torna indietro')])
    scelta = input('Seleziona (numero): ').strip()
    if scelta == '1':
        try:
            piano = calcola_annulla(leggi_stato(base_path))
        except ErroreOperazione as e:
            print(f"❌ {e}")
            return False
        return _esegui_piano(base_path, piano)
    if scelta == '2':
        return ripristina_copia(base_path)
    return False


def archivio_menu(lab_path):
    """Archivio del lab per la consegna (stesso codice della GUI): solo i file della configurazione."""
    from .archivio import contenuto_archivio, crea_archivio, nome_archivio_valido
    base, lab = os.path.dirname(os.path.abspath(lab_path)), os.path.basename(os.path.normpath(lab_path))
    nome = input(f"Nome dell'archivio (Invio = {lab}): ").strip() or lab
    for suff in ('.tar.gz', '.zip'):
        if nome.endswith(suff):
            nome = nome[:-len(suff)]
    if not nome_archivio_valido(nome):
        print("❌ Nome dell'archivio non valido (lettere, numeri, _ - .).")
        return
    if nome != lab:
        print(f"Attenzione: dentro l'archivio la cartella si chiamerà {lab}, non {nome}. Se il testo chiede "
              f"che cartella e archivio abbiano lo stesso nome, rinomina il lab.")
    formato = 'zip' if input("Formato: t = .tar.gz (quello della consegna), z = .zip [t]: ").strip().lower() == 'z' else 'tar.gz'
    dest = os.path.join(base, f"{nome}.{formato}")
    file, esclusi = contenuto_archivio(base, lab)
    print(f"\nNell'archivio: {len(file)} file della cartella {lab}.")
    if esclusi:
        print("Lasciati fuori: " + ', '.join(esclusi))
    if os.path.exists(dest) and not _si(f"{os.path.basename(dest)} esiste già. Lo sostituisco? (s/N): "):
        print('Annullato.')
        return
    dest, file, comando, esclusi = crea_archivio(base, lab, nome, formato)
    print(f"✅ Archivio creato: {dest} ({len(file)} file)")
    print(f"   Comando equivalente: {comando}")


def menu_post_creazione(base_path, routers):
    while True:
        routers = routers_dai_file(base_path)    # anche le modifiche fatte dalla GUI o a mano
        items = [
            'Genera file XML aggiornato',
            'Testa Funzionamento (PING)',
            'Opzioni Laboratorio',
            'Crea archivio per la consegna',
            'Pagine web e apache2 (links dal client, lab acceso)'
        ]
        print_menu('-------------- Menu post-creazione --------------', items, extra_options=[('0', 'Termina Programma')])
        print('\n--------------------------------------------------\n')

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
        elif choice == '4':
            archivio_menu(base_path)
        elif choice == '5':
            from gui.terminale_web import testa_pagine_web     # stesse funzioni Kathará della GUI
            testa_pagine_web(base_path)
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
    _proponi_xml_fuori(target)
    # i dati dei router si leggono dai file a ogni giro del menu: niente XML da creare o leggere
    menu_opzioni_laboratorio(target, None)


def _proponi_xml_fuori(lab_path):
    """Lab creati prima della fase 1.7: l'XML dei metadati sta ancora dentro il lab."""
    from .supporto import nome_lab, sposta_xml_fuori, xml_nel_lab
    if not xml_nel_lab(lab_path):
        return
    print(f"\nIl lab contiene {nome_lab(lab_path)}.xml (metadati del generatore), che va tolto prima della consegna.")
    if _si("Lo sposto in .labgenerator/ accanto ai lab? (S/n): ", True):
        fuori, copia = sposta_xml_fuori(lab_path)
        print(f"✅ XML spostato in {fuori} (copia di sicurezza del lab: {copia}).")