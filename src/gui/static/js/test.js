// Scheda Test: raggiungibilità, sessioni e convergenza, rotta, tabelle, ping, percorso, guasto di un link.
import { $, api, esc, esegui, S } from './comune.js';
import { dispositivo } from './dispositivo.js';
import { scheda } from './main.js';
import { ridisegna } from './topologia.js';

// ---------- test ----------
$('#bPing').onclick = async e => {
  const r = await esegui({azione: 'raggiungibilita'}, 'Raggiungibilità ' + S.nome, e.target);
  if (r && r.risultato) mostraPing(r.risultato);
};
export function mostraPing(r) {
  const devs = [...new Set(r.destinazioni.map(x => x.dev))], ko = [];
  let h = `<div class="scroll"><table class="mat" style="width:auto"><tr><th>da \\ verso</th>${devs.map(d => `<th class="v"><span>${esc(d)}</span></th>`).join('')}</tr>`;
  for (const s of r.sorgenti) { const e = r.esiti[s] || {};
    h += `<tr><th>${esc(s)}</th>`;
    if (e._errore) { h += `<td colspan="${devs.length}" class="ko" style="text-align:left">${esc(e._errore)}</td></tr>`; ko.push(s + ': ' + e._errore); continue; }
    for (const d of devs) {
      if (d === s) { h += '<td class="self">—</td>'; continue; }
      const ips = r.destinazioni.filter(x => x.dev === d).map(x => x.ip), no = ips.filter(ip => e[ip] !== true);
      no.forEach(ip => ko.push(`${s} → ${ip} (${d})`));
      const cls = no.length === 0 ? 'ok' : (no.length === ips.length ? 'ko' : 'mezzo');
      h += `<td class="${cls}" title="${esc(no.length ? 'non raggiunti: ' + no.join(', ') : 'tutti raggiunti')}">${ips.length - no.length}/${ips.length}</td>`;
    }
    h += '</tr>';
  }
  h += '</table></div>';
  h += ko.length ? `<div class="koline" style="margin-top:8px">${ko.length} ping falliti</div><details><summary>Elenco</summary><ul class="avvisi">${ko.map(x => `<li>${esc(x)}</li>`).join('')}</ul></details>
      <div class="muted small">Un KO può essere voluto: filtri e policy del testo, oppure reti interne non annunciate in BGP
      (il ping parte dall'IP dell'interfaccia di uscita: se quella rete non è annunciata, la risposta non torna).
      Controlla che corrisponda a quello che chiede l'esercizio.</div>`
    : '<div class="okline" style="margin-top:8px">✔ Tutti gli indirizzi raggiunti da tutti i dispositivi.</div>';
  $('#rPing').innerHTML = h;
}
$('#bSessioni').onclick = async e => {
  const r = await esegui({azione: 'sessioni'}, 'Sessioni BGP/OSPF ' + S.nome, e.target);
  if (r && r.risultato) mostraSessioni(r.risultato);
};
export function stato(x) {
  if (x.escluso) return `<span class="badge" title="${esc(x.stato || '')}">${esc(x.escluso)}</span>`;
  return `<span class="badge ${x.ok ? 'ok' : 'ko'}">${esc(x.stato || 'errore')}</span>`;
}
export function mostraSessioni(r) {
  let h = '<h3>BGP</h3>';
  h += r.bgp.length ? `<table><tr><th>Router</th><th>Neighbor</th><th>Dispositivo</th><th>AS</th><th>Stato</th><th>Prefissi ricevuti</th><th>Attiva da</th></tr>${r.bgp.map(x => x.errore ? `<tr><td>${esc(x.router)}</td><td colspan="6" class="koline">${esc(x.errore)}</td></tr>` :
    `<tr><td>${esc(x.router)}</td><td><code>${esc(x.neighbor)}</code></td><td>${esc(x.chi)}</td><td>${esc(x.as || '')}</td><td>${stato(x)}</td><td>${esc(x.prefissi == null ? '' : x.prefissi)}</td><td>${esc(x.uptime || '')}</td></tr>`).join('')}</table>` : '<div class="muted">Nessun router BGP.</div>';
  h += '<h3 style="margin-top:14px">OSPF</h3>';
  h += r.ospf.length ? `<table><tr><th>Router</th><th>Vicino</th><th>Dispositivo</th><th>Router-ID</th><th>Interfaccia</th><th>Stato</th></tr>${r.ospf.map(x =>
    `<tr><td>${esc(x.router)}</td><td><code>${esc(x.vicino)}</code></td><td>${esc(x.chi)}</td><td>${esc(x.router_id || '')}</td><td>${esc(x.interfaccia || '')}</td><td>${stato(x)}</td></tr>`).join('')}</table>
    <div class="muted small">"non trovato" = router OSPF dello stesso AS sulla stessa LAN che non è diventato vicino (interfaccia non coperta dalle network OSPF, area diversa, lab non ancora convergente).</div>` : '<div class="muted">Nessun router OSPF.</div>';
  const rid = r.ridistribuzione || [];
  if (rid.length) {
    h += '<h3 style="margin-top:14px">Ridistribuzione nell\'IGP (redistribute bgp / connected)</h3>';
    h += `<table><tr><th>Router</th><th>IGP</th><th>Riga nel frr.conf</th><th>Da ridistribuire</th><th>Entrate nell'IGP</th><th title="show zebra client: rotte ridistribuite che zebra ha passato a ripd/ospfd dall'avvio (tutte le righe redistribute insieme)">Passate da zebra</th><th>Stato</th><th></th></tr>${rid.map(x =>
      `<tr class="${x.ok ? '' : 'sosp'}"><td>${esc(x.router)}</td><td>${esc(x.igp)}</td><td><code>${esc(x.riga)}</code></td><td>${x.errore ? '' : esc(x.totale)}</td>
       <td title="${esc((x.mancanti || []).length ? 'mancanti: ' + x.mancanti.join(', ') : '')}">${x.errore ? `<span class="koline">${esc(x.errore)}</span>` : esc(x.iniettate)}</td>
       <td>${x.zebra == null ? '' : esc(x.zebra)}</td><td>${stato(x)}${x.causa ? `<div class="small muted">${esc(x.causa)}</div>` : ''}</td>
       <td>${x.ok ? '' : `<button class="small" data-riapplica="${esc(x.router)}" data-igp="${esc(x.igp)}">Riapplica</button>`}</td></tr>`).join('')}</table>
      <div class="muted small">Controlla che le rotte BGP e le reti connesse (quelle non già coperte dalle network dell'IGP) siano davvero entrate in RIP/OSPF.
      Con FRR 10.5.3 a volte la ridistribuzione non parte all'avvio anche se il file è giusto: zebra non riceve la richiesta del demone
      e "Passate da zebra" resta 0. "Riapplica" toglie e rimette tutte le righe redistribute del blocco a lab acceso (i file non cambiano).
      Se "Passate da zebra" è più di 0 ma la riga resta "non attiva", la causa è un'altra (es. una route-map che filtra tutto).</div>`;
  }
  S.sessioni = r;
  $('#rSessioni').innerHTML = h;
}
$('#rSessioni').addEventListener('click', async e => {
  const b = e.target.closest('[data-riapplica]'); if (!b) return;
  const res = await esegui({azione: 'riapplica', dev: b.dataset.riapplica, igp: b.dataset.igp}, 'Riapplica ridistribuzione ' + b.dataset.riapplica, b);
  if (res && Array.isArray(res.risultato) && S.sessioni) {
    const nuove = res.risultato;
    S.sessioni.ridistribuzione = S.sessioni.ridistribuzione.map(x => nuove.find(n => n.router === x.router && n.igp === x.igp && n.riga === x.riga) || x);
    mostraSessioni(S.sessioni);
  }
});
// ---------- ping ----------
export function origini() {
  const d = (S.lab.dispositivi.find(x => x.nome === $('#pnSrc').value) || {interfacce: [], loopback: []});
  $('#pnOrig').innerHTML = '<option value="">automatica</option>' + d.interfacce.filter(i => i.ip).map(i => `<option value="${esc(i.ip.split('/')[0])}">${esc(i.dev + ' ' + i.ip.split('/')[0])}</option>`).join('')
    + d.loopback.map(ip => `<option value="${esc(ip.split('/')[0])}">${esc('lo ' + ip.split('/')[0])}</option>`).join('');
}
$('#pnSrc').onchange = origini;
$('#bPn').onclick = e => { const ip = $('#pnDst').value.trim(); if (!ip) { $('#pnDst').focus(); return; } pingUno($('#pnSrc').value, ip, $('#pnOrig').value, e.target); };
export async function pingUno(src, ip, origine, bottone) {
  const r = await esegui({azione: 'ping', dev: src, ip, origine}, 'ping ' + src + ' → ' + ip + (origine ? ' (da ' + origine + ')' : ''), bottone);
  if (!r || !r.risultato) return;
  const p = r.risultato;
  const chi = p.dev_destinazione ? `${esc(p.dev_destinazione)}${p.lan_destinazione ? ' · LAN ' + esc(p.lan_destinazione) : ''}` : 'fuori dal lab';
  let h = `<div class="${p.ok ? 'okline' : 'koline'}"><b>${p.ok ? '✔ Risponde' : '✘ Nessuna risposta'}</b> — ${p.inviati ? p.ricevuti + '/' + p.inviati + ' pacchetti' : 'il ping non è partito'}${p.media ? ' · media ' + esc(p.media) + ' ms' : ''}</div>
    <div class="small" style="margin:6px 0">${esc(p.sorgente)} → <code>${esc(p.destinazione)}</code> (${chi})</div>
    <div class="small muted">Partito da: ${p.partenza ? `<code>${esc(p.partenza)}</code>${p.dev_uscita ? ' (' + esc(p.dev_uscita) + ')' : ''}${p.origine ? ' — scelta da te' : ' — automatica'}` : '—'}${p.rotta ? '' : ` · <b>nessuna rotta verso ${esc(p.destinazione)}</b>`}</div>`;
  if (p.suggerimento) h += `<div class="warnline small" style="margin-top:6px">${esc(p.suggerimento)}</div>`;
  $('#rPn').innerHTML = h;
}
$('#bPercorso').onclick = e => {
  const ip = $('#pDst').value.trim(); if (!ip) { $('#pDst').focus(); return; }
  percorso($('#pSrc').value, ip, e.target, {atteso: $('#pAtt').value, attesoR: $('#pAttR').value, ritorno: $('#pRit').checked,
    modo: document.querySelector('input[name=pModo]:checked').value});
};
// confronto con il percorso richiesto dal testo: nomi di LAN oppure di dispositivi
export function confrontaPercorso(p, atteso, modo) {
  const tok = (atteso || '').split(/[\s,;>→]+/).filter(Boolean);
  if (!tok.length) return null;
  const lanN = {}, devN = {};
  S.lab.lan.forEach(l => lanN[l.nome.toLowerCase()] = l.nome);
  S.lab.dispositivi.forEach(d => devN[d.nome.toLowerCase()] = d.nome);
  const tipo = tok.every(t => lanN[t.toLowerCase()]) ? 'lan' : tok.every(t => devN[t.toLowerCase()]) ? 'dev' : null;
  if (!tipo) {
    const ignoti = tok.filter(t => !lanN[t.toLowerCase()] && !devN[t.toLowerCase()]);
    return {errore: (ignoti.length ? `Non riconosco ${ignoti.join(', ')}` : 'Hai mescolato LAN e dispositivi')
      + `: usa solo nomi di LAN (${S.lab.lan.map(l => l.nome).join(' ')}) oppure solo nomi di dispositivi.`};
  }
  const att = tok.map(t => (tipo === 'lan' ? lanN : devN)[t.toLowerCase()]);
  const fatto = tipo === 'lan' ? p.hop.map(x => x.lan).filter(Boolean) : [p.sorgente].concat(p.hop.map(x => x.dev).filter(Boolean));
  let punto = -1, ok;
  if (modo === 'esatta') {
    let i = 0; while (i < att.length && i < fatto.length && att[i] === fatto[i]) i++;
    ok = i === att.length && i === fatto.length; if (!ok) punto = i;
  } else {
    let j = 0; for (const x of fatto) if (j < att.length && x === att[j]) j++;
    ok = j === att.length; if (!ok) punto = j;
  }
  return {ok, tipo, modo, att, fatto, punto, mancanti: att.filter(t => !fatto.includes(t))};
}
export function htmlConfronto(c) {
  if (!c) return '';
  if (c.errore) return `<div class="warnline small" style="margin:6px 0">${esc(c.errore)}</div>`;
  const seq = c.fatto.map((x, i) => {
    const giusto = c.modo === 'esatta' ? (c.punto < 0 || i < c.punto) : c.att.includes(x);
    return `<b class="${giusto ? 'okline' : (c.modo === 'esatta' && i === c.punto ? 'koline' : '')}">${esc(x)}</b>`;
  }).join(' ');
  let h = `<div class="small" style="margin:6px 0">${c.tipo === 'lan' ? 'Link attraversati' : 'Dispositivi attraversati'}: ${seq}</div>`;
  if (c.ok) return h + `<div class="okline"><b>✔ Come richiesto</b> — ${c.modo === 'esatta' ? 'sequenza esatta' : 'passa per'} ${esc(c.att.join(' '))}</div>`;
  let perche;
  if (c.modo === 'esatta') {
    perche = c.punto >= c.fatto.length ? `il percorso finisce prima: manca ${esc(c.att.slice(c.punto).join(' '))}`
      : c.punto >= c.att.length ? `il percorso continua oltre il richiesto (${esc(c.fatto.slice(c.punto).join(' '))})`
      : `al passo ${c.punto + 1} atteso <b>${esc(c.att[c.punto])}</b>, invece <b>${esc(c.fatto[c.punto])}</b>`;
  } else {
    perche = c.mancanti.length ? `non passa per <b>${esc(c.mancanti.join(' '))}</b>` : `ci passa ma non nell'ordine richiesto (${esc(c.att.join(' '))})`;
  }
  return h + `<div class="koline"><b>✘ Diverso dal richiesto</b> (${esc(c.att.join(' '))}): ${perche}</div>`;
}
// routing loop: un dispositivo che ricompare più avanti nel percorso (A → B → A ...)
export function loopPercorso(p) {
  const devs = [p.sorgente].concat(p.hop.map(x => x.dev).filter(Boolean));
  for (let i = 0; i < devs.length; i++) {
    const j = devs.indexOf(devs[i], i + 1);
    if (j > i + 1) return devs.slice(i, j);
  }
  return null;
}
export function htmlPercorso(p, titolo, c) {
  const nomi = [p.sorgente].concat(p.hop.map(x => x.dev || x.ip)), loop = loopPercorso(p);
  const spenti = S.spenti && S.spenti.size ? [...S.spenti] : [];
  let h = `<h3 style="margin-top:10px">${esc(titolo)}</h3><div class="${p.arrivato ? 'okline' : 'koline'}"><b>${p.arrivato ? '✔ Arrivato' : '✘ Non arrivato'}</b> a ${esc(p.destinazione)}${p.dev_destinazione ? ' (' + esc(p.dev_destinazione) + ')' : ''} — ${p.hop.length} hop</div>
    <div style="margin:6px 0"><b>${nomi.map(esc).join(' → ')}</b></div>`;
  if (loop) h += `<div class="koline small" style="margin:6px 0"><b>⟳ Routing loop tra ${esc(loop.join(' e '))}</b>: i pacchetti rimbalzano tra questi router (ognuno crede che la strada passi per l'altro).
    ${spenti.length ? 'Hai un link spento: la rete forse si sta ancora riassestando, attendi la convergenza e riprova.' : 'Controlla le loro rotte verso questa destinazione (Rotta verso una rete).'}</div>`;
  else if (!p.arrivato && spenti.length) h += `<div class="warnline small" style="margin:6px 0">C'è un link spento (${esc(spenti.join(', '))}): se l'hai appena spento attendi la convergenza e riprova; se resta così, non c'è un percorso di riserva.</div>`;
  if (c && !c.errore && !p.arrivato) h += `<div class="small muted">Il pacchetto non arriva: il confronto con l'atteso riguarda solo il tratto percorso.</div>`;
  h += htmlConfronto(c);
  h += `<details${c ? '' : ' open'}><summary class="small">Hop</summary><div class="hop muted small"><b>S</b><span>${esc(p.sorgente)}</span></div>`;
  h += p.hop.map(x => `<div class="hop small"><b>${x.n}</b><code>${esc(x.ip)}</code><span>${esc(x.dev || (x.ip === '*' ? 'nessuna risposta' : 'fuori dal lab'))}</span><span class="muted">${x.lan ? 'LAN ' + esc(x.lan) : ''}</span></div>`).join('');
  return h + '</details>';
}
// evidenzia un percorso sulla topologia (link attesi e non attraversati in rosso)
export function evidenzia(p, c) {
  const ordine = {}; ordine[p.sorgente] = 'S';
  p.hop.forEach(x => { if (x.dev && ordine[x.dev] == null) ordine[x.dev] = x.n; });
  S.evid = {dev: new Set([p.sorgente].concat(p.hop.filter(x => x.dev).map(x => x.dev))), lan: new Set(p.hop.filter(x => x.lan).map(x => x.lan)), ordine,
    manca: new Set(c && c.tipo === 'lan' ? c.mancanti : [])};
  ridisegna();
}
export async function percorso(src, ip, bottone, opz) {
  opz = opz || {};
  const r = await esegui({azione: 'percorso', dev: src, ip: ip}, 'Percorso ' + src + ' → ' + ip, bottone);
  if (!r || !r.risultato) return;
  const p = r.risultato, c = confrontaPercorso(p, opz.atteso, opz.modo);
  let q = null, cq = null, nota = '';
  if (opz.ritorno) {
    // ritorno: dalla destinazione verso l'IP della sorgente sulla LAN da cui è partito il traceroute
    const d = dispositivo(src), lan0 = p.hop[0] && p.hop[0].lan;
    const it = d && (d.interfacce.find(i => i.lan === lan0 && i.ip) || d.interfacce.find(i => i.ip));
    if (!p.dev_destinazione) nota = "Ritorno non possibile: la destinazione non è un dispositivo del lab.";
    else if (!it) nota = `Ritorno non possibile: ${src} non ha indirizzi.`;
    else {
      const ipr = it.ip.split('/')[0];
      const rr = await esegui({azione: 'percorso', dev: p.dev_destinazione, ip: ipr}, 'Percorso ' + p.dev_destinazione + ' → ' + ipr, bottone);
      if (rr && rr.risultato) { q = rr.risultato; cq = confrontaPercorso(q, opz.attesoR, opz.modo); }
    }
  }
  evidenzia(p, c);
  let h = htmlPercorso(p, 'Andata: ' + src + ' → ' + ip, c);
  if (q) h += htmlPercorso(q, 'Ritorno: ' + q.sorgente + ' → ' + q.destinazione, cq);
  if (nota) h += `<div class="warnline small" style="margin-top:6px">${esc(nota)}</div>`;
  h += `<div class="riga"><button class="small ghost" id="vediMappa">Andata sulla topologia</button>${q ? '<button class="small ghost" id="vediRit">Ritorno sulla topologia</button>' : ''}</div>`;
  $('#rPercorso').innerHTML = h;
  $('#vediMappa').onclick = () => { evidenzia(p, c); scheda('topo'); };
  if (q) $('#vediRit').onclick = () => { evidenzia(q, cq); scheda('topo'); };
}

