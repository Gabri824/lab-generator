"""
src/core/frr_autofix.py
Motore diagnostico e di auto-fix deterministico multi-livello per FRRouting (frr.conf)
e coerenza del laboratorio Kathará. Solo libreria standard Python (zero dipendenze esterne).
"""
import difflib
import ipaddress
import os
import re

from .analyzer import (
    _analizza_frr,
    _proprietari,
    _voce_prefix_list,
    controlla_topologia,
    controlli_configurazione,
    isole_ospf,
    leggi_dispositivi,
    riferimenti_frr,
)
from .cli_io import correggi_nome_kathara, nome_kathara_valido
from .file_utils import _leggi_righe
from .net_frr import _contiene, _norm_net
from .templates import _FRR_GLOBALI

# ---------------------------------------------------------------------------
# Mini-tabella grammaticale FRR per contesto di blocco
# ---------------------------------------------------------------------------
_GLOBAL_CMDS = {
    'router', 'interface', 'route-map', 'ip', 'ipv6', 'access-list', 'bgp',
    'log', 'debug', 'hostname', 'password', 'enable', 'line', 'service', 'frr',
    'vrf', 'agentx', 'end', 'exit', 'no', 'username', 'banner', 'defaults',
    'mpls', 'segment-routing', 'bfd', 'rpki', 'key', 'fpm', 'table', 'zebra',
    'allow-reserved-ranges', 'dump', 'pbr-map', 'nexthop-group', 'mac',
}

_BLOCK_CMDS = {
    'global': _GLOBAL_CMDS,
    'router bgp': {
        'bgp', 'no', 'neighbor', 'network', 'redistribute', 'timers',
        'aggregate-address', 'distance', 'maximum-paths', 'address-family',
        'exit-address-family', 'exit', 'end', 'coalesce-time', 'default-originate',
        'synchronization', 'auto-summary', 'table-map', 'update-delay',
        'dampening', 'bmp', 'vnc', 'listen', 'peer-group', 'neighbor-group',
        'maximum-prefix', 'import', 'export', 'rd', 'route-target',
    },
    'router ospf': {
        'network', 'area', 'redistribute', 'auto-cost', 'default-information',
        'ospf', 'passive-interface', 'timers', 'distance', 'log-adjacency-changes',
        'max-metric', 'neighbor', 'no', 'refresh', 'summary-address',
        'distribute-list', 'default-metric', 'capability', 'compatible',
        'maximum-paths', 'write-multiplier', 'proactive-arp', 'router-info',
        'mpls-te', 'segment-routing', 'exit', 'end',
    },
    'router rip': {
        'network', 'redistribute', 'route', 'default-information',
        'passive-interface', 'version', 'timers', 'distance', 'distribute-list',
        'offset-list', 'neighbor', 'default-metric', 'allow-ecmp', 'no',
        'exit', 'end',
    },
    'interface': {
        'ip', 'ipv6', 'ospf', 'description', 'bandwidth', 'shutdown', 'no',
        'link-detect', 'multicast', 'mpls', 'bfd', 'isis', 'rip', 'exit', 'end',
    },
    'route-map': {
        'match', 'set', 'on-match', 'call', 'continue', 'description', 'no',
        'exit', 'end',
    },
}

_NEIGHBOR_SUBCMDS = {
    'remote-as', 'description', 'update-source', 'ebgp-multihop', 'next-hop-self',
    'prefix-list', 'route-map', 'distribute-list', 'filter-list', 'default-originate',
    'timers', 'shutdown', 'activate', 'soft-reconfiguration', 'send-community',
    'allowas-in', 'as-override', 'weight', 'password', 'passive', 'capability',
    'advertisement-interval', 'maximum-prefix', 'route-reflector-client',
    'local-as', 'remove-private-as', 'bfd', 'peer-group', 'interface',
    'strict-capability-match', 'disable-connected-check', 'ttl-security',
    'override-capability', 'dont-capability-negotiate', 'solo', 'port',
    'unsuppress-map', 'attribute-unchanged', 'addpath-tx-all-paths',
    'addpath-tx-bestpath-per-as', 'fall-over', 'graceful-restart', 'no',
    'sender-as-path-loop-detection', 'as-path',
}

_BGP_SUBCMDS = {
    'ebgp-requires-policy', 'network', 'router-id', 'log-neighbor-changes',
    'always-compare-med', 'deterministic-med', 'bestpath', 'default',
    'cluster-id', 'confederation', 'graceful-restart', 'fast-external-failover',
    'enforce-first-as', 'dampening', 'max-med', 'suppress-fib-pending',
    'disable-ebgp-connected-route-check', 'allow-martian-nexthop', 'as-path',
    'community-list', 'extcommunity-list', 'large-community-list',
    'graceful-shutdown', 'administrative-distance', 'scan-time',
}

_IP_GLOBAL_SUBCMDS = {
    'prefix-list', 'access-list', 'route', 'community-list', 'extcommunity-list',
    'as-path', 'forwarding', 'protocol', 'nht', 'import-table', 'router-id',
}

_OSPF_IF_SUBCMDS = {
    'cost', 'area', 'priority', 'hello-interval', 'dead-interval', 'network',
    'authentication', 'authentication-key', 'message-digest-key', 'mtu-ignore',
    'passive', 'retransmit-interval', 'transmit-delay', 'bfd', 'dead-interval',
    'gr-hello-delay',
}

_MATCH_SUBCMDS = {
    'ip', 'ipv6', 'as-path', 'community', 'extcommunity', 'large-community',
    'interface', 'local-preference', 'metric', 'origin', 'peer', 'probability',
    'source-protocol', 'tag', 'rpki', 'evpn', 'mac', 'vrf', 'source-instance',
}

_SET_SUBCMDS = {
    'local-preference', 'metric', 'as-path', 'community', 'extcommunity',
    'large-community', 'ip', 'ipv6', 'weight', 'origin', 'tag',
    'atomic-aggregate', 'aggregator', 'comm-list', 'metric-type',
    'originator-id', 'src', 'table', 'forwarding-address', 'label-index',
    'distance', 'sr-te', 'l3vpn', 'evpn',
}

_REDISTRIBUTE_PROTOS = {
    'bgp', 'ospf', 'rip', 'connected', 'static', 'kernel', 'isis', 'eigrp',
    'babel', 'sharp', 'table', 'nhrp', 'openfabric', 'vnc',
}

_ROUTER_PROTOS = {
    'bgp', 'ospf', 'ospf6', 'rip', 'ripng', 'isis', 'eigrp', 'babel', 'openfabric', 'static',
}

_RE_START_FRR = re.compile(
    r'^\s*(?:systemctl\s+start\s+frr|/etc/init\.d/frr\s+start|service\s+frr\s+start)\b'
)
_RE_START_APACHE = re.compile(
    r'^\s*(?:systemctl\s+start\s+apache2|/etc/init\.d/apache2\s+start|service\s+apache2\s+start)\b'
)


def _indent_of(raw_line):
    return raw_line[:len(raw_line) - len(raw_line.lstrip(' \t'))]


def _replace_token_in_raw(raw_line, old_tok, new_tok, occurrence=1):
    """Sostituisce la `occurrence`-esima occorrenza esatta del token preservando gli spazi."""
    count = [0]

    def _sub(m):
        count[0] += 1
        if count[0] == occurrence:
            return new_tok
        return m.group(0)

    nuova = re.sub(rf'(?<!\S){re.escape(old_tok)}(?!\S)', _sub, raw_line)
    return nuova


def _make_issue(
    id_regola,
    gravita,
    confidenza,
    file_rel,
    riga,
    testo,
    messaggio,
    fixes=None,
):
    fixes = list(fixes or [])
    correzione = None
    for fx in fixes:
        if fx.get('tipo') == 'replace_line' and fx.get('nuova_riga') is not None:
            correzione = fx['nuova_riga']
            break
    return {
        'id_regola': id_regola,
        'gravita': gravita,
        'confidenza': confidenza,
        'file': file_rel,
        'riga': riga,
        'testo': testo,
        'messaggio': messaggio,
        'correzione': correzione,
        'fixes': fixes,
    }


