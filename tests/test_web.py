"""
tests/test_web.py
Pagine web e apache2 (core/web.py, gui/kathara.py, gui/terminale_web.py):
- indirizzi accettati nel comando links (niente che possa uscire dall'URL o dal comando);
- server web, nomi DNS (record A e CNAME) e client ricavati dai file del lab;
- spiegazioni degli esiti di links misurati con Kathará;
- verifica completa con un Kathará finto: GUI (server) e terminale danno gli stessi esiti.
"""
import builtins
import os
import shutil
import stat
import tempfile
import time
import unittest
from unittest import mock

import _comune as c
from _server import ServerDiProva
from core import web
from core.stato import leggi_stato
from gui import kathara as kt
from gui import terminale_web

DNS_LAB = os.path.join(c.TESTS, 'attesi', 'scenari', 'dns_root_auth_resolver')
PAPILLON = os.path.join(c.FIXTURE_LABS, 'papillon_mio')

# Kathará finto: risponde come quello vero (uscite misurate il 2026-11-22) secondo il comando
FINTO = r'''#!/bin/sh
# kathara exec -d <lab> <dispositivo> '<comando>'
echo "$@" >> "$(dirname "$0")/chiamate"
dev="$4"; cmd="$5"
d="$(dirname "$0")"
case "$cmd" in
  *"ip route get"*) if [ -f "$d/senza_gateway" ]; then echo "RTNETLINK answers: Network is unreachable"; exit 2; fi
                    echo "10.0.1.80 via 10.0.0.1 dev eth0 src 10.0.0.10 uid 0"; exit 0 ;;
  *traceroute*) echo "traceroute to 10.0.1.80 (10.0.1.80), 12 hops max, 60 byte packets"; echo " 1  10.0.0.1  0.352 ms !N"; exit 0 ;;
  *links*) if [ -f "$d/rete" ]; then echo "Network is unreachable"; exit 1; fi ;;
esac
case "$cmd" in
  *is-active*) if [ -f "$(dirname "$0")/apache_acceso" ]; then echo active; exit 0; else echo inactive; exit 3; fi ;;
  *"systemctl start apache2"*) touch "$(dirname "$0")/apache_acceso"; exit 0 ;;
  *links*http://www.com/*) if [ -f "$(dirname "$0")/apache_acceso" ]; then echo "                Server www1"; exit 0; else echo "Connection refused"; exit 1; fi ;;
  *links*http://web.com/*) echo "Host not found"; exit 1 ;;
  *links*http://10.0.1.80/*) if [ -f "$(dirname "$0")/apache_acceso" ]; then echo "                Server www1"; exit 0; else echo "Connection refused"; exit 1; fi ;;
esac
exit 1
'''


def _kathara_finto(cartella):
    p = os.path.join(cartella, 'kathara')
    with open(p, 'w') as f:
        f.write(FINTO)
    os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
    return p


class TestIndirizzi(unittest.TestCase):

    def test_validi(self):
        for x in ('10.0.1.80', 'www.com', 'web.com.', 'www', 'dns_com', 'a-b.example.org', '::1'):
            self.assertTrue(web.indirizzo_valido(x), x)

    def test_rifiutati(self):
        for x in ('', ' ', 'www.com; reboot', '$(id)', 'a b', 'http://www.com', 'www.com/x', '-www',
                  'www..com', '10.0.0.300', '1.2.3', "a'b", 'a\nb', 'x' * 300):
            self.assertFalse(web.indirizzo_valido(x), repr(x))
        with self.assertRaises(ValueError):
            web.comando_links('$(id)')

    def test_comando(self):
        self.assertEqual(['timeout', '8', 'links', '-dump', 'http://www.com/'], web.comando_links(' www.com '))


