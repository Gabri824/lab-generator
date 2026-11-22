// Scheda Registro: operazioni e comandi eseguiti dalla GUI.
import { $, api, errore, esc } from './comune.js';

// ---------- registro ----------
export async function registro() {
  try {
    const r = await api('/api/registro');
    $('#rRegistro').innerHTML = r.length ? `<table><tr><th>Ora</th><th>Operazione</th><th>Comando</th><th>Esito</th></tr>${r.slice().reverse().map(x =>
      `<tr><td>${esc(x.ora)}</td><td>${esc(x.operazione)}</td><td><code>${esc(x.comando)}</code></td><td class="${x.esito.startsWith('OK') ? 'okline' : (x.esito === 'in corso' ? 'warnline' : 'koline')}">${esc(x.esito)}</td></tr>`).join('')}</table>` : '<div class="muted">Nessuna operazione.</div>';
  } catch (e) { errore(e); }
}
