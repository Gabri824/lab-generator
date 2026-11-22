// tests/strumenti/cdp.mjs
// Un Chromium senza finestra guidato con il protocollo DevTools (CDP), senza dipendenze: lo usano
// prova_gui.mjs (schede e comandi Kathará) e prova_editor.mjs (editor grafico). Node 22+.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

export const pausa = ms => new Promise(r => setTimeout(r, ms));

export function trovaChrome(scelto) {
  return scelto || ['/usr/bin/chromium', '/usr/bin/google-chrome', '/usr/bin/chromium-browser'].find(p => fs.existsSync(p));
}

// Avvia Chromium e apre una scheda. Restituisce gli strumenti per guidarla.
export async function apriBrowser(chromePath, larghezza = 1440, altezza = 900) {
  const profilo = fs.mkdtempSync(path.join(os.tmpdir(), 'prova-gui-'));
  const chrome = spawn(chromePath, ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profilo}`,
    '--no-first-run', '--no-default-browser-check', '--disable-gpu', `--window-size=${larghezza},${altezza}`,
    // la scheda senza finestra non va trattata come "in sottofondo" (fotogrammi e timer rallentati)
    '--disable-renderer-backgrounding', '--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows',
    'about:blank'],
  { stdio: ['ignore', 'ignore', 'pipe'] });
  const wsBrowser = await new Promise((ok, ko) => {
    let buf = '';
    chrome.stderr.on('data', d => { buf += d; const m = buf.match(/DevTools listening on (ws:\/\/\S+)/); if (m) ok(m[1]); });
    setTimeout(() => ko(new Error('Chromium non risponde')), 20000);
  });
  const porta = new URL(wsBrowser).port;
  const pagina = await (await fetch(`http://127.0.0.1:${porta}/json/new?about:blank`, { method: 'PUT' })).json();
  const ws = new WebSocket(pagina.webSocketDebuggerUrl);
  await new Promise(r => ws.addEventListener('open', r));
  let nid = 0;
  const attese = new Map(), errori = [];
  function cdp(method, params = {}) {
    return new Promise((ok, ko) => { const id = ++nid; attese.set(id, { ok, ko }); ws.send(JSON.stringify({ id, method, params })); });
  }
  ws.addEventListener('message', ev => {
    const m = JSON.parse(ev.data);
    if (m.id && attese.has(m.id)) { const { ok, ko } = attese.get(m.id); attese.delete(m.id); m.error ? ko(new Error(m.error.message)) : ok(m.result); return; }
    if (m.method === 'Page.javascriptDialogOpening') cdp('Page.handleJavaScriptDialog', { accept: true });
    if (m.method === 'Runtime.exceptionThrown') errori.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
    if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') errori.push(m.params.args.map(a => a.value ?? a.description).join(' '));
    if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error') errori.push(m.params.entry.text + ' ' + (m.params.entry.url || ''));
  });
  async function js(expr) {
    const r = await cdp('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
    return r.result.value;
  }
  async function aspetta(cond, ms, cosa) {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) { if (await js(cond)) return true; await pausa(300); }
    throw new Error(`tempo scaduto (${Math.round(ms / 1000)} s): ${cosa}`);
  }
  const testo = sel => js(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); return e ? e.innerText.trim() : null; })()`);
  const visibile = sel => js(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); return !!e && !e.hidden && e.offsetParent !== null; })()`);
  async function scatta(cartella, nome) {
    if (!cartella) return;
    fs.mkdirSync(cartella, { recursive: true });
    const r = await cdp('Page.captureScreenshot', { format: 'png' });
    fs.writeFileSync(path.join(cartella, nome + '.png'), Buffer.from(r.data, 'base64'));
  }
  // tasti veri (eventi della tastiera di Chromium): tasto('r'), tasto('Escape'), tasto('z', {ctrl: true})
  const CODICI = { Escape: 27, Delete: 46, Tab: 9, Enter: 13, Backspace: 8, ArrowLeft: 37, ArrowUp: 38, ArrowRight: 39, ArrowDown: 40 };
  async function tasto(k, { ctrl = false, shift = false } = {}) {
    const lettera = k.length === 1;
    const modifiers = (ctrl ? 2 : 0) | (shift ? 8 : 0);
    const base = { key: k, code: lettera ? 'Key' + k.toUpperCase() : k, windowsVirtualKeyCode: lettera ? k.toUpperCase().charCodeAt(0) : CODICI[k], modifiers };
    await cdp('Input.dispatchKeyEvent', Object.assign({ type: 'keyDown' }, base, lettera && !ctrl ? { text: k } : {}));
    await cdp('Input.dispatchKeyEvent', Object.assign({ type: 'keyUp' }, base));
  }
  const scrivi = t => cdp('Input.insertText', { text: t });
  // mouse vero sullo schermo (coordinate della pagina)
  async function clic(x, y, { shift = false } = {}) {
    const m = shift ? 8 : 0;
    await cdp('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y, modifiers: m });
    await cdp('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1, modifiers: m });
    await cdp('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1, modifiers: m });
  }
  async function trascina(x0, y0, x1, y1, { shift = false, passi = 8 } = {}) {
    const m = shift ? 8 : 0;
    await cdp('Input.dispatchMouseEvent', { type: 'mouseMoved', x: x0, y: y0, modifiers: m });
    await cdp('Input.dispatchMouseEvent', { type: 'mousePressed', x: x0, y: y0, button: 'left', clickCount: 1, modifiers: m });
    for (let i = 1; i <= passi; i++)
      await cdp('Input.dispatchMouseEvent', { type: 'mouseMoved', x: x0 + (x1 - x0) * i / passi, y: y0 + (y1 - y0) * i / passi, button: 'left', buttons: 1, modifiers: m });
    await cdp('Input.dispatchMouseEvent', { type: 'mouseReleased', x: x1, y: y1, button: 'left', clickCount: 1, modifiers: m });
  }
  function chiudi(codice) {
    try { ws.close(); } catch (e) { /* già chiuso */ }
    try { chrome.kill(); } catch (e) { /* già chiuso */ }
    setTimeout(() => { fs.rmSync(profilo, { recursive: true, force: true }); process.exit(codice); }, 500);
  }
  await cdp('Page.enable'); await cdp('Runtime.enable'); await cdp('Log.enable');
  await cdp('Emulation.setDeviceMetricsOverride', { width: larghezza, height: altezza, deviceScaleFactor: 1, mobile: false });
  return { cdp, js, aspetta, testo, visibile, scatta, tasto, scrivi, clic, trascina, chiudi, errori };
}
