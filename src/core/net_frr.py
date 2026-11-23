"""
src/core/net_frr.py
Calcolo subnet, supernetting, costruttori stanze FRR (BGP/OSPF/RIP) e gestione automatica neighbor.
"""
import ipaddress
import os
import re

from .cli_io import input_asn
from .file_utils import (
    _append_righe,
    _esiste_file,
    _leggi_righe,
    _leggi_testo,
    _rimuovi_righe,
    _rimuovi_route_map,
    _scrivi_righe,
    insert_lines_into_protocol_block,
)


def aggregate_to_supernet_for_router(interface_ips, agg_prefix=16):
    """Aggrega le reti collegate di un router."""
    networks = []
    for ip_cidr in interface_ips:
        try:
            iface = ipaddress.ip_interface(ip_cidr)
            networks.append(iface.network)
        except ValueError:
            continue
    if not networks:
        return []

    collapsed = list(ipaddress.collapse_addresses(networks))
    ipv4_nets = [n for n in collapsed if isinstance(n, ipaddress.IPv4Network)]
    ipv6_nets = [n for n in collapsed if isinstance(n, ipaddress.IPv6Network)]

    super_map = {}
    for n in ipv4_nets:
        if n.prefixlen <= agg_prefix:
            super_map.setdefault(n, []).append(n)
        else:
            s = n.supernet(new_prefix=agg_prefix)
            super_map.setdefault(s, []).append(n)

    result_nets = []
    for supern, members in super_map.items():
        if isinstance(supern, ipaddress.IPv4Network):
            if len(members) > 1:
                result_nets.append(supern)
            else:
                result_nets.append(members[0])
        else:
            for m in members:
                result_nets.append(m)

    result_nets.extend(ipv6_nets)
    final = list(ipaddress.collapse_addresses(result_nets))
    return [str(n) for n in final]


def collapse_interface_networks(interface_ips):
    """Collassa le reti derivate dalle interfacce evitando di forzare supernet di lunghezza fissa."""
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
    """Sceglie un singolo supernet byte-aligned (solo /8 o /16) che copra tutte le interfacce."""
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

    same_first2 = all(o[:2] == octets_list[0][:2] for o in octets_list)
    same_first1 = all(o[0] == octets_list[0][0] for o in octets_list)

    if same_first2:
        a, b = octets_list[0][0], octets_list[0][1]
        return f"{a}.{b}.0.0/16"
    if same_first1:
        a = octets_list[0][0]
        return f"{a}.0.0.0/8"

    return None


def group_by_first_octet(interface_ips):
    """Raggruppa gli indirizzi per primo ottetto."""
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


def _norm_net(net):
    """'10.0.1.1/24' -> '10.0.1.0/24' (lascia invariato ciò che non è una rete valida)."""
    try:
        return str(ipaddress.ip_network(str(net).strip(), strict=False))
    except ValueError:
        return str(net).strip()


def _strip_cidr(ip_cidr):
    if not ip_cidr:
        return None
    return str(ip_cidr).split('/')[0]


def get_first_iface_ip(ifaces):
    if not ifaces:
        return None
    ip_cidr = ifaces[0].get("ip")
    if not ip_cidr:
        return None
    return ip_cidr.split("/")[0]


def find_routers_by_asn(routers, asn):
    return [name for name, r in routers.items() if str(r.get("asn", "")) == str(asn)]


def _as_number(rname, data):
    """Numero dell'AS del router: ASN BGP oppure dal nome 'as<N>r<M>'."""
    asn = str(data.get('asn') or '').strip()
    if asn.isdigit():
        return int(asn)
    m = re.match(r'as(\d+)r', rname or '', re.IGNORECASE)
    return int(m.group(1)) if m else None


def default_igp_networks(rname, data):
    """Network da annunciare in OSPF/RIP proposte per un router."""
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
    """Aggregato /8 dell'AS proposto per 'Aggiungi network BGP'."""
    return default_igp_networks(rname, data)


def mk_bgp_stanza(asn, redistribute=None, networks=None):
    """Costruisce la stanza BGP."""
    lines = [
        f"router bgp {asn}",
        "",
        "    no bgp ebgp-requires-policy",
        "    no bgp network import-check",
    ]
    if networks:
        lines.append("")
        seen = set()
        for net in networks:
            try:
                n = ipaddress.ip_network(net, strict=False)
                s = str(n)
            except Exception:
                s = str(net)
            if s not in seen:
                lines.append(f"    network {s}")
                seen.add(s)
    return "\n".join(lines) + "\n\n"