def _parse_blocks(righe):
    """Analizza il file frr.conf riga per riga tracciando il contesto di blocco.
    Ritorna lista di dict: {riga, raw, norm, indent, blocco, header_info, block_id}.
    """
    parsed = []
    blocco = 'global'
    header_info = {}
    block_seq = 0
    block_id = ('global', 0)

    for idx, raw in enumerate(righe, 1):
        norm = ' '.join(raw.split())
        indent = _indent_of(raw)
        if not norm or norm.startswith('!') or norm.startswith('#'):
            parsed.append({
                'riga': idx, 'raw': raw, 'norm': norm, 'indent': indent,
                'blocco': blocco, 'header_info': dict(header_info),
                'block_id': block_id, 'ignora': True,
            })
            continue

        toks = norm.split()
        first = toks[0]

        if first in ('exit', 'end'):
            if first == 'end' or blocco != 'global':
                blocco = 'global'
                header_info = {}
                block_id = ('global', 0)
            parsed.append({
                'riga': idx, 'raw': raw, 'norm': norm, 'indent': indent,
                'blocco': 'global', 'header_info': {}, 'block_id': block_id,
                'ignora': False, 'is_header': False,
            })
            continue

        if first == 'exit-address-family' and blocco == 'router bgp':
            parsed.append({
                'riga': idx, 'raw': raw, 'norm': norm, 'indent': indent,
                'blocco': blocco, 'header_info': dict(header_info), 'block_id': block_id,
                'ignora': False, 'is_header': False,
            })
            continue

        # Transizioni di blocco principali
        m_rt = re.match(r'^router\s+(bgp|ospf|rip)\b(?:\s+(\S+))?', norm)
        if m_rt:
            block_seq += 1
            proto = m_rt.group(1)
            blocco = f'router {proto}'
            header_info = {'proto': proto, 'asn': m_rt.group(2) or ''}
            block_id = (blocco, block_seq)
            parsed.append({
                'riga': idx, 'raw': raw, 'norm': norm, 'indent': indent,
                'blocco': blocco, 'header_info': dict(header_info), 'block_id': block_id,
                'ignora': False, 'is_header': True,
            })
            continue

        m_if = re.match(r'^interface\s+(\S+)', norm)
        if m_if and not indent:
            block_seq += 1
            blocco = 'interface'
            header_info = {'iface': m_if.group(1)}
            block_id = ('interface', m_if.group(1), block_seq)
            parsed.append({
                'riga': idx, 'raw': raw, 'norm': norm, 'indent': indent,
                'blocco': blocco, 'header_info': dict(header_info), 'block_id': block_id,
                'ignora': False, 'is_header': True,
            })
            continue

        m_rm = re.match(r'^route-map\s+(\S+)\s+(permit|deny)\s+(\d+)', norm)
        if m_rm:
            block_seq += 1
            blocco = 'route-map'
            header_info = {'name': m_rm.group(1), 'action': m_rm.group(2), 'seq': m_rm.group(3)}
            block_id = ('route-map', m_rm.group(1), m_rm.group(3), block_seq)
            parsed.append({
                'riga': idx, 'raw': raw, 'norm': norm, 'indent': indent,
                'blocco': blocco, 'header_info': dict(header_info), 'block_id': block_id,
                'ignora': False, 'is_header': True,
            })
            continue

        # Comandi globali non indentati chiudono il blocco precedente
        if not indent and (_FRR_GLOBALI.match(norm) or first in ('ip', 'ipv6')):
            # Eccezione: 'ip ospf ...' o 'ip address ...' dentro 'interface' può essere scritto senza indentazione
            if not (blocco == 'interface' and re.match(r'^ip(?:v6)?\s+(?:ospf|address|rip)\b', norm)):
                blocco = 'global'
                header_info = {}
                block_id = ('global', 0)

        parsed.append({
            'riga': idx, 'raw': raw, 'norm': norm, 'indent': indent,
            'blocco': blocco, 'header_info': dict(header_info), 'block_id': block_id,
            'ignora': False, 'is_header': False,
        })

    return parsed


def _close_keyword(tok, valid_set, cutoff=0.72):
    if not tok or tok in valid_set:
        return None
    # Non correggere numeri, IP, CIDR o simboli molto corti
    if tok[0].isdigit() or '/' in tok or len(tok) < 3:
        return None
    # Se contiene lettere maiuscole è probabilmente un nome di policy/interfaccia
    if any(c.isupper() for c in tok):
        return None
    matches = difflib.get_close_matches(tok, sorted(valid_set), n=1, cutoff=cutoff)
    return matches[0] if matches else None


def _check_typo_line(entry, file_rel):
    """Controlla errori di battitura sulle keyword FRR della riga."""
    if entry.get('ignora') or entry.get('is_header'):
        return None
    norm = entry['norm']
    raw = entry['raw']
    blocco = entry['blocco']
    riga = entry['riga']
    toks = norm.split()
    if not toks:
        return None

    allowed_first = _BLOCK_CMDS.get(blocco, _GLOBAL_CMDS)
    t0 = toks[0]

    # 1. Controllo prima keyword del comando
    # Non segnalare come typo se t0 è una keyword valida di un ALTRO blocco (ci pensa frr.wrong_block)
    all_known_first = set().union(*_BLOCK_CMDS.values())
    if t0 not in allowed_first:
        if t0 not in all_known_first:
            pool = all_known_first if (blocco == 'global' and entry['indent']) else (allowed_first | (_GLOBAL_CMDS if not entry['indent'] else set()))
            cand = _close_keyword(t0, pool, cutoff=0.72)
            if cand:
                nuova = _replace_token_in_raw(raw, t0, cand, occurrence=1)
                return _make_issue(
                    'frr.typo_cmd', 'errore', 'sicuro', file_rel, riga, raw,
                    f"Possibile errore di battitura nel comando '{t0}': intendevi '{cand}'?",
                    [{
                        'etichetta': f"Correggi '{t0}' → '{cand}'",
                        'confidenza': 'sicuro',
                        'tipo': 'replace_line',
                        'riga': riga,
                        'nuova_riga': nuova,
                    }],
                )
        return None

    # 2. Controllo sotto-comandi composti
    check_pairs = []
    if t0 == 'router' and len(toks) >= 2:
        check_pairs.append((1, _ROUTER_PROTOS, 0.72))
    elif t0 == 'ip' and len(toks) >= 2:
        if blocco == 'interface':
            check_pairs.append((1, {'ospf', 'address', 'rip', 'igmp', 'pim', 'irdp'}, 0.72))
            if toks[1] == 'ospf' and len(toks) >= 3:
                check_pairs.append((2, _OSPF_IF_SUBCMDS, 0.72))
        else:
            check_pairs.append((1, _IP_GLOBAL_SUBCMDS, 0.72))
    elif t0 == 'ospf' and blocco == 'interface' and len(toks) >= 2:
        check_pairs.append((1, _OSPF_IF_SUBCMDS, 0.72))
    elif t0 == 'neighbor' and blocco == 'router bgp' and len(toks) >= 3:
        check_pairs.append((2, _NEIGHBOR_SUBCMDS, 0.72))
        if len(toks) >= 5 and toks[2] in ('prefix-list', 'route-map', 'distribute-list', 'filter-list'):
            if toks[4] not in ('in', 'out'):
                cand_d = _close_keyword(toks[4], {'in', 'out'}, cutoff=0.6)
                if cand_d:
                    nuova = _replace_token_in_raw(raw, toks[4], cand_d)
                    return _make_issue(
                        'frr.typo_cmd', 'errore', 'sicuro', file_rel, riga, raw,
                        f"Direzione '{toks[4]}' non valida per neighbor: intendevi '{cand_d}'?",
                        [{
                            'etichetta': f"Correggi '{toks[4]}' → '{cand_d}'",
                            'confidenza': 'sicuro',
                            'tipo': 'replace_line',
                            'riga': riga,
                            'nuova_riga': nuova,
                        }],
                    )
    elif t0 == 'no' and len(toks) >= 2:
        if blocco == 'router bgp':
            if toks[1] == 'bgp' and len(toks) >= 3:
                check_pairs.append((2, _BGP_SUBCMDS, 0.72))
                if len(toks) >= 4 and toks[2] == 'network':
                    check_pairs.append((3, {'import-check'}, 0.72))
            elif toks[1] == 'neighbor' and len(toks) >= 4:
                check_pairs.append((3, _NEIGHBOR_SUBCMDS, 0.72))
            elif toks[1] not in _BLOCK_CMDS['router bgp']:
                check_pairs.append((1, _BLOCK_CMDS['router bgp'] - {'no'}, 0.72))
    elif t0 == 'bgp' and len(toks) >= 2:
        check_pairs.append((1, _BGP_SUBCMDS, 0.72))
    elif t0 == 'redistribute' and len(toks) >= 2:
        check_pairs.append((1, _REDISTRIBUTE_PROTOS, 0.72))
        if len(toks) >= 3 and toks[2] not in ('route-map', 'metric', 'metric-type', 'table'):
            check_pairs.append((2, {'route-map', 'metric', 'metric-type'}, 0.72))
    elif t0 == 'match' and blocco == 'route-map' and len(toks) >= 2:
        check_pairs.append((1, _MATCH_SUBCMDS, 0.72))
        if toks[1] == 'ip' and len(toks) >= 3:
            check_pairs.append((2, {'address', 'next-hop', 'route-source'}, 0.72))
            if toks[2] in ('address', 'next-hop', 'route-source') and len(toks) >= 5:
                # es. match ip address prefx-list NOME
                if toks[3] not in ('prefix-list', 'access-list'):
                    check_pairs.append((3, {'prefix-list'}, 0.72))
    elif t0 == 'set' and blocco == 'route-map' and len(toks) >= 2:
        check_pairs.append((1, _SET_SUBCMDS, 0.72))
    elif t0 == 'auto-cost' and blocco == 'router ospf' and len(toks) >= 2:
        check_pairs.append((1, {'reference-bandwidth'}, 0.72))
    elif t0 == 'default-information' and blocco in ('router ospf', 'router rip') and len(toks) >= 2:
        check_pairs.append((1, {'originate'}, 0.72))
        if len(toks) >= 3 and toks[1] == 'originate':
            check_pairs.append((2, {'always', 'metric', 'metric-type', 'route-map'}, 0.72))

    for pos, valid_set, cutoff in check_pairs:
        tok = toks[pos]
        if tok in valid_set:
            continue
        cand = _close_keyword(tok, valid_set, cutoff=cutoff)
        if cand:
            # Calcola quale occorrenza di `tok` corrisponde a `pos`
            occ = sum(1 for k in range(pos + 1) if toks[k] == tok)
            nuova = _replace_token_in_raw(raw, tok, cand, occurrence=occ)
            return _make_issue(
                'frr.typo_cmd', 'errore', 'sicuro', file_rel, riga, raw,
                f"Possibile errore di battitura '{tok}': intendevi '{cand}'?",
                [{
                    'etichetta': f"Correggi '{tok}' → '{cand}'",
                    'confidenza': 'sicuro',
                    'tipo': 'replace_line',
                    'riga': riga,
                    'nuova_riga': nuova,
                }],
            )

    return None


