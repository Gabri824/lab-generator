// Modalità Modifica, fase 5.2: dispositivi e indirizzi dal disegno. Clic su un'interfaccia, su una
// LAN o su un dispositivo apre le sue azioni; ognuna è un'operazione del motore (stessa calcola_X
// del terminale, Opzioni 11 e 13) con modulo, anteprima, applica e annulla (modifica.js).
import { $, api, azione, esc, S } from './comune.js';
import { dispositivo, lato } from './dispositivo.js';
import { apriMenu, apriOperazione, autoCost, costoOspf, togliCosto } from './modifica.js';
import { assegnati, datiDispositivo, ipDelModulo, ipUsati, listaReti, nomeLibero, parametriDefaultBgp, parametriDefaultIgp,
  primoIpLibero, prossimaLoopback, reteNormalizzata, retiEbgp, stessaParteHost, subnetDellaLan, vicinatoDellaLan } from './proposte.js';
import { diagnostica, htmlProblemi, problemiDi } from './diagnosi.js';
import { menuPolicy, policyVersoNeighbor, vociPolicyLan } from './modifica_policy.js';
import { htmlPulsantePercorso, iniziaPercorso, puntoPercorso } from './percorso_voluto.js';
import { gesti } from './topologia.js';

const TIPI = {router: 'router', host: 'host', www: 'server web', dns: 'server DNS'};
const reti = t => String(t || '').split(/[\s,;]+/).filter(Boolean);
const opzioni = async (operazione, parametri) => (await azione({azione: 'opzioni', operazione, parametri})).opzioni;
function avviso(t) { S.op = null; S.esito = {avviso: t}; S.sel = null; lato(); }
const interfaccia = (d, dev) => d.interfacce.find(x => x.dev === dev) || {dev, lan: '', ip: ''};

// ---------- interfaccia ----------
function menuInterfaccia(dev, iface) {
  const d = dispositivo(dev); if (!d) return;
  const it = interfaccia(d, iface);
  const ospf = d.tipo === 'router' && d.demoni.includes('ospfd');
  const voci = [
    {testo: 'Cambia IP', fai: () => cambiaIp(d, it)},
    {testo: "Sposta su un'altra LAN", fai: () => spostaInterfaccia(d, it)},
  ];
  if (ospf) voci.push({testo: it.costo ? `Costo OSPF (adesso ${it.costo})` : 'Costo OSPF', fai: () => costoOspf(dev, iface)});
  if (ospf && it.costo) voci.push({testo: 'Togli il costo OSPF', fai: () => togliCosto(dev, iface)});
  voci.push({testo: "Togli l'interfaccia", pericolo: true, fai: () => togliInterfaccia(d, it)});
  apriMenu({titolo: `${dev} ${iface}`, spiegazione: `LAN ${it.lan}${it.ip ? ' · ' + it.ip : ' · senza IP'}`, voci});
}

function cambiaIp(d, it) {
  if (!it.ip) return avviso(`${d.nome} ${it.dev} non ha un IP nello startup: aggiungilo con "File a righe".`);
  apriOperazione({
    operazione: 'ip_interfaccia', titolo: `IP di ${d.nome} ${it.dev}`,
    spiegazione: `Adesso ${it.ip} (LAN ${it.lan}). Basta l'ultimo numero: il resto viene dalla subnet. Il nuovo IP prende il posto del vecchio ovunque compare (gateway, neighbor BGP, ...).`,
    fissi: {dispositivo: d.nome, dev: it.dev},
    schema: [{nome: 'nuovo', etichetta: 'Nuovo IP', obbligatorio: true, segnaposto: 'es. 5 oppure 10.0.0.5/24'},
             {nome: 'solo_questo', etichetta: 'Se esce dalla rete della LAN, cambia solo questo (senza rinumerare la LAN)', tipo: 'si_no'}],
    valori: {nuovo: it.ip.split('/')[0], solo_questo: false},
    prepara: v => ({nuovo: ipDelModulo(v.nuovo, it.ip), solo_questo: !!v.solo_questo}),
  });
}

function ipProposto(subnet, ipAttuale, vecchiaRete) {
  const usati = ipUsati(S.lab);
  const stesso = vecchiaRete ? stessaParteHost(ipAttuale, vecchiaRete, subnet) : '';
  return stesso && !usati.has(stesso.split('/')[0]) ? stesso : primoIpLibero(subnet, usati);
}

function spostaInterfaccia(d, it) {
  const altre = S.lab.lan.map(l => l.nome).filter(n => n !== it.lan);
  apriOperazione({
    operazione: 'sposta_interfaccia', titolo: `Sposta ${d.nome} ${it.dev}`,
    spiegazione: `Adesso sulla LAN ${it.lan}. Scegli dove spostarla; nel passo dopo l'IP nuovo è già proposto.`,
    schema: [{nome: 'lan', etichetta: 'LAN', tipo: 'scelta', obbligatorio: true, opzioni: [...altre.map(n => [n, `${n} ${subnetDellaLan(S.lab, n)}`]), ['__nuova', 'una LAN nuova']]},
             {nome: 'nuova', etichetta: 'Nome della LAN nuova', segnaposto: 'es. Z', aiuto: 'Solo se hai scelto "una LAN nuova": lettere e numeri.'}],
    valori: {lan: altre[0] || '__nuova'},
    avanti: v => {
      const lan = v.lan === '__nuova' ? String(v.nuova || '').trim() : v.lan;
      if (!/^[A-Za-z0-9]+$/.test(lan)) throw new Error('Scrivi il nome della LAN nuova: lettere e numeri (es. Z).');
      if (v.lan === '__nuova' && S.lab.lan.some(l => l.nome === lan)) throw new Error(`La LAN ${lan} c'è già: sceglila dall'elenco.`);
      const subnet = subnetDellaLan(S.lab, lan);
      return {
        operazione: 'sposta_interfaccia', titolo: `Sposta ${d.nome} ${it.dev} sulla LAN ${lan}`,
        spiegazione: subnet ? `La LAN ${lan} ha la subnet ${subnet}: l'IP proposto è libero.` : `La LAN ${lan} è nuova: scegli l'IP (con la maschera).`,
        fissi: {dispositivo: d.nome, dev: it.dev, nuova_lan: lan},
        schema: [{nome: 'nuovo_ip', etichetta: 'IP sulla LAN ' + lan, obbligatorio: true}],
        valori: {nuovo_ip: subnet ? ipProposto(subnet, it.ip, subnetDellaLan(S.lab, it.lan)) : it.ip},
        prepara: x => {
          const ip = ipDelModulo(x.nuovo_ip, subnet || it.ip);
          return ip === it.ip ? {} : {nuovo_ip: ip};
        },
      };
    },
  });
}

