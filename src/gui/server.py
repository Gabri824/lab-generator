"""Server web locale della GUI (solo libreria standard, funziona senza internet).

Ascolta solo su 127.0.0.1. Le richieste che eseguono comandi o modificano file
devono avere l'intestazione X-Lab-Gen: 1 (una pagina di un altro sito non può
aggiungerla) e un Host locale (contro il DNS rebinding).
"""
import ipaddress
import json
import os
import re
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from . import dati, kathara
from .pagina import PAGINA


def open_browser(url):
    """Apre il browser ripulendo LD_LIBRARY_PATH dall'ambiente PyInstaller."""
    lp_key = "LD_LIBRARY_PATH"
    orig_val = os.environ.get(lp_key)
    pyinstaller_orig = os.environ.get(f"{lp_key}_ORIG")

    try:
        if getattr(sys, "frozen", False):
            if pyinstaller_orig is not None:
                os.environ[lp_key] = pyinstaller_orig
            elif lp_key in os.environ:
                del os.environ[lp_key]

        webbrowser.open(url)
    finally:
        if orig_val is not None:
            os.environ[lp_key] = orig_val
        else:
            os.environ.pop(lp_key, None)


class Errore(Exception):
    pass


class Stato:
    def __init__(self, base, gen):
        self.base = base
        self.gen = gen
        self.kathara = kathara.trova_kathara()
        self.versione = None
        self.lavori = kathara.Lavori()
        self.archivi = set()
        self.spenti = {}
        self.server = None

    def link_spenti(self, nome):
        s = self.spenti.get(nome)
        if s and kathara.avvio_lab(self.base, nome) != s['avvio']:
            self.spenti.pop(nome, None)
            return []
        return sorted(s['lan']) if s else []

    def lab_path(self, nome):
        if not dati.nome_valido(nome) or nome not in dati.elenco_lab(self.base):
            raise Errore(f"Lab '{nome}' non trovato in {self.base}")
        return os.path.join(self.base, nome)

    def leggi_lab(self, nome):
        return dati.leggi_lab(self.gen, self.lab_path(nome))

    def serve_kathara(self):
        if not self.kathara:
            raise Errore("Comando 'kathara' non trovato nel PATH: installalo o aggiungilo al PATH.")


def _dispositivo(lab, nome):
    for d in lab['dispositivi']:
        if d['nome'] == nome:
            return d
    raise Errore(f"Dispositivo '{nome}' non presente nel lab")


def _ip(valore):
    try:
        return str(ipaddress.ip_address(str(valore).strip().split('/')[0]))
    except ValueError:
        raise Errore(f"IP non valido: {valore}")


def _rete(valore):
    v = str(valore or '').strip()
    try:
        return str(ipaddress.ip_network(v, strict=False)) if '/' in v else str(ipaddress.ip_address(v))
    except ValueError:
        raise Errore(f"Rete o IP non valido: {v}")


