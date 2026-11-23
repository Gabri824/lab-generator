// Topologia: grafo del lab, disposizione automatica, disegno SVG, trascinamento e zoom.
import { $, esc, mem, S } from './comune.js';
import { lato } from './dispositivo.js';
import { creaLivelli } from './componenti/livelli.js';
import { inviluppo, varianti } from './disposizione.js';
import { etichettaCosto, etichettaIface, largCosto, largh, largIface, largLan, testoCosto } from './etichette.js';
import { alberoDns, avvisiSulDisegno, LIVELLI, relazioniCpp, resolver, segniRouter, sessioniBgp, siglePolicy } from './livelli.js';

// ---------- topologia ----------
export function evidLink(l) {
  const e = S.evid; if (!e || !e.lan.has(l.lan)) return false;
  return e.dev.has(l.a.slice(2)) && (l.b.startsWith('l:') || e.dev.has(l.b.slice(2)));
}
export const STILE_SVG = `<style>
.lk{stroke:#94a3b8;stroke-width:2}.lk.ev{stroke:#f59e0b;stroke-width:6}.lk.manca{stroke:#dc2626;stroke-width:6;opacity:.45}
.lk.off{stroke:#dc2626;stroke-width:3;stroke-dasharray:9 6;opacity:1}
.t{font:600 12.5px system-ui,sans-serif;fill:#0f172a;paint-order:stroke;stroke:#fff;stroke-width:4px;stroke-linejoin:round}
.ts{font:10.5px system-ui,sans-serif;fill:#475569;paint-order:stroke;stroke:#fff;stroke-width:3px;stroke-linejoin:round}
.pill{fill:#fff;stroke:#94a3b8;stroke-width:1}.pt{font:600 11px system-ui,sans-serif;fill:#334155}
.nt{font:700 11px system-ui,sans-serif;fill:#fff}.lt{font:11px system-ui,sans-serif;fill:#334155}.lb{font-weight:700;fill:#0f172a}
.ga{font:700 16px system-ui,sans-serif;paint-order:stroke;stroke:#fff;stroke-width:5px;stroke-linejoin:round}.gp{font:600 12px system-ui,sans-serif}.nodo{cursor:pointer}
.sel{stroke:#0f172a;stroke-width:2.5;fill:none;stroke-dasharray:4 3}
.ring{stroke:#f59e0b;stroke-width:5;fill:none}.ord{font:700 11px system-ui,sans-serif;fill:#fff}
.cs{fill:#fef3c7;stroke:#d97706;stroke-width:1}.ct{font:700 11px system-ui,sans-serif;fill:#92400e}
.lk.bgp{stroke:#334155;stroke-width:3.5}.ses{fill:none;stroke-width:2.2;stroke-dasharray:7 5;opacity:.85}.ses.ko{stroke:#dc2626;stroke-width:3.2;stroke-dasharray:1.5 5;stroke-linecap:round;opacity:1}
.polr{fill:#ecfeff;stroke:#0891b2;stroke-width:1}.polt{font:600 10.5px system-ui,sans-serif;fill:#155e75}.cpp{fill:#0f172a}
.bdg{stroke-width:1}.bt{font:700 9.5px system-ui,sans-serif;text-anchor:middle}.b00{fill:#fde68a;stroke:#b45309}.b00t{fill:#78350f}
.bR{fill:#ede9fe;stroke:#7c3aed}.bRt{fill:#5b21b6}.bA{fill:#dc2626;stroke:#fff}.bAt{fill:#fff}
.dnsl{fill:none;stroke:#7c3aed;stroke-width:1.8;stroke-dasharray:3 4}.dnst{font:600 10.5px system-ui,sans-serif;fill:#6d28d9;paint-order:stroke;stroke:#fff;stroke-width:3px;stroke-linejoin:round}
.mod [data-mod]{cursor:pointer}.mod [data-mod="pol"]:hover .polr{stroke:#2563eb;stroke-width:2}.mod [data-mod]:hover .pill,.mod [data-mod]:hover .pill-lan{stroke:#2563eb;stroke-width:2}.mod .nodo[data-id^="l:"]:hover rect{stroke:#2563eb}.mod text[data-mod]:hover{text-decoration:underline}
</style>`;
// protocolli interni di un AS (dai demoni FRR dei suoi router)
export function igpGruppo(G, g) {
  const p = new Set();
  for (const n of G.nodes) if (n.gruppo === g && n.dev) {
    if (n.dev.demoni.includes('ospfd')) p.add('OSPF');
    if (n.dev.demoni.includes('ripd')) p.add('RIP');
  }
  return [...p].sort().join(' + ');
}
// nome del dispositivo dal lato più libero dai collegamenti (di preferenza sotto)
export function latoNome(G, pos, n) {
  const p = pos[n.id], ang = [];
  for (const l of G.links) {
    const o = l.a === n.id ? l.b : (l.b === n.id ? l.a : null);
    if (o) ang.push(Math.atan2(pos[o].y - p.y, pos[o].x - p.x));
  }
  let meglio = Math.PI / 2, punti = -1;
  for (const k of [2, 6, 0, 4, 1, 3, 5, 7]) {          // sotto, sopra, destra, sinistra, diagonali
    const a = k * Math.PI / 4;
    const dist = ang.length ? Math.min(...ang.map(b => { const d = Math.abs(a - b) % (2 * Math.PI); return Math.min(d, 2 * Math.PI - d); })) : Math.PI;
    if (dist > punti + 0.35) { punti = dist; meglio = a; }
  }
  return meglio;
}
export const RAGGIO = {router: 22, host: 19, www: 19, dns: 19};
// Posizione delle etichette senza sovrapposizioni. Ogni etichetta scivola lungo il
// proprio link (s = distanza dal primo nodo) e, se non basta, si scosta di poco di lato
// (o); nodi, nomi dei dispositivi e subnet delle LAN sono ostacoli fissi.
// opz (Topologia, fase 5.6): costi = etichette di solo costo se iface è spento; segni = sigle e
// frecce sui link [{da, verso, w, h, ...}]; sotto = {id del nodo: righe sotto il nome}
export function posizionaEtichette(G, pos, iface, extra, opz = {}) {
  const et = [], ost = extra.slice(), byId = {};
  G.nodes.forEach(n => byId[n.id] = n);
  const nomi = {};
  for (const n of G.nodes) {
    const p = pos[n.id];
    if (n.tipo === 'lan') {
      ost.push({x: p.x, y: p.y, w: Math.max(34, 9 * n.nome.length + 16), h: 24});
      if (n.subnet) ost.push({x: p.x, y: p.y + 23, w: largh(n.subnet, 10.5) + 4, h: 13});
      continue;
    }
    const r = RAGGIO[n.tipo] || 20;
    ost.push({x: p.x, y: p.y, w: 2 * r, h: 2 * r});
    const a = latoNome(G, pos, n), cx = Math.cos(a), cy = Math.sin(a);
    const sotto = (opz.sotto && opz.sotto[n.id]) || [];
    const w = Math.max(largh(n.nome, 12.5), ...sotto.map(t => largh(t, 10.5))) + 4;
    const anc = cx > 0.5 ? 'start' : (cx < -0.5 ? 'end' : 'middle');
    const tx = p.x + cx * 30, ty = p.y + cy * 32 - (cy < -0.5 ? 13 * sotto.length : 0);
    nomi[n.id] = {anc, x: tx, y: ty + 4.5};
    ost.push({x: tx + (anc === 'start' ? w / 2 : anc === 'end' ? -w / 2 : 0), y: ty + 6.5 * sotto.length, w, h: 17 + 13 * sotto.length});
  }
  const raggio = id => byId[id].tipo === 'lan' ? Math.max(17, (9 * byId[id].nome.length + 16) / 2) : (RAGGIO[byId[id].tipo] || 20);
  for (const l of G.links) {
    const A = pos[l.a], B = pos[l.b], dx = B.x - A.x, dy = B.y - A.y, len = Math.sqrt(dx * dx + dy * dy) || 1;
    const ux = dx / len, uy = dy / len;
    const est = (w, h) => w / 2 * Math.abs(ux) + h / 2 * Math.abs(uy);     // ingombro lungo il link
    const base = {ax: A.x, ay: A.y, ux, uy, len, o: 0, h: 18};
    if (!l.b.startsWith('l:')) {
      const w = largLan(l);
      et.push(Object.assign({}, base, {tipo: 'lan', l, w, s: len / 2, sMin: len * 0.3, sMax: len * 0.7}));
    }
    if (!iface && !opz.costi) continue;
    const vede = it => it && (iface || testoCosto(it)), larg = it => (iface ? largIface(it) : largCosto(it));
    if (vede(l.ia)) {
      const w = larg(l.ia), sMin = raggio(l.a) + est(w, 18) + 3;
      et.push(Object.assign({}, base, {tipo: 'if', it: l.ia, nodo: l.a, w, s: Math.max(sMin, Math.min(52, len * 0.28)), sMin, sMax: Math.max(sMin, len / 2 - 8)}));
    }
    if (vede(l.ib)) {
      const w = larg(l.ib), sMax = len - raggio(l.b) - est(w, 18) - 3;
      et.push(Object.assign({}, base, {tipo: 'if', it: l.ib, nodo: l.b, w, s: Math.min(sMax, len - Math.min(52, len * 0.28)), sMin: Math.min(sMax, len / 2 + 8), sMax}));
    }
  }
  for (const g of opz.segni || []) {
    const A = pos[g.da], B = pos[g.verso]; if (!A || !B) continue;
    const dx = B.x - A.x, dy = B.y - A.y, len = Math.sqrt(dx * dx + dy * dy) || 1, ux = dx / len, uy = dy / len;
    const ing = g.w / 2 * Math.abs(ux) + g.h / 2 * Math.abs(uy), sMin = raggio(g.da) + ing + 2;
    const sMax = Math.max(sMin, g.meta ? len * 0.75 : len / 2 - 4);
    const s0 = g.meta ? len / 2 : sMin + (iface ? 58 : 10);
    et.push({tipo: 'seg', g, ax: A.x, ay: A.y, ux, uy, len, o: 0, w: g.w, h: g.h, s: Math.max(sMin, Math.min(sMax, s0)), sMin: g.meta ? len * 0.25 : sMin, sMax});
  }
  const centro = e => { e.x = e.ax + e.ux * e.s - e.uy * e.o; e.y = e.ay + e.uy * e.s + e.ux * e.o; };
  // sposta e di (Dx, Dy): prima lungo il link, poi (se è al limite o il link è di traverso) di lato
  const sposta = (e, Dx, Dy) => {
    const d = Math.hypot(Dx, Dy) || 1, lungo = (e.ux * Dx + e.uy * Dy) / d, lato = (-e.uy * Dx + e.ux * Dy) / d;
    if (Math.abs(lungo) > 0.25) {
      const s = Math.max(e.sMin, Math.min(e.sMax, e.s + Math.max(-14, Math.min(14, d / lungo))));
      const fatto = Math.abs(s - e.s) > 0.01; e.s = s;
      if (fatto) return;
    }
    if (Math.abs(lato) > 0.1) e.o = Math.max(-16, Math.min(16, e.o + Math.max(-8, Math.min(8, d / lato))));
  };
  const urto = (a, b, pad) => {
    const ox = (a.w + b.w) / 2 + pad - Math.abs(a.x - b.x), oy = (a.h + b.h) / 2 + pad - Math.abs(a.y - b.y);
    if (ox <= 0 || oy <= 0) return null;
    return ox < oy ? [(a.x >= b.x ? 1 : -1) * ox, 0] : [0, (a.y >= b.y ? 1 : -1) * oy];
  };
  for (let it = 0; it < 120; it++) {
    et.forEach(centro);
    let urti = 0;
    for (let i = 0; i < et.length; i++) {
      for (let j = i + 1; j < et.length; j++) {
        const D = urto(et[i], et[j], 3); if (!D) continue;
        urti++; sposta(et[i], D[0] / 2, D[1] / 2); sposta(et[j], -D[0] / 2, -D[1] / 2); centro(et[i]); centro(et[j]);
      }
      for (const o of ost) { const D = urto(et[i], o, 3); if (D) { urti++; sposta(et[i], D[0], D[1]); centro(et[i]); } }
    }
    if (!urti) break;
  }
  et.forEach(centro);
  return {et, nomi};
}
// livello acceso (senza la barra dei livelli, es. nei test, tutti accesi)
export const livello = id => !S.livelli || S.livelli.has(id);
const titolo = t => `<title>${esc(t)}</title>`;
const curva = (a, b, piega) => {
  const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2, dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
  const k = Math.min(60, len * 0.22) * piega, cx = mx - dy / len * k, cy = my + dx / len * k;
  return {d: `M${a.x},${a.y} Q${cx},${cy} ${b.x},${b.y}`, x: (a.x + 2 * cx + b.x) / 4, y: (a.y + 2 * cy + b.y) / 4};
};
// link del disegno che porta dal router alla LAN di un neighbor: id dell'altro capo (LAN o router)
function versoLan(G, router, lan) {
  const id = 'd:' + router;
  for (const l of G.links) {
    if (l.a === id && l.ia && l.ia.lan === lan) return l.b;
    if (l.b === id && l.ib && l.ib.lan === lan) return l.a;
  }
  return null;
}
// segni dei livelli Policy (sigle sui link, frecce Customer-Provider-Peer) per posizionaEtichette
function segniLink(G, pos, lab) {
  const out = [];
  if (!lab || !livello('policy')) return out;
  for (const x of siglePolicy(lab)) {
    const verso = (x.lan && versoLan(G, x.router, x.lan)) || (x.peer && pos['d:' + x.peer] ? 'd:' + x.peer : null);
    if (verso) out.push({tipo: 'pol', da: 'd:' + x.router, verso, w: largh(x.testo, 10.5) + 12, h: 16, x});
  }
  for (const r of relazioniCpp(lab)) {
    if (r.provider) {
      const verso = versoLan(G, r.provider, r.lan); if (!verso) continue;
      out.push({tipo: 'cpp', da: 'd:' + r.provider, verso, w: 16, h: 16, titolo: `${r.customer} è cliente di ${r.provider} (Customer-Provider-Peer): la freccia punta al provider`});
    } else {
      const verso = versoLan(G, r.peer[0], r.lan); if (!verso) continue;
      out.push({tipo: 'peer', da: 'd:' + r.peer[0], verso, w: largh('peer', 10.5) + 12, h: 16, meta: true, titolo: `${r.peer[0]} e ${r.peer[1]} sono peer (Customer-Provider-Peer)`});
    }
  }
  return out;
}
function htmlSegno(e) {
  const g = e.g;
  if (g.tipo === 'pol') return `<g class="pol" data-mod="pol" data-dev="${esc(g.x.router)}" data-ip="${esc(g.x.ip)}">${titolo(g.x.titolo)}<rect class="polr" x="${e.x - e.w / 2}" y="${e.y - 8}" width="${e.w}" height="16" rx="8"/><text class="polt" x="${e.x}" y="${e.y + 3.8}" text-anchor="middle">${esc(g.x.testo)}</text></g>`;
  if (g.tipo === 'peer') return `<g>${titolo(g.titolo)}<rect class="polr" x="${e.x - e.w / 2}" y="${e.y - 8}" width="${e.w}" height="16" rx="8"/><text class="polt" x="${e.x}" y="${e.y + 3.8}" text-anchor="middle">peer</text></g>`;
  // freccia verso il provider (l'inizio del segmento, e.ax/e.ay)
  const px = -e.ux, py = -e.uy, x = e.x, y = e.y;
  const p = [[x + px * 8, y + py * 8], [x - px * 6 - py * 7, y - py * 6 + px * 7], [x - px * 6 + py * 7, y - py * 6 - px * 7]];
  return `<g>${titolo(g.titolo)}<path class="cpp" d="M${p.map(q => q[0].toFixed(1) + ',' + q[1].toFixed(1)).join(' L')} Z"/></g>`;
}
// piccolo cerchio con una scritta accanto al nodo (0/0, R, !)
const distintivo = (cx, cy, testo, cls, tit) => `<g>${titolo(tit)}<circle class="bdg ${cls}" cx="${cx}" cy="${cy}" r="${testo.length > 1 ? 11 : 8.5}"/><text class="bt ${cls}t" x="${cx}" y="${cy + 3.4}">${esc(testo)}</text></g>`;

