// Scheda Riepilogo e controlli: avvisi automatici, controllo di frr.conf, configurazione per router.
import { $, esc, esegui, S } from './comune.js';
import { diagnosticaLab } from './diagnosi.js';

// ---------- riepilogo e controlli ----------
export function listaAvvisi(titolo, av, okTesto) {
  return `<h3>${titolo}</h3>` + (av.length ? `<ul class="avvisi">${av.map(a => `<li class="warnline">${esc(a)}</li>`).join('')}</ul>` : `<div class="okline">✔ ${okTesto}</div>`);
}
// controllo configurazione FRR: nomi (dai file, sempre) + sintassi (vtysh --dryrun, lab acceso)
export function righeFrr() {
  const righe = [];
  for (const d of S.lab.dispositivi) {
    for (const x of d.riferimenti_frr || []) righe.push(Object.assign({router: d.nome}, x));
    const s = S.sintassi && S.sintassi[d.nome];
    if (s && s.righe) for (const x of s.righe) righe.push(Object.assign({router: d.nome}, x));
    if (s && s.errore) righe.push({router: d.nome, riga: '', testo: '', gravita: 'avviso', messaggio: 'sintassi non controllata: ' + s.errore});
  }
  return righe.sort((a, b) => a.router.localeCompare(b.router) || (a.riga || 0) - (b.riga || 0));
}
export function htmlControlloFrr() {
  const righe = righeFrr();
  let h = `<div class="card"><h2>Controllo configurazione FRR</h2>
    <div class="muted small">FRR non segnala gli errori di frr.conf: salta le righe che non capisce, e una route-map o prefix-list inesistente su un neighbor
      blocca tutte le rotte con la sessione comunque Established. I <b>nomi</b> (route-map, prefix-list, access-list) sono controllati dai file, sempre;
      la <b>sintassi</b> con <code>vtysh --dryrun</code> sul file attuale (serve il lab acceso, il router non viene modificato).</div>
    <div class="riga"><button id="bSintassi">Controlla la sintassi (lab acceso)</button>
      <span class="small ${S.sintassi ? 'okline' : 'muted'}">${S.sintassi ? 'sintassi controllata' : 'sintassi non ancora controllata'}</span></div>`;
  if (!righe.length) h += `<div class="okline">✔ Nessun problema${S.sintassi ? '' : ' nei nomi'}.</div>`;
  else h += `<table><tr><th>Router</th><th>Riga</th><th>Testo</th><th>Problema</th></tr>${righe.map(x =>
    `<tr class="${x.gravita === 'errore' ? 'sosp' : ''}"><td>${esc(x.router)}</td><td>${esc(x.riga)}</td><td><code>${esc(x.testo)}</code></td>
     <td class="small ${x.gravita === 'errore' ? 'koline' : 'warnline'}">${x.gravita === 'errore' ? '✘ ' : '⚠ '}${esc(x.messaggio)}${x.suggerimento && x.suggerimento !== x.messaggio ? `<div class="muted">${esc(x.suggerimento)}</div>` : ''}</td></tr>`).join('')}</table>
    <div class="muted small">✘ = da correggere; ⚠ = da controllare (una lista definita e mai usata è spesso lo stesso nome scritto in due modi).</div>`;
  return h + '</div>';
}
$('#t-riep').addEventListener('click', async e => {
  if (e.target.id !== 'bSintassi') return;
  const r = await esegui({azione: 'sintassi_frr'}, 'Sintassi frr.conf ' + S.nome, e.target);
  if (r && r.risultato) { S.sintassi = r.risultato; riepilogo(); }
});
export function riepilogo() {
  const L = S.lab, r = L.dispositivi.filter(d => d.riepilogo), altri = L.dispositivi.filter(d => !d.riepilogo);
  // gli avvisi sui nomi di frr.conf sono nella card "Controllo configurazione FRR"
  const config = L.avvisi_config.filter(a => !/\(frr\.conf riga \d+\)/.test(a));
  let h = `<div class="card"><h2>Controlli automatici</h2>${listaAvvisi('Topologia (LAN e subnet)', L.avvisi_topologia, 'LAN e subnet coerenti.')}
    <div style="height:8px"></div>${listaAvvisi('Dimenticanze tipiche', config, 'Nessuna dimenticanza trovata.')}
    <div class="muted small" style="margin-top:8px">Sono suggerimenti: confrontali sempre con il testo dell'esercizio.</div></div>`;
  h += htmlControlloFrr();
  h += `<div class="card"><h2>Diagnostica di frr.conf</h2><p class="muted small">Refusi nei comandi, comandi nel blocco sbagliato, reti scritte male,
    route-map e prefix-list usate ma non definite, demoni non abilitati, avvio di FRR o apache2 mancante, gateway. Le correzioni si applicano dal pannello del dispositivo in modalità Modifica ("Diagnostica") o con le Opzioni 15.</p>
    <div class="btns"><button id="bDiagnosi" type="button">Esegui la diagnostica</button></div><div id="rDiagnosi"></div></div>`;
  h += '<div class="griglia">';
  for (const d of r) { const R = d.riepilogo;
    h += `<div class="card"><div class="riga" style="margin:0 0 6px"><h3 style="margin:0">${esc(d.nome)}</h3>${d.asn ? `<span class="badge">AS${esc(d.asn)}</span>` : ''}<span class="muted small">${esc(d.demoni.join(' '))}</span></div><table>`;
    for (const g of R.igp) h += `<tr><th>${g.protocollo}</th><td>${esc(g.voci.join(', ') || '-')}${g.redistribute.length ? `<div class="small muted">redistribute ${esc(g.redistribute.join(', '))}</div>` : ''}${g.auto_cost ? `<div class="small muted">auto-cost reference-bandwidth ${esc(g.auto_cost)}</div>` : ''}</td></tr>`;
    if (R.costi.length) h += `<tr><th>Costo OSPF</th><td>${esc(R.costi.join(', '))}</td></tr>`;
    if (d.demoni.includes('bgpd')) {
      h += `<tr><th>Network BGP</th><td>${esc(R.bgp_networks.join(', ') || '-')}</td></tr>`;
      if (R.redistribute_bgp.length) h += `<tr><th>Redistribute in BGP</th><td>${esc(R.redistribute_bgp.join(', '))}</td></tr>`;
    }
    h += '</table>';
    if (R.neighbor.length) {
      h += '<table style="margin-top:8px"><tr><th>Neighbor</th><th>Chi</th><th>Tipo</th><th>Policy</th></tr>';
      for (const n of R.neighbor) h += `<tr><td><code>${esc(n.ip)}</code></td><td>${esc(n.chi)}<div class="small muted">AS${esc(n.asn)}</div></td><td>${n.tipo}</td><td>${n.policy.length ? n.policy.map(p => `<div><b>${esc(p.direzione)}</b>: ${esc(p.testo)}</div>`).join('') : '<span class="muted">nessuna</span>'}</td></tr>`;
      h += '</table>';
    }
    h += '</div>';
  }
  h += '</div>';
  if (altri.length) {
    h += `<div class="card"><h2>Host e server</h2><table><tr><th>Nome</th><th>Tipo</th><th>IP</th><th>Gateway</th><th>Nameserver</th><th>Zone DNS</th></tr>`;
    for (const d of altri) h += `<tr><td>${esc(d.nome)}</td><td>${esc(d.tipo)}</td><td>${esc(d.interfacce.map(i => i.dev + ' ' + (i.ip || '-')).join(', '))}</td><td>${esc(d.gateway || '-')}</td><td>${esc(d.nameserver.join(', ') || '-')}</td><td>${esc(d.zone.map(z => z[0] + ' (' + z[1] + ')').join(', '))}</td></tr>`;
    h += '</table></div>';
  }
  h += `<div class="card"><h2>LAN</h2><table><tr><th>LAN</th><th>Subnet</th><th>Dispositivi</th></tr>${L.lan.map(l => `<tr><td>${esc(l.nome)}</td><td>${esc(l.subnet || '-')}</td><td>${esc(l.membri.join(', '))}</td></tr>`).join('')}</table></div>`;
  $('#t-riep').innerHTML = h;
  $('#bDiagnosi').onclick = e => diagnosticaLab($('#rDiagnosi'), e.target);
}
