// Modalità Modifica, fase 5.5: policy BGP (Opzioni 2 del terminale). Dal pannello del router
// ("Policy BGP": si sceglie il neighbor) o dal link fra due AS ("Policy BGP su A verso B"); poi il
// tipo: local-preference in ingresso, MED in uscita, prefix-list, access-list, Customer-Provider-Peer.
// Ogni passo è la stessa calcola_policy / calcola_cpp del terminale. Customer-Provider-Peer si
// imposta un lato alla volta: dopo l'applica la GUI propone il lato opposto, già compilato.
import { azione, S } from './comune.js';
import { dispositivo, lato } from './dispositivo.js';
import { apriMenu, apriOperazione } from './modifica.js';
import { parametriCpp, parametriPolicy, RELAZIONE_INVERSA } from './proposte.js';

const opzioni = async (router) => (await azione({azione: 'opzioni', operazione: 'policy', parametri: {router}})).opzioni;
function avviso(t) { S.op = null; S.esito = {avviso: t}; S.sel = null; lato(); }
const REL = {provider: 'il vicino è il mio provider', customer: 'il vicino è il mio cliente (customer)', peer: 'siamo alla pari (peer)'};
const ip0 = x => String(x || '').split('/')[0];

function descrivi(ip, nb, asn) {
  const chi = nb.dispositivo || nb.descrizione || '?';
  return `${ip} ${chi} AS${nb.remote_as}${String(nb.remote_as) === String(asn) ? ' iBGP' : ' eBGP'}${nb.relazione ? ' · ' + nb.relazione : ''}`;
}
const giaScritte = nb => (nb.policy || []).map(p => `${p.tipo} ${p.nome} ${p.verso}`).join(', ');

// apre un menu dall'interno di un passo "avanti" (che di solito restituisce un modulo)
function menuDa(menu) { const da = S.op; apriMenu(menu); S.op.da = da; return null; }

// ---------- dal pannello del router ----------
export async function menuPolicy(router) {
  const info = await opzioni(router);
  const voci = Object.entries(info.neighbor).map(([ip, nb]) => ({
    testo: descrivi(ip, nb, info.asn), aiuto: giaScritte(nb) ? 'Già scritte: ' + giaScritte(nb) : 'Nessuna policy scritta',
    fai: () => menuTipi(router, ip, info)}));
  voci.push({testo: 'Un neighbor non ancora configurato', fai: () => nuovoNeighbor(router, info)});
  apriMenu({titolo: `Policy BGP di ${router}`, voci,
    spiegazione: `AS${info.asn}. Scegli il neighbor a cui applicare la policy (come l'"IP neighbor" del terminale).`});
}

function nuovoNeighbor(router, info) {
  apriOperazione({
    operazione: 'policy', titolo: `Policy BGP di ${router}: neighbor nuovo`,
    spiegazione: 'Il neighbor non è configurato: viene aggiunto (neighbor ... remote-as) insieme alla policy.',
    schema: [{nome: 'ip', etichetta: 'IP del neighbor', obbligatorio: true, segnaposto: 'es. 10.0.0.2'},
             {nome: 'asn', etichetta: 'AS del neighbor', tipo: 'numero', obbligatorio: true}],
    controlla: v => (/^\d{1,3}(\.\d{1,3}){3}$/.test(String(v.ip).trim()) ? {} : {ip: 'IP senza maschera, es. 10.0.0.2.'}),
    avanti: v => {
      const ip = String(v.ip).trim();
      if (info.neighbor[ip]) throw new Error(`${ip} è già un neighbor di ${router}: sceglilo dall'elenco.`);
      return menuTipi(router, ip, info, {asn: String(v.asn)});
    },
  });
}

// ---------- dal link fra due AS ----------
// voci del menu della LAN: una per verso (A verso B, B verso A) fra router BGP di AS diversi
export function vociPolicyLan(lan) {
  const bgp = S.lab.dispositivi.filter(d => d.tipo === 'router' && d.demoni.includes('bgpd') && d.interfacce.some(it => it.lan === lan && it.ip));
  const voci = [];
  for (const a of bgp) for (const b of bgp) {
    if (a === b || !a.asn || String(a.asn) === String(b.asn)) continue;
    const ipB = ip0(b.interfacce.find(it => it.lan === lan && it.ip).ip);
    voci.push({testo: `Policy BGP su ${a.nome} verso ${b.nome}`, fai: () => policyVerso(a.nome, ipB, b)});
  }
  return voci;
}

async function policyVerso(router, ip, altro) {
  const info = await opzioni(router);
  return menuTipi(router, ip, info, info.neighbor[ip] ? null : {asn: String(altro.asn), dispositivo: altro.nome});
}