def _check_wrong_block(entry, file_rel):
    """Rileva comandi collocati nel blocco FRR sbagliato."""
    if entry.get('ignora') or entry.get('is_header'):
        return None
    norm = entry['norm']
    raw = entry['raw']
    blocco = entry['blocco']
    riga = entry['riga']

    # network X area Y fuori da router ospf
    m_net_area = re.match(r'^network\s+(\S+)\s+area\s+(\S+)', norm)
    if m_net_area and blocco != 'router ospf':
        fixes = []
        if blocco in ('router bgp', 'router rip'):
            nuova = _indent_of(raw) + f"network {m_net_area.group(1)}"
            fixes.append({
                'etichetta': f"Rimuovi 'area {m_net_area.group(2)}' (sintassi {blocco})",
                'confidenza': 'proposta',
                'tipo': 'replace_line',
                'riga': riga,
                'nuova_riga': nuova,
            })
        return _make_issue(
            'frr.wrong_block', 'errore', 'proposta', file_rel, riga, raw,
            f"Il comando 'network ... area ...' è sintassi OSPF ma si trova in '{blocco}'.",
            fixes,
        )

    # network X senza 'area' dentro router ospf
    m_net_only = re.match(r'^network\s+(\S+)$', norm)
    if m_net_only and blocco == 'router ospf':
        nuova = raw.rstrip() + ' area 0.0.0.0'
        return _make_issue(
            'frr.wrong_block', 'errore', 'proposta', file_rel, riga, raw,
            "In 'router ospf' il comando 'network' richiede 'area <id>' (es. area 0.0.0.0).",
            [{
                'etichetta': "Aggiungi 'area 0.0.0.0'",
                'confidenza': 'proposta',
                'tipo': 'replace_line',
                'riga': riga,
                'nuova_riga': nuova,
            }],
        )

    # Comandi BGP fuori da router bgp
    if blocco != 'router bgp':
        if re.match(r'^neighbor\s+\S+\s+(remote-as|prefix-list|route-map|update-source|next-hop-self|default-originate|ebgp-multihop)\b', norm):
            return _make_issue(
                'frr.wrong_block', 'errore', 'proposta', file_rel, riga, raw,
                f"Il comando BGP '{norm}' si trova fuori da 'router bgp' (contesto attuale: '{blocco}').",
                [],
            )
        if re.match(r'^no\s+bgp\s+(ebgp-requires-policy|network\s+import-check)\b', norm):
            return _make_issue(
                'frr.wrong_block', 'errore', 'proposta', file_rel, riga, raw,
                f"La direttiva '{norm}' deve stare dentro 'router bgp' (trovata in '{blocco}').",
                [],
            )

    # Comandi OSPF fuori da router ospf
    if blocco != 'router ospf':
        if re.match(r'^(auto-cost\s+reference-bandwidth|area\s+\S+\s+stub)\b', norm):
            return _make_issue(
                'frr.wrong_block', 'errore', 'proposta', file_rel, riga, raw,
                f"Il comando OSPF '{norm}' deve stare dentro 'router ospf' (trovato in '{blocco}').",
                [],
            )

    # match / set fuori da route-map
    if blocco != 'route-map' and re.match(r'^(match|set)\s+', norm):
        return _make_issue(
            'frr.wrong_block', 'errore', 'proposta', file_rel, riga, raw,
            f"Il comando '{norm}' appartiene a una 'route-map' ma si trova in '{blocco}'.",
            [],
        )

    # ospf cost fuori da interface
    if blocco != 'interface' and re.match(r'^(?:ip\s+)?ospf\s+cost\b', norm):
        return _make_issue(
            'frr.wrong_block', 'errore', 'proposta', file_rel, riga, raw,
            f"Il comando '{norm}' va dentro un blocco 'interface <ethX>' (trovato in '{blocco}').",
            [],
        )

    # redistribute fuori da router bgp/ospf/rip
    if blocco not in ('router bgp', 'router ospf', 'router rip') and norm.startswith('redistribute '):
        return _make_issue(
            'frr.wrong_block', 'errore', 'proposta', file_rel, riga, raw,
            f"Il comando '{norm}' deve stare dentro un blocco 'router <proto>' (trovato in '{blocco}').",
            [],
        )

    return None


def _check_bad_cidr(entry, file_rel):
    """Rileva prefissi CIDR con bit host accesi (es. 10.0.1.1/24 -> 10.0.1.0/24)."""
    if entry.get('ignora'):
        return None
    norm = entry['norm']
    raw = entry['raw']
    riga = entry['riga']

    cidr_tok = None
    m = re.match(r'^network\s+(\S+/\d+)\b', norm)
    if m:
        cidr_tok = m.group(1)
    else:
        m = re.match(r'^ip\s+prefix-list\s+\S+\s+(?:seq\s+\d+\s+)?(?:permit|deny)\s+(\S+/\d+)\b', norm)
        if m:
            cidr_tok = m.group(1)
        else:
            m = re.match(r'^(?:ip\s+)?access-list\s+(?:(?:standard|extended)\s+)?\S+\s+(?:seq\s+\d+\s+)?(?:permit|deny)\s+(\S+/\d+)\b', norm)
            if m:
                cidr_tok = m.group(1)
            else:
                m = re.match(r'^(?:ip\s+route|route|aggregate-address)\s+(\S+/\d+)\b', norm)
                if m:
                    cidr_tok = m.group(1)

    if not cidr_tok:
        return None

    try:
        iface = ipaddress.ip_interface(cidr_tok)
    except ValueError:
        return None

    if iface.ip != iface.network.network_address:
        norm_net = str(iface.network)
        nuova = _replace_token_in_raw(raw, cidr_tok, norm_net)
        return _make_issue(
            'frr.bad_cidr', 'errore', 'sicuro', file_rel, riga, raw,
            f"Il prefisso '{cidr_tok}' ha bit host accesi: la rete corretta è '{norm_net}'.",
            [{
                'etichetta': f"Normalizza in {norm_net}",
                'confidenza': 'sicuro',
                'tipo': 'replace_line',
                'riga': riga,
                'nuova_riga': nuova,
            }],
        )
    return None


