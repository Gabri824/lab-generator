// tests/js/bozza.test.mjs
// Regole della bozza dell'editor (src/gui/static/js/editor/bozza.js), con node --test.
// L'identità con il wizard sui lab interi è in tests/test_bozza.py.
import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  chiaveArea, completaIp, converti, elementoDelCampo, leggiRete, nuovaBozza, nuovoId, proponiSubnet, rinumera, testoRete, zoneDelWizard,
} from '../../src/gui/static/js/editor/bozza.js';

// costruttore di bozze di prova: disp('r', x, y, {...}), lan(subnet, {...}), link(d, l, ip)
function costruisci(f) {
  const b = nuovaBozza('prova');
  const disp = (tipo, x, y, extra = {}) => { const d = Object.assign({id: nuovoId(b, 'd'), tipo, nome: '', x, y}, extra); b.dispositivi.push(d); return d.id; };
  const lan = (subnet, extra = {}) => { const l = Object.assign({id: nuovoId(b, 'l'), nome: '', subnet, punto: false, x: 0, y: 0}, extra); b.lan.push(l); return l.id; };
  const link = (d, l, ip = '') => { b.collegamenti.push({id: nuovoId(b, 'c'), dispositivo: d, lan: l, ip}); return b.collegamenti.at(-1).id; };
  const zona = (tipo, valore, x, y, w, h, stub = false) => { b.zone.push({id: nuovoId(b, 'z'), tipo, valore, stub, x, y, w, h}); return b.zone.at(-1).id; };
  f({disp, lan, link, zona, b});
  return b;
}
const errori = conv => conv.problemi.filter(p => p.gravita === 'errore');
const haErrore = (conv, id, parola) => conv.problemi.some(p => p.gravita === 'errore' && p.id === id && p.messaggio.includes(parola));

test('indirizzi: lettura, rete normalizzata, valori sbagliati', () => {
  assert.deepEqual(testoRete(leggiRete('10.0.0.77/24')), '10.0.0.0/24');
  assert.equal(leggiRete('10.0.0.1'), null);
  assert.equal(leggiRete('10.0.0.300/24'), null);
  assert.equal(leggiRete('10.0.0.0/33'), null);
  assert.equal(chiaveArea('0'), '0.0.0.0');
  assert.equal(chiaveArea('1'), '0.0.0.1');
});

test('IP automatici: prima i router, poi gli altri; salta rete, broadcast e IP già presi', () => {
  let h, r1, r2, ch, cr1, cr2;
  const b = costruisci(({disp, lan, link}) => {
    h = disp('host', 0, 0); r1 = disp('router', 0, 0); r2 = disp('router', 0, 0);
    const l = lan('10.0.0.0/29');
    ch = link(h, l); cr1 = link(r1, l, '10.0.0.1/29'); cr2 = link(r2, l);
  });
  const conv = converti(b);
  assert.equal(conv.ip[cr1], '10.0.0.1/29');
  assert.equal(conv.ip[cr2], '10.0.0.2/29', 'il router prima dell\'host');
  assert.equal(conv.ip[ch], '10.0.0.3/29');
  assert.equal(conv.modello.hosts[0].gateway, '10.0.0.1', 'gateway proposto dal primo router della LAN');
  assert.deepEqual(errori(conv), []);
});

test('IP automatici: /31 usa entrambi gli indirizzi, subnet piena è un errore', () => {
  let c1, c2, l3;
  const b = costruisci(({disp, lan, link}) => {
    const a = disp('router', 0, 0), b2 = disp('router', 0, 0), c = disp('router', 0, 0);
    const l = lan('10.0.0.0/31', {punto: true}); c1 = link(a, l); c2 = link(b2, l);
    l3 = lan('10.9.9.0/30'); link(a, l3); link(b2, l3); link(c, l3);
  });
  const conv = converti(b);
  assert.equal(conv.ip[c1], '10.0.0.0/31');
  assert.equal(conv.ip[c2], '10.0.0.1/31');
  assert.ok(haErrore(conv, l3, 'non ha più indirizzi liberi'));
});

