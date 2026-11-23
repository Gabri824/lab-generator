"""Comandi Kathará per la GUI: avvio/arresto del lab, comandi sui dispositivi,
test (raggiungibilità, sessioni BGP/OSPF, percorso), terminale, archivio.

Si eseguono solo i comandi di questo file (lista chiusa, niente shell libera):
nomi di lab/dispositivi e IP arrivano già validati dal server.
"""
import base64
import concurrent.futures
import datetime
import hashlib
import ipaddress
import itertools
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time

from core import web

from . import dati

ANSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')

# comandi sui dispositivi: chiave -> (etichetta, argomenti); '{ip}' è sostituito dall'IP
# (già validato) per i comandi che lo richiedono
COMANDI = {
    'bgp': ('show ip bgp', ['vtysh', '-c', 'show ip bgp']),
    'bgp_summary': ('show ip bgp summary', ['vtysh', '-c', 'show ip bgp summary']),
    'route': ('show ip route', ['vtysh', '-c', 'show ip route']),
    'ospf_nei': ('show ip ospf neighbor', ['vtysh', '-c', 'show ip ospf neighbor']),
    'ospf_if': ('show ip ospf interface', ['vtysh', '-c', 'show ip ospf interface']),
    'rip': ('show ip rip', ['vtysh', '-c', 'show ip rip']),
    'running': ('show running-config', ['vtysh', '-c', 'show running-config']),
    'ip_route': ('ip route', ['ip', 'route']),
    'ip_addr': ('ip -br addr', ['ip', '-br', 'addr']),
    'ping': ('ping {ip}', ['ping', '-c', '3', '-W', '1', '{ip}']),
    'traceroute': ('traceroute {ip}', ['traceroute', '-n', '-w', '1', '-q', '1', '-m', '20', '{ip}']),
    'bgp_ricevute': ('rotte accettate da {ip}', ['vtysh', '-c', 'show ip bgp neighbors {ip} routes']),
    'bgp_annunciate': ('rotte annunciate a {ip}', ['vtysh', '-c', 'show ip bgp neighbors {ip} advertised-routes']),
    'apache_stato': ('stato apache2', ['systemctl', 'is-active', 'apache2']),
    'apache_avvia': ('avvia apache2', ['systemctl', 'start', 'apache2']),
}


def comando(chiave, ip=None):
    """(etichetta, argomenti) di un comando della lista, con l'IP al posto di '{ip}'."""
    etichetta, args = COMANDI[chiave]
    return etichetta.replace('{ip}', ip or ''), [a.replace('{ip}', ip or '') for a in args]


def serve_ip(chiave):
    return any('{ip}' in a for a in COMANDI[chiave][1])


def trova_kathara():
    return shutil.which('kathara')


def _env(colonne=100):
    # senza colori: l'output va in una pagina, non in un terminale
    # (colonne=250 per leggere le tabelle di `kathara list` senza tagli)
    return dict(os.environ, COLUMNS=str(colonne), TERM='dumb', NO_COLOR='1')


def _pulisci(testo):
    righe = []
    for r in ANSI.sub('', testo).split('\n'):
        pezzi = [p for p in r.split('\r') if p.strip()]     # barre di avanzamento
        righe.append(pezzi[-1] if pezzi else '')
    return '\n'.join(righe)


def testo_comando(args):
    return ' '.join(a if re.match(r'^[\w@%+=:,./-]+$', a) else "'" + a.replace("'", "'\\''") + "'"
                    for a in args)


# -------------------------
# Lavori in background e registro operazioni
# -------------------------
class Lavoro:
    def __init__(self, titolo):
        self.titolo = titolo
        self.righe = []
        self.fatto = False
        self.rc = None
        self.risultato = None
        self.lock = threading.Lock()

    def scrivi(self, testo):
        with self.lock:
            self.righe.extend(_pulisci(testo).rstrip('\n').split('\n'))


class Lavori:
    def __init__(self):
        self._lavori = {}
        self._id = itertools.count(1)
        self.registro = []
        self._lock = threading.Lock()

    def avvia(self, titolo, comando, funzione):
        """Esegue funzione(lavoro) in un thread; ritorna l'id del lavoro."""
        lav = Lavoro(titolo)
        lid = str(next(self._id))
        self._lavori[lid] = lav
        voce = {'ora': time.strftime('%H:%M:%S'), 'operazione': titolo, 'comando': comando, 'esito': 'in corso'}
        with self._lock:
            self.registro.append(voce)

        def corpo():
            t0 = time.time()
            try:
                lav.rc = funzione(lav)
            except Exception as e:      # l'errore va nella pagina, il server resta su
                lav.scrivi(f"Errore: {e}")
                lav.rc = -1
            voce['esito'] = ('OK' if lav.rc == 0 else f"errore ({lav.rc})") + f" in {time.time() - t0:.0f}s"
            lav.fatto = True
        threading.Thread(target=corpo, daemon=True).start()
        return lid

    def leggi(self, lid, da=0):
        lav = self._lavori.get(lid)
        if lav is None:
            return None
        with lav.lock:
            return {'titolo': lav.titolo, 'fatto': lav.fatto, 'rc': lav.rc,
                    'righe': lav.righe[da:], 'totale': len(lav.righe), 'risultato': lav.risultato}

    def annota(self, operazione, comando, esito):
        with self._lock:
            self.registro.append({'ora': time.strftime('%H:%M:%S'), 'operazione': operazione,
                                  'comando': comando, 'esito': esito})


def esegui(args, lav=None, timeout=600):
    """Esegue un comando; se c'è un lavoro, l'output arriva alla pagina riga per riga.
    Ritorna (rc, testo)."""
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, env=_env())
    timer = threading.Timer(timeout, p.kill)
    timer.start()
    out = []
    try:
        for riga in iter(p.stdout.readline, b''):
            s = riga.decode('utf-8', errors='replace')
            out.append(s)
            if lav is not None:
                lav.scrivi(s)
        p.wait()
    finally:
        timer.cancel()
        p.stdout.close()
    return p.returncode, _pulisci(''.join(out))


def suggerimento(testo):
    """Spiegazione in italiano per gli errori di Kathará più comuni (None se non ne riconosce)."""
    if 'DockerDaemonConnectionError' in testo or 'Cannot connect to Docker' in testo:
        if sys.platform.startswith('win'):
            return "-> Docker non è attivo: avvia Docker Desktop, aspetta che sia pronto e riprova."
        return ("-> Docker non è raggiungibile: il servizio non è attivo oppure il tuo utente non è nel "
                "gruppo 'docker' (prova 'docker ps' in un terminale).")
    if 'already exists' in testo:
        return "-> Alcuni dispositivi di questo lab sono già avviati: premi 'Ferma (lclean)' e riprova."
    if 'SyntaxError' in testo and 'lab.conf' in testo:
        return ("-> lab.conf non valido (es. nomi di dispositivo con '-', '.' o maiuscole): guarda "
                "'Riepilogo e controlli' oppure apri il lab dal menu 5 del generatore per correggerlo.")
    # non basta 'is not running': lo scrive anche vtysh ('ospfd is not running') a router acceso
    if 'MachineNotRunningError' in testo or re.search(r'Device \S+ is not running', testo):
        return "-> Il dispositivo non è avviato: avvia il lab (lstart) e riprova."
    return None


def esegui_spiegato(args, lav, timeout=600):
    """Come esegui(), ma se il comando fallisce aggiunge la spiegazione dell'errore."""
    rc, out = esegui(args, lav, timeout)
    s = suggerimento(out) if rc != 0 else None
    if s:
        lav.scrivi('\n' + s)
    return rc, out


