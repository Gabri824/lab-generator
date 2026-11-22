// Avvio della pagina: elenco dei lab, apertura di un lab, schede, avvio e arresto del lab, file modificati.
import { avvisoArchivio } from './archivio.js';
import { $, api, azione, errore, esc, esegui, mem, S, segui } from './comune.js';
import { lato } from './dispositivo.js';
import { interfacce } from './interfacce.js';
import { registro } from './registro.js';
import { riepilogo } from './riepilogo.js';
import { apriEditor } from './editor/editor.js';
import { attendiConvergenza, controllaSpenti, lanGuasto, origini } from './test.js';
import { colori, grafo, ridisegna, varianti } from './topologia.js';

// ---------- elenco lab e stato ----------
export async function caricaLabs() {
  try { S.labs = (await api('/api/labs')).labs; } catch (e) { errore(e); }
  disegnaLabs(); aggiornaStato();
}
export async function aggiornaStato() {
  try { S.stato = await api('/api/stato'); } catch (e) { return; }
  disegnaLabs(); testaLab();
}
export function disegnaLabs() {
  $('#labs').innerHTML = S.labs.map(l => {
    const n = (S.stato[l] || []).length;
    // un pulsante per lab: si apre anche da tastiera
    const on = l === S.nome;
    return `<li class="${on ? 'on' : ''}"><button type="button" class="lab" data-lab="${esc(l)}"${on ? ' aria-current="true"' : ''}><span class="dot ${n ? 'acceso' : ''}" aria-hidden="true"></span>${esc(l)}${n ? ` <span class="small">(${n} accesi)</span>` : ''}</button></li>`;
  }).join('') || '<li class="muted">Nessun lab trovato</li>';
}
export const SCHEDE = ['topo', 'riep', 'intf', 'test', 'arch', 'reg'];
export function testaLab() {
  if (!S.lab) return;
  controllaModificati(); controllaSpenti();
  const tot = S.lab.dispositivi.length, acc = (S.stato[S.nome] || []).length;
  const b = $('#labStato');
  b.textContent = acc === 0 ? 'spento' : (acc === tot ? 'avviato (' + acc + '/' + tot + ')' : 'parziale (' + acc + '/' + tot + ')');
  b.className = 'badge ' + (acc === 0 ? '' : (acc === tot ? 'ok' : 'warn'));
}

export async function apriLab(nome, mantieni) {
  try {
    const lab = await api('/api/lab?nome=' + encodeURIComponent(nome));
    const cambiato = nome !== S.nome;
    S.lab = lab; S.nome = nome; S.sintassi = null;   // i file possono essere cambiati: sintassi da ricontrollare
    history.replaceState(null, '', '#lab=' + encodeURIComponent(nome) + '&tab=' + S.tab);
    if (cambiato) { S.sel = null; S.evid = null; $('#rPing').innerHTML = $('#rSessioni').innerHTML = $('#rPercorso').innerHTML = $('#rArchivio').innerHTML = ''; }
    $('#vuoto').hidden = true; $('#editor').hidden = true; $('#vista').hidden = false;
    $('#labNome').textContent = nome;
    $('#xmlNota').hidden = !lab.xml;
    $('#xmlNota').innerHTML = `Nel lab c'è <code>${esc(nome)}.xml</code> del generatore: <b>va tolto prima della consegna</b> (l'archivio creato da qui lo esclude già). Aprendo il lab dalle Opzioni del terminale puoi spostarlo in <code>.labgenerator/</code>, accanto ai lab.`;
    S.colori = colori(lab); S.G = grafo(lab);
    // posizioni: quelle spostate a mano nella Topologia, poi quelle del disegno dell'editor
    // (.labgenerator/<lab>/disegno.json), altrimenti la disposizione automatica
    let salvate = mem('pos:' + nome);
    const tutte = p => p && S.G.nodes.every(n => p[n.id]);
    if (!tutte(salvate)) {
      try { const d = (await api('/api/disegno?lab=' + encodeURIComponent(nome))).disegno; salvate = d && d.posizioni; } catch (e) { salvate = null; }
    }
    S.varianti = null; S.variante = 0;
    S.pos = tutte(salvate) ? JSON.parse(JSON.stringify(salvate)) : (S.varianti = varianti(S.G))[0];
    if (!mantieni || cambiato) S.vb = null;
    $('#ipList').innerHTML = lab.dispositivi.flatMap(d => d.interfacce.filter(i => i.ip).map(i => `<option value="${esc(i.ip.split('/')[0])}">${esc(d.nome + ' ' + i.dev)}</option>`)
      .concat(d.loopback.map(ip => `<option value="${esc(ip.split('/')[0])}">${esc(d.nome + ' lo')}</option>`))).join('');
    $('#pSrc').innerHTML = lab.dispositivi.map(d => `<option>${esc(d.nome)}</option>`).join('');
    $('#pnSrc').innerHTML = $('#pSrc').innerHTML; origini();
    if (cambiato) { $('#rPn').innerHTML = $('#rGuasto').innerHTML = ''; S.spenti = null; $('#linkNota').hidden = true; }
    lanGuasto();
    $('#rDev').innerHTML = lab.dispositivi.filter(d => d.tipo === 'router').map(d => `<option>${esc(d.nome)}</option>`).join('');
    $('#retiList').innerHTML = [...new Set(lab.lan.map(l => l.subnet).concat(lab.dispositivi.flatMap(d => (d.riepilogo || {}).bgp_networks || [])))]
      .filter(Boolean).map(r => `<option value="${esc(r)}"></option>`).join('');
    if (cambiato) { $('#rRotta').innerHTML = $('#rTabelle').innerHTML = ''; S.reali = null; }
    interfacce(); avvisoArchivio();
    if (!$('#aNome').value || cambiato) $('#aNome').value = nome;
    disegnaLabs(); testaLab(); ridisegna(); lato(); riepilogo();
  } catch (e) { errore(e); }
}