function togliInterfaccia(d, it) {
  apriOperazione({
    operazione: 'togli_interfaccia', titolo: `Togli ${d.nome} ${it.dev}`,
    spiegazione: `Toglie la riga di lab.conf, l'IP nello startup, le rotte e il blocco interface di ${it.dev}; le interfacce dopo vengono rinumerate.`,
    fissi: {nome: d.nome, dev: it.dev},
    schema: (d.demoni.includes('bgpd') || d.tipo !== 'router'
      ? [{nome: 'togli_neighbor', etichetta: 'Togli anche i neighbor degli altri router che puntano a questo IP', tipo: 'si_no'}] : [])
      .concat([{nome: 'pulisci_riferimenti', etichetta: 'Togli anche quello che resta senza uso: gateway, rotte, resolver e record DNS che usavano questo IP, route-map e liste', tipo: 'si_no'}]),
    valori: {togli_neighbor: true, pulisci_riferimenti: true},
    prepara: v => ({togli_neighbor: v.togli_neighbor !== false, pulisci_riferimenti: v.pulisci_riferimenti !== false}),
  });
}

// ---------- LAN ----------
function menuLan(lan) {
  const l = S.lab.lan.find(x => x.nome === lan); if (!l) return;
  const v = vicinatoDellaLan(S.lab, lan);
  apriMenu({
    titolo: `LAN ${lan}`, spiegazione: `${l.subnet || 'senza subnet'} · ${v.membri.join(', ') || 'nessun dispositivo'}`,
    voci: [
      {testo: 'Cambia subnet', fai: () => cambiaSubnet(l)},
      {testo: 'Collega un dispositivo a questa LAN', fai: () => collega(l)},
      ...Object.entries(TIPI).map(([t, n]) => ({testo: `Aggiungi qui un ${n}`, fai: () => aggiungi(t, lan)})),
      ...vociPolicyLan(lan),
    ],
  });
}

function cambiaSubnet(l) {
  if (!l.subnet) return avviso(`La LAN ${l.nome} non ha IP da cambiare.`);
  apriOperazione({
    operazione: 'rinumera_lan', titolo: `Subnet della LAN ${l.nome}`,
    spiegazione: `Adesso ${l.subnet}. Nel passo dopo vedi gli IP nuovi proposti (stessa parte host) e puoi cambiarli.`,
    schema: [{nome: 'rete', etichetta: 'Nuova subnet', obbligatorio: true, segnaposto: 'es. 10.0.5.0/24'}],
    valori: {rete: l.subnet},
    avanti: v => {
      const rete = reteNormalizzata(v.rete);
      if (!rete) throw new Error('Subnet non valida: scrivila come 10.0.5.0/24.');
      if (rete === reteNormalizzata(l.subnet)) throw new Error('È la stessa subnet di adesso.');
      const membri = S.lab.dispositivi.flatMap(d => d.interfacce.filter(it => it.lan === l.nome && it.ip).map(it => ({d: d.nome, it})));
      return {
        operazione: 'rinumera_lan', titolo: `Subnet della LAN ${l.nome}: ${l.subnet} → ${rete}`,
        spiegazione: 'IP proposti con la stessa parte host. Basta l\'ultimo numero. Gateway, neighbor BGP e network nei file cambiano insieme.',
        fissi: {lan: l.nome, nuova_rete: rete},
        schema: membri.map(m => ({nome: `ip:${m.d}:${m.it.dev}`, etichetta: `${m.d} ${m.it.dev} (era ${m.it.ip})`, obbligatorio: true})),
        valori: Object.fromEntries(membri.map(m => [`ip:${m.d}:${m.it.dev}`, stessaParteHost(m.it.ip, l.subnet, rete)])),
        prepara: x => ({assegnati: assegnati(x, rete)}),
      };
    },
  });
}

function collega(l) {
  const qui = new Set(S.lab.dispositivi.filter(d => d.interfacce.some(it => it.lan === l.nome)).map(d => d.nome));
  const altri = S.lab.dispositivi.filter(d => !qui.has(d.nome)).map(d => d.nome);
  if (!altri.length) return avviso(`Tutti i dispositivi sono già sulla LAN ${l.nome}.`);
  apriOperazione({
    operazione: 'aggiungi_interfaccia', titolo: `Collega un dispositivo alla LAN ${l.nome}`,
    spiegazione: `Aggiunge al dispositivo un'interfaccia nuova (la prima ethN libera) sulla LAN ${l.nome}${l.subnet ? ' (' + l.subnet + ')' : ''}.`,
    fissi: {lan: l.nome},
    schema: [{nome: 'nome', etichetta: 'Dispositivo', tipo: 'scelta', obbligatorio: true, opzioni: altri},
             {nome: 'ip', etichetta: 'IP', obbligatorio: true, segnaposto: 'es. 10.0.0.5/24'}],
    valori: {nome: altri[0], ip: l.subnet ? primoIpLibero(l.subnet, ipUsati(S.lab)) : ''},
    prepara: v => ({nome: v.nome, ip: l.subnet ? ipDelModulo(v.ip, l.subnet) : v.ip}),
  });
}

