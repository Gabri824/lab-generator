// Modalità Modifica, fase 5.5b: "Percorso voluto", un'opzione in più accanto alla 5.5 (le policy
// fatte a mano restano il modo principale). Si clicca sul disegno la sorgente, gli AS o i link da
// attraversare e la destinazione; il server (gui/percorso_voluto.py) propone per ogni punto di
// scelta di BGP una policy della 5.5 (local-preference, MED o prefix-list), che si apre come un
// normale modulo: anteprima, applica o salta, una alla volta. Alla fine "Verifica percorso" nella
// scheda Test (lab acceso) dice se il traffico passa davvero di lì: le proposte non sono una garanzia.
import { $, esc, esegui, S } from './comune.js';
import { lato } from './dispositivo.js';
import { scheda } from './main.js';
import { apriMenu, apriOperazione } from './modifica.js';
import { parametriPolicy } from './proposte.js';
import { ridisegna } from './topologia.js';

const T = () => S.op && S.op.conf && S.op.conf.traccia;     // il pannello del tracciamento è aperto

function nomePunto(p) { return p.tipo === 'lan' ? `LAN ${p.nome}` : p.tipo === 'as' ? `AS${p.nome}` : p.nome; }

function evidenziaPunti(punti) {
  const dev = new Set(), lan = new Set(), ordine = {};
  punti.forEach((p, i) => {
    if (p.tipo === 'dev') { dev.add(p.nome); if (ordine[p.nome] == null) ordine[p.nome] = i === 0 ? 'S' : i; }
    if (p.tipo === 'lan') {
      lan.add(p.nome);
      const l = S.lab.lan.find(x => x.nome === p.nome);
      for (const m of (l ? l.membri : [])) dev.add(m);
    }
  });
  S.evid = {dev, lan, ordine, manca: new Set()};
  ridisegna();
}

function htmlTraccia(t) {
  const asLab = [...new Set(S.lab.dispositivi.filter(d => d.tipo === 'router' && d.demoni.includes('bgpd') && d.gruppo && d.gruppo !== '_').map(d => String(d.gruppo)))];
  return `<ol class="storia-mod">${t.punti.map((p, i) => `<li>${i === 0 ? '<b>sorgente</b> ' : ''}${esc(nomePunto(p))}</li>`).join('')
      || '<li class="muted">nessun punto: clicca la sorgente</li>'}</ol>
    <div class="btns"><button type="button" class="ghost small" data-pv="togli"${t.punti.length ? '' : ' disabled'}>Togli l'ultimo</button>
      <button type="button" class="ghost small" data-pv="ricomincia"${t.punti.length ? '' : ' disabled'}>Ricomincia</button></div>
    <fieldset class="gruppo" style="margin-top:8px"><legend class="small">Le altre strade sono vietate, non solo meno preferite (filtro, come "as100r1 applies filters" di lift), in:</legend>
      ${asLab.map(a => `<label class="scelta small"><input type="checkbox" data-pv-vieta="${esc(a)}"${t.vieta.includes(a) ? ' checked' : ''}> AS${esc(a)}</label>`).join(' ')}
    </fieldset>`;
}

function aggiorna() {
  const op = S.op; if (!T()) return;
  op.conf.corpo = htmlTraccia(op.conf.traccia);
  evidenziaPunti(op.conf.traccia.punti);
  lato();
}

// ---------- 1. si disegna il percorso ----------
export function iniziaPercorso() {
  const t = {punti: [], vieta: []};
  apriOperazione({
    titolo: 'Percorso voluto', traccia: t, corpo: htmlTraccia(t),
    spiegazione: 'Clicca sul disegno, in ordine: la sorgente (un dispositivo), gli AS o i link fra AS da attraversare, la destinazione (una LAN o un dispositivo). '
      + 'Il programma propone le policy della 5.5 per ottenerlo; non è una garanzia: alla fine prova con "Verifica percorso".',
    leggi: () => t,
    avanti: () => calcola(t),
  });
  evidenziaPunti([]);
}

// clic sul disegno mentre il pannello è aperto: true se il clic è stato preso come punto
export function puntoPercorso(m) {
  const op = S.op; if (!T()) return false;
  const t = op.conf.traccia;
  let p = null;
  if (m.mod === 'dev') p = {tipo: 'dev', nome: m.nome};
  else if (m.mod === 'if') p = {tipo: 'dev', nome: m.dev};
  else if (m.mod === 'lan') p = {tipo: 'lan', nome: m.lan};
  else if (m.mod === 'as') p = {tipo: 'as', nome: String(m.as)};
  if (!p) return false;
  if (!t.punti.length && p.tipo !== 'dev') { $('#opRis').innerHTML = '<div class="warnline">Il primo punto è la sorgente: clicca un dispositivo.</div>'; return true; }
  const u = t.punti[t.punti.length - 1];
  if (!u || u.tipo !== p.tipo || u.nome !== p.nome) t.punti.push(p);
  aggiorna();
  return true;
}