def azione(st, dati_rich):
    tipo = dati_rich.get('azione')
    nome_lab = dati_rich.get('lab', '')
    lab_path = st.lab_path(nome_lab)
    k = st.kathara

    if tipo == 'lclean':
        st.serve_kathara()
        args = [k, 'lclean', '-d', lab_path]
        lid = st.lavori.avvia(f"lclean {nome_lab}", kathara.testo_comando(['kathara'] + args[1:]),
                              lambda lav: kathara.esegui_spiegato(args, lav)[0])
        return {'lavoro': lid}

    if tipo == 'lstart':
        st.serve_kathara()
        accesi = kathara.stato_lab(k, st.base, [nome_lab])[nome_lab]
        if accesi and not dati_rich.get('riavvia'):
            return {'gia_acceso': len(accesi)}
        start = [k, 'lstart', '--noterminals', '-d', lab_path]
        clean = [k, 'lclean', '-d', lab_path]

        def corpo(lav):
            if accesi:
                rc = kathara.esegui_spiegato(clean, lav)[0]
                if rc != 0:
                    return rc
            return kathara.esegui_spiegato(start, lav)[0]
        testo = kathara.testo_comando(['kathara'] + start[1:])
        if accesi:
            testo = kathara.testo_comando(['kathara'] + clean[1:]) + ' && ' + testo
        lid = st.lavori.avvia(f"{'riavvio' if accesi else 'lstart'} {nome_lab}", testo, corpo)
        return {'lavoro': lid}

    if tipo == 'archivio':
        nome = (dati_rich.get('nome') or nome_lab).strip()
        formato = 'zip' if dati_rich.get('formato') == 'zip' else 'tar.gz'
        for suff in ('.tar.gz', '.zip'):
            if nome.endswith(suff):
                nome = nome[:-len(suff)]
        if not dati.nome_valido(nome):
            raise Errore("Nome dell'archivio non valido (lettere, numeri, _ - .)")
        dest, file, comando, esclusi = kathara.crea_archivio(st.base, nome_lab, nome, formato)
        st.archivi.add(os.path.basename(dest))
        st.lavori.annota(f"archivio {nome_lab}", comando, f"OK: {os.path.basename(dest)}")
        return {'percorso': dest, 'file': file, 'comando': comando, 'esclusi': esclusi,
                'scarica': '/api/scarica?nome=' + quote(os.path.basename(dest))}

    st.serve_kathara()
    lab = st.leggi_lab(nome_lab)

    if tipo == 'comando':
        dev = _dispositivo(lab, dati_rich.get('dev'))['nome']
        chiave = dati_rich.get('comando')
        if chiave not in kathara.COMANDI:
            raise Errore('Comando non previsto')
        ip = _ip(dati_rich.get('ip')) if kathara.serve_ip(chiave) else None
        etichetta, cmd = kathara.comando(chiave, ip)
        args = kathara.kexec(k, lab_path, dev, cmd)
        testo = kathara.testo_exec(lab_path, dev, cmd)
        lid = st.lavori.avvia(f"{dev}: {etichetta}", testo, lambda lav: kathara.esegui_spiegato(args, lav, timeout=120)[0])
        return {'lavoro': lid}

    if tipo == 'terminale':
        dev = _dispositivo(lab, dati_rich.get('dev'))['nome']
        ok, msg, comando = kathara.apri_terminale(k, lab_path, dev)
        st.lavori.annota(f"terminale {dev}", comando, 'OK' if ok else 'comando da copiare')
        return {'ok': ok, 'messaggio': msg, 'comando': comando}

    if tipo == 'raggiungibilita':
        lid = st.lavori.avvia(f"raggiungibilità {nome_lab}", 'ping da ogni dispositivo verso tutti gli IP',
                              lambda lav: kathara.raggiungibilita(k, lab_path, lab, lav))
        return {'lavoro': lid}

    if tipo == 'sessioni':
        lid = st.lavori.avvia(f"sessioni BGP/OSPF {nome_lab}",
                              "vtysh -c 'show ip bgp summary json' / 'show ip ospf neighbor json' su ogni router",
                              lambda lav: kathara.sessioni(k, lab_path, lab, lav, set(st.link_spenti(nome_lab))))
        return {'lavoro': lid}

    if tipo == 'percorso':
        dev = _dispositivo(lab, dati_rich.get('dev'))['nome']
        ip = _ip(dati_rich.get('ip'))
        testo = kathara.testo_exec(lab_path, dev, kathara.comando('traceroute', ip)[1])
        lid = st.lavori.avvia(f"percorso {dev} -> {ip}", testo,
                              lambda lav: kathara.percorso(k, lab_path, lab, dev, ip, lav))
        return {'lavoro': lid}

    if tipo == 'ping':
        d = _dispositivo(lab, dati_rich.get('dev'))
        dev = d['nome']
        ip = _ip(dati_rich.get('ip'))
        origine = None
        if dati_rich.get('origine'):
            origine = _ip(dati_rich.get('origine'))
            propri = {x.split('/')[0] for x in [it['ip'] for it in d['interfacce'] if it['ip']] + d['loopback']}
            if origine not in propri:
                raise Errore(f"{origine} non è un indirizzo di {dev}")
        cmd = kathara.comando('ping', ip)[1]
        if origine:
            cmd = cmd[:-1] + ['-I', origine, ip]
        testo = kathara.testo_exec(lab_path, dev, cmd)
        lid = st.lavori.avvia(f"ping {dev} -> {ip}" + (f" (da {origine})" if origine else ''), testo,
                              lambda lav: kathara.ping(k, lab_path, lab, dev, ip, origine, lav))
        return {'lavoro': lid}

    if tipo == 'sintassi_frr':
        lid = st.lavori.avvia(f"sintassi frr.conf {nome_lab}", 'vtysh --dryrun -f frr.conf su ogni router',
                              lambda lav: kathara.sintassi_frr(k, lab_path, lab, lav))
        return {'lavoro': lid}

    if tipo == 'link':
        lan = dati_rich.get('lan')
        if lan not in {l['nome'] for l in lab['lan']}:
            raise Errore(f"LAN '{lan}' non presente nel lab")
        acceso = bool(dati_rich.get('acceso'))
        avvio = kathara.avvio_lab(st.base, nome_lab)
        if not avvio:
            raise Errore('Il lab non è acceso: avvialo prima di simulare un guasto.')
        membri = kathara.membri_lan(lab, lan)

        def corpo(lav):
            rc = kathara.imposta_link(k, lab_path, lab, lan, acceso, lav)
            s = st.spenti.get(nome_lab)
            if not s or s['avvio'] != avvio:
                s = st.spenti[nome_lab] = {'avvio': avvio, 'lan': set()}
            if acceso:
                s['lan'].discard(lan)
            elif rc == 0:
                s['lan'].add(lan)
            return rc
        verso = 'up' if acceso else 'down'
        testo = '; '.join(f"kathara exec {d} -- ip link set {i} {verso}" for d, i in membri)
        lid = st.lavori.avvia(f"{'riaccendi' if acceso else 'spegni'} link {lan}", testo, corpo)
        return {'lavoro': lid}

    if tipo == 'convergenza':
        lid = st.lavori.avvia(f"attendi convergenza {nome_lab}",
                              'sessioni BGP/OSPF rilette ogni 15 s (al massimo 5 minuti)',
                              lambda lav: kathara.convergenza(k, lab_path, lab, lav, spenti=set(st.link_spenti(nome_lab))))
        return {'lavoro': lid}

    if tipo == 'riapplica':
        dev = _dispositivo(lab, dati_rich.get('dev'))['nome']
        proto = dati_rich.get('igp')
        righe = kathara.righe_redistribute(lab, dev, proto) if proto in ('RIP', 'OSPF') else []
        if not righe:
            raise Errore(f"{dev} non ha righe 'redistribute' in {proto}")
        blocco = 'router rip' if proto == 'RIP' else 'router ospf'
        comando = (f"vtysh -c 'conf t' -c '{blocco}' " + ' '.join(f"-c 'no {x}'" for x in righe)
                   + ' ' + ' '.join(f"-c '{x}'" for x in righe))
        lid = st.lavori.avvia(f"riapplica ridistribuzione {dev}", comando,
                              lambda lav: kathara.riapplica_ridistribuzione(k, lab_path, lab, dev, proto, lav))
        return {'lavoro': lid}

    if tipo == 'rotta':
        dev = _dispositivo(lab, dati_rich.get('dev'))['nome']
        rete = _rete(dati_rich.get('rete'))
        lid = st.lavori.avvia(f"rotta {dev} -> {rete}", f"vtysh -c 'show ip route {rete}' -c 'show ip bgp {rete}'",
                              lambda lav: kathara.rotta(k, lab_path, lab, dev, rete, lav))
        return {'lavoro': lid}

    if tipo == 'tabelle':
        lid = st.lavori.avvia(f"tabelle di routing {nome_lab}", 'ip -j route su ogni router',
                              lambda lav: kathara.tabelle(k, lab_path, lab, lav))
        return {'lavoro': lid}

    if tipo == 'interfacce_reali':
        lid = st.lavori.avvia(f"interfacce reali {nome_lab}", 'ip -j addr su ogni dispositivo',
                              lambda lav: kathara.interfacce_reali(k, lab_path, lab, lav))
        return {'lavoro': lid}

    raise Errore('Azione non prevista')


