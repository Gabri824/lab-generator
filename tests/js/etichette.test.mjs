// Etichette delle interfacce: il costo OSPF compare solo se è scritto nel frr.conf.
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { etichettaIface, largIface, testoCosto } from '../../src/gui/static/js/etichette.js';

const base = {dev: 'eth1', ip: '10.0.0.1/30'};

test('senza costo scritto: niente pezzo del costo', () => {
  for (const costo of [undefined, null, '']) {
    const it = Object.assign({}, base, {costo});
    assert.equal(testoCosto(it), '');
    const h = etichettaIface(it, 0, 0, '#000');
    assert.ok(!h.includes('class="cs"') && !h.includes('<title>'), h);
  }
});

test('costo scritto: pezzo c<N> con la spiegazione e etichetta più larga', () => {
  const it = Object.assign({}, base, {costo: '20'});
  const h = etichettaIface(it, 0, 0, '#000');
  assert.match(h, />c20<\/text>/);
  assert.match(h, /<title>eth1: costo OSPF 20 \(scritto nel frr\.conf\)<\/title>/);
  assert.ok(largIface(it) > largIface(base));
  // le parti stanno tutte dentro il contorno dell'etichetta
  const larghezza = +h.match(/class="pill" x="[^"]*" y="[^"]*" width="([^"]+)"/)[1];
  assert.ok(Math.abs(larghezza - largIface(it)) < 1e-9);
});

test('costo numerico (dal JSON) e valori non validi', () => {
  assert.equal(testoCosto(Object.assign({}, base, {costo: 7})), 'c7');
  assert.equal(testoCosto(Object.assign({}, base, {costo: 'abc'})), '');
  assert.equal(testoCosto(Object.assign({}, base, {costo: '<b>'})), '');
});

test('senza IP il costo resta accanto al nome', () => {
  const h = etichettaIface({dev: 'eth0', ip: '', costo: '5'}, 0, 0, '#000');
  assert.match(h, />c5<\/text>/);
  assert.ok(!h.includes('class="nt"'));
});
