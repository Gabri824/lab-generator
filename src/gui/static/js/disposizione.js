// Disposizione automatica della Topologia (grafo del lab, varianti senza incroci): funzioni pure,
// usate dalla Topologia e dall'editor ("Parti da un lab esistente"); si provano con Node.
import { COL } from './comune.js';
import { largIface, largLan } from './etichette.js';

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
