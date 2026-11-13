"""
src/core/device_editor.py
Modifica guidata dei dispositivi (IP, LAN, gateway, protocolli, AS) ed editor interattivo a righe.
"""
import ipaddress
import os
import re
import subprocess

from .analyzer import _problemi_di, _proprietari, leggi_dispositivi, riferimenti_frr
from .cli_io import (
    _si,
    asn_valido,
    input,
    input_area,
    input_int,
    input_reti,
    print_menu,
)
from .file_utils import (
    _applica_modifiche,
    _avvisi_lab,
    _file_di_testo,
    _fine_blocco,
    _inizio_blocco,
    _inserisci_nel_blocco,
    _righe_file,
    _set_demone,
    ripristina_copia,
)
from .net_frr import (
    _norm_net,
    default_igp_networks,
    mk_bgp_stanza,
    mk_ospf_stanza,
    mk_rip_stanza,
)
from .persistence import _aggiorna_xml, _xml_sostituisci
from .templates import _FRR_GLOBALI, _RE_GW, _RE_IP_ADD, _RE_TOKEN_IP


def modifica_router_menu(base_path, routers):
    """Apre frr.conf di un router con l'editor di sistema ($EDITOR o nano)."""
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


# --- Modifica a righe ---
def _file_modificabili(lab_path, nome):
    cand = [
        f"{nome}.startup",
        os.path.join(nome, 'etc', 'frr', 'frr.conf'),
        os.path.join(nome, 'etc', 'resolv.conf')
    ]
    bind = os.path.join(lab_path, nome, 'etc', 'bind')
    if os.path.isdir(bind):
        cand += [os.path.join(nome, 'etc', 'bind', f) for f in sorted(os.listdir(bind))]
    return [c for c in cand if os.path.isfile(os.path.join(lab_path, c))]


def _indenta(righe, dopo, testo, frr):
    """Riga nuova inserita dopo l'indice `dopo` (-1 = in cima): in frr.conf, dentro un blocco
    prende 4 spazi; i comandi globali restano a sinistra."""
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
    """Modifica a righe di un file del lab, con le righe numerate e gli avvisi di frr.conf."""
    path = os.path.join(lab_path, rel)
    frr = rel.replace(os.sep, '/').endswith('frr/frr.conf')
    originali = _righe_file(path)
    righe, storia = list(originali), []
    aiuto = (
        "  M n = modifica la riga n      E n = elimina la riga n     A n = aggiungi righe dopo la n (A 0 = in cima)\n"
        "  C n = applica la correzione suggerita sulla riga n          U = annulla l'ultima modifica\n"
        "  S = salva                       0 = esci                    V = rivedi il file"
    )
    mostra = True
    while True:
        note = _note_frr(righe) if frr else {}
        if mostra:
            stato_mod = ', modificato, non salvato' if righe != originali else ''
            print(f"\n=== {rel.replace(os.sep, '/')} ({len(righe)} righe{stato_mod}) ===")
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
                print("Annullata l'ultima modifica.")
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


# --- Sostituzione di IP e reti in tutti i file del lab ---
def _sostituzione_ip(ip_map, iface_map, net_map):
    """Funzione testo -> testo: sostituisce IP, IP/maschera di interfaccia e reti."""
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
                    return f"{ip_map[a]}/{l}"
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
    """Righe con un aggregato che conteneva la rete vecchia ma non contiene la nuova."""
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
                            avvisi.append(
                                f"{rel.replace(os.sep, '/')} riga {k}: '{l.strip()}' comprende {v} "
                                f"ma non {nu}: controllala a mano."
                            )
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


# --- Scelte comuni ---
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


def _chiedi_nuovo_ip(prompt, own, rete=None, dentro=None, propri=()):
    """IP con maschera (senza maschera prende quella di `rete`); rifiuta rete/broadcast e IP duplicati."""
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