$('#side').addEventListener('click', e => {
  const b = e.target.closest('[data-pv]'); if (!b || !T()) return;
  const t = S.op.conf.traccia;
  if (b.dataset.pv === 'togli') t.punti.pop(); else t.punti.length = 0;
  aggiorna();
});
$('#side').addEventListener('change', e => {
  const c = e.target.closest('[data-pv-vieta]'); if (!c || !T()) return;
  const t = S.op.conf.traccia, a = c.dataset.pvVieta;
  t.vieta = c.checked ? [...new Set([...t.vieta, a])] : t.vieta.filter(x => x !== a);
});

// ---------- 2. il server propone ----------
async function calcola(t) {
  if (t.punti.length < 2) throw new Error('Servono almeno la sorgente e la destinazione.');
  const r = await esegui({azione: 'percorso_voluto', lab: S.nome, punti: t.punti, vieta: t.vieta}, 'Percorso voluto da ' + t.punti[0].nome);
  if (!r || !r.risultato) throw new Error("Non ho potuto calcolare le proposte: guarda l'Output.");
  const x = r.risultato, punti = t.punti.slice();
  const fatti = [];
  const da = S.op;
  apriMenu({
    titolo: `Percorso voluto: ${x.sequenza.map(a => 'AS' + a).join(' → ')}`,
    spiegazione: `Rete di destinazione ${x.rete} (annunciata da AS${x.origine}). ` + (x.modo === 'tabelle'
      ? 'Proposte basate sulle tabelle BGP del lab acceso.' : 'Lab spento: proposte basate solo sui file (AS path più corto); accendi il lab per proposte più precise.')
      + (x.note.length ? ' ' + x.note.join(' ') : ''),
    voci: [
      ...(x.proposte.length ? [{testo: `Vedi le proposte una alla volta (${x.proposte.length})`, fai: () => apri(proposta(x, 0, fatti, punti))}] : []),
      {testo: 'Verifica percorso (scheda Test, lab acceso)', fai: () => vaiVerifica(x.verifica)},
    ],
  });
  S.op.da = da;
  evidenziaPunti(punti);
  return null;
}

// ---------- 3. una proposta alla volta, come i moduli della 5.5 ----------
// proposta() e fine() restituiscono il passo (modulo, o {menu}) senza aprirlo: dopo l'applica lo
// apre modifica.js (conf.poi), con l'esito della proposta appena applicata sopra
function apri(passo) { if (passo.menu) apriMenu(passo.menu); else apriOperazione(passo); }

function proposta(x, k, fatti, punti) {
  if (k >= x.proposte.length) return fine(x, fatti, punti);
  const p = x.proposte[k], par = p.parametri, tipo = par.tipo;
  const schema = [], valori = {};
  if (tipo === 'local_pref' || tipo === 'med') { schema.push({nome: 'valore', etichetta: tipo === 'med' ? 'MED (metric)' : 'Local-preference', tipo: 'numero', obbligatorio: true}); valori.valore = par.valore; }
  if (tipo !== 'med') { schema.push({nome: 'altre', etichetta: 'Reti', obbligatorio: tipo !== 'local_pref', aiuto: 'Separate da virgola.'}); valori.altre = (par.reti || []).join(', '); }
  return {
    operazione: 'policy', titolo: `Proposta ${k + 1} di ${x.proposte.length} (AS${p.as}): ${p.titolo}`, spiegazione: p.perche,
    fissi: {router: par.router, neighbor: par.neighbor, asn_nuovo: null},
    schema, valori,
    prepara: v => parametriPolicy(tipo, {valore: v.valore, altre: v.altre, direzione: par.direzione}),
    poi: async () => { fatti.push(p.titolo); evidenziaPunti(punti); return proposta(x, k + 1, fatti, punti); },
    salta: () => proposta(x, k + 1, fatti, punti),
  };
}

function fine(x, fatti, punti) {
  evidenziaPunti(punti);
  return {menu: {
    titolo: 'Percorso voluto: fatto',
    spiegazione: (fatti.length ? `Applicate: ${fatti.join('; ')}. ` : 'Nessuna proposta applicata. ')
      + 'Ora accendi (o riavvia) il lab, attendi la convergenza e prova con "Verifica percorso": è lì che si vede se il traffico passa davvero di lì. Ogni policy si toglie con Annulla.',
    voci: [{testo: 'Verifica percorso (scheda Test, lab acceso)', fai: () => vaiVerifica(x.verifica)}],
  }};
}

function vaiVerifica(v) {
  const sel = $('#pSrc');
  if (sel && [...sel.options].some(o => o.value === v.dev)) sel.value = v.dev;
  if ($('#pDst')) $('#pDst').value = v.ip || '';
  if ($('#pAtt')) $('#pAtt').value = v.atteso || '';
  const per = document.querySelector('input[name=pModo][value=per]'); if (per) per.checked = true;
  scheda('test');
  const b = $('#bPercorso'); if (b) b.scrollIntoView({block: 'center'});
}

export const htmlPulsantePercorso = () => `<div class="btns"><button type="button" class="ghost small" data-gesto="percorso"
  title="Clicca sorgente, AS o link e destinazione: il programma propone le policy (opzione in più accanto a Policy BGP)">Percorso voluto (proposte di policy)</button></div>`;