test('IP scritti a mano: fuori subnet, broadcast, doppioni', () => {
  let c1, c2, c3;
  const b = costruisci(({disp, lan, link}) => {
    const a = disp('router', 0, 0), x = disp('router', 0, 0), y = disp('host', 0, 0);
    const l = lan('10.0.0.0/24');
    c1 = link(a, l, '10.0.1.1/24'); c2 = link(x, l, '10.0.0.255/24'); c3 = link(y, l, '10.0.0.7/24');
    const l2 = lan('10.0.5.0/24'); link(y, l2, '10.0.5.7/24');
  });
  b.collegamenti.push({id: 'cdoppio', dispositivo: b.dispositivi[0].id, lan: b.lan[1].id, ip: '10.0.5.7/24'});
  const conv = converti(b);
  assert.ok(haErrore(conv, c1, 'non è nella subnet'));
  assert.ok(haErrore(conv, c2, 'broadcast'));
  assert.equal(conv.ip[c3], '10.0.0.7/24');
  assert.ok(haErrore(conv, 'cdoppio', 'già usato'));
});

test('subnet ricavata dal primo IP scritto; LAN senza subnet né IP è un errore', () => {
  let ch, lvuota;
  const b = costruisci(({disp, lan, link}) => {
    const h = disp('host', 0, 0), r = disp('router', 0, 0);
    const l = lan(''); ch = link(h, l, '192.168.5.10/24'); link(r, l);
    lvuota = lan(''); link(r, lvuota);
  });
  const conv = converti(b);
  assert.equal(conv.subnet[b.lan[0].id], '192.168.5.0/24');
  assert.equal(conv.ip[ch], '192.168.5.10/24');
  assert.equal(conv.modello.routers.r1.interfaces[0].ip, '192.168.5.1/24');
  assert.ok(haErrore(conv, lvuota, 'Manca la subnet'));
});

test('zone per posizione: AS e RIP sul centro del router, bordi compresi', () => {
  const b = costruisci(({disp, lan, link, zona}) => {
    const a = disp('router', 100, 100), x = disp('router', 300, 100), y = disp('router', 500, 500);
    const l = lan('10.0.0.0/24'); link(a, l); link(x, l); link(y, l);
    zona('as', '20', 0, 0, 100, 100);          // a sul bordo in basso a destra
    zona('rip', '', 250, 50, 100, 100);
  });
  const m = converti(b).modello;
  assert.deepEqual(Object.keys(m.routers), ['r1', 'r2', 'r3'], 'nomi automatici r<n>, anche dentro un AS');
  assert.deepEqual(m.routers.r1.protocols, ['bgp'], 'r1 è di confine: sulla sua LAN ci sono router fuori dall\'AS');
  assert.equal(m.routers.r1.asn, '20');
  assert.deepEqual(m.routers.r2.protocols, ['rip']);
  assert.deepEqual(m.routers.r3.protocols, []);
});

test('router in due AS e LAN in due aree sono errori', () => {
  let r, l;
  const b = costruisci(({disp, lan, link, zona}) => {
    r = disp('router', 50, 50);
    l = lan('10.0.0.0/30', {x: 50, y: 50}); link(r, l);
    zona('as', '1', 0, 0, 100, 100); zona('as', '2', 25, 25, 100, 100);
    zona('ospf', '0', 0, 0, 100, 100); zona('ospf', '1', 0, 0, 100, 100);
  });
  const conv = converti(b);
  assert.ok(haErrore(conv, r, 'due riquadri AS'));
  assert.ok(haErrore(conv, l, 'due aree OSPF'));
});

test('aree OSPF: una sola area, stub, e router di confine con le aree di ogni rete', () => {
  const b = costruisci(({disp, lan, link, zona}) => {
    const r1 = disp('router', 0, 0), r2 = disp('router', 200, 0), r3 = disp('router', 400, 0);
    const a = lan('10.0.0.0/30', {punto: true}); link(r1, a); link(r2, a);     // mezzo (100, 0)
    const c = lan('10.1.0.0/30', {punto: true}); link(r2, c); link(r3, c);     // mezzo (300, 0)
    zona('ospf', '1.1.1.1', 250, -50, 300, 100, true);
    zona('ospf', '0', 50, -50, 100, 100);                                      // '0' = backbone
  });
  const m = converti(b).modello.routers;
  assert.equal(m.r1.ospf_area, '0');
  assert.equal(m.r1.ospf_area_stub, false);
  assert.equal(m.r1.ospf_aree, undefined, 'una sola area: niente aree per rete');
  assert.equal(m.r3.ospf_area, '1.1.1.1');
  assert.equal(m.r3.ospf_area_stub, true);
  assert.equal(m.r2.ospf_area, '0', 'il router di confine ha come area principale la backbone');
  assert.equal(m.r2.ospf_area_stub, false);
  assert.deepEqual(m.r2.ospf_aree, {'10.0.0.0/30': '0', '10.1.0.0/30': '1.1.1.1'});
  assert.deepEqual(m.r2.ospf_aree_stub, ['1.1.1.1']);
  assert.deepEqual(m.r2.igp_networks, ['10.0.0.0/30', '10.1.0.0/30']);
});