def _check_prefix_list_ge_le(entry, file_rel):
    """Controlla coerenza di eventuali modificatori ge/le in una prefix-list."""
    if entry.get('ignora'):
        return None
    norm = entry['norm']
    raw = entry['raw']
    riga = entry['riga']
    m = re.match(r'^ip\s+prefix-list\s+(\S+)\s+(.*)', norm)
    if not m or m.group(2).startswith('description'):
        return None
    voce = _voce_prefix_list(m.group(2))
    if not voce:
        return None
    _azione, rete, ge, le = voce
    if rete == 'any':
        return None
    try:
        net = ipaddress.ip_network(rete, strict=False)
    except ValueError:
        return None
    plen = net.prefixlen
    max_len = net.max_prefixlen
    if ge and (ge <= plen or ge > max_len):
        return _make_issue(
            'frr.invalid_prefix_entry', 'errore', 'proposta', file_rel, riga, raw,
            f"Modificatore 'ge {ge}' non valido per '{rete}' (deve soddisfare {plen} < ge <= {max_len}).",
            [],
        )
    if le and (le <= plen or le > max_len):
        return _make_issue(
            'frr.invalid_prefix_entry', 'errore', 'proposta', file_rel, riga, raw,
            f"Modificatore 'le {le}' non valido per '{rete}' (deve soddisfare {plen} < le <= {max_len}).",
            [],
        )
    if ge and le and ge > le:
        return _make_issue(
            'frr.invalid_prefix_entry', 'errore', 'proposta', file_rel, riga, raw,
            f"Intervallo prefissi non valido: 'ge {ge}' è maggiore di 'le {le}'.",
            [],
        )
    return None


def _policy_block_lines(righe, tipo, nome):
    """Restituisce i numeri di riga (1-based) appartenenti alla definizione di una policy."""
    out = []
    if tipo == 'prefix-list':
        rx = re.compile(rf'^\s*ip(?:v6)?\s+prefix-list\s+{re.escape(nome)}\b')
        for idx, l in enumerate(righe, 1):
            if rx.match(l):
                out.append(idx)
    elif tipo == 'access-list':
        rx = re.compile(rf'^\s*(?:ip\s+)?access-list\s+{re.escape(nome)}\b')
        for idx, l in enumerate(righe, 1):
            if rx.match(l):
                out.append(idx)
    elif tipo == 'route-map':
        dentro = False
        for idx, l in enumerate(righe, 1):
            s = ' '.join(l.split())
            if re.match(rf'^route-map\s+{re.escape(nome)}\s+(permit|deny)\s+\d+', s):
                dentro = True
                out.append(idx)
                continue
            if dentro:
                if not s:
                    continue
                if re.match(r'^(match|set|on-match|call|continue|description)\b', s):
                    out.append(idx)
                    continue
                dentro = False
    return out


def _symbol_used_elsewhere(righe, tipo, nome):
    """True se la policy `(tipo, nome)` è referenziata almeno una volta nel file."""
    for l in righe:
        s = ' '.join(l.split())
        if not s or s.startswith('!'):
            continue
        if tipo == 'route-map':
            if re.search(rf'\broute-map\s+{re.escape(nome)}\b', s) and not re.match(
                rf'^route-map\s+{re.escape(nome)}\s+(permit|deny)\s+\d+', s
            ):
                return True
        elif tipo == 'prefix-list':
            if re.search(rf'\bprefix-list\s+{re.escape(nome)}\b', s) and not re.match(
                rf'^ip(?:v6)?\s+prefix-list\s+{re.escape(nome)}\b', s
            ):
                return True
        elif tipo == 'access-list':
            if (
                re.search(rf'\bdistribute-list\s+{re.escape(nome)}\b', s)
                or re.search(rf'\bmatch\s+ip\s+address\s+{re.escape(nome)}\b', s)
            ) and not re.match(rf'^(?:ip\s+)?access-list\s+{re.escape(nome)}\b', s):
                return True
    return False


def _integrate_riferimenti_frr(righe, file_rel, lab_subnets=None):
    """Integra i risultati di analyzer.riferimenti_frr nel contratto strutturato."""
    refs = riferimenti_frr(righe)
    issues = []

    # Raccogli le definizioni suggerite per un chiamante rotto: non proporre delete su quelle!
    suggerite_da_rotti = set()
    for x in refs:
        m = re.search(r"(route-map|prefix-list|access-list) (\S+) non è definita.*Forse intendevi (\S+) \(riga", x['messaggio'])
        if m:
            suggerite_da_rotti.add((m.group(1), m.group(3)))

    for x in refs:
        riga = x['riga']
        raw = righe[riga - 1] if 1 <= riga <= len(righe) else x.get('testo', '')
        msg = x['messaggio']
        grav = x['gravita']

        # Caso A: voce prefix-list scartata (senza maschera / malformata)
        m_pl = re.search(r"'([^']+)' non è valido in una prefix-list", msg)
        if m_pl:
            valore = m_pl.group(1)
            m_prop = re.search(r"Forse intendevi (\S+)\?", msg)
            fixes = []
            conf = 'proposta'
            if m_prop:
                proposta = m_prop.group(1)
                nuova = _replace_token_in_raw(raw, valore, proposta)
                if nuova != raw:
                    conf = 'sicuro'
                    fixes.append({
                        'etichetta': f"Sostituisci '{valore}' → '{proposta}'",
                        'confidenza': 'sicuro',
                        'tipo': 'replace_line',
                        'riga': riga,
                        'nuova_riga': nuova,
                    })
            elif lab_subnets:
                cands = [s for s in lab_subnets if _contiene(s, valore)]
                if len(cands) == 1:
                    nuova = _replace_token_in_raw(raw, valore, cands[0])
                    if nuova != raw:
                        fixes.append({
                            'etichetta': f"Usa subnet del lab '{cands[0]}'",
                            'confidenza': 'proposta',
                            'tipo': 'replace_line',
                            'riga': riga,
                            'nuova_riga': nuova,
                        })
            issues.append(_make_issue(
                'frr.invalid_prefix_entry', grav, conf, file_rel, riga, raw, msg, fixes
            ))
            continue

        # Caso B: riferimento a policy non definita (con o senza close match)
        m_undef = re.search(r"(route-map|prefix-list|access-list) (\S+) non è definita", msg)
        if m_undef:
            tipo, nome = m_undef.group(1), m_undef.group(2)
            m_sim = re.search(r"Forse intendevi (\S+) \(riga (\d+)\)\?", msg)
            fixes = []
            if m_sim:
                sim_nome = m_sim.group(1)
                nuova = _replace_token_in_raw(raw, nome, sim_nome)
                if nuova != raw:
                    fixes.append({
                        'etichetta': f"Usa '{sim_nome}'",
                        'confidenza': 'sicuro',
                        'tipo': 'replace_line',
                        'riga': riga,
                        'nuova_riga': nuova,
                    })
                if not _symbol_used_elsewhere(righe, tipo, sim_nome):
                    fixes.append({
                        'etichetta': f"Rinomina definizione '{sim_nome}' → '{nome}'",
                        'confidenza': 'proposta',
                        'tipo': 'rename_symbol',
                        'tipo_simbolo': tipo,
                        'da': sim_nome,
                        'a': nome,
                    })
                issues.append(_make_issue(
                    'frr.ref_typo', grav, 'sicuro' if fixes else 'proposta',
                    file_rel, riga, raw, msg, fixes
                ))
            else:
                issues.append(_make_issue(
                    'frr.ref_undefined', grav, 'proposta', file_rel, riga, raw, msg, []
                ))
            continue

        # Caso C: network BGP bloccata in uscita da una prefix-list
        m_blk = re.search(r"questo router annuncia (\S+) \(riga \d+\), ma la prefix-list (\S+) non la lascia passare", msg)
        if m_blk:
            rete, pl_nome = m_blk.group(1), m_blk.group(2)
            pl_lines = _policy_block_lines(righe, 'prefix-list', pl_nome)
            fixes = []
            if pl_lines:
                fixes.append({
                    'etichetta': f"Aggiungi 'permit {rete}' a {pl_nome}",
                    'confidenza': 'proposta',
                    'tipo': 'insert_after',
                    'riga': pl_lines[-1],
                    'righe': [f"ip prefix-list {pl_nome} permit {rete}"],
                })
            issues.append(_make_issue(
                'bgp.prefix_list_blocks_network', grav, 'proposta', file_rel, riga, raw, msg, fixes
            ))
            continue

        # Caso D: policy definita ma mai usata
        m_un = re.search(r"(route-map|prefix-list|access-list) (\S+) è definita ma non è usata", msg)
        if m_un:
            tipo, nome = m_un.group(1), m_un.group(2)
            fixes = []
            if (tipo, nome) not in suggerite_da_rotti:
                righe_del = _policy_block_lines(righe, tipo, nome)
                if righe_del:
                    fixes.append({
                        'etichetta': f"Rimuovi {tipo} inutilizzata '{nome}'",
                        'confidenza': 'proposta',
                        'tipo': 'delete_line',
                        'riga': righe_del[0],
                        'righe_num': righe_del,
                    })
            issues.append(_make_issue(
                'frr.unused_policy', grav, 'proposta', file_rel, riga, raw, msg, fixes
            ))
            continue

        # Fallback generico
        issues.append(_make_issue(
            'frr.ref_other', grav, 'proposta', file_rel, riga, raw, msg, []
        ))

    return issues


