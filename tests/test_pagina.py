"""
tests/test_pagina.py
La pagina della GUI (src/gui/static/) e come il server la consegna.

- Il server consegna index.html con la regola di sicurezza (Content-Security-Policy) e solo i
  file di static/ con un'estensione prevista; rifiuta '..', file nascosti e altre estensioni.
- Ogni file citato dalle pagine e ogni modulo importato dal JavaScript esiste e arriva con il tipo
  giusto; ogni nome importato è esportato dal modulo da cui viene.
- La pagina rispetta la regola di sicurezza: niente script in linea né attributi onclick=.
- Gli elementi che il codice cerca per id ($('#...')) esistono nella pagina o nel codice che li crea.
- Con Node: sintassi di ogni modulo, test dei componenti e delle etichette delle interfacce
  (tests/js/componenti.test.mjs, tests/js/etichette.test.mjs).

Le prove nel browser vero (schede, comandi Kathará, larghezze) sono in tests/strumenti/prova_gui.mjs.
"""
import os
import re
import shutil
import subprocess
import unittest

from _server import ServerDiProva
from gui import server

STATIC = server.STATIC
TESTS = os.path.dirname(os.path.abspath(__file__))
RE_IMPORT = re.compile(r"^import\s*\{([^}]*)\}\s*from\s*'([^']+)';", re.M)
RE_EXPORT = re.compile(r"^export\s+(?:async\s+function|function|const|let|class)\s+([\w$]+)", re.M)


def _file(estensione):
    out = []
    for radice, _, files in os.walk(STATIC):
        out += [os.path.join(radice, f) for f in files if f.endswith(estensione)]
    return sorted(out)


