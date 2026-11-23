// Modalità Modifica della Topologia (fase 5): ogni gesto apre un'operazione del motore (la stessa
// calcola_X del terminale) con il modulo, l'anteprima delle righe e "Applica". Ogni modifica
// applicata finisce nella storia del lab e si annulla con "Annulla modifica" (anche quelle fatte
// dal terminale); per tornare indietro di molti passi ci sono le copie di sicurezza.
import { $, azione, esc, mem, S } from './comune.js';
import { htmlAnteprima, htmlConflitto } from './componenti/diff.js';
import { creaPannello } from './componenti/proprieta.js';
import { dispositivo, lato } from './dispositivo.js';
import { apriLab, scheda } from './main.js';
import { gesti, ridisegna } from './topologia.js';

const AIUTO = 'Modifica: clic su interfacce, LAN, scritte degli AS e dispositivi per le loro azioni · trascina per spostare la vista';
let aiutoNormale = null;

// ---------- storia e pulsante "Annulla modifica" ----------
export async function aggiornaStoria() {
  try { S.storia = (await azione({azione: 'opzioni', operazione: 'annulla'})).opzioni || []; } catch (e) { S.storia = []; }
  const b = $('#bAnnulla'), u = S.storia[0];
  b.disabled = !u;
  b.title = u ? `Annulla: ${u.titolo} (${u.ora})` : 'Nessuna modifica da annullare';
}

export function esciModifica() { S.modifica = false; S.op = null; S.esito = null; segnaPulsante(); }
function segnaPulsante() {
  $('#bModifica').setAttribute('aria-pressed', String(!!S.modifica));
  const a = document.querySelector('#t-topo .toolbar__aiuto');
  if (a) { if (aiutoNormale == null) aiutoNormale = a.textContent; a.textContent = S.modifica ? AIUTO : aiutoNormale; }
}
function accendi(on) {
  S.modifica = on; S.op = null; S.esito = null; segnaPulsante(); ridisegna(); lato();
}
$('#bModifica').onclick = () => accendi(!S.modifica);
$('#bAnnulla').onclick = () => {
  if (!S.storia || !S.storia.length) return;
  if (!S.modifica) { S.modifica = true; segnaPulsante(); ridisegna(); }
  apriOperazione({operazione: 'annulla', titolo: 'Annulla l\'ultima modifica',
    spiegazione: `Ultima modifica: ${S.storia[0].titolo} (${S.storia[0].ora}). I file tornano com'erano prima.`, subito: true});
};

// ---------- operazione: modulo, anteprima, applica ----------
// conf = {operazione, titolo, spiegazione, fissi: {parametri già scelti}, schema, valori,
//         prepara: valori del modulo -> parametri (può lanciare Error con il messaggio per l'utente),
//         controlla: valori -> {campo: errore}, subito: anteprima senza modulo,
//         avanti: valori -> conf del passo dopo (al posto di "Anteprima"),
//         corpo + leggi: html del modulo fatto a mano e funzione che ne legge i valori,
//         poi: dopo l'applica -> conf del passo successivo proposto (es. il lato opposto), {menu}, o null,
//         salta: conf (o {menu}) del passo dopo senza applicare questo: pulsante "Salta"}
// Un menu di azioni: apriMenu({titolo, spiegazione, voci: [{testo, fai, aiuto, pericolo}]}).
export function apriOperazione(conf) {
  S.op = {conf, ant: null, par: null};
  S.esito = null;
  lato();
  if (conf.subito) anteprima();
}
function apriPasso(p) { if (p.menu) apriMenu(p.menu); else apriOperazione(p); }
export function apriMenu(menu) {
  S.op = {menu};
  S.esito = null;
  lato();
}

function testata(t, spiegazione) {
  return `<div class="riga" style="margin:0"><h3>${esc(t)}</h3><div class="sp"></div><a href="#" data-mod-azione="indietro">indietro</a></div>
    ${spiegazione ? `<p class="small muted">${esc(spiegazione)}</p>` : ''}`;
}

