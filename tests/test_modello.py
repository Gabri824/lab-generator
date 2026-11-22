"""
tests/test_modello.py
Test delle regole di un lab (src/core/modello.py) e del loro uso nelle domande del terminale.

I messaggi attesi sono quelli che il wizard stampava prima della fase 1.3: le domande devono
rifiutare gli stessi valori con le stesse parole.
"""
import builtins
import os
import unittest

import _comune as c
from core import cli_io, modello
from core.modello import completa_lab, valida_lab
from core.persistence import dati_da_stato


def _con_input(risposte, funzione, *args, **kw):
    """Esegue una domanda del terminale con le risposte date; restituisce (valore, testo stampato)."""
    risposte = list(risposte)
    vero, builtins.input = builtins.input, lambda prompt='': risposte.pop(0)
    try:
        with c.silenzio() as out:
            valore = funzione(*args, **kw)
    finally:
        builtins.input = vero
    return valore, out.getvalue()


class TestRegole(unittest.TestCase):

    def test_valori_giusti(self):
        self.assertIsNone(modello.errore_nome_lab('bgp_es-1'))
        self.assertIsNone(modello.errore_nome_dispositivo('as10r1'))
        self.assertIsNone(modello.errore_lan('A1'))
        self.assertIsNone(modello.errore_ip_cidr('10.0.0.1/24'))
        self.assertIsNone(modello.errore_ip('10.0.0.1'))
        self.assertIsNone(modello.errore_ip('10.0.0.1/24'))
        self.assertIsNone(modello.errore_ipv4('10.0.0.1'))
        self.assertIsNone(modello.errore_asn('65000'))
        self.assertIsNone(modello.errore_area('0'))
        self.assertIsNone(modello.errore_area('1.1.1.1'))
        self.assertIsNone(modello.errore_protocolli('bgp, ospf'))
        self.assertIsNone(modello.errore_reti('10.0.0.0/8, 20.0.0.0/16'))
        self.assertIsNone(modello.errore_destinazione('default'))
        self.assertIsNone(modello.errore_destinazione('30.0.0.0/24'))
        self.assertIsNone(modello.errore_allow_recursion('any'))
        self.assertIsNone(modello.errore_allow_recursion('10.0.0.0/24; 20.0.0.0/8'))

    def test_messaggi_come_prima(self):
        self.assertEqual(
            "Nome non valido. Usa solo lettere minuscole, numeri, '_' e '-' (es. bgp_es1). "
            "Niente spazi, accenti, '/' o '.'.", modello.errore_nome_lab('Lab 1'))
        self.assertEqual("'web-srv' non è valido per Kathará (solo lettere minuscole, cifre e _).",
                         modello.errore_nome_dispositivo('web-srv'))
        self.assertEqual("Nome 'r1' già usato. Scegli un altro.", modello.errore_nome_usato('r1', {'r1'}))
        self.assertEqual("Nome LAN non valido. Usa solo lettere e numeri (es. A o A1). Evita punti o indirizzi IP.",
                         modello.errore_lan('A.1'))
        self.assertEqual("Inserisci la maschera usando '/' alla fine (es. 192.168.1.1/24)",
                         modello.errore_ip_cidr('10.0.0.1'))
        self.assertEqual("Formato non valido. Usa x.x.x.x/yy (es. 192.168.1.1/24)",
                         modello.errore_ip_cidr('10.0.0.300/24'))
        self.assertEqual("Errore: l'IP 10.0.0.1 è già stato assegnato. Scegli un altro IP.",
                         modello.errore_ip_usato('10.0.0.1/24', {'10.0.0.1'}))
        self.assertEqual("IP non valido (es. 10.0.0.1)", modello.errore_ip('10.0.0'))
        self.assertEqual("IP non valido. Inserisci un IPv4 (es. 10.0.0.2)", modello.errore_ipv4('10.0.0.2/24'))
        self.assertEqual("Numero AS non valido: solo cifre (es. 20).", modello.errore_asn('AS20'))
        self.assertEqual("Area OSPF non valida: un numero (es. 0) o x.x.x.x (es. 1.1.1.1).",
                         modello.errore_area('area1'))
        self.assertEqual("Inserisci almeno un protocollo (bgp/ospf/rip/statico).", modello.errore_protocolli(''))
        self.assertEqual("Usa solo: bgp ospf rip statico", modello.errore_protocolli('bgp isis'))
        self.assertEqual("Rete non valida: manca la maschera in '10.0.0.0' (es. 10.0.0.0/8)",
                         modello.errore_reti('10.0.0.0'))
        self.assertEqual("Inserisci una sola rete.", modello.errore_destinazione('10.0.0.0/8 20.0.0.0/8'))
        ifs = [{'name': 'eth0', 'ip': '10.0.0.10/24'}]
        self.assertEqual("10.1.0.1 non è in nessuna subnet di pc1 (10.0.0.0/24): "
                         "il gateway è l'IP del router sulla stessa LAN dell'host.",
                         modello.errore_gateway_host('10.1.0.1', ifs, 'pc1'))
        self.assertIsNone(modello.errore_gateway_host('10.0.0.1', ifs, 'pc1'))
        self.assertEqual("pc1 non ha l'interfaccia eth3 (ha: eth0, eth1).",
                         modello.errore_interfaccia('eth3', ['eth0', 'eth1'], 'pc1'))

    def test_nessun_emoji_nei_messaggi(self):
        """I messaggi delle regole sono testo semplice (alcuni terminali non stampano le emoji)."""
        messaggi = [
            modello.errore_nome_lab('X'), modello.errore_lan('.'), modello.errore_ip_cidr('x'),
            modello.errore_asn('x'), modello.errore_area('x'), modello.errore_protocolli('x'),
        ]
        messaggi += [p['messaggio'] for p in valida_lab(_modello_sbagliato())]
        for m in messaggi:
            self.assertFalse(any(ord(ch) >= 0x2190 for ch in m), m)


