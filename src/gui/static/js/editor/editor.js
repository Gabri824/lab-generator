// Editor grafico per i lab nuovi (fase 4.2): strumenti, mouse e tastiera, pannello semplice,
// annulla/ripeti. I dati stanno nella bozza (bozza.js), le modifiche passano da azioni.js.
import { $, azione, esc, mem, outFine, outInizio, outScrivi, S } from '../comune.js';
import { creaBarraStoria, Storia } from '../componenti/storia.js';
import {
  aggiungiDispositivo, aggiungiLan, aggiungiZona, collega, duplica, elimina, GRIGLIA, imposta, impostaInterfaccia, impostaProprieta,
  modificaElenco, posizioni, ridimensionaZona, rinominaPerAs, sposta, ZONE,
} from './azioni.js';
import { apriLab, caricaLabs } from '../main.js';
import { converti, elementoDelCampo, leggiRete, nuovaBozza, proponiSubnet, TIPI, VERSIONE } from './bozza.js';
import { riquadro, svgBozza } from './disegno.js';
import { caricaLab } from './da_lab.js';
import { grafo, varianti } from '../disposizione.js';
import { campo, htmlDns, htmlGateway, htmlLab, htmlRouter } from './pannelli.js';

const STRUMENTI = {
  seleziona: {tasto: 'Escape', aiuto: 'Clic per selezionare (Maiusc+clic per aggiungere), trascina per spostare, Maiusc+trascina sullo sfondo per selezionare un\'area, Canc per eliminare.'},
  router: {tasto: 'r', aiuto: 'Clic sul foglio per mettere un router. Esc per tornare a Seleziona.'},
  host: {tasto: 'h', aiuto: 'Clic sul foglio per mettere un host. Esc per tornare a Seleziona.'},
  www: {tasto: 'w', aiuto: 'Clic sul foglio per mettere un server WWW. Esc per tornare a Seleziona.'},
  dns: {tasto: 'd', aiuto: 'Clic sul foglio per mettere un server DNS. Esc per tornare a Seleziona.'},
  lan: {tasto: 'n', aiuto: 'Clic sul foglio per mettere un nodo LAN (per una rete con più di due dispositivi).'},
  collega: {tasto: 'l', aiuto: 'Clic su un dispositivo, poi su un altro (link diretto), su un nodo LAN o sulla linea di un link diretto (diventa un nodo LAN).'},
  as: {tasto: 'a', aiuto: 'Trascina un rettangolo intorno ai router dell\'AS (o clic per un riquadro standard), poi scrivi il numero AS.'},
  rip: {tasto: 'i', aiuto: 'Trascina un rettangolo intorno ai router che usano RIP.'},
  ospf: {tasto: 'o', aiuto: 'Trascina un rettangolo intorno alle LAN (o ai link) dell\'area, poi scrivi l\'area. Un router con LAN in due aree diventa router di confine.'},
};
const NOMI_STRUMENTI = {seleziona: 'Seleziona', router: 'Router', host: 'Host', www: 'WWW', dns: 'DNS', lan: 'Nodo LAN', collega: 'Collega', as: 'AS', rip: 'RIP', ospf: 'Area OSPF'};
const NOME_ZONA = {as: 'Riquadro AS', rip: 'Zona RIP', ospf: 'Area OSPF'};

const E = {bozza: nuovaBozza(''), temp: null, storia: null, conv: null, sel: new Set(), strumento: 'seleziona',
  attesa: null, griglia: true, vb: null, trascina: null, avviso: ''};

const aperto = () => !$('#editor').hidden;
const attuale = () => E.temp || E.bozza;

// per le prove nel browser (tests/strumenti/prova_gui.mjs): copia della bozza attuale
window.__bozzaEditor = () => JSON.parse(JSON.stringify(E.bozza));

// ----------------------------------------------------------------------------- stato e disegno

function cambia(nuova) {
  E.temp = null;
  E.bozza = nuova;
  E.storia.fai(nuova);
  salvaBozza();
  aggiornaTutto();
  controllaMotore();
}

// la bozza resta nel browser: se si chiude la pagina, riaprendo l'editor si riprende da qui
const CHIAVE_BOZZA = 'editor:bozza';
function salvaBozza() { mem(CHIAVE_BOZZA, E.bozza); }
function bozzaValida(b) {
  return b && typeof b === 'object' && b.versione === VERSIONE && ['dispositivi', 'lan', 'collegamenti', 'zone'].every(k => Array.isArray(b[k]));
}
const vuota = b => !b.dispositivi.length && !b.lan.length && !b.zone.length;

// ----------------------------------------------------------------------------- controlli del motore dal vivo
//
// Dopo ogni modifica, con una pausa di 0,4 s, il modello va a valida_lab sul server (le stesse
// regole del terminale, in modalità "lab in costruzione"). Le risposte vecchie si scartano.

let attesaMotore = null, giroMotore = 0;
function controllaMotore() {
  clearTimeout(attesaMotore);
  attesaMotore = setTimeout(async () => {
    const giro = ++giroMotore, b = E.bozza;
    const dati = {azione: 'valida_lab', modello: converti(b).modello, parziale: true};
    if (b.nome) dati.nome = b.nome;
    let r;
    try { r = await azione(dati); } catch (e) { r = {problemi: [], completato: null, errore: e.message}; }
    if (giro !== giroMotore) return;
    E.motore = r;
    mappaMotore();
    disegna();
    const f = document.activeElement;
    if (f && $('#edPannello').contains(f) && ['INPUT', 'SELECT', 'TEXTAREA'].includes(f.tagName)) segnaCampi();   // non si toglie il testo che si sta scrivendo
    else pannello();
  }, 400);
}