// ---------- guasto di un link ----------
export function lanGuasto() {
  const sel = $('#gLan').value;
  $('#gLan').innerHTML = S.lab.lan.map(l => {
    const m = S.lab.dispositivi.flatMap(d => d.interfacce.filter(i => i.lan === l.nome).map(i => d.nome + ' ' + i.dev));
    return `<option value="${esc(l.nome)}">${esc(l.nome)}${S.spenti && S.spenti.has(l.nome) ? ' (spento)' : ''} — ${esc(m.join(' ↔ '))}</option>`;
  }).join('');
  if (sel) $('#gLan').value = sel;
}
export async function link(lan, acceso, bottone) {
  const r = await esegui({azione: 'link', lan, acceso}, (acceso ? 'Riaccendi' : 'Spegni') + ' link ' + lan, bottone);
  await controllaSpenti();
  // i protocolli devono riassestarsi prima di tracciare i percorsi
  if (r && r.rc === 0) await attendiConvergenza($('#bConv'));
}
$('#gGiu').onclick = e => link($('#gLan').value, false, e.target);
$('#gSu').onclick = e => link($('#gLan').value, true, e.target);
export async function controllaSpenti() {
  if (!S.nome) return;
  let lan = [];
  if ((S.stato[S.nome] || []).length) { try { lan = (await api('/api/spenti?lab=' + encodeURIComponent(S.nome))).lan; } catch (e) { return; } }
  const prima = [...(S.spenti || [])].join(' ');
  S.spenti = new Set(lan);
  const n = $('#linkNota');
  n.hidden = !lan.length;
  if (lan.length) n.innerHTML = `<b>⚠ Link spento${lan.length > 1 ? 'i' : ''}: ${lan.map(esc).join(', ')}</b> — guasto simulato dalla GUI (tratteggio rosso sulla topologia): ping e percorsi ne risentono.
    ${lan.map(l => `<button class="small" data-riaccendi="${esc(l)}">Riaccendi ${esc(l)}</button>`).join(' ')}`;
  $('#rGuasto').innerHTML = lan.length ? `<div class="warnline small">Spenti ora: ${lan.map(esc).join(', ')}</div>` : '';
  if (prima !== lan.join(' ')) { lanGuasto(); ridisegna(); }
}
$('#linkNota').addEventListener('click', e => {
  const b = e.target.closest('[data-riaccendi]'); if (b) link(b.dataset.riaccendi, true, b);
});