def kexec(kathara, lab_path, dev, comando):
    """Argomenti di `kathara exec`, con il comando in un'unica stringa.
    Il pacchetto ufficiale di Kathará (compilato con Nuitka) si rifiuta di partire se tra i suoi
    argomenti c'è esattamente '-c' o '-m', anche dopo '--': così 'vtysh -c ...' e 'ping -c ...'
    fallirebbero e la GUI leggerebbe 0 sessioni. Una stringa sola passa il controllo e Kathará la
    divide con shlex.split (POSIX su ogni sistema), l'operazione inversa di shlex.join."""
    return [kathara, 'exec', '-d', lab_path, dev, shlex.join(comando)]


def testo_exec(lab_path, dev, comando):
    """Il comando di kexec come va scritto in un terminale, per il registro delle operazioni."""
    return testo_comando(['kathara', 'exec', '-d', lab_path, dev]) + ' "' + shlex.join(comando) + '"'


# -------------------------
# Stato dei lab (quali dispositivi sono avviati)
# -------------------------
def hash_lab(path):
    """Stesso identificativo che Kathará dà a un lab: md5 del percorso in base64,
    tenendo solo lettere e cifre."""
    return re.sub(r'[^0-9a-zA-Z]', '', base64.urlsafe_b64encode(hashlib.md5(path.encode('utf-8')).digest()).decode())


def stato_lab(kathara, base, labs):
    """{lab: [dispositivi avviati]}. Usa `docker ps` (veloce); se docker non è
    utilizzabile, `kathara list` (più lento)."""
    per_hash = {}
    for lab in labs:
        p = os.path.join(base, lab)
        for cand in {os.path.abspath(p), os.path.realpath(p)}:
            per_hash[hash_lab(cand)] = lab
    stato = {lab: [] for lab in labs}
    docker = shutil.which('docker')
    righe = None
    if docker:
        try:
            r = subprocess.run([docker, 'ps', '--filter', 'label=app=kathara', '--format',
                                '{{.Label "lab_hash"}}|{{.Label "name"}}'],
                               capture_output=True, timeout=20, env=_env())
            if r.returncode == 0:
                righe = [l.split('|', 1) for l in r.stdout.decode('utf-8', 'replace').splitlines() if '|' in l]
        except (OSError, subprocess.SubprocessError):
            righe = None
    if righe is None and kathara:
        try:
            r = subprocess.run([kathara, 'list'], capture_output=True, timeout=60, env=_env(250))
            righe = []
            for l in _pulisci(r.stdout.decode('utf-8', 'replace')).splitlines():
                c = [x.strip() for x in l.strip().strip('|').split('|')]
                if len(c) >= 2 and c[0] in per_hash:
                    righe.append(c[:2])
        except (OSError, subprocess.SubprocessError):
            righe = []
    for h, nome in righe or []:
        if h in per_hash:
            stato[per_hash[h]].append(nome)
    return stato


# -------------------------
# Test
# -------------------------
def _parallelo(funzione, elementi, max_thread=6):
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_thread) as ex:
        return dict(zip(elementi, ex.map(funzione, elementi)))


def raggiungibilita(kathara, lab_path, lab, lav):
    """Da ogni dispositivo, ping di tutti gli IP degli altri (in parallelo)."""
    disp = {d['nome']: d for d in lab['dispositivi']}
    owner = dati.indirizzi(disp)
    destinazioni = sorted(owner.items(), key=lambda x: (x[1], ipaddress.ip_address(x[0])))
    sorgenti = [d['nome'] for d in lab['dispositivi'] if d['interfacce']]

    def prova(src):
        ips = [ip for ip, n in destinazioni if n != src]
        script = ('for ip in ' + ' '.join(ips) + '; do (ping -c 2 -i 0.3 -W 1 $ip >/dev/null 2>&1 '
                  '&& echo "OK $ip" || echo "KO $ip") & done; wait')
        rc, out = esegui(kexec(kathara, lab_path, src, ['bash', '-c', script]), timeout=120)
        esiti = {}
        for l in out.splitlines():
            m = re.match(r'(OK|KO) (\S+)$', l.strip())
            if m:
                esiti[m.group(2)] = m.group(1) == 'OK'
        ok = sum(esiti.values())
        lav.scrivi(f"{src}: {ok}/{len(ips)} raggiunti" if esiti else f"{src}: errore\n{out.strip()}")
        return esiti if esiti else {'_errore': out.strip()[-300:]}

    lav.scrivi(f"Ping da {len(sorgenti)} dispositivi verso {len(destinazioni)} indirizzi...")
    esiti = _parallelo(prova, sorgenti)
    lav.risultato = {'sorgenti': sorgenti,
                     'destinazioni': [{'ip': ip, 'dev': n} for ip, n in destinazioni],
                     'esiti': esiti}
    ko = sum(1 for e in esiti.values() for k, v in e.items() if k != '_errore' and not v)
    lav.scrivi(f"Fatto: {ko} ping falliti.")
    return 0


def _json_o_none(testo):
    """Primo oggetto JSON nel testo (prima possono esserci messaggi come 'ospfd is not running')."""
    i = testo.find('{')
    if i < 0:
        return None
    try:
        return json.JSONDecoder().raw_decode(testo[i:])[0]
    except ValueError:
        return None


def _leggi_sessioni(kathara, lab_path, lab, spenti=()):
    """Peering BGP e vicini OSPF di ogni router, con quelli attesi dalla configurazione.
    Le sessioni sui link spenti dalla GUI (guasto simulato) sono segnate 'escluso' e
    non contano per la convergenza. Ritorna (righe_bgp, righe_ospf)."""
    disp = {d['nome']: d for d in lab['dispositivi']}
    owner = dati.indirizzi(disp)
    router = [d['nome'] for d in lab['dispositivi'] if d['tipo'] == 'router'
              and ({'bgpd', 'ospfd'} & set(d['demoni']))]
    sep = '@@SEPARATORE@@'

    def leggi(r):
        script = (f"vtysh -c 'show ip bgp summary json' 2>&1; echo {sep}; "
                  f"vtysh -c 'show ip ospf neighbor json' 2>&1")
        rc, out = esegui(kexec(kathara, lab_path, r, ['bash', '-c', script]), timeout=60)
        if sep not in out:
            return {'errore': out.strip()[-300:]}
        bgp, ospf = out.split(sep, 1)
        return {'bgp': _json_o_none(bgp), 'ospf': _json_o_none(ospf)}

    letture = _parallelo(leggi, router)
    righe_bgp, righe_ospf = [], []
    for r in router:
        d, l = disp[r], letture[r]
        if 'errore' in l:
            righe_bgp.append({'router': r, 'errore': l['errore']})
            continue
        if 'bgpd' in d['demoni']:
            peers = ((l['bgp'] or {}).get('ipv4Unicast') or {}).get('peers') or {}
            attesi = [n['ip'] for n in (d['riepilogo'] or {}).get('neighbor', [])]
            for ip in attesi + [p for p in peers if p not in attesi]:
                p = peers.get(ip)
                riga = {'router': r, 'neighbor': ip, 'chi': owner.get(ip, '?'),
                        'as': p.get('remoteAs') if p else None,
                        'stato': (p.get('state') or p.get('peerState')) if p else 'non trovato',
                        'prefissi': p.get('pfxRcd') if p else None,
                        'uptime': p.get('peerUptime') if p else None,
                        'ok': bool(p) and p.get('state') == 'Established'}
                lan_n = dati.lan_di_ip(disp, ip)
                if lan_n in spenti and not riga['ok']:
                    riga['escluso'] = f"link {lan_n} spento"
                righe_bgp.append(riga)
        if 'ospfd' in d['demoni']:
            trovati = {}
            for rid, voci in ((l['ospf'] or {}).get('neighbors') or {}).items():
                for v in voci if isinstance(voci, list) else [voci]:
                    ip = v.get('ifaceAddress') or v.get('address') or ''
                    trovati[ip] = {'router_id': rid, 'stato': v.get('nbrState') or v.get('state') or '?',
                                   'interfaccia': (v.get('ifaceName') or '').split(':')[0]}
            # attesi: router OSPF dello stesso AS sulle stesse LAN
            attesi = []
            for it in d['interfacce']:
                if it['lan'] in spenti:
                    continue
                for altro in disp.values():
                    if altro['nome'] == r or 'ospfd' not in altro['demoni'] or altro['gruppo'] != d['gruppo']:
                        continue
                    attesi += [x['ip'].split('/')[0] for x in altro['interfacce']
                               if x['lan'] == it['lan'] and x['ip']]
            for ip in attesi + [ip for ip in trovati if ip not in attesi]:
                v = trovati.get(ip)
                righe_ospf.append({'router': r, 'vicino': ip, 'chi': owner.get(ip, '?'),
                                   'router_id': v['router_id'] if v else None,
                                   'interfaccia': v['interfaccia'] if v else None,
                                   'stato': v['stato'] if v else 'non trovato',
                                   'ok': bool(v) and v['stato'].startswith('Full')})
    return righe_bgp, righe_ospf


