// Anteprima delle modifiche: mostra la risposta di 'anteprima' (api.py) file per file, con le righe
// tolte e aggiunte, le note da leggere prima di confermare e il caso "nessuna modifica".
// Modello: il componente diff-review della skill di design (intestazione del file con i conteggi,
// righe con numero e segno su due tinte fisse di rosso e verde).
import { esc } from '../comune.js';

const STATI = {nuovo: 'nuovo', modificato: 'modificato', eliminato: 'eliminato', spostato: 'spostato'};

function barra(piu, meno) {
  // cinque quadratini divisi tra aggiunte e tolte, come nella revisione del codice
  const tot = piu + meno;
  if (!tot) return '';
  let p = Math.round(5 * piu / tot);
  if (piu && !p) p = 1;
  if (meno && p === 5) p = 4;
  return '<span class="diff__barra" aria-hidden="true">' + '<i class="piu"></i>'.repeat(p) + '<i class="meno"></i>'.repeat(5 - p) + '</span>';
}

function percorso(file) {
  const i = file.lastIndexOf('/');
  return i < 0 ? `<b>${esc(file)}</b>` : `<span class="diff__dir">${esc(file.slice(0, i + 1))}</span><b>${esc(file.slice(i + 1))}</b>`;
}

export function htmlFile(f) {
  const piu = f.righe.filter(r => r.segno === '+').length, meno = f.righe.length - piu;
  let h = `<article class="diff"><header class="diff__testa">
    <span class="diff__file">${percorso(f.file)}</span>
    <span class="badge diff__stato diff__stato--${esc(f.stato)}">${esc(STATI[f.stato] || f.stato)}</span>
    ${f.da ? `<span class="small muted">era <code>${esc(f.da)}</code></span>` : ''}
    <span class="sp"></span>
    <span class="diff__conta"><b class="piu">+${piu}</b><b class="meno">&minus;${meno}</b>${barra(piu, meno)}</span>
  </header>`;
  if (!f.righe.length) return h + '<div class="diff__vuoto small muted">Il file cambia solo posto: il contenuto resta uguale.</div></article>';
  h += '<div class="diff__righe">';
  let prima = null;
  for (const r of f.righe) {
    // un salto nella numerazione separa due gruppi di modifiche lontani nel file
    if (prima && prima.segno === r.segno && r.numero !== prima.numero + 1) h += '<div class="diff__salto" aria-hidden="true">⋯</div>';
    const cls = r.segno === '+' ? 'piu' : 'meno';
    h += `<div class="diff__riga ${cls}"><span class="diff__n">${r.numero}</span><span class="diff__s" aria-label="${cls === 'piu' ? 'aggiunta' : 'tolta'}">${r.segno === '+' ? '+' : '&minus;'}</span><code>${esc(r.testo) || ' '}</code></div>`;
    prima = r;
  }
  return h + '</div></article>';
}

// r = {titolo, file: [...], note: [...], vuoto}
export function htmlAnteprima(r) {
  const file = r.file || [];
  let piu = 0, meno = 0;
  file.forEach(f => f.righe.forEach(x => (x.segno === '+' ? piu++ : meno++)));
  let h = `<div class="anteprima"><div class="anteprima__testa"><h3>${esc(r.titolo || 'Anteprima delle modifiche')}</h3>`;
  h += file.length ? `<span class="small muted">${file.length} file · <span class="okline">+${piu}</span> <span class="koline">&minus;${meno}</span></span>` : '';
  h += '</div>';
  if (r.note && r.note.length) h += `<ul class="anteprima__note">${r.note.map(n => `<li>${esc(n)}</li>`).join('')}</ul>`;
  if (!file.length) h += `<div class="anteprima__vuota">${esc(r.vuoto || 'Nessuna modifica.')}</div>`;
  return h + file.map(htmlFile).join('') + '</div>';
}

// errore 409 di 'applica' (ErroreServer): i file cambiati dopo l'anteprima, niente scritto
export function htmlConflitto(err) {
  const file = (err && err.dati && err.dati.file) || [];
  return `<div class="conflitto" role="alert"><b>Non ho scritto nulla: il lab è cambiato dopo l'anteprima.</b>
    ${file.length ? `<div class="small">File cambiati: ${file.map(f => `<code>${esc(f)}</code>`).join(', ')}</div>` : ''}
    <div class="small">Rifai l'anteprima per vedere le modifiche sui file di adesso.</div></div>`;
}
