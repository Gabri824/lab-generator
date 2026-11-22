// tests/js/azioni.test.mjs
// Azioni dell'editor sulla bozza (src/gui/static/js/editor/azioni.js), con node --test.
import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  aggiungiDispositivo, aggiungiLan, aggiungiZona, collega, duplica, elimina, imposta, impostaInterfaccia, rinominaPerAs, impostaProprieta, modificaElenco, posizioni, ridimensionaZona, sposta,
  spostaInterfaccia,
} from '../../src/gui/static/js/editor/azioni.js';
import { converti, nuovaBozza } from '../../src/gui/static/js/editor/bozza.js';

function tre() {
  let b = nuovaBozza('prova'), r;
  r = aggiungiDispositivo(b, 'router', 0, 0); b = r.bozza; const a = r.id;
  r = aggiungiDispositivo(b, 'router', 200, 0); b = r.bozza; const x = r.id;
  r = aggiungiDispositivo(b, 'host', 100, 200); b = r.bozza; const h = r.id;
  return {b, a, x, h};
}

test('aggiungere: id nuovi, griglia di 20 px solo se chiesta, la bozza di partenza non cambia', () => {
  const b0 = nuovaBozza('');
  const r = aggiungiDispositivo(b0, 'router', 33, 47, true);
  assert.deepEqual([r.bozza.dispositivi[0].x, r.bozza.dispositivi[0].y], [40, 40]);
  assert.equal(b0.dispositivi.length, 0);
  const r2 = aggiungiDispositivo(r.bozza, 'dns', 33, 47);
  assert.notEqual(r2.id, r.id);
  assert.deepEqual([r2.bozza.dispositivi[1].x, r2.bozza.dispositivi[1].y], [33, 47]);
  const l = aggiungiLan(r2.bozza, 101, 99, true);
  assert.deepEqual([l.bozza.lan[0].x, l.bozza.lan[0].y, l.bozza.lan[0].punto], [100, 100, false]);
  assert.throws(() => aggiungiDispositivo(b0, 'switch', 0, 0));
});

test('collegare due dispositivi: link diretto, una volta sola', () => {
  const {b, a, x} = tre();
  const r = collega(b, a, x);
  assert.equal(r.bozza.lan.length, 1);
  assert.equal(r.bozza.lan[0].punto, true);
  assert.deepEqual(r.bozza.collegamenti.map(c => c.dispositivo), [a, x]);
  const di_nuovo = collega(r.bozza, x, a);
  assert.equal(di_nuovo.bozza.lan.length, 1);
  assert.match(di_nuovo.messaggio, /già collegati/);
  assert.match(collega(b, a, a).messaggio, /altro dispositivo/);
});

test('terzo dispositivo sul link diretto: diventa un nodo LAN nel punto di mezzo, con la stessa subnet', () => {
  let {b, a, x, h} = tre();
  let r = collega(b, a, x); b = r.bozza; const l = r.id;
  b = imposta(b, l, 'subnet', '10.0.0.0/24');
  b = imposta(b, l, 'nome', 'k');
  r = collega(b, h, l);
  const lan = r.bozza.lan[0];
  assert.equal(lan.punto, false);
  assert.deepEqual([lan.x, lan.y, lan.subnet, lan.nome], [100, 0, '10.0.0.0/24', 'K']);
  const conv = converti(r.bozza);
  assert.deepEqual(conv.problemi.filter(p => p.gravita === 'errore'), []);
  assert.equal(conv.modello.hosts[0].interfaces[0].ip, '10.0.0.3/24');
  assert.match(collega(r.bozza, h, l).messaggio, /già in questa LAN/);
});

test('collegare a un nodo LAN', () => {
  let {b, a, x} = tre();
  const n = aggiungiLan(b, 100, 100); b = n.bozza;
  b = collega(b, a, n.id).bozza;
  b = collega(b, x, n.id).bozza;
  assert.equal(b.lan.length, 1);
  assert.deepEqual(b.collegamenti.map(c => c.lan), [n.id, n.id]);
  assert.match(collega(b, n.id, a).messaggio, /partendo da un dispositivo/);
});

