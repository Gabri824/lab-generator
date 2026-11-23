// Bozza dell'editor grafico (fase 4) e sua traduzione nel modello del wizard.
//
// Solo dati, nessun elemento della pagina: la usano l'editor nel browser e i test con Node.
// Le regole che decidono i file (completa_lab, valida_lab, genera_lab) restano nel motore Python:
// qui si raccolgono i dati del disegno, come fanno le domande del wizard nel terminale.
//
// Bozza (versione 1):
//   {versione, nome, resolver: id di un DNS | null, blocco_subnet: '10.255.0.0/16' | '',
//    dispositivi: [{id, tipo: 'router'|'host'|'www'|'dns', nome: '' (= automatico), x, y,
//                   router: {redistribuisci_bgp: bool, statiche: [{rete, via, dev?}], igp_networks: '' (= proposte),
//                            bgp: 'auto' | 'si' | 'no', ospf?: 'no' (senza OSPF anche se una sua LAN è in un'area,
//                            es. un router RIP sul confine con OSPF)},
//                   host: {gateway: '', nameserver: ''}, www: {gateway: '', nameserver: ''},
//                   (nameserver: IP del resolver solo di questo dispositivo, separati da virgola; vuoto = quello del lab)
//                   dns: {gateway, root_type: 'master'|'hint'|null, delegations: [{zone, ns, ip}],
//                         allow_recursion: null|'any'|'reti', dnssec_validation: bool (true = validazione disattivata),
//                         zone: [{nome, record: [{nome, tipo: 'A'|'NS'|'CNAME'|'DELEGATION', valore, extra}]}]}}],
//                   (record: A valore = IP; NS valore = nameserver, extra = glue; CNAME valore = destinazione;
//                    DELEGATION valore = nameserver, extra = IP)
//    lan: [{id, nome: '' (= lettera automatica), subnet: '' , punto: bool, x, y}],
//    collegamenti: [{id, dispositivo, lan, ip: '' (= automatico)}],
//    zone: [{id, tipo: 'as'|'rip'|'ospf', valore: numero AS o area, stub: bool, bgp: 'confine'|'tutti' (AS), x, y, w, h}]}
//
// - punto = link diretto tra due dispositivi: la LAN non si disegna, la sua posizione è il punto
//   di mezzo tra i due;
// - l'ordine dei collegamenti di un dispositivo dà eth0, eth1, ...;
// - le zone contano per posizione: il centro di un router nel riquadro AS o nella zona RIP, il
//   nodo della LAN (o il punto di mezzo del link) nella zona dell'area OSPF;
// - il riquadro AS dà l'AS ai suoi router; BGP va solo ai router di confine (collegati a un router
//   fuori dal loro AS), a tutti se il riquadro ha bgp 'tutti', con l'eccezione per router (si/no);
// - i nomi li dà l'editor quando si mette il dispositivo (r1, host1, ...) e non cambiano più da
//   soli; un nome vuoto diventa automatico (r<n>, host<n>, www<n>, root/dns<n>).

export const VERSIONE = 1;
export const TIPI = ['router', 'host', 'www', 'dns'];
const ORDINE_PROTOCOLLI = ['bgp', 'ospf', 'rip', 'statico'];

// ----------------------------------------------------------------------------- indirizzi IPv4

export function ipInt(s) {
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(String(s || '').trim());
  if (!m) return null;
  const o = m.slice(1).map(Number);
  if (o.some(x => x > 255)) return null;
  return ((o[0] << 24) >>> 0) + (o[1] << 16) + (o[2] << 8) + o[3];
}
export function intIp(n) {
  return [n >>> 24, (n >>> 16) & 255, (n >>> 8) & 255, n & 255].join('.');
}
function maschera(p) { return p === 0 ? 0 : ((0xffffffff << (32 - p)) >>> 0); }