def _analizza_livello1(righe, parsed, file_rel, lab_subnets=None):
    issues = []

    # 1. Typo, wrong_block, bad_cidr, prefix-list ge/le, duplicate_line
    seen_in_block = {}
    bgp_blocks = []  # lista di dict per ogni router bgp

    cur_bgp = None
    for entry in parsed:
        if entry.get('ignora'):
            continue
        riga = entry['riga']
        norm = entry['norm']
        raw = entry['raw']
        blocco = entry['blocco']
        bid = entry['block_id']

        if entry.get('is_header') and blocco == 'router bgp':
            cur_bgp = {
                'header_riga': riga,
                'asn': entry['header_info'].get('asn', ''),
                'has_ebgp_policy': False,
                'has_import_check': False,
                'has_network': False,
                'neighbors': [],  # (riga, ip, remote_as, raw, indent)
                'update_sources': set(),
            }
            bgp_blocks.append(cur_bgp)
        elif blocco != 'router bgp':
            cur_bgp = None

        if cur_bgp is not None and not entry.get('is_header'):
            if norm == 'no bgp ebgp-requires-policy':
                cur_bgp['has_ebgp_policy'] = True
            elif norm == 'no bgp network import-check':
                cur_bgp['has_import_check'] = True
            elif norm.startswith('network '):
                cur_bgp['has_network'] = True
            m_nb = re.match(r'^neighbor\s+(\S+)\s+remote-as\s+(\S+)$', norm)
            if m_nb:
                cur_bgp['neighbors'].append((riga, m_nb.group(1), m_nb.group(2), raw, entry['indent'] or '    '))
            m_us = re.match(r'^neighbor\s+(\S+)\s+update-source\s+\S+', norm)
            if m_us:
                cur_bgp['update_sources'].add(m_us.group(1))

        # Typo comando
        typo_issue = _check_typo_line(entry, file_rel)
        if typo_issue:
            issues.append(typo_issue)
            continue

        # Blocco errato
        wb_issue = _check_wrong_block(entry, file_rel)
        if wb_issue:
            issues.append(wb_issue)

        # Bit host accesi in CIDR
        cidr_issue = _check_bad_cidr(entry, file_rel)
        if cidr_issue:
            issues.append(cidr_issue)

        # Modificatori ge/le invalidi in prefix-list
        pl_issue = _check_prefix_list_ge_le(entry, file_rel)
        if pl_issue:
            issues.append(pl_issue)

        # Righe duplicate identiche nello stesso blocco
        if not entry.get('is_header') and norm not in ('exit', 'end', 'exit-address-family'):
            key = (bid, norm)
            if key in seen_in_block:
                first_riga = seen_in_block[key]
                issues.append(_make_issue(
                    'frr.duplicate_line', 'avviso', 'sicuro', file_rel, riga, raw,
                    f"Riga duplicata (identica alla riga {first_riga} nello stesso blocco).",
                    [{
                        'etichetta': f"Elimina riga duplicata ({riga})",
                        'confidenza': 'sicuro',
                        'tipo': 'delete_line',
                        'riga': riga,
                    }],
                ))
            else:
                seen_in_block[key] = riga

    # 2. Direttive BGP obbligatorie
    cfg_bgp = _analizza_frr(righe)
    senza_policy = [ip for ip, asn in cfg_bgp['neighbors'].items() if str(asn) != str(cfg_bgp['asn'])
                    and not {'in', 'out'} <= {d for _, _, d in cfg_bgp['link'].get(ip, [])}]
    for b in bgp_blocks:
        if not b['has_ebgp_policy'] and senza_policy:
            issues.append(_make_issue(
                'bgp.missing_ebgp_policy', 'avviso', 'sicuro', file_rel, b['header_riga'],
                righe[b['header_riga'] - 1],
                "Manca 'no bgp ebgp-requires-policy' e i neighbor eBGP " + ', '.join(senza_policy)
                + " non hanno una policy in entrambe le direzioni: in FRR >= 7.4 senza policy non si scambiano rotte.",
                [{
                    'etichetta': "Aggiungi 'no bgp ebgp-requires-policy'",
                    'confidenza': 'sicuro',
                    'tipo': 'insert_after',
                    'riga': b['header_riga'],
                    'righe': ['    no bgp ebgp-requires-policy'],
                }],
            ))
        if b['has_network'] and not b['has_import_check']:
            issues.append(_make_issue(
                'bgp.missing_import_check', 'info', 'sicuro', file_rel, b['header_riga'],
                righe[b['header_riga'] - 1],
                "Manca 'no bgp network import-check' nel blocco 'router bgp': le reti aggregate non presenti esattamente nella RIB potrebbero non essere annunciate.",
                [{
                    'etichetta': "Aggiungi 'no bgp network import-check'",
                    'confidenza': 'sicuro',
                    'tipo': 'insert_after',
                    'riga': b['header_riga'],
                    'righe': ['    no bgp network import-check'],
                }],
            ))

    # 3. Integrazione riferimenti_frr (route-map, prefix-list, access-list)
    issues.extend(_integrate_riferimenti_frr(righe, file_rel, lab_subnets=lab_subnets))

    return issues, bgp_blocks


