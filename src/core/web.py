"""
Pagine web e apache2: server web del lab, nomi DNS che portano a loro, comando `links` da un client
e spiegazione dell'esito. Usato dalla GUI (pannello del dispositivo e scheda Test) e dal terminale
(menu 4); qui non si esegue niente: i comandi li lancia chi chiama (kathara exec) o l'utente.

Esiti di `timeout 8 links -dump http://<x>/` misurati con Kathará (kathara/base, 2026-11-22):
pagina -> codice 0; 'Host not found' (nome non risolto, resolver o DNS spenti); 'Connection refused'
(apache2 spento); 'Network is unreachable' (client senza gateway, oppure un router lungo il percorso
senza la rotta: è lo stesso messaggio); codice 124 (nessuna risposta). Per i problemi di rete la
diagnosi continua con `ip route get` sul client e `traceroute` (spiega_traceroute), che dicono se
manca il gateway del client o quale router ferma i pacchetti.
"""
import ipaddress
import re

from .stato import _nome_assoluto

ATTESA = 8                       # secondi concessi a links prima di dichiarare "nessuna risposta"
COMANDO_APACHE = 'systemctl is-active apache2 || systemctl start apache2'
_RE_NOME = re.compile(r'^(?=.{1,253}$)[A-Za-z0-9_](?:[A-Za-z0-9_-]{0,62})(?:\.[A-Za-z0-9_](?:[A-Za-z0-9_-]{0,62}))*\.?$')


def indirizzo_valido(x):
    """IP o nome DNS (lettere, cifre, '-', '_' e punti): sicuro dentro un URL e un comando."""
    x = str(x or '').strip()
    try:
        ipaddress.ip_address(x)
        return True
    except ValueError:
        return bool(_RE_NOME.match(x)) and not x.replace('.', '').isdigit()


_RE_PERCORSO = re.compile(r'^/[A-Za-z0-9._~/%-]*$')


def dividi_url(x):
    """'web.com', 'web.com/~guest/' o 'http://web.com/~guest/' -> ('web.com', '/~guest/'); None se non
    è un indirizzo sicuro (IP o nome, e un percorso con soli lettere, cifre e . _ ~ / % -)."""
    s = str(x or '').strip()
    if s.lower().startswith('http://'):
        s = s[7:]
    host, barra, resto = s.partition('/')
    percorso = '/' + resto if barra else '/'
    if not indirizzo_valido(host) or not _RE_PERCORSO.match(percorso):
        return None
    return host, percorso


def url_valido(x):
    return dividi_url(x) is not None


def comando_links(indirizzo):
    """Argomenti del comando da eseguire sul client (indirizzo: IP, nome o URL con il percorso)."""
    parti = dividi_url(indirizzo)
    if not parti:
        raise ValueError(f"Indirizzo non valido: {indirizzo}")
    return ['timeout', str(ATTESA), 'links', '-dump', f"http://{parti[0]}{parti[1]}"]


def server_web(stato):
    """[{'nome', 'ip': [IP senza maschera]}] dei server web (tipo www o con apache2 nello startup)."""
    out = []
    for n, d in sorted(stato['dispositivi'].items()):
        if d.get('tipo') == 'www' or d.get('apache'):
            ips = [it['ip'].split('/')[0] for it in d['interfacce'] if it['ip']]
            out.append({'nome': n, 'ip': ips})
    return out


def nomi_web(stato):
    """[{'nome', 'server', 'ip', 'via'}]: nomi delle zone DNS del lab (record A, e CNAME che portano a un
    record A) che puntano a un IP di un server web. 'via' è 'A' oppure 'CNAME <destinazione>'."""
    di_ip = {ip: s['nome'] for s in server_web(stato) for ip in s['ip']}
    a, cname = {}, {}
    for d in stato['dispositivi'].values():
        for z in ((d.get('dns') or {}).get('zone') or []):
            if z['tipo'] != 'master' or z['zona'] == '.':
                continue
            for r in z['record']:
                if r['tipo'] == 'A' and r['valore'] in di_ip:
                    a.setdefault(r['nome'], (di_ip[r['valore']], r['valore']))
                elif r['tipo'] == 'CNAME':
                    cname.setdefault(r['nome'], _nome_assoluto(r['valore'], z['zona']))
    out = [{'nome': n, 'server': a[n][0], 'ip': a[n][1], 'via': 'A'} for n in sorted(a)]
    for n, dest in sorted(cname.items()):
        visti, x = {n}, dest
        while x in cname and x not in visti:          # catene di CNAME (senza cicli)
            visti.add(x)
            x = cname[x]
        if x in a and n not in a:
            out.append({'nome': n, 'server': a[x][0], 'ip': a[x][1], 'via': f"CNAME {dest}"})
    return out


def bersagli_web(stato):
    """[{'indirizzo', 'server', 'ip', 'tipo': 'ip' | 'nome', 'via'}]: prima gli IP, poi i nomi."""
    out = [{'indirizzo': ip, 'server': s['nome'], 'ip': ip, 'tipo': 'ip', 'via': ''} for s in server_web(stato) for ip in s['ip']]
    out += [{'indirizzo': n['nome'], 'server': n['server'], 'ip': n['ip'], 'tipo': 'nome', 'via': n['via']} for n in nomi_web(stato)]
    return out


def ip_del_bersaglio(stato, indirizzo):
    """IP da usare per la diagnosi: l'indirizzo stesso, o il record A di un nome noto (None se no)."""
    x = (dividi_url(indirizzo) or (str(indirizzo or '').strip(), ''))[0]
    try:
        return str(ipaddress.ip_address(x))
    except ValueError:
        n = x.rstrip('.').lower()
        return next((b['ip'] for b in nomi_web(stato) if b['nome'] == n), None)