// '10.0.0.1/24' -> {base, prefisso, ip}; null se non valido
export function leggiRete(s) {
  const m = /^\s*([\d.]+)\/(\d{1,2})\s*$/.exec(String(s || ''));
  if (!m) return null;
  const ip = ipInt(m[1]), p = Number(m[2]);
  if (ip === null || p > 32) return null;
  return {base: (ip & maschera(p)) >>> 0, prefisso: p, ip};
}
export function testoRete(r) { return `${intIp(r.base)}/${r.prefisso}`; }
function dimensione(r) { return 2 ** (32 - r.prefisso); }
function dentro(r, n) { return ((n & maschera(r.prefisso)) >>> 0) === r.base; }
// indirizzi assegnabili: niente indirizzo di rete e broadcast, tranne /31 e /32
function utilizzabile(r, n) {
  if (!dentro(r, n)) return false;
  if (r.prefisso >= 31) return true;
  return n !== r.base && n !== r.base + dimensione(r) - 1;
}
function sovrapposte(a, b) {
  return dentro(a, b.base) || dentro(b, a.base);
}

// ----------------------------------------------------------------------------- aree OSPF e zone

// '0' e '0.0.0.0' sono la stessa area
export function chiaveArea(a) {
  const s = String(a ?? '').trim();
  return /^\d+$/.test(s) ? intIp(Number(s) >>> 0) : s;
}
const backbone = a => chiaveArea(a) === '0.0.0.0';
const areaValida = a => { const s = String(a ?? '').trim(); return /^\d+$/.test(s) ? Number(s) <= 4294967295 : ipInt(s) !== null; };

export function contiene(z, p) {
  return p.x >= z.x && p.x <= z.x + z.w && p.y >= z.y && p.y <= z.y + z.h;
}

// ----------------------------------------------------------------------------- bozza

export function nuovaBozza(nome = '') {
  return {versione: VERSIONE, nome, resolver: null, blocco_subnet: '', dispositivi: [], lan: [], collegamenti: [], zone: []};
}

export function nuovoId(bozza, prefisso) {
  const usati = new Set([...bozza.dispositivi, ...bozza.lan, ...bozza.collegamenti, ...bozza.zone].map(x => x.id));
  let k = 1;
  while (usati.has(prefisso + k)) k++;
  return prefisso + k;
}

const copia = x => JSON.parse(JSON.stringify(x));

// lettere automatiche delle LAN: A..Z, poi AA, AB, ...
function lettera(k) {
  let s = '';
  for (k += 1; k > 0; k = Math.floor((k - 1) / 26)) s = String.fromCharCode(65 + (k - 1) % 26) + s;
  return s;
}

// ----------------------------------------------------------------------------- conversione