function disegnaOp(el) {
  if (S.op.menu) {
    const m = S.op.menu;
    el.innerHTML = (S.op.esito ? htmlEsito(S.op.esito) : '') + testata(m.titolo, m.spiegazione) + `<div class="menu-mod">${m.voci.map((v, i) =>
      `<button type="button" class="${v.pericolo ? 'danger' : 'ghost'} small" data-mod-voce="${i}"${v.aiuto ? ` title="${esc(v.aiuto)}"` : ''}>${esc(v.testo)}</button>`).join('')}</div>`;
    return;
  }
  const {conf} = S.op;
  el.innerHTML = (S.op.esito ? htmlEsito(S.op.esito) : '') + testata(conf.titolo, conf.spiegazione) + `<div id="opForm">${conf.corpo || ''}</div>
    <div class="btns">${conf.subito ? '' : `<button type="button" class="primario" data-mod-azione="anteprima">${conf.avanti ? 'Avanti' : 'Anteprima'}</button>`}${conf.salta ? '<button type="button" class="ghost" data-mod-azione="salta">Salta</button>' : ''}</div>
    <div id="opRis" aria-live="polite"></div>`;
  if (!conf.corpo && conf.schema && conf.schema.length) S.op.pannello = creaPannello($('#opForm'), {schema: conf.schema, valori: conf.valori || {}});
}

async function anteprima() {
  const op = S.op; if (!op || op.menu) return;
  let valori = {};
  if (op.pannello) {
    const err = Object.assign(op.pannello.controlla(), op.conf.controlla ? op.conf.controlla(op.pannello.valori()) : {});
    if (!op.pannello.mostraErrori(err)) return;
    valori = op.pannello.valori();
  } else if (op.conf.leggi) valori = op.conf.leggi();
  if (op.conf.avanti) {
    try { const dopo = await op.conf.avanti(valori); if (dopo) { apriOperazione(dopo); S.op.da = op; } }
    catch (e) { $('#opRis').innerHTML = `<div class="koline" role="alert">${esc(e.message)}</div>`; }
    return;
  }
  try { op.par = Object.assign({}, op.conf.fissi || {}, op.conf.prepara ? op.conf.prepara(valori) : valori); }
  catch (e) { $('#opRis').innerHTML = `<div class="koline" role="alert">${esc(e.message)}</div>`; return; }
  const ris = $('#opRis');
  ris.innerHTML = '<div class="muted small">Calcolo l\'anteprima…</div>';
  try {
    op.ant = await azione({azione: 'anteprima', operazione: op.conf.operazione, parametri: op.par});
    ris.innerHTML = htmlAnteprima(op.ant) + (op.ant.vuoto ? '' :
      `<div class="btns"><button type="button" class="primario" data-mod-azione="applica">Applica</button></div>
       <p class="small muted">Prima di scrivere viene fatta una copia di sicurezza del lab; la modifica si potrà annullare.</p>`);
  } catch (e) {
    ris.innerHTML = `<div class="koline" role="alert">${esc(e.message)}</div>` +
      (op.conf.operazione === 'annulla' ? '<div class="btns"><button type="button" data-mod-azione="copie">Copie di sicurezza</button></div>' : '');
  }
}

async function applica(bottone) {
  const op = S.op; if (!op || !op.ant) return;
  bottone.disabled = true;
  try {
    const r = await azione({azione: 'applica', operazione: op.conf.operazione, parametri: op.par,
      impronte: op.ant.impronte, firma: op.ant.firma});
    // rinomina: il dispositivo resta dov'era sul disegno (anche nelle posizioni spostate a mano)
    if (r.scritto && op.conf.operazione === 'rinomina' && S.pos && S.pos['d:' + op.par.vecchio]) {
      S.pos['d:' + op.par.nuovo] = S.pos['d:' + op.par.vecchio]; delete S.pos['d:' + op.par.vecchio];
      if (mem('pos:' + S.nome)) mem('pos:' + S.nome, S.pos);
    }
    S.op = null; S.sel = null;        // l'esito si legge nel pannello della modalità Modifica
    S.esito = r.scritto ? {ok: true, titolo: r.titolo, file: r.file, copia: r.copia, messaggi: r.messaggi || [], operazione: op.conf.operazione, par: op.par,
      nuovi: r.nuovi || [], risolti: r.risolti || [], annullato: op.conf.operazione === 'annulla'}
      : {avviso: r.vuoto || 'Nessuna modifica.'};
    await aggiornaStoria();
    await apriLab(S.nome, true);     // ridisegna, rilegge i file e ripassa da lato()
    if (r.scritto && op.conf.poi) {  // passo successivo proposto, con l'esito di questo sopra
      const esito = S.esito, dopo = await op.conf.poi().catch(() => null);
      if (dopo) { apriPasso(dopo); S.op.esito = esito; S.op.da = null; lato(); }
    }
  } catch (e) {
    bottone.disabled = false;
    $('#opRis').innerHTML = e.codice === 409 ? htmlConflitto(e) + `<div class="btns"><button type="button" data-mod-azione="anteprima">Rifai l'anteprima</button></div>`
      : `<div class="koline" role="alert">${esc(e.message)}</div>`;
  }
}

