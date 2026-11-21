"""
src/core/ops_api.py
API headless (senza input/print) per tutte le operazioni di creazione, importazione
e modifica dei laboratori Kathará. Usata dalla GUI web con anteprima diff,
delta dei controlli (topologia/configurazione) e backup automatico al commit.
"""
import datetime
import difflib
import ipaddress
import os
import re
import shutil
import tempfile

from .analyzer import (
    _analizza_frr,
    _problemi_di,
    _proprietari,
    collect_lab_ips,
    controlla_topologia,
    controlli_configurazione,
    generate_ping_oneliner,
    isole_ospf,
    leggi_dispositivi,
    riferimenti_frr,
)
from .cli_io import (
    area_valida,
    asn_valido,
    correggi_nome_kathara,
    nome_kathara_valido,
    parse_reti,
)
from .device_editor import (
    _correzione_suggerita,
    _file_modificabili,
    _ip_del_router,
    _membri_lan,
    _piano_sostituzioni,
    _rete_lan,
    _reti_da_controllare,
    _sostituzione_ip,
)
from .file_utils import (
    _append_righe,
    _cartella_copie,
    _comandi_nodo,
    _file_di_testo,
    _fine_blocco,
    _indici_nodo,
    _inizio_blocco,
    _inserisci_nel_blocco,
    _leggi_righe,
    _righe_file,
    _rimuovi_righe,
    _rimuovi_route_map,
    _scrivi_esatte,
    _scrivi_righe,
    _set_demone,
    copia_di_sicurezza,
    insert_lines_into_protocol_block,
)
from .generators import (
    _righe_delega,
    _soa_root,
    build_lab_conf_text,
    crea_dns_host,
    crea_host_multi,
    crea_router_files,
    crea_www_file,
)
from .net_frr import (
    _ip_verso,
    _neighbor_presente,
    _norm_net,
    _reti_peering,
    add_ibgp_loopback_neighbors,
    add_neighbor_if_missing,
    auto_generate_bgp_neighbors,
    default_bgp_aggregate,
    default_igp_networks,
    mk_bgp_stanza,
    mk_ospf_stanza,
    mk_rip_stanza,
    static_route_lines,
)
from .persistence import (
    correggi_nomi_importati,
    correggi_nomi_lab,
    export_lab_to_xml,
    load_lab_from_json,
    load_lab_from_xml,
    parse_lab_conf_for_nodes,
    rebuild_lab_metadata_and_export,
    recreate_lab_from_data,
)
from .templates import DAEMONS_TMPL, FRR_HEADER, VTYSH_TMPL, _RE_GW, _RE_IP_ADD, _RE_TOKEN_IP


class OpError(ValueError):
    """Errore di validazione o esecuzione di un'operazione headless."""


RE_LAB_NAME = re.compile(r'^[A-Za-z0-9_.-]+$')
RE_LAN_NAME = re.compile(r'^[A-Za-z0-9_]+$')


def _valida_nome_lab(nome):
    n = str(nome or '').strip()
    if not n or not RE_LAB_NAME.match(n) or n in ('.', '..'):
        raise OpError("Nome del laboratorio non valido (usa lettere, numeri, _ - .).")
    return n


def _valida_nome_dev(nome):
    n = str(nome or '').strip()
    if not nome_kathara_valido(n):
        prop = correggi_nome_kathara(n)
        raise OpError(
            f"Nome dispositivo '{n}' non valido per Kathará (solo lettere minuscole, cifre e _). "
            f"Suggerito: '{prop}'."
        )
    return n


def _valida_lan(lan):
    l = str(lan or '').strip()
    if not l or not RE_LAN_NAME.match(l):
        raise OpError(f"Nome LAN '{l}' non valido (usa lettere e numeri, es. A o A1).")
    return l


def _valida_ip_cidr(val, own=None, propri=()):
    s = str(val or '').strip()
    if '/' not in s:
        raise OpError(f"Manca la maschera CIDR in '{s}' (es. 10.0.0.1/24).")
    try:
        iface = ipaddress.ip_interface(s)
    except ValueError:
        raise OpError(f"IP/maschera non valido: '{s}'.")
    if iface.network.prefixlen < 31 and iface.ip in (
        iface.network.network_address,
        iface.network.broadcast_address,
    ):
        raise OpError(f"{iface.ip} è l'indirizzo di rete o di broadcast di {iface.network}.")
    if own is not None:
        chi = own.get(str(iface.ip))
        if chi and str(iface.ip) not in propri:
            raise OpError(f"IP {iface.ip} già usato da {chi[0]} ({chi[1]}).")
    return iface


def _valida_ip_solo(val):
    s = str(val or '').strip().split('/')[0]
    try:
        return str(ipaddress.ip_address(s))
    except ValueError:
        raise OpError(f"Indirizzo IP non valido: '{val}'.")


def _parse_lista_reti(val, opzionale=False):
    if isinstance(val, list):
        raw = ','.join(str(x).strip() for x in val if str(x).strip())
    else:
        raw = str(val or '').strip()
    if not raw:
        if opzionale:
            return []
        raise OpError("Inserisci almeno una rete CIDR (es. 10.0.0.0/24).")
    try:
        return parse_reti(raw)
    except ValueError as e:
        raise OpError(f"Rete non valida: {e}")


def _routers_from_disk(lab_path):
    disp = leggi_dispositivi(lab_path)
    routers = {}
    for nome, d in disp.items():
        if d['tipo'] != 'router':
            continue
        protos = []
        if 'bgpd' in d['demoni']:
            protos.append('bgp')
        if 'ospfd' in d['demoni']:
            protos.append('ospf')
        if 'ripd' in d['demoni']:
            protos.append('rip')
        if not protos:
            protos.append('statico')
        ifaces = [
            {'name': it['dev'], 'lan': it['lan'], 'ip': it['ip']}
            for it in d['interfacce']
        ]
        routers[nome] = {
            'protocols': protos,
            'asn': d['asn'] or '',
            'interfaces': ifaces,
            'loopbacks': list(d['loopback']),
        }
    return routers


def _collega_neighbor_silenzioso(fpath, ip, tipo, nome, direz, note):
    vecchie = [
        l for l in _leggi_righe(fpath)
        if re.match(rf"\s*neighbor {re.escape(ip)} {tipo} (\S+) {direz}\s*$", l)
        and l.split()[3] != nome
    ]
    for v in vecchie:
        note.append(
            f"{ip} aveva già '{v.strip()}': FRR usa una sola {tipo} per direzione, sostituita con {nome}."
        )
    if vecchie:
        _rimuovi_righe(fpath, lambda l: l in vecchie)
    riga = f"neighbor {ip} {tipo} {nome} {direz}"
    if not any(l.strip() == riga for l in _leggi_righe(fpath)):
        insert_lines_into_protocol_block(fpath, proto='bgp', asn=None, lines=[riga])


def _scrivi_route_map_silenziosa(fpath, rm_name, stanza, note, pl_name=None):
    if any(l.strip().startswith(f"route-map {rm_name} ") for l in _leggi_righe(fpath)):
        note.append(f"La route-map {rm_name} esisteva già ed è stata aggiornata.")
        _rimuovi_route_map(fpath, rm_name)
    if pl_name:
        _rimuovi_righe(fpath, lambda l: l.strip().startswith(f"ip prefix-list {pl_name} "))
    _append_righe(fpath, stanza)


def _append_lab_conf_block(lab_path, lines):
    lc = os.path.join(lab_path, 'lab.conf')
    cur = _righe_file(lc) if os.path.exists(lc) else []
    while cur and not cur[-1].strip():
        cur.pop()
    if cur:
        cur.append('')
    cur.extend(lines)
    _scrivi_esatte(lc, cur)


def _sync_xml_if_present(lab_path):
    nome = os.path.basename(os.path.normpath(lab_path))
    xmlp = os.path.join(lab_path, f"{nome}.xml")
    if os.path.exists(xmlp):
        try:
            rebuild_lab_metadata_and_export(lab_path)
        except Exception:
            pass


def _snapshot_files(lab_path):
    if not os.path.isdir(lab_path):
        return {}
    snap = {}
    for rel in _file_di_testo(lab_path):
        key = rel.replace(os.sep, '/')
        snap[key] = _righe_file(os.path.join(lab_path, rel))
    return snap


def _build_diff(before, after, context=3):
    files = sorted(set(before.keys()) | set(after.keys()))
    out = []
    for f in files:
        a = before.get(f)
        b = after.get(f)
        if a == b:
            continue
        if a is None:
            stato = 'creato'
            righe = [{'tipo': 'add', 'n1': None, 'n2': i + 1, 'testo': l} for i, l in enumerate(b)]
        elif b is None:
            stato = 'eliminato'
            righe = [{'tipo': 'del', 'n1': i + 1, 'n2': None, 'testo': l} for i, l in enumerate(a)]
        else:
            stato = 'modificato'
            righe = []
            sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
            for grp in sm.get_grouped_opcodes(context):
                if righe:
                    righe.append({'tipo': 'sep', 'n1': None, 'n2': None, 'testo': '···'})
                for tag, i1, i2, j1, j2 in grp:
                    if tag == 'equal':
                        for k in range(i2 - i1):
                            righe.append({'tipo': 'eq', 'n1': i1 + k + 1, 'n2': j1 + k + 1, 'testo': a[i1 + k]})
                    else:
                        for k in range(i1, i2):
                            righe.append({'tipo': 'del', 'n1': k + 1, 'n2': None, 'testo': a[k]})
                        for k in range(j1, j2):
                            righe.append({'tipo': 'add', 'n1': None, 'n2': k + 1, 'testo': b[k]})
        out.append({'file': f, 'stato': stato, 'righe': righe})
    return out


def _avvisi_set(lab_path):
    if not os.path.isfile(os.path.join(lab_path, 'lab.conf')):
        return set()
    return set(controlla_topologia(lab_path)) | set(controlli_configurazione(lab_path))



def _policy_refs_in_line(line):
    """Estrae eventuali (tipo, nome) di policy referenziati su una riga neighbor."""
    s = ' '.join(line.split())
    m = re.match(r'neighbor\s+\S+\s+(prefix-list|route-map|distribute-list)\s+(\S+)\s+(in|out)\b', s)
    if m:
        tipo = 'access-list' if m.group(1) == 'distribute-list' else m.group(1)
        return [(tipo, m.group(2))]
    m2 = re.match(r'neighbor\s+\S+\s+default-originate\s+route-map\s+(\S+)\b', s)
    if m2:
        return [('route-map', m2.group(1))]
    return []


def _pulisci_policy_orfane_frr(righe, candidati):
    """Rimuove route-map/prefix-list/access-list candidate che non risultano più usate in frr.conf."""
    if not candidati:
        return righe, []
    out = list(righe)
    rimossi = []
    coda = list(dict.fromkeys(candidati))

    while coda:
        tipo, nome = coda.pop(0)
        if (tipo, nome) in rimossi:
            continue
        # Controlla se è ancora usata altrove nel file
        usata = False
        for l in out:
            s = ' '.join(l.split())
            if tipo == 'route-map':
                if re.search(rf'\broute-map\s+{re.escape(nome)}\b', s) and not s.startswith(f'route-map {nome} '):
                    usata = True
                    break
            elif tipo == 'prefix-list':
                if (
                    re.search(rf'\bprefix-list\s+{re.escape(nome)}\b', s)
                    and not s.startswith(f'ip prefix-list {nome} ')
                    and not s.startswith(f'ipv6 prefix-list {nome} ')
                ):
                    usata = True
                    break
            elif tipo == 'access-list':
                if (
                    (re.search(rf'\bdistribute-list\s+{re.escape(nome)}\b', s)
                     or re.search(rf'\bmatch\s+ip\s+address\s+{re.escape(nome)}\b', s))
                    and not re.match(rf'(?:ip\s+)?access-list\s+{re.escape(nome)}\b', s)
                ):
                    usata = True
                    break
        if usata:
            continue

        nuove = []
        if tipo == 'route-map':
            dentro = False
            for l in out:
                s = ' '.join(l.split())
                if s.startswith(f'route-map {nome} '):
                    dentro = True
                    continue
                if dentro and re.match(r'(match|set|on-match|call|continue)\b', s):
                    mp = re.match(r'match\s+ip\s+address\s+prefix-list\s+(\S+)', s)
                    if mp:
                        coda.append(('prefix-list', mp.group(1)))
                    ma = re.match(r'match\s+ip\s+address\s+(?!prefix-list\b)(\S+)', s)
                    if ma:
                        coda.append(('access-list', ma.group(1)))
                    continue
                dentro = False
                nuove.append(l)
        elif tipo == 'prefix-list':
            rx_pl = re.compile(rf'^\s*ip(?:v6)?\s+prefix-list\s+{re.escape(nome)}\b')
            nuove = [l for l in out if not rx_pl.match(l)]
        elif tipo == 'access-list':
            rx_al = re.compile(rf'^\s*(?:ip\s+)?access-list\s+{re.escape(nome)}\b')
            nuove = [l for l in out if not rx_al.match(l)]
        else:
            nuove = out

        if nuove != out:
            out = nuove
            rimossi.append((tipo, nome))

    return out, rimossi


def _pulisci_riferimenti_ip(lab_path, ips_rimossi, note, escludi_dev=None, descrizione=''):
    """Rimuove riferimenti a IP eliminati in tutto il lab: neighbor BGP + policy orfane,
    rotte statiche/gateway in .startup e frr.conf, nameserver in resolv.conf e record A DNS."""
    ips = {str(ip).split('/')[0].strip() for ip in (ips_rimossi or []) if str(ip).strip()}
    if not ips:
        return
    disp = leggi_dispositivi(lab_path)
    tag = f" ({descrizione})" if descrizione else ""

    for n2, d2 in sorted(disp.items()):
        if n2 == escludi_dev:
            continue

        # 1. frr.conf: neighbor <ip>, ip route ... <ip>, e policy orfane collegate
        if d2['frr']:
            f2 = os.path.join(lab_path, n2, 'etc', 'frr', 'frr.conf')
            if os.path.exists(f2):
                v = _righe_file(f2)
                nu = []
                cand_pol = []
                rm_nb = False
                for l in v:
                    s = ' '.join(l.split())
                    mnb = re.match(r'neighbor\s+(\S+)\s', s)
                    if mnb and mnb.group(1) in ips:
                        cand_pol.extend(_policy_refs_in_line(l))
                        rm_nb = True
                        continue
                    msr = re.match(r'ip\s+route\s+\S+\s+(\S+)', s)
                    if msr and msr.group(1) in ips:
                        continue
                    nu.append(l)
                if cand_pol:
                    nu, pol_rm = _pulisci_policy_orfane_frr(nu, cand_pol)
                else:
                    pol_rm = []
                if nu != v:
                    _scrivi_righe(f2, nu)
                    extra = f" + policy orfane ({', '.join(x[1] for x in pol_rm)})" if pol_rm else ""
                    if rm_nb:
                        note.append(f"Rimossi riferimenti neighbor{tag} da {n2}/etc/frr/frr.conf{extra}.")
                    else:
                        note.append(f"Rimosse rotte statiche verso IP eliminati{tag} in {n2}/etc/frr/frr.conf.")

        # 2. .startup: default gateway e rotte statiche verso IP eliminati
        st2 = os.path.join(lab_path, f"{n2}.startup")
        if os.path.exists(st2):
            v = _righe_file(st2)
            nu = []
            for l in v:
                mgw = _RE_GW.match(l)
                if mgw and (mgw.group(1) or mgw.group(2)).split('/')[0] in ips:
                    continue
                msr = re.match(r'^\s*ip\s+route\s+add\s+\S+\s+via\s+(\S+)', l)
                if msr and msr.group(1).split('/')[0] in ips:
                    continue
                nu.append(l)
            if nu != v:
                _scrivi_esatte(st2, nu)
                note.append(f"Rimosso gateway/rotta statica verso IP eliminato{tag} in {n2}.startup.")

        # 3. resolv.conf: nameserver <ip>
        res2 = os.path.join(lab_path, n2, 'etc', 'resolv.conf')
        if os.path.exists(res2):
            v = _righe_file(res2)
            nu = [l for l in v if not (re.match(r'^\s*nameserver\s+(\S+)', l) and l.split()[1] in ips)]
            if nu != v:
                if any(x.strip() for x in nu):
                    _scrivi_esatte(res2, nu)
                else:
                    os.remove(res2)
                note.append(f"Rimosso nameserver eliminato{tag} da {n2}/etc/resolv.conf.")

        # 4. DNS zone files: record A verso IP eliminati
        bind_dir = os.path.join(lab_path, n2, 'etc', 'bind')
        if os.path.isdir(bind_dir):
            for fn in sorted(os.listdir(bind_dir)):
                if not fn.startswith('db.'):
                    continue
                fp = os.path.join(bind_dir, fn)
                v = _righe_file(fp)
                nu = []
                for l in v:
                    code_part = l.split(';', 1)[0].strip()
                    toks = code_part.split()
                    if len(toks) >= 2 and 'A' in [t.upper() for t in toks[:-1]] and toks[-1] in ips:
                        continue
                    nu.append(l)
                if nu != v:
                    _scrivi_esatte(fp, nu)
                    note.append(f"Rimossi record A verso IP eliminato{tag} in {n2}/etc/bind/{fn}.")


