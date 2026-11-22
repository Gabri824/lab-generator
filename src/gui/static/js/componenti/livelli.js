// Interruttori dei livelli del disegno (indirizzi, sessioni BGP, policy, costi OSPF, DNS...).
// Ogni livello è un pulsante role="switch"; la scelta resta nel browser (chiave), se disponibile.
//
//   const l = creaLivelli(el, [{id, etichetta, attivo}], (attivi) => ..., 'livelli:topologia')
//   l.attivi() -> Set degli id accesi
import { esc, mem } from '../comune.js';

export function creaLivelli(el, livelli, onCambio, chiave) {
  const salvati = chiave ? mem(chiave) : null;
  const acceso = new Set(livelli.filter(l => (salvati && l.id in salvati) ? salvati[l.id] : l.attivo).map(l => l.id));
  el.classList.add('livelli');
  el.setAttribute('role', 'group');
  if (!el.getAttribute('aria-label')) el.setAttribute('aria-label', 'Livelli del disegno');
  el.innerHTML = livelli.map(l => `<button type="button" class="livello" role="switch" data-livello="${esc(l.id)}" aria-checked="${acceso.has(l.id)}">
    <span class="livello__inter" aria-hidden="true"></span>${esc(l.etichetta)}</button>`).join('');
  el.addEventListener('click', e => {
    const b = e.target.closest('[data-livello]');
    if (!b) return;
    const id = b.dataset.livello;
    acceso.has(id) ? acceso.delete(id) : acceso.add(id);
    b.setAttribute('aria-checked', acceso.has(id));
    if (chiave) mem(chiave, Object.fromEntries(livelli.map(l => [l.id, acceso.has(l.id)])));
    if (onCambio) onCambio(new Set(acceso));
  });
  return {attivi: () => new Set(acceso)};
}
