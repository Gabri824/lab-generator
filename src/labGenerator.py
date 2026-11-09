#!/usr/bin/env python3
"""
lab_generator.py
- Sposta i comandi di debug BGP globali sotto 'log file /var/log/frr/frr.log'
  invece che dentro la sezione 'router bgp ...'
"""
import os
import shutil
import ipaddress
import subprocess
import argparse
import json
import sys
import re
import builtins
import difflib

# -------------------------
# Navigazione nella creazione guidata
# -------------------------
class TornaIndietro(Exception):
    """'<' digitato: torna alla domanda precedente."""


class RicominciaDispositivo(Exception):
    """'<<' digitato: ricomincia la configurazione del dispositivo corrente."""


# attiva solo durante la creazione guidata (esegui_passi): altrove '<' è un input normale
_NAV_ATTIVA = False


def input(prompt=''):
    """Sostituisce input(): durante la creazione guidata intercetta '<' e '<<'."""
    s = builtins.input(prompt)
    if _NAV_ATTIVA:
        t = s.strip()
        if t == '<<':
            raise RicominciaDispositivo()
        if t == '<':
            raise TornaIndietro()
    return s

# -------------------------
# Utility input / validazioni
# -------------------------
def input_non_vuoto(prompt):
    while True:
        v = input(prompt).strip()
        if v:
            return v

def input_lan(prompt):
    """Chiede il nome della LAN e valida che contenga solo lettere e numeri.
    Ritorna il valore in maiuscolo. Esempi validi: 'A', 'A1', 'LAN2'.
    Non permette punti o altri caratteri (es. indirizzi IP).
    """
    while True:
        s = input_non_vuoto(prompt).strip().upper()
        # accetta solo lettere e numeri, almeno 1 carattere
        if s.isalnum():
            return s
        print("❌ Nome LAN non valido. Usa solo lettere e numeri (es. A o A1). Evita punti o indirizzi IP.")

def nome_kathara_valido(nome):
    """Nomi dei dispositivi in lab.conf: solo minuscole, cifre e '_'. Verificato su
    Kathará 3.7.7: 'web-srv', 'web.srv' e 'WebSrv' vengono scartati (linfo vede 0
    dispositivi) e `kathara lstart` si ferma con SyntaxError."""
    return bool(re.fullmatch(r"[a-z0-9_]+", nome or ''))


def correggi_nome_kathara(nome):
    """Proposta di nome valido: minuscolo, caratteri vietati sostituiti da '_' (ns-com -> ns_com)."""
    return re.sub(r"[^a-z0-9_]", "_", (nome or '').strip().lower()) or 'dispositivo'


def input_lab_name(prompt):
    """Chiede il nome del laboratorio: solo minuscole, numeri, '_' e '-'.
    Il nome diventa sia la cartella del lab sia il nome del file XML."""
    while True:
        s = input_non_vuoto(prompt).strip()
        if re.fullmatch(r"[a-z0-9_-]+", s):
            return s
        print("❌ Nome non valido. Usa solo lettere minuscole, numeri, '_' e '-' (es. bgp_es1). Niente spazi, accenti, '/' o '.'.")

def input_int(prompt, min_val=0):
    while True:
        s = input(prompt).strip()
        try:
            n = int(s)
            if n >= min_val:
                return n
            print(f"❌ Inserisci un intero ≥ {min_val}")
        except ValueError:
            print("❌ Inserisci un numero intero valido")
 
def valida_ip_cidr(prompt):
    """Valida e ritorna un indirizzo con CIDR (es. 10.0.0.1/24)."""
    while True:
        s = input(prompt).strip()
        # richiediamo esplicitamente la presenza del prefisso '/'
        if '/' not in s:
            print("❌ Inserisci la maschera usando '/' alla fine (es. 192.168.1.1/24)")
            continue
        try:
            ipaddress.ip_interface(s)
            return s
        except Exception:
            print("❌ Formato non valido. Usa x.x.x.x/yy (es. 192.168.1.1/24)")

def valida_ip_senza_cidr(prompt):
    while True:
        s = input(prompt).strip()
        try:
            ipaddress.ip_address(s)
            return s
        except Exception:
            print("❌ IP non valido. Inserisci un IPv4 (es. 10.0.0.2)")

def asn_valido(s):
    return s.isdigit() and 1 <= int(s) <= 4294967295


def input_asn(prompt):
    """Numero AS: solo cifre (FRR scarterebbe 'router bgp abc' o 'remote-as abc')."""
    while True:
        s = input_non_vuoto(prompt).strip()
        if asn_valido(s):
            return s
        print("❌ Numero AS non valido: solo cifre (es. 20).")


def area_valida(s):
    """Area OSPF: un numero (0) o il formato x.x.x.x (0.0.0.0)."""
    if s.isdigit():
        return int(s) <= 4294967295
    try:
        ipaddress.IPv4Address(s)
        return True
    except ValueError:
        return False


def input_area(prompt, default=None):
    """Area OSPF valida; con un default, Invio a vuoto ritorna il default."""
    while True:
        s = input(prompt).strip()
        if not s and default is not None:
            return default
        if s and area_valida(s):
            return s
        if s:
            print("❌ Area OSPF non valida: un numero (es. 0) o x.x.x.x (es. 1.1.1.1).")


def input_destinazione(prompt):
    """Destinazione di una rotta statica: una rete con maschera oppure 'default'."""
    while True:
        s = input_non_vuoto(prompt).strip()
        if s.lower() == 'default':
            return 'default'
        try:
            reti = parse_reti(s)
        except ValueError as e:
            print(f"❌ Rete non valida: {e}")
            continue
        if len(reti) == 1:
            return reti[0]
        print("❌ Inserisci una sola rete.")


def valida_protocols(prompt):
    allowed = {"bgp", "ospf", "rip", "statico"}
    while True:
        s = input(prompt).strip().lower().replace(",", " ")
        # Non permettere input vuoto: l'utente deve indicare almeno un valore
        if not s:
            print("❌ Inserisci almeno un protocollo (bgp/ospf/rip/statico).")
            continue
        toks = [t for t in s.split() if t]
        if toks and all(t in allowed for t in toks):
            return list(dict.fromkeys(toks))
        print("❌ Usa solo: bgp ospf rip statico")


def print_menu(title, items, extra_options=None):
    """Stampa un menu ordinato con titolo, una riga vuota, opzioni numerate

    - `title`: stringa titolo (stampa su singola riga)
    - `items`: lista di stringhe che saranno numerate 1..n
    - `extra_options`: lista di tuple (chiave, etichetta) per opzioni non numeriche
    """
    # titolo e riga vuota
    print(f"\n{title}\n")
    # opzioni numerate
    for i, it in enumerate(items, start=1):
        print(f"  {i}) {it}")
    # opzioni extra (es. M) Inserisci manualmente)
    if extra_options:
        for k, lab in extra_options:
            print(f"  {k}) {lab}")
    # linea vuota prima del prompt
    print("")

# -------------------------
# Templates
# -------------------------
DAEMONS_TMPL = """zebra={zebra} 
ripd={ripd}
ospfd={ospfd}
bgpd={bgpd}

ospf6d=no
ripngd=no
isisd=no
pimd=no
ldpd=no
nhrpd=no
eigrpd=no
babeld=no
sharpd=no
staticd=no
pbrd=no
bfdd=no
fabricd=no

######

vtysh_enable=yes
zebra_options=" -s 90000000 --daemon -A 127.0.0.1"
bgpd_options="   --daemon -A 127.0.0.1"
ospfd_options="  --daemon -A 127.0.0.1"
ospf6d_options=" --daemon -A ::1"
ripd_options="   --daemon -A 127.0.0.1"
ripngd_options=" --daemon -A ::1"
isisd_options="  --daemon -A 127.0.0.1"
pimd_options="  --daemon -A 127.0.0.1"
ldpd_options="  --daemon -A 127.0.0.1"
nhrpd_options="  --daemon -A 127.0.0.1"
eigrpd_options="  --daemon -A 127.0.0.1"
babeld_options="  --daemon -A 127.0.0.1"
sharpd_options="  --daemon -A 127.0.0.1"
staticd_options="  --daemon -A 127.0.0.1"
pbrd_options="  --daemon -A 127.0.0.1"
bfdd_options="  --daemon -A 127.0.0.1"
fabricd_options="  --daemon -A 127.0.0.1"
"""

VTYSH_TMPL = """service integrated-vtysh-config
hostname {hostname}
"""

FRR_HEADER = """password zebra
enable password zebra

log file /var/log/frr/frr.log
"""
STARTUP_ROUTER_TMPL = """{ip_config}

systemctl start frr
"""

STARTUP_HOST_TMPL = """{ip_config}
ip route add default via {gateway} dev eth0
"""

STARTUP_WWW_TMPL = """ip address add {ip} dev eth0
ip route add default via {gateway} dev eth0
systemctl start apache2 
"""

WWW_INDEX = """<html><head><title>www</title></head><body><h1>Server WWW</h1></body></html>"""

LAB_CONF_HEADER = ""

# -------------------------
# Helpers FRR: aggregazione reti
# -------------------------
def aggregate_to_supernet_for_router(interface_ips, agg_prefix=16):
    """
    Aggrega le reti collegate di un router.

    - Prima collassa gli indirizzi adiacenti (come prima).
    - Poi, per IPv4, se ci sono più reti che ricadono nello stesso supernet
      di lunghezza `agg_prefix` (es. /16), queste saranno aggregate in quel
      supernet. Se invece c'è una sola rete nel supernet, viene mantenuta
      la rete originale.

    Questo evita di permettere modifiche manuali ai singoli `frr.conf` per
    gestire l'aggregazione: viene calcolata automaticamente qui.

    Note/assunzioni:
    - L'aggregazione automatica opera per default su /16 per IPv4. Se vuoi
      un comportamento diverso puoi cambiare `agg_prefix`.
    - IPv6 viene semplicemente collassato ma non verrà ulteriormente
      supernettato dal comportamento di gruppo qui (per evitare scelte
      ambigue sui prefissi IPv6).
    """
    networks = []
    for ip_cidr in interface_ips:
        try:
            iface = ipaddress.ip_interface(ip_cidr)
            networks.append(iface.network)
        except ValueError:
            continue
    if not networks:
        return []

    # Collassa reti contigue come prima
    collapsed = list(ipaddress.collapse_addresses(networks))

    ipv4_nets = [n for n in collapsed if isinstance(n, ipaddress.IPv4Network)]
    ipv6_nets = [n for n in collapsed if isinstance(n, ipaddress.IPv6Network)]

    # Raggruppa IPv4 per supernet di lunghezza agg_prefix
    super_map = {}
    for n in ipv4_nets:
        if n.prefixlen <= agg_prefix:
            # la rete è già più ampia o uguale del target: la manteniamo così
            super_map.setdefault(n, []).append(n)
        else:
            s = n.supernet(new_prefix=agg_prefix)
            super_map.setdefault(s, []).append(n)

    result_nets = []
    for supern, members in super_map.items():
        if isinstance(supern, ipaddress.IPv4Network):
            # se ci sono più reti nel supernet, allora usiamo il supernet
            if len(members) > 1:
                result_nets.append(supern)
            else:
                # una sola rete -> mantieni la rete originale
                result_nets.append(members[0])
        else:
            # safety fallback
            for m in members:
                result_nets.append(m)

    # aggiungi IPv6 così come è stato collassato
    result_nets.extend(ipv6_nets)

    # Riricollassa per sicurezza e ritorna come stringhe
    final = list(ipaddress.collapse_addresses(result_nets))
    return [str(n) for n in final]


def collapse_interface_networks(interface_ips):
    """
    Collassa le reti derivate dalle interfacce evitando di forzare
    supernet di lunghezza fissa. Restituisce la lista di reti collassate
    (es. ['1.2.0.0/24','1.3.0.0/24'] -> ['1.2.0.0/24','1.3.0.0/24'] o
    se contigue vengono unite secondo ipaddress.collapse_addresses).

    Questa funzione è il punto centrale che useremo per passare le reti
    ai generatori di stanza (BGP/OSPF/RIP). I generatori possono poi
    scegliere di prendere un supernet più ampio se lo ritengono opportuno.
    """
    networks = []
    for ip_cidr in interface_ips:
        try:
            iface = ipaddress.ip_interface(ip_cidr)
            networks.append(iface.network)
        except Exception:
            continue
    if not networks:
        return []
    collapsed = list(ipaddress.collapse_addresses(networks))
    return [str(n) for n in collapsed]


def choose_allowed_byte_aligned_supernet(interface_ips):
    """
    Sceglie un singolo supernet byte-aligned (solo /8 o /16) che copra
    tutte le interfacce fornite in `interface_ips` (lista di stringhe IP/CIDR).

    Regole:
    - Preferisce /16 quando le interfacce condividono i primi due ottetti.
    - Usa /8 solo se condividono solo il primo ottetto.
    - Non restituisce /24: gli accorciamenti a /24 non sono consentiti.
    - Se non è possibile trovare un /16 o /8 sensato, ritorna None.
    """
    nets = []
    for ip_cidr in interface_ips:
        try:
            iface = ipaddress.ip_interface(ip_cidr)
            nets.append(iface.network)
        except Exception:
            continue
    if not nets:
        return None
    collapsed = list(ipaddress.collapse_addresses(nets))
    ipv4_nets = [n for n in collapsed if isinstance(n, ipaddress.IPv4Network)]
    if not ipv4_nets:
        return None
    min_addr = min(n.network_address for n in ipv4_nets)
    max_addr = max(n.broadcast_address for n in ipv4_nets)
    # Deterministic byte-by-byte logic to prefer /16 when sensible.
    # Extract IPv4 addresses as tuples of octets
    octets_list = []
    for ip_cidr in interface_ips:
        try:
            iface = ipaddress.ip_interface(ip_cidr)
            ip = iface.ip
            if isinstance(ip, ipaddress.IPv4Address):
                octs = tuple(int(x) for x in str(ip).split('.'))
                octets_list.append(octs)
        except Exception:
            continue
    if not octets_list:
        return None

    # check commonality
    same_first2 = all(o[:2] == octets_list[0][:2] for o in octets_list)
    same_first1 = all(o[0] == octets_list[0][0] for o in octets_list)

    if same_first2:
        # prefer /16 when possible
        a, b = octets_list[0][0], octets_list[0][1]
        return f"{a}.{b}.0.0/16"
    if same_first1:
        # /8
        a = octets_list[0][0]
        return f"{a}.0.0.0/8"

    return None


def group_by_first_octet(interface_ips):
    """Raggruppa gli indirizzi per primo ottetto (es. 100.x.x.x -> key 100).
    Restituisce dict: {first_octet_int: [ip_cidr_str, ...], ...}
    """
    groups = {}
    for ip_cidr in interface_ips:
        try:
            iface = ipaddress.ip_interface(ip_cidr)
            addr = iface.ip
            if isinstance(addr, ipaddress.IPv4Address):
                fo = int(str(addr).split('.')[0])
                groups.setdefault(fo, []).append(ip_cidr)
        except Exception:
            continue
    return groups

# -------------------------
# FRR stanza builders
# -------------------------
def mk_bgp_stanza(asn, redistribute=None, networks=None):
    """
    Costruisce la stanza BGP. Secondo le regole fornite dall'utente,
    BGP deve annunciare tutte le network effettivamente collegate al
    router senza accorciarle: manteniamo i prefissi originali.
    """
    lines = [
        f"router bgp {asn}",
        "",
        "    no bgp ebgp-requires-policy",
        "    no bgp network import-check",
    ]
    if networks:
        # aggiungi riga vuota prima delle network
        lines.append("")
        # scrivi le network così come sono (dedupando)
        seen = set()
        for net in networks:
            try:
                # normalizza la rete (es. 10.0.1.1/24 -> 10.0.1.0/24)
                n = ipaddress.ip_network(net, strict=False)
                s = str(n)
            except Exception:
                s = str(net)
            if s not in seen:
                lines.append(f"    network {s}")
                seen.add(s)
    # NOTE: non aggiungiamo più automaticamente comandi `redistribute`.
    # L'amministratore preferisce gestirli manualmente nel file `frr.conf`.
    # Questo evita policy non desiderate inserite automaticamente.

    return "\n".join(lines) + "\n\n"

def mk_ospf_stanza(networks, area=None, stub=False, redistribute=None):
    """
    Costruisce la stanza OSPF: una riga `network <rete> area <area>` per ogni
    rete, così come viene passata (la scelta delle reti avviene prima, in
    default_igp_networks o nella creazione guidata). Se `stub` è True aggiunge
    `area <area> stub`.
    """
    area = area or '0.0.0.0'
    lines = ["router ospf", ""]
    seen = set()
    for net in networks or []:
        s = _norm_net(net)
        if s not in seen:
            lines.append(f"    network {s} area {area}")
            seen.add(s)
    if stub:
        lines.append(f"    area {area} stub")
    if redistribute:
        lines.append("")
        for cmd in redistribute:
            lines.append(f"    {cmd}")
    return "\n".join(lines) + "\n\n"

def mk_rip_stanza(networks, redistribute=None):
    lines = ["router rip", ""]
    seen = set()
    for net in networks or []:
        s = _norm_net(net)
        if s not in seen:
            lines.append(f"    network {s}")
            seen.add(s)
    if redistribute:
        lines.append("")
        for cmd in redistribute:
            lines.append(f"    {cmd}")
    return "\n".join(lines) + "\n\n"


def _norm_net(net):
    """'10.0.1.1/24' -> '10.0.1.0/24' (lascia invariato ciò che non è una rete valida)."""
    try:
        return str(ipaddress.ip_network(str(net).strip(), strict=False))
    except ValueError:
        return str(net).strip()


def parse_reti(s):
    """'10.0.0.0/8, 20.1.0.0/16' -> ['10.0.0.0/8', '20.1.0.0/16'].
    Solleva ValueError se una rete non è valida o manca la '/'."""
    out = []
    for tok in s.replace(',', ' ').split():
        if '/' not in tok:
            raise ValueError(f"manca la maschera in '{tok}' (es. 10.0.0.0/8)")
        n = str(ipaddress.ip_network(tok, strict=False))
        if n not in out:
            out.append(n)
    return out


def input_reti(prompt, default=None, opzionale=False):
    """Chiede una o più reti separate da virgola; invio -> default (se dato)."""
    while True:
        s = input(prompt).strip()
        if not s:
            if default:
                return list(default)
            if opzionale:
                return []
            print("❌ Inserisci almeno una rete (es. 100.0.0.0/8).")
            continue
        try:
            return parse_reti(s)
        except ValueError as e:
            print(f"❌ Rete non valida: {e}")


def _as_number(rname, data):
    """Numero dell'AS del router: ASN BGP oppure dal nome 'as<N>r<M>'."""
    asn = str(data.get('asn') or '').strip()
    if asn.isdigit():
        return int(asn)
    m = re.match(r'as(\d+)r', rname or '', re.IGNORECASE)
    return int(m.group(1)) if m else None


def default_igp_networks(rname, data):
    """Network da annunciare in OSPF/RIP proposte per un router.

    Regola (verificata sulle 26 soluzioni di lab-bgp: stesse interfacce coperte
    in tutti i 109 casi): si prendono le interfacce "dell'AS", cioè quelle il
    cui primo ottetto è il numero dell'AS; se nessuna, il gruppo per primo
    ottetto con più LAN (prefisso < /30), poi con più interfacce. La network è
    l'aggregato /8 di quel primo ottetto. I link eBGP (altro primo ottetto)
    restano fuori.
    """
    groups = {}
    for it in data.get('interfaces', []):
        try:
            iface = ipaddress.ip_interface(it.get('ip', ''))
        except ValueError:
            continue
        if isinstance(iface, ipaddress.IPv4Interface):
            groups.setdefault(int(str(iface.ip).split('.')[0]), []).append(iface)
    if not groups:
        return []
    asn = _as_number(rname, data)
    if asn in groups:
        octet = asn
    else:
        octet = max(groups, key=lambda o: (sum(i.network.prefixlen < 30 for i in groups[o]), len(groups[o])))
    return [f"{octet}.0.0.0/8"]


def default_bgp_aggregate(rname, data):
    """Aggregato /8 dell'AS proposto per 'Aggiungi network BGP' (es. AS100 -> 100.0.0.0/8).
    Stessa regola delle network IGP: conta il primo ottetto delle interfacce, non
    solo il numero AS (in alcuni esercizi as100r1 è in AS1 ma usa 100.x)."""
    return default_igp_networks(rname, data)


def format_ospf_multi_area(area_nets_map, stub_areas=None, redistribute=None):
    """
    Costruisce un unico blocco 'router ospf' che contiene tutte le network
    annotate con la relativa area, e le dichiarazioni 'area <id> stub'
    dopo le network.

    - area_nets_map: dict area_id -> list of network strings
    - stub_areas: iterable of area_id da marcare come stub
    - redistribute: list of redistribute commands to add
    """
    if stub_areas is None:
        stub_areas = set()
    lines = ["router ospf", ""]
    # ordiniamo le aree per stabilità (area 0.0.0.0 prima se presente)
    def area_sort_key(a):
        return (0 if a == '0.0.0.0' else 1, str(a))
    for area in sorted(area_nets_map.keys(), key=area_sort_key):
        nets = area_nets_map.get(area) or []
        for n in nets:
            lines.append(f"    network {n} area {area}")
    # aggiungi dichiarazioni stub dopo le network
    for area in sorted(stub_areas):
        lines.append(f"    area {area} stub")
    # Aggiungi riga vuota prima dei redistribute se ci sono stub areas
    if stub_areas and redistribute:
        lines.append("")
    # Aggiungi comandi redistribute se forniti
    if redistribute:
        for cmd in redistribute:
            lines.append(f"    {cmd}")
    return "\n".join(lines) + "\n\n"

# -------------------------
# Creazione file router
# -------------------------
def iface_for_nexthop(interfaces, via):
    """Nome dell'interfaccia la cui subnet contiene il next-hop `via`, o None."""
    try:
        nh = ipaddress.ip_address(via)
    except Exception:
        return None
    for iface in interfaces:
        try:
            if nh in ipaddress.ip_interface(iface.get('ip', '')).network:
                return iface.get('name')
        except Exception:
            continue
    return None


def static_route_lines(data):
    """Restituisce le righe 'ip route add ...' per le rotte statiche del router.

    static_routes può essere una lista di stringhe o dict.
    Esempio dict: {"network":"30.0.0.0/24","via":"10.0.0.13","dev":"eth0"}
    """
    static_routes = data.get('static_routes', []) or []
    route_lines = []
    # default dev se non specificato: prima interfaccia o 'eth0'
    default_dev = (data.get('interfaces') and data.get('interfaces')[0].get('name')) or 'eth0'
    for r in static_routes:
        if isinstance(r, str):
            # se l'utente ha fornito la stringa completa, rimuoviamo
            # eventuale maschera dal next-hop (es. 'via 10.0.0.13/30' -> 'via 10.0.0.13')
            s = re.sub(r"(via\s+)([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)/\d+", r"\1\2", r)
            route_lines.append(f"ip route add {s}")
        elif isinstance(r, dict):
            net = r.get('network') or r.get('net') or r.get('dest')
            via = r.get('via') or r.get('nexthop') or r.get('gw')
            # rimuovi la maschera dal next-hop se presente
            if isinstance(via, str) and '/' in via:
                via = via.split('/')[0]
            dev = r.get('dev') or r.get('if') or iface_for_nexthop(data.get('interfaces') or [], via) or default_dev
            if net and via:
                route_lines.append(f"ip route add {net} via {via} dev {dev}")
            elif net and dev:
                route_lines.append(f"ip route add {net} dev {dev}")
            elif isinstance(r.get('cmd'), str):
                route_lines.append(r.get('cmd'))
    return route_lines


