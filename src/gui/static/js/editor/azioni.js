// Azioni dell'editor sulla bozza: ognuna riceve una bozza e ne restituisce una nuova (la vecchia
// non cambia), così annulla/ripeti tiene semplicemente le copie. Solo dati: provate con Node.
import { completaIp, converti, leggiRete, nuovoId, rinumera, TIPI } from './bozza.js';

const copia = x => JSON.parse(JSON.stringify(x));
export const GRIGLIA = 20;
export const aGriglia = (v, griglia) => (griglia ? Math.round(v / GRIGLIA) * GRIGLIA : Math.round(v));

// nome libero per un dispositivo nuovo: r<n>, host<n>, www<n>, dns<n> (il primo numero libero)
const BASE_NOME = {router: 'r', host: 'host', www: 'www', dns: 'dns'};
export function nomeLibero(bozza, tipo, extra = []) {
  const usati = new Set(Object.values(converti(bozza).nomi).concat(extra));
  let k = 1;
  while (usati.has(BASE_NOME[tipo] + k)) k++;
  return BASE_NOME[tipo] + k;
}

// Il nome si dà adesso e poi non cambia più da solo (né entrando in un AS né eliminando altri).
export function aggiungiDispositivo(bozza, tipo, x, y, griglia = false) {
  if (!TIPI.includes(tipo)) throw new Error('tipo non previsto: ' + tipo);
  const b = copia(bozza), id = nuovoId(b, 'd');
  const d = {id, tipo, nome: nomeLibero(b, tipo), x: aGriglia(x, griglia), y: aGriglia(y, griglia)};
  // un DNS nuovo parte come nel wizard: hint per '.', niente ricorsione, DNSSEC attiva, nessuna zona
  if (tipo === 'dns') d.dns = {gateway: '', forwarders: null, root_type: 'hint', allow_recursion: null, dnssec_validation: false, delegations: [], zone: []};
  b.dispositivi.push(d);
  return {bozza: b, id};
}

export function aggiungiLan(bozza, x, y, griglia = false) {
  const b = copia(bozza), id = nuovoId(b, 'l');
  b.lan.push({id, nome: '', subnet: '', punto: false, x: aGriglia(x, griglia), y: aGriglia(y, griglia)});
  return {bozza: b, id};
}

const membri = (b, idLan) => b.collegamenti.filter(c => c.lan === idLan);

// Collega il dispositivo `da` a `verso`:
// - un altro dispositivo: link diretto (LAN punto-punto nuova);
// - un nodo LAN: il dispositivo entra nella LAN;
// - un link diretto (LAN punto-punto): diventa un nodo LAN nel suo punto di mezzo, con la stessa
//   subnet e lettera, e il dispositivo ci entra.
// Restituisce {bozza, id (della LAN), messaggio}; se non c'è niente da fare la bozza resta uguale.
export function collega(bozza, da, verso) {
  const b = copia(bozza);
  const d = b.dispositivi.find(x => x.id === da);
  if (!d) return {bozza: b, id: null, messaggio: 'Si collega partendo da un dispositivo.'};
  const altro = b.dispositivi.find(x => x.id === verso);
  if (altro) {
    if (altro.id === d.id) return {bozza: b, id: null, messaggio: 'Scegli un altro dispositivo.'};
    const gia = b.lan.find(l => l.punto && membri(b, l.id).length === 2
      && membri(b, l.id).every(c => c.dispositivo === d.id || c.dispositivo === altro.id)
      && new Set(membri(b, l.id).map(c => c.dispositivo)).size === 2);
    if (gia) return {bozza: b, id: gia.id, messaggio: 'Sono già collegati da un link diretto.'};
    const id = nuovoId(b, 'l');
    b.lan.push({id, nome: '', subnet: '', punto: true, x: (d.x + altro.x) / 2, y: (d.y + altro.y) / 2});
    b.collegamenti.push({id: nuovoId(b, 'c'), dispositivo: d.id, lan: id, ip: ''});
    b.collegamenti.push({id: nuovoId(b, 'c'), dispositivo: altro.id, lan: id, ip: ''});
    return {bozza: b, id, messaggio: ''};
  }
  const l = b.lan.find(x => x.id === verso);
  if (!l) return {bozza: b, id: null, messaggio: 'Collega a un dispositivo, a un nodo LAN o a un link.'};
  if (membri(b, l.id).some(c => c.dispositivo === d.id)) return {bozza: b, id: l.id, messaggio: 'È già in questa LAN.'};
  if (l.punto) {
    const ds = membri(b, l.id).map(c => b.dispositivi.find(x => x.id === c.dispositivo)).filter(Boolean);
    if (ds.length === 2) { l.x = (ds[0].x + ds[1].x) / 2; l.y = (ds[0].y + ds[1].y) / 2; }
    l.punto = false;
  }
  b.collegamenti.push({id: nuovoId(b, 'c'), dispositivo: d.id, lan: l.id, ip: ''});
  return {bozza: b, id: l.id, messaggio: ''};
}

