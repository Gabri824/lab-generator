// Pilota della modalità Modifica (fasi 5.1 e 5.2) in Chromium senza finestra, con mouse e tastiera
// veri: costo OSPF dal disegno e dal pannello del router, auto-cost dalla scritta dell'AS, anteprima,
// applica, annulla, conflitto con un file cambiato dopo l'anteprima; subnet di una LAN, IP di
// un'interfaccia, spostamento su una LAN nuova, host aggiunto, rinominato e tolto, protocollo
// aggiunto, file a righe; BGP (5.3), DNS (5.4), policy BGP dal router e dal link fra due AS con
// Customer-Provider-Peer e il lato opposto proposto (5.5); tutto annullato fino al lab di partenza;
// copie di sicurezza e ripristino.
// Usa una COPIA del lab (--lab-path), mai un lab vero.
//
//   node tests/strumenti/prova_modifica.mjs --url http://127.0.0.1:8795/ --lab papillon_mio \
//        --lab-path /tmp/labs/papillon_mio [--shots cartella]
import fs from 'node:fs';
import path from 'node:path';
import { apriBrowser, pausa, trovaChrome } from './cdp.mjs';

const arg = (n, d) => { const i = process.argv.indexOf('--' + n); return i > 0 ? process.argv[i + 1] : d; };
const URL_GUI = arg('url', 'http://127.0.0.1:8795/'), LAB = arg('lab', 'papillon_mio'), LAB_PATH = arg('lab-path'), SHOTS = arg('shots');
if (!LAB_PATH) { console.error('serve --lab-path (una copia del lab)'); process.exit(2); }

const B = await apriBrowser(trovaChrome(arg('chrome')));
const passi = [];
async function passo(nome, f) {
  const t0 = Date.now();
  try { await f(); passi.push({nome, ok: true}); console.log(`ok   ${nome} (${((Date.now() - t0) / 1000).toFixed(1)} s)`); }
  catch (e) { passi.push({nome, ok: false, errore: e.message}); console.log(`KO   ${nome}: ${e.message}`); await B.scatta(SHOTS, 'ko-' + passi.length); }
}
const centro = sel => B.js(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return null; e.scrollIntoView({block: 'center'}); const r = e.getBoundingClientRect(); return {x: r.x + r.width / 2, y: r.y + r.height / 2}; })()`);
async function clicSu(sel) { const c = await centro(sel); if (!c) throw new Error('non trovato: ' + sel); await B.clic(c.x, c.y); }
const lato = () => B.testo('#side');
// voce di un menu della modalità Modifica (interfaccia, LAN) per il testo del pulsante
async function clicVoce(testo) {
  await B.aspetta(`[...document.querySelectorAll('#side [data-mod-voce]')].some(b => b.innerText.includes(${JSON.stringify(testo)}))`, 5000, 'voce ' + testo);
  const i = await B.js(`[...document.querySelectorAll('#side [data-mod-voce]')].findIndex(b => b.innerText.includes(${JSON.stringify(testo)}))`);
  await clicSu(`#side [data-mod-voce="${await B.js(`document.querySelectorAll('#side [data-mod-voce]')[${i}].dataset.modVoce`)}"]`);
}
async function campo(nome, valore) {
  await aspettaCampo(nome);
  await B.js(`(() => { const x = document.querySelector('#side [name=${JSON.stringify(nome)}]'); x.focus(); x.select && x.select(); })()`);
  await B.scrivi(String(valore));
}
async function aspettaCampo(nome) {
  await B.aspetta(`!!document.querySelector('#side [name=${JSON.stringify(nome)}]')`, 10000, 'campo ' + nome);
}
async function anteprimaEApplica(atteso) {
  await B.aspetta(`!!document.querySelector('#side [data-mod-azione="anteprima"]')`, 10000, 'pulsante Anteprima');
  await clicSu('#side [data-mod-azione="anteprima"]');
  await B.aspetta(`!!document.querySelector('#side [data-mod-azione="applica"]') || /koline/.test(document.querySelector('#opRis')?.innerHTML || '')`, 10000, 'anteprima');
  if (!await B.js(`!!document.querySelector('#side [data-mod-azione="applica"]')`)) throw new Error('anteprima rifiutata: ' + await B.testo('#opRis'));
  await clicSu('#side [data-mod-azione="applica"]');
  await B.aspetta(`document.querySelector('#side').innerText.includes(${JSON.stringify('Fatto: ' + atteso)})`, 10000, 'esito ' + atteso);
}
const testo = rel => fs.readFileSync(path.join(LAB_PATH, rel), 'utf8');
const esiste = rel => fs.existsSync(path.join(LAB_PATH, rel));
const frr = r => fs.readFileSync(path.join(LAB_PATH, r, 'etc', 'frr', 'frr.conf'), 'utf8');
const originale = {r1: frr('r1'), r2: frr('r2'), r3: frr('r3'), r4: frr('r4')};

