"""
tests/test_risoluzione.py
Fase 6, "Risoluzione di un nome" (core/risoluzione.py, gui/kathara.risoluzione, menu 4 del
terminale): la catena di crab (resolver locale, root, it, roma3.it) è giusta; ogni anello rotto
apposta viene indicato (resolver, ricorsione, db.root, glue della delega, delega verso il server
sbagliato, record mancante); CNAME seguito; spiegazioni delle uscite di dig; GUI e terminale
danno lo stesso risultato.
"""
import builtins
import os
import re
import tempfile
import unittest
from unittest import mock

import _comune as c
from core import risoluzione as ris
from gui import kathara as kt
from gui import terminale_web
from test_dns_esami import _modello_crab


def _crab(tmp):
    with c.silenzio():
        c.core.genera_lab(tmp, 'crab', _modello_crab())
    return os.path.join(tmp, 'crab')


def _cambia(p, rel, prima, dopo):
    f = os.path.join(p, rel)
    with open(f, encoding='utf-8') as fh:
        t = fh.read()
    nuovo = re.sub(prima, dopo, t, flags=re.M)
    assert nuovo != t, (rel, prima)
    with open(f, 'w', encoding='utf-8') as fh:
        fh.write(nuovo)


def _controlla(p, client='client', nome='web.roma3.it'):
    return ris.controlla_nome(c.core.leggi_stato(p), client, nome)


class TestCatena(unittest.TestCase):

    def test_crab_giusto(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = _controlla(_crab(tmp))
            self.assertTrue(r['ok'], r['passi'])
            self.assertEqual('30.0.0.2', r['ip'])
            self.assertEqual(['local', 'root', 'it', 'roma3'], r['catena'])
            self.assertEqual(['30.0.0.5', '30.0.0.10', '30.0.0.4', '30.0.0.3'], r['catena_ip'])

    def test_anelli_rotti(self):
        rotture = {
            'resolver': ('client/etc/resolv.conf', r'^nameserver .*$', ''),
            'ricorsione': ('local/etc/bind/named.conf.options', r'allow-recursion \{ 0/0; \};', 'allow-recursion { 10.0.0.0/8; };'),
            'radice': ('local/etc/bind/db.root', r'30\.0\.0\.10', '30.0.0.99'),
            'deleghe': ('root/etc/bind/db.root', r'^dns\.it\.\s+IN\s+A\s+30\.0\.0\.4\s*$', ''),
            'deleghe ': ('it/etc/bind/db.it', r'^dns\.roma3\.it\.(\s+IN\s+A\s+)30\.0\.0\.3', r'dns.roma3.it.\g<1>30.0.0.4'),
        }
        for anello, (rel, prima, dopo) in rotture.items():
            with self.subTest(anello=anello), tempfile.TemporaryDirectory() as tmp:
                p = _crab(tmp)
                _cambia(p, rel, prima, dopo)
                r = _controlla(p)
                self.assertFalse(r['ok'])
                ultimo = r['passi'][-1]
                self.assertEqual(anello.strip(), ultimo['anello'], ultimo['testo'])
                self.assertFalse(ultimo['ok'])
                self.assertTrue(ultimo['rimedio'], 'serve il rimedio')
        with tempfile.TemporaryDirectory() as tmp:
            p = _crab(tmp)
            zona = next(f for f in os.listdir(os.path.join(p, 'roma3', 'etc', 'bind')) if f.startswith('db.') and 'roma3' in f)
            _cambia(p, f'roma3/etc/bind/{zona}', r'^web\.roma3\.it\..*$', 'www.roma3.it. IN CNAME web2.roma3.it.\nweb2.roma3.it. IN A 30.0.0.2')
            self.assertEqual('record', _controlla(p)['passi'][-1]['anello'], 'web.roma3.it non c\'è più')
            r = _controlla(p, nome='www.roma3.it')
            self.assertTrue(r['ok'], r['passi'])
            self.assertEqual('30.0.0.2', r['ip'], 'CNAME seguito')

    def test_resolver_che_non_e_un_dns(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _crab(tmp)
            _cambia(p, 'client/etc/resolv.conf', r'30\.0\.0\.5', '30.0.0.1')     # il router
            r = _controlla(p)
            self.assertEqual(('resolver', False), (r['passi'][-1]['anello'], r['passi'][-1]['ok']))


class TestDig(unittest.TestCase):

    def test_spiegazioni(self):
        ok = ";; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 1\n;; ANSWER SECTION:\nweb.roma3.it.\t60\tIN\tA\t30.0.0.2\n"
        self.assertEqual('ok', ris.spiega_dig(ok, 'web.roma3.it')[0])
        rinvio = (";; status: NOERROR\n;; AUTHORITY SECTION:\nit.\t60\tIN\tNS\tdns.it.\n\n"
                  ";; ADDITIONAL SECTION:\ndns.it.\t60\tIN\tA\t30.0.0.4\n\n")   # il glue non è una risposta
        self.assertEqual('rinvio', ris.spiega_dig(rinvio, 'web.roma3.it', 'root')[0])
        self.assertEqual('inesistente', ris.spiega_dig(';; status: NXDOMAIN', 'x')[0])
        self.assertEqual('rifiutata', ris.spiega_dig(';; status: REFUSED', 'x')[0])
        self.assertEqual('errore', ris.spiega_dig(';; status: SERVFAIL', 'x')[0])
        self.assertEqual('irraggiungibile', ris.spiega_dig(';; connection timed out; no servers could be reached', 'x')[0])
        self.assertEqual([['dig', '+time=2', '+tries=1', 'web.it'], ['dig', '+time=2', '+tries=1', '+norecurse', '@1.1.1.1', 'web.it']],
                         ris.comandi_dig('web.it', ['1.1.1.1']))


class TestGuiTerminale(unittest.TestCase):

    def test_stesso_risultato(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _crab(tmp)
            lav = kt.Lavoro('prova')
            kt.risoluzione(None, p, c.core.leggi_stato(p), 'client', 'web.roma3.it', lav)
            risposte = iter(['', 'web.roma3.it'])
            stati = c.core.leggi_stato(p)
            client = sorted(n for n, d in stati['dispositivi'].items() if d.get('nameserver') or d.get('tipo') != 'router')
            with c.silenzio(), mock.patch.object(terminale_web, 'input', lambda *a: next(risposte)), \
                    mock.patch.object(kt, 'trova_kathara', lambda: None):
                r = terminale_web.testa_risoluzione(p)
            self.assertEqual(lav.risultato, r)
            self.assertIn('client', client)


if __name__ == '__main__':
    unittest.main()