test('eliminare: un dispositivo porta via i suoi collegamenti e il link diretto rimasto monco', () => {
  let {b, a, x, h} = tre();
  b = collega(b, a, x).bozza;
  const n = aggiungiLan(b, 0, 0); b = collega(n.bozza, h, n.id).bozza; b = collega(b, a, n.id).bozza;
  b.resolver = h;
  const e = elimina(b, [x]);
  assert.equal(e.lan.length, 1, 'il link diretto a-x sparisce, il nodo LAN resta');
  assert.deepEqual(e.collegamenti.map(c => c.dispositivo).sort(), [a, h].sort());
  assert.equal(elimina(b, [h]).resolver, null);
  const solo = elimina(b, [n.id]);
  assert.equal(solo.collegamenti.length, 2, 'eliminare una LAN toglie i suoi collegamenti');
  const c = b.collegamenti.find(x2 => x2.dispositivo === h).id;
  assert.equal(elimina(b, [c]).collegamenti.length, 3, 'si può togliere un solo collegamento');
});

test('spostare: insieme, con la griglia sulla posizione finale; i link diretti non si spostano da soli', () => {
  let {b, a, x} = tre();
  b = collega(b, a, x).bozza;
  const p = posizioni(b, [a, x, b.lan[0].id]);
  assert.deepEqual(Object.keys(p), [a, x], 'il link diretto non ha una posizione sua');
  const s = sposta(b, p, 13, 27, true);
  assert.deepEqual(s.dispositivi.slice(0, 2).map(d => [d.x, d.y]), [[20, 20], [220, 20]]);
  const s2 = sposta(b, p, 13, 27, false);
  assert.deepEqual(s2.dispositivi[0], Object.assign({}, b.dispositivi[0], {x: 13, y: 27}));
});

test('pannello: nome, subnet con rinumerazione, IP, nome del lab', () => {
  let {b, a, x} = tre();
  let r = collega(b, a, x); b = r.bozza; const l = r.id;
  b = imposta(b, l, 'subnet', '10.0.0.0/30');
  b = imposta(b, b.collegamenti[1].id, 'ip', '10.0.0.2/30');
  b = imposta(b, l, 'subnet', '192.168.1.0/30');
  assert.equal(b.collegamenti[1].ip, '192.168.1.2/30');
  b = imposta(b, a, 'nome', 'core');
  b = imposta(b, null, 'nome_lab', ' esame1 ');
  b = imposta(b, l, 'subnet', 'boh');
  assert.equal(b.lan[0].subnet, 'boh');
  assert.equal(b.dispositivi[0].nome, 'core');
  assert.equal(b.nome, 'esame1');
  assert.ok(converti(b).problemi.some(p => p.id === l && p.messaggio.includes('Subnet non valida')));
});

test('ordine delle interfacce', () => {
  let {b, a, x, h} = tre();
  b = collega(b, a, x).bozza; b = collega(b, a, h).bozza;
  const [c0, c1] = converti(b).interfacce[a];
  const s = spostaInterfaccia(b, c1, -1);
  assert.deepEqual(converti(s).interfacce[a], [c1, c0]);
  assert.deepEqual(spostaInterfaccia(b, c0, -1), b, 'la prima non sale');
  assert.deepEqual(spostaInterfaccia(b, c1, +1), b, 'l\'ultima non scende');
});

test('zone: valore iniziale (AS vuoto, prima area 0.0.0.0, poi vuota), clic = riquadro standard', () => {
  let b = nuovaBozza(''), r;
  r = aggiungiZona(b, 'as', {x: 10, y: 10, w: 200, h: 100}); b = r.bozza;
  assert.deepEqual(b.zone[0], {id: r.id, tipo: 'as', valore: '', x: 10, y: 10, w: 200, h: 100});
  r = aggiungiZona(b, 'ospf', {x: 0, y: 0, w: 300, h: 300}); b = r.bozza;
  assert.equal(b.zone[1].valore, '0.0.0.0');
  assert.equal(b.zone[1].stub, false);
  r = aggiungiZona(b, 'ospf', {x: 500, y: 0, w: 100, h: 100}); b = r.bozza;
  assert.equal(b.zone[2].valore, '', 'la seconda area si scrive');
  r = aggiungiZona(b, 'rip', {x: 100, y: 100, w: 3, h: 2}, true); b = r.bozza;
  assert.deepEqual([b.zone[3].x, b.zone[3].y, b.zone[3].w, b.zone[3].h], [-20, 20, 240, 160], 'clic: 240x160 centrato, sulla griglia');
  assert.throws(() => aggiungiZona(b, 'eigrp', {x: 0, y: 0, w: 99, h: 99}));
});

