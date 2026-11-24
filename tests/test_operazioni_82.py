"""
tests/test_operazioni_82.py
Fase 8.2: operazioni singole più tolleranti (cpp idempotente, network BGP rimuovi/modifica,
resolver e gateway vuoti, IP di un'interfaccia senza IP) e DNS senza zona root.
"""
import os
import re
import shutil
import tempfile
import unittest

import _comune as c
from core import operazioni as op
from core.modifiche import scrivi_piano


def _lab(nome):
    tmp = tempfile.TemporaryDirectory()
    p = os.path.join(tmp.name, nome)
    shutil.copytree(os.path.join(c.FIXTURE_LABS, nome), p)
    return tmp, p


def _scrivi(p, piano):
    assert scrivi_piano(p, piano)['scritto']
    return c.leggi_albero(p)


class TestCpp(unittest.TestCase):

    def _cpp(self, p, rel, reti=('5.0.0.0/8',)):
        return op.calcola_cpp(c.core.leggi_stato(p), 'as50r1', 'as70r1', '192.168.0.21', '70', rel, list(reti))

    def test_ripetuto_non_duplica(self):
        tmp, p = _lab('candy_test')
        with tmp:
            _scrivi(p, self._cpp(p, 'provider'))
            _scrivi(p, self._cpp(p, 'provider'))                 # assesta le righe vuote
            dopo = c.leggi_albero(p)
            piano = self._cpp(p, 'provider')
            self.assertEqual({}, piano['modifiche'], 'la terza volta non cambia più nulla')
            frr = dopo['as50r1/etc/frr/frr.conf']
            self.assertEqual(1, len(re.findall(r'neighbor 192\.168\.0\.21 prefix-list provider_as70r1_in in', frr)))
            self.assertEqual(1, len(re.findall(r'ip prefix-list provider_as70r1_out permit', frr)))

    def test_cambio_relazione_sostituisce_binding_e_liste(self):
        tmp, p = _lab('candy_test')
        with tmp:
            _scrivi(p, self._cpp(p, 'provider'))
            frr = _scrivi(p, self._cpp(p, 'peer'))['as50r1/etc/frr/frr.conf']
            self.assertNotIn('provider_as70r1', frr)
            self.assertEqual(1, len(re.findall(r'neighbor 192\.168\.0\.21 prefix-list peer_as70r1_in in', frr)))
            self.assertEqual(1, len(re.findall(r'neighbor 192\.168\.0\.21 prefix-list peer_as70r1_out out', frr)))

    def test_non_tocca_il_local_pref(self):
        tmp, p = _lab('candy_test')
        with tmp:
            frr = _scrivi(p, self._cpp(p, 'customer'))['as50r1/etc/frr/frr.conf']
            self.assertIn('neighbor 192.168.0.21 route-map PREF_IN_192_168_0_21 in', frr)
            self.assertIn('set local-preference 110', frr)


class TestNetworkBgp(unittest.TestCase):

    def test_rimuovi(self):
        tmp, p = _lab('candy_test')
        with tmp:
            st = c.core.leggi_stato(p)
            rete = sorted(op.opzioni_network_bgp(st, 'as50r1')['as50r1']['presenti'])[0]
            frr = _scrivi(p, op.calcola_network_bgp(st, 'as50r1', [rete], azione='rimuovi'))['as50r1/etc/frr/frr.conf']
            self.assertNotIn(f'network {rete}\n', frr)
            self.assertIn('network 192.168.0.', frr)

    def test_rimuovi_rete_non_annunciata(self):
        tmp, p = _lab('candy_test')
        with tmp, self.assertRaises(op.ErroreOperazione):
            op.calcola_network_bgp(c.core.leggi_stato(p), 'as50r1', ['9.9.9.0/24'], azione='rimuovi')

    def test_modifica_propaga_alle_liste(self):
        tmp, p = _lab('candy_test')
        with tmp:
            # as20r1 annuncia 20.0.0.0/8: lo scrivo anche in una prefix-list sua e in una access-list di as10r1
            fr = os.path.join(p, 'as20r1', 'etc', 'frr', 'frr.conf')
            testo = re.sub(r'(router bgp \d+\n)', r'\1    network 20.0.0.0/8\n', open(fr, encoding='utf-8').read(), count=1)
            with open(fr, 'w', encoding='utf-8') as f:
                f.write(testo + 'ip prefix-list PROVA permit 20.0.0.0/8\n')
            fr10 = os.path.join(p, 'as10r1', 'etc', 'frr', 'frr.conf')
            with open(fr10, 'a', encoding='utf-8') as f:
                f.write('access-list 10 deny 20.0.0.0/8\nip prefix-list ALTRA permit 30.0.0.0/8\n')
            st = c.core.leggi_stato(p)
            self.assertIn('20.0.0.0/8', op.opzioni_network_bgp(st, 'as20r1')['as20r1']['presenti'])
            piano = op.calcola_network_bgp(st, 'as20r1', ['20.0.0.0/8'], azione='modifica', nuova_rete='20.0.0.0/16')
            dopo = _scrivi(p, piano)
            self.assertIn('network 20.0.0.0/16', dopo['as20r1/etc/frr/frr.conf'])
            self.assertIn('ip prefix-list PROVA permit 20.0.0.0/16', dopo['as20r1/etc/frr/frr.conf'])
            self.assertIn('access-list 10 deny 20.0.0.0/16', dopo['as10r1/etc/frr/frr.conf'])
            self.assertIn('ip prefix-list ALTRA permit 30.0.0.0/8', dopo['as10r1/etc/frr/frr.conf'])

    def test_modifica_non_tocca_le_liste_se_altri_annunciano_ancora(self):
        tmp, p = _lab('candy_test')
        with tmp:
            # as10r1 e as20r1 annunciano entrambi 77.0.0.0/8 (e una prefix-list la cita)
            for r in ('as10r1', 'as20r1'):
                fr = os.path.join(p, r, 'etc', 'frr', 'frr.conf')
                testo = re.sub(r'(router bgp \d+\n)', r'\1    network 77.0.0.0/8\n', open(fr, encoding='utf-8').read(), count=1)
                open(fr, 'w', encoding='utf-8').write(testo + 'ip prefix-list PROVA permit 77.0.0.0/8\n')
            st = c.core.leggi_stato(p)
            piano = op.calcola_network_bgp(st, 'as10r1', ['77.0.0.0/8'], azione='modifica', nuova_rete='77.0.0.0/16')
            dopo = _scrivi(p, piano)
            self.assertIn('network 77.0.0.0/16', dopo['as10r1/etc/frr/frr.conf'])
            self.assertIn('ip prefix-list PROVA permit 77.0.0.0/8', dopo['as10r1/etc/frr/frr.conf'])
            self.assertTrue(any('annunciata anche da as20r1' in n for n in piano['note']))