// problemi del motore -> elemento del disegno e campo del pannello
function chiaveDelCampo(campo, el) {
  if (campo === 'lab.resolver') return 'resolver:lab';
  if (!el) return null;
  if (el.collegamento && /\.ip$/.test(campo)) return `ip:${el.collegamento}`;
  if (/^[^.]+\.name$/.test(campo)) return `nome:${el.id}`;
  if (/\.(gateway|gw_dev)$/.test(campo)) return `gateway:${el.id}`;
  if (/\.igp_networks$/.test(campo)) return `igp:${el.id}`;
  const m = /\.static_routes\[(\d+)\]/.exec(campo);
  if (m) return `statica:${el.id}:${m[1]}:${/\.via$/.test(campo) ? 'via' : 'rete'}`;
  if (/^lan\./.test(campo)) return `subnet:${el.id}`;
  return null;
}
function mappaMotore() {
  E.motoreMappati = ((E.motore && E.motore.problemi) || []).map(p => {
    const el = elementoDelCampo(E.conv || converti(E.bozza), p.campo);
    return Object.assign({}, p, {id: el ? el.id : null, chiave: chiaveDelCampo(p.campo, el)});
  });
}
function segnaCampi() {
  const pan = $('#edPannello');
  pan.querySelectorAll('.ed-errore-motore').forEach(x => x.remove());
  pan.querySelectorAll('[data-chiave][aria-invalid]').forEach(x => x.removeAttribute('aria-invalid'));
  for (const p of (E.motoreMappati || []).filter(x => x.chiave && x.gravita === 'errore')) {
    const el = pan.querySelector(`[data-chiave="${CSS.escape(p.chiave)}"]`);
    if (!el) continue;
    el.setAttribute('aria-invalid', 'true');
    const d = document.createElement('p');
    d.className = 'campo__errore ed-errore-motore';
    d.textContent = p.messaggio;
    (el.closest('.prop__campo, td') || el).appendChild(d);
  }
}

// ----------------------------------------------------------------------------- fase 5.7: parti da un lab esistente
//
// La bozza tiene il lab di partenza (bozza.origine: percorso, modello iniziale, nome di partenza di
// ogni dispositivo): anteprima e creazione lo mandano al server, che unisce i file (core/unione.py).
function elencoLab() {
  $('#edDaLabScelta').innerHTML = '<option value="">(scrivi la cartella)</option>'
    + (S.labs || []).map(n => `<option value="${esc(n)}"${n === S.nome ? ' selected' : ''}>${esc(n)}</option>`).join('');
}

// posizioni: quelle spostate a mano nella Topologia, poi il disegno salvato, poi la disposizione automatica
function posizioniDi(r) {
  const G = grafo(r.lab), tutte = p => p && G.nodes.every(n => p[n.id]);
  const mano = r.nome && (S.labs || []).includes(r.nome) ? mem('pos:' + r.nome) : null;
  if (tutte(mano)) return mano;
  if (tutte(r.posizioni)) return r.posizioni;
  return varianti(G)[0];
}

async function caricaDaLab() {
  const lab = $('#edDaLabScelta').value, cartella = $('#edDaLabCartella').value.trim();
  const esito = $('#edDaLabEsito');
  if (!lab && !cartella) { esito.innerHTML = '<div class="warnline">Scegli un lab o scrivi la cartella.</div>'; return; }
  if (!vuota(E.bozza) && !confirm('La bozza attuale verrà sostituita (si può tornare indietro con Annulla). Continuare?')) return;
  esito.innerHTML = '<div class="muted small">Leggo il lab…</div>';
  let r;
  // la cartella scritta vince sul lab scelto nell'elenco (che parte dal lab aperto)
  try { r = await azione(cartella ? {azione: 'lab_come_modello', cartella} : {azione: 'lab_come_modello', lab}); }
  catch (e) { esito.innerHTML = `<div class="koline" role="alert">${esc(e.message)}</div>`; return; }
  if (r.senza_ip.length) {
    esito.innerHTML = `<div class="koline" role="alert">Questo lab non si può caricare: interfacce senza indirizzo IPv4 (${esc(r.senza_ip.slice(0, 4).join(', '))}${r.senza_ip.length > 4 ? ', …' : ''}).
      Il generatore descrive solo interfacce con un IP (es. i data center spine/leaf degli esami non si rappresentano).</div>`;
    return;
  }
  const x = caricaLab(r, posizioniDi(r));
  E.vb = null; E.sel.clear(); E.anteprima = null; disegnaAnteprima();
  cambia(x.bozza);
  $('#edNome').value = '';
  E.differenze = x.differenze;
  esito.innerHTML = '';
  $('#edDaLabSez').hidden = true; $('#edDaLab').setAttribute('aria-expanded', 'false');
  avvisa(`Bozza partita da ${r.nome}: scrivi il nome del nuovo lab in alto. Con "Anteprima file" vedi i file con le righe che passano dal lab di partenza.`);
}

function dimenticaOrigine() {
  if (!confirm('Il nuovo lab verrà creato solo dalla bozza: le righe che l\'editor non mostra (policy, costi, ...) non passeranno. Continuare?')) return;
  const b = JSON.parse(JSON.stringify(E.bozza)); delete b.origine;
  E.differenze = null;
  cambia(b);
}

// parametro 'origine' per anteprima e creazione: nome di partenza dei dispositivi rinominati
function conOrigine() {
  const o = E.bozza.origine; if (!o) return {};
  const c = converti(E.bozza), nomi = {};
  for (const d of E.bozza.dispositivi) if (o.nomi[d.id] && c.nomi[d.id] && c.nomi[d.id] !== o.nomi[d.id]) nomi[c.nomi[d.id]] = o.nomi[d.id];
  return {origine: {cartella: o.percorso, modello: o.modello, nomi}};
}

