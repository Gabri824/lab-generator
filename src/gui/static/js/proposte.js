// Proposte per i moduli della modalità Modifica (fase 5.2): IP liberi, nomi liberi, protocolli dei
// vicini, dati di un dispositivo nuovo nella forma del modello del wizard. Niente pagina: si provano
// con Node (tests/js/proposte.test.mjs). `lab` è la risposta di /api/lab.
import { completaIp, intIp, ipInt, leggiRete, testoRete } from './editor/bozza.js';

export { completaIp };

export function ipUsati(lab) {
  const s = new Set();
  for (const d of lab.dispositivi) {
    for (const it of d.interfacce) if (it.ip) s.add(it.ip.split('/')[0]);
    for (const ip of d.loopback || []) s.add(ip.split('/')[0]);
  }
  return s;
}

export function subnetDellaLan(lab, lan) {
  const l = lab.lan.find(x => x.nome === lan);
  return l && l.subnet ? l.subnet : '';
}

// primo IP libero della subnet ('10.0.0.0/24'); `preferito` = parte host da provare per prima
export function primoIpLibero(subnet, usati, preferito = null) {
  const r = leggiRete(subnet);
  if (!r) return '';
  const n = 2 ** (32 - r.prefisso);
  const valido = h => (r.prefisso >= 31 ? h >= 0 && h < n : h >= 1 && h < n - 1) && !usati.has(intIp(r.base + h));
  const host = [];
  if (preferito != null) host.push(preferito);
  for (let h = 0; h < n && h < 65536; h++) host.push(h);
  const h = host.find(valido);
  return h == null ? '' : `${intIp(r.base + h)}/${r.prefisso}`;
}

// IP scritto nel modulo: "5" o "0.5" completati dalla subnet, maschera aggiunta se manca
export function ipDelModulo(valore, subnet) {
  return completaIp(valore, subnet);
}

const NOMI = {router: 'r', host: 'host', www: 'www', dns: 'dns'};

// nome libero: per i router che si chiamano tutti as<AS>r<n> (e AS noto) as<AS>r<n>, altrimenti
// r<n>, host<n>, www<n>, dns<n>
export function nomeLibero(lab, tipo, asn = '') {
  const usati = new Set(lab.dispositivi.map(d => d.nome));
  // come il wizard: il primo DNS del lab si chiama root (server root, master per '.')
  if (tipo === 'dns' && !lab.dispositivi.some(d => d.tipo === 'dns') && !usati.has('root')) return 'root';
  const routers = lab.dispositivi.filter(d => d.tipo === 'router').map(d => d.nome);
  const conAs = routers.length && routers.every(n => /^as\d+r\d+$/.test(n));
  const pre = tipo === 'router' && conAs && /^\d+$/.test(String(asn)) ? `as${asn}r` : NOMI[tipo];
  for (let i = 1; ; i++) if (!usati.has(pre + i)) return pre + i;
}

// router della LAN e quello che hanno in comune: IGP, AS (gruppo del disegno), gateway proposto
export function vicinatoDellaLan(lab, lan) {
  const membri = lab.dispositivi.filter(d => d.interfacce.some(it => it.lan === lan));
  const routers = membri.filter(d => d.tipo === 'router');
  const igp = ['ospf', 'rip'].filter(p => routers.some(r => r.demoni.includes(p + 'd')));
  const gruppi = [...new Set(routers.map(r => r.gruppo).filter(g => g && g !== '_'))];
  const r0 = routers.find(r => r.interfacce.some(it => it.lan === lan && it.ip));
  const gw = r0 ? r0.interfacce.find(it => it.lan === lan && it.ip).ip.split('/')[0] : '';
  const bgp = routers.some(r => r.demoni.includes('bgpd'));
  return {membri: membri.map(d => d.nome), routers: routers.map(r => r.nome), igp, asn: gruppi.length === 1 ? String(gruppi[0]) : '', gateway: gw, bgp};
}

