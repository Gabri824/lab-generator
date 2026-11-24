// Pilota della fase 8 in Chromium senza finestra: checklist "Pronto per la consegna" (Riepilogo e
// Archivio), "Azzera il routing" con anteprima, Applica e Annulla, casella di pulizia in "Togli il
// dispositivo", "Applica i fix sicuri" nella Diagnostica, Togli network BGP.
// Usa COPIE dei lab (candy per il routing, lift per i fix sicuri): --lab candy --lab-fix lift.
//
//   node tests/strumenti/prova_fase8.mjs --url http://127.0.0.1:8795/ --lab candy --lab-fix lift [--shots cartella]
import { apriBrowser, pausa, trovaChrome } from './cdp.mjs';

const arg = (n, d) => { const i = process.argv.indexOf('--' + n); return i > 0 ? process.argv[i + 1] : d; };
const URL_GUI = arg('url', 'http://127.0.0.1:8795/'), LAB = arg('lab', 'candy'), FIX = arg('lab-fix', 'lift'), SHOTS = arg('shots');
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
const apri = async (lab, tab) => {
  await B.cdp('Page.navigate', {url: `${URL_GUI}?r=${Date.now()}#lab=${lab}&tab=${tab}`});
  await B.aspetta(`document.querySelector('#labNome').innerText === ${JSON.stringify(lab)} && !!document.querySelector('#t-riep .consegna-card')`, 20000, 'lab ' + lab);
  await pausa(300);
};

await B.cdp('Page.enable'); await B.cdp('Runtime.enable');

await passo('Checklist "Pronto per la consegna" in Riepilogo e in Archivio', async () => {
  await apri(LAB, 'riep');
  await B.aspetta(`document.querySelectorAll('.consegna-card li').length >= 12`, 30000, 'checklist (due schede)');
  const t = await B.js(`document.querySelector('#t-riep .consegna-card').innerText`);
  if (!/Pronto per la consegna/.test(t) || !/default route/i.test(t) || !/frr\.conf/.test(t) || !/archivio/i.test(t)) throw new Error(t.slice(0, 400));
  await clicSu('[data-tab="arch"]');
  const a = await B.js(`document.querySelector('#t-arch .consegna-card').innerText`);
  if (!/Pronto per la consegna/.test(a)) throw new Error(a.slice(0, 200));
  await B.scatta(SHOTS, 'consegna-archivio');
});

await passo('Azzera il routing: anteprima, Applica, il lab non ha più network né neighbor, Annulla', async () => {
  await apri(LAB, 'topo');
  await clicSu('#bModifica');
  await clicSu('#side [data-gesto="reset"]');
  await B.aspetta(`!!document.querySelector('#side [data-mod-azione="anteprima"]')`, 10000, 'form');
  await clicSu('#side [data-mod-azione="anteprima"]');
  await B.aspetta(`!!document.querySelector('#side [data-mod-azione="applica"]')`, 15000, 'anteprima');
  const ant = await B.testo('#opRis');
  if (!/neighbor/.test(ant) || !/frr\.conf/.test(ant)) throw new Error('anteprima senza le righe tolte: ' + ant.slice(0, 200));
  await clicSu('#side [data-mod-azione="applica"]');
  await B.aspetta(`/Fatto|applicat|scritt/i.test(document.querySelector('#side').innerText)`, 15000, 'applicato');
  const r = await B.js(`fetch('/api/lab?nome=${LAB}').then(x => x.json()).then(l => l.dispositivi.filter(d => d.riepilogo).map(d => d.riepilogo.neighbor.length + d.riepilogo.bgp_networks.length).reduce((a, b) => a + b, 0))`);
  if (r !== 0) throw new Error('restano ' + r + ' neighbor/network');
  await clicSu('[data-tab="topo"]');
  await clicSu('#bAnnulla');
  await B.aspetta(`!!document.querySelector('#side [data-mod-azione="applica"]')`, 10000, 'annulla');
  await clicSu('#side [data-mod-azione="applica"]');
  await B.aspetta(`/Annullato/.test(document.querySelector('#side').innerText)`, 10000, 'annullato');
  const dopo = await B.js(`fetch('/api/lab?nome=${LAB}').then(x => x.json()).then(l => l.dispositivi.filter(d => d.riepilogo).map(d => d.riepilogo.neighbor.length).reduce((a, b) => a + b, 0))`);
  if (!dopo) throw new Error('il lab non è tornato com\'era');
});

