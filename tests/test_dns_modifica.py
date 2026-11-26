"""
tests/test_dns_modifica.py
DNS su un lab già creato (collaudo di tennis): zona nuova, record A, ricorsione e DNSSEC come
operazioni con anteprima e Annulla; il terminale (Opzioni 9) scrive gli stessi file della GUI; con
le operazioni la catena di risoluzione di tennis senza DNS diventa completa.
"""
import builtins
import os
import re
import shutil
import tempfile
import unittest
from unittest import mock

import _comune as c
from core import operazioni as op
from core import risoluzione
from core import routing_ops
from core.modifiche import scrivi_piano


def _lab(nome):
    tmp = tempfile.TemporaryDirectory()
    p = os.path.join(tmp.name, nome)
    shutil.copytree(os.path.join(c.FIXTURE_LABS, nome), p)
    return tmp, p


def _scrivi(p, piano):
    assert scrivi_piano(p, piano)['scritto'], piano
    with c.silenzio():
        op.dopo_scrittura(p, piano)


def _leggi(p, rel):
    with open(os.path.join(p, rel), encoding='utf-8') as f:
        return f.read()


def _metti(f, testo):
    with open(f, 'w', encoding='utf-8') as fh:
        fh.write(testo)


def _senza_dns_com(p):
    """tennis senza zona com, delega, ricorsione e resolver di pc."""
    os.remove(os.path.join(p, 'ns_com/etc/bind/db.com'))
    nc = os.path.join(p, 'ns_com/etc/bind/named.conf')
    t = _leggi(p, 'ns_com/etc/bind/named.conf')
    _metti(nc, re.sub(r'\nzone "com" \{[^}]*\};\n?', '\n', t))
    for f in ('root/etc/bind/db.root',):
        t = _leggi(p, f)
        _metti(os.path.join(p, f), '\n'.join(l for l in t.split('\n') if 'com.' not in l) + '\n')
    o = os.path.join(p, 'ns_local/etc/bind/named.conf.options')
    _metti(o, 'options {\n    directory "/var/cache/bind";\n};\n')
    os.remove(os.path.join(p, 'pc/etc/resolv.conf'))


