// Pilota dei livelli del disegno (fase 5.6) in Chromium senza finestra: interruttori (accesi
// all'apertura, spenti e riaccesi, ricordati dopo il ricaricamento), sigle delle policy di lift,
// sessione BGP sbagliata segnata, link eBGP marcati, etichette senza indirizzi, clic su una sigla in
// modalità Modifica (apre la policy di quel neighbor), configurazione in breve nel pannello, albero
// DNS e resolver di tennis. Usa COPIE dei lab (--base con lift_rotto e tennis_test).
//
//   node tests/strumenti/prova_livelli.mjs --url http://127.0.0.1:8795/ --base /tmp/labs [--shots cartella]
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
const conta = sel => B.js(`document.querySelectorAll(${JSON.stringify(sel)}).length`);
const acceso = id => B.js(`document.querySelector('#livelli [data-livello="${id}"]').getAttribute('aria-checked') === 'true'`);
async function interruttore(id, voglio) { if (await acceso(id) !== voglio) await clicSu(`#livelli [data-livello="${id}"]`); await pausa(200); }
async function apri(lab) {
  await B.cdp('Page.navigate', {url: `${URL_GUI}?giro=${Date.now()}#lab=${lab}&tab=topo`});
  await B.aspetta(`!!document.querySelector('#svg g[data-id]') && !!document.querySelector('#livelli [data-livello]')`, 20000, 'topologia ' + lab);
  await pausa(500);
}

await B.cdp('Page.enable'); await B.cdp('Runtime.enable');

await passo('livelli accesi all\'apertura: tutti tranne Sessioni BGP e DNS', async () => {
  await apri('lift_rotto');
  const stato = await B.js(`Object.fromEntries([...document.querySelectorAll('#livelli [data-livello]')].map(b => [b.dataset.livello, b.getAttribute('aria-checked')]))`);
  const atteso = {indirizzi: 'true', costi: 'true', sessioni: 'false', policy: 'true', segni: 'true', dns: 'false', avvisi: 'true'};
  if (JSON.stringify(stato) !== JSON.stringify(atteso)) throw new Error(JSON.stringify(stato));
});

await passo('Policy: sigle di lift sul disegno, spente e riaccese', async () => {
  const testi = await B.js(`[...document.querySelectorAll('#svg g.pol text')].map(t => t.textContent).sort().join('|')`);
  if (testi !== 'LP 150 in|LP 150 in|filtro in') throw new Error('sigle: ' + testi);
  await interruttore('policy', false);
  if (await conta('#svg g.pol')) throw new Error('le sigle restano con il livello spento');
  await interruttore('policy', true);
  if (await conta('#svg g.pol') !== 3) throw new Error('le sigle non tornano');
});

await passo('Sessioni BGP: link eBGP marcati e la sessione sbagliata segnata', async () => {
  await interruttore('sessioni', true);
  if (await conta('#svg .lk.bgp') < 6) throw new Error('link eBGP non marcati: ' + await conta('#svg .lk.bgp'));
  if (await conta('#svg .ses.ko') !== 1) throw new Error('sessioni sbagliate: ' + await conta('#svg .ses.ko'));
  const t = await B.js(`document.querySelector('#svg .ses.ko title').textContent`);
  if (!/remote-as 301/.test(t)) throw new Error('spiegazione: ' + t);
  await B.scatta(SHOTS, 'livelli-lift');
});

await passo('Indirizzi spenti: niente etichette delle interfacce; scelta ricordata', async () => {
  await interruttore('indirizzi', false);
  if (await conta('#svg [data-mod="if"]')) throw new Error('etichette ancora visibili');
  await apri('lift_rotto');
  if (await acceso('indirizzi') || !await acceso('sessioni')) throw new Error('scelta dei livelli non ricordata');
  await interruttore('indirizzi', true);
});

await passo('Pannello del router: configurazione in breve', async () => {
  await clicSu('#svg g[data-id="d:as300r1"] circle');
  await B.aspetta(`/Configurazione in breve/.test(document.querySelector('#side').innerText)`, 5000, 'riepilogo nel pannello');
  const t = await B.js(`document.querySelector('#side details').textContent`);
  if (!/local-preference 150/.test(t)) throw new Error('policy non nel riepilogo: ' + t.slice(0, 200));
});

await passo('Modifica: clic sulla sigla LP 150 apre la policy di quel neighbor', async () => {
  await clicSu('#bModifica');
  await B.aspetta(`document.querySelector('#bModifica').getAttribute('aria-pressed') === 'true'`, 5000, 'modalità Modifica');
  await clicSu('#svg g.pol[data-dev="as300r1"][data-ip="1.0.0.14"] rect');
  await B.aspetta(`/Policy su as300r1 verso 1.0.0.14/.test(document.querySelector('#side').innerText)`, 10000, 'menu della policy');
  await clicSu('#bModifica');
});

await passo('DNS: albero delle deleghe e resolver di tennis', async () => {
  await apri('tennis_test');
  await interruttore('dns', true);
  if (await conta('#svg .dnsl') < 1) throw new Error('nessuna delega disegnata');
  const zone = await B.js(`[...document.querySelectorAll('#svg .dnst')].map(t => t.textContent).join(' ')`);
  if (!/\bcom\b/.test(zone)) throw new Error('zone: ' + zone);
  if (!await B.js(`[...document.querySelectorAll('#svg text.ts')].some(t => /^ns: /.test(t.textContent))`)) throw new Error('resolver non scritto');
  await B.scatta(SHOTS, 'livelli-tennis');
});

if (B.errori.length) passi.push({nome: 'errori nella pagina', ok: false, errore: B.errori.join(' | ')});
await B.chiudi();
const ko = passi.filter(p => !p.ok);
console.log(`${passi.length - ko.length}/${passi.length} passi ok`);
for (const p of ko) console.log('KO', p.nome, p.errore);
process.exit(ko.length ? 1 : 0);
