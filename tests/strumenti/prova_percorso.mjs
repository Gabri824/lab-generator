// Pilota del "Percorso voluto" (fase 5.5b) in Chromium senza finestra, con mouse e tastiera veri:
// stairs senza policy (as4r2 -> as1r1 lungo H, F, B: tre MED proposti e applicati, poi "Verifica
// percorso" già compilata) e lift senza policy (as100r1 -> K senza il link B, filtro solo in AS100,
// una proposta applicata e una saltata); alla fine tutto annullato.
// Usa COPIE dei lab (--base), mai lab veri.
//
//   node tests/strumenti/prova_percorso.mjs --url http://127.0.0.1:8795/ --base /tmp/labs [--shots cartella]
import fs from 'node:fs';
import path from 'node:path';
import { apriBrowser, trovaChrome } from './cdp.mjs';

const arg = (n, d) => { const i = process.argv.indexOf('--' + n); return i > 0 ? process.argv[i + 1] : d; };
const URL_GUI = arg('url', 'http://127.0.0.1:8795/'), BASE = arg('base'), SHOTS = arg('shots');
if (!BASE) { console.error('serve --base (cartella con le copie stairs_mio e lift_mio)'); process.exit(2); }

const B = await apriBrowser(trovaChrome(arg('chrome')));
const passi = [];
async function passo(nome, f) {
  const t0 = Date.now();
  try { await f(); passi.push({nome, ok: true}); console.log(`ok   ${nome} (${((Date.now() - t0) / 1000).toFixed(1)} s)`); }
  catch (e) { passi.push({nome, ok: false, errore: e.message}); console.log(`KO   ${nome}: ${e.message}`); await B.scatta(SHOTS, 'ko-' + passi.length); }
}
const centro = sel => B.js(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return null; e.scrollIntoView({block: 'center'}); const r = e.getBoundingClientRect(); return {x: r.x + r.width / 2, y: r.y + r.height / 2}; })()`);
async function clicSu(sel) { const c = await centro(sel); if (!c) throw new Error('non trovato: ' + sel); await B.clic(c.x, c.y); }
const testoSide = () => B.js(`document.querySelector('#side').innerText`);
async function clicVoce(testo) {
  await B.aspetta(`[...document.querySelectorAll('#side [data-mod-voce]')].some(b => b.innerText.includes(${JSON.stringify(testo)}))`, 20000, 'voce ' + testo);
  const i = await B.js(`[...document.querySelectorAll('#side [data-mod-voce]')].find(b => b.innerText.includes(${JSON.stringify(testo)})).dataset.modVoce`);
  await clicSu(`#side [data-mod-voce="${i}"]`);
}
async function anteprimaEApplica(atteso) {
  await B.aspetta(`!!document.querySelector('#side [data-mod-azione="anteprima"]')`, 10000, 'pulsante Anteprima');
  await clicSu('#side [data-mod-azione="anteprima"]');
  await B.aspetta(`!!document.querySelector('#side [data-mod-azione="applica"]') || /koline/.test(document.querySelector('#opRis')?.innerHTML || '')`, 10000, 'anteprima');
  if (!await B.js(`!!document.querySelector('#side [data-mod-azione="applica"]')`)) throw new Error('anteprima rifiutata: ' + await B.testo('#opRis'));
  await clicSu('#side [data-mod-azione="applica"]');
  await B.aspetta(`document.querySelector('#side').innerText.includes(${JSON.stringify('Fatto: ' + atteso)})`, 15000, 'esito ' + atteso);
}
const frr = (lab, r) => fs.readFileSync(path.join(BASE, lab, r, 'etc', 'frr', 'frr.conf'), 'utf8');
const albero = lab => {
  const out = {};
  const giro = d => { for (const f of fs.readdirSync(d, {withFileTypes: true})) { if (f.name.startsWith('.') || f.name.endsWith('.xml')) continue;
    const p = path.join(d, f.name); if (f.isDirectory()) giro(p); else out[path.relative(BASE, p)] = fs.readFileSync(p, 'utf8'); } };
  giro(path.join(BASE, lab)); return out;
};
const iniziale = {stairs_mio: albero('stairs_mio'), lift_mio: albero('lift_mio')};
const router = n => `#svg g[data-id="d:${n}"] circle`, lan = n => `#svg g[data-mod="lan"][data-lan="${n}"] .pill-lan`;