def _gestisci_edit(st, path, corpo):
    ops = st.gen.ops_api
    try:
        if path == '/api/edit/create_lab':
            r = ops.create_lab(st.base, corpo)
            st.lavori.annota(f"crea lab {r['lab']}", "creazione lab da GUI", "OK")
            return r
        if path == '/api/edit/delete_lab':
            nome = corpo.get('lab', '')
            r = ops.delete_lab(st.base, nome)
            st.lavori.annota(f"elimina lab {nome}", f"rimozione lab (backup: {r['backup']})", "OK")
            return r
        if path == '/api/edit/import':
            r = ops.import_lab_content(
                st.base, corpo.get('filename', ''), corpo.get('content', ''),
                overwrite=bool(corpo.get('overwrite')), custom_name=corpo.get('custom_name') or None,
            )
            if r.get('ok'):
                st.lavori.annota(f"importa {r['lab']}", f"import da {corpo.get('filename', 'file')}", "OK")
            return r
        if path == '/api/edit/preview':
            return ops.preview_op(st.base, corpo.get('lab', ''), corpo.get('op', ''), corpo.get('params') or {})
        if path == '/api/edit/commit':
            lab = corpo.get('lab', '')
            op = corpo.get('op', '')
            r = ops.commit_op(st.base, lab, op, corpo.get('params') or {})
            st.lavori.annota(f"modifica {lab}: {r['titolo']}", f"op={op}" + (f" (backup: {r['backup']})" if r.get('backup') else ""), "OK")
            return r
        if path == '/api/edit/restore':
            lab = corpo.get('lab', '')
            lp = st.lab_path(lab)
            r = ops.restore_backup(lp, corpo.get('backup', ''))
            st.lavori.annota(f"ripristina {lab}", f"backup {r['ripristinato']}", "OK")
            return r
        if path == '/api/edit/ping_oneliner':
            return ops.ping_oneliner(st.lab_path(corpo.get('lab', '')))
        if path == '/api/edit/check_frr':
            lab = corpo.get('lab') or ''
            dev = corpo.get('dev') or None
            lp = st.lab_path(lab) if lab else None
            return {'problemi': ops.check_frr_content(corpo.get('content', ''), lab_path=lp, dev=dev)}
        if path == '/api/edit/diagnose':
            lp = st.lab_path(corpo.get('lab', ''))
            dev = str(corpo.get('dev') or '').strip()
            if not dev:
                raise Errore("Dispositivo non specificato.")
            return {'problemi': ops.diagnose_device(lp, dev)}
        if path == '/api/edit/suggest_ip':
            return {'ip': ops.suggerisci_ip_lan(st.lab_path(corpo.get('lab', '')), corpo.get('lan', ''), exclude=corpo.get('exclude') or [])}
    except ops.OpError as e:
        raise Errore(str(e))
    raise Errore('Endpoint edit non previsto')


