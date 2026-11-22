// Pannello proprietà: un modulo costruito da uno schema, con l'etichetta sopra ogni campo, un aiuto
// facoltativo e l'errore sotto il campo. Lo useranno l'editor grafico (dispositivo, LAN, AS, area)
// e le Opzioni (parametri di un'operazione).
//
//   const p = creaPannello(el, {titolo, schema: [{nome, etichetta, tipo, opzioni, aiuto, obbligatorio,
//                                               segnaposto, campo}], valori, onCambio})
//   p.valori()            -> {nome: valore}
//   p.controlla()         -> {nome: messaggio} dei campi obbligatori vuoti o dei numeri non validi
//   p.mostraErrori(map)   -> errori sotto i campi ({nome: messaggio}); il primo prende il focus
//
// tipo: 'testo' (predefinito), 'numero', 'scelta' (opzioni: [[valore, testo]] o [valore]), 'si_no'.
// campo: nome del campo nei problemi di valida_lab (data-campo), per segnaCampi e l'elenco errori.
import { esc } from '../comune.js';

let n = 0;

function controllo(c, id, v) {
  const comuni = `id="${id}" name="${esc(c.nome)}"${c.campo ? ` data-campo="${esc(c.campo)}"` : ''} aria-describedby="${id}-e${c.aiuto ? ` ${id}-a` : ''}"`;
  if (c.tipo === 'scelta') {
    const op = (c.opzioni || []).map(o => Array.isArray(o) ? o : [o, o]);
    return `<select ${comuni}>${op.map(([val, t]) => `<option value="${esc(val)}"${String(val) === String(v ?? '') ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select>`;
  }
  if (c.tipo === 'si_no') return `<input type="checkbox" ${comuni}${v ? ' checked' : ''}>`;
  const tipo = c.tipo === 'numero' ? ' inputmode="numeric"' : '';
  return `<input ${comuni}${tipo} value="${esc(v ?? '')}"${c.segnaposto ? ` placeholder="${esc(c.segnaposto)}"` : ''} autocomplete="off" spellcheck="false">`;
}

export function creaPannello(el, {titolo, schema, valori = {}, onCambio}) {
  const base = 'prop' + (++n);
  const id = c => `${base}-${c.nome}`;
  el.innerHTML = `<form class="prop" novalidate>${titolo ? `<h3 class="prop__titolo">${esc(titolo)}</h3>` : ''}
    ${schema.map(c => {
      const i = id(c);
      const aiuto = c.aiuto ? `<p class="prop__aiuto" id="${i}-a">${esc(c.aiuto)}</p>` : '';
      const errore = `<p class="campo__errore" id="${i}-e" hidden></p>`;
      if (c.tipo === 'si_no') return `<div class="prop__campo prop__campo--si"><label class="scelta" for="${i}">${controllo(c, i, valori[c.nome])} ${esc(c.etichetta)}</label>${aiuto}${errore}</div>`;
      return `<div class="prop__campo"><label for="${i}">${esc(c.etichetta)}${c.obbligatorio ? '' : ' <span class="prop__fac">(facoltativo)</span>'}</label>${controllo(c, i, valori[c.nome])}${aiuto}${errore}</div>`;
    }).join('')}</form>`;
  const form = el.querySelector('form');
  const leggi = c => {
    const x = form.querySelector('#' + CSS.escape(id(c)));
    if (c.tipo === 'si_no') return x.checked;
    const v = x.value.trim();
    return c.tipo === 'numero' && v !== '' && /^-?\d+$/.test(v) ? Number(v) : v;
  };
  const tutti = () => Object.fromEntries(schema.map(c => [c.nome, leggi(c)]));
  form.addEventListener('submit', e => e.preventDefault());
  form.addEventListener('change', e => {
    const c = schema.find(x => x.nome === e.target.name);
    if (c && onCambio) onCambio(c.nome, leggi(c), tutti());
  });
  const mostraErrori = errori => {
    let primo = null;
    for (const c of schema) {
      const x = form.querySelector('#' + CSS.escape(id(c))), d = form.querySelector('#' + CSS.escape(id(c) + '-e'));
      const m = errori && errori[c.nome];
      d.hidden = !m; d.textContent = m || '';
      if (m) { x.setAttribute('aria-invalid', 'true'); primo = primo || x; } else x.removeAttribute('aria-invalid');
    }
    if (primo) primo.focus();
    return !primo;
  };
  return {
    form,
    valori: tutti,
    controlla() {
      const e = {};
      for (const c of schema) {
        const v = leggi(c);
        if (c.obbligatorio && (v === '' || v == null)) e[c.nome] = `Scrivi ${c.etichetta.toLowerCase()}.`;
        else if (c.tipo === 'numero' && v !== '' && typeof v !== 'number') e[c.nome] = `${c.etichetta}: serve un numero intero.`;
      }
      return e;
    },
    mostraErrori,
  };
}
