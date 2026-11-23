// Ingombro della pagina (fase 7): ogni scheda, la modalità Modifica e l'editor a 1440, 1024, 768 e
// 390 px di larghezza. Controlla che la pagina non scorra in orizzontale e che nessun elemento
// visibile esca a destra dal suo riquadro (card, pannello, barra); fa una schermata per caso.
//
//   node tests/strumenti/prova_ingombro.mjs --url http://127.0.0.1:8795/ --lab tennis [--shots cartella]
import { apriBrowser, pausa, trovaChrome } from './cdp.mjs';

const arg = (n, d) => { const i = process.argv.indexOf('--' + n); return i > 0 ? process.argv[i + 1] : d; };
const URL_GUI = arg('url', 'http://127.0.0.1:8795/'), LAB = arg('lab', 'tennis'), SHOTS = arg('shots');
const LARGHEZZE = [1440, 1024, 768, 390];
const B = await apriBrowser(trovaChrome(arg('chrome')));
await B.cdp('Page.enable'); await B.cdp('Runtime.enable');

// elementi che escono a destra dal contenitore più vicino che non scorre (o dalla finestra)
const CONTROLLO = `(() => {
  const vw = document.documentElement.clientWidth, out = [];
  const scorre = el => { const s = getComputedStyle(el); return /(auto|scroll|hidden)/.test(s.overflowX) && el.scrollWidth > el.clientWidth + 1; };
  if (document.documentElement.scrollWidth > vw + 1) out.push('pagina: scorre in orizzontale di ' + (document.documentElement.scrollWidth - vw) + ' px');
  for (const el of document.querySelectorAll('button, input, select, textarea, label, h1, h2, h3, .badge, .riga, .btns, table, svg, pre, code')) {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height || getComputedStyle(el).visibility === 'hidden') continue;
    let c = el.parentElement;
    while (c && c !== document.body && !c.matches('.card, .side, .toolbar, aside, header, section, .ed-bozza, .ed-barra, #side, dialog')) c = c.parentElement;
    if (!c || c === document.body) { if (r.right > vw + 1) out.push(el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + ' esce dalla finestra'); continue; }
    let s = el.parentElement, dentroScroll = false;
    while (s && s !== c) { if (scorre(s)) { dentroScroll = true; break; } s = s.parentElement; }
    if (dentroScroll || scorre(c)) continue;
    const cr = c.getBoundingClientRect();
    if (r.right > cr.right + 2) out.push(el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (el.className && typeof el.className === 'string' ? '.' + el.className.split(' ')[0] : '') + ' "' + (el.innerText || el.value || '').trim().slice(0, 30) + '" esce di ' + Math.round(r.right - cr.right) + ' px da ' + c.tagName.toLowerCase() + (c.id ? '#' + c.id : '') + '.' + (c.className || '').toString().split(' ')[0]);
  }
  return [...new Set(out)].slice(0, 12);
})()`;

const casi = [
  ['topologia', `#lab=${LAB}&tab=topo`, null],
  ['modifica', `#lab=${LAB}&tab=topo`, `document.querySelector('#bModifica').click()`],
  ['riepilogo', `#lab=${LAB}&tab=riep`, null],
  ['interfacce', `#lab=${LAB}&tab=intf`, null],
  ['test', `#lab=${LAB}&tab=test`, null],
  ['archivio', `#lab=${LAB}&tab=arch`, null],
  ['registro', `#lab=${LAB}&tab=reg`, null],
  ['editor', '#nuovo', null],
];
let problemi = 0;
for (const w of LARGHEZZE) {
  await B.cdp('Emulation.setDeviceMetricsOverride', {width: w, height: 900, deviceScaleFactor: 1, mobile: w < 500});
  for (const [nome, hash, poi] of casi) {
    await B.cdp('Page.navigate', {url: `${URL_GUI}?r=${Date.now()}${hash}`});
    await pausa(1800);
    if (poi) { await B.js(poi); await pausa(600); }
    const r = await B.js(CONTROLLO);
    await B.scatta(SHOTS, `ingombro-${w}-${nome}`);
    if (r.length) { problemi += r.length; console.log(`KO   ${w} px ${nome}:\n       ` + r.join('\n       ')); }
    else console.log(`ok   ${w} px ${nome}`);
  }
}
if (B.errori.length) console.log('errori nella pagina: ' + B.errori.join(' | '));
await B.chiudi();
console.log(problemi ? `${problemi} problemi di ingombro` : 'nessun problema di ingombro');
process.exit(problemi ? 1 : 0);