// clic su una sigla di policy sul disegno (livello Policy): i tipi di policy verso quel neighbor
export async function policyVersoNeighbor(router, ip) {
  const info = await opzioni(router);
  return menuTipi(router, ip, info, info.neighbor[ip] ? null : {asn: ''});
}

// ---------- tipo di policy ----------
function menuTipi(router, ip, info, nuovo = null) {
  const nb = info.neighbor[ip] || {remote_as: nuovo.asn, dispositivo: nuovo.dispositivo || null, policy: [], relazione: null};
  const ctx = {router, ip, info, nb, asn_nuovo: nuovo ? nuovo.asn : null};
  const voci = [
    {testo: 'Local-preference in ingresso', fai: () => formValore(ctx, 'local_pref')},
    {testo: 'MED (metric) in uscita', fai: () => formValore(ctx, 'med')},
    {testo: 'Prefix-list: scarta delle reti (in o out)', fai: () => formReti(ctx, 'prefix_list')},
    {testo: 'Access-list: scarta delle reti in ingresso', fai: () => formReti(ctx, 'access_list')},
    {testo: 'Customer-Provider-Peer' + (nb.relazione ? ` (adesso: ${nb.relazione})` : ''), fai: () => formCpp(ctx)},
  ];
  const menu = {titolo: `Policy su ${router} verso ${ip}`, voci,
    spiegazione: (nuovo ? `${ip} non è ancora un neighbor di ${router}: viene aggiunto con AS${nuovo.asn}. ` : `${descrivi(ip, nb, info.asn)}. `)
      + (giaScritte(nb) ? `Già scritte: ${giaScritte(nb)}.` : 'Nessuna policy scritta verso questo neighbor.')};
  if (S.op && S.op.conf && S.op.conf.avanti) return menuDa(menu);   // da "neighbor nuovo"
  apriMenu(menu);
  return null;
}

const fissiPolicy = (c, tipo) => ({router: c.router, neighbor: c.ip, tipo, asn_nuovo: c.asn_nuovo});

// caselle delle reti annunciate nel lab (una per rete), prima quelle dell'AS indicato
function campiReti(c, primaAs) {
  const viste = new Set(), righe = [];
  const ordine = x => (String(x.asn) === String(primaAs) ? 0 : 1);
  for (const x of [...c.info.reti_lab].sort((p, q) => ordine(p) - ordine(q))) {
    if (viste.has(x.rete)) continue;
    viste.add(x.rete);
    righe.push({nome: 'r:' + x.rete, tipo: 'si_no', etichetta: `${x.rete} (network di ${x.router}, AS${x.asn})`});
  }
  return [...righe, {nome: 'altre', etichetta: 'Altre reti', aiuto: 'Separate da virgola, es. 1.0.0.0/24.'}];
}

function formValore(c, tipo) {
  const lp = tipo === 'local_pref';
  const scritta = (c.nb.policy || []).some(p => p.tipo === 'route-map' && p.verso === (lp ? 'in' : 'out'));
  apriOperazione({
    operazione: 'policy', titolo: lp ? `Local-preference su ${c.router} da ${c.ip}` : `MED su ${c.router} verso ${c.ip}`,
    spiegazione: (lp
      ? 'Route-map in ingresso con set local-preference: le rotte ricevute da questo neighbor vengono preferite (il valore più alto vince; il predefinito è 100). Senza reti spuntate vale per tutte le rotte.'
      : 'Route-map in uscita con set metric: il vicino preferisce il link con il MED più basso. Si mette sul link da rendere meno preferito.')
      + (scritta ? ' Se esiste già la route-map di questo tipo verso il neighbor, viene sostituita.' : ''),
    fissi: fissiPolicy(c, tipo),
    schema: [{nome: 'valore', etichetta: lp ? 'Local-preference' : 'MED (metric)', tipo: 'numero', obbligatorio: true},
             ...(lp ? campiReti(c, c.nb.remote_as).map(x => (x.nome === 'altre' ? Object.assign({}, x, {aiuto: 'Separate da virgola. Nessuna rete = tutte le rotte del neighbor.'}) : x)) : [])],
    valori: {valore: lp ? 150 : 20},
    prepara: v => parametriPolicy(tipo, v),
  });
}

function formReti(c, tipo) {
  const pl = tipo === 'prefix_list';
  apriOperazione({
    operazione: 'policy', titolo: pl ? `Prefix-list su ${c.router} (neighbor ${c.ip})` : `Access-list su ${c.router} da ${c.ip}`,
    spiegazione: pl
      ? "deny delle reti scelte + permit any. In ingresso: non accetta quelle rotte dal neighbor; in uscita: non gliele annuncia. Se la prefix-list c'è già, le reti nuove si aggiungono."
      : "access-list deny delle reti + permit any, collegata con una route-map in ingresso: le rotte di quelle reti ricevute dal neighbor vengono scartate.",
    fissi: fissiPolicy(c, tipo),
    schema: [...(pl ? [{nome: 'direzione', etichetta: 'Direzione', tipo: 'scelta', obbligatorio: true,
                        opzioni: [['in', 'in: rotte ricevute dal neighbor'], ['out', 'out: rotte annunciate al neighbor']]}] : []),
             ...campiReti(c, c.nb.remote_as)],
    valori: {direzione: 'in'},
    prepara: v => parametriPolicy(tipo, v),
  });
}

