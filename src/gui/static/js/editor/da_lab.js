// Fase 5.7, "Parti da un lab esistente": dal modello di un lab (letto dai file dal server,
// persistence.modello_da_stato) alla bozza dell'editor. La bozza ricava i protocolli dai riquadri
// (AS, zone RIP, aree OSPF) per posizione: qui i riquadri si costruiscono intorno ai loro membri
// e, se un riquadro di gruppo prenderebbe dentro un elemento che non c'entra, si passa a un
// riquadro piccolo per ogni membro. Le righe che il modello non contiene non si perdono: alla
// creazione il server unisce i file (core/unione.py). Solo dati: si prova con Node.
import { converti, VERSIONE } from './bozza.js';

const ip0 = x => String(x || '').split('/')[0];
const rete = ip => {
  const [a, p] = String(ip).split('/'); const n = a.split('.').map(Number), pr = Number(p);
  if (n.length !== 4 || n.some(x => !(x >= 0 && x <= 255)) || !(pr >= 0 && pr <= 32)) return null;
  const v = ((n[0] << 24) | (n[1] << 16) | (n[2] << 8) | n[3]) >>> 0, m = pr === 0 ? 0 : ((0xffffffff << (32 - pr)) >>> 0);
  return {base: (v & m) >>> 0, prefisso: pr, ip: v};
};
const testo = r => `${[24, 16, 8, 0].map(s => (r.base >>> s) & 255).join('.')}/${r.prefisso}`;
const copre = (grande, piccola) => grande && piccola && grande.prefisso <= piccola.prefisso
  && ((piccola.base & (grande.prefisso === 0 ? 0 : ((0xffffffff << (32 - grande.prefisso)) >>> 0))) >>> 0) === grande.base;

// zone DNS del wizard ({zona: {nome: valore | record}}) -> zone dell'editor (inverso di zoneDelWizard)
export function zoneDellEditor(zones) {
  if (!zones) return [];
  return Object.entries(zones).map(([nome, rec]) => ({nome, record: Object.entries(rec || {}).map(([n, v]) => {
    if (typeof v === 'string') return {nome: n, tipo: 'A', valore: v, extra: ''};
    if (v.type === 'NS') return {nome: n, tipo: 'NS', valore: v.ns || '', extra: v.glue || ''};
    if (v.type === 'CNAME') return {nome: n, tipo: 'CNAME', valore: v.target || '', extra: ''};
    if (v.type === 'DELEGATION') return {nome: v.zone || n, tipo: 'DELEGATION', valore: v.ns || '', extra: v.ns_ip || ''};
    return {nome: n, tipo: 'A', valore: String(v.ip || ''), extra: ''};
  })}));
}

const dentro = (z, p) => p.x >= z.x && p.x <= z.x + z.w && p.y >= z.y && p.y <= z.y + z.h;
const intorno = (punti, m) => {
  const xs = punti.map(p => p.x), ys = punti.map(p => p.y);
  const x = Math.min(...xs) - m, y = Math.min(...ys) - m;
  return {x, y, w: Math.max(...xs) + m - x, h: Math.max(...ys) + m - y};
};
// riquadri per gruppi: {valore: [punti dei membri]}; gli altri punti non devono finirci dentro.
// Restituisce [{valore, x, y, w, h}] (uno per gruppo, o uno per membro se non si può).
function riquadri(gruppi, tutti, margine) {
  const out = [];
  for (const [valore, membri] of Object.entries(gruppi)) {
    const estranei = tutti.filter(p => !membri.includes(p));
    let z = null;
    for (const m of [margine, 24, 12]) { const r = intorno(membri, m); if (!estranei.some(p => dentro(r, p))) { z = r; break; } }
    if (z) out.push(Object.assign({valore}, z));
    else for (const p of membri) out.push(Object.assign({valore}, intorno([p], 10)));
  }
  return out;
}

