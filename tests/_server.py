"""
tests/_server.py
Server vero della GUI su 127.0.0.1 per i test (test_api.py, test_pagina.py).
"""
import http.client
import json
import os
import shutil
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

import _comune as c
from core import supporto
from gui import server


class ServerDiProva(unittest.TestCase):
    """Un server vero su 127.0.0.1 con una cartella dei lab temporanea."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.base = cls.tmp.name
        cls.st = server.Stato(cls.base, None)
        cls.srv = ThreadingHTTPServer(('127.0.0.1', 0), server.Gestore)
        cls.porta = cls.srv.server_address[1]
        server.Gestore.st = cls.st
        server.Gestore.host_ok = {f'127.0.0.1:{cls.porta}'}
        cls.st.server = cls.srv
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def lab(self, nome):
        """Copia nuova di un lab di prova nella cartella dei lab del server."""
        p = os.path.join(self.base, nome)
        shutil.rmtree(p, ignore_errors=True)
        shutil.rmtree(supporto.cartella_supporto(p), ignore_errors=True)
        shutil.copytree(os.path.join(c.FIXTURE_LABS, nome), p)
        return p

    def grezza(self, metodo, percorso, intestazioni=None):
        """(codice, intestazioni, corpo in byte) senza interpretare il JSON; il percorso va com'è."""
        conn = http.client.HTTPConnection('127.0.0.1', self.porta, timeout=60)
        h = {'Host': f'127.0.0.1:{self.porta}'}
        h.update(intestazioni or {})
        try:
            conn.request(metodo, percorso, headers=h)
            r = conn.getresponse()
            return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
        finally:
            conn.close()

    def richiesta(self, metodo, percorso, corpo=None, intestazioni=None, grezzo=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.porta, timeout=60)
        h = {'Host': f'127.0.0.1:{self.porta}', 'X-Lab-Gen': '1', 'Content-Type': 'application/json'}
        h.update(intestazioni or {})
        dati = grezzo if grezzo is not None else (None if corpo is None else json.dumps(corpo).encode('utf-8'))
        try:
            conn.request(metodo, percorso, body=dati, headers=h)
            r = conn.getresponse()
            return r.status, json.loads(r.read().decode('utf-8'))
        finally:
            conn.close()

    def azione(self, **corpo):
        return self.richiesta('POST', '/api/azione', corpo)

    def anteprima_e_applica(self, lab, operazione, parametri):
        codice, ant = self.azione(azione='anteprima', lab=lab, operazione=operazione, parametri=parametri)
        self.assertEqual(200, codice, ant)
        codice, esito = self.azione(azione='applica', lab=lab, operazione=operazione, parametri=parametri,
                                    impronte=ant['impronte'], firma=ant['firma'])
        self.assertEqual(200, codice, esito)
        return ant, esito