export function svgContenuto(G, pos) {
  let h = STILE_SVG, etichetteAS = '';
  const lab = S.lab && G === S.G ? S.lab : null;      // l'editor usa solo posizionaEtichette
  const disp = lab ? Object.fromEntries(lab.dispositivi.map(d => [d.nome, d])) : {};
  const avvisi = lab && livello('avvisi') ? avvisiSulDisegno(lab) : {dev: {}, as: {}};
  const ostAS = [];      // scritte degli AS: ostacoli per le etichette
  const gruppi = [...new Set(G.nodes.map(n => n.gruppo).filter(g => g && g !== '_'))];
  for (const g of gruppi) {
    const pts = inviluppo(G.nodes.filter(n => n.gruppo === g).map(n => pos[n.id]));
    const c = S.colori[g] || '#64748b', igp = igpGruppo(G, g);
    const d = 'M' + pts.map(p => p.x.toFixed(1) + ',' + p.y.toFixed(1)).join(' L') + ' Z';
    h += `<path d="${d}" fill="${c}" stroke="${c}" stroke-width="110" stroke-linejoin="round" stroke-linecap="round" opacity="0.10"/>`;
    const top = pts.reduce((a, b) => b.y < a.y ? b : a);
    ostAS.push({x: top.x, y: top.y - 69, w: largh('AS' + g, 16) + (igp ? largh('· ' + igp, 12) + 6 : 0) + 6, h: 22});
    const wAS = ostAS[ostAS.length - 1].w;   // area di clic della scritta (modalità Modifica), anche tra le parole
    etichetteAS += `<rect data-mod="as" data-as="${esc(g)}" x="${top.x - wAS / 2}" y="${top.y - 80}" width="${wAS}" height="22" fill="transparent"/>`;
    etichetteAS += `<text class="ga" x="${top.x}" y="${top.y - 64}" text-anchor="middle" fill="${c}" data-mod="as" data-as="${esc(g)}">AS${esc(g)}${igp ? `<tspan class="gp" dx="6">· ${esc(igp)}</tspan>` : ''}</text>`;
    if (avvisi.as[g]) etichetteAS += distintivo(top.x + wAS / 2 + 10, top.y - 69, '!', 'bA', avvisi.as[g].join('\n\n'));
  }
  // livello Sessioni BGP: link eBGP marcati; iBGP e sessioni sbagliate come curve tratteggiate
  const ebgp = new Set(), curve = [];
  if (lab && livello('sessioni')) for (const x of sessioniBgp(lab)) {
    const A = pos['d:' + x.a], B = pos['d:' + x.b]; if (!A || !B) continue;
    if (x.tipo === 'eBGP' && x.stato === 'ok') {
      for (const r of [x.a, x.b]) { const v = x.lan && versoLan(G, r, x.lan); if (v) ebgp.add(['d:' + r, v].sort().join('|')); }
      if (x.lan) continue;                // eBGP fra loopback: anche la curva
    }
    const c = curva(A, B, 1), col = x.stato === 'ko' ? '' : ` stroke="${S.colori[(disp[x.a] || {}).gruppo] || '#475569'}"`;
    const tit = x.stato === 'ko' ? 'Sessione BGP da controllare: ' + x.perche : `${x.tipo} ${x.a} - ${x.b}`;
    curve.push(`<path class="ses${x.stato === 'ko' ? ' ko' : ''}" d="${c.d}"${col}>${titolo(tit)}</path>`
      + (x.stato === 'ko' ? distintivo(c.x, c.y, '!', 'bA', tit) : ''));
  }
  for (const l of G.links) { const a = pos[l.a], b = pos[l.b];
    const cls = S.spenti && S.spenti.has(l.lan) ? ' off' : evidLink(l) ? ' ev' : (S.evid && S.evid.manca && S.evid.manca.has(l.lan)) ? ' manca'
      : ebgp.has([l.a, l.b].sort().join('|')) ? ' bgp' : '';
    h += `<line class="lk${cls}" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>`; }
  h += curve.join('');
  // livello DNS: deleghe dal server padre al figlio, con il nome della zona
  if (lab && livello('dns')) for (const x of alberoDns(lab)) {
    const A = pos['d:' + x.da], B = x.a && pos['d:' + x.a]; if (!A || !B) continue;
    const c = curva(A, B, -1);
    h += `<path class="dnsl" d="${c.d}">${titolo(`Delega: ${x.da} delega la zona ${x.zona} a ${x.ns} (${x.ip || '?'}, ${x.a})`)}</path><text class="dnst" x="${c.x}" y="${c.y}" text-anchor="middle">${esc(x.zona)}</text>`;
  }
  // righe sotto il nome: loopback (Segni sui router) e resolver (DNS)
  const sotto = {};
  if (lab) for (const n of G.nodes) { const d = disp[n.nome]; if (!d || n.tipo === 'lan') continue;
    const r = [];
    if (livello('segni') && d.tipo === 'router') r.push(...segniRouter(d).loopback.map(ip => 'lo ' + ip));
    if (livello('dns') && resolver(lab, d)) r.push(resolver(lab, d));
    if (r.length) sotto[n.id] = r;
  }
  const iface = !!S.modifica || livello('indirizzi');
  const {et, nomi} = posizionaEtichette(G, pos, iface, ostAS, {costi: livello('costi'), segni: segniLink(G, pos, lab), sotto});
  const ord = (S.evid && S.evid.ordine) || {};
  for (const n of G.nodes) { const p = pos[n.id];
    h += `<g class="nodo" data-id="${esc(n.id)}" transform="translate(${p.x},${p.y})">`;
    if (n.tipo === 'lan') {
      const w = Math.max(34, 9 * n.nome.length + 16);
      h += `<rect x="${-w / 2}" y="-12" width="${w}" height="24" rx="12" fill="#f8fafc" stroke="#64748b" stroke-width="1.5"/><text class="t" y="4" text-anchor="middle">${esc(n.nome)}</text>`;
      if (n.subnet) h += `<text class="ts" y="27" text-anchor="middle">${esc(n.subnet)}</text>`;
    } else {
      const c = n.tipo === 'router' ? (S.colori[n.gruppo] || '#64748b') : {host: '#475569', www: '#0d9488', dns: '#7c3aed'}[n.tipo];
      if (S.evid && S.evid.dev.has(n.nome)) h += n.tipo === 'router' ? '<circle class="ring" r="27"/>' : '<rect class="ring" x="-24" y="-20" width="48" height="40" rx="8"/>';
      if (n.nome === S.sel) h += n.tipo === 'router' ? '<circle class="sel" r="32"/>' : '<rect class="sel" x="-29" y="-25" width="58" height="50" rx="10"/>';
      if (n.tipo === 'router') {
        h += `<circle r="20" fill="${c}" stroke="#fff" stroke-width="2"/><path d="M-10,-4 H9 M5,-8 L9,-4 L5,0 M10,4 H-9 M-5,0 L-9,4 L-5,8" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`;
      } else {
        const scritta = {host: '', www: 'www', dns: 'DNS'}[n.tipo];
        h += `<rect x="-17" y="-13" width="34" height="26" rx="4" fill="${c}" stroke="#fff" stroke-width="2"/>`;
        h += scritta ? `<text y="4" text-anchor="middle" style="font:700 10px system-ui,sans-serif;fill:#fff">${scritta}</text>` : '<rect x="-10" y="-7" width="20" height="12" rx="1.5" fill="none" stroke="#fff" stroke-width="1.6"/>';
      }
      const t = nomi[n.id];
      h += `<text class="t" x="${(t.x - p.x).toFixed(1)}" y="${(t.y - p.y).toFixed(1)}" text-anchor="${t.anc}">${esc(n.nome)}</text>`;
      (sotto[n.id] || []).forEach((r, k) => { h += `<text class="ts" x="${(t.x - p.x).toFixed(1)}" y="${(t.y - p.y + 13 * (k + 1)).toFixed(1)}" text-anchor="${t.anc}">${esc(r)}</text>`; });
      if (ord[n.nome] != null) h += `<circle cx="20" cy="-20" r="10" fill="#f59e0b"/><text class="ord" x="20" y="-16" text-anchor="middle">${esc(ord[n.nome])}</text>`;
      const d = disp[n.nome];
      if (d && livello('segni') && d.tipo === 'router') {
        const sg = segniRouter(d);
        if (sg.default.length) h += distintivo(-21, -19, '0/0', 'b00', 'Manda la default route: ' + sg.default.join('; '));
        if (sg.redistribuisce.length) h += distintivo(20, 19, 'R', 'bR', 'Ridistribuisce BGP in ' + sg.redistribuisce.join(' e ') + ' (redistribute bgp)');
      }
      if (avvisi.dev[n.nome]) h += distintivo(-20, 19, '!', 'bA', avvisi.dev[n.nome].join('\n\n'));
    }
    h += '</g>';
  }
  // etichette sopra a tutto: link punto-punto (nome e subnet), interfacce, sigle delle policy
  const col = id => { const n = G.nodes.find(x => x.id === id); return (n && S.colori[n.gruppo]) || '#475569'; };
  for (const e of et) {
    if (e.tipo === 'lan') h += `<g data-mod="lan" data-lan="${esc(e.l.lan)}"><rect class="pill-lan" x="${e.x - e.w / 2}" y="${e.y - 9}" width="${e.w}" height="18" rx="9" fill="#f8fafc" stroke="#cbd5e1"/>`
      + `<text class="lt" x="${e.x}" y="${e.y + 4}" text-anchor="middle"><tspan class="lb">${esc(e.l.lan)}</tspan> ${esc(e.l.subnet || '')}</text></g>`;
    else if (e.tipo === 'seg') h += htmlSegno(e);
    else h += `<g data-mod="if" data-dev="${esc(e.nodo.slice(2))}" data-iface="${esc(e.it.dev)}">${iface ? etichettaIface(e.it, e.x, e.y, col(e.nodo)) : etichettaCosto(e.it, e.x, e.y)}</g>`;
  }
  return h + etichetteAS;
}
export function viewBox() {
  const ps = Object.values(S.pos); if (!ps.length) return '0 0 100 100';
  const xs = ps.map(p => p.x), ys = ps.map(p => p.y), m = 100;
  const x0 = Math.min(...xs) - m, y0 = Math.min(...ys) - m - 20, x1 = Math.max(...xs) + m, y1 = Math.max(...ys) + m;
  return `${x0} ${y0} ${x1 - x0} ${y1 - y0}`;
}
export function ridisegna() {
  if (!S.G) return;
  if (!S.vb) S.vb = viewBox();
  const svg = $('#svg'); svg.setAttribute('viewBox', S.vb); svg.innerHTML = svgContenuto(S.G, S.pos);
  svg.classList.toggle('mod', !!S.modifica);
  $('#bTogli').hidden = !S.evid;
}
let trascina = null;
// modalità Modifica (modifica.js): clic senza trascinare su un'etichetta d'interfaccia o sulla
// scritta di un AS -> gesti.su({mod: 'if', dev, iface} | {mod: 'as', as})
export const gesti = {su: null, punto: null};
export function puntoSvg(e) { const m = $('#svg').getScreenCTM().inverse(); const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(m); return {x: p.x, y: p.y}; }
// trascinando un nodo lo si sposta, trascinando lo sfondo si sposta la vista; rotellina = zoom
$('#svg').addEventListener('pointerdown', e => {
  const g = e.target.closest('[data-id]'), m = S.modifica && e.target.closest('[data-mod]');
  trascina = g && !m ? {id: g.dataset.id, x: e.clientX, y: e.clientY, mosso: false}
               : {sfondo: true, x: e.clientX, y: e.clientY, vb: S.vb.split(' ').map(Number), scala: 1 / $('#svg').getScreenCTM().a,
                  mod: m ? Object.assign({}, m.dataset) : null, mosso: false};
  $('#svg').setPointerCapture(e.pointerId);
});
$('#svg').addEventListener('pointermove', e => {
  if (!trascina) return;
  if (trascina.sfondo) {
    if (Math.abs(e.clientX - trascina.x) + Math.abs(e.clientY - trascina.y) > 4) trascina.mosso = true;
    const [x, y, w, h] = trascina.vb, s = trascina.scala;
    S.vb = [x - (e.clientX - trascina.x) * s, y - (e.clientY - trascina.y) * s, w, h].join(' ');
    $('#svg').setAttribute('viewBox', S.vb); return;
  }
  if (Math.abs(e.clientX - trascina.x) + Math.abs(e.clientY - trascina.y) > 4) trascina.mosso = true;
  if (trascina.mosso) { S.pos[trascina.id] = puntoSvg(e); ridisegna(); }
});
$('#svg').addEventListener('pointerup', () => {
  if (!trascina) return;
  const t = trascina; trascina = null;
  if (t.sfondo) { if (t.mod && !t.mosso && gesti.su) gesti.su(t.mod); return; }
  if (t.mosso) mem('pos:' + S.nome, S.pos);
  else if (t.id.startsWith('d:')) {
    if (S.modifica && gesti.su && gesti.punto && gesti.punto({mod: 'dev', nome: t.id.slice(2)})) return;   // punto del percorso voluto
    S.sel = t.id.slice(2); if (S.modifica) S.op = null; ridisegna(); lato();
  }
  else if (t.id.startsWith('l:') && S.modifica && gesti.su) gesti.su({mod: 'lan', lan: t.id.slice(2)});
});
$('#svg').addEventListener('wheel', e => {
  e.preventDefault();
  const f = e.deltaY > 0 ? 1.15 : 1 / 1.15, p = puntoSvg(e), [x, y, w, h] = S.vb.split(' ').map(Number);
  S.vb = [p.x - (p.x - x) * f, p.y - (p.y - y) * f, w * f, h * f].join(' ');
  $('#svg').setAttribute('viewBox', S.vb);
}, {passive: false});
$('#bAdatta').onclick = () => { S.vb = null; ridisegna(); };
$('#bRiordina').onclick = () => {
  if (!S.varianti) { S.varianti = varianti(S.G); S.variante = -1; }
  S.variante = (S.variante + 1) % S.varianti.length;
  S.pos = JSON.parse(JSON.stringify(S.varianti[S.variante]));
  mem('pos:' + S.nome, null); S.vb = null; ridisegna();
};
// barra dei livelli del disegno (la scelta resta nel browser)
S.livelli = creaLivelli($('#livelli'), LIVELLI, a => { S.livelli = a; ridisegna(); }, 'livelli:topologia').attivi();
$('#bTogli').onclick = () => { S.evid = null; ridisegna(); };
$('#bSvg').onclick = () => {
  const testo = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox()}" width="1400" style="background:#fff">${svgContenuto(S.G, S.pos)}</svg>`;
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([testo], {type: 'image/svg+xml'}));
  a.download = S.nome + '-topologia.svg'; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
};