// Traduce la bozza nel modello del wizard. Restituisce:
//   modello: {routers, hosts, wwws, resolver} (hosts = host e poi DNS, come il wizard)
//   nomi: {id dispositivo: nome}, nomiLan: {id LAN: nome}, subnet: {id LAN: 'rete/prefisso'}
//   interfacce: {id dispositivo: [id collegamento, ...]} (eth0, eth1, ...), ip: {id collegamento: 'ip/prefisso'}
//   zone: {id router: {as, rip}, id LAN: {valore, stub, zona} | null}, membri: {id zona: [id router o LAN]},
//   abr: [id dei router di confine]
//   problemi: [{id, campo, gravita: 'errore'|'avviso', messaggio}] che esistono solo nel disegno
export function converti(bozza) {
  const b = bozza, problemi = [];
  const segnala = (id, campo, gravita, messaggio) => problemi.push({id, campo, gravita, messaggio});
  const disp = new Map(b.dispositivi.map(d => [d.id, d]));
  const lans = new Map(b.lan.map(l => [l.id, l]));

  const coll = [];
  for (const c of b.collegamenti) {
    if (disp.has(c.dispositivo) && lans.has(c.lan)) coll.push(c);
    else segnala(c.id, 'collegamento', 'errore', 'Collegamento a un elemento che non c\'è più.');
  }
  const perDisp = new Map(b.dispositivi.map(d => [d.id, []]));
  const perLan = new Map(b.lan.map(l => [l.id, []]));
  for (const c of coll) { perDisp.get(c.dispositivo).push(c); perLan.get(c.lan).push(c); }

  // nomi dei dispositivi: prima quelli scritti, poi gli automatici
  const nomi = {}, usati = new Set();
  for (const d of b.dispositivi) {
    const n = String(d.nome || '').trim();
    if (!n) continue;
    if (!/^[a-z0-9_]+$/.test(n)) segnala(d.id, 'nome', 'errore', `'${n}' non è valido per Kathará (solo minuscole, cifre e _).`);
    if (usati.has(n)) segnala(d.id, 'nome', 'errore', `Nome '${n}' già usato da un altro dispositivo.`);
    usati.add(n); nomi[d.id] = n;
  }

  // zone per posizione
  const zone = {};
  const zoneDi = (tipo, p) => b.zone.filter(z => z.tipo === tipo && contiene(z, p));
  const posLan = l => {
    if (!l.punto) return {x: l.x, y: l.y};
    const ds = perLan.get(l.id).map(c => disp.get(c.dispositivo));
    if (ds.length !== 2) return {x: l.x ?? 0, y: l.y ?? 0};
    return {x: (ds[0].x + ds[1].x) / 2, y: (ds[0].y + ds[1].y) / 2};
  };
  // ogni zona controllata una volta: valore e chi ci sta dentro
  const membri = {}, zonaValida = {};
  for (const z of b.zone) {
    const v = String(z.valore ?? '').trim();
    membri[z.id] = [];
    if (z.tipo === 'as') {
      zonaValida[z.id] = /^\d+$/.test(v) && Number(v) >= 1 && Number(v) <= 4294967295;
      if (!v) segnala(z.id, 'valore', 'errore', 'Scrivi il numero AS del riquadro.');
      else if (!zonaValida[z.id]) segnala(z.id, 'valore', 'errore', `Numero AS non valido: '${v}' (solo cifre, es. 100).`);
    } else if (z.tipo === 'ospf') {
      zonaValida[z.id] = areaValida(v) && v !== '';
      if (!v) segnala(z.id, 'valore', 'errore', "Scrivi l'area OSPF (es. 0.0.0.0).");
      else if (!zonaValida[z.id]) segnala(z.id, 'valore', 'errore', `Area OSPF non valida: '${v}' (un numero o x.x.x.x).`);
    } else zonaValida[z.id] = true;
  }
  for (const d of b.dispositivi) {
    if (d.tipo !== 'router') continue;
    const as = zoneDi('as', d), rip = zoneDi('rip', d);
    as.concat(rip).forEach(z => membri[z.id].push(d.id));
    if (as.length > 1) segnala(d.id, 'zona', 'errore', `${nomi[d.id] || 'Il router'} sta in due riquadri AS: lascialo in uno solo.`);
    const asn = as.length && zonaValida[as[0].id] ? String(as[0].valore).trim() : '';
    zone[d.id] = {as: asn, rip: rip.length > 0, bgpTutti: !!(as.length && as[0].bgp === 'tutti')};
  }
  for (const l of b.lan) {
    const ar = zoneDi('ospf', posLan(l));
    ar.forEach(z => membri[z.id].push(l.id));
    if (ar.length > 1) segnala(l.id, 'zona', 'errore', `La LAN sta in due aree OSPF: lasciala in una sola.`);
    zone[l.id] = ar.length && zonaValida[ar[0].id] ? {valore: String(ar[0].valore).trim(), stub: !!ar[0].stub, zona: ar[0].id} : null;
  }
  for (const z of b.zone) if (!membri[z.id].length) segnala(z.id, 'membri', 'avviso', z.tipo === 'ospf' ? "L'area non contiene nessuna LAN." : 'Il riquadro non contiene nessun router.');

  // nomi automatici (per i nomi lasciati vuoti): r<n>, host<n>, www<n>, root/dns<n>
  const libero = base => { let k = 1; while (usati.has(base + k)) k++; usati.add(base + k); return base + k; };
  for (const d of b.dispositivi) {
    if (nomi[d.id]) continue;
    if (d.tipo === 'router') nomi[d.id] = libero('r');
    else if (d.tipo === 'dns' && (d.dns || {}).root_type === 'master' && !usati.has('root')) { usati.add('root'); nomi[d.id] = 'root'; }
    else nomi[d.id] = libero({host: 'host', www: 'www', dns: 'dns'}[d.tipo] || 'dispositivo');
  }

  // nomi delle LAN: quelli scritti (in maiuscolo, come il wizard), poi le lettere libere
  const nomiLan = {}, lettere = new Set();
  for (const l of b.lan) {
    const n = String(l.nome || '').trim().toUpperCase();
    if (!n) continue;
    if (!/^[A-Z0-9]+$/.test(n)) segnala(l.id, 'nome', 'errore', `Nome LAN '${n}' non valido: solo lettere e numeri.`);
    if (lettere.has(n)) segnala(l.id, 'nome', 'errore', `Nome LAN '${n}' già usato.`);
    lettere.add(n); nomiLan[l.id] = n;
  }
  let k = 0;
  for (const l of b.lan) {
    if (nomiLan[l.id]) continue;
    while (lettere.has(lettera(k))) k++;
    nomiLan[l.id] = lettera(k); lettere.add(lettera(k));
  }

  // subnet e indirizzi
  const subnet = {}, ip = {}, ipUsati = new Map();     // ip intero -> id collegamento
  const reti = {};
  for (const l of b.lan) {
    const membri = perLan.get(l.id);
    if (l.punto && membri.length !== 2) segnala(l.id, 'collegamenti', 'errore', `Un link diretto collega due dispositivi (ora ${membri.length}).`);
    let r = null;
    if (String(l.subnet || '').trim()) {
      r = leggiRete(l.subnet);
      if (!r) segnala(l.id, 'subnet', 'errore', `Subnet non valida: '${l.subnet}' (es. 10.0.0.0/30).`);
    } else {
      // senza subnet: quella del primo IP scritto a mano
      const c = membri.find(x => leggiRete(x.ip));
      if (c) r = leggiRete(c.ip);
    }
    if (r) { reti[l.id] = r; subnet[l.id] = testoRete(r); }
  }
  for (const [id, r] of Object.entries(reti))
    for (const [id2, r2] of Object.entries(reti))
      if (id < id2 && sovrapposte(r, r2)) segnala(id2, 'subnet', 'errore', `La subnet ${testoRete(r2)} si sovrappone a ${testoRete(r)} (LAN ${nomiLan[id]}).`);
  // prima gli IP scritti a mano
  for (const c of coll) {
    if (!String(c.ip || '').trim()) continue;
    const r = reti[c.lan], x = leggiRete(c.ip) || (ipInt(c.ip) !== null && r ? {ip: ipInt(c.ip), prefisso: r.prefisso} : null);
    if (!x) { segnala(c.id, 'ip', 'errore', `IP non valido: '${c.ip}' (es. 10.0.0.1/30).`); continue; }
    if (r && (!dentro(r, x.ip) || x.prefisso !== r.prefisso)) { segnala(c.id, 'ip', 'errore', `${c.ip} non è nella subnet ${testoRete(r)} della LAN ${nomiLan[c.lan]}.`); continue; }
    if (r && !utilizzabile(r, x.ip)) { segnala(c.id, 'ip', 'errore', `${intIp(x.ip)} è l'indirizzo di rete o di broadcast di ${testoRete(r)}.`); continue; }
    if (ipUsati.has(x.ip)) { segnala(c.id, 'ip', 'errore', `${intIp(x.ip)} è già usato da un altro collegamento.`); continue; }
    ipUsati.set(x.ip, c.id);
    ip[c.id] = `${intIp(x.ip)}/${x.prefisso}`;
  }
  // poi gli automatici: per ogni LAN, prima i router, poi gli altri, nell'ordine dei collegamenti
  for (const l of b.lan) {
    const senza = perLan.get(l.id).filter(c => !ip[c.id] && !String(c.ip || '').trim());
    if (!senza.length) continue;
    const r = reti[l.id];
    if (!r) { segnala(l.id, 'subnet', 'errore', `Manca la subnet della LAN ${nomiLan[l.id]}: scrivila o scrivi l'IP di un dispositivo.`); continue; }
    senza.sort((a, c) => (disp.get(a.dispositivo).tipo !== 'router') - (disp.get(c.dispositivo).tipo !== 'router'));
    let n = r.base;
    for (const c of senza) {
      while (n < r.base + dimensione(r) && (!utilizzabile(r, n) || ipUsati.has(n))) n++;
      if (n >= r.base + dimensione(r)) { segnala(l.id, 'subnet', 'errore', `La subnet ${testoRete(r)} non ha più indirizzi liberi.`); break; }
      ipUsati.set(n, c.id);
      ip[c.id] = `${intIp(n)}/${r.prefisso}`;
    }
  }

  // modello
  const interfacce = {}, abr = [], bgpConfine = {};
  const routers = {}, hosts = [], dnss = [], wwws = [];
  const ifaces = d => perDisp.get(d.id).map((c, i) => ({name: `eth${i}`, lan: nomiLan[c.lan], ip: ip[c.id] || ''}));
  // gateway proposto: l'IP del primo router sulla LAN della prima interfaccia
  const gatewayProposto = d => {
    const c0 = perDisp.get(d.id)[0];
    if (!c0) return '';
    const r = perLan.get(c0.lan).find(c => disp.get(c.dispositivo).tipo === 'router' && ip[c.id]);
    return r ? ip[r.id].split('/')[0] : '';
  };
  // resolver solo di questo dispositivo (come l'Opzione 5 del terminale): 'nameserver' del modello
  const conNameserver = (x, conf, idD) => {
    const ns = String((conf || {}).nameserver || '').split(/[\s,;]+/).filter(Boolean);
    const sbagliato = ns.find(v => ipInt(v) === null);
    if (sbagliato) segnala(idD, 'nameserver', 'errore', `Resolver non valido: '${sbagliato}' (un IP, es. 10.0.0.53).`);
    else if (ns.length) x.nameserver = ns;
    return x;
  };
  for (const d of b.dispositivi) {
    interfacce[d.id] = perDisp.get(d.id).map(c => c.id);
    const nome = nomi[d.id], its = ifaces(d);
    if (!its.length) segnala(d.id, 'collegamenti', 'avviso', `${nome} non è collegato a nessuna LAN.`);
    if (d.tipo === 'router') {
      const opz = d.router || {};
      const z = zone[d.id];
      const ospf = perDisp.get(d.id).map(c => ({c, area: zone[c.lan]})).filter(x => x.area);
      const statiche = (opz.statiche || []).filter(s => String(s.rete || '').trim() && String(s.via || '').trim());
      const p = new Set();
      // BGP: eccezione del router, altrimenti tutti i router dell'AS o solo quelli di confine
      const scelta = opz.bgp || 'auto';
      const confine = !!z.as && perDisp.get(d.id).some(c => perLan.get(c.lan).some(x => x.dispositivo !== d.id
        && disp.get(x.dispositivo).tipo === 'router' && (zone[x.dispositivo] || {}).as !== z.as));
      const bgp = scelta === 'si' || (scelta === 'auto' && !!z.as && (z.bgpTutti || confine));
      if (bgp && !z.as) segnala(d.id, 'bgp', 'errore', `${nome}: per BGP mettilo in un riquadro AS (serve il numero AS).`);
      if (bgp && z.as) p.add('bgp');
      bgpConfine[d.id] = confine;
      if (ospf.length && opz.ospf !== 'no') p.add('ospf');
      if (z.rip) p.add('rip');
      if (statiche.length) p.add('statico');
      const r = {protocols: ORDINE_PROTOCOLLI.filter(x => p.has(x)), asn: p.has('bgp') ? z.as : '', interfaces: its};
      if (statiche.length) r.static_routes = statiche.map(s => Object.assign({network: s.rete.trim(), via: s.via.trim()}, s.dev ? {dev: s.dev} : {}));
      if (ospf.length && opz.ospf !== 'no') {
        const aree = [];
        for (const x of ospf) if (!aree.some(a => chiaveArea(a.valore) === chiaveArea(x.area.valore))) aree.push(x.area);
        const principale = aree.find(a => backbone(a.valore)) || aree[0];
        r.ospf_area = principale.valore;
        r.ospf_area_stub = principale.stub && !backbone(principale.valore);
        if (aree.length > 1) {
          abr.push(d.id);
          // router di confine: l'area di ogni rete e le aree stub (come chiedi_aree_ospf del terminale)
          r.ospf_aree = {};
          for (const x of ospf) if (subnet[x.c.lan]) r.ospf_aree[subnet[x.c.lan]] = x.area.valore;
          r.ospf_aree_stub = [];
          for (const a of [principale, ...aree.filter(a => a !== principale)])
            if (a.stub && !backbone(a.valore) && !r.ospf_aree_stub.includes(a.valore)) r.ospf_aree_stub.push(a.valore);
          r.igp_networks = Object.keys(r.ospf_aree);
        }
      }
      // network IGP scritte a mano (come nel wizard); sui router di confine le decidono le aree
      const scritte = String(opz.igp_networks || '').split(/[\s,;]+/).filter(Boolean);
      if (scritte.length && (p.has('ospf') || p.has('rip')) && !r.ospf_aree) {
        const reti = scritte.map(leggiRete);
        const sbagliata = scritte.find((x, i) => !reti[i]);
        if (sbagliata) segnala(d.id, 'igp_networks', 'errore', `Network non valida: '${sbagliata}' (es. 10.0.0.0/30).`);
        else r.igp_networks = [...new Set(reti.map(testoRete))];
      }
      if (p.has('bgp') && (p.has('ospf') || p.has('rip')) && opz.redistribuisci_bgp === false) r.igp_redistribute_bgp = false;
      routers[nome] = r;
    } else if (d.tipo === 'host') {
      hosts.push(conNameserver({name: nome, interfaces: its, gateway: String((d.host || {}).gateway || '').trim() || gatewayProposto(d)}, d.host, d.id));
    } else {
      if (its.length > 1) segnala(d.id, 'collegamenti', 'errore', `${nome}: un server ${d.tipo === 'www' ? 'WWW' : 'DNS'} ha una sola interfaccia.`);
      const conf = d[d.tipo] || {};
      const base = conNameserver({name: nome, ip: its[0] ? its[0].ip : '', gateway: String(conf.gateway || '').trim() || gatewayProposto(d), lan: its[0] ? its[0].lan : ''}, conf, d.id);
      if (d.tipo === 'www') wwws.push(base);
      else {
        const x = Object.assign(base, {dns: true});
        for (const k of ['forwarders', 'root_type', 'allow_recursion', 'dnssec_validation', 'delegations'])
          if (conf[k] !== undefined) x[k] = copia(conf[k]);
        if (conf.zone !== undefined) x.zones = zoneDelWizard(conf.zone);
        // come nel wizard: le deleghe valgono solo per chi è master della zona '.'
        if (x.delegations !== undefined && x.root_type !== 'master') x.delegations = [];
        dnss.push(x);
      }
    }
  }
  let resolver = null;
  if (b.resolver) {
    const d = disp.get(b.resolver);
    if (!d || d.tipo !== 'dns') segnala(b.resolver, 'resolver', 'errore', 'Il resolver del lab deve essere un server DNS del disegno.');
    else resolver = nomi[d.id];
  }
  const ipStr = Object.fromEntries(Object.entries(ip));
  return {modello: {routers, hosts: hosts.concat(dnss), wwws, resolver}, nomi, nomiLan, subnet, interfacce, ip: ipStr, zone, membri, abr, bgpConfine, problemi};
}