class TestDomandeDelTerminale(unittest.TestCase):
    """Le domande rifiutano i valori sbagliati con lo stesso messaggio di prima e li richiedono."""

    def test_ip_con_maschera(self):
        v, out = _con_input(['10.0.0.1', '10.0.0.1/24'], cli_io.valida_ip_cidr, 'IP: ')
        self.assertEqual('10.0.0.1/24', v)
        self.assertIn("❌ Inserisci la maschera usando '/' alla fine (es. 192.168.1.1/24)", out)

    def test_gateway_opzionale(self):
        v, out = _con_input(['10.0.0', ''], cli_io.valida_gateway, 'GW: ', opzionale=True)
        self.assertEqual('', v)
        self.assertIn("❌ IP non valido (es. 10.0.0.1), invio per nessuno", out)
        v, _ = _con_input(['10.0.0.1/24'], cli_io.valida_gateway, 'GW: ')
        self.assertEqual('10.0.0.1', v)

    def test_protocolli_asn_area(self):
        v, out = _con_input(['bgp isis', 'BGP, ospf, bgp'], cli_io.valida_protocols, 'P: ')
        self.assertEqual(['bgp', 'ospf'], v)
        self.assertIn("❌ Usa solo: bgp ospf rip statico", out)
        v, out = _con_input(['AS20', '20'], cli_io.input_asn, 'AS: ')
        self.assertEqual('20', v)
        self.assertIn("❌ Numero AS non valido: solo cifre (es. 20).", out)
        v, out = _con_input(['x', ''], cli_io.input_area, 'Area: ', default='0.0.0.0')
        self.assertEqual('0.0.0.0', v)
        self.assertIn("❌ Area OSPF non valida", out)

    def test_lan_e_destinazione(self):
        v, out = _con_input(['a.1', 'b'], cli_io.input_lan, 'LAN: ')
        self.assertEqual('B', v)
        self.assertIn("❌ Nome LAN non valido", out)
        v, out = _con_input(['10.0.0.0', '10.0.0.1/8'], cli_io.input_destinazione, 'Dest: ')
        self.assertEqual('10.0.0.0/8', v)
        self.assertIn("❌ Rete non valida: manca la maschera in '10.0.0.0' (es. 10.0.0.0/8)", out)

    def test_ip_gia_usato_nel_wizard(self):
        from core.wizard import _chiedi_ip_libero
        v, out = _con_input(['10.0.0.1/24', '10.0.0.2/24'], _chiedi_ip_libero, 'IP: ', {'10.0.0.1'}, set())
        self.assertEqual('10.0.0.2/24', v)
        self.assertIn("❌ Errore: l'IP 10.0.0.1 è già stato assegnato. Scegli un altro IP.", out)

    def test_nome_dispositivo(self):
        from core.persistence import _chiedi_nome
        v, out = _con_input(['web-srv', ''], _chiedi_nome, 'webserver', 'www1', set())
        self.assertEqual('web_srv', v)
        self.assertIn("❌ 'web-srv' non è valido per Kathará (solo lettere minuscole, cifre e _).", out)
        v, out = _con_input(['r1', 'r2'], _chiedi_nome, 'router', 'r1', {'r1'})
        self.assertEqual('r2', v)
        self.assertIn("Nome 'r1' già usato. Scegli un altro.", out)