test('protocolli in ordine fisso, statiche, ridistribuzione solo se BGP e IGP', () => {
  const b = costruisci(({disp, lan, link, zona}) => {
    const r = disp('router', 10, 10, {router: {redistribuisci_bgp: false, statiche: [{rete: 'default', via: '10.0.0.2'}, {rete: '', via: ''}]}});
    const s = disp('router', 300, 300, {router: {redistribuisci_bgp: false}});
    const l = lan('10.0.0.0/24', {x: 10, y: 10}); link(r, l); link(s, l);
    zona('rip', '', 0, 0, 50, 50); zona('as', '5', 0, 0, 50, 50); zona('as', '6', 250, 250, 100, 100);
  });
  const m = converti(b).modello.routers;
  assert.deepEqual(m.r1.protocols, ['bgp', 'rip', 'statico']);
  assert.deepEqual(m.r1.static_routes, [{network: 'default', via: '10.0.0.2'}]);
  assert.equal(m.r1.igp_redistribute_bgp, false);
  assert.equal(m.r2.igp_redistribute_bgp, undefined, 'solo BGP: niente ridistribuzione nell\'IGP');
});

test('nomi: scritti rispettati, automatici che li saltano, non validi e doppi segnalati', () => {
  let x, y;
  const b = costruisci(({disp}) => {
    disp('router', 0, 0, {nome: 'r1'}); disp('router', 0, 0); x = disp('host', 0, 0, {nome: 'PC-1'});
    y = disp('host', 0, 0, {nome: 'r1'}); disp('dns', 0, 0, {dns: {root_type: 'master'}}); disp('dns', 0, 0); disp('www', 0, 0);
  });
  const conv = converti(b);
  assert.deepEqual(b.dispositivi.map(d => conv.nomi[d.id]), ['r1', 'r2', 'PC-1', 'r1', 'root', 'dns1', 'www1']);
  assert.ok(haErrore(conv, x, 'non è valido per Kathará'));
  assert.ok(haErrore(conv, y, 'già usato'));
});

test('lettere delle LAN: maiuscole, saltano quelle scritte, dopo Z vengono AA, AB', () => {
  const b = costruisci(({lan}) => { lan('', {nome: 'b'}); for (let i = 0; i < 27; i++) lan(''); });
  const conv = converti(b), nomi = b.lan.map(l => conv.nomiLan[l.id]);
  assert.equal(nomi[0], 'B');
  assert.equal(nomi[1], 'A');
  assert.equal(nomi[2], 'C');
  assert.deepEqual(nomi.slice(-2), ['AA', 'AB']);
});

test('server: una sola interfaccia, gateway scritto vince sulla proposta, resolver per id', () => {
  let w, dns, h;
  const b = costruisci(({disp, lan, link}) => {
    const r = disp('router', 0, 0); w = disp('www', 0, 0, {www: {gateway: '10.0.0.254'}});
    dns = disp('dns', 0, 0, {dns: {root_type: 'hint', dnssec_validation: true}}); h = disp('host', 0, 0);
    const l = lan('10.0.0.0/24'), l2 = lan('10.0.1.0/24');
    link(r, l); link(w, l); link(w, l2); link(dns, l);
  });
  b.resolver = dns;
  let conv = converti(b);
  assert.equal(conv.modello.wwws[0].gateway, '10.0.0.254');
  assert.ok(haErrore(conv, w, 'una sola interfaccia'));
  assert.equal(conv.modello.resolver, 'dns1');
  assert.deepEqual(conv.modello.hosts.map(x => x.name), ['host1', 'dns1'], 'prima gli host, poi i DNS');
  assert.equal(conv.modello.hosts[1].gateway, '10.0.0.1');
  assert.equal(conv.modello.hosts[1].dnssec_validation, true);
  assert.ok(conv.problemi.some(p => p.id === h && p.gravita === 'avviso'), 'host senza collegamenti: avviso');
  b.resolver = w;
  conv = converti(b);
  assert.ok(haErrore(conv, w, 'resolver'));
});

test('link diretto con un numero di dispositivi diverso da due', () => {
  let l;
  const b = costruisci(({disp, lan, link}) => { const a = disp('router', 0, 0); l = lan('10.0.0.0/30', {punto: true}); link(a, l); });
  assert.ok(haErrore(converti(b), l, 'collega due dispositivi'));
});

