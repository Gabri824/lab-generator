// Livelli del disegno (fase 5.6): dai dati del lab (gli stessi del Riepilogo, letti dai file) ai
// segni da disegnare. Funzioni pure, senza la pagina: si provano con Node (tests/js/livelli.test.mjs).

export const LIVELLI = [
  {id: 'indirizzi', etichetta: 'Indirizzi', attivo: true},
  {id: 'costi', etichetta: 'Costi OSPF', attivo: true},
  {id: 'sessioni', etichetta: 'Sessioni BGP', attivo: false},
  {id: 'policy', etichetta: 'Policy', attivo: true},
  {id: 'segni', etichetta: 'Segni sui router', attivo: true},
  {id: 'dns', etichetta: 'DNS', attivo: false},
  {id: 'avvisi', etichetta: 'Avvisi', attivo: true},
];

const ip0 = x => String(x || '').split('/')[0];

// IP (interfacce e loopback) -> nome del dispositivo
export function proprietari(lab) {
  const o = {};
  for (const d of lab.dispositivi) for (const ip of [...d.interfacce.map(i => i.ip).filter(Boolean), ...(d.loopback || [])]) o[ip0(ip)] = d.nome;
  return o;
}

// LAN su cui sta un IP (quella dell'interfaccia del proprietario), o null (loopback, esterni)
export function lanDiIp(lab, ip) {
  for (const d of lab.dispositivi) for (const it of d.interfacce) if (it.ip && ip0(it.ip) === ip) return it.lan;
  return null;
}

// Sessioni BGP, una per coppia di router: {a, b, tipo, stato: 'ok' | 'ko', perche, lan}.
// ko: il vicino non ha BGP, non ha il neighbor verso questo router (scritto da una parte sola),
// o l'AS scritto non è il suo. I neighbor fuori dal lab non si disegnano.
export function sessioniBgp(lab) {
  const own = proprietari(lab), disp = Object.fromEntries(lab.dispositivi.map(d => [d.nome, d]));
  const mieiIp = n => new Set([...disp[n].interfacce.map(i => ip0(i.ip)).filter(Boolean), ...(disp[n].loopback || []).map(ip0)]);
  const out = new Map();
  for (const d of lab.dispositivi) for (const nb of ((d.riepilogo || {}).neighbor || [])) {
    const b = own[nb.ip]; if (!b || b === d.nome) continue;
    const altro = disp[b], suoi = (altro.riepilogo || {}).neighbor || [], miei = mieiIp(d.nome);
    let perche = '';
    if (!altro.demoni.includes('bgpd')) perche = `${b} non ha BGP`;
    else if (!suoi.some(x => miei.has(x.ip))) perche = `${d.nome} ha il neighbor ${nb.ip} (${b}), ma ${b} non ha un neighbor verso ${d.nome}`;
    else if (altro.asn && String(nb.asn) !== String(altro.asn)) perche = `${d.nome} scrive remote-as ${nb.asn} per ${b}, che è AS${altro.asn}`;
    const k = [d.nome, b].sort().join('|'), prima = out.get(k);
    const s = {a: d.nome, b, tipo: nb.tipo, stato: perche ? 'ko' : 'ok', perche, lan: lanDiIp(lab, nb.ip)};
    if (!prima || (prima.stato === 'ok' && s.stato === 'ko')) out.set(k, s);
  }
  return [...out.values()];
}

// Sigle delle policy, una per neighbor: {router, ip, peer, lan, testo: 'LP 150 in', titolo}
export function siglePolicy(lab) {
  const own = proprietari(lab), out = [];
  for (const d of lab.dispositivi) for (const nb of ((d.riepilogo || {}).neighbor || [])) {
    const parti = (nb.policy || []).filter(p => p.breve).map(p => `${p.breve} ${p.direzione}`);
    if (!parti.length) continue;
    out.push({router: d.nome, ip: nb.ip, peer: own[nb.ip] || null, lan: lanDiIp(lab, nb.ip), testo: [...new Set(parti)].join(' · '),
      titolo: `${d.nome} verso ${nb.chi} (${nb.ip}): ` + nb.policy.map(p => `${p.direzione} ${p.testo}`).join('; ')});
  }
  return out;
}

// Customer-Provider-Peer: [{customer, provider} | {peer: [a, b]}, lan], dalla relazione scritta da
// una parte o dall'altra (provider da una parte = customer dall'altra)
export function relazioniCpp(lab) {
  const own = proprietari(lab), out = new Map();
  for (const d of lab.dispositivi) for (const nb of ((d.riepilogo || {}).neighbor || [])) {
    const b = own[nb.ip]; if (!nb.relazione || !b) continue;
    const k = [d.nome, b].sort().join('|'); if (out.has(k)) continue;
    const lan = lanDiIp(lab, nb.ip);
    if (nb.relazione === 'peer') out.set(k, {peer: [d.nome, b], lan});
    else if (nb.relazione === 'provider') out.set(k, {customer: d.nome, provider: b, lan});
    else out.set(k, {customer: b, provider: d.nome, lan});
  }
  return [...out.values()];
}

// segni accanto a un router: default route mandata, ridistribuzione BGP -> IGP, loopback
export function segniRouter(d) {
  const R = d.riepilogo || {};
  return {default: R.default || [], redistribuisce: R.redistribute_bgp_igp || [], loopback: (d.loopback || []).map(ip0)};
}

// albero DNS: deleghe {da: server padre, a: server figlio (o null), zona, ns}
export function alberoDns(lab) {
  return lab.dispositivi.flatMap(d => (d.deleghe || []).map(x => ({da: d.nome, a: x.server || null, zona: x.zona, ns: x.ns, ip: x.ip})));
}

// resolver di un dispositivo (non router): 'ns: local' (nome del server, o l'IP se è fuori dal lab)
export function resolver(lab, d) {
  if (d.tipo === 'router' || !(d.nameserver || []).length) return '';
  const own = proprietari(lab);
  return 'ns: ' + d.nameserver.map(ip => own[ip0(ip)] || ip).join(', ');
}

// avvisi automatici sui dispositivi e sugli AS che citano: {dev: {nome: [testi]}, as: {g: [testi]}}
export function avvisiSulDisegno(lab) {
  const testi = [...(lab.avvisi_topologia || []), ...(lab.avvisi_config || [])];
  const dev = {}, as = {};
  const nomi = lab.dispositivi.map(d => d.nome).sort((a, b) => b.length - a.length);
  for (const t of testi) {
    let trovato = false;
    for (const n of nomi) if (new RegExp(`(^|[^\\w])${n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}($|[^\\w])`).test(t)) { (dev[n] = dev[n] || []).push(t); trovato = true; }
    for (const m of t.matchAll(/\bAS(\d+)\b/g)) { (as[m[1]] = as[m[1]] || []).includes(t) || (as[m[1]] = as[m[1]] || []).push(t); trovato = true; }
    if (!trovato) (dev[''] = dev[''] || []).push(t);
  }
  // errori della diagnostica di frr.conf, se è stata eseguita (pannello o Riepilogo)
  for (const [n, ps] of Object.entries(lab.diagnosi || {}))
    for (const x of ps) if (x.gravita === 'errore') (dev[n] = dev[n] || []).push(`Diagnostica: ${x.file}${x.riga ? ' riga ' + x.riga : ''}: ${x.messaggio}`);
  return {dev, as};
}