export function modelloDaBozza(bozza) { return converti(bozza).modello; }

// zone DNS dell'editor (elenco con righe di record) -> formato del wizard ({zona: {nome: record}})
export function zoneDelWizard(zone) {
  if (!zone || !zone.length) return null;
  const out = {};
  for (const z of zone) {
    const nome = String(z.nome || '').trim().replace(/\.$/, '');
    if (!nome) continue;
    const rec = out[nome] = {};
    for (const r of z.record || []) {
      const n = String(r.nome || '').trim(), v = String(r.valore || '').trim(), e = String(r.extra || '').trim();
      if (!n || !v) continue;
      if (r.tipo === 'A') rec[n] = v.split('/')[0];
      else if (r.tipo === 'NS') rec[n] = Object.assign({type: 'NS', ns: v}, e ? {glue: e} : {});
      else if (r.tipo === 'CNAME') rec[n] = {type: 'CNAME', target: v};
      else if (r.tipo === 'DELEGATION') rec[n] = Object.assign({type: 'DELEGATION', zone: n, ns: v}, e ? {ns_ip: e} : {});
    }
  }
  return Object.keys(out).length ? out : null;
}

// ----------------------------------------------------------------------------- strumenti dell'editor

// Nuova subnet di una LAN: gli IP scritti a mano tengono la stessa parte host se ci stanno,
// altrimenti tornano automatici. Restituisce una nuova bozza.
export function rinumera(bozza, idLan, nuova) {
  const b = copia(bozza), l = b.lan.find(x => x.id === idLan);
  if (!l) return b;
  const vecchia = leggiRete(l.subnet) || (() => { const c = b.collegamenti.find(x => x.lan === idLan && leggiRete(x.ip)); return c ? leggiRete(c.ip) : null; })();
  const r = leggiRete(nuova);
  l.subnet = r ? testoRete(r) : String(nuova || '').trim();
  if (!r) return b;
  const presi = new Set(b.collegamenti.filter(c => c.lan !== idLan && leggiRete(c.ip)).map(c => leggiRete(c.ip).ip));
  for (const c of b.collegamenti.filter(x => x.lan === idLan && String(x.ip || '').trim())) {
    const x = leggiRete(c.ip) || (ipInt(c.ip) !== null ? {ip: ipInt(c.ip)} : null);
    const n = x && vecchia ? r.base + (x.ip - vecchia.base) : null;
    if (n !== null && n >= r.base && n < r.base + dimensione(r) && utilizzabile(r, n) && !presi.has(n)) {
      c.ip = `${intIp(n)}/${r.prefisso}`; presi.add(n);
    } else c.ip = '';
  }
  return b;
}

