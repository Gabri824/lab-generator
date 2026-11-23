// Segni dei livelli del disegno (static/js/livelli.js) per un lab letto da gui/dati.py, per
// test_livelli_disegno.py:  echo '{"lab": {...}}' | node tests/js/livelli_dati.mjs
import * as L from '../../src/gui/static/js/livelli.js';
let testo = '';
for await (const c of process.stdin) testo += c;
const {lab} = JSON.parse(testo);
process.stdout.write(JSON.stringify({
  sessioni: L.sessioniBgp(lab), policy: L.siglePolicy(lab), cpp: L.relazioniCpp(lab), dns: L.alberoDns(lab),
  segni: Object.fromEntries(lab.dispositivi.map(d => [d.nome, L.segniRouter(d)])),
  resolver: Object.fromEntries(lab.dispositivi.map(d => [d.nome, L.resolver(lab, d)])),
  avvisi: L.avvisiSulDisegno(lab),
}));