test('rinumera: stessa parte host se ci sta, altrimenti IP automatico', () => {
  let l, c1, c2, c3;
  const b = costruisci(({disp, lan, link}) => {
    const a = disp('router', 0, 0), x = disp('host', 0, 0), y = disp('host', 0, 0);
    l = lan('10.0.0.0/24');
    c1 = link(a, l, '10.0.0.1/24'); c2 = link(x, l, '10.0.0.200/24'); c3 = link(y, l);
  });
  const n = rinumera(b, l, '172.16.0.0/25');
  const ip = id => n.collegamenti.find(c => c.id === id).ip;
  assert.equal(n.lan[0].subnet, '172.16.0.0/25');
  assert.equal(ip(c1), '172.16.0.1/25');
  assert.equal(ip(c2), '', '.200 non sta in una /25: torna automatico');
  assert.equal(ip(c3), '');
  assert.equal(b.lan[0].subnet, '10.0.0.0/24', 'la bozza di partenza non cambia');
  assert.deepEqual(errori(converti(n)), []);
});

test('proponi subnet: serve il blocco, salta le reti occupate, si ferma a blocco pieno', () => {
  const b = costruisci(({disp, lan, link}) => {
    const a = disp('router', 0, 0), x = disp('router', 0, 0), y = disp('router', 0, 0);
    const p1 = lan('', {punto: true}); link(a, p1); link(x, p1);
    const p2 = lan('', {punto: true}); link(x, p2); link(y, p2);
    const g = lan('10.255.0.0/30', {punto: true}); link(a, g); link(y, g);
  });
  assert.match(proponiSubnet(b).messaggio, /blocco/);
  b.blocco_subnet = '10.255.0.0/28';
  const r = proponiSubnet(b);
  assert.equal(r.assegnate, 2);
  assert.deepEqual(r.bozza.lan.map(l => l.subnet), ['10.255.0.4/30', '10.255.0.8/30', '10.255.0.0/30']);
  assert.deepEqual(errori(converti(r.bozza)), []);
  b.blocco_subnet = '10.255.0.0/29';
  assert.match(proponiSubnet(b).messaggio, /non ha più \/30 libere/);
});

test('dal campo di un problema di valida_lab all\'elemento del disegno', () => {
  let r, c2, l;
  const b = costruisci(({disp, lan, link}) => {
    r = disp('router', 0, 0); l = lan('10.0.0.0/24', {nome: 'B'}); const l2 = lan('10.0.1.0/24');
    link(r, l2); c2 = link(r, l);
  });
  const conv = converti(b);
  assert.deepEqual(elementoDelCampo(conv, 'r1.interfaces[1].ip'), {id: r, collegamento: c2});
  assert.deepEqual(elementoDelCampo(conv, 'r1.asn'), {id: r});
  assert.deepEqual(elementoDelCampo(conv, 'lan.B'), {id: l});
  assert.equal(elementoDelCampo(conv, 'lab.resolver'), null);
});

test('router di confine: la backbone è l\'area principale anche se la prima rete sta in un\'altra area', () => {
  const b = costruisci(({disp, lan, link, zona}) => {
    const r = disp('router', 200, 0), x = disp('router', 400, 0), y = disp('router', 0, 0);
    const c = lan('10.1.0.0/30', {punto: true}); link(r, c); link(x, c);     // prima interfaccia: area 2 stub
    const a = lan('10.0.0.0/30', {punto: true}); link(r, a); link(y, a);     // seconda: backbone
    zona('ospf', '2.2.2.2', 250, -50, 200, 100, true);
    zona('ospf', '0.0.0.0', 50, -50, 100, 100);
  });
  const r = converti(b).modello.routers.r1;
  assert.equal(r.ospf_area, '0.0.0.0');
  assert.equal(r.ospf_area_stub, false);
  assert.deepEqual(r.ospf_aree, {'10.1.0.0/30': '2.2.2.2', '10.0.0.0/30': '0.0.0.0'});
  assert.deepEqual(r.ospf_aree_stub, ['2.2.2.2']);
});