class TestResolverGatewayIp(unittest.TestCase):

    def test_resolver_vuoto_toglie_il_file(self):
        tmp, p = _lab('tennis_test')
        with tmp:
            dopo = _scrivi(p, op.calcola_resolver(c.core.leggi_stato(p), 'pc', ''))
            self.assertNotIn('pc/etc/resolv.conf', dopo)

    def test_resolver_vuoto_senza_file(self):
        tmp, p = _lab('tennis_test')
        with tmp:
            piano = op.calcola_resolver(c.core.leggi_stato(p), 'web_srv', '')
            self.assertEqual({}, piano['modifiche'])
            self.assertTrue(piano['vuoto'])

    def test_gateway_vuoto_toglie_la_route(self):
        tmp, p = _lab('tennis_test')
        with tmp:
            dopo = _scrivi(p, op.calcola_gateway(c.core.leggi_stato(p), 'pc', ''))
            self.assertNotIn('default', dopo['pc.startup'])
            self.assertIn('ip address add 10.0.0.2/24 dev eth0', dopo['pc.startup'])

    def test_ip_interfaccia_senza_ip(self):
        tmp, p = _lab('tennis_test')
        with tmp:
            st0 = c.core.leggi_stato(p)
            with open(os.path.join(p, 'pc.startup'), encoding='utf-8') as f:
                righe = [l for l in f.read().split('\n') if 'ip address add' not in l]
            with open(os.path.join(p, 'pc.startup'), 'w', encoding='utf-8') as f:
                f.write('\n'.join(righe))
            st = c.core.leggi_stato(p)
            piano = op.calcola_ip_interfaccia(st, 'pc', 'eth0', '10.0.0.2')
            dopo = _scrivi(p, piano)
            self.assertEqual('ip address add 10.0.0.2/24 dev eth0', dopo['pc.startup'].split('\n')[0])
            self.assertIn('ip route add default', dopo['pc.startup'])


class TestDnsSenzaRoot(unittest.TestCase):

    def _server(self, root_type):
        from core.generators import crea_dns_host
        tmp = tempfile.TemporaryDirectory()
        crea_dns_host(tmp.name, 'ns_com', '20.1.0.3/24', '20.1.0.1/24', 'G', zones={'com': {'web.com': '2.2.0.2'}},
                      root_type=root_type, root_server_ip='20.3.0.2' if root_type == 'hint' else None)
        return tmp, os.path.join(tmp.name, 'ns_com', 'etc', 'bind')

    def test_senza_root_niente_zona_punto(self):
        for rt in (None, 'none'):
            tmp, bind = self._server(rt)
            with tmp:
                named = open(os.path.join(bind, 'named.conf'), encoding='utf-8').read()
                self.assertNotIn('zone "."', named)
                self.assertIn('zone "com"', named)
                self.assertFalse(os.path.exists(os.path.join(bind, 'db.root')))

    def test_hint_e_master_come_prima(self):
        for rt in ('hint', 'master'):
            tmp, bind = self._server(rt)
            with tmp:
                self.assertIn('zone "."', open(os.path.join(bind, 'named.conf'), encoding='utf-8').read())
                self.assertTrue(os.path.exists(os.path.join(bind, 'db.root')))


if __name__ == '__main__':
    unittest.main()
