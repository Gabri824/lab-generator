// Checklist "Pronto per la consegna" a semaforo nelle schede Riepilogo e Archivio: mette insieme controlli
// che il programma già fa (dimenticanze, diagnostica di frr.conf, costi OSPF, ridistribuzione, XML, nome
// dell'archivio). I controlli sono in consegna_controlli.js; qui la pagina.
import { $, S } from './comune.js';
import { controlliConsegna, htmlConsegna } from './consegna_controlli.js';
import { problemiDi } from './diagnosi.js';

let giro = 0;
// riempie gli elementi (#consRiep, #consArch): subito i controlli dai dati già letti, poi la diagnostica
export async function aggiornaConsegna() {
  if (!S.lab) return;
  const mio = ++giro;
  const el = [...document.querySelectorAll('.consegna-card')];
  const stato = diagnosi => controlliConsegna({lab: S.lab, diagnosi, acceso: (S.stato[S.nome] || []).length > 0,
    ridistribuzione: S.sessioni && S.sessioni.ridistribuzione || null, nomeArchivio: $('#aNome').value});
  const disegna = diagnosi => el.forEach(e => { e.innerHTML = htmlConsegna(stato(diagnosi)); });
  disegna(null);
  const diag = {};
  for (const d of S.lab.dispositivi.filter(x => x.demoni.length || x.tipo !== 'router')) {
    try { diag[d.nome] = await problemiDi(d.nome); } catch (e) { diag[d.nome] = []; }
    if (mio !== giro) return;
  }
  disegna(diag);
}

$('#aNome').addEventListener('change', () => aggiornaConsegna());
document.addEventListener('click', e => { if (e.target.closest('[data-consegna]')) aggiornaConsegna(); });
