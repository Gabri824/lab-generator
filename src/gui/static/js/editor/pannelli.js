// Parti del pannello proprietà dell'editor (fase 4.4): router, host e server, DNS, lab.
// Ogni campo ha data-chiave = "<proprietà>:<id>[:indici...]": editor.js la passa ad
// azioni.impostaProprieta; i pulsanti degli elenchi hanno data-elenco, data-op e data-indici.
import { esc } from '../comune.js';

export function campo(etichetta, chiave, valore, segnaposto, attributi = '', aiuto = '') {
  return `<div class="prop__campo"><label for="edc-${chiave}">${esc(etichetta)}</label>
    <input id="edc-${chiave}" data-chiave="${chiave}" value="${esc(valore ?? '')}" placeholder="${esc(segnaposto)}" autocomplete="off" spellcheck="false" ${attributi}>
    ${aiuto ? `<p class="prop__aiuto">${aiuto}</p>` : ''}</div>`;
}
const casella = (chiave, acceso, testo) => `<label class="scelta ed-casella"><input type="checkbox" data-chiave="${chiave}"${acceso ? ' checked' : ''}> ${testo}</label>`;
const scelta = (chiave, valore, opzioni, etichetta) => `<select data-chiave="${chiave}" aria-label="${esc(etichetta)}">${opzioni.map(([v, t]) => `<option value="${esc(v)}"${String(v) === String(valore ?? '') ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select>`;
const cella = (chiave, valore, segnaposto, etichetta) => `<input data-chiave="${chiave}" value="${esc(valore ?? '')}" placeholder="${esc(segnaposto)}" aria-label="${esc(etichetta)}" autocomplete="off" spellcheck="false">`;
const togli = (elenco, id, indici, etichetta) => `<button type="button" class="ghost small" data-elenco="${elenco}" data-op="togli" data-id="${id}" data-indici="${indici}" aria-label="${esc(etichetta)}">✕</button>`;
const aggiungi = (elenco, id, indici, testo) => `<button type="button" class="ghost small" data-elenco="${elenco}" data-op="aggiungi" data-id="${id}" data-indici="${indici}">+ ${testo}</button>`;

// voce del modello (router, host, www o dns) di un dispositivo
export function voceModello(conv, d) {
  const nome = conv.nomi[d.id], m = conv.modello;
  if (d.tipo === 'router') return m.routers[nome] || {protocols: []};
  if (d.tipo === 'www') return m.wwws.find(x => x.name === nome) || {};
  return m.hosts.find(x => x.name === nome) || {};
}

export function htmlRouter(d, conv, completato) {
  const r = voceModello(conv, d), opz = d.router || {}, nome = conv.nomi[d.id];
  const igp = r.protocols.includes('ospf') || r.protocols.includes('rip');
  let h = `<div class="prop__campo"><label for="edc-bgp-${d.id}">BGP</label><select id="edc-bgp-${d.id}" data-chiave="bgp:${d.id}">
    <option value="auto"${!opz.bgp || opz.bgp === 'auto' ? ' selected' : ''}>automatico (dal riquadro AS)</option>
    <option value="si"${opz.bgp === 'si' ? ' selected' : ''}>sì</option><option value="no"${opz.bgp === 'no' ? ' selected' : ''}>no</option></select></div>`;
  const inArea = r.protocols.includes('ospf') || opz.ospf === 'no';
  if (inArea) h += `<div class="prop__campo"><label for="edc-ospf-${d.id}">OSPF</label><select id="edc-ospf-${d.id}" data-chiave="ospf:${d.id}">
    <option value="auto"${opz.ospf !== 'no' ? ' selected' : ''}>automatico (dalle aree)</option><option value="no"${opz.ospf === 'no' ? ' selected' : ''}>no (es. router RIP sul confine)</option></select></div>`;
  if (r.protocols.includes('bgp') && igp)
    h += casella(`redistribuisci:${d.id}`, opz.redistribuisci_bgp !== false, "ridistribuisci BGP nell'IGP (redistribute bgp)");
  if (igp && !r.ospf_aree) {
    const proposte = ((completato && completato.routers && completato.routers[nome]) || {}).igp_networks || [];
    h += campo(`Network ${r.protocols.includes('ospf') ? 'OSPF' : 'RIP'}`, `igp:${d.id}`, opz.igp_networks, proposte.length ? `proposte: ${proposte.join(', ')}` : 'proposte dal motore',
      '', 'Vuoto = quelle proposte (come Invio nel wizard). Più reti separate da virgola.');
  } else if (r.ospf_aree) {
    h += `<p class="small"><b>Network per area</b> (router di confine, dalle zone): ${Object.entries(r.ospf_aree).map(([n, a]) => `${esc(n)} → ${esc(a)}`).join(', ')}</p>`;
  }
  const st = opz.statiche || [], its = (conv.interfacce[d.id] || []).map((_, k) => [`eth${k}`, `eth${k}`]);
  h += `<h4 class="ed-sotto">Rotte statiche</h4>`;
  if (st.length) h += `<table class="ed-tab"><tr><th>Rete</th><th>Via</th><th>Interf.</th><th></th></tr>${st.map((s, k) => `<tr>
      <td>${cella(`statica:${d.id}:${k}:rete`, s.rete, 'default o 10.0.0.0/24', `Rete della rotta ${k + 1}`)}</td>
      <td>${cella(`statica:${d.id}:${k}:via`, s.via, 'IP del next-hop', `Next-hop della rotta ${k + 1}`)}</td>
      <td>${scelta(`statica:${d.id}:${k}:dev`, s.dev || '', [['', 'auto'], ...its], `Interfaccia della rotta ${k + 1}`)}</td>
      <td>${togli('statica', d.id, k, `Togli la rotta ${k + 1}`)}</td></tr>`).join('')}</table>`;
  h += `<div class="btns">${aggiungi('statica', d.id, '', 'rotta statica')}</div>`;
  return h;
}

export function htmlGateway(d, conv) {
  const scritto = (d[d.tipo] || {}).gateway || '', proposto = voceModello(conv, d).gateway || '';
  return campo('Gateway', `gateway:${d.id}`, scritto, scritto ? '' : (proposto ? `proposto: ${proposto}` : 'nessun router sulla LAN'), '',
    'Vuoto = l\'IP del router sulla sua LAN.')
    + campo('Resolver solo di questo dispositivo', `nameserver:${d.id}`, (d[d.tipo] || {}).nameserver || '', 'vuoto = quello del lab', '',
      'IP di un server DNS (anche fuori dal lab), come "Resolver" delle Opzioni. Più IP separati da virgola.');
}

const TIPI_RECORD = [['A', 'A'], ['NS', 'NS'], ['CNAME', 'CNAME'], ['DELEGATION', 'DELEGATION']];
const AIUTO_RECORD = {A: ['IP', ''], NS: ['nameserver (es. dns.com.)', 'glue IP (facoltativo)'], CNAME: ['destinazione (es. www)', ''], DELEGATION: ['nameserver', 'IP (facoltativo)']};

export function htmlDns(d, conv) {
  const c = d.dns || {}, nome = conv.nomi[d.id];
  const tipoRoot = c.root_type !== undefined ? (c.root_type || '') : (nome === 'root' ? 'master' : 'hint');
  let h = `<div class="prop__campo"><label>Tipo per la zona "."</label>${scelta(`root_type:${d.id}`, tipoRoot, [['master', 'master (è un server root)'], ['hint', 'hint (usa i server root)'], ['', 'nessuno']], 'Tipo per la zona punto')}</div>`;
  if (tipoRoot === 'master') {
    const del = c.delegations || [];
    h += `<h4 class="ed-sotto">Deleghe dal root</h4>`;
    if (del.length) h += `<table class="ed-tab"><tr><th>Zona</th><th>Nameserver</th><th>IP</th><th></th></tr>${del.map((x, k) => `<tr>
        <td>${cella(`delega:${d.id}:${k}:zone`, x.zone, 'es. com', `Zona della delega ${k + 1}`)}</td>
        <td>${cella(`delega:${d.id}:${k}:ns`, x.ns, 'es. dns.com', `Nameserver della delega ${k + 1}`)}</td>
        <td>${cella(`delega:${d.id}:${k}:ip`, x.ip, 'IP', `IP della delega ${k + 1}`)}</td>
        <td>${togli('delega', d.id, k, `Togli la delega ${k + 1}`)}</td></tr>`).join('')}</table>`;
    h += `<div class="btns">${aggiungi('delega', d.id, '', 'delega')}</div>`;
  }
  const zone = c.zone || [];
  h += `<h4 class="ed-sotto">Zone (server autoritativo)</h4>`;
  zone.forEach((z, k) => {
    h += `<div class="ed-zona-dns">${campo(`Zona ${k + 1}`, `zona:${d.id}:${k}`, z.nome, 'es. com')}`;
    if ((z.record || []).length) h += `<table class="ed-tab"><tr><th>Nome</th><th>Tipo</th><th>Valore</th><th></th><th></th></tr>${z.record.map((r, ri) => {
      const [aV, aE] = AIUTO_RECORD[r.tipo] || ['', ''];
      return `<tr><td>${cella(`record:${d.id}:${k}:${ri}:nome`, r.nome, r.tipo === 'NS' ? '@' : 'es. www', `Nome del record ${ri + 1}`)}</td>
        <td>${scelta(`record:${d.id}:${k}:${ri}:tipo`, r.tipo, TIPI_RECORD, `Tipo del record ${ri + 1}`)}</td>
        <td>${cella(`record:${d.id}:${k}:${ri}:valore`, r.valore, aV, `Valore del record ${ri + 1}`)}</td>
        <td>${aE ? cella(`record:${d.id}:${k}:${ri}:extra`, r.extra, aE, `${aE} del record ${ri + 1}`) : ''}</td>
        <td>${togli('record', d.id, `${k},${ri}`, `Togli il record ${ri + 1}`)}</td></tr>`;
    }).join('')}</table>`;
    h += `<div class="btns">${aggiungi('record', d.id, k, 'record')}${togli('zona', d.id, k, `Togli la zona ${k + 1}`).replace('>✕<', '>Togli la zona<')}</div></div>`;
  });
  h += `<div class="btns">${aggiungi('zona', d.id, '', 'zona')}</div>`;
  const ric = c.allow_recursion;
  h += casella(`ricorsione:${d.id}`, !!ric, 'fa da resolver (allow-recursion)');
  if (ric) h += campo('Reti ammesse', `ricorsione_reti:${d.id}`, ric === 'any' ? '' : ric, 'any (tutte)', '', 'Vuoto = any. Più reti separate da virgola.');
  h += casella(`dnssec:${d.id}`, !!c.dnssec_validation, 'disattiva la validazione DNSSEC (dnssec-validation no)');
  return h;
}

export function htmlLab(b, conv) {
  const dns = b.dispositivi.filter(d => d.tipo === 'dns');
  let h = `<div class="prop__campo"><label for="edc-resolver">Resolver finale del lab</label>${scelta('resolver:lab', b.resolver || '', [['', 'nessuno'], ...dns.map(d => [d.id, conv.nomi[d.id]])], 'Resolver finale del lab').replace('<select ', '<select id="edc-resolver" ')}
    <p class="prop__aiuto">Il DNS che host e server usano come nameserver (resolv.conf).</p></div>`;
  h += campo('Blocco per le subnet dei link diretti', 'blocco:lab', b.blocco_subnet, 'es. 10.255.0.0/16');
  h += `<div class="btns"><button type="button" class="small" data-azione="proponi"${b.blocco_subnet ? '' : ' disabled'}>Proponi subnet</button></div>`;
  return h;
}