// ---------- pannello iniziale della modalità Modifica ----------
function htmlEsito(x) {
  if (!x) return '';
  if (x.avviso) return `<div class="warnline" role="status">${esc(x.avviso)}</div>`;
  if (x.ripristino) return `<div class="okline" role="status">Lab ripristinato com'era il ${esc(x.quando)}. Lo stato di prima è salvato in <code>${esc(x.copia_di_prima)}</code>.</div>`;
  return `<div class="esito-mod" role="status"><div class="okline">${esc(x.annullato ? 'Annullato' : 'Fatto')}: ${esc(x.titolo)}</div>
    <div class="small muted">File scritti: ${x.file.map(f => `<code>${esc(f)}</code>`).join(', ')}</div>
    ${x.messaggi.length ? `<div class="small">${x.messaggi.map(m => esc(m.replace(/^\s*(✅|❌|⚠️)\s*/u, ''))).join('<br>')}</div>` : ''}
    ${x.nuovi.length ? `<div class="warnline small">Avvisi nuovi: ${x.nuovi.map(esc).join('; ')}</div>` : ''}
    ${x.risolti.length ? `<div class="okline small">Avvisi risolti: ${x.risolti.map(esc).join('; ')}</div>` : ''}
    ${x.annullato ? '' : htmlTestSuggerito(x)}</div>`;
}

// ---------- test suggerito dopo la modifica (fase 6) ----------
const TEST = {
  percorso: ['policy', 'cpp', 'costo_ospf', 'togli_costo_ospf', 'auto_cost'],
  sessioni: ['network_bgp', 'ibgp', 'default_originate', 'default_igp', 'loopback', 'redistribuzione', 'redistribuzione_route_map', 'aggiungi_protocollo', 'togli_protocollo', 'as'],
  ping: ['gateway', 'ip_interfaccia', 'sposta_interfaccia', 'rinumera_lan', 'aggiungi_dispositivo', 'aggiungi_interfaccia', 'togli_interfaccia', 'togli_dispositivo'],
  risoluzione: ['resolver', 'delega_dns'],
};
const NOME_TEST = {percorso: 'Verifica percorso', sessioni: 'Sessioni BGP e OSPF', ping: 'Raggiungibilità', risoluzione: 'Risoluzione di un nome'};
export const testDopo = operazione => Object.keys(TEST).find(k => TEST[k].includes(operazione)) || null;
function htmlTestSuggerito(x) {
  const t = testDopo(x.operazione); if (!t) return '';
  const acceso = (S.stato[S.nome] || []).length;
  return `<div class="small" style="margin-top:6px">Prova adatta: <button type="button" class="ghost small" data-mod-azione="prova" data-test="${t}">${NOME_TEST[t]}</button>
    <span class="muted">${acceso ? 'Il lab è acceso: le modifiche ai file valgono dopo averlo fermato e riavviato (lclean, lstart).' : 'Prima avvia il lab (lstart).'}${t === 'risoluzione' ? ' La risoluzione si controlla anche a lab spento, dai file.' : ''}</span></div>`;
}
function vaiAlTest(t) {
  const x = S.esito || {}, par = x.par || {};
  const card = {percorso: '#bPercorso', sessioni: '#bSessioni', ping: '#bPing', risoluzione: '#bRisolvi'}[t];
  if (t === 'risoluzione' && par.dispositivo && [...$('#dnSrc').options].some(o => o.value === par.dispositivo)) $('#dnSrc').value = par.dispositivo;
  scheda('test');
  const b = $(card); if (b) { b.scrollIntoView({block: 'center'}); b.focus(); }
}