def _conta(righe):
    righe = [x for x in righe if not x.get('escluso')]
    return sum(1 for x in righe if x.get('ok')), len(righe)


TIPI_CONTROLLATI = ('bgp', 'connected')


def righe_redistribute(lab, router, proto):
    """Tutte le righe 'redistribute ...' del blocco RIP/OSPF di un router, come sono nei file."""
    for d in lab['dispositivi']:
        if d['nome'] == router:
            for igp in (d.get('riepilogo') or {}).get('igp', []):
                if igp['protocollo'] == proto:
                    return ['redistribute ' + x for x in igp['redistribute']]
    return []


def ridistribuzioni(lab):
    """[(router, 'RIP'|'OSPF', riga)] per ogni 'redistribute bgp|connected ...' scritto nei file del lab."""
    voci = []
    for d in lab['dispositivi']:
        for igp in (d.get('riepilogo') or {}).get('igp', []):
            for x in igp['redistribute']:
                if x.split()[0] in TIPI_CONTROLLATI:
                    voci.append((d['nome'], igp['protocollo'], 'redistribute ' + x))
    return voci


def _rotte_passate_da_zebra(testo, client):
    """Dal 'show zebra client': quante rotte ridistribuite zebra ha mandato al demone
    (riga Redist:v4, colonna Add, contata dalla connessione). None se non si legge."""
    for blocco in re.split(r'^Client: ', testo, flags=re.M)[1:]:
        if blocco.split(None, 1)[0] == client:
            m = re.search(r'^Redist:v4\s+(\d+)', blocco, re.M)
            return int(m.group(1)) if m else None
    return None


def _ridistribuzione_router(kathara, lab_path, voce):
    """Le rotte da ridistribuire sono davvero entrate in RIP/OSPF?
    bgp: rotte BGP scelte → RIP: righe B(r); OSPF: LSA esterni generati dal router.
    connected: reti connesse non già coperte dall'IGP (RIP: C(i); OSPF: interfacce OSPF)
               → RIP: righe C(r); OSPF: LSA esterni generati dal router.
    In più legge da 'show zebra client' quante rotte zebra ha passato al demone: 0 vuol dire
    che la richiesta di ridistribuzione non è mai arrivata a zebra (difetto di avvio)."""
    r, proto, riga = voce
    tipo = riga.split()[1]
    sep = '@@SEPARATORE@@'
    cmd = 'show ip rip' if proto == 'RIP' else 'show ip ospf database external self-originate'
    extra = f"; echo {sep}; vtysh -c 'show ip ospf interface' 2>&1" if proto == 'OSPF' and tipo == 'connected' else ''
    script = (f"vtysh -c 'show ip route {tipo} json' 2>&1; echo {sep}; vtysh -c '{cmd}' 2>&1; "
              f"echo {sep}; vtysh -c 'show zebra client' 2>&1{extra}")
    rc, out = esegui(kexec(kathara, lab_path, r, ['bash', '-c', script]), timeout=60)
    x = {'router': r, 'igp': proto, 'riga': riga, 'tipo': tipo}
    parti = out.split(sep)
    if len(parti) < 3:
        return dict(x, errore=out.strip()[-300:], ok=False, stato='errore')
    rotte, igp, zebra = parti[0], parti[1], parti[2]
    reti = sorted(p for p, voci in (_json_o_none(rotte) or {}).items()
                  if isinstance(voci, list) and any(v.get('selected') for v in voci))
    if tipo == 'connected':
        # le reti già dentro l'IGP con 'network' non vengono ridistribuite: si tolgono
        if proto == 'RIP':
            coperte = set(re.findall(r'^\s*C\(i\)\s+(\S+)', igp, re.M))
        else:
            coperte = {str(ipaddress.ip_network(a, strict=False))
                       for a in re.findall(r'Internet Address (\d+\.\d+\.\d+\.\d+/\d+)', parti[3] if len(parti) > 3 else '')}
        reti = [p for p in reti if p not in coperte]
    if proto == 'RIP':
        codice = 'B' if tipo == 'bgp' else 'C'
        dentro = set(re.findall(rf'^\s*{codice}\(r\)\s+(\S+)', igp, re.M))
    else:
        ids = set(re.findall(r'Link State ID:\s*(\S+)', igp))
        dentro = {p for p in reti if p.split('/')[0] in ids}
    iniettate = [p for p in reti if p in dentro]
    passate = _rotte_passate_da_zebra(zebra, 'rip' if proto == 'RIP' else 'ospf')
    x.update(totale=len(reti), iniettate=len(iniettate), mancanti=[p for p in reti if p not in dentro],
             zebra=passate, ok=not reti or bool(iniettate))
    x['stato'] = (('nessuna rotta BGP' if tipo == 'bgp' else 'niente da ridistribuire') if not reti
                  else 'attiva' if iniettate else 'non attiva')
    if not x['ok']:
        x['causa'] = ("zebra non ha mai passato rotte a " + ('ripd' if proto == 'RIP' else 'ospfd')
                      + ": richiesta persa all'avvio, usa Riapplica" if passate == 0 else
                      "zebra passa rotte ma queste non entrano: controlla route-map/filtri sulla riga"
                      if passate else '')
    return x


def _leggi_ridistribuzione(kathara, lab_path, lab):
    voci = ridistribuzioni(lab)
    letture = _parallelo(lambda v: _ridistribuzione_router(kathara, lab_path, v), voci)
    return [letture[v] for v in voci]


def _scrivi_ridistribuzione(lav, righe):
    for x in righe:
        if not x['ok']:
            cosa = 'rotte BGP' if x.get('tipo') == 'bgp' else 'reti connesse da ridistribuire'
            zebra = '' if x.get('zebra') is None else f", zebra ne ha passate {x['zebra']} al demone"
            lav.scrivi(f"⚠ {x['router']}: '{x['riga']}' in {x['igp']} non attiva ({x.get('totale', '?')} {cosa}, "
                       f"nessuna entrata in {x['igp']}{zebra}). Usa 'Riapplica' nella tabella Ridistribuzione "
                       f"(con FRR 10.5.3 a volte non parte all'avvio).")