def proprietari(stato):
    """{IP: dispositivo} per dare un nome agli hop del traceroute."""
    return {it['ip'].split('/')[0]: n for n, d in stato['dispositivi'].items() for it in d['interfacce'] if it['ip']}


def client_web(stato):
    """Dispositivi da cui provare le pagine: tutti tranne i router (kathara/frr non ha links)."""
    return [n for n, d in sorted(stato['dispositivi'].items()) if d.get('tipo') != 'router' and d['interfacce']]


def spiega_links(codice, testo, indirizzo=''):
    """(esito, spiegazione) dalla sola uscita di links. esito: 'ok', 'dns', 'apache', 'rete', 'vuota',
    'errore'; per 'rete' la diagnosi (gateway o router) la danno ip route get e spiega_traceroute."""
    t = testo or ''
    if codice == 0 and re.search(r'\bNot Found\b', t) and 'requested URL' in t:
        utente = re.search(r'/~([A-Za-z0-9_.-]+)', indirizzo or '')
        return 'non_trovata', ("apache2 risponde ma la pagina non c'è (404 Not Found)" + (
            f": per /~{utente.group(1)}/ servono il modulo userdir (a2enmod userdir), l'utente {utente.group(1)} e "
            f"/home/{utente.group(1)}/public_html/index.html sul server" if utente else ": controlla il percorso e i file in /var/www/html"))
    if codice == 0 and t.strip():
        return 'ok', 'pagina ricevuta'
    if codice == 0:
        return 'vuota', "il server ha risposto con una pagina vuota: controlla index.html sul server"
    if 'Host not found' in t:
        return 'dns', ("nome non risolto: controlla il nameserver del client (resolv.conf), che il resolver "
                       f"sia acceso e che le zone DNS abbiano il record di {indirizzo or 'quel nome'}")
    if 'Connection refused' in t:
        return 'apache', "la rete arriva al server ma apache2 non risponde: controlla che apache2 sia avviato sul server"
    if 'Network is unreachable' in t:
        return 'rete', ("rete irraggiungibile: manca la rotta sul client (gateway) o su un router lungo il "
                        "percorso (guarda il traceroute)")
    if 'No route to host' in t:
        return 'rete', "host irraggiungibile: controlla l'IP del server e il routing (ping e traceroute)"
    if codice == 124:
        return 'rete', (f"nessuna risposta entro {ATTESA} secondi: controlla il routing (ping e traceroute verso "
                        "il server) e il gateway del server")
    return 'errore', "links non è riuscito: guarda l'output sopra"


SENZA_GATEWAY = "il client non ha una rotta verso quella rete: controlla il gateway del client"
_RE_HOP = re.compile(r'^\s*(\d+)\s+(\S+)(.*)$', re.M)


def spiega_traceroute(testo, dest, chi=None):
    """(esito, spiegazione) da `traceroute -n -q 1` del client verso dest. chi = {IP: dispositivo}.
    Esempi misurati: ' 1  20.20.1.1  0.352 ms !N' (r1 senza rotta), hop che rispondono e poi solo
    '*' (andata o ritorno mancanti dopo l'ultimo che risponde)."""
    chi = chi or {}
    nome = lambda ip: f"{chi[ip]} ({ip})" if ip in chi else ip
    hops = []
    for n, ip, resto in _RE_HOP.findall(testo or ''):
        f = re.search(r'!(\w)', resto)
        hops.append((int(n), None if ip == '*' else ip, f.group(1) if f else None))
    for _, ip, f in hops:
        if not f or not ip:
            continue
        if f == 'N':
            return 'rete', (f"{nome(ip)} non ha una rotta verso {dest}: controlla che la rete del server sia "
                            "annunciata in BGP (Opzioni 6: network o aggregato) e ridistribuita nell'IGP "
                            "(redistribute bgp), oppure una rotta statica")
        if f == 'H':
            return 'rete', f"{nome(ip)} non raggiunge {dest} (host irraggiungibile): server spento o IP sbagliato"
        if f in ('X', 'P'):
            return 'rete', f"{nome(ip)} rifiuta i pacchetti verso {dest} (comunicazione vietata): c'è un filtro"
        return 'rete', f"{nome(ip)} risponde con un errore (!{f}) verso {dest}"
    risposti = [ip for _, ip, _ in hops if ip]
    if risposti and risposti[-1] == dest:
        return 'rete', (f"{nome(dest)} risponde al traceroute ma la pagina non arriva: controlla apache2 sul "
                        "server e il ritorno verso il client")
    if risposti:
        return 'rete', (f"i pacchetti si fermano dopo {nome(risposti[-1])}: dal router successivo manca la "
                        "rotta all'andata o al ritorno verso il client (annunci BGP, ridistribuzione, gateway "
                        "del server)")
    return 'rete', "nessun router risponde al traceroute: controlla il router della LAN del client"


def prima_riga(testo):
    return next((l.strip() for l in (testo or '').splitlines() if l.strip()), '')


def comandi_da_incollare(stato):
    """Testo per il terminale (menu 4): comandi links per i client e apache2 per i server."""
    righe = []
    server, bersagli = server_web(stato), bersagli_web(stato)
    if not server:
        return 'Nessun server web nel lab (dispositivi con apache2).'
    righe.append("=== Pagine web: da incollare su un client (host, dns o server) ===")
    for b in bersagli:
        nota = f"   # {b['server']}" + (f", {b['via']}" if b['via'] and b['via'] != 'A' else '')
        righe.append(' '.join(comando_links(b['indirizzo'])) + nota)
    righe.append('')
    righe.append("=== apache2: da incollare su " + ', '.join(s['nome'] for s in server) + " ===")
    righe.append(COMANDO_APACHE)
    return '\n'.join(righe)