function disegnaCasa(el) {
  const st = S.storia || [];
  el.innerHTML = `<h3>Modifica del lab</h3>
    ${htmlEsito(S.esito)}
    <p class="small muted">Clic sull'etichetta di un'<b>interfaccia</b> (IP, LAN, costo OSPF), su una <b>LAN</b> (subnet, collega, aggiungi),
      sulla scritta di un <b>AS</b> (aggregato, iBGP, auto-cost) o su un <b>dispositivo</b> (le sue azioni nel pannello).
      Ogni modifica mostra prima le righe che cambiano; dopo "Applica" si può annullare.</p>
    ${S.htmlCasaModifica ? S.htmlCasaModifica() : ''}
    ${htmlAutoCost()}
    <h4 class="ed-sotto">Ultime modifiche</h4>
    ${st.length ? `<ol class="storia-mod">${st.slice(0, 8).map(v => `<li><span class="small muted">${esc(v.ora.slice(11))}</span> ${esc(v.titolo)}</li>`).join('')}</ol>
      <div class="btns"><button type="button" data-mod-azione="annulla">Annulla l'ultima</button></div>`
      : '<div class="small muted">Nessuna modifica registrata per questo lab.</div>'}
    <h4 class="ed-sotto">Copie di sicurezza</h4>
    <div id="modCopie"><button type="button" class="ghost small" data-mod-azione="copie">Mostra le copie</button></div>`;
}
S.latoModifica = el => (S.op ? disegnaOp(el) : disegnaCasa(el));

// pulsanti degli AS (come il clic sulla scritta dell'AS): aggregato, iBGP, auto-cost
function htmlAutoCost() {
  const as = [...new Set(S.G.nodes.filter(n => n.tipo === 'router' && n.gruppo !== '_').map(n => n.gruppo))];
  if (!as.length) return '';
  return `<div class="btns">${as.map(g => `<button type="button" class="ghost small" data-gesto="as" data-as="${esc(g)}" title="Aggregato, iBGP, auto-cost">AS${esc(g)}</button>`).join('')}</div>`;
}

async function mostraCopie() {
  const el = $('#modCopie') || $('#opRis');
  el.innerHTML = '<div class="muted small">Leggo le copie…</div>';
  try {
    const c = (await azione({azione: 'copie'})).copie;
    el.innerHTML = c.length ? `<p class="small muted">Copie di tutto il lab fatte prima di ogni modifica (la più recente in alto). Ripristinare riporta
      tutti i file a quel momento; lo stato di adesso viene salvato in un'altra copia.</p>
      <ul class="copie-mod">${c.slice(0, 15).map(x => `<li><span>${esc(x.quando)}</span><button type="button" class="ghost small" data-copia="${esc(x.nome)}" data-quando="${esc(x.quando)}">Ripristina</button></li>`).join('')}</ul>`
      : '<div class="small muted">Nessuna copia di sicurezza per questo lab.</div>';
  } catch (e) { el.innerHTML = `<div class="koline">${esc(e.message)}</div>`; }
}

async function ripristinaCopia(b) {
  if (!confirm(`Il lab ${S.nome} tornerà com'era il ${b.dataset.quando}. Le modifiche fatte dopo si perdono (restano in una copia di sicurezza). Confermi?`)) return;
  b.disabled = true;
  try {
    const r = await azione({azione: 'ripristina', copia: b.dataset.copia});
    S.op = null; S.sel = null; S.esito = Object.assign({ripristino: true}, r);
    await aggiornaStoria();
    await apriLab(S.nome, true);
  } catch (e) { b.disabled = false; $('#modCopie').insertAdjacentHTML('beforeend', `<div class="koline">${esc(e.message)}</div>`); }
}