await B.cdp('Page.enable'); await B.cdp('Runtime.enable');
await B.cdp('Page.navigate', {url: `${URL_GUI}#lab=${LAB}&tab=topo`});
await B.aspetta(`!!document.querySelector('#svg g[data-id]')`, 20000, 'topologia');

await passo('modalità Modifica accesa', async () => {
  await clicSu('#bModifica');
  await B.aspetta(`document.querySelector('#bModifica').getAttribute('aria-pressed') === 'true' && /Modifica del lab/.test(document.querySelector('#side').innerText)`, 5000, 'pannello Modifica');
  if (!await B.js(`document.querySelector('#svg').classList.contains('mod')`)) throw new Error('disegno non in modalità mod');
});

await passo('costo OSPF dal disegno: clic sull\'etichetta di r1 eth1', async () => {
  await clicSu('#svg g[data-mod="if"][data-dev="r1"][data-iface="eth1"] .pill');
  await clicVoce('Costo OSPF');
  await B.aspetta(`/Costo OSPF di r1 eth1/.test(document.querySelector('#side').innerText)`, 5000, 'modulo del costo');
  await clicSu('#side input[name="costo"]');
  await B.scrivi('20');
  await clicSu('#side [data-mod-azione="anteprima"]');
  await B.aspetta(`/ospf cost 20/.test(document.querySelector('#opRis').innerText)`, 10000, 'anteprima con la riga');
  await B.scatta(SHOTS, 'mod-anteprima');
  await clicSu('#side [data-mod-azione="applica"]');
  await B.aspetta(`/Fatto: Costo OSPF di r1 eth1: 20/.test(document.querySelector('#side').innerText)`, 10000, 'esito');
  if (!/ospf cost 20/.test(frr('r1'))) throw new Error('frr.conf non scritto');
  await B.aspetta(`[...document.querySelectorAll('#svg g.costo title')].some(t => /eth1: costo OSPF 20/.test(t.textContent))`, 5000, 'c20 sul disegno');
  await B.aspetta(`!document.querySelector('#bAnnulla').disabled`, 5000, 'Annulla attivo');
  await B.scatta(SHOTS, 'mod-fatto');
});

await passo('costo minore di 1 rifiutato senza scrivere', async () => {
  const prima = frr('r2');
  await clicSu('#svg g[data-mod="if"][data-dev="r2"][data-iface="eth1"] .pill');
  await clicVoce('Costo OSPF');
  await B.aspetta(`/Costo OSPF di r2 eth1/.test(document.querySelector('#side').innerText)`, 5000, 'modulo');
  await clicSu('#side input[name="costo"]'); await B.scrivi('0');
  await clicSu('#side [data-mod-azione="anteprima"]');
  await B.aspetta(`/almeno|≥ 1|intero/.test(document.querySelector('#opRis').innerText)`, 10000, 'errore del motore');
  if (frr('r2') !== prima) throw new Error('scritto lo stesso');
  await clicSu('#side [data-mod-azione="indietro"]');
});

await passo('auto-cost dalla scritta dell\'AS20', async () => {
  await clicSu('#svg rect[data-mod="as"][data-as="20"]');
  await clicVoce('Auto-cost');
  await B.aspetta(`/Auto-cost su AS20/.test(document.querySelector('#side').innerText)`, 5000, 'modulo auto-cost');
  // papillon_mio ha già l'auto-cost su tutti: la proposta è toglierlo
  const v = await B.js(`document.querySelector('#side select[name="togli"]').value`);
  if (v !== 'si') throw new Error('proposta inattesa: ' + v);
  await clicSu('#side [data-mod-azione="anteprima"]');
  await B.aspetta(`/auto-cost reference-bandwidth 100/.test(document.querySelector('#opRis').innerText)`, 10000, 'anteprima');
  await clicSu('#side [data-mod-azione="applica"]');
  await B.aspetta(`/Fatto: Togli auto-cost/.test(document.querySelector('#side').innerText)`, 10000, 'esito');
  if (/auto-cost/.test(frr('r1'))) throw new Error('auto-cost ancora in r1');
});

