// "Parti da un lab esistente" (editor/da_lab.js): bozza dal modello, stesso modello di ritorno.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { converti, zoneDelWizard } from '../../src/gui/static/js/editor/bozza.js';
import { bozzaDaModello, differenzeModello, zoneDellEditor } from '../../src/gui/static/js/editor/da_lab.js';

test('zone DNS: andata e ritorno con il formato del wizard', () => {
  const z = {'it': {'dns.it.': '30.0.0.4', 'roma3.it.': {type: 'DELEGATION', zone: 'roma3.it.', ns: 'dns.roma3.it.', ns_ip: '30.0.0.3'}}};
  assert.deepEqual(zoneDelWizard(zoneDellEditor(z)), z);
});

test('router RIP sul confine con OSPF, AS con BGP, host con resolver suo', () => {
  const m = {resolver: null, wwws: [], routers: {
    r1: {protocols: ['bgp', 'ospf'], asn: '10', interfaces: [{name: 'eth0', lan: 'A', ip: '10.0.0.1/24'}, {name: 'eth1', lan: 'B', ip: '1.0.0.1/30'}],
         ospf_area: '0.0.0.0', ospf_area_stub: false, igp_networks: ['10.0.0.0/24']},
    r2: {protocols: ['rip'], asn: '', interfaces: [{name: 'eth0', lan: 'A', ip: '10.0.0.2/24'}, {name: 'eth1', lan: 'C', ip: '20.0.0.1/24'}], igp_networks: ['20.0.0.0/24']},
    r3: {protocols: ['bgp'], asn: '20', interfaces: [{name: 'eth0', lan: 'B', ip: '1.0.0.2/30'}]},
  }, hosts: [{name: 'pc', interfaces: [{name: 'eth0', lan: 'C', ip: '20.0.0.5/24'}], gateway: '20.0.0.1', nameserver: ['9.9.9.9']}]};
  const pos = {'d:r1': {x: 0, y: 0}, 'd:r2': {x: 200, y: 0}, 'd:r3': {x: -300, y: 0}, 'd:pc': {x: 400, y: 0}, 'l:A': {x: 100, y: 60}, 'l:C': {x: 300, y: 60}};
  const b = bozzaDaModello(m, pos);
  assert.equal(b.dispositivi.find(d => d.nome === 'r2').router.ospf, 'no', 'r2 non fa OSPF anche se la LAN A è nell\'area');
  const c = converti(b);
  assert.deepEqual(differenzeModello(m, c.modello), []);
  assert.deepEqual(c.problemi.filter(p => p.gravita === 'errore'), []);
  assert.deepEqual(c.modello.hosts[0].nameserver, ['9.9.9.9']);
});