// ---------- dispositivo ----------
function azioniDispositivo(d) {
  const a = [['rinomina', 'Rinomina']];
  const ha = p => d.demoni.includes(p + 'd');
  if (d.tipo !== 'router') a.push(['gateway', 'Gateway'], ['resolver', 'Resolver']);
  if (d.tipo === 'dns' && (d.zone || []).some(z => z[0] === '.' && z[1] === 'master')) a.push(['delega', 'Delega una zona']);
  if (d.tipo === 'router' && d.asn) a.push(['as', 'Cambia AS']);
  if (d.tipo === 'router') for (const p of ['ospf', 'rip', 'bgp'])
    a.push(ha(p) ? [`togli:${p}`, `Togli ${p.toUpperCase()}`] : [`aggiungi:${p}`, `Aggiungi ${p.toUpperCase()}`]);
  a.push(['loopback', 'Aggiungi loopback']);
  if (d.tipo === 'router' && ha('bgp')) a.push(['network', 'Network BGP'], ['network_togli', 'Togli network'], ['network_cambia', 'Cambia network'], ['policy', 'Policy BGP']);
  if (d.tipo === 'router' && (ha('bgp') || ha('ospf') || ha('rip'))) a.push(['default', 'Default route']);
  if (d.tipo === 'router' && ha('bgp') && (ha('ospf') || ha('rip'))) a.push(['ridistribuzione', 'Ridistribuzione BGP → IGP']);
  a.push(['diagnosi', 'Diagnostica'], ['righe', 'File a righe'], ['togli', 'Togli il dispositivo']);
  return a;
}

S.htmlModificaDispositivo = d => `<h4 class="ed-sotto">Modifica</h4>
  <div class="btns">${d.interfacce.map(it => `<button type="button" class="ghost small" data-gesto="if" data-dev="${esc(d.nome)}" data-iface="${esc(it.dev)}"
    title="IP, LAN, costo OSPF, togli">${esc(it.dev)}${it.costo ? ` (costo ${esc(it.costo)})` : ''}</button>`).join('')}</div>
  <div class="btns">${azioniDispositivo(d).map(([id, t]) => `<button type="button" class="${id === 'togli' ? 'danger' : 'ghost'} small" data-gesto="disp" data-dev="${esc(d.nome)}" data-azione="${esc(id)}">${esc(t)}</button>`).join('')}</div>`;

async function azioneDispositivo(dev, az) {
  const d = dispositivo(dev); if (!d) return;
  try {
    if (az === 'rinomina') rinomina(d);
    else if (az === 'gateway') await gateway(d);
    else if (az === 'as') cambiaAs(d);
    else if (az.startsWith('aggiungi:')) await aggiungiProtocollo(d, az.slice(9));
    else if (az.startsWith('togli:')) togliProtocollo(d, az.slice(6));
    else if (az === 'righe') await righe(d);
    else if (az === 'diagnosi') await diagnostica(d.nome);
    else if (az === 'loopback') loopback(d);
    else if (az === 'resolver') await resolver(d);
    else if (az === 'delega') await delega(d);
    else if (az === 'network') await networkBgp(d.nome);
    else if (az === 'network_togli') await cambiaNetwork(d, true);
    else if (az === 'network_cambia') await cambiaNetwork(d, false);
    else if (az === 'policy') await menuPolicy(d.nome);
    else if (az === 'default') menuDefault(d);
    else if (az === 'ridistribuzione') await ridistribuzione(d);
    else if (az === 'togli') await togliDispositivo(d);
  } catch (e) { avviso(e.message); }
}

function rinomina(d) {
  apriOperazione({
    operazione: 'rinomina', titolo: `Rinomina ${d.nome}`,
    spiegazione: 'Cambiano lab.conf, la cartella e i file del dispositivo, l\'hostname e le description dei neighbor; la posizione nel disegno resta.',
    fissi: {vecchio: d.nome},
    schema: [{nome: 'nuovo', etichetta: 'Nome nuovo', obbligatorio: true, aiuto: 'Minuscole, cifre e _ (regola di Kathará).'}],
    valori: {nuovo: d.nome},
  });
}

async function gateway(d) {
  const o = await opzioni('gateway', {dispositivo: d.nome});
  const cand = (o.candidati || []).map(([ip, n, dev]) => [ip, `${ip} (${n}, ${dev})`]);
  apriOperazione({
    operazione: 'gateway', titolo: `Gateway di ${d.nome}`,
    spiegazione: `Adesso: ${o.attuale || 'nessuno'}.`,
    fissi: {dispositivo: d.nome},
    schema: [{nome: 'scelto', etichetta: 'Gateway', tipo: 'scelta', obbligatorio: true, opzioni: [...cand, ['__altro', 'un altro IP'], ['__nessuno', 'nessuno (togli il gateway)']]},
             {nome: 'altro', etichetta: 'Altro IP', segnaposto: 'es. 10.0.0.254', aiuto: 'Solo se hai scelto "un altro IP".'},
             {nome: 'forza', etichetta: 'Anche se è fuori dalla rete delle sue interfacce', tipo: 'si_no'}],
    valori: {scelto: (cand.find(c => c[0] === o.attuale) || cand[0] || ['__altro'])[0], forza: false},
    prepara: v => {
      if (v.scelto === '__nessuno') return {gw: ''};
      const gw = v.scelto === '__altro' ? String(v.altro || '').trim() : v.scelto;
      if (!gw) throw new Error('Scrivi l\'IP del gateway.');
      return {gw, forza: !!v.forza};
    },
  });
}

function cambiaAs(d) {
  apriOperazione({
    operazione: 'as', titolo: `AS di ${d.nome}`,
    spiegazione: `Adesso AS${d.asn}. Cambia 'router bgp' e i 'remote-as' degli altri router verso ${d.nome}.`,
    fissi: {router: d.nome},
    schema: [{nome: 'nuovo', etichetta: 'Nuovo AS', tipo: 'numero', obbligatorio: true}],
    valori: {nuovo: d.asn},
    prepara: v => ({nuovo: String(v.nuovo)}),
  });
}