function htmlOrigine() {
  const o = E.bozza.origine, el = $('#edOrigine');
  if (!o) { el.hidden = true; return; }
  el.hidden = false;
  const diff = E.differenze || [];
  el.innerHTML = `<b>Bozza partita da ${esc(o.nome)}</b> <span class="muted">(${esc(o.percorso)})</span>: le righe che l'editor non mostra passano nel nuovo lab; cambiano solo quelle che tocchi.
    ${diff.length ? `<div class="warnline">L'editor rappresenta in modo diverso:<ul>${diff.map(t => `<li>${esc(t)}</li>`).join('')}</ul>I file non cambiano per questo: cambiano solo se modifichi quella parte.</div>` : ''}
    <button type="button" class="ghost small" data-dimentica>Crea solo dalla bozza (senza le righe del lab di partenza)</button>`;
}

function htmlUnione(u) {
  const n = Object.keys(u.conservate).length;
  return `<div class="ed-origine small"><b>Dal lab di partenza</b> (${esc(u.percorso)}): righe che l'editor non mostra conservate in ${n} file${u.copiati.length ? `; file portati così come sono: ${u.copiati.map(esc).join(', ')}` : ''}${u.non_creati.length ? `; non creati perché il lab di partenza non li aveva: ${u.non_creati.map(esc).join(', ')}` : ''}.
    ${u.avvisi.length ? `<div class="warnline" role="alert">Da controllare:<ul>${u.avvisi.map(t => `<li>${esc(t)}</li>`).join('')}</ul></div>` : ''}</div>`;
}
const righeUnione = u => (u ? [`Dal lab di partenza: righe conservate in ${Object.keys(u.conservate).length} file, ${u.copiati.length} file portati così come sono.`].concat(u.avvisi.map(t => 'Da controllare: ' + t)) : []);

function aggiornaTutto() {
  const tutti = new Set([...E.bozza.dispositivi, ...E.bozza.lan, ...E.bozza.collegamenti, ...E.bozza.zone].map(x => x.id));
  E.sel = new Set([...E.sel].filter(id => tutti.has(id)));
  if (E.attesa && !tutti.has(E.attesa)) E.attesa = null;
  disegna();
  pannello();
  htmlOrigine();
}

function disegna() {
  const b = attuale();
  E.conv = converti(b);
  if (!E.vb) E.vb = riquadro(b);
  const svg = $('#edSvg');
  svg.setAttribute('viewBox', E.vb);
  const errori = E.conv.problemi.filter(p => p.gravita === 'errore').map(p => p.id)
    .concat((E.motoreMappati || []).filter(p => p.gravita === 'errore' && p.id).map(p => p.id));
  svg.innerHTML = svgBozza(b, E.conv, {sel: E.sel, problemi: new Set(errori),
    attesa: E.attesa, rettangolo: E.trascina && (E.trascina.tipo === 'rettangolo' || E.trascina.tipo === 'zona') ? E.trascina.r : null});
  svg.classList.toggle('ed-aggiungi', E.strumento !== 'seleziona' && E.strumento !== 'collega');
  svg.classList.toggle('ed-zona', ZONE.includes(E.strumento));
  svg.classList.toggle('ed-collega', E.strumento === 'collega');
}

function scegli(strumento) {
  E.strumento = strumento;
  E.attesa = null;
  document.querySelectorAll('#edStrumenti [data-strumento]').forEach(b => b.setAttribute('aria-pressed', b.dataset.strumento === strumento));
  $('#edAiuto').textContent = E.avviso || STRUMENTI[strumento].aiuto;
  disegna();
}

function avvisa(testo) {
  E.avviso = testo || '';
  $('#edAiuto').textContent = E.avviso || STRUMENTI[E.strumento].aiuto;
  $('#edAiuto').classList.toggle('warnline', !!E.avviso);
}

// ----------------------------------------------------------------------------- mouse

function puntoSvg(e) {
  const m = $('#edSvg').getScreenCTM().inverse();
  const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(m);
  return {x: p.x, y: p.y};
}

// elemento sotto il puntatore: {id, tipo: 'dispositivo'|'lan'|'link'|'coll'} oppure null
function bersaglio(e) {
  const g = e.target.closest('[data-el]');
  return g ? {id: g.dataset.el, tipo: g.dataset.tipo, angolo: g.dataset.angolo} : null;
}
const lanDelCollegamento = id => (E.bozza.collegamenti.find(c => c.id === id) || {}).lan;

function giu(e) {
  if (e.button !== 0) return;
  const p = puntoSvg(e), t = bersaglio(e);
  avvisa('');
  if (TIPI.includes(E.strumento)) {
    const r = aggiungiDispositivo(E.bozza, E.strumento, p.x, p.y, E.griglia);
    E.sel = new Set([r.id]);
    return cambia(r.bozza);
  }
  if (ZONE.includes(E.strumento)) {
    $('#edSvg').setPointerCapture(e.pointerId);
    E.trascina = {tipo: 'zona', p, r: {x: p.x, y: p.y, w: 0, h: 0}};
    return;
  }
  if (E.strumento === 'lan') {
    const r = aggiungiLan(E.bozza, p.x, p.y, E.griglia);
    E.sel = new Set([r.id]);
    return cambia(r.bozza);
  }
  if (E.strumento === 'collega') {
    if (!t) { E.attesa = null; return disegna(); }
    if (!E.attesa) {
      if (t.tipo !== 'dispositivo') { avvisa('Prima clicca il dispositivo da collegare.'); return; }
      E.attesa = t.id;
      return disegna();
    }
    const verso = t.tipo === 'coll' ? lanDelCollegamento(t.id) : t.id;
    const r = collega(E.bozza, E.attesa, verso);
    E.attesa = null;
    if (r.messaggio) avvisa(r.messaggio);
    if (r.id) E.sel = new Set([r.id]);
    return JSON.stringify(r.bozza) === JSON.stringify(E.bozza) ? aggiornaTutto() : cambia(r.bozza);
  }
  // seleziona
  $('#edSvg').setPointerCapture(e.pointerId);
  if (t && t.tipo === 'maniglia') {
    const z = E.bozza.zone.find(x => x.id === t.id);
    E.trascina = {tipo: 'ridimensiona', id: t.id, angolo: t.angolo, partenza: {x: z.x, y: z.y, w: z.w, h: z.h}};
    return;
  }
  if (t) {
    if (e.shiftKey) {
      E.sel.has(t.id) ? E.sel.delete(t.id) : E.sel.add(t.id);
      return aggiornaTutto();
    }
    if (!E.sel.has(t.id)) E.sel = new Set([t.id]);
    E.trascina = {tipo: 'muovi', p, partenza: posizioni(E.bozza, [...E.sel]), mosso: false};
    disegna();
    pannello();
    return;
  }
  if (e.shiftKey) E.trascina = {tipo: 'rettangolo', p, r: {x: p.x, y: p.y, w: 0, h: 0}};
  else E.trascina = {tipo: 'sfondo', x: e.clientX, y: e.clientY, vb: E.vb.split(' ').map(Number), scala: 1 / $('#edSvg').getScreenCTM().a, mosso: false};
}

function muovi(e) {
  const t = E.trascina;
  if (!t) return;
  if (t.tipo === 'sfondo') {
    if (Math.abs(e.clientX - t.x) + Math.abs(e.clientY - t.y) > 3) t.mosso = true;
    const [x, y, w, h] = t.vb;
    E.vb = [x - (e.clientX - t.x) * t.scala, y - (e.clientY - t.y) * t.scala, w, h].join(' ');
    $('#edSvg').setAttribute('viewBox', E.vb);
    return;
  }
  const p = puntoSvg(e);
  if (t.tipo === 'ridimensiona') {
    E.temp = ridimensionaZona(E.bozza, t.id, t.angolo, p, t.partenza, E.griglia);
    return disegna();
  }
  if (t.tipo === 'rettangolo' || t.tipo === 'zona') {
    t.r = {x: Math.min(p.x, t.p.x), y: Math.min(p.y, t.p.y), w: Math.abs(p.x - t.p.x), h: Math.abs(p.y - t.p.y)};
    return disegna();
  }
  if (Math.abs(p.x - t.p.x) + Math.abs(p.y - t.p.y) > 3) t.mosso = true;
  if (t.mosso) { E.temp = sposta(E.bozza, t.partenza, p.x - t.p.x, p.y - t.p.y, E.griglia); disegna(); }
}

function su() {
  const t = E.trascina;
  E.trascina = null;
  if (!t) return;
  if (t.tipo === 'sfondo') { if (!t.mosso && E.sel.size) { E.sel.clear(); aggiornaTutto(); } return; }
  if (t.tipo === 'ridimensiona') {
    if (E.temp) cambia(E.temp); else disegna();
    return;
  }
  if (t.tipo === 'zona') {
    const r = aggiungiZona(E.bozza, E.strumento, t.r, E.griglia);
    E.sel = new Set([r.id]);
    E.strumento = 'seleziona';
    scegli('seleziona');
    cambia(r.bozza);
    // il valore della zona si scrive subito
    const v = $('#edPannello [data-chiave^="valore:"]');
    if (v) { v.focus(); v.select(); }
    return;
  }
  if (t.tipo === 'rettangolo') {
    const r = t.r, b = E.bozza;
    for (const x of [...b.dispositivi, ...b.lan.filter(l => !l.punto)])
      if (x.x >= r.x && x.x <= r.x + r.w && x.y >= r.y && x.y <= r.y + r.h) E.sel.add(x.id);
    return aggiornaTutto();
  }
  if (t.mosso && E.temp) cambia(E.temp);
  else { E.temp = null; disegna(); }
}

function rotella(e) {
  e.preventDefault();
  const f = e.deltaY > 0 ? 1.15 : 1 / 1.15, p = puntoSvg(e), [x, y, w, h] = E.vb.split(' ').map(Number);
  E.vb = [p.x - (p.x - x) * f, p.y - (p.y - y) * f, w * f, h * f].join(' ');
  $('#edSvg').setAttribute('viewBox', E.vb);
}

// ----------------------------------------------------------------------------- tastiera

function scrivendo(el) {
  return el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName));
}

function tasto(e) {
  if (!aperto() || e.altKey || scrivendo(e.target)) return;
  const k = e.key.toLowerCase();
  if (e.ctrlKey || e.metaKey) {
    if (k === 'd' && E.sel.size) {           // duplica
      e.preventDefault();
      const r = duplica(E.bozza, [...E.sel]);
      E.sel = new Set(r.ids);
      cambia(r.bozza);
    } else if (k === 'a') {                  // seleziona tutto
      e.preventDefault();
      E.sel = new Set([...E.bozza.dispositivi, ...E.bozza.lan.filter(l => !l.punto), ...E.bozza.zone].map(x => x.id));
      aggiornaTutto();
    }
    return;
  }
  const freccia = {arrowleft: [-1, 0], arrowright: [1, 0], arrowup: [0, -1], arrowdown: [0, 1]}[k];
  if (freccia && E.sel.size) {
    e.preventDefault();
    cambia(sposta(E.bozza, posizioni(E.bozza, [...E.sel]), freccia[0] * GRIGLIA, freccia[1] * GRIGLIA, E.griglia));
    return;
  }
  if (k === 'f') { e.preventDefault(); E.vb = null; disegna(); return; }
  if (k === 'delete' || k === 'backspace') {
    if (E.sel.size) { e.preventDefault(); cambia(elimina(E.bozza, [...E.sel])); }
    return;
  }
  // Esc su Seleziona toglie anche la selezione
  if (k === 'escape' && E.strumento === 'seleziona' && E.sel.size) { E.sel.clear(); aggiornaTutto(); }
  const s = Object.keys(STRUMENTI).find(x => STRUMENTI[x].tasto.toLowerCase() === k);
  if (s) { e.preventDefault(); avvisa(''); scegli(s); }
}

// ----------------------------------------------------------------------------- pannello


function problemiDi(ids) {
  const ps = E.conv.problemi.filter(p => ids.includes(p.id)).concat((E.motoreMappati || []).filter(p => p.id && ids.includes(p.id)));
  return ps.length ? `<ul class="ed-problemi">${ps.map(p => `<li class="${p.gravita === 'errore' ? 'koline' : 'warnline'}">${p.gravita === 'errore' ? '✘' : '⚠'} ${esc(p.messaggio)}</li>`).join('')}</ul>` : '';
}

const TIPO = {router: 'router', host: 'host', www: 'server WWW', dns: 'server DNS'};

// menu dell'interfaccia di un collegamento: scegliere un altro numero scambia le due interfacce
function menuEth(idColl, etichetta) {
  const c = E.conv, col = E.bozza.collegamenti.find(x => x.id === idColl);
  const tutte = c.interfacce[col.dispositivo] || [], k = tutte.indexOf(idColl);
  return `<select data-chiave="eth:${idColl}" aria-label="${esc(etichetta)}">${tutte.map((_, n) => `<option value="${n}"${n === k ? ' selected' : ''}>eth${n}</option>`).join('')}</select>`;
}
// IP di un collegamento con la parte fissa della subnet già scritta: si scrive solo il numero finale
function campoIpCorto(idColl, etichetta) {
  const c = E.conv, col = E.bozza.collegamenti.find(x => x.id === idColl), r = leggiRete(c.subnet[col.lan]);
  const fissi = r ? Math.min(3, Math.floor(r.prefisso / 8)) : 0;
  const parti = ip => String(ip || '').split('/')[0].split('.');
  const fisso = r ? parti(c.subnet[col.lan]).slice(0, fissi).join('.') + '.' : '';
  const scritto = col.ip ? (r && leggiRete(col.ip) && leggiRete(col.ip).base === r.base ? parti(col.ip).slice(fissi).join('.') : col.ip) : '';
  const auto = c.ip[idColl] ? (r ? parti(c.ip[idColl]).slice(fissi).join('.') : c.ip[idColl]) : '';
  return `<span class="ed-ip">${fisso ? `<span class="ed-ip__fisso">${esc(fisso)}</span>` : ''}<input data-chiave="ip:${idColl}" value="${esc(scritto)}" placeholder="${esc(auto || 'automatico')}" aria-label="${esc(etichetta)}" size="${fisso ? 4 : 16}" autocomplete="off" spellcheck="false"></span>`;
}

function pannello() {
  const b = E.bozza, c = E.conv, el = $('#edPannello');
  const chiaveFuoco = document.activeElement && el.contains(document.activeElement) ? document.activeElement.dataset.chiave : null;
  const ids = [...E.sel];
  let h = '';
  if (ids.length > 1) {
    h = `<h3>${ids.length} elementi selezionati</h3><div class="btns"><button type="button" class="danger small" data-azione="elimina">Elimina (Canc)</button></div>`;
  } else if (ids.length === 1 && b.dispositivi.some(d => d.id === ids[0])) {
    const d = b.dispositivi.find(x => x.id === ids[0]), colls = c.interfacce[d.id] || [];
    h = `<div class="riga" style="margin:0 0 8px"><h3>${esc(c.nomi[d.id])}</h3><span class="badge">${TIPO[d.tipo]}</span></div>`;
    h += campo('Nome', `nome:${d.id}`, d.nome, `automatico: ${c.nomi[d.id]}`);
    if (d.tipo === 'router') {
      const r = c.modello.routers[c.nomi[d.id]] || {protocols: []}, z = c.zone[d.id] || {};
      if (z.as && !r.protocols.includes('bgp')) h += `<p class="small muted">AS ${esc(z.as)}: router interno, senza BGP (cambia sotto se serve).</p>`;
      const det = {bgp: `AS ${z.as}${c.bgpConfine[d.id] ? ', router di confine' : ''}`, ospf: r.ospf_aree ? 'router di confine: ' + [...new Set(Object.values(r.ospf_aree))].join(', ') : `area ${r.ospf_area}${r.ospf_area_stub ? ' stub' : ''}`, rip: 'zona RIP', statico: 'rotte statiche'};
      h += `<p class="small"><b>Protocolli</b> (dalle zone): ${r.protocols.length ? r.protocols.map(p => `${p.toUpperCase()} <span class="muted">(${esc(det[p] || '')})</span>`).join(', ') : '<span class="muted">nessuno: mettilo in un riquadro AS, in una zona RIP o una sua LAN in un\'area OSPF</span>'}</p>`;
    }
    h += `<h4 class="ed-sotto">Interfacce</h4>`;
    if (!colls.length) h += '<p class="small muted">Nessun collegamento: usa lo strumento Collega (L).</p>';
    else h += '<table class="ed-intf"><tr><th>Interf.</th><th>LAN</th><th>IP</th><th></th></tr>' + colls.map((id, k) => {
      const col = b.collegamenti.find(x => x.id === id);
      return `<tr><td>${menuEth(id, `Interfaccia del collegamento con la LAN ${c.nomiLan[col.lan]}`)}</td><td><button type="button" class="ghost small" data-vai="${esc(col.lan)}">${esc(c.nomiLan[col.lan])}</button></td>
        <td>${campoIpCorto(id, `IP di eth${k}`)}</td>
        <td class="ed-ord"><button type="button" class="ghost small" data-togli="${id}" aria-label="Togli il collegamento eth${k}">✕</button></td></tr>`;
    }).join('') + '</table><p class="small muted">Scegli eth0, eth1... per scambiare le interfacce. IP: basta il numero finale; vuoto = automatico.</p>';
    if (d.tipo === 'router') h += htmlRouter(d, c, E.motore && E.motore.completato);
    else h += `<h4 class="ed-sotto">Rete</h4>` + htmlGateway(d, c);
    if (d.tipo === 'dns') h += `<h4 class="ed-sotto">DNS</h4>` + htmlDns(d, c);
    h += problemiDi([d.id, ...colls]);
    h += '<div class="btns"><button type="button" class="danger small" data-azione="elimina">Elimina dispositivo</button></div>';
  } else if (ids.length === 1 && b.lan.some(l => l.id === ids[0])) {
    const l = b.lan.find(x => x.id === ids[0]), ms = b.collegamenti.filter(x => x.lan === l.id);
    h = `<div class="riga" style="margin:0 0 8px"><h3>LAN ${esc(c.nomiLan[l.id])}</h3><span class="badge">${l.punto ? 'link diretto' : 'nodo LAN'}</span></div>`;
    h += campo('Nome', `nome:${l.id}`, l.nome, `automatico: ${c.nomiLan[l.id]}`);
    h += campo('Subnet', `subnet:${l.id}`, l.subnet, c.subnet[l.id] && !l.subnet ? `dagli IP: ${c.subnet[l.id]}` : 'es. 10.0.0.0/30');
    h += '<p class="small muted">Cambiando la subnet gli IP scritti a mano tengono la stessa parte host.</p>';
    const ar = c.zone[l.id];
    h += `<p class="small"><b>Area OSPF:</b> ${ar ? esc(ar.valore) + (ar.stub ? ' stub' : '') : '<span class="muted">nessuna</span>'}</p>`;
    h += `<h4 class="ed-sotto">Dispositivi</h4>`;
    h += ms.length ? `<table class="ed-intf"><tr><th>Dispositivo</th><th>Interf.</th><th>IP</th></tr>${ms.map(m => `<tr>
        <td><button type="button" class="ghost small" data-vai="${esc(m.dispositivo)}">${esc(c.nomi[m.dispositivo])}</button></td>
        <td>${menuEth(m.id, `Interfaccia di ${c.nomi[m.dispositivo]} su questa LAN`)}</td>
        <td>${campoIpCorto(m.id, `IP di ${c.nomi[m.dispositivo]} su questa LAN`)}</td></tr>`).join('')}</table>
      <p class="small muted">IP: basta il numero finale; vuoto = automatico.</p>` : '<p class="muted small">nessuno</p>';
    h += problemiDi([l.id, ...ms.map(m => m.id)]);
    h += '<div class="btns"><button type="button" class="danger small" data-azione="elimina">Elimina LAN</button></div>';
  } else if (ids.length === 1 && b.zone.some(x => x.id === ids[0])) {
    const z = b.zone.find(x => x.id === ids[0]), ms = c.membri[z.id] || [];
    h = `<div class="riga" style="margin:0 0 8px"><h3>${NOME_ZONA[z.tipo]}</h3></div>`;
    if (z.tipo === 'as') {
      h += campo('Numero AS', `valore:${z.id}`, z.valore, 'es. 100', 'inputmode="numeric"');
      h += `<div class="prop__campo"><label for="edc-bgpzona">BGP su</label><select id="edc-bgpzona" data-chiave="bgpzona:${z.id}">
        <option value="confine"${z.bgp === 'tutti' ? '' : ' selected'}>solo i router di confine</option>
        <option value="tutti"${z.bgp === 'tutti' ? ' selected' : ''}>tutti i router (iBGP)</option></select>
        <p class="prop__aiuto">Di confine = collegati a un router fuori da questo AS. Ogni router può fare eccezione dal suo pannello.</p></div>`;
      h += `<div class="btns"><button type="button" class="ghost small" data-azione="rinomina-as" data-id="${esc(z.id)}">Rinomina i router come as${esc(String(z.valore || '?').trim() || '?')}r1, as${esc(String(z.valore || '?').trim() || '?')}r2…</button></div>`;
    }
    if (z.tipo === 'ospf') {
      h += campo('Area', `valore:${z.id}`, z.valore, 'es. 0.0.0.0 o 1.1.1.1');
      h += `<label class="scelta"><input type="checkbox" data-chiave="stub:${z.id}"${z.stub ? ' checked' : ''}> area stub</label>`;
    }
    h += `<p class="small muted">${z.tipo === 'ospf' ? 'Contiene le LAN il cui nodo (o il punto di mezzo del link diretto) sta nel rettangolo.' : 'Contiene i router il cui centro sta nel rettangolo.'} Si ridimensiona dagli angoli.</p>`;
    h += `<h4 class="ed-sotto">${z.tipo === 'ospf' ? 'LAN' : 'Router'}</h4><ul class="ed-membri">${ms.map(id => `<li><button type="button" class="ghost small" data-vai="${esc(id)}">${esc(c.nomi[id] || 'LAN ' + c.nomiLan[id])}</button>${(c.abr || []).includes(id) ? ' <span class="badge">ABR</span>' : ''}</li>`).join('') || '<li class="muted small">nessuno</li>'}</ul>`;
    if (z.tipo === 'ospf') {
      const conf = b.dispositivi.filter(d => (c.abr || []).includes(d.id) && (c.interfacce[d.id] || []).some(id => { const col = b.collegamenti.find(x => x.id === id); return ms.includes(col.lan); }));
      if (conf.length) h += `<p class="small">Router di confine: ${conf.map(d => esc(c.nomi[d.id])).join(', ')}</p>`;
    }
    h += problemiDi([z.id]);
    h += '<div class="btns"><button type="button" class="danger small" data-azione="elimina">Elimina zona</button></div>';
  } else if (ids.length === 1 && b.collegamenti.some(x => x.id === ids[0])) {
    const col = b.collegamenti.find(x => x.id === ids[0]), k = (c.interfacce[col.dispositivo] || []).indexOf(col.id);
    h = `<div class="riga" style="margin:0 0 8px"><h3>${esc(c.nomi[col.dispositivo])} eth${k}</h3><span class="badge">collegamento</span></div>
      <p class="small">LAN <button type="button" class="ghost small" data-vai="${esc(col.lan)}">${esc(c.nomiLan[col.lan])}</button>
      dispositivo <button type="button" class="ghost small" data-vai="${esc(col.dispositivo)}">${esc(c.nomi[col.dispositivo])}</button></p>`;
    h += `<div class="prop__campo"><label>Interfaccia</label>${menuEth(col.id, 'Interfaccia')}</div>`;
    h += `<div class="prop__campo"><label>IP</label>${campoIpCorto(col.id, 'IP')}</div>`;
    h += problemiDi([col.id]);
    h += '<div class="btns"><button type="button" class="danger small" data-azione="elimina">Togli il collegamento</button></div>';
  } else {
    const n = t => b.dispositivi.filter(d => d.tipo === t).length;
    h = `<h3>Lab</h3><p class="small muted">${n('router')} router, ${n('host')} host, ${n('www')} WWW, ${n('dns')} DNS, ${b.lan.length} LAN.</p>`;
    h += htmlLab(b, c);
    const mot = E.motoreMappati || [];
    if (E.motore && E.motore.errore) h += `<p class="small warnline">Controlli del motore non disponibili: ${esc(E.motore.errore)}</p>`;
    else if (E.motore) {
      const me = mot.filter(p => p.gravita === 'errore').length, ma = mot.length - me;
      h += `<h4 class="ed-sotto">Controlli del motore</h4>` + (mot.length
        ? `<p class="small">${me ? `<span class="koline">${me} errori</span>` : ''}${me && ma ? ' · ' : ''}${ma ? `<span class="warnline">${ma} avvisi</span>` : ''}</p>
          <ul class="ed-problemi">${mot.map(p => `<li><button type="button" class="ghost small ed-vai"${p.id ? ` data-vai="${esc(p.id)}"` : ' disabled'}><span class="${p.gravita === 'errore' ? 'koline' : 'warnline'}">${p.gravita === 'errore' ? '✘' : '⚠'}</span> <code>${esc(p.campo)}</code> ${esc(p.messaggio)}</button></li>`).join('')}</ul>`
        : '<p class="small okline">✔ Nessun problema per il motore.</p>');
    }
    const err = c.problemi.filter(p => p.gravita === 'errore').length, avv = c.problemi.length - err;
    if (c.problemi.length) h += `<h4 class="ed-sotto">Problemi del disegno</h4><p class="small">${err ? `<span class="koline">${err} errori</span>` : ''}${err && avv ? ' · ' : ''}${avv ? `<span class="warnline">${avv} avvisi</span>` : ''}</p>
      <ul class="ed-problemi">${c.problemi.map(p => `<li><button type="button" class="ghost small ed-vai" data-vai="${esc(p.id)}"><span class="${p.gravita === 'errore' ? 'koline' : 'warnline'}">${p.gravita === 'errore' ? '✘' : '⚠'}</span> ${esc(p.messaggio)}</button></li>`).join('')}</ul>`;
    h += `<h4 class="ed-sotto">Tasti</h4><dl class="ed-tasti"><dt>R H W D</dt><dd>router, host, WWW, DNS</dd><dt>N</dt><dd>nodo LAN</dd><dt>L</dt><dd>collega</dd><dt>A I O</dt><dd>riquadro AS, zona RIP, area OSPF</dd>
      <dt>Esc</dt><dd>seleziona</dd><dt>Canc</dt><dd>elimina</dd><dt>Ctrl+Z / Ctrl+Y</dt><dd>annulla / ripeti</dd>
      <dt>Ctrl+D</dt><dd>duplica</dd><dt>Ctrl+A</dt><dd>seleziona tutto</dd><dt>Frecce</dt><dd>sposta la selezione</dd><dt>F</dt><dd>adatta la vista</dd></dl>`;
  }
  el.innerHTML = h;
  segnaCampi();
  if (chiaveFuoco) { const x = el.querySelector(`[data-chiave="${CSS.escape(chiaveFuoco)}"]`); if (x) x.focus(); }
}

function cambioCampo(e) {
  const k = e.target.dataset.chiave;
  if (!k) return;
  const [campoNome, id, ...resto] = k.split(':');
  const valore = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
  const nuova = campoNome === 'eth' ? impostaInterfaccia(E.bozza, id, valore)
    : ['nome', 'ip', 'subnet', 'valore', 'stub', 'bgpzona'].includes(campoNome) ? imposta(E.bozza, id, campoNome, valore)
      : impostaProprieta(E.bozza, id, campoNome, valore, resto.map(x => (/^\d+$/.test(x) ? Number(x) : x)));
  // il pannello si ridisegna dopo che il focus si è spostato sul campo successivo (Tab)
  if (JSON.stringify(nuova) !== JSON.stringify(E.bozza)) { E.bozza = nuova; E.storia.fai(nuova); salvaBozza(); disegna(); setTimeout(pannello, 0); controllaMotore(); }
}

function cliccaPannello(e) {
  const b = e.target.closest('button');
  if (!b) return;
  if (b.dataset.azione === 'elimina') return cambia(elimina(E.bozza, [...E.sel]));
  if (b.dataset.elenco) {
    const indici = String(b.dataset.indici || '').split(',').filter(x => x !== '').map(Number);
    return cambia(modificaElenco(E.bozza, b.dataset.id, b.dataset.elenco, b.dataset.op, indici));
  }
  if (b.dataset.azione === 'proponi') {
    const r = proponiSubnet(E.bozza);
    avvisa(r.messaggio);
    return r.assegnate ? cambia(r.bozza) : undefined;
  }
  if (b.dataset.vai) { E.sel = new Set([b.dataset.vai]); return aggiornaTutto(); }
  if (b.dataset.azione === 'rinomina-as') {
    const r = rinominaPerAs(E.bozza, b.dataset.id);
    avvisa(r.messaggio);
    return cambia(r.bozza);
  }
  if (b.dataset.togli) return cambia(elimina(E.bozza, [b.dataset.togli]));
}

// ----------------------------------------------------------------------------- anteprima e creazione (4.5)

function disegnaAnteprima() {
  const r = E.anteprima, sez = $('#edAnteprima');
  if (!r) { sez.hidden = true; return; }
  sez.hidden = false;
  const errori = r.errori || [];
  $('#edAntErrori').innerHTML = errori.length
    ? `<div class="conflitto" role="alert"><b>Il lab non si può ancora creare: ${errori.length} ${errori.length === 1 ? 'errore' : 'errori'}.</b>
       <ul class="ed-problemi">${errori.map(p => { const el = elementoDelCampo(E.conv, p.campo); return `<li><button type="button" class="ghost small ed-vai"${el ? ` data-vai="${esc(el.id)}"` : ' disabled'}>✘ <code>${esc(p.campo)}</code> ${esc(p.messaggio)}</button></li>`; }).join('')}</ul></div>`
    : '';
  if (r.unione) $('#edAntErrori').innerHTML += htmlUnione(r.unione);
  const file = r.file || [];
  $('#edAntConta').textContent = file.length ? `${file.length} file` : '';
  if (!file.some(f => f.file === E.fileAperto)) E.fileAperto = file.length ? file[0].file : null;
  $('#edAntFile').innerHTML = file.map(f => `<li><button type="button" data-file="${esc(f.file)}"${f.file === E.fileAperto ? ' aria-current="true"' : ''}>${esc(f.file)}</button></li>`).join('');
  const aperto = file.find(f => f.file === E.fileAperto);
  $('#edAntTesto').textContent = aperto ? aperto.testo : '';
  $('#edAntTesto').closest('.ed-ant-corpo').hidden = !file.length;
}

async function anteprima() {
  const b = $('#edAnteprimaBtn');
  b.disabled = true;
  try {
    const r = await azione(Object.assign({azione: 'anteprima_lab', nome: (E.bozza.nome || '').trim() || 'anteprima', modello: converti(E.bozza).modello}, conOrigine()));
    E.anteprima = r;
    disegnaAnteprima();
    $('#edAnteprima').scrollIntoView({block: 'nearest'});
  } catch (e) { avvisa('Anteprima non riuscita: ' + e.message); }
  finally { b.disabled = false; }
}

// posizioni e zone per la Topologia del lab creato (.labgenerator/<lab>/disegno.json)
function disegnoDellaBozza() {
  const c = converti(E.bozza), posizioni = {};
  for (const d of E.bozza.dispositivi) posizioni['d:' + c.nomi[d.id]] = {x: d.x, y: d.y};
  for (const l of E.bozza.lan.filter(x => !x.punto)) posizioni['l:' + c.nomiLan[l.id]] = {x: l.x, y: l.y};
  return {versione: VERSIONE, posizioni, zone: E.bozza.zone.map(({tipo, valore, stub, x, y, w, h}) => ({tipo, valore, stub: !!stub, x, y, w, h}))};
}

async function crea(sovrascrivi = false) {
  const nome = (E.bozza.nome || '').trim();
  if (!/^[a-z0-9_-]+$/.test(nome)) {
    avvisa('Scrivi il nome del lab in alto: minuscole, cifre, _ e - (es. rossimario).');
    $('#edNome').setAttribute('aria-invalid', 'true');
    $('#edNome').focus();
    return;
  }
  $('#edNome').removeAttribute('aria-invalid');
  const b = $('#edCrea');
  b.disabled = true;
  let r;
  try { r = await azione(Object.assign({azione: 'crea_lab', nome, modello: converti(E.bozza).modello, disegno: disegnoDellaBozza(), sovrascrivi}, conOrigine())); }
  catch (e) { avvisa('Creazione non riuscita: ' + e.message); b.disabled = false; return; }
  b.disabled = false;
  if (r.esiste) {
    if (confirm(r.messaggio)) return crea(true);
    return;
  }
  if (!r.creato) {
    E.anteprima = {errori: r.errori || [], file: []};
    disegnaAnteprima();
    avvisa('Il lab non è stato creato: correggi gli errori indicati.');
    return;
  }
  outInizio('Crea laboratorio ' + nome);
  outScrivi(['Creato: ' + r.percorso].concat(r.copia ? ['Il lab di prima è nella copia di sicurezza: ' + r.copia] : [], r.messaggi || [], righeUnione(r.unione)));
  outFine(true, 'completato');
  // il disegno ora è il lab: l'editor riparte da un foglio vuoto (annullabile con Ctrl+Z)
  E.anteprima = null; disegnaAnteprima();
  E.vb = null; E.sel.clear();
  cambia(nuovaBozza(''));
  $('#edNome').value = '';
  await caricaLabs();
  await apriLab(nome);
}

function nuovaBozzaVuota() {
  if (!vuota(E.bozza) && !confirm('Ricominciare da un foglio vuoto? (si può tornare indietro con Annulla)')) return;
  E.vb = null; E.sel.clear(); E.anteprima = null; disegnaAnteprima();
  cambia(nuovaBozza(''));
  $('#edNome').value = '';
}

function esporta() {
  const testo = JSON.stringify(E.bozza, null, 1) + '\n';
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([testo], {type: 'application/json'}));
  a.download = (E.bozza.nome || 'bozza') + '.json';
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function importa(file) {
  const r = new FileReader();
  r.onload = () => {
    let b = null;
    try { b = JSON.parse(r.result); } catch (e) { /* sotto */ }
    if (!bozzaValida(b)) { avvisa('Questo file non è una bozza dell\'editor (versione ' + VERSIONE + ').'); return; }
    E.vb = null; E.sel.clear(); E.anteprima = null; disegnaAnteprima();
    cambia(b);
    $('#edNome').value = b.nome || '';
    avvisa(`Bozza importata da ${file.name}.`);
  };
  r.readAsText(file);
}

// ----------------------------------------------------------------------------- apertura

let pronto = false;

function prepara() {
  if (pronto) return;
  pronto = true;
  E.griglia = mem('editor:griglia') !== false;
  const salvata = mem(CHIAVE_BOZZA);
  if (bozzaValida(salvata) && !vuota(salvata)) { E.bozza = salvata; E.ripresa = true; }
  E.storia = new Storia(E.bozza);
  creaBarraStoria($('#edStoria'), E.storia, s => { E.temp = null; E.bozza = s; salvaBozza(); aggiornaTutto(); controllaMotore(); $('#edNome').value = s.nome || ''; }, aperto);
  $('#edStrumenti').innerHTML = Object.entries(NOMI_STRUMENTI)
    .map(([k, t]) => `<button type="button" class="ghost small" data-strumento="${k}" aria-pressed="false" aria-keyshortcuts="${STRUMENTI[k].tasto === 'Escape' ? 'Escape' : STRUMENTI[k].tasto.toUpperCase()}">${t} <kbd>${STRUMENTI[k].tasto === 'Escape' ? 'Esc' : STRUMENTI[k].tasto.toUpperCase()}</kbd></button>`).join('');
  $('#edStrumenti').addEventListener('click', e => { const b = e.target.closest('[data-strumento]'); if (b) { avvisa(''); scegli(b.dataset.strumento); } });
  $('#edGriglia').checked = E.griglia;
  $('#edGriglia').onchange = () => { E.griglia = $('#edGriglia').checked; mem('editor:griglia', E.griglia); };
  $('#edAdatta').onclick = () => { E.vb = null; disegna(); };
  $('#edNome').onchange = () => cambia(imposta(E.bozza, null, 'nome_lab', $('#edNome').value));
  const svg = $('#edSvg');
  svg.addEventListener('pointerdown', giu);
  svg.addEventListener('pointermove', muovi);
  svg.addEventListener('pointerup', su);
  svg.addEventListener('pointercancel', su);
  svg.addEventListener('wheel', rotella, {passive: false});
  $('#edPannello').addEventListener('change', cambioCampo);
  $('#edPannello').addEventListener('click', cliccaPannello);
  document.addEventListener('keydown', tasto);
  $('#edChiudi').onclick = chiudiEditor;
  $('#edAnteprimaBtn').onclick = anteprima;
  $('#edCrea').onclick = () => crea(false);
  $('#edNuova').onclick = nuovaBozzaVuota;
  $('#edDaLab').onclick = () => { const s = $('#edDaLabSez'); s.hidden = !s.hidden; $('#edDaLab').setAttribute('aria-expanded', String(!s.hidden)); if (!s.hidden) elencoLab(); };
  $('#edDaLabCarica').onclick = caricaDaLab;
  $('#edDaLabCartella').addEventListener('input', () => { if ($('#edDaLabCartella').value.trim()) $('#edDaLabScelta').value = ''; });
  $('#edDaLabScelta').addEventListener('change', () => { if ($('#edDaLabScelta').value) $('#edDaLabCartella').value = ''; });
  $('#edOrigine').addEventListener('click', e => { if (e.target.closest('[data-dimentica]')) dimenticaOrigine(); });
  $('#edEsporta').onclick = esporta;
  $('#edImporta').onclick = () => $('#edFile').click();
  $('#edFile').onchange = () => { const f = $('#edFile').files[0]; if (f) importa(f); $('#edFile').value = ''; };
  $('#edAntChiudi').onclick = () => { E.anteprima = null; disegnaAnteprima(); };
  $('#edAnteprima').addEventListener('click', e => {
    const f = e.target.closest('[data-file]');
    if (f) { E.fileAperto = f.dataset.file; disegnaAnteprima(); return; }
    const v = e.target.closest('[data-vai]');
    if (v) { E.sel = new Set([v.dataset.vai]); aggiornaTutto(); }
  });
}

export function apriEditor() {
  prepara();
  $('#vuoto').hidden = true;
  $('#vista').hidden = true;
  $('#editor').hidden = false;
  history.replaceState(null, '', '#nuovo');
  $('#edNome').value = E.bozza.nome || '';
  scegli(E.strumento);
  aggiornaTutto();
  controllaMotore();
  if (E.ripresa) { avvisa('Bozza ripresa dal browser: continua da dove eri rimasto (Nuova bozza per ricominciare).'); E.ripresa = false; }
}

export function chiudiEditor() {
  if (!aperto()) return;
  $('#editor').hidden = true;
  if (S.lab) { $('#vista').hidden = false; history.replaceState(null, '', '#lab=' + encodeURIComponent(S.nome) + '&tab=' + S.tab); }
  else { $('#vuoto').hidden = false; history.replaceState(null, '', '#'); }
}