// bozza dal modello. posizioni: {'d:<nome>': {x, y}, 'l:<LAN>': {x, y}} (quelle della Topologia
// o del disegno salvato); opz.reti_proposte: {router: true se le sue network IGP sono quelle
// proposte dal generatore}; opz.origine: dati del lab di partenza da tenere nella bozza.
export function bozzaDaModello(modello, posizioni, opz = {}) {
  const pos = posizioni || {}, proposte = opz.reti_proposte || {};
  const b = {versione: VERSIONE, nome: '', resolver: null, blocco_subnet: '', dispositivi: [], lan: [], collegamenti: [], zone: []};
  const routers = modello.routers || {}, hosts = modello.hosts || [], wwws = modello.wwws || [];
  const voci = [...Object.entries(routers).map(([nome, r]) => ({nome, tipo: 'router', r, its: r.interfaces || []})),
    ...hosts.map(h => ({nome: h.name, tipo: h.dns ? 'dns' : 'host', h, its: h.interfaces || [{name: 'eth0', lan: h.lan, ip: h.ip}]})),
    ...wwws.map(w => ({nome: w.name, tipo: 'www', h: w, its: [{name: 'eth0', lan: w.lan, ip: w.ip}]}))];
  // LAN: membri, subnet dal primo IP
  const lans = new Map();
  for (const v of voci) for (const it of v.its) {
    if (!it.lan) continue;
    if (!lans.has(it.lan)) lans.set(it.lan, {nome: it.lan, membri: [], subnet: ''});
    const l = lans.get(it.lan); l.membri.push(v.nome);
    if (!l.subnet && rete(it.ip)) l.subnet = testo(rete(it.ip));
  }
  // posizioni mancanti: su una griglia sotto il resto
  let k = 0;
  const maxY = Math.max(0, ...Object.values(pos).map(p => p.y));
  const posDi = id => pos[id] || (pos[id] = {x: (k % 8) * 120, y: maxY + 160 + Math.floor(k++ / 8) * 120});
  const id = {};
  voci.forEach((v, i) => { id[v.nome] = 'd' + (i + 1); });
  for (const v of voci) {
    const p = posDi('d:' + v.nome), d = {id: id[v.nome], tipo: v.tipo, nome: v.nome, x: Math.round(p.x), y: Math.round(p.y)};
    if (v.tipo === 'router') {
      const r = v.r;
      d.router = {
        bgp: (r.protocols || []).includes('bgp') ? 'si' : 'no',
        redistribuisci_bgp: r.igp_redistribute_bgp !== false,
        statiche: (r.static_routes || []).map(s => Object.assign({rete: s.network, via: s.via}, s.dev ? {dev: s.dev} : {})),
        igp_networks: proposte[v.nome] ? '' : (r.igp_networks || []).join(', '),
      };
      if (!(r.protocols || []).includes('ospf')) d.router.ospf = 'no';     // anche se una sua LAN è in un'area
    } else {
      const h = v.h, conf = {gateway: h.gateway || ''};
      if (h.nameserver && h.nameserver.length) conf.nameserver = h.nameserver.join(', ');
      if (v.tipo === 'dns') Object.assign(conf, {root_type: h.root_type ?? null, delegations: h.delegations || [], allow_recursion: h.allow_recursion ?? null,
        dnssec_validation: !!h.dnssec_validation, forwarders: h.forwarders ?? null, zone: zoneDellEditor(h.zones)});
      d[v.tipo] = conf;
    }
    b.dispositivi.push(d);
  }
  let il = 0;
  for (const l of lans.values()) {
    const punto = l.membri.length === 2 && l.membri[0] !== l.membri[1];
    const p = punto ? null : posDi('l:' + l.nome);
    b.lan.push(Object.assign({id: 'l' + (++il), nome: l.nome, subnet: l.subnet, punto}, p ? {x: Math.round(p.x), y: Math.round(p.y)} : {}));
  }
  const idLan = Object.fromEntries(b.lan.map(l => [l.nome, l.id]));
  let ic = 0;
  for (const v of voci) for (const it of v.its) if (it.lan)
    b.collegamenti.push({id: 'c' + (++ic), dispositivo: id[v.nome], lan: idLan[it.lan], ip: it.ip || ''});
  const nodo = n => b.dispositivi.find(d => d.nome === n);
  const puntoLan = l => {
    if (!l.punto) return {x: l.x, y: l.y};
    const [a, c] = lans.get(l.nome).membri.map(nodo);
    return {x: (a.x + c.x) / 2, y: (a.y + c.y) / 2};
  };

  // riquadri AS (router con BGP), zone RIP, aree OSPF (LAN coperte dalle network OSPF)
  const puntiRouter = b.dispositivi.filter(d => d.tipo === 'router').map(d => ({x: d.x, y: d.y, nome: d.nome}));
  const perAs = {}, perRip = {};
  // nel riquadro AS anche i router interni dello stesso AS (opz.gruppi, come li raggruppa la
  // Topologia): restano senza BGP ('bgp: no'), il riquadro è solo più leggibile
  const gruppi = opz.gruppi || {};
  for (const [n, r] of Object.entries(routers)) {
    const p = puntiRouter.find(x => x.nome === n);
    if ((r.protocols || []).includes('bgp') && r.asn) (perAs[r.asn] = perAs[r.asn] || []).push(p);
    else if (gruppi[n] && Object.values(routers).some(x => String(x.asn) === String(gruppi[n]) && (x.protocols || []).includes('bgp')))
      (perAs[gruppi[n]] = perAs[gruppi[n]] || []).push(p);
    if ((r.protocols || []).includes('rip')) (perRip.rip = perRip.rip || []).push(p);
  }
  const area = {}, stub = {};
  for (const [, r] of Object.entries(routers)) {
    if (!(r.protocols || []).includes('ospf')) continue;
    const reti = (r.igp_networks || []).map(rete).filter(Boolean);
    for (const it of r.interfaces || []) {
      const s = rete(it.ip); if (!s || !it.lan) continue;
      const a = r.ospf_aree ? r.ospf_aree[testo(s)] : (reti.some(n => copre(n, s)) ? r.ospf_area : null);
      if (a == null) continue;
      if (area[it.lan] == null) area[it.lan] = a;
      const stubR = r.ospf_aree ? (r.ospf_aree_stub || []).includes(a) : (r.ospf_area_stub && r.ospf_area === a);
      if (stubR) stub[a] = true;
    }
  }
  const puntiLan = b.lan.map(l => Object.assign(puntoLan(l), {nome: l.nome}));
  const perArea = {};
  for (const [lan, a] of Object.entries(area)) (perArea[a] = perArea[a] || []).push(puntiLan.find(p => p.nome === lan));
  let iz = 0;
  const zona = (tipo, z, extra = {}) => b.zone.push(Object.assign({id: 'z' + (++iz), tipo, valore: tipo === 'rip' ? '' : z.valore,
    x: Math.round(z.x), y: Math.round(z.y), w: Math.round(z.w), h: Math.round(z.h)}, extra));
  for (const z of riquadri(perAs, puntiRouter, 60)) zona('as', z, {bgp: 'confine'});
  for (const z of riquadri(perRip, puntiRouter, 40)) zona('rip', z);
  for (const z of riquadri(perArea, puntiLan, 40)) zona('ospf', z, {stub: !!stub[z.valore]});

  const res = modello.resolver && b.dispositivi.find(d => d.nome === modello.resolver && d.tipo === 'dns');
  b.resolver = res ? res.id : null;
  if (opz.origine) b.origine = opz.origine;
  return b;
}

