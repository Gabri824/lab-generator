#!/usr/bin/env node
// tests/strumenti/prova_editor.mjs
// Prova dell'editor grafico in un Chromium senza finestra, con mouse e tastiera veri: disegna il lab
// di tests/bozze/ospf_abr.json (senza le zone, che arrivano nella 4.3), scrive subnet e IP nel
// pannello e controlla che la bozza dia lo stesso modello. Prova anche trascinamento con la
// griglia, selezione ad area, eliminazione, terzo dispositivo su un link diretto, annulla/ripeti,
// e fa le foto a 1440, 1024 e 768 in chiaro e scuro.
//
//   node tests/strumenti/prova_editor.mjs --url http://127.0.0.1:8791/ [--shots cartella] [--out esito.json]
//        [--base cartella dei lab del server]   (per controllare anche i file scritti su disco)
// Il server deve essere avviato (anche senza lab). Esce con 1 se qualcosa non torna.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { converti } from '../../src/gui/static/js/editor/bozza.js';
import { apriBrowser, pausa, trovaChrome } from './cdp.mjs';

const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i > 0 ? process.argv[i + 1] : d; };
const URL_GUI = arg('url', 'http://127.0.0.1:8765/');
const SHOTS = arg('shots');
const OUT = arg('out');
const BASE = arg('base');
const QUI = path.dirname(fileURLToPath(import.meta.url));

const B = await apriBrowser(trovaChrome(arg('chrome')));
const { cdp, js, aspetta, scrivi, clic, trascina, errori } = B;
// i tasti degli strumenti (R, L, A...) l'editor li ignora se il focus è in un campo del pannello
// (lì servono a scrivere): come chi clicca sul foglio prima di disegnare, il pilota toglie il focus
async function tasto(k, opz = {}) {
  if (k.length === 1 && !opz.ctrl) await js('document.activeElement && document.activeElement.blur && document.activeElement.blur()');
  await B.tasto(k, opz);
}
const esito = { passi: {}, errori };
let falliti = 0;
async function passo(nome, f) {
  process.stdout.write(`- ${nome} ... `);
  const t0 = Date.now();
  try { esito.passi[nome] = (await f()) ?? 'ok'; console.log(`ok (${((Date.now() - t0) / 1000).toFixed(1)} s)`); }
  catch (e) { falliti++; esito.passi[nome] = { errore: String(e.message || e) }; console.log('ERRORE: ' + (e.message || e)); }
}

// punto del disegno -> punto dello schermo
const schermo = async (x, y) => js(`(() => { const p = new DOMPoint(${x}, ${y}).matrixTransform(document.querySelector('#edSvg').getScreenCTM()); return [p.x, p.y]; })()`);
const clicSu = async (p, opz) => { const [x, y] = await schermo(p.x, p.y); await clic(x, y, opz); await pausa(60); };
const bozza = () => js('window.__bozzaEditor()');
const meta = (a, b) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
// file che il server genererebbe (anteprima_lab) = file del wizard salvati nei test?
const RE_SERIAL = /\b\d{10}(\s*;\s*serial)/g;
const normalizza = t => t.replace(RE_SERIAL, 'AAAAMMGGNN$1');
function albero(cartella, base = cartella, out = {}) {
  for (const f of fs.readdirSync(cartella).sort()) {
    const p = path.join(cartella, f);
    if (fs.statSync(p).isDirectory()) albero(p, base, out);
    else out[path.relative(base, p).split(path.sep).join('/')] = normalizza(fs.readFileSync(p, 'utf8'));
  }
  return out;
}
async function stessiFileDelWizard(scenario, modello) {
  const corpo = JSON.stringify({ azione: 'anteprima_lab', nome: scenario, modello });
  const r = await js(`fetch('/api/azione', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Lab-Gen': '1'}, body: ${JSON.stringify(corpo)}}).then(r => r.json())`);
  assert.ok(r.creabile, 'il lab non si genera: ' + JSON.stringify(r.errori || r.errore));
  const fatti = Object.fromEntries(r.file.map(f => [f.file, normalizza(f.testo)]));
  assert.deepEqual(fatti, albero(path.join(QUI, '..', 'attesi', 'scenari', scenario)), 'file diversi da quelli del wizard');
  return Object.keys(fatti).length;
}
// campi del pannello per chiave esatta
async function scriviChiave(chiave, valore) {
  await js(`(() => { const e = document.querySelector('#edPannello [data-chiave="${chiave}"]'); e.focus(); e.select && e.select(); })()`);
  await scrivi(valore);
  await tasto('Tab');
  await pausa(150);
}
async function scegliChiave(chiave, valore) {
  await js(`(() => { const e = document.querySelector('#edPannello [data-chiave="${chiave}"]'); e.value = ${JSON.stringify(valore)}; e.dispatchEvent(new Event('change', {bubbles: true})); })()`);
  await pausa(150);
}
const premiPannello = async sel => { await js(`document.querySelector('#edPannello ${sel}').click()`); await pausa(120); };