# --- Modifica IP, rete di una LAN, spostamento interfaccia, gateway ---
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
    nuovo = _chiedi_nuovo_ip(
        f"Nuovo IP (es. {vecchio.ip}/{vecchio.network.prefixlen}; senza maschera tiene "
        f"/{vecchio.network.prefixlen}; Invio = annulla): ",
        own, rete=vecchio.network, propri=(str(vecchio.ip),)
    )
    if nuovo is None or nuovo == vecchio:
        print('Nessuna modifica.')
        return
    if nuovo.network != vecchio.network and altri:
        print(
            f"⚠️ {nuovo} non è nella rete della LAN {it['lan']} ({vecchio.network}): gli altri dispositivi "
            f"della LAN non lo raggiungerebbero."
        )
        print("  1) cambia la rete di tutta la LAN (anche gli IP degli altri)\n  2) cambia solo questo IP\n  0) annulla")
        s = input("Scelta: ").strip()
        if s == '1':
            rinumera_lan(lab_path, routers, it['lan'], nuova_rete=nuovo.network, fissi={(nome, it['dev']): nuovo})
            return
        if s != '2':
            print('Annullato.')
            return
    net_map = {str(vecchio.network): str(nuovo.network)} if nuovo.network != vecchio.network and not altri else {}
    _esegui_sostituzione(
        lab_path, routers,
        {str(vecchio.ip): str(nuovo.ip)},
        {str(vecchio): str(nuovo)},
        net_map,
        f"IP di {nome} {it['dev']}: {vecchio} -> {nuovo}"
    )


def rinumera_lan_menu(lab_path, routers, nome):
    it = _scegli_interfaccia(leggi_dispositivi(lab_path)[nome], "LAN da rinumerare (scegli l'interfaccia)")
    if it:
        rinumera_lan(lab_path, routers, it['lan'])


def rinumera_lan(lab_path, routers, lan, nuova_rete=None, fissi=None):
    """Cambia la rete di una LAN: ogni dispositivo mantiene la stessa parte host quando possibile."""
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
                cand = _chiedi_nuovo_ip(
                    f"IP per {n} {x['dev']} in {nuova_rete} (era {v}; Invio = annulla tutto): ",
                    own, rete=nuova_rete, dentro=nuova_rete,
                    propri=[str(m['ip']).split('/')[0] for _, m in membri]
                )
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
    _esegui_sostituzione(
        lab_path, routers,
        {str(vecchi[k].ip): str(nuovi[k].ip) for k in vecchi},
        {str(vecchi[k]): str(nuovi[k]) for k in vecchi},
        {str(vecchia): str(nuova_rete)},
        f"Rete della LAN {lan}: {vecchia} -> {nuova_rete}"
    )


def sposta_interfaccia(lab_path, routers, nome):
    disp = leggi_dispositivi(lab_path)
    own = _proprietari(disp)
    it = _scegli_interfaccia(disp[nome], 'Interfaccia da spostare')
    if not it:
        return
    lans = sorted({x['lan'] for dd in disp.values() for x in dd['interfacce']})
    print("\nLAN del lab:")
    for l in lans:
        print(f"   {l:<6} {str(_rete_lan(disp, l) or '-'):<18} " + ', '.join(n for n, _ in _membri_lan(disp, l)))
    while True:
        nuova = input(
            f"Nuova LAN per {nome} {it['dev']} (ora {it['lan']}; nome esistente o nuovo, Invio = annulla): "
        ).strip()
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
        n_ip = _chiedi_nuovo_ip(
            f"Nuovo IP in {rete} (Invio = lascia {v}): ",
            own, rete=rete, dentro=rete, propri=(str(v.ip),)
        )
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

    _esegui_sostituzione(
        lab_path, routers, ip_map, iface_map, {},
        f"{nome} {it['dev']}: LAN {it['lan']} -> {nuova}",
        extra={lc: (vecchie, nuove)}, xml_extra=xml_lan
    )


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
    dev = next(
        (it['dev'] for it in d['interfacce']
         if it['ip'] and ipaddress.ip_address(gw) in ipaddress.ip_interface(it['ip']).network),
        None
    )
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


