// Livelli del disegno (fase 5.6): funzioni pure di static/js/livelli.js su dati scritti a mano.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import * as L from '../../src/gui/static/js/livelli.js';

const router = (nome, asn, ips, neighbor, extra = {}) => Object.assign({
  nome, tipo: 'router', asn, gruppo: asn, demoni: ['bgpd'], loopback: [], nameserver: [], deleghe: [],
  interfacce: ips.map(([ip, lan], k) => ({dev: 'eth' + k, ip, lan})),
  riepilogo: {igp: [], costi: [], bgp_networks: [], neighbor, default: [], redistribute_bgp_igp: []}}, extra);
const nb = (ip, asn, tipo, altro = {}) => Object.assign({ip, asn, tipo, chi: '?', policy: [], relazione: null}, altro);

test('sessioni BGP: giuste, scritte da una parte sola, AS sbagliato', () => {
  const lab = {dispositivi: [
    router('r1', '1', [['10.0.0.1/30', 'A'], ['10.0.1.1/30', 'B']], [nb('10.0.0.2', '2', 'eBGP'), nb('10.0.1.2', '9', 'eBGP')]),
    router('r2', '2', [['10.0.0.2/30', 'A']], [nb('10.0.0.1', '1', 'eBGP')]),
    router('r3', '3', [['10.0.1.2/30', 'B']], []),
  ]};
  const s = Object.fromEntries(L.sessioniBgp(lab).map(x => [x.a + '-' + x.b, x]));
  assert.equal(s['r1-r2'].stato, 'ok');
  assert.equal(s['r1-r2'].lan, 'A');
  assert.equal(s['r1-r3'].stato, 'ko');
  assert.match(s['r1-r3'].perche, /r3 non ha un neighbor verso r1/);
  lab.dispositivi[2].riepilogo.neighbor = [nb('10.0.1.1', '1', 'eBGP')];
  assert.match(L.sessioniBgp(lab).find(x => x.b === 'r3' || x.a === 'r3').perche, /remote-as 9 per r3, che è AS3/);
});

test('policy, Customer-Provider-Peer, segni, resolver, DNS, avvisi', () => {
  const pol = [{direzione: 'in', breve: 'LP 150', testo: 'route-map ...'}, {direzione: 'out', breve: '', testo: 'prefix-list permit any'}];
  const lab = {avvisi_config: ['AS2: costi OSPF espliciti su r2 eth0', 'r10: manca qualcosa'], avvisi_topologia: [], dispositivi: [
    router('r1', '1', [['10.0.0.1/30', 'A']], [nb('10.0.0.2', '2', 'eBGP', {policy: pol, relazione: 'provider', chi: 'r2'})],
      {loopback: ['1.1.1.1/32']}),
    router('r2', '2', [['10.0.0.2/30', 'A']], [nb('10.0.0.1', '1', 'eBGP')]),
    router('r10', '2', [['10.0.0.6/30', 'B']], []),
    {nome: 'pc', tipo: 'host', interfacce: [{dev: 'eth0', ip: '20.0.0.5/24', lan: 'C'}], loopback: [], nameserver: ['20.0.0.53'], demoni: []},
    {nome: 'local', tipo: 'dns', interfacce: [{dev: 'eth0', ip: '20.0.0.53/24', lan: 'C'}], loopback: [], nameserver: [], demoni: [],
     deleghe: [{zona: 'com', ns: 'dns.com', ip: '20.0.0.9', server: null}]},
  ]};
  assert.deepEqual(L.siglePolicy(lab).map(x => [x.router, x.testo, x.lan]), [['r1', 'LP 150 in', 'A']], 'solo le policy che cambiano qualcosa');
  assert.deepEqual(L.relazioniCpp(lab), [{customer: 'r1', provider: 'r2', lan: 'A'}]);
  assert.deepEqual(L.segniRouter(lab.dispositivi[0]).loopback, ['1.1.1.1']);
  assert.equal(L.resolver(lab, lab.dispositivi[3]), 'ns: local');
  assert.equal(L.resolver(lab, lab.dispositivi[0]), '', 'i router no');
  assert.deepEqual(L.alberoDns(lab), [{da: 'local', a: null, zona: 'com', ns: 'dns.com', ip: '20.0.0.9'}]);
  const av = L.avvisiSulDisegno(lab);
  assert.deepEqual(Object.keys(av.dev).sort(), ['r10', 'r2'], 'r1 non è citato (r10 non conta)');
  assert.deepEqual(Object.keys(av.as), ['2']);
});