def _modello_sbagliato():
    return {
        'nome': 'Lab Prova',
        'routers': {
            'r1': {'protocols': ['bgp', 'ospf'], 'asn': 'AS1', 'ospf_area': '0.0.0.0', 'ospf_area_stub': True,
                   'interfaces': [{'name': 'eth0', 'lan': 'A', 'ip': '10.0.0.1/30'},
                                  {'name': 'eth1', 'lan': 'B.1', 'ip': '10.0.1.0/24'}],
                   'igp_networks': ['10.0.0.0/8'],
                   'static_routes': [{'network': '30.0.0.0', 'via': '10.0.0.2', 'dev': 'eth9'}]},
            'R-2': {'protocols': ['isis'], 'asn': '', 'interfaces': [{'name': 'eth0', 'lan': 'A', 'ip': '10.0.0.1/30'}]},
        },
        'hosts': [
            {'name': 'pc1', 'interfaces': [{'name': 'eth0', 'lan': 'C', 'ip': '10.2.0.10/24'}],
             'gateway': '10.9.0.1', 'gw_dev': 'eth0', 'ip': '10.2.0.10/24', 'lan': 'C'},
            {'name': 'dns1', 'dns': True, 'ip': '10.3.0.2/24', 'gateway': '10.4.0.1', 'lan': 'D',
             'zones': {'com': {'www': '10.0.0.x', 'web': {'type': 'CNAME'}}},
             'allow_recursion': '10.0.0.0', 'delegations': [{'zone': '', 'ns': 'dns.com', 'ip': '1.2.3'}]},
        ],
        'wwws': [{'name': 'pc1', 'ip': '10.5.0.80', 'gateway': '10.5.0.1', 'lan': 'E'},
                 {'name': 'web2', 'ip': '10.6.0.80/24', 'gateway': '', 'lan': 'F'}],
        'resolver': 'pc1',
    }