test('zone: ridimensionare da ogni angolo, l\'opposto resta fermo, lato minimo 40', () => {
  const b = aggiungiZona(nuovaBozza(''), 'as', {x: 100, y: 100, w: 200, h: 100}).bozza, id = b.zone[0].id, p0 = {x: 100, y: 100, w: 200, h: 100};
  const r = (angolo, p) => { const z = ridimensionaZona(b, id, angolo, p, p0).zone[0]; return [z.x, z.y, z.w, z.h]; };
  assert.deepEqual(r('se', {x: 400, y: 260}), [100, 100, 300, 160]);
  assert.deepEqual(r('nw', {x: 50, y: 20}), [50, 20, 250, 180]);
  assert.deepEqual(r('ne', {x: 350, y: 150}), [100, 150, 250, 50]);
  assert.deepEqual(r('sw', {x: 0, y: 400}), [0, 100, 300, 300]);
  assert.deepEqual(r('se', {x: 0, y: 0}), [100, 100, 40, 40], 'non si rovescia: lato minimo');
  assert.deepEqual(ridimensionaZona(b, id, 'se', {x: 413, y: 267}, p0, true).zone[0].w, 320, 'con la griglia');
  assert.deepEqual(b.zone[0], Object.assign({id}, {tipo: 'as', valore: '', x: 100, y: 100, w: 200, h: 100}), 'la bozza di partenza non cambia');
});

test('zone: valore e stub dal pannello, spostare ed eliminare', () => {
  let b = aggiungiZona(nuovaBozza(''), 'ospf', {x: 0, y: 0, w: 100, h: 100}).bozza;
  const id = b.zone[0].id;
  b = imposta(b, id, 'valore', ' 1.1.1.1 ');
  b = imposta(b, id, 'stub', true);
  assert.deepEqual([b.zone[0].valore, b.zone[0].stub], ['1.1.1.1', true]);
  b = imposta(b, id, 'stub', false);
  assert.equal(b.zone[0].stub, false);
  const s = sposta(b, posizioni(b, [id]), 30, 40);
  assert.deepEqual([s.zone[0].x, s.zone[0].y, s.zone[0].w], [30, 40, 100]);
  assert.equal(elimina(b, [id]).zone.length, 0);
});

test('proprietà del router: ridistribuzione, network IGP scritte, rotte statiche', () => {
  let b = nuovaBozza(''), r = aggiungiDispositivo(b, 'router', 0, 0); b = r.bozza; const id = r.id;
  b = impostaProprieta(b, id, 'redistribuisci', false);
  b = impostaProprieta(b, id, 'igp', ' 10.0.0.0/30, 10.0.1.0/30 ');
  b = modificaElenco(b, id, 'statica', 'aggiungi');
  b = modificaElenco(b, id, 'statica', 'aggiungi');
  b = impostaProprieta(b, id, 'statica', 'default', [0, 'rete']);
  b = impostaProprieta(b, id, 'statica', '10.0.0.2', [0, 'via']);
  b = impostaProprieta(b, id, 'statica', 'eth0', [0, 'dev']);
  assert.deepEqual(b.dispositivi[0].router, {redistribuisci_bgp: false, igp_networks: '10.0.0.0/30, 10.0.1.0/30',
    statiche: [{rete: 'default', via: '10.0.0.2', dev: 'eth0'}, {rete: '', via: ''}]});
  b = modificaElenco(b, id, 'statica', 'togli', [0]);
  assert.deepEqual(b.dispositivi[0].router.statiche, [{rete: '', via: ''}]);
});

