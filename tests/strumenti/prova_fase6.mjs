// Pilota della fase 6 in Chromium senza finestra (lab spento): card "Risoluzione di un nome" della
// scheda Test (catena dai file di tennis, poi un nome che non esiste con il rimedio), e il test
// suggerito dopo una modifica (Resolver di pc -> "Risoluzione di un nome" già sul dispositivo).
// Usa una COPIA di tennis_test (--base con la cartella "tennis").
//
//   node tests/strumenti/prova_fase6.mjs --url http://127.0.0.1:8795/ [--shots cartella]
import { apriBrowser, pausa, trovaChrome } from './cdp.mjs';

const arg = (n, d) => { const i = process.argv.indexOf('--' + n); return i > 0 ? process.argv[i + 1] : d; };
const URL_GUI = arg('url', 'http://127.0.0.1:8795/'), SHOTS = arg('shots');
const B = await apriBrowser(trovaChrome(arg('chrome')));
const passi = [];
async function passo(nome, f) {
  const t0 = Date.now();
  try { await f(); passi.push({nome, ok: true}); console.log(`ok   ${nome} (${((Date.now() - t0) / 1000).toFixed(1)} s)`); }
  catch (e) { passi.push({nome, ok: false, errore: e.message}); console.log(`KO   ${nome}: ${e.message}`); await B.scatta(SHOTS, 'ko-' + passi.length); }
}
const centro = sel => B.js(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return null; e.scrollIntoView({block: 'center'}); const r = e.getBoundingClientRect(); return {x: r.x + r.width / 2, y: r.y + r.height / 2}; })()`);
async function clicSu(sel) { const c = await centro(sel); if (!c) throw new Error('non trovato: ' + sel); await B.clic(c.x, c.y); }
async function scriviIn(sel, t) { await clicSu(sel); await B.js(`document.querySelector(${JSON.stringify(sel)}).select()`); await B.scrivi(t); }

await B.cdp('Page.enable'); await B.cdp('Runtime.enable');
await B.cdp('Page.navigate', {url: `${URL_GUI}?r=${Date.now()}#lab=tennis&tab=test`});
await B.aspetta(`!!document.querySelector('#dnSrc option')`, 20000, 'scheda Test');

await passo('Risoluzione di un nome dai file: web.com da pc', async () => {
  if (await B.js(`document.querySelector('#dnSrc').value`) !== 'pc') throw new Error('dispositivo proposto: ' + await B.js(`document.querySelector('#dnSrc').value`));
  await scriviIn('#dnNome', 'web.com');
  await clicSu('#bRisolvi');
  await B.aspetta(`/web\\.com → 2\\.2\\.0\\.2/.test(document.querySelector('#rRisolvi').innerText)`, 20000, 'esito');
  const t = await B.testo('#rRisolvi');
  if (!/ns_local → root → ns_com/.test(t) || !/Lab spento/.test(t)) throw new Error(t.slice(0, 300));
  await B.scatta(SHOTS, 'risoluzione-ok');
});

await passo('nome che non esiste: anello e rimedio', async () => {
  await scriviIn('#dnNome', 'nonce.com');
  await clicSu('#bRisolvi');
  await B.aspetta(`/la catena si interrompe/.test(document.querySelector('#rRisolvi').innerText)`, 20000, 'esito');
  if (!/non c'è un record A per nonce\.com/.test(await B.testo('#rRisolvi'))) throw new Error('anello sbagliato');
});

await passo('test suggerito dopo il Resolver di pc', async () => {
  await clicSu('[data-tab="topo"]');
  await B.aspetta(`!!document.querySelector('#svg g[data-id="d:pc"]')`, 10000, 'topologia');
  await clicSu('#bModifica');
  await clicSu('#svg g[data-id="d:pc"] rect');
  await clicSu('#side [data-gesto="disp"][data-azione="resolver"]');
  await B.aspetta(`!!document.querySelector('#side [name="scelto"]')`, 10000, 'modulo del resolver');
  await B.js(`(() => { const s = document.querySelector('#side [name="scelto"]'); s.value = [...s.options].find(o => o.textContent.includes('ns_com')).value; s.dispatchEvent(new Event('change', {bubbles: true})); })()`);
  await clicSu('#side [data-mod-azione="anteprima"]');
  await B.aspetta(`!!document.querySelector('#side [data-mod-azione="applica"]')`, 10000, 'anteprima');
  await clicSu('#side [data-mod-azione="applica"]');
  await B.aspetta(`!!document.querySelector('#side [data-mod-azione="prova"][data-test="risoluzione"]')`, 15000, 'test suggerito');
  if (!/Prima avvia il lab/.test(await B.testo('#side'))) throw new Error('manca la nota sul lab spento');
  await clicSu('#side [data-mod-azione="prova"]');
  await B.aspetta(`!document.querySelector('#t-test').hidden`, 5000, 'scheda Test');
  if (await B.js(`document.querySelector('#dnSrc').value`) !== 'pc') throw new Error('dispositivo non preimpostato');
  await clicSu('[data-tab="topo"]');
  await clicSu('#bAnnulla');
  await B.aspetta(`!!document.querySelector('#side [data-mod-azione="applica"]')`, 10000, 'annulla');
  await clicSu('#side [data-mod-azione="applica"]');
  await B.aspetta(`/Annullato/.test(document.querySelector('#side').innerText)`, 10000, 'annullato');
  await pausa(300);
});

if (B.errori.length) passi.push({nome: 'errori nella pagina', ok: false, errore: B.errori.join(' | ')});
await B.chiudi();
const ko = passi.filter(p => !p.ok);
console.log(`${passi.length - ko.length}/${passi.length} passi ok`);
for (const p of ko) console.log('KO', p.nome, p.errore);
process.exit(ko.length ? 1 : 0);