def riapplica_ridistribuzione(kathara, lab_path, lab, router, proto, lav):
    """Toglie e rimette TUTTE le righe 'redistribute' del blocco RIP/OSPF a lab acceso (i file non
    cambiano): se la richiesta a zebra si è persa all'avvio, di solito si sono perse tutte insieme.
    Riscrivere una riga già presente non basta: il demone non vede modifiche e non rimanda niente."""
    righe = righe_redistribute(lab, router, proto)
    blocco = 'router rip' if proto == 'RIP' else 'router ospf'
    args = ['vtysh', '-c', 'conf t', '-c', blocco]
    for riga in righe:
        args += ['-c', 'no ' + riga]
    for riga in righe:
        args += ['-c', riga]
    rc = esegui_spiegato(kexec(kathara, lab_path, router, args), lav, timeout=60)[0]
    if rc != 0:
        return rc
    voci = [v for v in ridistribuzioni(lab) if v[0] == router and v[1] == proto]
    for _ in range(4):
        time.sleep(3)
        esiti = [_ridistribuzione_router(kathara, lab_path, v) for v in voci]
        if all(x['ok'] for x in esiti):
            break
    lav.risultato = esiti
    for x in esiti:
        lav.scrivi(f"{router}: '{x['riga']}' {x['stato']} ({x.get('iniettate', 0)}/{x.get('totale', 0)} in {proto}"
                   + ('' if x.get('zebra') is None else f"; zebra ha passato {x['zebra']} rotte") + ").")
    return 0


def sessioni(kathara, lab_path, lab, lav, spenti=()):
    lav.scrivi("Lettura delle sessioni BGP e OSPF...")
    righe_bgp, righe_ospf = _leggi_sessioni(kathara, lab_path, lab, spenti)
    rid = _leggi_ridistribuzione(kathara, lab_path, lab)
    lav.risultato = {'bgp': righe_bgp, 'ospf': righe_ospf, 'ridistribuzione': rid}
    ko = sum(1 for x in righe_bgp + righe_ospf if not x.get('ok') and not x.get('escluso'))
    lav.scrivi(f"Fatto: {len(righe_bgp)} sessioni BGP, {len(righe_ospf)} vicini OSPF, {ko} non attivi.")
    _scrivi_ridistribuzione(lav, rid)
    return 0


def _motivo_attesa(righe):
    """Perché il lab non è ancora pronto, dalla prima riga non attiva (None se sono tutte attive)."""
    for x in righe:
        if x.get('ok') or x.get('escluso'):
            continue
        if x.get('errore'):
            ultima = [l for l in x['errore'].splitlines() if l.strip()][-1:] or ['nessuna risposta']
            return f"{x['router']}: lettura non riuscita: {ultima[0].strip()[:200]}"
        return f"{x['router']} -> {x.get('neighbor') or x.get('vicino')}: {x.get('stato')}"
    return None


def convergenza(kathara, lab_path, lab, lav, limite=300, passo=15, spenti=()):
    """Rilegge le sessioni ogni `passo` secondi finché sono tutte Established/Full
    (al massimo `limite` secondi: i testi avvisano che possono servire fino a 5 minuti).
    Il motivo dell'attesa va nell'Output subito, e di nuovo solo quando cambia."""
    t0 = time.time()
    motivo_scritto = None
    while True:
        righe_bgp, righe_ospf = _leggi_sessioni(kathara, lab_path, lab, spenti)
        (ob, tb), (oo, to) = _conta(righe_bgp), _conta(righe_ospf)
        trascorsi = time.time() - t0
        lav.risultato = {'bgp': righe_bgp, 'ospf': righe_ospf}
        lav.scrivi(f"{trascorsi:4.0f}s  BGP {ob}/{tb} Established   OSPF {oo}/{to} Full")
        motivo = _motivo_attesa(righe_bgp + righe_ospf)
        if motivo and motivo != motivo_scritto:
            lav.scrivi(f"       {motivo}")
            motivo_scritto = motivo
        if ob == tb and oo == to:
            # le rotte BGP possono arrivare qualche secondo dopo la sessione: fino a 30 s
            for i in range(4):
                rid = _leggi_ridistribuzione(kathara, lab_path, lab)
                if all(x['ok'] for x in rid):
                    break
                if i < 3:
                    time.sleep(10)
            lav.risultato['ridistribuzione'] = rid
            if all(x['ok'] for x in rid):
                lav.scrivi(f"✔ Lab pronto dopo {time.time() - t0:.0f} s: puoi lanciare i test.")
            else:
                lav.scrivi(f"Sessioni attive dopo {time.time() - t0:.0f} s, ma:")
                _scrivi_ridistribuzione(lav, rid)
            return 0
        if trascorsi + passo > limite:
            giu = [f"{x['router']} -> {x.get('neighbor') or x.get('vicino')} ({x.get('chi')}): {x.get('stato') or x.get('errore')}"
                   for x in righe_bgp + righe_ospf if not x.get('ok') and not x.get('escluso')]
            consiglio = ("La GUI non riesce a leggere questi router con 'kathara exec': il problema non è la "
                         "configurazione del lab. Controlla da 'Terminale' con 'show ip bgp summary'."
                         if any(x.get('errore') for x in righe_bgp) else
                         "Non è più un problema di tempo: controlla neighbor, remote-as, network OSPF e LAN.")
            lav.scrivi(f"✘ Dopo {trascorsi:.0f} s non sono ancora attive:\n  " + '\n  '.join(giu)
                       + "\n  " + consiglio)
            return 1
        time.sleep(passo)


def percorso(kathara, lab_path, lab, src, ip, lav):
    """Traceroute da src a ip; gli hop vengono tradotti in dispositivi e LAN."""
    disp = {d['nome']: d for d in lab['dispositivi']}
    owner = dati.indirizzi(disp)
    args = kexec(kathara, lab_path, src, comando('traceroute', ip)[1])
    rc, out = esegui(args, lav, timeout=120)
    hop, prec = [], src
    for l in out.splitlines():
        m = re.match(r'\s*(\d+)\s+(\S+)', l)
        if not m:
            continue
        h_ip = m.group(2)
        dev = owner.get(h_ip)
        lan = None
        if dev:
            # LAN attraversata: quella in comune tra il dispositivo precedente e questo
            comuni = ({it['lan'] for it in disp[prec]['interfacce']} &
                      {it['lan'] for it in disp[dev]['interfacce']}) if prec in disp else set()
            lan_ip = dati.lan_di_ip(disp, h_ip)
            lan = lan_ip if lan_ip in comuni else (sorted(comuni)[0] if comuni else lan_ip)
            prec = dev
        hop.append({'n': int(m.group(1)), 'ip': h_ip, 'dev': dev, 'lan': lan})
    arrivato = bool(hop) and hop[-1]['ip'] == ip
    lav.risultato = {'sorgente': src, 'destinazione': ip, 'dev_destinazione': owner.get(ip),
                     'hop': hop, 'arrivato': arrivato, 'costi_ospf': costi_ospf(kathara, lab_path, disp, src, hop)}
    return rc


def _costi_interfacce(testo):
    """{interfaccia: costo} da 'show ip ospf interface json' (FRR: {'interfaces': {...}} o {...})."""
    j = _json_o_none(testo) or {}
    tutte = j.get('interfaces', j) if isinstance(j, dict) else {}
    return {n: v.get('cost') for n, v in tutte.items() if isinstance(v, dict) and v.get('cost') is not None}


def costi_ospf(kathara, lab_path, disp, src, hop):
    """Costo OSPF dell'interfaccia da cui ogni router OSPF del percorso fa uscire i pacchetti (fase
    6): [{dev, iface, lan, costo}]. Serve a capire perché OSPF ha scelto una strada."""
    passi, prec = [], src
    for h in hop:
        if prec in disp and h.get('lan'):
            it = next((i for i in disp[prec]['interfacce'] if i['lan'] == h['lan']), None)
            if it and 'ospfd' in disp[prec]['demoni']:
                passi.append({'dev': prec, 'iface': it['dev'], 'lan': h['lan']})
        if h.get('dev'):
            prec = h['dev']
    routers = sorted({x['dev'] for x in passi})
    if not routers:
        return []

    def leggi(r):
        _, out = esegui(kexec(kathara, lab_path, r, ['vtysh', '-c', 'show ip ospf interface json']), timeout=60)
        return _costi_interfacce(out)
    costi = _parallelo(leggi, routers)
    for x in passi:
        x['costo'] = costi.get(x['dev'], {}).get(x['iface'])
    return passi