def _rimuovi_blocco_interfaccia_frr(righe, dev):
    """Rimuove un blocco 'interface <dev>' da frr.conf (es. costi OSPF)."""
    out, i = [], 0
    rx = re.compile(rf'^\s*interface\s+{re.escape(dev)}\s*$')
    while i < len(righe):
        if rx.match(righe[i]):
            i = _fine_blocco(righe, i)
            continue
        out.append(righe[i])
        i += 1
    return out


def _rimuovi_network_frr(righe, nets, protos=('bgp', 'ospf', 'rip')):
    """Rimuove 'network <net>' dai blocchi router specificati in frr.conf."""
    bersagli = {_norm_net(x) for x in nets if x}
    if not bersagli:
        return righe
    out, cur = [], None
    for l in righe:
        s = ' '.join(l.split())
        m = re.match(r'router\s+(bgp|ospf|rip)\b', s)
        if m:
            cur = m.group(1)
        elif l and not l[0].isspace() and not s.startswith('!'):
            cur = None
        elif cur in protos and s.startswith('network '):
            toks = s.split()
            if len(toks) >= 2 and _norm_net(toks[1]) in bersagli:
                continue
        out.append(l)
    return out


def _rinomina_interfacce_dispositivo(lab_path, nome, old_to_new, note):
    """Rinomina in sicurezza (due passaggi) le interfacce ethX -> ethY di `nome`
    su lab.conf, <nome>.startup e <nome>/etc/frr/frr.conf."""
    mappa = {k: v for k, v in old_to_new.items() if k != v}
    if not mappa:
        return

    # 1. lab.conf: riscrive le righe nome[idx]=LAN secondo i nuovi indici
    lc = os.path.join(lab_path, 'lab.conf')
    righe_lc = _righe_file(lc)
    rx_if = re.compile(rf'^(\s*{re.escape(nome)}\s*\[\s*)(\d+)(\s*\]\s*=\s*.+)$')
    rx_any = re.compile(rf'^\s*{re.escape(nome)}\s*\[')

    idx_map = {int(k[3:]): int(v[3:]) for k, v in old_to_new.items() if k.startswith('eth') and v.startswith('eth')}
    righe_if = []
    altre_dev = []
    prima_pos = None
    resto = []
    for l in righe_lc:
        mif = rx_if.match(l)
        if mif:
            if prima_pos is None:
                prima_pos = len(resto)
            old_i = int(mif.group(2))
            new_i = idx_map.get(old_i, old_i)
            righe_if.append((new_i, f"{mif.group(1)}{new_i}{mif.group(3)}"))
        elif rx_any.match(l):
            if prima_pos is None:
                prima_pos = len(resto)
            altre_dev.append(l)
        else:
            resto.append(l)
    righe_if.sort(key=lambda x: x[0])
    blocco_dev = [x[1] for x in righe_if] + altre_dev
    if prima_pos is None:
        nuove_lc = resto + blocco_dev
    else:
        nuove_lc = resto[:prima_pos] + blocco_dev + resto[prima_pos:]
    if nuove_lc != righe_lc:
        _scrivi_esatte(lc, nuove_lc)

    # Helper sostituzione a 2 passaggi per evitare collisioni durante gli swap (es. eth1 <-> eth2)
    def _sub_two_pass(text):
        tmp_map = {k: f"__TMP_IFACE_{i}__" for i, k in enumerate(mappa)}
        t = text
        for old_d, tok in tmp_map.items():
            t = re.sub(rf'(?<![A-Za-z0-9_]){re.escape(old_d)}(?![A-Za-z0-9_])', tok, t)
        for old_d, tok in tmp_map.items():
            t = t.replace(tok, mappa[old_d])
        return t

    # 2. <nome>.startup
    st = os.path.join(lab_path, f"{nome}.startup")
    if os.path.exists(st):
        v = _righe_file(st)
        nu = [_sub_two_pass(l) for l in v]
        # Riordina le righe 'ip address add ... dev ethN' per indice crescente
        ip_rows, other_rows, first_ip = [], [], None
        for l in nu:
            mip = _RE_IP_ADD.match(l)
            if mip and mip.group(2).startswith('eth') and mip.group(2)[3:].isdigit():
                if first_ip is None:
                    first_ip = len(other_rows)
                ip_rows.append((int(mip.group(2)[3:]), l))
            else:
                other_rows.append(l)
        if ip_rows:
            ip_rows.sort(key=lambda x: x[0])
            nu = other_rows[:first_ip] + [x[1] for x in ip_rows] + other_rows[first_ip:]
        if nu != v:
            _scrivi_esatte(st, nu)

    # 3. <nome>/etc/frr/frr.conf
    frr = os.path.join(lab_path, nome, 'etc', 'frr', 'frr.conf')
    if os.path.exists(frr):
        v = _righe_file(frr)
        nu = [_sub_two_pass(l) for l in v]
        if nu != v:
            _scrivi_esatte(frr, nu)


def _propaga_rete_in_policy(lab_path, old_net, new_net, note, origine_router=None):
    """Aggiorna riferimenti a old_net -> new_net in prefix-list/access-list dei router del lab."""
    if not old_net or not new_net or old_net == new_net:
        return
    disp = leggi_dispositivi(lab_path)
    # Verifica se old_net è ancora una subnet di qualche interfaccia o annunciata altrove
    ancora_usata = False
    for n, d in disp.items():
        if n == origine_router:
            continue
        for it in d['interfacce']:
            if it['ip'] and _norm_net(it['ip']) == old_net:
                ancora_usata = True
                break
        if d['frr']:
            cfg = _analizza_frr(_leggi_righe(os.path.join(lab_path, n, 'etc', 'frr', 'frr.conf')))
            if any(_norm_net(x) == old_net for x in cfg.get('bgp_networks', [])):
                ancora_usata = True
    f = _sostituzione_ip({}, {}, {old_net: new_net})
    for n, d in sorted(disp.items()):
        if not d['frr']:
            continue
        if ancora_usata and n != origine_router:
            continue
        fp = os.path.join(lab_path, n, 'etc', 'frr', 'frr.conf')
        v = _righe_file(fp)
        nu = []
        for l in v:
            s = ' '.join(l.split())
            if re.match(r'(ip(?:v6)?\s+prefix-list|(?:ip\s+)?access-list)\s+', s):
                nu.append(f(l))
            else:
                nu.append(l)
        if nu != v:
            _scrivi_esatte(fp, nu)
            note.append(f"Aggiornati riferimenti policy ({old_net} → {new_net}) in {n}/etc/frr/frr.conf.")


def _op_add_router(lab_path, p, note):
    disp = leggi_dispositivi(lab_path) if os.path.isfile(os.path.join(lab_path, 'lab.conf')) else {}
    own = _proprietari(disp)
    nome = _valida_nome_dev(p.get('nome'))
    if nome in disp:
        raise OpError(f"Esiste già un dispositivo chiamato '{nome}'.")

    protos = [str(x).strip().lower() for x in (p.get('protocols') or []) if str(x).strip()]
    valid_p = {'bgp', 'ospf', 'rip', 'statico'}
    if not protos or any(x not in valid_p for x in protos):
        raise OpError("Seleziona almeno un protocollo valido (bgp, ospf, rip, statico).")

    asn = ''
    if 'bgp' in protos:
        asn = str(p.get('asn') or '').strip()
        if not asn_valido(asn):
            raise OpError("Numero AS non valido (solo cifre, es. 10).")

    ospf_area = '0.0.0.0'
    ospf_stub = False
    if 'ospf' in protos:
        ospf_area = str(p.get('ospf_area') or '0.0.0.0').strip()
        if not area_valida(ospf_area):
            raise OpError(f"Area OSPF non valida: '{ospf_area}' (es. 0.0.0.0 oppure 1).")
        ospf_stub = bool(p.get('ospf_area_stub')) and ospf_area not in ('0', '0.0.0.0')

    raw_ifaces = p.get('interfaces') or []
    if not raw_ifaces:
        raise OpError("Un router deve avere almeno una interfaccia.")
    ifaces = []
    local_ips = set()
    for idx, it in enumerate(raw_ifaces):
        lan = _valida_lan(it.get('lan'))
        ip_obj = _valida_ip_cidr(it.get('ip'), own=own)
        if str(ip_obj.ip) in local_ips:
            raise OpError(f"IP duplicato {ip_obj.ip} sullo stesso router.")
        local_ips.add(str(ip_obj.ip))
        ifaces.append({'name': f"eth{idx}", 'lan': lan, 'ip': str(ip_obj)})

    loopbacks = []
    for lb in (p.get('loopbacks') or []):
        s = str(lb).strip()
        if not s:
            continue
        if '/' not in s:
            s = s + '/32'
        ip_obj = _valida_ip_cidr(s, own=own)
        if str(ip_obj.ip) in local_ips:
            raise OpError(f"Loopback {ip_obj.ip} duplicata.")
        local_ips.add(str(ip_obj.ip))
        loopbacks.append(str(ip_obj))

    static_routes = []
    for sr in (p.get('static_routes') or []):
        dest = str(sr.get('dest') or '').strip()
        via = str(sr.get('via') or '').strip()
        if not dest and not via:
            continue
        if dest != 'default':
            try:
                dest = str(ipaddress.ip_network(dest, strict=False))
            except ValueError:
                raise OpError(f"Destinazione rotta statica non valida: '{dest}'.")
        via = _valida_ip_solo(via)
        dev = str(sr.get('dev') or '').strip()
        static_routes.append({'dest': dest, 'via': via, 'dev': dev})

    rdata = {
        'protocols': protos,
        'asn': asn,
        'interfaces': ifaces,
        'loopbacks': loopbacks,
        'ospf_area': ospf_area,
        'ospf_area_stub': ospf_stub,
        'igp_redistribute_bgp': bool(p.get('igp_redistribute_bgp', True)),
        'static_routes': static_routes,
    }

    if p.get('igp_networks'):
        rdata['igp_networks'] = _parse_lista_reti(p['igp_networks'], opzionale=True)
    if p.get('bgp_extra_networks'):
        rdata['bgp_extra_networks'] = _parse_lista_reti(p['bgp_extra_networks'], opzionale=True)

    crea_router_files(lab_path, nome, rdata, interactive=False)

    lc_lines = [f"{nome}[{i}]={it['lan']}" for i, it in enumerate(ifaces)]
    if any(x in protos for x in ('bgp', 'ospf', 'rip')):
        lc_lines.append(f'{nome}[image]="kathara/frr"')
    else:
        lc_lines.append(f'{nome}[image]="kathara/base"')
    _append_lab_conf_block(lab_path, lc_lines)

    if 'bgp' in protos and p.get('auto_bgp_neighbors', True):
        routers_all = _routers_from_disk(lab_path)
        auto_generate_bgp_neighbors(lab_path, routers_all)
        note.append("Sessioni BGP verso router BGP adiacenti sulle stesse LAN create automaticamente.")

    if loopbacks and 'bgp' in protos:
        try:
            add_ibgp_loopback_neighbors(lab_path, _routers_from_disk(lab_path))
        except Exception:
            pass

    return f"Aggiungi router {nome}"


def _op_add_host(lab_path, p, note):
    disp = leggi_dispositivi(lab_path) if os.path.isfile(os.path.join(lab_path, 'lab.conf')) else {}
    own = _proprietari(disp)
    nome = _valida_nome_dev(p.get('nome'))
    if nome in disp:
        raise OpError(f"Esiste già un dispositivo chiamato '{nome}'.")
    raw_ifaces = p.get('interfaces') or []
    if not raw_ifaces:
        raise OpError("L'host deve avere almeno una interfaccia.")
    ifaces = []
    local_ips = set()
    for idx, it in enumerate(raw_ifaces):
        lan = _valida_lan(it.get('lan'))
        ip_obj = _valida_ip_cidr(it.get('ip'), own=own)
        if str(ip_obj.ip) in local_ips:
            raise OpError(f"IP duplicato {ip_obj.ip} sullo stesso host.")
        local_ips.add(str(ip_obj.ip))
        ifaces.append({'name': f"eth{idx}", 'lan': lan, 'ip': str(ip_obj)})

    gw = str(p.get('gateway') or '').strip()
    gw_dev = str(p.get('gw_dev') or '').strip()
    if gw:
        gw = _valida_ip_solo(gw)
        if not gw_dev:
            gw_dev = next(
                (it['name'] for it in ifaces if ipaddress.ip_address(gw) in ipaddress.ip_interface(it['ip']).network),
                ifaces[0]['name'],
            )
        if not any(ipaddress.ip_address(gw) in ipaddress.ip_interface(it['ip']).network for it in ifaces):
            note.append(f"Il gateway {gw} non appartiene alla subnet di nessuna interfaccia di {nome}.")

    crea_host_multi(lab_path, nome, ifaces, gateway=gw or None, gw_dev=gw_dev or 'eth0')
    lc_lines = [f"{nome}[{i}]={it['lan']}" for i, it in enumerate(ifaces)]
    lc_lines.append(f'{nome}[image]="kathara/base"')
    _append_lab_conf_block(lab_path, lc_lines)

    res = str(p.get('resolver') or '').strip()
    if res:
        res_ip = _valida_ip_solo(res)
        os.makedirs(os.path.join(lab_path, nome, 'etc'), exist_ok=True)
        _scrivi_esatte(os.path.join(lab_path, nome, 'etc', 'resolv.conf'), [f"nameserver {res_ip}"])

    return f"Aggiungi host {nome}"


def _op_add_www(lab_path, p, note):
    disp = leggi_dispositivi(lab_path) if os.path.isfile(os.path.join(lab_path, 'lab.conf')) else {}
    own = _proprietari(disp)
    nome = _valida_nome_dev(p.get('nome'))
    if nome in disp:
        raise OpError(f"Esiste già un dispositivo chiamato '{nome}'.")
    lan = _valida_lan(p.get('lan'))
    ip_obj = _valida_ip_cidr(p.get('ip'), own=own)
    gw = _valida_ip_solo(p.get('gateway'))
    if ipaddress.ip_address(gw) not in ip_obj.network:
        note.append(f"Il gateway {gw} non appartiene alla subnet {ip_obj.network}.")
    crea_www_file(lab_path, nome, str(ip_obj), gw, lan)
    _append_lab_conf_block(lab_path, [f"{nome}[0]={lan}", f'{nome}[image]="kathara/base"'])

    res = str(p.get('resolver') or '').strip()
    if res:
        res_ip = _valida_ip_solo(res)
        os.makedirs(os.path.join(lab_path, nome, 'etc'), exist_ok=True)
        _scrivi_esatte(os.path.join(lab_path, nome, 'etc', 'resolv.conf'), [f"nameserver {res_ip}"])

    return f"Aggiungi server WWW {nome}"