// ----------------------------------------------------------------------------- zone

export const ZONE = ['as', 'rip', 'ospf'];
export const LATO_MIN = 40;          // lato minimo di una zona
export const ZONA_CLIC = {w: 240, h: 160};   // zona creata con un clic senza trascinare

// Zona nuova dal rettangolo trascinato (r = {x, y, w, h}). Valore: vuoto per l'AS (si scrive),
// '0.0.0.0' per la prima area OSPF del disegno, vuoto per le altre.
export function aggiungiZona(bozza, tipo, r, griglia = false) {
  if (!ZONE.includes(tipo)) throw new Error('zona non prevista: ' + tipo);
  const b = copia(bozza), id = nuovoId(b, 'z');
  let {x, y, w, h} = r;
  if (w < LATO_MIN && h < LATO_MIN) { x -= ZONA_CLIC.w / 2; y -= ZONA_CLIC.h / 2; w = ZONA_CLIC.w; h = ZONA_CLIC.h; }
  const x0 = aGriglia(x, griglia), y0 = aGriglia(y, griglia);
  const z = {id, tipo, valore: '', x: x0, y: y0, w: Math.max(LATO_MIN, aGriglia(x + w, griglia) - x0), h: Math.max(LATO_MIN, aGriglia(y + h, griglia) - y0)};
  if (tipo === 'ospf') { z.stub = false; if (!b.zone.some(q => q.tipo === 'ospf')) z.valore = '0.0.0.0'; }
  b.zone.push(z);
  return {bozza: b, id};
}

// Ridimensiona una zona trascinando un angolo ('nw', 'ne', 'sw', 'se') fino al punto p; l'angolo
// opposto resta fermo. `partenza` = il rettangolo all'inizio del trascinamento.
export function ridimensionaZona(bozza, id, angolo, p, partenza, griglia = false) {
  const b = copia(bozza), z = b.zone.find(q => q.id === id);
  if (!z) return b;
  const r = partenza;
  const fermoX = angolo.includes('w') ? r.x + r.w : r.x, fermoY = angolo.includes('n') ? r.y + r.h : r.y;
  let px = aGriglia(p.x, griglia), py = aGriglia(p.y, griglia);
  if (angolo.includes('w')) px = Math.min(px, fermoX - LATO_MIN); else px = Math.max(px, fermoX + LATO_MIN);
  if (angolo.includes('n')) py = Math.min(py, fermoY - LATO_MIN); else py = Math.max(py, fermoY + LATO_MIN);
  z.x = Math.min(px, fermoX); z.y = Math.min(py, fermoY);
  z.w = Math.abs(px - fermoX); z.h = Math.abs(py - fermoY);
  return b;
}

// Elimina dispositivi, LAN, collegamenti e zone. Un dispositivo porta via i suoi collegamenti, una
// LAN anche; un link diretto rimasto con meno di due estremi sparisce; il resolver eliminato si toglie.
export function elimina(bozza, ids) {
  const b = copia(bozza), via = new Set(ids);
  b.dispositivi = b.dispositivi.filter(d => !via.has(d.id));
  const restano = new Set(b.dispositivi.map(d => d.id));
  b.lan = b.lan.filter(l => !via.has(l.id));
  b.collegamenti = b.collegamenti.filter(c => !via.has(c.id) && restano.has(c.dispositivo) && b.lan.some(l => l.id === c.lan));
  const monchi = new Set(b.lan.filter(l => l.punto && membri(b, l.id).length < 2).map(l => l.id));
  b.lan = b.lan.filter(l => !monchi.has(l.id));
  b.collegamenti = b.collegamenti.filter(c => !monchi.has(c.lan));
  b.zone = b.zone.filter(z => !via.has(z.id));
  if (b.resolver && !restano.has(b.resolver)) b.resolver = null;
  return b;
}

