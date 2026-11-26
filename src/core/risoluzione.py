"""
src/core/risoluzione.py
Fase 6, "Risoluzione di un nome": segue la catena che il DNS percorre per risolvere un nome da un
dispositivo del lab e dice il primo anello che manca, con l'operazione che lo sistema.

    client -> nameserver (resolv.conf) -> ricorsione permessa (allow-recursion) -> hint della radice
    (db.root del resolver) -> root -> delega della zona di primo livello (con glue) -> ... -> record A

Dai file (controlla_nome, anche a lab spento) e dalle uscite di dig del lab acceso
(spiega_dig, comandi_dig). Come gli esami del corso: record A, NS, CNAME, deleghe con glue,
resolver locale. La raggiungibilità dei server si vede solo a lab acceso.
"""
import ipaddress
import re

from .modello import parse_reti

MAX_CNAME = 5


def _nome(x):
    x = str(x or '').strip().lower()
    return '.' if x in ('.', '@') else x.rstrip('.')


def _dentro(nome, zona):
    return zona == '.' or nome == zona or nome.endswith('.' + zona)


def _zone(stato, dev, tipo=None):
    d = stato['dispositivi'].get(dev) or {}
    return [z for z in ((d.get('dns') or {}).get('zone') or []) if tipo is None or z['tipo'] == tipo]


def _ip_di(stato, dev):
    return [it['ip'].split('/')[0] for it in stato['dispositivi'][dev]['interfacce'] if it['ip']]


def _record(zona, nome, tipo):
    return [r for r in zona['record'] if _nome(r['nome']) == nome and r['tipo'] == tipo]


def _ricorsione(stato, resolver, ip_client):
    """(permessa, spiegazione) per allow-recursion del resolver (bind: senza la riga solo
    localnets e localhost)."""
    regole = (stato['dispositivi'][resolver].get('dns') or {}).get('allow_recursion')
    locali = [ipaddress.ip_interface(it['ip']).network for it in stato['dispositivi'][resolver]['interfacce'] if it['ip']]
    ip = ipaddress.ip_address(ip_client)
    voci = regole if regole is not None else ['localnets', 'localhost']
    for v in voci:
        v = str(v).strip().lower()
        if v == 'any':
            return True, "allow-recursion any"
        if v == 'localnets' and any(ip in n for n in locali):
            return True, "il client è su una rete del resolver (localnets)"
        if v in ('localnets', 'localhost', 'none', ''):
            continue
        try:
            reti = [ipaddress.ip_network(r) for r in parse_reti(v)]
        except ValueError:
            continue
        if any(ip in n for n in reti):
            return True, f"allow-recursion {v}"
    if regole is None:
        return False, (f"{resolver} non ha allow-recursion: bind permette la ricorsione solo alle sue reti, e "
                       f"{ip_client} non è su una di esse")
    return False, f"allow-recursion {{ {'; '.join(regole)}; }} di {resolver} non comprende {ip_client}"