def _op_add_dns(lab_path, p, note):
    disp = leggi_dispositivi(lab_path) if os.path.isfile(os.path.join(lab_path, 'lab.conf')) else {}
    own = _proprietari(disp)
    nome = _valida_nome_dev(p.get('nome'))
    if nome in disp:
        raise OpError(f"Esiste già un dispositivo chiamato '{nome}'.")
    lan = _valida_lan(p.get('lan'))
    ip_obj = _valida_ip_cidr(p.get('ip'), own=own)
    gw = _valida_ip_solo(p.get('gateway'))
    if ipaddress.ip_address(gw) not in ip_obj.network:
        note.append(f"Il gateway {gw} non appartiene alla subnet {ip_obj.network}.")

    root_type = str(p.get('root_type') or 'hint').strip().lower()
    if root_type not in ('master', 'hint', 'none'):
        raise OpError("root_type deve essere 'master', 'hint' oppure 'none'.")
    root_server_ip = str(p.get('root_server_ip') or '').strip()
    if root_type == 'hint':
        if not root_server_ip:
            for dn, dd in disp.items():
                if dd['tipo'] == 'dns' and any(z['zona'] == '.' and z['tipo'] == 'master' for z in dd.get('zone', [])):
                    if dd['interfacce'] and dd['interfacce'][0]['ip']:
                        root_server_ip = dd['interfacce'][0]['ip'].split('/')[0]
                        break
        if root_server_ip:
            root_server_ip = _valida_ip_solo(root_server_ip)

    delegations = []
    for d in (p.get('delegations') or []):
        z = str(d.get('zone') or '').strip().strip('.')
        ns = str(d.get('ns') or '').strip().rstrip('.')
        dip = str(d.get('ip') or '').strip()
        if z and ns:
            delegations.append({'zone': z, 'ns': ns, 'ip': _valida_ip_solo(dip) if dip else ''})

    zones = {}
    for z in (p.get('zones') or []):
        zname = str(z.get('zone') or '').strip().strip('.')
        if not zname:
            continue
        recs = {}
        for r in (z.get('records') or []):
            rname = str(r.get('name') or '').strip()
            rtype = str(r.get('type') or 'A').strip().upper()
            rval = str(r.get('value') or '').strip()
            rextra = str(r.get('extra') or '').strip()
            if not rname or not rval:
                continue
            if rtype == 'A':
                recs[rname] = {'type': 'A', 'ip': _valida_ip_solo(rval)}
            elif rtype == 'NS':
                recs[rname] = {'type': 'NS', 'ns': rval, 'glue': _valida_ip_solo(rextra) if rextra else ''}
            elif rtype == 'CNAME':
                recs[rname] = {'type': 'CNAME', 'target': rval}
            elif rtype == 'DELEGATION':
                recs[rname] = {'type': 'DELEGATION', 'zone': rname, 'ns': rval, 'ns_ip': _valida_ip_solo(rextra) if rextra else ''}
        zones[zname] = recs

    allow_rec = str(p.get('allow_recursion') or '').strip() or None
    dnssec_no = bool(p.get('dnssec_validation', True))

    crea_dns_host(
        lab_path, nome, str(ip_obj), gw, lan,
        zones=zones or None,
        root_type=root_type if root_type != 'none' else None,
        root_server_ip=root_server_ip or None,
        allow_recursion=allow_rec,
        dnssec_validation=dnssec_no,
        delegations=delegations or None,
    )
    _append_lab_conf_block(lab_path, [f"{nome}[0]={lan}", f'{nome}[image]="kathara/base"'])

    for target in (p.get('set_as_resolver_for') or []):
        if target in disp:
            os.makedirs(os.path.join(lab_path, target, 'etc'), exist_ok=True)
            _scrivi_esatte(
                os.path.join(lab_path, target, 'etc', 'resolv.conf'),
                [f"nameserver {ip_obj.ip}"],
            )

    return f"Aggiungi server DNS {nome}"


def _op_delete_device(lab_path, p, note):
    disp = leggi_dispositivi(lab_path)
    nome = str(p.get('nome') or '').strip()
    if nome not in disp:
        raise OpError(f"Dispositivo '{nome}' non trovato.")
    d = disp[nome]

    lc = os.path.join(lab_path, 'lab.conf')
    vecchie = _righe_file(lc)
    rx = re.compile(rf'^\s*{re.escape(nome)}\s*\[')
    _scrivi_righe(lc, [l for l in vecchie if not rx.match(l)])

    st = os.path.join(lab_path, f"{nome}.startup")
    if os.path.exists(st):
        os.remove(st)
    ddir = os.path.join(lab_path, nome)
    if os.path.isdir(ddir):
        shutil.rmtree(ddir)

    if p.get('clean_neighbors', True):
        miei = _ip_del_router(d)
        _pulisci_riferimenti_ip(lab_path, miei, note, escludi_dev=nome, descrizione=f"dispositivo {nome} eliminato")

    return f"Elimina dispositivo {nome}"


def _op_add_interface(lab_path, p, note):
    disp = leggi_dispositivi(lab_path)
    own = _proprietari(disp)
    nome = str(p.get('nome') or '').strip()
    if nome not in disp:
        raise OpError(f"Dispositivo '{nome}' non trovato.")
    d = disp[nome]
    lan = _valida_lan(p.get('lan'))
    ip_obj = _valida_ip_cidr(p.get('ip'), own=own)

    used_idx = {it['idx'] for it in d['interfacce']}
    idx = 0
    while idx in used_idx:
        idx += 1
    dev = f"eth{idx}"

    lc = os.path.join(lab_path, 'lab.conf')
    righe = _righe_file(lc)
    rx = re.compile(rf'^\s*{re.escape(nome)}\s*\[')
    last = max((k for k, l in enumerate(righe) if rx.match(l)), default=len(righe) - 1)
    righe.insert(last + 1, f"{nome}[{idx}]={lan}")
    _scrivi_esatte(lc, righe)

    st = os.path.join(lab_path, f"{nome}.startup")
    sr = _righe_file(st) if os.path.exists(st) else []
    ip_line = f"ip address add {ip_obj} dev {dev}"
    ins = next(
        (k for k, l in enumerate(sr) if re.match(r'^\s*(systemctl|ip\s+route|route\s+add)\b', l)),
        len(sr),
    )
    sr.insert(ins, ip_line)
    _scrivi_esatte(st, sr)
    try:
        os.chmod(st, 0o755)
    except Exception:
        pass

    frr = os.path.join(lab_path, nome, 'etc', 'frr', 'frr.conf')
    if d['tipo'] == 'router' and os.path.exists(frr):
        net_s = str(ip_obj.network)
        if p.get('announce_bgp') and 'bgpd' in d['demoni']:
            insert_lines_into_protocol_block(frr, proto='bgp', lines=[f"network {net_s}"])
        if p.get('announce_igp'):
            if 'ospfd' in d['demoni']:
                area = str(p.get('ospf_area') or '0.0.0.0').strip()
                insert_lines_into_protocol_block(frr, proto='ospf', lines=[f"network {net_s} area {area}"])
            if 'ripd' in d['demoni']:
                insert_lines_into_protocol_block(frr, proto='rip', lines=[f"network {net_s}"])
        if p.get('auto_bgp_neighbors', True) and 'bgpd' in d['demoni']:
            auto_generate_bgp_neighbors(lab_path, _routers_from_disk(lab_path))

    return f"Aggiungi interfaccia {dev} ({ip_obj}, LAN {lan}) a {nome}"


def _op_remove_interface(lab_path, p, note):
    disp = leggi_dispositivi(lab_path)
    nome = str(p.get('nome') or '').strip()
    dev = str(p.get('dev') or '').strip()
    if nome not in disp:
        raise OpError(f"Dispositivo '{nome}' non trovato.")
    d = disp[nome]
    it = next((x for x in d['interfacce'] if x['dev'] == dev), None)
    if not it:
        raise OpError(f"Interfaccia '{dev}' non trovata su {nome}.")

    lc = os.path.join(lab_path, 'lab.conf')
    rx = re.compile(rf'^\s*{re.escape(nome)}\s*\[\s*{it["idx"]}\s*\]\s*=')
    _scrivi_esatte(lc, [l for l in _righe_file(lc) if not rx.match(l)])

    st = os.path.join(lab_path, f"{nome}.startup")
    if os.path.exists(st):
        rx_st = re.compile(rf'^\s*ip\s+a(?:ddr(?:ess)?)?\s+add\s+\S+\s+dev\s+{re.escape(dev)}\b')
        rx_rt = re.compile(rf'^\s*ip\s+route\s+add\s+.*\bdev\s+{re.escape(dev)}\b')
        _scrivi_esatte(st, [l for l in _righe_file(st) if not rx_st.match(l) and not rx_rt.match(l)])

    old_ip_str = it['ip']
    old_ip_only = old_ip_str.split('/')[0] if old_ip_str else ''
    old_net = _norm_net(old_ip_str) if old_ip_str else ''

    # Pulisce frr.conf locale: stanza interface <dev>, network orfana e neighbor verso peer solo su quella LAN
    if d['frr']:
        frr = os.path.join(lab_path, nome, 'etc', 'frr', 'frr.conf')
        if os.path.exists(frr):
            v = _righe_file(frr)
            nu = _rimuovi_blocco_interfaccia_frr(v, dev)
            altre_mie_stessa_net = any(
                x['dev'] != dev and x['ip'] and _norm_net(x['ip']) == old_net
                for x in d['interfacce']
            )
            if old_net and not altre_mie_stessa_net:
                nu = _rimuovi_network_frr(nu, [old_net])
            # Rimuovi neighbor locali verso IP su questa LAN se non condividono altre LAN con nome
            if old_net:
                try:
                    net_obj = ipaddress.ip_network(old_net, strict=False)
                except ValueError:
                    net_obj = None
                if net_obj:
                    cand_pol = []
                    nu2 = []
                    for l in nu:
                        s = ' '.join(l.split())
                        mnb = re.match(r'neighbor\s+(\S+)\s', s)
                        if mnb:
                            try:
                                if ipaddress.ip_address(mnb.group(1)) in net_obj:
                                    cand_pol.extend(_policy_refs_in_line(l))
                                    continue
                            except ValueError:
                                pass
                        nu2.append(l)
                    nu, _ = _pulisci_policy_orfane_frr(nu2, cand_pol)
            if nu != v:
                _scrivi_righe(frr, nu)

    if old_ip_only:
        _pulisci_riferimenti_ip(lab_path, [old_ip_only], note, escludi_dev=nome, descrizione=f"{nome} {dev} rimossa")

    return f"Rimuovi interfaccia {dev} da {nome}"


def _op_edit_interface_ip(lab_path, p, note):
    disp = leggi_dispositivi(lab_path)
    own = _proprietari(disp)
    nome = str(p.get('nome') or '').strip()
    dev = str(p.get('dev') or '').strip()
    if nome not in disp:
        raise OpError(f"Dispositivo '{nome}' non trovato.")
    it = next((x for x in disp[nome]['interfacce'] if x['dev'] == dev), None)
    if not it:
        raise OpError(f"Interfaccia '{dev}' non trovata su {nome}.")

    raw_new = str(p.get('new_ip') or '').strip()
    if not it['ip']:
        nuovo = _valida_ip_cidr(raw_new, own=own)
        st = os.path.join(lab_path, f"{nome}.startup")
        righe = _righe_file(st) if os.path.exists(st) else []
        ins = next(
            (k for k, l in enumerate(righe) if re.match(r'^\s*(systemctl|ip\s+route|route\s+add)\b', l)),
            len(righe),
        )
        righe.insert(ins, f"ip address add {nuovo} dev {dev}")
        _scrivi_esatte(st, righe)
        return f"Assegna IP {nuovo} a {nome} {dev}"

    vecchio = ipaddress.ip_interface(it['ip'])
    if '/' not in raw_new:
        raw_new = f"{raw_new}/{vecchio.network.prefixlen}"
    nuovo = _valida_ip_cidr(raw_new, own=own, propri=(str(vecchio.ip),))
    if nuovo == vecchio:
        raise OpError("Il nuovo IP è identico a quello attuale.")

    altri = [
        (n, x) for n, x in _membri_lan(disp, it['lan'])
        if not (n == nome and x['dev'] == dev) and x['ip']
    ]
    if nuovo.network != vecchio.network and altri and p.get('mode') == 'lan':
        return _op_renumber_lan(
            lab_path,
            {'lan': it['lan'], 'new_network': str(nuovo.network), 'fixed': {f"{nome}:{dev}": str(nuovo)}},
            note,
        )

    altri_stessa_net_lab = any(
        not (n == nome and x['dev'] == dev) and x['ip'] and _norm_net(x['ip']) == str(vecchio.network)
        for n, dd in disp.items() for x in dd['interfacce']
    )
    altri_miei_stessa_net = any(
        x['dev'] != dev and x['ip'] and _norm_net(x['ip']) == str(vecchio.network)
        for x in disp[nome]['interfacce']
    )
    net_map = {str(vecchio.network): str(nuovo.network)} if (nuovo.network != vecchio.network and not altri_stessa_net_lab) else {}
    f = _sostituzione_ip({str(vecchio.ip): str(nuovo.ip)}, {str(vecchio): str(nuovo)}, net_map)
    modifiche = _piano_sostituzioni(lab_path, f)
    # Se la subnet cambia solo su questo nodo (altri nodi restano sulla vecchia), aggiorna comunque il frr.conf locale
    if nuovo.network != vecchio.network and not net_map and not altri_miei_stessa_net and disp[nome]['frr']:
        rel_frr = os.path.join(nome, 'etc', 'frr', 'frr.conf')
        f_loc = _sostituzione_ip({str(vecchio.ip): str(nuovo.ip)}, {str(vecchio): str(nuovo)}, {str(vecchio.network): str(nuovo.network)})
        v_frr = _righe_file(os.path.join(lab_path, rel_frr))
        n_frr = [f_loc(l) for l in v_frr]
        if n_frr != v_frr:
            modifiche[rel_frr] = (v_frr, n_frr)
    coppie = [(vecchio.network, nuovo.network)] if nuovo.network != vecchio.network else []
    if coppie:
        note.extend(_reti_da_controllare(lab_path, modifiche, coppie))
    for rel, (_, nuove) in modifiche.items():
        _scrivi_esatte(os.path.join(lab_path, rel), nuove)
    return f"IP di {nome} {dev}: {vecchio} → {nuovo}"


def _op_renumber_lan(lab_path, p, note):
    disp = leggi_dispositivi(lab_path)
    own = _proprietari(disp)
    lan = str(p.get('lan') or '').strip()
    membri = [(n, x) for n, x in _membri_lan(disp, lan) if x['ip']]
    vecchia = _rete_lan(disp, lan)
    if not vecchia or not membri:
        raise OpError(f"La LAN '{lan}' non ha IP da rinumerare.")
    try:
        nuova_rete = ipaddress.ip_network(str(p.get('new_network') or '').strip(), strict=False)
    except ValueError:
        raise OpError("Nuova rete non valida (usa formato CIDR, es. 10.0.5.0/24).")
    if nuova_rete == vecchia:
        raise OpError("La nuova rete coincide con quella attuale.")

    fuori = sorted(
        ip for ip, (_, _, l) in own.items()
        if l != lan and ipaddress.ip_address(ip) in nuova_rete
    )
    if fuori:
        note.append(f"Attenzione: la rete {nuova_rete} contiene già IP di altre LAN ({', '.join(fuori)}).")

    occupati = {ip for ip, (_, _, l) in own.items() if l != lan}
    fixed = p.get('fixed') or {}
    nuovi = {}
    used_new = set()

    for n, x in membri:
        key_str = f"{n}:{x['dev']}"
        if key_str in fixed and str(fixed[key_str]).strip():
            raw = str(fixed[key_str]).strip()
            if '/' not in raw:
                raw = f"{raw}/{nuova_rete.prefixlen}"
            c = _valida_ip_cidr(raw, own=own, propri=[str(m['ip']).split('/')[0] for _, m in membri])
            if c.network != nuova_rete:
                raise OpError(f"IP '{c}' per {n} {x['dev']} non appartiene a {nuova_rete}.")
            if str(c.ip) in used_new:
                raise OpError(f"IP duplicato {c.ip} nella LAN {lan}.")
            nuovi[(n, x['dev'])] = c
            used_new.add(str(c.ip))

    host_iter = iter(nuova_rete.hosts() if nuova_rete.prefixlen < 31 else list(nuova_rete))
    for n, x in membri:
        k = (n, x['dev'])
        if k in nuovi:
            continue
        v = ipaddress.ip_interface(x['ip'])
        cand = None
        off = int(v.ip) - int(vecchia.network_address)
        if 0 <= off < nuova_rete.num_addresses:
            c = ipaddress.ip_interface(f"{ipaddress.ip_address(int(nuova_rete.network_address) + off)}/{nuova_rete.prefixlen}")
            bad = nuova_rete.prefixlen < 31 and c.ip in (nuova_rete.network_address, nuova_rete.broadcast_address)
            if not bad and str(c.ip) not in occupati and str(c.ip) not in used_new:
                cand = c
        if cand is None:
            for h in host_iter:
                if str(h) not in occupati and str(h) not in used_new:
                    cand = ipaddress.ip_interface(f"{h}/{nuova_rete.prefixlen}")
                    break
        if cand is None:
            raise OpError(f"Indirizzi esauriti nella subnet {nuova_rete} per {n} {x['dev']}.")
        nuovi[k] = cand
        used_new.add(str(cand.ip))

    vecchi = {(n, x['dev']): ipaddress.ip_interface(x['ip']) for n, x in membri}
    ip_map = {str(vecchi[k].ip): str(nuovi[k].ip) for k in vecchi}
    iface_map = {str(vecchi[k]): str(nuovi[k]) for k in vecchi}
    net_map = {str(vecchia): str(nuova_rete)}

    f = _sostituzione_ip(ip_map, iface_map, net_map)
    modifiche = _piano_sostituzioni(lab_path, f)
    note.extend(_reti_da_controllare(lab_path, modifiche, [(vecchia, nuova_rete)]))
    for rel, (_, nuove) in modifiche.items():
        _scrivi_esatte(os.path.join(lab_path, rel), nuove)
    return f"Rinumera LAN {lan}: {vecchia} → {nuova_rete}"


