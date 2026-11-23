// "Parti da un lab esistente" (editor/da_lab.js) per test_da_lab.py: dalla risposta di
// lab_come_modello (stdin) alla bozza, con la disposizione automatica della Topologia.
//   echo '{...}' | node tests/js/da_lab_dati.mjs
import { grafo, varianti } from '../../src/gui/static/js/disposizione.js';
import { caricaLab } from '../../src/gui/static/js/editor/da_lab.js';
let testo = '';
for await (const c of process.stdin) testo += c;
const dati = JSON.parse(testo);
const posizioni = dati.posizioni || varianti(grafo(dati.lab))[0];
const r = caricaLab(dati, posizioni);
process.stdout.write(JSON.stringify({differenze: r.differenze, errori: r.problemi.filter(p => p.gravita === 'errore'),
  modello0: r.bozza.origine.modello, bozza: r.bozza}));