// Sposta dispositivi, nodi LAN e zone; con la griglia la posizione finale si allinea.
// `partenza` = {id: {x, y}} le posizioni all'inizio del trascinamento.
export function sposta(bozza, partenza, dx, dy, griglia = false) {
  const b = copia(bozza);
  for (const x of [...b.dispositivi, ...b.lan.filter(l => !l.punto), ...b.zone]) {
    const p = partenza[x.id];
    if (!p) continue;
    x.x = aGriglia(p.x + dx, griglia);
    x.y = aGriglia(p.y + dy, griglia);
  }
  return b;
}

export function posizioni(bozza, ids) {
  const out = {}, voluti = new Set(ids);
  for (const x of [...bozza.dispositivi, ...bozza.lan.filter(l => !l.punto), ...bozza.zone])
    if (voluti.has(x.id)) out[x.id] = {x: x.x, y: x.y};
  return out;
}

// Cambia un valore scritto nel pannello. campo: 'nome' (dispositivo o LAN), 'subnet' (LAN: i
// membri vengono rinumerati), 'ip' (collegamento), 'valore' e 'stub' (zona), 'nome_lab',
// 'blocco_subnet'.
export function imposta(bozza, id, campo, valore) {
  const v = String(valore ?? '').trim();
  if (campo === 'nome_lab') return Object.assign(copia(bozza), {nome: v});
  if (campo === 'blocco_subnet') return Object.assign(copia(bozza), {blocco_subnet: v});
  if (campo === 'subnet') return v && leggiRete(v) ? rinumera(bozza, id, v) : (() => { const b = copia(bozza); const l = b.lan.find(x => x.id === id); if (l) l.subnet = v; return b; })();
  const b = copia(bozza);
  const el = b.dispositivi.find(x => x.id === id) || b.lan.find(x => x.id === id) || b.collegamenti.find(x => x.id === id)
    || b.zone.find(x => x.id === id);
  if (!el) return b;
  if (campo === 'valore') { el.valore = v; return b; }
  if (campo === 'bgpzona') { el.bgp = v === 'tutti' ? 'tutti' : 'confine'; return b; }
  if (campo === 'stub') { el.stub = valore === true || valore === 'true'; return b; }
  if (campo === 'nome') el.nome = b.lan.includes(el) ? v.toUpperCase() : v;
  else if (campo === 'ip') el.ip = completaIp(v, converti(bozza).subnet[el.lan]);
  return b;
}

// Sposta un collegamento prima (-1) o dopo (+1) tra quelli dello stesso dispositivo: cambia
// l'ordine delle interfacce eth0, eth1, ...
export function spostaInterfaccia(bozza, idColl, verso) {
  const b = copia(bozza), i = b.collegamenti.findIndex(c => c.id === idColl);
  if (i < 0) return b;
  const dev = b.collegamenti[i].dispositivo;
  const pos = b.collegamenti.map((c, k) => (c.dispositivo === dev ? k : -1)).filter(k => k >= 0);
  const j = pos[pos.indexOf(i) + verso];
  if (j === undefined) return b;
  [b.collegamenti[i], b.collegamenti[j]] = [b.collegamenti[j], b.collegamenti[i]];
  return b;
}

// ----------------------------------------------------------------------------- proprietà (pannello completo, 4.4)

const sezione = (d, chiave) => (d[chiave] = d[chiave] || {});