def _op_move_interface(lab_path, p, note):
    disp = leggi_dispositivi(lab_path)
    own = _proprietari(disp)
    nome = str(p.get('nome') or '').strip()
    dev = str(p.get('dev') or '').strip()
    nuova = _valida_lan(p.get('new_lan'))
    if nome not in disp:
        raise OpError(f"Dispositivo '{nome}' non trovato.")
    it = next((x for x in disp[nome]['interfacce'] if x['dev'] == dev), None)
    if not it:
        raise OpError(f"Interfaccia '{dev}' non trovata su {nome}.")
    if nuova == it['lan']:
        raise OpError(f"{nome} {dev} è già sulla LAN {nuova}.")

    lc = os.path.join(lab_path, 'lab.conf')
    vecchie = _righe_file(lc)
    rx = re.compile(rf'^(\s*{re.escape(nome)}\s*\[\s*{it["idx"]}\s*\]\s*=\s*)(\S+?)(\s*)$')
    nuove, trovata = [], False
    for l in vecchie:
        m = rx.match(l)
        if m and not trovata:
            q = '"' if m.group(2).startswith('"') else ''
            l, trovata = f"{m.group(1)}{q}{nuova}{q}", True
        nuove.append(l)
    if not trovata:
        raise OpError(f"Riga {nome}[{it['idx']}]=... non trovata in lab.conf.")

    ip_map, iface_map, net_map = {}, {}, {}
    old_lan = it['lan']
    old_iface = ipaddress.ip_interface(it['ip']) if it['ip'] else None
    new_iface = None
    new_ip_raw = str(p.get('new_ip') or '').strip()
    if new_ip_raw:
        rete = _rete_lan(disp, nuova)
        if '/' not in new_ip_raw and rete:
            new_ip_raw = f"{new_ip_raw}/{rete.prefixlen}"
        elif '/' not in new_ip_raw and old_iface:
            new_ip_raw = f"{new_ip_raw}/{old_iface.network.prefixlen}"
        propri_ok = (str(old_iface.ip),) if old_iface else ()
        new_iface = _valida_ip_cidr(new_ip_raw, own=own, propri=propri_ok)
        if old_iface:
            ip_map, iface_map = {str(old_iface.ip): str(new_iface.ip)}, {str(old_iface): str(new_iface)}
            altri_old_net = any(
                not (n == nome and x['dev'] == dev) and x['ip'] and _norm_net(x['ip']) == str(old_iface.network)
                for n, dd in disp.items() for x in dd['interfacce']
            )
            if new_iface.network != old_iface.network and not altri_old_net:
                net_map = {str(old_iface.network): str(new_iface.network)}

    # Prima aggiorna lab.conf
    _scrivi_esatte(lc, nuove)

    # Se il dispositivo cambia LAN, pulisci vecchi neighbor BGP diretti sulla vecchia LAN
    if old_iface and disp[nome]['tipo'] == 'router' and 'bgpd' in disp[nome]['demoni']:
        old_peers_ips = {
            x['ip'].split('/')[0] for n, x in _membri_lan(disp, old_lan)
            if n != nome and x['ip']
        }
        # Rimuovi neighbor verso i vecchi peer su old_lan dal router spostato
        frr_loc = os.path.join(lab_path, nome, 'etc', 'frr', 'frr.conf')
        if old_peers_ips and os.path.exists(frr_loc):
            vf = _righe_file(frr_loc)
            nf, cp = [], []
            for l in vf:
                s = ' '.join(l.split())
                mnb = re.match(r'neighbor\s+(\S+)\s', s)
                if mnb and mnb.group(1) in old_peers_ips:
                    cp.extend(_policy_refs_in_line(l))
                    continue
                nf.append(l)
            nf, _ = _pulisci_policy_orfane_frr(nf, cp)
            if nf != vf:
                _scrivi_righe(frr_loc, nf)
        # Rimuovi neighbor verso il vecchio IP dai router rimasti su old_lan
        for n_peer, _ in _membri_lan(disp, old_lan):
            if n_peer == nome or not disp[n_peer]['frr']:
                continue
            fp = os.path.join(lab_path, n_peer, 'etc', 'frr', 'frr.conf')
            if os.path.exists(fp):
                vf = _righe_file(fp)
                nf, cp = [], []
                for l in vf:
                    s = ' '.join(l.split())
                    mnb = re.match(r'neighbor\s+(\S+)\s', s)
                    if mnb and mnb.group(1) == str(old_iface.ip):
                        cp.extend(_policy_refs_in_line(l))
                        continue
                    nf.append(l)
                nf, _ = _pulisci_policy_orfane_frr(nf, cp)
                if nf != vf:
                    _scrivi_righe(fp, nf)
                    note.append(f"Rimosso neighbor verso {nome} ({old_iface.ip}) da {n_peer}/etc/frr/frr.conf.")

    if ip_map:
        f = _sostituzione_ip(ip_map, iface_map, net_map)
        modifiche = _piano_sostituzioni(lab_path, f)
        if old_iface and new_iface and new_iface.network != old_iface.network and not net_map and disp[nome]['frr']:
            altri_miei_old = any(
                x['dev'] != dev and x['ip'] and _norm_net(x['ip']) == str(old_iface.network)
                for x in disp[nome]['interfacce']
            )
            if not altri_miei_old:
                rel_frr = os.path.join(nome, 'etc', 'frr', 'frr.conf')
                f_loc = _sostituzione_ip(ip_map, iface_map, {str(old_iface.network): str(new_iface.network)})
                v_frr = _righe_file(os.path.join(lab_path, rel_frr))
                n_frr = [f_loc(l) for l in v_frr]
                if n_frr != v_frr:
                    modifiche[rel_frr] = (v_frr, n_frr)
        for rel, (_, n_lines) in modifiche.items():
            _scrivi_esatte(os.path.join(lab_path, rel), n_lines)
    elif new_iface and not old_iface:
        st = os.path.join(lab_path, f"{nome}.startup")
        sr = _righe_file(st) if os.path.exists(st) else []
        ins = next((k for k, l in enumerate(sr) if re.match(r'^\s*(systemctl|ip\s+route|route\s+add)\b', l)), len(sr))
        sr.insert(ins, f"ip address add {new_iface} dev {dev}")
        _scrivi_esatte(st, sr)

    if disp[nome]['tipo'] == 'router' and 'bgpd' in disp[nome]['demoni']:
        auto_generate_bgp_neighbors(lab_path, _routers_from_disk(lab_path))

    if len(_membri_lan(disp, old_lan)) == 1:
        note.append(f"La LAN {old_lan} è rimasta senza dispositivi.")
    return f"Sposta {nome} {dev}: LAN {old_lan} → {nuova}"


def _op_change_gateway(lab_path, p, note):
    disp = leggi_dispositivi(lab_path)
    nome = str(p.get('nome') or '').strip()
    if nome not in disp:
        raise OpError(f"Dispositivo '{nome}' non trovato.")
    d = disp[nome]
    if d['tipo'] == 'router':
        raise OpError("Il default gateway guidato si imposta su host, www e dns.")
    gw = str(p.get('gateway') or '').strip()
    rel = f"{nome}.startup"
    st_path = os.path.join(lab_path, rel)
    vecchie = _righe_file(st_path) if os.path.exists(st_path) else []

    if not gw:
        nuove = [l for l in vecchie if not _RE_GW.match(l)]
        _scrivi_esatte(st_path, nuove)
        return f"Rimuovi default gateway da {nome}"

    gw = _valida_ip_solo(gw)
    dev = str(p.get('dev') or '').strip()
    if not dev:
        dev = next(
            (it['dev'] for it in d['interfacce']
             if it['ip'] and ipaddress.ip_address(gw) in ipaddress.ip_interface(it['ip']).network),
            None,
        )
    if dev is None:
        note.append(f"{gw} non appartiene alla subnet di nessuna interfaccia di {nome}.")
        dev = d['interfacce'][0]['dev'] if d['interfacce'] else 'eth0'

    nuove, fatto = [], False
    for l in vecchie:
        if _RE_GW.match(l) and not fatto:
            l = re.sub(r'(via|gw)\s+\S+', rf'\g<1> {gw}', l, count=1)
            if ' dev ' in l:
                l = re.sub(r'\bdev\s+\S+', f"dev {dev}", l)
            fatto = True
        nuove.append(l)
    if not fatto:
        ultimo = max((k for k, l in enumerate(nuove) if _RE_IP_ADD.match(l)), default=-1)
        nuove.insert(ultimo + 1, f"ip route add default via {gw} dev {dev}")
    _scrivi_esatte(st_path, nuove)
    return f"Default gateway di {nome}: {d['gateway'] or '-'} → {gw}"


def _op_change_as(lab_path, p, note):
    disp = leggi_dispositivi(lab_path)
    nome = str(p.get('nome') or '').strip()
    if nome not in disp or not disp[nome]['asn']:
        raise OpError(f"{nome} non ha 'router bgp': abilita prima BGP.")
    d = disp[nome]
    vecchio = d['asn']
    nuovo = str(p.get('new_as') or '').strip()
    if not asn_valido(nuovo) or nuovo == vecchio:
        raise OpError("Nuovo AS non valido o uguale a quello attuale.")

    rel = os.path.join(nome, 'etc', 'frr', 'frr.conf')
    righe = _righe_file(os.path.join(lab_path, rel))
    nuove_r = []
    for l in righe:
        l2 = re.sub(rf'^(\s*router\s+bgp\s+){vecchio}\b', rf'\g<1>{nuovo}', l)
        if re.match(r'^\s*set\s+as-path\s+prepend\b', l2):
            l2 = re.sub(rf'(?<=\s){vecchio}(?=\s|$)', nuovo, l2)
        nuove_r.append(l2)
    _scrivi_esatte(os.path.join(lab_path, rel), nuove_r)

    miei = _ip_del_router(d)
    for n, dd in disp.items():
        if n == nome or not dd['frr']:
            continue
        r2 = os.path.join(lab_path, n, 'etc', 'frr', 'frr.conf')
        v = _righe_file(r2)
        nu = []
        for l in v:
            m = re.match(rf'^(\s*neighbor\s+(\S+)\s+remote-as\s+){vecchio}(\s*)$', l)
            nu.append(f"{m.group(1)}{nuovo}{m.group(3)}" if m and m.group(2) in miei else l)
        if nu != v:
            _scrivi_esatte(r2, nu)

    for k, l in enumerate(righe, 1):
        if 'as-path' in l and re.search(rf'\b{vecchio}\b', l):
            note.append(f"{rel.replace(os.sep, '/')} riga {k}: '{l.strip()}' contiene ancora {vecchio}.")
    if re.match(rf'as{vecchio}r', nome):
        note.append(f"Il nome {nome} contiene ancora AS{vecchio}: il dispositivo non viene rinominato.")
    return f"Cambia AS di {nome}: AS{vecchio} → AS{nuovo}"


def _op_manage_protocols(lab_path, p, note):
    disp = leggi_dispositivi(lab_path)
    nome = str(p.get('nome') or '').strip()
    action = str(p.get('action') or '').strip().lower()
    proto = str(p.get('protocol') or '').strip().lower()
    if nome not in disp or not disp[nome]['frr']:
        raise OpError(f"{nome} non è un router FRR.")
    if action not in ('add', 'remove') or proto not in ('bgp', 'ospf', 'rip'):
        raise OpError("Azione o protocollo non valido.")
    d = disp[nome]
    attivi = [x for x in ('bgp', 'ospf', 'rip') if f"{x}d" in d['demoni']]

    rel = os.path.join(lab_path, nome, 'etc', 'frr', 'frr.conf')
    reld = os.path.join(lab_path, nome, 'etc', 'frr', 'daemons')
    righe = _righe_file(rel)
    dm = _righe_file(reld)

    if action == 'add':
        if proto in attivi:
            raise OpError(f"{proto.upper()} è già attivo su {nome}.")
        while righe and not righe[-1].strip():
            righe.pop()
        _scrivi_esatte(reld, _set_demone(dm, f"{proto}d", 'yes'))
        dati_r = {'asn': d['asn'] or '', 'interfaces': [{'ip': it['ip']} for it in d['interfacce'] if it['ip']]}
        if proto in ('ospf', 'rip'):
            proposta = default_igp_networks(nome, dati_r)
            reti = _parse_lista_reti(p.get('networks'), opzionale=True) or proposta
            redis = ['redistribute connected']
            if 'bgp' in attivi and bool(p.get('redistribute_bgp', True)):
                redis.append('redistribute bgp')
            if proto == 'ospf':
                area = str(p.get('ospf_area') or '0.0.0.0').strip()
                if not area_valida(area):
                    raise OpError(f"Area OSPF non valida: '{area}'.")
                stub = bool(p.get('ospf_area_stub')) and area not in ('0', '0.0.0.0')
                blocco = mk_ospf_stanza(reti, area, stub, redis).rstrip('\n').split('\n')
            else:
                blocco = mk_rip_stanza(reti, redis).rstrip('\n').split('\n')
            i = _inizio_blocco(righe, r'router bgp\b')
            nuove = righe + [''] + blocco if i is None else righe[:i] + blocco + [''] + righe[i:]
            _scrivi_esatte(rel, nuove)
        else:
            asn = str(p.get('asn') or '').strip()
            if not asn_valido(asn):
                raise OpError("Numero AS non valido (solo cifre).")
            proprie = [_norm_net(it['ip']) for it in d['interfacce'] if it['ip']]
            reti = _parse_lista_reti(p.get('networks'), opzionale=True)
            if p.get('networks') is None:
                reti = proprie
            blocco = mk_bgp_stanza(asn, networks=reti).rstrip('\n').split('\n')
            if not any(l.strip().startswith('debug bgp') for l in righe):
                i = next((k for k, l in enumerate(righe) if l.strip().startswith('log file')), len(righe) - 1)
                righe = righe[:i + 1] + ['', 'debug bgp keepalives', 'debug bgp updates in', 'debug bgp updates out'] + righe[i + 1:]
            if bool(p.get('redistribute_bgp', True)):
                for igp in ('ospf', 'rip'):
                    if igp in attivi:
                        con = _inserisci_nel_blocco(righe, rf'router {igp}\b', ['redistribute bgp'])
                        if con is not None:
                            righe = con
            _scrivi_esatte(rel, righe + [''] + blocco)
            if bool(p.get('auto_bgp_neighbors', True)):
                auto_generate_bgp_neighbors(lab_path, _routers_from_disk(lab_path))
        return f"Attiva {proto.upper()} su {nome}"

    if proto not in attivi:
        raise OpError(f"{proto.upper()} non è attivo su {nome}.")
    nuove = list(righe)
    i = _inizio_blocco(nuove, rf'router {proto}\b')
    if i is not None:
        f = _fine_blocco(nuove, i)
        while f < len(nuove) and not nuove[f].strip():
            f += 1
        del nuove[i:f]
    nuove = [
        l for l in nuove
        if not re.match(rf'\s*redistribute\s+{proto}\b', l)
        and not (proto == 'bgp' and re.match(r'\s*debug\s+bgp\b', l))
    ]
    _scrivi_esatte(rel, nuove)
    _scrivi_esatte(reld, _set_demone(dm, f"{proto}d", 'no'))

    if proto == 'bgp' and bool(p.get('clean_remote_neighbors', True)):
        miei = _ip_del_router(d)
        for n2, d2 in disp.items():
            if n2 == nome or not d2['frr']:
                continue
            r2 = os.path.join(lab_path, n2, 'etc', 'frr', 'frr.conf')
            v = _righe_file(r2)
            nu = [l for l in v if not (re.match(r'\s*neighbor\s+(\S+)\s', l) and l.split()[1] in miei)]
            if nu != v:
                _scrivi_esatte(r2, nu)
        note.append("Eventuali route-map/prefix-list non più usate verranno segnalate dai controlli FRR.")
    return f"Disattiva {proto.upper()} su {nome}"


