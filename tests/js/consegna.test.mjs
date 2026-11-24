// Checklist "Pronto per la consegna": controlli puri sui dati del lab.
import test from 'node:test';
import assert from 'node:assert/strict';
import { controlliConsegna, htmlConsegna } from '../../src/gui/static/js/consegna_controlli.js';

const disp = (nome, extra = {}) => Object.assign({nome, tipo: 'router', demoni: ['ospfd'], riferimenti_frr: [],
  riepilogo: {default: [], costi: [], igp: [{protocollo: 'OSPF', auto_cost: null}]}}, extra);
const lab = (dispositivi, extra = {}) => Object.assign({nome: 'rossimario', xml: false, dispositivi}, extra);
const per = (c, id) => c.find(x => x.id === id);

test('lab pulito: tutto verde, con i controlli a lab acceso non fatti', () => {
  const c = controlliConsegna({lab: lab([disp('r1')]), diagnosi: {r1: []}, acceso: false, nomeArchivio: 'rossimario.tar.gz'});
  assert.deepEqual(c.map(x => x.stato), ['ok', 'ok', 'ok', 'nd', 'ok', 'ok']);
});

test('default route, costi senza auto-cost, XML e nome diverso sono avvisi', () => {
  const r1 = disp('r1', {riepilogo: {default: ['BGP network 0.0.0.0/0'], costi: ['eth0 50'], igp: [{protocollo: 'OSPF', auto_cost: null}]}});
  const c = controlliConsegna({lab: lab([r1], {xml: true}), diagnosi: {r1: []}, nomeArchivio: 'altro'});
  for (const id of ['default', 'auto', 'xml', 'nome']) assert.equal(per(c, id).stato, 'avviso', id);
  assert.match(per(c, 'auto').dettaglio, /r1/);
});

test('con auto-cost i costi espliciti vanno bene', () => {
  const r1 = disp('r1', {riepilogo: {default: [], costi: ['eth0 50'], igp: [{protocollo: 'OSPF', auto_cost: '100'}]}});
  assert.equal(per(controlliConsegna({lab: lab([r1]), diagnosi: {}}), 'auto').stato, 'ok');
});

test('errori di frr.conf e riferimenti non definiti sono rossi; senza diagnostica resta da fare', () => {
  const r1 = disp('r1', {riferimenti_frr: [{gravita: 'errore', riga: 7, messaggio: 'route-map X non definita'}]});
  const c = controlliConsegna({lab: lab([r1]), diagnosi: {r1: [{gravita: 'errore', riga: 3, messaggio: 'refuso'}, {gravita: 'avviso', riga: 4, messaggio: 'x'}]}});
  assert.equal(per(c, 'frr').stato, 'ko');
  assert.match(per(c, 'frr').titolo, /^2 errori/);
  assert.equal(per(controlliConsegna({lab: lab([disp('r1')])}), 'frr').stato, 'nd');
});

test('ridistribuzione: non letta, attiva, non attiva', () => {
  const base = {lab: lab([disp('r1')]), diagnosi: {}, acceso: true};
  assert.equal(per(controlliConsegna(base), 'redistribuzione').stato, 'nd');
  assert.equal(per(controlliConsegna({...base, ridistribuzione: [{router: 'r1', igp: 'RIP', ok: true}]}), 'redistribuzione').stato, 'ok');
  const k = per(controlliConsegna({...base, ridistribuzione: [{router: 'r1', igp: 'RIP', ok: false}]}), 'redistribuzione');
  assert.equal(k.stato, 'ko');
  assert.match(k.dettaglio, /r1 \(RIP\)/);
});

test('il semaforo mostra il caso peggiore e si protegge dall\'HTML', () => {
  const c = controlliConsegna({lab: lab([disp('<b>r1</b>', {riferimenti_frr: [{gravita: 'errore', riga: 1, messaggio: '<i>x</i>'}]})]), diagnosi: {}});
  const h = htmlConsegna(c);
  assert.match(h, /Ci sono errori da correggere/);
  assert.ok(!h.includes('<i>x</i>') && !h.includes('<b>r1</b>'));
});
