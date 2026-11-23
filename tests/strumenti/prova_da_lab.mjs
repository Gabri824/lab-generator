// Pilota di "Parti da un lab esistente" (fase 5.7) in Chromium senza finestra: nell'editor carica
// lift (copia), controlla bozza e riquadro del lab di partenza, rinomina un router dal pannello,
// guarda l'anteprima (le local-preference e il filtro restano, il filtro segue il router
// rinominato), crea lift2 e controlla i file su disco; poi una cartella che non è un lab e un data
// center senza IPv4 (rifiutati con la spiegazione). Usa COPIE dei lab (--base con lift e dc).
//
//   node tests/strumenti/prova_da_lab.mjs --url http://127.0.0.1:8795/ --base /tmp/labs [--shots cartella]
import fs from 'node:fs';
import path from 'node:path';
import { apriBrowser, pausa, trovaChrome } from './cdp.mjs';

const arg = (n, d) => { const i = process.argv.indexOf('--' + n); return i > 0 ? process.argv[i + 1] : d; };
const URL_GUI = arg('url', 'http://127.0.0.1:8795/'), BASE = arg('base'), SHOTS = arg('shots');
if (!BASE) { console.error('serve --base'); process.exit(2); }
const B = await apriBrowser(trovaChrome(arg('chrome')));
const passi = [];
async function passo(nome, f) {
  const t0 = Date.now();
  try { await f(); passi.push({nome, ok: true}); console.log(`ok   ${nome} (${((Date.now() - t0) / 1000).toFixed(1)} s)`); }
  catch (e) { passi.push({nome, ok: false, errore: e.message}); console.log(`KO   ${nome}: ${e.message}`); await B.scatta(SHOTS, 'ko-' + passi.length); }
}
const centro = sel => B.js(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return null; e.scrollIntoView({block: 'center'}); const r = e.getBoundingClientRect(); return {x: r.x + r.width / 2, y: r.y + r.height / 2}; })()`);
async function clicSu(sel) { const c = await centro(sel); if (!c) throw new Error('non trovato: ' + sel); await B.clic(c.x, c.y); }
async function scriviIn(sel, testo) { await clicSu(sel); await B.js(`document.querySelector(${JSON.stringify(sel)}).select()`); await B.scrivi(testo); }
const bozza = () => B.js('window.__bozzaEditor()');
const frr = (lab, r) => fs.readFileSync(path.join(BASE, lab, r, 'etc', 'frr', 'frr.conf'), 'utf8');

await B.cdp('Page.enable'); await B.cdp('Runtime.enable');

await passo('editor: lift caricato nella bozza', async () => {
  await B.cdp('Page.navigate', {url: `${URL_GUI}?r=${Date.now()}#nuovo`});
  await B.aspetta(`!!document.querySelector('#edDaLab') && !document.querySelector('#editor').hidden`, 20000, 'editor');
  await clicSu('#edDaLab');
  await B.aspetta(`!document.querySelector('#edDaLabSez').hidden && [...document.querySelectorAll('#edDaLabScelta option')].some(o => o.value === 'lift')`, 5000, 'elenco dei lab');
  await B.js(`document.querySelector('#edDaLabScelta').value = 'lift'`);
  await clicSu('#edDaLabCarica');
  await B.aspetta(`!document.querySelector('#edOrigine').hidden`, 20000, 'bozza caricata');
  const b = await bozza();
  if (b.dispositivi.length !== 8) throw new Error('dispositivi: ' + b.dispositivi.length);
  if (b.zone.filter(z => z.tipo === 'as').length < 6) throw new Error('riquadri AS: ' + b.zone.filter(z => z.tipo === 'as').length);
  const t = await B.testo('#edOrigine');
  if (!/Bozza partita da lift/.test(t) || /rappresenta in modo diverso/.test(t)) throw new Error('riquadro: ' + t.slice(0, 200));
  await B.scatta(SHOTS, 'da-lab-caricato');
});

