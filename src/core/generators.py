"""
src/core/generators.py
Creazione su disco dei file di configurazione per router FRR, host, server WWW, DNS BIND9 e lab.conf.
"""
import datetime
import ipaddress
import os

from .net_frr import (
    collapse_interface_networks,
    default_igp_networks,
    mk_bgp_stanza,
    mk_ospf_stanza,
    mk_rip_stanza,
    static_route_lines,
)
from .templates import (
    DAEMONS_TMPL,
    FRR_HEADER,
    STARTUP_HOST_TMPL,
    STARTUP_ROUTER_TMPL,
    STARTUP_WWW_TMPL,
    VTYSH_TMPL,
)


def crea_router_files(base_path, rname, data, interactive=True):
    """Crea la cartella del router, i file FRR (daemons, vtysh.conf, frr.conf) e il file .startup."""
    protos = data.get("protocols") or []
    only_static = ('statico' in protos) and all(p == 'statico' for p in protos)
    if only_static:
        ip_cfg_lines = [
            f"ip address add {iface['ip']} dev {iface.get('name', 'eth0')}"
            for iface in data.get('interfaces', [])
        ]
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

    if "bgp" in data["protocols"]:
        parts.append(
            "debug bgp keepalives\n"
            "debug bgp updates in\n"
            "debug bgp updates out\n"
        )

    phys_iface_ips = [iface["ip"] for iface in data["interfaces"]]
    loopbacks = data.get('loopbacks') or []
    combined_ips = phys_iface_ips + loopbacks

    original_nets = []
    for ip_cidr in phys_iface_ips:
        try:
            n = ipaddress.ip_network(ip_cidr, strict=False)
            original_nets.append(str(n))
        except Exception:
            continue

    _ = collapse_interface_networks(combined_ips)

    protos = data.get("protocols", [])
    has_bgp = "bgp" in protos
    has_ospf = "ospf" in protos
    has_rip = "rip" in protos

    ospf_redistribute = []
    rip_redistribute = []

    inietta_bgp = has_bgp and data.get('igp_redistribute_bgp', True)
    if has_ospf:
        ospf_redistribute.append("redistribute connected")
        if inietta_bgp:
            ospf_redistribute.append("redistribute bgp")

    if has_rip:
        rip_redistribute.append("redistribute connected")
        if inietta_bgp:
            rip_redistribute.append("redistribute bgp")

    if has_ospf or has_rip:
        igp_nets = data.get('igp_networks') or default_igp_networks(rname, data)
        for lb in loopbacks:
            try:
                lb_ip = ipaddress.ip_interface(lb).ip
                if not any(lb_ip in ipaddress.ip_network(n, strict=False) for n in igp_nets):
                    igp_nets = igp_nets + [str(ipaddress.ip_interface(lb).network)]
            except ValueError:
                pass
        if has_ospf:
            parts.append(
                mk_ospf_stanza(
                    igp_nets,
                    area=data.get('ospf_area') or '0.0.0.0',
                    stub=bool(data.get('ospf_area_stub')),
                    redistribute=ospf_redistribute
                )
            )
        if has_rip:
            parts.append(mk_rip_stanza(igp_nets, redistribute=rip_redistribute))

    if "bgp" in data["protocols"]:
        parts.append(
            mk_bgp_stanza(
                data.get("asn", ""),
                networks=original_nets + list(data.get('bgp_extra_networks') or [])
            )
        )

    with open(os.path.join(etc_frr, "frr.conf"), 'w', encoding='utf-8', newline='\n') as f:
        f.write("\n".join(parts))

    ip_cfg_lines = [f"ip address add {iface['ip']} dev {iface['name']}" for iface in data["interfaces"]]
    for lb in loopbacks:
        ip_cfg_lines.append(f"ip address add {lb} dev lo")
    ip_cfg_lines.extend(static_route_lines(data))

    startup_path = os.path.join(base_path, f"{rname}.startup")
    with open(startup_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(STARTUP_ROUTER_TMPL.format(ip_config="\n".join(ip_cfg_lines)))
    try:
        os.chmod(startup_path, 0o755)
    except Exception:
        pass


def crea_host_file(base_path, hname, ip_cidr, gateway_cidr, lan):
    os.makedirs(base_path, exist_ok=True)
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
    """Crea lo startup di un host con una o più interfacce."""
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

    html_content = f"<html><head><title>{name}</title></head><body><h1>Server {name}</h1></body></html>"

    with open(index_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(html_content)
    startup_path = os.path.join(base_path, f"{name}.startup")
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
    return [
        '$TTL 60000',
        '@ IN SOA ROOT-SERVER. root.ROOT-SERVER. (',
        f'    {serial} ; serial',
        '    28800 ; refresh',
        '    14400 ; retry',
        '    3600000 ; expire',
        '    0 ; negative cache ttl',
        ')',
        ''
    ]


def _righe_delega(zone, ns, ip):
    """Delega di una zona dal root: '<zona>. NS <ns>.' + glue '<ns>. A <ip>'."""
    righe = [_rec_dns(zone, 'NS', ns)]
    if ip:
        righe.append(_rec_dns(ns, 'A', str(ip).split('/')[0]))
    return righe


def crea_dns_host(
    base_path, name, ip_cidr, gateway_cidr, lan,
    forwarders=None, zones=None, root_type=None, root_server_ip=None,
    allow_recursion=None, dnssec_validation=False, delegations=None
):
    """Crea la struttura di un Host DNS (BIND9) nella directory del lab."""
    bind_dir = os.path.join(base_path, name, 'etc', 'bind')
    os.makedirs(bind_dir, exist_ok=True)

    opts_lines = [
        'options {',
        '    directory "/var/cache/bind";',
    ]
    if forwarders:
        fw_items = ' '.join(f"{x};" for x in forwarders)
        opts_lines.append('    forwarders { ' + fw_items + ' };')
    if allow_recursion:
        opts_lines.append('    allow-recursion { ' + str(allow_recursion) + '; };')
    if dnssec_validation:
        opts_lines.append('    dnssec-validation no;')
    opts_lines.append('};')
    opts_content = "\n".join(opts_lines) + "\n"
    with open(os.path.join(bind_dir, 'named.conf.options'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(opts_content)

    def format_dns_record(rec_name, rtype, value, cls='IN', name_width=16):
        def _is_ip(s):
            try:
                ipaddress.ip_address(s)
                return True
            except Exception:
                return False

        if rec_name != '@' and isinstance(rec_name, str) and '.' in rec_name and not rec_name.endswith('.'):
            rec_name = rec_name + '.'

        if isinstance(rtype, str) and rtype.upper() in ('NS', 'CNAME', 'PTR'):
            if isinstance(value, str) and '.' in value and not value.endswith('.') and not _is_ip(value):
                value = value + '.'

        name_field = f"{rec_name:<{name_width}}"
        return f"{name_field}\t{cls}\t{rtype}\t{value}"

    host_ip = ip_cidr.split('/')[0] if ip_cidr else '127.0.0.1'
    if root_type == 'master':
        ip_root = host_ip
    elif root_type == 'hint' and root_server_ip:
        ip_root = root_server_ip
    else:
        ip_root = host_ip

    serial = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d') + '01'
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

    if zones:
        for zname, records in zones.items():
            if zname == '.':
                continue
            rev = '.'.join(zname.split('.')[::-1])
            zone_file_path = os.path.join(bind_dir, f"db.{rev}")
            serial_zone = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d') + '01'
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
            if isinstance(records, dict):
                for h, ipval in records.items():
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

    gateway = gateway_cidr.split('/')[0] if '/' in gateway_cidr else gateway_cidr
    startup = f"ip address add {ip_cidr} dev eth0\nip route add default via {gateway} dev eth0\nsystemctl start named\n"
    startup_path = os.path.join(base_path, f"{name}.startup")
    with open(startup_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(startup)
    try:
        os.chmod(startup_path, 0o755)
    except Exception:
        pass


def build_lab_conf_text(routers, hosts, wwws):
    """Ricostruisce il contenuto di lab.conf dai dati."""
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