// ---------- file modificati dopo l'avvio ----------
let controlloInCorso = false;
export async function controllaModificati() {
  if (!S.nome || controlloInCorso) return;
  if (!(S.stato[S.nome] || []).length) { $('#modNota').hidden = true; return; }
  controlloInCorso = true;
  try {
    const m = await api('/api/modificati?lab=' + encodeURIComponent(S.nome));
    const n = $('#modNota');
    n.hidden = !(m.avviato && m.file.length);
    if (!n.hidden) n.innerHTML = `<b>Hai modificato ${m.file.length} file dopo l'avvio del lab</b> (avviato alle ${esc(m.avvio)}): ${m.file.slice(0, 6).map(f => '<code>' + esc(f) + '</code>').join(', ')}${m.file.length > 6 ? '…' : ''}.
      Le modifiche non sono attive finché non riavvii il lab. <button class="small" id="bRiavvia">Riavvia ora (lclean + lstart)</button>`;
  } catch (e) { /* stato non disponibile: nessun avviso */ }
  finally { controlloInCorso = false; }
}
$('#modNota').addEventListener('click', async e => {
  if (e.target.id !== 'bRiavvia') return;
  e.target.disabled = true;
  try {
    const j = await azione({azione: 'lstart', riavvia: true});
    const r = await segui(j.lavoro, 'riavvio ' + S.nome);
    await apriLab(S.nome, true); aggiornaStato();
    if (r && r.rc === 0) await attendiConvergenza($('#bConv'));
  } catch (err) { errore(err); }
});

// ---------- schede e pulsanti generali ----------
export function scheda(t) {
  if (!SCHEDE.includes(t)) return;
  S.tab = t;
  history.replaceState(null, '', '#lab=' + encodeURIComponent(S.nome) + '&tab=' + t);
  document.querySelectorAll('#tabs button').forEach(b => { b.classList.toggle('on', b.dataset.tab === t); b.setAttribute('aria-selected', b.dataset.tab === t); });
  SCHEDE.forEach(x => $('#t-' + x).hidden = x !== t);
  if (t === 'reg') registro();
  if (t === 'topo') ridisegna();
}
$('#tabs').onclick = e => { const b = e.target.closest('button'); if (b) scheda(b.dataset.tab); };
$('#labs').onclick = e => { const li = e.target.closest('[data-lab]'); if (li) apriLab(li.dataset.lab); };
$('#bAggiorna').onclick = caricaLabs;
$('#bNuovo').onclick = () => apriEditor();
$('#bRileggi').onclick = () => apriLab(S.nome, true);
$('#bPulisci').onclick = () => { $('#outTesto').textContent = ''; $('#outStato').textContent = ''; $('#outTitolo').textContent = 'Output'; };
$('#bStart').onclick = async e => {
  const b = e.target; b.disabled = true;
  try {
    let j = await azione({azione: 'lstart'});
    if (j.gia_acceso) {
      if (!confirm(`Il lab ${S.nome} è già acceso (${j.gia_acceso} dispositivi). Riavviarlo da capo (lclean + lstart)?`)) return;
      j = await azione({azione: 'lstart', riavvia: true});
    }
    const r = await segui(j.lavoro, 'lstart ' + S.nome);
    aggiornaStato();
    // dopo l'avvio si aspetta da soli che BGP/OSPF convergano (fino a 5 minuti)
    if (r && r.rc === 0) await attendiConvergenza($('#bConv'));
  } catch (err) { errore(err); }
  finally { b.disabled = false; aggiornaStato(); }
};
$('#bClean').onclick = async e => {
  if (!confirm('Fermare e cancellare i container del lab ' + S.nome + '?')) return;
  await esegui({azione: 'lclean'}, 'lclean ' + S.nome, e.target); aggiornaStato();
};
$('#bEsci').onclick = async () => {
  if (!confirm('Chiudere la GUI? I lab avviati restano accesi.')) return;
  try { await fetch('/api/esci', {method: 'POST', headers: {'X-Lab-Gen': '1', 'Content-Type': 'application/json'}, body: '{}'}); } catch (e) {}
  document.body.innerHTML = '<div class="vuoto">GUI chiusa. Puoi chiudere questa scheda.</div>';
};

(async function inizio() {
  try {
    const i = await api('/api/info');
    $('#base').textContent = 'Cartella: ' + i.base;
    const info = () => $('#info').textContent = i.kathara ? 'Kathará: ' + (i.versione || i.kathara) : '⚠ kathara non trovato nel PATH: comandi e test non disponibili';
    info();
    if (i.kathara && !i.versione) setTimeout(async () => { try { Object.assign(i, await api('/api/info')); info(); } catch (e) {} }, 3000);
  } catch (e) { errore(e); }
  await caricaLabs();
  // indirizzo diretto: http://127.0.0.1:8765/#lab=<nome>&tab=<topo|riep|test|arch|reg>
  const h = new URLSearchParams(location.hash.slice(1));
  if (h.get('lab') && S.labs.includes(h.get('lab'))) { await apriLab(h.get('lab')); if (h.get('tab')) scheda(h.get('tab')); }
  else if (location.hash === '#nuovo') apriEditor();
  setInterval(aggiornaStato, 10000);
})();