def _analizza_livello2_e_3(righe, parsed, bgp_blocks, file_rel, lab_path, dev):
    issues = []
    if not lab_path or not dev or not os.path.isfile(os.path.join(lab_path, 'lab.conf')):
        return issues

    disp = leggi_dispositivi(lab_path)
    if dev not in disp:
        return issues
    d = disp[dev]
    own = _proprietari(disp)

    # --- LIVELLO 2: coerenza del singolo dispositivo ---
    # 2.1 daemon.disabled
    daemons_path = os.path.join(lab_path, dev, 'etc', 'frr', 'daemons')
    daemons_txt = '\n'.join(_leggi_righe(daemons_path)) if os.path.exists(daemons_path) else ''
    enabled_daemons = set(re.findall(r'^\s*(zebra|bgpd|ospfd|ripd)\s*=\s*yes\b', daemons_txt, re.M))

    proto_headers = {}
    for entry in parsed:
        if entry.get('is_header') and entry['blocco'] in ('router bgp', 'router ospf', 'router rip'):
            proto = entry['blocco'].split()[1]
            proto_headers.setdefault(proto, entry['riga'])

    for proto, h_riga in proto_headers.items():
        dname = f"{proto}d"
        if dname not in enabled_daemons:
            issues.append(_make_issue(
                'daemon.disabled', 'errore', 'sicuro', file_rel, h_riga, righe[h_riga - 1],
                f"Il blocco 'router {proto}' è configurato ma '{dname}=yes' non è abilitato in {dev}/etc/frr/daemons.",
                [{
                    'etichetta': f"Abilita {dname}=yes in daemons",
                    'confidenza': 'sicuro',
                    'tipo': 'lab_op',
                    'op': 'apply_diag_fix',
                    'params': {'kind': 'enable_daemon', 'nome': dev, 'daemon': dname},
                }],
            ))

    # 2.2 startup.missing_frr
    if proto_headers:
        st_path = os.path.join(lab_path, f"{dev}.startup")
        st_lines = _leggi_righe(st_path) if os.path.exists(st_path) else []
        has_frr_start = any(
            _RE_START_FRR.match(l) for l in st_lines if not l.lstrip().startswith('#')
        )
        if not has_frr_start:
            first_riga = min(proto_headers.values())
            issues.append(_make_issue(
                'startup.missing_frr', 'errore', 'sicuro', f"{dev}.startup", first_riga,
                righe[first_riga - 1],
                f"FRR è configurato ma {dev}.startup non avvia il servizio ('systemctl start frr' assente).",
                [{
                    'etichetta': f"Aggiungi 'systemctl start frr' in {dev}.startup",
                    'confidenza': 'sicuro',
                    'tipo': 'lab_op',
                    'op': 'apply_diag_fix',
                    'params': {'kind': 'add_startup_frr', 'nome': dev},
                }],
            ))

    # 2.3 frr.unknown_interface
    known_ifaces = {it['dev'] for it in d['interfacce']} | {'lo', 'lo0'}
    for idx_e, entry in enumerate(parsed):
        if entry.get('is_header') and entry['blocco'] == 'interface':
            ifname = entry['header_info'].get('iface', '')
            if ifname and ifname not in known_ifaces:
                # Trova tutte le righe del blocco interface
                bid = entry['block_id']
                blk_righe = [e['riga'] for e in parsed if e['block_id'] == bid and not e.get('ignora')]
                fixes = []
                for it in d['interfacce']:
                    nuova = _replace_token_in_raw(entry['raw'], ifname, it['dev'])
                    fixes.append({
                        'etichetta': f"Sostituisci con {it['dev']} (LAN {it['lan']})",
                        'confidenza': 'proposta',
                        'tipo': 'replace_line',
                        'riga': entry['riga'],
                        'nuova_riga': nuova,
                    })
                fixes.append({
                    'etichetta': f"Rimuovi blocco 'interface {ifname}'",
                    'confidenza': 'proposta',
                    'tipo': 'delete_line',
                    'riga': entry['riga'],
                    'righe_num': blk_righe or [entry['riga']],
                })
                issues.append(_make_issue(
                    'frr.unknown_interface', 'errore', 'proposta', file_rel, entry['riga'], entry['raw'],
                    f"Interfaccia '{ifname}' non esiste in lab.conf per {dev} (disponibili: {', '.join(sorted(it['dev'] for it in d['interfacce'])) or 'nessuna'}).",
                    fixes,
                ))

    # --- LIVELLO 3: coerenza cross-router ---
    # Costruisci mappa subnet/LAN -> router BGP
    dev_if_nets = []
    for it in d['interfacce']:
        if it['ip']:
            try:
                dev_if_nets.append((it['lan'], ipaddress.ip_interface(it['ip'])))
            except ValueError:
                pass

    lan_bgp_peers = {}
    for rn, rd in disp.items():
        if rn == dev or rd['tipo'] != 'router':
            continue
        if not rd['asn'] and 'bgpd' not in rd['demoni']:
            continue
        for it in rd['interfacce']:
            if it['ip']:
                lan_bgp_peers.setdefault(it['lan'], []).append((rn, it['ip'].split('/')[0], rd['asn']))

    dev_own_ips = {it['ip'].split('/')[0] for it in d['interfacce'] if it['ip']} | {
        lb.split('/')[0] for lb in d['loopback']
    }
    peer_cfgs = {}

    def _get_peer_cfg(peer_name):
        if peer_name not in peer_cfgs:
            fp = os.path.join(lab_path, peer_name, 'etc', 'frr', 'frr.conf')
            peer_cfgs[peer_name] = _analizza_frr(_leggi_righe(fp)) if os.path.exists(fp) else None
        return peer_cfgs[peer_name]

    for b in bgp_blocks:
        my_asn = b['asn']
        configured_nb_ips = {nb[1] for nb in b['neighbors']}
        for nb_riga, nb_ip, nb_ras, nb_raw, nb_indent in b['neighbors']:
            chi = own.get(nb_ip)
            if chi is None:
                # 3.2 bgp.unknown_neighbor
                cands = []
                try:
                    nb_addr = ipaddress.ip_address(nb_ip)
                except ValueError:
                    nb_addr = None
                if nb_addr is not None:
                    for lan_name, my_iface in dev_if_nets:
                        if nb_addr in my_iface.network:
                            for rn, rip, ras in lan_bgp_peers.get(lan_name, []):
                                if rip not in configured_nb_ips:
                                    cands.append((rn, rip, ras, lan_name))
                # Deduplica candidati
                cands = list(dict.fromkeys(cands))
                fixes = []
                conf = 'proposta'
                if len(cands) == 1:
                    rn, rip, ras, lan_name = cands[0]
                    nuova = _replace_token_in_raw(nb_raw, nb_ip, rip)
                    if ras and ras != nb_ras:
                        nuova = re.sub(rf'(\bremote-as\s+){re.escape(nb_ras)}\b', rf'\g<1>{ras}', nuova, count=1)
                    conf = 'sicuro'
                    fixes.append({
                        'etichetta': f"Usa {rip} ({rn}, LAN {lan_name})",
                        'confidenza': 'sicuro',
                        'tipo': 'replace_line',
                        'riga': nb_riga,
                        'nuova_riga': nuova,
                    })
                    msg = f"neighbor {nb_ip} non esiste nel lab: sulla stessa LAN ({lan_name}) c'è {rn} ({rip})."
                elif len(cands) > 1:
                    for rn, rip, ras, lan_name in cands:
                        nuova = _replace_token_in_raw(nb_raw, nb_ip, rip)
                        if ras and ras != nb_ras:
                            nuova = re.sub(rf'(\bremote-as\s+){re.escape(nb_ras)}\b', rf'\g<1>{ras}', nuova, count=1)
                        fixes.append({
                            'etichetta': f"Usa {rip} ({rn})",
                            'confidenza': 'proposta',
                            'tipo': 'replace_line',
                            'riga': nb_riga,
                            'nuova_riga': nuova,
                        })
                    msg = f"neighbor {nb_ip} non esiste nel lab; candidati BGP sulla stessa LAN: {', '.join(f'{r} ({i})' for r, i, _, _ in cands)}."
                else:
                    msg = f"neighbor {nb_ip} non corrisponde a nessun indirizzo IP del lab (refuso?)."
                issues.append(_make_issue(
                    'bgp.unknown_neighbor', 'errore', conf, file_rel, nb_riga, nb_raw, msg, fixes
                ))
                continue

            peer_name, peer_dev, peer_lan = chi
            if peer_name == dev:
                issues.append(_make_issue(
                    'bgp.unknown_neighbor', 'errore', 'proposta', file_rel, nb_riga, nb_raw,
                    f"neighbor {nb_ip} è un indirizzo di {dev} stesso.",
                    [{
                        'etichetta': f"Elimina riga neighbor verso se stesso ({nb_riga})",
                        'confidenza': 'proposta',
                        'tipo': 'delete_line',
                        'riga': nb_riga,
                    }],
                ))
                continue

            peer_d = disp.get(peer_name)
            peer_asn = (peer_d or {}).get('asn')

            # 3.1 bgp.wrong_remote_as
            if peer_asn and str(peer_asn) != str(nb_ras):
                nuova = re.sub(rf'(\bremote-as\s+){re.escape(nb_ras)}\b', rf'\g<1>{peer_asn}', nb_raw, count=1)
                issues.append(_make_issue(
                    'bgp.wrong_remote_as', 'errore', 'sicuro', file_rel, nb_riga, nb_raw,
                    f"remote-as {nb_ras} non corrisponde all'AS reale di {peer_name} ({peer_asn}).",
                    [{
                        'etichetta': f"Imposta remote-as {peer_asn}",
                        'confidenza': 'sicuro',
                        'tipo': 'replace_line',
                        'riga': nb_riga,
                        'nuova_riga': nuova,
                    }],
                ))

            # 3.4 bgp.ibgp_missing_update_source
            eff_peer_asn = str(peer_asn or nb_ras)
            if my_asn and eff_peer_asn == str(my_asn) and peer_dev == 'lo' and d['loopback']:
                if nb_ip not in b['update_sources']:
                    issues.append(_make_issue(
                        'bgp.ibgp_missing_update_source', 'errore', 'sicuro', file_rel, nb_riga, nb_raw,
                        f"Sessione iBGP verso la loopback di {peer_name} ({nb_ip}) senza 'update-source lo': la sessione non si stabilirà.",
                        [{
                            'etichetta': f"Aggiungi 'neighbor {nb_ip} update-source lo'",
                            'confidenza': 'sicuro',
                            'tipo': 'insert_after',
                            'riga': nb_riga,
                            'righe': [f"{nb_indent}neighbor {nb_ip} update-source lo"],
                        }],
                    ))

            # 3.3 bgp.asymmetric_peer
            if peer_d and peer_d['frr']:
                pcfg = _get_peer_cfg(peer_name)
                if pcfg and pcfg.get('asn') and not (set(pcfg['neighbors'].keys()) & dev_own_ips):
                    # Calcola l'IP locale di dev da usare su peer
                    my_ip_for_peer = None
                    use_lo = False
                    if peer_lan is not None:
                        my_ip_for_peer = next(
                            (it['ip'].split('/')[0] for it in d['interfacce'] if it['lan'] == peer_lan and it['ip']),
                            None,
                        )
                    elif peer_dev == 'lo' and d['loopback']:
                        my_ip_for_peer = d['loopback'][0].split('/')[0]
                        use_lo = True
                    if not my_ip_for_peer:
                        my_ip_for_peer = next((it['ip'].split('/')[0] for it in d['interfacce'] if it['ip']), None)

                    fixes = []
                    if my_ip_for_peer and my_asn:
                        fixes.append({
                            'etichetta': f"Aggiungi neighbor {my_ip_for_peer} (AS{my_asn}) su {peer_name}",
                            'confidenza': 'proposta',
                            'tipo': 'lab_op',
                            'op': 'apply_diag_fix',
                            'params': {
                                'kind': 'add_peer_neighbor',
                                'peer': peer_name,
                                'neighbor_ip': my_ip_for_peer,
                                'remote_as': str(my_asn),
                                'description': f"Router {dev}",
                                'update_source': 'lo' if use_lo else '',
                            },
                        })
                    issues.append(_make_issue(
                        'bgp.asymmetric_peer', 'avviso', 'proposta', file_rel, nb_riga, nb_raw,
                        f"Peering BGP asimmetrico: {dev} punta a {peer_name} ({nb_ip}), ma {peer_name} non ha il neighbor speculare verso {dev}.",
                        fixes,
                    ))

    # 3.5 ospf.missing_auto_cost: tolta (c'è già l'avviso dell'analyzer)

    return issues