await passo('rinomina as100r1 in as100r9 dal pannello', async () => {
  const id = (await bozza()).dispositivi.find(d => d.nome === 'as100r1').id;
  await clicSu(`#edSvg g.nodo[data-el="${id}"] circle`);
  await B.aspetta(`!!document.querySelector('#edPannello [data-chiave="nome:${id}"]')`, 5000, 'pannello del router');
  await scriviIn(`#edPannello [data-chiave="nome:${id}"]`, 'as100r9');
  await B.tasto('Tab');
  await pausa(400);
  if (!(await bozza()).dispositivi.some(d => d.nome === 'as100r9')) throw new Error('nome non cambiato');
});

await passo('anteprima: righe del lab di partenza conservate', async () => {
  await scriviIn('#edNome', 'lift2');
  await B.tasto('Tab');
  await clicSu('#edAnteprimaBtn');
  await B.aspetta(`!document.querySelector('#edAnteprima').hidden && /Dal lab di partenza/.test(document.querySelector('#edAnteprima').innerText)`, 20000, 'anteprima con unione');
  await clicSu('#edAntFile [data-file="as100r9/etc/frr/frr.conf"]');
  if (!/FILTER_IN_1_0_0_10/.test(await B.testo('#edAntTesto'))) throw new Error('il filtro non segue il router rinominato');
  await clicSu('#edAntFile [data-file="as300r1/etc/frr/frr.conf"]');
  if (!/set local-preference 150/.test(await B.testo('#edAntTesto'))) throw new Error('local-preference persa');
  await B.scatta(SHOTS, 'da-lab-anteprima');
});

await passo('crea lift2: file su disco con le policy, lift non toccato', async () => {
  const prima = fs.readFileSync(path.join(BASE, 'lift', 'as300r1', 'etc', 'frr', 'frr.conf'), 'utf8');
  await clicSu('#edCrea');
  await B.aspetta(`location.hash.includes('lab=lift2')`, 30000, 'lab creato e aperto');
  if (!/set local-preference 150/.test(frr('lift2', 'as300r1'))) throw new Error('local-preference non scritta');
  if (!/FILTER_IN_1_0_0_10/.test(frr('lift2', 'as100r9'))) throw new Error('filtro non scritto');
  if (fs.existsSync(path.join(BASE, 'lift2', 'as100r1.startup'))) throw new Error('as100r1 c\'è ancora');
  if (fs.readFileSync(path.join(BASE, 'lift', 'as300r1', 'etc', 'frr', 'frr.conf'), 'utf8') !== prima) throw new Error('lift è stato toccato');
});

await passo('cartella che non è un lab e data center senza IPv4: spiegazione', async () => {
  await B.cdp('Page.navigate', {url: `${URL_GUI}?r=${Date.now()}#nuovo`});
  await B.aspetta(`!!document.querySelector('#edDaLab') && !document.querySelector('#editor').hidden`, 20000, 'editor');
  await clicSu('#edDaLab');
  await B.js(`document.querySelector('#edDaLabScelta').value = 'lift'`);   // lab scelto nell'elenco: la cartella scritta deve vincere
  await scriviIn('#edDaLabCartella', path.join(BASE, 'non_esiste'));
  await clicSu('#edDaLabCarica');
  await B.aspetta(`/non c'è un lab.conf/.test(document.querySelector('#edDaLabEsito').innerText)`, 10000, 'errore cartella');
  await scriviIn('#edDaLabCartella', path.join(BASE, 'dc'));
  await clicSu('#edDaLabCarica');
  await B.aspetta(`/senza indirizzo IPv4/.test(document.querySelector('#edDaLabEsito').innerText)`, 10000, 'errore data center');
});

// 400: la cartella che non è un lab e il data center, rifiutati apposta
B.errori.splice(0, B.errori.length, ...B.errori.filter(e => !/status of 400/.test(e)));
if (B.errori.length) passi.push({nome: 'errori nella pagina', ok: false, errore: B.errori.join(' | ')});
await B.chiudi();
const ko = passi.filter(p => !p.ok);
console.log(`${passi.length - ko.length}/${passi.length} passi ok`);
for (const p of ko) console.log('KO', p.nome, p.errore);
process.exit(ko.length ? 1 : 0);
