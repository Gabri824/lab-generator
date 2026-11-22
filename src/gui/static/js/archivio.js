// Scheda Archivio: archivio per la consegna, senza l'XML del generatore.
import { $, azione, esc, S } from './comune.js';
import { registro } from './registro.js';

// ---------- avviso sul nome dell'archivio ----------
export function avvisoArchivio() {
  const nome = $('#aNome').value.trim().replace(/\.(tar\.gz|zip)$/, ''), a = $('#aAvviso');
  a.hidden = !nome || nome === S.nome;
  if (!a.hidden) a.innerHTML = `Dentro l'archivio la cartella si chiamerà <code>${esc(S.nome)}</code>, non <code>${esc(nome)}</code>.
    Se il testo chiede che cartella e archivio si chiamino <code>&lt;cognome&gt;&lt;nome&gt;</code>, crea il lab con quel nome (o rinomina la cartella del lab).`;
}
$('#aNome').oninput = avvisoArchivio;

// ---------- archivio ----------
$('#bArchivio').onclick = async e => {
  e.target.disabled = true;
  try {
    const fmt = document.querySelector('input[name=aFmt]:checked').value;
    const r = await azione({azione: 'archivio', nome: $('#aNome').value.trim(), formato: fmt});
    $('#rArchivio').innerHTML = `<div class="okline">✔ Creato: <code>${esc(r.percorso)}</code> (${r.file.length} file)</div>
      <div class="small">Esclusi: ${r.esclusi.map(x => '<code>' + esc(x) + '</code>').join(', ')}${r.esclusi.some(x => x.endsWith('/shared')) ? ' (cartella vuota creata da Kathará)' : ''}</div>
      <div class="riga"><a href="${esc(r.scarica)}"><button class="small">Scarica</button></a></div>
      <div class="small">Comando equivalente (dalla cartella dei lab):</div><pre class="file">${esc(r.comando)}</pre>
      <details><summary>File nell'archivio</summary><pre class="file">${esc(r.file.join('\n'))}</pre></details>`;
    if (S.tab === 'reg') registro();
  } catch (err) { $('#rArchivio').innerHTML = `<div class="koline">${esc(err.message)}</div>`; }
  finally { e.target.disabled = false; }
};
