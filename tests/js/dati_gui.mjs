// Valori che la GUI manda al motore, calcolati dalle funzioni di static/js/proposte.js, per
// test_modifica_gui.py (stessi file del terminale).
//   node tests/js/dati_gui.mjs '{"tipo": ..., "valori": ...}'            -> datiDispositivo
//   node tests/js/dati_gui.mjs '{"funzione": "...", "argomenti": [...]}'  -> funzione(...argomenti)
import * as P from '../../src/gui/static/js/proposte.js';
const x = JSON.parse(process.argv[2]);
const r = x.funzione ? P[x.funzione](...x.argomenti) : P.datiDispositivo(x.tipo, x.valori);
process.stdout.write(JSON.stringify(r));