def _op_ospf_cost(lab_path, p, note):
    disp = leggi_dispositivi(lab_path)
    nome = str(p.get('nome') or '').strip()
    dev = str(p.get('dev') or '').strip()
    if nome not in disp or 'ospfd' not in disp[nome]['demoni']:
        raise OpError(f"{nome} non ha OSPF abilitato.")
    if not any(it['dev'] == dev for it in disp[nome]['interfacce']):
        raise OpError(f"Interfaccia '{dev}' non trovata su {nome}.")

    fpath = os.path.join(lab_path, nome, 'etc', 'frr', 'frr.conf')
    righe = _righe_file(fpath)
    remove = bool(p.get('remove'))
    costo = None
    if not remove:
        try:
            costo = int(p.get('cost'))
            if costo < 1:
                raise ValueError()
        except (TypeError, ValueError):
            raise OpError("Il costo OSPF deve essere un intero >= 1.")

    rx = rf'interface\s+{re.escape(dev)}\b'
    idx = _inizio_blocco(righe, rx)
    if idx is not None:
        fine = _fine_blocco(righe, idx)
        nuove_blocco = [l for l in righe[idx:fine] if not re.match(r'\s*(?:ip\s+)?ospf\s+cost\b', l)]
        if not remove:
            nuove_blocco.append(f"    ospf cost {costo}")
        if remove and len(nuove_blocco) <= 1:
            righe = righe[:idx] + righe[fine:]
        else:
            righe = righe[:idx] + nuove_blocco + righe[fine:]
        _scrivi_righe(fpath, righe)
    elif not remove:
        _append_righe(fpath, [f"interface {dev}", f"    ospf cost {costo}"])

    cfg = _analizza_frr(_leggi_righe(fpath))
    if not remove and not cfg.get('auto_cost'):
        note.append(
            "Attenzione: in kathara/frr il costo predefinito senza 'auto-cost reference-bandwidth 100' è 10000 "
            "(non 10). Considera di attivare 'Costi OSPF predefiniti a 10' sull'AS."
        )
    return f"{'Rimuovi' if remove else f'Imposta (= {costo})'} costo OSPF su {nome} {dev}"


def _op_bgp_policy(lab_path, p, note):
    disp = leggi_dispositivi(lab_path)
    nome = str(p.get('nome') or '').strip()
    kind = str(p.get('kind') or '').strip().lower()
    if nome not in disp or 'bgpd' not in disp[nome]['demoni']:
        raise OpError(f"{nome} non ha BGP abilitato.")
    fpath = os.path.join(lab_path, nome, 'etc', 'frr', 'frr.conf')
    if not os.path.exists(fpath):
        raise OpError(f"frr.conf non trovato per {nome}.")

    if kind == 'default_originate':
        neighs = [str(x).strip() for x in (p.get('neighbors') or []) if str(x).strip()]
        if not neighs:
            raise OpError("Seleziona almeno un neighbor BGP.")
        vecchie = _righe_file(fpath)
        cfg = _analizza_frr(vecchie)
        solo = bool(p.get('only_default'))
        extra = _parse_lista_reti(p.get('extra_networks'), opzionale=True) if solo else []
        nuove = list(vecchie)
        righe_bgp = []
        for ip in neighs:
            ip = _valida_ip_solo(ip)
            if ip not in cfg['neighbors']:
                raise OpError(f"Neighbor {ip} non è configurato su {nome}.")
            if ip not in cfg['default_orig']:
                righe_bgp.append(f"neighbor {ip} default-originate")
            if solo:
                pl = f"SOLO_DEFAULT_{ip.replace('.', '_')}"
                for t_, pn, direz in cfg['link'].get(ip, []):
                    if t_ == 'prefix-list' and direz == 'out' and pn != pl:
                        note.append(f"{ip} aveva già 'prefix-list {pn} out': sostituita con {pl}.")
                        nuove = [l for l in nuove if ' '.join(l.split()) != f"neighbor {ip} prefix-list {pn} out"]
                nuove = [l for l in nuove if not l.strip().startswith(f"ip prefix-list {pl} ")]
                if f"neighbor {ip} prefix-list {pl} out" not in (' '.join(l.split()) for l in nuove):
                    righe_bgp.append(f"neighbor {ip} prefix-list {pl} out")
                nuove += [''] + [f"ip prefix-list {pl} permit {r}" for r in ['0.0.0.0/0'] + extra]
        if righe_bgp:
            ins = _inserisci_nel_blocco(nuove, r'router bgp\b', righe_bgp)
            if ins is None:
                raise OpError(f"{nome}: blocco 'router bgp' non trovato.")
            nuove = ins
        _scrivi_righe(fpath, nuove)
        annunciate = {_norm_net(n) for n in cfg['bgp_networks']}
        for r in extra:
            if _norm_net(r) not in annunciate:
                note.append(f"{r} non è tra le network BGP di {nome}: aggiungila con 'Aggiungi network BGP'.")
        note.append("default-originate da solo basta: 'network 0.0.0.0/0' non è necessario salvo richiesta esplicita.")
        return f"Default-originate BGP su {nome} verso {', '.join(neighs)}"

    if kind == 'cpp':
        neigh_ip = _valida_ip_solo(p.get('neighbor_ip'))
        neigh_name = str(p.get('neighbor_name') or neigh_ip.replace('.', '_')).strip()
        neigh_asn = str(p.get('neighbor_asn') or '').strip()
        rel_type = str(p.get('relation') or '').strip().lower()
        if rel_type not in ('provider', 'customer', 'peer'):
            raise OpError("Relazione economica non valida (provider, customer, peer).")

        if not _neighbor_presente(fpath, neigh_ip):
            if not asn_valido(neigh_asn):
                raise OpError(f"Neighbor {neigh_ip} non esiste su {nome}: specifica un ASN valido per crearlo.")
            insert_lines_into_protocol_block(
                fpath, proto='bgp',
                lines=[f"neighbor {neigh_ip} remote-as {neigh_asn}", f"neighbor {neigh_ip} description {neigh_name}"],
            )
        pl_in = f"{rel_type}_{neigh_name}_in"
        pl_out = f"{rel_type}_{neigh_name}_out"
        _rimuovi_righe(fpath, lambda l: l.strip().startswith(f"ip prefix-list {pl_in} ") or l.strip().startswith(f"ip prefix-list {pl_out} "))
        lines_append = [f"ip prefix-list {pl_in} permit any"]
        if rel_type == 'customer':
            lines_append.append(f"ip prefix-list {pl_out} permit any")
        else:
            own_nets = _parse_lista_reti(p.get('own_networks'), opzionale=True)
            cust_nets = _parse_lista_reti(p.get('customer_networks'), opzionale=True)
            all_out = list(dict.fromkeys(own_nets + cust_nets))
            if not all_out:
                note.append(f"Nessuna rete in uscita specificata: {nome} non annuncerà prefissi verso {neigh_name}.")
            lines_append += [f"ip prefix-list {pl_out} permit {r}" for r in all_out]
        _collega_neighbor_silenzioso(fpath, neigh_ip, 'prefix-list', pl_in, 'in', note)
        _collega_neighbor_silenzioso(fpath, neigh_ip, 'prefix-list', pl_out, 'out', note)
        _append_righe(fpath, lines_append)
        return f"Relazione {rel_type.upper()} su {nome} verso {neigh_name} ({neigh_ip})"

    neigh_ip = _valida_ip_solo(p.get('neighbor_ip'))
    if not _neighbor_presente(fpath, neigh_ip):
        nuovo_asn = str(p.get('neighbor_asn') or '').strip()
        if not asn_valido(nuovo_asn):
            raise OpError(f"Neighbor {neigh_ip} non è configurato su {nome}: inserisci il suo ASN per crearlo.")
        insert_lines_into_protocol_block(fpath, proto='bgp', lines=[f"neighbor {neigh_ip} remote-as {nuovo_asn}"])
        note.append(f"Creato nuovo neighbor {neigh_ip} remote-as {nuovo_asn} su {nome}.")

    tag = neigh_ip.replace('.', '_')

    if kind == 'prefix_list':
        direz = str(p.get('direction') or '').strip().lower()
        if direz not in ('in', 'out'):
            raise OpError("Direzione non valida: scegli 'in' o 'out'.")
        reti = _parse_lista_reti(p.get('networks'))
        pl_name = f"PL_{nome}_{tag}_{direz}"
        pat = re.compile(rf"^\s*ip prefix-list {re.escape(pl_name)} deny (\S+)")
        prev = [m.group(1) for m in map(pat.match, _leggi_righe(fpath)) if m]
        tutte = prev + [r for r in reti if r not in prev]
        _rimuovi_righe(fpath, lambda l: l.strip().startswith(f"ip prefix-list {pl_name} "))
        _append_righe(
            fpath,
            [f"ip prefix-list {pl_name} deny {r}" for r in tutte]
            + [f"ip prefix-list {pl_name} permit any"],
        )
        _collega_neighbor_silenzioso(fpath, neigh_ip, 'prefix-list', pl_name, direz, note)
        return f"Prefix-list {direz} su {nome} (neighbor {neigh_ip}): deny {', '.join(tutte)}"

    if kind == 'local_pref':
        try:
            lp_val = int(p.get('value'))
            if lp_val < 0:
                raise ValueError()
        except (TypeError, ValueError):
            raise OpError("Valore local-preference non valido (intero >= 0).")
        reti = _parse_lista_reti(p.get('networks'), opzionale=True)
        rm_name, pl_name = f"PREF_IN_{tag}", f"PREF_IN_{tag}_NETS"
        if reti:
            stanza = [
                f"route-map {rm_name} permit 10",
                f"    match ip address prefix-list {pl_name}",
                f"    set local-preference {lp_val}",
                f"route-map {rm_name} permit 20",
                "",
            ] + [f"ip prefix-list {pl_name} permit {r}" for r in reti]
        else:
            stanza = [f"route-map {rm_name} permit 10", f"    set local-preference {lp_val}"]
        _scrivi_route_map_silenziosa(fpath, rm_name, stanza, note, pl_name=pl_name)
        _collega_neighbor_silenzioso(fpath, neigh_ip, 'route-map', rm_name, 'in', note)
        return f"Local-preference {lp_val} (in) su {nome} da {neigh_ip}"

    if kind == 'med':
        try:
            m_val = int(p.get('value'))
            if m_val < 0:
                raise ValueError()
        except (TypeError, ValueError):
            raise OpError("Valore MED (metric) non valido (intero >= 0).")
        rm_name = f"LOCALMED_OUT_{tag}"
        _scrivi_route_map_silenziosa(fpath, rm_name, [f"route-map {rm_name} permit 10", f"    set metric {m_val}"], note)
        _collega_neighbor_silenzioso(fpath, neigh_ip, 'route-map', rm_name, 'out', note)
        return f"MED {m_val} (out) su {nome} verso {neigh_ip}"

    if kind == 'access_list':
        reti = _parse_lista_reti(p.get('networks'))
        contenuto = '\n'.join(_leggi_righe(fpath))
        acl_id = 10
        while re.search(rf"access-list {acl_id}\b", contenuto):
            acl_id += 10
        rm_name = f"FILTER_IN_{tag}"
        stanza = (
            [f"access-list {acl_id} deny {r}" for r in reti]
            + [f"access-list {acl_id} permit any", "", f"route-map {rm_name} permit 10", f"    match ip address {acl_id}"]
        )
        _scrivi_route_map_silenziosa(fpath, rm_name, stanza, note)
        _collega_neighbor_silenzioso(fpath, neigh_ip, 'route-map', rm_name, 'in', note)
        return f"Access-list {acl_id} + route-map {rm_name} (in) su {nome} da {neigh_ip}"

    raise OpError(f"Tipo di policy BGP non riconosciuto: '{kind}'.")


def _op_add_loopback(lab_path, p, note):
    disp = leggi_dispositivi(lab_path)
    own = _proprietari(disp)
    nome = str(p.get('nome') or '').strip()
    if nome not in disp:
        raise OpError(f"Dispositivo '{nome}' non trovato.")
    d = disp[nome]
    raw_ip = str(p.get('ip') or '').strip()
    if '/' not in raw_ip:
        raw_ip = raw_ip + '/32'
    ip_obj = _valida_ip_cidr(raw_ip, own=own)
    ipcidr = str(ip_obj)

    st = os.path.join(lab_path, f"{nome}.startup")
    lines = _righe_file(st) if os.path.exists(st) else []
    lb_line = f"ip address add {ipcidr} dev lo"
    if any(l.strip() == lb_line for l in lines):
        raise OpError(f"Loopback {ipcidr} già presente su {nome}.")
    ins = next((k for k, l in enumerate(lines) if re.match(r'^\s*systemctl\s+start\b', l)), len(lines))
    lines.insert(ins, lb_line)
    _scrivi_esatte(st, lines)

    fpath = os.path.join(lab_path, nome, 'etc', 'frr', 'frr.conf')
    if d['tipo'] == 'router' and os.path.exists(fpath):
        if 'ospfd' in d['demoni'] and bool(p.get('announce_igp', True)):
            area = str(p.get('ospf_area') or '0.0.0.0').strip()
            if not area_valida(area):
                raise OpError(f"Area OSPF non valida: '{area}'.")
            insert_lines_into_protocol_block(fpath, proto='ospf', lines=[f"network {ipcidr} area {area}"])
        if 'ripd' in d['demoni'] and bool(p.get('announce_igp', True)):
            insert_lines_into_protocol_block(fpath, proto='rip', lines=[f"network {ipcidr}"])
        if bool(p.get('ibgp_loopback', False)) and 'bgpd' in d['demoni']:
            try:
                add_ibgp_loopback_neighbors(lab_path, _routers_from_disk(lab_path))
            except Exception:
                pass
    return f"Aggiungi loopback {ipcidr} su {nome}"