async function aggiungiProtocollo(d, proto) {
  const o = await opzioni('aggiungi_protocollo', {router: d.nome});
  const conBgp = o.attivi.includes('bgp');
  const P = proto.toUpperCase();
  if (proto === 'bgp') {
    const vicini = o.vicini_bgp || [];
    apriOperazione({
      operazione: 'aggiungi_protocollo', titolo: `Aggiungi BGP a ${d.nome}`,
      spiegazione: 'Daemons, blocco router bgp con le network proposte e le sessioni con i router BGP sulle sue LAN (anche dal loro lato); redistribute bgp negli IGP del router.',
      fissi: {router: d.nome, proto},
      schema: [{nome: 'asn', etichetta: 'AS', tipo: 'numero', obbligatorio: true},
               {nome: 'reti', etichetta: 'Network annunciate', aiuto: 'Separate da virgola; vuoto = nessuna.'},
               ...vicini.map(v => ({nome: 's:' + v.nome, etichetta: `Sessione con ${v.nome} (${v.ip}, AS${v.asn || '?'})`, tipo: 'si_no'}))],
      valori: Object.assign({asn: o.asn_proposto || d.gruppo || '', reti: (o.proposta_bgp || []).join(', ')}, Object.fromEntries(vicini.map(v => ['s:' + v.nome, true]))),
      prepara: v => ({asn: String(v.asn), reti: reti(v.reti), sessioni: vicini.filter(x => v['s:' + x.nome]).map(x => x.nome)}),
    });
    return;
  }
  const schema = [{nome: 'reti', etichetta: `Network ${P}`, obbligatorio: true, aiuto: 'Proposte dal motore come nel wizard; separate da virgola.'}];
  if (proto === 'ospf') schema.push({nome: 'area', etichetta: 'Area', obbligatorio: true}, {nome: 'stub', etichetta: 'Area stub', tipo: 'si_no'});
  if (conBgp) schema.push({nome: 'redistribute_bgp', etichetta: `Ridistribuisci BGP in ${P} (redistribute bgp)`, tipo: 'si_no'});
  apriOperazione({
    operazione: 'aggiungi_protocollo', titolo: `Aggiungi ${P} a ${d.nome}`,
    spiegazione: `Daemons e blocco router ${proto} con redistribute connected.`,
    fissi: {router: d.nome, proto},
    schema, valori: {reti: (o.proposta_igp || []).join(', '), area: '0.0.0.0', stub: false, redistribute_bgp: true},
    prepara: v => Object.assign({reti: reti(v.reti)}, proto === 'ospf' ? {area: String(v.area).trim(), stub: !!v.stub} : {},
      conBgp ? {redistribute_bgp: !!v.redistribute_bgp} : {}),
  });
}

function togliProtocollo(d, proto) {
  const P = proto.toUpperCase();
  apriOperazione({
    operazione: 'togli_protocollo', titolo: `Togli ${P} da ${d.nome}`,
    spiegazione: `Toglie il blocco router ${proto}, le righe redistribute ${proto} e spegne il demone.`,
    fissi: {router: d.nome, proto},
    schema: proto === 'bgp' ? [{nome: 'anche_sui_vicini', etichetta: `Togli anche i neighbor degli altri router verso ${d.nome}`, tipo: 'si_no'},
      {nome: 'pulisci_riferimenti', etichetta: 'Togli anche le route-map e le liste che restano senza uso', tipo: 'si_no'}] : [],
    valori: {anche_sui_vicini: true, pulisci_riferimenti: true},
    prepara: v => (proto === 'bgp' ? {anche_sui_vicini: v.anche_sui_vicini !== false, pulisci_riferimenti: v.pulisci_riferimenti !== false} : {}),
    subito: proto !== 'bgp',
  });
}

async function togliDispositivo(d) {
  const o = await opzioni('togli_dispositivo', {nome: d.nome});
  const note = [o.gateway_di.length ? `è il gateway di ${o.gateway_di.join(', ')}` : '', o.resolver_di.length ? `è il resolver di ${o.resolver_di.join(', ')}` : '']
    .filter(Boolean).join('; ');
  apriOperazione({
    operazione: 'togli_dispositivo', titolo: `Togli ${d.nome}`,
    spiegazione: `Toglie le righe di lab.conf, la cartella e i file di ${d.nome}.` + (note ? ` Attenzione: ${note}.` : ''),
    fissi: {nome: d.nome},
    schema: (o.neighbor.length ? [{nome: 'togli_neighbor', etichetta: `Togli anche i neighbor verso ${d.nome} su ${o.neighbor.join(', ')}`, tipo: 'si_no'}] : [])
      .concat([{nome: 'pulisci_riferimenti', etichetta: 'Togli anche quello che resta senza uso: gateway, rotte, resolver e record DNS che usavano i suoi IP, route-map e liste', tipo: 'si_no'}]),
    valori: {togli_neighbor: true, pulisci_riferimenti: true},
    prepara: v => ({togli_neighbor: v.togli_neighbor !== false, pulisci_riferimenti: v.pulisci_riferimenti !== false}),
  });
}

