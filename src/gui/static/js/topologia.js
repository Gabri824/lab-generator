// Topologia: grafo del lab, disposizione automatica, disegno SVG, trascinamento e zoom.
import { $, COL, esc, mem, S } from './comune.js';
import { lato } from './dispositivo.js';

// ---------- topologia ----------
export function colori(lab) {
  const gs = [...new Set(lab.dispositivi.map(d => d.gruppo).filter(Boolean))].sort((a, b) => a - b);
  const m = {}; gs.forEach((g, i) => m[g] = COL[i % COL.length]); return m;
}
export function grafo(lab) {
  const nodes = [], links = [];
  for (const d of lab.dispositivi) nodes.push({id: 'd:' + d.nome, nome: d.nome, tipo: d.tipo, gruppo: d.gruppo || '_', dev: d});
  for (const l of lab.lan) {
    const ms = [];
    for (const d of lab.dispositivi) for (const it of d.interfacce) if (it.lan === l.nome) ms.push({d, it});
    if (ms.length === 2 && ms[0].d.nome !== ms[1].d.nome) {
      links.push({a: 'd:' + ms[0].d.nome, b: 'd:' + ms[1].d.nome, lan: l.nome, subnet: l.subnet, ia: ms[0].it, ib: ms[1].it});
    } else {
      nodes.push({id: 'l:' + l.nome, nome: l.nome, tipo: 'lan', subnet: l.subnet, gruppo: null});
      for (const m of ms) links.push({a: 'd:' + m.d.nome, b: 'l:' + l.nome, lan: l.nome, subnet: l.subnet, ia: m.it, ib: null});
    }
  }
  // una LAN tutta dentro un AS appartiene a quell'AS (per il riquadro dell'AS)
  for (const n of nodes) if (n.tipo === 'lan') {
    const gs = new Set(links.filter(l => l.b === n.id).map(l => nodes.find(x => x.id === l.a).gruppo));
    n.gruppo = gs.size === 1 ? [...gs][0] : null;
  }
  return {nodes, links};
}
// generatore pseudo-casuale con seme: stessa variante = stessa disposizione
export function casuale(seme) {
  let t = (seme * 2654435761) >>> 0;
  return () => { t = (t + 0x6D2B79F5) >>> 0; let r = Math.imul(t ^ (t >>> 15), 1 | t); r ^= r + Math.imul(r ^ (r >>> 7), 61 | r); return ((r ^ (r >>> 14)) >>> 0) / 4294967296; };
}
export function mescola(v, rnd) { v = v.slice(); for (let i = v.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [v[i], v[j]] = [v[j], v[i]]; } return v; }
export function disponi(G, seme) {
  const pos = {}, membri = {}, rnd = casuale(seme || 0);
  for (const n of G.nodes) if (n.tipo !== 'lan') (membri[n.gruppo] = membri[n.gruppo] || []).push(n);
  let gruppi = Object.keys(membri).sort((a, b) => (+a || 1e9) - (+b || 1e9));
  if (seme) gruppi = mescola(gruppi, rnd);
  const R = gruppi.length > 1 ? 150 + 75 * gruppi.length : 0, centro = {};
  gruppi.forEach((g, i) => { const a = 2 * Math.PI * i / gruppi.length - Math.PI / 2; centro[g] = {x: R * Math.cos(a), y: R * Math.sin(a)}; });
  for (const g of gruppi) { const ms = seme ? mescola(membri[g], rnd) : membri[g], r = ms.length > 1 ? 45 + 14 * ms.length : 0;
    ms.forEach((n, i) => { const a = 2 * Math.PI * i / ms.length; pos[n.id] = {x: centro[g].x + r * Math.cos(a), y: centro[g].y + r * Math.sin(a)}; }); }
  for (const n of G.nodes) if (n.tipo === 'lan') {
    const ls = G.links.filter(l => l.b === n.id); let x = 0, y = 0;
    ls.forEach(l => { x += pos[l.a].x; y += pos[l.a].y; });
    const k = Math.max(ls.length, 1); pos[n.id] = {x: x / k + 9, y: y / k + 9};
  }
  // lunghezza a riposo dei link: abbastanza per le etichette che ci stanno sopra
  const riposo = l => l.b.startsWith('l:') ? Math.max(115, 60 + largIface(l.ia))
    : Math.max(210, 56 + largIface(l.ia) + largIface(l.ib) + largLan(l));
  const N = G.nodes.length, IT = 700;
  for (let it = 0; it < IT; it++) {
    const f = {}; G.nodes.forEach(n => f[n.id] = {x: 0, y: 0});
    for (let i = 0; i < N; i++) for (let j = i + 1; j < N; j++) {
      const a = G.nodes[i], b = G.nodes[j], pa = pos[a.id], pb = pos[b.id];
      let dx = pa.x - pb.x, dy = pa.y - pb.y, d2 = dx * dx + dy * dy;
      if (d2 < 1) { dx = (i - j) * 0.1; dy = 0.5; d2 = dx * dx + dy * dy; }
      const altro = a.gruppo && b.gruppo && a.gruppo !== b.gruppo;
      const d = Math.sqrt(d2), k = (altro ? 34000 : 16000) / d2;
      f[a.id].x += k * dx / d; f[a.id].y += k * dy / d; f[b.id].x -= k * dx / d; f[b.id].y -= k * dy / d;
    }
    for (const l of G.links) {
      const pa = pos[l.a], pb = pos[l.b], dx = pb.x - pa.x, dy = pb.y - pa.y, d = Math.sqrt(dx * dx + dy * dy) || 1;
      const k = (d - riposo(l)) * 0.06;
      f[l.a].x += k * dx / d; f[l.a].y += k * dy / d; f[l.b].x -= k * dx / d; f[l.b].y -= k * dy / d;
    }
    // coesione dell'AS solo tra i router: gli host restano all'esterno, vicino al loro router
    for (const g of gruppi) { const ms = membri[g].filter(n => n.tipo === 'router'); if (g === '_' || ms.length < 2) continue;
      let cx = 0, cy = 0; ms.forEach(n => { cx += pos[n.id].x; cy += pos[n.id].y; }); cx /= ms.length; cy /= ms.length;
      ms.forEach(n => { f[n.id].x += (cx - pos[n.id].x) * 0.012; f[n.id].y += (cy - pos[n.id].y) * 0.012; }); }
    const T = 40 * (1 - it / IT) + 0.5;
    for (const n of G.nodes) { const v = f[n.id], m = Math.sqrt(v.x * v.x + v.y * v.y) || 1, s = Math.min(m, T) / m; pos[n.id].x += v.x * s; pos[n.id].y += v.y * s; }
  }
  return pos;
}
// qualità di una disposizione: incroci tra link + nodi appoggiati su link non loro (meno = meglio)
export function difetti(G, pos) {
  const seg = G.links.map(l => [pos[l.a], pos[l.b], l.a, l.b]);
  const cr = (o, a, b) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
  let n = 0;
  for (let i = 0; i < seg.length; i++) for (let j = i + 1; j < seg.length; j++) {
    const [p1, p2, a1, b1] = seg[i], [q1, q2, a2, b2] = seg[j];
    if (a1 === a2 || a1 === b2 || b1 === a2 || b1 === b2) continue;
    if (cr(p1, p2, q1) * cr(p1, p2, q2) < 0 && cr(q1, q2, p1) * cr(q1, q2, p2) < 0) n += 1;
  }
  for (const nd of G.nodes) { const p = pos[nd.id];
    for (const [a, b, ia, ib] of seg) {
      if (ia === nd.id || ib === nd.id) continue;
      const dx = b.x - a.x, dy = b.y - a.y, L = dx * dx + dy * dy || 1;
      const t = Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / L));
      if (Math.hypot(a.x + t * dx - p.x, a.y + t * dy - p.y) < 34) n += 0.7;
    }
  }
  return n;
}
// varie disposizioni (semi diversi), dalla migliore alla peggiore; "Riordina" le scorre
// ruota la disposizione in modo che il lato lungo sia orizzontale (il riquadro è largo)
export function orizzontale(pos) {
  const ps = Object.values(pos), n = ps.length || 1;
  const mx = ps.reduce((s, p) => s + p.x, 0) / n, my = ps.reduce((s, p) => s + p.y, 0) / n;
  let sxx = 0, syy = 0, sxy = 0;
  ps.forEach(p => { const dx = p.x - mx, dy = p.y - my; sxx += dx * dx; syy += dy * dy; sxy += dx * dy; });
  const a = -0.5 * Math.atan2(2 * sxy, sxx - syy), c = Math.cos(a), s = Math.sin(a);
  for (const k in pos) { const dx = pos[k].x - mx, dy = pos[k].y - my; pos[k] = {x: dx * c - dy * s, y: dx * s + dy * c}; }
  return pos;
}
export function varianti(G) {
  const v = [];
  for (let s = 0; s < 10; s++) { const pos = orizzontale(disponi(G, s)); v.push({pos, d: difetti(G, pos)}); }
  return v.sort((a, b) => a.d - b.d).map(x => x.pos);
}
export function inviluppo(p) {
  if (p.length < 3) return p;
  p = p.slice().sort((a, b) => a.x - b.x || a.y - b.y);
  const cr = (o, a, b) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x), lo = [], up = [];
  for (const q of p) { while (lo.length >= 2 && cr(lo[lo.length - 2], lo[lo.length - 1], q) <= 0) lo.pop(); lo.push(q); }
  for (const q of p.slice().reverse()) { while (up.length >= 2 && cr(up[up.length - 2], up[up.length - 1], q) <= 0) up.pop(); up.push(q); }
  return lo.slice(0, -1).concat(up.slice(0, -1));
}
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
</style>`;
export const largh = (testo, px) => testo.length * px * 0.62;
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
// etichetta di interfaccia: [eth0|1] = nome dell'interfaccia + ultimo numero dell'IP
export const numIp = it => it.ip ? it.ip.split('/')[0].split('.')[3] : '';
export const largIface = it => largh(it.dev, 11) + 8 + (numIp(it) ? largh(numIp(it), 11) + 9 : 0);
export const largLan = l => largh(l.lan + '  ' + (l.subnet || ''), 11) + 10;
export function etichettaIface(it, x, y, colore) {
  const num = numIp(it);
  const w1 = largh(it.dev, 11) + 8, w2 = num ? largh(num, 11) + 9 : 0, w = w1 + w2, x0 = x - w / 2;
  let h = `<rect class="pill" x="${x0}" y="${y - 9}" width="${w}" height="18" rx="4"/>`;
  h += `<text class="pt" x="${x0 + w1 / 2}" y="${y + 4}" text-anchor="middle">${esc(it.dev)}</text>`;
  if (num) h += `<rect x="${x0 + w1}" y="${y - 9}" width="${w2}" height="18" rx="4" fill="${colore}"/><rect x="${x0 + w1}" y="${y - 9}" width="4" height="18" fill="${colore}"/>`
             + `<text class="nt" x="${x0 + w1 + w2 / 2}" y="${y + 4}" text-anchor="middle">${esc(num)}</text>`;
  return h;
}
export const RAGGIO = {router: 22, host: 19, www: 19, dns: 19};
// Posizione delle etichette senza sovrapposizioni. Ogni etichetta scivola lungo il
// proprio link (s = distanza dal primo nodo) e, se non basta, si scosta di poco di lato
// (o); nodi, nomi dei dispositivi e subnet delle LAN sono ostacoli fissi.
export function posizionaEtichette(G, pos, iface, extra) {
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
    const a = latoNome(G, pos, n), cx = Math.cos(a), cy = Math.sin(a), w = largh(n.nome, 12.5) + 4;
    const anc = cx > 0.5 ? 'start' : (cx < -0.5 ? 'end' : 'middle');
    const tx = p.x + cx * 30, ty = p.y + cy * 32;
    nomi[n.id] = {anc, x: tx, y: ty + 4.5};
    ost.push({x: tx + (anc === 'start' ? w / 2 : anc === 'end' ? -w / 2 : 0), y: ty, w, h: 17});
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
    if (!iface) continue;
    if (l.ia) {
      const w = largIface(l.ia), sMin = raggio(l.a) + est(w, 18) + 3;
      et.push(Object.assign({}, base, {tipo: 'if', it: l.ia, nodo: l.a, w, s: Math.max(sMin, Math.min(52, len * 0.28)), sMin, sMax: Math.max(sMin, len / 2 - 8)}));
    }
    if (l.ib) {
      const w = largIface(l.ib), sMax = len - raggio(l.b) - est(w, 18) - 3;
      et.push(Object.assign({}, base, {tipo: 'if', it: l.ib, nodo: l.b, w, s: Math.min(sMax, len - Math.min(52, len * 0.28)), sMin: Math.min(sMax, len / 2 + 8), sMax}));
    }
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
export function svgContenuto(G, pos) {
  let h = STILE_SVG, etichetteAS = '';
  const ostAS = [];      // scritte degli AS: ostacoli per le etichette
  const gruppi = [...new Set(G.nodes.map(n => n.gruppo).filter(g => g && g !== '_'))];
  for (const g of gruppi) {
    const pts = inviluppo(G.nodes.filter(n => n.gruppo === g).map(n => pos[n.id]));
    const c = S.colori[g] || '#64748b', igp = igpGruppo(G, g);
    const d = 'M' + pts.map(p => p.x.toFixed(1) + ',' + p.y.toFixed(1)).join(' L') + ' Z';
    h += `<path d="${d}" fill="${c}" stroke="${c}" stroke-width="110" stroke-linejoin="round" stroke-linecap="round" opacity="0.10"/>`;
    const top = pts.reduce((a, b) => b.y < a.y ? b : a);
    ostAS.push({x: top.x, y: top.y - 69, w: largh('AS' + g, 16) + (igp ? largh('· ' + igp, 12) + 6 : 0) + 6, h: 22});
    etichetteAS += `<text class="ga" x="${top.x}" y="${top.y - 64}" text-anchor="middle" fill="${c}">AS${esc(g)}${igp ? `<tspan class="gp" dx="6">· ${esc(igp)}</tspan>` : ''}</text>`;
  }
  for (const l of G.links) { const a = pos[l.a], b = pos[l.b];
    const cls = S.spenti && S.spenti.has(l.lan) ? ' off' : evidLink(l) ? ' ev' : (S.evid && S.evid.manca && S.evid.manca.has(l.lan)) ? ' manca' : '';
    h += `<line class="lk${cls}" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>`; }
  const {et, nomi} = posizionaEtichette(G, pos, $('#cIface').checked, ostAS);
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
        const lab = {host: '', www: 'www', dns: 'DNS'}[n.tipo];
        h += `<rect x="-17" y="-13" width="34" height="26" rx="4" fill="${c}" stroke="#fff" stroke-width="2"/>`;
        h += lab ? `<text y="4" text-anchor="middle" style="font:700 10px system-ui,sans-serif;fill:#fff">${lab}</text>` : '<rect x="-10" y="-7" width="20" height="12" rx="1.5" fill="none" stroke="#fff" stroke-width="1.6"/>';
      }
      const t = nomi[n.id];
      h += `<text class="t" x="${(t.x - p.x).toFixed(1)}" y="${(t.y - p.y).toFixed(1)}" text-anchor="${t.anc}">${esc(n.nome)}</text>`;
      if (ord[n.nome] != null) h += `<circle cx="20" cy="-20" r="10" fill="#f59e0b"/><text class="ord" x="20" y="-16" text-anchor="middle">${esc(ord[n.nome])}</text>`;
    }
    h += '</g>';
  }
  // etichette sopra a tutto: link punto-punto (nome e subnet) e interfacce
  const col = id => { const n = G.nodes.find(x => x.id === id); return (n && S.colori[n.gruppo]) || '#475569'; };
  for (const e of et) {
    if (e.tipo === 'lan') h += `<rect x="${e.x - e.w / 2}" y="${e.y - 9}" width="${e.w}" height="18" rx="9" fill="#f8fafc" stroke="#cbd5e1"/>`
      + `<text class="lt" x="${e.x}" y="${e.y + 4}" text-anchor="middle"><tspan class="lb">${esc(e.l.lan)}</tspan> ${esc(e.l.subnet || '')}</text>`;
    else h += etichettaIface(e.it, e.x, e.y, col(e.nodo));
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
  $('#bTogli').hidden = !S.evid;
}
let trascina = null;
export function puntoSvg(e) { const m = $('#svg').getScreenCTM().inverse(); const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(m); return {x: p.x, y: p.y}; }
// trascinando un nodo lo si sposta, trascinando lo sfondo si sposta la vista; rotellina = zoom
$('#svg').addEventListener('pointerdown', e => {
  const g = e.target.closest('[data-id]');
  trascina = g ? {id: g.dataset.id, x: e.clientX, y: e.clientY, mosso: false}
               : {sfondo: true, x: e.clientX, y: e.clientY, vb: S.vb.split(' ').map(Number), scala: 1 / $('#svg').getScreenCTM().a};
  $('#svg').setPointerCapture(e.pointerId);
});
$('#svg').addEventListener('pointermove', e => {
  if (!trascina) return;
  if (trascina.sfondo) {
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
  if (t.sfondo) return;
  if (t.mosso) mem('pos:' + S.nome, S.pos);
  else if (t.id.startsWith('d:')) { S.sel = t.id.slice(2); ridisegna(); lato(); }
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
$('#cIface').onchange = ridisegna;
$('#bTogli').onclick = () => { S.evid = null; ridisegna(); };
$('#bSvg').onclick = () => {
  const testo = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox()}" width="1400" style="background:#fff">${svgContenuto(S.G, S.pos)}</svg>`;
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([testo], {type: 'image/svg+xml'}));
  a.download = S.nome + '-topologia.svg'; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
};
