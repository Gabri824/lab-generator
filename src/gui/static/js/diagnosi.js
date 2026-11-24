// Diagnostica di frr.conf (core/frr_autofix.py) nella
// GUI: pannello del dispositivo in modalità Modifica (problemi + pulsanti delle correzioni, ognuna
// un'operazione con anteprima e Annulla), card del Riepilogo, problemi sotto "File a righe".
// I risultati restano in S.lab.diagnosi, così il livello Avvisi mette il "!" sui dispositivi.
import { azione, esc, S } from './comune.js';
import { lato } from './dispositivo.js';
import { apriMenu, apriOperazione } from './modifica.js';
import { ridisegna } from './topologia.js';

const LETTERE = 'abcdefghij';

export async function problemiDi(nome) {
  const p = (await azione({azione: 'opzioni', lab: S.nome, operazione: 'correggi_frr', parametri: {dispositivo: nome}})).opzioni || [];
  S.lab.diagnosi = Object.assign(S.lab.diagnosi || {}, {[nome]: p});
  return p;
}

export function htmlProblemi(problemi, conCorrezioni = true) {
  if (!problemi.length) return '<div class="okline small">Nessun problema trovato.</div>';
  return `<ol class="small diagnosi">${problemi.map(x => `<li><span class="${x.gravita === 'errore' ? 'koline' : 'warnline'}">${esc(x.gravita)}</span>
    <code>${esc(x.file)}${x.riga ? ' riga ' + x.riga : ''}</code>: ${esc(x.messaggio)}
    ${conCorrezioni && x.correzioni.length ? `<div class="muted">Correzioni: ${x.correzioni.map(c => esc(c.etichetta)).join(' · ')}</div>` : ''}</li>`).join('')}</ol>`;
}

// passo del pannello: il menu dei problemi con un pulsante per ogni correzione ({menu}, per conf.poi)
export async function passoDiagnosi(nome) {
  const problemi = await problemiDi(nome);
  ridisegna();
  const sicuri = (await azione({azione: 'opzioni', lab: S.nome, operazione: 'correggi_frr_sicuri', parametri: {dispositivo: nome}})).opzioni || [];
  const voci = [];
  if (sicuri.length) voci.push({
    testo: `Applica i ${sicuri.length} fix sicuri di frr.conf`, aiuto: sicuri.map(s => (s.riga ? `riga ${s.riga}: ` : '') + s.etichetta).join(' · '),
    fai: () => apriOperazione({operazione: 'correggi_frr_sicuri', titolo: `Fix sicuri di ${nome}`, subito: true, poi: () => passoDiagnosi(nome),
      fissi: {dispositivo: nome}, spiegazione: 'Solo le correzioni di cui il programma è sicuro (non le proposte, non le "info"); l\'anteprima mostra ogni riga.'}),
  });
  problemi.forEach((x, k) => x.correzioni.forEach((c, j) => voci.push({
    testo: `${k + 1}${LETTERE[j]}) ${c.etichetta}`, aiuto: x.messaggio, fai: () => correggi(nome, x, c, j)})));
  return {menu: {
    titolo: `Diagnostica di ${nome}`,
    spiegazione: problemi.length
      ? problemi.map((x, k) => `${k + 1}. ${x.file}${x.riga ? ' riga ' + x.riga : ''}: ${x.messaggio}`).join(' · ')
        + ' — Ogni correzione mostra prima le righe che cambiano e si annulla con "Annulla modifica".'
      : `Nessun problema trovato in ${nome} (frr.conf, daemons, startup, gateway, nome).`,
    voci,
  }};
}

export async function diagnostica(nome) {
  const p = await passoDiagnosi(nome);
  apriMenu(p.menu);
}

function correggi(nome, x, c, j) {
  const poi = () => passoDiagnosi(nome);
  if (c.rimando) {
    apriOperazione({operazione: c.rimando.operazione, titolo: c.etichetta, subito: true, fissi: c.rimando.parametri, poi,
      spiegazione: `${x.messaggio} Correzione con l'operazione "${c.rimando.operazione}", come dalle altre azioni.`});
    return;
  }
  apriOperazione({operazione: 'correggi_frr', titolo: c.etichetta, subito: true, poi,
    fissi: {dispositivo: nome, regola: x.regola, riga: x.riga, messaggio: x.messaggio, correzione: j},
    spiegazione: `${x.file}${x.riga ? ' riga ' + x.riga : ''}: ${x.messaggio}`});
}

// card del Riepilogo: diagnostica di tutti i dispositivi con frr.conf, solo da leggere
export async function diagnosticaLab(el, bottone) {
  bottone.disabled = true;
  el.innerHTML = '<div class="muted small">Diagnostica in corso…</div>';
  const nomi = S.lab.dispositivi.filter(d => d.demoni.length || d.tipo !== 'router').map(d => d.nome);
  let h = '', tot = 0;
  for (const n of nomi) {
    try {
      const p = await problemiDi(n);
      if (p.length) { tot += p.length; h += `<h4 class="ed-sotto">${esc(n)}</h4>${htmlProblemi(p)}`; }
    } catch (e) { h += `<div class="koline small">${esc(n)}: ${esc(e.message)}</div>`; }
  }
  el.innerHTML = (tot ? `<div class="warnline">${tot} ${tot === 1 ? 'problema' : 'problemi'}: per correggerli, modalità Modifica → pannello del dispositivo → "Diagnostica" (o Opzioni 15 nel terminale).</div>` : '<div class="okline">Nessun problema trovato.</div>') + h;
  bottone.disabled = false;
  ridisegna(); lato();
}