async function righe(d) {
  const modificabili = (await opzioni('righe', {dispositivo: d.nome})) || [];
  const testi = await api('/api/file?lab=' + encodeURIComponent(S.nome) + '&dev=' + encodeURIComponent(d.nome));
  const file = testi.filter(f => modificabili.includes(f.file));
  if (!file.length) return avviso(`${d.nome} non ha file da modificare a righe.`);
  apriOperazione({
    operazione: 'righe', titolo: `File di ${d.nome}`,
    spiegazione: 'Per le righe che le altre azioni non coprono. Nel passo dopo scrivi nel file; l\'anteprima mostra le differenze e dopo "Applica" il Riepilogo segnala gli avvisi nuovi.',
    schema: [{nome: 'rel', etichetta: 'File', tipo: 'scelta', obbligatorio: true, opzioni: file.map(f => f.file)}],
    valori: {rel: file[0].file},
    avanti: async v => {
      const f = file.find(x => x.file === v.rel);
      const vecchie = f.testo.split('\n');
      if (vecchie.length && vecchie[vecchie.length - 1] === '') vecchie.pop();
      // problemi della diagnostica di questo file (per riga), per correggerli mentre si scrive
      let probl = [];
      try { probl = (await problemiDi(d.nome)).filter(x => x.file === v.rel); } catch (e) { probl = []; }
      return {
        operazione: 'righe', titolo: v.rel,
        corpo: `<label class="small muted" for="opRighe">Contenuto del file</label>
          <textarea id="opRighe" class="righe-mod" rows="18" spellcheck="false" autocomplete="off">${esc(vecchie.join('\n'))}</textarea>
          ${probl.length ? `<div class="small"><b>Diagnostica di questo file</b> (riga di adesso):${htmlProblemi(probl, false)}</div>` : ''}`,
        leggi: () => ({testo: $('#opRighe').value}),
        prepara: x => ({rel: v.rel, nuove: x.testo.replace(/\r/g, '').replace(/\n+$/, '').split('\n'), vecchie}),
      };
    },
  });
}

// ---------- BGP (fase 5.3) ----------
function menuAs(g) {
  const routers = S.lab.dispositivi.filter(d => d.tipo === 'router' && String(d.gruppo) === String(g));
  const bgp = routers.filter(d => d.demoni.includes('bgpd')), ospf = routers.some(d => d.demoni.includes('ospfd'));
  const voci = [];
  if (bgp.length) voci.push({testo: "Annuncia l'aggregato (network BGP)", fai: () => aggregato(g, bgp.map(d => d.nome))});
  if (bgp.length >= 2) voci.push({testo: 'Completa l\'iBGP (tutti con tutti)', fai: () => apriOperazione({
    operazione: 'ibgp', titolo: `iBGP completo nell'AS${g}`, fissi: {asn: String(g)}, subito: true,
    spiegazione: `Sessioni iBGP mancanti tra ${bgp.map(d => d.nome).join(', ')}: l'anteprima le mostra prima di scriverle. Controlla il testo: alcuni esercizi vietano l'iBGP (es. butterfly).`})});
  if (ospf) voci.push({testo: 'Auto-cost (costi OSPF predefiniti)', fai: () => autoCost(g)});
  if (!voci.length) return avviso(`L'AS${g} non ha router BGP né OSPF: niente da fare qui.`);
  apriMenu({titolo: `AS${g}`, spiegazione: `Router: ${routers.map(d => d.nome).join(', ')}` + (bgp.length ? ` · con BGP: ${bgp.map(d => d.nome).join(', ')}` : ''), voci});
}

async function aggregato(g, routers) {
  if (routers.length === 1) return networkBgp(routers[0], `Aggregato dell'AS${g} su ${routers[0]}`);
  apriOperazione({
    operazione: 'network_bgp', titolo: `Aggregato dell'AS${g}`,
    spiegazione: 'Su quale router BGP annunciarlo (di solito quello di confine, collegato agli altri AS).',
    schema: [{nome: 'router', etichetta: 'Router', tipo: 'scelta', obbligatorio: true, opzioni: routers}],
    valori: {router: routers.find(r => retiEbgp(S.lab, r).length) || routers[0]},
    avanti: v => confNetwork(v.router, `Aggregato dell'AS${g} su ${v.router}`),
  });
}

async function networkBgp(router, titolo) { apriOperazione(await confNetwork(router, titolo)); }

async function confNetwork(router, titolo) {
  const info = (await opzioni('network_bgp', {router}))[router];
  return {
    operazione: 'network_bgp', titolo: titolo || `Network BGP su ${router}`,
    spiegazione: `Già annunciate: ${info.presenti.join(', ') || 'nessuna'}. Proposta del motore (come nel terminale): ${info.proposta.join(', ')}; puoi cambiarla.`,
    schema: [{nome: 'reti', etichetta: 'Reti da annunciare', obbligatorio: true, aiuto: 'Separate da virgola, es. 20.20.0.0/16 oppure 0.0.0.0/0.'}],
    valori: {reti: info.proposta.join(', ')},
    avanti: async v => {
      const reti = listaReti(v.reti);
      if (!reti.some(r => !info.presenti.includes(r))) throw new Error('Tutte le reti indicate sono già annunciate.');
      const coperte = ((await opzioni('network_bgp', {router, reti}))[router] || {}).coperte || [];
      return {
        operazione: 'network_bgp', titolo: `Network BGP su ${router}: ${reti.join(', ')}`,
        spiegazione: coperte.length ? `Le reti ${coperte.join(', ')} sono già contenute nell'aggregato.` : 'Nessuna rete già annunciata è contenuta in queste.',
        fissi: {router, reti},
        schema: coperte.length ? [{nome: 'togli_coperte', etichetta: `Togli ${coperte.join(', ')} e annuncia solo l'aggregato`, tipo: 'si_no'}] : [],
        valori: {togli_coperte: false},
        prepara: x => ({togli_coperte: !!x.togli_coperte}),
        subito: !coperte.length,
      };
    },
  };
}

