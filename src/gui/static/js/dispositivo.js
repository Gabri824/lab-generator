// Pannello del dispositivo accanto alla topologia: interfacce, file e comandi Kathará.
import { $, api, azione, errore, esc, esegui, S } from './comune.js';
import { percorso } from './test.js';
import { ridisegna } from './topologia.js';

// ---------- pannello del dispositivo ----------
export const ETICHETTE = {bgp_summary: 'show ip bgp summary', bgp: 'show ip bgp', route: 'show ip route', ospf_nei: 'show ip ospf neighbor', ospf_if: 'show ip ospf interface', rip: 'show ip rip', running: 'show running-config', ip_route: 'ip route', ip_addr: 'ip -br addr', apache_stato: 'stato apache2', apache_avvia: 'avvia apache2'};
export function dispositivo(nome) { return S.lab && S.lab.dispositivi.find(d => d.nome === nome); }
export function lato() {
  const d = dispositivo(S.sel), el = $('#side');
  if (!d) {
    el.innerHTML = `<h3>Dispositivi</h3><div class="muted small">Clic su un dispositivo nella topologia per vedere la sua configurazione e lanciare i comandi.</div>
      <table style="margin-top:8px"><tr><th>Nome</th><th>Tipo</th><th>AS</th></tr>${S.lab.dispositivi.map(x => `<tr><td><a href="#" data-sel="${esc(x.nome)}">${esc(x.nome)}</a></td><td>${esc(x.tipo)}</td><td>${esc(x.asn || '')}</td></tr>`).join('')}</table>`;
    return;
  }
  const cmd = [];
  if (d.tipo === 'router') {
    if (d.demoni.includes('bgpd')) cmd.push('bgp_summary', 'bgp');
    cmd.push('route');
    if (d.demoni.includes('ospfd')) cmd.push('ospf_nei', 'ospf_if');
    if (d.demoni.includes('ripd')) cmd.push('rip');
    cmd.push('running');
  }
  cmd.push('ip_route', 'ip_addr');
  const web = S.lab.web || {server: [], bersagli: [], client: []};
  if (web.server.some(x => x.nome === d.nome)) cmd.push('apache_stato', 'apache_avvia');
  el.innerHTML = `<div class="riga" style="margin:0"><h3>${esc(d.nome)}</h3><span class="badge">${esc(d.tipo)}</span>${d.asn ? `<span class="badge">AS${esc(d.asn)}</span>` : ''}<div class="sp"></div><a href="#" data-sel="">elenco</a></div>
    <table><tr><th>Interf.</th><th>IP</th><th>LAN</th></tr>${d.interfacce.map(i => `<tr><td>${esc(i.dev)}</td><td>${esc(i.ip || '-')}</td><td>${esc(i.lan)}</td></tr>`).join('')}
    ${d.loopback.map(ip => `<tr><td>lo</td><td>${esc(ip)}</td><td></td></tr>`).join('')}</table>
    ${d.gateway ? `<div class="small" style="margin-top:6px">Gateway: <code>${esc(d.gateway)}</code></div>` : ''}
    ${d.nameserver.length ? `<div class="small">Nameserver: <code>${esc(d.nameserver.join(', '))}</code></div>` : ''}
    ${d.demoni.length ? `<div class="small">Demoni FRR: ${esc(d.demoni.join(', '))}</div>` : ''}
    <div class="btns">${cmd.map(c => `<button class="small ghost" data-cmd="${c}">${esc(ETICHETTE[c])}</button>`).join('')}</div>
    <div class="riga"><input id="sIp" list="ipList" placeholder="IP" size="15"><button class="small" data-cmd="ping">ping</button><button class="small" data-cmd="traceroute">traceroute</button><button class="small ghost" id="sPerc">percorso sulla mappa</button></div>
    ${web.client.includes(d.nome) ? `<div class="riga"><input id="sWeb" list="webList" placeholder="${esc(web.bersagli.length ? 'IP o nome del server web' : 'nessun server web nel lab')}" size="20" aria-label="Pagina web da aprire con links"><button class="small" id="sLinks" title="links -dump http://…/ (lab acceso)">links</button></div>` : ''}
    <div class="btns"><button class="small" id="sTerm">Apri terminale (kathara connect)</button></div>
    <div id="sTermMsg" class="small"></div>
    <div id="sFile" class="muted small">Caricamento dei file…</div>`;
  api('/api/file?lab=' + encodeURIComponent(S.nome) + '&dev=' + encodeURIComponent(d.nome)).then(fs => {
    $('#sFile').outerHTML = '<div>' + fs.map(f => `<details><summary>${esc(f.file)}</summary><pre class="file">${esc(f.testo)}</pre></details>`).join('') + '</div>';
  }).catch(e => { $('#sFile').textContent = String(e.message); });
}
$('#side').addEventListener('click', async e => {
  const s = e.target.closest('[data-sel]');
  if (s) { e.preventDefault(); S.sel = s.dataset.sel || null; ridisegna(); lato(); return; }
  const b = e.target.closest('[data-cmd]');
  if (b) {
    const c = b.dataset.cmd, dati = {azione: 'comando', dev: S.sel, comando: c};
    if (c === 'ping' || c === 'traceroute') { dati.ip = $('#sIp').value.trim(); if (!dati.ip) { $('#sIp').focus(); return; } }
    esegui(dati, S.sel + ': ' + (ETICHETTE[c] || c + ' ' + dati.ip), b);
    return;
  }
  if (e.target.id === 'sLinks') {
    const ind = $('#sWeb').value.trim(); if (!ind) { $('#sWeb').focus(); return; }
    esegui({azione: 'pagina_web', dev: S.sel, indirizzo: ind}, `${S.sel}: links ${ind}`, e.target);
    return;
  }
  if (e.target.id === 'sPerc') { const ip = $('#sIp').value.trim(); if (!ip) { $('#sIp').focus(); return; } percorso(S.sel, ip, e.target); }
  if (e.target.id === 'sTerm') {
    try { const r = await azione({azione: 'terminale', dev: S.sel});
      $('#sTermMsg').innerHTML = `<div class="${r.ok ? 'okline' : 'warnline'}">${esc(r.messaggio)}</div><code>${esc(r.comando)}</code>`;
    } catch (err) { errore(err); }
  }
});
