"""
tests/test_operazioni_83.py
Fase 8.3: reset del routing, fix sicuri in blocco, suggerimenti di vtysh --dryrun.
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
from core import routing_ops
from core.modifiche import scrivi_piano


def _lab(nome):
    tmp = tempfile.TemporaryDirectory()
    p = os.path.join(tmp.name, nome)
    shutil.copytree(os.path.join(c.FIXTURE_LABS, nome), p)
    return tmp, p


def _leggi(p, rel):
    with open(os.path.join(p, rel), encoding='utf-8') as f:
        return f.read()


class TestResetRouting(unittest.TestCase):

    def test_azzera_tutto_e_tiene_la_topologia(self):
        tmp, p = _lab('candy_test')
        with tmp:
            prima = c.leggi_albero(p)
            st = c.core.leggi_stato(p)
            piano = op.calcola_reset_routing(st)
            scrivi_piano(p, piano)
            dopo = c.leggi_albero(p)
            for rel, testo in prima.items():
                if not rel.endswith('frr.conf'):
                    self.assertEqual(testo, dopo[rel], f'{rel} non doveva cambiare')
            frr = dopo['as50r1/etc/frr/frr.conf']
            self.assertIn('router bgp 50', frr)
            self.assertIn('no bgp ebgp-requires-policy', frr)
            self.assertIn('no bgp network import-check', frr)
            for parola in ('neighbor', 'network', 'route-map', 'prefix-list', 'redistribute'):
                self.assertIsNone(re.search(rf'(?m)^\s*(?:ip )?{parola} ', frr), parola)
            self.assertIn('debug bgp updates in', frr)
            # idempotente
            self.assertEqual({}, op.calcola_reset_routing(c.core.leggi_stato(p))['modifiche'])

    def test_ospf_rip_restano_vuoti_e_costi_via(self):
        tmp, p = _lab('papillon_mio')
        with tmp:
            scrivi_piano(p, op.calcola_reset_routing(c.core.leggi_stato(p)))
            frr = _leggi(p, 'r2/etc/frr/frr.conf')
            self.assertIn('router ospf', frr)
            for parola in ('network', 'cost', 'redistribute', 'interface'):
                self.assertNotIn(parola, frr)
            self.assertIn('ospfd=yes', _leggi(p, 'r2/etc/frr/daemons'))

    def test_rotte_statiche_dei_router_tolte_ma_non_degli_host(self):
        tmp, p = _lab('hourglass_test')
        with tmp:
            router = next(n for n, d in c.core.leggi_stato(p)['dispositivi'].items() if d['tipo'] == 'router')
            with open(os.path.join(p, router + '.startup'), 'a', encoding='utf-8') as f:
                f.write('ip route add 9.9.9.0/24 via 10.0.0.1 dev eth0\n')
            st = c.core.leggi_stato(p)
            self.assertTrue(op.opzioni_reset_routing(st)['statiche'], 'la fixture deve avere rotte statiche sui router')
            host = {n: _leggi(p, n + '.startup') for n, d in st['dispositivi'].items() if d['tipo'] != 'router'}
            scrivi_piano(p, op.calcola_reset_routing(st))
            for n in op.opzioni_reset_routing(st)['router']:
                self.assertNotIn('ip route add', _leggi(p, n + '.startup'))
            for n, t in host.items():
                self.assertEqual(t, _leggi(p, n + '.startup'), f'{n} non doveva cambiare')

    def test_un_solo_router(self):
        tmp, p = _lab('candy_test')
        with tmp:
            piano = op.calcola_reset_routing(c.core.leggi_stato(p), 'as10r1')
            self.assertEqual({'as10r1/etc/frr/frr.conf'}, {r.replace(os.sep, '/') for r in piano['modifiche']})
            with self.assertRaises(op.ErroreOperazione):
                op.calcola_reset_routing(c.core.leggi_stato(p), 'non_esiste')

    def test_terminale_come_la_gui(self):
        with tempfile.TemporaryDirectory() as tmp:
            g, t = os.path.join(tmp, 'g'), os.path.join(tmp, 't')
            for x in (g, t):
                os.makedirs(x)
                shutil.copytree(os.path.join(c.FIXTURE_LABS, 'candy_test'), os.path.join(x, 'candy_test'))
            pg, pt = os.path.join(g, 'candy_test'), os.path.join(t, 'candy_test')
            piano = op.calcola_reset_routing(c.core.leggi_stato(pg))
            scrivi_piano(pg, piano)
            with c.silenzio():
                op.dopo_scrittura(pg, piano)
            risposte = iter(['1', 's'])
            with c.silenzio(), mock.patch.object(builtins, 'input', lambda *a: next(risposte)):
                routing_ops.azzera_routing(pt)
            self.assertEqual(c.leggi_albero(pg), c.leggi_albero(pt))


class TestFixSicuri(unittest.TestCase):

    def _rovina(self, p):
        f = os.path.join(p, 'as300r1/etc/frr/frr.conf')
        t = _leggi(p, 'as300r1/etc/frr/frr.conf')
        n = re.sub(r'^(\s*)neighbor 1\.0\.0\.9 remote-as 100', r'\1neigbor 1.0.0.9 remote-as 100', t, flags=re.M)
        self.assertNotEqual(t, n)
        with open(f, 'w', encoding='utf-8') as fh:
            fh.write(n)

    def test_applica_i_sicuri_in_blocco(self):
        tmp, p = _lab('lift_mio')
        with tmp:
            self._rovina(p)
            st = c.core.leggi_stato(p)
            sicuri = op.opzioni_correggi_frr_sicuri(st, 'as300r1')
            self.assertTrue(sicuri)
            scrivi_piano(p, op.calcola_correggi_frr_sicuri(st, 'as300r1'))
            self.assertIn('neighbor 1.0.0.9 remote-as 100', _leggi(p, 'as300r1/etc/frr/frr.conf'))
            self.assertEqual([], op.opzioni_correggi_frr_sicuri(c.core.leggi_stato(p), 'as300r1'))

    def test_nessun_sicuro_non_cambia_nulla(self):
        tmp, p = _lab('lift_mio')
        with tmp:
            piano = op.calcola_correggi_frr_sicuri(c.core.leggi_stato(p), 'as300r1')
            self.assertEqual({}, piano['modifiche'])
            self.assertTrue(piano['vuoto'])

    def test_info_e_proposte_non_si_toccano(self):
        from core.frr_autofix import analizza_frr_avanzato, applica_fix_sicuri_testo
        tmp, p = _lab('lift_mio')
        with tmp:
            self._rovina(p)
            st = c.core.leggi_stato(p)
            testo = _leggi(p, 'as300r1/etc/frr/frr.conf')
            tutte = analizza_frr_avanzato(testo, lab_path=p, dev='as300r1')
            senza_info = [i for i in tutte if i['gravita'] != 'info']
            etichette = {s['etichetta'] for s in op.opzioni_correggi_frr_sicuri(st, 'as300r1')}
            for i in tutte:
                if i['gravita'] == 'info':
                    for fx in i.get('fixes') or []:
                        self.assertNotIn(fx.get('etichetta'), etichette)
            for i in senza_info:
                for fx in i.get('fixes') or []:
                    if fx.get('confidenza') != 'sicuro':
                        self.assertNotIn(fx.get('etichetta'), etichette)
            self.assertEqual(applica_fix_sicuri_testo(testo, senza_info),
                             _leggi(p, 'as300r1/etc/frr/frr.conf').replace('neigbor', 'neighbor'))

    def test_terminale_s_applica_i_sicuri(self):
        with tempfile.TemporaryDirectory() as tmp:
            g, t = os.path.join(tmp, 'g'), os.path.join(tmp, 't')
            for x in (g, t):
                os.makedirs(x)
                shutil.copytree(os.path.join(c.FIXTURE_LABS, 'lift_mio'), os.path.join(x, 'lift_mio'))
                self._rovina(os.path.join(x, 'lift_mio'))
            pg, pt = os.path.join(g, 'lift_mio'), os.path.join(t, 'lift_mio')
            piano = op.calcola_correggi_frr_sicuri(c.core.leggi_stato(pg), 'as300r1')
            scrivi_piano(pg, piano)
            with c.silenzio():
                op.dopo_scrittura(pg, piano)
            nomi = sorted(c.core.leggi_stato(pt)['dispositivi'])
            risposte = iter([str(nomi.index('as300r1') + 1), 'S', 's', '', '0'])
            with c.silenzio(), mock.patch.object(builtins, 'input', lambda *a: next(risposte)):
                routing_ops.menu_diagnostica(pt)
            self.assertEqual(c.leggi_albero(pg), c.leggi_albero(pt))


class TestMenuIbgp(unittest.TestCase):
    """Collaudo di tennis: con AS2 e AS20 nella lista, "2" è la voce 2 (AS20), non l'AS 2."""

    def _scegli(self, risposta):
        tmp, p = _lab('tennis_test')
        with tmp:
            for r in ('as20r1', 'as20r2', 'as20r3', 'as20r4', 'as2r1', 'as2r2'):
                f = os.path.join(p, r, 'etc', 'frr', 'frr.conf')
                t = _leggi(p, f'{r}/etc/frr/frr.conf')
                with open(f, 'w', encoding='utf-8') as fh:
                    fh.write('\n'.join(l for l in t.split('\n') if not re.search(r'neighbor \S+ (remote-as (2|20)$|description iBGP)', l)) + '\n')
            prima = c.leggi_albero(p)
            risposte = iter([risposta, 's'])
            with c.silenzio(), mock.patch.object(builtins, 'input', lambda *a: next(risposte)):
                routing_ops.aggiungi_ibgp_full_mesh(p, None)
            dopo = c.leggi_albero(p)
            return {k.split('/')[0] for k in dopo if dopo[k] != prima.get(k) and k.endswith('frr.conf')}

    def test_voce_della_lista(self):
        self.assertEqual({'as20r1', 'as20r2', 'as20r3', 'as20r4'}, self._scegli('2'))

    def test_as_scritto(self):
        self.assertEqual({'as2r1', 'as2r2'}, self._scegli('AS2'))
        self.assertEqual({'as20r1', 'as20r2', 'as20r3', 'as20r4'}, self._scegli('as20'))


class TestSuggerimentoVtysh(unittest.TestCase):

    def test_riga_con_refuso_ha_il_suggerimento(self):
        from core.frr_autofix import suggerisci_per_riga_vtysh
        tmp, p = _lab('lift_mio')
        with tmp:
            TestFixSicuri()._rovina(p)
            testo = _leggi(p, 'as300r1/etc/frr/frr.conf')
            riga = 1 + next(k for k, l in enumerate(testo.split('\n')) if 'neigbor' in l)
            s = suggerisci_per_riga_vtysh(testo, riga, 'neigbor', lab_path=p, dev='as300r1')
            self.assertTrue(s and 'neighbor' in s, s)

    def test_sintassi_frr_usa_il_suggerimento(self):
        import inspect
        from gui import kathara
        self.assertIn('suggerisci_per_riga_vtysh', inspect.getsource(kathara.sintassi_frr))


if __name__ == '__main__':
    unittest.main()
