// Proposte dei moduli della modalità Modifica (static/js/proposte.js).
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { assegnati, ipDelModulo, ipUsati, nomeLibero, primoIpLibero, reteNormalizzata, stessaParteHost,
  subnetDellaLan, vicinatoDellaLan } from '../../src/gui/static/js/proposte.js';

const disp = (nome, tipo, its, extra = {}) => Object.assign({nome, tipo, demoni: [], loopback: [], gruppo: null,
  interfacce: its.map(([dev, lan, ip]) => ({dev, lan, ip}))}, extra);
const LAB = {
  lan: [{nome: 'A', subnet: '10.0.0.0/24'}, {nome: 'B', subnet: '10.0.1.0/30'}, {nome: 'C', subnet: ''}],
  dispositivi: [
    disp('as20r1', 'router', [['eth0', 'A', '10.0.0.1/24'], ['eth1', 'B', '10.0.1.1/30']], {demoni: ['ospfd', 'bgpd'], gruppo: 20, loopback: ['1.1.1.1/32']}),
    disp('as20r2', 'router', [['eth0', 'B', '10.0.1.2/30']], {demoni: ['ospfd'], gruppo: 20}),
    disp('pc1', 'host', [['eth0', 'A', '10.0.0.2/24']]),
  ],
};

test('IP usati e primo libero', () => {
  const u = ipUsati(LAB);
  assert.ok(u.has('10.0.0.1') && u.has('1.1.1.1'));
  assert.equal(primoIpLibero('10.0.0.0/24', u), '10.0.0.3/24');
  assert.equal(primoIpLibero('10.0.0.0/24', u, 50), '10.0.0.50/24', 'parte host preferita, se libera');
  assert.equal(primoIpLibero('10.0.0.0/24', u, 1), '10.0.0.3/24', 'preferita occupata: la prima libera');
  assert.equal(primoIpLibero('10.0.1.0/30', u), '', '/30 pieno');
  assert.equal(primoIpLibero('10.0.2.0/31', new Set()), '10.0.2.0/31', '/31: anche il primo indirizzo');
  assert.equal(primoIpLibero('sbagliata', u), '');
  assert.equal(subnetDellaLan(LAB, 'A'), '10.0.0.0/24');
  assert.equal(subnetDellaLan(LAB, 'C'), '');
});

test('IP scritto nel modulo', () => {
  assert.equal(ipDelModulo('5', '10.0.0.1/24'), '10.0.0.5/24');
  assert.equal(ipDelModulo('1.5', '10.0.0.0/16'), '10.0.1.5/16');
  assert.equal(ipDelModulo('10.0.0.9', '10.0.0.0/24'), '10.0.0.9/24');
  assert.equal(ipDelModulo('10.0.0.9/25', '10.0.0.0/24'), '10.0.0.9/25');
});

test('nomi liberi', () => {
  assert.equal(nomeLibero(LAB, 'router', '20'), 'as20r3', 'router tutti as<AS>r<n>');
  assert.equal(nomeLibero(LAB, 'router', ''), 'r1', 'AS sconosciuto');
  assert.equal(nomeLibero(LAB, 'host'), 'host1');
  assert.equal(nomeLibero(LAB, 'dns'), 'root', 'il primo DNS è root, come nel wizard');
  const conDns = {lan: LAB.lan, dispositivi: [...LAB.dispositivi, disp('root', 'dns', [['eth0', 'A', '10.0.0.53/24']])]};
  assert.equal(nomeLibero(conDns, 'dns'), 'dns1');
});

test('vicini della LAN', () => {
  const v = vicinatoDellaLan(LAB, 'B');
  assert.deepEqual(v.routers, ['as20r1', 'as20r2']);
  assert.deepEqual(v.igp, ['ospf']);
  assert.equal(v.asn, '20');
  assert.equal(v.gateway, '10.0.1.1');
  assert.equal(vicinatoDellaLan(LAB, 'A').membri.join(','), 'as20r1,pc1');
  assert.equal(vicinatoDellaLan(LAB, 'C').gateway, '');
});

test('nuova subnet: stessa parte host e IP scelti', () => {
  assert.equal(stessaParteHost('10.0.0.7/24', '10.0.0.0/24', '192.168.5.0/24'), '192.168.5.7/24');
  assert.equal(stessaParteHost('10.0.0.200/24', '10.0.0.0/24', '192.168.5.0/30'), '', 'non ci sta');
  assert.equal(reteNormalizzata('10.0.5.9/24'), '10.0.5.0/24');
  assert.equal(reteNormalizzata('ciao'), '');
  assert.deepEqual(assegnati({'ip:r1:eth0': '9', 'ip:pc1:eth0': '192.168.5.20', altro: 'x', 'ip:r2:eth1': ''}, '192.168.5.0/24'),
    [['r1', 'eth0', '192.168.5.9/24'], ['pc1', 'eth0', '192.168.5.20/24']]);
});