class Gestore(BaseHTTPRequestHandler):
    st = None
    host_ok = set()

    def log_message(self, *a):
        pass

    def _manda(self, codice, corpo, tipo='application/json; charset=utf-8', extra=None):
        if not isinstance(corpo, bytes):
            corpo = json.dumps(corpo, ensure_ascii=False).encode('utf-8')
        self.send_response(codice)
        self.send_header('Content-Type', tipo)
        self.send_header('Content-Length', str(len(corpo)))
        self.send_header('Cache-Control', 'no-store')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(corpo)

    def _host_valido(self):
        return self.headers.get('Host', '') in self.host_ok

    def do_GET(self):
        if not self._host_valido():
            return self._manda(403, {'errore': 'host non consentito'})
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        st = self.st
        try:
            if u.path == '/':
                return self._manda(200, PAGINA.encode('utf-8'), 'text/html; charset=utf-8')
            if u.path == '/api/info':
                return self._manda(200, {'base': st.base, 'kathara': st.kathara, 'versione': st.versione,
                                         'sistema': sys.platform})
            if u.path == '/api/labs':
                return self._manda(200, {'labs': dati.elenco_lab(st.base)})
            if u.path == '/api/stato':
                labs = dati.elenco_lab(st.base)
                return self._manda(200, kathara.stato_lab(st.kathara, st.base, labs))
            if u.path == '/api/lab':
                return self._manda(200, st.leggi_lab(q.get('nome', '')))
            if u.path == '/api/file':
                lab = st.leggi_lab(q.get('lab', ''))
                dev = _dispositivo(lab, q.get('dev'))['nome']
                return self._manda(200, dati.file_dispositivo(st.lab_path(q['lab']), dev))
            if u.path == '/api/backups':
                lp = st.lab_path(q.get('lab', ''))
                return self._manda(200, {'backups': st.gen.ops_api.list_backups(lp)})
            if u.path == '/api/modificati':
                st.lab_path(q.get('lab', ''))
                return self._manda(200, kathara.file_modificati(st.base, q['lab']))
            if u.path == '/api/spenti':
                st.lab_path(q.get('lab', ''))
                return self._manda(200, {'lan': st.link_spenti(q['lab'])})
            if u.path == '/api/lavoro':
                r = st.lavori.leggi(q.get('id', ''), int(q.get('da', '0') or 0))
                return self._manda(200 if r else 404, r or {'errore': 'lavoro non trovato'})
            if u.path == '/api/registro':
                return self._manda(200, st.lavori.registro)
            if u.path == '/api/scarica':
                nome = q.get('nome', '')
                if nome not in st.archivi:
                    raise Errore('Archivio non disponibile')
                with open(os.path.join(st.base, nome), 'rb') as f:
                    corpo = f.read()
                return self._manda(200, corpo, 'application/octet-stream',
                                   {'Content-Disposition': f'attachment; filename="{nome}"'})
            return self._manda(404, {'errore': 'pagina non trovata'})
        except Errore as e:
            return self._manda(400, {'errore': str(e)})
        except Exception as e:
            return self._manda(500, {'errore': f"{type(e).__name__}: {e}"})

    def do_POST(self):
        if not self._host_valido() or self.headers.get('X-Lab-Gen') != '1':
            return self._manda(403, {'errore': 'richiesta non consentita'})
        try:
            n = int(self.headers.get('Content-Length', '0') or 0)
            corpo = json.loads(self.rfile.read(n).decode('utf-8') or '{}')
            p = urlparse(self.path).path
            if p == '/api/esci':
                self._manda(200, {'ok': True})
                threading.Thread(target=self.st.server.shutdown, daemon=True).start()
                return
            if p == '/api/azione':
                return self._manda(200, azione(self.st, corpo))
            if p.startswith('/api/edit/'):
                return self._manda(200, _gestisci_edit(self.st, p, corpo))
            return self._manda(404, {'errore': 'pagina non trovata'})
        except Errore as e:
            return self._manda(400, {'errore': str(e)})
        except Exception as e:
            return self._manda(500, {'errore': f"{type(e).__name__}: {e}"})