async function apri(lab) {
  await B.cdp('Page.navigate', {url: `${URL_GUI}?giro=${Date.now()}#lab=${lab}&tab=topo`});   // pagina ricaricata da capo
  await B.aspetta(`!!document.querySelector('#svg g[data-id]') && document.querySelector('#bModifica')`, 20000, 'topologia ' + lab);
  await B.aspetta(`!!document.querySelector('#svg g[data-id="d:${lab === 'lift_mio' ? 'as100r1' : 'as4r2'}"]')`, 20000, 'disegno di ' + lab);
  if (await B.js(`document.querySelector('#bModifica').getAttribute('aria-pressed') !== 'true'`)) await clicSu('#bModifica');
  await B.aspetta(`/Modifica del lab/.test(document.querySelector('#side').innerText)`, 5000, 'pannello Modifica');
}
async function annullaTutto(lab) {
  for (let k = 0; k < 10; k++) {
    if (await B.js(`document.querySelector('#bAnnulla').disabled`)) break;
    await clicSu('#bAnnulla');
    await B.aspetta(`!!document.querySelector('#side [data-mod-azione="applica"]')`, 10000, 'anteprima dell\'annullamento');
    await clicSu('#side [data-mod-azione="applica"]');
    await B.aspetta(`/Annullato:/.test(document.querySelector('#side').innerText)`, 10000, 'annullato');
  }
  const ora = albero(lab);
  for (const [f, t] of Object.entries(iniziale[lab])) if (ora[f] !== t) throw new Error(`${f} diverso da prima`);
}

await B.cdp('Page.enable'); await B.cdp('Runtime.enable');

await passo('stairs: percorso as4r2 -> as1r1 lungo H, F, B cliccato sul disegno', async () => {
  await apri('stairs_mio');
  await clicSu('#side [data-gesto="percorso"]');
  await B.aspetta(`/clicca la sorgente/.test(document.querySelector('#side').innerText)`, 5000, 'pannello del percorso');
  for (const s of [router('as4r2'), lan('H'), lan('F'), lan('B'), router('as1r1')]) await clicSu(s);
  const t = await testoSide();
  for (const x of ['sorgente as4r2', 'LAN H', 'LAN F', 'LAN B', 'as1r1']) if (!t.includes(x)) throw new Error('manca il punto ' + x);
  if (!await B.js(`document.querySelectorAll('#svg .lk.ev').length >= 3`)) throw new Error('link non evidenziati');
  await B.scatta(SHOTS, 'percorso-punti');
  await clicSu('#side [data-mod-azione="anteprima"]');                    // Avanti
  await B.aspetta(`/Percorso voluto: AS4 → AS3 → AS2 → AS1/.test(document.querySelector('#side').innerText)`, 20000, 'proposte');
  if (!/Lab spento/.test(await testoSide())) throw new Error('modo "lab spento" non dichiarato');
});