async function cambiaNetwork(d, togli) {
  const info = (await opzioni('network_bgp', {router: d.nome}))[d.nome];
  if (!info.presenti.length) throw new Error(`${d.nome} non annuncia ancora nessuna network in BGP.`);
  apriOperazione({
    operazione: 'network_bgp', titolo: `${togli ? 'Togli' : 'Cambia'} una network BGP di ${d.nome}`,
    spiegazione: togli ? 'Toglie la riga network dal blocco router bgp.'
      : 'Cambia la riga network e, se nessun altro router annuncia la vecchia rete, anche prefix-list e access-list dei router del lab che la citano.',
    fissi: {router: d.nome, azione: togli ? 'rimuovi' : 'modifica'},
    schema: [{nome: 'rete', etichetta: 'Network annunciata', tipo: 'scelta', obbligatorio: true, opzioni: info.presenti},
             ...(togli ? [] : [{nome: 'nuova', etichetta: 'Nuova rete', obbligatorio: true, segnaposto: 'es. 20.20.0.0/16'}])],
    valori: {rete: info.presenti[0]},
    prepara: v => ({reti: [v.rete], ...(togli ? {} : {nuova_rete: String(v.nuova || '').trim()})}),
  });
}

function loopback(d) {
  const proposta = prossimaLoopback(S.lab);
  apriOperazione({
    operazione: 'loopback', titolo: `Loopback su ${d.nome}`,
    spiegazione: (d.loopback.length ? `Ha già: ${d.loopback.join(', ')}. ` : '') + (d.tipo === 'router'
      ? 'Indirizzo /32 su lo; sui router OSPF/RIP anche la network nell\'IGP (nella sua area) e, se altri router dello stesso AS hanno una loopback, le sessioni iBGP tra le loopback.'
      : 'Indirizzo /32 su lo, nello startup.'),
    fissi: {dispositivo: d.nome},
    schema: [{nome: 'ip', etichetta: 'IP della loopback', obbligatorio: true, segnaposto: 'es. 1.1.1.1', aiuto: proposta ? 'Proposta: la successiva della serie già usata nel lab; puoi cambiarla.' : 'Diventa /32.'}],
    valori: {ip: proposta ? proposta.split('/')[0] : ''},
    prepara: v => ({ip: String(v.ip).trim().split('/')[0]}),
  });
}

function menuDefault(d) {
  const voci = [];
  if (d.demoni.includes('bgpd')) voci.push({testo: 'BGP: manda la default a dei neighbor (default-originate)', fai: () => defaultBgp(d)});
  if (d.demoni.includes('ospfd')) voci.push({testo: 'OSPF: annuncia la default (default-information originate)', fai: () => defaultIgp(d, 'ospf')});
  if (d.demoni.includes('ripd')) voci.push({testo: 'RIP: annuncia la default o un\'altra rete', fai: () => defaultIgp(d, 'rip')});
  apriMenu({titolo: `Default route da ${d.nome}`, voci});
}

async function defaultBgp(d) {
  const cfg = await opzioni('default_originate', {router: d.nome});
  const owner = Object.fromEntries(S.lab.dispositivi.flatMap(x => x.interfacce.filter(it => it.ip).map(it => [it.ip.split('/')[0], x.nome])));
  const vicini = Object.entries(cfg.neighbors);
  // default_orig arriva come dizionario {ip: ...} (o elenco): chi ha già default-originate
  const gia = ip => (Array.isArray(cfg.default_orig) ? cfg.default_orig.includes(ip) : !!(cfg.default_orig || {})[ip]);
  apriOperazione({
    operazione: 'default_originate', titolo: `Default route da ${d.nome} (BGP)`,
    spiegazione: `Neighbor di ${d.nome} (AS${cfg.asn}); proposti quelli eBGP. default-originate da solo basta: 'network 0.0.0.0/0' non serve.`,
    fissi: {router: d.nome, owner},
    schema: [...vicini.map(([ip, a]) => ({nome: 'n:' + ip, tipo: 'si_no',
      etichetta: `${ip} ${owner[ip] || cfg.descr[ip] || '?'} AS${a} ${a === cfg.asn ? 'iBGP' : 'eBGP'}${gia(ip) ? ' (ha già default-originate)' : ''}`})),
      {nome: 'solo', etichetta: "Solo la default (es. 'announces just the default route')", tipo: 'si_no'},
      {nome: 'extra', etichetta: 'Reti in più oltre alla default', aiuto: 'Solo con "Solo la default"; separate da virgola. Vuoto = solo la default.'}],
    valori: Object.fromEntries(vicini.map(([ip, a]) => ['n:' + ip, a !== cfg.asn])),
    prepara: v => parametriDefaultBgp(v, cfg.neighbors),
  });
}

function defaultIgp(d, proto) {
  const P = proto.toUpperCase();
  apriOperazione({
    operazione: 'default_igp', titolo: `Default route in ${P} su ${d.nome}`,
    spiegazione: proto === 'ospf' ? "default-information originate; con 'always' se il router non ha una default sua."
      : 'route <rete> annuncia la rete anche senza una rotta (come la guida 009); default-information originate annuncia la default.',
    fissi: {router: d.nome, proto},
    schema: proto === 'ospf' ? [{nome: 'ha_default', etichetta: 'Il router ha già una default sua (statica nello startup o imparata da BGP)', tipo: 'si_no'}]
      : [{nome: 'modo', etichetta: 'Come', tipo: 'scelta', opzioni: [['1', 'route <rete>'], ['2', 'default-information originate']]},
         {nome: 'rete', etichetta: 'Rete (con route <rete>)', aiuto: 'Vuoto = 0.0.0.0/0, la default.'}],
    valori: {ha_default: false, modo: '1', rete: '0.0.0.0/0'},
    prepara: v => parametriDefaultIgp(proto, v),
  });
}