await passo('Togli il dispositivo: la casella di pulizia c\'è ed è attiva', async () => {
  await apri(LAB, 'topo');
  await clicSu('#bModifica');
  await clicSu('#svg g[data-id="d:as80r1"] circle');
  await clicSu('#side [data-gesto="disp"][data-azione="togli"]');
  await B.aspetta(`/Togli as80r1/.test(document.querySelector('#side').innerText)`, 10000, 'form');
  const t = await B.testo('#opForm');
  if (!/Togli anche quello che resta senza uso/.test(t)) throw new Error(t.slice(0, 300));
  const attiva = await B.js(`[...document.querySelectorAll('#opForm input[type=checkbox]')].map(c => c.checked)`);
  if (!attiva.length || !attiva.every(Boolean)) throw new Error('caselle: ' + JSON.stringify(attiva));
  await clicSu('#side [data-mod-azione="anteprima"]');
  await B.aspetta(`!!document.querySelector('#side [data-mod-azione="applica"]')`, 15000, 'anteprima');
  await clicSu('#side [data-mod-azione="indietro"]');
});

await passo('Togli una network BGP dal pannello del router', async () => {
  await apri(LAB, 'topo');
  await clicSu('#bModifica');
  await clicSu('#svg g[data-id="d:as20r1"] circle');
  await clicSu('#side [data-gesto="disp"][data-azione="network_togli"]');
  await B.aspetta(`/Togli una network BGP/.test(document.querySelector('#side').innerText)`, 10000, 'form');
  await clicSu('#side [data-mod-azione="anteprima"]');
  await B.aspetta(`!!document.querySelector('#side [data-mod-azione="applica"]')`, 15000, 'anteprima');
  if (!/network /.test(await B.testo('#opRis'))) throw new Error('anteprima senza la riga network');
  await clicSu('#side [data-mod-azione="indietro"]');
});

await passo('Diagnostica: "Applica i fix sicuri" corregge il refuso in blocco', async () => {
  await apri(FIX, 'topo');
  await clicSu('#bModifica');
  await clicSu('#svg g[data-id="d:as300r1"] circle');
  await clicSu('#side [data-gesto="disp"][data-azione="diagnosi"]');
  await B.aspetta(`/Diagnostica di as300r1/.test(document.querySelector('#side').innerText)`, 15000, 'menu della diagnostica');
  await clicVoce('fix sicuri');
  await B.aspetta(`!!document.querySelector('#side [data-mod-azione="applica"]')`, 15000, 'anteprima');
  if (!/neighbor 1\.0\.0\.9 remote-as 100/.test(await B.testo('#opRis'))) throw new Error('anteprima senza la riga corretta');
  await clicSu('#side [data-mod-azione="applica"]');
  await B.aspetta(`/Nessun problema trovato in as300r1/.test(document.querySelector('#side').innerText)`, 20000, 'diagnostica rifatta');
  await clicSu('#bAnnulla');
  await B.aspetta(`!!document.querySelector('#side [data-mod-azione="applica"]')`, 10000, 'annulla');
  await clicSu('#side [data-mod-azione="applica"]');
  await B.aspetta(`/Annullato/.test(document.querySelector('#side').innerText)`, 10000, 'annullato');
});

if (B.errori.length) passi.push({nome: 'errori nella pagina', ok: false, errore: B.errori.join(' | ')});
await B.chiudi();
const ko = passi.filter(p => !p.ok);
console.log(`${passi.length - ko.length}/${passi.length} passi ok`);
for (const p of ko) console.log('KO', p.nome, p.errore);
process.exit(ko.length ? 1 : 0);