class TestDalLab(unittest.TestCase):

    def test_lab_dns(self):
        st = leggi_stato(DNS_LAB)
        self.assertEqual([{'nome': 'www1', 'ip': ['10.0.1.80']}], web.server_web(st))
        self.assertEqual([{'nome': 'www.com', 'server': 'www1', 'ip': '10.0.1.80', 'via': 'A'},
                          {'nome': 'web.com', 'server': 'www1', 'ip': '10.0.1.80', 'via': 'CNAME www.com'}], web.nomi_web(st))
        self.assertEqual(['10.0.1.80', 'www.com', 'web.com'], [b['indirizzo'] for b in web.bersagli_web(st)])
        self.assertEqual(['dns_com', 'host1', 'resolver', 'root', 'www1'], web.client_web(st))
        testo = web.comandi_da_incollare(st)
        self.assertIn('timeout 8 links -dump http://web.com/   # www1, CNAME www.com', testo)
        self.assertIn(web.COMANDO_APACHE, testo)

    def test_lab_senza_dns(self):
        st = leggi_stato(PAPILLON)
        self.assertEqual([('30.30.1.2', 'server', 'ip')], [(b['indirizzo'], b['server'], b['tipo']) for b in web.bersagli_web(st)])
        self.assertEqual(['client', 'server'], web.client_web(st), 'i router non hanno links')

    def test_senza_server_web(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, 'lab')
            shutil.copytree(PAPILLON, p)
            shutil.rmtree(os.path.join(p, 'server', 'var'))
            with open(os.path.join(p, 'server.startup'), encoding='utf-8') as f:
                righe = [l for l in f if 'apache2' not in l]
            with open(os.path.join(p, 'server.startup'), 'w', encoding='utf-8') as f:
                f.writelines(righe)
            st = leggi_stato(p)
            self.assertEqual([], web.server_web(st))
            self.assertIn('Nessun server web', web.comandi_da_incollare(st))

    def test_nomi_solo_verso_i_server_web(self):
        """Record A verso IP che non sono di un server web, CNAME verso nomi sconosciuti, catene e
        cicli di CNAME, zone non autoritative e la zona '.'."""
        def zona(nome, tipo, record):
            return {'zona': nome, 'tipo': tipo, 'record': [{'nome': n, 'tipo': t, 'valore': v} for n, t, v in record]}
        st = {'dispositivi': {
            'w': {'tipo': 'www', 'apache': True, 'interfacce': [{'ip': '1.1.1.1/24'}], 'dns': None},
            'd': {'tipo': 'dns', 'apache': False, 'interfacce': [{'ip': '1.1.1.2/24'}], 'dns': {'zone': [
                zona('it', 'master', [('a.it', 'A', '1.1.1.1'), ('dns.it', 'A', '1.1.1.2'), ('b.it', 'CNAME', 'a'),
                                      ('c.it', 'CNAME', 'b.it.'), ('x.it', 'CNAME', 'y'), ('y.it', 'CNAME', 'x'),
                                      ('z.it', 'CNAME', 'dns')]),
                zona('org', 'slave', [('s.org', 'A', '1.1.1.1')]),
                zona('.', 'master', [('root.', 'A', '1.1.1.1')])]}},
        }}
        self.assertEqual([('a.it', 'A'), ('b.it', 'CNAME a.it'), ('c.it', 'CNAME b.it')],
                         [(n['nome'], n['via']) for n in web.nomi_web(st)])


class TestSpiegazioni(unittest.TestCase):

    def test_esiti_misurati(self):
        casi = [
            (0, '                Server www1\n', 'ok'),
            (0, '\n', 'vuota'),
            (1, 'Host not found\n', 'dns'),
            (1, 'Connection refused\n', 'apache'),
            (1, 'Network is unreachable\n', 'rete'),
            (1, 'No route to host\n', 'rete'),
            (124, '', 'rete'),
            (2, 'qualcosa di strano', 'errore'),
        ]
        for codice, testo, atteso in casi:
            with self.subTest(testo=testo):
                esito, spiegazione = web.spiega_links(codice, testo, 'www.com')
                self.assertEqual(atteso, esito)
                self.assertTrue(spiegazione)
        self.assertIn('www.com', web.spiega_links(1, 'Host not found', 'www.com')[1])


class TestTraceroute(unittest.TestCase):
    """Uscite di traceroute misurate con Kathará (copia di papillon_gui, 2026-11-22)."""
    CHI = {'20.20.1.1': 'r1', '20.20.2.2': 'r2', '20.20.3.2': 'r3', '30.30.1.2': 'server'}
    TESTA = 'traceroute to 30.30.1.2 (30.30.1.2), 12 hops max, 60 byte packets\n'

    def test_router_senza_rotta(self):
        esito, s = web.spiega_traceroute(self.TESTA + ' 1  20.20.1.1  0.352 ms !N\n', '30.30.1.2', self.CHI)
        self.assertEqual('rete', esito)
        self.assertTrue(s.startswith('r1 (20.20.1.1) non ha una rotta verso 30.30.1.2'), s)
        self.assertIn('Opzioni 6', s)
        t = self.TESTA + ' 1  20.20.1.1  0.241 ms\n 2  20.20.2.2  0.455 ms\n 3  20.20.3.2  0.784 ms !N\n'
        self.assertTrue(web.spiega_traceroute(t, '30.30.1.2', self.CHI)[1].startswith('r3 (20.20.3.2) non ha'))

    def test_si_ferma_dopo(self):
        t = self.TESTA + ' 1  20.20.1.1  0.197 ms\n 2  20.20.2.2  0.287 ms\n 3  20.20.3.2  0.485 ms\n' + \
            ''.join(f' {n}  *\n' for n in range(4, 9))
        self.assertIn('si fermano dopo r3 (20.20.3.2)', web.spiega_traceroute(t, '30.30.1.2', self.CHI)[1])

    def test_altri_casi(self):
        self.assertIn('raggiunge', web.spiega_traceroute(self.TESTA + ' 1  20.20.1.1  1 ms !H\n', '30.30.1.2', self.CHI)[1])
        self.assertIn('filtro', web.spiega_traceroute(self.TESTA + ' 1  20.20.1.1  1 ms !X\n', '30.30.1.2', self.CHI)[1])
        self.assertIn('risponde al traceroute', web.spiega_traceroute(self.TESTA + ' 1  30.30.1.2  1 ms\n', '30.30.1.2', self.CHI)[1])
        self.assertIn('nessun router', web.spiega_traceroute(self.TESTA + ' 1  *\n 2  *\n', '30.30.1.2', self.CHI)[1])
        self.assertIn('9.9.9.9', web.spiega_traceroute(self.TESTA + ' 1  9.9.9.9  1 ms !N\n', '30.30.1.2', self.CHI)[1])

    def test_ip_del_bersaglio(self):
        st = leggi_stato(DNS_LAB)
        self.assertEqual('10.0.1.80', web.ip_del_bersaglio(st, 'web.com'))
        self.assertEqual('10.0.1.80', web.ip_del_bersaglio(st, 'WWW.com.'))
        self.assertEqual('1.2.3.4', web.ip_del_bersaglio(st, '1.2.3.4'))
        self.assertIsNone(web.ip_del_bersaglio(st, 'altro.com'))


