"""
src/core/generazione.py
Generazione di un lab nuovo dal suo modello: un'unica strada per wizard, import XML/JSON e GUI.

genera_lab costruisce tutto in una cartella temporanea accanto ai lab e lo mette al suo posto
solo alla fine: se qualcosa va storto prima, il lab di prima (se c'era) resta com'era e la
cartella temporanea viene tolta. Se sostituisce un lab esistente, prima ne fa una copia di
sicurezza in .backup_labgenerator/.

Non chiede e non stampa nulla: i messaggi dei generatori vengono raccolti e restituiti.
"""
import contextlib
import io
import os
import shutil
import tempfile

from .file_utils import copia_di_sicurezza
from .generators import crea_dns_host, crea_host_multi, crea_router_files, crea_www_file
from .modello import dispositivi, valida_lab
from .net_frr import auto_generate_bgp_neighbors, rimuovi_network_bgp_interne
from .persistence import rebuild_lab_metadata_and_export


def lab_conf_da_modello(modello):
    """Testo di lab.conf come lo scrive il wizard: router, host, www, dns, nell'ordine di inserimento."""
    righe = []
    ordine = (
        [(n, 'router', r) for n, r in modello.get('routers', {}).items()]
        + [(h.get('name'), 'host', h) for h in modello.get('hosts', []) if not h.get('dns')]
        + [(w.get('name'), 'www', w) for w in modello.get('wwws', [])]
        + [(h.get('name'), 'dns', h) for h in modello.get('hosts', []) if h.get('dns')]
    )
    for nome, tipo, d in ordine:
        ifaces = d.get('interfaces') or [{'lan': d.get('lan', '')}]
        for idx, it in enumerate(ifaces):
            righe.append(f"{nome}[{idx}]={it.get('lan', '')}")
        if tipo == 'router':
            if any(p in d.get('protocols', []) for p in ('bgp', 'ospf', 'rip')):
                righe.append(f'{nome}[image]="kathara/frr"')
        else:
            righe.append(f'{nome}[image]="{d.get("image") or "kathara/base"}"')
        righe.append('')
    return '\n'.join(righe).strip() + '\n'


def ip_del_resolver(modello):
    """IP (senza maschera) del server DNS scelto come resolver, o None."""
    nome = modello.get('resolver')
    for n, tipo, d in dispositivi(modello):
        if n == nome and tipo == 'dns':
            return str(d.get('ip') or '').split('/')[0] or None
    return None