class TestOperazioni(unittest.TestCase):

    def test_tennis_da_zero_alla_catena_completa(self):
        tmp, p = _lab('tennis_test')
        with tmp:
            _senza_dns_com(p)
            st = lambda: c.core.leggi_stato(p)
            self.assertFalse(risoluzione.controlla_nome(st(), 'pc', 'web.com')['ok'])
            ip_com = op.opzioni_dns(st(), 'ns_com')['ip']
            _scrivi(p, op.calcola_zona_dns(st(), 'ns_com', 'com', {'web': '2.2.0.2'}))
            _scrivi(p, op.calcola_delega_dns(st(), 'root', 'com', 'dns.com', ip_com))
            _scrivi(p, op.calcola_ricorsione_dns(st(), 'ns_local', True, '', True))
            _scrivi(p, op.calcola_resolver(st(), 'pc', op.opzioni_dns(st(), 'ns_local')['ip']))
            r = risoluzione.controlla_nome(st(), 'pc', 'web.com')
            self.assertTrue(r['ok'], r['passi'])
            self.assertEqual('2.2.0.2', r['ip'])
            db = _leggi(p, 'ns_com/etc/bind/db.com')
            self.assertIn('@ IN SOA dns.com. root.dns.com.', db)
            self.assertRegex(db, r'dns\.com\.\s+IN\s+A\s+' + re.escape(ip_com))
            self.assertIn('allow-recursion { any; };', _leggi(p, 'ns_local/etc/bind/named.conf.options'))

    def test_zona_gia_presente_e_nome_sbagliato(self):
        tmp, p = _lab('tennis_test')
        with tmp:
            st = c.core.leggi_stato(p)
            self.assertTrue(op.calcola_zona_dns(st, 'ns_com', 'com')['vuoto'])
            with self.assertRaises(op.ErroreOperazione):
                op.calcola_zona_dns(st, 'ns_com', 'co m')
            with self.assertRaises(op.ErroreOperazione):
                op.calcola_zona_dns(st, 'pc', 'org')

    def test_record_aggiungi_sostituisci_togli(self):
        tmp, p = _lab('tennis_test')
        with tmp:
            st = lambda: c.core.leggi_stato(p)
            _scrivi(p, op.calcola_record_dns(st(), 'ns_com', 'com', 'www', '2.2.0.3'))
            self.assertIn(('www.com', 'A', '2.2.0.3'), [z for z in op.opzioni_dns(st(), 'ns_com')['zone'] if z['zona'] == 'com'][0]['record'])
            self.assertTrue(op.calcola_record_dns(st(), 'ns_com', 'com', 'www.com.', '2.2.0.3')['vuoto'])
            piano = op.calcola_record_dns(st(), 'ns_com', 'com', 'web', '2.2.0.9')
            self.assertTrue(piano['note'])
            _scrivi(p, piano)
            db = _leggi(p, 'ns_com/etc/bind/db.com')
            self.assertNotIn('2.2.0.2', db)
            self.assertEqual(1, len(re.findall(r'^web\.com\.', db, re.M)))
            _scrivi(p, op.calcola_record_dns(st(), 'ns_com', 'com', 'www', togli=True))
            self.assertNotIn('www.com', _leggi(p, 'ns_com/etc/bind/db.com'))
            with self.assertRaises(op.ErroreOperazione):
                op.calcola_record_dns(st(), 'ns_com', 'org', 'x', '1.1.1.1')      # non è master di org
            with self.assertRaises(op.ErroreOperazione):
                op.calcola_record_dns(st(), 'ns_com', 'com', 'x', '1.1.1')

    def test_ricorsione_reti_e_togli(self):
        tmp, p = _lab('tennis_test')
        with tmp:
            st = lambda: c.core.leggi_stato(p)
            _scrivi(p, op.calcola_ricorsione_dns(st(), 'ns_local', True, '10.0.0.0/24, 1.0.0.0/24', False))
            o = _leggi(p, 'ns_local/etc/bind/named.conf.options')
            self.assertIn('allow-recursion { 10.0.0.0/24; 1.0.0.0/24; };', o)
            self.assertNotIn('dnssec-validation', o)
            self.assertEqual({}, op.calcola_ricorsione_dns(st(), 'ns_local', True, '10.0.0.0/24 1.0.0.0/24', False)['modifiche'])
            _scrivi(p, op.calcola_ricorsione_dns(st(), 'ns_local', False, '', True))
            o = _leggi(p, 'ns_local/etc/bind/named.conf.options')
            self.assertNotIn('allow-recursion', o)
            self.assertIn('dnssec-validation no;', o)
            with self.assertRaises(op.ErroreOperazione):
                op.calcola_ricorsione_dns(st(), 'ns_local', True, '10.0.0/99', False)

    def test_annulla_toglie_la_zona(self):
        tmp, p = _lab('tennis_test')
        with tmp:
            prima = c.leggi_albero(p)
            _scrivi(p, op.calcola_zona_dns(c.core.leggi_stato(p), 'ns_com', 'org', {'www': '2.2.0.2'}))
            self.assertIn('ns_com/etc/bind/db.org', c.leggi_albero(p))
            _scrivi(p, op.calcola_annulla(c.core.leggi_stato(p)))
            self.assertEqual(prima, c.leggi_albero(p))


class TestTerminale(unittest.TestCase):

    def test_stessi_file_della_gui(self):
        with tempfile.TemporaryDirectory() as tmp:
            g, t = os.path.join(tmp, 'g'), os.path.join(tmp, 't')
            for x in (g, t):
                os.makedirs(x)
                shutil.copytree(os.path.join(c.FIXTURE_LABS, 'tennis_test'), os.path.join(x, 'tennis_test'))
                _senza_dns_com(os.path.join(x, 'tennis_test'))
            pg, pt = os.path.join(g, 'tennis_test'), os.path.join(t, 'tennis_test')
            st = lambda: c.core.leggi_stato(pg)
            _scrivi(pg, op.calcola_zona_dns(st(), 'ns_com', 'com', {'web': '2.2.0.2'}))
            _scrivi(pg, op.calcola_record_dns(st(), 'ns_com', 'com', 'www', '2.2.0.3'))
            _scrivi(pg, op.calcola_ricorsione_dns(st(), 'ns_local', True, '10.0.0.0/24', True))
            server = sorted(n for n, d in c.core.leggi_stato(pt)['dispositivi'].items() if d.get('dns'))
            k = lambda n: str(server.index(n) + 1)
            risposte = iter(['2', k('ns_com'), 'com', 'web', '2.2.0.2', '', 's',
                             '3', k('ns_com'), 'www', '2.2.0.3', 's',
                             '4', k('ns_local'), 's', '10.0.0.0/24', 's', 's',
                             '0'])
            with c.silenzio(), mock.patch.object(builtins, 'input', lambda *a: next(risposte)):
                routing_ops.menu_dns(pt)

            def senza_serial(albero):
                return {k2: re.sub(r'\d{10} ; serial', 'S ; serial', v) for k2, v in albero.items()}
            self.assertEqual(senza_serial(c.leggi_albero(pg)), senza_serial(c.leggi_albero(pt)))


if __name__ == '__main__':
    unittest.main()
