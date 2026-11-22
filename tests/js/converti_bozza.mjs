// Converte una bozza dell'editor nel modello del wizard e lo stampa in JSON (per tests/test_bozza.py).
//   node tests/js/converti_bozza.mjs tests/bozze/ospf_abr.json
import fs from 'node:fs';
import { converti } from '../../src/gui/static/js/editor/bozza.js';

const r = converti(JSON.parse(fs.readFileSync(process.argv[2], 'utf8')));
process.stdout.write(JSON.stringify({modello: r.modello, problemi: r.problemi}));