// Confronto fra il modello del lab e quello che la bozza dà (converti): le differenze sono le cose
// che l'editor non sa rappresentare così come sono (i file non le perdono: alla creazione il server
// unisce i file del lab di partenza). Testi per l'utente.
export function differenzeModello(atteso, ottenuto) {
  const out = [];
  const R1 = atteso.routers || {}, R2 = ottenuto.routers || {};
  for (const [n, r] of Object.entries(R1)) {
    const s = R2[n];
    if (!s) { out.push(`${n}: router mancante nella bozza.`); continue; }
    const p1 = [...(r.protocols || [])].sort().join(','), p2 = [...(s.protocols || [])].sort().join(',');
    if (p1 !== p2) out.push(`${n}: protocolli ${p1 || '-'} nel lab, ${p2 || '-'} nella bozza.`);
    if ((r.protocols || []).includes('bgp') && String(r.asn) !== String(s.asn)) out.push(`${n}: AS ${r.asn} nel lab, ${s.asn || '-'} nella bozza.`);
    const i1 = (r.interfaces || []).map(i => `${i.name} ${i.lan} ${i.ip}`).join('; '), i2 = (s.interfaces || []).map(i => `${i.name} ${i.lan} ${i.ip}`).join('; ');
    if (i1 !== i2) out.push(`${n}: interfacce diverse (lab: ${i1}; bozza: ${i2}).`);
    if ((r.protocols || []).includes('ospf') && !r.ospf_aree && s.ospf_area !== undefined && String(r.ospf_area) !== String(s.ospf_area))
      out.push(`${n}: area OSPF ${r.ospf_area} nel lab, ${s.ospf_area} nella bozza.`);
  }
  for (const n of Object.keys(R2)) if (!R1[n]) out.push(`${n}: router in più nella bozza.`);
  const altri = m => Object.fromEntries([...(m.hosts || []), ...(m.wwws || [])].map(h => [h.name, h]));
  const H1 = altri(atteso), H2 = altri(ottenuto);
  for (const [n, h] of Object.entries(H1)) {
    const g = H2[n];
    if (!g) { out.push(`${n}: dispositivo mancante nella bozza.`); continue; }
    if ((h.gateway || '') !== (g.gateway || '')) out.push(`${n}: gateway ${h.gateway || '-'} nel lab, ${g.gateway || '-'} nella bozza.`);
    if ((h.nameserver || []).join(',') !== (g.nameserver || []).join(',')) out.push(`${n}: resolver diverso.`);
  }
  if ((atteso.resolver || null) !== (ottenuto.resolver || null)) out.push(`Resolver del lab: ${atteso.resolver || '-'} nel lab, ${ottenuto.resolver || '-'} nella bozza.`);
  return out;
}

// carica: bozza + modello iniziale (quello che la bozza dà appena caricata, base dell'unione) e differenze
export function caricaLab(dati, posizioni) {
  const gruppi = Object.fromEntries(((dati.lab || {}).dispositivi || []).filter(d => d.tipo === 'router' && d.gruppo).map(d => [d.nome, String(d.gruppo)]));
  const b = bozzaDaModello(dati.modello, posizioni, {reti_proposte: dati.reti_proposte, gruppi});
  const c = converti(b);
  b.origine = {percorso: dati.percorso, nome: dati.nome, modello: c.modello,
    nomi: Object.fromEntries(b.dispositivi.map(d => [d.id, d.nome]))};
  return {bozza: b, differenze: differenzeModello(dati.modello, c.modello), problemi: c.problemi};
}