def avvia(base, gen, porta=8765, apri_browser=True):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except Exception:
            pass
    st = Stato(os.path.abspath(base), gen)
    server = None
    for p in range(porta, porta + 20):
        try:
            server = ThreadingHTTPServer(('127.0.0.1', p), Gestore)
            break
        except OSError:
            continue
    if server is None:
        print(f"❌ Nessuna porta libera tra {porta} e {porta + 19}.")
        return
    p = server.server_address[1]
    Gestore.st = st
    Gestore.host_ok = {f"127.0.0.1:{p}", f"localhost:{p}"}
    st.server = server
    server.daemon_threads = True

    def versione():
        if st.kathara:
            rc, out = kathara.esegui([st.kathara, '--version'], timeout=30)
            m = re.search(r'version:?\s*(\S+)', out, re.I)
            st.versione = m.group(1) if m else out.strip()[:80]
    threading.Thread(target=versione, daemon=True).start()

    url = f"http://127.0.0.1:{p}/"
    print(f"\n🌐 GUI avviata: {url}")
    print(f"   Lab letti da: {st.base}")
    if not st.kathara:
        print("   ⚠️ 'kathara' non trovato nel PATH: creazione, modifica e validazione funzionano; i test live richiedono Kathará.")
    print("   Per chiuderla: pulsante 'Chiudi GUI' nella pagina oppure Ctrl+C qui.\n")
    if apri_browser:
        threading.Timer(0.5, lambda: open_browser(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    print("GUI chiusa. (I lab avviati restano accesi: chiudili con lclean se non ti servono.)")
