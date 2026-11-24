// Checklist "Pronto per la consegna" (parte pura, senza pagina: si prova con Node, tests/js/consegna.test.mjs).
// `controlliConsegna` riceve il lab (/api/lab), la diagnostica {dispositivo: [problemi]} e lo stato;
// `htmlConsegna` la mette in forma di semaforo.
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

const SEGNO = {ok: '✔', avviso: '⚠', ko: '✘', nd: '·'};

export function controlliConsegna({lab, diagnosi = null, acceso = false, ridistribuzione = null, nomeArchivio = ''}) {
  const out = [];
  const router = lab.dispositivi.filter(d => d.riepilogo);
  const conDefault = router.filter(d => (d.riepilogo.default || []).length);
  out.push(conDefault.length
    ? {id: 'default', stato: 'avviso', titolo: 'Default route presenti', dettaglio: conDefault.map(d => `${d.nome} (${d.riepilogo.default.join('; ')})`).join(' · ') + '. Controlla che il testo le chieda.'}
    : {id: 'default', stato: 'ok', titolo: 'Nessuna default route non richiesta'});

  const errori = [];
  for (const d of lab.dispositivi) {
    for (const x of d.riferimenti_frr || []) if (x.gravita === 'errore') errori.push(`${d.nome} riga ${x.riga || '?'}: ${x.messaggio}`);
    for (const x of (diagnosi && diagnosi[d.nome]) || []) if (x.gravita === 'errore') errori.push(`${d.nome} ${x.riga ? 'riga ' + x.riga + ': ' : ''}${x.messaggio}`);
  }
  const unici = [...new Set(errori)];
  out.push(unici.length
    ? {id: 'frr', stato: 'ko', titolo: `${unici.length} ${unici.length === 1 ? 'errore' : 'errori'} in frr.conf e riferimenti`, dettaglio: unici.slice(0, 6).join(' · ') + (unici.length > 6 ? ' …' : '')}
    : {id: 'frr', stato: diagnosi ? 'ok' : 'nd', titolo: diagnosi ? 'Nessun errore di frr.conf né riferimento non definito' : 'Diagnostica non ancora eseguita'});

  const senzaAuto = router.filter(d => d.riepilogo.costi.length && !d.riepilogo.igp.some(g => g.protocollo === 'OSPF' && g.auto_cost));
  out.push(senzaAuto.length
    ? {id: 'auto', stato: 'avviso', titolo: 'Costi OSPF espliciti senza auto-cost reference-bandwidth 100', dettaglio: senzaAuto.map(d => d.nome).join(', ') + '. Senza, i costi di default non sono quelli del testo (Opzioni 10).'}
    : {id: 'auto', stato: 'ok', titolo: 'Costi OSPF coerenti con auto-cost'});

  if (!acceso) out.push({id: 'redistribuzione', stato: 'nd', titolo: 'Ridistribuzione BGP → IGP: lab spento', dettaglio: 'Si controlla a lab acceso (Test → Sessioni).'});
  else if (!ridistribuzione) out.push({id: 'redistribuzione', stato: 'nd', titolo: 'Ridistribuzione BGP → IGP non ancora letta', dettaglio: 'Test → Leggi le sessioni.'});
  else {
    const spente = ridistribuzione.filter(x => !x.ok);
    out.push(spente.length
      ? {id: 'redistribuzione', stato: 'ko', titolo: `${spente.length} ridistribuzioni non attive`, dettaglio: spente.map(x => `${x.router} (${x.igp})`).join(', ') + '. Test → Riapplica.'}
      : {id: 'redistribuzione', stato: 'ok', titolo: 'Ridistribuzione BGP → IGP attiva'});
  }

  out.push(lab.xml
    ? {id: 'xml', stato: 'avviso', titolo: "Nel lab c'è l'XML del generatore", dettaglio: "L'archivio creato da qui lo esclude; toglilo comunque dalla cartella."}
    : {id: 'xml', stato: 'ok', titolo: "Nessun file XML nella cartella del lab"});

  const nome = String(nomeArchivio || '').trim().replace(/\.(tar\.gz|zip)$/, '');
  out.push(nome && nome !== lab.nome
    ? {id: 'nome', stato: 'avviso', titolo: `Archivio "${nome}" diverso dalla cartella "${lab.nome}"`, dettaglio: 'Se il testo chiede <cognome><nome> per entrambi, rinomina la cartella o crea il lab con quel nome.'}
    : {id: 'nome', stato: 'ok', titolo: 'Nome della cartella e dell\'archivio uguali', dettaglio: 'Ricorda: il testo chiede <cognome><nome>.'});
  return out;
}

export function htmlConsegna(controlli) {
  const peggio = controlli.some(c => c.stato === 'ko') ? 'ko' : controlli.some(c => c.stato === 'avviso') ? 'avviso' : controlli.some(c => c.stato === 'nd') ? 'nd' : 'ok';
  const classe = {ok: 'okline', avviso: 'warnline', ko: 'koline', nd: 'muted'};
  const riassunto = {ok: 'Tutto a posto.', avviso: 'Da controllare (non sono errori sicuri).', ko: 'Ci sono errori da correggere.', nd: 'Alcuni controlli non sono ancora possibili.'}[peggio];
  return `<h2>Pronto per la consegna <span class="${classe[peggio]}">${SEGNO[peggio]}</span></h2>
    <div class="small ${classe[peggio]}">${riassunto}</div>
    <ul class="consegna">${controlli.map(c => `<li class="${classe[c.stato]}"><span aria-hidden="true">${SEGNO[c.stato]}</span>
      <span><b>${esc(c.titolo)}</b>${c.dettaglio ? `<div class="small muted">${esc(c.dettaglio)}</div>` : ''}</span></li>`).join('')}</ul>
    <div class="btns"><button type="button" class="ghost small" data-consegna="ricontrolla">Ricontrolla</button></div>`;
}