def mk_ospf_stanza(networks, area=None, stub=False, redistribute=None, aree=None, aree_stub=None):
    """Costruisce la stanza OSPF.

    Con una sola area: tutte le network in `area` (stub se `stub`). Per un router di confine
    (ABR): `aree` = {rete: area} dà l'area di ogni rete (le reti non elencate stanno in `area`)
    e `aree_stub` = le aree da dichiarare stub."""
    area = area or '0.0.0.0'
    aree = {_norm_net(k): v for k, v in (aree or {}).items()}
    lines = ["router ospf", ""]
    seen = set()
    for net in networks or []:
        s = _norm_net(net)
        if s not in seen:
            lines.append(f"    network {s} area {aree.get(s, area)}")
            seen.add(s)
    if aree:
        for a in aree_stub or []:
            lines.append(f"    area {a} stub")
    elif stub:
        lines.append(f"    area {area} stub")
    if redistribute:
        lines.append("")
        for cmd in redistribute:
            lines.append(f"    {cmd}")
    return "\n".join(lines) + "\n\n"


def mk_rip_stanza(networks, redistribute=None):
    """Costruisce la stanza RIP."""
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


def format_ospf_multi_area(area_nets_map, stub_areas=None, redistribute=None):
    """Costruisce un unico blocco 'router ospf' multi-area."""
    if stub_areas is None:
        stub_areas = set()
    lines = ["router ospf", ""]

    def area_sort_key(a):
        return (0 if a == '0.0.0.0' else 1, str(a))

    for area in sorted(area_nets_map.keys(), key=area_sort_key):
        nets = area_nets_map.get(area) or []
        for n in nets:
            lines.append(f"    network {n} area {area}")
    for area in sorted(stub_areas):
        lines.append(f"    area {area} stub")
    if stub_areas and redistribute:
        lines.append("")
    if redistribute:
        for cmd in redistribute:
            lines.append(f"    {cmd}")
    return "\n".join(lines) + "\n\n"


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
    """Restituisce le righe 'ip route add ...' per le rotte statiche del router."""
    static_routes = data.get('static_routes', []) or []
    route_lines = []
    default_dev = (data.get('interfaces') and data.get('interfaces')[0].get('name')) or 'eth0'
    for r in static_routes:
        if isinstance(r, str):
            s = re.sub(r"(via\s+)([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)/\d+", r"\1\2", r)
            route_lines.append(f"ip route add {s}")
        elif isinstance(r, dict):
            net = r.get('network') or r.get('net') or r.get('dest')
            via = r.get('via') or r.get('nexthop') or r.get('gw')
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


def add_neighbor_if_missing(base_path, src_router, neigh_ip, neigh_asn, desc=None):
    fpath = os.path.join(base_path, src_router, "etc", "frr", "frr.conf")
    if not _esiste_file(fpath):
        return
    content = _leggi_testo(fpath) or ''
    neigh_ip_stripped = neigh_ip.split('/')[0] if '/' in neigh_ip else neigh_ip
    if f"neighbor {neigh_ip_stripped} remote-as" in content:
        return
    lines = [f"neighbor {neigh_ip_stripped} remote-as {neigh_asn}"]
    if desc:
        lines.append(f"neighbor {neigh_ip_stripped} description {desc}")
    insert_lines_into_protocol_block(fpath, proto='bgp', asn=None, lines=lines)


def auto_generate_bgp_neighbors(base_path, routers):
    """Per ogni coppia di router sulla stessa LAN aggiunge i neighbor BGP reciproci."""
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
            for j in range(i + 1, len(members)):
                r1, ip1, asn1 = members[i]
                r2, ip2, asn2 = members[j]
                if "bgp" not in routers[r1]["protocols"] or "bgp" not in routers[r2]["protocols"]:
                    continue
                add_neighbor_if_missing(base_path, r1, ip2, routers[r2]['asn'], desc=f"Router {r2}")
                add_neighbor_if_missing(base_path, r2, ip1, routers[r1]['asn'], desc=f"Router {r1}")


def rimuovi_network_bgp_interne(base_path, routers):
    """Toglie dal blocco BGP le network dei link interni all'AS."""
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
            peering = any(
                'bgp' in routers[o].get('protocols', []) and _as_number(o, routers[o]) != my_as
                for o in others
            )
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


