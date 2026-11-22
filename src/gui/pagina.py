# Pagina della GUI: HTML, CSS e JavaScript in un'unica stringa, senza file
# esterni né CDN, così funziona offline e dentro l'eseguibile PyInstaller.
PAGINA = r"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lab Generator GUI</title>
<style>
:root{--bg:#f1f5f9;--pan:#fff;--txt:#0f172a;--mut:#64748b;--bor:#e2e8f0;--acc:#2563eb;--ok:#16a34a;--ko:#dc2626;--warn:#d97706;--okbg:#dcfce7;--kobg:#fee2e2;--warnbg:#fef3c7;--code:#0b1220;--codetxt:#e2e8f0}
@media (prefers-color-scheme: dark){:root{--bg:#0b1220;--pan:#111a2e;--txt:#e2e8f0;--mut:#94a3b8;--bor:#22304a;--acc:#60a5fa;--ok:#4ade80;--ko:#f87171;--warn:#fbbf24;--okbg:#14321f;--kobg:#3b1515;--warnbg:#3a2a0b;--code:#050912;--codetxt:#cbd5e1}}
*{box-sizing:border-box}
body{margin:0;font:14px/1.45 system-ui,-apple-system,"Segoe UI",Ubuntu,sans-serif;background:var(--bg);color:var(--txt)}
button{font:inherit;border:1px solid var(--acc);background:var(--acc);color:#fff;border-radius:7px;padding:6px 12px;cursor:pointer}
button:hover{filter:brightness(1.08)}
button:disabled{opacity:.5;cursor:default}
button.ghost{background:transparent;color:var(--acc)}
button.danger{background:var(--ko);border-color:var(--ko)}
button.small{padding:3px 8px;font-size:12.5px}
input,select{font:inherit;padding:5px 8px;border:1px solid var(--bor);border-radius:7px;background:var(--pan);color:var(--txt)}
code,pre{font-family:ui-monospace,"Cascadia Mono",Consolas,"DejaVu Sans Mono",monospace;font-size:12.5px}
.muted{color:var(--mut)}.small{font-size:12.5px}
.sp{flex:1}
header.top{height:50px;display:flex;align-items:center;gap:14px;padding:0 16px;background:var(--pan);border-bottom:1px solid var(--bor)}
.brand{font-weight:700;font-size:16px}.brand span{color:var(--acc)}
.wrap{display:grid;grid-template-columns:220px 1fr;height:calc(100vh - 50px)}
aside{background:var(--pan);border-right:1px solid var(--bor);overflow:auto;padding:12px}
.aside-h{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
#base{overflow-wrap:anywhere}
#labs{list-style:none;margin:0 0 12px;padding:0}
#labs li{padding:7px 9px;border-radius:7px;cursor:pointer;display:flex;align-items:center;gap:8px}
#labs li:hover{background:var(--bg)}
#labs li.on{background:var(--acc);color:#fff}
.dot{width:9px;height:9px;border-radius:50%;background:var(--mut);opacity:.5;flex:none}
.dot.acceso{background:var(--ok);opacity:1}
main{display:flex;flex-direction:column;min-width:0;min-height:0}
#scorri{flex:1;overflow:auto;padding:14px 18px}
.vuoto{padding:40px;color:var(--mut)}
.labhead{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.labhead h1{font-size:20px;margin:0}
.badge{font-size:12px;padding:2px 9px;border-radius:20px;background:var(--bor);color:var(--mut)}
.badge.ok{background:var(--okbg);color:var(--ok)}.badge.ko{background:var(--kobg);color:var(--ko)}.badge.warn{background:var(--warnbg);color:var(--warn)}
.nota{margin:10px 0 0;padding:8px 12px;border-radius:8px;background:var(--warnbg);color:var(--txt);border:1px solid var(--warn)}
nav.tabs{display:flex;gap:4px;margin:14px 0 12px;border-bottom:1px solid var(--bor);flex-wrap:wrap}
nav.tabs button{background:transparent;color:var(--mut);border:none;border-bottom:2px solid transparent;border-radius:0;padding:8px 12px}
nav.tabs button.on{color:var(--acc);border-bottom-color:var(--acc);font-weight:600}
.card{background:var(--pan);border:1px solid var(--bor);border-radius:10px;padding:14px;margin-bottom:14px}
.card h2{font-size:15px;margin:0 0 10px}
.card h3{font-size:14px;margin:0 0 6px}
.topo{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:14px}
.canvas{background:#fff;border:1px solid var(--bor);border-radius:10px;height:max(420px,calc(100vh - 420px));display:flex;flex-direction:column;overflow:hidden}
.toolbar{display:flex;gap:10px;align-items:center;padding:7px 10px;border-bottom:1px solid #e2e8f0;flex-wrap:wrap;color:#334155}
.toolbar .muted{color:#64748b}
.toolbar button.ghost{color:#2563eb;border-color:#2563eb}
svg.mappa{flex:1;width:100%;min-height:0;touch-action:none;user-select:none}
.side{background:var(--pan);border:1px solid var(--bor);border-radius:10px;padding:12px;max-height:max(420px,calc(100vh - 420px));overflow:auto}
a{color:var(--acc)}
.side h3{margin:0 0 4px;font-size:16px}
.btns{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
table{border-collapse:collapse;width:100%}
th,td{text-align:left;padding:4px 8px;border-bottom:1px solid var(--bor);vertical-align:top}
th{font-weight:600;color:var(--mut);font-size:12.5px}
.griglia{display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:14px}
ul.avvisi{margin:4px 0 0;padding-left:20px}
ul.avvisi li{margin:3px 0}
.okline{color:var(--ok)}.koline{color:var(--ko)}.warnline{color:var(--warn)}
details{margin:6px 0}summary{cursor:pointer;color:var(--acc)}
pre.file{background:var(--code);color:var(--codetxt);padding:8px 10px;border-radius:8px;overflow:auto;max-height:300px;margin:6px 0}
.output{height:170px;flex:none;border-top:1px solid var(--bor);background:var(--code);color:var(--codetxt);display:flex;flex-direction:column}
.out-h{display:flex;align-items:center;gap:10px;padding:5px 12px;border-bottom:1px solid #1e293b}
.out-h button.ghost{color:#93c5fd;border-color:#334155}
#outTesto{flex:1;overflow:auto;margin:0;padding:8px 12px;white-space:pre-wrap}
.mat td,.mat th{text-align:center;padding:3px 5px;font-size:12.5px;border:1px solid var(--bor)}
.mat th.v{vertical-align:bottom;height:110px}
.mat th.v span{writing-mode:vertical-rl;transform:rotate(180deg)}
.mat td.ok{background:var(--okbg);color:var(--ok)}.mat td.ko{background:var(--kobg);color:var(--ko);font-weight:600}
tr.sosp td{background:var(--warnbg)}tr.best td{background:var(--okbg)}table.intf td{font-size:13px}
.mat td.mezzo{background:var(--warnbg);color:var(--warn);font-weight:600}.mat td.self{color:var(--mut)}
.mat th:first-child,.mat tr th{text-align:left}
.scroll{overflow:auto}
.riga{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:8px 0}
.hop{display:flex;gap:10px;padding:3px 0}.hop b{min-width:22px}
@media (max-width:1100px){.topo{grid-template-columns:1fr}.side{max-height:none}}
@media (max-width:700px){.wrap{grid-template-columns:1fr}aside{max-height:160px}}
</style>
</head>
<body>
<header class="top">
  <div class="brand">Lab Generator <span>GUI</span></div>
  <div id="info" class="muted small"></div>
  <div class="sp"></div>
  <button id="bEsci" class="ghost small">Chiudi GUI</button>
</header>
<div class="wrap">
  <aside>
    <div class="aside-h"><b>Lab</b><button id="bAggiorna" class="ghost small">Aggiorna</button></div>
    <ul id="labs"></ul>
    <div class="muted small" id="base"></div>
  </aside>
  <main>
    <div id="scorri">
      <div id="vuoto" class="vuoto">Scegli un lab dall'elenco a sinistra.</div>
      <div id="vista" hidden>
        <div class="labhead">
          <h1 id="labNome"></h1><span id="labStato" class="badge"></span>
          <div class="sp"></div>
          <button id="bStart">▶ Avvia (lstart)</button>
          <button id="bClean" class="danger">■ Ferma (lclean)</button>
          <button id="bRileggi" class="ghost">Rileggi i file</button>
        </div>
        <div id="xmlNota" class="nota" hidden></div>
        <div id="modNota" class="nota" hidden></div>
        <div id="linkNota" class="nota" hidden></div>
        <nav class="tabs" id="tabs">
          <button data-tab="topo" class="on">Topologia</button>
          <button data-tab="riep">Riepilogo e controlli</button>
          <button data-tab="intf">Interfacce</button>
          <button data-tab="test">Test</button>
          <button data-tab="arch">Archivio</button>
          <button data-tab="reg">Registro</button>
        </nav>
        <section id="t-topo">
          <div class="topo">
            <div class="canvas">
              <div class="toolbar">
                <button id="bRiordina" class="ghost small">Riordina</button>
                <button id="bAdatta" class="ghost small">Adatta</button>
                <label class="small"><input type="checkbox" id="cIface" checked> interfacce</label>
                <button id="bSvg" class="ghost small">Scarica immagine (SVG)</button>
                <button id="bTogli" class="ghost small" hidden>Togli evidenziazione</button>
                <span class="muted small">Trascina i nodi o lo sfondo · rotellina per lo zoom · clic su un dispositivo per i comandi</span>
              </div>
              <svg id="svg" class="mappa"></svg>
            </div>
            <div id="side" class="side"></div>
          </div>
        </section>
        <section id="t-riep" hidden></section>
        <section id="t-intf" hidden>
          <div class="card">
            <h2>Interfacce</h2>
            <div class="muted small">Una riga per interfaccia, da confrontare con la figura: chi c'è dall'altra parte, IGP e costo, sessioni BGP e policy. In giallo le righe sospette.</div>
            <div class="riga">
              <input id="iFiltro" placeholder="Filtra (dispositivo, LAN, IP...)" size="28">
              <label class="small"><input type="checkbox" id="iSolo"> solo righe con avvisi</label>
              <button id="bReali" class="ghost small">Confronta con il lab acceso</button>
            </div>
            <div id="rIntf" class="scroll"></div>
          </div>
        </section>
        <section id="t-test" hidden>
          <div class="card">
            <h2>Raggiungibilità</h2>
            <div class="muted small">Da ogni dispositivo, ping verso tutti gli IP degli altri (2 tentativi). Il lab deve essere avviato da almeno 1-2 minuti, il tempo che BGP converga.</div>
            <div class="riga"><button id="bPing">Esegui il test</button></div>
            <div id="rPing"></div>
          </div>
          <div class="card">
            <h2>Sessioni BGP e OSPF</h2>
            <div class="muted small">Per ogni router: neighbor BGP configurati (devono essere <b>Established</b>) e vicini OSPF (devono essere <b>Full</b>).</div>
            <div class="riga"><button id="bSessioni">Leggi le sessioni</button>
              <button id="bConv" class="ghost">Attendi convergenza (fino a 5 min)</button></div>
            <div id="rSessioni"></div>
          </div>
          <div class="card">
            <h2>Rotta verso una rete</h2>
            <div class="muted small">Come un router raggiunge una rete: next-hop scelto e tutti i percorsi BGP ricevuti con local-preference, MED e AS-path. Serve per "prefers…", "local preference", "MED", "filters out…".</div>
            <div class="riga">
              <label>Router <select id="rDev"></select></label>
              <label>rete o IP <input id="rRete" list="retiList" placeholder="es. 100.0.0.0/8" size="18"></label>
              <button id="bRotta">Mostra</button>
            </div>
            <div id="rRotta"></div>
          </div>
          <div class="card">
            <h2>Tabelle di routing</h2>
            <div class="muted small">Per ogni router, quali reti del lab sono nella tabella e verso chi. È il controllo "kernel_routes" della correzione automatica.</div>
            <div class="riga"><button id="bTabelle">Leggi le tabelle</button></div>
            <div id="rTabelle"></div>
          </div>
          <div class="card">
            <h2>Ping</h2>
            <div class="muted small">Ping da un dispositivo verso un IP del lab (dall'elenco) o uno qualsiasi. L'output compare in diretta nel riquadro Output.
              "Origine" sceglie l'IP da cui parte il ping (<code>ping -I</code>): da un router, in automatico parte dall'interfaccia di uscita.</div>
            <div class="riga">
              <label>Da <select id="pnSrc"></select></label>
              <label>verso <input id="pnDst" list="ipList" placeholder="IP di destinazione" size="18"></label>
              <label>Origine <select id="pnOrig"></select></label>
              <button id="bPn">Ping</button>
            </div>
            <div id="rPn"></div>
          </div>
          <div class="card">
            <h2>Verifica percorso</h2>
            <div class="muted small">Traceroute da un dispositivo verso un IP: gli hop diventano router e LAN, evidenziati sulla topologia. Serve per le richieste del tipo "i pacchetti devono attraversare ...".</div>
            <div class="riga">
              <label>Da <select id="pSrc"></select></label>
              <label>verso <input id="pDst" list="ipList" placeholder="IP di destinazione" size="18"></label>
              <button id="bPercorso">Traccia il percorso</button>
            </div>
            <div class="riga">
              <label>Atteso <input id="pAtt" placeholder="es. G F  oppure  as20r1 as20r4" size="26"></label>
              <label><input type="radio" name="pModo" value="per" checked> deve passare per</label>
              <label><input type="radio" name="pModo" value="esatta"> sequenza esatta</label>
            </div>
            <div class="riga">
              <label><input type="checkbox" id="pRit"> anche il ritorno</label>
              <label>atteso al ritorno <input id="pAttR" placeholder="es. H F" size="26"></label>
            </div>
            <div class="muted small">"Atteso" è facoltativo: nomi delle LAN (le lettere della figura) oppure dei dispositivi, separati da spazi.
              "Deve passare per" = quei link in quell'ordine, anche con altri in mezzo; "sequenza esatta" = tutto il percorso.</div>
            <div id="rPercorso"></div>
          </div>
          <div class="card">
            <h2>Guasto di un link</h2>
            <div class="muted small">Spegne un link (<code>ip link set ethX down</code> su tutti i dispositivi della LAN) per vedere il percorso di riserva:
              "se il link X si guasta, il traffico deve passare per…". Vale solo a lab acceso, i file non cambiano; "Riaccendi" (o un riavvio del lab) rimette tutto com'era.</div>
            <div class="riga">
              <label>LAN <select id="gLan"></select></label>
              <button id="gGiu" class="danger">Spegni</button>
              <button id="gSu" class="ghost">Riaccendi</button>
            </div>
            <div id="rGuasto"></div>
          </div>
        </section>
        <section id="t-arch" hidden>
          <div class="card">
            <h2>Archivio per la consegna</h2>
            <div class="muted small">Crea l'archivio nella cartella dei lab, <b>senza l'XML del generatore</b>. Il formato richiesto per la consegna è <code>.tar.gz</code>.</div>
            <div class="riga">
              <label>Nome <input id="aNome" size="22"></label>
              <label><input type="radio" name="aFmt" value="tar.gz" checked> .tar.gz</label>
              <label><input type="radio" name="aFmt" value="zip"> .zip</label>
              <button id="bArchivio">Crea archivio</button>
            </div>
            <div id="aAvviso" class="nota" hidden></div>
            <div id="rArchivio"></div>
          </div>
        </section>
        <section id="t-reg" hidden>
          <div class="card">
            <h2>Registro operazioni</h2>
            <div id="rRegistro"></div>
          </div>
        </section>
      </div>
    </div>
    <div class="output">
      <div class="out-h"><b id="outTitolo">Output</b><span id="outStato" class="small"></span><div class="sp"></div><button id="bPulisci" class="ghost small">Pulisci</button></div>
      <pre id="outTesto"></pre>
    </div>
  </main>
</div>
<datalist id="ipList"></datalist>
<datalist id="retiList"></datalist>
<script>
"use strict";
const $ = s => document.querySelector(s);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pausa = ms => new Promise(r => setTimeout(r, ms));
const S = {labs: [], stato: {}, lab: null, nome: null, sel: null, G: null, pos: null, vb: null, evid: null, tab: 'topo'};
const COL = ['#2563eb','#16a34a','#dc2626','#9333ea','#ea580c','#0891b2','#ca8a04','#db2777','#4f46e5','#65a30d','#0f766e','#b45309'];

function mem(k, v) {           // localStorage opzionale (posizioni dei nodi)
  try { if (v === undefined) return JSON.parse(localStorage.getItem(k) || 'null'); localStorage.setItem(k, JSON.stringify(v)); } catch (e) { return null; }
}
async function api(path) {
  const r = await fetch(path); const j = await r.json();
  if (!r.ok) throw new Error(j.errore || r.status); return j;
}
async function azione(dati) {
  const r = await fetch('/api/azione', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Lab-Gen': '1'}, body: JSON.stringify(Object.assign({lab: S.nome}, dati))});
  const j = await r.json();
  if (!r.ok) throw new Error(j.errore || r.status); return j;
}

// ---------- output dei comandi ----------
function outInizio(titolo) { $('#outTitolo').textContent = titolo; $('#outStato').textContent = ' in corso…'; $('#outStato').className = 'small warnline'; $('#outTesto').textContent = ''; }
function outScrivi(righe) { const p = $('#outTesto'); const giu = p.scrollTop + p.clientHeight >= p.scrollHeight - 5; p.textContent += righe.map(r => r + '\n').join(''); if (giu) p.scrollTop = p.scrollHeight; }
function outFine(ok, testo) { $('#outStato').textContent = ' ' + testo; $('#outStato').className = 'small ' + (ok ? 'okline' : 'koline'); }
function errore(e) { outInizio('Errore'); outScrivi([String(e.message || e)]); outFine(false, 'errore'); }

// il riquadro Output mostra solo l'ultimo lavoro avviato: uno più vecchio ancora in corso
// (es. la convergenza partita dopo lstart) continua in silenzio e il suo risultato arriva
// comunque alla sua card e al Registro, senza mescolare le righe con quelle del nuovo
async function segui(lid, titolo) {
  S.visibile = lid; outInizio(titolo); let da = 0;
  for (;;) {
    const r = await api('/api/lavoro?id=' + lid + '&da=' + da), mio = S.visibile === lid;
    if (r.righe.length && mio) outScrivi(r.righe); da = r.totale;
    if (r.fatto) { if (mio) outFine(r.rc === 0, r.rc === 0 ? 'completato' : 'terminato con errore (' + r.rc + ')'); if (S.tab === 'reg') registro(); return r; }
    await pausa(600);
  }
}
async function esegui(dati, titolo, bottone) {
  if (bottone) bottone.disabled = true;
  try { const j = await azione(dati); return await segui(j.lavoro, titolo); }
  catch (e) { errore(e); return null; }
  finally { if (bottone) bottone.disabled = false; }
}

// ---------- elenco lab e stato ----------
async function caricaLabs() {
  try { S.labs = (await api('/api/labs')).labs; } catch (e) { errore(e); }
  disegnaLabs(); aggiornaStato();
}
async function aggiornaStato() {
  try { S.stato = await api('/api/stato'); } catch (e) { return; }
  disegnaLabs(); testaLab();
}
function disegnaLabs() {
  $('#labs').innerHTML = S.labs.map(l => {
    const n = (S.stato[l] || []).length;
    return `<li data-lab="${esc(l)}" class="${l === S.nome ? 'on' : ''}"><span class="dot ${n ? 'acceso' : ''}"></span>${esc(l)}${n ? ` <span class="small">(${n})</span>` : ''}</li>`;
  }).join('') || '<li class="muted">Nessun lab trovato</li>';
}
const SCHEDE = ['topo', 'riep', 'intf', 'test', 'arch', 'reg'];
function testaLab() {
  if (!S.lab) return;
  controllaModificati(); controllaSpenti();
  const tot = S.lab.dispositivi.length, acc = (S.stato[S.nome] || []).length;
  const b = $('#labStato');
  b.textContent = acc === 0 ? 'spento' : (acc === tot ? 'avviato (' + acc + '/' + tot + ')' : 'parziale (' + acc + '/' + tot + ')');
  b.className = 'badge ' + (acc === 0 ? '' : (acc === tot ? 'ok' : 'warn'));
}

async function apriLab(nome, mantieni) {
  try {
    const lab = await api('/api/lab?nome=' + encodeURIComponent(nome));
    const cambiato = nome !== S.nome;
    S.lab = lab; S.nome = nome; S.sintassi = null;   // i file possono essere cambiati: sintassi da ricontrollare
    history.replaceState(null, '', '#lab=' + encodeURIComponent(nome) + '&tab=' + S.tab);
    if (cambiato) { S.sel = null; S.evid = null; $('#rPing').innerHTML = $('#rSessioni').innerHTML = $('#rPercorso').innerHTML = $('#rArchivio').innerHTML = ''; }
    $('#vuoto').hidden = true; $('#vista').hidden = false;
    $('#labNome').textContent = nome;
    $('#xmlNota').hidden = !lab.xml;
    $('#xmlNota').innerHTML = `Nel lab c'è <code>${esc(nome)}.xml</code> del generatore: <b>va tolto prima della consegna</b> (l'archivio creato da qui lo esclude già). Aprendo il lab dalle Opzioni del terminale puoi spostarlo in <code>.labgenerator/</code>, accanto ai lab.`;
    S.colori = colori(lab); S.G = grafo(lab);
    const salvate = mem('pos:' + nome);
    S.varianti = null; S.variante = 0;
    S.pos = (salvate && S.G.nodes.every(n => salvate[n.id])) ? salvate : (S.varianti = varianti(S.G))[0];
    if (!mantieni || cambiato) S.vb = null;
    $('#ipList').innerHTML = lab.dispositivi.flatMap(d => d.interfacce.filter(i => i.ip).map(i => `<option value="${esc(i.ip.split('/')[0])}">${esc(d.nome + ' ' + i.dev)}</option>`)
      .concat(d.loopback.map(ip => `<option value="${esc(ip.split('/')[0])}">${esc(d.nome + ' lo')}</option>`))).join('');
    $('#pSrc').innerHTML = lab.dispositivi.map(d => `<option>${esc(d.nome)}</option>`).join('');
    $('#pnSrc').innerHTML = $('#pSrc').innerHTML; origini();
    if (cambiato) { $('#rPn').innerHTML = $('#rGuasto').innerHTML = ''; S.spenti = null; $('#linkNota').hidden = true; }
    lanGuasto();
    $('#rDev').innerHTML = lab.dispositivi.filter(d => d.tipo === 'router').map(d => `<option>${esc(d.nome)}</option>`).join('');
    $('#retiList').innerHTML = [...new Set(lab.lan.map(l => l.subnet).concat(lab.dispositivi.flatMap(d => (d.riepilogo || {}).bgp_networks || [])))]
      .filter(Boolean).map(r => `<option value="${esc(r)}"></option>`).join('');
    if (cambiato) { $('#rRotta').innerHTML = $('#rTabelle').innerHTML = ''; S.reali = null; }
    interfacce(); avvisoArchivio();
    if (!$('#aNome').value || cambiato) $('#aNome').value = nome;
    disegnaLabs(); testaLab(); ridisegna(); lato(); riepilogo();
  } catch (e) { errore(e); }
}

// ---------- topologia ----------
function colori(lab) {
  const gs = [...new Set(lab.dispositivi.map(d => d.gruppo).filter(Boolean))].sort((a, b) => a - b);
  const m = {}; gs.forEach((g, i) => m[g] = COL[i % COL.length]); return m;
}
function grafo(lab) {
  const nodes = [], links = [];
  for (const d of lab.dispositivi) nodes.push({id: 'd:' + d.nome, nome: d.nome, tipo: d.tipo, gruppo: d.gruppo || '_', dev: d});
  for (const l of lab.lan) {
    const ms = [];
    for (const d of lab.dispositivi) for (const it of d.interfacce) if (it.lan === l.nome) ms.push({d, it});
    if (ms.length === 2 && ms[0].d.nome !== ms[1].d.nome) {
      links.push({a: 'd:' + ms[0].d.nome, b: 'd:' + ms[1].d.nome, lan: l.nome, subnet: l.subnet, ia: ms[0].it, ib: ms[1].it});
    } else {
      nodes.push({id: 'l:' + l.nome, nome: l.nome, tipo: 'lan', subnet: l.subnet, gruppo: null});
      for (const m of ms) links.push({a: 'd:' + m.d.nome, b: 'l:' + l.nome, lan: l.nome, subnet: l.subnet, ia: m.it, ib: null});
    }
  }
  // una LAN tutta dentro un AS appartiene a quell'AS (per il riquadro dell'AS)
  for (const n of nodes) if (n.tipo === 'lan') {
    const gs = new Set(links.filter(l => l.b === n.id).map(l => nodes.find(x => x.id === l.a).gruppo));
    n.gruppo = gs.size === 1 ? [...gs][0] : null;
  }
  return {nodes, links};
}
// generatore pseudo-casuale con seme: stessa variante = stessa disposizione
function casuale(seme) {
  let t = (seme * 2654435761) >>> 0;
  return () => { t = (t + 0x6D2B79F5) >>> 0; let r = Math.imul(t ^ (t >>> 15), 1 | t); r ^= r + Math.imul(r ^ (r >>> 7), 61 | r); return ((r ^ (r >>> 14)) >>> 0) / 4294967296; };
}
function mescola(v, rnd) { v = v.slice(); for (let i = v.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [v[i], v[j]] = [v[j], v[i]]; } return v; }
function disponi(G, seme) {
  const pos = {}, membri = {}, rnd = casuale(seme || 0);
  for (const n of G.nodes) if (n.tipo !== 'lan') (membri[n.gruppo] = membri[n.gruppo] || []).push(n);
  let gruppi = Object.keys(membri).sort((a, b) => (+a || 1e9) - (+b || 1e9));
  if (seme) gruppi = mescola(gruppi, rnd);
  const R = gruppi.length > 1 ? 150 + 75 * gruppi.length : 0, centro = {};
  gruppi.forEach((g, i) => { const a = 2 * Math.PI * i / gruppi.length - Math.PI / 2; centro[g] = {x: R * Math.cos(a), y: R * Math.sin(a)}; });
  for (const g of gruppi) { const ms = seme ? mescola(membri[g], rnd) : membri[g], r = ms.length > 1 ? 45 + 14 * ms.length : 0;
    ms.forEach((n, i) => { const a = 2 * Math.PI * i / ms.length; pos[n.id] = {x: centro[g].x + r * Math.cos(a), y: centro[g].y + r * Math.sin(a)}; }); }
  for (const n of G.nodes) if (n.tipo === 'lan') {
    const ls = G.links.filter(l => l.b === n.id); let x = 0, y = 0;
    ls.forEach(l => { x += pos[l.a].x; y += pos[l.a].y; });
    const k = Math.max(ls.length, 1); pos[n.id] = {x: x / k + 9, y: y / k + 9};
  }
  // lunghezza a riposo dei link: abbastanza per le etichette che ci stanno sopra
  const riposo = l => l.b.startsWith('l:') ? Math.max(115, 60 + largIface(l.ia))
    : Math.max(210, 56 + largIface(l.ia) + largIface(l.ib) + largLan(l));
  const N = G.nodes.length, IT = 700;
  for (let it = 0; it < IT; it++) {
    const f = {}; G.nodes.forEach(n => f[n.id] = {x: 0, y: 0});
    for (let i = 0; i < N; i++) for (let j = i + 1; j < N; j++) {
      const a = G.nodes[i], b = G.nodes[j], pa = pos[a.id], pb = pos[b.id];
      let dx = pa.x - pb.x, dy = pa.y - pb.y, d2 = dx * dx + dy * dy;
      if (d2 < 1) { dx = (i - j) * 0.1; dy = 0.5; d2 = dx * dx + dy * dy; }
      const altro = a.gruppo && b.gruppo && a.gruppo !== b.gruppo;
      const d = Math.sqrt(d2), k = (altro ? 34000 : 16000) / d2;
      f[a.id].x += k * dx / d; f[a.id].y += k * dy / d; f[b.id].x -= k * dx / d; f[b.id].y -= k * dy / d;
    }
    for (const l of G.links) {
      const pa = pos[l.a], pb = pos[l.b], dx = pb.x - pa.x, dy = pb.y - pa.y, d = Math.sqrt(dx * dx + dy * dy) || 1;
      const k = (d - riposo(l)) * 0.06;
      f[l.a].x += k * dx / d; f[l.a].y += k * dy / d; f[l.b].x -= k * dx / d; f[l.b].y -= k * dy / d;
    }
    // coesione dell'AS solo tra i router: gli host restano all'esterno, vicino al loro router
    for (const g of gruppi) { const ms = membri[g].filter(n => n.tipo === 'router'); if (g === '_' || ms.length < 2) continue;
      let cx = 0, cy = 0; ms.forEach(n => { cx += pos[n.id].x; cy += pos[n.id].y; }); cx /= ms.length; cy /= ms.length;
      ms.forEach(n => { f[n.id].x += (cx - pos[n.id].x) * 0.012; f[n.id].y += (cy - pos[n.id].y) * 0.012; }); }
    const T = 40 * (1 - it / IT) + 0.5;
    for (const n of G.nodes) { const v = f[n.id], m = Math.sqrt(v.x * v.x + v.y * v.y) || 1, s = Math.min(m, T) / m; pos[n.id].x += v.x * s; pos[n.id].y += v.y * s; }
  }
  return pos;
}
// qualità di una disposizione: incroci tra link + nodi appoggiati su link non loro (meno = meglio)
function difetti(G, pos) {
  const seg = G.links.map(l => [pos[l.a], pos[l.b], l.a, l.b]);
  const cr = (o, a, b) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
  let n = 0;
  for (let i = 0; i < seg.length; i++) for (let j = i + 1; j < seg.length; j++) {
    const [p1, p2, a1, b1] = seg[i], [q1, q2, a2, b2] = seg[j];
    if (a1 === a2 || a1 === b2 || b1 === a2 || b1 === b2) continue;
    if (cr(p1, p2, q1) * cr(p1, p2, q2) < 0 && cr(q1, q2, p1) * cr(q1, q2, p2) < 0) n += 1;
  }
  for (const nd of G.nodes) { const p = pos[nd.id];
    for (const [a, b, ia, ib] of seg) {
      if (ia === nd.id || ib === nd.id) continue;
      const dx = b.x - a.x, dy = b.y - a.y, L = dx * dx + dy * dy || 1;
      const t = Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / L));
      if (Math.hypot(a.x + t * dx - p.x, a.y + t * dy - p.y) < 34) n += 0.7;
    }
  }
  return n;
}
// varie disposizioni (semi diversi), dalla migliore alla peggiore; "Riordina" le scorre
// ruota la disposizione in modo che il lato lungo sia orizzontale (il riquadro è largo)
function orizzontale(pos) {
  const ps = Object.values(pos), n = ps.length || 1;
  const mx = ps.reduce((s, p) => s + p.x, 0) / n, my = ps.reduce((s, p) => s + p.y, 0) / n;
  let sxx = 0, syy = 0, sxy = 0;
  ps.forEach(p => { const dx = p.x - mx, dy = p.y - my; sxx += dx * dx; syy += dy * dy; sxy += dx * dy; });
  const a = -0.5 * Math.atan2(2 * sxy, sxx - syy), c = Math.cos(a), s = Math.sin(a);
  for (const k in pos) { const dx = pos[k].x - mx, dy = pos[k].y - my; pos[k] = {x: dx * c - dy * s, y: dx * s + dy * c}; }
  return pos;
}
function varianti(G) {
  const v = [];
  for (let s = 0; s < 10; s++) { const pos = orizzontale(disponi(G, s)); v.push({pos, d: difetti(G, pos)}); }
  return v.sort((a, b) => a.d - b.d).map(x => x.pos);
}
function inviluppo(p) {
  if (p.length < 3) return p;
  p = p.slice().sort((a, b) => a.x - b.x || a.y - b.y);
  const cr = (o, a, b) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x), lo = [], up = [];
  for (const q of p) { while (lo.length >= 2 && cr(lo[lo.length - 2], lo[lo.length - 1], q) <= 0) lo.pop(); lo.push(q); }
  for (const q of p.slice().reverse()) { while (up.length >= 2 && cr(up[up.length - 2], up[up.length - 1], q) <= 0) up.pop(); up.push(q); }
  return lo.slice(0, -1).concat(up.slice(0, -1));
}
function evidLink(l) {
  const e = S.evid; if (!e || !e.lan.has(l.lan)) return false;
  return e.dev.has(l.a.slice(2)) && (l.b.startsWith('l:') || e.dev.has(l.b.slice(2)));
}
const STILE_SVG = `<style>
.lk{stroke:#94a3b8;stroke-width:2}.lk.ev{stroke:#f59e0b;stroke-width:6}.lk.manca{stroke:#dc2626;stroke-width:6;opacity:.45}
.lk.off{stroke:#dc2626;stroke-width:3;stroke-dasharray:9 6;opacity:1}
.t{font:600 12.5px system-ui,sans-serif;fill:#0f172a;paint-order:stroke;stroke:#fff;stroke-width:4px;stroke-linejoin:round}
.ts{font:10.5px system-ui,sans-serif;fill:#475569;paint-order:stroke;stroke:#fff;stroke-width:3px;stroke-linejoin:round}
.pill{fill:#fff;stroke:#94a3b8;stroke-width:1}.pt{font:600 11px system-ui,sans-serif;fill:#334155}
.nt{font:700 11px system-ui,sans-serif;fill:#fff}.lt{font:11px system-ui,sans-serif;fill:#334155}.lb{font-weight:700;fill:#0f172a}
.ga{font:700 16px system-ui,sans-serif;paint-order:stroke;stroke:#fff;stroke-width:5px;stroke-linejoin:round}.gp{font:600 12px system-ui,sans-serif}.nodo{cursor:pointer}
.sel{stroke:#0f172a;stroke-width:2.5;fill:none;stroke-dasharray:4 3}
.ring{stroke:#f59e0b;stroke-width:5;fill:none}.ord{font:700 11px system-ui,sans-serif;fill:#fff}
</style>`;
const largh = (testo, px) => testo.length * px * 0.62;
// protocolli interni di un AS (dai demoni FRR dei suoi router)
function igpGruppo(G, g) {
  const p = new Set();
  for (const n of G.nodes) if (n.gruppo === g && n.dev) {
    if (n.dev.demoni.includes('ospfd')) p.add('OSPF');
    if (n.dev.demoni.includes('ripd')) p.add('RIP');
  }
  return [...p].sort().join(' + ');
}
// nome del dispositivo dal lato più libero dai collegamenti (di preferenza sotto)
function latoNome(G, pos, n) {
  const p = pos[n.id], ang = [];
  for (const l of G.links) {
    const o = l.a === n.id ? l.b : (l.b === n.id ? l.a : null);
    if (o) ang.push(Math.atan2(pos[o].y - p.y, pos[o].x - p.x));
  }
  let meglio = Math.PI / 2, punti = -1;
  for (const k of [2, 6, 0, 4, 1, 3, 5, 7]) {          // sotto, sopra, destra, sinistra, diagonali
    const a = k * Math.PI / 4;
    const dist = ang.length ? Math.min(...ang.map(b => { const d = Math.abs(a - b) % (2 * Math.PI); return Math.min(d, 2 * Math.PI - d); })) : Math.PI;
    if (dist > punti + 0.35) { punti = dist; meglio = a; }
  }
  return meglio;
}
// etichetta di interfaccia: [eth0|1] = nome dell'interfaccia + ultimo numero dell'IP
const numIp = it => it.ip ? it.ip.split('/')[0].split('.')[3] : '';
const largIface = it => largh(it.dev, 11) + 8 + (numIp(it) ? largh(numIp(it), 11) + 9 : 0);
const largLan = l => largh(l.lan + '  ' + (l.subnet || ''), 11) + 10;
function etichettaIface(it, x, y, colore) {
  const num = numIp(it);
  const w1 = largh(it.dev, 11) + 8, w2 = num ? largh(num, 11) + 9 : 0, w = w1 + w2, x0 = x - w / 2;
  let h = `<rect class="pill" x="${x0}" y="${y - 9}" width="${w}" height="18" rx="4"/>`;
  h += `<text class="pt" x="${x0 + w1 / 2}" y="${y + 4}" text-anchor="middle">${esc(it.dev)}</text>`;
  if (num) h += `<rect x="${x0 + w1}" y="${y - 9}" width="${w2}" height="18" rx="4" fill="${colore}"/><rect x="${x0 + w1}" y="${y - 9}" width="4" height="18" fill="${colore}"/>`
             + `<text class="nt" x="${x0 + w1 + w2 / 2}" y="${y + 4}" text-anchor="middle">${esc(num)}</text>`;
  return h;
}
const RAGGIO = {router: 22, host: 19, www: 19, dns: 19};
// Posizione delle etichette senza sovrapposizioni. Ogni etichetta scivola lungo il
// proprio link (s = distanza dal primo nodo) e, se non basta, si scosta di poco di lato
// (o); nodi, nomi dei dispositivi e subnet delle LAN sono ostacoli fissi.
function posizionaEtichette(G, pos, iface, extra) {
  const et = [], ost = extra.slice(), byId = {};
  G.nodes.forEach(n => byId[n.id] = n);
  const nomi = {};
  for (const n of G.nodes) {
    const p = pos[n.id];
    if (n.tipo === 'lan') {
      ost.push({x: p.x, y: p.y, w: Math.max(34, 9 * n.nome.length + 16), h: 24});
      if (n.subnet) ost.push({x: p.x, y: p.y + 23, w: largh(n.subnet, 10.5) + 4, h: 13});
      continue;
    }
    const r = RAGGIO[n.tipo] || 20;
    ost.push({x: p.x, y: p.y, w: 2 * r, h: 2 * r});
    const a = latoNome(G, pos, n), cx = Math.cos(a), cy = Math.sin(a), w = largh(n.nome, 12.5) + 4;
    const anc = cx > 0.5 ? 'start' : (cx < -0.5 ? 'end' : 'middle');
    const tx = p.x + cx * 30, ty = p.y + cy * 32;
    nomi[n.id] = {anc, x: tx, y: ty + 4.5};
    ost.push({x: tx + (anc === 'start' ? w / 2 : anc === 'end' ? -w / 2 : 0), y: ty, w, h: 17});
  }
  const raggio = id => byId[id].tipo === 'lan' ? Math.max(17, (9 * byId[id].nome.length + 16) / 2) : (RAGGIO[byId[id].tipo] || 20);
  for (const l of G.links) {
    const A = pos[l.a], B = pos[l.b], dx = B.x - A.x, dy = B.y - A.y, len = Math.sqrt(dx * dx + dy * dy) || 1;
    const ux = dx / len, uy = dy / len;
    const est = (w, h) => w / 2 * Math.abs(ux) + h / 2 * Math.abs(uy);     // ingombro lungo il link
    const base = {ax: A.x, ay: A.y, ux, uy, len, o: 0, h: 18};
    if (!l.b.startsWith('l:')) {
      const w = largLan(l);
      et.push(Object.assign({}, base, {tipo: 'lan', l, w, s: len / 2, sMin: len * 0.3, sMax: len * 0.7}));
    }
    if (!iface) continue;
    if (l.ia) {
      const w = largIface(l.ia), sMin = raggio(l.a) + est(w, 18) + 3;
      et.push(Object.assign({}, base, {tipo: 'if', it: l.ia, nodo: l.a, w, s: Math.max(sMin, Math.min(52, len * 0.28)), sMin, sMax: Math.max(sMin, len / 2 - 8)}));
    }
    if (l.ib) {
      const w = largIface(l.ib), sMax = len - raggio(l.b) - est(w, 18) - 3;
      et.push(Object.assign({}, base, {tipo: 'if', it: l.ib, nodo: l.b, w, s: Math.min(sMax, len - Math.min(52, len * 0.28)), sMin: Math.min(sMax, len / 2 + 8), sMax}));
    }
  }
  const centro = e => { e.x = e.ax + e.ux * e.s - e.uy * e.o; e.y = e.ay + e.uy * e.s + e.ux * e.o; };
  // sposta e di (Dx, Dy): prima lungo il link, poi (se è al limite o il link è di traverso) di lato
  const sposta = (e, Dx, Dy) => {
    const d = Math.hypot(Dx, Dy) || 1, lungo = (e.ux * Dx + e.uy * Dy) / d, lato = (-e.uy * Dx + e.ux * Dy) / d;
    if (Math.abs(lungo) > 0.25) {
      const s = Math.max(e.sMin, Math.min(e.sMax, e.s + Math.max(-14, Math.min(14, d / lungo))));
      const fatto = Math.abs(s - e.s) > 0.01; e.s = s;
      if (fatto) return;
    }
    if (Math.abs(lato) > 0.1) e.o = Math.max(-16, Math.min(16, e.o + Math.max(-8, Math.min(8, d / lato))));
  };
  const urto = (a, b, pad) => {
    const ox = (a.w + b.w) / 2 + pad - Math.abs(a.x - b.x), oy = (a.h + b.h) / 2 + pad - Math.abs(a.y - b.y);
    if (ox <= 0 || oy <= 0) return null;
    return ox < oy ? [(a.x >= b.x ? 1 : -1) * ox, 0] : [0, (a.y >= b.y ? 1 : -1) * oy];
  };
  for (let it = 0; it < 120; it++) {
    et.forEach(centro);
    let urti = 0;
    for (let i = 0; i < et.length; i++) {
      for (let j = i + 1; j < et.length; j++) {
        const D = urto(et[i], et[j], 3); if (!D) continue;
        urti++; sposta(et[i], D[0] / 2, D[1] / 2); sposta(et[j], -D[0] / 2, -D[1] / 2); centro(et[i]); centro(et[j]);
      }
      for (const o of ost) { const D = urto(et[i], o, 3); if (D) { urti++; sposta(et[i], D[0], D[1]); centro(et[i]); } }
    }
    if (!urti) break;
  }
  et.forEach(centro);
  return {et, nomi};
}
function svgContenuto(G, pos) {
  let h = STILE_SVG, etichetteAS = '';
  const ostAS = [];      // scritte degli AS: ostacoli per le etichette
  const gruppi = [...new Set(G.nodes.map(n => n.gruppo).filter(g => g && g !== '_'))];
  for (const g of gruppi) {
    const pts = inviluppo(G.nodes.filter(n => n.gruppo === g).map(n => pos[n.id]));
    const c = S.colori[g] || '#64748b', igp = igpGruppo(G, g);
    const d = 'M' + pts.map(p => p.x.toFixed(1) + ',' + p.y.toFixed(1)).join(' L') + ' Z';
    h += `<path d="${d}" fill="${c}" stroke="${c}" stroke-width="110" stroke-linejoin="round" stroke-linecap="round" opacity="0.10"/>`;
    const top = pts.reduce((a, b) => b.y < a.y ? b : a);
    ostAS.push({x: top.x, y: top.y - 69, w: largh('AS' + g, 16) + (igp ? largh('· ' + igp, 12) + 6 : 0) + 6, h: 22});
    etichetteAS += `<text class="ga" x="${top.x}" y="${top.y - 64}" text-anchor="middle" fill="${c}">AS${esc(g)}${igp ? `<tspan class="gp" dx="6">· ${esc(igp)}</tspan>` : ''}</text>`;
  }
  for (const l of G.links) { const a = pos[l.a], b = pos[l.b];
    const cls = S.spenti && S.spenti.has(l.lan) ? ' off' : evidLink(l) ? ' ev' : (S.evid && S.evid.manca && S.evid.manca.has(l.lan)) ? ' manca' : '';
    h += `<line class="lk${cls}" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>`; }
  const {et, nomi} = posizionaEtichette(G, pos, $('#cIface').checked, ostAS);
  const ord = (S.evid && S.evid.ordine) || {};
  for (const n of G.nodes) { const p = pos[n.id];
    h += `<g class="nodo" data-id="${esc(n.id)}" transform="translate(${p.x},${p.y})">`;
    if (n.tipo === 'lan') {
      const w = Math.max(34, 9 * n.nome.length + 16);
      h += `<rect x="${-w / 2}" y="-12" width="${w}" height="24" rx="12" fill="#f8fafc" stroke="#64748b" stroke-width="1.5"/><text class="t" y="4" text-anchor="middle">${esc(n.nome)}</text>`;
      if (n.subnet) h += `<text class="ts" y="27" text-anchor="middle">${esc(n.subnet)}</text>`;
    } else {
      const c = n.tipo === 'router' ? (S.colori[n.gruppo] || '#64748b') : {host: '#475569', www: '#0d9488', dns: '#7c3aed'}[n.tipo];
      if (S.evid && S.evid.dev.has(n.nome)) h += n.tipo === 'router' ? '<circle class="ring" r="27"/>' : '<rect class="ring" x="-24" y="-20" width="48" height="40" rx="8"/>';
      if (n.nome === S.sel) h += n.tipo === 'router' ? '<circle class="sel" r="32"/>' : '<rect class="sel" x="-29" y="-25" width="58" height="50" rx="10"/>';
      if (n.tipo === 'router') {
        h += `<circle r="20" fill="${c}" stroke="#fff" stroke-width="2"/><path d="M-10,-4 H9 M5,-8 L9,-4 L5,0 M10,4 H-9 M-5,0 L-9,4 L-5,8" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`;
      } else {
        const lab = {host: '', www: 'www', dns: 'DNS'}[n.tipo];
        h += `<rect x="-17" y="-13" width="34" height="26" rx="4" fill="${c}" stroke="#fff" stroke-width="2"/>`;
        h += lab ? `<text y="4" text-anchor="middle" style="font:700 10px system-ui,sans-serif;fill:#fff">${lab}</text>` : '<rect x="-10" y="-7" width="20" height="12" rx="1.5" fill="none" stroke="#fff" stroke-width="1.6"/>';
      }
      const t = nomi[n.id];
      h += `<text class="t" x="${(t.x - p.x).toFixed(1)}" y="${(t.y - p.y).toFixed(1)}" text-anchor="${t.anc}">${esc(n.nome)}</text>`;
      if (ord[n.nome] != null) h += `<circle cx="20" cy="-20" r="10" fill="#f59e0b"/><text class="ord" x="20" y="-16" text-anchor="middle">${esc(ord[n.nome])}</text>`;
    }
    h += '</g>';
  }
  // etichette sopra a tutto: link punto-punto (nome e subnet) e interfacce
  const col = id => { const n = G.nodes.find(x => x.id === id); return (n && S.colori[n.gruppo]) || '#475569'; };
  for (const e of et) {
    if (e.tipo === 'lan') h += `<rect x="${e.x - e.w / 2}" y="${e.y - 9}" width="${e.w}" height="18" rx="9" fill="#f8fafc" stroke="#cbd5e1"/>`
      + `<text class="lt" x="${e.x}" y="${e.y + 4}" text-anchor="middle"><tspan class="lb">${esc(e.l.lan)}</tspan> ${esc(e.l.subnet || '')}</text>`;
    else h += etichettaIface(e.it, e.x, e.y, col(e.nodo));
  }
  return h + etichetteAS;
}
function viewBox() {
  const ps = Object.values(S.pos); if (!ps.length) return '0 0 100 100';
  const xs = ps.map(p => p.x), ys = ps.map(p => p.y), m = 100;
  const x0 = Math.min(...xs) - m, y0 = Math.min(...ys) - m - 20, x1 = Math.max(...xs) + m, y1 = Math.max(...ys) + m;
  return `${x0} ${y0} ${x1 - x0} ${y1 - y0}`;
}
function ridisegna() {
  if (!S.G) return;
  if (!S.vb) S.vb = viewBox();
  const svg = $('#svg'); svg.setAttribute('viewBox', S.vb); svg.innerHTML = svgContenuto(S.G, S.pos);
  $('#bTogli').hidden = !S.evid;
}
let trascina = null;
function puntoSvg(e) { const m = $('#svg').getScreenCTM().inverse(); const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(m); return {x: p.x, y: p.y}; }
// trascinando un nodo lo si sposta, trascinando lo sfondo si sposta la vista; rotellina = zoom
$('#svg').addEventListener('pointerdown', e => {
  const g = e.target.closest('[data-id]');
  trascina = g ? {id: g.dataset.id, x: e.clientX, y: e.clientY, mosso: false}
               : {sfondo: true, x: e.clientX, y: e.clientY, vb: S.vb.split(' ').map(Number), scala: 1 / $('#svg').getScreenCTM().a};
  $('#svg').setPointerCapture(e.pointerId);
});
$('#svg').addEventListener('pointermove', e => {
  if (!trascina) return;
  if (trascina.sfondo) {
    const [x, y, w, h] = trascina.vb, s = trascina.scala;
    S.vb = [x - (e.clientX - trascina.x) * s, y - (e.clientY - trascina.y) * s, w, h].join(' ');
    $('#svg').setAttribute('viewBox', S.vb); return;
  }
  if (Math.abs(e.clientX - trascina.x) + Math.abs(e.clientY - trascina.y) > 4) trascina.mosso = true;
  if (trascina.mosso) { S.pos[trascina.id] = puntoSvg(e); ridisegna(); }
});
$('#svg').addEventListener('pointerup', () => {
  if (!trascina) return;
  const t = trascina; trascina = null;
  if (t.sfondo) return;
  if (t.mosso) mem('pos:' + S.nome, S.pos);
  else if (t.id.startsWith('d:')) { S.sel = t.id.slice(2); ridisegna(); lato(); }
});
$('#svg').addEventListener('wheel', e => {
  e.preventDefault();
  const f = e.deltaY > 0 ? 1.15 : 1 / 1.15, p = puntoSvg(e), [x, y, w, h] = S.vb.split(' ').map(Number);
  S.vb = [p.x - (p.x - x) * f, p.y - (p.y - y) * f, w * f, h * f].join(' ');
  $('#svg').setAttribute('viewBox', S.vb);
}, {passive: false});
$('#bAdatta').onclick = () => { S.vb = null; ridisegna(); };
$('#bRiordina').onclick = () => {
  if (!S.varianti) { S.varianti = varianti(S.G); S.variante = -1; }
  S.variante = (S.variante + 1) % S.varianti.length;
  S.pos = JSON.parse(JSON.stringify(S.varianti[S.variante]));
  mem('pos:' + S.nome, null); S.vb = null; ridisegna();
};
$('#cIface').onchange = ridisegna;
$('#bTogli').onclick = () => { S.evid = null; ridisegna(); };
$('#bSvg').onclick = () => {
  const testo = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox()}" width="1400" style="background:#fff">${svgContenuto(S.G, S.pos)}</svg>`;
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([testo], {type: 'image/svg+xml'}));
  a.download = S.nome + '-topologia.svg'; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
};

// ---------- pannello del dispositivo ----------
const ETICHETTE = {bgp_summary: 'show ip bgp summary', bgp: 'show ip bgp', route: 'show ip route', ospf_nei: 'show ip ospf neighbor', ospf_if: 'show ip ospf interface', rip: 'show ip rip', running: 'show running-config', ip_route: 'ip route', ip_addr: 'ip -br addr'};
function dispositivo(nome) { return S.lab && S.lab.dispositivi.find(d => d.nome === nome); }
function lato() {
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
  el.innerHTML = `<div class="riga" style="margin:0"><h3>${esc(d.nome)}</h3><span class="badge">${esc(d.tipo)}</span>${d.asn ? `<span class="badge">AS${esc(d.asn)}</span>` : ''}<div class="sp"></div><a href="#" data-sel="">elenco</a></div>
    <table><tr><th>Interf.</th><th>IP</th><th>LAN</th></tr>${d.interfacce.map(i => `<tr><td>${esc(i.dev)}</td><td>${esc(i.ip || '-')}</td><td>${esc(i.lan)}</td></tr>`).join('')}
    ${d.loopback.map(ip => `<tr><td>lo</td><td>${esc(ip)}</td><td></td></tr>`).join('')}</table>
    ${d.gateway ? `<div class="small" style="margin-top:6px">Gateway: <code>${esc(d.gateway)}</code></div>` : ''}
    ${d.nameserver.length ? `<div class="small">Nameserver: <code>${esc(d.nameserver.join(', '))}</code></div>` : ''}
    ${d.demoni.length ? `<div class="small">Demoni FRR: ${esc(d.demoni.join(', '))}</div>` : ''}
    <div class="btns">${cmd.map(c => `<button class="small ghost" data-cmd="${c}">${esc(ETICHETTE[c])}</button>`).join('')}</div>
    <div class="riga"><input id="sIp" list="ipList" placeholder="IP" size="15"><button class="small" data-cmd="ping">ping</button><button class="small" data-cmd="traceroute">traceroute</button><button class="small ghost" id="sPerc">percorso sulla mappa</button></div>
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
  if (e.target.id === 'sPerc') { const ip = $('#sIp').value.trim(); if (!ip) { $('#sIp').focus(); return; } percorso(S.sel, ip, e.target); }
  if (e.target.id === 'sTerm') {
    try { const r = await azione({azione: 'terminale', dev: S.sel});
      $('#sTermMsg').innerHTML = `<div class="${r.ok ? 'okline' : 'warnline'}">${esc(r.messaggio)}</div><code>${esc(r.comando)}</code>`;
    } catch (err) { errore(err); }
  }
});

// ---------- riepilogo e controlli ----------
function listaAvvisi(titolo, av, okTesto) {
  return `<h3>${titolo}</h3>` + (av.length ? `<ul class="avvisi">${av.map(a => `<li class="warnline">${esc(a)}</li>`).join('')}</ul>` : `<div class="okline">✔ ${okTesto}</div>`);
}
// controllo configurazione FRR: nomi (dai file, sempre) + sintassi (vtysh --dryrun, lab acceso)
function righeFrr() {
  const righe = [];
  for (const d of S.lab.dispositivi) {
    for (const x of d.riferimenti_frr || []) righe.push(Object.assign({router: d.nome}, x));
    const s = S.sintassi && S.sintassi[d.nome];
    if (s && s.righe) for (const x of s.righe) righe.push(Object.assign({router: d.nome}, x));
    if (s && s.errore) righe.push({router: d.nome, riga: '', testo: '', gravita: 'avviso', messaggio: 'sintassi non controllata: ' + s.errore});
  }
  return righe.sort((a, b) => a.router.localeCompare(b.router) || (a.riga || 0) - (b.riga || 0));
}
function htmlControlloFrr() {
  const righe = righeFrr();
  let h = `<div class="card"><h2>Controllo configurazione FRR</h2>
    <div class="muted small">FRR non segnala gli errori di frr.conf: salta le righe che non capisce, e una route-map o prefix-list inesistente su un neighbor
      blocca tutte le rotte con la sessione comunque Established. I <b>nomi</b> (route-map, prefix-list, access-list) sono controllati dai file, sempre;
      la <b>sintassi</b> con <code>vtysh --dryrun</code> sul file attuale (serve il lab acceso, il router non viene modificato).</div>
    <div class="riga"><button id="bSintassi">Controlla la sintassi (lab acceso)</button>
      <span class="small ${S.sintassi ? 'okline' : 'muted'}">${S.sintassi ? 'sintassi controllata' : 'sintassi non ancora controllata'}</span></div>`;
  if (!righe.length) h += `<div class="okline">✔ Nessun problema${S.sintassi ? '' : ' nei nomi'}.</div>`;
  else h += `<table><tr><th>Router</th><th>Riga</th><th>Testo</th><th>Problema</th></tr>${righe.map(x =>
    `<tr class="${x.gravita === 'errore' ? 'sosp' : ''}"><td>${esc(x.router)}</td><td>${esc(x.riga)}</td><td><code>${esc(x.testo)}</code></td>
     <td class="small ${x.gravita === 'errore' ? 'koline' : 'warnline'}">${x.gravita === 'errore' ? '✘ ' : '⚠ '}${esc(x.messaggio)}</td></tr>`).join('')}</table>
    <div class="muted small">✘ = da correggere; ⚠ = da controllare (una lista definita e mai usata è spesso lo stesso nome scritto in due modi).</div>`;
  return h + '</div>';
}
$('#t-riep').addEventListener('click', async e => {
  if (e.target.id !== 'bSintassi') return;
  const r = await esegui({azione: 'sintassi_frr'}, 'Sintassi frr.conf ' + S.nome, e.target);
  if (r && r.risultato) { S.sintassi = r.risultato; riepilogo(); }
});
function riepilogo() {
  const L = S.lab, r = L.dispositivi.filter(d => d.riepilogo), altri = L.dispositivi.filter(d => !d.riepilogo);
  // gli avvisi sui nomi di frr.conf sono nella card "Controllo configurazione FRR"
  const config = L.avvisi_config.filter(a => !/\(frr\.conf riga \d+\)/.test(a));
  let h = `<div class="card"><h2>Controlli automatici</h2>${listaAvvisi('Topologia (LAN e subnet)', L.avvisi_topologia, 'LAN e subnet coerenti.')}
    <div style="height:8px"></div>${listaAvvisi('Dimenticanze tipiche', config, 'Nessuna dimenticanza trovata.')}
    <div class="muted small" style="margin-top:8px">Sono suggerimenti: confrontali sempre con il testo dell'esercizio.</div></div>`;
  h += htmlControlloFrr();
  h += '<div class="griglia">';
  for (const d of r) { const R = d.riepilogo;
    h += `<div class="card"><div class="riga" style="margin:0 0 6px"><h3 style="margin:0">${esc(d.nome)}</h3>${d.asn ? `<span class="badge">AS${esc(d.asn)}</span>` : ''}<span class="muted small">${esc(d.demoni.join(' '))}</span></div><table>`;
    for (const g of R.igp) h += `<tr><th>${g.protocollo}</th><td>${esc(g.voci.join(', ') || '-')}${g.redistribute.length ? `<div class="small muted">redistribute ${esc(g.redistribute.join(', '))}</div>` : ''}${g.auto_cost ? `<div class="small muted">auto-cost reference-bandwidth ${esc(g.auto_cost)}</div>` : ''}</td></tr>`;
    if (R.costi.length) h += `<tr><th>Costo OSPF</th><td>${esc(R.costi.join(', '))}</td></tr>`;
    if (d.demoni.includes('bgpd')) {
      h += `<tr><th>Network BGP</th><td>${esc(R.bgp_networks.join(', ') || '-')}</td></tr>`;
      if (R.redistribute_bgp.length) h += `<tr><th>Redistribute in BGP</th><td>${esc(R.redistribute_bgp.join(', '))}</td></tr>`;
    }
    h += '</table>';
    if (R.neighbor.length) {
      h += '<table style="margin-top:8px"><tr><th>Neighbor</th><th>Chi</th><th>Tipo</th><th>Policy</th></tr>';
      for (const n of R.neighbor) h += `<tr><td><code>${esc(n.ip)}</code></td><td>${esc(n.chi)}<div class="small muted">AS${esc(n.asn)}</div></td><td>${n.tipo}</td><td>${n.policy.length ? n.policy.map(p => `<div><b>${esc(p.direzione)}</b>: ${esc(p.testo)}</div>`).join('') : '<span class="muted">nessuna</span>'}</td></tr>`;
      h += '</table>';
    }
    h += '</div>';
  }
  h += '</div>';
  if (altri.length) {
    h += `<div class="card"><h2>Host e server</h2><table><tr><th>Nome</th><th>Tipo</th><th>IP</th><th>Gateway</th><th>Nameserver</th><th>Zone DNS</th></tr>`;
    for (const d of altri) h += `<tr><td>${esc(d.nome)}</td><td>${esc(d.tipo)}</td><td>${esc(d.interfacce.map(i => i.dev + ' ' + (i.ip || '-')).join(', '))}</td><td>${esc(d.gateway || '-')}</td><td>${esc(d.nameserver.join(', ') || '-')}</td><td>${esc(d.zone.map(z => z[0] + ' (' + z[1] + ')').join(', '))}</td></tr>`;
    h += '</table></div>';
  }
  h += `<div class="card"><h2>LAN</h2><table><tr><th>LAN</th><th>Subnet</th><th>Dispositivi</th></tr>${L.lan.map(l => `<tr><td>${esc(l.nome)}</td><td>${esc(l.subnet || '-')}</td><td>${esc(l.membri.join(', '))}</td></tr>`).join('')}</table></div>`;
  $('#t-riep').innerHTML = h;
}

// ---------- test ----------
$('#bPing').onclick = async e => {
  const r = await esegui({azione: 'raggiungibilita'}, 'Raggiungibilità ' + S.nome, e.target);
  if (r && r.risultato) mostraPing(r.risultato);
};
function mostraPing(r) {
  const devs = [...new Set(r.destinazioni.map(x => x.dev))], ko = [];
  let h = `<div class="scroll"><table class="mat" style="width:auto"><tr><th>da \\ verso</th>${devs.map(d => `<th class="v"><span>${esc(d)}</span></th>`).join('')}</tr>`;
  for (const s of r.sorgenti) { const e = r.esiti[s] || {};
    h += `<tr><th>${esc(s)}</th>`;
    if (e._errore) { h += `<td colspan="${devs.length}" class="ko" style="text-align:left">${esc(e._errore)}</td></tr>`; ko.push(s + ': ' + e._errore); continue; }
    for (const d of devs) {
      if (d === s) { h += '<td class="self">—</td>'; continue; }
      const ips = r.destinazioni.filter(x => x.dev === d).map(x => x.ip), no = ips.filter(ip => e[ip] !== true);
      no.forEach(ip => ko.push(`${s} → ${ip} (${d})`));
      const cls = no.length === 0 ? 'ok' : (no.length === ips.length ? 'ko' : 'mezzo');
      h += `<td class="${cls}" title="${esc(no.length ? 'non raggiunti: ' + no.join(', ') : 'tutti raggiunti')}">${ips.length - no.length}/${ips.length}</td>`;
    }
    h += '</tr>';
  }
  h += '</table></div>';
  h += ko.length ? `<div class="koline" style="margin-top:8px">${ko.length} ping falliti</div><details><summary>Elenco</summary><ul class="avvisi">${ko.map(x => `<li>${esc(x)}</li>`).join('')}</ul></details>
      <div class="muted small">Un KO può essere voluto: filtri e policy del testo, oppure reti interne non annunciate in BGP
      (il ping parte dall'IP dell'interfaccia di uscita: se quella rete non è annunciata, la risposta non torna).
      Controlla che corrisponda a quello che chiede l'esercizio.</div>`
    : '<div class="okline" style="margin-top:8px">✔ Tutti gli indirizzi raggiunti da tutti i dispositivi.</div>';
  $('#rPing').innerHTML = h;
}
$('#bSessioni').onclick = async e => {
  const r = await esegui({azione: 'sessioni'}, 'Sessioni BGP/OSPF ' + S.nome, e.target);
  if (r && r.risultato) mostraSessioni(r.risultato);
};
function stato(x) {
  if (x.escluso) return `<span class="badge" title="${esc(x.stato || '')}">${esc(x.escluso)}</span>`;
  return `<span class="badge ${x.ok ? 'ok' : 'ko'}">${esc(x.stato || 'errore')}</span>`;
}
function mostraSessioni(r) {
  let h = '<h3>BGP</h3>';
  h += r.bgp.length ? `<table><tr><th>Router</th><th>Neighbor</th><th>Dispositivo</th><th>AS</th><th>Stato</th><th>Prefissi ricevuti</th><th>Attiva da</th></tr>${r.bgp.map(x => x.errore ? `<tr><td>${esc(x.router)}</td><td colspan="6" class="koline">${esc(x.errore)}</td></tr>` :
    `<tr><td>${esc(x.router)}</td><td><code>${esc(x.neighbor)}</code></td><td>${esc(x.chi)}</td><td>${esc(x.as || '')}</td><td>${stato(x)}</td><td>${esc(x.prefissi == null ? '' : x.prefissi)}</td><td>${esc(x.uptime || '')}</td></tr>`).join('')}</table>` : '<div class="muted">Nessun router BGP.</div>';
  h += '<h3 style="margin-top:14px">OSPF</h3>';
  h += r.ospf.length ? `<table><tr><th>Router</th><th>Vicino</th><th>Dispositivo</th><th>Router-ID</th><th>Interfaccia</th><th>Stato</th></tr>${r.ospf.map(x =>
    `<tr><td>${esc(x.router)}</td><td><code>${esc(x.vicino)}</code></td><td>${esc(x.chi)}</td><td>${esc(x.router_id || '')}</td><td>${esc(x.interfaccia || '')}</td><td>${stato(x)}</td></tr>`).join('')}</table>
    <div class="muted small">"non trovato" = router OSPF dello stesso AS sulla stessa LAN che non è diventato vicino (interfaccia non coperta dalle network OSPF, area diversa, lab non ancora convergente).</div>` : '<div class="muted">Nessun router OSPF.</div>';
  const rid = r.ridistribuzione || [];
  if (rid.length) {
    h += '<h3 style="margin-top:14px">Ridistribuzione nell\'IGP (redistribute bgp / connected)</h3>';
    h += `<table><tr><th>Router</th><th>IGP</th><th>Riga nel frr.conf</th><th>Da ridistribuire</th><th>Entrate nell'IGP</th><th title="show zebra client: rotte ridistribuite che zebra ha passato a ripd/ospfd dall'avvio (tutte le righe redistribute insieme)">Passate da zebra</th><th>Stato</th><th></th></tr>${rid.map(x =>
      `<tr class="${x.ok ? '' : 'sosp'}"><td>${esc(x.router)}</td><td>${esc(x.igp)}</td><td><code>${esc(x.riga)}</code></td><td>${x.errore ? '' : esc(x.totale)}</td>
       <td title="${esc((x.mancanti || []).length ? 'mancanti: ' + x.mancanti.join(', ') : '')}">${x.errore ? `<span class="koline">${esc(x.errore)}</span>` : esc(x.iniettate)}</td>
       <td>${x.zebra == null ? '' : esc(x.zebra)}</td><td>${stato(x)}${x.causa ? `<div class="small muted">${esc(x.causa)}</div>` : ''}</td>
       <td>${x.ok ? '' : `<button class="small" data-riapplica="${esc(x.router)}" data-igp="${esc(x.igp)}">Riapplica</button>`}</td></tr>`).join('')}</table>
      <div class="muted small">Controlla che le rotte BGP e le reti connesse (quelle non già coperte dalle network dell'IGP) siano davvero entrate in RIP/OSPF.
      Con FRR 10.5.3 a volte la ridistribuzione non parte all'avvio anche se il file è giusto: zebra non riceve la richiesta del demone
      e "Passate da zebra" resta 0. "Riapplica" toglie e rimette tutte le righe redistribute del blocco a lab acceso (i file non cambiano).
      Se "Passate da zebra" è più di 0 ma la riga resta "non attiva", la causa è un'altra (es. una route-map che filtra tutto).</div>`;
  }
  S.sessioni = r;
  $('#rSessioni').innerHTML = h;
}
$('#rSessioni').addEventListener('click', async e => {
  const b = e.target.closest('[data-riapplica]'); if (!b) return;
  const res = await esegui({azione: 'riapplica', dev: b.dataset.riapplica, igp: b.dataset.igp}, 'Riapplica ridistribuzione ' + b.dataset.riapplica, b);
  if (res && Array.isArray(res.risultato) && S.sessioni) {
    const nuove = res.risultato;
    S.sessioni.ridistribuzione = S.sessioni.ridistribuzione.map(x => nuove.find(n => n.router === x.router && n.igp === x.igp && n.riga === x.riga) || x);
    mostraSessioni(S.sessioni);
  }
});
// ---------- ping ----------
function origini() {
  const d = (S.lab.dispositivi.find(x => x.nome === $('#pnSrc').value) || {interfacce: [], loopback: []});
  $('#pnOrig').innerHTML = '<option value="">automatica</option>' + d.interfacce.filter(i => i.ip).map(i => `<option value="${esc(i.ip.split('/')[0])}">${esc(i.dev + ' ' + i.ip.split('/')[0])}</option>`).join('')
    + d.loopback.map(ip => `<option value="${esc(ip.split('/')[0])}">${esc('lo ' + ip.split('/')[0])}</option>`).join('');
}
$('#pnSrc').onchange = origini;
$('#bPn').onclick = e => { const ip = $('#pnDst').value.trim(); if (!ip) { $('#pnDst').focus(); return; } pingUno($('#pnSrc').value, ip, $('#pnOrig').value, e.target); };
async function pingUno(src, ip, origine, bottone) {
  const r = await esegui({azione: 'ping', dev: src, ip, origine}, 'ping ' + src + ' → ' + ip + (origine ? ' (da ' + origine + ')' : ''), bottone);
  if (!r || !r.risultato) return;
  const p = r.risultato;
  const chi = p.dev_destinazione ? `${esc(p.dev_destinazione)}${p.lan_destinazione ? ' · LAN ' + esc(p.lan_destinazione) : ''}` : 'fuori dal lab';
  let h = `<div class="${p.ok ? 'okline' : 'koline'}"><b>${p.ok ? '✔ Risponde' : '✘ Nessuna risposta'}</b> — ${p.inviati ? p.ricevuti + '/' + p.inviati + ' pacchetti' : 'il ping non è partito'}${p.media ? ' · media ' + esc(p.media) + ' ms' : ''}</div>
    <div class="small" style="margin:6px 0">${esc(p.sorgente)} → <code>${esc(p.destinazione)}</code> (${chi})</div>
    <div class="small muted">Partito da: ${p.partenza ? `<code>${esc(p.partenza)}</code>${p.dev_uscita ? ' (' + esc(p.dev_uscita) + ')' : ''}${p.origine ? ' — scelta da te' : ' — automatica'}` : '—'}${p.rotta ? '' : ` · <b>nessuna rotta verso ${esc(p.destinazione)}</b>`}</div>`;
  if (p.suggerimento) h += `<div class="warnline small" style="margin-top:6px">${esc(p.suggerimento)}</div>`;
  $('#rPn').innerHTML = h;
}
$('#bPercorso').onclick = e => {
  const ip = $('#pDst').value.trim(); if (!ip) { $('#pDst').focus(); return; }
  percorso($('#pSrc').value, ip, e.target, {atteso: $('#pAtt').value, attesoR: $('#pAttR').value, ritorno: $('#pRit').checked,
    modo: document.querySelector('input[name=pModo]:checked').value});
};
// confronto con il percorso richiesto dal testo: nomi di LAN oppure di dispositivi
function confrontaPercorso(p, atteso, modo) {
  const tok = (atteso || '').split(/[\s,;>→]+/).filter(Boolean);
  if (!tok.length) return null;
  const lanN = {}, devN = {};
  S.lab.lan.forEach(l => lanN[l.nome.toLowerCase()] = l.nome);
  S.lab.dispositivi.forEach(d => devN[d.nome.toLowerCase()] = d.nome);
  const tipo = tok.every(t => lanN[t.toLowerCase()]) ? 'lan' : tok.every(t => devN[t.toLowerCase()]) ? 'dev' : null;
  if (!tipo) {
    const ignoti = tok.filter(t => !lanN[t.toLowerCase()] && !devN[t.toLowerCase()]);
    return {errore: (ignoti.length ? `Non riconosco ${ignoti.join(', ')}` : 'Hai mescolato LAN e dispositivi')
      + `: usa solo nomi di LAN (${S.lab.lan.map(l => l.nome).join(' ')}) oppure solo nomi di dispositivi.`};
  }
  const att = tok.map(t => (tipo === 'lan' ? lanN : devN)[t.toLowerCase()]);
  const fatto = tipo === 'lan' ? p.hop.map(x => x.lan).filter(Boolean) : [p.sorgente].concat(p.hop.map(x => x.dev).filter(Boolean));
  let punto = -1, ok;
  if (modo === 'esatta') {
    let i = 0; while (i < att.length && i < fatto.length && att[i] === fatto[i]) i++;
    ok = i === att.length && i === fatto.length; if (!ok) punto = i;
  } else {
    let j = 0; for (const x of fatto) if (j < att.length && x === att[j]) j++;
    ok = j === att.length; if (!ok) punto = j;
  }
  return {ok, tipo, modo, att, fatto, punto, mancanti: att.filter(t => !fatto.includes(t))};
}
function htmlConfronto(c) {
  if (!c) return '';
  if (c.errore) return `<div class="warnline small" style="margin:6px 0">${esc(c.errore)}</div>`;
  const seq = c.fatto.map((x, i) => {
    const giusto = c.modo === 'esatta' ? (c.punto < 0 || i < c.punto) : c.att.includes(x);
    return `<b class="${giusto ? 'okline' : (c.modo === 'esatta' && i === c.punto ? 'koline' : '')}">${esc(x)}</b>`;
  }).join(' ');
  let h = `<div class="small" style="margin:6px 0">${c.tipo === 'lan' ? 'Link attraversati' : 'Dispositivi attraversati'}: ${seq}</div>`;
  if (c.ok) return h + `<div class="okline"><b>✔ Come richiesto</b> — ${c.modo === 'esatta' ? 'sequenza esatta' : 'passa per'} ${esc(c.att.join(' '))}</div>`;
  let perche;
  if (c.modo === 'esatta') {
    perche = c.punto >= c.fatto.length ? `il percorso finisce prima: manca ${esc(c.att.slice(c.punto).join(' '))}`
      : c.punto >= c.att.length ? `il percorso continua oltre il richiesto (${esc(c.fatto.slice(c.punto).join(' '))})`
      : `al passo ${c.punto + 1} atteso <b>${esc(c.att[c.punto])}</b>, invece <b>${esc(c.fatto[c.punto])}</b>`;
  } else {
    perche = c.mancanti.length ? `non passa per <b>${esc(c.mancanti.join(' '))}</b>` : `ci passa ma non nell'ordine richiesto (${esc(c.att.join(' '))})`;
  }
  return h + `<div class="koline"><b>✘ Diverso dal richiesto</b> (${esc(c.att.join(' '))}): ${perche}</div>`;
}
// routing loop: un dispositivo che ricompare più avanti nel percorso (A → B → A ...)
function loopPercorso(p) {
  const devs = [p.sorgente].concat(p.hop.map(x => x.dev).filter(Boolean));
  for (let i = 0; i < devs.length; i++) {
    const j = devs.indexOf(devs[i], i + 1);
    if (j > i + 1) return devs.slice(i, j);
  }
  return null;
}
function htmlPercorso(p, titolo, c) {
  const nomi = [p.sorgente].concat(p.hop.map(x => x.dev || x.ip)), loop = loopPercorso(p);
  const spenti = S.spenti && S.spenti.size ? [...S.spenti] : [];
  let h = `<h3 style="margin-top:10px">${esc(titolo)}</h3><div class="${p.arrivato ? 'okline' : 'koline'}"><b>${p.arrivato ? '✔ Arrivato' : '✘ Non arrivato'}</b> a ${esc(p.destinazione)}${p.dev_destinazione ? ' (' + esc(p.dev_destinazione) + ')' : ''} — ${p.hop.length} hop</div>
    <div style="margin:6px 0"><b>${nomi.map(esc).join(' → ')}</b></div>`;
  if (loop) h += `<div class="koline small" style="margin:6px 0"><b>⟳ Routing loop tra ${esc(loop.join(' e '))}</b>: i pacchetti rimbalzano tra questi router (ognuno crede che la strada passi per l'altro).
    ${spenti.length ? 'Hai un link spento: la rete forse si sta ancora riassestando, attendi la convergenza e riprova.' : 'Controlla le loro rotte verso questa destinazione (Rotta verso una rete).'}</div>`;
  else if (!p.arrivato && spenti.length) h += `<div class="warnline small" style="margin:6px 0">C'è un link spento (${esc(spenti.join(', '))}): se l'hai appena spento attendi la convergenza e riprova; se resta così, non c'è un percorso di riserva.</div>`;
  if (c && !c.errore && !p.arrivato) h += `<div class="small muted">Il pacchetto non arriva: il confronto con l'atteso riguarda solo il tratto percorso.</div>`;
  h += htmlConfronto(c);
  h += `<details${c ? '' : ' open'}><summary class="small">Hop</summary><div class="hop muted small"><b>S</b><span>${esc(p.sorgente)}</span></div>`;
  h += p.hop.map(x => `<div class="hop small"><b>${x.n}</b><code>${esc(x.ip)}</code><span>${esc(x.dev || (x.ip === '*' ? 'nessuna risposta' : 'fuori dal lab'))}</span><span class="muted">${x.lan ? 'LAN ' + esc(x.lan) : ''}</span></div>`).join('');
  return h + '</details>';
}
// evidenzia un percorso sulla topologia (link attesi e non attraversati in rosso)
function evidenzia(p, c) {
  const ordine = {}; ordine[p.sorgente] = 'S';
  p.hop.forEach(x => { if (x.dev && ordine[x.dev] == null) ordine[x.dev] = x.n; });
  S.evid = {dev: new Set([p.sorgente].concat(p.hop.filter(x => x.dev).map(x => x.dev))), lan: new Set(p.hop.filter(x => x.lan).map(x => x.lan)), ordine,
    manca: new Set(c && c.tipo === 'lan' ? c.mancanti : [])};
  ridisegna();
}
async function percorso(src, ip, bottone, opz) {
  opz = opz || {};
  const r = await esegui({azione: 'percorso', dev: src, ip: ip}, 'Percorso ' + src + ' → ' + ip, bottone);
  if (!r || !r.risultato) return;
  const p = r.risultato, c = confrontaPercorso(p, opz.atteso, opz.modo);
  let q = null, cq = null, nota = '';
  if (opz.ritorno) {
    // ritorno: dalla destinazione verso l'IP della sorgente sulla LAN da cui è partito il traceroute
    const d = dispositivo(src), lan0 = p.hop[0] && p.hop[0].lan;
    const it = d && (d.interfacce.find(i => i.lan === lan0 && i.ip) || d.interfacce.find(i => i.ip));
    if (!p.dev_destinazione) nota = "Ritorno non possibile: la destinazione non è un dispositivo del lab.";
    else if (!it) nota = `Ritorno non possibile: ${src} non ha indirizzi.`;
    else {
      const ipr = it.ip.split('/')[0];
      const rr = await esegui({azione: 'percorso', dev: p.dev_destinazione, ip: ipr}, 'Percorso ' + p.dev_destinazione + ' → ' + ipr, bottone);
      if (rr && rr.risultato) { q = rr.risultato; cq = confrontaPercorso(q, opz.attesoR, opz.modo); }
    }
  }
  evidenzia(p, c);
  let h = htmlPercorso(p, 'Andata: ' + src + ' → ' + ip, c);
  if (q) h += htmlPercorso(q, 'Ritorno: ' + q.sorgente + ' → ' + q.destinazione, cq);
  if (nota) h += `<div class="warnline small" style="margin-top:6px">${esc(nota)}</div>`;
  h += `<div class="riga"><button class="small ghost" id="vediMappa">Andata sulla topologia</button>${q ? '<button class="small ghost" id="vediRit">Ritorno sulla topologia</button>' : ''}</div>`;
  $('#rPercorso').innerHTML = h;
  $('#vediMappa').onclick = () => { evidenzia(p, c); scheda('topo'); };
  if (q) $('#vediRit').onclick = () => { evidenzia(q, cq); scheda('topo'); };
}

// ---------- guasto di un link ----------
function lanGuasto() {
  const sel = $('#gLan').value;
  $('#gLan').innerHTML = S.lab.lan.map(l => {
    const m = S.lab.dispositivi.flatMap(d => d.interfacce.filter(i => i.lan === l.nome).map(i => d.nome + ' ' + i.dev));
    return `<option value="${esc(l.nome)}">${esc(l.nome)}${S.spenti && S.spenti.has(l.nome) ? ' (spento)' : ''} — ${esc(m.join(' ↔ '))}</option>`;
  }).join('');
  if (sel) $('#gLan').value = sel;
}
async function link(lan, acceso, bottone) {
  const r = await esegui({azione: 'link', lan, acceso}, (acceso ? 'Riaccendi' : 'Spegni') + ' link ' + lan, bottone);
  await controllaSpenti();
  // i protocolli devono riassestarsi prima di tracciare i percorsi
  if (r && r.rc === 0) await attendiConvergenza($('#bConv'));
}
$('#gGiu').onclick = e => link($('#gLan').value, false, e.target);
$('#gSu').onclick = e => link($('#gLan').value, true, e.target);
async function controllaSpenti() {
  if (!S.nome) return;
  let lan = [];
  if ((S.stato[S.nome] || []).length) { try { lan = (await api('/api/spenti?lab=' + encodeURIComponent(S.nome))).lan; } catch (e) { return; } }
  const prima = [...(S.spenti || [])].join(' ');
  S.spenti = new Set(lan);
  const n = $('#linkNota');
  n.hidden = !lan.length;
  if (lan.length) n.innerHTML = `<b>⚠ Link spento${lan.length > 1 ? 'i' : ''}: ${lan.map(esc).join(', ')}</b> — guasto simulato dalla GUI (tratteggio rosso sulla topologia): ping e percorsi ne risentono.
    ${lan.map(l => `<button class="small" data-riaccendi="${esc(l)}">Riaccendi ${esc(l)}</button>`).join(' ')}`;
  $('#rGuasto').innerHTML = lan.length ? `<div class="warnline small">Spenti ora: ${lan.map(esc).join(', ')}</div>` : '';
  if (prima !== lan.join(' ')) { lanGuasto(); ridisegna(); }
}
$('#linkNota').addEventListener('click', e => {
  const b = e.target.closest('[data-riaccendi]'); if (b) link(b.dataset.riaccendi, true, b);
});

// ---------- interfacce ----------
function interfacce() {
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

// ---------- convergenza ----------
async function attendiConvergenza(bottone) {
  const r = await esegui({azione: 'convergenza'}, 'Attendi convergenza ' + S.nome, bottone);
  if (r && r.risultato) mostraSessioni(r.risultato);
  return r;
}
$('#bConv').onclick = e => attendiConvergenza(e.target);

// ---------- rotta verso una rete ----------
$('#bRotta').onclick = async e => {
  const rete = $('#rRete').value.trim(); if (!rete) { $('#rRete').focus(); return; }
  const r = await esegui({azione: 'rotta', dev: $('#rDev').value, rete}, 'Rotta ' + $('#rDev').value + ' → ' + rete, e.target);
  if (r && r.risultato) mostraRotta(r.risultato);
};
function mostraRotta(r) {
  const I = r.instradamento;
  let h = '';
  if (!I) h += `<div class="koline"><b>✘ ${esc(r.dev)} non ha nessuna rotta verso ${esc(r.rete)}.</b> La rete non è annunciata, è filtrata o il lab non è ancora convergente.</div>`;
  else {
    const hop = I.hop.map(x => x.connessa || !x.ip ? `direttamente su ${esc(x.dev || '')}${x.lan ? ' (LAN ' + esc(x.lan) + ')' : ''}`
      : `via <code>${esc(x.ip)}</code> = <b>${esc(x.chi || '?')}</b>${x.lan ? ' sulla LAN ' + esc(x.lan) : ''}`).join('<br>');
    h += `<div class="okline"><b>✔ ${esc(r.dev)} → ${esc(I.prefisso)}</b> imparata da <b>${esc(I.protocollo)}</b></div><div style="margin:4px 0 10px">${hop}</div>`;
  }
  if (r.bgp.length) {
    h += `<h3>Percorsi BGP per ${esc(r.prefisso_bgp || r.rete)} (${r.bgp.length})</h3><table><tr><th></th><th>Da</th><th>Tipo</th><th>AS-path</th><th>Local-pref</th><th>MED</th><th>Origine</th><th>Perché</th></tr>`;
    for (const p of r.bgp) h += `<tr class="${p.best ? 'best' : ''}"><td>${p.best ? '★ best' : (p.valido ? '' : '<span class="koline">non valido</span>')}</td>
      <td><b>${esc(p.chi)}</b> <span class="muted">${esc(p.da || '')}</span></td><td>${esc(p.tipo)}</td><td><code>${esc(p.aspath || '(locale)')}</code></td>
      <td>${p.locpref == null ? '<span class="muted">100</span>' : '<b>' + esc(p.locpref) + '</b>'}</td><td>${p.med == null ? '<span class="muted">-</span>' : esc(p.med)}</td>
      <td>${esc(p.origine || '')}</td><td class="small muted">${esc(p.best ? p.motivo : '')}</td></tr>`;
    h += '</table><div class="muted small">Local-pref più alta vince; a parità, AS-path più corto; poi MED più basso (tra annunci dello stesso AS vicino). Se manca un percorso che ti aspetti, controlla cosa annuncia o filtra il vicino (pulsanti sotto).</div>';
  } else if (I) h += '<div class="muted small">Nessun percorso BGP per questa rete su questo router (rotta interna, connessa o imparata via IGP).</div>';
  if (r.neighbor.length) h += `<div class="riga small">Annunci per vicino: ${r.neighbor.map(ip => `<button class="small ghost" data-nb="${esc(ip)}" data-c="bgp_ricevute">accettati da ${esc(ip)}</button><button class="small ghost" data-nb="${esc(ip)}" data-c="bgp_annunciate">inviati a ${esc(ip)}</button>`).join(' ')}</div>`;
  $('#rRotta').innerHTML = h;
  $('#rRotta').dataset.dev = r.dev;
}
$('#rRotta').addEventListener('click', e => {
  const b = e.target.closest('[data-nb]'); if (!b) return;
  const dev = $('#rRotta').dataset.dev;
  esegui({azione: 'comando', dev, comando: b.dataset.c, ip: b.dataset.nb}, `${dev}: ${b.textContent}`, b);
});

// ---------- tabelle di routing ----------
$('#bTabelle').onclick = async e => {
  const r = await esegui({azione: 'tabelle'}, 'Tabelle di routing ' + S.nome, e.target);
  if (r && r.risultato) mostraTabelle(r.risultato);
};
function mostraTabelle(r) {
  const SIG = {connected: 'C', bgp: 'B', ospf: 'O', rip: 'R', static: 'S', kernel: 'K'};
  let h = `<div class="scroll"><table class="mat" style="width:auto"><tr><th>router \\ rete</th>${r.reti.map(x => `<th class="v"><span>${esc(x)}</span></th>`).join('')}</tr>`;
  const mancanti = [];
  for (const ro of r.router) {
    h += `<tr><th>${esc(ro)}</th>`;
    if (r.errori[ro]) { h += `<td colspan="${r.reti.length}" class="ko" style="text-align:left">${esc(r.errori[ro])}</td></tr>`; continue; }
    for (const rete of r.reti) {
      const c = r.celle[ro][rete];
      if (c.tipo === 'mancante') { mancanti.push(`${ro}: ${rete}`); h += '<td class="ko" title="nessuna rotta">✘</td>'; continue; }
      if (c.tipo === 'propria') { h += '<td class="self" title="annunciata da questo router (network BGP)">★</td>'; continue; }
      if (c.tipo === 'specifiche') { h += `<td class="mezzo" title="${esc('nessuna rotta per l\'aggregato, ma ci sono le sue sottoreti: ' + c.da)}">~</td>`; continue; }
      const via = c.connessa ? `connessa (${c.dev})` : `via ${c.chi || c.via}`;
      const titolo = `${c.tipo === 'coperta' ? 'coperta da ' + c.da + ', ' : ''}${c.protocollo} ${via}`;
      h += `<td class="${c.tipo === 'esatta' ? 'ok' : 'mezzo'}" title="${esc(titolo)}">${SIG[c.protocollo] || '?'}</td>`;
    }
    h += '</tr>';
  }
  h += `</table></div><div class="small muted" style="margin-top:6px">C connessa · B BGP · O OSPF · R RIP · S statica · <span class="warnline">giallo</span> = coperta da una rotta più ampia · ~ = solo le sottoreti dell'aggregato · ★ = annunciata dal router stesso · passa il mouse su una cella per il next-hop.</div>`;
  h += mancanti.length ? `<div class="koline" style="margin-top:8px">${mancanti.length} reti mancanti</div><details><summary>Elenco</summary><ul class="avvisi">${mancanti.map(x => `<li>${esc(x)}</li>`).join('')}</ul></details>
      <div class="muted small">Può essere voluto (filtri, reti interne "non visibili dall'esterno"); altrimenti manca una network BGP, una ridistribuzione o una sessione.</div>`
    : '<div class="okline" style="margin-top:8px">✔ Ogni router ha una rotta verso tutte le reti del lab.</div>';
  $('#rTabelle').innerHTML = h;
}

// ---------- file modificati dopo l'avvio ----------
let controlloInCorso = false;
async function controllaModificati() {
  if (!S.nome || controlloInCorso) return;
  if (!(S.stato[S.nome] || []).length) { $('#modNota').hidden = true; return; }
  controlloInCorso = true;
  try {
    const m = await api('/api/modificati?lab=' + encodeURIComponent(S.nome));
    const n = $('#modNota');
    n.hidden = !(m.avviato && m.file.length);
    if (!n.hidden) n.innerHTML = `<b>Hai modificato ${m.file.length} file dopo l'avvio del lab</b> (avviato alle ${esc(m.avvio)}): ${m.file.slice(0, 6).map(f => '<code>' + esc(f) + '</code>').join(', ')}${m.file.length > 6 ? '…' : ''}.
      Le modifiche non sono attive finché non riavvii il lab. <button class="small" id="bRiavvia">Riavvia ora (lclean + lstart)</button>`;
  } catch (e) { /* stato non disponibile: nessun avviso */ }
  finally { controlloInCorso = false; }
}
$('#modNota').addEventListener('click', async e => {
  if (e.target.id !== 'bRiavvia') return;
  e.target.disabled = true;
  try {
    const j = await azione({azione: 'lstart', riavvia: true});
    const r = await segui(j.lavoro, 'riavvio ' + S.nome);
    await apriLab(S.nome, true); aggiornaStato();
    if (r && r.rc === 0) await attendiConvergenza($('#bConv'));
  } catch (err) { errore(err); }
});

// ---------- avviso sul nome dell'archivio ----------
function avvisoArchivio() {
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

// ---------- registro ----------
async function registro() {
  try {
    const r = await api('/api/registro');
    $('#rRegistro').innerHTML = r.length ? `<table><tr><th>Ora</th><th>Operazione</th><th>Comando</th><th>Esito</th></tr>${r.slice().reverse().map(x =>
      `<tr><td>${esc(x.ora)}</td><td>${esc(x.operazione)}</td><td><code>${esc(x.comando)}</code></td><td class="${x.esito.startsWith('OK') ? 'okline' : (x.esito === 'in corso' ? 'warnline' : 'koline')}">${esc(x.esito)}</td></tr>`).join('')}</table>` : '<div class="muted">Nessuna operazione.</div>';
  } catch (e) { errore(e); }
}

// ---------- schede e pulsanti generali ----------
function scheda(t) {
  if (!SCHEDE.includes(t)) return;
  S.tab = t;
  history.replaceState(null, '', '#lab=' + encodeURIComponent(S.nome) + '&tab=' + t);
  document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === t));
  SCHEDE.forEach(x => $('#t-' + x).hidden = x !== t);
  if (t === 'reg') registro();
  if (t === 'topo') ridisegna();
}
$('#tabs').onclick = e => { const b = e.target.closest('button'); if (b) scheda(b.dataset.tab); };
$('#labs').onclick = e => { const li = e.target.closest('[data-lab]'); if (li) apriLab(li.dataset.lab); };
$('#bAggiorna').onclick = caricaLabs;
$('#bRileggi').onclick = () => apriLab(S.nome, true);
$('#bPulisci').onclick = () => { $('#outTesto').textContent = ''; $('#outStato').textContent = ''; $('#outTitolo').textContent = 'Output'; };
$('#bStart').onclick = async e => {
  const b = e.target; b.disabled = true;
  try {
    let j = await azione({azione: 'lstart'});
    if (j.gia_acceso) {
      if (!confirm(`Il lab ${S.nome} è già acceso (${j.gia_acceso} dispositivi). Riavviarlo da capo (lclean + lstart)?`)) return;
      j = await azione({azione: 'lstart', riavvia: true});
    }
    const r = await segui(j.lavoro, 'lstart ' + S.nome);
    aggiornaStato();
    // dopo l'avvio si aspetta da soli che BGP/OSPF convergano (fino a 5 minuti)
    if (r && r.rc === 0) await attendiConvergenza($('#bConv'));
  } catch (err) { errore(err); }
  finally { b.disabled = false; aggiornaStato(); }
};
$('#bClean').onclick = async e => {
  if (!confirm('Fermare e cancellare i container del lab ' + S.nome + '?')) return;
  await esegui({azione: 'lclean'}, 'lclean ' + S.nome, e.target); aggiornaStato();
};
$('#bEsci').onclick = async () => {
  if (!confirm('Chiudere la GUI? I lab avviati restano accesi.')) return;
  try { await fetch('/api/esci', {method: 'POST', headers: {'X-Lab-Gen': '1', 'Content-Type': 'application/json'}, body: '{}'}); } catch (e) {}
  document.body.innerHTML = '<div class="vuoto">GUI chiusa. Puoi chiudere questa scheda.</div>';
};

(async function inizio() {
  try {
    const i = await api('/api/info');
    $('#base').textContent = 'Cartella: ' + i.base;
    const info = () => $('#info').textContent = i.kathara ? 'Kathará: ' + (i.versione || i.kathara) : '⚠ kathara non trovato nel PATH: comandi e test non disponibili';
    info();
    if (i.kathara && !i.versione) setTimeout(async () => { try { Object.assign(i, await api('/api/info')); info(); } catch (e) {} }, 3000);
  } catch (e) { errore(e); }
  await caricaLabs();
  // indirizzo diretto: http://127.0.0.1:8765/#lab=<nome>&tab=<topo|riep|test|arch|reg>
  const h = new URLSearchParams(location.hash.slice(1));
  if (h.get('lab') && S.labs.includes(h.get('lab'))) { await apriLab(h.get('lab')); if (h.get('tab')) scheda(h.get('tab')); }
  setInterval(aggiornaStato, 10000);
})();
</script>
</body>
</html>
"""