// dati per calcola_aggiungi_dispositivo, nella forma che il wizard (e l'editor) danno al motore
export function datiDispositivo(tipo, v) {
  const nome = String(v.nome || '').trim(), lan = String(v.lan || '').trim(), ip = String(v.ip || '').trim();
  const gateway = String(v.gateway || '').trim();
  if (tipo === 'router') {
    const protocolli = ['bgp', 'ospf', 'rip'].filter(p => v[p]);
    const r = {name: nome, protocols: protocolli, asn: v.bgp ? String(v.asn || '').trim() : '',
      interfaces: [{name: 'eth0', lan, ip}]};
    if (v.ospf) { r.ospf_area = String(v.area || '0.0.0.0').trim(); r.ospf_area_stub = !!v.stub; }
    return r;
  }
  if (tipo === 'host') return {name: nome, interfaces: [{name: 'eth0', lan, ip}], gateway};
  const base = {name: nome, ip, gateway, lan};
  if (tipo === 'www') return base;
  return Object.assign(base, {dns: true, root_type: v.root_type ?? (nome === 'root' ? 'master' : 'hint'), delegations: []});
}

// rinumera una LAN: [dispositivo, interfaccia, ip] dai campi del modulo ('ip:<disp>:<dev>')
export function assegnati(valori, subnet) {
  const out = [];
  for (const [k, x] of Object.entries(valori)) {
    if (!k.startsWith('ip:') || !String(x).trim()) continue;
    const [, disp, dev] = k.split(':');
    out.push([disp, dev, completaIp(String(x), subnet)]);
  }
  return out;
}

// stessa parte host nella nuova rete (come proposta_rinumera_lan del motore)
export function stessaParteHost(ip, vecchia, nuova) {
  const a = leggiRete(vecchia), b = leggiRete(nuova), x = ipInt(String(ip).split('/')[0]);
  if (!a || !b || x === null) return '';
  const h = x - a.base;
  return h >= 0 && h < 2 ** (32 - b.prefisso) ? `${intIp(b.base + h)}/${b.prefisso}` : '';
}

export function reteNormalizzata(s) {
  const r = leggiRete(s);
  return r ? testoRete(r) : '';
}

// posizioni per tutti i nodi partendo da quelle note (`base`): i nodi nuovi (dispositivo aggiunto,
// LAN nuova) vanno vicino ai loro vicini già disposti. null se ne mancano più della metà (meglio
// allora la disposizione automatica).
export function completaPosizioni(G, base) {
  const pos = {};
  for (const n of G.nodes) if (base && base[n.id]) pos[n.id] = {x: base[n.id].x, y: base[n.id].y};
  const mancano = G.nodes.filter(n => !pos[n.id]);
  if (!mancano.length) return pos;
  if (mancano.length * 2 > G.nodes.length) return null;
  const vicini = id => G.links.filter(l => l.a === id || l.b === id).map(l => (l.a === id ? l.b : l.a));
  const xs = Object.values(pos).map(p => p.x);
  let destra = xs.length ? Math.max(...xs) + 120 : 0, k = 0;
  for (let giro = 0; giro < 3 && mancano.some(n => !pos[n.id]); giro++) {
    for (const n of mancano) {
      if (pos[n.id]) continue;
      const noti = vicini(n.id).filter(v => pos[v]);
      if (!noti.length) { if (giro < 2) continue; pos[n.id] = {x: destra, y: 80 * k++}; continue; }
      const cx = noti.reduce((a, v) => a + pos[v].x, 0) / noti.length, cy = noti.reduce((a, v) => a + pos[v].y, 0) / noti.length;
      const ang = (Object.keys(pos).length * 2.399) % (2 * Math.PI);     // angolo aureo: nuovi nodi non sovrapposti
      // con un solo vicino: a 90 px da lui; con più vicini: nel mezzo (un dispositivo un po' sotto, per non
      // stare sulla linea tra i vicini; una LAN proprio nel mezzo)
      const r = noti.length > 1 ? 0 : 90, sotto = noti.length > 1 && n.id.startsWith('d:') ? 40 : 0;
      pos[n.id] = {x: cx + r * Math.cos(ang), y: cy + r * Math.sin(ang) + sotto};
    }
  }
  return pos;
}

// ---------- BGP (fase 5.3) ----------
// reti scritte nel modulo ("20.20.0.0/16, 30.0.0.0/8"): normalizzate; Error alla prima sbagliata
export function listaReti(testo) {
  const out = [];
  for (const x of String(testo || '').split(/[\s,;]+/).filter(Boolean)) {
    const r = reteNormalizzata(x);
    if (!r) throw new Error(`Rete non valida: '${x}' (es. 20.20.0.0/16).`);
    if (!out.includes(r)) out.push(r);
  }
  return out;
}

