// Pagina di prova dei componenti comuni (static/prova.html).
import { $, azione, ErroreServer } from './comune.js';
import { htmlAnteprima, htmlConflitto } from './componenti/diff.js';
import { collegaErrori, htmlErrori, segnaCampi } from './componenti/errori.js';
import { creaLivelli } from './componenti/livelli.js';
import { creaPannello } from './componenti/proprieta.js';
import { creaBarraStoria, Storia } from './componenti/storia.js';

// forma della risposta di 'anteprima' (api.py)
const ESEMPIO = {
  titolo: 'Costo OSPF di r1 eth1: 50',
  note: ["Il costo vale solo per OSPF: controlla con Test -> Verifica percorso."],
  file: [
    {file: 'r1/etc/frr/frr.conf', stato: 'modificato', righe: [
      {segno: '-', numero: 12, testo: ' network 20.20.0.0/16 area 0.0.0.0'},
      {segno: '+', numero: 12, testo: ' network 20.20.1.0/24 area 0.0.0.0'},
      {segno: '+', numero: 13, testo: ' network 20.20.2.0/24 area 0.0.0.0'},
      {segno: '+', numero: 20, testo: 'interface eth1'},
      {segno: '+', numero: 21, testo: '    ospf cost 50'}]},
    {file: 'core1/etc/frr/frr.conf', stato: 'spostato', da: 'as40r1/etc/frr/frr.conf', righe: []},
    {file: 'pc2.startup', stato: 'nuovo', righe: [{segno: '+', numero: 1, testo: 'ip address add 20.20.1.20/24 dev eth0'}]},
  ],
};
$('#pAnt').onclick = () => { $('#rAnt').innerHTML = htmlAnteprima(ESEMPIO); };
$('#pVuota').onclick = () => { $('#rAnt').innerHTML = htmlAnteprima({titolo: 'IP di as10r1 eth1', file: [], vuoto: 'Nessuna modifica.'}); };
$('#pConf').onclick = () => { $('#rAnt').innerHTML = htmlConflitto(new ErroreServer(409, {errore: 'conflitto', file: ['r1/etc/frr/frr.conf']})); };

// pannello proprietà di un router; il controllo usa davvero valida_lab (non scrive nulla)
const pannello = creaPannello($('#rProp'), {
  titolo: 'Router r1',
  schema: [
    {nome: 'nome', etichetta: 'Nome', obbligatorio: true, campo: 'r1.name', aiuto: 'Solo minuscole, cifre e _ (regola di Kathará).'},
    {nome: 'asn', etichetta: 'AS', tipo: 'numero', campo: 'r1.asn'},
    {nome: 'ip', etichetta: 'IP di eth0', obbligatorio: true, segnaposto: '10.0.0.1/30', campo: 'r1.interfaces[0].ip'},
    {nome: 'proto', etichetta: 'Protocollo', tipo: 'scelta', opzioni: [['ospf', 'OSPF'], ['rip', 'RIP'], ['bgp', 'BGP']]},
    {nome: 'stub', etichetta: 'Area stub', tipo: 'si_no'},
  ],
  valori: {nome: 'r1', asn: '', ip: '10.0.0.300/30', proto: 'ospf'},
});
$('#pControlla').onclick = async () => {
  const errori = pannello.controlla();
  if (!pannello.mostraErrori(errori)) return;
  const v = pannello.valori();
  const modello = {routers: {[v.nome]: {protocols: [v.proto], asn: String(v.asn || ''), interfaces: [{name: 'eth0', lan: 'A', ip: v.ip}]}}, hosts: [], wwws: []};
  try {
    const r = await azione({azione: 'valida_lab', modello});
    $('#rErr').innerHTML = htmlErrori(r.problemi);
    segnaCampi($('#rProp'), r.problemi);
  } catch (e) { $('#rErr').innerHTML = `<div class="koline">${e.message}</div>`; }
};
collegaErrori($('#rErr'), campo => [...document.querySelectorAll('#rProp [data-campo]')].find(x => x.dataset.campo === campo));

const livelli = creaLivelli($('#rLiv'), [
  {id: 'ip', etichetta: 'Indirizzi', attivo: true}, {id: 'bgp', etichetta: 'Sessioni BGP', attivo: true},
  {id: 'policy', etichetta: 'Policy'}, {id: 'costi', etichetta: 'Costi OSPF'}, {id: 'dns', etichetta: 'DNS'},
], a => { $('#rLivStato').textContent = 'Accesi: ' + ([...a].join(', ') || 'nessuno'); });
$('#rLivStato').textContent = 'Accesi: ' + [...livelli.attivi()].join(', ');

const storia = new Storia({routers: []});
const mostra = s => { $('#rStoStato').textContent = JSON.stringify(s, null, 1); };
creaBarraStoria($('#rSto'), storia, mostra);
$('#pAggiungi').onclick = () => { const s = storia.stato; s.routers.push('r' + (s.routers.length + 1)); storia.fai(s); mostra(storia.stato); };
mostra(storia.stato);