def add_ibgp_loopback_neighbors(base_path, routers):
    """Configura neighbor iBGP basati su loopback tra router dello stesso AS."""
    def _ensure_pair(r_local, r_peer):
        r_local_data = routers.get(r_local, {})
        r_peer_data = routers.get(r_peer, {})
        if not r_local_data or not r_peer_data:
            return
        asn_local = str(r_local_data.get('asn', '')).strip()
        asn_peer = str(r_peer_data.get('asn', '')).strip()
        if not asn_local or asn_local != asn_peer:
            return
        lbs_local = r_local_data.get('loopbacks') or []
        lbs_peer = r_peer_data.get('loopbacks') or []
        if not lbs_local or not lbs_peer:
            return
        lb_local = _strip_cidr(lbs_local[0])
        lb_peer = _strip_cidr(lbs_peer[0])
        if not lb_local or not lb_peer:
            return

        f_local = os.path.join(base_path, r_local, 'etc', 'frr', 'frr.conf')
        f_peer = os.path.join(base_path, r_peer, 'etc', 'frr', 'frr.conf')

        if not _esiste_file(f_local) or not _esiste_file(f_peer):
            return

        cont_local = _leggi_testo(f_local) or ''
        cont_peer = _leggi_testo(f_peer) or ''

        to_add_local = []
        if f"neighbor {lb_peer} remote-as" not in cont_local:
            to_add_local.append(f"neighbor {lb_peer} remote-as {asn_local}")
        if f"neighbor {lb_peer} update-source" not in cont_local:
            to_add_local.append(f"neighbor {lb_peer} update-source {lb_local}")

        to_add_peer = []
        if f"neighbor {lb_local} remote-as" not in cont_peer:
            to_add_peer.append(f"neighbor {lb_local} remote-as {asn_local}")
        if f"neighbor {lb_local} update-source" not in cont_peer:
            to_add_peer.append(f"neighbor {lb_local} update-source {lb_peer}")

        if to_add_local:
            insert_lines_into_protocol_block(f_local, proto='bgp', asn=asn_local, lines=to_add_local)
            print(f"✅ Aggiunti iBGP neighbor su {r_local}: {', '.join(to_add_local)}")
        if to_add_peer:
            insert_lines_into_protocol_block(f_peer, proto='bgp', asn=asn_local, lines=to_add_peer)
            print(f"✅ Aggiunti iBGP neighbor su {r_peer}: {', '.join(to_add_peer)}")

    names = list(routers.keys())
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            n1, n2 = names[i], names[j]
            if 'bgp' not in routers.get(n1, {}).get('protocols', []) or 'bgp' not in routers.get(n2, {}).get('protocols', []):
                continue
            asn1 = str(routers.get(n1, {}).get('asn', '')).strip()
            asn2 = str(routers.get(n2, {}).get('asn', '')).strip()
            if not asn1 or asn1 != asn2:
                continue
            lbs1 = routers.get(n1, {}).get('loopbacks') or []
            lbs2 = routers.get(n2, {}).get('loopbacks') or []
            if not lbs1 or not lbs2:
                continue
            _ensure_pair(n1, n2)


def _neighbor_presente(fpath, ip):
    return any(re.match(rf"\s*neighbor {re.escape(ip)} remote-as\b", l) for l in _leggi_righe(fpath))


def _collega_al_neighbor(fpath, ip, tipo, nome, direz):
    """Collega prefix-list/route-map al neighbor dentro router bgp."""
    vecchie = [
        l for l in _leggi_righe(fpath)
        if re.match(rf"\s*neighbor {re.escape(ip)} {tipo} (\S+) {direz}\s*$", l)
        and l.split()[3] != nome
    ]
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
    """IP dell'interfaccia di `y` da cui partono i pacchetti verso `x` lungo il percorso interno all'AS."""
    def interno(r):
        rd = routers[r]
        return ('bgp' not in rd.get('protocols', []) and rd.get('protocols')) or \
               str(rd.get('asn', '')).strip() == asn

    members = _lan_members(routers)
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

    data = routers[y]
    igp = [ipaddress.ip_network(n, strict=False) for n in (data.get('igp_networks') or default_igp_networks(y, data))]
    ifs = [ipaddress.ip_interface(it['ip']) for it in data.get('interfaces', []) if it.get('ip')]
    for i in ifs:
        if any(i.ip in n for n in igp):
            return str(i.ip)
    return str(ifs[0].ip) if ifs else None


def _contiene(rete, ip):
    try:
        return ipaddress.ip_address(ip.split('/')[0]) in ipaddress.ip_network(rete, strict=False)
    except ValueError:
        return False


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
    """Le network del router, ognuna con il router all'altro capo se è un link."""
    out = []
    for rete in reti:
        altri = [
            n for n, r in routers.items()
            if n != target and any(_contiene(rete, it.get('ip') or '') for it in r.get('interfaces', []))
        ]
        out.append(f"{rete}" + (f" (link con {', '.join(altri)})" if altri else " (rete propria)"))
    return out