// Annulla / ripeti per l'editor: una pila di copie dello stato (bozza del disegno).
//
//   const s = new Storia(statoIniziale)
//   s.fai(nuovoStato)    dopo ogni modifica (svuota i "ripeti")
//   s.annulla() / s.ripeti() -> lo stato da mostrare, oppure null se non c'è niente
//   creaBarraStoria(el, s, applica)   pulsanti Annulla e Ripeti con Ctrl+Z e Ctrl+Y (o Ctrl+Maiusc+Z)

const copia = x => (typeof structuredClone === 'function' ? structuredClone(x) : JSON.parse(JSON.stringify(x)));

export class Storia {
  constructor(iniziale, max = 100) {
    this.max = max;
    this.passati = [];
    this.futuri = [];
    this.attuale = copia(iniziale);
    this.ascolta = [];
  }
  get stato() { return copia(this.attuale); }
  get puoAnnullare() { return this.passati.length > 0; }
  get puoRipetere() { return this.futuri.length > 0; }
  _avvisa() { this.ascolta.forEach(f => f(this)); }
  fai(nuovo) {
    if (JSON.stringify(nuovo) === JSON.stringify(this.attuale)) return false;
    this.passati.push(this.attuale);
    if (this.passati.length > this.max) this.passati.shift();
    this.attuale = copia(nuovo);
    this.futuri = [];
    this._avvisa();
    return true;
  }
  annulla() {
    if (!this.passati.length) return null;
    this.futuri.push(this.attuale);
    this.attuale = this.passati.pop();
    this._avvisa();
    return this.stato;
  }
  ripeti() {
    if (!this.futuri.length) return null;
    this.passati.push(this.attuale);
    this.attuale = this.futuri.pop();
    this._avvisa();
    return this.stato;
  }
}

function inScrittura(el) {
  return el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName));
}

export function creaBarraStoria(el, storia, applica) {
  el.classList.add('storia');
  el.innerHTML = `<button type="button" class="ghost small" data-storia="annulla" aria-keyshortcuts="Control+Z">Annulla</button>
    <button type="button" class="ghost small" data-storia="ripeti" aria-keyshortcuts="Control+Y">Ripeti</button>`;
  const [bA, bR] = el.querySelectorAll('button');
  const aggiorna = () => { bA.disabled = !storia.puoAnnullare; bR.disabled = !storia.puoRipetere; };
  const fai = cosa => { const s = cosa === 'annulla' ? storia.annulla() : storia.ripeti(); if (s) applica(s); };
  el.addEventListener('click', e => { const b = e.target.closest('[data-storia]'); if (b) fai(b.dataset.storia); });
  // i tasti valgono quando non si sta scrivendo in un campo (lì Ctrl+Z annulla il testo)
  const tasti = e => {
    if (!(e.ctrlKey || e.metaKey) || inScrittura(e.target)) return;
    const k = e.key.toLowerCase();
    if (k === 'z' && !e.shiftKey) { e.preventDefault(); fai('annulla'); }
    else if (k === 'y' || (k === 'z' && e.shiftKey)) { e.preventDefault(); fai('ripeti'); }
  };
  document.addEventListener('keydown', tasti);
  storia.ascolta.push(aggiorna);
  aggiorna();
  return {aggiorna, togli: () => document.removeEventListener('keydown', tasti)};
}