// Riempie i link diretti senza subnet (né IP scritti) con le /30 libere del blocco del lab.
// Restituisce {bozza, assegnate, messaggio}.
export function proponiSubnet(bozza) {
  const b = copia(bozza), blocco = leggiRete(b.blocco_subnet);
  if (!blocco) return {bozza: b, assegnate: 0, messaggio: 'Scrivi prima il blocco da cui prendere le subnet (es. 10.255.0.0/16).'};
  if (blocco.prefisso > 30) return {bozza: b, assegnate: 0, messaggio: 'Il blocco deve essere almeno una /30.'};
  const conv = converti(b);
  const prese = Object.values(conv.subnet).map(leggiRete);
  let n = blocco.base, assegnate = 0;
  for (const l of b.lan) {
    if (!l.punto || String(l.subnet || '').trim() || conv.subnet[l.id]) continue;
    let r = null;
    for (; n + 4 <= blocco.base + dimensione(blocco); n += 4) {
      const cand = {base: n, prefisso: 30};
      if (!prese.some(p => sovrapposte(p, cand))) { r = cand; n += 4; break; }
    }
    if (!r) return {bozza: b, assegnate, messaggio: `Il blocco ${testoRete(blocco)} non ha più /30 libere.`};
    l.subnet = testoRete(r); prese.push(r); assegnate++;
  }
  return {bozza: b, assegnate, messaggio: assegnate ? `${assegnate} subnet assegnate.` : 'Nessun link diretto senza subnet.'};
}