def controlla_nome(stato, client, nome):
    """Catena di risoluzione di `nome` da `client` letta dai file. Restituisce
    {'nome', 'client', 'ok': bool | None (non controllabile), 'ip': IP trovato o None,
     'passi': [{'anello', 'ok', 'testo', 'rimedio'}], 'catena': [server interrogati, in ordine],
     'catena_ip': [IP con cui il resolver li interroga]}."""
    nome = _nome(nome)
    passi, catena, catena_ip = [], [], []
    out = {'nome': nome, 'client': client, 'ok': None, 'ip': None, 'passi': passi, 'catena': catena,
           'catena_ip': catena_ip}

    def passo(anello, ok, testo, rimedio=''):
        passi.append({'anello': anello, 'ok': ok, 'testo': testo, 'rimedio': rimedio})
        if ok is False or ok is None:
            out['ok'] = ok
        return ok

    d = stato['dispositivi'].get(client)
    if not d:
        passo('client', False, f"{client} non è un dispositivo del lab.")
        return out
    ip_client = next(iter(_ip_di(stato, client)), None)
    ns = list(d.get('nameserver') or [])
    if not ns:
        passo('resolver', False, f"{client} non ha un nameserver (etc/resolv.conf assente o vuoto).",
              f"Resolver di {client} (Opzioni 5 / pannello del dispositivo).")
        return out
    proprietari = stato['proprietari']
    resolver = proprietari.get(ns[0])
    if not resolver:
        passo('resolver', None, f"{client} usa {ns[0]}, che non è nel lab: non posso seguire la catena.")
        return out
    if not stato['dispositivi'][resolver].get('dns'):
        passo('resolver', False, f"{client} usa {ns[0]} ({resolver}), che non è un server DNS.",
              f"Resolver di {client}: scegli un server DNS del lab.")
        return out
    passo('resolver', True, f"{client} usa {ns[0]} ({resolver}).")
    catena.append(resolver)
    catena_ip.append(ns[0])

    # il resolver è già autoritativo per il nome?
    def risolvi_su(server, n):
        z = max((z for z in _zone(stato, server, 'master') if _dentro(n, _nome(z['zona']))),
                key=lambda z: len(_nome(z['zona'])), default=None)
        return z

    if risolvi_su(resolver, nome) is None:
        ok, perche = _ricorsione(stato, resolver, ip_client) if ip_client else (False, f"{client} non ha IP")
        if not passo('ricorsione', ok, perche[0].upper() + perche[1:] + '.',
                     '' if ok else f"Ricorsione su {resolver}: allow-recursion con la rete di {client} (es. 0/0), "
                                   f"con 'File a righe' su named.conf.options."):
            return out
        # hint della radice nel resolver
        hint = next((z for z in _zone(stato, resolver) if _nome(z['zona']) == '.'), None)
        radici = [n for n in stato['dispositivi'] if any(_nome(z['zona']) == '.' for z in _zone(stato, n, 'master'))]
        if not hint:
            passo('radice', False, f"{resolver} non ha la zona '.' (db.root): non sa da dove partire.",
                  "Ricrea il server DNS con il tipo per '.' (hint o master).")
            return out
        if hint['tipo'] == 'master':
            server = resolver
            passo('radice', True, f"{resolver} è lui stesso il root ('.' master).")
        else:
            ns_root = [_nome(r['valore']) for r in _record(hint, '.', 'NS')]
            ip_root = [r['valore'] for r in hint['record'] if r['tipo'] == 'A' and _nome(r['nome']) in ns_root]
            server = next((proprietari.get(ip) for ip in ip_root if proprietari.get(ip) in radici), None)
            if not server:
                dove = f" (il root del lab è {', '.join(f'{r} {_ip_di(stato, r)[0]}' for r in radici)})" if radici else ''
                passo('radice', False, f"Il db.root di {resolver} punta a {', '.join(ip_root) or 'nessun IP'}, che non è il "
                                       f"server root del lab{dove}.",
                      f"db.root di {resolver} con l'IP del root ('File a righe').")
                return out
            passo('radice', True, f"Il db.root di {resolver} punta a {server} ({', '.join(ip_root)}).")
            catena.append(server)
            catena_ip.append(next(ip for ip in ip_root if proprietari.get(ip) == server))
    else:
        server = resolver

    # dal root (o dal server autoritativo) giù fino al record
    visti, cname = set(), 0
    while True:
        if (server, nome) in visti:
            passo('deleghe', False, f"Le deleghe per {nome} girano in tondo ({server}).")
            return out
        visti.add((server, nome))
        z = risolvi_su(server, nome)
        if z is None:
            passo('zona', False, f"{server} non ha una zona che contiene {nome}.",
                  f"Delega o zona per {nome} su {server}.")
            return out
        zona = _nome(z['zona'])
        # BIND non carica una zona il cui nameserver sta dentro la zona ma non ha un record A
        senza_a = [n for n in (_nome(r['valore']) for r in _record(z, zona, 'NS'))
                   if _dentro(n, zona) and not _record(z, n, 'A')]
        if senza_a:
            passo('zona', False, f"{server} non carica la zona {zona}: il nameserver {senza_a[0]} è dentro la zona "
                                 f"ma non ha il record A (BIND: 'NS has no address records').",
                  f"Record A di {senza_a[0]} con l'IP di {server} nella zona {zona} (Record A, o Opzioni 9).")
            return out
        # delega a una zona figlia che contiene il nome
        deleghe = sorted({_nome(r['nome']) for r in z['record'] if r['tipo'] == 'NS'
                          and _nome(r['nome']) != zona and _dentro(nome, _nome(r['nome']))}, key=len, reverse=True)
        if deleghe:
            figlia = deleghe[0]
            nss = [_nome(r['valore']) for r in _record(z, figlia, 'NS')]
            glue = [(n, r['valore']) for n in nss for r in z['record'] if r['tipo'] == 'A' and _nome(r['nome']) == n]
            if not glue:
                passo('deleghe', False, f"{server} delega {figlia} a {', '.join(nss)} senza il record A (glue) del nameserver.",
                      f"Delega di {figlia} su {server} con l'IP del nameserver (Delega una zona / 'File a righe').")
                return out
            prossimo = next((proprietari.get(ip) for _, ip in glue if proprietari.get(ip)), None)
            if not prossimo or not stato['dispositivi'][prossimo].get('dns'):
                passo('deleghe', False, f"{server} delega {figlia} a {glue[0][0]} ({glue[0][1]}), che non è un server DNS del lab.",
                      f"Glue di {figlia} su {server} con l'IP del server che ha la zona {figlia}.")
                return out
            if not any(_nome(x['zona']) == figlia for x in _zone(stato, prossimo, 'master')):
                passo('deleghe', False, f"{server} delega {figlia} a {prossimo}, ma {prossimo} non ha la zona {figlia}.",
                      f"Zona {figlia} su {prossimo}, o delega verso il server giusto.")
                return out
            ip_prossimo = next(ip for _, ip in glue if proprietari.get(ip) == prossimo)
            passo('deleghe', True, f"{server} (zona {zona}) delega {figlia} a {prossimo} ({ip_prossimo}).")
            server = prossimo
            catena.append(server)
            catena_ip.append(ip_prossimo)
            continue
        a = _record(z, nome, 'A')
        if a:
            out['ip'] = a[0]['valore']
            passo('record', True, f"{server} (zona {zona}): {nome} -> {a[0]['valore']}.")
            if out['ok'] is None and all(p['ok'] for p in passi):
                out['ok'] = True
            if out['ip'] not in proprietari:
                passi.append({'anello': 'record', 'ok': None, 'rimedio': '',
                              'testo': f"{a[0]['valore']} non è l'IP di un dispositivo del lab: controlla il record."})
            return out
        c = _record(z, nome, 'CNAME')
        if c and cname < MAX_CNAME:
            cname += 1
            dest = _nome(c[0]['valore'])
            if '.' not in dest:
                dest = f"{dest}.{zona}" if zona != '.' else dest
            passo('record', True, f"{server} (zona {zona}): {nome} è un alias (CNAME) di {dest}.")
            nome = dest
            continue
        passo('record', False, f"Nella zona {zona} di {server} non c'è un record A per {nome}.",
              f"Record A di {nome} nella zona {zona} su {server} ('File a righe' su db.{zona.strip('.')}).")
        return out