await passo('stairs: tre MED proposti e applicati uno alla volta', async () => {
  await clicVoce('Vedi le proposte una alla volta (3)');
  await B.aspetta(`/Proposta 1 di 3/.test(document.querySelector('#side').innerText)`, 5000, 'proposta 1');
  await anteprimaEApplica('MED 20 verso 10.0.0.22 su as3r2');
  await B.aspetta(`/Proposta 2 di 3/.test(document.querySelector('#side').innerText)`, 10000, 'proposta 2 dopo l\'applica');
  await anteprimaEApplica('MED 20 verso 10.0.0.10 su as2r1');
  await B.aspetta(`/Proposta 3 di 3/.test(document.querySelector('#side').innerText)`, 10000, 'proposta 3');
  await anteprimaEApplica('MED 20 verso 10.0.0.6 su as1r2');
  await B.aspetta(`/Percorso voluto: fatto/.test(document.querySelector('#side').innerText)`, 10000, 'fine');
  for (const [r, ip] of [['as3r2', '10.0.0.22'], ['as2r1', '10.0.0.10'], ['as1r2', '10.0.0.6']])
    if (!new RegExp(`neighbor ${ip.replace(/\./g, '\\.')} route-map LOCALMED_OUT_\\S+ out`).test(frr('stairs_mio', r))) throw new Error('MED non scritto su ' + r);
});

await passo('stairs: "Verifica percorso" già compilata nella scheda Test', async () => {
  await clicVoce('Verifica percorso');
  await B.aspetta(`document.querySelector('#t-test') && !document.querySelector('#t-test').hidden`, 5000, 'scheda Test');
  const v = await B.js(`[document.querySelector('#pSrc').value, document.querySelector('#pDst').value, document.querySelector('#pAtt').value]`);
  if (JSON.stringify(v) !== JSON.stringify(['as4r2', '1.0.0.1', 'H F B'])) throw new Error('campi: ' + JSON.stringify(v));
});

await passo('stairs: annulla tutto, il lab torna com\'era', async () => {
  await apri('stairs_mio');
  await annullaTutto('stairs_mio');
});

await passo('lift: as100r1 -> K senza il link B, filtro solo in AS100; una applicata, una saltata', async () => {
  await apri('lift_mio');
  await clicSu('#side [data-gesto="percorso"]');
  for (const s of [router('as100r1'), lan('A'), lan('C'), lan('G')]) await clicSu(s);
  await clicSu('#svg g[data-id="l:K"] rect');
  await clicSu('#side [data-pv-vieta="100"]');
  await clicSu('#side [data-mod-azione="anteprima"]');                    // Avanti
  await B.aspetta(`/Percorso voluto: AS100 → AS200 → AS300 → AS400 → AS10/.test(document.querySelector('#side').innerText)`, 20000, 'proposte');
  await clicVoce('Vedi le proposte');
  await B.aspetta(`/Proposta 1 di/.test(document.querySelector('#side').innerText)`, 5000, 'proposta 1');
  if (!/Prefix-list su as100r1: scarta 10\.1\.0\.0\/24 da as300r1/.test(await testoSide())) throw new Error('la prima proposta non è il filtro su as100r1');
  await anteprimaEApplica('Prefix-list PL_as100r1_1_0_0_10_in su as100r1');
  await B.aspetta(`/Proposta 2 di/.test(document.querySelector('#side').innerText)`, 10000, 'proposta 2');
  await clicSu('#side [data-mod-azione="salta"]');
  await B.aspetta(`/Percorso voluto: fatto/.test(document.querySelector('#side').innerText)`, 10000, 'fine dopo Salta');
  if (!/ip prefix-list PL_as100r1_1_0_0_10_in deny 10\.1\.0\.0\/24/.test(frr('lift_mio', 'as100r1'))) throw new Error('filtro non scritto');
  if (/PREF_IN/.test(frr('lift_mio', 'as300r1'))) throw new Error('la proposta saltata è stata scritta');
  await annullaTutto('lift_mio');
});

await passo('modalità Modifica spenta', async () => {
  await clicSu('#bModifica');
  await B.aspetta(`document.querySelector('#bModifica').getAttribute('aria-pressed') === 'false'`, 5000, 'spenta');
});

if (B.errori.length) passi.push({nome: 'errori nella pagina', ok: false, errore: B.errori.join(' | ')});
await B.chiudi();
const ko = passi.filter(p => !p.ok);
console.log(`${passi.length - ko.length}/${passi.length} passi ok`);
for (const p of ko) console.log('KO', p.nome, p.errore);
process.exit(ko.length ? 1 : 0);