def _op_redistribute_bgp_igp(lab_path, p, note):
    disp = leggi_dispositivi(lab_path)
    nome = str(p.get('nome') or '').strip()
    mode = str(p.get('mode') or '').strip().lower()
    if nome not in disp:
        raise OpError(f"Router '{nome}' non trovato.")
    d = disp[nome]
    protos = [x for x in ('ospf', 'rip') if f"{x}d" in d['demoni']]
    if 'bgpd' not in d['demoni'] or not protos:
        raise OpError(f"{nome} deve avere sia BGP sia OSPF o RIP.")
    fpath = os.path.join(lab_path, nome, 'etc', 'frr', 'frr.conf')

    if mode in ('off', 'all'):
        out, blocco = [], None
        for l in _leggi_righe(fpath):
            s = l.strip()
            if s.startswith('router '):
                blocco = s.split()[1]
            elif l and not l[0].isspace():
                blocco = None
            if blocco in ('ospf', 'rip') and s.startswith('redistribute bgp'):
                continue
            out.append(l)
        _scrivi_righe(fpath, out)
        if mode == 'all':
            for igp in protos:
                insert_lines_into_protocol_block(fpath, proto=igp, lines=['redistribute bgp'])
            return f"Attiva 'redistribute bgp' su {nome} ({', '.join(protos).upper()})"
        return f"Rimuovi 'redistribute bgp' da {nome} ({', '.join(protos).upper()})"

    if mode == 'ebgp':
        net_raw = str(p.get('neighbor_network') or '').strip()
        try:
            prefix = str(ipaddress.ip_network(net_raw, strict=False))
        except ValueError:
            raise OpError("Rete di collegamento con il neighbor BGP non valida (es. 50.7.1.0/24).")
        _rimuovi_righe(fpath, lambda l: l.strip().startswith('redistribute bgp'))
        _rimuovi_righe(fpath, lambda l: l.strip().startswith('ip prefix-list myNeighbors '))
        _rimuovi_route_map(fpath, 'eBGP')
        _append_righe(fpath, [
            f"ip prefix-list myNeighbors permit {prefix} le 32",
            "",
            "route-map eBGP permit 10",
            "    match ip next-hop prefix-list myNeighbors",
        ])
        for igp in protos:
            insert_lines_into_protocol_block(fpath, proto=igp, lines=['redistribute bgp route-map eBGP'])
        return f"Ridistribuzione BGP→IGP (route-map eBGP, {prefix}) su {nome}"

    raise OpError("Modalità ridistribuzione non valida (off, all, ebgp).")


def _op_set_resolver(lab_path, p, note):
    disp = leggi_dispositivi(lab_path)
    nome = str(p.get('nome') or '').strip()
    if nome not in disp:
        raise OpError(f"Dispositivo '{nome}' non trovato.")
    ns_ip = str(p.get('nameserver') or '').strip()
    dest = os.path.join(lab_path, nome, 'etc', 'resolv.conf')
    if not ns_ip:
        if os.path.exists(dest):
            os.remove(dest)
        return f"Rimuovi resolv.conf da {nome}"
    ns_ip = _valida_ip_solo(ns_ip)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    _scrivi_esatte(dest, [f"nameserver {ns_ip}"])
    return f"Imposta resolver {ns_ip} su {nome}"


def _op_bgp_network(lab_path, p, note):
    disp = leggi_dispositivi(lab_path)
    routers = _routers_from_disk(lab_path)
    nome = str(p.get('nome') or '').strip()
    if nome not in disp or 'bgpd' not in disp[nome]['demoni']:
        raise OpError(f"{nome} non ha BGP abilitato.")
    fpath = os.path.join(lab_path, nome, 'etc', 'frr', 'frr.conf')
    action = str(p.get('action') or 'add').strip().lower()

    if action == 'edit':
        old_raw = str(p.get('old_network') or '').strip()
        new_raw = str(p.get('new_network') or '').strip()
        old_n = _parse_lista_reti(old_raw)[0]
        new_n = _parse_lista_reti(new_raw)[0]
        if old_n == new_n:
            raise OpError("La nuova network BGP coincide con quella attuale.")
        out, in_bgp, trovata = [], False, False
        for l in _leggi_righe(fpath):
            s = l.strip()
            if s.startswith('router '):
                in_bgp = s.startswith('router bgp')
            elif l and not l[0].isspace():
                in_bgp = False
            elif in_bgp and s.startswith('network ') and len(s.split()) == 2 and _norm_net(s.split()[1]) == old_n:
                indent = l[:len(l) - len(l.lstrip())]
                out.append(f"{indent}network {new_n}")
                trovata = True
                continue
            out.append(l)
        if not trovata:
            raise OpError(f"Network BGP '{old_n}' non trovata su {nome}.")
        _scrivi_righe(fpath, out)
        _propaga_rete_in_policy(lab_path, old_n, new_n, note, origine_router=nome)
        return f"Modifica network BGP su {nome}: {old_n} → {new_n}"

    reti = _parse_lista_reti(p.get('networks'))

    if action == 'remove':
        rim = set(reti)
        out, in_bgp = [], False
        for l in _leggi_righe(fpath):
            s = l.strip()
            if s.startswith('router '):
                in_bgp = s.startswith('router bgp')
            elif l and not l[0].isspace():
                in_bgp = False
            elif in_bgp and s.startswith('network ') and len(s.split()) == 2 and _norm_net(s.split()[1]) in rim:
                continue
            out.append(l)
        _scrivi_righe(fpath, out)
        return f"Rimuovi network BGP ({', '.join(reti)}) da {nome}"

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
    if nuove:
        insert_lines_into_protocol_block(fpath, proto='bgp', lines=[f"network {r}" for r in nuove])

    if bool(p.get('remove_covered')):
        aggregati = [ipaddress.ip_network(r) for r in reti]
        peering = _reti_peering(nome, routers)
        coperte = sorted(
            pr for pr in presenti
            if pr not in peering
            and any(ipaddress.ip_network(pr) != a and ipaddress.ip_network(pr).subnet_of(a) for a in aggregati)
        )
        if coperte:
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
            note.append(f"Rimosse da BGP le sottoreti già coperte dall'aggregato: {', '.join(coperte)}.")
    return f"Aggiungi network BGP ({', '.join(nuove or reti)}) su {nome}"


def _op_ibgp_full_mesh(lab_path, p, note):
    routers = _routers_from_disk(lab_path)
    asn = str(p.get('asn') or '').strip()
    membri = [rn for rn, rd in routers.items() if 'bgp' in rd['protocols'] and str(rd.get('asn', '')).strip() == asn]
    if len(membri) < 2:
        raise OpError(f"AS{asn} ha meno di due router BGP.")
    aggiunte = 0
    for x in membri:
        fpath = os.path.join(lab_path, x, 'etc', 'frr', 'frr.conf')
        presenti = set(re.findall(r'neighbor (\S+) remote-as', '\n'.join(_leggi_righe(fpath))))
        nuove = []
        for y in membri:
            if y == x:
                continue
            ips_y = {str(ipaddress.ip_interface(it['ip']).ip) for it in routers[y]['interfaces'] if it.get('ip')}
            if presenti & ips_y:
                continue
            ip = _ip_verso(routers, y, x, asn)
            if ip:
                nuove += [f"neighbor {ip} remote-as {asn}", f"neighbor {ip} description iBGP {y}"]
        if nuove:
            insert_lines_into_protocol_block(fpath, proto='bgp', lines=nuove)
            aggiunte += len(nuove) // 2
    if not aggiunte:
        note.append(f"Tutte le sessioni iBGP in AS{asn} erano già presenti.")
    note.append("Controlla il testo dell'esercizio: alcuni scenari (es. butterfly) vietano l'iBGP.")
    return f"Sessioni iBGP full mesh su AS{asn} (+{aggiunte} neighbor)"


def _op_dns_delegation(lab_path, p, note):
    nome = str(p.get('nome') or '').strip()
    nc = os.path.join(lab_path, nome, 'etc', 'bind', 'named.conf')
    if not os.path.isfile(nc):
        raise OpError(f"{nome} non è un server DNS (named.conf assente).")
    testo = ' '.join(' '.join(_leggi_righe(nc)).split())
    if re.search(r'zone "\." \{ type master;', testo) is None:
        raise OpError(f"{nome} non è il server root (zona '.' non è 'type master').")
    zona = str(p.get('zone') or '').strip().strip('.')
    if not zona:
        raise OpError("Specifica la zona da delegare (es. com).")
    ns = str(p.get('ns') or f"dns.{zona}").strip().rstrip('.')
    ip = _valida_ip_solo(p.get('ip'))

    fpath = os.path.join(lab_path, nome, 'etc', 'bind', 'db.root')
    righe = _leggi_righe(fpath)
    if not any('SOA' in l for l in righe):
        serial = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d') + '01'
        righe = _soa_root(serial) + righe
        note.append("Aggiunto record SOA mancante in db.root.")
    if any(l.split()[:1] == [f"{zona}."] and 'NS' in l.split() for l in righe if l.strip()):
        raise OpError(f"La zona '{zona}' è già delegata in {nome}/etc/bind/db.root.")
    _scrivi_righe(fpath, righe + _righe_delega(zona, ns, ip))
    return f"Delega DNS {zona} → {ns} ({ip}) su {nome}"


def _op_ospf_auto_cost(lab_path, p, note):
    isole = isole_ospf(lab_path)
    if not isole:
        raise OpError("Nessun router OSPF trovato nel lab.")
    label = str(p.get('island') or '').strip()
    enable = bool(p.get('enable', True))
    scelta = next((x for x in isole if x[0] == label), None)
    if not scelta:
        raise OpError(f"Dominio OSPF '{label}' non trovato.")
    et, rs, _ = scelta
    for r in rs:
        fp = os.path.join(lab_path, r, 'etc', 'frr', 'frr.conf')
        _rimuovi_righe(fp, lambda l: l.strip().startswith('auto-cost reference-bandwidth'))
        if enable:
            insert_lines_into_protocol_block(fp, proto='ospf', lines=['auto-cost reference-bandwidth 100'])
    if enable:
        note.append("Costo OSPF predefinito impostato a 10 (100 / 10 Mbit) su tutti i router dell'AS.")
    else:
        note.append("auto-cost rimosso: il costo predefinito torna a 10000.")
    return f"{'Attiva' if enable else 'Rimuovi'} auto-cost OSPF su {et}"


def _op_default_igp(lab_path, p, note):
    nome = str(p.get('nome') or '').strip()
    proto = str(p.get('protocol') or '').strip().lower()
    if proto not in ('rip', 'ospf'):
        raise OpError("Protocollo IGP non valido (rip o ospf).")
    fpath = os.path.join(lab_path, nome, 'etc', 'frr', 'frr.conf')
    if not os.path.isfile(fpath):
        raise OpError(f"frr.conf non trovato per {nome}.")
    rx = rf'router {proto}\b'
    vecchie = _righe_file(fpath)
    inizio = _inizio_blocco(vecchie, rx)
    if inizio is None:
        raise OpError(f"{nome} non ha il blocco 'router {proto}'.")
    blocco = _comandi_nodo(vecchie, inizio)

    if proto == 'rip':
        mode = str(p.get('rip_mode') or 'route').strip().lower()
        if mode == 'route':
            reti = _parse_lista_reti(p.get('networks') or '0.0.0.0/0')
            nuove = [f"route {r}" for r in reti if f"route {r}" not in blocco]
        elif mode == 'originate':
            nuove = [] if 'default-information originate' in blocco else ['default-information originate']
        else:
            raise OpError("Modalità RIP non valida (route o originate).")
        if not nuove:
            raise OpError(f"Configurazione già presente in router rip su {nome}.")
        righe = _inserisci_nel_blocco(vecchie, rx, nuove)
        _scrivi_esatte(fpath, righe)
        return f"Default route RIP su {nome}"

    always = bool(p.get('always', True))
    riga = 'default-information originate' + (' always' if always else '')
    if riga in blocco:
        raise OpError(f"'{riga}' è già presente in router ospf su {nome}.")
    togli = {
        k for k in _indici_nodo(vecchie, inizio)
        if vecchie[k].strip().startswith('default-information originate')
    }
    pulite = [l for k, l in enumerate(vecchie) if k not in togli]
    righe = _inserisci_nel_blocco(pulite, rx, [riga])
    _scrivi_esatte(fpath, righe)
    if always:
        note.append("'always' fa annunciare la default anche se il router non possiede una rotta 0.0.0.0/0.")
    return f"Default route OSPF ({riga}) su {nome}"


def _op_save_file(lab_path, p, note):
    rel = str(p.get('file') or '').strip().replace('\\', '/')
    if not rel or rel.startswith('/') or '..' in rel.split('/'):
        raise OpError("Percorso file non valido.")
    full = os.path.abspath(os.path.join(lab_path, rel))
    base_abs = os.path.abspath(lab_path)
    if not full.startswith(base_abs + os.sep):
        raise OpError("Percorso file fuori dalla cartella del lab.")
    content = str(p.get('content', ''))
    righe = content.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    if righe and righe[-1] == '':
        righe.pop()
    os.makedirs(os.path.dirname(full), exist_ok=True)
    _scrivi_esatte(full, righe)
    if rel.endswith('.startup'):
        try:
            os.chmod(full, 0o755)
        except Exception:
            pass
    if rel.endswith('etc/frr/frr.conf'):
        refs = riferimenti_frr(righe)
        for x in refs:
            if x['gravita'] == 'errore':
                note.append(f"riga {x['riga']}: {x['messaggio']}")
    return f"Salva file {rel}"


def _op_fix_names(lab_path, p, note):
    ok = correggi_nomi_lab(lab_path, interactive=False)
    if not ok:
        raise OpError("Tutti i nomi dei dispositivi sono già validi per Kathará.")
    return "Correggi nomi dispositivi non validi per Kathará"


def _op_regen_xml(lab_path, p, note):
    out = rebuild_lab_metadata_and_export(lab_path)
    if not out:
        raise OpError("Rigenerazione XML non riuscita.")
    return f"Rigenera {os.path.basename(out)}"


def _op_delete_xml(lab_path, p, note):
    nome = os.path.basename(os.path.normpath(lab_path))
    xmlp = os.path.join(lab_path, f"{nome}.xml")
    if not os.path.exists(xmlp):
        raise OpError("Nessun file XML presente nel lab.")
    os.remove(xmlp)
    return f"Rimuovi {nome}.xml"



def _op_reorder_interfaces(lab_path, p, note):
    disp = leggi_dispositivi(lab_path)
    nome = str(p.get('nome') or '').strip()
    if nome not in disp:
        raise OpError(f"Dispositivo '{nome}' non trovato.")
    d = disp[nome]
    order = [str(x).strip() for x in (p.get('order') or []) if str(x).strip()]
    cur_devs = [it['dev'] for it in d['interfacce']]
    if sorted(order) != sorted(cur_devs) or len(order) != len(cur_devs):
        raise OpError("Ordine interfacce non valido: devono essere presenti tutte e sole le interfacce del dispositivo.")
    old_to_new = {old_dev: f"eth{i}" for i, old_dev in enumerate(order)}
    if all(k == v for k, v in old_to_new.items()):
        raise OpError("L'ordine delle interfacce non è cambiato.")
    _rinomina_interfacce_dispositivo(lab_path, nome, old_to_new, note)
    mappa_txt = ', '.join(f"{k}→{v}" for k, v in old_to_new.items() if k != v)
    return f"Riordina interfacce di {nome} ({mappa_txt})"