// Proprietà di un dispositivo scritte nel pannello. chiave = la parte prima dei ':' nel campo del
// pannello, percorso = gli indici che seguono (per righe di elenchi):
//   redistribuisci (router, bool), igp (router, testo), gateway (host, www, dns), ospf (router: 'no' = senza OSPF
//   anche con una LAN in un'area), nameserver (host, www, dns: resolver solo suo),
//   statica [k, rete|via|dev], root_type, ricorsione (bool), ricorsione_reti, dnssec (bool),
//   zona [k] (nome), record [k, r, nome|tipo|valore|extra], delega [k, zone|ns|ip]
export function impostaProprieta(bozza, id, chiave, valore, percorso = []) {
  const b = copia(bozza);
  if (chiave === 'resolver') { b.resolver = valore || null; return b; }
  if (chiave === 'blocco') { b.blocco_subnet = String(valore || '').trim(); return b; }
  const d = b.dispositivi.find(x => x.id === id);
  if (!d) return b;
  const v = typeof valore === 'string' ? valore.trim() : valore;
  const [k, r, campo] = percorso.length === 3 ? percorso : [percorso[0], undefined, percorso[1]];
  if (chiave === 'redistribuisci') sezione(d, 'router').redistribuisci_bgp = !!valore;
  else if (chiave === 'bgp') sezione(d, 'router').bgp = ['si', 'no'].includes(v) ? v : 'auto';
  else if (chiave === 'igp') sezione(d, 'router').igp_networks = v;
  else if (chiave === 'gateway') sezione(d, d.tipo).gateway = v;
  else if (chiave === 'ospf') { const r = sezione(d, 'router'); if (v === 'no') r.ospf = 'no'; else delete r.ospf; }
  else if (chiave === 'nameserver') sezione(d, d.tipo).nameserver = v;
  else if (chiave === 'statica') { const s = (sezione(d, 'router').statiche || [])[k]; if (s) s[campo] = v; }
  else if (chiave === 'root_type') sezione(d, 'dns').root_type = v || null;
  else if (chiave === 'ricorsione') { const c = sezione(d, 'dns'); c.allow_recursion = valore ? (c.allow_recursion || 'any') : null; }
  else if (chiave === 'ricorsione_reti') { const c = sezione(d, 'dns'); if (c.allow_recursion) c.allow_recursion = v || 'any'; }
  else if (chiave === 'dnssec') sezione(d, 'dns').dnssec_validation = !!valore;
  else if (chiave === 'zona') { const z = (sezione(d, 'dns').zone || [])[k]; if (z) z.nome = v.replace(/\.$/, ''); }
  else if (chiave === 'record') { const z = (sezione(d, 'dns').zone || [])[k]; const x = z && z.record[r]; if (x) x[campo] = v; }
  else if (chiave === 'delega') { const x = (sezione(d, 'dns').delegations || [])[k]; if (x) x[campo] = v; }
  return b;
}

// Aggiunge o toglie una riga: elenco = 'statica' | 'zona' | 'record' (indice della zona) | 'delega'.
export function modificaElenco(bozza, id, elenco, azione, indici = []) {
  const b = copia(bozza), d = b.dispositivi.find(x => x.id === id);
  if (!d) return b;
  const righe = {
    statica: () => (sezione(d, 'router').statiche = sezione(d, 'router').statiche || []),
    zona: () => (sezione(d, 'dns').zone = sezione(d, 'dns').zone || []),
    record: () => ((sezione(d, 'dns').zone || [])[indici[0]] || {record: []}).record,
    delega: () => (sezione(d, 'dns').delegations = sezione(d, 'dns').delegations || []),
  }[elenco];
  if (!righe) return b;
  const l = righe();
  const nuova = {statica: {rete: '', via: ''}, zona: {nome: '', record: []}, record: {nome: '', tipo: 'A', valore: '', extra: ''}, delega: {zone: '', ns: '', ip: ''}}[elenco];
  if (azione === 'aggiungi') l.push(nuova);
  else l.splice(indici[indici.length - 1], 1);
  return b;
}

// ----------------------------------------------------------------------------- duplica (Ctrl+D)

