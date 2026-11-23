"""
tests/test_unione.py
Fase 5.7, unione a tre vie (core/unione.py): nuovo lab = originale + (nuovo - base). Senza
modifiche resta l'originale; una modifica cambia solo le sue righe; le righe che il modello non
contiene (policy, costi...) restano; file rinominati, file in più, file che l'originale non aveva.
"""
import unittest

import _comune  # noqa: F401  (percorso di src)

from core.unione import porta_nel_lab, unisci

ORIG = ('router bgp 1\n neighbor 1.1.1.2 remote-as 2\n neighbor 1.1.1.2 route-map LP in\n network 10.0.0.0/8\n!\n'
        'route-map LP permit 10\n set local-preference 150\n')
BASE = 'router bgp 1\n neighbor 1.1.1.2 remote-as 2\n network 10.0.0.0/8\n!\n'


class TestUnisci(unittest.TestCase):

    def test_senza_modifiche_resta_originale(self):
        self.assertEqual(ORIG, unisci(ORIG, BASE, BASE))

    def test_riga_aggiunta_al_suo_posto(self):
        nuovo = BASE.replace(' network 10.0.0.0/8\n', ' network 10.0.0.0/8\n network 20.0.0.0/8\n')
        self.assertEqual(ORIG.replace(' network 10.0.0.0/8\n', ' network 10.0.0.0/8\n network 20.0.0.0/8\n'), unisci(ORIG, BASE, nuovo))

    def test_riga_cambiata_e_tolta(self):
        nuovo = BASE.replace('remote-as 2', 'remote-as 3').replace(' network 10.0.0.0/8\n', '')
        out = unisci(ORIG, BASE, nuovo)
        self.assertIn('neighbor 1.1.1.2 remote-as 3', out)
        self.assertNotIn('network 10.0.0.0/8', out)
        self.assertIn('set local-preference 150', out, 'le righe che il modello non ha restano')

    def test_riga_da_togliere_che_l_originale_non_ha(self):
        self.assertEqual('a\nc\n', unisci('a\nc\n', 'a\nb\nc\n', 'a\nc\n'))


class TestPortaNelLab(unittest.TestCase):

    def test_rinomina_file_in_piu_e_avvisi(self):
        orig = {'r1/etc/frr/frr.conf': ORIG, 'r1/var/www/html/index.html': '<h1>mia</h1>', 'r1.startup': 'ip a add 1.1.1.1/30 dev eth0\n',
                'lab.conf': 'r1[0]="A"\n'}
        base = {'r1/etc/frr/frr.conf': BASE, 'r1.startup': 'ip address add 1.1.1.1/30 dev eth0\n', 'lab.conf': 'r1[0]="A"\n',
                'r1/etc/frr/daemons': 'bgpd=yes\n'}
        nuovo = {'rx/etc/frr/frr.conf': BASE.replace('1.1.1.2', '1.1.1.6'), 'rx.startup': 'ip address add 1.1.1.5/30 dev eth0\n',
                 'lab.conf': 'rx[0]="A"\n', 'rx/etc/frr/daemons': 'bgpd=yes\n'}
        file, r = porta_nel_lab(orig, base, nuovo, {'rx': 'r1'})
        self.assertIn('route-map LP permit 10', file['rx/etc/frr/frr.conf'])
        self.assertIn('neighbor 1.1.1.6 remote-as 2', file['rx/etc/frr/frr.conf'])
        self.assertEqual('<h1>mia</h1>', file['rx/var/www/html/index.html'], 'la pagina scritta a mano segue il dispositivo')
        self.assertEqual(['rx/var/www/html/index.html'], r['copiati'])
        self.assertEqual(['rx/etc/frr/daemons'], r['non_creati'], "l'originale non aveva daemons e la bozza non lo cambia")
        self.assertNotIn('rx/etc/frr/daemons', file)
        self.assertTrue(any('1.1.1.2' in a for a in r['avvisi']), 'la route-map cita un IP che non c\'è più')
        self.assertEqual('rx[0]="A"\n', file['lab.conf'])

    def test_dispositivo_tolto(self):
        orig = {'r2/x.html': 'p', 'r2.startup': 's\n', 'lab.conf': 'r1[0]="A"\nr2[0]="A"\n'}
        base = {'r2.startup': 's\n', 'lab.conf': 'r1[0]="A"\nr2[0]="A"\n'}
        file, r = porta_nel_lab(orig, base, {'lab.conf': 'r1[0]="A"\n'})
        self.assertEqual({'lab.conf': 'r1[0]="A"\n'}, file)


if __name__ == '__main__':
    unittest.main()
