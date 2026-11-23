// Pilota della diagnostica di frr.conf in Chromium senza
// finestra: card del Riepilogo, "!" sul disegno, "Diagnostica" nel pannello di as1r2 in modalità
// Modifica, correzione con anteprima e Applica, poi nessun problema; Annulla rimette il file.
// Usa una COPIA di stairs_mio con la route-map di as1r2 rotta (--base con la cartella "stairs").
//
//   node tests/strumenti/prova_diagnosi.mjs --url http://127.0.0.1:8795/ [--shots cartella]
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
async function clicVoce(testo) {
  await B.aspetta(`[...document.querySelectorAll('#side [data-mod-voce]')].some(b => b.innerText.includes(${JSON.stringify(testo)}))`, 15000, 'voce ' + testo);
  const i = await B.js(`[...document.querySelectorAll('#side [data-mod-voce]')].find(b => b.innerText.includes(${JSON.stringify(testo)})).dataset.modVoce`);
  await clicSu(`#side [data-mod-voce="${i}"]`);
}

await B.cdp('Page.enable'); await B.cdp('Runtime.enable');
await B.cdp('Page.navigate', {url: `${URL_GUI}?r=${Date.now()}#lab=stairs&tab=riep`});
await B.aspetta(`!!document.querySelector('#bDiagnosi')`, 20000, 'Riepilogo');

await passo('Riepilogo: la diagnostica trova la route-map non definita su as1r2', async () => {
  await clicSu('#bDiagnosi');
  await B.aspetta(`/problem/.test(document.querySelector('#rDiagnosi').innerText)`, 30000, 'esito');
  const t = await B.testo('#rDiagnosi');
  if (!/as1r2/.test(t) || !/LOCALMED_OUT non è definita/.test(t)) throw new Error(t.slice(0, 300));
});

await passo('Diagnostica dal pannello di as1r2, correzione con anteprima e Applica', async () => {
  await clicSu('[data-tab="topo"]');
  await B.aspetta(`!!document.querySelector('#svg g[data-id="d:as1r2"]')`, 10000, 'topologia');
  await clicSu('#bModifica');
  await clicSu('#svg g[data-id="d:as1r2"] circle');
  await clicSu('#side [data-gesto="disp"][data-azione="diagnosi"]');
  await B.aspetta(`/Diagnostica di as1r2/.test(document.querySelector('#side').innerText)`, 15000, 'menu della diagnostica');
  await clicVoce("Usa 'LOCALMED_OUT_10_0_0_6'");
  await B.aspetta(`!!document.querySelector('#side [data-mod-azione="applica"]')`, 15000, 'anteprima');
  if (!/LOCALMED_OUT_10_0_0_6 out/.test(await B.testo('#opRis'))) throw new Error('anteprima senza la riga corretta');
  await clicSu('#side [data-mod-azione="applica"]');
  await B.aspetta(`/Nessun problema trovato in as1r2/.test(document.querySelector('#side').innerText)`, 20000, 'diagnostica rifatta dopo l\'applica');
});

await passo('Annulla rimette la riga rotta', async () => {
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
