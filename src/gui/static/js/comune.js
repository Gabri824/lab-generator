// Parti comuni della GUI: richieste al server, stato della pagina (S), riquadro Output e lavori.
import { registro } from './registro.js';

export function $(s) { return document.querySelector(s); }
export function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
export function pausa(ms) { return new Promise(r => setTimeout(r, ms)); }
export const S = {labs: [], stato: {}, lab: null, nome: null, sel: null, G: null, pos: null, vb: null, evid: null, tab: 'topo'};
export const COL = ['#2563eb','#16a34a','#dc2626','#9333ea','#ea580c','#0891b2','#ca8a04','#db2777','#4f46e5','#65a30d','#0f766e','#b45309'];

export function mem(k, v) {           // localStorage opzionale (posizioni dei nodi)
  try { if (v === undefined) return JSON.parse(localStorage.getItem(k) || 'null'); localStorage.setItem(k, JSON.stringify(v)); } catch (e) { return null; }
}
// errore del server: e.codice = stato HTTP (400 richiesta, 409 conflitto, 413, 422 valori), e.dati = risposta
export class ErroreServer extends Error {
  constructor(codice, dati) { super((dati && dati.errore) || String(codice)); this.codice = codice; this.dati = dati || {}; }
}
async function risposta(r) {
  let j = null;
  try { j = await r.json(); } catch (e) { j = {errore: r.status + ' ' + r.statusText}; }
  if (!r.ok) throw new ErroreServer(r.status, j);
  return j;
}
export async function api(path) {
  return risposta(await fetch(path));
}
// POST /api/azione; il lab aperto viene aggiunto se la richiesta non ne indica un altro
export async function azione(dati) {
  return risposta(await fetch('/api/azione', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Lab-Gen': '1'},
    body: JSON.stringify(Object.assign({lab: S.nome}, dati))}));
}

// ---------- output dei comandi ----------
export function outInizio(titolo) { $('#outTitolo').textContent = titolo; $('#outStato').textContent = ' in corso…'; $('#outStato').className = 'small warnline'; $('#outTesto').textContent = ''; }
export function outScrivi(righe) { const p = $('#outTesto'); const giu = p.scrollTop + p.clientHeight >= p.scrollHeight - 5; p.textContent += righe.map(r => r + '\n').join(''); if (giu) p.scrollTop = p.scrollHeight; }
export function outFine(ok, testo) { $('#outStato').textContent = ' ' + testo; $('#outStato').className = 'small ' + (ok ? 'okline' : 'koline'); }
export function errore(e) { outInizio('Errore'); outScrivi([String(e.message || e)]); outFine(false, 'errore'); }

// il riquadro Output mostra solo l'ultimo lavoro avviato: uno più vecchio ancora in corso
// (es. la convergenza partita dopo lstart) continua in silenzio e il suo risultato arriva
// comunque alla sua card e al Registro, senza mescolare le righe con quelle del nuovo
export async function segui(lid, titolo) {
  S.visibile = lid; outInizio(titolo); let da = 0;
  for (;;) {
    const r = await api('/api/lavoro?id=' + lid + '&da=' + da), mio = S.visibile === lid;
    if (r.righe.length && mio) outScrivi(r.righe); da = r.totale;
    if (r.fatto) { if (mio) outFine(r.rc === 0, r.rc === 0 ? 'completato' : 'terminato con errore (' + r.rc + ')'); if (S.tab === 'reg') registro(); return r; }
    await pausa(600);
  }
}
export async function esegui(dati, titolo, bottone) {
  if (bottone) bottone.disabled = true;
  try { const j = await azione(dati); return await segui(j.lavoro, titolo); }
  catch (e) { errore(e); return null; }
  finally { if (bottone) bottone.disabled = false; }
}
