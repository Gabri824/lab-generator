// tests/js/componenti.test.mjs
// Test dei componenti comuni della GUI che non hanno bisogno del browser (node --test).
// Li lancia tests/test_pagina.py quando Node è installato.
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { htmlAnteprima, htmlConflitto, htmlFile } from '../../src/gui/static/js/componenti/diff.js';
import { htmlErrori } from '../../src/gui/static/js/componenti/errori.js';
import { Storia } from '../../src/gui/static/js/componenti/storia.js';

const ANTEPRIMA = {
  titolo: 'Costo OSPF di r1 eth1: 50', note: ['nota <b>'],
  file: [
    {file: 'r1/etc/frr/frr.conf', stato: 'modificato', righe: [
      {segno: '-', numero: 12, testo: ' network 20.20.0.0/16 area 0.0.0.0'},
      {segno: '+', numero: 12, testo: ' network 20.20.1.0/24 area 0.0.0.0'},
      {segno: '+', numero: 20, testo: 'interface eth1'}]},
    {file: 'pc2.startup', stato: 'nuovo', righe: [{segno: '+', numero: 1, testo: '<script>alert(1)</script>'}]},
  ],
};
const testo = h => h.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();

test('anteprima: conteggi, stato dei file, salto tra gruppi lontani', () => {
  const h = htmlAnteprima(ANTEPRIMA);
  assert.match(testo(h), /2 file · \+3 &minus;1/);
  assert.equal((h.match(/class="diff"/g) || []).length, 2);
  assert.match(h, /diff__stato--nuovo/);
  assert.equal((htmlFile(ANTEPRIMA.file[0]).match(/diff__salto/g) || []).length, 1, 'riga 13 -> 20: un salto');
  assert.match(h, /<span class="diff__dir">r1\/etc\/frr\/<\/span><b>frr\.conf<\/b>/);
});

test('anteprima: il testo dei file e delle note non diventa HTML', () => {
  const h = htmlAnteprima(ANTEPRIMA);
  assert.ok(!h.includes('<script>'));
  assert.ok(h.includes('&lt;script&gt;alert(1)&lt;/script&gt;'));
  assert.ok(h.includes('nota &lt;b&gt;'));
});

test('anteprima vuota e conflitto', () => {
  assert.match(testo(htmlAnteprima({titolo: 'x', file: [], vuoto: 'Nessuna modifica da salvare.'})), /Nessuna modifica da salvare\./);
  const c = htmlConflitto({codice: 409, dati: {file: ['r1/etc/frr/frr.conf']}});
  assert.match(c, /role="alert"/);
  assert.match(testo(c), /Non ho scritto nulla.*r1\/etc\/frr\/frr\.conf/);
});

test('errori: prima gli errori poi gli avvisi, con il campo da raggiungere', () => {
  const h = htmlErrori([
    {campo: 'r2.asn', gravita: 'avviso', messaggio: 'AS mancante'},
    {campo: 'r1.interfaces[0].ip', gravita: 'errore', messaggio: 'Formato non valido'},
  ]);
  assert.match(testo(h), /1 errore · 1 avviso/);
  assert.ok(h.indexOf('r1.interfaces[0].ip') < h.indexOf('r2.asn'));
  assert.match(h, /data-campo="r1\.interfaces\[0\]\.ip"/);
  assert.match(testo(htmlErrori([])), /Nessun problema/);
});

test('storia: fai, annulla, ripeti, limite e copie indipendenti', () => {
  const s = new Storia({r: []}, 2);
  assert.equal(s.puoAnnullare, false);
  assert.equal(s.fai({r: []}), false, 'stesso stato: niente da annullare');
  s.fai({r: ['r1']}); s.fai({r: ['r1', 'r2']}); s.fai({r: ['r1', 'r2', 'r3']});
  assert.deepEqual(s.annulla(), {r: ['r1', 'r2']});
  assert.deepEqual(s.annulla(), {r: ['r1']});
  assert.equal(s.annulla(), null, 'limite di 2 passi');
  assert.deepEqual(s.ripeti(), {r: ['r1', 'r2']});
  s.fai({r: ['x']});
  assert.equal(s.puoRipetere, false, 'una modifica nuova svuota i ripeti');
  const st = s.stato; st.r.push('y');
  assert.deepEqual(s.stato, {r: ['x']}, 'lo stato restituito è una copia');
});