def _scrivi_lab(lab_path, nome, modello, lab_conf_testo):
    """Scrive tutti i file del lab in lab_path (cartella vuota)."""
    routers, hosts, wwws = modello.get('routers', {}), modello.get('hosts', []), modello.get('wwws', [])

    for rname, rdata in routers.items():
        crea_router_files(lab_path, rname, rdata, interactive=False)

    dns_root_ip = None
    for h in hosts:
        if isinstance(h, dict) and h.get('dns') and str(h.get('root_type', '')).lower() == 'master':
            ip = h.get('ip') or ''
            dns_root_ip = ip.split('/')[0] if '/' in ip else ip
            break

    for h in hosts:
        try:
            if isinstance(h, dict) and (h.get('dns') or str(h.get('type', '')).lower() == 'dns'):
                fwd = h.get('forwarders') if isinstance(h.get('forwarders'), list) else None
                zones = h.get('zones') if isinstance(h.get('zones'), dict) else None
                rt = h.get('root_type') if isinstance(h.get('root_type'), str) else None
                allow_rec = h.get('allow_recursion') if isinstance(h.get('allow_recursion'), str) else None
                dnssec_val = bool(h.get('dnssec_validation'))
                if rt and str(rt).lower() != 'master' and dns_root_ip:
                    crea_dns_host(
                        lab_path, h.get('name'), h.get('ip'), h.get('gateway'), h.get('lan'),
                        forwarders=fwd, zones=zones, root_type=rt, root_server_ip=dns_root_ip,
                        allow_recursion=allow_rec, dnssec_validation=dnssec_val
                    )
                else:
                    crea_dns_host(
                        lab_path, h.get('name'), h.get('ip'), h.get('gateway'), h.get('lan'),
                        forwarders=fwd, zones=zones, root_type=rt,
                        allow_recursion=allow_rec, dnssec_validation=dnssec_val,
                        delegations=h.get('delegations') if isinstance(h.get('delegations'), list) else None
                    )
            else:
                ifaces = h.get('interfaces') or [{'name': 'eth0', 'ip': h.get('ip'), 'lan': h.get('lan')}]
                crea_host_multi(lab_path, h.get('name'), ifaces, h.get('gateway'), h.get('gw_dev') or 'eth0')
        except Exception as e:
            print(f"⚠️ Errore creando l'host {h.get('name') if isinstance(h, dict) else h}: {e}")

    for w in wwws:
        try:
            crea_www_file(lab_path, w.get('name'), w.get('ip'), w.get('gateway'), w.get('lan'))
        except Exception as e:
            print(f"⚠️ Errore creando il webserver {w.get('name')}: {e}")

    # resolver: come il wizard, resolv.conf su tutti gli host, i server DNS e i www
    ip_res = ip_del_resolver(modello)
    if ip_res:
        for dev in {h.get('name') for h in hosts if h.get('name')} | {w.get('name') for w in wwws if w.get('name')}:
            etc = os.path.join(lab_path, dev, 'etc')
            os.makedirs(etc, exist_ok=True)
            with open(os.path.join(etc, 'resolv.conf'), 'w', encoding='utf-8', newline='\n') as f:
                f.write(f"nameserver {ip_res}\n")

    with open(os.path.join(lab_path, 'lab.conf'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(lab_conf_testo if lab_conf_testo else lab_conf_da_modello(modello))

    auto_generate_bgp_neighbors(lab_path, routers)
    rimuovi_network_bgp_interne(lab_path, routers)



def genera_lab(base, nome, modello, sovrascrivi=False, lab_conf_testo=None, tollerante=False):
    """Crea il lab `nome` in `base` dal modello (routers, hosts, wwws, resolver).

    - Il modello viene controllato con valida_lab: con errori non si scrive nulla, a meno di
      tollerante=True (import da XML/JSON: si crea comunque, come prima).
    - Se il lab esiste e sovrascrivi è False non si tocca nulla.
    - lab_conf_testo: testo di lab.conf già pronto (import); altrimenti si ricava dal modello.

    Restituisce {'creato', 'percorso', 'problemi', 'errori', 'copia', 'messaggi', 'motivo'}."""
    lab_path = os.path.join(base, nome)
    problemi = valida_lab(dict(modello, nome=nome))
    errori = [p for p in problemi if p['gravita'] == 'errore']
    esito = {'creato': False, 'percorso': lab_path, 'problemi': problemi, 'errori': errori,
             'copia': None, 'messaggi': [], 'motivo': None}
    if errori and not tollerante:
        esito['motivo'] = 'errori'
        return esito
    if os.path.exists(lab_path) and not sovrascrivi:
        esito['motivo'] = 'esiste'
        return esito

    os.makedirs(base, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='.labgen-tmp-', dir=base)
    try:
        nuovo = os.path.join(tmp, nome)
        os.makedirs(nuovo)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _scrivi_lab(nuovo, nome, modello, lab_conf_testo)
        esito['messaggi'] = [r.replace(nuovo, lab_path) for r in buf.getvalue().splitlines() if r.strip()]
        vecchio = None
        if os.path.exists(lab_path):
            esito['copia'] = copia_di_sicurezza(lab_path)
            vecchio = os.path.join(tmp, '.vecchio')
            os.replace(lab_path, vecchio)
        try:
            os.replace(nuovo, lab_path)
        except OSError:
            if vecchio:                    # il lab di prima torna al suo posto
                os.replace(vecchio, lab_path)
            raise
        esito['creato'] = True
        # XML dei metadati, fuori dal lab, rigenerato dai file appena scritti
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rebuild_lab_metadata_and_export(lab_path)
        esito['messaggi'] += [r for r in buf.getvalue().splitlines() if r.strip()]
        return esito
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