// ---------- Customer-Provider-Peer ----------
function formCpp(c, preset = null) {
  const esterno = !c.nb.dispositivo;
  return apriOperazione({
    operazione: 'cpp', titolo: `Customer-Provider-Peer su ${c.router} verso ${c.nb.dispositivo || c.ip}`,
    spiegazione: 'La relazione vista da questo router. Provider o peer: accetta tutto e annuncia solo le reti scelte (le proprie e quelle dei clienti); customer: accetta e annuncia tutto.'
      + (c.nb.relazione_da === 'qui' ? ` Attenzione: la relazione ${c.nb.relazione} è già scritta su ${c.router}, rifarla aggiunge di nuovo le righe.`
        : c.nb.relazione ? ` Proposta: ${c.nb.relazione}, l'inverso di quella scritta su ${c.nb.dispositivo}.` : ''),
    schema: [{nome: 'relazione', etichetta: 'Relazione', tipo: 'scelta', obbligatorio: true, opzioni: Object.entries(REL)},
             ...(esterno ? [{nome: 'vicino', etichetta: 'Nome del vicino', obbligatorio: true, aiuto: 'Il vicino non è un router del lab: serve per i nomi delle prefix-list.'}] : [])],
    valori: {relazione: preset || c.nb.relazione || 'provider', vicino: ''},
    avanti: v => passoCpp(c, v.relazione, esterno ? String(v.vicino).trim() : c.nb.dispositivo),
  });
}

function passoCpp(c, relazione, vicino, poi = true) {
  const fissi = {router: c.router, vicino, ip: c.ip, asn: String(c.nb.remote_as)};
  const conf = {
    operazione: 'cpp', titolo: `${relazione[0].toUpperCase() + relazione.slice(1)} ${vicino} su ${c.router}`, fissi,
    poi: poi && c.nb.dispositivo ? () => latoOpposto(c.router, c.nb.dispositivo, relazione) : null,
  };
  if (relazione === 'customer') return Object.assign(conf, {subito: true, prepara: () => parametriCpp('customer', {}),
    spiegazione: `${vicino} è un cliente di ${c.router}: prefix-list in e out con permit any.`});
  return Object.assign(conf, {
    spiegazione: `${c.router} annuncia a ${vicino} (${relazione}) solo le reti spuntate. Proposte come nelle soluzioni del corso: le reti proprie, i link con i clienti e le reti dei clienti; non i link con provider e peer. Puoi cambiarle.`,
    schema: [...c.info.reti.map(r => ({nome: 'r:' + r.rete, tipo: 'si_no',
      etichetta: `${r.rete} (${r.tipo === 'propria' ? 'rete propria' : r.tipo === 'cliente' ? 'rete del cliente ' + r.con.join(', ') : 'link con ' + r.con.join(', ')})`})),
      {nome: 'altre', etichetta: 'Altre reti', aiuto: 'Separate da virgola, es. 100.10.0.0/16.'}],
    valori: Object.fromEntries(c.info.reti.map(r => ['r:' + r.rete, r.proposta])),
    prepara: v => parametriCpp(relazione, v),
  });
}

// dopo l'applica su un lato: lo stesso link visto dall'altro router, con la relazione inversa
async function latoOpposto(router, altro, relazione) {
  const d = dispositivo(altro);
  if (!d || !d.demoni.includes('bgpd')) return null;
  const info = await opzioni(altro);
  const mio = dispositivo(router);
  const mieiIp = new Set(mio ? mio.interfacce.map(it => ip0(it.ip)).filter(Boolean) : []);
  const ip = Object.keys(info.neighbor).find(i => info.neighbor[i].dispositivo === router || mieiIp.has(i));
  if (!ip) return null;
  const nb = info.neighbor[ip];
  if (nb.relazione_da === 'qui') return null;   // l'altro lato è già impostato
  const inversa = RELAZIONE_INVERSA[relazione];
  const conf = passoCpp({router: altro, ip, info, nb}, inversa, router, false);
  conf.titolo = `Lato opposto: ${conf.titolo}`;
  conf.spiegazione = `Ora l'altro lato: su ${altro}, ${router} è il suo ${inversa}. Applica per configurarlo, oppure "indietro" per lasciarlo così. ` + conf.spiegazione;
  conf.subito = false;                    // anche verso un cliente: si conferma con "Anteprima"
  return conf;
}