test('proprietà del DNS: tipo per ".", deleghe, zone e record, ricorsione, DNSSEC; gateway e resolver del lab', () => {
  let b = nuovaBozza(''), r = aggiungiDispositivo(b, 'dns', 0, 0); b = r.bozza; const id = r.id;
  assert.deepEqual(b.dispositivi[0].dns, {gateway: '', forwarders: null, root_type: 'hint', allow_recursion: null, dnssec_validation: false,
    delegations: [], zone: []}, 'un DNS nuovo parte come nel wizard');
  b = impostaProprieta(b, id, 'gateway', '10.0.0.1');
  b = impostaProprieta(b, id, 'root_type', 'master');
  b = modificaElenco(b, id, 'delega', 'aggiungi');
  b = impostaProprieta(b, id, 'delega', 'com', [0, 'zone']);
  b = modificaElenco(b, id, 'zona', 'aggiungi');
  b = impostaProprieta(b, id, 'zona', 'com.', [0]);
  b = modificaElenco(b, id, 'record', 'aggiungi', [0]);
  b = modificaElenco(b, id, 'record', 'aggiungi', [0]);
  b = impostaProprieta(b, id, 'record', 'www', [0, 0, 'nome']);
  b = impostaProprieta(b, id, 'record', '10.0.1.80', [0, 0, 'valore']);
  b = impostaProprieta(b, id, 'record', 'CNAME', [0, 1, 'tipo']);
  b = modificaElenco(b, id, 'record', 'togli', [0, 1]);
  b = impostaProprieta(b, id, 'ricorsione_reti', '10.0.0.0/24');
  assert.equal(b.dispositivi[0].dns.allow_recursion, null, 'le reti contano solo con la ricorsione accesa');
  b = impostaProprieta(b, id, 'ricorsione', true);
  assert.equal(b.dispositivi[0].dns.allow_recursion, 'any');
  b = impostaProprieta(b, id, 'ricorsione_reti', '10.0.0.0/24');
  b = impostaProprieta(b, id, 'dnssec', true);
  b = impostaProprieta(b, null, 'resolver', id);
  b = impostaProprieta(b, null, 'blocco', ' 10.255.0.0/16 ');
  const dns = b.dispositivi[0].dns;
  assert.deepEqual(dns, {gateway: '10.0.0.1', forwarders: null, root_type: 'master', allow_recursion: '10.0.0.0/24', dnssec_validation: true,
    delegations: [{zone: 'com', ns: '', ip: ''}], zone: [{nome: 'com', record: [{nome: 'www', tipo: 'A', valore: '10.0.1.80', extra: ''}]}]});
  assert.equal(b.resolver, id);
  assert.equal(b.blocco_subnet, '10.255.0.0/16');
  b = impostaProprieta(b, id, 'ricorsione', false);
  assert.equal(b.dispositivi[0].dns.allow_recursion, null);
});

test('duplica: dispositivi, nodi LAN, zone e collegamenti tra loro; nomi, IP e subnet automatici', () => {
  let {b, a, x, h} = tre();
  b = imposta(b, a, 'nome', 'core');
  let r = collega(b, a, x); b = r.bozza; const p = r.id;             // link diretto a-x
  b = imposta(b, p, 'subnet', '10.0.0.0/30');
  const n = aggiungiLan(b, 300, 300); b = n.bozza;
  b = collega(b, x, n.id).bozza; b = collega(b, h, n.id).bozza;      // nodo LAN con x e h
  b = imposta(b, n.id, 'subnet', '10.1.0.0/24');
  b = imposta(b, b.collegamenti.find(c => c.dispositivo === h).id, 'ip', '10.1.0.9/24');
  b = aggiungiZona(b, 'as', {x: -50, y: -50, w: 100, h: 100}).bozza;
  b = imposta(b, b.zone[0].id, 'valore', '7');
  const d = duplica(b, [a, x, n.id, b.zone[0].id]);                  // h non selezionato
  const nuovi = d.bozza.dispositivi.slice(b.dispositivi.length);
  assert.equal(nuovi.length, 2);
  assert.deepEqual(nuovi.map(z => [z.nome, z.x, z.y]), [['r1', 40, 40], ['r3', 240, 40]], 'nomi liberi (r1 è libero: a si chiama core)');
  const lanNuove = d.bozza.lan.slice(b.lan.length);
  assert.deepEqual(lanNuove.map(l => [l.punto, l.subnet, l.nome]), [[true, '', ''], [false, '', '']], 'link diretto e nodo LAN copiati (nell\'ordine di prima), senza subnet');
  const colNuovi = d.bozza.collegamenti.slice(b.collegamenti.length);
  assert.equal(colNuovi.length, 3, 'a-x diretto (2) e x-nodo (1); h non è stato duplicato');
  assert.ok(colNuovi.every(c => c.ip === ''));
  assert.equal(d.bozza.zone.length, 2);
  assert.deepEqual([d.bozza.zone[1].x, d.bozza.zone[1].valore], [-10, '7']);
  assert.equal(d.ids.length, 4, 'selezione nuova: due router, il nodo LAN e la zona');
  const ids = new Set([...d.bozza.dispositivi, ...d.bozza.lan, ...d.bozza.collegamenti, ...d.bozza.zone].map(x => x.id));
  assert.equal(ids.size, d.bozza.dispositivi.length + d.bozza.lan.length + d.bozza.collegamenti.length + d.bozza.zone.length, 'id tutti diversi');
  assert.ok(converti(d.bozza).problemi.some(p => /due riquadri AS/.test(p.messaggio)), 'la zona copiata si sovrappone: errore segnalato');
});