// ---------- convergenza ----------
export async function attendiConvergenza(bottone) {
  const r = await esegui({azione: 'convergenza'}, 'Attendi convergenza ' + S.nome, bottone);
  if (r && r.risultato) mostraSessioni(r.risultato);
  return r;
}
$('#bConv').onclick = e => attendiConvergenza(e.target);

// ---------- rotta verso una rete ----------
$('#bRotta').onclick = async e => {
  const rete = $('#rRete').value.trim(); if (!rete) { $('#rRete').focus(); return; }
  const r = await esegui({azione: 'rotta', dev: $('#rDev').value, rete}, 'Rotta ' + $('#rDev').value + ' → ' + rete, e.target);
  if (r && r.risultato) mostraRotta(r.risultato);
};
export function mostraRotta(r) {
  const I = r.instradamento;
  let h = '';
  if (!I) h += `<div class="koline"><b>✘ ${esc(r.dev)} non ha nessuna rotta verso ${esc(r.rete)}.</b> La rete non è annunciata, è filtrata o il lab non è ancora convergente.</div>`;
  else {
    const hop = I.hop.map(x => x.connessa || !x.ip ? `direttamente su ${esc(x.dev || '')}${x.lan ? ' (LAN ' + esc(x.lan) + ')' : ''}`
      : `via <code>${esc(x.ip)}</code> = <b>${esc(x.chi || '?')}</b>${x.lan ? ' sulla LAN ' + esc(x.lan) : ''}`).join('<br>');
    h += `<div class="okline"><b>✔ ${esc(r.dev)} → ${esc(I.prefisso)}</b> imparata da <b>${esc(I.protocollo)}</b></div><div style="margin:4px 0 10px">${hop}</div>`;
  }
  if (r.bgp.length) {
    h += `<h3>Percorsi BGP per ${esc(r.prefisso_bgp || r.rete)} (${r.bgp.length})</h3><table><tr><th></th><th>Da</th><th>Tipo</th><th>AS-path</th><th>Local-pref</th><th>MED</th><th>Origine</th><th>Perché</th></tr>`;
    for (const p of r.bgp) h += `<tr class="${p.best ? 'best' : ''}"><td>${p.best ? '★ best' : (p.valido ? '' : '<span class="koline">non valido</span>')}</td>
      <td><b>${esc(p.chi)}</b> <span class="muted">${esc(p.da || '')}</span></td><td>${esc(p.tipo)}</td><td><code>${esc(p.aspath || '(locale)')}</code></td>
      <td>${p.locpref == null ? '<span class="muted">100</span>' : '<b>' + esc(p.locpref) + '</b>'}</td><td>${p.med == null ? '<span class="muted">-</span>' : esc(p.med)}</td>
      <td>${esc(p.origine || '')}</td><td class="small muted">${esc(p.best ? p.motivo : '')}</td></tr>`;
    h += '</table><div class="muted small">Local-pref più alta vince; a parità, AS-path più corto; poi MED più basso (tra annunci dello stesso AS vicino). Se manca un percorso che ti aspetti, controlla cosa annuncia o filtra il vicino (pulsanti sotto).</div>';
  } else if (I) h += '<div class="muted small">Nessun percorso BGP per questa rete su questo router (rotta interna, connessa o imparata via IGP).</div>';
  if (r.neighbor.length) h += `<div class="riga small">Annunci per vicino: ${r.neighbor.map(ip => `<button class="small ghost" data-nb="${esc(ip)}" data-c="bgp_ricevute">accettati da ${esc(ip)}</button><button class="small ghost" data-nb="${esc(ip)}" data-c="bgp_annunciate">inviati a ${esc(ip)}</button>`).join(' ')}</div>`;
  $('#rRotta').innerHTML = h;
  $('#rRotta').dataset.dev = r.dev;
}
$('#rRotta').addEventListener('click', e => {
  const b = e.target.closest('[data-nb]'); if (!b) return;
  const dev = $('#rRotta').dataset.dev;
  esegui({azione: 'comando', dev, comando: b.dataset.c, ip: b.dataset.nb}, `${dev}: ${b.textContent}`, b);
});

