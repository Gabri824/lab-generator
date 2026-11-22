"""
tests/test_controlli.py
Controlli statici di frr.conf (src/core/analyzer.py): casi specifici.
"""
import unittest

import _comune  # noqa: F401  (mette src/ nel path)
from core import riferimenti_frr


class TestRiferimentiFrr(unittest.TestCase):

    def test_prefix_list_usata_da_match_next_hop(self):
        """La route-map eBGP usa la prefix-list con 'match ip next-hop': non è 'definita ma non usata'."""
        righe = [
            'router rip',
            '    redistribute bgp route-map eBGP',
            'ip prefix-list myNeighbors permit 10.2.0.0/30 le 32',
            'route-map eBGP permit 10',
            '    match ip next-hop prefix-list myNeighbors',
        ]
        self.assertEqual([], [x['messaggio'] for x in riferimenti_frr(righe)])

    def test_prefix_list_non_definita_in_match_next_hop(self):
        righe = ['route-map eBGP permit 10', '    match ip next-hop prefix-list Inesistente',
                 'router rip', '    redistribute bgp route-map eBGP']
        msg = [x['messaggio'] for x in riferimenti_frr(righe)]
        self.assertTrue(any('prefix-list Inesistente non è definita' in m for m in msg), msg)

    def test_prefix_list_davvero_non_usata(self):
        righe = ['router bgp 1', 'ip prefix-list Sola permit 10.0.0.0/8']
        msg = [x['messaggio'] for x in riferimenti_frr(righe)]
        self.assertTrue(any('Sola è definita ma non è usata' in m for m in msg), msg)


if __name__ == '__main__':
    unittest.main()