await passo('pannello del router: pulsanti delle interfacce', async () => {
  await clicSu('#svg g[data-id="d:r4"] circle');
  await B.aspetta(`!!document.querySelector('#side [data-gesto="if"][data-dev="r4"]')`, 5000, 'pulsanti delle interfacce');
  await clicSu('#side [data-gesto="if"][data-dev="r4"][data-iface="eth0"]');
  await clicVoce('Costo OSPF');
  await B.aspetta(`/Costo OSPF di r4 eth0/.test(document.querySelector('#side').innerText)`, 5000, 'modulo');
  await clicSu('#side [data-mod-azione="indietro"]');
});

await passo('conflitto: file cambiato dopo l\'anteprima', async () => {
  await clicSu('#svg g[data-mod="if"][data-dev="r3"][data-iface="eth0"] .pill');
  await clicVoce('Costo OSPF');
  await B.aspetta(`/Costo OSPF di r3 eth0/.test(document.querySelector('#side').innerText)`, 5000, 'modulo');
  await clicSu('#side input[name="costo"]'); await B.scrivi('7');
  await clicSu('#side [data-mod-azione="anteprima"]');
  await B.aspetta(`!!document.querySelector('#side [data-mod-azione="applica"]')`, 10000, 'anteprima');
  const r3 = frr('r3');
  fs.appendFileSync(path.join(LAB_PATH, 'r3', 'etc', 'frr', 'frr.conf'), '! cambiato a mano\n');
  await clicSu('#side [data-mod-azione="applica"]');
  await B.aspetta(`/Non ho scritto nulla/.test(document.querySelector('#opRis').innerText)`, 10000, 'conflitto');
  if (/ospf cost 7/.test(frr('r3'))) throw new Error('scritto nonostante il conflitto');
  fs.writeFileSync(path.join(LAB_PATH, 'r3', 'etc', 'frr', 'frr.conf'), r3);     // com'era prima della mano
  await B.scatta(SHOTS, 'mod-conflitto');
  await clicSu('#side [data-mod-azione="indietro"]');
});

await passo('annulla due volte: il lab torna com\'era', async () => {
  await clicSu('#bAnnulla');
  await B.aspetta(`!!document.querySelector('#side [data-mod-azione="applica"]')`, 10000, 'anteprima dell\'annullamento (auto-cost)');
  await clicSu('#side [data-mod-azione="applica"]');
  await B.aspetta(`/Annullato: Annulla: Togli auto-cost/.test(document.querySelector('#side').innerText)`, 10000, 'primo annullamento');
  await clicSu('#bAnnulla');
  await B.aspetta(`!!document.querySelector('#side [data-mod-azione="applica"]')`, 10000, 'anteprima (costo)');
  await clicSu('#side [data-mod-azione="applica"]');
  await B.aspetta(`/Annullato: Annulla: Costo OSPF di r1 eth1/.test(document.querySelector('#side').innerText)`, 10000, 'secondo annullamento');
  for (const r of Object.keys(originale)) if (frr(r) !== originale[r]) throw new Error(`${r} diverso dall'originale`);
  await B.aspetta(`document.querySelector('#bAnnulla').disabled`, 5000, 'Annulla spento a storia vuota');
});

// ---------- fase 5.2 ----------
const iniziale = {};
for (const f of ['lab.conf', 'client.startup', 'r1.startup', 'r4.startup', 'r1/etc/frr/frr.conf', 'r4/etc/frr/frr.conf', 'r4/etc/frr/daemons']) iniziale[f] = testo(f);

await passo('LAN A: subnet nuova con gli IP proposti', async () => {
  await clicSu('#svg [data-mod="lan"][data-lan="A"] rect');
  await clicVoce('Cambia subnet');
  await campo('rete', '20.20.9.0/24');
  await clicSu('#side [data-mod-azione="anteprima"]');                    // Avanti
  await B.aspetta(`document.querySelector('#side [name="ip:client:eth0"]')?.value === '20.20.9.2/24'`, 5000, 'IP proposto');
  await anteprimaEApplica('Rete della LAN A');
  if (!/20\.20\.9\.2\/24/.test(testo('client.startup')) || !/via 20\.20\.9\.1/.test(testo('client.startup'))) throw new Error('client non rinumerato');
});