def _op_edit_router(lab_path, p, note):
    """Modifica completa di un router (simile a Aggiungi Router) con propagazione dei riferimenti."""
    disp = leggi_dispositivi(lab_path)
    nome = str(p.get('nome') or '').strip()
    if nome not in disp or disp[nome]['tipo'] != 'router':
        raise OpError(f"Router '{nome}' non trovato.")
    d = disp[nome]

    protos = [str(x).strip().lower() for x in (p.get('protocols') or []) if str(x).strip()]
    valid_p = {'bgp', 'ospf', 'rip', 'statico'}
    if not protos or any(x not in valid_p for x in protos):
        raise OpError("Seleziona almeno un protocollo valido (bgp, ospf, rip, statico).")

    asn = ''
    if 'bgp' in protos:
        asn = str(p.get('asn') or '').strip()
        if not asn_valido(asn):
            raise OpError("Numero AS non valido (solo cifre, es. 10).")

    ospf_area = '0.0.0.0'
    ospf_stub = False
    if 'ospf' in protos:
        ospf_area = str(p.get('ospf_area') or '0.0.0.0').strip()
        if not area_valida(ospf_area):
            raise OpError(f"Area OSPF non valida: '{ospf_area}'.")
        ospf_stub = bool(p.get('ospf_area_stub')) and ospf_area not in ('0', '0.0.0.0')

    raw_ifaces = p.get('interfaces') or []
    if not raw_ifaces:
        raise OpError("Un router deve avere almeno una interfaccia.")

    own = _proprietari(disp)
    miei_vecchi_ip = {it['ip'].split('/')[0] for it in d['interfacce'] if it['ip']} | {lb.split('/')[0] for lb in d['loopback']}

    # Validazione nuove interfacce
    parsed_ifaces = []
    local_ips = set()
    for idx, it in enumerate(raw_ifaces):
        lan = _valida_lan(it.get('lan'))
        ip_obj = _valida_ip_cidr(it.get('ip'), own=own, propri=miei_vecchi_ip)
        if str(ip_obj.ip) in local_ips:
            raise OpError(f"IP duplicato {ip_obj.ip} sullo stesso router.")
        local_ips.add(str(ip_obj.ip))
        parsed_ifaces.append({
            'new_idx': idx,
            'new_dev': f"eth{idx}",
            'orig_dev': str(it.get('orig_dev') or '').strip(),
            'lan': lan,
            'ip_obj': ip_obj,
        })

    # Validazione loopback
    loopbacks = []
    for lb in (p.get('loopbacks') or []):
        s = str(lb).strip()
        if not s:
            continue
        if '/' not in s:
            s = s + '/32'
        ip_obj = _valida_ip_cidr(s, own=own, propri=miei_vecchi_ip)
        if str(ip_obj.ip) in local_ips:
            raise OpError(f"Loopback {ip_obj.ip} duplicata.")
        local_ips.add(str(ip_obj.ip))
        loopbacks.append(str(ip_obj))

    # Validazione rotte statiche
    static_routes = []
    for sr in (p.get('static_routes') or []):
        dest = str(sr.get('dest') or '').strip()
        via = str(sr.get('via') or '').strip()
        if not dest and not via:
            continue
        if dest != 'default':
            try:
                dest = str(ipaddress.ip_network(dest, strict=False))
            except ValueError:
                raise OpError(f"Destinazione rotta statica non valida: '{dest}'.")
        via = _valida_ip_solo(via)
        dev_sr = str(sr.get('dev') or '').strip()
        static_routes.append({'dest': dest, 'via': via, 'dev': dev_sr})

    old_by_dev = {it['dev']: it for it in d['interfacce']}
    kept_orig_devs = {x['orig_dev'] for x in parsed_ifaces if x['orig_dev'] in old_by_dev}
    removed_ifaces = [it for it in d['interfacce'] if it['dev'] not in kept_orig_devs]

    # 1. Rinomina interfacce riordinate (per preservare eventuali blocchi 'interface ethX' in frr.conf)
    rename_map = {x['orig_dev']: x['new_dev'] for x in parsed_ifaces if x['orig_dev'] in old_by_dev}
    if any(k != v for k, v in rename_map.items()):
        # Solo righe interface ethX in frr.conf (lab.conf e startup vengono riscritti sotto)
        frr_p = os.path.join(lab_path, nome, 'etc', 'frr', 'frr.conf')
        if os.path.exists(frr_p):
            v_frr = _righe_file(frr_p)
            tmp_m = {k: f"__TMP_RENAME_IF_{i}__" for i, k in enumerate(rename_map)}
            nu_frr = []
            for l in v_frr:
                t = l
                for ok, tk in tmp_m.items():
                    t = re.sub(rf'(?<![A-Za-z0-9_]){re.escape(ok)}(?![A-Za-z0-9_])', tk, t)
                for ok, tk in tmp_m.items():
                    t = t.replace(tk, rename_map[ok])
                nu_frr.append(t)
            if nu_frr != v_frr:
                _scrivi_esatte(frr_p, nu_frr)

    # 2. Propagazione IP / subnet per le interfacce modificate e pulizia per quelle rimosse
    ip_map, iface_map, net_map_global, net_map_local = {}, {}, {}, {}
    removed_ips = []
    for it in removed_ifaces:
        if it['ip']:
            removed_ips.append(it['ip'].split('/')[0])
    old_lb_ips = {lb.split('/')[0] for lb in d['loopback']}
    new_lb_ips = {lb.split('/')[0] for lb in loopbacks}
    removed_ips.extend(sorted(old_lb_ips - new_lb_ips))

    for x in parsed_ifaces:
        orig = old_by_dev.get(x['orig_dev'])
        if not orig or not orig['ip']:
            continue
        v_if = ipaddress.ip_interface(orig['ip'])
        n_if = x['ip_obj']
        if v_if != n_if:
            ip_map[str(v_if.ip)] = str(n_if.ip)
            iface_map[str(v_if)] = str(n_if)
            if v_if.network != n_if.network:
                altri_lab_old = any(
                    not (n == nome and y['dev'] == orig['dev']) and y['ip'] and _norm_net(y['ip']) == str(v_if.network)
                    for n, dd in disp.items() for y in dd['interfacce']
                )
                altri_miei_old = any(
                    y['orig_dev'] != x['orig_dev'] and str(y['ip_obj'].network) == str(v_if.network)
                    for y in parsed_ifaces
                )
                if not altri_lab_old:
                    net_map_global[str(v_if.network)] = str(n_if.network)
                elif not altri_miei_old:
                    net_map_local[str(v_if.network)] = str(n_if.network)

    if ip_map or net_map_global:
        f_sub = _sostituzione_ip(ip_map, iface_map, net_map_global)
        mods = _piano_sostituzioni(lab_path, f_sub)
        for rel, (_, n_lines) in mods.items():
            _scrivi_esatte(os.path.join(lab_path, rel), n_lines)
        if net_map_local and d['frr']:
            fp = os.path.join(lab_path, nome, 'etc', 'frr', 'frr.conf')
            if os.path.exists(fp):
                f_loc = _sostituzione_ip({}, {}, net_map_local)
                vf = _righe_file(fp)
                nf = [f_loc(l) for l in vf]
                if nf != vf:
                    _scrivi_esatte(fp, nf)

    # 3. Aggiorna lab.conf per questo router
    uses_frr = any(x in protos for x in ('bgp', 'ospf', 'rip'))
    img_line = f'{nome}[image]="kathara/frr"' if uses_frr else f'{nome}[image]="kathara/base"'
    lc = os.path.join(lab_path, 'lab.conf')
    righe_lc = _righe_file(lc)
    rx_dev = re.compile(rf'^\s*{re.escape(nome)}\s*\[')
    first_pos = None
    resto = []
    for l in righe_lc:
        if rx_dev.match(l):
            if first_pos is None:
                first_pos = len(resto)
            continue
        resto.append(l)
    nuovo_blocco_lc = [f"{nome}[{x['new_idx']}]={x['lan']}" for x in parsed_ifaces] + [img_line]
    if first_pos is None:
        if resto and resto[-1].strip():
            resto.append('')
        nuove_lc = resto + nuovo_blocco_lc
    else:
        nuove_lc = resto[:first_pos] + nuovo_blocco_lc + resto[first_pos:]
    _scrivi_esatte(lc, nuove_lc)

    # 4. Aggiorna <nome>.startup
    startup_lines = [f"ip address add {x['ip_obj']} dev {x['new_dev']}" for x in parsed_ifaces]
    for lb in loopbacks:
        startup_lines.append(f"ip address add {lb} dev lo")
    iface_dicts = [{'name': x['new_dev'], 'lan': x['lan'], 'ip': str(x['ip_obj'])} for x in parsed_ifaces]
    startup_lines.extend(static_route_lines({'interfaces': iface_dicts, 'static_routes': static_routes}))
    if uses_frr:
        startup_lines.extend(['', 'systemctl start frr'])
    st_path = os.path.join(lab_path, f"{nome}.startup")
    _scrivi_esatte(st_path, startup_lines)
    try:
        os.chmod(st_path, 0o755)
    except Exception:
        pass

    # 5. Gestione FRR (daemons + frr.conf)
    etc_frr = os.path.join(lab_path, nome, 'etc', 'frr')
    frr_path = os.path.join(etc_frr, 'frr.conf')
    daemons_path = os.path.join(etc_frr, 'daemons')
    old_asn = d['asn']
    had_bgp = 'bgpd' in d['demoni']

    if not uses_frr:
        if os.path.isdir(etc_frr):
            shutil.rmtree(etc_frr, ignore_errors=True)
        if had_bgp:
            all_ips = list(miei_vecchi_ip | {str(x['ip_obj'].ip) for x in parsed_ifaces})
            _pulisci_riferimenti_ip(lab_path, all_ips, note, escludi_dev=nome, descrizione=f"BGP disattivato su {nome}")
    else:
        os.makedirs(etc_frr, exist_ok=True)
        if not os.path.exists(os.path.join(etc_frr, 'vtysh.conf')):
            with open(os.path.join(etc_frr, 'vtysh.conf'), 'w', encoding='utf-8', newline='\n') as fh:
                fh.write(VTYSH_TMPL.format(hostname=f"{nome}-frr"))
        if os.path.exists(daemons_path):
            dm = _righe_file(daemons_path)
            dm = _set_demone(dm, 'zebra', 'yes')
            dm = _set_demone(dm, 'bgpd', 'yes' if 'bgp' in protos else 'no')
            dm = _set_demone(dm, 'ospfd', 'yes' if 'ospf' in protos else 'no')
            dm = _set_demone(dm, 'ripd', 'yes' if 'rip' in protos else 'no')
            _scrivi_esatte(daemons_path, dm)
        else:
            with open(daemons_path, 'w', encoding='utf-8', newline='\n') as fh:
                fh.write(DAEMONS_TMPL.format(
                    zebra='yes',
                    ripd='yes' if 'rip' in protos else 'no',
                    ospfd='yes' if 'ospf' in protos else 'no',
                    bgpd='yes' if 'bgp' in protos else 'no',
                ))

        righe = _righe_file(frr_path) if os.path.exists(frr_path) else FRR_HEADER.rstrip('\n').split('\n')

        # Rimuovi blocchi interface per interfacce rimosse
        for rem in removed_ifaces:
            righe = _rimuovi_blocco_interfaccia_frr(righe, rem['dev'])

        # Helper per aggiornare / creare / rimuovere un blocco router <proto>
        def _togli_blocco(lines, proto_name):
            out_l = list(lines)
            i = _inizio_blocco(out_l, rf'router\s+{proto_name}\b')
            if i is not None:
                f_end = _fine_blocco(out_l, i)
                while f_end < len(out_l) and not out_l[f_end].strip():
                    f_end += 1
                del out_l[i:f_end]
            return out_l

        # Calcola reti IGP desiderate
        rdata_tmp = {'asn': asn, 'interfaces': iface_dicts}
        igp_nets_raw = p.get('igp_networks')
        igp_nets = _parse_lista_reti(igp_nets_raw, opzionale=True) if (igp_nets_raw is not None and str(igp_nets_raw).strip()) else default_igp_networks(nome, rdata_tmp)
        for lb in loopbacks:
            try:
                lb_ip = ipaddress.ip_interface(lb).ip
                if not any(lb_ip in ipaddress.ip_network(n, strict=False) for n in igp_nets):
                    igp_nets = igp_nets + [str(ipaddress.ip_interface(lb).network)]
            except ValueError:
                pass
        red_bgp = ('bgp' in protos) and bool(p.get('igp_redistribute_bgp', True))

        # --- OSPF ---
        if 'ospf' not in protos:
            righe = _togli_blocco(righe, 'ospf')
            righe = [l for l in righe if not re.match(r'\s*redistribute\s+ospf\b', l)]
        else:
            i_o = _inizio_blocco(righe, r'router\s+ospf\b')
            if i_o is None:
                redis = ['redistribute connected'] + (['redistribute bgp'] if red_bgp else [])
                blk = mk_ospf_stanza(igp_nets, ospf_area, ospf_stub, redis).rstrip('\n').split('\n')
                i_b = _inizio_blocco(righe, r'router\s+bgp\b')
                righe = (righe + [''] + blk) if i_b is None else (righe[:i_b] + blk + [''] + righe[i_b:])
            else:
                f_o = _fine_blocco(righe, i_o)
                body = righe[i_o + 1:f_o]
                # Conserva direttive extra (auto-cost, default-information, redistribute non-bgp/connected o route-map)
                kept_extra = []
                has_red_conn = False
                has_red_bgp_rm = False
                for l in body:
                    s = ' '.join(l.split())
                    if not s or s.startswith('network ') or re.match(r'area\s+\S+\s+stub\b', s):
                        continue
                    if s == 'redistribute connected':
                        has_red_conn = True
                        continue
                    if s == 'redistribute bgp':
                        continue
                    if s.startswith('redistribute bgp '):
                        if red_bgp:
                            has_red_bgp_rm = True
                            kept_extra.append(l)
                        continue
                    kept_extra.append(l)
                new_body = [''] + [f"    network {n} area {ospf_area}" for n in dict.fromkeys(igp_nets)]
                if ospf_stub:
                    new_body.append(f"    area {ospf_area} stub")
                new_body.append('')
                if has_red_conn or True:
                    new_body.append('    redistribute connected')
                if red_bgp and not has_red_bgp_rm:
                    new_body.append('    redistribute bgp')
                new_body.extend(kept_extra)
                righe = righe[:i_o + 1] + new_body + righe[f_o:]

        # --- RIP ---
        if 'rip' not in protos:
            righe = _togli_blocco(righe, 'rip')
            righe = [l for l in righe if not re.match(r'\s*redistribute\s+rip\b', l)]
        else:
            i_r = _inizio_blocco(righe, r'router\s+rip\b')
            if i_r is None:
                redis = ['redistribute connected'] + (['redistribute bgp'] if red_bgp else [])
                blk = mk_rip_stanza(igp_nets, redis).rstrip('\n').split('\n')
                i_b = _inizio_blocco(righe, r'router\s+bgp\b')
                righe = (righe + [''] + blk) if i_b is None else (righe[:i_b] + blk + [''] + righe[i_b:])
            else:
                f_r = _fine_blocco(righe, i_r)
                body = righe[i_r + 1:f_r]
                kept_extra = []
                has_red_bgp_rm = False
                for l in body:
                    s = ' '.join(l.split())
                    if not s or s.startswith('network ') or s == 'redistribute connected' or s == 'redistribute bgp':
                        continue
                    if s.startswith('redistribute bgp '):
                        if red_bgp:
                            has_red_bgp_rm = True
                            kept_extra.append(l)
                        continue
                    kept_extra.append(l)
                new_body = [''] + [f"    network {n}" for n in dict.fromkeys(igp_nets)]
                new_body.extend(['', '    redistribute connected'])
                if red_bgp and not has_red_bgp_rm:
                    new_body.append('    redistribute bgp')
                new_body.extend(kept_extra)
                righe = righe[:i_r + 1] + new_body + righe[f_r:]

        # --- BGP ---
        if 'bgp' not in protos:
            righe = _togli_blocco(righe, 'bgp')
            righe = [l for l in righe if not re.match(r'\s*debug\s+bgp\b', l) and not re.match(r'\s*redistribute\s+bgp\b', l)]
            _scrivi_righe(frr_path, righe)
            if had_bgp:
                all_ips = list(miei_vecchi_ip | {str(x['ip_obj'].ip) for x in parsed_ifaces})
                _pulisci_riferimenti_ip(lab_path, all_ips, note, escludi_dev=nome, descrizione=f"BGP disattivato su {nome}")
        else:
            if not any(l.strip().startswith('debug bgp') for l in righe):
                idx_log = next((k for k, l in enumerate(righe) if l.strip().startswith('log file')), 0)
                righe = righe[:idx_log + 1] + ['', 'debug bgp keepalives', 'debug bgp updates in', 'debug bgp updates out'] + righe[idx_log + 1:]

            bgp_nets_raw = p.get('bgp_networks')
            if bgp_nets_raw is not None:
                bgp_nets = _parse_lista_reti(bgp_nets_raw, opzionale=True)
            else:
                bgp_nets = [str(x['ip_obj'].network) for x in parsed_ifaces]

            i_b = _inizio_blocco(righe, r'router\s+bgp\b')
            old_bgp_nets = []
            if i_b is None:
                blk = mk_bgp_stanza(asn, networks=bgp_nets).rstrip('\n').split('\n')
                righe = righe + [''] + blk
            else:
                f_b = _fine_blocco(righe, i_b)
                righe[i_b] = f"router bgp {asn}"
                body = righe[i_b + 1:f_b]
                kept_body = []
                for l in body:
                    s = ' '.join(l.split())
                    if s.startswith('network ') and len(s.split()) == 2:
                        old_bgp_nets.append(_norm_net(s.split()[1]))
                        continue
                    kept_body.append(l)
                # Inserisci le network subito dopo no bgp ... (o in testa al blocco)
                ins_pos = 0
                for k, l in enumerate(kept_body):
                    s = ' '.join(l.split())
                    if s.startswith('no bgp ') or s.startswith('bgp '):
                        ins_pos = k + 1
                net_lines = [f"    network {n}" for n in dict.fromkeys(bgp_nets)]
                if net_lines:
                    kept_body = kept_body[:ins_pos] + [''] + net_lines + kept_body[ins_pos:]
                righe = righe[:i_b + 1] + kept_body + righe[f_b:]

            # Se l'ASN è cambiato, aggiorna set as-path prepend locale
            if old_asn and old_asn != asn:
                righe = [
                    re.sub(rf'(?<=\s){old_asn}(?=\s|$)', asn, l)
                    if re.match(r'^\s*set\s+as-path\s+prepend\b', l) else l
                    for l in righe
                ]

            _scrivi_righe(frr_path, righe)

            # Propagazione cambio ASN verso tutti gli altri router
            if old_asn and old_asn != asn:
                miei_attuali = {str(x['ip_obj'].ip) for x in parsed_ifaces} | {lb.split('/')[0] for lb in loopbacks}
                for n2, d2 in disp.items():
                    if n2 == nome or not d2['frr']:
                        continue
                    fp2 = os.path.join(lab_path, n2, 'etc', 'frr', 'frr.conf')
                    if not os.path.exists(fp2):
                        continue
                    v2 = _righe_file(fp2)
                    nu2 = []
                    for l in v2:
                        m = re.match(rf'^(\s*neighbor\s+(\S+)\s+remote-as\s+){old_asn}(\s*)$', l)
                        nu2.append(f"{m.group(1)}{asn}{m.group(3)}" if m and m.group(2) in miei_attuali else l)
                    if nu2 != v2:
                        _scrivi_esatte(fp2, nu2)
                        note.append(f"Aggiornato remote-as di {nome} (AS{old_asn} → AS{asn}) in {n2}/etc/frr/frr.conf.")

            # Propagazione modifica 1-a-1 di una network BGP annunciata verso prefix-list/access-list
            removed_bn = [x for x in old_bgp_nets if x not in bgp_nets]
            added_bn = [x for x in bgp_nets if x not in old_bgp_nets]
            if len(removed_bn) == 1 and len(added_bn) == 1:
                _propaga_rete_in_policy(lab_path, removed_bn[0], added_bn[0], note, origine_router=nome)

    # 6. Pulisci riferimenti agli IP effettivamente rimossi (interfacce/loopback eliminate)
    if removed_ips:
        _pulisci_riferimenti_ip(lab_path, removed_ips, note, escludi_dev=nome, descrizione=f"interfacce/loopback rimosse da {nome}")

    # 7. Auto-neighbor BGP sulle LAN condivise se richiesto
    if 'bgp' in protos and bool(p.get('auto_bgp_neighbors', True)):
        auto_generate_bgp_neighbors(lab_path, _routers_from_disk(lab_path))

    return f"Modifica configurazione router {nome}"