class TestValidaLab(unittest.TestCase):

    def test_trova_i_problemi(self):
        trovati = {(p['campo'], p['gravita']) for p in valida_lab(_modello_sbagliato())}
        attesi = {
            ('lab.nome', 'errore'),
            ('r1.asn', 'errore'),
            ('r1.ospf_area_stub', 'avviso'),
            ('r1.interfaces[1].lan', 'errore'),
            ('r1.interfaces[1].ip', 'avviso'),            # indirizzo di rete
            ('r1.static_routes[0].network', 'errore'),
            ('r1.static_routes[0].dev', 'avviso'),
            ('R-2.name', 'errore'),
            ('R-2.protocols', 'errore'),
            ('R-2.interfaces[0].ip', 'errore'),           # IP già usato da r1
            ('pc1.gateway', 'errore'),                    # host: gateway fuori subnet
            ('dns1.gateway', 'avviso'),                   # dns: gateway fuori subnet
            ('dns1.zones.com.www', 'errore'),
            ('dns1.zones.com.web.target', 'errore'),
            ('dns1.allow_recursion', 'errore'),
            ('dns1.delegations[0].zone', 'errore'),
            ('dns1.delegations[0].ip', 'errore'),
            ('pc1.name', 'errore'),                       # nome usato due volte (host e www)
            ('pc1.interfaces[0].ip', 'errore'),           # www senza maschera
            ('web2.gateway', 'errore'),                   # www senza gateway
            ('lab.resolver', 'errore'),
        }
        self.assertEqual(set(), attesi - trovati, 'problemi non trovati')

    def test_avvisi_tra_dispositivi(self):
        m = {'routers': {
            'r1': {'protocols': ['ospf'], 'ospf_area': '0.0.0.0', 'igp_networks': ['10.0.0.0/8'],
                   'interfaces': [{'name': 'eth0', 'lan': 'A', 'ip': '10.0.0.1/30'},
                                  {'name': 'eth1', 'lan': 'B', 'ip': '10.0.1.1/30'}]},
            'r2': {'protocols': ['ospf'], 'ospf_area': '1.1.1.1', 'igp_networks': ['10.0.0.0/8'],
                   'interfaces': [{'name': 'eth0', 'lan': 'A', 'ip': '10.0.0.2/30'},
                                  {'name': 'eth1', 'lan': 'C', 'ip': '10.0.9.1/24'}]},
        }, 'hosts': [{'name': 'pc', 'interfaces': [{'name': 'eth0', 'lan': 'C', 'ip': '10.0.8.5/24'}],
                      'gateway': '', 'ip': '10.0.8.5/24', 'lan': 'C'}], 'wwws': []}
        msg = [p['messaggio'] for p in valida_lab(m)]
        self.assertTrue(any("aree OSPF diverse (r1 area 0.0.0.0, r2 area 1.1.1.1)" in x for x in msg), msg)
        self.assertTrue(any("LAN B: link /30 di r1" in x for x in msg), msg)
        self.assertTrue(any("LAN C: i dispositivi sono in subnet diverse" in x for x in msg), msg)
        # durante il wizard il link con un solo estremo non si segnala: l'altro può arrivare dopo
        self.assertFalse(any("LAN B: link /30" in p['messaggio'] for p in valida_lab(m, parziale=True)))

    def test_lab_reali_senza_errori(self):
        """I lab che funzionano, trasformati in modello, non hanno errori."""
        cartelle = [os.path.join(c.FIXTURE_LABS, lab) for lab in c.elenco_lab()]
        cartelle += [os.path.join(c.ATTESI, 'scenari', s) for s in c.elenco_scenari()]
        for p in cartelle:
            with self.subTest(lab=os.path.basename(p)):
                r, h, w = dati_da_stato(c.core.leggi_stato(p))
                errori = [x for x in valida_lab({'routers': r, 'hosts': h, 'wwws': w}) if x['gravita'] == 'errore']
                self.assertEqual([], errori)


class TestAreeOspf(unittest.TestCase):
    """Router di confine (ABR): l'area si dà per rete (fase 1.8)."""

    def modello(self, area_r3='1.1.1.1', aree_r2=None, stub=None):
        return {'routers': {
            'r1': {'protocols': ['ospf'], 'ospf_area': '0.0.0.0', 'igp_networks': ['10.0.0.0/30'],
                   'interfaces': [{'name': 'eth0', 'lan': 'A', 'ip': '10.0.0.1/30'}]},
            'r2': {'protocols': ['ospf'], 'ospf_area': '0.0.0.0', 'igp_networks': ['10.0.0.0/30', '10.1.0.0/30'],
                   'ospf_aree': aree_r2 or {'10.0.0.0/30': '0.0.0.0', '10.1.0.0/30': '1.1.1.1'},
                   'ospf_aree_stub': stub if stub is not None else ['1.1.1.1'],
                   'interfaces': [{'name': 'eth0', 'lan': 'A', 'ip': '10.0.0.2/30'},
                                  {'name': 'eth1', 'lan': 'B', 'ip': '10.1.0.1/30'}]},
            'r3': {'protocols': ['ospf'], 'ospf_area': area_r3, 'ospf_area_stub': True, 'igp_networks': ['10.1.0.0/30'],
                   'interfaces': [{'name': 'eth0', 'lan': 'B', 'ip': '10.1.0.2/30'}]},
        }, 'hosts': [], 'wwws': []}

    def test_router_di_confine_valido(self):
        self.assertEqual([], valida_lab(self.modello()))

    def test_lan_in_aree_diverse(self):
        msg = [p['messaggio'] for p in valida_lab(self.modello(area_r3='2.2.2.2'))]
        self.assertTrue(any('LAN B: i router la mettono in aree OSPF diverse' in m for m in msg), msg)

    def test_area_che_non_tocca_la_backbone(self):
        # r2 non è più di confine: mette tutte e due le reti in area 1.1.1.1
        m = self.modello(aree_r2={'10.0.0.0/30': '1.1.1.1', '10.1.0.0/30': '1.1.1.1'})
        m['routers']['r1']['ospf_area'] = '0.0.0.0'
        m['routers']['r1']['interfaces'][0]['lan'] = 'Z'           # r1 da solo nella backbone
        msg = [p['messaggio'] for p in valida_lab(m)]
        self.assertTrue(any("L'area OSPF 1.1.1.1 non tocca la backbone" in x for x in msg), msg)

    def test_backbone_stub(self):
        msg = [p['messaggio'] for p in valida_lab(self.modello(stub=['0.0.0.0', '1.1.1.1']))]
        self.assertIn('La backbone (area 0.0.0.0) non può essere stub.', msg)

    def test_area_non_valida(self):
        m = self.modello(aree_r2={'10.0.0.0/30': '0.0.0.0', '10.1.0.0/30': 'uno'})
        self.assertTrue(any(p['campo'] == 'r2.ospf_aree.10.1.0.0/30' and p['gravita'] == 'errore' for p in valida_lab(m)))

    def test_interfaccia_senza_ip(self):
        m = self.modello()
        m['routers']['r3']['interfaces'][0]['ip'] = ''
        msg = [p['messaggio'] for p in valida_lab(m)]
        self.assertIn("r3 eth0: manca l'IP (nello startup non c'è la riga 'ip address add').", msg)