async function ridistribuzione(d) {
  const red = (await opzioni('redistribuzione', {}))[d.nome] || {};
  const igp = Object.keys(red), conBgp = igp.filter(p => red[p].includes('bgp'));
  const voci = [];
  if (conBgp.length) voci.push({testo: `Togli redistribute bgp (da ${conBgp.join(', ').toUpperCase()})`, fai: () => apriOperazione({
    operazione: 'redistribuzione', titolo: `Togli redistribute bgp su ${d.nome}`, fissi: {router: d.nome, attiva: false}, subito: true})});
  if (conBgp.length < igp.length) voci.push({testo: 'Rimetti redistribute bgp', fai: () => apriOperazione({
    operazione: 'redistribuzione', titolo: `Rimetti redistribute bgp su ${d.nome}`, fissi: {router: d.nome, attiva: true}, subito: true})});
  const reti = retiEbgp(S.lab, d.nome);
  voci.push({testo: 'Solo le rotte imparate via eBGP (route-map eBGP)', fai: () => apriOperazione({
    operazione: 'redistribuzione_route_map', titolo: `Route-map eBGP su ${d.nome}`,
    spiegazione: "redistribute bgp route-map eBGP: entrano nell'IGP solo le rotte con il next-hop nella rete del neighbor eBGP.",
    fissi: {router: d.nome},
    schema: [{nome: 'rete', etichetta: 'Rete di collegamento con il neighbor eBGP', obbligatorio: true, aiuto: reti.length ? 'Proposta dalle LAN verso altri AS.' : 'es. 10.1.0.0/30'}],
    valori: {rete: reti[0] || ''},
    prepara: v => { const r = reteNormalizzata(String(v.rete).includes('/') ? v.rete : v.rete + '/32'); if (!r) throw new Error('Rete non valida (es. 10.1.0.0/30).'); return {rete: v.rete.trim()}; },
  })});
  apriMenu({titolo: `Ridistribuzione BGP → IGP su ${d.nome}`, spiegazione: igp.map(p => `${p.toUpperCase()}: redistribute ${red[p].join(', ') || '-'}`).join(' · '), voci});
}

// ---------- DNS (fase 5.4: le Opzioni 5 e 9 del terminale) ----------
async function resolver(d) {
  const o = await opzioni('resolver', {});
  const cand = (o.candidati || []).filter(([n]) => n !== d.nome || d.tipo === 'dns').map(([n, ip]) => [ip, `${n} - ${ip}`]);
  const attuale = (d.nameserver || [])[0] || '';
  apriOperazione({
    operazione: 'resolver', titolo: `Resolver di ${d.nome}`,
    spiegazione: `Adesso: ${attuale || 'nessuno'}. Scrive "nameserver <IP>" in ${d.nome}/etc/resolv.conf.`,
    fissi: {dispositivo: d.nome},
    schema: [{nome: 'scelto', etichetta: 'Server DNS', tipo: 'scelta', obbligatorio: true, opzioni: [...cand, ['__altro', 'un altro IP'], ['__nessuno', 'nessuno (togli il resolver)']]},
             {nome: 'altro', etichetta: 'Altro IP', segnaposto: 'es. 9.9.9.9', aiuto: 'Solo se hai scelto "un altro IP".'}],
    valori: {scelto: (cand.find(c => c[0] === attuale) || cand[0] || ['__altro'])[0]},
    prepara: v => {
      if (v.scelto === '__nessuno') return {ip: ''};
      const ip = v.scelto === '__altro' ? String(v.altro || '').trim() : v.scelto;
      if (!ip) throw new Error('Scrivi l\'IP del server DNS.');
      return {ip};
    },
  });
}

async function delega(d) {
  const o = await opzioni('resolver', {});
  const altri = (o.candidati || []).filter(([n]) => n !== d.nome);
  apriOperazione({
    operazione: 'delega_dns', titolo: `Delega una zona da ${d.nome}`,
    spiegazione: `${d.nome} è il root: la delega aggiunge in db.root il record NS della zona e il glue A del suo nameserver.`,
    schema: [{nome: 'zona', etichetta: 'Zona da delegare', obbligatorio: true, segnaposto: 'es. com'},
             {nome: 'server', etichetta: 'Server DNS che la gestirà', tipo: 'scelta', opzioni: [...altri.map(([n, ip]) => [n, `${n} - ${ip}`]), ['', 'lo scrivo io']]}],
    valori: {server: altri[0] ? altri[0][0] : ''},
    avanti: v => {
      const zona = String(v.zona || '').trim().replace(/^\.+|\.+$/g, '');
      if (!/^[a-z0-9-]+(\.[a-z0-9-]+)*$/i.test(zona)) throw new Error('Zona non valida (es. com oppure roma3.it).');
      const srv = altri.find(([n]) => n === v.server);
      return {
        operazione: 'delega_dns', titolo: `Delega di ${zona} da ${d.nome}`,
        spiegazione: 'Nome del nameserver e IP del glue sono proposti (come nel terminale); puoi cambiarli.',
        fissi: {server: d.nome, zona},
        schema: [{nome: 'ns', etichetta: `Nameserver di ${zona}`, obbligatorio: true},
                 {nome: 'ip', etichetta: 'IP del nameserver (glue)', obbligatorio: true, segnaposto: 'es. 20.1.0.3'}],
        valori: {ns: `dns.${zona}`, ip: srv ? srv[1] : ''},
        prepara: x => ({ns: String(x.ns).trim().replace(/\.+$/, ''), ip: String(x.ip).trim()}),
      };
    },
  });
}

// ---------- azzerare il routing ----------
async function azzeraRouting() {
  const o = await opzioni('reset_routing', {});
  if (!o.router.length) throw new Error('Il lab non ha router.');
  const nStat = Object.values(o.statiche).reduce((a, x) => a + x.length, 0);
  apriOperazione({
    operazione: 'reset_routing', titolo: 'Azzera il routing',
    spiegazione: `Toglie da frr.conf di ${o.router.length} router network, neighbor, redistribute, policy e costi OSPF` + (nStat ? ` e ${nStat} rotte statiche dagli .startup` : '')
      + `. Restano lab.conf, IP, loopback, demoni e tutti i pc, server WWW e DNS. L'anteprima mostra ogni riga; si annulla con "Annulla modifica".`,
    schema: [{nome: 'router', etichetta: 'Router', tipo: 'scelta', opzioni: [['', 'tutti'], ...o.router.map(r => [r, r])]}],
    valori: {router: ''},
    prepara: v => (v.router ? {router: v.router} : {}),
  });
}

