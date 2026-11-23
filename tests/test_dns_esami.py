"""
tests/test_dns_esami.py
DNS come negli esami del corso (Esami_IDC: tennis, crab, mirada, palabra, patchwork, Shuriken),
verificati il 2026-11-22: la creazione (wizard ed editor) deve saper fare la gerarchia root ->
dominio di primo livello -> sottodominio (record DELEGATION, come crab e Shuriken) e il resolver
locale scritto come nelle soluzioni ('allow-recursion { 0/0; }', forma abbreviata di bind).
"""
import os
import tempfile
import unittest

import _comune as c
from core.modello import errore_allow_recursion, parse_reti


def _modello_crab():
    """Gerarchia di crab su una sola LAN (il routing non c'entra): root, it, roma3, local, client, web."""
    dns = lambda nome, ip, **k: dict({'name': nome, 'ip': ip, 'gateway': '30.0.0.1', 'lan': 'A', 'dns': True,
                                      'root_type': 'hint', 'allow_recursion': None, 'dnssec_validation': False,
                                      'delegations': [], 'zones': None}, **k)
    return {
        'routers': {'r1': {'protocols': ['statico'], 'asn': '', 'interfaces': [{'name': 'eth0', 'lan': 'A', 'ip': '30.0.0.1/24'}],
                           'static_routes': []}},
        'hosts': [
            dns('root', '30.0.0.10/24', root_type='master', delegations=[{'zone': 'it', 'ns': 'dns.it', 'ip': '30.0.0.4'}]),
            dns('it', '30.0.0.4/24', zones={'it': {'dns.it.': '30.0.0.4', 'roma3.it.': {
                'type': 'DELEGATION', 'zone': 'roma3.it.', 'ns': 'dns.roma3.it.', 'ns_ip': '30.0.0.3'}}}),
            dns('roma3', '30.0.0.3/24', zones={'roma3.it': {'dns.roma3.it.': '30.0.0.3', 'web.roma3.it.': '30.0.0.2'}}),
            dns('local', '30.0.0.5/24', allow_recursion='0/0', dnssec_validation=True),
            {'name': 'client', 'interfaces': [{'name': 'eth0', 'lan': 'A', 'ip': '30.0.0.20/24'}], 'gateway': '30.0.0.1'},
        ],
        'wwws': [{'name': 'web', 'ip': '30.0.0.2/24', 'gateway': '30.0.0.1', 'lan': 'A'}],
        'resolver': 'local',
    }


class TestReti(unittest.TestCase):

    def test_forma_abbreviata_di_bind(self):
        self.assertEqual(['0.0.0.0/0', '10.0.0.0/8', '192.168.0.0/16'], parse_reti('0/0, 10/8 192.168/16'))
        self.assertIsNone(errore_allow_recursion('0/0'), 'come le soluzioni del corso')
        self.assertIsNone(errore_allow_recursion('any'))
        self.assertIsNotNone(errore_allow_recursion('10/33'))
        self.assertIsNotNone(errore_allow_recursion('10.0.0.0'))


class TestGerarchiaCrab(unittest.TestCase):

    def test_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with c.silenzio():
                e = c.core.genera_lab(tmp, 'crab', _modello_crab())
            self.assertTrue(e['creato'], e['errori'])
            lab = os.path.join(tmp, 'crab')

            def leggi(rel):
                with open(os.path.join(lab, rel), encoding='utf-8') as f:
                    return ' '.join(f.read().split())
            self.assertIn('it. IN NS dns.it.', leggi('root/etc/bind/db.root'))
            db_it = leggi('it/etc/bind/db.it')
            self.assertIn('roma3.it. IN NS dns.roma3.it.', db_it, 'delega dal dominio di primo livello')
            self.assertIn('dns.roma3.it. IN A 30.0.0.3', db_it, 'glue del sottodominio')
            zona = next(f for f in os.listdir(os.path.join(lab, 'roma3', 'etc', 'bind')) if f.startswith('db.') and 'roma3' in f)
            self.assertIn('web.roma3.it. IN A 30.0.0.2', leggi(os.path.join('roma3', 'etc', 'bind', zona)))
            opzioni = leggi('local/etc/bind/named.conf.options')
            self.assertIn('allow-recursion { 0/0; };', opzioni)
            self.assertIn('dnssec-validation no;', opzioni)
            self.assertIn('nameserver 30.0.0.5', leggi('client/etc/resolv.conf'))


if __name__ == '__main__':
    unittest.main()