async function scriviCampo(prefisso, valore) {
  // il testo che c'è già (es. il nome dato alla creazione) viene sostituito, non allungato
  await js(`(() => { const e = document.querySelector('#edPannello [data-chiave^="${prefisso}"]'); e.focus(); e.select && e.select(); })()`);
  await scrivi(valore);
  await tasto('Tab');
  await pausa(150);
}

// posizioni (multipli di 20: con la griglia restano uguali)
const R1 = { x: -300, y: -100 }, R2 = { x: -100, y: -100 }, R3 = { x: 100, y: -100 }, HOST = { x: 100, y: 180 }, LANC = { x: 100, y: 40 };

try {
  await cdp('Page.navigate', { url: new URL('/#nuovo', URL_GUI).href });
  await aspetta(`!document.querySelector('#editor').hidden && !!document.querySelector('#edStrumenti button')`, 20000, 'apertura dell\'editor');

  await passo('disegno con mouse e tastiera', async () => {
    await tasto('r'); await clicSu(R1); await clicSu(R2); await clicSu(R3);
    await tasto('h'); await clicSu(HOST);
    await tasto('l'); await clicSu(R1); await clicSu(R2); await clicSu(R2); await clicSu(R3);
    await tasto('n'); await clicSu(LANC);
    await tasto('l'); await clicSu(R3); await clicSu(LANC); await clicSu(HOST); await clicSu(LANC);
    await tasto('Escape');
    const b = await bozza();
    assert.equal(b.dispositivi.length, 4);
    assert.equal(b.lan.length, 3);
    assert.equal(b.collegamenti.length, 6);
    return { dispositivi: b.dispositivi.length, lan: b.lan.length, collegamenti: b.collegamenti.length };
  });

  await passo('subnet e IP dal pannello', async () => {
    await clicSu(meta(R1, R2));
    await aspetta(`document.querySelector('#edPannello').innerText.includes('LAN A')`, 5000, 'pannello della LAN A');
    await scriviCampo('subnet:', '10.0.0.0/30');
    await clicSu(meta(R2, R3));
    await aspetta(`document.querySelector('#edPannello').innerText.includes('LAN B')`, 5000, 'pannello della LAN B');
    await scriviCampo('subnet:', '10.1.0.0/30');
    await clicSu(LANC);
    await aspetta(`document.querySelector('#edPannello').innerText.includes('LAN C')`, 5000, 'pannello della LAN C');
    await scriviCampo('subnet:', '10.1.1.0/24');
    await clicSu(HOST);
    await aspetta(`document.querySelector('#edPannello').innerText.includes('host1')`, 5000, 'pannello di host1');
    await scriviCampo('ip:', '10.1.1.10/24');
    await js('document.activeElement.blur()');
    await B.scatta(SHOTS, 'editor-disegno');
  });

  await passo('stesso modello della bozza di riferimento (senza zone)', async () => {
    const atteso = JSON.parse(fs.readFileSync(path.join(QUI, '..', 'bozze', 'ospf_abr.json'), 'utf8'));
    atteso.zone = [];
    const fatto = converti(await bozza());
    assert.deepEqual(fatto.problemi.filter(p => p.gravita === 'errore'), []);
    assert.deepEqual(fatto.modello, converti(atteso).modello);
    return { router: Object.keys(fatto.modello.routers), lan: Object.values(fatto.nomiLan) };
  });

    await passo('zone disegnate trascinando (aree OSPF, router di confine)', async () => {
    const tira = async (a, b2) => { const [x0, y0] = await schermo(a.x, a.y), [x1, y1] = await schermo(b2.x, b2.y); await trascina(x0, y0, x1, y1); await pausa(100); };
    await tasto('o'); await tira({ x: -360, y: -140 }, { x: -140, y: -60 });
    assert.equal(await js(`document.activeElement.dataset.chiave?.startsWith('valore:') && document.activeElement.value`), '0.0.0.0', 'prima area: 0.0.0.0 già scritto e pronto');
    await js('document.activeElement.blur()');
    await tasto('o'); await tira({ x: -40, y: -160 }, { x: 240, y: 120 });
    assert.equal(await js(`document.activeElement.dataset.chiave?.startsWith('valore:') && document.activeElement.value`), '', 'seconda area: da scrivere');
    await scrivi('1.1.1.1'); await tasto('Tab'); await pausa(150);
    await js(`document.querySelector('#edPannello [data-chiave^="stub:"]').click()`); await pausa(150);
    await js('document.activeElement.blur()');
    const atteso = JSON.parse(fs.readFileSync(path.join(QUI, '..', 'bozze', 'ospf_abr.json'), 'utf8'));
    const fatto = converti(await bozza());
    assert.deepEqual(fatto.problemi.filter(p => p.gravita === 'errore'), []);
    assert.deepEqual(fatto.modello, converti(atteso).modello, 'stesso modello della bozza di riferimento, zone comprese');
    assert.equal(await js(`document.querySelectorAll('#edSvg .ed-abr').length`), 1, 'r2 segnato ABR');
    await B.scatta(SHOTS, 'editor-zone');
    return { abr: fatto.abr.map(id => fatto.nomi[id]), file_uguali_al_wizard: await stessiFileDelWizard('ospf_abr', fatto.modello) };
  });

  await passo('ridimensionare una zona dall\'angolo', async () => {
    const prima = await bozza(), z = prima.zone[1];
    await clicSu({ x: z.x + 30, y: z.y + 16 });
    assert.equal(await js(`document.querySelectorAll('#edSvg .ed-maniglia').length`), 4, 'quattro maniglie');
    const [x0, y0] = await schermo(z.x + z.w, z.y + z.h), [x1, y1] = await schermo(z.x + z.w + 60, z.y + z.h + 80);
    await trascina(x0, y0, x1, y1);
    const dopo = (await bozza()).zone[1];
    assert.deepEqual([dopo.x, dopo.y, dopo.w, dopo.h], [z.x, z.y, z.w + 60, z.h + 80]);
    await tasto('z', { ctrl: true });
    assert.deepEqual(await bozza(), prima);
    await tasto('Escape');
  });

const finale = await bozza();
let conTerzo = null;

  await passo('trascinamento con la griglia', async () => {
    const [x0, y0] = await schermo(R1.x, R1.y);
    const [x1, y1] = await schermo(R1.x + 37, R1.y + 23);
    await trascina(x0, y0, x1, y1);
    const d = (await bozza()).dispositivi[0];
    assert.deepEqual([d.x, d.y], [-260, -80]);
    await tasto('z', { ctrl: true });
    assert.deepEqual((await bozza()).dispositivi[0].x, R1.x, 'un trascinamento si annulla in un passo');
  });

  await passo('selezione ad area con Maiusc', async () => {
    await tasto('Escape');
    assert.equal(await js(`document.querySelector('#edPannello').innerText.includes('Tasti')`), true, 'Esc toglie la selezione');
    const [x0, y0] = await schermo(-160, -160), [x1, y1] = await schermo(160, -40);
    await trascina(x0, y0, x1, y1, { shift: true });
    await aspetta(`document.querySelector('#edPannello').innerText.includes('2 elementi selezionati')`, 5000, 'due router selezionati');
    await tasto('Escape');
  });

  await passo('eliminare e annullare', async () => {
    await clicSu(HOST);
    await tasto('Delete');
    let b = await bozza();
    assert.equal(b.dispositivi.length, 3);
    assert.equal(b.collegamenti.length, 5);
    await tasto('z', { ctrl: true });
    b = await bozza();
    assert.deepEqual(b, finale);
  });

  await passo('clic sull\'etichetta di un\'interfaccia: vale come il suo link', async () => {
    await clicSu({ x: R2.x + 52, y: R2.y });
    await aspetta(`document.querySelector('#edPannello').innerText.includes('LAN B')`, 5000, 'pannello della LAN B');
    await tasto('Escape');
  });

  await passo('terzo dispositivo sul link diretto', async () => {
    const R4 = { x: -100, y: 120 };
    await tasto('r'); await clicSu(R4);
    await tasto('l'); await clicSu(R4); await clicSu({ x: R2.x + 0.25 * (R3.x - R2.x), y: R2.y });
    await tasto('Escape');
    const b = await bozza();
    const lanB = b.lan.find(l => l.subnet === '10.1.0.0/30');
    assert.equal(lanB.punto, false, 'il link diretto è diventato un nodo LAN');
    assert.equal(b.collegamenti.filter(c => c.lan === lanB.id).length, 3);
    await B.scatta(SHOTS, 'editor-terzo');
    conTerzo = b;
    await tasto('z', { ctrl: true }); await tasto('z', { ctrl: true });
    assert.deepEqual(await bozza(), finale);
  });

  await passo('annulla tutto e ripeti tutto', async () => {
    for (let i = 0; i < 40; i++) await tasto('z', { ctrl: true });
    assert.equal((await bozza()).dispositivi.length, 0);
    // ripeti rifà anche le due azioni del passo prima, annullate ma ancora nella pila dei "ripeti"
    for (let i = 0; i < 40; i++) await tasto('y', { ctrl: true });
    assert.deepEqual(await bozza(), conTerzo);
    await tasto('z', { ctrl: true }); await tasto('z', { ctrl: true });
    assert.deepEqual(await bozza(), finale);
  });

  await passo('secondo lab: due AS e un\'area, nomi scritti nel pannello (bgp_ibgp_due_as)', async () => {
    // foglio nuovo: la bozza si salva nel browser, quindi non basta ricaricare la pagina
    await js(`document.querySelector('#edNuova').click()`);      // conferma accettata dal pilota
    await aspetta(`window.__bozzaEditor().dispositivi.length === 0 && window.__bozzaEditor().zone.length === 0`, 5000, 'foglio vuoto');
    const tira = async (a, b2) => { const [x0, y0] = await schermo(a.x, a.y), [x1, y1] = await schermo(b2.x, b2.y); await trascina(x0, y0, x1, y1); await pausa(100); };
    const A1 = { x: -300, y: -100 }, A2 = { x: -300, y: 100 }, A3 = { x: 100, y: -100 }, PC = { x: 100, y: 180 }, LA = { x: -380, y: 0 }, LY = { x: 100, y: 60 };
    await tasto('n'); await clicSu(LA);
    await tasto('r'); await clicSu(A1); await clicSu(A2); await clicSu(A3);
    await tasto('h'); await clicSu(PC);
    await tasto('l'); await clicSu(A1); await clicSu(LA); await clicSu(A1); await clicSu(A3); await clicSu(A2); await clicSu(LA);
    await tasto('n'); await clicSu(LY);
    await tasto('l'); await clicSu(A3); await clicSu(LY); await clicSu(PC); await clicSu(LY);
    await tasto('Escape');
    for (const [p, nome] of [[A1, 'r1'], [A2, 'r2'], [A3, 'r3'], [PC, 'pc1']]) { await clicSu(p); await scriviCampo('nome:', nome); }
    await clicSu(PC); await scriviCampo('ip:', '200.0.0.10/24');
    for (const [p, nome, rete] of [[LA, 'A', '10.0.0.0/24'], [meta(A1, A3), 'X', '192.168.0.0/30'], [LY, 'Y', '200.0.0.0/24']]) {
      await clicSu(p); await scriviCampo('nome:', nome); await scriviCampo('subnet:', rete);
    }
    await js('document.activeElement.blur()');
    await tasto('a'); await tira({ x: -420, y: -160 }, { x: -220, y: 160 }); await scrivi('100'); await tasto('Tab'); await pausa(150);
    // r2 è interno ma in questo lab ha BGP (iBGP): BGP su tutti i router dell'AS 100
    await js(`(() => { const e = document.querySelector('#edPannello [data-chiave^="bgpzona:"]'); e.value = 'tutti'; e.dispatchEvent(new Event('change', {bubbles: true})); })()`); await pausa(150);
    await js('document.activeElement && document.activeElement.blur()');
    await tasto('a'); await tira({ x: 20, y: -160 }, { x: 200, y: -20 }); await scrivi('200'); await tasto('Tab'); await pausa(150);
    await tasto('o'); await tira({ x: -420, y: -40 }, { x: -340, y: 40 }); await js('document.activeElement.blur()');
    await clicSu(A1);
    await aspetta(`!!document.querySelector('#edPannello [data-chiave^="redistribuisci:"]')`, 5000, 'casella della ridistribuzione di r1');
    await premiPannello('[data-chiave^="redistribuisci:"]');
    await tasto('Escape');
    const atteso = JSON.parse(fs.readFileSync(path.join(QUI, '..', 'bozze', 'bgp_ibgp_due_as.json'), 'utf8'));
    const fatto = converti(await bozza());
    assert.deepEqual(fatto.problemi.filter(p => p.gravita === 'errore'), []);
    assert.deepEqual(fatto.modello, converti(atteso).modello);
    await B.scatta(SHOTS, 'editor-due-as');
    return { router: Object.fromEntries(Object.entries(fatto.modello.routers).map(([n, r]) => [n, r.protocols.join('+') + (r.asn ? ' AS' + r.asn : '')])),
      file_uguali_al_wizard: await stessiFileDelWizard('bgp_ibgp_due_as', fatto.modello) };
  });

  await passo('terzo lab: DNS con root, autoritativo e resolver, host e server web (dns_root_auth_resolver)', async () => {
    // foglio nuovo: la bozza si salva nel browser, quindi non basta ricaricare la pagina
    await js(`document.querySelector('#edNuova').click()`);      // conferma accettata dal pilota
    await aspetta(`window.__bozzaEditor().dispositivi.length === 0 && window.__bozzaEditor().zone.length === 0`, 5000, 'foglio vuoto');
    const tira = async (a, b2) => { const [x0, y0] = await schermo(a.x, a.y), [x1, y1] = await schermo(b2.x, b2.y); await trascina(x0, y0, x1, y1); await pausa(100); };
    const R = { x: 0, y: 0 }, H = { x: -340, y: 0 }, W = { x: -100, y: 200 }, ROOT = { x: 340, y: -100 }, COM = { x: 340, y: 100 }, RES = { x: 100, y: 200 };
    const LA = { x: -200, y: 0 }, LB = { x: 0, y: 140 }, LZ = { x: 200, y: 0 };
    await tasto('r'); await clicSu(R);
    await tasto('h'); await clicSu(H);
    await tasto('w'); await clicSu(W);
    await tasto('d'); await clicSu(ROOT); await clicSu(COM); await clicSu(RES);
    await tasto('n'); await clicSu(LA); await clicSu(LB); await clicSu(LZ);
    await tasto('l');
    for (const [a, b2] of [[R, LA], [R, LB], [R, LZ], [H, LA], [W, LB], [ROOT, LZ], [COM, LZ], [RES, LB]]) { await clicSu(a); await clicSu(b2); }
    await tasto('Escape');
    const id = (await bozza()).dispositivi.map(d => d.id);       // r1, host1, www1, root, dns_com, resolver
    await clicSu(LZ); await scriviCampo('nome:', 'Z');
    for (const [p, ip] of [[H, '10.0.0.10/24'], [W, '10.0.1.80/24'], [ROOT, '10.0.2.2/24'], [COM, '10.0.2.3/24'], [RES, '10.0.1.53/24']]) { await clicSu(p); await scriviCampo('ip:', ip); }
    // root: master per '.' e delega di com
    await clicSu(ROOT); await scriviChiave(`nome:${id[3]}`, 'root');
    await scegliChiave(`root_type:${id[3]}`, 'master');
    await premiPannello('[data-elenco="delega"][data-op="aggiungi"]');
    await scriviChiave(`delega:${id[3]}:0:zone`, 'com'); await scriviChiave(`delega:${id[3]}:0:ns`, 'dns.com'); await scriviChiave(`delega:${id[3]}:0:ip`, '10.0.2.3');
    // autoritativo per com: www A, web CNAME, @ NS con glue; DNSSEC disattivata
    await clicSu(COM); await scriviChiave(`nome:${id[4]}`, 'dns_com');
    await premiPannello('[data-elenco="zona"][data-op="aggiungi"]');
    await scriviChiave(`zona:${id[4]}:0`, 'com');
    for (const [k, [n, t, v, e]] of [['www', 'A', '10.0.1.80', ''], ['web', 'CNAME', 'www', ''], ['@', 'NS', 'dns.com.', '10.0.2.3']].entries()) {
      await premiPannello('[data-elenco="record"][data-op="aggiungi"]');
      await scriviChiave(`record:${id[4]}:0:${k}:nome`, n);
      if (t !== 'A') await scegliChiave(`record:${id[4]}:0:${k}:tipo`, t);
      await scriviChiave(`record:${id[4]}:0:${k}:valore`, v);
      if (e) await scriviChiave(`record:${id[4]}:0:${k}:extra`, e);
    }
    await premiPannello(`[data-chiave="dnssec:${id[4]}"]`);
    // resolver: ricorsione per tutti, DNSSEC disattivata
    await clicSu(RES); await scriviChiave(`nome:${id[5]}`, 'resolver');
    await premiPannello(`[data-chiave="ricorsione:${id[5]}"]`);
    await premiPannello(`[data-chiave="dnssec:${id[5]}"]`);
    // router in una zona RIP; resolver finale del lab
    await tasto('i'); await tira({ x: -60, y: -60 }, { x: 60, y: 60 });
    await tasto('Escape'); await tasto('Escape');
    await scegliChiave('resolver:lab', id[5]);
    await js('document.activeElement && document.activeElement.blur()');
    const atteso = JSON.parse(fs.readFileSync(path.join(QUI, '..', 'bozze', 'dns_root_auth_resolver.json'), 'utf8'));
    const fatto = converti(await bozza());
    assert.deepEqual(fatto.problemi.filter(p => p.gravita === 'errore'), []);
    assert.deepEqual(fatto.modello, converti(atteso).modello);
    await clicSu(COM); await pausa(300);
    await B.scatta(SHOTS, 'editor-dns');
    return { file_uguali_al_wizard: await stessiFileDelWizard('dns_root_auth_resolver', fatto.modello), resolver: fatto.modello.resolver };
  });

  await passo('controlli del motore dal vivo: un gateway sbagliato compare e poi sparisce', async () => {
    const H = { x: -340, y: 0 };
    await clicSu(H);
    const id = (await bozza()).dispositivi[1].id;
    await scriviChiave(`gateway:${id}`, '10.9.9.9');
    await aspetta(`!!document.querySelector('#edPannello .ed-errore-motore') && document.querySelectorAll('#edSvg .ed-err').length > 0`, 5000, 'errore del motore sotto il campo e sul disegno');
    const messaggio = await js(`document.querySelector('#edPannello .ed-errore-motore').textContent`);
    await js(`(() => { const e = document.querySelector('#edPannello [data-chiave="gateway:${id}"]'); e.value = ''; e.dispatchEvent(new Event('change', {bubbles: true})); e.blur(); })()`);
    await aspetta(`!document.querySelector('#edPannello .ed-errore-motore') && document.querySelectorAll('#edSvg .ed-err').length === 0`, 5000, 'errore sparito');
    await tasto('Escape');
    await aspetta(`document.querySelector('#edPannello').innerText.includes('Controlli del motore')`, 5000, 'controlli del motore nel pannello del lab');
    return { messaggio };
  });

  await passo('anteprima e creazione del lab disegnato (dnslab)', async () => {
    await js(`document.querySelector('#edNome').focus()`); await scrivi('dnslab'); await tasto('Tab'); await pausa(150);
    await js(`document.querySelector('#edAnteprimaBtn').click()`);
    await aspetta(`!document.querySelector('#edAnteprima').hidden && document.querySelectorAll('#edAntFile [data-file]').length > 0`, 15000, 'anteprima dei file');
    const n = await js(`document.querySelectorAll('#edAntFile [data-file]').length`);
    assert.equal(n, 26);
    await js(`document.querySelector('#edAntFile [data-file="root.startup"]').click()`);
    assert.match(await js(`document.querySelector('#edAntTesto').textContent`), /ip address add 10\.0\.2\.2\/24 dev eth0/);
    await B.scatta(SHOTS, 'editor-anteprima');
    await js(`document.querySelector('#edCrea').click()`);
    await aspetta(`document.querySelector('#editor').hidden && document.querySelector('#labNome')?.textContent === 'dnslab'`, 30000, 'lab creato e aperto');
    await aspetta(`document.querySelectorAll('#svg [data-id]').length > 0`, 10000, 'topologia del lab');
    const pos = await js(`document.querySelector('#svg [data-id="d:host1"]').getAttribute('transform')`);
    assert.equal(pos, 'translate(-340,0)', 'la Topologia usa le posizioni del disegno');
    await B.scatta(SHOTS, 'editor-lab-creato');
    const out = { file: n, topologia_host1: pos };
    if (BASE) {
      assert.deepEqual(albero(path.join(BASE, 'dnslab')), albero(path.join(QUI, '..', 'attesi', 'scenari', 'dns_root_auth_resolver')), 'file su disco diversi da quelli del wizard');
      const d = JSON.parse(fs.readFileSync(path.join(BASE, '.labgenerator', 'dnslab', 'disegno.json'), 'utf8'));
      assert.deepEqual(d.posizioni['d:root'], { x: 340, y: -100 });
      out.su_disco = 'uguali al wizard, disegno.json salvato';
    }
    await js(`document.querySelector('#bNuovo').click()`);
    await aspetta(`!document.querySelector('#editor').hidden`, 5000, 'editor riaperto');
    assert.equal(await js('window.__bozzaEditor().dispositivi.length'), 0, 'dopo la creazione il foglio è vuoto');
    return out;
  });

  await passo('importare un JSON e ricreare un lab esistente: conferma e copia di sicurezza', async () => {
    const doc = await cdp('DOM.getDocument', {});
    const nodo = await cdp('DOM.querySelector', { nodeId: doc.root.nodeId, selector: '#edFile' });
    await cdp('DOM.setFileInputFiles', { nodeId: nodo.nodeId, files: [path.join(QUI, '..', 'bozze', 'dns_root_auth_resolver.json')] });
    await aspetta(`window.__bozzaEditor().dispositivi.length === 6`, 5000, 'bozza importata');
    await js(`document.querySelector('#edNome').focus(); document.querySelector('#edNome').select()`); await scrivi('dnslab'); await tasto('Tab'); await pausa(150);
    await js(`document.querySelector('#edCrea').click()`);           // chiede conferma: il pilota accetta
    await aspetta(`document.querySelector('#editor').hidden && document.querySelector('#labNome')?.textContent === 'dnslab'`, 30000, 'lab ricreato');
    if (BASE) {
      assert.ok(fs.existsSync(path.join(BASE, '.backup_labgenerator', 'dnslab')), 'manca la copia di sicurezza');
      assert.deepEqual(albero(path.join(BASE, 'dnslab')), albero(path.join(QUI, '..', 'attesi', 'scenari', 'dns_root_auth_resolver')));
    }
  });

  await passo('bozza ripresa dopo aver ricaricato la pagina', async () => {
    await js(`document.querySelector('#bNuovo').click()`);
    await aspetta(`!document.querySelector('#editor').hidden`, 5000, 'editor');
    await tasto('r'); await clicSu({ x: 0, y: 0 }); await tasto('Escape');
    await cdp('Page.navigate', { url: new URL('/#nuovo', URL_GUI).href.replace('#nuovo', '?r=1#nuovo') });
    await aspetta(`!!document.querySelector('#edStrumenti button') && !document.querySelector('#editor').hidden`, 20000, 'editor dopo il ricaricamento');
    assert.equal(await js('window.__bozzaEditor().dispositivi.length'), 1);
    assert.match(await js(`document.querySelector('#edAiuto').textContent`), /Bozza ripresa/);
  });

  await passo('Ctrl+D, Ctrl+A, frecce e Nuova bozza', async () => {
    await clicSu({ x: 0, y: 0 });
    await tasto('d', { ctrl: true });
    let b = await bozza();
    assert.equal(b.dispositivi.length, 2);
    assert.deepEqual([b.dispositivi[1].x, b.dispositivi[1].y, b.dispositivi[1].nome], [40, 40, 'r2'], 'la copia ha subito un nome suo');
    await tasto('a', { ctrl: true });
    await aspetta(`document.querySelector('#edPannello').innerText.includes('2 elementi selezionati')`, 5000, 'tutto selezionato');
    await tasto('ArrowRight');
    b = await bozza();
    assert.deepEqual(b.dispositivi.map(d => d.x), [20, 60]);
    await js(`document.querySelector('#edNuova').click()`);         // conferma accettata dal pilota
    assert.equal((await bozza()).dispositivi.length, 0);
    await tasto('z', { ctrl: true });
    assert.equal((await bozza()).dispositivi.length, 2, 'Nuova bozza si annulla');
    await js(`document.querySelector('#edNuova').click()`);
  });

  await passo('IP corti dalla LAN, scambio di interfaccia, nomi stabili, BGP ai router di confine, rinomina per AS', async () => {
    const tira = async (a, b2) => { const [x0, y0] = await schermo(a.x, a.y), [x1, y1] = await schermo(b2.x, b2.y); await trascina(x0, y0, x1, y1); await pausa(100); };
    const P1 = { x: -200, y: 0 }, P2 = { x: 0, y: 0 }, P3 = { x: 200, y: 0 };
    await tasto('r'); await clicSu(P1); await clicSu(P2); await clicSu(P3);
    await tasto('l'); await clicSu(P1); await clicSu(P2); await clicSu(P2); await clicSu(P3);
    await tasto('Escape');
    // subnet e IP corti dal pannello della LAN r1-r2
    await clicSu(meta(P1, P2));
    await scriviCampo('subnet:', '10.0.0.0/30');
    let b = await bozza();
    const [c1, c2] = b.collegamenti.filter(c => c.lan === b.lan[0].id).map(c => c.id);
    await scriviChiave(`ip:${c1}`, '2');
    b = await bozza();
    assert.equal(b.collegamenti.find(c => c.id === c1).ip, '10.0.0.2/30', 'scritto solo "2"');
    assert.equal(converti(b).ip[c2], '10.0.0.1/30', 'l\'altro resta automatico');
    // r2: il link verso r3 diventa eth0
    await clicSu(P2);
    const verso3 = b.collegamenti.find(c => c.dispositivo === b.dispositivi[1].id && c.lan === b.lan[1].id).id;
    await scegliChiave(`eth:${verso3}`, '0');
    assert.equal(converti(await bozza()).interfacce[b.dispositivi[1].id][0], verso3, 'interfacce scambiate');
    // riquadri AS: i nomi restano, BGP solo ai router di confine
    await tasto('Escape');
    await tasto('a'); await tira({ x: -260, y: -60 }, { x: 60, y: 60 }); await scrivi('20'); await tasto('Tab'); await pausa(150);
    await tasto('a'); await tira({ x: 140, y: -60 }, { x: 260, y: 60 }); await scrivi('30'); await tasto('Tab'); await pausa(150);
    await js('document.activeElement && document.activeElement.blur()');
    let c = converti(await bozza());
    assert.deepEqual(Object.keys(c.modello.routers), ['r1', 'r2', 'r3'], 'entrare in un AS non cambia i nomi');
    assert.deepEqual(Object.values(c.modello.routers).map(r => r.protocols.join('+')), ['', 'bgp', 'bgp'], 'BGP solo su r2 e r3 (di confine)');
    // rinomina per AS, su richiesta
    const z20 = (await bozza()).zone[0];
    await clicSu({ x: z20.x + 30, y: z20.y + 16 });
    await premiPannello('[data-azione="rinomina-as"]');
    c = converti(await bozza());
    assert.deepEqual(Object.keys(c.modello.routers), ['as20r1', 'as20r2', 'r3']);
    await B.scatta(SHOTS, 'editor-regole-nuove');
    await js(`document.querySelector('#edNuova').click()`);
  });

  await passo('foto e ingombro', async () => {
    const out = {};
    for (const scuro of [false, true]) {
      await cdp('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: scuro ? 'dark' : 'light' }, { name: 'prefers-reduced-motion', value: 'reduce' }] });
      for (const w of [1440, 1024, 768]) {
        await cdp('Emulation.setDeviceMetricsOverride', { width: w, height: 900, deviceScaleFactor: 1, mobile: false });
        await clicSu(R2); await pausa(250);
        await B.scatta(SHOTS, `editor-${w}-${scuro ? 'scuro' : 'chiaro'}`);
        const f = await js(`(() => { const w = innerWidth, r = [];
          if (document.documentElement.scrollWidth > w + 1) r.push('pagina: scorre di lato');
          if (document.documentElement.scrollHeight > innerHeight + 1) r.push('pagina: scorre in verticale');
          for (const e of document.querySelectorAll('#editor *')) {
            if (!e.offsetParent || e.closest('svg, .scroll, table')) continue;
            const b = e.getBoundingClientRect(); if (b.width && b.right > w + 1) r.push((e.id ? '#' + e.id : e.tagName.toLowerCase()) + ' fino a ' + Math.round(b.right));
          } return [...new Set(r)].slice(0, 10); })()`);
        if (f.length) out[`${w} ${scuro ? 'scuro' : 'chiaro'}`] = f;
      }
    }
    assert.deepEqual(out, {}, JSON.stringify(out));
  });
} catch (e) {
  falliti++;
  esito.fatale = String(e.message || e);
  console.error('ERRORE: ' + esito.fatale);
}
if (errori.length) { falliti++; console.log('errori nella console:\n  ' + errori.join('\n  ')); }
if (OUT) fs.writeFileSync(OUT, JSON.stringify(esito, null, 1));
console.log(falliti ? `\n${falliti} problemi` : '\nTutto a posto.');
B.chiudi(falliti ? 1 : 0);