// ---------- aggiungere un dispositivo ----------
function aggiungi(tipo, lan) {
  const lans = S.lab.lan.filter(l => l.subnet);
  if (!lans.length) return avviso('Il lab non ha LAN con una subnet a cui collegarlo.');
  if (!lan) {
    apriOperazione({
      operazione: 'aggiungi_dispositivo', titolo: `Aggiungi un ${TIPI[tipo]}`,
      spiegazione: 'Scegli la LAN dove collegarlo (oppure clicca una LAN sul disegno e usa "Aggiungi qui").',
      schema: [{nome: 'lan', etichetta: 'LAN', tipo: 'scelta', obbligatorio: true, opzioni: lans.map(l => [l.nome, `${l.nome} ${l.subnet}`])}],
      valori: {lan: lans[0].nome},
      avanti: v => confAggiungi(tipo, v.lan),
    });
    return;
  }
  apriOperazione(confAggiungi(tipo, lan));
}

function confAggiungi(tipo, lan) {
  const subnet = subnetDellaLan(S.lab, lan), v = vicinatoDellaLan(S.lab, lan);
  const ip = primoIpLibero(subnet, ipUsati(S.lab));
  const schema = [{nome: 'nome', etichetta: 'Nome', obbligatorio: true, aiuto: 'Minuscole, cifre e _ (regola di Kathará).'},
                  {nome: 'ip', etichetta: `IP sulla LAN ${lan}`, obbligatorio: true}];
  const valori = {nome: nomeLibero(S.lab, tipo, v.asn), ip};
  if (tipo === 'router') {
    schema.push({nome: 'ospf', etichetta: 'OSPF', tipo: 'si_no'}, {nome: 'rip', etichetta: 'RIP', tipo: 'si_no'},
                {nome: 'area', etichetta: 'Area OSPF', aiuto: 'Solo con OSPF.'}, {nome: 'stub', etichetta: 'Area stub', tipo: 'si_no'},
                {nome: 'bgp', etichetta: 'BGP', tipo: 'si_no'}, {nome: 'asn', etichetta: 'AS (per BGP)', tipo: 'numero'},
                {nome: 'sessioni', etichetta: 'Con BGP: apri le sessioni con i router BGP sulla LAN (da entrambi i lati)', tipo: 'si_no'});
    Object.assign(valori, {ospf: v.igp.includes('ospf'), rip: v.igp.includes('rip'), area: '0.0.0.0', stub: false, bgp: false, asn: v.asn, sessioni: true});
  } else {
    if (tipo === 'dns') {
      schema.push({nome: 'root_type', etichetta: 'Tipo per la zona "."', tipo: 'scelta',
        opzioni: [['master', 'master (è un server root)'], ['hint', 'hint (usa i server root)'], ['', 'nessuno']],
        aiuto: 'Zone, deleghe e ricorsione si impostano dopo (DNS, fase 5.4) o con File a righe.'});
      valori.root_type = valori.nome === 'root' ? 'master' : 'hint';
    }
    schema.push({nome: 'gateway', etichetta: 'Gateway', aiuto: 'Proposto: il router della LAN.'},
                {nome: 'resolver', etichetta: 'Usa il resolver del lab (se c\'è)', tipo: 'si_no'});
    Object.assign(valori, {gateway: v.gateway, resolver: true});
  }
  return {
    operazione: 'aggiungi_dispositivo', titolo: `Aggiungi un ${TIPI[tipo]} sulla LAN ${lan}`,
    spiegazione: `${subnet} · sulla LAN: ${v.membri.join(', ') || 'nessuno'}. I valori sono già proposti; quelli che mancano li completa il motore come nel wizard.`,
    schema, valori,
    controlla: x => (tipo === 'router' && !x.ospf && !x.rip && !x.bgp ? {ospf: 'Scegli almeno un protocollo.'}
      : tipo === 'router' && x.bgp && !x.asn ? {asn: 'Con BGP serve il numero AS.'} : {}),
    prepara: x => ({tipo, dati: datiDispositivo(tipo, Object.assign({}, x, {lan, ip: ipDelModulo(x.ip, subnet)})),
      sessioni_bgp: tipo === 'router' ? !!x.sessioni : true, resolver: tipo === 'router' ? true : !!x.resolver}),
  };
}

S.htmlCasaModifica = () => `<div class="btns">${Object.entries(TIPI).map(([t, n]) =>
  `<button type="button" class="ghost small" data-gesto="aggiungi" data-tipo="${t}">+ ${esc(n[0].toUpperCase() + n.slice(1))}</button>`).join('')}</div>`
  + htmlPulsantePercorso()
  + `<div class="btns"><button type="button" class="ghost small danger" data-gesto="reset" title="Toglie network, neighbor, policy, costi e rotte statiche dai router; restano topologia, IP, demoni e pc/WWW/DNS">Azzera il routing</button></div>`;

// ---------- smistamento dei gesti (disegno e pulsanti dei pannelli) ----------
gesti.su = m => {
  if (!S.modifica) return;
  if (puntoPercorso(m)) return;          // pannello "Percorso voluto" aperto: il clic è un punto
  if (m.mod === 'percorso') return iniziaPercorso();
  if (m.mod === 'pol') return policyVersoNeighbor(m.dev, m.ip).catch(e => avviso(e.message));
  if (m.mod === 'if') menuInterfaccia(m.dev, m.iface);
  else if (m.mod === 'as') menuAs(m.as);
  else if (m.mod === 'lan') menuLan(m.lan);
  else if (m.mod === 'disp') azioneDispositivo(m.dev, m.azione);
  else if (m.mod === 'aggiungi') aggiungi(m.tipo, m.lan);
  else if (m.mod === 'reset') azzeraRouting().catch(e => avviso(e.message));
};
gesti.punto = puntoPercorso;
