// Disegno della bozza nell'editor: stesse icone ed etichette della Topologia (riusa le sue funzioni
// senza cambiarle), più selezione, problemi e collegamento in corso.
import { COL, esc } from '../comune.js';
import { etichettaIface, largh } from '../etichette.js';
import { posizionaEtichette, STILE_SVG } from '../topologia.js';

export const COLORE = {router: '#2563eb', host: '#475569', www: '#0d9488', dns: '#7c3aed'};

const STILE_EDITOR = `<style>
.ed-colpo{stroke:transparent;stroke-width:14;cursor:pointer}
.lk.ed-sel{stroke:#0f172a;stroke-width:4}
.ed-err{stroke:#dc2626;stroke-width:2.5;fill:none;stroke-dasharray:5 3}
.ed-attesa{stroke:#f59e0b;stroke-width:4;fill:none}
.ed-rett{fill:rgb(37 99 235 / .08);stroke:#2563eb;stroke-width:1;stroke-dasharray:4 3}
.ed-vuoto{font:14px system-ui,sans-serif;fill:#64748b}
.nodo{cursor:pointer}
.ed-zona-bordo{fill:none;stroke:transparent;stroke-width:12;pointer-events:stroke;cursor:move}
.ed-zona-et{cursor:move}
.ed-zt{font:600 13px system-ui,sans-serif;paint-order:stroke;stroke:#fff;stroke-width:4px;stroke-linejoin:round}
.ed-maniglia{fill:#fff;stroke:#0f172a;stroke-width:1.5}
.ed-abr{font:700 9px system-ui,sans-serif;fill:#fff}
</style>`;

const COLORE_ZONA = {rip: '#b45309', ospf: '#0f766e'};
const TRATTO_ZONA = {as: '', rip: '9 5', ospf: '4 4'};

// colore di ogni AS (numeri validi in ordine crescente), come i colori degli AS nella Topologia
export function coloriAs(bozza) {
  const asn = [...new Set(bozza.zone.filter(z => z.tipo === 'as' && /^\d+$/.test(String(z.valore).trim())).map(z => Number(z.valore)))].sort((a, b) => a - b);
  return Object.fromEntries(asn.map((a, i) => [String(a), COL[i % COL.length]]));
}
const coloreZona = (z, colori) => z.tipo === 'as' ? (colori[String(Number(z.valore))] || '#64748b') : COLORE_ZONA[z.tipo];
function testoZona(z) {
  const v = String(z.valore ?? '').trim();
  if (z.tipo === 'as') return `AS ${v || '?'}`;
  if (z.tipo === 'rip') return 'RIP';
  return `Area ${v || '?'}${z.stub ? ' · stub' : ''}`;
}

// zone dietro a tutto (le più grandi sotto), etichette sopra le zone ma sotto il resto
function svgZone(bozza, colori, sel, err) {
  const zone = bozza.zone.slice().sort((a, b) => b.w * b.h - a.w * a.h);
  let fondo = '', etichette = '';
  for (const z of zone) {
    const c = coloreZona(z, colori), s = sel.has(z.id);
    fondo += `<rect x="${z.x}" y="${z.y}" width="${z.w}" height="${z.h}" rx="18" fill="${c}" fill-opacity="${z.tipo === 'as' ? 0.07 : 0.05}" stroke="${c}" stroke-width="${s ? 3 : 2}"${TRATTO_ZONA[z.tipo] ? ` stroke-dasharray="${TRATTO_ZONA[z.tipo]}"` : ''} pointer-events="none"/>`;
    fondo += `<g data-el="${esc(z.id)}" data-tipo="zona"><rect class="ed-zona-bordo" x="${z.x}" y="${z.y}" width="${z.w}" height="${z.h}" rx="18"/></g>`;
    if (err.has(z.id)) fondo += `<rect class="ed-err" x="${z.x - 5}" y="${z.y - 5}" width="${z.w + 10}" height="${z.h + 10}" rx="22"/>`;
    const t = testoZona(z), w = largh(t, 13) + 14;
    etichette += `<g class="ed-zona-et" data-el="${esc(z.id)}" data-tipo="zona"><rect x="${z.x + 8}" y="${z.y + 6}" width="${w}" height="20" rx="6" fill="#fff" fill-opacity="${s ? 1 : 0.85}" stroke="${s ? '#0f172a' : c}" stroke-width="${s ? 1.5 : 1}"/>`
      + `<text class="ed-zt" x="${z.x + 15}" y="${z.y + 21}" fill="${c}">${esc(t)}</text></g>`;
  }
  return fondo + etichette;
}
function maniglie(z) {
  const m = 12;
  return [['nw', z.x, z.y], ['ne', z.x + z.w, z.y], ['sw', z.x, z.y + z.h], ['se', z.x + z.w, z.y + z.h]]
    .map(([a, x, y]) => `<rect class="ed-maniglia" data-el="${esc(z.id)}" data-tipo="maniglia" data-angolo="${a}" x="${x - m / 2}" y="${y - m / 2}" width="${m}" height="${m}" style="cursor:${a === 'nw' || a === 'se' ? 'nwse' : 'nesw'}-resize"/>`).join('');
}