test('posizioni: i nodi nuovi vicino ai vicini, gli altri fermi', async () => {
  const { completaPosizioni } = await import('../../src/gui/static/js/proposte.js');
  const G = {nodes: ['d:r1', 'd:r2', 'l:A', 'd:pc9'].map(id => ({id})),
    links: [{a: 'd:r1', b: 'l:A'}, {a: 'd:r2', b: 'l:A'}, {a: 'd:pc9', b: 'l:A'}]};
  const base = {'d:r1': {x: 0, y: 0}, 'd:r2': {x: 200, y: 0}, 'l:A': {x: 100, y: 50}};
  const p = completaPosizioni(G, base);
  assert.deepEqual(p['d:r1'], {x: 0, y: 0});
  assert.deepEqual(p['l:A'], {x: 100, y: 50});
  const d = Math.hypot(p['d:pc9'].x - 100, p['d:pc9'].y - 50);
  assert.ok(d > 30 && d < 200, `pc9 vicino alla LAN A (distanza ${d})`);
  assert.equal(completaPosizioni(G, {'d:r1': {x: 0, y: 0}}), null, 'ne mancano più della metà');
  assert.deepEqual(Object.keys(completaPosizioni(G, Object.assign({'d:pc9': {x: 5, y: 5}}, base))).sort(), ['d:pc9', 'd:r1', 'd:r2', 'l:A']);
  // LAN nuova tra due dispositivi già disposti: nel mezzo
  const G2 = {nodes: ['d:a', 'd:b', 'l:N'].map(id => ({id})), links: [{a: 'd:a', b: 'l:N'}, {a: 'd:b', b: 'l:N'}]};
  assert.deepEqual(completaPosizioni(G2, {'d:a': {x: 0, y: 0}, 'd:b': {x: 100, y: 0}})['l:N'], {x: 50, y: 0});
});

test('BGP: reti, loopback, reti eBGP, parametri delle default route', async () => {
  const P = await import('../../src/gui/static/js/proposte.js');
  assert.deepEqual(P.listaReti('20.20.0.0/16, 30.30.1.0/24;20.20.0.0/16'), ['20.20.0.0/16', '30.30.1.0/24']);
  assert.deepEqual(P.listaReti('20.20.5.9/16'), ['20.20.0.0/16'], 'normalizzata');
  assert.throws(() => P.listaReti('20.20/16'), /non valida/);
  assert.equal(P.prossimaLoopback(LAB), '1.1.1.2/32');
  assert.equal(P.prossimaLoopback({lan: [], dispositivi: [disp('r', 'router', [])]}), '', 'nessuna serie: niente proposta');
  const due = {lan: LAB.lan, dispositivi: [...LAB.dispositivi, disp('x', 'router', [], {loopback: ['1.1.1.2/32']})]};
  assert.equal(P.prossimaLoopback(due), '1.1.1.3/32');
  const conAltroAs = {lan: LAB.lan, dispositivi: [...LAB.dispositivi.slice(0, 1),
    disp('as30r1', 'router', [['eth0', 'B', '10.0.1.2/30']], {demoni: ['bgpd'], gruppo: 30})]};
  assert.deepEqual(P.retiEbgp(conAltroAs, 'as20r1'), ['10.0.1.0/30']);
  assert.deepEqual(P.retiEbgp(LAB, 'as20r1'), [], 'stesso AS: niente eBGP');
  const nb = {'1.0.0.1': '10', '2.0.0.1': '20'};
  assert.deepEqual(P.parametriDefaultBgp({'n:2.0.0.1': true, solo: false, extra: '9.0.0.0/8'}, nb), {scelti: ['2.0.0.1'], solo: false, extra: []});
  assert.deepEqual(P.parametriDefaultBgp({'n:1.0.0.1': true, 'n:2.0.0.1': true, solo: true, extra: '9.0.0.0/8'}, nb).extra, ['9.0.0.0/8']);
  assert.throws(() => P.parametriDefaultBgp({solo: true}, nb), /almeno un neighbor/);
  assert.deepEqual(P.parametriDefaultIgp('ospf', {ha_default: true}), {modo: '1', reti: ['0.0.0.0/0'], ha_default: true});
  assert.deepEqual(P.parametriDefaultIgp('rip', {modo: '1', rete: ''}), {modo: '1', reti: ['0.0.0.0/0'], ha_default: false});
  assert.deepEqual(P.parametriDefaultIgp('rip', {modo: '1', rete: '5.5.5.0/24'}).reti, ['5.5.5.0/24']);
  assert.equal(P.parametriDefaultIgp('rip', {modo: '2'}).modo, '2');
});

test('policy BGP: reti scelte, parametri delle policy e di Customer-Provider-Peer', async () => {
  const P = await import('../../src/gui/static/js/proposte.js');
  assert.deepEqual(P.retiScelte({'r:10.0.0.0/8': true, 'r:20.0.0.0/8': false, altre: '30.0.0.0/8, 10.0.0.0/8'}), ['10.0.0.0/8', '30.0.0.0/8']);
  assert.deepEqual(P.parametriPolicy('med', {valore: '20'}), {tipo: 'med', valore: 20});
  assert.deepEqual(P.parametriPolicy('local_pref', {valore: 150}), {tipo: 'local_pref', valore: 150, reti: []}, 'senza reti: tutte le rotte');
  assert.deepEqual(P.parametriPolicy('prefix_list', {direzione: 'out', 'r:1.0.0.0/24': true}), {tipo: 'prefix_list', direzione: 'out', reti: ['1.0.0.0/24']});
  assert.throws(() => P.parametriPolicy('access_list', {}), /almeno una rete/);
  assert.throws(() => P.parametriPolicy('med', {valore: 'x'}), /numero intero/);
  assert.deepEqual(P.parametriCpp('customer', {'r:1.0.0.0/24': true}), {relazione: 'customer', reti_out: []}, 'verso un cliente si annuncia tutto');
  assert.deepEqual(P.parametriCpp('peer', {'r:1.0.0.0/24': true}), {relazione: 'peer', reti_out: ['1.0.0.0/24']});
  assert.equal(P.RELAZIONE_INVERSA.provider, 'customer');
});