await passo('IP di r4 eth1: basta l\'ultimo numero', async () => {
  await clicSu('#svg g[data-mod="if"][data-dev="r4"][data-iface="eth1"] .pill');
  await clicVoce('Cambia IP');
  await campo('nuovo', '9');
  await anteprimaEApplica('IP di r4 eth1');
  if (!/20\.20\.5\.9\/24 dev eth1/.test(testo('r4.startup'))) throw new Error('IP non cambiato');
});

await passo('client eth0 su una LAN nuova', async () => {
  await clicSu('#svg g[data-mod="if"][data-dev="client"][data-iface="eth0"] .pill');
  await clicVoce("Sposta su un'altra LAN");
  await aspettaCampo('lan');
  await B.js(`(() => { const s = document.querySelector('#side [name="lan"]'); s.value = '__nuova'; s.dispatchEvent(new Event('change', {bubbles: true})); })()`);
  await campo('nuova', 'Z');
  await clicSu('#side [data-mod-azione="anteprima"]');                    // Avanti
  await B.aspetta(`!!document.querySelector('#side [name="nuovo_ip"]')`, 5000, 'passo dell\'IP');
  await campo('nuovo_ip', '10.99.0.2/24');
  await anteprimaEApplica('client eth0: LAN A -> Z');
  if (!/client\[0\]=Z/.test(testo('lab.conf'))) throw new Error('lab.conf non cambiato');
});

await passo('host aggiunto, rinominato e tolto', async () => {
  await clicSu('#side [data-mod-azione="indietro"]').catch(() => {});
  await B.aspetta(`!!document.querySelector('#side [data-gesto="aggiungi"][data-tipo="host"]')`, 5000, 'pulsante + Host');
  await clicSu('#side [data-gesto="aggiungi"][data-tipo="host"]');
  await aspettaCampo('lan');
  await B.js(`document.querySelector('#side [name="lan"]').value = 'B'`);
  await clicSu('#side [data-mod-azione="anteprima"]');                    // Avanti
  await B.aspetta(`document.querySelector('#side [name="gateway"]')?.value === '20.20.2.1' || document.querySelector('#side [name="gateway"]')?.value === '20.20.2.2'`, 5000, 'gateway proposto');
  const nome = await B.js(`document.querySelector('#side [name="nome"]').value`);
  await anteprimaEApplica(`Aggiungi host ${nome}`);
  if (!esiste(nome + '.startup')) throw new Error('startup non creato');
  await B.aspetta(`!!document.querySelector('#svg g[data-id="d:${nome}"]')`, 5000, 'host sul disegno');
  await clicSu(`#svg g[data-id="d:${nome}"] rect`);
  await clicSu(`#side [data-gesto="disp"][data-azione="rinomina"]`);
  await campo('nuovo', 'pc9');
  await anteprimaEApplica(`Rinomina ${nome} -> pc9`);
  if (!esiste('pc9.startup') || esiste(nome + '.startup')) throw new Error('rinomina non fatta');
  await clicSu('#svg g[data-id="d:pc9"] rect');
  await clicSu('#side [data-gesto="disp"][data-azione="togli"]');
  await anteprimaEApplica('Togli');
  if (esiste('pc9.startup')) throw new Error('host non tolto');
});

await passo('RIP aggiunto a r4 con le network proposte', async () => {
  await clicSu('#svg g[data-id="d:r4"] circle');
  await clicSu('#side [data-gesto="disp"][data-azione="aggiungi:rip"]');
  await B.aspetta(`!!document.querySelector('#side [name="reti"]')?.value`, 5000, 'network proposte');
  await anteprimaEApplica('Aggiungi RIP a r4');
  if (!/ripd=yes/.test(testo('r4/etc/frr/daemons')) || !/router rip/.test(testo('r4/etc/frr/frr.conf'))) throw new Error('RIP non aggiunto');
});