def _leggi(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


def _url(p):
    return '/static/' + os.path.relpath(p, STATIC).replace(os.sep, '/')


class TestConsegna(ServerDiProva):

    def test_pagina_e_intestazioni(self):
        codice, h, corpo = self.grezza('GET', '/')
        self.assertEqual(200, codice)
        self.assertTrue(h['content-type'].startswith('text/html'))
        self.assertIn("script-src 'self'", h['content-security-policy'])
        self.assertIn("frame-ancestors 'none'", h['content-security-policy'])
        self.assertEqual('nosniff', h['x-content-type-options'])
        self.assertIn(b'id="labNome"', corpo)
        self.assertEqual(corpo, self.grezza('GET', '/index.html')[2])

    def test_file_citati_e_moduli(self):
        """Ogni /static/... citato da una pagina e ogni import del JS risponde 200 con il tipo giusto."""
        tipi = {'.css': 'text/css', '.js': 'text/javascript', '.svg': 'image/svg+xml', '.html': 'text/html'}
        visti = set()
        for pagina in _file('.html'):
            for url in re.findall(r'(?:href|src)="(/static/[^"]+)"', _leggi(pagina)):
                visti.add(url)
        for js in _file('.js'):
            for _, rel in RE_IMPORT.findall(_leggi(js)):
                p = os.path.normpath(os.path.join(os.path.dirname(js), rel))
                visti.add(_url(p))
        self.assertTrue(len(visti) > 10)
        for url in sorted(visti):
            with self.subTest(url=url):
                codice, h, _ = self.grezza('GET', url)
                self.assertEqual(200, codice)
                self.assertTrue(h['content-type'].startswith(tipi[os.path.splitext(url)[1]]))

    def test_percorsi_rifiutati(self):
        for url in ('/static/../server.py', '/static/%2e%2e/server.py', '/static/js/../../api.py', '/static/.nascosto',
                    '/static/js/', '/static/', '/static/js/main.py', '/static//etc/passwd', '/static/js\\..\\..\\api.py',
                    '/server.py', '/favicon.ico'):
            with self.subTest(url=url):
                self.assertEqual(404, self.grezza('GET', url)[0])
        with self.subTest('host diverso'):
            self.assertEqual(403, self.grezza('GET', '/static/js/main.js', {'Host': 'esempio.it'})[0])


class TestFileStatico(unittest.TestCase):
    """I due controlli di file_statico, uno per volta (sopra, via HTTP, si coprono a vicenda)."""

    def test_controlli(self):
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            st = os.path.join(tmp, 'static')
            os.makedirs(os.path.join(st, 'css'))
            for nome in ('css/ok.css', '.segreto.css', 'css/.nascosto.css'):
                with open(os.path.join(st, nome), 'w') as f:
                    f.write('x')
            with open(os.path.join(tmp, 'fuori.css'), 'w') as f:
                f.write('segreto')
            collegamento = hasattr(os, 'symlink')
            if collegamento:
                try:
                    os.symlink(os.path.join(tmp, 'fuori.css'), os.path.join(st, 'css', 'link.css'))
                except OSError:          # Windows senza permessi per i collegamenti
                    collegamento = False
            with mock.patch.object(server, 'STATIC', st):
                self.assertEqual((b'x', 'text/css; charset=utf-8'), server.file_statico('/static/css/ok.css'))
                for url in ('/static/.segreto.css', '/static/css/.nascosto.css', '/static/css/../../fuori.css',
                            '/static/css/ok.py', '/static/css', '/css/ok.css'):
                    with self.subTest(url=url):
                        self.assertIsNone(server.file_statico(url))
                if collegamento:
                    self.assertIsNone(server.file_statico('/static/css/link.css'), 'collegamento che esce da static/')


class TestCodiceDellaPagina(unittest.TestCase):

    def test_nomi_importati_esistono(self):
        export = {os.path.normpath(p): set(RE_EXPORT.findall(_leggi(p))) for p in _file('.js')}
        for js in _file('.js'):
            for nomi, rel in RE_IMPORT.findall(_leggi(js)):
                origine = os.path.normpath(os.path.join(os.path.dirname(js), rel))
                for n in (x.strip() for x in nomi.split(',') if x.strip()):
                    with self.subTest(file=os.path.relpath(js, STATIC), nome=n):
                        self.assertIn(n, export.get(origine, set()), f"{n} non è esportato da {rel}")

    def test_regola_di_sicurezza(self):
        for p in _file('.html'):
            testo = _leggi(p)
            with self.subTest(file=os.path.basename(p)):
                self.assertEqual([], re.findall(r'<script(?![^>]*\bsrc=)[^>]*>', testo), 'script in linea')
                self.assertEqual([], re.findall(r'\son[a-z]+\s*=', testo), 'attributi on...=')
        for p in _file('.js'):
            with self.subTest(file=os.path.basename(p)):
                self.assertNotRegex(_leggi(p), r'\beval\(|new Function\(')

    def test_id_cercati_esistono(self):
        tutto = ''.join(_leggi(p) for p in _file('.html') + _file('.js'))
        dichiarati = set(re.findall(r'\bid="([\w-]+)"', tutto))
        for p in _file('.js'):
            for i in re.findall(r"\$\('#([\w-]+)'\)", _leggi(p)):
                with self.subTest(file=os.path.basename(p), id=i):
                    self.assertIn(i, dichiarati)

    def test_eseguibile_include_la_pagina(self):
        """La build PyInstaller (workflow) deve includere gui/static, altrimenti la GUI risponde 404."""
        wf = os.path.join(os.path.dirname(TESTS), '.github', 'workflows', 'build-and-release.yml')
        self.assertIn('--add-data "src/gui/static:gui/static"', _leggi(wf))

    def test_niente_risorse_esterne(self):
        """Offline: nessun font, script o foglio di stile da internet."""
        for p in _file('.html') + _file('.css') + _file('.js'):
            with self.subTest(file=os.path.relpath(p, STATIC)):
                self.assertNotRegex(_leggi(p), r'(?:src|href)="https?://|@import\s+url\(\s*["\']?https?://|fetch\(\s*["\']https?://')


@unittest.skipUnless(shutil.which('node'), 'node non installato')
class TestJavaScript(unittest.TestCase):

    def test_sintassi(self):
        for p in _file('.js'):
            with self.subTest(file=os.path.relpath(p, STATIC)):
                r = subprocess.run(['node', '--check', p], capture_output=True, text=True)
                self.assertEqual(0, r.returncode, r.stderr)

    def test_componenti(self):
        for nome in ('componenti.test.mjs', 'etichette.test.mjs'):
            with self.subTest(file=nome):
                r = subprocess.run(['node', '--test', os.path.join(TESTS, 'js', nome)],
                                   capture_output=True, text=True, timeout=120)
                self.assertEqual(0, r.returncode, r.stdout[-3000:] + r.stderr[-2000:])


if __name__ == '__main__':
    unittest.main()