class TestCompletaLab(unittest.TestCase):

    def test_valori_proposti(self):
        m = completa_lab({
            'routers': {
                'r1': {'protocols': ['ospf'], 'interfaces': [{'lan': 'A', 'ip': '10.0.0.1/30'}]},
                'r2': {'protocols': ['ospf'], 'ospf_area': '1.1.1.1', 'ospf_area_stub': True,
                       'interfaces': [{'lan': 'A', 'ip': '10.0.0.2/30'}]},
                'r3': {'protocols': ['ospf', 'statico'],
                       'interfaces': [{'lan': 'B', 'ip': '20.0.0.1/24'}, {'lan': 'C', 'ip': '30.0.0.1/24'}],
                       'static_routes': [{'network': 'default', 'via': '30.0.0.254'}]},
            },
            'hosts': [{'interfaces': [{'lan': 'C', 'ip': '30.0.0.10/24'}, {'lan': 'D', 'ip': '40.0.0.10/24'}],
                       'gateway': '40.0.0.1'},
                      {'dns': True, 'ip': '30.0.0.53/24', 'gateway': '30.0.0.1', 'lan': 'C'},
                      {'dns': True, 'ip': '30.0.0.54/24', 'gateway': '30.0.0.1', 'lan': 'C'}],
            'wwws': [{'ip': '20.0.0.80/24', 'gateway': '20.0.0.1', 'lan': 'B'}],
        })
        r = m['routers']
        self.assertEqual('eth0', r['r1']['interfaces'][0]['name'])
        self.assertEqual(('0.0.0.0', False), (r['r1']['ospf_area'], r['r1']['ospf_area_stub']))
        self.assertEqual(('1.1.1.1', True), (r['r2']['ospf_area'], r['r2']['ospf_area_stub']))
        self.assertEqual(('0.0.0.0', False), (r['r3']['ospf_area'], r['r3']['ospf_area_stub']),
                         "eredita l'area del primo router OSPF")
        self.assertEqual(['10.0.0.0/8'], r['r1']['igp_networks'])
        self.assertEqual('eth1', r['r3']['static_routes'][0]['dev'])
        host, root, dns2 = m['hosts']
        self.assertEqual(('host1', 'eth1'), (host['name'], host['gw_dev']))
        self.assertEqual(('root', 'master'), (root['name'], root['root_type']))
        self.assertEqual(('dns2', 'hint'), (dns2['name'], dns2['root_type']))
        self.assertEqual('www1', m['wwws'][0]['name'])

    def test_non_cambia_i_lab_completi(self):
        for lab in c.elenco_lab():
            with self.subTest(lab=lab):
                r, h, w = dati_da_stato(c.core.leggi_stato(os.path.join(c.FIXTURE_LABS, lab)))
                self.assertEqual(r, completa_lab({'routers': r, 'hosts': h, 'wwws': w})['routers'])


if __name__ == '__main__':
    unittest.main()