await passo('file a righe: una riga nel frr.conf di r1', async () => {
  await clicSu('#svg g[data-id="d:r1"] circle');
  await clicSu('#side [data-gesto="disp"][data-azione="righe"]');
  await aspettaCampo('rel');
  await B.js(`document.querySelector('#side [name="rel"]').value = 'r1/etc/frr/frr.conf'`);
  await clicSu('#side [data-mod-azione="anteprima"]');                    // Avanti
  await B.aspetta(`!!document.querySelector('#opRighe')`, 5000, 'editor a righe');
  await B.js(`(() => { const t = document.querySelector('#opRighe'); t.value = t.value + '\\n! nota dalla GUI'; })()`);
  await anteprimaEApplica('Modifica di r1/etc/frr/frr.conf');
  if (!/! nota dalla GUI/.test(testo('r1/etc/frr/frr.conf'))) throw new Error('riga non scritta');
  await B.scatta(SHOTS, 'mod-righe');
});

// ---------- fase 5.3 ----------
for (const f of ['r3/etc/frr/frr.conf']) iniziale[f] = iniziale[f] || testo(f);

await passo('AS20: aggregato dal menu dell\'AS, con le reti già coperte', async () => {
  await clicSu('#svg rect[data-mod="as"][data-as="20"]');
  await clicVoce("Annuncia l'aggregato");
  await aspettaCampo('reti');
  await clicSu('#side [data-mod-azione="anteprima"]');                    // Avanti
  await B.aspetta(`/già contenute nell'aggregato/.test(document.querySelector('#side').innerText)`, 10000, 'reti coperte');
  await anteprimaEApplica('Network BGP su r3');
  if (!/network 20\.0\.0\.0\/8/.test(testo('r3/etc/frr/frr.conf'))) throw new Error('aggregato non scritto');
});

await passo('loopback su r1', async () => {
  await clicSu('#svg g[data-id="d:r1"] circle');
  await clicSu('#side [data-gesto="disp"][data-azione="loopback"]');
  await campo('ip', '1.1.1.1');
  await anteprimaEApplica('Loopback 1.1.1.1/32 su r1');
  if (!/1\.1\.1\.1\/32 dev lo/.test(testo('r1.startup'))) throw new Error('loopback non scritta');
});

await passo('default route in OSPF e verso il vicino BGP (r3)', async () => {
  await clicSu('#svg g[data-id="d:r3"] circle');
  await clicSu('#side [data-gesto="disp"][data-azione="default"]');
  await clicVoce('OSPF');
  await anteprimaEApplica('Default route in OSPF su r3');
  if (!/default-information originate always/.test(testo('r3/etc/frr/frr.conf'))) throw new Error('default OSPF non scritta');
  await clicSu('#svg g[data-id="d:r3"] circle');
  await clicSu('#side [data-gesto="disp"][data-azione="default"]');
  await clicVoce('BGP');
  await aspettaCampo('n:10.1.0.2');
  if (!await B.js(`document.querySelector('#side [name="n:10.1.0.2"]').checked`)) throw new Error('il vicino eBGP non è proposto');
  await anteprimaEApplica('Default route da r3');
  if (!/neighbor 10\.1\.0\.2 default-originate/.test(testo('r3/etc/frr/frr.conf'))) throw new Error('default-originate non scritto');
});

await passo('ridistribuzione: togli redistribute bgp su r3', async () => {
  await clicSu('#svg g[data-id="d:r3"] circle');
  await clicSu('#side [data-gesto="disp"][data-azione="ridistribuzione"]');
  await clicVoce('Togli redistribute bgp');
  await B.aspetta(`!!document.querySelector('#side [data-mod-azione="applica"]')`, 10000, 'anteprima');
  await clicSu('#side [data-mod-azione="applica"]');
  await B.aspetta(`document.querySelector('#side').innerText.includes('Fatto: Togli redistribute bgp su r3')`, 10000, 'esito');
  if (/^\s*redistribute bgp\s*$/m.test(testo('r3/etc/frr/frr.conf'))) throw new Error('redistribute bgp ancora presente');
});