// Grafo nel formato della Topologia (nodi 'd:<id>' e 'l:<id>'), per riusare posizionaEtichette.
export function grafoBozza(bozza, conv) {
  const nodes = [], links = [], pos = {};
  const disp = new Map(bozza.dispositivi.map(d => [d.id, d]));
  for (const d of bozza.dispositivi) {
    nodes.push({id: 'd:' + d.id, el: d.id, nome: conv.nomi[d.id], tipo: d.tipo, gruppo: null});
    pos['d:' + d.id] = {x: d.x, y: d.y};
  }
  const iface = c => {
    const k = (conv.interfacce[c.dispositivo] || []).indexOf(c.id);
    return {dev: 'eth' + Math.max(k, 0), ip: conv.ip[c.id] || ''};
  };
  for (const l of bozza.lan) {
    const ms = bozza.collegamenti.filter(c => c.lan === l.id && disp.has(c.dispositivo));
    const nome = conv.nomiLan[l.id], subnet = conv.subnet[l.id] || '';
    if (l.punto && ms.length === 2) {
      links.push({a: 'd:' + ms[0].dispositivo, b: 'd:' + ms[1].dispositivo, lan: nome, subnet, ia: iface(ms[0]), ib: iface(ms[1]), el: l.id, punto: true});
      continue;
    }
    nodes.push({id: 'l:' + l.id, el: l.id, nome, tipo: 'lan', subnet, gruppo: null});
    pos['l:' + l.id] = {x: l.x ?? 0, y: l.y ?? 0};
    for (const c of ms) links.push({a: 'd:' + c.dispositivo, b: 'l:' + l.id, lan: nome, subnet, ia: iface(c), ib: null, el: c.id, lanEl: l.id});
  }
  return {G: {nodes, links}, pos};
}