def analizza_frr_avanzato(content, lab_path=None, dev=None):
    """Analisi diagnostica deterministica multi-livello per frr.conf.
    Esegue Livello 1 sempre; se `lab_path` e `dev` sono forniti esegue anche Livelli 2 e 3.
    """
    text = str(content or '').replace('\r\n', '\n').replace('\r', '\n')
    righe = text.split('\n')
    if righe and righe[-1] == '':
        righe.pop()

    file_rel = f"{dev}/etc/frr/frr.conf" if dev else "frr.conf"

    lab_subnets = None
    if lab_path and os.path.isfile(os.path.join(lab_path, 'lab.conf')):
        try:
            disp = leggi_dispositivi(lab_path)
            lab_subnets = sorted({
                _norm_net(it['ip'])
                for dd in disp.values() for it in dd['interfacce']
                if it['ip'] and '/' in it['ip']
            })
        except Exception:
            lab_subnets = None

    parsed = _parse_blocks(righe)
    issues, bgp_blocks = _analizza_livello1(righe, parsed, file_rel, lab_subnets=lab_subnets)
    if lab_path and dev:
        issues.extend(_analizza_livello2_e_3(righe, parsed, bgp_blocks, file_rel, lab_path, dev))

    # Deduplicazione (id_regola, riga, messaggio)
    seen = set()
    out = []
    for x in issues:
        k = (x['id_regola'], x['riga'], x['messaggio'])
        if k in seen:
            continue
        seen.add(k)
        out.append(x)

    out.sort(key=lambda x: (x['riga'] or 0, 0 if x['gravita'] == 'errore' else 1, x['id_regola']))
    return out


def _rename_symbol_in_lines(righe, tipo_simbolo, da, a):
    """Rinomina tutte le occorrenze coerenti di una route-map / prefix-list / access-list."""
    if not da or not a or da == a:
        return list(righe)
    out = []
    for l in righe:
        s = ' '.join(l.split())
        if tipo_simbolo == 'route-map':
            if re.search(rf'\broute-map\s+{re.escape(da)}\b', s):
                l = re.sub(rf'(\broute-map\s+){re.escape(da)}(?=\s|$)', rf'\g<1>{a}', l)
        elif tipo_simbolo == 'prefix-list':
            if re.search(rf'\bprefix-list\s+{re.escape(da)}\b', s) or re.search(rf'\bdistribute-list\s+prefix\s+{re.escape(da)}\b', s):
                l = re.sub(rf'(\bprefix-list\s+){re.escape(da)}(?=\s|$)', rf'\g<1>{a}', l)
                l = re.sub(rf'(\bdistribute-list\s+prefix\s+){re.escape(da)}(?=\s|$)', rf'\g<1>{a}', l)
        elif tipo_simbolo == 'access-list':
            if (
                re.search(rf'\baccess-list\s+{re.escape(da)}\b', s)
                or re.search(rf'\bdistribute-list\s+{re.escape(da)}\b', s)
                or re.search(rf'\bmatch\s+ip\s+address\s+{re.escape(da)}\b', s)
            ):
                l = re.sub(rf'(\baccess-list\s+){re.escape(da)}(?=\s|$)', rf'\g<1>{a}', l)
                l = re.sub(rf'(\bdistribute-list\s+){re.escape(da)}(?=\s|$)', rf'\g<1>{a}', l)
                l = re.sub(rf'(\bmatch\s+ip\s+address\s+){re.escape(da)}(?=\s|$)', rf'\g<1>{a}', l)
        out.append(l)
    return out


def applica_fix_testo(content, fix):
    """Applica un fix testuale puro (`replace_line`, `insert_after`, `delete_line`, `rename_symbol`)."""
    if not fix or not isinstance(fix, dict):
        return content
    raw_text = str(content or '').replace('\r\n', '\n').replace('\r', '\n')
    had_trailing_nl = raw_text.endswith('\n')
    righe = raw_text.split('\n')
    if had_trailing_nl and righe and righe[-1] == '':
        righe.pop()

    tipo = fix.get('tipo')
    if tipo == 'replace_line':
        idx = int(fix.get('riga') or 0) - 1
        if 0 <= idx < len(righe) and fix.get('nuova_riga') is not None:
            righe[idx] = str(fix['nuova_riga'])
    elif tipo == 'insert_after':
        riga = int(fix.get('riga') or 0)
        nuove = [str(x) for x in (fix.get('righe') or [])]
        if 0 <= riga <= len(righe) and nuove:
            righe[riga:riga] = nuove
    elif tipo == 'delete_line':
        righe_num = fix.get('righe_num')
        if righe_num:
            to_del = sorted({int(n) for n in righe_num if 1 <= int(n) <= len(righe)}, reverse=True)
            for n in to_del:
                del righe[n - 1]
        else:
            idx = int(fix.get('riga') or 0) - 1
            if 0 <= idx < len(righe):
                del righe[idx]
    elif tipo == 'rename_symbol':
        righe = _rename_symbol_in_lines(
            righe, fix.get('tipo_simbolo', ''), fix.get('da', ''), fix.get('a', '')
        )

    res = '\n'.join(righe)
    if had_trailing_nl and res:
        res += '\n'
    return res