def ping(kathara, lab_path, lab, src, ip, origine, lav):
    """Ping da src verso ip (anche fuori dal lab); origine = IP di src da usare (-I) o None.
    Se fallisce perché la risposta non sa tornare (origine in una rete non annunciata in
    BGP), suggerisce un'interfaccia di src che sta in una rete annunciata."""
    disp = {d['nome']: d for d in lab['dispositivi']}
    owner = dati.indirizzi(disp)
    # interfaccia e IP da cui parte il ping: la stessa scelta del kernel
    _, rg = esegui(kexec(kathara, lab_path, src, ['ip', '-j', 'route', 'get', ip]), timeout=30)
    via = _json_o_none(rg) or {}
    partenza = origine or via.get('prefsrc')
    dev_uscita = next((it['dev'] for it in disp[src]['interfacce'] if it['ip'] and it['ip'].split('/')[0] == partenza),
                      None) if origine else via.get('dev')
    cmd = comando('ping', ip)[1]
    if origine:
        cmd = cmd[:-1] + ['-I', origine, ip]
    rc, out = esegui(kexec(kathara, lab_path, src, cmd), lav, timeout=60)
    m = re.search(r'(\d+) packets transmitted, (\d+) received', out)
    media = re.search(r'= [\d.]+/([\d.]+)/', out)
    inviati, ricevuti = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    ok = ricevuti > 0

    suggerimento = None
    if not ok:
        reti = [ipaddress.ip_network(n, strict=False) for d in lab['dispositivi']
                for n in ((d.get('riepilogo') or {}).get('bgp_networks') or [])]

        def annunciato(a):
            try:
                return any(ipaddress.ip_address(a) in n for n in reti)
            except ValueError:
                return False
        stesso_as = owner.get(ip) and disp[owner[ip]].get('gruppo') == disp[src].get('gruppo')
        if not via.get('dev'):
            suggerimento = (f"{src} non ha una rotta verso {ip}: controlla con 'Rotta verso una rete' "
                            f"o 'Tabelle di routing'.")
        elif reti and not stesso_as and not annunciato(partenza):
            alt = [f"{it['dev']} ({it['ip'].split('/')[0]})" for it in disp[src]['interfacce']
                   if it['ip'] and it['ip'].split('/')[0] != partenza and annunciato(it['ip'].split('/')[0])]
            suggerimento = (f"Il ping parte da {partenza}, in una rete non annunciata in BGP: la risposta "
                            f"non sa tornare. " + (f"Riprova con origine {', '.join(alt)}." if alt else
                            f"Nessuna interfaccia di {src} è in una rete annunciata: può essere voluto dal testo."))
        else:
            suggerimento = "Usa 'Verifica percorso' per vedere dove si ferma (o una policy del testo che lo blocca)."
    lav.risultato = {'sorgente': src, 'destinazione': ip, 'origine': origine, 'rotta': bool(via.get('dev')),
                     'partenza': partenza, 'dev_uscita': dev_uscita,
                     'dev_destinazione': owner.get(ip), 'lan_destinazione': dati.lan_di_ip(disp, ip),
                     'inviati': inviati, 'ricevuti': ricevuti, 'media': media.group(1) if media else None,
                     'ok': ok, 'suggerimento': suggerimento}
    return 0 if m else rc


def _percorsi_bgp(bgp, owner):
    """Percorsi di 'show ip bgp <rete> json': da chi, AS path, local-pref, MED, scelto o no."""
    percorsi = []
    for p in bgp.get('paths', []):
        peer = p.get('peer') or {}
        nh = (p.get('nexthops') or [{}])[0].get('ip')
        da = peer.get('peerId') or nh
        percorsi.append({'da': da, 'chi': owner.get(da or '') or peer.get('hostname') or '?',
                         'tipo': {'external': 'eBGP', 'internal': 'iBGP'}.get(peer.get('type'), peer.get('type') or ''),
                         'aspath': (p.get('aspath') or {}).get('string', ''), 'locpref': p.get('locPrf'),
                         'med': p.get('metric'), 'weight': p.get('weight'), 'origine': p.get('origin'),
                         'nexthop': nh, 'valido': p.get('valid', False),
                         'best': bool((p.get('bestpath') or {}).get('overall')),
                         'motivo': (p.get('bestpath') or {}).get('selectionReason', '')})
    return percorsi


def tabelle_bgp(kathara, lab_path, lab, routers, rete, lav):
    """{router: percorsi BGP per `rete`} letti dal lab acceso (fase 5.5b, percorso voluto)."""
    owner = dati.indirizzi({d['nome']: d for d in lab['dispositivi']})

    def leggi(r):
        _, out = esegui(kexec(kathara, lab_path, r, ['vtysh', '-c', f'show ip bgp {rete} json']), timeout=60)
        return r, _percorsi_bgp(_json_o_none(out) or {}, owner)
    out = {}
    for r, percorsi in _parallelo(leggi, routers).values():
        best = next((p for p in percorsi if p['best']), None)
        lav.scrivi(f"{r}: " + (f"AS path {best['aspath'] or '-'} via {best['nexthop'] or best['da']} "
                               f"(local-pref {best['locpref']}, MED {best['med']})" if best else f"nessuna rotta BGP per {rete}"))
        out[r] = percorsi
    return out


def rotta(kathara, lab_path, lab, dev, rete, lav):
    """Come un router raggiunge una rete (o un IP): rotta scelta con il next-hop e tutti
    i percorsi BGP ricevuti con local-pref, MED, AS-path e il motivo della scelta."""
    disp = {d['nome']: d for d in lab['dispositivi']}
    owner = dati.indirizzi(disp)
    sep = '@@SEPARATORE@@'
    script = (f"vtysh -c 'show ip route {rete} json' 2>&1; echo {sep}; "
              f"vtysh -c 'show ip bgp {rete} json' 2>&1")
    lav.scrivi(f"{dev}: show ip route {rete} / show ip bgp {rete}")
    rc, out = esegui(kexec(kathara, lab_path, dev, ['bash', '-c', script]), timeout=60)
    if sep not in out:
        lav.scrivi(out.strip())
        s = suggerimento(out)
        if s:
            lav.scrivi(s)
        return 1
    parte_route, parte_bgp = out.split(sep, 1)
    instradamento = None
    for prefisso, voci in (_json_o_none(parte_route) or {}).items():
        for v in voci if isinstance(voci, list) else []:
            if not v.get('selected'):
                continue
            hops = [{'ip': h.get('ip'), 'dev': h.get('interfaceName'), 'chi': owner.get(h.get('ip') or ''),
                     'lan': dati.lan_di_ip(disp, h.get('ip')) if h.get('ip') else
                     next((it['lan'] for it in disp[dev]['interfacce'] if it['dev'] == h.get('interfaceName')), None),
                     'connessa': bool(h.get('directlyConnected'))}
                    for h in v.get('nexthops', []) if h.get('active', True)]
            instradamento = {'prefisso': prefisso, 'protocollo': v.get('protocol'),
                             'distanza': v.get('distance'), 'metrica': v.get('metric'), 'hop': hops}
    bgp = _json_o_none(parte_bgp) or {}
    percorsi = _percorsi_bgp(bgp, owner)
    lav.risultato = {'dev': dev, 'rete': rete, 'prefisso_bgp': bgp.get('prefix'),
                     'instradamento': instradamento, 'bgp': percorsi,
                     'neighbor': [n['ip'] for n in (disp[dev]['riepilogo'] or {}).get('neighbor', [])]}
    if instradamento:
        h = instradamento['hop'][0] if instradamento['hop'] else {}
        lav.scrivi(f"Rotta scelta: {instradamento['prefisso']} via {h.get('ip') or 'connessa'} "
                   f"({h.get('chi') or h.get('dev') or ''}) [{instradamento['protocollo']}]; {len(percorsi)} percorsi BGP.")
    else:
        lav.scrivi(f"Nessuna rotta verso {rete} nella tabella di {dev}.")
    return 0