def _op_reset_topology(lab_path, p, note):
    """Resetta tutte le policy BGP e il routing dei router lasciando intatta
    la topologia base (nodi, LAN, IP, host/WWW/DNS) e i protocolli attivati (daemons + ASN)."""
    disp = leggi_dispositivi(lab_path)
    resettati = []
    for nome, d in sorted(disp.items()):
        if d['tipo'] != 'router':
            continue

        # 1. .startup: conserva IP interfacce, loopback e systemctl start frr; rimuove rotte statiche
        st_path = os.path.join(lab_path, f"{nome}.startup")
        if os.path.exists(st_path):
            v_st = _righe_file(st_path)
            nu_st = [
                l for l in v_st
                if not re.match(r'^\s*(?:ip\s+route\s+add|route\s+add)\b', l)
            ]
            if nu_st != v_st:
                _scrivi_esatte(st_path, nu_st)

        # 2. frr.conf: ricostruisce solo header + blocchi vuoti per i protocolli abilitati nei daemons
        if not d['frr']:
            continue
        frr_path = os.path.join(lab_path, nome, 'etc', 'frr', 'frr.conf')
        demoni = set(d['demoni'])
        parts = [FRR_HEADER.rstrip('\n')]

        if 'bgpd' in demoni:
            parts.append(
                "\ndebug bgp keepalives\n"
                "debug bgp updates in\n"
                "debug bgp updates out"
            )
        if 'ospfd' in demoni:
            parts.append("\nrouter ospf\n")
        if 'ripd' in demoni:
            parts.append("\nrouter rip\n")
        if 'bgpd' in demoni:
            asn = d['asn'] or ''
            if not asn:
                m = re.match(r'as(\d+)r', nome, re.I)
                asn = m.group(1) if m else '1'
            parts.append(
                f"\nrouter bgp {asn}\n\n"
                "    no bgp ebgp-requires-policy\n"
                "    no bgp network import-check"
            )

        nuovo_testo = "\n".join(parts).rstrip('\n') + "\n"
        vecchio_testo = "\n".join(_righe_file(frr_path)) + "\n"
        if nuovo_testo != vecchio_testo:
            with open(frr_path, 'w', encoding='utf-8', newline='\n') as fh:
                fh.write(nuovo_testo)
            resettati.append(nome)

    if resettati:
        note.append(
            f"Azzerati routing e policy su {len(resettati)} router ({', '.join(resettati)}). "
            "Topologia (lab.conf), IP interfacce, host/WWW/DNS e protocolli attivi (daemons) sono rimasti intatti."
        )
    else:
        note.append("Nessun router aveva configurazioni di routing/policy da azzerare.")
    return "Resetta topologia (routing e policy azzerati)"


_LAB_OPS = {
    'add_router': _op_add_router,
    'add_host': _op_add_host,
    'add_www': _op_add_www,
    'add_dns': _op_add_dns,
    'delete_device': _op_delete_device,
    'add_interface': _op_add_interface,
    'remove_interface': _op_remove_interface,
    'edit_interface_ip': _op_edit_interface_ip,
    'renumber_lan': _op_renumber_lan,
    'move_interface': _op_move_interface,
    'change_gateway': _op_change_gateway,
    'change_as': _op_change_as,
    'manage_protocols': _op_manage_protocols,
    'ospf_cost': _op_ospf_cost,
    'bgp_policy': _op_bgp_policy,
    'add_loopback': _op_add_loopback,
    'redistribute_bgp_igp': _op_redistribute_bgp_igp,
    'set_resolver': _op_set_resolver,
    'bgp_network': _op_bgp_network,
    'ibgp_full_mesh': _op_ibgp_full_mesh,
    'dns_delegation': _op_dns_delegation,
    'ospf_auto_cost': _op_ospf_auto_cost,
    'default_igp': _op_default_igp,
    'save_file': _op_save_file,
    'fix_names': _op_fix_names,
    'regen_xml': _op_regen_xml,
    'delete_xml': _op_delete_xml,
    'reorder_interfaces': _op_reorder_interfaces,
    'edit_router': _op_edit_router,
    'reset_topology': _op_reset_topology,
}


def preview_op(base, lab_name, op, params):
    if op not in _LAB_OPS:
        raise OpError(f"Operazione '{op}' non prevista.")
    lab_path = os.path.join(base, _valida_nome_lab(lab_name))
    if not os.path.isfile(os.path.join(lab_path, 'lab.conf')):
        raise OpError(f"Lab '{lab_name}' non trovato.")

    prima_files = _snapshot_files(lab_path)
    prima_avvisi = _avvisi_set(lab_path)
    note = []

    with tempfile.TemporaryDirectory(prefix='labgen_prev_') as tmp:
        sim_path = os.path.join(tmp, os.path.basename(os.path.normpath(lab_path)))
        shutil.copytree(lab_path, sim_path)
        titolo = _LAB_OPS[op](sim_path, params or {}, note)
        dopo_files = _snapshot_files(sim_path)
        dopo_avvisi = _avvisi_set(sim_path)

    diff = _build_diff(prima_files, dopo_files)
    xml_op = op in ('regen_xml', 'delete_xml')
    return {
        'titolo': titolo,
        'note': note,
        'diff': diff,
        'ha_modifiche': bool(diff) or xml_op,
        'avvisi_risolti': sorted(prima_avvisi - dopo_avvisi),
        'avvisi_nuovi': sorted(dopo_avvisi - prima_avvisi),
        'avvisi_totale': len(dopo_avvisi),
    }


def commit_op(base, lab_name, op, params):
    if op not in _LAB_OPS:
        raise OpError(f"Operazione '{op}' non prevista.")
    lab_path = os.path.join(base, _valida_nome_lab(lab_name))
    if not os.path.isfile(os.path.join(lab_path, 'lab.conf')):
        raise OpError(f"Lab '{lab_name}' non trovato.")

    prima_avvisi = _avvisi_set(lab_path)
    note = []
    backup_path = None
    if op != 'regen_xml':
        backup_path = copia_di_sicurezza(lab_path, etichetta=op)

    try:
        titolo = _LAB_OPS[op](lab_path, params or {}, note)
        if op not in ('regen_xml', 'delete_xml'):
            _sync_xml_if_present(lab_path)
    except Exception:
        if backup_path and os.path.isdir(backup_path):
            shutil.rmtree(lab_path, ignore_errors=True)
            shutil.copytree(backup_path, lab_path)
        raise

    dopo_avvisi = _avvisi_set(lab_path)
    return {
        'ok': True,
        'titolo': titolo,
        'note': note,
        'backup': os.path.basename(backup_path) if backup_path else None,
        'avvisi_risolti': sorted(prima_avvisi - dopo_avvisi),
        'avvisi_nuovi': sorted(dopo_avvisi - prima_avvisi),
    }


def create_lab(base, params):
    nome = _valida_nome_lab(params.get('nome'))
    overwrite = bool(params.get('overwrite'))
    lab_path = os.path.join(base, nome)
    if os.path.exists(lab_path):
        if not overwrite:
            raise OpError(f"Il lab '{nome}' esiste già in {base}.")
        if os.path.isfile(os.path.join(lab_path, 'lab.conf')):
            copia_di_sicurezza(lab_path, etichetta='prima_sovrascrittura')
        shutil.rmtree(lab_path)

    os.makedirs(lab_path, exist_ok=True)
    _scrivi_esatte(os.path.join(lab_path, 'lab.conf'), [f"# Lab {nome}"])

    note = []
    try:
        for r in (params.get('routers') or []):
            r_copy = dict(r)
            r_copy['auto_bgp_neighbors'] = False
            _op_add_router(lab_path, r_copy, note)
        for h in (params.get('hosts') or []):
            _op_add_host(lab_path, h, note)
        for w in (params.get('wwws') or []):
            _op_add_www(lab_path, w, note)
        for d in (params.get('dns') or []):
            _op_add_dns(lab_path, d, note)

        routers_all = _routers_from_disk(lab_path)
        if routers_all:
            auto_generate_bgp_neighbors(lab_path, routers_all)
            try:
                add_ibgp_loopback_neighbors(lab_path, routers_all)
            except Exception:
                pass

        res_ip = str(params.get('global_resolver') or '').strip()
        if res_ip:
            res_ip = _valida_ip_solo(res_ip)
            disp = leggi_dispositivi(lab_path)
            for dn, dd in disp.items():
                if dd['tipo'] != 'dns':
                    os.makedirs(os.path.join(lab_path, dn, 'etc'), exist_ok=True)
                    _scrivi_esatte(os.path.join(lab_path, dn, 'etc', 'resolv.conf'), [f"nameserver {res_ip}"])

        if bool(params.get('export_xml', False)):
            rebuild_lab_metadata_and_export(lab_path)
    except Exception:
        shutil.rmtree(lab_path, ignore_errors=True)
        raise

    return {'ok': True, 'lab': nome, 'note': note}


def delete_lab(base, lab_name):
    nome = _valida_nome_lab(lab_name)
    lab_path = os.path.join(base, nome)
    if not os.path.isfile(os.path.join(lab_path, 'lab.conf')):
        raise OpError(f"Lab '{nome}' non trovato.")
    backup = copia_di_sicurezza(lab_path, etichetta='prima_eliminazione')
    shutil.rmtree(lab_path)
    return {'ok': True, 'backup': os.path.basename(backup)}


def import_lab_content(base, filename, content, overwrite=False, custom_name=None):
    ext = os.path.splitext(filename or '')[1].lower()
    with tempfile.TemporaryDirectory(prefix='labgen_imp_') as tmp:
        fpath = os.path.join(tmp, 'import' + (ext if ext in ('.xml', '.json') else '.xml'))
        with open(fpath, 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)
        try:
            if ext == '.json':
                lab_name, routers, hosts, wwws, lab_conf_text = load_lab_from_json(fpath)
            elif ext == '.xml':
                lab_name, routers, hosts, wwws, lab_conf_text = load_lab_from_xml(fpath)
            else:
                try:
                    lab_name, routers, hosts, wwws, lab_conf_text = load_lab_from_xml(fpath)
                except Exception:
                    lab_name, routers, hosts, wwws, lab_conf_text = load_lab_from_json(fpath)
        except Exception as e:
            raise OpError(f"File XML/JSON non valido: {e}")

    lab_name = _valida_nome_lab(custom_name or lab_name)
    dest = os.path.join(base, lab_name)
    if os.path.exists(dest):
        if not overwrite:
            return {'esiste': True, 'lab': lab_name}
        if os.path.isfile(os.path.join(dest, 'lab.conf')):
            copia_di_sicurezza(dest, etichetta='prima_import')

    routers, lab_conf_text = correggi_nomi_importati(routers, hosts, wwws, lab_conf_text, interactive=False)
    recreate_lab_from_data(lab_name, base, routers, hosts, wwws, lab_conf_text, confirm=False)
    return {'ok': True, 'lab': lab_name}


def ping_oneliner(lab_path):
    routers_meta = None
    try:
        xmlpath = os.path.join(lab_path, os.path.basename(os.path.normpath(lab_path)) + '.xml')
        if os.path.exists(xmlpath):
            _, routers_meta, _, _, _ = load_lab_from_xml(xmlpath)
    except Exception:
        routers_meta = None
    ips = collect_lab_ips(lab_path, routers_meta)
    if not ips:
        raise OpError("Nessun IP trovato nella directory del lab.")
    return {'comando': generate_ping_oneliner(ips), 'conteggio': len(ips)}


def list_backups(lab_path):
    c = _cartella_copie(lab_path)
    if not os.path.isdir(c):
        return []
    return sorted(
        (d for d in os.listdir(c) if os.path.isfile(os.path.join(c, d, 'lab.conf'))),
        reverse=True,
    )


def restore_backup(lab_path, backup_name):
    if not backup_name or '/' in backup_name or '\\' in backup_name or '..' in backup_name:
        raise OpError("Nome backup non valido.")
    src = os.path.join(_cartella_copie(lab_path), backup_name)
    if not os.path.isfile(os.path.join(src, 'lab.conf')):
        raise OpError(f"Copia di sicurezza '{backup_name}' non trovata.")
    prima = copia_di_sicurezza(lab_path, etichetta='prima_del_ripristino')
    shutil.rmtree(lab_path)
    shutil.copytree(src, lab_path)
    return {'ok': True, 'ripristinato': backup_name, 'salvato_prima': os.path.basename(prima)}


def check_frr_content(content):
    righe = str(content or '').replace('\r\n', '\n').replace('\r', '\n').split('\n')
    refs = riferimenti_frr(righe)
    out = []
    for x in refs:
        row_idx = (x.get('riga') or 0) - 1
        suggerita = None
        if 0 <= row_idx < len(righe):
            suggerita = _correzione_suggerita(righe[row_idx], x['messaggio'])
        item = dict(x)
        item['correzione'] = suggerita
        out.append(item)
    return out


def suggerisci_ip_lan(lab_path, lan, exclude=None):
    disp = leggi_dispositivi(lab_path)
    own = set(_proprietari(disp).keys())
    for ex in (exclude or []):
        s = str(ex or '').strip().split('/')[0]
        if s:
            own.add(s)
    rete = _rete_lan(disp, lan)
    if not rete:
        return ''
    candidates = rete.hosts() if rete.prefixlen < 31 else list(rete)
    for h in candidates:
        if str(h) not in own:
            return f"{h}/{rete.prefixlen}"
    return ''