// ---------- fase 5.4 ----------
await passo('DNS: server root aggiunto, delega di com, resolver del client', async () => {
  await clicSu('#side [data-mod-azione="indietro"]').catch(() => {});
  await clicSu('#svg', ).catch(() => {});
  await B.js(`document.querySelector('#bModifica').click(); document.querySelector('#bModifica').click()`);   // pannello iniziale
  await B.aspetta(`!!document.querySelector('#side [data-gesto="aggiungi"][data-tipo="dns"]')`, 5000, 'pulsante + Server DNS');
  await clicSu('#side [data-gesto="aggiungi"][data-tipo="dns"]');
  await aspettaCampo('lan');
  await B.js(`document.querySelector('#side [name="lan"]').value = 'B'`);
  await clicSu('#side [data-mod-azione="anteprima"]');                    // Avanti
  await aspettaCampo('nome');
  if (await B.js(`document.querySelector('#side [name="nome"]').value`) !== 'root') throw new Error('il primo DNS non si chiama root');
  if (await B.js(`document.querySelector('#side [name="root_type"]').value`) !== 'master') throw new Error('root non master');
  await anteprimaEApplica('Aggiungi dns root');
  await B.aspetta(`!!document.querySelector('#svg g[data-id="d:root"]')`, 5000, 'root sul disegno');
  await clicSu('#svg g[data-id="d:root"] rect');
  await clicSu('#side [data-gesto="disp"][data-azione="delega"]');
  await campo('zona', 'com');
  await B.js(`document.querySelector('#side [name="server"]').value = ''`);
  await clicSu('#side [data-mod-azione="anteprima"]');                    // Avanti
  await aspettaCampo('ns');
  if (await B.js(`document.querySelector('#side [name="ns"]').value`) !== 'dns.com') throw new Error('nameserver non proposto');
  await campo('ip', '20.20.2.53');
  await anteprimaEApplica('Delega della zona com su root');
  if (!/com\.\s+IN\s+NS\s+dns\.com\./.test(testo('root/etc/bind/db.root'))) throw new Error('delega non scritta');
  await clicSu('#svg g[data-id="d:client"] rect');
  await clicSu('#side [data-gesto="disp"][data-azione="resolver"]');
  await aspettaCampo('scelto');
  const ip = await B.js(`document.querySelector('#side [name="scelto"]').value`);
  await anteprimaEApplica('Resolver di client');
  if (!testo('client/etc/resolv.conf').includes('nameserver ' + ip)) throw new Error('resolv.conf non scritto');
});

// ---------- fase 5.5 ----------
await passo('policy dal pannello di r3: local-preference 150 da r5', async () => {
  await clicSu('#svg g[data-id="d:r3"] circle');
  await clicSu('#side [data-gesto="disp"][data-azione="policy"]');
  await clicVoce('10.1.0.2 r5 AS30');
  await clicVoce('Local-preference');
  await aspettaCampo('valore');
  if (String(await B.js(`document.querySelector('#side [name="valore"]').value`)) !== '150') throw new Error('valore 150 non proposto');
  await anteprimaEApplica('Local preference 150 da 10.1.0.2 su r3');
  if (!/set local-preference 150/.test(frr('r3')) || !/neighbor 10\.1\.0\.2 route-map PREF_IN_10_1_0_2 in/.test(frr('r3'))) throw new Error('route-map non scritta');
});

await passo('policy dal link F: MED 20 su r5 verso r3', async () => {
  await clicSu('#svg g[data-mod="lan"][data-lan="F"] .pill-lan');
  await clicVoce('Policy BGP su r5 verso r3');
  await clicVoce('MED');
  await aspettaCampo('valore');
  await anteprimaEApplica('MED 20 verso 10.1.0.1 su r5');
  if (!/set metric 20/.test(frr('r5'))) throw new Error('MED non scritto');
});

await passo('prefix-list in uscita su r3 verso r5, rete scelta con la casella', async () => {
  await clicSu('#svg g[data-mod="lan"][data-lan="F"] .pill-lan');
  await clicVoce('Policy BGP su r3 verso r5');
  await clicVoce('Prefix-list');
  await aspettaCampo('direzione');
  await B.js(`document.querySelector('#side [name="direzione"]').value = 'out'`);
  await clicSu('#side [name="r:30.30.0.0/16"]');
  await anteprimaEApplica('Prefix-list PL_r3_10_1_0_2_out su r3');
  if (!/ip prefix-list PL_r3_10_1_0_2_out deny 30\.30\.0\.0\/16/.test(frr('r3'))) throw new Error('prefix-list non scritta');
});

