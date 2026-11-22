// Elenco di errori e avvisi (risposta di 'valida_lab': [{campo, gravita, messaggio, dispositivi?}]).
// Ogni voce è un pulsante che porta al campo sbagliato; segnaCampi mette l'errore sotto il campo
// (aria-invalid e aria-describedby), come chiede la base dei form.
import { esc } from '../comune.js';

export function htmlErrori(problemi, titolo) {
  const errori = problemi.filter(p => p.gravita === 'errore'), avvisi = problemi.filter(p => p.gravita !== 'errore');
  if (!problemi.length) return '<div class="errori errori--ok okline">✔ Nessun problema.</div>';
  const voce = p => `<li><button type="button" class="errori__voce errori__voce--${p.gravita === 'errore' ? 'errore' : 'avviso'}" data-campo="${esc(p.campo)}">
      <span class="errori__segno" aria-hidden="true">${p.gravita === 'errore' ? '✘' : '⚠'}</span>
      <span class="errori__testo"><span class="errori__campo">${esc(p.campo)}</span> ${esc(p.messaggio)}</span></button></li>`;
  return `<div class="errori"${titolo ? ` aria-label="${esc(titolo)}"` : ''}>
    <div class="errori__conta small">${errori.length ? `<span class="koline">${errori.length} ${errori.length === 1 ? 'errore' : 'errori'}</span>` : ''}${errori.length && avvisi.length ? ' · ' : ''}${avvisi.length ? `<span class="warnline">${avvisi.length} ${avvisi.length === 1 ? 'avviso' : 'avvisi'}</span>` : ''}</div>
    <ul>${errori.map(voce).join('')}${avvisi.map(voce).join('')}</ul></div>`;
}

// clic su una voce: trova(campo) restituisce l'elemento da mostrare (di solito un controllo)
export function collegaErrori(contenitore, trova) {
  contenitore.addEventListener('click', e => {
    const b = e.target.closest('[data-campo]');
    if (!b || !contenitore.contains(b) || !b.classList.contains('errori__voce')) return;
    const el = trova(b.dataset.campo);
    if (el) { el.scrollIntoView({block: 'nearest'}); if (el.focus) el.focus(); }
  });
}

// errore sotto ogni controllo con data-campo uguale al campo del problema; il primo prende il focus
export function segnaCampi(radice, problemi, metti_focus) {
  radice.querySelectorAll('[data-campo][aria-invalid]').forEach(el => {
    el.removeAttribute('aria-invalid');
    const d = document.getElementById(el.dataset.errore || '');
    if (d) d.hidden = true;
  });
  let primo = null;
  for (const p of problemi.filter(x => x.gravita === 'errore')) {
    const el = [...radice.querySelectorAll('[data-campo]')].find(x => x.dataset.campo === p.campo && !x.classList.contains('errori__voce'));
    if (!el) continue;
    el.setAttribute('aria-invalid', 'true');
    let d = document.getElementById(el.dataset.errore || '');
    if (!d) {
      d = document.createElement('p');
      d.className = 'campo__errore';
      d.id = 'err-' + Math.random().toString(36).slice(2, 9);
      el.dataset.errore = d.id;
      el.setAttribute('aria-describedby', ((el.getAttribute('aria-describedby') || '') + ' ' + d.id).trim());
      (el.closest('.prop__campo, .campo') || el).insertAdjacentElement('beforeend', d);
    }
    d.textContent = p.messaggio;
    d.hidden = false;
    primo = primo || el;
  }
  if (primo && metti_focus) primo.focus();
  return primo;
}