def applica_fix_sicuri_testo(content, issues):
    """Applica in blocco solo i fix locali con `confidenza == 'sicuro'`,
    ordinandoli dal basso verso l'alto per preservare gli indici di riga."""
    local_safe = []
    seen_replace_or_del = set()
    seen_insert = set()
    for item in issues or []:
        for fx in item.get('fixes') or []:
            if fx.get('confidenza') != 'sicuro':
                continue
            tipo = fx.get('tipo')
            if tipo not in ('replace_line', 'insert_after', 'delete_line'):
                continue
            riga = int(fx.get('riga') or 0)
            if tipo in ('replace_line', 'delete_line'):
                if riga in seen_replace_or_del:
                    continue
                seen_replace_or_del.add(riga)
            elif tipo == 'insert_after':
                key = (riga, tuple(fx.get('righe') or []))
                if key in seen_insert:
                    continue
                seen_insert.add(key)
            local_safe.append(fx)
            break  # al massimo un fix sicuro per singolo issue

    # Ordine decrescente di riga; a parità di riga: insert_after prima di replace_line prima di delete_line
    prio = {'insert_after': 2, 'replace_line': 1, 'delete_line': 0}
    local_safe.sort(key=lambda f: (int(f.get('riga') or 0), prio.get(f.get('tipo'), 0)), reverse=True)

    out = content
    for fx in local_safe:
        out = applica_fix_testo(out, fx)
    return out


def _wrap_local_fix_as_lab_op(dev, fix):
    """Converte un fix locale FRR in una lab_op transazionale per modalDiagnostica."""
    if fix.get('tipo') == 'lab_op':
        return fix
    return {
        'etichetta': fix.get('etichetta', 'Applica fix'),
        'confidenza': fix.get('confidenza', 'proposta'),
        'tipo': 'lab_op',
        'op': 'apply_diag_fix',
        'params': {
            'kind': 'frr_text_fix',
            'nome': dev,
            'fix': dict(fix),
        },
    }


def diagnosi_dispositivo(lab_path, dev):
    """Raccoglie tutti i problemi azionabili di un dispositivo (FRR, daemons, startup, gateway, nomi)."""
    if not lab_path or not dev or not os.path.isfile(os.path.join(lab_path, 'lab.conf')):
        return []
    disp = leggi_dispositivi(lab_path)
    if dev not in disp:
        return []
    d = disp[dev]
    own = _proprietari(disp)
    out = []

    # 1. Nome Kathará non valido
    if not nome_kathara_valido(dev):
        prop = correggi_nome_kathara(dev)
        out.append(_make_issue(
            'kathara.invalid_name', 'errore', 'sicuro', 'lab.conf', None, dev,
            f"Nome '{dev}' non valido per Kathará (solo lettere minuscole, cifre e _): suggerito '{prop}'.",
            [{
                'etichetta': f"Rinomina in '{prop}'",
                'confidenza': 'sicuro',
                'tipo': 'lab_op',
                'op': 'fix_names',
                'params': {},
            }],
        ))

    # 2. Problemi FRR (Livelli 1, 2, 3) convertendo i fix locali in lab_op transazionali
    frr_path = os.path.join(lab_path, dev, 'etc', 'frr', 'frr.conf')
    if d['frr'] and os.path.exists(frr_path):
        with open(frr_path, 'r', encoding='utf-8', errors='replace') as fh:
            frr_text = fh.read()
        for item in analizza_frr_avanzato(frr_text, lab_path=lab_path, dev=dev):
            wrapped = dict(item)
            wrapped['fixes'] = [_wrap_local_fix_as_lab_op(dev, fx) for fx in item.get('fixes') or []]
            out.append(wrapped)

    # 3. Host / WWW / DNS: gateway mancante o errato
    if d['tipo'] != 'router':
        # Trova router sulle stesse LAN di dev
        gw_cands = []
        for it in d['interfacce']:
            for rn, rd in disp.items():
                if rn == dev or rd['tipo'] != 'router':
                    continue
                for rit in rd['interfacce']:
                    if rit['lan'] == it['lan'] and rit['ip']:
                        gw_cands.append((rn, rit['ip'].split('/')[0], it['dev'], it['lan']))
        gw_cands = list(dict.fromkeys(gw_cands))

        if not d['gateway'] and any(it['ip'] for it in d['interfacce']):
            fixes = [
                {
                    'etichetta': f"Imposta gateway {rip} ({rn}, LAN {lan})",
                    'confidenza': 'proposta',
                    'tipo': 'lab_op',
                    'op': 'change_gateway',
                    'params': {'nome': dev, 'gateway': rip, 'dev': idev},
                }
                for rn, rip, idev, lan in gw_cands
            ]
            out.append(_make_issue(
                'host.missing_gateway', 'avviso', 'proposta', f"{dev}.startup", None, '',
                f"{dev}: nessun default gateway configurato, non raggiungerà reti esterne alla sua LAN.",
                fixes,
            ))
        elif d['gateway']:
            chi_gw = own.get(d['gateway'])
            gw_ok = True
            try:
                gw_ip = ipaddress.ip_address(d['gateway'])
                in_net = any(
                    it['ip'] and gw_ip in ipaddress.ip_interface(it['ip']).network
                    for it in d['interfacce']
                )
                if not in_net or chi_gw is None or chi_gw[0] == dev:
                    gw_ok = False
            except ValueError:
                gw_ok = False
            if not gw_ok:
                fixes = [
                    {
                        'etichetta': f"Imposta gateway {rip} ({rn})",
                        'confidenza': 'proposta',
                        'tipo': 'lab_op',
                        'op': 'change_gateway',
                        'params': {'nome': dev, 'gateway': rip, 'dev': idev},
                    }
                    for rn, rip, idev, _ in gw_cands
                ]
                out.append(_make_issue(
                    'host.bad_gateway', 'errore', 'proposta', f"{dev}.startup", None, f"gateway {d['gateway']}",
                    f"{dev}: il default gateway '{d['gateway']}' non è raggiungibile o non appartiene a un router sulla sua LAN.",
                    fixes,
                ))

    # 4. WWW senza avvio apache2
    if d['tipo'] == 'www' and not d['apache']:
        out.append(_make_issue(
            'www.missing_apache', 'errore', 'sicuro', f"{dev}.startup", None, '',
            f"{dev}: server WWW senza 'systemctl start apache2' in {dev}.startup.",
            [{
                'etichetta': f"Aggiungi 'systemctl start apache2' in {dev}.startup",
                'confidenza': 'sicuro',
                'tipo': 'lab_op',
                'op': 'apply_diag_fix',
                'params': {'kind': 'add_startup_apache', 'nome': dev},
            }],
        ))

    # 5. iBGP incompleto (sempre 'proposta', mai 'sicuro' per rispettare scenari butterfly)
    if d['tipo'] == 'router' and d['asn'] and d['frr']:
        stessi_as = [rn for rn, rd in disp.items() if rd['tipo'] == 'router' and rd['asn'] == d['asn'] and rn != dev]
        if stessi_as:
            cfg_dev = _analizza_frr(_leggi_righe(frr_path))
            mancanti = []
            for altro in sorted(stessi_as):
                ips_altro = {it['ip'].split('/')[0] for it in disp[altro]['interfacce'] if it['ip']} | {
                    lb.split('/')[0] for lb in disp[altro]['loopback']
                }
                if not (set(cfg_dev['neighbors']) & ips_altro):
                    mancanti.append(altro)
            if mancanti:
                out.append(_make_issue(
                    'bgp.missing_ibgp', 'avviso', 'proposta', f"{dev}/etc/frr/frr.conf", None, '',
                    f"Sessioni iBGP mancanti in AS{d['asn']} verso {', '.join(mancanti)} (solo se richieste dalla traccia; in scenari butterfly non servono).",
                    [{
                        'etichetta': f"Crea full-mesh iBGP in AS{d['asn']}",
                        'confidenza': 'proposta',
                        'tipo': 'lab_op',
                        'op': 'ibgp_full_mesh',
                        'params': {'asn': str(d['asn'])},
                    }],
                ))

    return out


def suggerisci_per_riga_vtysh(content, riga_num, testo_vtysh='', lab_path=None, dev=None):
    """Incrocia una riga rigettata da `vtysh --dryrun` con il motore `analizza_frr_avanzato`
    per restituire un eventuale suggerimento mirato (testo o None)."""
    try:
        issues = analizza_frr_avanzato(content, lab_path=lab_path, dev=dev)
    except Exception:
        return None
    for x in issues:
        if x.get('riga') == riga_num:
            if x.get('fixes'):
                etichette = [fx['etichetta'] for fx in x['fixes'][:2] if fx.get('etichetta')]
                if etichette:
                    return f"{x['messaggio']} → Suggerimento: {' / '.join(etichette)}"
            return x.get('messaggio')
    return None