test('la backbone segnata come stub non diventa stub', () => {
  const b = costruisci(({disp, lan, link, zona}) => {
    const r = disp('router', 0, 0), x = disp('router', 100, 0), y = disp('router', 300, 0);
    const a = lan('10.0.0.0/30', {punto: true}); link(r, a); link(x, a);     // mezzo (50, 0)
    const c = lan('10.1.0.0/30', {punto: true}); link(x, c); link(y, c);     // mezzo (200, 0)
    zona('ospf', '0', 0, -50, 100, 100, true);
    zona('ospf', '3', 150, -50, 100, 100, true);
  });
  const m = converti(b).modello.routers;
  assert.equal(m.r1.ospf_area_stub, false);
  assert.equal(m.r2.ospf_area_stub, false);
  assert.deepEqual(m.r2.ospf_aree_stub, ['3']);
});

test('zone: valore mancante o sbagliato una volta per zona, zone vuote, membri e router di confine', () => {
  let zAs, zAr, zVuota, zRip, r;
  const b = costruisci(({disp, lan, link, zona}) => {
    r = disp('router', 50, 50); const x = disp('router', 60, 60), y = disp('router', 300, 50);
    const a = lan('10.0.0.0/30', {punto: true}); link(r, a); link(y, a);         // mezzo (175, 50)
    const c = lan('10.1.0.0/24', {x: 50, y: 50}); link(r, c); link(x, c);
    zAs = zona('as', 'cento', 0, 0, 100, 100);
    zAr = zona('ospf', '', 0, 0, 100, 100);
    zona('ospf', '2', 150, 0, 100, 100);
    zRip = zona('rip', '', 0, 0, 100, 100);
    zVuota = zona('as', '7', 1000, 1000, 50, 50);
  });
  const conv = converti(b);
  const di = id => conv.problemi.filter(p => p.id === id);
  assert.equal(di(zAs).length, 1);
  assert.match(di(zAs)[0].messaggio, /Numero AS non valido/);
  assert.equal(di(zAr).length, 1);
  assert.match(di(zAr)[0].messaggio, /Scrivi l'area/);
  assert.equal(di(zVuota)[0].gravita, 'avviso');
  assert.deepEqual(conv.membri[zRip].length, 2);
  assert.equal(conv.zone[r].as, '', 'AS non valido: il router non prende BGP');
  assert.deepEqual(conv.modello.routers.r1.protocols, ['ospf', 'rip'], 'area senza valore: conta solo l\'area 2');
  assert.deepEqual(conv.abr, []);
  b.zone.find(z => z.id === zAr).valore = '0';
  assert.deepEqual(converti(b).abr, [r], 'con l\'area 0 scritta r è router di confine');
});

test('network IGP scritte a mano: normalizzate, solo con OSPF o RIP, mai sui router di confine', () => {
  let r, s2;
  const b = costruisci(({disp, lan, link, zona}) => {
    r = disp('router', 0, 0, {router: {igp_networks: '10.0.0.1/30, 10.0.0.0/30;10.9.0.0/16'}});
    s2 = disp('router', 100, 0, {router: {igp_networks: '10.0.0.0/30, boh'}});
    const a = lan('10.0.0.0/30', {punto: true}); link(r, a); link(s2, a);
    zona('rip', '', -50, -50, 200, 100);
  });
  const conv = converti(b);
  assert.deepEqual(conv.modello.routers.r1.igp_networks, ['10.0.0.0/30', '10.9.0.0/16']);
  assert.ok(conv.problemi.some(p => p.id === s2 && p.messaggio.includes("'boh'")));
  b.zone = [];
  assert.equal(converti(b).modello.routers.r1.igp_networks, undefined, 'senza IGP non servono');
});

test('zone DNS dell\'editor nel formato del wizard', () => {
  assert.equal(zoneDelWizard([]), null);
  assert.equal(zoneDelWizard(undefined), null);
  assert.deepEqual(zoneDelWizard([{nome: 'com.', record: [
    {nome: 'www', tipo: 'A', valore: '10.0.1.80/24', extra: ''},
    {nome: 'web', tipo: 'CNAME', valore: 'www', extra: ''},
    {nome: '@', tipo: 'NS', valore: 'dns.com.', extra: '10.0.2.3'},
    {nome: 'sub', tipo: 'DELEGATION', valore: 'ns.sub.com.', extra: ''},
    {nome: '', tipo: 'A', valore: '1.2.3.4', extra: ''}]}, {nome: '', record: []}]), {com: {
    www: '10.0.1.80', web: {type: 'CNAME', target: 'www'}, '@': {type: 'NS', ns: 'dns.com.', glue: '10.0.2.3'},
    sub: {type: 'DELEGATION', zone: 'sub', ns: 'ns.sub.com.'}}});
});

test('deleghe del DNS solo se è master per ".", come nel wizard', () => {
  const b = costruisci(({disp, lan, link}) => {
    const d = disp('dns', 0, 0, {dns: {root_type: 'hint', delegations: [{zone: 'com', ns: 'dns.com', ip: '1.2.3.4'}], zone: []}});
    link(d, lan('10.0.0.0/24'));
  });
  assert.deepEqual(converti(b).modello.hosts[0].delegations, []);
  b.dispositivi[0].dns.root_type = 'master';
  assert.equal(converti(b).modello.hosts[0].delegations.length, 1);
});

test('sui router di confine le network scritte a mano non contano: le decidono le aree', () => {
  const b = costruisci(({disp, lan, link, zona}) => {
    const r1 = disp('router', 0, 0), r2 = disp('router', 200, 0, {router: {igp_networks: '1.0.0.0/8'}}), r3 = disp('router', 400, 0);
    const a = lan('10.0.0.0/30', {punto: true}); link(r1, a); link(r2, a);
    const c = lan('10.1.0.0/30', {punto: true}); link(r2, c); link(r3, c);
    zona('ospf', '0', 50, -50, 100, 100);
    zona('ospf', '1', 250, -50, 100, 100);
  });
  assert.deepEqual(converti(b).modello.routers.r2.igp_networks, ['10.0.0.0/30', '10.1.0.0/30']);
});

test('BGP: solo ai router di confine, a tutti con "tutti", eccezioni per router; AS solo con BGP', () => {
  // papillon in piccolo: AS 20 con r1 (interno) e r3 (confine), AS 30 con r5 (confine)
  let r1, r3, r5, zAs;
  const b = costruisci(({disp, lan, link, zona}) => {
    r1 = disp('router', 0, 0); r3 = disp('router', 100, 0); r5 = disp('router', 300, 0);
    const a = lan('10.0.0.0/30', {punto: true}); link(r1, a); link(r3, a);
    const f = lan('10.1.0.0/30', {punto: true}); link(r3, f); link(r5, f);
    zAs = zona('as', '20', -50, -50, 200, 100); zona('as', '30', 250, -50, 100, 100);
  });
  let c = converti(b), m = c.modello.routers;
  assert.deepEqual([m.r1.protocols, m.r1.asn], [[], ''], 'r1 interno: niente BGP, niente AS nel modello');
  assert.deepEqual([m.r2.protocols, m.r2.asn], [['bgp'], '20']);
  assert.deepEqual([m.r3.protocols, m.r3.asn], [['bgp'], '30']);
  assert.equal(c.zone[r1].as, '20', 'ma sta nell\'AS 20 (colore, membri)');
  assert.deepEqual([c.bgpConfine[r1], c.bgpConfine[r3]], [false, true]);
  b.zone.find(z => z.id === zAs).bgp = 'tutti';
  assert.deepEqual(converti(b).modello.routers.r1.protocols, ['bgp'], 'con "tutti" anche r1');
  b.dispositivi.find(d => d.id === r1).router = {bgp: 'no'};
  assert.deepEqual(converti(b).modello.routers.r1.protocols, [], 'eccezione: no');
  b.zone.find(z => z.id === zAs).bgp = 'confine';
  b.dispositivi.find(d => d.id === r1).router = {bgp: 'si'};
  assert.deepEqual(converti(b).modello.routers.r1.protocols, ['bgp'], 'eccezione: sì');
  b.zone = b.zone.filter(z => z.id !== zAs);
  c = converti(b);
  assert.ok(c.problemi.some(p => p.id === r1 && /riquadro AS/.test(p.messaggio)), 'BGP senza AS: errore');
  assert.deepEqual(c.modello.routers.r1.protocols, []);
});

test('completaIp: numero finale, ultime due parti, IP intero, maschera, senza subnet', () => {
  assert.equal(completaIp('10', '10.0.0.0/24'), '10.0.0.10/24');
  assert.equal(completaIp('6', '10.0.0.4/30'), '10.0.0.6/30');
  assert.equal(completaIp('1.10', '10.0.0.0/16'), '10.0.1.10/16');
  assert.equal(completaIp('192.168.1.7', '10.0.0.0/24'), '192.168.1.7/24', 'IP intero: resta suo (converti dirà se è fuori subnet)');
  assert.equal(completaIp('10.0.0.9/25', '10.0.0.0/24'), '10.0.0.9/25');
  assert.equal(completaIp('7', ''), '7', 'senza subnet resta com\'è');
  assert.equal(completaIp('boh', '10.0.0.0/24'), 'boh');
});