// ---------- gesti: dal disegno e dai pulsanti del pannello ----------
export function costoOspf(dev, iface) {
  const d = dispositivo(dev);
  if (!d || d.tipo !== 'router' || !d.demoni.includes('ospfd')) {
    S.op = null; S.esito = {avviso: `Il costo OSPF vale solo sui router con OSPF: ${dev} non lo ha.`}; S.sel = null; lato(); return;
  }
  const it = d.interfacce.find(x => x.dev === iface) || {};
  apriOperazione({
    operazione: 'costo_ospf', titolo: `Costo OSPF di ${dev} ${iface}`,
    spiegazione: (it.costo ? `Adesso: ${it.costo} (scritto nel frr.conf).` : 'Adesso: quello predefinito (nessun costo scritto nel frr.conf).')
      + ' Il percorso con la somma dei costi più bassa vince.',
    fissi: {router: dev, interfaccia: iface},
    schema: [{nome: 'costo', etichetta: 'Costo', tipo: 'numero', obbligatorio: true, aiuto: 'Numero intero da 1 a 65535.'}],
    valori: {costo: it.costo || ''},
  });
}
export function togliCosto(dev, iface) {
  const it = (dispositivo(dev).interfacce.find(x => x.dev === iface)) || {};
  apriOperazione({operazione: 'togli_costo_ospf', titolo: `Togli il costo OSPF di ${dev} ${iface}`,
    spiegazione: `Adesso: ${it.costo}. Togliendo la riga ${iface} torna al costo predefinito.`,
    fissi: {router: dev, interfaccia: iface}, subito: true});
}

export async function autoCost(g) {
  let gruppi = [];
  try { gruppi = (await azione({azione: 'opzioni', operazione: 'auto_cost'})).opzioni || []; } catch (e) { gruppi = []; }
  const rs = new Set(S.G.nodes.filter(n => n.gruppo === g).map(n => n.nome));
  const miei = gruppi.filter(x => x.router.some(r => rs.has(r)));
  if (!miei.length) { S.op = null; S.esito = {avviso: `Nell'AS${g} non ci sono router OSPF: l'auto-cost non serve.`}; S.sel = null; lato(); return; }
  const descr = x => `${x.etichetta}: router ${x.router.join(', ')}; con auto-cost: ${x.con_auto_cost.join(', ') || 'nessuno'}`
    + (x.costi.length ? `; costi scritti: ${x.costi.join(', ')}` : '');
  const tutti = miei[0].con_auto_cost.length === miei[0].router.length;
  apriOperazione({
    operazione: 'auto_cost', titolo: `Auto-cost su AS${g}`,
    spiegazione: miei.map(descr).join(' · ') + '. Con auto-cost reference-bandwidth 100 tutti i router OSPF del gruppo calcolano i costi predefiniti allo stesso modo.',
    schema: [
      ...(miei.length > 1 ? [{nome: 'etichetta', etichetta: 'Gruppo OSPF', tipo: 'scelta', obbligatorio: true, opzioni: miei.map(x => x.etichetta)}] : []),
      {nome: 'togli', etichetta: 'Cosa fare', tipo: 'scelta', obbligatorio: true,
       opzioni: [['no', 'Metti auto-cost reference-bandwidth 100 su tutti'], ['si', "Togli l'auto-cost da tutti"]]},
    ],
    valori: {togli: tutti ? 'si' : 'no'},
    prepara: v => ({etichetta: v.etichetta || miei[0].etichetta, togli: v.togli === 'si'}),
  });
}

// i gesti (gesti.su) e la sezione Modifica del pannello del dispositivo sono in modifica_lab.js
$('#side').addEventListener('click', e => {
  if (!S.modifica) return;
  const g = e.target.closest('[data-gesto]');
  if (g) { e.preventDefault(); gesti.su(Object.assign({mod: g.dataset.gesto}, g.dataset)); return; }
  const v = e.target.closest('[data-mod-voce]');
  if (v && S.op && S.op.menu) { const voce = S.op.menu.voci[Number(v.dataset.modVoce)]; const da = S.op; Promise.resolve(voce.fai()).then(() => { if (S.op && S.op !== da && !S.op.da) S.op.da = da; }); return; }
  const c = e.target.closest('[data-copia]');
  if (c) { ripristinaCopia(c); return; }
  const a = e.target.closest('[data-mod-azione]');
  if (!a) return;
  e.preventDefault();
  const az = a.dataset.modAzione;
  if (az === 'indietro') { const es = S.op && !S.op.da && S.op.esito; S.op = (S.op && S.op.da) || null; if (es) S.esito = es; lato(); }
  else if (az === 'anteprima') anteprima();
  else if (az === 'salta' && S.op && S.op.conf && S.op.conf.salta) { const da = S.op; apriPasso(S.op.conf.salta()); S.op.da = da; }
  else if (az === 'applica') applica(a);
  else if (az === 'copie') mostraCopie();
  else if (az === 'annulla') $('#bAnnulla').click();
  else if (az === 'prova') vaiAlTest(a.dataset.test);
});