// stato: {sel: Set di id, problemi: Set di id, attesa: id del dispositivo da cui parte il collegamento,
//         rettangolo: {x, y, w, h} | null, interfacce: bool}
export function svgBozza(bozza, conv, stato) {
  const {G, pos} = grafoBozza(bozza, conv);
  const sel = stato.sel || new Set(), err = stato.problemi || new Set();
  let h = STILE_SVG + STILE_EDITOR;
  if (!G.nodes.length && !bozza.zone.length) {
    return h + `<text class="ed-vuoto" x="0" y="0" text-anchor="middle">Scegli uno strumento: R router, H host, W server WWW, D server DNS, N nodo LAN, L collega, A AS, I RIP, O area OSPF</text>`;
  }
  const colori = coloriAs(bozza), abr = new Set(conv.abr || []);
  h += svgZone(bozza, colori, sel, err);
  for (const l of G.links) {
    const a = pos[l.a], b = pos[l.b], s = sel.has(l.el) || (l.lanEl && sel.has(l.lanEl));
    h += `<g data-el="${esc(l.el)}" data-tipo="${l.punto ? 'link' : 'coll'}"><line class="lk${s ? ' ed-sel' : ''}" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>`
      + `<line class="ed-colpo" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/></g>`;
    if (err.has(l.el)) h += `<line class="ed-err" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>`;
  }
  const {et, nomi} = posizionaEtichette(G, pos, stato.interfacce !== false, []);
  // l'etichetta di un'interfaccia appartiene al suo link: un clic lì vale come un clic sul link
  const linkDi = new Map();
  for (const l of G.links) { linkDi.set(l.ia, l); if (l.ib) linkDi.set(l.ib, l); }
  for (const n of G.nodes) {
    const p = pos[n.id];
    h += `<g class="nodo" data-el="${esc(n.el)}" data-tipo="${n.tipo === 'lan' ? 'lan' : 'dispositivo'}" transform="translate(${p.x},${p.y})">`;
    if (n.tipo === 'lan') {
      const w = Math.max(34, 9 * n.nome.length + 16);
      if (sel.has(n.el)) h += `<rect class="sel" x="${-w / 2 - 6}" y="-18" width="${w + 12}" height="36" rx="18"/>`;
      if (err.has(n.el)) h += `<rect class="ed-err" x="${-w / 2 - 4}" y="-16" width="${w + 8}" height="32" rx="16"/>`;
      h += `<rect x="${-w / 2}" y="-12" width="${w}" height="24" rx="12" fill="#f8fafc" stroke="#64748b" stroke-width="1.5"/><text class="t" y="4" text-anchor="middle">${esc(n.nome)}</text>`;
      h += `<text class="ts" y="27" text-anchor="middle">${esc(n.subnet || 'subnet?')}</text>`;
    } else {
      const as = n.tipo === 'router' && conv.zone[n.el] ? conv.zone[n.el].as : '';
      const c = as ? (colori[String(Number(as))] || COLORE.router) : COLORE[n.tipo];
      if (stato.attesa === n.el) h += n.tipo === 'router' ? '<circle class="ed-attesa" r="27"/>' : '<rect class="ed-attesa" x="-24" y="-20" width="48" height="40" rx="8"/>';
      if (sel.has(n.el)) h += n.tipo === 'router' ? '<circle class="sel" r="32"/>' : '<rect class="sel" x="-29" y="-25" width="58" height="50" rx="10"/>';
      if (err.has(n.el)) h += n.tipo === 'router' ? '<circle class="ed-err" r="36"/>' : '<rect class="ed-err" x="-33" y="-29" width="66" height="58" rx="12"/>';
      if (n.tipo === 'router') {
        h += `<circle r="20" fill="${c}" stroke="#fff" stroke-width="2"/><path d="M-10,-4 H9 M5,-8 L9,-4 L5,0 M10,4 H-9 M-5,0 L-9,4 L-5,8" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`;
        if (abr.has(n.el)) h += '<g transform="translate(13,-30)"><rect width="30" height="15" rx="7.5" fill="#0f766e"/><text class="ed-abr" x="15" y="11" text-anchor="middle">ABR</text></g>';
      } else {
        const lab = {host: '', www: 'www', dns: 'DNS'}[n.tipo];
        h += `<rect x="-17" y="-13" width="34" height="26" rx="4" fill="${c}" stroke="#fff" stroke-width="2"/>`;
        h += lab ? `<text y="4" text-anchor="middle" style="font:700 10px system-ui,sans-serif;fill:#fff">${lab}</text>` : '<rect x="-10" y="-7" width="20" height="12" rx="1.5" fill="none" stroke="#fff" stroke-width="1.6"/>';
      }
      const t = nomi[n.id];
      h += `<text class="t" x="${(t.x - p.x).toFixed(1)}" y="${(t.y - p.y).toFixed(1)}" text-anchor="${t.anc}">${esc(n.nome)}</text>`;
    }
    h += '</g>';
  }
  for (const e of et) {
    if (e.tipo === 'lan') {
      const s = sel.has(e.l.el);
      h += `<g class="nodo" data-el="${esc(e.l.el)}" data-tipo="link"><rect x="${e.x - e.w / 2}" y="${e.y - 9}" width="${e.w}" height="18" rx="9" fill="#f8fafc" stroke="${s ? '#0f172a' : '#cbd5e1'}"${s ? ' stroke-width="2"' : ''}/>`
        + `<text class="lt" x="${e.x}" y="${e.y + 4}" text-anchor="middle"><tspan class="lb">${esc(e.l.lan)}</tspan> ${esc(e.l.subnet || 'subnet?')}</text></g>`;
    } else {
      const l = linkDi.get(e.it);
      h += l ? `<g class="nodo" data-el="${esc(l.el)}" data-tipo="${l.punto ? 'link' : 'coll'}">${etichettaIface(e.it, e.x, e.y, '#475569')}</g>`
        : etichettaIface(e.it, e.x, e.y, '#475569');
    }
  }
  for (const z of bozza.zone) if (sel.has(z.id) && sel.size === 1) h += maniglie(z);
  if (stato.rettangolo) {
    const r = stato.rettangolo;
    h += `<rect class="ed-rett" x="${r.x}" y="${r.y}" width="${r.w}" height="${r.h}"/>`;
  }
  return h;
}

// riquadro che contiene tutto il disegno, con un margine
export function riquadro(bozza) {
  const ps = [...bozza.dispositivi, ...bozza.lan.filter(l => !l.punto)].map(x => ({x: x.x, y: x.y}));
  for (const z of bozza.zone || []) ps.push({x: z.x, y: z.y}, {x: z.x + z.w, y: z.y + z.h});
  if (!ps.length) return '-450 -250 900 500';
  const xs = ps.map(p => p.x), ys = ps.map(p => p.y), m = 110;
  const x0 = Math.min(...xs) - m, y0 = Math.min(...ys) - m, x1 = Math.max(...xs) + m, y1 = Math.max(...ys) + m;
  const w = Math.max(x1 - x0, 500), hh = Math.max(y1 - y0, 320);
  return `${(x0 + x1 - w) / 2} ${(y0 + y1 - hh) / 2} ${w} ${hh}`;
}