// IP scritto nel pannello -> 'ip/prefisso': basta il numero finale ('10' in 10.0.0.0/24 ->
// 10.0.0.10/24; '1.10' in 10.0.0.0/16 -> 10.0.1.10/16) o l'IP intero senza maschera. Senza subnet
// nota resta com'è (lo controlla converti).
export function completaIp(valore, subnet) {
  const v = String(valore ?? '').trim();
  const r = leggiRete(subnet);
  if (!v || !r) return v;
  const m = /^(\d{1,3}(?:\.\d{1,3}){0,3})(?:\/(\d{1,2}))?$/.exec(v);
  if (!m) return v;
  const parti = m[1].split('.');
  const ottetti = intIp(r.base).split('.');
  const ip = parti.length === 4 ? m[1] : ottetti.slice(0, 4 - parti.length).concat(parti).join('.');
  return `${ip}/${m[2] || r.prefisso}`;
}

// Elemento del disegno di un problema di valida_lab ('r1.interfaces[0].ip', 'lan.A', 'r2.asn', ...):
// {id, collegamento?} oppure null.
export function elementoDelCampo(conv, campo) {
  const s = String(campo || '');
  if (s.startsWith('lan.')) {
    const nome = s.slice(4).split('.')[0];
    const id = Object.keys(conv.nomiLan).find(k => conv.nomiLan[k] === nome);
    return id ? {id} : null;
  }
  const nome = s.split('.')[0];
  const id = Object.keys(conv.nomi).find(k => conv.nomi[k] === nome);
  if (!id) return null;
  const m = /\binterfaces\[(\d+)\]/.exec(s);
  const c = m ? (conv.interfacce[id] || [])[Number(m[1])] : null;
  return c ? {id, collegamento: c} : {id};
}