// ---------- tabelle di routing ----------
$('#bTabelle').onclick = async e => {
  const r = await esegui({azione: 'tabelle'}, 'Tabelle di routing ' + S.nome, e.target);
  if (r && r.risultato) mostraTabelle(r.risultato);
};
export function mostraTabelle(r) {
  const SIG = {connected: 'C', bgp: 'B', ospf: 'O', rip: 'R', static: 'S', kernel: 'K'};
  let h = `<div class="scroll"><table class="mat" style="width:auto"><tr><th>router \\ rete</th>${r.reti.map(x => `<th class="v"><span>${esc(x)}</span></th>`).join('')}</tr>`;
  const mancanti = [];
  for (const ro of r.router) {
    h += `<tr><th>${esc(ro)}</th>`;
    if (r.errori[ro]) { h += `<td colspan="${r.reti.length}" class="ko" style="text-align:left">${esc(r.errori[ro])}</td></tr>`; continue; }
    for (const rete of r.reti) {
      const c = r.celle[ro][rete];
      if (c.tipo === 'mancante') { mancanti.push(`${ro}: ${rete}`); h += '<td class="ko" title="nessuna rotta">✘</td>'; continue; }
      if (c.tipo === 'propria') { h += '<td class="self" title="annunciata da questo router (network BGP)">★</td>'; continue; }
      if (c.tipo === 'specifiche') { h += `<td class="mezzo" title="${esc('nessuna rotta per l\'aggregato, ma ci sono le sue sottoreti: ' + c.da)}">~</td>`; continue; }
      const via = c.connessa ? `connessa (${c.dev})` : `via ${c.chi || c.via}`;
      const titolo = `${c.tipo === 'coperta' ? 'coperta da ' + c.da + ', ' : ''}${c.protocollo} ${via}`;
      h += `<td class="${c.tipo === 'esatta' ? 'ok' : 'mezzo'}" title="${esc(titolo)}">${SIG[c.protocollo] || '?'}</td>`;
    }
    h += '</tr>';
  }
  h += `</table></div><div class="small muted" style="margin-top:6px">C connessa · B BGP · O OSPF · R RIP · S statica · <span class="warnline">giallo</span> = coperta da una rotta più ampia · ~ = solo le sottoreti dell'aggregato · ★ = annunciata dal router stesso · passa il mouse su una cella per il next-hop.</div>`;
  h += mancanti.length ? `<div class="koline" style="margin-top:8px">${mancanti.length} reti mancanti</div><details><summary>Elenco</summary><ul class="avvisi">${mancanti.map(x => `<li>${esc(x)}</li>`).join('')}</ul></details>
      <div class="muted small">Può essere voluto (filtri, reti interne "non visibili dall'esterno"); altrimenti manca una network BGP, una ridistribuzione o una sessione.</div>`
    : '<div class="okline" style="margin-top:8px">✔ Ogni router ha una rotta verso tutte le reti del lab.</div>';
  $('#rTabelle').innerHTML = h;
}