# ----------------------------------------------------------------------------- lab acceso

def comandi_dig(nome, catena_ip):
    """Comandi da eseguire sul client: dig normale e una domanda non ricorsiva a ogni server."""
    base = ['dig', '+time=2', '+tries=1']
    return [base + [nome]] + [base + ['+norecurse', f'@{ip}', nome] for ip in catena_ip]


_RE_STATO = re.compile(r'status: (\w+)')


def spiega_dig(testo, nome, chi=None):
    """(esito, spiegazione) di un'uscita di dig: ok | inesistente | rifiutata | errore | irraggiungibile | rinvio."""
    t = testo or ''
    if 'connection timed out' in t or 'no servers could be reached' in t or 'communications error' in t:
        return 'irraggiungibile', (f"{chi or 'Il server'} non risponde: problema di routing fra il client e il server "
                                   f"(Verifica percorso) o named spento sul server.")
    m = _RE_STATO.search(t)
    st = m.group(1) if m else ''
    def sezione(titolo):           # righe della sezione fino alla riga vuota (il glue sta in ADDITIONAL)
        m = re.search(rf';; {titolo} SECTION:\n(.*?)(?:\n\s*\n|\Z)', t, re.S)
        return m.group(1) if m else ''
    risposte = re.findall(r'^\S+\s+\d+\s+IN\s+(A|CNAME)\s+(\S+)', sezione('ANSWER'), re.M)
    if st == 'NOERROR' and risposte:
        return 'ok', f"{nome} -> {', '.join(v for _, v in risposte)}"
    if st == 'NOERROR' and re.search(r'^\S+\s+\d+\s+IN\s+NS\s', sezione('AUTHORITY'), re.M):
        return 'rinvio', f"{chi or 'il server'} rimanda a un altro server (delega): giusto per un server che non ha il nome."
    if st == 'NXDOMAIN':
        return 'inesistente', f"{chi or 'il DNS'} risponde che {nome} non esiste (manca il record o la delega)."
    if st == 'REFUSED':
        return 'rifiutata', f"{chi or 'il resolver'} rifiuta la domanda: ricorsione non permessa per il client (allow-recursion)."
    if st == 'SERVFAIL':
        return 'errore', (f"{chi or 'il resolver'} non riesce a risolvere (SERVFAIL): un server della catena non risponde, "
                          f"una delega è sbagliata o la validazione DNSSEC fallisce (dnssec-validation no).")
    return 'errore', f"Risposta inattesa di dig ({st or 'nessuno stato'})."