await passo('Customer-Provider-Peer: r5 provider di r3, poi il lato opposto proposto', async () => {
  await clicSu('#svg g[data-id="d:r3"] circle');
  await clicSu('#side [data-gesto="disp"][data-azione="policy"]');
  await clicVoce('10.1.0.2 r5');
  await clicVoce('Customer-Provider-Peer');
  await aspettaCampo('relazione');
  await B.js(`document.querySelector('#side [name="relazione"]').value = 'provider'`);
  await clicSu('#side [data-mod-azione="anteprima"]');                    // Avanti
  await aspettaCampo('r:20.20.0.0/16');
  if (!await B.js(`document.querySelector('#side [name="r:20.20.0.0/16"]').checked`)) throw new Error('rete propria non proposta');
  if (await B.js(`document.querySelector('#side [name="r:10.1.0.0/30"]').checked`)) throw new Error('il link con il provider è proposto');
  await anteprimaEApplica('Provider r5 su r3');
  if (!/ip prefix-list provider_r5_out permit 20\.20\.0\.0\/16/.test(frr('r3'))) throw new Error('prefix-list provider non scritta');
  await B.aspetta(`/Lato opposto: Customer r3 su r5/.test(document.querySelector('#side').innerText)`, 10000, 'lato opposto proposto');
  await anteprimaEApplica('Customer r3 su r5');
  if (!/neighbor 10\.1\.0\.1 prefix-list customer_r3_out out/.test(frr('r5'))) throw new Error('lato opposto non scritto');
});

await passo('annulla tutto: il lab torna com\'era', async () => {
  for (let k = 0; k < 40; k++) {
    if (await B.js(`document.querySelector('#bAnnulla').disabled`)) break;
    await clicSu('#bAnnulla');
    await B.aspetta(`!!document.querySelector('#side [data-mod-azione="applica"]') || /koline/.test(document.querySelector('#opRis')?.innerHTML || '')`, 10000, 'anteprima dell\'annullamento');
    if (!await B.js(`!!document.querySelector('#side [data-mod-azione="applica"]')`)) throw new Error(await B.testo('#opRis'));
    await clicSu('#side [data-mod-azione="applica"]');
    await B.aspetta(`/Annullato:/.test(document.querySelector('#side').innerText)`, 10000, 'annullato');
  }
  for (const [f, t] of Object.entries(iniziale)) if (testo(f) !== t) throw new Error(`${f} diverso da prima della 5.2`);
  for (const n of ['pc9.startup', 'host1.startup']) if (esiste(n)) throw new Error(n + ' ancora presente');
});

await passo('copie di sicurezza e ripristino', async () => {
  // una modifica, poi si torna alla copia fatta prima di scriverla
  await clicSu('#svg g[data-mod="if"][data-dev="r1"][data-iface="eth0"] .pill');
  await clicVoce('Costo OSPF');
  await clicSu('#side input[name="costo"]'); await B.scrivi('33');
  await clicSu('#side [data-mod-azione="anteprima"]');
  await B.aspetta(`!!document.querySelector('#side [data-mod-azione="applica"]')`, 10000, 'anteprima');
  await clicSu('#side [data-mod-azione="applica"]');
  await B.aspetta(`/Fatto: Costo OSPF di r1 eth0: 33/.test(document.querySelector('#side').innerText)`, 10000, 'esito');
  await clicSu('#side [data-mod-azione="copie"]');
  await B.aspetta(`!!document.querySelector('#side [data-copia]')`, 10000, 'elenco copie');
  await B.scatta(SHOTS, 'mod-copie');
  await clicSu('#side [data-copia]');                 // la più recente: prima del costo 33 (conferma accettata)
  await B.aspetta(`/Lab ripristinato/.test(document.querySelector('#side').innerText)`, 10000, 'ripristino');
  if (frr('r1') !== originale.r1) throw new Error('r1 non ripristinato');
  await B.aspetta(`document.querySelector('#bAnnulla').disabled`, 5000, 'storia svuotata');
});

await passo('modalità Modifica spenta', async () => {
  await clicSu('#bModifica');
  await B.aspetta(`document.querySelector('#bModifica').getAttribute('aria-pressed') === 'false' && !document.querySelector('#svg').classList.contains('mod')`, 5000, 'spenta');
});

// 422 (costo 0) e 409 (conflitto) sono provocati apposta: non sono errori della pagina
const errori = B.errori.filter(e => !/status of (422|409)/.test(e));
if (errori.length) passi.push({nome: 'errori nella pagina', ok: false, errore: errori.join(' | ')});
await B.chiudi();
const ko = passi.filter(p => !p.ok);
console.log(`\n${passi.length - ko.length}/${passi.length} passi ok` + (ko.length ? '\n' + ko.map(p => `KO ${p.nome}: ${p.errore}`).join('\n') : ''));
process.exit(ko.length ? 1 : 0);