def reti_del_lab(lab):
    """Reti da cercare nelle tabelle: subnet delle LAN e network annunciate in BGP."""
    reti = {l['subnet'] for l in lab['lan'] if l['subnet']}
    for d in lab['dispositivi']:
        reti.update((d['riepilogo'] or {}).get('bgp_networks', []))
    out = []
    for r in reti:
        try:
            out.append(ipaddress.ip_network(r, strict=False))
        except ValueError:
            pass
    return [str(r) for r in sorted(out, key=lambda n: (int(n.network_address), n.prefixlen))]


def tabelle(kathara, lab_path, lab, lav):
    """Per ogni router: quali reti del lab sono nella tabella di routing (rotta esatta,
    coperta da una rotta più ampia o mancante) e verso chi. È il controllo 'kernel_routes'
    della correzione automatica."""
    disp = {d['nome']: d for d in lab['dispositivi']}
    owner = dati.indirizzi(disp)
    router = [d['nome'] for d in lab['dispositivi'] if d['tipo'] == 'router']
    reti = reti_del_lab(lab)

    def leggi(r):
        # tabella di FRR: a differenza di 'ip -j route' elenca i next-hop anche per il multipath
        rc, out = esegui(kexec(kathara, lab_path, r, ['vtysh', '-c', 'show ip route json']), timeout=60)
        tab = _json_o_none(out)
        return tab if tab is not None else {'_errore': out.strip()[-300:]}
    lav.scrivi(f"Lettura delle tabelle di {len(router)} router ({len(reti)} reti del lab)...")
    lette = _parallelo(leggi, router)
    celle, errori = {}, {}
    for r in router:
        tab = lette[r]
        if '_errore' in tab:
            errori[r] = tab['_errore']
            continue
        rotte = []
        for prefisso, voci in tab.items():
            for v in voci if isinstance(voci, list) else []:
                if not v.get('selected') or v.get('protocol') == 'local':
                    continue
                hop = [h for h in v.get('nexthops', []) if h.get('active', True)]
                x = {'dst': prefisso, 'protocol': v.get('protocol'),
                     'nexthops': [{'gateway': h.get('ip'), 'dev': h.get('interfaceName', '')} for h in hop]}
                try:
                    rotte.append((ipaddress.ip_network(prefisso, strict=False), x))
                except ValueError:
                    pass
        celle[r] = {}
        for rete in reti:
            n = ipaddress.ip_network(rete)
            esatta = next((x for net, x in rotte if net == n), None)
            coprenti = sorted(((net, x) for net, x in rotte if net != n and n.subnet_of(net)),
                              key=lambda t: -t[0].prefixlen)
            x, tipo = (esatta, 'esatta') if esatta else ((coprenti[0][1], 'coperta') if coprenti else (None, 'mancante'))
            if x is None:
                # l'aggregato che il router annuncia lui stesso (network X/8) non è nella sua tabella
                if rete in (disp[r]['riepilogo'] or {}).get('bgp_networks', []):
                    celle[r][rete] = {'tipo': 'propria'}
                    continue
                # aggregato assente ma con le sue sottoreti presenti (es. 40.0.0.0/8 e 40.40.1.0/24)
                dentro = [(net, y) for net, y in rotte if net != n and net.subnet_of(n)]
                if dentro:
                    celle[r][rete] = {'tipo': 'specifiche', 'protocollo': dentro[0][1]['protocol'],
                                      'da': ', '.join(str(net) for net, _ in dentro[:4]) + ('…' if len(dentro) > 4 else '')}
                else:
                    celle[r][rete] = {'tipo': 'mancante'}
                continue
            # multipath: i next-hop sono nella lista 'nexthops' invece che in 'gateway'
            gws = [x['gateway']] if x.get('gateway') else [h.get('gateway') for h in x.get('nexthops', []) if h.get('gateway')]
            celle[r][rete] = {'tipo': tipo, 'da': x.get('dst'), 'protocollo': x.get('protocol'),
                              'via': ', '.join(gws), 'chi': ', '.join(owner.get(g, g) for g in gws),
                              'dev': x.get('dev') or ', '.join(h.get('dev', '') for h in x.get('nexthops', [])),
                              'connessa': not gws}
    lav.risultato = {'router': router, 'reti': reti, 'celle': celle, 'errori': errori}
    mancanti = sum(1 for c in celle.values() for v in c.values() if v['tipo'] == 'mancante')
    lav.scrivi(f"Fatto: {mancanti} reti mancanti in totale.")
    return 0


def interfacce_reali(kathara, lab_path, lab, lav):
    """Stato reale delle interfacce nei container (up/down e IP assegnati)."""
    nomi = [d['nome'] for d in lab['dispositivi']]

    def leggi(n):
        rc, out = esegui(kexec(kathara, lab_path, n, ['ip', '-j', 'addr']), timeout=60)
        try:
            dati_ip = json.loads(out[out.index('['):])
        except ValueError:
            return {'_errore': out.strip()[-200:]}
        return {x.get('ifname'): {'stato': x.get('operstate'),
                                  'ip': [f"{a['local']}/{a['prefixlen']}" for a in x.get('addr_info', [])
                                         if a.get('family') == 'inet']}
                for x in dati_ip}
    lav.scrivi(f"Lettura delle interfacce di {len(nomi)} dispositivi...")
    lav.risultato = _parallelo(leggi, nomi)
    lav.scrivi("Fatto.")
    return 0


TRADUZIONI_VTYSH = {
    'Unknown command': "FRR non capisce questa riga e la ignora (errore di battitura, valore non valido o comando nel blocco sbagliato)",
    'Ambiguous command': "comando ambiguo (abbreviato troppo): FRR lo ignora",
    'Command incomplete': "comando incompleto: manca una parte, FRR lo ignora",
}