class _Lav:
    def __init__(self):
        self.righe, self.risultato = [], None

    def scrivi(self, t):
        self.righe.append(t)


class TestConKatharaFinto(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.bin = self._tmp.name
        self.k = _kathara_finto(self.bin)
        self.lab = os.path.join(self.bin, 'dnslab')
        shutil.copytree(DNS_LAB, self.lab)

    def tearDown(self):
        self._tmp.cleanup()

    def chiamate(self):
        with open(os.path.join(self.bin, 'chiamate')) as f:
            return f.read()

    def test_verifica_con_apache_spento_poi_acceso(self):
        st = leggi_stato(self.lab)
        lav = _Lav()
        kt.verifica_web(self.k, self.lab, st, 'host1', lav)
        r = lav.risultato
        self.assertEqual([False], [x['attivo'] for x in r['server']])
        esiti = {p['indirizzo']: (p['esito'], p['spiegazione']) for p in r['pagine']}
        self.assertEqual('apache', esiti['www.com'][0])
        self.assertIn('apache2 è spento su www1', esiti['www.com'][1])
        self.assertEqual('dns', esiti['web.com'][0])
        open(os.path.join(self.bin, 'apache_acceso'), 'w').close()
        lav = _Lav()
        kt.verifica_web(self.k, self.lab, st, 'host1', lav)
        esiti = {p['indirizzo']: (p['esito'], p['riga']) for p in lav.risultato['pagine']}
        self.assertEqual(('ok', 'Server www1'), esiti['10.0.1.80'])
        self.assertEqual([True], [x['attivo'] for x in lav.risultato['server']])
        self.assertIn("exec -d %s host1 timeout 8 links -dump http://www.com/" % self.lab, self.chiamate())

    def test_diagnosi_router_senza_rotta(self):
        """Stesso messaggio di links, due cause: un router senza rotta (lo dice il traceroute) ..."""
        open(os.path.join(self.bin, 'rete'), 'w').close()
        st = leggi_stato(self.lab)
        lav = _Lav()
        kt.verifica_web(self.k, self.lab, st, 'host1', lav)
        for p in lav.risultato['pagine']:
            self.assertEqual('rete', p['esito'])
            self.assertTrue(p['spiegazione'].startswith('r1 (10.0.0.1) non ha una rotta verso 10.0.1.80'), p)
        lav = _Lav()
        kt.pagina_web(self.k, self.lab, 'host1', 'web.com', lav, st)
        self.assertIn('traceroute -n 10.0.1.80:', '\n'.join(lav.righe), 'nel pannello si vede il traceroute')
        self.assertIn('r1 (10.0.0.1) non ha una rotta', lav.righe[-1])

    def test_diagnosi_senza_gateway(self):
        """... oppure il client senza gateway (ip route get non trova la strada)."""
        open(os.path.join(self.bin, 'rete'), 'w').close()
        open(os.path.join(self.bin, 'senza_gateway'), 'w').close()
        lav = _Lav()
        kt.verifica_web(self.k, self.lab, leggi_stato(self.lab), 'host1', lav)
        self.assertEqual({('gateway', web.SENZA_GATEWAY)}, {(p['esito'], p['spiegazione']) for p in lav.risultato['pagine']})
        self.assertNotIn('traceroute', self.chiamate())

    def test_pagina_dal_pannello(self):
        lav = _Lav()
        self.assertEqual(1, kt.pagina_web(self.k, self.lab, 'host1', 'web.com', lav))
        self.assertEqual('dns', lav.risultato['esito'])
        self.assertIn('nome non risolto', lav.righe[-1])

    def test_terminale(self):
        """Stessa verifica dal terminale: chiede se eseguire, propone l'host, avvia apache2 solo col sì."""
        risposte = iter(['s', '', 's'])
        with c.silenzio(), mock.patch.object(builtins, 'input', lambda *a: next(risposte)), \
                mock.patch.object(kt, 'stato_lab', lambda k, base, labs: {'dnslab': ['host1', 'www1', 'r1']}):
            r = terminale_web.testa_pagine_web(self.lab, kathara=self.k)
        self.assertEqual('host1', r['client'])
        self.assertTrue(all(p['esito'] == 'ok' for p in r['pagine'] if p['indirizzo'] != 'web.com'))
        self.assertIn('systemctl start apache2', self.chiamate())

    def test_terminale_senza_conferma_non_avvia(self):
        risposte = iter(['s', '', 'n'])
        with c.silenzio(), mock.patch.object(builtins, 'input', lambda *a: next(risposte)), \
                mock.patch.object(kt, 'stato_lab', lambda k, base, labs: {'dnslab': ['host1', 'www1']}):
            r = terminale_web.testa_pagine_web(self.lab, kathara=self.k)
        self.assertEqual([False], [x['attivo'] for x in r['server']])
        self.assertNotIn('systemctl start apache2', self.chiamate())

    def test_terminale_lab_spento_o_no(self):
        with c.silenzio(), mock.patch.object(kt, 'stato_lab', lambda k, base, labs: {'dnslab': []}), \
                mock.patch.object(builtins, 'input', lambda *a: self.fail('non deve chiedere niente')):
            self.assertIsNone(terminale_web.testa_pagine_web(self.lab, kathara=self.k))
        risposte = iter(['n'])
        with c.silenzio(), mock.patch.object(builtins, 'input', lambda *a: next(risposte)), \
                mock.patch.object(kt, 'stato_lab', lambda k, base, labs: {'dnslab': ['host1']}):
            self.assertIsNone(terminale_web.testa_pagine_web(self.lab, kathara=self.k))
        self.assertFalse(os.path.exists(os.path.join(self.bin, 'chiamate')), 'con il no non esegue niente')


class TestServer(ServerDiProva):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.st.kathara = _kathara_finto(self._tmp.name)
        self.st.gen = c.core
        p = os.path.join(self.base, 'dnslab')
        shutil.rmtree(p, ignore_errors=True)
        shutil.copytree(DNS_LAB, p)

    def tearDown(self):
        self.st.kathara, self.st.gen = None, None
        self._tmp.cleanup()

    def aspetta(self, lid):
        for _ in range(200):
            j = self.st.lavori.leggi(lid)
            if j['fatto']:
                return j
            time.sleep(0.05)
        self.fail('lavoro non finito')

    def test_dati_del_lab(self):
        codice, lab = self.richiesta('GET', '/api/lab?nome=dnslab')
        self.assertEqual(200, codice, lab)
        self.assertEqual(['10.0.1.80', 'www.com', 'web.com'], [b['indirizzo'] for b in lab['web']['bersagli']])
        self.assertNotIn('r1', lab['web']['client'])

    def test_pagina_web(self):
        codice, r = self.azione(azione='pagina_web', lab='dnslab', dev='host1', indirizzo='web.com')
        self.assertEqual(200, codice, r)
        j = self.aspetta(r['lavoro'])
        self.assertEqual('dns', j['risultato']['esito'])
        for cattivo in ('www.com; reboot', '$(id)', ''):
            codice, r = self.azione(azione='pagina_web', lab='dnslab', dev='host1', indirizzo=cattivo)
            self.assertEqual(400, codice, r)

    def test_verifica_web(self):
        codice, r = self.azione(azione='verifica_web', lab='dnslab', dev='r1')
        self.assertEqual(400, codice, r)
        codice, r = self.azione(azione='verifica_web', lab='dnslab', dev='host1')
        self.assertEqual(200, codice, r)
        j = self.aspetta(r['lavoro'])
        self.assertEqual(3, len(j['risultato']['pagine']))
        codice, r = self.azione(azione='comando', lab='dnslab', dev='www1', comando='apache_avvia')
        self.aspetta(r['lavoro'])
        codice, r = self.azione(azione='verifica_web', lab='dnslab', dev='host1')
        j = self.aspetta(r['lavoro'])
        self.assertEqual([True], [x['attivo'] for x in j['risultato']['server']])
        codice, reg = self.richiesta('GET', '/api/registro')
        self.assertTrue(any('systemctl start apache2' in v['comando'] for v in reg))


if __name__ == '__main__':
    unittest.main()
