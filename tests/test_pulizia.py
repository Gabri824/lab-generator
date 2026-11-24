"""
tests/test_pulizia.py
Fase 8.1: pulizia a cascata dei riferimenti orfani (src/core/pulizia.py) nelle operazioni che
tolgono o spostano dispositivi, interfacce e protocolli.
"""
import os
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


def _dopo(p, piano):
    """File del lab dopo aver scritto il piano."""
    assert scrivi_piano(p, piano)['scritto']
    return c.leggi_albero(p)


class TestPulizia(unittest.TestCase):

    def test_togli_dispositivo_toglie_resolver_e_gateway(self):
        tmp, p = _lab('tennis_test')
        with tmp:
            # ns_local è il resolver di pc: nameserver tolto e resolv.conf (rimasto vuoto) eliminato
            piano = op.calcola_togli_dispositivo(c.core.leggi_stato(p), 'ns_local')
            self.assertIn('pc/etc/resolv.conf', [r.replace(os.sep, '/') for r in piano['modifiche']])
            self.assertIsNone(piano['modifiche'][os.path.join('pc', 'etc', 'resolv.conf')][1])
            dopo = _dopo(p, piano)
            self.assertNotIn('pc/etc/resolv.conf', dopo)
            self.assertNotIn('ns_local.startup', dopo)

    def test_togli_dispositivo_senza_pulizia_lascia_i_riferimenti(self):
        tmp, p = _lab('tennis_test')
        with tmp:
            piano = op.calcola_togli_dispositivo(c.core.leggi_stato(p), 'ns_local', pulisci_riferimenti=False)
            dopo = _dopo(p, piano)
            self.assertIn('nameserver 1.0.0.2', dopo['pc/etc/resolv.conf'])
            self.assertTrue(any('resolver' in n for n in piano['note']))

    def test_togli_dns_toglie_il_record_a_nella_zona_del_padre(self):
        tmp, p = _lab('tennis_test')
        with tmp:
            piano = op.calcola_togli_dispositivo(c.core.leggi_stato(p), 'ns_com')
            self.assertTrue(any('dns.com. IN A 20.1.0.3' in n for n in piano['note']), piano['note'])
            dopo = _dopo(p, piano)
            self.assertNotIn('20.1.0.3', dopo['root/etc/bind/db.root'])

    def test_togli_router_toglie_gateway_dei_pc(self):
        tmp, p = _lab('tennis_test')
        with tmp:
            st = c.core.leggi_stato(p)
            gw = op.opzioni_togli_dispositivo(st, 'as20r1')
            router = next((n for n in ('as2r1', 'as2r2', 'as2r3', 'as1r1', 'as10r1', 'as20r1', 'as20r2', 'as20r3', 'as20r4')
                           if op.opzioni_togli_dispositivo(st, n)['gateway_di']), None)
            self.assertIsNotNone(router, gw)
            chi = op.opzioni_togli_dispositivo(st, router)['gateway_di'][0]
            dopo = _dopo(p, op.calcola_togli_dispositivo(st, router))
            self.assertNotIn('ip route add default', dopo[chi + '.startup'])

    def test_togli_bgp_toglie_la_prefix_list_orfana(self):
        tmp, p = _lab('candy_test')
        with tmp:
            piano = op.calcola_togli_protocollo(c.core.leggi_stato(p), 'as10r1', 'bgp')
            dopo = _dopo(p, piano)
            self.assertNotIn('prefix-list', dopo['as10r1/etc/frr/frr.conf'])
            self.assertTrue(any('PL_as10r1_192_168_0_2_in' in n for n in piano['note']))

    def test_togli_bgp_senza_pulizia_lascia_la_lista(self):
        tmp, p = _lab('candy_test')
        with tmp:
            dopo = _dopo(p, op.calcola_togli_protocollo(c.core.leggi_stato(p), 'as10r1', 'bgp', pulisci_riferimenti=False))
            self.assertIn('prefix-list', dopo['as10r1/etc/frr/frr.conf'])

    def test_togli_interfaccia_toglie_neighbor_e_liste(self):
        tmp, p = _lab('candy_test')
        with tmp:
            prima = c.leggi_albero(p)
            piano = op.calcola_togli_interfaccia(c.core.leggi_stato(p), 'as50r1', 'eth1')
            dopo = _dopo(p, piano)
            self.assertNotEqual(prima['as50r1/etc/frr/frr.conf'], dopo['as50r1/etc/frr/frr.conf'])
            self.assertNotIn('192.168.0.21', dopo['as50r1/etc/frr/frr.conf'])
            self.assertNotIn('PREF_IN_192_168_0_21', dopo['as50r1/etc/frr/frr.conf'])      # route-map orfana
            self.assertNotIn('192.168.0.22', dopo['as70r1/etc/frr/frr.conf'])

    def test_lista_ancora_usata_resta(self):
        # una route-map usata da un altro neighbor non viene toccata
        from core.pulizia import _togli_orfane
        prima = ['router bgp 1', '    neighbor 1.1.1.1 route-map RM in', '    neighbor 2.2.2.2 route-map RM in',
                 'route-map RM permit 10', '    match ip address prefix-list PL', 'ip prefix-list PL permit any']
        dopo = [l for l in prima if '1.1.1.1' not in l]
        nuove, tolti = _togli_orfane(list(dopo), prima)
        self.assertEqual((nuove, tolti), (dopo, []))

    def test_cascata_route_map_e_liste(self):
        from core.pulizia import _togli_orfane
        prima = ['router bgp 1', '    neighbor 1.1.1.1 route-map RM in',
                 'route-map RM permit 10', '    match ip address prefix-list PL', '    set local-preference 150',
                 'ip prefix-list PL permit any', 'ip prefix-list ALTRA permit any']
        dopo = [l for l in prima if '1.1.1.1' not in l]
        nuove, tolti = _togli_orfane(list(dopo), prima)
        self.assertEqual(tolti, ['RM', 'PL'])
        self.assertEqual(nuove, ['router bgp 1', 'ip prefix-list ALTRA permit any'])   # ALTRA non era usata: resta

    def test_sposta_interfaccia_toglie_i_neighbor_della_vecchia_lan(self):
        tmp, p = _lab('candy_test')
        with tmp:
            st = c.core.leggi_stato(p)
            piano = op.calcola_sposta_interfaccia(st, 'as50r1', 'eth1', 'Z', '190.9.9.1/24')
            dopo = _dopo(p, piano)
            self.assertNotIn('192.168.0.21', dopo['as50r1/etc/frr/frr.conf'])
            self.assertNotIn('PREF_IN_192_168_0_21', dopo['as50r1/etc/frr/frr.conf'])
            self.assertNotIn('192.168.0.22', dopo['as70r1/etc/frr/frr.conf'])

    def test_sposta_interfaccia_senza_pulizia_conserva_i_neighbor(self):
        tmp, p = _lab('candy_test')
        with tmp:
            st = c.core.leggi_stato(p)
            dopo = _dopo(p, op.calcola_sposta_interfaccia(st, 'as50r1', 'eth1', 'Z', '190.9.9.1/24', pulisci_riferimenti=False))
            self.assertIn('neighbor 192.168.0.21', dopo['as50r1/etc/frr/frr.conf'])


if __name__ == '__main__':
    unittest.main()