def sintassi_frr(kathara, lab_path, lab, lav):
    """'vtysh --dryrun' sul frr.conf attuale di ogni router: rilegge il file senza applicarlo
    e riporta le righe che FRR scarterebbe, con il numero di riga. Il file arriva nel
    container in base64 (nessun carattere del file può diventare un comando)."""
    router = [d['nome'] for d in lab['dispositivi'] if d['tipo'] == 'router'
              and os.path.exists(os.path.join(lab_path, d['nome'], 'etc', 'frr', 'frr.conf'))]

    def leggi(r):
        with open(os.path.join(lab_path, r, 'etc', 'frr', 'frr.conf'), 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('ascii')
        script = (f"echo {b64} | base64 -d > /tmp/controllo_frr.conf && "
                  f"vtysh --dryrun -f /tmp/controllo_frr.conf 2>&1; echo @@RC=$?")
        rc, out = esegui(kexec(kathara, lab_path, r, ['bash', '-c', script]), timeout=60)
        if '@@RC=' not in out:
            return {'errore': out.strip()[-300:]}
        righe = []
        for m in re.finditer(r'^line (\d+): % ([^\[:\n]+)(?:\[\d+\])?:\s*(.*)$', out, re.M):
            tipo = m.group(2).strip()
            righe.append({'riga': int(m.group(1)), 'testo': ' '.join(m.group(3).split()), 'gravita': 'errore',
                          'messaggio': TRADUZIONI_VTYSH.get(tipo, tipo)})
        return {'righe': righe}

    lav.scrivi(f"Controllo della sintassi di frr.conf su {len(router)} router (vtysh --dryrun)...")
    lav.risultato = _parallelo(leggi, router)
    n = sum(len(x.get('righe', [])) for x in lav.risultato.values())
    for r in router:
        x = lav.risultato[r]
        if x.get('errore'):
            lav.scrivi(f"  {r}: non controllato ({x['errore'][-120:]})")
        for e in x.get('righe', []):
            lav.scrivi(f"  {r} riga {e['riga']}: {e['testo']}  ->  {e['messaggio']}")
    lav.scrivi(f"Fatto: {n} righe che FRR scarterebbe." if n else "✔ Nessuna riga scartata da FRR.")
    return 0


def membri_lan(lab, lan):
    """[(dispositivo, interfaccia)] collegati a una LAN."""
    return [(d['nome'], it['dev']) for d in lab['dispositivi'] for it in d['interfacce'] if it['lan'] == lan]


def _router_id_ospf(kathara, lab_path, router):
    return (_json_o_none(esegui(kexec(kathara, lab_path, router, ['vtysh', '-c', 'show ip ospf json']),
                                timeout=30)[1]) or {}).get('routerId')


def imposta_link(kathara, lab_path, lab, lan, acceso, lav):
    """Guasto simulato: 'ip link set <eth> down' (o up) su tutti i dispositivi della LAN.
    Vale solo a lab acceso, i file non cambiano; con up gli IP e le rotte connesse tornano.
    Se un router usava come Router ID OSPF un IP di quel link, FRR gli cambia identità e
    OSPF resta bloccato (visto su tennis: percorsi rotti per minuti, ok dopo un clear):
    in quel caso si riavvia il processo OSPF di quel router."""
    verso = 'up' if acceso else 'down'
    membri = membri_lan(lab, lan)
    disp = {d['nome']: d for d in lab['dispositivi']}
    ospf = sorted({m[0] for m in membri if 'ospfd' in disp[m[0]]['demoni']})
    rid_prima = _parallelo(lambda r: _router_id_ospf(kathara, lab_path, r), ospf)
    esiti = _parallelo(lambda m: esegui(kexec(kathara, lab_path, m[0], ['ip', 'link', 'set', m[1], verso]), timeout=60),
                       membri)
    rc = 0
    for m in membri:
        r, out = esiti[m]
        lav.scrivi(f"{m[0]} {m[1]} {verso}: " + ('ok' if r == 0 else 'errore ' + out.strip()[-200:]))
        rc = rc or r
    if ospf:
        time.sleep(5)
        rid_dopo = _parallelo(lambda r: _router_id_ospf(kathara, lab_path, r), ospf)
        for r in ospf:
            if rid_prima[r] and rid_dopo[r] and rid_prima[r] != rid_dopo[r]:
                lav.scrivi(f"{r}: il Router ID OSPF è cambiato ({rid_prima[r]} -> {rid_dopo[r]}) perché usava un IP di "
                           f"questo link. Così OSPF si blocca (informazioni vecchie e nuove mescolate): riavvio il "
                           f"processo OSPF di {r} (clear ip ospf process). Un router con 'ospf router-id' fisso non ne soffre.")
                esegui(kexec(kathara, lab_path, r, ['vtysh', '-c', 'clear ip ospf process']), lav, timeout=60)
    lav.scrivi(f"Link {lan} {'riacceso' if acceso else 'spento'}." + ('' if acceso else
               " Usa 'Attendi convergenza' e poi 'Verifica percorso' per vedere il percorso di riserva."))
    lav.risultato = {'lan': lan, 'acceso': acceso, 'membri': [f"{a} {b}" for a, b in membri]}
    return rc


def avvio_lab(base, lab):
    """Ora (epoch) in cui è stato avviato il lab, dal container più vecchio; None se
    spento o se docker non è utilizzabile."""
    docker = shutil.which('docker')
    if not docker:
        return None
    p = os.path.join(base, lab)
    hash_ok = {hash_lab(c) for c in {os.path.abspath(p), os.path.realpath(p)}}
    try:
        r = subprocess.run([docker, 'ps', '--filter', 'label=app=kathara', '--format',
                            '{{.Label "lab_hash"}}|{{.CreatedAt}}'], capture_output=True, timeout=20, env=_env())
    except (OSError, subprocess.SubprocessError):
        return None
    tempi = []
    for l in r.stdout.decode('utf-8', 'replace').splitlines():
        h, _, quando = l.partition('|')
        if h in hash_ok:
            try:
                tempi.append(datetime.datetime.strptime(quando[:25], '%Y-%m-%d %H:%M:%S %z').timestamp())
            except ValueError:
                pass
    return min(tempi) if tempi else None


def file_modificati(base, lab):
    """File del lab cambiati dopo l'avvio (es. modifiche dal menu Opzioni a lab acceso):
    non sono attivi finché il lab non viene riavviato."""
    avvio = avvio_lab(base, lab)
    if avvio is None:
        return {'avviato': False, 'file': []}
    lab_dir = os.path.join(base, lab)
    cambiati = []
    for radice, cartelle, nomi in os.walk(lab_dir):
        cartelle[:] = [c for c in cartelle if not (radice == lab_dir and c == 'shared') and c != '__pycache__']
        for n in nomi:
            f = os.path.join(radice, n)
            rel = os.path.relpath(f, lab_dir).replace(os.sep, '/')
            if rel == f"{lab}.xml":
                continue
            if os.path.getmtime(f) > avvio + 5:
                cambiati.append(rel)
    return {'avviato': True, 'avvio': time.strftime('%H:%M:%S', time.localtime(avvio)), 'file': sorted(cambiati)}


# -------------------------
# Terminale e archivio
# -------------------------
# come ogni terminale vuole il comando da eseguire (nome del programma -> opzioni prima del comando)
OPZIONI_TERMINALE = {
    'foot': [], 'xdg-terminal-exec': [], 'kitty': [], 'alacritty': ['-e'], 'ghostty': ['-e'],
    'wezterm': ['start', '--'], 'gnome-terminal': ['--'], 'kgx': ['--'], 'ptyxis': ['--'],
    'konsole': ['-e'], 'xfce4-terminal': ['-x'], 'mate-terminal': ['-x'], 'terminator': ['-x'],
    'tilix': ['-e'], 'lxterminal': ['-e'], 'qterminal': ['-e'], 'urxvt': ['-e'], 'st': ['-e'],
    'x-terminal-emulator': ['-e'], 'xterm': ['-e'],
}
ALTRI_TERMINALI = ['xdg-terminal-exec', 'foot', 'alacritty', 'kitty', 'ghostty', 'wezterm', 'gnome-terminal',
                   'kgx', 'ptyxis', 'konsole', 'xfce4-terminal', 'mate-terminal', 'terminator', 'tilix',
                   'lxterminal', 'qterminal', 'x-terminal-emulator', 'urxvt', 'xterm']


def _terminale_di_kathara():
    """Il terminale impostato in Kathará (~/.config/kathara.conf, chiave "terminal"), se c'è."""
    try:
        with open(os.path.join(os.path.expanduser('~'), '.config', 'kathara.conf'), encoding='utf-8') as f:
            t = json.load(f).get('terminal')
        return t if isinstance(t, str) and t.strip() else None
    except (OSError, ValueError, AttributeError):
        return None


def _terminali_candidati():
    """[(eseguibile, opzioni)] in ordine: quello di Kathará, $TERMINAL, poi quelli noti; senza doppioni."""
    nomi = [_terminale_di_kathara()]
    try:
        nomi += shlex.split(os.environ.get('TERMINAL', ''))[:1]
    except ValueError:
        pass
    nomi += ALTRI_TERMINALI
    out, visti = [], set()
    for n in nomi:
        exe = shutil.which(n) if n else None
        if not exe or os.path.realpath(exe) in visti:
            continue
        visti.add(os.path.realpath(exe))
        out.append((exe, OPZIONI_TERMINALE.get(os.path.basename(exe), ['-e'])))
    return out


def _env_finestra():
    """Ambiente per un programma con finestra: nell'eseguibile PyInstaller si toglie il
    LD_LIBRARY_PATH delle sue librerie (come per il browser), altrimenti il terminale non parte."""
    env = dict(os.environ)
    if getattr(sys, 'frozen', False):
        orig = env.get('LD_LIBRARY_PATH_ORIG')
        if orig is not None:
            env['LD_LIBRARY_PATH'] = orig
        else:
            env.pop('LD_LIBRARY_PATH', None)
    return env


def apri_terminale(kathara, lab_path, dev):
    """Apre `kathara connect` in una nuova finestra. Ritorna (ok, messaggio, comando)."""
    args = [kathara or 'kathara', 'connect', '-d', lab_path, dev]
    comando = testo_comando(['kathara', 'connect', '-d', lab_path, dev])
    if sys.platform.startswith('win'):
        subprocess.Popen(args, creationflags=subprocess.CREATE_NEW_CONSOLE)
        return True, 'Terminale aperto in una nuova finestra.', comando
    for exe, opz in _terminali_candidati():
        try:
            p = subprocess.Popen([exe] + opz + args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True, env=_env_finestra())
        except OSError:
            continue
        try:
            # un terminale che non riesce ad aprirsi (niente schermo, opzioni sbagliate) esce subito
            if p.wait(timeout=0.8) != 0:
                continue
        except subprocess.TimeoutExpired:
            pass
        return True, f"Terminale aperto con {os.path.basename(exe)}.", comando
    return False, 'Nessun terminale grafico trovato: copia il comando in un terminale.', comando


def crea_archivio(base, lab, nome, formato):
    """Archivio del lab per la consegna: lo crea il motore (core/archivio.py), lo stesso del terminale.
    Ritorna (percorso, elenco dei file, comando equivalente, esclusi)."""
    from core.archivio import crea_archivio as crea
    return crea(base, lab, nome, formato)




# -------------------------
# Pagine web e apache2 (spiegazioni e bersagli in core/web.py, uguali per il terminale)
# -------------------------
def _diagnosi_rete(kathara, lab_path, dev, ip, chi, lav=None):
    """(esito, spiegazione) quando la pagina non arriva per la rete: prima `ip route get` sul client
    (senza rotta = gateway), poi traceroute per sapere quale router ferma i pacchetti."""
    rc, out = esegui(kexec(kathara, lab_path, dev, ['ip', 'route', 'get', ip]), timeout=40)
    if rc != 0:
        return ('gateway', web.SENZA_GATEWAY) if 'unreachable' in out.lower() else None
    if lav is not None:
        lav.scrivi(f"\ntraceroute -n {ip}:")
    rc, out = esegui(kexec(kathara, lab_path, dev, ['traceroute', '-n', '-w', '1', '-q', '1', '-m', '12', ip]),
                     lav, timeout=60)
    return web.spiega_traceroute(out, ip, chi) if 'traceroute to' in out else None


def _links(kathara, lab_path, dev, indirizzo, lav=None, stato=None):
    """(esito, spiegazione, testo) di links -dump da dev verso indirizzo."""
    rc, out = esegui(kexec(kathara, lab_path, dev, web.comando_links(indirizzo)), lav, timeout=web.ATTESA + 40)
    s = suggerimento(out) if rc != 0 else None
    if s:
        return 'errore', s.lstrip('-> '), out
    esito, spiegazione = web.spiega_links(rc, out, indirizzo)
    ip = web.ip_del_bersaglio(stato, indirizzo) if stato else None
    if esito == 'rete' and ip:
        d = _diagnosi_rete(kathara, lab_path, dev, ip, web.proprietari(stato), lav)
        if d:
            esito, spiegazione = d
    return esito, spiegazione, out


def pagina_web(kathara, lab_path, dev, indirizzo, lav, stato=None):
    """Pannello del dispositivo: la pagina in Output e, se non arriva, perché."""
    esito, spiegazione, _ = _links(kathara, lab_path, dev, indirizzo, lav, stato)
    lav.scrivi(('\n' if esito == 'ok' else '\n-> ') + spiegazione)
    lav.risultato = {'esito': esito, 'spiegazione': spiegazione}
    return 0 if esito == 'ok' else 1


def apache_attivi(kathara, lab_path, nomi):
    """{server: True/False/None}: None se non si è potuto chiedere (es. dispositivo spento)."""
    def chiedi(n):
        rc, out = esegui(kexec(kathara, lab_path, n, ['systemctl', 'is-active', 'apache2']), timeout=40)
        ultima = (out.strip().splitlines() or [''])[-1].strip()
        return True if ultima == 'active' else (False if ultima in ('inactive', 'failed', 'activating', 'deactivating') else None)
    return _parallelo(chiedi, nomi) if nomi else {}


def verifica_web(kathara, lab_path, stato, client, lav):
    """Scheda Test: stato di apache2 su ogni server, poi links da `client` verso ogni IP e nome."""
    server, bersagli = web.server_web(stato), web.bersagli_web(stato)
    attivi = apache_attivi(kathara, lab_path, [x['nome'] for x in server])
    for x in server:
        a = attivi.get(x['nome'])
        lav.scrivi(f"{x['nome']}: apache2 " + ('attivo' if a else 'spento' if a is False else 'stato non letto'))

    def prova(i):
        b = bersagli[i]
        esito, spiegazione, out = _links(kathara, lab_path, client, b['indirizzo'], stato=stato)
        if esito == 'apache' and attivi.get(b['server']) is False:
            spiegazione = f"apache2 è spento su {b['server']}: va avviato (systemctl start apache2)"
        return dict(b, esito=esito, spiegazione=spiegazione, riga=web.prima_riga(out) if esito == 'ok' else '')
    pagine = list(_parallelo(prova, list(range(len(bersagli)))).values())
    for p in pagine:
        lav.scrivi(f"{client} -> {p['indirizzo']}: " + ('ok, ' + p['riga'] if p['esito'] == 'ok' else p['spiegazione']))
    lav.risultato = {'client': client, 'server': [dict(x, attivo=attivi.get(x['nome'])) for x in server], 'pagine': pagine}
    ko = sum(p['esito'] != 'ok' for p in pagine) + sum(attivi.get(x['nome']) is not True for x in server)
    lav.scrivi(f"Fatto: {ko} {'problema' if ko == 1 else 'problemi'}." if ko else 'Fatto: tutte le pagine arrivano.')
    return 0


def risoluzione(kathara, lab_path, stato, client, nome, lav):
    """Fase 6, "Risoluzione di un nome": la catena dai file (core/risoluzione.py) e, sul lab acceso,
    dig dal client e una domanda non ricorsiva a ogni server della catena, con la spiegazione."""
    from core import risoluzione as ris
    r = ris.controlla_nome(stato, client, nome)
    lav.scrivi(f"Dai file ({client} -> {r['nome']}):")
    for p in r['passi']:
        lav.scrivi(('  ok   ' if p['ok'] else '  ??   ' if p['ok'] is None else '  NO   ') + p['testo']
                   + (f"  -> {p['rimedio']}" if p['rimedio'] else ''))
    prove = []
    if kathara:
        cmds = ris.comandi_dig(r['nome'], r['catena_ip'])
        chi = [None] + [f"{s} ({ip})" for s, ip in zip(r['catena'], r['catena_ip'])]
        for c, x in zip(cmds, chi):
            rc, out = esegui(kexec(kathara, lab_path, client, c), timeout=30)
            esito, spiegazione = ris.spiega_dig(out, r['nome'], x)
            lav.scrivi(f"{' '.join(c)}: {esito} - {spiegazione}")
            prove.append({'comando': ' '.join(c), 'chi': x, 'esito': esito, 'spiegazione': spiegazione, 'uscita': out[-1500:]})
            if suggerimento(out):
                lav.scrivi(suggerimento(out))
                break
    r['dig'] = prove
    lav.risultato = r
    return 0