// prossima loopback della serie già usata nel lab (dopo 1.1.1.1/32: 1.1.1.2/32); '' se non ce ne sono
export function prossimaLoopback(lab) {
  const lb = lab.dispositivi.flatMap(d => d.loopback || []).map(x => ipInt(String(x).split('/')[0])).filter(x => x !== null);
  if (!lb.length) return '';
  const usati = ipUsati(lab);
  let n = Math.max(...lb) + 1;
  while (usati.has(intIp(n)) && n % 256 < 255) n++;
  return n % 256 === 0 || n % 256 === 255 ? '' : intIp(n) + '/32';
}

// subnet delle LAN dove il router ha un vicino router di un altro AS (per la route-map eBGP)
export function retiEbgp(lab, router) {
  const r = lab.dispositivi.find(d => d.nome === router);
  if (!r) return [];
  const mio = r.gruppo;
  return r.interfacce.filter(it => it.ip && lab.dispositivi.some(o => o.nome !== router && o.tipo === 'router'
    && o.gruppo && o.gruppo !== mio && o.interfacce.some(x => x.lan === it.lan))).map(it => subnetDellaLan(lab, it.lan) || reteNormalizzata(it.ip));
}

// default-originate: neighbor spuntati nei campi 'n:<ip>', "solo la default" e reti in più
export function parametriDefaultBgp(valori, neighbors) {
  const scelti = Object.keys(neighbors).filter(ip => valori['n:' + ip]);
  if (!scelti.length) throw new Error('Scegli almeno un neighbor.');
  const solo = !!valori.solo;
  return {scelti, solo, extra: solo ? listaReti(valori.extra) : []};
}

// default route in OSPF o RIP, come le domande del terminale (Opzioni 12)
export function parametriDefaultIgp(proto, valori) {
  if (proto === 'ospf') return {modo: '1', reti: ['0.0.0.0/0'], ha_default: !!valori.ha_default};
  const modo = valori.modo === '2' ? '2' : '1';
  const reti = modo === '1' ? (listaReti(valori.rete || '0.0.0.0/0').length ? listaReti(valori.rete || '0.0.0.0/0') : ['0.0.0.0/0']) : ['0.0.0.0/0'];
  return {modo, reti, ha_default: false};
}

// ---------- policy BGP (fase 5.5, Opzioni 2 del terminale) ----------
// reti spuntate nei campi 'r:<rete>' più quelle scritte in 'altre', senza doppioni
export function retiScelte(valori) {
  const out = Object.keys(valori).filter(k => k.startsWith('r:') && valori[k]).map(k => k.slice(2));
  for (const r of listaReti(valori.altre)) if (!out.includes(r)) out.push(r);
  return out;
}

// parametri di calcola_policy dai valori del modulo; tipo: prefix_list, local_pref, med, access_list
export function parametriPolicy(tipo, valori) {
  const valore = v => {
    const n = Number(String(v ?? '').trim());
    if (!Number.isInteger(n) || n < 0 || n > 4294967295) throw new Error('Serve un numero intero (es. 150).');
    return n;
  };
  if (tipo === 'med') return {tipo, valore: valore(valori.valore)};
  const reti = retiScelte(valori);
  if (tipo === 'local_pref') return {tipo, valore: valore(valori.valore), reti};
  if (!reti.length) throw new Error('Scegli o scrivi almeno una rete.');
  if (tipo === 'access_list') return {tipo, reti};
  if (!['in', 'out'].includes(valori.direzione)) throw new Error("Direzione: 'in' oppure 'out'.");
  return {tipo, direzione: valori.direzione, reti};
}

// Customer-Provider-Peer: verso un cliente si annuncia tutto, verso provider e peer solo le reti scelte
export function parametriCpp(relazione, valori) {
  if (!['provider', 'customer', 'peer'].includes(relazione)) throw new Error('Scelta non valida.');
  return {relazione, reti_out: relazione === 'customer' ? [] : retiScelte(valori)};
}

export const RELAZIONE_INVERSA = {provider: 'customer', customer: 'provider', peer: 'peer'};