// Duplica i dispositivi, i nodi LAN e le zone selezionati e i collegamenti tra loro (anche i link
// diretti con entrambi gli estremi selezionati), spostati di 40 px. Nomi, IP e subnet ripartono
// vuoti (automatici) per non creare doppioni. Restituisce {bozza, ids} (gli elementi nuovi).
export const SCARTO_DUPLICA = 40;
export function duplica(bozza, ids) {
  const b = copia(bozza), sel = new Set(ids), nuovo = {}, ids2 = [];
  const id = p => { const x = nuovoId(b, p); b.dispositivi.push({id: x, segnaposto: true}); return x; };   // riserva l'id
  for (const d of bozza.dispositivi.filter(x => sel.has(x.id))) nuovo[d.id] = id('d');
  for (const l of bozza.lan.filter(x => sel.has(x.id) && !x.punto)) nuovo[l.id] = id('l');
  // link diretti con entrambi gli estremi duplicati
  for (const l of bozza.lan.filter(x => x.punto)) {
    const ms = bozza.collegamenti.filter(c => c.lan === l.id);
    if (ms.length === 2 && ms.every(c => nuovo[c.dispositivo])) nuovo[l.id] = id('l');
  }
  for (const z of bozza.zone.filter(x => sel.has(x.id))) nuovo[z.id] = id('z');
  b.dispositivi = b.dispositivi.filter(x => !x.segnaposto);
  const nomiNuovi = [];
  for (const d of bozza.dispositivi.filter(x => nuovo[x.id])) {
    const nome = nomeLibero(bozza, d.tipo, nomiNuovi);
    nomiNuovi.push(nome);
    b.dispositivi.push(Object.assign(copia(d), {id: nuovo[d.id], nome, x: d.x + SCARTO_DUPLICA, y: d.y + SCARTO_DUPLICA}));
    ids2.push(nuovo[d.id]);
  }
  for (const l of bozza.lan.filter(x => nuovo[x.id])) {
    b.lan.push(Object.assign(copia(l), {id: nuovo[l.id], nome: '', subnet: '', x: (l.x ?? 0) + SCARTO_DUPLICA, y: (l.y ?? 0) + SCARTO_DUPLICA}));
    if (!l.punto) ids2.push(nuovo[l.id]);
  }
  for (const c of bozza.collegamenti.filter(x => nuovo[x.dispositivo] && nuovo[x.lan]))
    b.collegamenti.push({id: nuovoId(b, 'c'), dispositivo: nuovo[c.dispositivo], lan: nuovo[c.lan], ip: ''});
  for (const z of bozza.zone.filter(x => nuovo[x.id])) {
    b.zone.push(Object.assign(copia(z), {id: nuovo[z.id], x: z.x + SCARTO_DUPLICA, y: z.y + SCARTO_DUPLICA}));
    ids2.push(nuovo[z.id]);
  }
  return {bozza: b, ids: ids2};
}

// ----------------------------------------------------------------------------- interfacce e nomi per AS

// Il collegamento diventa l'interfaccia eth<k> del suo dispositivo: si scambia con quello che
// aveva quel numero.
export function impostaInterfaccia(bozza, idColl, k) {
  const b = copia(bozza), i = b.collegamenti.findIndex(c => c.id === idColl);
  if (i < 0) return b;
  const pos = b.collegamenti.map((c, n) => (c.dispositivo === b.collegamenti[i].dispositivo ? n : -1)).filter(n => n >= 0);
  const j = pos[Number(k)];
  if (j === undefined || j === i) return b;
  [b.collegamenti[i], b.collegamenti[j]] = [b.collegamenti[j], b.collegamenti[i]];
  return b;
}

// "Rinomina i router come as20r1, as20r2...": i router del riquadro AS, nell'ordine in cui sono stati
// messi, prendono i nomi as<AS>r<n> liberi. Restituisce {bozza, messaggio}.
export function rinominaPerAs(bozza, idZona) {
  const b = copia(bozza), z = b.zone.find(x => x.id === idZona), conv = converti(b);
  const asn = z ? String(z.valore ?? '').trim() : '';
  if (!z || z.tipo !== 'as' || !/^\d+$/.test(asn)) return {bozza: b, messaggio: 'Scrivi prima il numero AS del riquadro.'};
  const dentro = new Set(conv.membri[z.id] || []);
  const routers = b.dispositivi.filter(d => dentro.has(d.id));
  if (!routers.length) return {bozza: b, messaggio: 'Il riquadro non contiene router.'};
  const usati = new Set(b.dispositivi.filter(d => !dentro.has(d.id)).map(d => conv.nomi[d.id]));
  let k = 1;
  for (const d of routers) {
    while (usati.has(`as${asn}r${k}`)) k++;
    d.nome = `as${asn}r${k}`;
    usati.add(d.nome);
  }
  return {bozza: b, messaggio: `${routers.length} router rinominati.`};
}