# --- Protocolli e AS ---
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
    note = [
        f"{rel.replace(os.sep, '/')} riga {k}: '{l.strip()}' contiene ancora {vecchio}: controllala."
        for k, l in enumerate(righe, 1) if 'as-path' in l and re.search(rf'\b{vecchio}\b', l)
    ]
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
        reti = input_reti(
            f"Network {p.upper()} da annunciare, separate da virgola (Invio = {', '.join(proposta)}): ",
            default=proposta
        )
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
        i = _inizio_blocco(righe, r'router bgp\b')
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
        reti = input_reti(
            f"Network BGP da annunciare (Invio = {', '.join(proprie) or 'nessuna'}): ",
            default=proprie, opzionale=True
        )
        blocco = mk_bgp_stanza(asn, networks=reti).rstrip('\n').split('\n')
        scelti = []
        for it in d['interfacce']:
            for n2, x in _membri_lan(disp, it['lan']):
                d2 = disp[n2]
                if n2 == nome or not x['ip'] or 'bgpd' not in d2['demoni']:
                    continue
                ip2 = x['ip'].split('/')[0]
                if _si(f"Sessione BGP con {n2} ({ip2}, AS{d2['asn'] or '?'})? (S/n): ", True):
                    blocco += [
                        f"    neighbor {ip2} remote-as {d2['asn']}",
                        f"    neighbor {ip2} description Router {n2}"
                    ]
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
                con = _inserisci_nel_blocco(
                    v, r'router bgp\b',
                    [f"neighbor {mio_ip} remote-as {asn}", f"neighbor {mio_ip} description Router {nome}"]
                )
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
    nuove = [
        l for l in nuove
        if not re.match(rf'\s*redistribute\s+{p}\b', l)
        and not (p == 'bgp' and re.match(r'\s*debug\s+bgp\b', l))
    ]
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
        if altri and _si(
            f"Tolgo anche le righe 'neighbor' che puntano a {nome} su "
            f"{', '.join(sorted(r.split(os.sep)[0] for r in altri))}? (S/n): ",
            True
        ):
            modifiche.update(altri)
        note.append("Route-map e prefix-list del router restano: i controlli le segnaleranno se non sono più usate.")

    def xml_p(r, h, w):
        if nome in r:
            r[nome]['protocols'] = [x for x in r[nome].get('protocols', []) if x != p]
            if p == 'bgp':
                r[nome]['asn'] = ''
    if _applica_modifiche(lab_path, modifiche, f"Togli {p.upper()} da {nome}", note):
        _aggiorna_xml(lab_path, routers, xml_p)


# --- Menu del dispositivo ---
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
        voci = [
            ("IP di un'interfaccia", modifica_ip_interfaccia),
            ('Rete di una LAN (cambia gli IP di tutti i dispositivi della LAN)', rinumera_lan_menu),
            ("Sposta un'interfaccia su un'altra LAN", sposta_interfaccia)
        ]
        if d['tipo'] == 'router':
            voci.append(('Protocolli (aggiungi o togli BGP, OSPF, RIP)', modifica_protocolli))
            if d['asn']:
                voci.append(('AS del router', cambia_as))
        else:
            voci.append(('Default gateway', cambia_gateway))
        voci += [
            ('Modifica a righe dei file (startup, frr.conf, resolv.conf, DNS)', modifica_righe),
            ('Ripristina il lab da una copia di sicurezza', ripristina_copia)
        ]
        print_menu(
            f'--- Modifica {nome} ---',
            [v[0] for v in voci],
            extra_options=[('A', 'Altro dispositivo'), ('0', 'Torna indietro')]
        )
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