def crea_router_files(base_path, rname, data, interactive=True):
    # Se il router è marcato come 'statico' (cioè l'utente ha scelto solo
    # il token 'statico' tra i protocolli), non creiamo la cartella del
    # router né i file FRR: generiamo solo lo startup con IP e rotte statiche.
    # interactive=False: nessun input() (usato da import XML/JSON).
    protos = data.get("protocols") or []
    only_static = ('statico' in protos) and all(p == 'statico' for p in protos)
    if only_static:
        ip_cfg_lines = [f"ip address add {iface['ip']} dev {iface.get('name','eth0')}" for iface in data.get('interfaces', [])]
        # loopbacks (se presenti) vanno aggiunte allo startup come interfacce lo
        for lb in (data.get('loopbacks') or []):
            ip_cfg_lines.append(f"ip address add {lb} dev lo")
        startup_lines = ip_cfg_lines + static_route_lines(data)
        startup_path = os.path.join(base_path, f"{rname}.startup")
        with open(startup_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write("\n".join(startup_lines) + "\n")
        try:
            os.chmod(startup_path, 0o755)
        except Exception:
            pass
        return

    etc_frr = os.path.join(base_path, rname, "etc", "frr")
    os.makedirs(etc_frr, exist_ok=True)

    # Forza sempre zebra=yes come richiesto
    zebra_flag = "yes"
    daemons = DAEMONS_TMPL.format(
        zebra=zebra_flag,
        ripd="yes" if "rip" in data["protocols"] else "no",
        ospfd="yes" if "ospf" in data["protocols"] else "no",
        bgpd="yes" if "bgp" in data["protocols"] else "no"
    )
    with open(os.path.join(etc_frr, "daemons"), 'w', encoding='utf-8', newline='\n') as f:
        f.write(daemons)

    hostname_line = f"{rname}-frr"
    with open(os.path.join(etc_frr, "vtysh.conf"), 'w', encoding='utf-8', newline='\n') as f:
        f.write(VTYSH_TMPL.format(hostname=hostname_line))

    parts = [FRR_HEADER]

    # Se il router usa BGP, aggiungi debug subito dopo l'intestazione
    if "bgp" in data["protocols"]:
        parts.append(
            "debug bgp keepalives\n"
            "debug bgp updates in\n"
            "debug bgp updates out\n"
        )

    phys_iface_ips = [iface["ip"] for iface in data["interfaces"]]
    # loopbacks separate: le aggiungiamo solo per OSPF/RIP e per lo startup,
    # ma non per BGP
    loopbacks = data.get('loopbacks') or []
    # combined (interfacce fisiche + loopbacks) per OSPF/RIP/aggregazioni
    combined_ips = phys_iface_ips + loopbacks
    # determiniamo le reti originali (una per interfaccia fisica) per BGP
    original_nets = []
    for ip_cidr in phys_iface_ips:
        try:
            n = ipaddress.ip_network(ip_cidr, strict=False)
            original_nets.append(str(n))
        except Exception:
            continue

    # collapsed networks (fallback per OSPF/RIP quando necessario)
    aggregated_nets = collapse_interface_networks(combined_ips)

    # Determina i comandi redistribute da aggiungere automaticamente
    # - Se il router ha solo RIP o solo OSPF: aggiungi "redistribute connected"
    # - Se il router ha BGP + RIP o BGP + OSPF: aggiungi "redistribute connected" e "redistribute bgp"
    protos = data.get("protocols", [])
    has_bgp = "bgp" in protos
    has_ospf = "ospf" in protos
    has_rip = "rip" in protos
    
    # Costruisci la lista di comandi redistribute per OSPF/RIP
    ospf_redistribute = []
    rip_redistribute = []
    
    # 'redistribute bgp' solo se il router deve iniettare nell'IGP le rotte BGP
    # (a volte il testo lo chiede solo a uno dei router di confine, es. tennis: solo as2r2)
    inietta_bgp = has_bgp and data.get('igp_redistribute_bgp', True)
    if has_ospf:
        ospf_redistribute.append("redistribute connected")
        if inietta_bgp:
            ospf_redistribute.append("redistribute bgp")

    if has_rip:
        rip_redistribute.append("redistribute connected")
        if inietta_bgp:
            rip_redistribute.append("redistribute bgp")

    # OSPF / RIP: le network sono quelle scelte nella creazione guidata
    # (data['igp_networks']) oppure, se mancano, l'aggregato /8 proposto da
    # default_igp_networks(). Un'unica area (come in tutte le soluzioni del corso):
    # i link eBGP restano fuori dall'IGP e arrivano con 'redistribute connected'.
    if has_ospf or has_rip:
        igp_nets = data.get('igp_networks') or default_igp_networks(rname, data)
        # loopback non coperte dalle network IGP: annunciate come /32
        for lb in loopbacks:
            try:
                lb_ip = ipaddress.ip_interface(lb).ip
                if not any(lb_ip in ipaddress.ip_network(n, strict=False) for n in igp_nets):
                    igp_nets = igp_nets + [str(ipaddress.ip_interface(lb).network)]
            except ValueError:
                pass
        if has_ospf:
            parts.append(mk_ospf_stanza(igp_nets, area=data.get('ospf_area') or '0.0.0.0',
                                        stub=bool(data.get('ospf_area_stub')), redistribute=ospf_redistribute))
        if has_rip:
            parts.append(mk_rip_stanza(igp_nets, redistribute=rip_redistribute))
    # BGP: annuncia tutte le network collegate senza accorciarle (mantieni prefissi originali)
    # BGP viene aggiunto per ultimo per garantire che appaia in fondo al file frr.conf
    if "bgp" in data["protocols"]:
        # + eventuali network non collegate (aggregato dell'AS, reti interne)
        parts.append(mk_bgp_stanza(data.get("asn", ""),
                                   networks=original_nets + list(data.get('bgp_extra_networks') or [])))

    with open(os.path.join(etc_frr, "frr.conf"), 'w', encoding='utf-8', newline='\n') as f:
        f.write("\n".join(parts))

    ip_cfg_lines = [f"ip address add {iface['ip']} dev {iface['name']}" for iface in data["interfaces"]]
    # aggiungi le loopback allo startup
    for lb in loopbacks:
        ip_cfg_lines.append(f"ip address add {lb} dev lo")
    # rotte statiche (se 'statico' è combinato con un protocollo di routing)
    ip_cfg_lines.extend(static_route_lines(data))
    startup_path = os.path.join(base_path, f"{rname}.startup")
    with open(startup_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(STARTUP_ROUTER_TMPL.format(ip_config="\n".join(ip_cfg_lines)))
    try:
        os.chmod(startup_path, 0o755)
    except Exception:
        pass



# -------------------------
# Host e WWW
# -------------------------
def crea_host_file(base_path, hname, ip_cidr, gateway_cidr, lan):
    os.makedirs(base_path, exist_ok=True)
    # gateway_cidr può contenere /prefisso; rimuoviamo la maschera per la route
    gateway = gateway_cidr.split('/')[0] if '/' in gateway_cidr else gateway_cidr
    startup = STARTUP_HOST_TMPL.format(ip_config=f"ip address add {ip_cidr} dev eth0", gateway=gateway)
    path = os.path.join(base_path, f"{hname}.startup")
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(startup)
    try:
        os.chmod(path, 0o755)
    except Exception:
        pass

def crea_host_multi(base_path, hname, interfaces, gateway=None, gw_dev='eth0'):
    """Crea lo startup di un host con una o più interfacce.

    - interfaces: lista di dict {"name": "eth0", "ip": "10.0.0.1/24", "lan": "A"}
    - gateway: IP (con o senza /prefisso) del default gateway, opzionale
    """
    os.makedirs(base_path, exist_ok=True)
    lines = [f"ip address add {iface['ip']} dev {iface['name']}" for iface in interfaces]
    if gateway:
        gw = gateway.split('/')[0]
        lines.append(f"ip route add default via {gw} dev {gw_dev or 'eth0'}")
    path = os.path.join(base_path, f"{hname}.startup")
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write("\n".join(lines) + "\n")
    try:
        os.chmod(path, 0o755)
    except Exception:
        pass


def crea_www_file(base_path, name, ip_cidr, gateway_cidr, lan):
    www_dir = os.path.join(base_path, name, "var", "www", "html")
    os.makedirs(www_dir, exist_ok=True)
    index_path = os.path.join(www_dir, "index.html")
    
    # Usa il nome del server nel titolo e nel corpo
    html_content = f"<html><head><title>{name}</title></head><body><h1>Server {name}</h1></body></html>"
    
    with open(index_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(html_content)
    startup_path = os.path.join(base_path, f"{name}.startup")
    # rimuovi la maschera dal gateway per la route (mantieni la maschera sull'IP dell'interfaccia)
    gateway = gateway_cidr.split('/')[0] if '/' in gateway_cidr else gateway_cidr
    with open(startup_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(STARTUP_WWW_TMPL.format(ip=ip_cidr, gateway=gateway))
    try:
        os.chmod(startup_path, 0o755)
    except Exception:
        pass


def _rec_dns(name, rtype, value):
    """Riga di un file di zona con colonne allineate (nomi e valori assoluti con il punto finale)."""
    def assoluto(s):
        s = str(s).strip()
        return s if s.endswith('.') or s == '@' else s + '.'
    nome = assoluto(name)
    if rtype in ('NS', 'CNAME', 'PTR'):
        value = assoluto(value)
    return f"{nome:<16}\tIN\t{rtype}\t{value}"


def _soa_root(serial):
    return ['$TTL 60000',
            '@ IN SOA ROOT-SERVER. root.ROOT-SERVER. (',
            f'    {serial} ; serial',
            '    28800 ; refresh',
            '    14400 ; retry',
            '    3600000 ; expire',
            '    0 ; negative cache ttl',
            ')',
            '']


def _righe_delega(zone, ns, ip):
    """Delega di una zona dal root: '<zona>. NS <ns>.' + glue '<ns>. A <ip>'."""
    righe = [_rec_dns(zone, 'NS', ns)]
    if ip:
        righe.append(_rec_dns(ns, 'A', str(ip).split('/')[0]))
    return righe


def crea_dns_host(base_path, name, ip_cidr, gateway_cidr, lan, forwarders=None, zones=None, root_type=None, root_server_ip=None, allow_recursion=None, dnssec_validation=False, delegations=None):
    """
    Crea la struttura di un Host DNS (BIND9) nella directory del lab.

    Struttura creata:
    <base_path>/<name>/etc/bind/
        db.root
        named.conf
        named.conf.options
        (facoltativo) db.<name>.<zone>

    Lo startup file conterrà `systemctl start named`.
    - forwarders: lista di indirizzi IP (stringhe) da inserire in named.conf.options
    - zones: dict zone_name -> dict of records (basic A records), e.g. {"example.local": {"host": "10.0.0.10"}}
    """
    bind_dir = os.path.join(base_path, name, 'etc', 'bind')
    os.makedirs(bind_dir, exist_ok=True)
    # --- named.conf.options ---
    # Two variants: minimal or with recursion + dnssec disabled
    opts_lines = [
        'options {',
        '    directory "/var/cache/bind";',
    ]
    # If forwarders are provided, include forwarders block
    if forwarders:
        # forwarders is expected to be a list of IPs
        fw_items = ' '.join(f"{x};" for x in forwarders)
        opts_lines.append('    forwarders { ' + fw_items + ' };')
    # allow_recursion can be 'any' or '0/0' or similar string to be placed verbatim
    if allow_recursion:
        opts_lines.append('    allow-recursion { ' + str(allow_recursion) + '; };')
    # dnssec_validation -> add dnssec-validation no;
    if dnssec_validation:
        opts_lines.append('    dnssec-validation no;')
    opts_lines.append('};')
    opts_content = "\n".join(opts_lines) + "\n"
    with open(os.path.join(bind_dir, 'named.conf.options'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(opts_content)

    # Helper per formattare record DNS in colonne allineate
    def format_dns_record(name, rtype, value, cls='IN', name_width=16):
        """
        Restituisce una stringa con colonne visivamente allineate:
        - `name` left-aligned in `name_width` caratteri
        - poi `cls` (es. IN), `rtype` (A/NS/CNAME) e `value`, separati da tab

        Esempio risultante:
        "nome            \tIN\tA\t10.0.0.1"
        """
        # Normalizza i nomi/valori per assicurare il punto finale sui FQDN
        # Non modificare il record speciale '@'
        def _is_ip(s):
            try:
                ipaddress.ip_address(s)
                return True
            except Exception:
                return False

        # se il name è un FQDN (contiene un punto ma non termina con '.') aggiungi '.'
        if name != '@' and isinstance(name, str) and '.' in name and not name.endswith('.'):
            name = name + '.'

        # per tipi che puntano ad un nome (NS, CNAME, PTR) aggiungi il punto anche al valore
        if isinstance(rtype, str) and rtype.upper() in ('NS', 'CNAME', 'PTR'):
            if isinstance(value, str) and '.' in value and not value.endswith('.') and not _is_ip(value):
                value = value + '.'

        # usa un campo nome con padding fisso, poi tab per separazione chiara
        name_field = f"{name:<{name_width}}"
        return f"{name_field}\t{cls}\t{rtype}\t{value}"

    # --- db.root ---
    # Decide se il server è root/master o hint: root_type == 'master' -> full SOA, 'hint' -> hint format
    host_ip = ip_cidr.split('/')[0] if ip_cidr else '127.0.0.1'
    # Determine which IP to write inside db.root:
    # - if this server is declared master -> use its own IP
    # - if this server is hint and a root_server_ip is provided -> use that IP
    # - otherwise fallback to the host IP
    if root_type == 'master':
        ip_root = host_ip
    elif root_type == 'hint' and root_server_ip:
        ip_root = root_server_ip
    else:
        ip_root = host_ip
    import datetime
    serial = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d') + '01'
    # db.root: per il root (master per '.') serve un file di zona completo, con SOA e
    # le deleghe dei domini di primo livello (es. com. NS dns.com. + glue A);
    # per gli altri server è il file "hint" con solo NS e A del root.
    db_root_lines = [
        format_dns_record('@', 'NS', 'ROOT-SERVER.'),
        format_dns_record('ROOT-SERVER.', 'A', ip_root),
        '',
    ]
    if root_type == 'master':
        db_root_lines = _soa_root(serial) + db_root_lines
        for d in (delegations or []):
            db_root_lines += _righe_delega(d.get('zone'), d.get('ns'), d.get('ip'))
        db_root_lines.append('')
    with open(os.path.join(bind_dir, 'db.root'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(db_root_lines))

    # --- named.conf ---
    # include options (absolute path) and declare zone for '.' as master or hint
    named_lines = [
        'include "/etc/bind/named.conf.options";',
        '',
    ]
    zone_type = 'hint' if root_type != 'master' else 'master'
    named_lines.append('zone "." {')
    named_lines.append(f'    type {zone_type};')
    named_lines.append('    file "/etc/bind/db.root";')
    named_lines.append('};')
    named_lines.append('')

    # add authoritative zones to named.conf if any
    if zones:
        for zname in zones.keys():
            if zname == '.':
                continue
            rev = '.'.join(zname.split('.')[::-1])
            fname = f"/etc/bind/db.{rev}"
            named_lines.append(f'zone "{zname}" {{')
            named_lines.append('    type master;')
            named_lines.append(f'    file "{fname}";')
            named_lines.append('};')
            named_lines.append('')

    with open(os.path.join(bind_dir, 'named.conf'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(named_lines))

    # create zone files if provided (other authoritative zones)
    if zones:
        for zname, records in zones.items():
            # skip root zone if present in zones (we already created db.root)
            if zname == '.':
                continue
            # create filename like db.it.roma3 for zone roma3.it
            rev = '.'.join(zname.split('.')[::-1])
            zone_file_path = os.path.join(bind_dir, f"db.{rev}")
            serial_zone = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d') + '01'
            # If this host is authoritative for the domain, create SOA as requested
            zone_lines = [
                '$TTL 60000',
                f"@ IN SOA dns.{zname}. root.dns.{zname}. (",
                f"    {serial_zone} ; serial",
                '    28800 ;  refresh',
                '    14400 ; retry',
                '    3600000 ; expire',
                '    0 ; negative cache ttl',
                ')',
                '',
                format_dns_record('@', 'NS', f'dns.{zname}.'),
                '',
            ]
            # add records if provided (A/NS/CNAME/delegation etc.)
            if isinstance(records, dict):
                for h, ipval in records.items():
                    # support simple A record (string) or complex record (dict)
                    if isinstance(ipval, str):
                        zone_lines.append(format_dns_record(h, 'A', ipval))
                        continue
                    if isinstance(ipval, dict):
                        rtype = str(ipval.get('type', 'A')).upper()
                        if rtype == 'A':
                            ipaddr = ipval.get('ip')
                            if ipaddr:
                                zone_lines.append(format_dns_record(h, 'A', ipaddr))
                        elif rtype == 'NS':
                            ns_host = ipval.get('ns') or ipval.get('host')
                            if ns_host:
                                zone_lines.append(format_dns_record(h, 'NS', ns_host))
                                glue_ip = ipval.get('glue') or ipval.get('ip') or ipval.get('glue_ip')
                                if glue_ip:
                                    zone_lines.append(format_dns_record(ns_host, 'A', glue_ip))
                        elif rtype == 'DELEGATION':
                            child_zone = ipval.get('zone') or h
                            ns_host = ipval.get('ns')
                            ns_ip = ipval.get('ns_ip') or ipval.get('glue_ip') or ipval.get('ip')
                            if child_zone and ns_host:
                                zone_lines.append(format_dns_record(child_zone, 'NS', ns_host))
                                if ns_ip:
                                    zone_lines.append(format_dns_record(ns_host, 'A', ns_ip))
                        elif rtype == 'CNAME':
                            target = ipval.get('target')
                            if target:
                                zone_lines.append(format_dns_record(h, 'CNAME', target))
                        else:
                            ipaddr = ipval.get('ip')
                            if ipaddr:
                                zone_lines.append(format_dns_record(h, 'A', ipaddr))
            with open(zone_file_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write('\n'.join(zone_lines) + '\n')

    # startup: configure IP and start named
    gateway = gateway_cidr.split('/')[0] if '/' in gateway_cidr else gateway_cidr
    startup = f"ip address add {ip_cidr} dev eth0\nip route add default via {gateway} dev eth0\nsystemctl start named\n"
    startup_path = os.path.join(base_path, f"{name}.startup")
    with open(startup_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(startup)
    try:
        os.chmod(startup_path, 0o755)
    except Exception:
        pass

# -------------------------
# BGP relations: manual menu
# -------------------------
def aggiungi_relazioni_bgp_menu(base_path, routers):
    print("\n=== Aggiungi relazioni BGP (manuale) ===")
    if not routers:
        print("Nessun router disponibile.")
        return
    while True:
        print("\nRouter disponibili:")
        for rn, r in routers.items():
            print(f" - {rn} (ASN: {r.get('asn','-')})")
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
        # crea le righe neighbor da inserire dentro il blocco router bgp
        neighbor_lines = [f"neighbor {neigh_ip} remote-as {routers[dst]['asn']}",
                          f"neighbor {neigh_ip} description {rel}_{dst}"]
        insert_lines_into_protocol_block(fpath, proto='bgp', asn=None, lines=neighbor_lines)

        # se richiesto, aggiungi le policy (prefix-list / route-map) al fondo del file
        if aggiungi_policy:
            policy = []
            policy.append(f"neighbor {neigh_ip} prefix-list {rel}_{dst}_in in")
            policy.append(f"neighbor {neigh_ip} prefix-list {rel}_{dst}_out out")
            policy.append("")
            policy.append(f"ip prefix-list {rel}_{dst}_in permit any")
            policy.append(f"ip prefix-list {rel}_{dst}_out permit any")
            policy.append("")
            policy.append(f"route-map pref_{dst}_in permit 10")
            policy.append(f"    set local-preference {local_pref}")
            policy.append("")
            policy.append(f"neighbor {neigh_ip} route-map pref_{dst}_in in")
            with open(fpath, 'a', encoding='utf-8', newline='\n') as f:
                for line in policy:
                    f.write(line + "\n")
        print(f"Relazione BGP ({rel}) aggiunta su {src} verso {dst} (neighbor {neigh_ip}).")

# -------------------------
# Auto-generate BGP neighbors for routers sharing same LAN
# -------------------------
def auto_generate_bgp_neighbors(base_path, routers):
    """
    Per ogni coppia di router che condividono la stessa LAN (campo 'lan' su interfacce),
    aggiunge neighbor reciproci usando l'IP dell'interfaccia del peer collegata a quella LAN.
    """
    lan_map = {}
    for rname, rdata in routers.items():
        for iface in rdata["interfaces"]:
            lan = iface.get("lan")
            if not lan:
                continue
            lan_map.setdefault(lan, []).append((rname, iface["ip"], rdata.get("asn")))

    for lan, members in lan_map.items():
        if len(members) < 2:
            continue
        for i in range(len(members)):
            for j in range(i+1, len(members)):
                r1, ip1, asn1 = members[i]
                r2, ip2, asn2 = members[j]
                if "bgp" not in routers[r1]["protocols"] or "bgp" not in routers[r2]["protocols"]:
                    continue
                add_neighbor_if_missing(base_path, r1, ip2, routers[r2]['asn'], desc=f"Router {r2}")
                add_neighbor_if_missing(base_path, r2, ip1, routers[r1]['asn'], desc=f"Router {r1}")

def rimuovi_network_bgp_interne(base_path, routers):
    """Toglie dal blocco BGP le network dei link interni all'AS.

    Un link è interno se gli altri router sulla stessa LAN sono tutti dello
    stesso AS o non hanno BGP (es. as100r1 - as100r2). Come nelle soluzioni del
    corso (64 casi su 81) questi link non si annunciano in BGP: li porta l'IGP
    e li copre l'aggregato dell'AS. Restano le LAN di peering e le LAN senza
    altri router (che il testo spesso chiede di annunciare).
    """
    lan_members = {}
    for rname, rdata in routers.items():
        for iface in rdata.get('interfaces', []):
            if iface.get('lan'):
                lan_members.setdefault(iface['lan'], []).append(rname)
    for rname, rdata in routers.items():
        if 'bgp' not in rdata.get('protocols', []):
            continue
        my_as = _as_number(rname, rdata)
        interne = []
        for iface in rdata.get('interfaces', []):
            others = [o for o in lan_members.get(iface.get('lan'), []) if o != rname]
            if not others:
                continue
            peering = any('bgp' in routers[o].get('protocols', []) and _as_number(o, routers[o]) != my_as
                          for o in others)
            if not peering:
                interne.append(_norm_net(iface.get('ip', '')))
        if interne:
            fpath = os.path.join(base_path, rname, 'etc', 'frr', 'frr.conf')
            out, in_bgp = [], False
            for l in _leggi_righe(fpath):
                s = l.strip()
                if s.startswith('router '):
                    in_bgp = s.startswith('router bgp')
                elif l and not l[0].isspace():
                    in_bgp = False
                elif in_bgp and s.startswith('network ') and len(s.split()) == 2 \
                        and _norm_net(s.split()[1]) in interne:
                    continue
                out.append(l)
            _scrivi_righe(fpath, out)


def add_neighbor_if_missing(base_path, src_router, neigh_ip, neigh_asn, desc=None):
    fpath = os.path.join(base_path, src_router, "etc", "frr", "frr.conf")
    if not os.path.exists(fpath):
        return
    with open(fpath, "r") as f:
        content = f.read()
    # strip CIDR if present
    neigh_ip_stripped = neigh_ip.split('/')[0] if '/' in neigh_ip else neigh_ip
    if f"neighbor {neigh_ip_stripped} remote-as" in content:
        return
    # Costruiamo le righe neighbor (senza newline finali)
    lines = [f"neighbor {neigh_ip_stripped} remote-as {neigh_asn}"]
    if desc:
        lines.append(f"neighbor {neigh_ip_stripped} description {desc}")
    # Inseriamo le righe dentro il blocco 'router bgp' se presente,
    # altrimenti appendiamo a fine file
    insert_lines_into_protocol_block(fpath, proto='bgp', asn=None, lines=lines)


def add_ibgp_loopback_neighbors(base_path, routers):
    """
    Cerca tutte le coppie di router che hanno BGP abilitato e lo stesso ASN
    e che dispongono di almeno una loopback ciascuno. Per ogni coppia crea
    nei rispettivi `frr.conf` le righe iBGP basate sulle loopback:

      neighbor <peer-loopback> remote-as <asn>
      neighbor <peer-loopback> update-source <local-loopback>

    Questa funzione evita di duplicare righe esistenti.
    """
    # helper per garantire la coppia su due router
    def _ensure_pair(r_local, r_peer):
        r_local_data = routers.get(r_local, {})
        r_peer_data = routers.get(r_peer, {})
        if not r_local_data or not r_peer_data:
            return
        asn_local = str(r_local_data.get('asn', '')).strip()
        asn_peer = str(r_peer_data.get('asn', '')).strip()
        if not asn_local or asn_local != asn_peer:
            return
        # prendiamo la prima loopback disponibile per ciascun router
        lbs_local = r_local_data.get('loopbacks') or []
        lbs_peer = r_peer_data.get('loopbacks') or []
        if not lbs_local or not lbs_peer:
            return
        lb_local = _strip_cidr(lbs_local[0])
        lb_peer = _strip_cidr(lbs_peer[0])
        if not lb_local or not lb_peer:
            return

        # files frr.conf
        f_local = os.path.join(base_path, r_local, 'etc', 'frr', 'frr.conf')
        f_peer = os.path.join(base_path, r_peer, 'etc', 'frr', 'frr.conf')

        # assicurati che i file esistano
        if not os.path.exists(f_local) or not os.path.exists(f_peer):
            return

        # leggi contenuti per verifica duplicati
        try:
            with open(f_local, 'r') as fh:
                cont_local = fh.read()
        except Exception:
            cont_local = ''
        try:
            with open(f_peer, 'r') as fh:
                cont_peer = fh.read()
        except Exception:
            cont_peer = ''

        # prepara righe da inserire in r_local per parlare con r_peer
        to_add_local = []
        if f"neighbor {lb_peer} remote-as" not in cont_local:
            to_add_local.append(f"neighbor {lb_peer} remote-as {asn_local}")
        if f"neighbor {lb_peer} update-source" not in cont_local:
            to_add_local.append(f"neighbor {lb_peer} update-source {lb_local}")

        # prepara righe da inserire in r_peer per parlare con r_local
        to_add_peer = []
        if f"neighbor {lb_local} remote-as" not in cont_peer:
            to_add_peer.append(f"neighbor {lb_local} remote-as {asn_local}")
        if f"neighbor {lb_local} update-source" not in cont_peer:
            to_add_peer.append(f"neighbor {lb_local} update-source {lb_peer}")

        # inserisci dentro il blocco router bgp <asn>
        if to_add_local:
            insert_lines_into_protocol_block(f_local, proto='bgp', asn=asn_local, lines=to_add_local)
            print(f"✅ Aggiunti iBGP neighbor su {r_local}: {', '.join(to_add_local)}")
        if to_add_peer:
            insert_lines_into_protocol_block(f_peer, proto='bgp', asn=asn_local, lines=to_add_peer)
            print(f"✅ Aggiunti iBGP neighbor su {r_peer}: {', '.join(to_add_peer)}")

    # cicla per tutte le coppie (n^2) — i dati sono piccoli, va bene
    names = [n for n in routers.keys()]
    for i in range(len(names)):
        for j in range(i+1, len(names)):
            n1 = names[i]
            n2 = names[j]
            # entrambi devono avere BGP abilitato
            if 'bgp' not in routers.get(n1, {}).get('protocols', []) or 'bgp' not in routers.get(n2, {}).get('protocols', []):
                continue
            # devono avere ASN uguale e non vuoto
            asn1 = str(routers.get(n1, {}).get('asn', '')).strip()
            asn2 = str(routers.get(n2, {}).get('asn', '')).strip()
            if not asn1 or asn1 != asn2:
                continue
            # devono avere almeno una loopback ciascuno
            lbs1 = routers.get(n1, {}).get('loopbacks') or []
            lbs2 = routers.get(n2, {}).get('loopbacks') or []
            if not lbs1 or not lbs2:
                continue
            # ensure pair both ways
            _ensure_pair(n1, n2)

# -------------------------
# Modifica frr.conf con editor
# -------------------------
def modifica_router_menu(base_path, routers):
    print("\n=== Modifica frr.conf router ===")
    keys = list(routers.keys())
    for i, k in enumerate(keys, 1):
        print(f"{i}. {k}")
    idx = input_int("Seleziona router (numero, 0 per annullare): ", 0)
    if idx == 0 or idx > len(keys):
        return
    sel = keys[idx - 1]
    fpath = os.path.join(base_path, sel, "etc", "frr", "frr.conf")
    if not os.path.exists(fpath):
        print("frr.conf non trovato per", sel)
        return
    editor = os.environ.get("EDITOR", "nano")
    try:
        subprocess.call([editor, fpath])
    except Exception as e:
        print("Errore aprendo editor:", e)


# -------------------------
# Menu post-creazione: implementazione richieste (in italiano)
# -------------------------
def append_frr_stanza(base_path, router, stanza):
    fpath = os.path.join(base_path, router, "etc", "frr", "frr.conf")
    if not os.path.exists(fpath):
        print(f"⚠️ frr.conf non trovato per {router}: {fpath}")
        return False
    with open(fpath, 'a', encoding='utf-8', newline='\n') as f:
        f.write("\n" + stanza + "\n")
    return True

def insert_lines_into_protocol_block(fpath, proto='bgp', asn=None, lines=None):
    """Inserisce `lines` (lista di stringhe, senza newline) dentro la sezione 'router <proto>' di fpath.
    - proto: 'bgp', 'ospf', 'rip', etc.
    - asn: opzionale, quando fornito cerca la stanza che contiene anche l'ASN (utile per 'router bgp <asn>').
    Se non trova una sezione valida, appende le righe alla fine del file.
    Le righe saranno indentate con 4 spazi quando inserite dentro il blocco.
    """
    if lines is None:
        return False
    try:
        with open(fpath, 'r') as f:
            content = f.readlines()
    except Exception as e:
        print(f"❌ Errore leggendo {fpath}: {e}")
        return False

    # trova la prima occorrenza di 'router <proto>' (case insensitive per 'router')
    idx = None
    target_start = f'router {proto}'.lower()
    for i, L in enumerate(content):
        s = L.strip().lower()
        if s.startswith(target_start):
            # se viene passato un asn, verifichiamo che la linea lo contenga (case insensitive check on line)
            if asn and str(asn) not in L:
                continue
            idx = i
            break

    if idx is None:
        # non trovato: append a fine file
        try:
            with open(fpath, 'a', encoding='utf-8', newline='\n') as f:
                # Assicurati che ci sia una newline prima se il file non è vuoto e non finisce con newline
                if os.path.getsize(fpath) > 0:
                    # Leggi l'ultimo carattere per vedere se serve newline (costoso aprire in r+ o seek, 
                    # ma per sicurezza scriviamo sempre una newline iniziale se appendiamo)
                    f.write('\n')
                for l in lines:
                    f.write(l + '\n')
            return True
        except Exception as e:
            print(f"❌ Errore scrivendo (append) su {fpath}: {e}")
            return False

    # trova il punto di inserimento: il primo indice dopo il blocco indentato
    j = idx + 1
    while j < len(content):
        line = content[j]
        # considera appartenenti al blocco le linee vuote o indentate
        if line.startswith(' ') or line.startswith('\t') or line.strip() == '':
            j += 1
            continue
        # se incontriamo un commento di sezione (es. '!') trattiamolo come parte del blocco
        if line.lstrip().startswith('!'):
            j += 1
            continue
        break
    # inserisci prima delle righe vuote finali del blocco, così le nuove righe
    # restano attaccate al blocco e non a ciò che viene dopo
    while j - 1 > idx and content[j - 1].strip() == '':
        j -= 1

    # prepara le righe indentate
    ind_lines = [('    ' + l) for l in lines]
    
    # Assicurati che la riga precedente abbia un newline
    if j > 0 and not content[j-1].endswith('\n'):
        content[j-1] += '\n'

    # inserisci prima dell'indice j
    new_content = content[:j] + [l + '\n' for l in ind_lines] + content[j:]
    
    try:
        with open(fpath, 'w', encoding='utf-8', newline='\n') as f:
            f.writelines(new_content)
        return True
    except Exception as e:
        print(f"❌ Errore scrivendo su {fpath}: {e}")
        return False

def select_router(routers, prompt="Seleziona router:"):
    keys = list(routers.keys())
    if not keys:
        print("Nessun router disponibile.")
        return None
    # stampa menu ordinato
    items = [f"{k} (ASN: {routers[k].get('asn','-')})" for k in keys]
    print_menu(prompt, items)
    while True:
        sel = input("Numero router (o nome, vuoto per annullare): ").strip()
        if not sel:
            return None
        if sel.isdigit():
            idx = int(sel)
            if 1 <= idx <= len(keys):
                return keys[idx-1]
            print("Indice non valido.")
        else:
            if sel in routers:
                return sel
            print("Nome router non valido.")

def select_interface(router_data):
    if not router_data or not router_data.get('interfaces'):
        print('Nessuna interfaccia disponibile per questo router.')
        return None
    ifaces = router_data['interfaces']
    items = [f"{it.get('name')} - {it.get('ip')}" for it in ifaces]
    print_menu('Interfacce disponibili:', items)
    while True:
        sel = input('Seleziona interfaccia (numero o nome, vuoto per annullare): ').strip()
        if not sel:
            return None
        if sel.isdigit():
            idx = int(sel)
            if 1 <= idx <= len(ifaces):
                return ifaces[idx-1]['name']
            print('Indice non valido.')
        else:
            for it in ifaces:
                if it.get('name') == sel:
                    return sel
            print('Nome interfaccia non valido.')

def get_first_iface_ip(ifaces):
    # ritorna l'IP (senza /prefisso) della prima interfaccia fornita
    if not ifaces:
        return None
    ip_cidr = ifaces[0].get("ip")
    if not ip_cidr:
        return None
    return ip_cidr.split("/")[0]


def _strip_cidr(ip_cidr):
    if not ip_cidr:
        return None
    return str(ip_cidr).split('/')[0]


def collect_lab_ips(lab_path, routers=None):
    """Raccoglie gli endpoint del lab: tutte le IP associate a interfacce.

    Restituisce una lista di dict con chiavi: 'ip', 'name', 'iface'.
    - Se `routers` è fornito (dict), prende gli IP dalle interfacce dei router
      e imposta 'name' al nome del router e 'iface' al nome dell'interfaccia.
    - Scansiona i file `*.startup` nella directory del lab per trovare tutte le
      occorrenze di `ip address add <ip>` e aggiunge record con 'name' = nome
      del file (senza .startup) e 'iface' se presente nella riga.
    Mantiene l'ordine di scoperta e rimuove duplicati identici (stesso IP, name, iface).
    """
    endpoints = []
    seen = set()
    # dai router
    if routers:
        for rname, rdata in routers.items():
            for iface in rdata.get('interfaces', []):
                ip = _strip_cidr(iface.get('ip'))
                if ip:
                    key = (ip, rname, iface.get('name'))
                    if key not in seen:
                        seen.add(key)
                        endpoints.append({'ip': ip, 'name': rname, 'iface': iface.get('name')})

    # dai file .startup (tutte le occorrenze)
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
                            # ip address add <ip> [dev <iface>]
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
    """Genera una one-liner bash che esegue `ping -c 1` su ogni endpoint.

    `endpoints` è una lista di dict con chiavi: 'ip', 'name', 'iface'. La one-liner
    esegue un singolo ping per IP e stampa per ogni record: "<ip> (<name> <iface>): <loss> packet loss"
    o "no reply" se l'output non è parsabile.
    """
    if not endpoints:
        return ''
    toks = []
    for e in endpoints:
        ip = e.get('ip')
        name = e.get('name') or ''
        iface = e.get('iface') or ''
        # escape any double quotes by removing them (names shouldn't contain quotes normally)
        token = f"{ip}|{name}|{iface}"
        toks.append(f'"{token}"')
    recs = ' '.join(toks)
    # single probe, print packet loss percentage extracted from ping summary
    cmd = (
        "for rec in " + recs + "; do IFS='|' read -r ip name iface <<< \"$rec\"; "
        "out=$(ping -c 1 \"$ip\" 2>&1); "
        "loss=$(echo \"$out\" | awk -F',' '/packet loss/ {print $3}' | awk '{print $1}'); "
        "if [ -z \"$loss\" ]; then echo -e \"[!] $ip ($name $iface): no reply\"; else "
        "loss_num=$(echo \"$loss\" | tr -d '%'); "
        "if [ \"$loss_num\" = \"0\" ]; then echo -e \"[OK] $ip ($name $iface): $loss packet loss\"; else echo -e \"[!] $ip ($name $iface): $loss packet loss\"; fi; fi; done"
    )
    return cmd

def find_routers_by_asn(routers, asn):
    return [name for name, r in routers.items() if str(r.get("asn","")) == str(asn)]

def assegna_costo_interfaccia(base_path, routers):
    print('\n--- Assegna costo OSPF su una interfaccia di un router ---')
    target = select_router(routers, prompt='Seleziona il router su cui impostare il costo OSPF:')
    if not target:
        print('Operazione annullata.')
        return
    # Validation: il router deve avere OSPF abilitato
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

# implementa_relazioni_as: rimosso — usare la creazione manuale di neighbor o riabilitare se necessario

# asboh_lookup_option: rimosso — l'operazione richiede consultazione esterna

# filter_as10_from_as60: rimosso — puoi riattivare la versione interattiva se ti serve

def ensure_neighbor_exists(fpath, neigh_ip):
    """Se non esiste una riga 'neighbor <ip> remote-as' nel file fpath, chiede ASN e la crea."""
    try:
        with open(fpath, 'r') as f:
            content = f.read()
    except Exception:
        return False
    neigh_ip_stripped = neigh_ip.split('/')[0] if '/' in neigh_ip else neigh_ip
    if f"neighbor {neigh_ip_stripped} remote-as" in content:
        return True
    # chiedi ASN all'utente
    asn = input_asn(f"ASN del neighbor {neigh_ip_stripped} (necessario per creare il neighbor): ")
    # inserisci il neighbor dentro il blocco router bgp
    lines = [f"neighbor {neigh_ip_stripped} remote-as {asn}"]
    insert_lines_into_protocol_block(fpath, proto='bgp', asn=None, lines=lines)
    return True

def _leggi_righe(fpath):
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            return f.read().split('\n')
    except OSError:
        return []


def _scrivi_righe(fpath, righe):
    # al massimo una riga vuota consecutiva, file che termina con un a capo
    out = []
    for l in righe:
        if l.strip() == '' and out and out[-1].strip() == '':
            continue
        out.append(l.rstrip())
    with open(fpath, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(out).rstrip('\n') + '\n')


def _rimuovi_righe(fpath, pred):
    righe = _leggi_righe(fpath)
    nuove = [l for l in righe if not pred(l)]
    if len(nuove) != len(righe):
        _scrivi_righe(fpath, nuove)


def _rimuovi_route_map(fpath, rm_name):
    """Toglie tutte le entry 'route-map <rm_name> ...' con le righe match/set che seguono."""
    out, dentro = [], False
    for l in _leggi_righe(fpath):
        s = l.strip()
        if s.startswith(f"route-map {rm_name} "):
            dentro = True
            continue
        if dentro and re.match(r'(match|set|on-match|call|continue)\b', s):
            continue
        dentro = False
        out.append(l)
    _scrivi_righe(fpath, out)


def _append_righe(fpath, righe):
    """Accoda un blocco di righe globali (prefix-list, route-map) separato da una riga vuota."""
    _scrivi_righe(fpath, _leggi_righe(fpath) + [''] + list(righe))


def aggiungi_network_bgp(base_path, routers):
    """Aggiunge una o più `network` al blocco router bgp (aggregato dell'AS,
    reti interne imparate con l'IGP, 0.0.0.0/0, ...)."""
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
    reti = input_reti(f"Reti da annunciare in BGP, separate da virgola (invio = {', '.join(proposta)}): ",
                      default=proposta)
    # reti già annunciate nel solo blocco router bgp (non quelle di RIP/OSPF)
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

    # reti già annunciate contenute in un aggregato appena aggiunto: spesso la
    # soluzione annuncia solo l'aggregato (es. 100.0.0.0/8 al posto di 100.0.0.0/24)
    aggregati = [ipaddress.ip_network(r) for r in nuove]
    # le LAN di peering (condivise con router di un altro AS) restano sempre annunciate
    peering = _reti_peering(target, routers)
    coperte = sorted(p for p in presenti
                     if p not in peering
                     and any(ipaddress.ip_network(p) != a and ipaddress.ip_network(p).subnet_of(a) for a in aggregati))
    if coperte:
        ans = input(f"Le reti {', '.join(coperte)} sono già contenute nell'aggregato. "
                    f"Toglierle da BGP e annunciare solo l'aggregato? (s/N): ").strip().lower()
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
    """Aggiunge al server root (master per '.') la delega di una zona:
    '<zona>. NS <ns>.' + glue '<ns>. A <ip>'. Se db.root non ha il SOA, lo aggiunge."""
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
    scelto = dns[int(sel) - 1] if sel.isdigit() and 1 <= int(sel) <= len(dns) else next((x for x in dns if x[0] == sel), None)
    if not scelto:
        print('Selezione non valida.')
        return
    nome, master = scelto
    if not master:
        print(f"⚠️ {nome} non è il root (in named.conf la zona '.' non è 'type master'): "
              f"le deleghe dei domini di primo livello vanno sul root.")
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
        import datetime
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


def _lan_members(routers):
    out = {}
    for rn, rd in routers.items():
        for it in rd.get('interfaces', []):
            if it.get('lan'):
                out.setdefault(it['lan'], []).append(rn)
    return out


def _reti_peering(rname, routers):
    """Reti delle LAN che il router condivide con router BGP di un altro AS."""
    members = _lan_members(routers)
    my_as = _as_number(rname, routers[rname])
    out = set()
    for it in routers[rname].get('interfaces', []):
        others = [o for o in members.get(it.get('lan'), []) if o != rname]
        if any('bgp' in routers[o].get('protocols', []) and _as_number(o, routers[o]) != my_as for o in others):
            out.add(_norm_net(it.get('ip', '')))
    return out


def _ip_verso(routers, y, x, asn):
    """IP dell'interfaccia di `y` da cui partono i pacchetti verso `x`, seguendo il
    percorso più corto dentro l'AS (router dello stesso AS o senza BGP, collegati da
    LAN). Senza 'update-source' una sessione iBGP si apre solo se l'IP configurato
    sull'altro router coincide con questo indirizzo sorgente."""
    def interno(r):
        rd = routers[r]
        return ('bgp' not in rd.get('protocols', []) and rd.get('protocols')) or \
               str(rd.get('asn', '')).strip() == asn
    members = _lan_members(routers)
    # BFS da y: per ogni router raggiunto ricorda la prima LAN usata uscendo da y
    first_lan = {y: None}
    coda = [y]
    while coda:
        r = coda.pop(0)
        for it in routers[r].get('interfaces', []):
            lan = it.get('lan')
            for o in members.get(lan, []):
                if o in first_lan or not interno(o):
                    continue
                first_lan[o] = first_lan[r] or lan
                if o == x:
                    lan_y = first_lan[o]
                    for it_y in routers[y].get('interfaces', []):
                        if it_y.get('lan') == lan_y:
                            return str(ipaddress.ip_interface(it_y['ip']).ip)
                coda.append(o)
    # nessun percorso interno trovato: prima interfaccia coperta dall'IGP
    data = routers[y]
    igp = [ipaddress.ip_network(n, strict=False) for n in (data.get('igp_networks') or default_igp_networks(y, data))]
    ifs = [ipaddress.ip_interface(it['ip']) for it in data.get('interfaces', []) if it.get('ip')]
    for i in ifs:
        if any(i.ip in n for n in igp):
            return str(i.ip)
    return str(ifs[0].ip) if ifs else None


def aggiungi_ibgp_full_mesh(base_path, routers):
    """Crea le sessioni iBGP mancanti tra tutti i router BGP di uno stesso AS
    (full mesh), usando per ogni vicino un IP interno raggiungibile via IGP."""
    print('\n--- Aggiungi sessioni iBGP (full mesh nell\'AS) ---')
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
    sel = input('Seleziona l\'AS (numero nella lista o numero AS, vuoto per annullare): ').strip()
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
            ips_y = {str(ipaddress.ip_interface(it['ip']).ip) for it in routers[y].get('interfaces', []) if it.get('ip')}
            if presenti & ips_y:
                continue  # sessione già presente (es. creata sulla LAN condivisa)
            ip = _ip_verso(routers, y, x, sel)
            if ip:
                nuove += [f"neighbor {ip} remote-as {sel}", f"neighbor {ip} description iBGP {y}"]
        if nuove:
            insert_lines_into_protocol_block(fpath, proto='bgp', asn=None, lines=nuove)
            aggiunte += len(nuove) // 2
            print(f"✅ {x}: " + ', '.join(l.split()[1] for l in nuove if 'remote-as' in l))
    print(f"Sessioni iBGP aggiunte: {aggiunte}" if aggiunte else 'Tutte le sessioni iBGP erano già presenti.')


class Annullato(Exception):
    """Invio a vuoto durante le domande di una policy: si torna al menu senza scrivere nulla."""


def _chiedi(prompt, vuoto_ok=False):
    """input() per le policy: Invio a vuoto annulla (salvo vuoto_ok=True)."""
    s = input(prompt).strip()
    if not s and not vuoto_ok:
        raise Annullato()
    return s


def _chiedi_ip(prompt):
    while True:
        s = _chiedi(prompt).split('/')[0]
        try:
            ipaddress.ip_address(s)
            return s
        except ValueError:
            print("❌ IP non valido (es. 10.0.0.2). Invio a vuoto per annullare.")


def _chiedi_asn(prompt):
    while True:
        s = _chiedi(prompt)
        if asn_valido(s):
            return s
        print("❌ Numero AS non valido: solo cifre (es. 20). Invio a vuoto per annullare.")


def _chiedi_int(prompt, min_val=0):
    while True:
        s = _chiedi(prompt)
        if s.isdigit() and int(s) >= min_val:
            return int(s)
        print(f"❌ Inserisci un intero ≥ {min_val}. Invio a vuoto per annullare.")


def _chiedi_reti(prompt, vuoto_ok=False):
    while True:
        s = _chiedi(prompt, vuoto_ok=vuoto_ok)
        if not s:
            return []
        try:
            return parse_reti(s)
        except ValueError as e:
            print(f"❌ Rete non valida: {e}. Invio a vuoto per annullare.")


def _chiedi_direzione():
    while True:
        s = _chiedi('Direzione (in/out): ').lower()
        if s in ('in', 'out'):
            return s
        print("Scrivi 'in' oppure 'out' (Invio a vuoto per annullare).")


def _neighbor_presente(fpath, ip):
    return any(re.match(rf"\s*neighbor {re.escape(ip)} remote-as\b", l) for l in _leggi_righe(fpath))


def _collega_al_neighbor(fpath, ip, tipo, nome, direz):
    """Collega prefix-list/route-map al neighbor dentro router bgp. FRR tiene un solo
    oggetto per tipo e direzione: se ce n'è già un altro, il collegamento viene sostituito."""
    vecchie = [l for l in _leggi_righe(fpath)
               if re.match(rf"\s*neighbor {re.escape(ip)} {tipo} (\S+) {direz}\s*$", l)
               and l.split()[3] != nome]
    for v in vecchie:
        print(f"⚠️ {ip} aveva già '{v.strip()}': FRR ne usa una sola per direzione, la sostituisco con {nome}.")
    if vecchie:
        _rimuovi_righe(fpath, lambda l: l in vecchie)
    riga = f"neighbor {ip} {tipo} {nome} {direz}"
    if not any(l.strip() == riga for l in _leggi_righe(fpath)):
        insert_lines_into_protocol_block(fpath, proto='bgp', asn=None, lines=[riga])


def _scrivi_route_map(fpath, rm_name, stanza, pl_name=None):
    """Sostituisce (o crea) la route-map rm_name e l'eventuale prefix-list associata."""
    if any(l.strip().startswith(f"route-map {rm_name} ") for l in _leggi_righe(fpath)):
        print(f"⚠️ La route-map {rm_name} esiste già: la sostituisco.")
        _rimuovi_route_map(fpath, rm_name)
    if pl_name:
        _rimuovi_righe(fpath, lambda l: l.strip().startswith(f"ip prefix-list {pl_name} "))
    _append_righe(fpath, stanza)


def policies_menu(base_path, routers):
    """Sotto-menu per applicare policies BGP ai router del lab.
    Prima vengono fatte tutte le domande (Invio a vuoto annulla), poi si scrive."""
    while True:
        items = [
            'Prefix-list: scarta una o più reti da/verso un neighbor (deny ... + permit any)',
            'Local-preference in ingresso (su tutte le rotte o solo su alcune reti)',
            'MED (metric) in uscita',
            'Access-list: scarta una rete in ingresso (via route-map)',
            'Configurazione Customer-Provider-Peer'
        ]
        print_menu('=== Policies BGP (scegli) ===', items, extra_options=[('0', 'Torna indietro')])
        c = input('Seleziona (numero): ').strip()
        if c == '0':
            break
        if c not in ('1', '2', '3', '4', '5'):
            print('Scelta non valida.')
            continue

        if c == '5':
            aggiungi_customer_provider_wizard(base_path, routers)
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

            # --- domande (nessuna scrittura finché non sono finite)
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
                reti = _chiedi_reti('Solo per alcune reti? Inserisci le reti separate da virgola '
                                    '(Invio = tutte le rotte): ', vuoto_ok=True)
            elif c == '3':
                m_val = _chiedi_int('Valore metric (MED) da impostare (es. 20): ', 0)
            elif c == '4':
                reti = _chiedi_reti('Rete da bloccare in ingresso (es. 10.0.1.0/24): ')
        except Annullato:
            print('Annullato: nessuna modifica.')
            continue

        # --- scritture
        if nuovo_asn:
            insert_lines_into_protocol_block(fpath, proto='bgp', asn=None,
                                             lines=[f"neighbor {neigh_ip} remote-as {nuovo_asn}"])
        tag = neigh_ip.replace('.', '_')

        if c == '1':
            pl_name = f"PL_{src}_{tag}_{direz}"
            # Se la prefix-list esiste già (opzione usata più volte sullo stesso
            # neighbor) la riscriviamo intera: tutti i deny PRIMA del 'permit any',
            # altrimenti i deny aggiunti dopo non avrebbero effetto.
            pat = re.compile(rf"^\s*ip prefix-list {re.escape(pl_name)} deny (\S+)")
            prev = [m.group(1) for m in map(pat.match, _leggi_righe(fpath)) if m]
            tutte = prev + [r for r in reti if r not in prev]
            _rimuovi_righe(fpath, lambda l: l.strip().startswith(f"ip prefix-list {pl_name} "))
            _append_righe(fpath, [f"ip prefix-list {pl_name} deny {r}" for r in tutte]
                          + [f"ip prefix-list {pl_name} permit any"])
            _collega_al_neighbor(fpath, neigh_ip, 'prefix-list', pl_name, direz)
            print(f"✅ {src}: prefix-list {pl_name} ({direz}, neighbor {neigh_ip}): "
                  f"deny {', '.join(tutte)} + permit any.")

        elif c == '2':
            rm_name, pl_name = f"PREF_IN_{tag}", f"PREF_IN_{tag}_NETS"
            if reti:
                # come nelle soluzioni: entry 10 con match (solo quelle reti),
                # entry 20 senza condizioni per lasciar passare tutto il resto
                stanza = [f"route-map {rm_name} permit 10",
                          f"    match ip address prefix-list {pl_name}",
                          f"    set local-preference {lp_val}",
                          f"route-map {rm_name} permit 20",
                          ""] + [f"ip prefix-list {pl_name} permit {r}" for r in reti]
            else:
                stanza = [f"route-map {rm_name} permit 10", f"    set local-preference {lp_val}"]
            _scrivi_route_map(fpath, rm_name, stanza, pl_name)
            _collega_al_neighbor(fpath, neigh_ip, 'route-map', rm_name, 'in')
            print(f"✅ {src}: route-map {rm_name} (neighbor {neigh_ip}, in): local-preference {lp_val} "
                  f"{'per ' + ', '.join(reti) if reti else 'su tutte le rotte'}.")

        elif c == '3':
            rm_name = f"LOCALMED_OUT_{tag}"
            _scrivi_route_map(fpath, rm_name, [f"route-map {rm_name} permit 10", f"    set metric {m_val}"])
            _collega_al_neighbor(fpath, neigh_ip, 'route-map', rm_name, 'out')
            print(f"✅ {src}: route-map {rm_name} (neighbor {neigh_ip}, out): metric {m_val}.")

        elif c == '4':
            # primo ID di access-list libero da 10 in su
            contenuto = '\n'.join(_leggi_righe(fpath))
            acl_id = 10
            while re.search(rf"access-list {acl_id}\b", contenuto):
                acl_id += 10
            rm_name = f"FILTER_IN_{tag}"
            stanza = [f"access-list {acl_id} deny {r}" for r in reti] + [f"access-list {acl_id} permit any", "",
                      f"route-map {rm_name} permit 10", f"    match ip address {acl_id}"]
            _scrivi_route_map(fpath, rm_name, stanza)
            _collega_al_neighbor(fpath, neigh_ip, 'route-map', rm_name, 'in')
            print(f"✅ {src}: access-list {acl_id} (deny {', '.join(reti)}) e route-map {rm_name} "
                  f"(neighbor {neigh_ip}, in).")


# -------------------------
# Riepilogo configurazione (controllo del testo durante la prova)
# -------------------------
def _analizza_frr(righe):
    """Estrae da frr.conf ciò che serve al riepilogo, indipendentemente dall'indentazione."""
    cfg = {'asn': None, 'bgp_networks': [], 'neighbors': {}, 'descr': {}, 'link': {},
           'igp': {}, 'redistribute': {}, 'costi': [], 'prefix_lists': {}, 'access_lists': {},
           'route_maps': {}, 'auto_cost': None}
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
                # access-list: la riportiamo così com'è (es. "deny 9.0.0.0/8; permit any")
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
    """Cerca refusi di LAN/IP leggendo lab.conf e gli startup del lab.
    Ritorna una lista di avvisi (vuota se è tutto coerente):
      - stessa LAN con interfacce in subnet diverse
      - stessa subnet su LAN con nomi diversi (nome della LAN sbagliato)
      - link /30-/31 con un solo dispositivo o con più di due
    Una LAN /24 con un solo router è normale (rete interna/stub): non viene segnalata.
    Segnala anche i nomi di dispositivo che Kathará non accetta (es. 'web-srv')."""
    nodes, _ = parse_lab_conf_for_nodes(lab_path)
    avvisi = [f"Nome '{n}' non valido per Kathará (solo lettere minuscole, cifre e _): il lab non si "
              f"avvierà. Apri il lab dal menu 5 (Opzioni): propone di rinominarlo in "
              f"'{correggi_nome_kathara(n)}' senza perdere le altre modifiche."
              for n in sorted(nodes) if not nome_kathara_valido(n)]
    per_lan = {}     # lan -> [(nodo, ethN, interfaccia)]
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
            avvisi.append(f"LAN {lan}: link {corte[0].network} con un solo dispositivo ({chi}). "
                          f"Manca l'altro estremo o il nome della LAN è sbagliato?")
        elif corte and len(membri) > 2:
            avvisi.append(f"LAN {lan}: link {corte[0].network} con {len(membri)} dispositivi ({chi})")
    # LAN con un nodo senza IP (switch/bridge, es. exapus, patchwork): più LAN possono
    # essere lo stesso segmento con la stessa subnet, non è un errore
    con_switch = {lan for lan, membri in per_lan.items() if any(i is None for _, _, i in membri)}
    for rete, lans in sorted(subnet_lan.items()):
        if len(lans) > 1 and not (lans & con_switch):
            avvisi.append(f"Subnet {rete} usata su LAN diverse ({', '.join(sorted(lans))}): "
                          f"probabile nome di LAN sbagliato")
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


def _contiene(rete, ip):
    try:
        return ipaddress.ip_address(ip.split('/')[0]) in ipaddress.ip_network(rete, strict=False)
    except ValueError:
        return False


def _esito_prefix_list(voci, rete):
    """Azione della prima voce che corrisponde alla rete; None = nessuna (viene scartata)."""
    try:
        r = ipaddress.ip_network(rete, strict=False)
    except ValueError:
        return 'deny'       # network malformata: FRR l'ha già scartata, non è un problema della lista
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
    o definite ma non usate (avviso, spesso è lo stesso nome scritto in due modi).
    Ritorna [{'riga', 'testo', 'gravita': 'errore'|'avviso', 'messaggio'}] ordinati per riga.
    Verificato su FRR 10.5.3: con una route-map o prefix-list inesistente su un neighbor
    (in o out) FRR non dà errori e la sessione è Established, ma non passa nessuna rotta."""
    definiti = {'route-map': {}, 'prefix-list': {}, 'access-list': {}}      # nome -> prima riga
    usi = []                                                              # (riga, testo, tipo, nome, contesto)
    voci_pl, scartate, reti_bgp, blocco = {}, [], [], None      # voci valide, righe non valide, network BGP
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
        m = re.search(r'\broute-map (\S+)', s)          # redistribute ... route-map, table-map, ...
        if m:
            usi.append((n, s, 'route-map', m.group(1), ('altro',)))
    usati = {(tipo, nome) for _, _, tipo, nome, _ in usi}
    art = {'route-map': 'la ', 'prefix-list': 'la ', 'access-list': "l'"}
    out = []
    for n, s, nome, valore in scartate:
        proposta = next((r for _, r in reti_bgp if _contiene(r, valore)), None)
        out.append({'riga': n, 'testo': s, 'gravita': 'errore',
                    'messaggio': f"'{valore}' non è valido in una prefix-list (serve una rete con la maschera): "
                                 f"FRR scarta la riga." + (f" Forse intendevi {proposta}?" if proposta else '')})
    for n, s, tipo, nome, ctx in usi:
        if nome in definiti[tipo]:
            continue
        if ctx[0] == 'neighbor':
            effetto = (f"FRR non dà errori e la sessione resta Established, ma "
                       f"{'da' if ctx[2] == 'in' else 'verso'} {ctx[1]} non passa nessuna rotta.")
        elif ctx[0] == 'match':
            effetto = "questa voce della route-map non troverà mai corrispondenze (il suo 'set' non si applica)."
        else:
            effetto = "il riferimento non porta a niente."
        simili = difflib.get_close_matches(nome, list(definiti[tipo]), n=1, cutoff=0.6)
        forse = f" Forse intendevi {simili[0]} (riga {definiti[tipo][simili[0]]})?" if simili else ''
        if any(x[2] == nome for x in scartate):
            forse = ' Tutte le sue righe sono scartate: correggile.'
        out.append({'riga': n, 'testo': s, 'gravita': 'errore',
                    'messaggio': f"{art[tipo]}{tipo} {nome} non è definita: {effetto}{forse}"})
    # una rete annunciata dal router che la sua prefix-list in uscita non nomina. Non si segnalano
    # un 'deny' esplicito (è una scelta) e i link verso provider e peer: nelle soluzioni del corso
    # (red-baron, pear-to-pear) non si annunciano. Un vicino senza filtri in uscita è un customer.
    liste_out = {c[1]: nome for _, _, tipo, nome, c in usi
                 if tipo == 'prefix-list' and c[0] == 'neighbor' and c[2] == 'out'}

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
                    out.append({'riga': n, 'testo': s, 'gravita': 'avviso',
                                'messaggio': f"questo router annuncia {rete} (riga {riga}), ma la prefix-list {nome} "
                                             f"non la lascia passare verso {ctx[1]}: se il testo vuole annunciarla, "
                                             f"aggiungila."})
    for tipo, nomi in definiti.items():
        for nome, n in nomi.items():
            if (tipo, nome) not in usati:
                out.append({'riga': n, 'testo': f"{tipo} {nome}", 'gravita': 'avviso',
                            'messaggio': f"{art[tipo]}{tipo} {nome} è definita ma non è usata da nessuna parte "
                                         f"(nome scritto diverso dove dovrebbe essere usata?)."})
    return sorted(out, key=lambda x: x['riga'])


def controlli_configurazione(lab_path):
    """Cerca le dimenticanze tipiche leggendo solo i file del lab (lab.conf,
    startup, frr.conf). Non modifica nulla: ritorna una lista di avvisi.

      1. reti interne di un AS con IGP non annunciate in BGP da nessun suo router
         (sulle 26 soluzioni scatta solo dove il testo dice che non devono essere visibili)
      2. iBGP incompleto tra i router BGP dello stesso AS
      3. neighbor con IP inesistente o remote-as diverso dall'AS del vicino
      4. prefix-list / route-map / access-list usate ma non definite (o definite ma non usate)
      5. host senza default gateway
      6. costi OSPF espliciti senza 'auto-cost reference-bandwidth 100' (Opzioni 10)
      7. pc, www e dns: gateway, resolver, apache2, deleghe DNS e record A (controlli_host)
    """
    nodes, _ = parse_lab_conf_for_nodes(lab_path)
    ips, rotte = {}, {}          # (nodo, dev) -> interfaccia ; nodo -> ha rotte
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

    # 1. reti interne non annunciate: "isole" IGP = router OSPF/RIP collegati da LAN,
    #    senza attraversare un confine tra AS diversi
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
                    pass        # riga malformata (es. '1.2.0.0./30'): FRR la scarterebbe
        mancanti = set()
        for membri in lan_membri.values():
            rs = [n for n, _ in membri if n in cfg]
            if not rs or any(r not in isola for r in rs):
                continue            # LAN di peering o fuori dall'isola
            for n, dev in membri:
                i = ips.get((n, dev))
                if i and not any(i.ip in a for a in annunciate):
                    mancanti.add(str(i.network))
        if mancanti:
            asn = cfg[bordo[0]]['asn']
            proposta = next((e.split()[0] for b in bordo for p in ('ospf', 'rip')
                             for e in cfg[b]['igp'].get(p, []) if not e.startswith('area')), '')
            avvisi.append(
                f"AS{asn}: reti interne non annunciate in BGP ({', '.join(sorted(mancanti))}). "
                f"Gli altri AS non le raggiungono -> Opzioni 6 su {', '.join(sorted(bordo))}"
                + (f" (es. {proposta})" if proposta else '')
                + ", a meno che il testo dica che non devono essere visibili.")

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
            avvisi.append(f"AS{asn}: sessioni iBGP mancanti ({'; '.join(mancano)}). "
                          f"Se il testo le chiede -> Opzioni 7; se le vieta (es. butterfly) va bene così.")

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

    # 5. host senza gateway (nodi senza FRR, con IP e nessuna rotta)
    for n in sorted(nodes):
        if n not in cfg and n in ips_di and not rotte.get(n):
            avvisi.append(f"{n}: nessun default gateway, non raggiungerà nulla fuori dalla sua LAN.")

    # 6. costi OSPF espliciti con il costo predefinito di kathara/frr (10000): il testo
    #    presuppone 10, quindi un costo "alto" come 90 diventa il link più conveniente
    for et, rs, cfgs in isole_ospf(lab_path):
        costi = [f"{r} {c}" for r in rs for c in cfgs[r]['costi']]
        senza = [r for r in rs if not cfgs[r]['auto_cost']]
        if costi and senza:
            avvisi.append(
                f"{et}: costi OSPF espliciti ({', '.join(costi)}), ma in kathara/frr il costo predefinito "
                f"delle altre interfacce è 10000, non 10: il costo indicato renderà quel link il più "
                f"conveniente invece del più caro. Se il testo chiede percorsi che dipendono da questo "
                f"costo -> Opzioni 10 su {et} (verifica con la GUI: show ip ospf interface / Verifica percorso).")

    # 7. pc, www e dns
    for n, msg in controlli_host(lab_path):
        avvisi.append(f"{n}: {msg}")
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


def riepilogo_configurazione(base_path, routers):
    """Stampa per ogni router: AS, network BGP, IGP, costi OSPF e, per ogni neighbor,
    le policy collegate. Serve a spuntare il testo dell'esercizio frase per frase."""
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
                print(f"  {igp.upper()}: {', '.join(cfg['igp'][igp]) or '-'}"
                      + (f"   redistribute {', '.join(red)}" if red else '')
                      + (f"   auto-cost {cfg['auto_cost']}" if igp == 'ospf' and cfg['auto_cost'] else ''))
        if cfg['costi']:
            print(f"  costo OSPF: {', '.join(cfg['costi'])}")
        if cfg['asn']:
            print(f"  network BGP: {', '.join(cfg['bgp_networks']) or '-'}")
            for ip, asn in cfg['neighbors'].items():
                chi = owner.get(ip) or cfg['descr'].get(ip, '?')
                tipo = 'iBGP' if asn == cfg['asn'] else 'eBGP'
                link = cfg['link'].get(ip, [])
                if not link:
                    print(f"  {ip:<15} {chi:<10} AS{asn:<5} {tipo}  nessuna policy")
                    continue
                for i, (t, nome, direz) in enumerate(link):
                    if t == 'prefix-list':
                        cosa = (f"prefix-list {_descrivi_lista(cfg['prefix_lists'][nome])}"
                                if nome in cfg['prefix_lists'] else f"prefix-list {nome} (non definita!)")
                    elif t == 'route-map':
                        cosa = f"route-map {_descrivi_route_map(cfg, nome)}"
                    else:
                        cosa = f"{t} {nome}"
                    testa = f"  {ip:<15} {chi:<10} AS{asn:<5} {tipo}" if i == 0 else ' ' * 37
                    print(f"{testa}  {direz:<3}: {cosa}")
    disp = leggi_dispositivi(base_path)
    stampa_host_e_server(base_path, disp)
    print("\nControlla ogni frase del testo: filtri (deny), preferenze (local-preference),"
          " MED (metric), network annunciate, costi OSPF, gateway e resolver dei pc, deleghe DNS.")
    # scorciatoia verso la modifica (Opzioni 11) dei dispositivi citati dai controlli
    citati = [n for n in sorted(disp) if _problemi_di(n, avvisi)]
    if citati:
        print(f"\nDispositivi citati nei controlli: {', '.join(citati)}")
        s = input("Vuoi correggere un dispositivo adesso? (nome, Invio = no): ").strip()
        if s in disp:
            modifica_dispositivo_menu(base_path, routers, s)
        elif s:
            print(f"'{s}' non è un dispositivo del lab: puoi usare Opzioni 11.")


def assegna_resolv_conf(base_path):
    """
    Interattivo per assegnare un file `resolv.conf` a un singolo dispositivo
    presente nella cartella `base_path`.

    Opzioni:
    1) imposta un unico nameserver (IP)
    2) inserisci il contenuto completo di resolv.conf (termina con una linea '.' da sola)
    3) copia il `resolv.conf` da un altro dispositivo che lo possiede
    """
    # elenca dispositivi: includi sia sottocartelle che eventuali file '<name>.startup'
    try:
        dir_items = [d for d in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, d)) and not d.startswith('.')]
        # aggiungi file .startup come possibili host/client (rimuovi estensione)
        startup_files = []
        for fn in os.listdir(base_path):
            if fn.endswith('.startup') and os.path.isfile(os.path.join(base_path, fn)):
                startup_files.append(os.path.splitext(fn)[0])
        # unisci e deduplica
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

    # assicurati che la directory del dispositivo esista (per host creati come .startup la creiamo ora)
    device_dir = os.path.join(base_path, target)
    os.makedirs(device_dir, exist_ok=True)
    etc_dir = os.path.join(device_dir, 'etc')
    os.makedirs(etc_dir, exist_ok=True)
    dest_path = os.path.join(etc_dir, 'resolv.conf')

    # Per semplicità operativa: saltiamo il sotto-menu delle modalità e
    # scegliamo direttamente l'opzione che interessa di più: impostare
    # un unico nameserver. Tuttavia manteniamo la ricerca di eventuali
    # `resolv.conf` esistenti per suggerire candidati IP.
    available_sources = []
    for d in items:
        src = os.path.join(base_path, d, 'etc', 'resolv.conf')
        if os.path.isfile(src):
            available_sources.append((d, src))
    # Imposta automaticamente la modalità 1 (unico nameserver)
    choice = '1'

    try:
        if choice == '1':
            # Candidati nameserver: solo i server DNS del lab (cartella etc/bind),
            # con l'IP della loro interfaccia preso dallo startup (non il primo IP
            # trovato in un file qualsiasi, che per un DNS è spesso quello del root).
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
                items = [f"{d} - {ip}" for (d, ip) in candidate_ns]
                print_menu('Dispositivi candidati come nameserver:', items, extra_options=[('M', 'Inserisci manualmente un IP')])
                selns = input('Seleziona il nameserver (numero) o M per manuale, INVIO per annullare: ').strip()
                if not selns:
                    print('Operazione annullata.')
                    return
                if selns.lower() == 'm':
                    manual = input_non_vuoto('Inserisci l\'IP del nameserver (es. 10.0.0.1): ').strip()
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
                # nessun candidato trovato, fallback a inserimento manuale
                print('Nessun IP candidato trovato nelle cartelle dei dispositivi.')
                manual = input_non_vuoto('Inserisci l\'IP del nameserver (es. 10.0.0.1): ').strip()
                try:
                    ipaddress.ip_address(manual)
                    ns_ip = manual
                except Exception:
                    print('IP non valido. Nessuna modifica effettuata.')
                    return

            # Scrive il file con la forma esatta richiesta: "nameserver <IP>\n"
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
            items = [d for (d, p) in available_sources]
            print_menu('Dispositivi con resolv.conf disponibile:', items)
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
        print('Errore durante l\'impostazione di resolv.conf:', e)


def aggiungi_loopback_menu(base_path, routers):
    """
    Aggiunge una loopback ad un dispositivo.
    - Per i router: aggiorna lo startup (`<name>.startup`) con `ip address add <ip/32> dev lo`
      e inserisce l'annuncio nei blocchi BGP/OSPF/RIP se il protocollo è abilitato.
    - Per altri dispositivi con file `.startup`: aggiunge solo la riga allo startup.
    """
    print('\n--- Aggiungi loopback ad un dispositivo ---')
    # Mostra direttamente la lista dei dispositivi disponibili: router + file .startup
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
        # nome diretto
        if sel in router_names:
            target = sel
        elif sel in only_startup:
            target = sel
        else:
            print('Selezione non valida.')
            return

    # marca il tipo per il codice esistente
    typ = 'r' if target in router_names else 'd'
    if typ.startswith('r'):
        # seleziona router solo se non abbiamo già impostato target
        if not target or target not in routers:
            target = select_router(routers, prompt='Seleziona il router a cui aggiungere la loopback:')
            if not target:
                print('Operazione annullata.')
                return
        ip_only = valida_ip_senza_cidr('IP loopback (es. 1.2.3.4): ')
        ipcidr = ip_only + '/32'
        # memorizza nel metadata
        routers.setdefault(target, {}).setdefault('loopbacks', [])
        if ipcidr in routers[target]['loopbacks']:
            print('⚠️ Loopback già presente nei dati del router.')
        else:
            routers[target]['loopbacks'].append(ipcidr)
        # aggiorna startup
        startup = os.path.join(base_path, f"{target}.startup")
        try:
            # legge lo startup (se esiste) e inserisce la loopback prima di
            # qualsiasi riga 'systemctl start ...' per mantenere l'ordine
            lines = []
            if os.path.exists(startup):
                with open(startup, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            lb_line = f"ip address add {ipcidr} dev lo\n"
            # evita duplicati
            if any(l.strip() == lb_line.strip() for l in lines):
                pass
            else:
                insert_idx = None
                for i, l in enumerate(lines):
                    if re.match(r'^\s*systemctl start\b', l):
                        insert_idx = i
                        break
                if insert_idx is None:
                    # appendare alla fine
                    if lines and not lines[-1].endswith('\n'):
                        lines[-1] = lines[-1] + '\n'
                    lines.append(lb_line)
                else:
                    lines.insert(insert_idx, lb_line)
                with open(startup, 'w', encoding='utf-8', newline='\n') as f:
                    f.writelines(lines)
        except Exception:
            print('⚠️ Impossibile aggiornare lo startup del router (file non trovato).')
        # aggiorna frr.conf: inserisci network nelle sezioni dei protocolli abilitati
        fpath = os.path.join(base_path, target, 'etc', 'frr', 'frr.conf')
        if os.path.exists(fpath):
            protos = routers.get(target, {}).get('protocols', [])
            # IMPORTANT: non annunciare mai la loopback in BGP
            # (anche se il router ha BGP abilitato non tocchiamo il blocco bgp)
            if 'ospf' in protos:
                area = routers.get(target, {}).get('ospf_area') or input_area('Area OSPF per annuncio della loopback (es. 0.0.0.0): ', default='0.0.0.0')
                insert_lines_into_protocol_block(fpath, proto='ospf', asn=None, lines=[f"network {ipcidr} area {area}"])
            if 'rip' in protos:
                insert_lines_into_protocol_block(fpath, proto='rip', asn=None, lines=[f"network {ipcidr}"])
            # Prova ad aggiungere automaticamente iBGP neighbors via loopback
            try:
                add_ibgp_loopback_neighbors(base_path, routers)
            except Exception:
                # non blocchiamo l'operazione principale se fallisce
                pass
            print(f"\n\n✅ Loopback {ipcidr} aggiunta a router {target} (startup aggiornato).\n")
        else:
            print(f"⚠️ frr.conf non trovato per {target}; è stata aggiornata solo la startup (se esistente).")
        return

    # Dispositivi generici: cerca file .startup nella cartella del lab
    items = []
    try:
        for fn in os.listdir(base_path):
            if fn.endswith('.startup'):
                items.append(fn[:-8])
    except Exception:
        pass
    if not items:
        print('Nessun dispositivo con file .startup trovato nella cartella del lab.')
        return
    print_menu('Dispositivi con startup:', items)
    sel = input('Seleziona il dispositivo (numero o nome, vuoto per annullare): ').strip()
    if not sel:
        print('Annullato.')
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




def _rete_di_ip(ip, routers):
    """Rete del lab (dalle interfacce dei router) che contiene un IP scritto senza maschera."""
    for r in routers.values():
        for it in r.get('interfaces', []):
            try:
                i = ipaddress.ip_interface(it.get('ip') or '')
            except ValueError:
                continue
            if ipaddress.ip_address(ip) in i.network:
                return str(i.network)
    return None


def _reti_del_router(target, routers, reti):
    """Le network del router, ognuna con il router all'altro capo se e' un link."""
    out = []
    for rete in reti:
        altri = [n for n, r in routers.items() if n != target and any(
            _contiene(rete, it.get('ip') or '') for it in r.get('interfaces', []))]
        out.append(f"{rete}" + (f" (link con {', '.join(altri)})" if altri else " (rete propria)"))
    return out


def _chiedi_reti_cpp(routers):
    """Reti per la prefix-list in uscita: vanno scritte come reti con maschera. 'permit 20.0.0.1'
    verrebbe scartata da FRR e la lista inesistente bloccherebbe tutti gli annunci (provato).
    Un indirizzo di router viene corretto con la sua rete, dopo conferma."""
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
            if indirizzo and input(f"{tok} è l'indirizzo di un router, non una rete. "
                                   f"Intendevi {rete}? (S/n): ").strip().lower().startswith('n'):
                print("Riscrivi la risposta.")
                break
            if rete not in reti:
                reti.append(rete)
        else:
            return reti


def aggiungi_customer_provider_wizard(base_path, routers):
    print("\n=== Configurazione Customer-Provider ===")
    
    # 1. Seleziona Router
    target = select_router(routers, prompt="Quale router stiamo configurando? ")
    if not target:
        return

    if "bgp" not in routers.get(target, {}).get("protocols", []):
        print(f"⚠️ Il router {target} non ha BGP abilitato.")
        return

    # 2. Seleziona Neighbor
    print(f"\nSeleziona il Neighbor (vicino) di {target}:")
    neigh_name = select_router(routers, prompt="Router vicino:")
    
    neigh_ip = None
    neigh_asn = None

    if not neigh_name:
        # Fallback manuale
        neigh_name = input("Nome del vicino (o invio per uscire): ").strip()
        if not neigh_name:
            return
        neigh_ip = valida_ip_senza_cidr("Inserisci IP del vicino: ")
        neigh_asn = input_asn("ASN del vicino: ")
    else:
        # Neighbor conosciuto: recuperiamo gli IP
        neigh_asn = routers[neigh_name].get('asn')
        ifaces = routers[neigh_name].get('interfaces', [])
        valid_ips = []
        for iface in ifaces:
            ip_cidr = iface.get('ip')
            if ip_cidr:
                ip = ip_cidr.split('/')[0]
                valid_ips.append(ip)
        
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

    # Assicurati che il neighbor esista nella conf BGP
    fpath = os.path.join(base_path, target, "etc", "frr", "frr.conf")
    if not os.path.exists(fpath):
        print(f"File {fpath} non trovato.")
        return

    # Check/Create neighbor (remote-as)
    with open(fpath, 'r') as f:
        content = f.read()
    
    if f"neighbor {neigh_ip} remote-as" not in content:
        print(f"Neighbor {neigh_ip} non presente. Lo aggiungo.")
        lines = [f"neighbor {neigh_ip} remote-as {neigh_asn}",
                 f"neighbor {neigh_ip} description {neigh_name}"]
        if not insert_lines_into_protocol_block(fpath, proto='bgp', asn=None, lines=lines):
            print("❌ Errore nell'inserimento del neighbor.")
            return
    
    # 3. Relazione Economica
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

    # 4. Reti coinvolte (Opzionale)
    # Usiamo nomi univoci per le prefix-list
    pl_in = f"{rel_type}_{neigh_name}_in"
    pl_out = f"{rel_type}_{neigh_name}_out"

    lines_to_append = []


    if rel_type in ("provider", "peer"):
        # Provider (il vicino è il mio provider) e Peer (siamo alla pari):
        # IN: permit any (accetto tutto dal vicino)
        # OUT: permit solo le mie reti e quelle dei miei clienti
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
        # Customer (Il vicino è il mio cliente):
        # IN: permit any (accetto tutto dal cliente)
        # OUT: permit any (invio la full table al cliente)
        lines_to_append.append(f"ip prefix-list {pl_in} permit any")
        lines_to_append.append(f"ip prefix-list {pl_out} permit any")

    # Collega le prefix-list al neighbor (con riga vuota prima per separazione)
    neigh_lines = [
        "",  # blank line for separation
        f"neighbor {neigh_ip} prefix-list {pl_in} in",
        f"neighbor {neigh_ip} prefix-list {pl_out} out"
    ]
    if insert_lines_into_protocol_block(fpath, proto='bgp', asn=None, lines=neigh_lines):
        # Scrivi le prefix-list nel file (append global) con riga vuota prima
        try:
            with open(fpath, 'a', encoding='utf-8', newline='\n') as f:
                f.write('\n')  # blank line before prefix-list definitions
                for l in lines_to_append:
                    f.write(l + '\n')
                f.write('\n')  # blank line after prefix-list definitions
        except Exception as e:
            print(f"❌ Errore scrivendo le prefix-list: {e}")
            return
        print(f"✅ Configurazione {rel_type.upper()} applicata su {target} verso {neigh_name}.")
    else:
        print(f"❌ Errore applicando la configurazione neighbor su {target}.")


def aggiungi_redistribuzione_bgp_igp(base_path, routers):
    print("\n=== Ridistribuzione BGP -> IGP (Route-map) ===")
    # Filtra i router che hanno sia BGP che (RIP o OSPF)
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

    # Chiedi IP del neighbor o Rete
    import ipaddress
    while True:
        neigh_ip = input("Inserisci la RETE di collegamento con il neighbor BGP (es. 50.7.1.0/24): ").strip()
        if not neigh_ip:
             print("Inserisci un valore.")
             continue
        try:
            # accetta sia 1.2.3.4 (diventa /32) che 1.2.3.0/24
            net = ipaddress.ip_network(neigh_ip, strict=False)
            prefix = str(net)
            break
        except ValueError:
            print("❌ Formato non valido. Inserisci IP o CIDR (es. 10.0.0.1 o 10.0.0.0/24)")
    
    # Costruisci la configurazione globale
    # prefix è già normalizzato (es. 10.0.0.1/32 o 50.7.1.0/24)
    
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

    # Appendi configurazione globale
    try:
        with open(fpath, 'a', encoding='utf-8', newline='\n') as f:
            f.write("\n\n")
            for line in global_conf:
                f.write(line + "\n")
    except Exception as e:
        print(f"❌ Errore scrivendo su {fpath}: {e}")
        return
            
    # Aggiungi comando redistribute
    protos = candidates[target]['protocols']
    redist_cmd = "redistribute bgp route-map eBGP"

    # il 'redistribute bgp' generato in automatico verrebbe duplicato:
    # lo togliamo, verrà sostituito da quello con la route-map
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
    """Toglie (attiva=False) o rimette (attiva=True) 'redistribute bgp' nei blocchi
    OSPF/RIP di un router BGP+IGP."""
    candidati = {k: v for k, v in routers.items()
                 if 'bgp' in v.get('protocols', []) and ({'ospf', 'rip'} & set(v.get('protocols', [])))}
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
        print(f"✅ {target}: redistribute bgp " + (f"aggiunto in {', '.join(mancanti)}." if mancanti else "era già presente."))
    else:
        _scrivi_righe(fpath, out)
        print(f"✅ {target}: redistribute bgp " + (f"tolto da {', '.join(sorted(presente))}." if presente else "non era presente."))
    routers[target]['igp_redistribute_bgp'] = attiva


def menu_ridistribuzione(base_path, routers):
    while True:
        print_menu('=== Ridistribuzione BGP -> IGP ===', [
            "Togli 'redistribute bgp' da un router (il testo la chiede solo su alcuni router di confine)",
            "Rimetti 'redistribute bgp' su un router",
            "Redistribute bgp con route-map eBGP (solo rotte imparate via eBGP)"],
            extra_options=[('0', 'Torna indietro')])
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


def isole_ospf(lab_path):
    """Domini OSPF del lab: router OSPF collegati da LAN e dello stesso AS (ASN BGP o
    'asN' nel nome). Ritorna [(etichetta, [router], {router: cfg})] leggendo solo i file."""
    nodes, _ = parse_lab_conf_for_nodes(lab_path)
    cfg = {}
    for n in nodes:
        f = os.path.join(lab_path, n, 'etc', 'frr', 'frr.conf')
        if os.path.exists(f):
            c = _analizza_frr(_leggi_righe(f))
            if 'ospf' in c['igp']:
                cfg[n] = c
    # si separano solo router con ASN BGP diversi; un router solo OSPF (es. as200r1 di eye)
    # si unisce ai vicini anche se il nome dice un altro numero (soluzione: router bgp 2)
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
        asn = next((as_di[n] for n in sorted(isola) if as_di[n]), '') or \
            next((str(_as_number(n, {})) for n in sorted(isola) if _as_number(n, {})), '')
        isole.append((f"AS{asn}" if asn else 'OSPF', sorted(isola), {n: cfg[n] for n in isola}))
    return isole


def imposta_auto_cost(base_path):
    """Opzioni 10: 'auto-cost reference-bandwidth 100' su tutti i router OSPF di un AS.
    Nell'immagine kathara/frr attuale il costo predefinito di un'interfaccia è 10000
    (riferimento 100 Gbit / 10 Mbit); i testi d'esame danno per scontato 10. Con il
    riferimento a 100 Mbit il predefinito torna 10 e i costi espliciti (es. 90) non cambiano.
    Verificato su eye e tennis: solo così si ottengono i percorsi richiesti dal testo."""
    isole = isole_ospf(base_path)
    if not isole:
        print('Nessun router OSPF nel lab.')
        return
    items = []
    for et, rs, cfgs in isole:
        costi = [f"{r} {c}" for r in rs for c in cfgs[r]['costi']]
        con = [r for r in rs if cfgs[r]['auto_cost']]
        stato = ('auto-cost già su tutti' if len(con) == len(rs)
                 else f"auto-cost su {len(con)}/{len(rs)}" if con else 'senza auto-cost')
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
    print(f"✅ Fatto. Controlla con la GUI (show ip ospf interface: 'Cost: 10') e con Test -> Verifica percorso.")


# -------------------------
# Dispositivi letti dai file del lab: pc, www e dns nel riepilogo, controlli,
# modifica guidata (IP, LAN, gateway, protocolli, AS) e modifica a righe.
# Le modifiche guidate cambiano solo le righe interessate, in tutti i file del lab,
# dopo un'anteprima e una copia di sicurezza: le aggiunte fatte a mano (policy, costi)
# restano. L'XML del generatore viene aggiornato con le stesse sostituzioni.
# -------------------------
_RE_IP_ADD = re.compile(r'\s*ip\s+a(?:ddr(?:ess)?)?\s+add\s+(\S+)\s+dev\s+(\S+)')
_RE_GW = re.compile(r'\s*(?:ip\s+route\s+add\s+default\s+via\s+(\S+)|route\s+add\s+default\s+gw\s+(\S+))')
_RE_APACHE = re.compile(r'(systemctl\s+start\s+apache2|/etc/init\.d/apache2\s+start|service\s+apache2\s+start)')
# un IPv4, con la maschera opzionale, non attaccato ad altre cifre o punti (1.0.0.10.in-addr.arpa resta fuori)
_RE_TOKEN_IP = re.compile(r'(?<![\w.])(\d{1,3}(?:\.\d{1,3}){3})(?:/(\d{1,2}))?(?![\w.])')
# comandi di frr.conf che stanno fuori dai blocchi (servono per l'indentazione e per la fine di un blocco)
_FRR_GLOBALI = re.compile(r'(router|interface|route-map|ip\s+prefix-list|ipv6\s+prefix-list|ip\s+route|'
                          r'access-list|ip\s+access-list|bgp\s+as-path|bgp\s+community-list|ip\s+community-list|'
                          r'log|debug|hostname|password|enable|line|service|frr|vrf|agentx|end)\b')


def _righe_file(path):
    """Righe di un file senza la riga vuota creata dall'a capo finale."""
    righe = _leggi_righe(path)
    if righe and righe[-1] == '':
        righe.pop()
    return righe


def _scrivi_esatte(path, righe):
    """Scrive le righe così come sono (a differenza di _scrivi_righe non toglie righe vuote)."""
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(righe) + '\n')


def _file_bind(lab_path, nome, f):
    """Percorso locale di un file citato in named.conf ('/etc/bind/db.com' o relativo a etc/bind)."""
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
            zone.append({'zona': m.group(1).rstrip('.').lower() or '.', 'tipo': t.group(1) if t else '?',
                         'file': _file_bind(lab_path, nome, fl.group(1)) if fl else None})
    return zone


def _nome_assoluto(nome, origine):
    if nome == '@':
        return origine or '.'
    if nome.endswith('.'):
        return nome.rstrip('.').lower() or '.'
    return f"{nome}.{origine}".lower() if origine else nome.lower()


def _record_dns(path, zona):
    """[(nome, tipo, valore)] di un file di zona, con i nomi assoluti (minuscoli, senza punto finale)."""
    origine = '' if zona == '.' else zona.lower()
    tipi = ('A', 'NS', 'SOA', 'CNAME', 'MX', 'PTR', 'AAAA', 'TXT')
    out, ultimo, in_par = [], origine or '.', False
    for raw in _leggi_righe(path):
        riga = raw.split(';', 1)[0]
        if in_par:
            in_par = ')' not in riga
            continue
        if '(' in riga and ')' not in riga:
            in_par = True            # SOA su più righe: le righe successive non servono
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
    """Tutti i dispositivi del lab letti dai file: tipo (router/host/www/dns), interfacce
    (da lab.conf e startup), gateway, resolver, zone DNS, demoni FRR e AS."""
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
        interfacce = [{'dev': f"eth{i}", 'idx': i, 'lan': lan, 'ip': (ips.get(f"eth{i}") or [''])[0]}
                      for i, lan in sorted((k, v) for k, v in meta.get('interfaces', {}).items() if isinstance(k, int))]
        demoni = re.findall(r'^\s*(bgpd|ospfd|ripd)\s*=\s*yes',
                            '\n'.join(_leggi_righe(os.path.join(d, 'etc', 'frr', 'daemons'))), re.M)
        cfg = _analizza_frr(_leggi_righe(frr)) if os.path.exists(frr) else None
        resolv = '\n'.join(_leggi_righe(os.path.join(d, 'etc', 'resolv.conf')))
        # IP su interfacce che non sono in lab.conf (bridge br1, vlan...): servono per sapere di chi sono
        altri_ip = [(dev, ip) for dev, lista in ips.items() for ip in lista
                    if dev != 'lo' and not any(it['dev'] == dev for it in interfacce)]
        disp[nome] = {'nome': nome, 'tipo': tipo, 'interfacce': interfacce, 'loopback': ips.get('lo', []),
                      'altri_ip': altri_ip,
                      'gateway': gw, 'apache': bool(_RE_APACHE.search(testo)),
                      'nameserver': re.findall(r'^\s*nameserver\s+(\S+)', resolv, re.M),
                      'zone': _zone_bind(lab_path, nome) if tipo == 'dns' else [],
                      'demoni': demoni, 'asn': (cfg or {}).get('asn'), 'frr': os.path.exists(frr)}
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
    """LAN -> segmento: le LAN unite da uno switch (dispositivo non router con 2+ interfacce e
    nessun IP, es. patchwork) sono lo stesso segmento Ethernet."""
    seg = {it['lan']: it['lan'] for d in disp.values() for it in d['interfacce']}

    def radice(x):
        while seg[x] != x:
            x = seg[x]
        return x
    for d in disp.values():
        if (d['tipo'] != 'router' and len(d['interfacce']) > 1 and not d.get('altri_ip')
                and not any(it['ip'] for it in d['interfacce'])):
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
    """Controlli su pc, www e dns: [(dispositivo, messaggio)].
      - gateway fuori dalla rete delle sue interfacce, di nessun dispositivo, su un'altra LAN o non di un router
      - resolver (resolv.conf) che non è l'IP di un server DNS del lab
      - www senza apache2 avviato nello startup
      - root hint e deleghe con un IP che non è di un DNS master di quella zona
      - record A con un IP che nessun dispositivo del lab ha"""
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
                    out.append((n, f"il gateway {gw} non è nella rete delle sue interfacce "
                                   f"({', '.join(str(r) for r, _ in reti)}): il dispositivo non lo raggiunge."))
                elif chi is None:
                    out.append((n, f"il gateway {gw} non è l'IP di nessun dispositivo del lab (refuso?)."))
                elif chi[0] == n:
                    out.append((n, f"il gateway {gw} è un suo stesso indirizzo."))
                elif (chi[2] is not None and None not in dentro
                      and seg.get(chi[2]) not in {seg.get(l) for l in dentro}):
                    out.append((n, f"il gateway {gw} è di {chi[0]}, che è sulla LAN {chi[2]}: non è sulla "
                                   f"stessa LAN del dispositivo ({', '.join(dentro)})."))
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
                            out.append((n, f"{fname}: il root server {nn} ha IP {v}, che "
                                           + (f"è di {chi[0]}, non del root del lab" if chi else
                                              "non è di nessun dispositivo del lab")
                                           + (f" ({', '.join(sorted(master['.']))})." if master.get('.') else '.')))
                continue
            glue = set()
            for _f, padre, figlia, nsn, ip in _deleghe_dns({'zone': [z]}, disp):
                if ip is None:
                    continue
                glue.add((nsn, ip))
                chi = own.get(ip)
                servono = master.get(figlia, set())
                if not chi or chi[0] not in servono:
                    out.append((n, f"{fname}: delega di {figlia} a {nsn} ({ip}), ma {ip} "
                                   + (f"è di {chi[0]}, che non è master di {figlia}" if chi else
                                      "non è di nessun dispositivo del lab")
                                   + (f" (lo è {', '.join(sorted(servono))})." if servono else '.')))
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
        ifs = ', '.join(f"{it['ip'] or '(senza IP)'} (LAN {it['lan']})" for it in d['interfacce']) or '(nessuna interfaccia)'
        parti = [f"{d['nome']:<{larg}}  {d['tipo']:<4}  {ifs}",
                 f"gw {d['gateway']} ({chi(d['gateway'])})" if d['gateway'] else "gw -"]
        if d['nameserver']:
            parti.append('resolver ' + ', '.join(f"{ns} ({chi(ns)})" for ns in d['nameserver']))
        if d['tipo'] == 'www':
            parti.append('apache2 avviato' if d['apache'] else 'apache2 NON avviato')
        if d['zone']:
            parti.append('zone: ' + ', '.join(f"{z['zona']} ({z['tipo']})" for z in d['zone']))
        print('   '.join(parti))
        for _f, padre, figlia, ns, ip in _deleghe_dns(d, disp):
            print(f"{'':<{larg}}        delega {figlia} -> {ns} {ip or '(senza glue)'}"
                  + (f" ({chi(ip)})" if ip else ''))


# --- copie di sicurezza ---
def _cartella_copie(lab_path):
    lab = os.path.abspath(lab_path)
    return os.path.join(os.path.dirname(lab), '.backup_labgenerator', os.path.basename(lab))


def copia_di_sicurezza(lab_path, etichetta=''):
    """Copia dell'intero lab in <cartella dei lab>/.backup_labgenerator/<lab>/<data-ora>."""
    import datetime
    base = _cartella_copie(lab_path)
    nome = datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + (f"_{etichetta}" if etichetta else '')
    dest, k = os.path.join(base, nome), 2
    while os.path.exists(dest):
        dest, k = os.path.join(base, f"{nome}_{k}"), k + 1
    shutil.copytree(lab_path, dest)
    return dest


def ripristina_copia(lab_path, routers=None, _nome=None):
    base = _cartella_copie(lab_path)
    copie = sorted((d for d in os.listdir(base) if os.path.isfile(os.path.join(base, d, 'lab.conf'))),
                   reverse=True) if os.path.isdir(base) else []
    if not copie:
        print('Nessuna copia di sicurezza per questo lab.')
        return False
    print_menu(f'Copie di sicurezza di {os.path.basename(os.path.abspath(lab_path))} (la più recente in alto):', copie[:15])
    s = input('Numero della copia da ripristinare (Invio = annulla): ').strip()
    if not (s.isdigit() and 1 <= int(s) <= min(len(copie), 15)):
        print('Annullato.')
        return False
    src = os.path.join(base, copie[int(s) - 1])
    if input(f"Il lab tornerà com'era in {copie[int(s) - 1]}. Confermi? (s/N): ").strip().lower() not in ('s', 'si', 'sì'):
        print('Annullato.')
        return False
    attuale = copia_di_sicurezza(lab_path, 'prima_del_ripristino')
    shutil.rmtree(lab_path)
    shutil.copytree(src, lab_path)
    print(f"✅ Lab ripristinato. Lo stato di prima del ripristino è salvato in: {attuale}")
    _ricarica_routers(lab_path, routers)
    return True


# --- XML del generatore ---
def _xml_del_lab(lab_path):
    p = os.path.join(lab_path, os.path.basename(os.path.normpath(lab_path)) + '.xml')
    return p if os.path.isfile(p) else None


def _ricarica_routers(lab_path, routers):
    p = _xml_del_lab(lab_path)
    if routers is not None and p:
        try:
            routers.clear()
            routers.update(load_lab_from_xml(p)[1])
        except Exception as e:
            print(f"⚠️ Non riesco a rileggere {os.path.basename(p)}: {e}")


def _mappa_dati(x, f):
    if isinstance(x, str):
        return f(x)
    if isinstance(x, list):
        return [_mappa_dati(v, f) for v in x]
    if isinstance(x, dict):
        return {k: _mappa_dati(v, f) for k, v in x.items()}
    return x


def _aggiorna_xml(lab_path, routers, trasforma):
    """Applica trasforma(routers, hosts, wwws) all'XML del lab (se c'è) e ai router in memoria."""
    p = _xml_del_lab(lab_path)
    if not p:
        if routers is not None:
            trasforma(routers, [], [])
        print("(nessun XML del generatore in questo lab: aggiornati solo i file)")
        return
    try:
        _, r, h, w, _ = load_lab_from_xml(p)
        trasforma(r, h, w)
        export_lab_to_xml(os.path.basename(os.path.normpath(lab_path)), lab_path, r, h, w)
        if routers is not None:
            routers.clear()
            routers.update(r)
    except Exception as e:
        print(f"⚠️ XML non aggiornato ({e}): i file del lab sono comunque modificati.")


def _xml_sostituisci(f):
    def t(r, h, w):
        for k in list(r):
            r[k] = _mappa_dati(r[k], f)
        h[:] = _mappa_dati(h, f)
        w[:] = _mappa_dati(w, f)
    return t


# --- anteprima, conferma e scrittura ---
def _avvisi_lab(lab_path):
    return set(controlla_topologia(lab_path)) | set(controlli_configurazione(lab_path))


def _stampa_diff(rel, vecchie, nuove):
    print(f"  {rel.replace(os.sep, '/')}")
    sm = difflib.SequenceMatcher(a=vecchie, b=nuove, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        for k in range(i1, i2):
            print(f"    - riga {k + 1:>3}: {vecchie[k].strip()}")
        for k in range(j1, j2):
            print(f"    + riga {k + 1:>3}: {nuove[k].strip()}")


def _applica_modifiche(lab_path, modifiche, titolo, note=None):
    """modifiche = {percorso relativo: (righe vecchie, righe nuove)}. Anteprima, conferma,
    copia di sicurezza, scrittura e controlli prima/dopo. True se ha scritto."""
    modifiche = {r: v for r, v in modifiche.items() if v[0] != v[1]}
    if not modifiche:
        print('Nessuna modifica da fare.')
        return False
    print(f"\n--- {titolo}: anteprima ({len(modifiche)} file) ---")
    for rel in sorted(modifiche):
        _stampa_diff(rel, *modifiche[rel])
    for n in note or []:
        print(f"  ⚠️ {n}")
    if input("\nConfermi le modifiche? (s/N): ").strip().lower() not in ('s', 'si', 'sì'):
        print('Annullato: nessun file modificato.')
        return False
    prima = _avvisi_lab(lab_path)
    copia = copia_di_sicurezza(lab_path)
    for rel, (_, nuove) in modifiche.items():
        _scrivi_esatte(os.path.join(lab_path, rel), nuove)
    print(f"✅ Modifiche scritte. Copia del lab com'era prima: {copia}")
    dopo = _avvisi_lab(lab_path)
    for a in sorted(prima - dopo):
        print(f"   ✔ risolto: {a}")
    for a in sorted(dopo - prima):
        print(f"   ⚠️ nuovo: {a}")
    if not (prima ^ dopo):
        print("   (i controlli dell'opzione 8 danno lo stesso esito di prima)")
    print("   Se il lab è avviato, le modifiche valgono dal prossimo avvio (lclean e poi lstart).")
    return True


# --- modifica a righe ---
def _file_modificabili(lab_path, nome):
    cand = [f"{nome}.startup", os.path.join(nome, 'etc', 'frr', 'frr.conf'), os.path.join(nome, 'etc', 'resolv.conf')]
    bind = os.path.join(lab_path, nome, 'etc', 'bind')
    if os.path.isdir(bind):
        cand += [os.path.join(nome, 'etc', 'bind', f) for f in sorted(os.listdir(bind))]
    return [c for c in cand if os.path.isfile(os.path.join(lab_path, c))]


def _indenta(righe, dopo, testo, frr):
    """Riga nuova inserita dopo l'indice `dopo` (-1 = in cima): in frr.conf, dentro un blocco
    prende 4 spazi; i comandi globali (router, route-map, ip prefix-list...) restano a sinistra."""
    if not frr or testo[:1].isspace():
        return testo
    t = testo.strip()
    if _FRR_GLOBALI.match(t) or t.startswith('!'):
        return t
    for k in range(dopo, -1, -1):
        s = righe[k]
        if not s.strip():
            continue
        if s[:1].isspace() or re.match(r'(router|interface|route-map|address-family)\b', s.strip()):
            return '    ' + t
        return t
    return t


def _correzione_suggerita(riga, messaggio):
    """Riga corretta secondo il 'Forse intendevi ...' del controllo, oppure None."""
    m = re.search(r"(?:route-map|prefix-list|access-list) (\S+) non è definita.*Forse intendevi (\S+) \(riga", messaggio)
    if not m:
        m = re.search(r"'([^']+)' non è valido in una prefix-list.*Forse intendevi (\S+)\?", messaggio)
    if not m:
        return None
    nuova = re.sub(rf'(?<!\S){re.escape(m.group(1))}(?!\S)', m.group(2), riga, count=1)
    return nuova if nuova != riga else None


def _note_frr(righe):
    note = {}
    for x in riferimenti_frr(righe):
        note.setdefault(x['riga'], []).append(x)
    return note


def editor_righe(lab_path, rel):
    """Modifica a righe di un file del lab, con le righe numerate e, in frr.conf, gli errori
    dei controlli sotto la riga. Le modifiche restano in memoria fino a 'S'."""
    path = os.path.join(lab_path, rel)
    frr = rel.replace(os.sep, '/').endswith('frr/frr.conf')
    originali = _righe_file(path)
    righe, storia = list(originali), []
    aiuto = ("  M n = modifica la riga n      E n = elimina la riga n     A n = aggiungi righe dopo la n (A 0 = in cima)\n"
             "  C n = applica la correzione suggerita sulla riga n          U = annulla l'ultima modifica\n"
             "  S = salva                       0 = esci                    V = rivedi il file")
    mostra = True
    while True:
        note = _note_frr(righe) if frr else {}
        if mostra:
            print(f"\n=== {rel.replace(os.sep, '/')} ({len(righe)} righe{', modificato, non salvato' if righe != originali else ''}) ===")
            for k, l in enumerate(righe, 1):
                print(f"{k:>3} | {l}")
                for x in note.get(k, []):
                    print(f"      {'✗' if x['gravita'] == 'errore' else '⚠'} {x['messaggio']}")
            print(aiuto)
        mostra = True
        s = input("Comando: ").strip()
        if not s:
            mostra = False
            continue
        cmd, arg = s[0].upper(), s[1:].strip()
        if cmd == '0':
            if righe != originali and input("Ci sono modifiche non salvate: esci senza salvare? (s/N): ").strip().lower() not in ('s', 'si', 'sì'):
                continue
            return
        if cmd == 'V':
            continue
        if cmd == 'U':
            if storia:
                righe = storia.pop()
                print('Annullata l\'ultima modifica.')
            else:
                print('Niente da annullare.')
            continue
        if cmd == 'S':
            if righe == originali:
                print('Nessuna modifica da salvare.')
                mostra = False
                continue
            if _applica_modifiche(lab_path, {rel: (originali, righe)}, f"Modifica di {rel.replace(os.sep, '/')}"):
                originali, storia = _righe_file(path), []
                righe = list(originali)
            continue
        if cmd not in 'MEAC':
            print('Comando non riconosciuto.')
            print(aiuto)
            mostra = False
            continue
        if not arg:
            arg = input("Numero di riga: ").strip()
        if not arg.isdigit():
            print('❌ Serve il numero di una riga (es. M 12).')
            mostra = False
            continue
        n = int(arg)
        if not (1 <= n <= len(righe)) and not (cmd == 'A' and n == 0):
            print(f"❌ Il file ha {len(righe)} righe.")
            mostra = False
            continue
        if cmd == 'M':
            print(f"Riga {n}: {righe[n - 1]}")
            t = input("Nuovo testo (Invio = lascia com'è): ")
            if not t.strip():
                mostra = False
                continue
            rientro = righe[n - 1][:len(righe[n - 1]) - len(righe[n - 1].lstrip())]
            storia.append(list(righe))
            righe[n - 1] = t if t[:1].isspace() else rientro + t.strip()
        elif cmd == 'E':
            storia.append(list(righe))
            print(f"Eliminata la riga {n}: {righe.pop(n - 1).strip()}")
        elif cmd == 'A':
            print("Righe da aggiungere (una per volta, Invio a vuoto per finire):")
            nuove = []
            while True:
                t = input("  + ")
                if not t.strip():
                    break
                nuove.append(t)
            if not nuove:
                mostra = False
                continue
            storia.append(list(righe))
            for j, t in enumerate(nuove):
                righe.insert(n + j, _indenta(righe, n + j - 1, t, frr))
        elif cmd == 'C':
            prop = None
            for x in note.get(n, []):
                prop = _correzione_suggerita(righe[n - 1], x['messaggio'])
                if prop:
                    break
            if not prop:
                print(f"Nessuna correzione automatica per la riga {n}: usa M {n}.")
                mostra = False
                continue
            print(f"  prima: {righe[n - 1].strip()}\n  dopo:  {prop.strip()}")
            storia.append(list(righe))
            righe[n - 1] = prop


def modifica_righe(lab_path, routers, nome):
    files = _file_modificabili(lab_path, nome)
    if not files:
        print(f"Nessun file da modificare per {nome}.")
        return
    print("\n(IP, LAN, gateway, protocolli e AS conviene cambiarli con le voci guidate: aggiornano anche gli")
    print(" altri dispositivi e l'XML. Le modifiche a righe cambiano solo il file scelto.)")
    while True:
        if len(files) == 1:
            editor_righe(lab_path, files[0])
            return
        print_menu(f'File di {nome}:', [f.replace(os.sep, '/') for f in files], extra_options=[('0', 'Torna indietro')])
        s = input('Seleziona: ').strip()
        if s == '0' or not s:
            return
        if s.isdigit() and 1 <= int(s) <= len(files):
            editor_righe(lab_path, files[int(s) - 1])
        else:
            print('Scelta non valida.')


# --- sostituzione di IP e reti in tutti i file del lab ---
def _file_di_testo(lab_path):
    """File di testo del lab (percorsi relativi), esclusi l'XML del generatore e le cartelle nascoste."""
    out = []
    for radice, dirs, files in os.walk(lab_path):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
        for f in sorted(files):
            p = os.path.join(radice, f)
            if radice == lab_path and f.endswith('.xml'):
                continue
            try:
                if os.path.getsize(p) > 512 * 1024:
                    continue
                with open(p, 'r', encoding='utf-8') as fh:
                    fh.read()
            except (OSError, UnicodeDecodeError):
                continue
            out.append(os.path.relpath(p, lab_path))
    return out


def _sostituzione_ip(ip_map, iface_map, net_map):
    """Funzione testo -> testo: IP (senza maschera) secondo ip_map, IP/maschera di un'interfaccia
    secondo iface_map, reti secondo net_map. Il resto (es. un aggregato /16) resta com'è."""
    def rep(m):
        a, l = m.group(1), m.group(2)
        if l is None:
            return ip_map.get(a, m.group(0))
        tok = f"{a}/{l}"
        if tok in iface_map:
            return iface_map[tok]
        if tok in net_map:
            return net_map[tok]
        if a in ip_map:
            try:
                rete = ipaddress.ip_network(tok, strict=False)
                if str(rete.network_address) != a or rete.prefixlen == 32:
                    return f"{ip_map[a]}/{l}"          # un indirizzo con maschera, non una rete
            except ValueError:
                pass
        return m.group(0)
    return lambda testo: _RE_TOKEN_IP.sub(rep, testo)


def _piano_sostituzioni(lab_path, f):
    modifiche = {}
    for rel in _file_di_testo(lab_path):
        vecchie = _righe_file(os.path.join(lab_path, rel))
        nuove = [f(l) for l in vecchie]
        if nuove != vecchie:
            modifiche[rel] = (vecchie, nuove)
    return modifiche


def _reti_da_controllare(lab_path, modifiche, coppie):
    """Righe con un aggregato che conteneva la rete vecchia ma non contiene la nuova (da guardare a mano)."""
    avvisi = []
    for rel in _file_di_testo(lab_path):
        righe = modifiche[rel][1] if rel in modifiche else _righe_file(os.path.join(lab_path, rel))
        for k, l in enumerate(righe, 1):
            for m in _RE_TOKEN_IP.finditer(l):
                if not m.group(2):
                    continue
                try:
                    n = ipaddress.ip_network(f"{m.group(1)}/{m.group(2)}", strict=False)
                    for v, nu in coppie:
                        if n.prefixlen < v.prefixlen and v.subnet_of(n) and not nu.subnet_of(n):
                            avvisi.append(f"{rel.replace(os.sep, '/')} riga {k}: '{l.strip()}' comprende {v} "
                                          f"ma non {nu}: controllala a mano.")
                except (ValueError, TypeError):
                    continue
    return avvisi


def _esegui_sostituzione(lab_path, routers, ip_map, iface_map, net_map, titolo, extra=None, xml_extra=None):
    f = _sostituzione_ip(ip_map, iface_map, net_map)
    modifiche = _piano_sostituzioni(lab_path, f)
    for rel, (v, n) in (extra or {}).items():
        modifiche[rel] = (v, [f(x) for x in n])
    coppie = [(ipaddress.ip_network(a), ipaddress.ip_network(b)) for a, b in net_map.items()]
    note = _reti_da_controllare(lab_path, modifiche, coppie) if coppie else []
    if not _applica_modifiche(lab_path, modifiche, titolo, note):
        return False

    def trasforma(r, h, w):
        _xml_sostituisci(f)(r, h, w)
        if xml_extra:
            xml_extra(r, h, w)
    _aggiorna_xml(lab_path, routers, trasforma)
    return True


# --- scelte comuni ---
def _scegli_dispositivo(disp, prompt='Dispositivo da modificare'):
    nomi = sorted(disp, key=lambda n: (['router', 'host', 'www', 'dns'].index(disp[n]['tipo']), n))
    voci = []
    for n in nomi:
        d = disp[n]
        ips = ', '.join(it['ip'] for it in d['interfacce'] if it['ip'])
        voci.append(f"{n:<10} {d['tipo']:<6}" + (f" AS{d['asn']}" if d['asn'] else '') + f"  {ips}")
    print_menu('Dispositivi del lab:', voci)
    while True:
        s = input(f"{prompt} (numero o nome, Invio = annulla): ").strip()
        if not s:
            return None
        if s.isdigit() and 1 <= int(s) <= len(nomi):
            return nomi[int(s) - 1]
        if s in disp:
            return s
        print('❌ Dispositivo non trovato.')


def _scegli_interfaccia(d, prompt='Interfaccia'):
    ifs = d['interfacce']
    if not ifs:
        print(f"{d['nome']} non ha interfacce in lab.conf.")
        return None
    if len(ifs) == 1:
        return ifs[0]
    print_menu(f"Interfacce di {d['nome']}:", [f"{it['dev']}  LAN {it['lan']:<5} {it['ip'] or '(senza IP)'}" for it in ifs])
    s = input(f"{prompt} (numero, Invio = annulla): ").strip()
    if s.isdigit() and 1 <= int(s) <= len(ifs):
        return ifs[int(s) - 1]
    print('Annullato.')
    return None


def _membri_lan(disp, lan):
    return [(d['nome'], it) for d in disp.values() for it in d['interfacce'] if it['lan'] == lan]


def _rete_lan(disp, lan):
    for _, it in _membri_lan(disp, lan):
        try:
            return ipaddress.ip_interface(it['ip']).network
        except ValueError:
            continue
    return None


def _si(prompt, default=False):
    r = input(prompt).strip().lower()
    if not r:
        return default
    return r in ('s', 'si', 'sì', 'y')


def _chiedi_nuovo_ip(prompt, own, rete=None, dentro=None, propri=()):
    """IP con maschera (senza maschera prende quella di `rete`); rifiuta indirizzo di rete/broadcast,
    IP già usati da altri (tranne `propri`) e, se `dentro` è dato, IP fuori da quella rete."""
    while True:
        s = input(prompt).strip()
        if not s:
            return None
        if '/' not in s and rete is not None:
            s = f"{s}/{rete.prefixlen}"
        try:
            i = ipaddress.ip_interface(s)
        except ValueError:
            print("❌ Formato non valido: x.x.x.x/yy (es. 10.0.0.5/24).")
            continue
        if i.network.prefixlen < 31 and i.ip in (i.network.network_address, i.network.broadcast_address):
            print(f"❌ {i.ip} è l'indirizzo di rete o di broadcast di {i.network}.")
            continue
        if dentro is not None and i.network != dentro:
            print(f"❌ Deve essere nella rete {dentro}.")
            continue
        chi = own.get(str(i.ip))
        if chi and str(i.ip) not in propri:
            print(f"❌ {i.ip} è già usato da {chi[0]} ({chi[1]}).")
            continue
        return i


# --- B: IP, rete di una LAN, spostamento di interfaccia, gateway ---
def modifica_ip_interfaccia(lab_path, routers, nome):
    disp = leggi_dispositivi(lab_path)
    own = _proprietari(disp)
    it = _scegli_interfaccia(disp[nome], "Interfaccia di cui cambiare l'IP")
    if not it:
        return
    if not it['ip']:
        print(f"{it['dev']} non ha un IP nello startup: aggiungilo con la modifica a righe.")
        return
    vecchio = ipaddress.ip_interface(it['ip'])
    altri = [(n, x) for n, x in _membri_lan(disp, it['lan']) if not (n == nome and x['dev'] == it['dev']) and x['ip']]
    print(f"\n{nome} {it['dev']} (LAN {it['lan']}): IP attuale {vecchio}")
    if altri:
        print(f"Sulla LAN {it['lan']} ({vecchio.network}) ci sono anche: " + ', '.join(f"{n} {x['ip']}" for n, x in altri))
    nuovo = _chiedi_nuovo_ip(f"Nuovo IP (es. {vecchio.ip}/{vecchio.network.prefixlen}; senza maschera tiene "
                             f"/{vecchio.network.prefixlen}; Invio = annulla): ", own, rete=vecchio.network,
                             propri=(str(vecchio.ip),))
    if nuovo is None or nuovo == vecchio:
        print('Nessuna modifica.')
        return
    if nuovo.network != vecchio.network and altri:
        print(f"⚠️ {nuovo} non è nella rete della LAN {it['lan']} ({vecchio.network}): gli altri dispositivi "
              f"della LAN non lo raggiungerebbero.")
        print("  1) cambia la rete di tutta la LAN (anche gli IP degli altri)\n  2) cambia solo questo IP\n  0) annulla")
        s = input("Scelta: ").strip()
        if s == '1':
            rinumera_lan(lab_path, routers, it['lan'], nuova_rete=nuovo.network, fissi={(nome, it['dev']): nuovo})
            return
        if s != '2':
            print('Annullato.')
            return
    net_map = {str(vecchio.network): str(nuovo.network)} if nuovo.network != vecchio.network and not altri else {}
    _esegui_sostituzione(lab_path, routers, {str(vecchio.ip): str(nuovo.ip)}, {str(vecchio): str(nuovo)}, net_map,
                         f"IP di {nome} {it['dev']}: {vecchio} -> {nuovo}")


def rinumera_lan_menu(lab_path, routers, nome):
    it = _scegli_interfaccia(leggi_dispositivi(lab_path)[nome], 'LAN da rinumerare (scegli l\'interfaccia)')
    if it:
        rinumera_lan(lab_path, routers, it['lan'])


def rinumera_lan(lab_path, routers, lan, nuova_rete=None, fissi=None):
    """Cambia la rete di una LAN: ogni dispositivo tiene la stessa parte host (10.0.0.1 -> 10.0.5.1)
    quando ci sta, altrimenti chiede l'IP."""
    disp = leggi_dispositivi(lab_path)
    own = _proprietari(disp)
    membri = [(n, x) for n, x in _membri_lan(disp, lan) if x['ip']]
    vecchia = _rete_lan(disp, lan)
    if not vecchia:
        print(f"La LAN {lan} non ha IP da cambiare.")
        return
    print(f"\nLAN {lan}: rete {vecchia}; " + ', '.join(f"{n} {x['dev']} {x['ip']}" for n, x in membri))
    while nuova_rete is None:
        s = input("Nuova rete della LAN (es. 10.0.5.0/24, Invio = annulla): ").strip()
        if not s:
            print('Annullato.')
            return
        try:
            nuova_rete = ipaddress.ip_network(s, strict=False)
        except ValueError:
            print('❌ Rete non valida (es. 10.0.5.0/24).')
    if nuova_rete == vecchia:
        print('È la stessa rete: niente da fare.')
        return
    fuori = sorted(ip for ip, (n, dev, l) in own.items() if l != lan and ipaddress.ip_address(ip) in nuova_rete)
    if fuori and not _si(f"⚠️ La rete {nuova_rete} contiene già IP di altre LAN ({', '.join(fuori)}). Continuo? (s/N): "):
        print('Annullato.')
        return
    occupati = {ip for ip, (n, dev, l) in own.items() if l != lan}
    nuovi = {}
    for n, x in membri:
        k, v = (n, x['dev']), ipaddress.ip_interface(x['ip'])
        if fissi and k in fissi:
            nuovi[k] = fissi[k]
            continue
        cand, off = None, int(v.ip) - int(vecchia.network_address)
        if 0 <= off < nuova_rete.num_addresses:
            c = ipaddress.ip_interface(f"{ipaddress.ip_address(int(nuova_rete.network_address) + off)}/{nuova_rete.prefixlen}")
            if not (nuova_rete.prefixlen < 31 and c.ip in (nuova_rete.network_address, nuova_rete.broadcast_address)):
                cand = c
        if cand is None or str(cand.ip) in occupati or cand in nuovi.values():
            while True:
                cand = _chiedi_nuovo_ip(f"IP per {n} {x['dev']} in {nuova_rete} (era {v}; Invio = annulla tutto): ",
                                        own, rete=nuova_rete, dentro=nuova_rete, propri=[str(m['ip']).split('/')[0] for _, m in membri])
                if cand is None:
                    print('Annullato.')
                    return
                if cand in nuovi.values():
                    print(f"❌ {cand.ip} l'hai già dato a un altro dispositivo della LAN.")
                    continue
                break
        nuovi[k] = cand
    print(f"\nLAN {lan}: {vecchia} -> {nuova_rete}")
    for n, x in membri:
        print(f"   {n:<10} {x['dev']}  {x['ip']} -> {nuovi[(n, x['dev'])]}")
    vecchi = {(n, x['dev']): ipaddress.ip_interface(x['ip']) for n, x in membri}
    _esegui_sostituzione(lab_path, routers,
                         {str(vecchi[k].ip): str(nuovi[k].ip) for k in vecchi},
                         {str(vecchi[k]): str(nuovi[k]) for k in vecchi},
                         {str(vecchia): str(nuova_rete)},
                         f"Rete della LAN {lan}: {vecchia} -> {nuova_rete}")


def sposta_interfaccia(lab_path, routers, nome):
    disp = leggi_dispositivi(lab_path)
    own = _proprietari(disp)
    it = _scegli_interfaccia(disp[nome], 'Interfaccia da spostare')
    if not it:
        return
    lans = sorted({x['lan'] for dd in disp.values() for x in dd['interfacce']})
    print(f"\nLAN del lab:")
    for l in lans:
        print(f"   {l:<6} {str(_rete_lan(disp, l) or '-'):<18} " + ', '.join(n for n, _ in _membri_lan(disp, l)))
    while True:
        nuova = input(f"Nuova LAN per {nome} {it['dev']} (ora {it['lan']}; nome esistente o nuovo, Invio = annulla): ").strip()
        if not nuova:
            print('Annullato.')
            return
        if nuova in lans or nuova.isalnum():
            break
        print("❌ Nome LAN non valido: solo lettere e numeri (es. A o A1).")
    if nuova == it['lan']:
        print('È già su quella LAN.')
        return
    lc = 'lab.conf'
    vecchie = _righe_file(os.path.join(lab_path, lc))
    rx = re.compile(rf'^(\s*{re.escape(nome)}\s*\[\s*{it["idx"]}\s*\]\s*=\s*)(\S+?)(\s*)$')
    nuove, trovata = [], False
    for l in vecchie:
        m = rx.match(l)
        if m and not trovata:
            q = '"' if m.group(2).startswith('"') else ''
            l, trovata = f"{m.group(1)}{q}{nuova}{q}", True
        nuove.append(l)
    if not trovata:
        print(f"Non trovo la riga {nome}[{it['idx']}]=... in lab.conf.")
        return
    ip_map, iface_map = {}, {}
    rete = _rete_lan(disp, nuova)
    if it['ip'] and rete and ipaddress.ip_interface(it['ip']).network != rete:
        v = ipaddress.ip_interface(it['ip'])
        print(f"L'IP {v} non è nella rete della LAN {nuova} ({rete}).")
        n_ip = _chiedi_nuovo_ip(f"Nuovo IP in {rete} (Invio = lascia {v}): ", own, rete=rete, dentro=rete, propri=(str(v.ip),))
        if n_ip:
            ip_map, iface_map = {str(v.ip): str(n_ip.ip)}, {str(v): str(n_ip)}
    if len(_membri_lan(disp, it['lan'])) == 1:
        print(f"Nota: la LAN {it['lan']} resterà senza dispositivi.")

    def xml_lan(r, h, w):
        for dati in [r.get(nome)] + [x for x in h + w if x.get('name') == nome]:
            if not dati:
                continue
            for i in dati.get('interfaces') or []:
                if i.get('name') == it['dev']:
                    i['lan'] = nuova
            if it['idx'] == 0 and 'lan' in dati:
                dati['lan'] = nuova
    _esegui_sostituzione(lab_path, routers, ip_map, iface_map, {}, f"{nome} {it['dev']}: LAN {it['lan']} -> {nuova}",
                         extra={lc: (vecchie, nuove)}, xml_extra=xml_lan)


def cambia_gateway(lab_path, routers, nome):
    disp = leggi_dispositivi(lab_path)
    d = disp[nome]
    if d['tipo'] == 'router':
        print("Il default gateway si cambia su pc, www e dns.")
        return
    cand = []
    for it in d['interfacce']:
        for n, x in _membri_lan(disp, it['lan']):
            if n != nome and x['ip'] and (disp[n]['tipo'] == 'router' or len(disp[n]['interfacce']) > 1):
                cand.append((x['ip'].split('/')[0], n, it['dev']))
    print(f"\nGateway attuale di {nome}: {d['gateway'] or 'nessuno'}")
    if cand:
        print_menu('Router sulle sue LAN:', [f"{ip}  ({n})" for ip, n, _ in cand])
    s = input("Nuovo gateway (numero dell'elenco o IP, Invio = annulla): ").strip()
    if not s:
        print('Annullato.')
        return
    if s.isdigit() and 1 <= int(s) <= len(cand):
        gw = cand[int(s) - 1][0]
    else:
        try:
            gw = str(ipaddress.ip_address(s.split('/')[0]))
        except ValueError:
            print('❌ IP non valido.')
            return
    dev = next((it['dev'] for it in d['interfacce'] if it['ip'] and
                ipaddress.ip_address(gw) in ipaddress.ip_interface(it['ip']).network), None)
    if dev is None:
        if not _si(f"⚠️ {gw} non è nella rete di nessuna interfaccia di {nome}. Lo metto comunque? (s/N): "):
            print('Annullato.')
            return
        dev = d['interfacce'][0]['dev'] if d['interfacce'] else 'eth0'
    rel = f"{nome}.startup"
    vecchie = _righe_file(os.path.join(lab_path, rel))
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
    if _applica_modifiche(lab_path, {rel: (vecchie, nuove)}, f"Gateway di {nome}: {d['gateway'] or '-'} -> {gw}"):
        def xml_gw(r, h, w):
            for x in h + w:
                if x.get('name') == nome:
                    x['gateway'] = gw
        _aggiorna_xml(lab_path, routers, xml_gw)


# --- C: protocolli e AS ---
def _inizio_blocco(righe, rx):
    return next((k for k, l in enumerate(righe) if re.match(rx, l.strip())), None)


def _fine_blocco(righe, inizio):
    """Indice dopo l'ultima riga del blocco che comincia a `inizio`. Il blocco finisce al primo
    comando globale (router, route-map, ip prefix-list...) anche se è rientrato: nelle soluzioni
    del corso (es. tennis) le route-map sono scritte rientrate dentro 'router bgp', ma per FRR
    sono fuori dal blocco, e una riga 'neighbor' scritta dopo di loro verrebbe scartata.
    Le righe senza rientro che non sono comandi globali restano nel blocco; si ferma a '!'."""
    fine = inizio + 1
    while fine < len(righe):
        s = righe[fine].strip()
        if s == 'exit':
            fine += 1
            break
        if s.startswith('!') or (s and _FRR_GLOBALI.match(s)):
            break
        fine += 1
    while fine - 1 > inizio and not righe[fine - 1].strip():
        fine -= 1
    return fine


def _inserisci_nel_blocco(righe, rx, nuove):
    i = _inizio_blocco(righe, rx)
    if i is None:
        return None
    f = _fine_blocco(righe, i)
    return righe[:f] + ['    ' + x for x in nuove] + righe[f:]


def _set_demone(righe, demone, valore):
    out, fatto = [], False
    for l in righe:
        if re.match(rf'\s*{demone}\s*=', l):
            l, fatto = f"{demone}={valore}", True
        out.append(l)
    if not fatto:
        out.append(f"{demone}={valore}")
    return out


def _ip_del_router(d):
    return {it['ip'].split('/')[0] for it in d['interfacce'] if it['ip']} | {x.split('/')[0] for x in d['loopback']}


def cambia_as(lab_path, routers, nome):
    disp = leggi_dispositivi(lab_path)
    d = disp[nome]
    rel = os.path.join(nome, 'etc', 'frr', 'frr.conf')
    if not d['asn']:
        print(f"{nome} non ha 'router bgp': aggiungi BGP con la voce Protocolli.")
        return
    vecchio = d['asn']
    s = input(f"Nuovo AS di {nome} (ora {vecchio}; Invio = annulla): ").strip()
    if not s:
        print('Annullato.')
        return
    if not asn_valido(s) or s == vecchio:
        print('❌ AS non valido o uguale a quello attuale.')
        return
    modifiche = {}
    righe = _righe_file(os.path.join(lab_path, rel))
    modifiche[rel] = (righe, [re.sub(rf'^(\s*router\s+bgp\s+){vecchio}\b', rf'\g<1>{s}', l) for l in righe])
    miei = _ip_del_router(d)
    for n, dd in disp.items():
        if n == nome or not dd['frr']:
            continue
        r2 = os.path.join(n, 'etc', 'frr', 'frr.conf')
        v = _righe_file(os.path.join(lab_path, r2))
        nu = []
        for l in v:
            m = re.match(rf'^(\s*neighbor\s+(\S+)\s+remote-as\s+){vecchio}(\s*)$', l)
            nu.append(f"{m.group(1)}{s}{m.group(3)}" if m and m.group(2) in miei else l)
        modifiche[r2] = (v, nu)
    note = [f"{rel.replace(os.sep, '/')} riga {k}: '{l.strip()}' contiene ancora {vecchio}: controllala."
            for k, l in enumerate(righe, 1) if 'as-path' in l and re.search(rf'\b{vecchio}\b', l)]
    if re.match(rf'as{vecchio}r', nome):
        note.append(f"Il nome {nome} contiene ancora AS{vecchio}: il dispositivo non viene rinominato.")

    def xml_as(r, h, w):
        if nome in r:
            r[nome]['asn'] = s
    if _applica_modifiche(lab_path, modifiche, f"AS di {nome}: {vecchio} -> {s}", note):
        _aggiorna_xml(lab_path, routers, xml_as)


def modifica_protocolli(lab_path, routers, nome):
    disp = leggi_dispositivi(lab_path)
    d = disp[nome]
    if not d['frr']:
        print(f"{nome} non ha frr.conf (router solo con rotte statiche): usa la modifica a righe dello startup.")
        return
    attivi = [p for p in ('bgp', 'ospf', 'rip') if f"{p}d" in d['demoni']]
    print(f"\nProtocolli attivi su {nome}: {', '.join(attivi) or 'nessuno'}")
    s = input("a = aggiungi un protocollo, t = togli un protocollo, Invio = annulla: ").strip().lower()
    if s not in ('a', 't'):
        print('Annullato.')
        return
    scelte = [p for p in ('bgp', 'ospf', 'rip') if (p not in attivi) == (s == 'a')]
    if not scelte:
        print('Nessun protocollo da ' + ('aggiungere.' if s == 'a' else 'togliere.'))
        return
    print_menu('Protocollo:', [p.upper() for p in scelte])
    k = input('Numero (Invio = annulla): ').strip()
    if not (k.isdigit() and 1 <= int(k) <= len(scelte)):
        print('Annullato.')
        return
    (_aggiungi_protocollo if s == 'a' else _togli_protocollo)(lab_path, routers, disp, nome, scelte[int(k) - 1], attivi)


def _aggiungi_protocollo(lab_path, routers, disp, nome, p, attivi):
    d = disp[nome]
    rel = os.path.join(nome, 'etc', 'frr', 'frr.conf')
    reld = os.path.join(nome, 'etc', 'frr', 'daemons')
    righe = _righe_file(os.path.join(lab_path, rel))
    while righe and not righe[-1].strip():
        righe.pop()
    dm = _righe_file(os.path.join(lab_path, reld))
    modifiche = {reld: (dm, _set_demone(dm, f"{p}d", 'yes'))}
    dati = {'asn': d['asn'] or '', 'interfaces': [{'ip': it['ip']} for it in d['interfacce'] if it['ip']]}
    xml = {}
    if p in ('ospf', 'rip'):
        proposta = default_igp_networks(nome, dati)
        reti = input_reti(f"Network {p.upper()} da annunciare, separate da virgola (Invio = {', '.join(proposta)}): ",
                          default=proposta)
        redis = ['redistribute connected']
        if 'bgp' in attivi and _si(f"Iniettare in {p.upper()} le rotte imparate da BGP (redistribute bgp)? (S/n): ", True):
            redis.append('redistribute bgp')
        if p == 'ospf':
            area = input_area("Area OSPF (Invio = 0.0.0.0): ", default='0.0.0.0')
            stub = area not in ('0', '0.0.0.0') and _si("Area stub? (s/N): ")
            blocco = mk_ospf_stanza(reti, area, stub, redis).rstrip('\n').split('\n')
            xml.update(ospf_area=area, ospf_area_stub=stub)
        else:
            blocco = mk_rip_stanza(reti, redis).rstrip('\n').split('\n')
        xml['igp_networks'] = reti
        if 'bgp' in attivi and 'redistribute bgp' not in redis:
            xml['igp_redistribute_bgp'] = False
        i = _inizio_blocco(righe, r'router bgp\b')            # IGP prima di BGP, come nella creazione
        nuove = righe + [''] + blocco if i is None else righe[:i] + blocco + [''] + righe[i:]
        modifiche[rel] = (_righe_file(os.path.join(lab_path, rel)), nuove)
    else:
        m = re.match(r'as(\d+)r', nome)
        while True:
            s = input(f"Numero AS di {nome}" + (f" (Invio = {m.group(1)})" if m else '') + ": ").strip() or (m.group(1) if m else '')
            if asn_valido(s):
                asn = s
                break
            print("❌ Numero AS non valido: solo cifre (es. 20).")
        proprie = [_norm_net(it['ip']) for it in d['interfacce'] if it['ip']]
        reti = input_reti(f"Network BGP da annunciare (Invio = {', '.join(proprie) or 'nessuna'}): ",
                          default=proprie, opzionale=True)
        blocco = mk_bgp_stanza(asn, networks=reti).rstrip('\n').split('\n')
        scelti = []
        for it in d['interfacce']:
            for n2, x in _membri_lan(disp, it['lan']):
                d2 = disp[n2]
                if n2 == nome or not x['ip'] or 'bgpd' not in d2['demoni']:
                    continue
                ip2 = x['ip'].split('/')[0]
                if _si(f"Sessione BGP con {n2} ({ip2}, AS{d2['asn'] or '?'})? (S/n): ", True):
                    blocco += [f"    neighbor {ip2} remote-as {d2['asn']}", f"    neighbor {ip2} description Router {n2}"]
                    scelti.append((n2, it['ip'].split('/')[0], d2))
        if not any(l.strip().startswith('debug bgp') for l in righe):
            i = next((k for k, l in enumerate(righe) if l.strip().startswith('log file')), len(righe) - 1)
            righe = righe[:i + 1] + ['', 'debug bgp keepalives', 'debug bgp updates in', 'debug bgp updates out'] + righe[i + 1:]
        for igp in ('ospf', 'rip'):
            if igp in attivi and _si(f"Iniettare in {igp.upper()} le rotte imparate da BGP (redistribute bgp)? (S/n): ", True):
                con = _inserisci_nel_blocco(righe, rf'router {igp}\b', ['redistribute bgp'])
                righe = con if con is not None else righe
        modifiche[rel] = (_righe_file(os.path.join(lab_path, rel)), righe + [''] + blocco)
        for n2, mio_ip, d2 in scelti:
            if _si(f"Aggiungo anche su {n2}: neighbor {mio_ip} remote-as {asn}? (S/n): ", True):
                r2 = os.path.join(n2, 'etc', 'frr', 'frr.conf')
                v = _righe_file(os.path.join(lab_path, r2))
                con = _inserisci_nel_blocco(v, r'router bgp\b', [f"neighbor {mio_ip} remote-as {asn}",
                                                                  f"neighbor {mio_ip} description Router {nome}"])
                if con is not None:
                    modifiche[r2] = (v, con)
        xml['asn'] = asn

    def xml_p(r, h, w):
        if nome in r:
            if p not in r[nome].setdefault('protocols', []):
                r[nome]['protocols'].append(p)
            r[nome].update(xml)
    if _applica_modifiche(lab_path, modifiche, f"Aggiungi {p.upper()} a {nome}"):
        _aggiorna_xml(lab_path, routers, xml_p)


def _togli_protocollo(lab_path, routers, disp, nome, p, attivi):
    d = disp[nome]
    rel = os.path.join(nome, 'etc', 'frr', 'frr.conf')
    reld = os.path.join(nome, 'etc', 'frr', 'daemons')
    righe = _righe_file(os.path.join(lab_path, rel))
    dm = _righe_file(os.path.join(lab_path, reld))
    nuove = list(righe)
    i = _inizio_blocco(nuove, rf'router {p}\b')
    if i is not None:
        f = _fine_blocco(nuove, i)
        while f < len(nuove) and not nuove[f].strip():
            f += 1
        del nuove[i:f]
    nuove = [l for l in nuove if not re.match(rf'\s*redistribute\s+{p}\b', l)
             and not (p == 'bgp' and re.match(r'\s*debug\s+bgp\b', l))]
    modifiche = {rel: (righe, nuove), reld: (dm, _set_demone(dm, f"{p}d", 'no'))}
    note = []
    if p == 'bgp':
        miei = _ip_del_router(d)
        altri = {}
        for n2, d2 in disp.items():
            if n2 == nome or not d2['frr']:
                continue
            r2 = os.path.join(n2, 'etc', 'frr', 'frr.conf')
            v = _righe_file(os.path.join(lab_path, r2))
            nu = [l for l in v if not (re.match(r'\s*neighbor\s+(\S+)\s', l) and l.split()[1] in miei)]
            if nu != v:
                altri[r2] = (v, nu)
        if altri and _si(f"Tolgo anche le righe 'neighbor' che puntano a {nome} su "
                         f"{', '.join(sorted(r.split(os.sep)[0] for r in altri))}? (S/n): ", True):
            modifiche.update(altri)
        note.append("Route-map e prefix-list del router restano: i controlli le segnaleranno se non sono più usate.")

    def xml_p(r, h, w):
        if nome in r:
            r[nome]['protocols'] = [x for x in r[nome].get('protocols', []) if x != p]
            if p == 'bgp':
                r[nome]['asn'] = ''
    if _applica_modifiche(lab_path, modifiche, f"Togli {p.upper()} da {nome}", note):
        _aggiorna_xml(lab_path, routers, xml_p)


# --- menu del dispositivo ---
def _problemi_di(nome, avvisi):
    return [a for a in avvisi if re.search(rf'(?<![\w-]){re.escape(nome)}(?![\w-])', a)]


def _stampa_scheda(lab_path, disp, nome):
    d = disp[nome]
    own = _proprietari(disp)
    print(f"\n=== {nome} ({d['tipo']}" + (f", AS{d['asn']}" if d['asn'] else '') + ") ===")
    for it in d['interfacce']:
        print(f"   {it['dev']}  LAN {it['lan']:<5} {it['ip'] or '(senza IP)'}")
    for lb in d['loopback']:
        print(f"   lo    {lb}")
    if d['tipo'] == 'router':
        print(f"   protocolli: {', '.join(x[:-1] for x in d['demoni']) or 'nessuno'}")
    else:
        print(f"   gateway: {d['gateway'] or '-'}" + (f" ({own.get(d['gateway'], ('?',))[0]})" if d['gateway'] else ''))
    if d['nameserver']:
        print(f"   resolver: {', '.join(d['nameserver'])}")
    if d['zone']:
        print(f"   zone: {', '.join(z['zona'] + ' (' + z['tipo'] + ')' for z in d['zone'])}")
    problemi = _problemi_di(nome, _avvisi_lab(lab_path))
    for a in sorted(problemi):
        print(f"   ⚠️ {a}")


def modifica_dispositivo_menu(base_path, routers, nome=None):
    """Opzioni 11: modifica guidata di un dispositivo (IP, LAN, gateway, protocolli, AS) o a righe."""
    while True:
        disp = leggi_dispositivi(base_path)
        if not disp:
            print('Nessun dispositivo in lab.conf.')
            return
        if nome not in disp:
            nome = _scegli_dispositivo(disp)
            if not nome:
                return
        d = disp[nome]
        _stampa_scheda(base_path, disp, nome)
        voci = [("IP di un'interfaccia", modifica_ip_interfaccia),
                ('Rete di una LAN (cambia gli IP di tutti i dispositivi della LAN)', rinumera_lan_menu),
                ("Sposta un'interfaccia su un'altra LAN", sposta_interfaccia)]
        if d['tipo'] == 'router':
            voci.append(('Protocolli (aggiungi o togli BGP, OSPF, RIP)', modifica_protocolli))
            if d['asn']:
                voci.append(('AS del router', cambia_as))
        else:
            voci.append(('Default gateway', cambia_gateway))
        voci += [('Modifica a righe dei file (startup, frr.conf, resolv.conf, DNS)', modifica_righe),
                 ('Ripristina il lab da una copia di sicurezza', ripristina_copia)]
        print_menu(f'--- Modifica {nome} ---', [v[0] for v in voci],
                   extra_options=[('A', 'Altro dispositivo'), ('0', 'Torna indietro')])
        s = input('Seleziona: ').strip().lower()
        if s == '0' or not s:
            return
        if s == 'a':
            nome = None
            continue
        if s.isdigit() and 1 <= int(s) <= len(voci):
            voci[int(s) - 1][1](base_path, routers, nome)
        else:
            print('Scelta non valida, riprova.')


def menu_opzioni_laboratorio(base_path, routers):
    """Sottomenu per opzioni avanzate del laboratorio."""
    while True:
        items = [
            'Imposta costo OSPF',
            'Aggiungi Policies BGP',
            'Aggiungi interfaccia loopback',
            "Ridistribuzione BGP -> IGP (togli/rimetti 'redistribute bgp', route-map eBGP)",
            'Assegna un resolver ad un dispositivo',
            'Aggiungi network BGP (aggregato dell\'AS, reti interne, 0.0.0.0/0)',
            'Aggiungi sessioni iBGP (full mesh tra i router BGP dello stesso AS)',
            "Riepilogo configurazione (per controllare il testo dell'esercizio)",
            'Aggiungi delega DNS sul root (es. com -> dns.com)',
            'Costi OSPF predefiniti a 10 (auto-cost reference-bandwidth 100 su un AS)',
            'Modifica un dispositivo (IP, LAN, gateway, protocolli, AS, righe dei file)'
        ]
        print_menu(f'=== Opzioni Laboratorio ({os.path.basename(os.path.normpath(base_path))}) ===',
                   items, extra_options=[('0', 'Torna indietro')])
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
        # footer: mostrato in basso per identificazione dell'autore
        print('\n--------------------------------------------------')
        print('---- Programma realizzato da sciro24 (Github) ----')
        print('-------- versione portabile modificata -----------')
        print('--------------------------------------------------\n')

        choice = input('Seleziona (numero): ').strip()
        if choice == '0':
            # torna al menu precedente
            break
        if choice == '1':
            # rigenera XML leggendo lab.conf / startup / etc per ricostruire lo stato corrente
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


def export_lab_to_xml(lab_name, lab_path, routers, hosts, wwws):
    """Esporta una rappresentazione XML del laboratorio in `lab_path/<lab_name>.xml`.
    Struttura semplice: <lab><routers>...<hosts>...<www>...<lab_conf>...</lab>
    """
    try:
        import xml.etree.ElementTree as ET
        from xml.dom import minidom

        root = ET.Element('lab', attrib={'name': lab_name})

        routers_el = ET.SubElement(root, 'routers')
        for rname, rdata in routers.items():
            r_el = ET.SubElement(routers_el, 'router', attrib={'name': rname})
            # protocols
            prot_el = ET.SubElement(r_el, 'protocols')
            for p in rdata.get('protocols', []):
                p_el = ET.SubElement(prot_el, 'protocol')
                p_el.text = str(p)
            # asn
            asn = rdata.get('asn', '')
            if asn:
                asn_el = ET.SubElement(r_el, 'asn')
                asn_el.text = str(asn)
            # OSPF info (optional)
            if rdata.get('ospf_area'):
                oa = ET.SubElement(r_el, 'ospf_area')
                oa.text = str(rdata.get('ospf_area'))
                if rdata.get('ospf_area_stub'):
                    oas = ET.SubElement(r_el, 'ospf_area_stub')
                    oas.text = '1'
            # ospf_extra_areas (dict) if present
            if isinstance(rdata.get('ospf_extra_areas'), dict):
                extra_el = ET.SubElement(r_el, 'ospf_extra_areas')
                for k, v in rdata.get('ospf_extra_areas', {}).items():
                    e = ET.SubElement(extra_el, 'area', attrib={'first_octet': str(k)})
                    if isinstance(v, dict):
                        if v.get('area'):
                            ET.SubElement(e, 'id').text = str(v.get('area'))
                        if v.get('stub'):
                            ET.SubElement(e, 'stub').text = '1'
                    else:
                        ET.SubElement(e, 'id').text = str(v)
            # interfaces
            if 'interfaces' in rdata:
                ifs_el = ET.SubElement(r_el, 'interfaces')
                for iface in rdata['interfaces']:
                    i_el = ET.SubElement(ifs_el, 'interface')
                    i_el.set('name', iface.get('name', ''))
                    i_el.set('lan', iface.get('lan', ''))
                    i_el.set('ip', iface.get('ip', ''))
            if rdata.get('igp_redistribute_bgp') is False:
                ET.SubElement(r_el, 'igp_redistribute_bgp').text = '0'
            # network IGP e network BGP aggiuntive
            for key, tag in (('igp_networks', 'igp_network'), ('bgp_extra_networks', 'bgp_extra_network')):
                if rdata.get(key):
                    el = ET.SubElement(r_el, key)
                    for n in rdata[key]:
                        ET.SubElement(el, tag).text = str(n)
            # loopbacks
            if rdata.get('loopbacks'):
                lbs_el = ET.SubElement(r_el, 'loopbacks')
                for lb in rdata['loopbacks']:
                    ET.SubElement(lbs_el, 'loopback').text = str(lb)
            # rotte statiche (dict network/via/dev oppure stringa)
            if rdata.get('static_routes'):
                sr_el = ET.SubElement(r_el, 'static_routes')
                for sr in rdata['static_routes']:
                    if isinstance(sr, dict):
                        ET.SubElement(sr_el, 'route', attrib={k: str(v) for k, v in sr.items() if v})
                    else:
                        ET.SubElement(sr_el, 'route', attrib={'cmd': str(sr)})

        hosts_el = ET.SubElement(root, 'hosts')
        for h in hosts:
            h_ifaces = h.get('interfaces') or []
            # per gli host multi-interfaccia ip/lan riportano la prima interfaccia
            first = h_ifaces[0] if h_ifaces else {}
            h_attrib = {'name': h.get('name',''), 'ip': h.get('ip') or first.get('ip',''),
                        'gateway': h.get('gateway') or '', 'lan': h.get('lan') or first.get('lan','')}
            if h.get('gw_dev'):
                h_attrib['gw_dev'] = h.get('gw_dev')
            if h.get('image'):
                h_attrib['image'] = h.get('image')
            h_el = ET.SubElement(hosts_el, 'host', attrib=h_attrib)
            if h_ifaces:
                ifs_el = ET.SubElement(h_el, 'interfaces')
                for iface in h_ifaces:
                    ET.SubElement(ifs_el, 'interface', attrib={'name': iface.get('name', ''),
                                                              'lan': iface.get('lan', ''),
                                                              'ip': iface.get('ip', '')})
            # dns info
            if h.get('dns'):
                ET.SubElement(h_el, 'dns').text = '1'
                # export root_type if present
                if h.get('root_type'):
                    ET.SubElement(h_el, 'root_type').text = str(h.get('root_type'))
                if isinstance(h.get('forwarders'), list):
                    fw_el = ET.SubElement(h_el, 'forwarders')
                    for fwd in h.get('forwarders'):
                        ET.SubElement(fw_el, 'forwarder').text = str(fwd)
                if isinstance(h.get('zones'), dict):
                    zones_el = ET.SubElement(h_el, 'zones')
                    for zname, records in h.get('zones').items():
                        z_el = ET.SubElement(zones_el, 'zone', attrib={'name': zname})
                        if isinstance(records, dict):
                            for rname, rip in records.items():
                                rec = ET.SubElement(z_el, 'record', attrib={'name': rname})
                                # support both simple A-record (string) and complex record (dict)
                                if isinstance(rip, dict):
                                    # write child elements for complex record
                                    for k, v in rip.items():
                                        c = ET.SubElement(rec, k)
                                        c.text = str(v)
                                else:
                                    rec.text = str(rip)
                # export allow_recursion and dnssec_validation if present
                if h.get('allow_recursion'):
                    ET.SubElement(h_el, 'allow_recursion').text = str(h.get('allow_recursion'))
                if h.get('dnssec_validation'):
                    ET.SubElement(h_el, 'dnssec_validation').text = '1'
                if h.get('delegations'):
                    dl_el = ET.SubElement(h_el, 'delegations')
                    for dl in h['delegations']:
                        ET.SubElement(dl_el, 'delegation', attrib={k: str(dl.get(k, '')) for k in ('zone', 'ns', 'ip')})

        www_el = ET.SubElement(root, 'www')
        for w in wwws:
            w_attrib = {'name': w.get('name',''), 'ip': w.get('ip',''), 'gateway': w.get('gateway',''), 'lan': w.get('lan','')}
            if w.get('image'):
                w_attrib['image'] = w.get('image')
            ET.SubElement(www_el, 'server', attrib=w_attrib)

        # include lab.conf content se presente
        try:
            with open(os.path.join(lab_path, 'lab.conf'), 'r') as f:
                labconf = f.read()
            lc_el = ET.SubElement(root, 'lab_conf')
            lc_el.text = labconf
        except Exception:
            pass

        rough = ET.tostring(root, 'utf-8')
        reparsed = minidom.parseString(rough)
        pretty = reparsed.toprettyxml(indent='  ', encoding='utf-8')

        out_path = os.path.join(lab_path, f"{lab_name}.xml")
        with open(out_path, 'wb') as f:
            f.write(pretty)
        print(f"\n\n✅ Esportato XML: {out_path}")
    except Exception as e:
        print('Errore esportazione XML:', e)
 
# Funzionalità di caricamento non-interattivo (XML/JSON) e ricreazione lab
def load_lab_from_xml(path):
    """Carica un lab da file XML generato dallo script.
    Ritorna: lab_name, routers(dict), hosts(list), wwws(list), lab_conf_text(str or None)
    """
    import xml.etree.ElementTree as ET
    tree = ET.parse(path)
    root = tree.getroot()
    lab_name = root.attrib.get('name') or os.path.splitext(os.path.basename(path))[0]

    routers = {}
    for r in root.findall('./routers/router'):
        rname = r.attrib.get('name')
        protocols = [p.text for p in r.findall('./protocols/protocol') if p.text]
        asn_el = r.find('asn')
        asn = asn_el.text if asn_el is not None else ''
        ospf_area = None
        ospf_stub = False
        oa_el = r.find('ospf_area')
        if oa_el is not None and oa_el.text:
            ospf_area = oa_el.text
        oas_el = r.find('ospf_area_stub')
        if oas_el is not None:
            ospf_stub = True
        # ospf_extra_areas
        extra_areas = {}
        for ea in r.findall('./ospf_extra_areas/area'):
            key = ea.attrib.get('first_octet')
            aid = ea.findtext('id')
            stub = ea.findtext('stub') is not None
            if key:
                if aid:
                    extra_areas[str(key)] = {'area': aid, 'stub': stub}
                else:
                    extra_areas[str(key)] = {'area': None, 'stub': stub}

        interfaces = []
        for it in r.findall('./interfaces/interface'):
            interfaces.append({
                'name': it.attrib.get('name',''),
                'lan': it.attrib.get('lan',''),
                'ip': it.attrib.get('ip','')
            })
        rd = {'protocols': protocols, 'asn': asn, 'interfaces': interfaces}
        if ospf_area:
            rd['ospf_area'] = ospf_area
            rd['ospf_area_stub'] = ospf_stub
        if extra_areas:
            rd['ospf_extra_areas'] = extra_areas
        for key, tag in (('igp_networks', 'igp_network'), ('bgp_extra_networks', 'bgp_extra_network')):
            vals = [e.text.strip() for e in r.findall(f'./{key}/{tag}') if e.text]
            if vals:
                rd[key] = vals
        if (r.findtext('igp_redistribute_bgp') or '').strip() == '0':
            rd['igp_redistribute_bgp'] = False
        loopbacks = [lb.text for lb in r.findall('./loopbacks/loopback') if lb.text]
        if loopbacks:
            rd['loopbacks'] = loopbacks
        static_routes = []
        for sr in r.findall('./static_routes/route'):
            if sr.attrib.get('cmd') and len(sr.attrib) == 1:
                static_routes.append(sr.attrib['cmd'])
            else:
                static_routes.append(dict(sr.attrib))
        if static_routes:
            rd['static_routes'] = static_routes
        routers[rname] = rd

    hosts = []
    for h in root.findall('./hosts/host'):
        name = h.attrib.get('name','')
        ip = h.attrib.get('ip','')
        gateway = h.attrib.get('gateway','')
        lan = h.attrib.get('lan','')
        image = h.attrib.get('image','')
        host_rec = {'name': name, 'ip': ip, 'gateway': gateway, 'lan': lan}
        if image:
            host_rec['image'] = image
        if h.attrib.get('gw_dev'):
            host_rec['gw_dev'] = h.attrib.get('gw_dev')
        h_ifaces = [{'name': it.attrib.get('name', ''), 'lan': it.attrib.get('lan', ''), 'ip': it.attrib.get('ip', '')}
                    for it in h.findall('./interfaces/interface')]
        if h_ifaces:
            host_rec['interfaces'] = h_ifaces
        # dns
        if h.find('dns') is not None:
            host_rec['dns'] = True
            rt = h.find('root_type')
            if rt is not None and rt.text:
                host_rec['root_type'] = rt.text
            fwd_el = h.find('forwarders')
            if fwd_el is not None:
                host_rec['forwarders'] = [f.text for f in fwd_el.findall('forwarder') if f.text]
            zones_el = h.find('zones')
            if zones_el is not None:
                zones = {}
                for z in zones_el.findall('zone'):
                    zname = z.attrib.get('name')
                    records = {}
                    for rec in z.findall('record'):
                        rname = rec.attrib.get('name')
                        # record may be simple text or complex children
                        if len(list(rec)) == 0:
                            rip = rec.text
                            if rname and rip:
                                records[rname] = rip
                        else:
                            # complex record: parse children into dict
                            crec = {}
                            for c in rec:
                                crec[c.tag] = c.text
                            records[rname] = crec
                    zones[zname] = records
                host_rec['zones'] = zones
            deleghe = [dict(e.attrib) for e in h.findall('./delegations/delegation')]
            if deleghe:
                host_rec['delegations'] = deleghe
            # optional: allow_recursion and dnssec_validation flags
            ar_el = h.find('allow_recursion')
            if ar_el is not None and ar_el.text:
                host_rec['allow_recursion'] = ar_el.text.strip()
            dv_el = h.find('dnssec_validation')
            if dv_el is not None and (dv_el.text and dv_el.text.strip() in ('1','true','yes')):
                host_rec['dnssec_validation'] = True
        hosts.append(host_rec)

    wwws = []
    for w in root.findall('./www/server'):
        name = w.attrib.get('name','')
        ip = w.attrib.get('ip','')
        gateway = w.attrib.get('gateway','')
        lan = w.attrib.get('lan','')
        image = w.attrib.get('image','')
        wrec = {'name': name, 'ip': ip, 'gateway': gateway, 'lan': lan}
        if image:
            wrec['image'] = image
        wwws.append(wrec)

    lab_conf_text = None
    lc = root.find('lab_conf')
    if lc is not None and lc.text:
        lab_conf_text = lc.text

    return lab_name, routers, hosts, wwws, lab_conf_text


def load_lab_from_json(path):
    """Carica un lab da file JSON. Atteso schema simile all'XML prodotto.
    Ritorna: lab_name, routers(dict), hosts(list), wwws(list), lab_conf_text(str or None)
    """
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    lab_name = data.get('lab', {}).get('name') or data.get('name') or os.path.splitext(os.path.basename(path))[0]
    routers = {}
    for r in data.get('routers', []):
        rname = r.get('name')
        protocols = r.get('protocols', [])
        asn = r.get('asn', '')
        interfaces = r.get('interfaces', [])
        rd = {'protocols': protocols, 'asn': asn, 'interfaces': interfaces}
        # optional ospf fields
        if r.get('ospf_area'):
            rd['ospf_area'] = r.get('ospf_area')
            rd['ospf_area_stub'] = bool(r.get('ospf_area_stub'))
        if r.get('ospf_extra_areas'):
            rd['ospf_extra_areas'] = r.get('ospf_extra_areas')
        if r.get('static_routes'):
            rd['static_routes'] = r.get('static_routes')
        if r.get('loopbacks'):
            rd['loopbacks'] = r.get('loopbacks')
        for key in ('igp_networks', 'bgp_extra_networks'):
            if r.get(key):
                rd[key] = list(r.get(key))
        if r.get('igp_redistribute_bgp') is False:
            rd['igp_redistribute_bgp'] = False
        routers[rname] = rd
    hosts = data.get('hosts', []) or []
    wwws = data.get('www', []) or data.get('wwws', []) or []
    lab_conf_text = data.get('lab_conf') or None
    return lab_name, routers, hosts, wwws, lab_conf_text


def parse_startup_files(lab_path, nodes):
    """
    Legge i file <node>.startup per cercare configurazioni IP.
    Aggiorna il dizionario 'nodes' con gli IP trovati.
    Formato atteso: 'ip address add <IP> dev <IFACE>' o 'ifconfig <IFACE> <IP> ...'
    """
    import re
    # Regex per 'ip address add'
    re_ip_add = re.compile(r"ip\s+a(?:ddr(?:ess)?)?\s+add\s+(?P<ip>[0-9\./]+)\s+dev\s+(?P<iface>\w+)")
    # Regex per 'ifconfig' - ora cattura anche /CIDR
    re_ifconfig = re.compile(r"ifconfig\s+(?P<iface>\w+)\s+(?P<ip>[0-9\./]+)")

    for node_name, node_data in nodes.items():
        startup_path = os.path.join(lab_path, f"{node_name}.startup")
        if not os.path.exists(startup_path):
            continue
        
        try:
            with open(startup_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Cerca IP
            # Prima cerca con 'ip addr'
            for m in re_ip_add.finditer(content):
                ip = m.group('ip')
                iface = m.group('iface')
                # Trova l'indice dell'interfaccia
                # Le interfacce in nodes sono {idx: lan}
                # Dobbiamo mappare iface (eth0 -> 0, eth1 -> 1)
                idx = -1
                if iface.startswith('eth'):
                    try:
                        idx = int(iface[3:])
                    except: pass
                
                if idx >= 0 and str(idx) in node_data['interfaces'] or idx in node_data['interfaces']:
                    # Normalizza key a int se possibile o stringa
                    key = idx if idx in node_data['interfaces'] else str(idx)
                    # Aggiungiamo info IP
                    if 'ips' not in node_data: node_data['ips'] = {}
                    node_data['ips'][key] = ip

            # Poi cerca con 'ifconfig' (se non trovato prima o aggiuntivo)
            for m in re_ifconfig.finditer(content):
                ip = m.group('ip')
                iface = m.group('iface')
                idx = -1
                if iface.startswith('eth'):
                    try:
                        idx = int(iface[3:])
                    except: pass
                
                if idx >= 0 and (str(idx) in node_data['interfaces'] or idx in node_data['interfaces']):
                    key = idx if idx in node_data['interfaces'] else str(idx)
                    if 'ips' not in node_data: node_data['ips'] = {}
                    # Sovrascrivi o aggiungi
                    node_data['ips'][key] = ip

        except Exception as e:
            print(f"Errore parsing startup {node_name}: {e}")
    
    return nodes

def build_lab_conf_text(routers, hosts, wwws):
    """Ricostruisce il contenuto di lab.conf dai dati (usato quando l'XML/JSON
    importato non contiene già il testo di lab.conf)."""
    lines = []
    for rname, rdata in routers.items():
        for idx, iface in enumerate(rdata.get('interfaces', [])):
            lines.append(f"{rname}[{idx}]={iface.get('lan', '')}")
        if any(p in rdata.get('protocols', []) for p in ("bgp", "ospf", "rip")):
            lines.append(f'{rname}[image]="kathara/frr"')
        lines.append("")
    for node in list(hosts) + list(wwws):
        ifaces = node.get('interfaces') or [{'lan': node.get('lan', '')}]
        for idx, iface in enumerate(ifaces):
            lines.append(f"{node.get('name')}[{idx}]={iface.get('lan', '')}")
        lines.append(f'{node.get("name")}[image]="{node.get("image") or "kathara/base"}"')
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _scegli_nomi_validi(nomi, interactive, annulla):
    """Per i nomi non validi per Kathará propone un nome corretto e chiede conferma
    (S = proposte, m = scegli tu, n = `annulla`). Ritorna {vecchio: nuovo} ({} se sono
    tutti validi) oppure None se l'utente annulla."""
    errati = [n for n in nomi if n and not nome_kathara_valido(n)]
    if not errati:
        return {}
    usati = {n for n in nomi if n not in errati}
    mappa = {}
    for n in errati:
        nuovo, k = correggi_nome_kathara(n), 2
        while nuovo in usati:
            nuovo, k = f"{correggi_nome_kathara(n)}_{k}", k + 1
        mappa[n] = nuovo
        usati.add(nuovo)
    print("\n⚠️ Nomi non validi per Kathará (solo lettere minuscole, cifre e _): il lab non si avvierebbe.")
    for vecchio, nuovo in mappa.items():
        print(f"   {vecchio} -> {nuovo}")
    if not interactive:
        print("   (rinominati automaticamente)")
        return mappa
    r = input(f"Rinominare così? (S = sì / m = scegli tu i nomi / n = {annulla}) [S]: ").strip().lower()
    if r == 'n':
        return None
    if r == 'm':
        usati = {n for n in nomi if n not in errati}
        for vecchio in mappa:
            mappa[vecchio] = _chiedi_nome(f"al posto di '{vecchio}'", mappa[vecchio], usati)
            usati.add(mappa[vecchio])
    return mappa


def correggi_nomi_lab(lab_path, interactive=True):
    """Rinomina sul posto i dispositivi con nomi non validi per Kathará di un lab già
    creato: righe di lab.conf, cartella, <nome>.startup e nome nell'XML del generatore.
    Non rigenera nulla, quindi le modifiche fatte dal menu Opzioni (policy, iBGP,
    network, deleghe DNS, resolver) restano. Ritorna True se ha rinominato qualcosa."""
    nodes, testo = parse_lab_conf_for_nodes(lab_path)
    mappa = _scegli_nomi_validi(list(nodes), interactive, 'lascia così')
    if not mappa:
        return False
    def sostituisci(t):
        for vecchio, nuovo in mappa.items():
            t = re.sub(rf"^(\s*){re.escape(vecchio)}(\s*\[)", rf"\g<1>{nuovo}\g<2>", t, flags=re.M)
            t = t.replace(f'name="{vecchio}"', f'name="{nuovo}"')
        return t
    def _scrivi_testo(p, t):
        with open(p, 'w', encoding='utf-8', newline='\n') as f:
            f.write(t)
    _scrivi_testo(os.path.join(lab_path, 'lab.conf'), sostituisci(testo))
    for vecchio, nuovo in mappa.items():
        for v, n in ((vecchio, nuovo), (f"{vecchio}.startup", f"{nuovo}.startup")):
            if os.path.exists(os.path.join(lab_path, v)):
                os.rename(os.path.join(lab_path, v), os.path.join(lab_path, n))
    xml = os.path.join(lab_path, os.path.basename(os.path.normpath(lab_path)) + '.xml')
    if os.path.exists(xml):
        with open(xml, 'r', encoding='utf-8') as f:
            _scrivi_testo(xml, sostituisci(f.read()))
    print("✅ Dispositivi rinominati (lab.conf, cartelle, .startup, XML). Il resto del lab non è cambiato.")
    return True


def correggi_nomi_importati(routers, hosts, wwws, lab_conf_text, interactive=True):
    """Nomi dei dispositivi non validi per Kathará in un XML/JSON (es. 'ns-com'): li
    rinomina in dati e lab.conf prima di ricreare il lab. In modalità interattiva chiede
    conferma (S = proposte, m = scegli tu, n = annulla).
    Ritorna (routers, lab_conf_text) aggiornati, oppure None se l'utente annulla."""
    nomi = list(routers) + [d.get('name') for d in list(hosts) + list(wwws) if isinstance(d, dict)]
    mappa = _scegli_nomi_validi(nomi, interactive, "annulla l'import")
    if mappa is None:
        print('Import annullato.')
        return None
    if not mappa:
        return routers, lab_conf_text
    routers = {mappa.get(n, n): d for n, d in routers.items()}
    for d in list(hosts) + list(wwws):
        if isinstance(d, dict) and d.get('name') in mappa:
            d['name'] = mappa[d['name']]
    if lab_conf_text:
        for vecchio, nuovo in mappa.items():
            lab_conf_text = re.sub(rf"^(\s*){re.escape(vecchio)}(\s*\[)", rf"\g<1>{nuovo}\g<2>",
                                   lab_conf_text, flags=re.M)
    return routers, lab_conf_text


def recreate_lab_from_data(lab_name, base, routers, hosts, wwws, lab_conf_text=None, confirm=False):
    """Ricrea il lab sul filesystem usando le funzioni esistenti.
    Restituisce il percorso `lab_path` creato, o None se l'utente annulla.
    - confirm=True: se la cartella esiste chiede conferma prima di cancellarla.
    """
    lab_path = os.path.join(base, lab_name)
    if os.path.exists(lab_path):
        if confirm:
            print(f"⚠️ La cartella {lab_path} esiste già. Se la sovrascrivi, il lab viene rigenerato dall'XML:")
            print("   le modifiche fatte dopo la creazione dal menu Opzioni (policy, iBGP, network BGP,")
            print("   costi OSPF, deleghe DNS, resolver, ridistribuzione) NON sono nell'XML e andranno perse.")
            ans = input("Sovrascrivere? (s/n): ").strip().lower()
            if ans != 's':
                print("Annullato.")
                return None
        # rimuovi esistente per ricreare
        if os.path.isdir(lab_path):
            shutil.rmtree(lab_path)
        else:
            os.remove(lab_path)
    os.makedirs(lab_path, exist_ok=True)

    # crea routers
    for rname, rdata in routers.items():
        crea_router_files(lab_path, rname, rdata, interactive=False)

    # crea hosts
    # prima pass: individua l'eventuale server DNS master per usare il suo IP come riferimento
    dns_root_ip = None
    for h in hosts:
        try:
            if isinstance(h, dict) and h.get('dns') and str(h.get('root_type','')).lower() == 'master':
                # estrai IP senza CIDR
                ip = h.get('ip') or ''
                dns_root_ip = ip.split('/')[0] if '/' in ip else ip
                break
        except Exception:
            continue

    for h in hosts:
        try:
            # supporta host DNS: se il dict contiene 'dns': True o 'type' == 'dns'
            if (isinstance(h, dict) and (h.get('dns') or str(h.get('type','')).lower() == 'dns')):
                # forwarders e zones sono opzionali
                fwd = h.get('forwarders') if isinstance(h.get('forwarders'), list) else None
                zones = h.get('zones') if isinstance(h.get('zones'), dict) else None
                rt = h.get('root_type') if isinstance(h.get('root_type'), str) else None
                # read optional flags from host dict (allow_recursion may be a string like 'any')
                allow_rec = h.get('allow_recursion') if isinstance(h.get('allow_recursion'), str) else None
                dnssec_val = bool(h.get('dnssec_validation'))
                if rt and str(rt).lower() != 'master' and dns_root_ip:
                    crea_dns_host(lab_path, h.get('name'), h.get('ip'), h.get('gateway'), h.get('lan'), forwarders=fwd, zones=zones, root_type=rt, root_server_ip=dns_root_ip, allow_recursion=allow_rec, dnssec_validation=dnssec_val)
                else:
                    crea_dns_host(lab_path, h.get('name'), h.get('ip'), h.get('gateway'), h.get('lan'), forwarders=fwd, zones=zones, root_type=rt, allow_recursion=allow_rec, dnssec_validation=dnssec_val,
                                  delegations=h.get('delegations') if isinstance(h.get('delegations'), list) else None)
            else:
                ifaces = h.get('interfaces') or [{'name': 'eth0', 'ip': h.get('ip'), 'lan': h.get('lan')}]
                crea_host_multi(lab_path, h.get('name'), ifaces, h.get('gateway'), h.get('gw_dev') or 'eth0')
        except Exception as e:
            print(f"⚠️ Errore creando l'host {h.get('name') if isinstance(h, dict) else h}: {e}")

    # crea webservers
    for w in wwws:
        try:
            crea_www_file(lab_path, w.get('name'), w.get('ip'), w.get('gateway'), w.get('lan'))
        except Exception as e:
            print(f"⚠️ Errore creando il webserver {w.get('name')}: {e}")

    # scrivi lab.conf: quello fornito, altrimenti ricostruito dai dati
    if not lab_conf_text:
        lab_conf_text = build_lab_conf_text(routers, hosts, wwws)
    try:
        with open(os.path.join(lab_path, 'lab.conf'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(lab_conf_text)
    except Exception as e:
        print(f"⚠️ Errore scrivendo lab.conf: {e}")

    # auto-generate BGP neighbors
    auto_generate_bgp_neighbors(lab_path, routers)
    # link interni all'AS: non annunciati in BGP (li porta l'IGP)
    rimuovi_network_bgp_interne(lab_path, routers)

    # esporta XML (aggiorna o crea)
    try:
        export_lab_to_xml(lab_name, lab_path, routers, hosts, wwws)
    except Exception:
        pass

    return lab_path


def parse_lab_conf_for_nodes(lab_path):
    """Parse `lab.conf` per ricavare nodi, mapping interfacce->LAN e immagini.
    Ritorna: nodes dict with keys: name -> {'interfaces': {idx: lan}, 'image': image}
    """
    import re
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
    # pattern: name[index]=value (handles spaces and quotes)
    # e.g. r1[0]="A" or r1[0]=A or r1 [ 0 ] = "A"
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
            # treat as interface index
            try:
                node['interfaces'][int(idx)] = val
            except Exception:
                node['interfaces'][idx] = val
    return nodes, lab_conf_text


def rebuild_lab_metadata_and_export(lab_path):
    """Ricostruisce routers/hosts/www dal filesystem (lab.conf, startup, etc) e rigenera l'XML.
    Restituisce il percorso del file XML creato o None in caso di errore.
    """
    lab_name = os.path.basename(os.path.normpath(lab_path))
    nodes, lab_conf_text = parse_lab_conf_for_nodes(lab_path)
    routers = {}
    hosts = []
    wwws = []

    for name, meta in nodes.items():
        image = meta.get('image','')
        # collect interfaces: build list of dicts {name, lan, ip}
        ifaces = []
        for idx, lan in sorted(meta.get('interfaces', {}).items(), key=lambda x: int(x[0]) if isinstance(x[0], int) or x[0].isdigit() else 0):
            eth = f"eth{idx}"
            ifaces.append({'name': eth, 'lan': lan, 'ip': ''})

        # read startup file for IPs and gateways
        startup_path = os.path.join(lab_path, f"{name}.startup")
        if os.path.exists(startup_path):
            try:
                with open(startup_path, 'r', encoding='utf-8') as f:
                    for L in f:
                        Ls = L.strip()
                        if not Ls:
                            continue
                        # ip address add <ip> dev <iface>
                        parts = Ls.split()
                        if len(parts) >= 5 and parts[0] == 'ip' and parts[1] == 'address' and parts[2] == 'add':
                            ip = parts[3]
                            dev = parts[5] if len(parts) > 5 and parts[4] == 'dev' else None
                            if dev:
                                for it in ifaces:
                                    if it['name'] == dev:
                                        it['ip'] = ip
                        # gateway extraction for hosts/www: 'ip route add default via <gw> dev eth0'
                        if len(parts) >= 7 and parts[0] == 'ip' and parts[1] == 'route' and parts[2] == 'add' and parts[3] == 'default' and parts[4] == 'via':
                            gw = parts[5]
                            # attach gateway to a host/www entry later
            except Exception:
                pass

        # if it's a FRR router image (heuristic)
        if 'frr' in image.lower() or 'kathara/frr' in image.lower():
            # detect protocols and ASN from etc/frr/frr.conf
            frr_conf = os.path.join(lab_path, name, 'etc', 'frr', 'frr.conf')
            protos = []
            asn = ''
            if os.path.exists(frr_conf):
                try:
                    with open(frr_conf, 'r', encoding='utf-8') as f:
                        txt = f.read()
                    if 'router bgp' in txt:
                        protos.append('bgp')
                        import re
                        m = re.search(r'router bgp\s+(\d+)', txt)
                        if m:
                            asn = m.group(1)
                    if 'router ospf' in txt:
                        protos.append('ospf')
                    if 'router rip' in txt:
                        protos.append('rip')
                except Exception:
                    pass
            routers[name] = {'protocols': protos, 'asn': asn, 'interfaces': ifaces}
        else:
            # decide host vs www by checking for www index file
            www_index = os.path.join(lab_path, name, 'var', 'www', 'html', 'index.html')
            # attempt to read IP/gateway from startup if present
            ip_val = ''
            gw_val = ''
            startup_path = os.path.join(lab_path, f"{name}.startup")
            if os.path.exists(startup_path):
                try:
                    with open(startup_path, 'r', encoding='utf-8') as f:
                        for L in f:
                            if 'ip address add' in L:
                                parts = L.strip().split()
                                if len(parts) >= 4:
                                    ip_val = parts[3]
                            if 'ip route add default via' in L:
                                parts = L.strip().split()
                                if len(parts) >= 6:
                                    gw_val = parts[5]
                except Exception:
                    pass
            if os.path.exists(www_index):
                wwws.append({'name': name, 'ip': ip_val, 'gateway': gw_val, 'lan': meta.get('interfaces', {}).get(0, '')})
            else:
                hosts.append({'name': name, 'ip': ip_val, 'gateway': gw_val, 'lan': meta.get('interfaces', {}).get(0, '')})

    try:
        export_lab_to_xml(lab_name, lab_path, routers, hosts, wwws)
        return os.path.join(lab_path, f"{lab_name}.xml")
    except Exception as e:
        print('Errore rigenerazione XML:', e)
        return None

# -------------------------
# Opzioni Laboratorio Menu
# -------------------------
def scegli_lab(base):
    """Fa scegliere un lab esistente: elenco numerato dei lab (cartelle con lab.conf)
    in `base`, oppure un percorso scritto a mano (relativo al terminale o a `base`).
    Ritorna il percorso della cartella o None."""
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
    """Opzioni su un lab già creato: chiede la cartella una volta sola e apre
    lo stesso menu del post-creazione (costo OSPF, policy, network BGP, ...)."""
    target = scegli_lab(base)
    if not target:
        return
    # nomi che Kathará non accetta (es. creati con versioni vecchie): rinomina sul posto
    correggi_nomi_lab(target)
    # router del lab dall'XML del generatore; se manca lo ricostruisce dai file
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

# -------------------------
# Creazione guidata a passi: '<' domanda precedente, '<<' ricomincia il
# dispositivo, riepilogo con conferma alla fine di ogni dispositivo
# -------------------------
def esegui_passi(titolo, costruisci_passi, riepilogo):
    """Esegue una sequenza di domande con navigazione e ritorna lo stato confermato.

    - costruisci_passi(stato) -> lista di funzioni passo(stato). Viene ricalcolata
      a ogni passo, così il numero di domande può dipendere dalle risposte già
      date (es. numero di interfacce).
    - riepilogo(stato) -> lista di righe mostrate prima della conferma finale.
    """
    global _NAV_ATTIVA
    prev = _NAV_ATTIVA
    _NAV_ATTIVA = True
    stato = {}
    i = 0
    try:
        while True:
            passi = costruisci_passi(stato) + [lambda st: _conferma(titolo, riepilogo(st))]
            if i >= len(passi):
                return stato
            try:
                passi[i](stato)
                i += 1
            except TornaIndietro:
                if i == 0:
                    print(f"  (sei già alla prima domanda di: {titolo})")
                else:
                    i -= 1
            except RicominciaDispositivo:
                print(f"\n>> Ricomincio da capo: {titolo}")
                stato.clear()
                i = 0
    finally:
        _NAV_ATTIVA = prev


def _conferma(titolo, righe):
    print(f"\n--- Riepilogo {titolo} ---")
    for r in righe:
        print(f"  {r}")
    while True:
        ans = input("Confermi? (s = sì / r = rifai da capo / < = correggi l'ultima risposta) [s]: ").strip().lower()
        if ans in ('', 's', 'si', 'sì'):
            return
        if ans == 'r':
            raise RicominciaDispositivo()
        print("Rispondi s, r oppure <.")


def _chiedi_nome(tipo, default, usati):
    s = None
    while True:
        if s is None:
            s = input(f"\nNome {tipo} (default {default}): ").strip() or default
        if not nome_kathara_valido(s):
            proposta = correggi_nome_kathara(s)
            print(f"❌ '{s}' non è valido per Kathará (solo lettere minuscole, cifre e _).")
            r = input(f"Usare '{proposta}'? (S/n, oppure scrivi un altro nome): ").strip()
            if r.lower() in ('', 's', 'si', 'sì'):
                s = proposta
            elif r.lower() == 'n':
                s = None
            else:
                s = r
            continue
        if s in usati:
            print(f"Nome '{s}' già usato. Scegli un altro.")
            s = None
            continue
        return s


def _chiedi_ip_libero(prompt, usati, altri):
    """IP/CIDR non ancora assegnato né nel lab (usati) né nel dispositivo corrente (altri)."""
    while True:
        ip = valida_ip_cidr(prompt)
        ip_only = ip.split('/')[0]
        if ip_only in usati or ip_only in altri:
            print(f"❌ Errore: l'IP {ip_only} è già stato assegnato. Scegli un altro IP.")
            continue
        return ip


def valida_gateway(prompt, opzionale=False):
    """IP del gateway, con o senza /prefisso (la maschera viene tolta)."""
    while True:
        s = input(prompt).strip()
        if not s and opzionale:
            return ''
        ip = s.split('/')[0]
        try:
            ipaddress.ip_address(ip)
            return ip
        except ValueError:
            print("❌ IP non valido (es. 10.0.0.1)" + (", invio per nessuno" if opzionale else ""))


def _ifaces_stato(st):
    """Interfacce del dispositivo in costruzione, solo quelle entro n_if."""
    return [{'name': f"eth{k}", 'lan': st['if'][k]['lan'], 'ip': st['if'][k]['ip']}
            for k in range(st.get('n_if', 0))]


def _altri_ip(st, idx):
    return {v['ip'].split('/')[0] for k, v in st.get('if', {}).items()
            if k != idx and k < st.get('n_if', 0) and v.get('ip')}


def _passo_lan(idx, prompt):
    def f(st):
        st.setdefault('if', {}).setdefault(idx, {})['lan'] = input_lan(prompt)
    return f


def _passo_ip(idx, prompt, used_ips):
    def f(st):
        st.setdefault('if', {}).setdefault(idx, {})['ip'] = _chiedi_ip_libero(prompt, used_ips, _altri_ip(st, idx))
    return f


def _registra_ifaces(ctx, name, interfaces):
    for idx, it in enumerate(interfaces):
        ctx['lab_conf_lines'].append(f"{name}[{idx}]={it['lan']}")
        ctx['used_ips'].add(it['ip'].split('/')[0])
    ctx['used_names'].add(name)


def wizard_conteggi():
    def passo(chiave, prompt):
        def f(st):
            st[chiave] = input_int(prompt, 0)
        return f
    passi = [passo('n_router', "Numero di router: "), passo('n_host', "Numero di host/PC: "),
             passo('n_www', "Numero di server WWW: "), passo('n_dns', "Numero di host DNS: ")]
    st = esegui_passi("numero di dispositivi", lambda st: passi,
                      lambda st: [f"router: {st['n_router']}   host: {st['n_host']}   "
                                  f"www: {st['n_www']}   dns: {st['n_dns']}"])
    return st['n_router'], st['n_host'], st['n_www'], st['n_dns']


def wizard_router(i, ctx):
    used_ips = ctx['used_ips']

    def p_nome(st):
        st['nome'] = _chiedi_nome('router', f"r{i}", ctx['used_names'])
        print(f"--- Configurazione router {st['nome']} ---")

    def p_proto(st):
        st['protocols'] = valida_protocols(f"Protocolli attivi su {st['nome']} (bgp/ospf/rip/statico, separati da virgola): ")

    def p_asn(st):
        st['asn'] = input_asn("Numero AS BGP: ")

    def p_area(st):
        first = ctx['first_ospf_area']
        if first is None:
            ans = input_non_vuoto("Questo è il primo router OSPF. Appartiene alla backbone (area 0.0.0.0)? (s/N): ").strip().lower()
            if ans.startswith('s'):
                st['ospf_area'], st['ospf_stub'] = '0.0.0.0', False
            else:
                st['ospf_area'] = input_area("Inserisci l'area OSPF di questo router (es. 1.1.1.1): ")
                st['ospf_stub'] = True
        else:
            first_stub = ctx['first_ospf_stub']
            ans = input_area(f"Area OSPF per {st['nome']} (vuoto -> default {first}{' stub' if first_stub else ''}): ", default='')
            if ans:
                st['ospf_area'] = ans
                st['ospf_stub'] = input_non_vuoto("Marcare quest'area come stub? (s/N): ").strip().lower().startswith('s')
            else:
                # stessa area del primo router: deve avere anche lo stesso flag stub
                st['ospf_area'], st['ospf_stub'] = first, first_stub

    def p_nif(st):
        st['n_if'] = input_int("Numero interfacce: ", 1)

    def p_igp(st):
        nome_igp = '/'.join(p.upper() for p in ('ospf', 'rip') if p in st['protocols'])
        proposta = default_igp_networks(st['nome'], {'asn': st.get('asn', '') if 'bgp' in st['protocols'] else '',
                                                     'interfaces': _ifaces_stato(st)})
        st['igp_networks'] = input_reti(
            f"Network {nome_igp} da annunciare, separate da virgola (invio = {', '.join(proposta)}): ",
            default=proposta)

    def p_redbgp(st):
        nome_igp = '/'.join(p.upper() for p in ('ospf', 'rip') if p in st['protocols'])
        r = input(f"Iniettare in {nome_igp} le rotte imparate da BGP (redistribute bgp)? (S/n): ").strip().lower()
        st['igp_redistribute_bgp'] = not r.startswith('n')

    def p_nstatic(st):
        st['n_static'] = input_int("Numero di rotte statiche (0 se nessuna): ", 0)

    def p_static(si):
        def f(st):
            print(f"Rotta statica #{si+1}:")
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
            if 'bgp' in protos:
                out.append(p_redbgp)
        if 'statico' in protos:
            out.append(p_nstatic)
            out += [p_static(si) for si in range(st.get('n_static', 0))]
        return out

    def statiche(st):
        return [st['static'][k] for k in range(st.get('n_static', 0))] if 'statico' in st['protocols'] else []

    def riepilogo(st):
        protos = st['protocols']
        righe = [f"router {st['nome']}   protocolli: {' '.join(protos)}"
                 + (f"   AS {st['asn']}" if 'bgp' in protos else '')]
        if 'ospf' in protos:
            righe.append(f"OSPF area {st['ospf_area']}{' (stub)' if st['ospf_stub'] else ''}")
        for it in _ifaces_stato(st):
            righe.append(f"{it['name']}   LAN {it['lan']:<4} {it['ip']}")
        if 'ospf' in protos or 'rip' in protos:
            righe.append(f"network IGP: {', '.join(st['igp_networks'])}"
                         + (f"   redistribute bgp: {'sì' if st.get('igp_redistribute_bgp', True) else 'NO'}"
                            if 'bgp' in protos else ''))
        for r in statiche(st):
            righe.append(f"rotta {r['network']} via {r['via']}" + (f" dev {r['dev']}" if r.get('dev') else ''))
        return righe

    st = esegui_passi(f"router n.{i}", passi, riepilogo)

    name, protos = st['nome'], st['protocols']
    interfaces = _ifaces_stato(st)
    rdata = {"protocols": protos, "asn": st.get('asn', '') if 'bgp' in protos else '', "interfaces": interfaces}
    if 'statico' in protos:
        rdata['static_routes'] = statiche(st)
    if 'ospf' in protos:
        rdata['ospf_area'] = st['ospf_area']
        rdata['ospf_area_stub'] = st['ospf_stub']
        if ctx['first_ospf_area'] is None:
            ctx['first_ospf_area'], ctx['first_ospf_stub'] = st['ospf_area'], st['ospf_stub']
    if 'ospf' in protos or 'rip' in protos:
        rdata['igp_networks'] = st['igp_networks']
        if 'bgp' in protos and not st.get('igp_redistribute_bgp', True):
            rdata['igp_redistribute_bgp'] = False
    _registra_ifaces(ctx, name, interfaces)
    # l'immagine FRR solo se il router usa davvero un protocollo di routing
    if any(p in protos for p in ("bgp", "ospf", "rip")):
        ctx['lab_conf_lines'].append(f'{name}[image]="kathara/frr"')
    ctx['lab_conf_lines'].append("")
    ctx['routers'][name] = rdata
    crea_router_files(ctx['lab_path'], name, rdata)


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
            # il gateway deve stare nella subnet di un'interfaccia dell'host
            if gw and not iface_for_nexthop(_ifaces_stato(st), gw):
                reti = ', '.join(str(ipaddress.ip_interface(it['ip']).network) for it in _ifaces_stato(st))
                print(f"❌ {gw} non è in nessuna subnet di {st['nome']} ({reti}): "
                      f"il gateway è l'IP del router sulla stessa LAN dell'host.")
                continue
            st['gw'] = gw
            return

    def p_gwdev(st):
        nomi = [it['name'] for it in _ifaces_stato(st)]
        auto = iface_for_nexthop(_ifaces_stato(st), st['gw']) or nomi[0]
        if len(nomi) == 1:
            # una sola interfaccia: nessuna scelta possibile
            st['gw_dev'] = nomi[0]
            print(f"Interfaccia per il gateway: {nomi[0]}")
            return
        while True:
            dev = input(f"Interfaccia per il gateway {st['gw']} (default {auto}): ").strip() or auto
            if dev in nomi:
                st['gw_dev'] = dev
                return
            print(f"❌ {st['nome']} non ha l'interfaccia {dev} (ha: {', '.join(nomi)}).")

    def passi(st):
        out = [p_nome, p_nif]
        for idx in range(st.get('n_if', 0)):
            out.append(_passo_ip(idx, f"    IP per eth{idx} (es. 192.168.10.{h}/24): ", used_ips))
            out.append(_passo_lan(idx, f"    LAN associata a eth{idx} (es. A): "))
        out.append(p_gw)
        if st.get('gw'):
            out.append(p_gwdev)
        return out

    def riepilogo(st):
        righe = [f"host {st['nome']}"]
        righe += [f"{it['name']}   LAN {it['lan']:<4} {it['ip']}" for it in _ifaces_stato(st)]
        righe.append(f"default gateway: {st['gw']} dev {st['gw_dev']}" if st.get('gw') else "default gateway: nessuno")
        return righe

    st = esegui_passi(f"host n.{h}", passi, riepilogo)

    name, interfaces = st['nome'], _ifaces_stato(st)
    gw, gw_dev = st.get('gw', ''), (st.get('gw_dev', '') if st.get('gw') else '')
    _registra_ifaces(ctx, name, interfaces)
    crea_host_multi(ctx['lab_path'], name, interfaces, gw, gw_dev or 'eth0')
    ctx['hosts'].append({"name": name, "interfaces": interfaces, "gateway": gw, "gw_dev": gw_dev,
                         "ip": interfaces[0]['ip'], "lan": interfaces[0]['lan']})
    ctx['lab_conf_lines'].append(f'{name}[image]="kathara/base"')
    ctx['lab_conf_lines'].append("")


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

    st = esegui_passi(f"webserver n.{w}", lambda st: [p_nome, p_ip, p_gw, p_lan],
                      lambda st: [f"webserver {st['nome']}   eth0   LAN {st['lan']:<4} {st['ip']}",
                                  f"default gateway: {st['gw']}"])

    name = st['nome']
    _registra_ifaces(ctx, name, [{'lan': st['lan'], 'ip': st['ip']}])
    crea_www_file(ctx['lab_path'], name, st['ip'], st['gw'], st['lan'])
    ctx['wwws'].append({"name": name, "ip": st['ip'], "gateway": st['gw'], "lan": st['lan']})
    ctx['lab_conf_lines'].append(f'{name}[image]="kathara/base"')
    ctx['lab_conf_lines'].append("")


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
                # store delegation using the child label as key
                records[child] = rec
            else:
                print("      Tipo record non riconosciuto, salto questo record.")
        zones[zname] = records
    return zones


def wizard_dns(d, ctx):
    # Il primo host DNS deve essere per forza il server root (se il nome è libero)
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
        # resolver: accetta richieste ricorsive da tutti (any) o solo da alcune reti
        ar = input("Il server fa da resolver (allow-recursion)? (s/N): ").strip().lower()
        if not ar.startswith('s'):
            st['allow_recursion'] = None
            return
        while True:
            reti = input("  Da quali reti? (invio = any, es. 10.0.0.0/24): ").strip()
            if not reti or reti.lower() == 'any':
                st['allow_recursion'] = 'any'
                return
            try:
                st['allow_recursion'] = '; '.join(parse_reti(reti))
                return
            except ValueError as e:
                print(f"❌ Rete non valida: {e}")

    def p_dnssec(st):
        dv = input("Vuoi disabilitare DNSSEC validation ?  (s/N): ").strip().lower()
        st['dnssec_validation'] = dv.startswith('s')

    def p_deleghe(st):
        # il root deve delegare i domini di primo livello ai loro nameserver,
        # altrimenti nessuno trova il server autorevole (es. com -> dns.com)
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
        # per il server root: sempre master per '.', niente zone/allow-recursion/dnssec, ma deleghe
        if st.get('nome') == 'root':
            out.append(p_deleghe)
        else:
            out += [p_zone, p_root_type]
            if st.get('root_type') == 'master':
                out.append(p_deleghe)
            out += [p_rec, p_dnssec]
        return out

    def riepilogo(st):
        righe = [f"DNS {st['nome']}   eth0   LAN {st['lan']:<4} {st['ip']}   gateway {st['gw']}"]
        if st['nome'] == 'root':
            righe.append("server root (master per '.')")
        else:
            righe.append(f"tipo per '.': {st.get('root_type') or 'nessuno'}   "
                         f"allow-recursion: {st.get('allow_recursion') or 'no'}   "
                         f"dnssec-validation no: {'sì' if st.get('dnssec_validation') else 'no'}")
            for z, recs in (st.get('zones') or {}).items():
                righe.append(f"zona {z}: {len(recs)} record")
        if st['nome'] == 'root' or st.get('root_type') == 'master':
            dl = st.get('delegations') or []
            righe.append("deleghe: " + (', '.join(f"{x['zone']} -> {x['ns']} ({x['ip']})" for x in dl)
                                        if dl else "nessuna (attenzione: senza deleghe nessun dominio si risolve)"))
        return righe

    st = esegui_passi(f"host DNS n.{d}", passi, riepilogo)

    name, ip, gw, lan = st['nome'], st['ip'], st['gw'], st['lan']
    if name == 'root':
        zones, root_type, allow_recursion, dnssec_validation = None, 'master', None, False
    else:
        zones, root_type = st.get('zones'), st.get('root_type')
        allow_recursion, dnssec_validation = st.get('allow_recursion'), st.get('dnssec_validation', False)
    delegations = (st.get('delegations') or []) if root_type == 'master' else []
    # registra l'IP del root master per gli hint successivi
    if root_type == 'master':
        ctx['dns_root_ip'] = ip.split('/')[0]
    _registra_ifaces(ctx, name, [{'lan': lan, 'ip': ip}])
    try:
        crea_dns_host(ctx['lab_path'], name, ip, gw, lan, forwarders=None, zones=zones, root_type=root_type,
                      root_server_ip=ctx['dns_root_ip'] if root_type != 'master' else None,
                      allow_recursion=allow_recursion, dnssec_validation=dnssec_validation,
                      delegations=delegations)
    except Exception as e:
        print(f"⚠️ Errore creando l'host DNS {name}: {e}")
    ctx['hosts'].append({"name": name, "ip": ip, "gateway": gw, "lan": lan, "dns": True, "forwarders": None,
                         "zones": zones, 'root_type': root_type, 'allow_recursion': allow_recursion,
                         'dnssec_validation': dnssec_validation, 'delegations': delegations})
    ctx['lab_conf_lines'].append(f'{name}[image]="kathara/base"')
    ctx['lab_conf_lines'].append("")

# -------------------------
# Main
# -------------------------
def avvia_gui(base, porta=8765):
    """GUI web locale (gui/): topologia, riepilogo, comandi Kathará e test nel browser."""
    from gui import server
    server.avvia(base, sys.modules[__name__], porta)


def main():
    # Terminali non UTF-8 (es. LANG=C sui PC del laboratorio, output reindirizzato
    # su Windows): le emoji nei messaggi farebbero crashare print().
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except Exception:
            pass
    # supporto modalità non-interattiva: --from-xml / --from-json
    parser = argparse.ArgumentParser(description='Generatore Kathará')
    parser.add_argument('--from-xml', help='Percorso file XML da importare per creare il lab')
    parser.add_argument('--from-json', help='Percorso file JSON da importare per creare il lab')
    parser.add_argument('--regen-xml', help='Percorso della directory del lab per rigenerare il file XML')
    parser.add_argument('--out', help='Cartella in cui creare i lab (default: cartella corrente)')
    parser.add_argument('--force', action='store_true', help='Con --from-xml/--from-json: sovrascrive un lab già esistente')
    parser.add_argument('--gui', action='store_true', help='Apre la GUI nel browser (topologia, riepilogo, comandi Kathará, test)')
    parser.add_argument('--porta', type=int, default=8765, help='Porta della GUI su 127.0.0.1 (default 8765)')
    args, remaining = parser.parse_known_args()

    base = os.path.abspath(os.path.expanduser(args.out)) if args.out else os.getcwd()
    os.makedirs(base, exist_ok=True)

    if args.gui:
        avvia_gui(base, args.porta)
        return

    # Se forniti via CLI, manteniamo il comportamento non-interattivo
    if args.regen_xml:
        out = rebuild_lab_metadata_and_export(args.regen_xml)
        if out:
            print(f"✅ XML rigenerato: {out}")
        else:
            print("❌ Rigenerazione XML fallita.")
        return
    if args.from_xml or args.from_json:
        if args.from_xml:
            lab_name, routers, hosts, wwws, lab_conf_text = load_lab_from_xml(args.from_xml)
        else:
            lab_name, routers, hosts, wwws, lab_conf_text = load_lab_from_json(args.from_json)
        if os.path.exists(os.path.join(base, lab_name)) and not args.force:
            print(f"❌ Il lab '{lab_name}' esiste già in {base}. Usa --force per sovrascriverlo.")
            sys.exit(1)
        routers, lab_conf_text = correggi_nomi_importati(routers, hosts, wwws, lab_conf_text, interactive=False)
        lab_path = recreate_lab_from_data(lab_name, base, routers, hosts, wwws, lab_conf_text)
        print(f"✅ Lab '{lab_name}' creato (non-interattivo) in: {lab_path}")
        stampa_controllo_topologia(lab_path)
        return

    print(f"\nI lab verranno creati in: {base}")

    # Modalità interattiva: chiedi all'utente se creare o importare
    while True:
        print("\n\n----- Katharà Lab Generator 2025 - versione portabile modificata -----")
        print("      (basata sul lavoro di sciro24, GitHub)\n")
        print("Scegli una modalità:\n")
        print("  1) Crea nuovo Laboratorio")
        print("  2) Importa file XML/JSON")
        print("  3) Genera file XML")
        print("  4) Testa Funzionamento (PING)")
        print("  5) Opzioni Laboratorio")
        print("  6) Interfaccia grafica (browser)")
        print("  0) Esci\n")
        print("--------------------------------------------------------\n")
        
        mode = input_non_vuoto("Digita un'opzione (0-6): ").strip()
        if not mode:
            continue
        if mode == '0':
            print('Uscita.')
            return
        if mode == '1':
            # procedi con il flusso interattivo classico
            lab_name = input_lab_name("Nome del laboratorio (es. bgp_es1): ")
            lab_path = os.path.join(base, lab_name)
            break
        if mode == '2':
            file_path = input_non_vuoto("Percorso del file XML/JSON da importare: ").strip().strip('"')
            # percorso relativo al terminale oppure alla cartella dei lab (--out)
            if not os.path.exists(file_path) and os.path.exists(os.path.join(base, file_path)):
                file_path = os.path.join(base, file_path)
            if not os.path.exists(file_path):
                print(f"File non trovato: {file_path}")
                continue
            ext = os.path.splitext(file_path)[1].lower()
            try:
                if ext == '.xml':
                    lab_name, routers, hosts, wwws, lab_conf_text = load_lab_from_xml(file_path)
                elif ext == '.json':
                    lab_name, routers, hosts, wwws, lab_conf_text = load_lab_from_json(file_path)
                else:
                    # tenta XML prima, poi JSON
                    try:
                        lab_name, routers, hosts, wwws, lab_conf_text = load_lab_from_xml(file_path)
                    except Exception:
                        lab_name, routers, hosts, wwws, lab_conf_text = load_lab_from_json(file_path)
                corretti = correggi_nomi_importati(routers, hosts, wwws, lab_conf_text)
                if corretti is None:
                    continue
                routers, lab_conf_text = corretti
                lab_path = recreate_lab_from_data(lab_name, base, routers, hosts, wwws, lab_conf_text, confirm=True)
                if not lab_path:
                    continue
                print(f"✅ Lab '{lab_name}' creato da file in: {lab_path}")
                stampa_controllo_topologia(lab_path)
                return
            except Exception as e:
                print('Errore importando il file:', e)
                continue
        if mode == '3':
            target = input_non_vuoto('Percorso della directory del lab da cui rigenerare l\'XML: ')
            if not os.path.isdir(target):
                print(f"Directory non trovata: {target}")
                continue
            out = rebuild_lab_metadata_and_export(target)
            if out:
                print(f"✅ XML rigenerato: {out}")
            else:
                print("❌ Rigenerazione XML fallita.")
            return
        if mode == '4':
            target = input_non_vuoto('Percorso della directory del lab per generare il comando ping: ')
            if not os.path.isdir(target):
                print(f"Directory non trovata: {target}")
                continue
            # proviamo a leggere routers.xml se presente (semplifica raccolta IP), ma la funzione
            # collect_lab_ips può operare anche senza routers
            routers_meta = None
            try:
                xmlpath = os.path.join(target, os.path.basename(os.path.normpath(target)) + '.xml')
                if os.path.exists(xmlpath):
                    try:
                        _, routers_meta, _, _, _ = load_lab_from_xml(xmlpath)
                    except Exception:
                        routers_meta = None
            except Exception:
                routers_meta = None
            ips = collect_lab_ips(target, routers_meta)
            if not ips:
                print('Nessun IP trovato nella directory del lab. Controlla che ci siano file .startup o i router con interfacce.')
                continue
            cmd = generate_ping_oneliner(ips)
            print('\n=== Comando ping generato (copia/incolla sulle macchine del lab) ===\n\n')
            print(cmd)
            print('\n\n=== Fine comando ===\n')
            # torna al menu principale
            continue
        if mode == '5':
            # Opzioni Laboratorio - nuovo submenu
            opzioni_laboratorio_menu(base)
            continue
        if mode == '6':
            avvia_gui(base, args.porta)
            continue
        print('Scelta non valida, riprova.')

    if os.path.exists(lab_path):
        ans = input("⚠️ Esiste già. Sovrascrivere? (s/n): ").strip().lower()
        if ans != "s":
            print("Annullato.")
            return
        if os.path.isdir(lab_path):
            shutil.rmtree(lab_path)
        else:
            os.remove(lab_path)
        print("Precedente eliminato.")

    os.makedirs(lab_path, exist_ok=True)

    print("\nSuggerimento: durante la creazione digita '<' per tornare alla domanda precedente")
    print("e '<<' per ricominciare il dispositivo corrente. Alla fine di ogni dispositivo")
    print("vedrai un riepilogo da confermare prima che i file vengano scritti.")

    n_router, n_host, n_www, n_dns = wizard_conteggi()

    lab_conf_lines = [LAB_CONF_HEADER.strip()]
    routers = {}
    # Collezioni per esportazione XML
    hosts = []
    wwws = []
    # stato condiviso tra i dispositivi: IP e nomi già usati, prima area OSPF, root DNS
    ctx = {'lab_path': lab_path, 'lab_conf_lines': lab_conf_lines, 'routers': routers,
           'hosts': hosts, 'wwws': wwws, 'used_ips': set(), 'used_names': set(),
           'first_ospf_area': None, 'first_ospf_stub': False, 'dns_root_ip': None}

    for i in range(1, n_router + 1):
        wizard_router(i, ctx)
    for h in range(1, n_host + 1):
        wizard_host(h, ctx)
    for w in range(1, n_www + 1):
        wizard_www(w, ctx)
    for d in range(1, n_dns + 1):
        wizard_dns(d, ctx)

    # write lab.conf
    # Se è presente almeno un host DNS, chiedi se uno di loro deve essere
    # DNS resolver per gli altri dispositivi (host/pc/www).
    try:
        has_dns = any(isinstance(h, dict) and h.get('dns') for h in hosts)
    except Exception:
        has_dns = False

    if has_dns:
        ask_resolver = input("\nVuoi che uno dei DNS creati sia resolver per gli altri dispositivi? (s/N): ").strip().lower()
        if ask_resolver.startswith('s'):
            # elenca i DNS disponibili con IP
            dns_list = [h for h in hosts if isinstance(h, dict) and h.get('dns')]
            items = [f"{dh.get('name')} - { (str(dh.get('ip') or '')).split('/')[0] }" for dh in dns_list]
            print_menu('Seleziona il DNS resolver dalla lista seguente:', items)
            # scegli per nome o numero
            resolver_choice = input("Inserisci il nome o il numero del DNS resolver scelto: ").strip()
            resolver_ip = None
            # check by number
            if resolver_choice.isdigit():
                idx = int(resolver_choice) - 1
                if 0 <= idx < len(dns_list):
                    resolver_ip = str(dns_list[idx].get('ip') or '').split('/')[0]
            else:
                for dh in dns_list:
                    if dh.get('name') == resolver_choice:
                        resolver_ip = str(dh.get('ip') or '').split('/')[0]
                        break

            if resolver_ip:
                # crea etc/resolv.conf in tutte le cartelle dei dispositivi host/pc/www/dns
                targets = []
                try:
                    targets.extend([h.get('name') for h in hosts if isinstance(h, dict) and h.get('name')])
                except Exception:
                    pass
                try:
                    targets.extend([w.get('name') for w in wwws if isinstance(w, dict) and w.get('name')])
                except Exception:
                    pass

                for dev in set(targets):
                    etc_dir = os.path.join(lab_path, dev, 'etc')
                    try:
                        os.makedirs(etc_dir, exist_ok=True)
                        resolver_path = os.path.join(etc_dir, 'resolv.conf')
                        with open(resolver_path, 'w', encoding='utf-8', newline='\n') as rf:
                            rf.write(f"nameserver {resolver_ip}\n")
                    except Exception:
                        # ignoriamo errori di scrittura per non bloccare la creazione
                        pass
                print(f"\nResolver impostato: nameserver {resolver_ip} -> creati file resolv.conf nelle cartelle dei dispositivi.")
            else:
                print("Scelta del resolver non valida o IP non trovato: nessun resolver impostato.")

    with open(os.path.join(lab_path, "lab.conf"), 'w', encoding='utf-8', newline='\n') as f:
        f.write("\n".join(lab_conf_lines).strip() + "\n")

    # Auto-generate BGP neighbors for routers sharing LANs
    auto_generate_bgp_neighbors(lab_path, routers)
    # link interni all'AS: non annunciati in BGP (li porta l'IGP)
    rimuovi_network_bgp_interne(lab_path, routers)

    # Esporta il laboratorio in formato XML per poterlo riusare come input
    try:
        export_lab_to_xml(lab_name, lab_path, routers, hosts, wwws)
    except Exception as e:
        print('Attenzione: esportazione XML fallita:', e)

    print(f"\n✅ Lab '{lab_name}' creato in: {lab_path}")
    stampa_controllo_topologia(lab_path)
    # Menu in italiano per implementare richieste aggiuntive
    try:
        menu_post_creazione(lab_path, routers)
    except Exception as e:
        print('Errore durante il menu post-creazione:', e)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Graceful shutdown on Ctrl+C: clear terminal and exit without traceback
        try:
            print()  # ensure newline after ^C
        except Exception:
            pass
        try:
            if os.name == 'nt':
                os.system('cls')
            else:
                os.system('clear')
        except Exception:
            pass
        try:
            sys.exit(0)
        except Exception:
            # fallback
            os._exit(0)