test('nomi dati alla creazione e stabili: entrando in un AS o eliminando un router non cambiano', () => {
  let b = nuovaBozza(''), r;
  for (const x of [0, 100, 200]) { r = aggiungiDispositivo(b, 'router', x, 0); b = r.bozza; }
  r = aggiungiDispositivo(b, 'dns', 0, 100); b = r.bozza;
  assert.deepEqual(b.dispositivi.map(d => d.nome), ['r1', 'r2', 'r3', 'dns1']);
  b = elimina(b, [b.dispositivi[1].id]);
  assert.deepEqual(b.dispositivi.map(d => d.nome), ['r1', 'r3', 'dns1'], 'r3 resta r3');
  b = aggiungiZona(b, 'as', {x: -50, y: -50, w: 400, h: 100}).bozza;
  b = imposta(b, b.zone[0].id, 'valore', '20');
  assert.deepEqual(Object.values(converti(b).nomi), ['r1', 'r3', 'dns1'], 'entrare in un AS non cambia il nome');
  r = aggiungiDispositivo(b, 'router', 300, 0);
  assert.equal(r.bozza.dispositivi.at(-1).nome, 'r2', 'un router nuovo prende il primo nome libero');
});

test('rinomina i router di un AS come as<AS>r<n>, solo su richiesta', () => {
  let b = nuovaBozza(''), r;
  for (const x of [0, 100, 500]) { r = aggiungiDispositivo(b, 'router', x, 0); b = r.bozza; }
  b = aggiungiZona(b, 'as', {x: -50, y: -50, w: 200, h: 100}).bozza;
  const z = b.zone[0].id;
  assert.match(rinominaPerAs(b, z).messaggio, /numero AS/);
  b = imposta(b, z, 'valore', '20');
  const n = rinominaPerAs(b, z);
  assert.deepEqual(n.bozza.dispositivi.map(d => d.nome), ['as20r1', 'as20r2', 'r3']);
  assert.match(n.messaggio, /2 router/);
});

test('interfaccia scelta dal menu: si scambia con quella che aveva quel numero', () => {
  let {b, a, x, h} = tre();
  b = collega(b, a, x).bozza; b = collega(b, a, h).bozza;
  const [c0, c1] = converti(b).interfacce[a];
  const s2 = impostaInterfaccia(b, c1, 0);
  assert.deepEqual(converti(s2).interfacce[a], [c1, c0]);
  assert.deepEqual(impostaInterfaccia(b, c0, 0), b, 'stesso numero: niente da fare');
  assert.deepEqual(impostaInterfaccia(b, c0, 7), b, 'numero che non esiste: niente da fare');
});

test('IP scritto con il solo numero finale: completato dalla subnet della LAN', () => {
  let {b, a, x} = tre();
  const r = collega(b, a, x); b = r.bozza;
  b = imposta(b, r.id, 'subnet', '10.0.0.4/30');
  const c = b.collegamenti[1].id;
  assert.equal(imposta(b, c, 'ip', '6').collegamenti[1].ip, '10.0.0.6/30');
  assert.equal(imposta(b, c, 'ip', '10.0.0.5').collegamenti[1].ip, '10.0.0.5/30', 'IP intero senza maschera');
  assert.equal(imposta(b, c, 'ip', '').collegamenti[1].ip, '', 'vuoto = automatico');
});
