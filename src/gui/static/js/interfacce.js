// Scheda Interfacce: una riga per interfaccia, filtro e confronto con il lab acceso.
import { $, esc, esegui, S } from './comune.js';
import { lato } from './dispositivo.js';
import { scheda } from './main.js';

// ---------- interfacce ----------
export function interfacce() {
  const f = $('#iFiltro').value.trim().toLowerCase(), solo = $('#iSolo').checked, R = S.reali;
  let righe = '', n = 0, sosp = 0;
  for (const d of S.lab.dispositivi) {
    const tutte = d.interfacce.map(it => Object.assign({}, it)).concat(d.loopback.map(ip => ({dev: 'lo', ip, lan: '', vicini: [], igp: [], bgp: [], avvisi: [], costo: null})));
    // sessioni BGP verso IP non sulle LAN del router (es. iBGP verso un router non adiacente)
    const diretti = new Set(d.interfacce.flatMap(it => (it.bgp || []).map(b => b.ip)));
    const altre = ((d.riepilogo || {}).neighbor || []).filter(n => !diretti.has(n.ip));
    if (altre.length) tutte.push({dev: 'BGP non diretto', ip: '', lan: '', vicini: [], igp: [], bgp: altre, avvisi: [], costo: null, extra: true});
    for (const it of tutte) {
      const reale = R && R[d.nome] ? R[d.nome] : null, avvisi = (it.avvisi || []).slice();
      let statoReale = '';
      if (R && !it.extra) {
        if (!reale || reale._errore) statoReale = `<span class="koline">${esc(reale && reale._errore ? 'non raggiungibile' : 'spento')}</span>`;
        else {
          const x = reale[it.dev];
          if (!x) { statoReale = '<span class="koline">interfaccia assente</span>'; avvisi.push('interfaccia assente nel container'); }
          else {
            const ok = !it.ip || x.ip.includes(it.ip), su = x.stato === 'UP' || it.dev === 'lo';
            statoReale = `<span class="${ok && su ? 'okline' : 'koline'}">${esc(x.stato)} ${esc(x.ip.join(', ') || 'senza IP')}</span>`;
            if (!ok) avvisi.push(`nel container l'IP è ${x.ip.join(', ') || 'assente'}`);
            if (!su) avvisi.push('interfaccia giù');
          }
        }
      }
      const testo = [d.nome, it.dev, it.ip, it.lan, ...(it.vicini || []).map(v => v.nome + ' ' + v.ip)].join(' ').toLowerCase();
      if (f && !testo.includes(f)) continue;
      if (solo && !avvisi.length) continue;
      n++; if (avvisi.length) sosp++;
      const igp = (it.igp || []).join(', ') + (it.costo ? ` · costo ${esc(it.costo)}` : '');
      const bgp = (it.bgp || []).map(b => `${b.tipo} ${esc(b.chi)} <span class="muted">AS${esc(b.asn)}${it.extra ? ' · ' + esc(b.ip) : ''}</span>`).join('<br>');
      const pol = (it.bgp || []).flatMap(b => b.policy.map(p => `<b>${esc(p.direzione)}</b> ${esc(p.testo)}`)).join('<br>');
      righe += `<tr class="${avvisi.length ? 'sosp' : ''}"><td><a href="#" data-vai="${esc(d.nome)}">${esc(d.nome)}</a></td><td>${esc(it.dev)}</td><td><code>${esc(it.ip || '-')}</code></td><td>${esc(it.lan)}</td>
        <td>${(it.vicini || []).map(v => `${esc(v.nome)} <span class="muted">${esc(v.ip || '')}</span>`).join('<br>') || (it.dev === 'lo' || it.extra ? '' : '<span class="muted">nessuno</span>')}</td>
        <td>${igp}</td><td>${bgp}</td><td class="small">${pol}</td>${R ? `<td class="small">${statoReale}</td>` : ''}
        <td class="small warnline">${avvisi.map(esc).join('<br>')}</td></tr>`;
    }
  }
  $('#rIntf').innerHTML = `<div class="small muted" style="margin-bottom:6px">${n} interfacce${sosp ? `, <span class="warnline">${sosp} con avvisi</span>` : ''}</div>
    <table class="intf"><tr><th>Dispositivo</th><th>Interf.</th><th>IP</th><th>LAN</th><th>Dall'altra parte</th><th>IGP</th><th>BGP su questa LAN</th><th>Policy</th>${R ? '<th>Nel lab acceso</th>' : ''}<th>Avvisi</th></tr>${righe}</table>`;
}
$('#iFiltro').oninput = interfacce;
$('#iSolo').onchange = interfacce;
$('#rIntf').addEventListener('click', e => {
  const a = e.target.closest('[data-vai]'); if (!a) return;
  e.preventDefault(); S.sel = a.dataset.vai; scheda('topo'); lato();
});
$('#bReali').onclick = async e => {
  const r = await esegui({azione: 'interfacce_reali'}, 'Interfacce reali ' + S.nome, e.target);
  if (r && r.risultato) { S.reali = r.risultato; interfacce(); }
};
