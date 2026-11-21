"""Motore JavaScript interattivo della GUI: clic destro contestuale, wizard di creazione,
import XML/JSON, tutte le operazioni CLI con anteprima diff/validazione, editor righe FRR,
backup/ripristino e diagnostica visuale. Compatibile con Firefox (Debian) e MS Edge (Win/Fedora).
"""

UI_EDIT_JS = r"""
async function apiPost(path, dati) {
  const r = await fetch(path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-Lab-Gen': '1'},
    body: JSON.stringify(dati || {})
  });
  const j = await r.json();
  if (!r.ok) throw new Error(j.errore || ('Errore HTTP ' + r.status));
  return j;
}

function toast(msg, tipo) {
  const wrap = $('#toastWrap');
  if (!wrap) return;
  const el = document.createElement('div');
  el.className = 'toast' + (tipo ? ' ' + tipo : '');
  el.textContent = msg;
  wrap.appendChild(el);
  setTimeout(() => { el.remove(); }, 4200);
}

async function copiaTesto(testo) {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(testo);
      toast('Copiato negli appunti');
      return true;
    }
  } catch (e) {}
  const ta = document.createElement('textarea');
  ta.value = testo;
  ta.style.position = 'fixed';
  ta.style.left = '-9999px';
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try { ok = document.execCommand('copy'); } catch (e) {}
  ta.remove();
  toast(ok ? 'Copiato negli appunti' : 'Seleziona e copia manualmente', ok ? '' : 'warn');
  return ok;
}

let _modalDragCleanup = null;
function chiudiModal() {
  if (_modalDragCleanup) { _modalDragCleanup(); _modalDragCleanup = null; }
  const bg = $('#modalBg'), box = $('#modalBox');
  if (box) { box.style.transform = ''; box.innerHTML = ''; }
  if (bg) { bg.hidden = true; }
}
function abilitaDragModal(box) {
  if (_modalDragCleanup) { _modalDragCleanup(); _modalDragCleanup = null; }
  const head = box.querySelector('.modal-h');
  if (!head) return;
  let dx = 0, dy = 0, sx = 0, sy = 0, bx = 0, by = 0, active = false;
  box.style.transform = '';
  const onDown = e => {
    if (e.button !== 0 || e.target.closest('button,input,select,a')) return;
    active = true;
    sx = e.clientX; sy = e.clientY;
    bx = dx; by = dy;
    head.classList.add('dragging');
    e.preventDefault();
  };
  const onMove = e => {
    if (!active) return;
    let nx = bx + (e.clientX - sx);
    let ny = by + (e.clientY - sy);
    // Mantieni sempre la barra del titolo raggiungibile nella finestra
    const rect = box.getBoundingClientRect();
    const curDx = dx, curDy = dy;
    const baseLeft = rect.left - curDx, baseTop = rect.top - curDy;
    const minX = 60 - rect.width - baseLeft;
    const maxX = window.innerWidth - 60 - baseLeft;
    const minY = 6 - baseTop;
    const maxY = window.innerHeight - 48 - baseTop;
    dx = Math.max(minX, Math.min(maxX, nx));
    dy = Math.max(minY, Math.min(maxY, ny));
    box.style.transform = `translate(${dx}px, ${dy}px)`;
  };
  const onUp = () => {
    if (!active) return;
    active = false;
    head.classList.remove('dragging');
  };
  head.addEventListener('mousedown', onDown);
  window.addEventListener('mousemove', onMove);
  window.addEventListener('mouseup', onUp);
  _modalDragCleanup = () => {
    head.removeEventListener('mousedown', onDown);
    window.removeEventListener('mousemove', onMove);
    window.removeEventListener('mouseup', onUp);
  };
}
function apriModal(titolo, bodyHtml, footerHtml, opts) {
  opts = opts || {};
  const bg = $('#modalBg'), box = $('#modalBox');
  box.className = 'modal' + (opts.wide ? ' wide' : '');
  box.style.transform = '';
  box.innerHTML = `<div class="modal-h" title="Trascina per spostare la finestra"><h2>${esc(titolo)}</h2><span class="modal-drag-hint">⠿ sposta</span><button class="modal-x" id="mClose" title="Chiudi (Esc)">&times;</button></div>
    <div class="modal-b" id="mBody"><div id="mErr" class="ferr" hidden></div>${bodyHtml}</div>
    <div class="modal-f" id="mFoot">${footerHtml || '<button class="ghost" id="mCancel">Chiudi</button>'}</div>`;
  bg.hidden = false;
  abilitaDragModal(box);
  $('#mClose').onclick = chiudiModal;
  const c = $('#mCancel'); if (c) c.onclick = chiudiModal;
  if (opts.onMount) opts.onMount(box);
  const first = box.querySelector('input:not([type=hidden]),select,textarea');
  if (first && !opts.noFocus) setTimeout(() => first.focus(), 20);
}
function modalErrore(msg) {
  const el = $('#mErr');
  if (!el) { toast(msg, 'err'); return; }
  el.textContent = String(msg || '');
  el.hidden = !msg;
  if (msg) el.scrollIntoView({block: 'nearest'});
}
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    if (!$('#ctxMenu').hidden) chiudiCtx();
    else if (!$('#modalBg').hidden) chiudiModal();
  }
});
$('#modalBg').addEventListener('mousedown', e => {
  if (e.target.id === 'modalBg') chiudiModal();
});

async function eseguiModifica(op, params, opts) {
  opts = opts || {};
  modalErrore('');
  let prev;
  try {
    prev = await apiPost('/api/edit/preview', {lab: S.nome, op, params});
  } catch (e) {
    if (!$('#modalBg').hidden) modalErrore(e.message);
    else toast(e.message, 'err');
    return;
  }
  if (!prev.ha_modifiche) {
    toast('Nessuna modifica da applicare.', 'warn');
    if (opts.closeIfNoChange) chiudiModal();
    return;
  }
  mostraPreviewDiff(op, params, prev, opts);
}

function mostraPreviewDiff(op, params, prev, opts) {
  let deltaHtml = '<div class="delta-box">';
  if (prev.avvisi_risolti && prev.avvisi_risolti.length) {
    deltaHtml += `<div class="delta-ok"><b>✔ Risolti (${prev.avvisi_risolti.length}):</b><ul class="avvisi">${prev.avvisi_risolti.map(a => `<li>${esc(a)}</li>`).join('')}</ul></div>`;
  }
  if (prev.avvisi_nuovi && prev.avvisi_nuovi.length) {
    deltaHtml += `<div class="delta-ko"><b>⚠ Nuovi avvisi introdotti (${prev.avvisi_nuovi.length}):</b><ul class="avvisi">${prev.avvisi_nuovi.map(a => `<li>${esc(a)}</li>`).join('')}</ul></div>`;
  }
  if (!(prev.avvisi_risolti && prev.avvisi_risolti.length) && !(prev.avvisi_nuovi && prev.avvisi_nuovi.length)) {
    deltaHtml += `<div class="finfo">Controlli topologia/configurazione invariati (totale avvisi del lab: <b>${prev.avvisi_totale}</b>).</div>`;
  }
  deltaHtml += '</div>';

  const noteHtml = (prev.note && prev.note.length)
    ? `<div class="fwarn">${prev.note.map(n => `<div>⚠ ${esc(n)}</div>`).join('')}</div>` : '';

  const diffHtml = (prev.diff && prev.diff.length) ? prev.diff.map(f => {
    const badgeCls = f.stato === 'creato' ? 'ok' : (f.stato === 'eliminato' ? 'ko' : 'warn');
    const rows = f.righe.map(r => {
      if (r.tipo === 'sep') return `<tr class="d-sep"><td colspan="4">···</td></tr>`;
      const cls = r.tipo === 'add' ? 'd-add' : (r.tipo === 'del' ? 'd-del' : 'd-eq');
      const sg = r.tipo === 'add' ? '+' : (r.tipo === 'del' ? '−' : ' ');
      return `<tr class="${cls}"><td class="ln">${r.n1 || ''}</td><td class="ln">${r.n2 || ''}</td><td class="sg">${sg}</td><td>${esc(r.testo)}</td></tr>`;
    }).join('');
    return `<div class="diff-file"><div class="diff-fh"><code>${esc(f.file)}</code><span class="badge ${badgeCls}">${esc(f.stato)}</span></div>
      <table class="diff-tbl">${rows}</table></div>`;
  }).join('') : `<div class="finfo">Operazione su metadati del lab (<code>${esc(prev.titolo)}</code>).</div>`;

  apriModal(
    'Anteprima modifiche: ' + prev.titolo,
    deltaHtml + noteHtml + diffHtml + `<div class="fhelp">Alla conferma verrà salvata automaticamente una copia di sicurezza in <code>.backup_labgenerator/${esc(S.nome)}/</code>.</div>`,
    `<button class="ghost" id="mCancel">Annulla</button><button class="okbtn" id="mCommit">✔ Conferma e scrivi</button>`,
    {
      wide: true,
      noFocus: true,
      onMount: () => {
        $('#mCommit').onclick = async e => {
          const btn = e.target; btn.disabled = true; btn.textContent = 'Scrittura…';
          try {
            const res = await apiPost('/api/edit/commit', {lab: S.nome, op, params});
            chiudiModal();
            toast('✔ ' + res.titolo + (res.backup ? ' (backup salvato)' : ''));
            await apriLab(S.nome, true);
            if (opts.onDone) opts.onDone(res);
          } catch (err) {
            modalErrore(err.message);
            btn.disabled = false; btn.textContent = '✔ Conferma e scrivi';
          }
        };
      }
    }
  );
}

function nomiLanLab() { return S.lab ? S.lab.lan.map(l => l.nome) : []; }
function routerLab() { return S.lab ? S.lab.dispositivi.filter(d => d.tipo === 'router') : []; }
function dnsLab() { return S.lab ? S.lab.dispositivi.filter(d => d.tipo === 'dns') : []; }
function prossimoNome(pref) {
  const esistenti = new Set((S.lab ? S.lab.dispositivi : []).map(d => d.nome));
  let i = 1; while (esistenti.has(pref + i)) i++; return pref + i;
}
function routerSuLan(lan) {
  if (!S.lab || !lan) return [];
  const out = [];
  for (const d of S.lab.dispositivi) {
    if (d.tipo !== 'router') continue;
    for (const it of d.interfacce) if (it.lan === lan && it.ip) out.push({nome: d.nome, ip: it.ip.split('/')[0], cidr: it.ip});
  }
  return out;
}
function asMultiBgp() {
  const perAs = {};
  for (const d of routerLab()) {
    if (d.demoni.includes('bgpd') && d.asn) (perAs[d.asn] = perAs[d.asn] || []).push(d.nome);
  }
  return Object.entries(perAs).filter(([, rs]) => rs.length >= 2).sort((a, b) => (+a[0] || 0) - (+b[0] || 0));
}
function lanDatalistHtml() {
  if (!S.lab) return '';
  return (S.lab.lan || []).map(l => `<option value="${esc(l.nome)}">${esc(l.nome + (l.subnet ? ' (' + l.subnet + ')' : ''))}</option>`).join('');
}
function lanEsistenteConSubnet(lan) {
  if (!S.lab || !lan) return false;
  const k = lan.trim();
  return (S.lab.lan || []).some(l => l.nome === k && !!l.subnet);
}
async function suggerisciIp(lan, inputEl, opts) {
  opts = opts || {};
  if (!S.nome || !lan || !lan.trim()) {
    if (!opts.silent) toast('Inserisci o seleziona prima una LAN.', 'warn');
    return;
  }
  try {
    const payload = {lab: S.nome, lan: lan.trim()};
    if (opts.exclude && opts.exclude.length) payload.exclude = opts.exclude;
    const r = await apiPost('/api/edit/suggest_ip', payload);
    if (r.ip && inputEl) {
      inputEl.value = r.ip;
      inputEl.dispatchEvent(new Event('input', {bubbles: true}));
    } else if (!opts.silent) {
      toast('LAN nuova o senza subnet rilevata: inserisci IP/CIDR manualmente.', 'warn');
    }
  } catch (e) {}
}
function collegaAutoSuggerisciLan(lanEl, ipEl, getExclude, onLanChange) {
  if (!lanEl || !ipEl) return;
  let lastAutoLan = '';
  const trigger = () => {
    const val = lanEl.value.trim();
    if (onLanChange) onLanChange(val);
    if (val && val !== lastAutoLan && lanEsistenteConSubnet(val)) {
      lastAutoLan = val;
      const excl = getExclude ? getExclude() : [];
      suggerisciIp(val, ipEl, {silent: true, exclude: excl});
    } else if (!val || !lanEsistenteConSubnet(val)) {
      lastAutoLan = '';
    }
  };
  lanEl.addEventListener('change', trigger);
  lanEl.addEventListener('input', trigger);
}
function creaListaInterfacceDnd(container, opts) {
  opts = opts || {};
  const ipPlaceholder = opts.ipPlaceholder || 'IP/CIDR (es. 10.0.0.1/24)';
  let dragSrc = null;

  function altriIpInLista(excludeRow) {
    return [...container.querySelectorAll('.if-card')]
      .filter(r => r !== excludeRow)
      .map(r => r.querySelector('.ifIp').value.trim())
      .filter(Boolean);
  }
  function aggiornaEtichette() {
    const rows = [...container.querySelectorAll('.if-card')];
    rows.forEach((r, idx) => {
      const badge = r.querySelector('.if-badge');
      if (badge) badge.textContent = `eth${idx} · LAN ${idx}`;
      const rm = r.querySelector('.ifRm');
      if (rm) rm.disabled = rows.length <= 1;
    });
    if (opts.onChange) opts.onChange();
  }
  function addRow(lan, ip, origDev) {
    const row = document.createElement('div');
    row.className = 'if-card';
    row.draggable = true;
    if (origDev) row.dataset.origDev = origDev;
    row.innerHTML = `<span class="if-handle" title="Trascina per spostare questa LAN su un'altra interfaccia">⋮⋮</span>
      <span class="if-badge">eth0 · LAN 0</span>
      <input class="ifLan" list="mLanList" placeholder="LAN (es. A)" value="${esc(lan || '')}">
      <input class="ifIp" placeholder="${esc(ipPlaceholder)}" value="${esc(ip || '')}">
      <button type="button" class="small ghost ifSug" title="Inserisce il prossimo IP libero della LAN">Suggerisci IP</button>
      <button type="button" class="small danger if-rm ifRm" title="Rimuovi questa interfaccia">✕</button>`;

    const lanEl = row.querySelector('.ifLan');
    const ipEl = row.querySelector('.ifIp');
    // Evita che il drag interferisca con la selezione del testo negli input
    row.querySelectorAll('input,button').forEach(ctrl => {
      ctrl.addEventListener('mousedown', () => { row.draggable = false; });
      ctrl.addEventListener('mouseup', () => { row.draggable = true; });
      ctrl.addEventListener('blur', () => { row.draggable = true; });
    });
    row.querySelector('.if-handle').addEventListener('mousedown', () => { row.draggable = true; });

    collegaAutoSuggerisciLan(lanEl, ipEl, () => altriIpInLista(row), opts.onLanInput);
    row.querySelector('.ifSug').onclick = () => suggerisciIp(lanEl.value, ipEl, {exclude: altriIpInLista(row)});
    row.querySelector('.ifRm').onclick = () => {
      if (container.querySelectorAll('.if-card').length > 1) {
        row.remove();
        aggiornaEtichette();
      }
    };

    row.addEventListener('dragstart', e => {
      if (document.activeElement && (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'BUTTON')) {
        e.preventDefault();
        return;
      }
      dragSrc = row;
      row.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
      try { e.dataTransfer.setData('text/plain', ''); } catch (_) {}
    });
    row.addEventListener('dragover', e => {
      if (!dragSrc || dragSrc === row) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      container.querySelectorAll('.if-card').forEach(x => x.classList.remove('drag-over'));
      row.classList.add('drag-over');
    });
    row.addEventListener('dragleave', () => row.classList.remove('drag-over'));
    row.addEventListener('drop', e => {
      e.preventDefault();
      row.classList.remove('drag-over');
      if (!dragSrc || dragSrc === row) return;
      const all = [...container.querySelectorAll('.if-card')];
      const fromIdx = all.indexOf(dragSrc);
      const toIdx = all.indexOf(row);
      if (fromIdx < toIdx) row.after(dragSrc);
      else row.before(dragSrc);
      aggiornaEtichette();
    });
    row.addEventListener('dragend', () => {
      if (dragSrc) dragSrc.classList.remove('dragging');
      container.querySelectorAll('.if-card').forEach(x => x.classList.remove('drag-over'));
      dragSrc = null;
      row.draggable = true;
    });

    container.appendChild(row);
    aggiornaEtichette();
    return row;
  }
  function getValues() {
    return [...container.querySelectorAll('.if-card')]
      .map(r => ({
        orig_dev: r.dataset.origDev || '',
        lan: r.querySelector('.ifLan').value.trim(),
        ip: r.querySelector('.ifIp').value.trim(),
      }))
      .filter(x => x.lan || x.ip);
  }
  return {addRow, getValues, refresh: aggiornaEtichette};
}

function chiudiCtx() {
  const m = $('#ctxMenu');
  if (m) { m.hidden = true; m.innerHTML = ''; }
}
function mostraCtx(x, y, titolo, badge, voci) {
  const m = $('#ctxMenu');
  let html = `<div class="ctx-head"><span>${esc(titolo)}</span>${badge ? `<span class="badge">${esc(badge)}</span>` : ''}</div>`;
  for (const v of voci) {
    if (v.sep) { html += '<div class="ctx-sep"></div>'; continue; }
    if (v.sec) { html += `<div class="ctx-sec">${esc(v.sec)}</div>`; continue; }
    const cls = v.cls ? ' ' + v.cls : '';
    html += `<button class="ctx-item${cls}" data-idx="${v._i}">${esc(v.label)}${v.hint ? `<span class="ctx-hint">${esc(v.hint)}</span>` : ''}</button>`;
  }
  m.innerHTML = html;
  m.hidden = false;
  const w = m.offsetWidth || 270, h = m.offsetHeight || 300;
  const px = Math.max(6, Math.min(x, window.innerWidth - w - 8));
  const py = Math.max(6, Math.min(y, window.innerHeight - h - 8));
  m.style.left = px + 'px';
  m.style.top = py + 'px';
  m.onclick = e => {
    const b = e.target.closest('[data-idx]');
    if (!b) return;
    const item = voci.find(v => String(v._i) === b.dataset.idx);
    chiudiCtx();
    if (item && item.fn) item.fn();
  };
}
function numeraVoci(voci) {
  let i = 0;
  return voci.map(v => (v.fn ? Object.assign({_i: ++i}, v) : v));
}

document.addEventListener('pointerdown', e => {
  const m = $('#ctxMenu');
  if (!m || m.hidden) return;
  if (!e.target.closest('#ctxMenu')) chiudiCtx();
});
window.addEventListener('blur', chiudiCtx);
window.addEventListener('resize', chiudiCtx);

$('#svg').addEventListener('contextmenu', e => {
  e.preventDefault();
  e.stopPropagation();
  if (!S.lab) return;
  const gNode = e.target.closest('[data-id]');
  if (gNode) {
    const id = gNode.dataset.id;
    if (id.startsWith('d:')) {
      const dev = dispositivo(id.slice(2));
      if (dev) {
        S.sel = dev.nome; ridisegna(); lato();
        apriCtxDispositivo(e.clientX, e.clientY, dev);
        return;
      }
    } else if (id.startsWith('l:')) {
      apriCtxLan(e.clientX, e.clientY, id.slice(2));
      return;
    }
  }
  const gLan = e.target.closest('[data-lan]');
  if (gLan) {
    apriCtxLan(e.clientX, e.clientY, gLan.dataset.lan);
    return;
  }
  apriCtxSfondo(e.clientX, e.clientY);
});

function apriCtxSfondo(x, y) {
  const voci = [
    {sec: 'Aggiungi dispositivo'},
    {label: '＋ Aggiungi Router', hint: 'BGP / OSPF / RIP / Statico', fn: () => modalAddRouter()},
    {label: '＋ Aggiungi Host / PC', hint: 'singola o multi-NIC', fn: () => modalAddHost()},
    {label: '＋ Aggiungi Server WWW', hint: 'Apache2', fn: () => modalAddWww()},
    {label: '＋ Aggiungi Server DNS', hint: 'BIND9 root / zone', fn: () => modalAddDns()},
    {sep: true},
    {sec: 'Operazioni globali sul lab'},
    {label: '⇄ Sessioni iBGP Full Mesh (per AS)', fn: () => modalIbgpMesh()},
    {label: '⚙ Costi OSPF predefiniti a 10 (auto-cost)', fn: () => modalAutoCost()},
    {label: '📋 Comando PING one-liner', fn: () => modalPingOneliner()},
    {label: '↺ Ripristina da backup', hint: String((S.lab.backups || []).length), fn: () => modalBackups()},
    {sep: true},
    {sec: 'Vista'},
    {label: '⟳ Riordina layout', fn: () => $('#bRiordina').click()},
    {label: '⤢ Adatta alla finestra', fn: () => $('#bAdatta').click()},
    {label: '⬇ Esporta topologia SVG', fn: () => $('#bSvg').click()},
  ];
  mostraCtx(x, y, 'Canvas: ' + S.nome, S.lab.dispositivi.length + ' nodi', numeraVoci(voci));
}

function apriCtxDispositivo(x, y, d) {
  const voci = [];
  if (d.problemi && d.problemi.length) {
    voci.push({label: `⚠ Diagnostica e correggi (${d.problemi.length})`, cls: 'warn', fn: () => modalDiagnostica(d)});
    voci.push({sep: true});
  }
  voci.push({sec: 'Configurazione dispositivo'});
  if (d.tipo === 'router') {
    voci.push({label: '✎ Modifica Router (AS, IGP, BGP, LAN…)', hint: d.asn ? 'AS' + d.asn : '', fn: () => modalEditRouter(d)});
  }
  voci.push({label: '🔌 Interfacce (Riordina / IP / LAN)', fn: () => modalInterfacce(d)});
  voci.push({label: '◎ Aggiungi interfaccia Loopback (lo)', fn: () => modalLoopback(d)});
  if (d.tipo === 'router') {
    if (d.has_frr) {
      voci.push({label: '⇄ Protocolli (aggiungi / togli BGP, OSPF, RIP)', fn: () => modalProtocolli(d)});
      if (d.asn && d.demoni.includes('bgpd')) voci.push({label: '🏷 Cambia numero AS', hint: 'AS' + d.asn, fn: () => modalCambiaAs(d)});
    }
    if (d.demoni.includes('bgpd')) {
      voci.push({sep: true}, {sec: 'BGP & Policy'});
      voci.push({label: '🛡 Aggiungi Policy BGP…', hint: 'PL / LP / MED / CPP / Def', fn: () => modalBgpPolicy(d)});
      voci.push({label: '📢 Modifica / Gestisci network BGP', hint: 'modifica / aggiungi', fn: () => modalBgpNetwork(d)});
    }
    if (d.demoni.includes('ospfd') || d.demoni.includes('ripd')) {
      voci.push({sep: true}, {sec: 'IGP (OSPF / RIP)'});
      if (d.demoni.includes('ospfd')) voci.push({label: '⚖ Imposta costo OSPF su interfaccia', fn: () => modalOspfCost(d)});
      if (d.demoni.includes('bgpd')) voci.push({label: '⇵ Ridistribuzione BGP → IGP', fn: () => modalRedistribute(d)});
      voci.push({label: '↪ Default route in IGP (OSPF/RIP)', fn: () => modalDefaultIgp(d)});
    }
  } else {
    voci.push({label: '↪ Cambia Default Gateway', hint: d.gateway || 'nessuno', fn: () => modalGateway(d)});
    if (d.tipo === 'dns' && d.is_dns_root) {
      voci.push({label: '🌐 Aggiungi delega DNS (db.root)', fn: () => modalDnsDelegation(d)});
    }
  }
  voci.push({label: '🧭 Assegna Resolver DNS (resolv.conf)', hint: (d.nameserver || [])[0] || '-', fn: () => modalResolver(d)});
  voci.push({sep: true}, {sec: 'File & Diagnostica'});
  voci.push({label: '✎ Editor file a righe (con check FRR)', fn: () => modalEditorFile(d)});
  voci.push({label: '💻 Apri terminale (kathara connect)', fn: () => {
    azione({azione: 'terminale', dev: d.nome}).then(r => toast(r.messaggio, r.ok ? '' : 'warn')).catch(errore);
  }});
  if (d.tipo === 'router' && d.demoni.includes('bgpd')) {
    voci.push({label: '▶ show ip bgp summary', fn: () => esegui({azione: 'comando', dev: d.nome, comando: 'bgp_summary'}, d.nome + ': show ip bgp summary')});
  }
  voci.push({label: '▶ show ip route / ip route', fn: () => esegui({azione: 'comando', dev: d.nome, comando: d.tipo === 'router' ? 'route' : 'ip_route'}, d.nome + ': route')});
  voci.push({sep: true});
  voci.push({label: '🗑 Elimina ' + d.nome, cls: 'danger', fn: () => modalEliminaDispositivo(d)});

  mostraCtx(x, y, d.nome, d.tipo + (d.asn ? ' · AS' + d.asn : ''), numeraVoci(voci));
}

function apriCtxLan(x, y, lanNome) {
  const l = (S.lab.lan || []).find(z => z.nome === lanNome);
  if (!l) return;
  const membriDev = l.membri.map(n => dispositivo(n)).filter(Boolean);
  const bgpMembri = membriDev.filter(d => d.tipo === 'router' && d.demoni.includes('bgpd'));
  const ospfMembri = membriDev.filter(d => d.tipo === 'router' && d.demoni.includes('ospfd'));
  const spento = S.spenti && S.spenti.has(lanNome);

  const voci = [];
  if (l.avvisi && l.avvisi.length) {
    voci.push({label: `⚠ Avvisi LAN ${lanNome} (${l.avvisi.length})`, cls: 'warn', fn: () => {
      apriModal('Avvisi LAN ' + lanNome,
        `<ul class="avvisi">${l.avvisi.map(a => `<li class="koline">${esc(a)}</li>`).join('')}</ul>`,
        `<button class="ghost" id="mCancel">Chiudi</button><button id="mRen">Rinumera LAN ${esc(lanNome)}</button>`,
        {onMount: () => { $('#mRen').onclick = () => modalRinumeraLan(lanNome); }});
    }});
    voci.push({sep: true});
  }
  voci.push({sec: 'Modifica LAN / Link'});
  voci.push({label: '🔢 Rinumera rete della LAN', hint: l.subnet || '-', fn: () => modalRinumeraLan(lanNome)});
  voci.push({label: '🔌 Collega un dispositivo a questa LAN', fn: () => modalCollegaAllaLan(lanNome)});
  if (bgpMembri.length === 2) {
    const [r1, r2] = bgpMembri;
    const ip2 = (r2.interfacce.find(it => it.lan === lanNome) || {}).ip || '';
    const ip1 = (r1.interfacce.find(it => it.lan === lanNome) || {}).ip || '';
    voci.push({sep: true}, {sec: 'Policy BGP sul link'});
    voci.push({label: `🛡 Policy su ${r1.nome} verso ${r2.nome}`, hint: ip2.split('/')[0], fn: () => modalBgpPolicy(r1, {neighbor_ip: ip2.split('/')[0], neighbor_name: r2.nome, neighbor_asn: r2.asn})});
    voci.push({label: `🛡 Policy su ${r2.nome} verso ${r1.nome}`, hint: ip1.split('/')[0], fn: () => modalBgpPolicy(r2, {neighbor_ip: ip1.split('/')[0], neighbor_name: r1.nome, neighbor_asn: r1.asn})});
  }
  if (ospfMembri.length) {
    voci.push({sep: true}, {sec: 'Costo OSPF sul link'});
    for (const r of ospfMembri) {
      const it = r.interfacce.find(i => i.lan === lanNome);
      if (it) voci.push({label: `⚖ Costo OSPF su ${r.nome} ${it.dev}`, hint: it.costo ? '=' + it.costo : 'default', fn: () => modalOspfCost(r, it.dev)});
    }
  }
  voci.push({sep: true}, {sec: 'Simulazione guasto (live)'});
  voci.push({
    label: spento ? `⚡ Riaccendi link ${lanNome}` : `⚡ Spegni link ${lanNome} (simula guasto)`,
    cls: spento ? '' : 'danger',
    fn: () => link(lanNome, spento, null)
  });

  mostraCtx(x, y, 'LAN ' + lanNome, l.subnet || 'nessuna subnet', numeraVoci(voci));
}

function modalNuovoLab() {
  const st = {tab: 'empty', routers: [], hosts: [], wwws: [], dns: []};
  function renderList() {
    const el = $('#wList'); if (!el) return;
    const items = [
      ...st.routers.map((r, i) => ({t: 'Router', n: r.nome, d: `${r.protocols.join(',')}${r.asn ? ' AS'+r.asn : ''} · ${r.interfaces.map(x=>x.lan+':'+x.ip).join(', ')}`, del: () => { st.routers.splice(i,1); renderList(); }})),
      ...st.hosts.map((h, i) => ({t: 'Host', n: h.nome, d: `${h.interfaces.map(x=>x.lan+':'+x.ip).join(', ')}${h.gateway ? ' gw '+h.gateway : ''}`, del: () => { st.hosts.splice(i,1); renderList(); }})),
      ...st.wwws.map((w, i) => ({t: 'WWW', n: w.nome, d: `${w.lan}:${w.ip} gw ${w.gateway}`, del: () => { st.wwws.splice(i,1); renderList(); }})),
      ...st.dns.map((d, i) => ({t: 'DNS', n: d.nome, d: `${d.lan}:${d.ip} (${d.root_type})`, del: () => { st.dns.splice(i,1); renderList(); }})),
    ];
    el.innerHTML = items.length ? `<table><tr><th>Tipo</th><th>Nome</th><th>Dettagli</th><th></th></tr>${items.map((x, idx) =>
      `<tr><td><span class="badge">${x.t}</span></td><td><b>${esc(x.n)}</b></td><td class="small">${esc(x.d)}</td><td><button class="small ghost" data-rm="${idx}">✕</button></td></tr>`).join('')}</table>`
      : '<div class="muted small">Nessun dispositivo ancora aggiunto al wizard. Puoi anche creare un lab vuoto e costruirlo col tasto destro sul canvas.</div>';
    el.onclick = e => { const b = e.target.closest('[data-rm]'); if (b) items[+b.dataset.rm].del(); };
  }

  apriModal(
    'Nuovo Laboratorio Kathará',
    `<div class="fgrid">
      <div class="field"><label>Nome laboratorio (cartella)</label><input id="nlNome" placeholder="es. cognomenome oppure bgp_es1"><div class="fhelp">All'esame usa <code>&lt;cognome&gt;&lt;nome&gt;</code> (minuscole, cifre, _).</div></div>
      <div class="field"><label>Opzioni iniziali</label>
        <div class="chkrow" style="margin-top:6px">
          <label><input type="checkbox" id="nlXml"> Esporta XML</label>
          <label><input type="checkbox" id="nlOver"> Sovrascrivi se esiste</label>
        </div>
      </div>
    </div>
    <div class="mtabs" id="nlTabs">
      <button data-t="empty" class="on">Canvas vuoto (costruzione visuale)</button>
      <button data-t="wiz">Wizard rapido multi-dispositivo</button>
    </div>
    <div id="nlEmpty" class="finfo">Crea subito il lab vuoto e lo apre nell'editor visuale: fai <b>clic destro sullo sfondo</b> per aggiungere Router, Host, WWW, DNS e collegarli in modo interattivo.</div>
    <div id="nlWiz" hidden>
      <div class="btns">
        <button class="small ghost" id="wAddR">＋ Router</button>
        <button class="small ghost" id="wAddH">＋ Host/PC</button>
        <button class="small ghost" id="wAddW">＋ Server WWW</button>
        <button class="small ghost" id="wAddD">＋ Server DNS</button>
      </div>
      <div id="wSub" class="card" hidden></div>
      <div id="wList"></div>
      <div class="field" style="margin-top:10px"><label>Resolver DNS globale opzionale (IP per resolv.conf su tutti i non-DNS)</label><input id="nlRes" placeholder="es. 20.1.0.3 (lascia vuoto per nessuno)"></div>
    </div>`,
    `<button class="ghost" id="mCancel">Annulla</button><button id="nlCrea">Crea Laboratorio</button>`,
    {
      wide: true,
      onMount: () => {
        renderList();
        $('#nlTabs').onclick = e => {
          const b = e.target.closest('button'); if (!b) return;
          st.tab = b.dataset.t;
          $('#nlTabs').querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
          $('#nlEmpty').hidden = st.tab !== 'empty';
          $('#nlWiz').hidden = st.tab !== 'wiz';
        };
        const sub = $('#wSub');
        $('#wAddR').onclick = () => {
          sub.hidden = false;
          sub.innerHTML = `<h3>Aggiungi Router al Wizard</h3>
            <div class="fgrid three">
              <div class="field"><label>Nome</label><input id="wrN" value="r${st.routers.length+1}"></div>
              <div class="field"><label>Protocolli</label><div class="chkrow"><label><input type="checkbox" class="wrP" value="bgp" checked>BGP</label><label><input type="checkbox" class="wrP" value="ospf">OSPF</label><label><input type="checkbox" class="wrP" value="rip">RIP</label><label><input type="checkbox" class="wrP" value="statico">Statico</label></div></div>
              <div class="field"><label>ASN (se BGP)</label><input id="wrA" placeholder="es. 10"></div>
              <div class="field full"><label>Interfacce (una per riga: <code>LAN IP/CIDR</code>)</label><textarea id="wrI" rows="2" placeholder="A 10.0.0.1/24&#10;B 10.20.0.1/30"></textarea></div>
              <div class="field"><label>Area OSPF</label><input id="wrArea" value="0.0.0.0"></div>
              <div class="field"><label>Network IGP (opz.)</label><input id="wrIgp" placeholder="auto se vuoto"></div>
              <div class="field"><label>Redistribute BGP in IGP</label><label><input type="checkbox" id="wrRed" checked> Sì</label></div>
            </div>
            <div class="riga"><button class="small" id="wrOk">Aggiungi alla lista</button><button class="small ghost" id="wrNo">Chiudi</button></div>`;
          $('#wrNo').onclick = () => sub.hidden = true;
          $('#wrOk').onclick = () => {
            const protos = [...sub.querySelectorAll('.wrP:checked')].map(c => c.value);
            const ifaces = $('#wrI').value.trim().split('\n').map(l => l.trim().split(/\s+/)).filter(a => a.length >= 2).map(([lan, ip]) => ({lan, ip}));
            if (!$('#wrN').value.trim() || !protos.length || !ifaces.length) { modalErrore('Compila nome, protocolli e almeno una interfaccia (LAN IP/CIDR).'); return; }
            modalErrore('');
            st.routers.push({nome: $('#wrN').value.trim(), protocols: protos, asn: $('#wrA').value.trim(), ospf_area: $('#wrArea').value.trim() || '0.0.0.0', igp_networks: $('#wrIgp').value.trim() || null, igp_redistribute_bgp: $('#wrRed').checked, interfaces: ifaces});
            sub.hidden = true; renderList();
          };
        };
        $('#wAddH').onclick = () => {
          sub.hidden = false;
          sub.innerHTML = `<h3>Aggiungi Host/PC al Wizard</h3>
            <div class="fgrid three">
              <div class="field"><label>Nome</label><input id="whN" value="pc${st.hosts.length+1}"></div>
              <div class="field"><label>LAN</label><input id="whL" placeholder="es. A"></div>
              <div class="field"><label>IP/CIDR</label><input id="whIp" placeholder="es. 10.0.0.10/24"></div>
              <div class="field"><label>Gateway</label><input id="whGw" placeholder="es. 10.0.0.1"></div>
            </div>
            <div class="riga"><button class="small" id="whOk">Aggiungi</button><button class="small ghost" id="whNo">Chiudi</button></div>`;
          $('#whNo').onclick = () => sub.hidden = true;
          $('#whOk').onclick = () => {
            if (!$('#whN').value.trim() || !$('#whL').value.trim() || !$('#whIp').value.trim()) { modalErrore('Compila nome, LAN e IP/CIDR.'); return; }
            modalErrore('');
            st.hosts.push({nome: $('#whN').value.trim(), interfaces: [{lan: $('#whL').value.trim(), ip: $('#whIp').value.trim()}], gateway: $('#whGw').value.trim()});
            sub.hidden = true; renderList();
          };
        };
        $('#wAddW').onclick = () => {
          sub.hidden = false;
          sub.innerHTML = `<h3>Aggiungi Server WWW al Wizard</h3>
            <div class="fgrid three">
              <div class="field"><label>Nome</label><input id="wwN" value="www${st.wwws.length+1}"></div>
              <div class="field"><label>LAN</label><input id="wwL" placeholder="es. A"></div>
              <div class="field"><label>IP/CIDR</label><input id="wwIp" placeholder="es. 10.0.0.80/24"></div>
              <div class="field"><label>Gateway</label><input id="wwGw" placeholder="es. 10.0.0.1"></div>
            </div>
            <div class="riga"><button class="small" id="wwOk">Aggiungi</button><button class="small ghost" id="wwNo">Chiudi</button></div>`;
          $('#wwNo').onclick = () => sub.hidden = true;
          $('#wwOk').onclick = () => {
            st.wwws.push({nome: $('#wwN').value.trim(), lan: $('#wwL').value.trim(), ip: $('#wwIp').value.trim(), gateway: $('#wwGw').value.trim()});
            sub.hidden = true; renderList();
          };
        };
        $('#wAddD').onclick = () => {
          sub.hidden = false;
          sub.innerHTML = `<h3>Aggiungi Server DNS al Wizard</h3>
            <div class="fgrid three">
              <div class="field"><label>Nome</label><input id="wdN" value="${st.dns.length ? 'dns'+st.dns.length : 'root'}"></div>
              <div class="field"><label>LAN</label><input id="wdL" placeholder="es. A"></div>
              <div class="field"><label>IP/CIDR</label><input id="wdIp" placeholder="es. 10.0.0.53/24"></div>
              <div class="field"><label>Gateway</label><input id="wdGw" placeholder="es. 10.0.0.1"></div>
              <div class="field"><label>Ruolo zona "."</label><select id="wdRt"><option value="master">Root (master per .)</option><option value="hint">Autorevole / Resolver (hint)</option><option value="none">Nessuna zona .</option></select></div>
            </div>
            <div class="riga"><button class="small" id="wdOk">Aggiungi</button><button class="small ghost" id="wdNo">Chiudi</button></div>`;
          $('#wdNo').onclick = () => sub.hidden = true;
          $('#wdOk').onclick = () => {
            st.dns.push({nome: $('#wdN').value.trim(), lan: $('#wdL').value.trim(), ip: $('#wdIp').value.trim(), gateway: $('#wdGw').value.trim(), root_type: $('#wdRt').value});
            sub.hidden = true; renderList();
          };
        };
        $('#nlCrea').onclick = async () => {
          const nome = $('#nlNome').value.trim();
          if (!nome) { modalErrore('Inserisci un nome per il laboratorio.'); return; }
          try {
            const payload = {
              nome,
              overwrite: $('#nlOver').checked,
              export_xml: $('#nlXml').checked,
              routers: st.tab === 'wiz' ? st.routers : [],
              hosts: st.tab === 'wiz' ? st.hosts : [],
              wwws: st.tab === 'wiz' ? st.wwws : [],
              dns: st.tab === 'wiz' ? st.dns : [],
              global_resolver: st.tab === 'wiz' ? $('#nlRes').value.trim() : '',
            };
            const r = await apiPost('/api/edit/create_lab', payload);
            chiudiModal();
            toast('✔ Laboratorio ' + r.lab + ' creato');
            await caricaLabs();
            await apriLab(r.lab);
          } catch (e) { modalErrore(e.message); }
        };
      }
    }
  );
}

function modalImporta() {
  apriModal(
    'Importa Laboratorio da XML / JSON',
    `<div class="fwarn">L'XML contiene i dati della creazione iniziale; eventuali nomi non validi per Kathará vengono corretti automaticamente.</div>
    <div class="fgrid one">
      <div class="field"><label>File XML o JSON</label><input type="file" id="impFile" accept=".xml,.json,text/xml,application/json"></div>
      <div class="field"><label>Nome lab personalizzato (opzionale, altrimenti usa il nome nel file)</label><input id="impName" placeholder="lascia vuoto per nome originale"></div>
      <div class="chkrow"><label><input type="checkbox" id="impOver"> Sovrascrivi se il lab esiste già (crea backup automatico)</label></div>
    </div>`,
    `<button class="ghost" id="mCancel">Annulla</button><button id="impGo">Importa</button>`,
    {
      onMount: () => {
        $('#impGo').onclick = async () => {
          const f = $('#impFile').files && $('#impFile').files[0];
          if (!f) { modalErrore('Seleziona un file .xml o .json.'); return; }
          const content = await f.text();
          try {
            const r = await apiPost('/api/edit/import', {
              filename: f.name,
              content,
              overwrite: $('#impOver').checked,
              custom_name: $('#impName').value.trim(),
            });
            if (r.esiste) {
              modalErrore(`Il lab '${r.lab}' esiste già. Spunta "Sovrascrivi" oppure indica un nome diverso.`);
              return;
            }
            chiudiModal();
            toast('✔ Lab ' + r.lab + ' importato');
            await caricaLabs();
            await apriLab(r.lab);
          } catch (e) { modalErrore(e.message); }
        };
      }
    }
  );
}

async function modalPingOneliner() {
  if (!S.nome) return;
  try {
    const r = await apiPost('/api/edit/ping_oneliner', {lab: S.nome});
    apriModal(
      'Comando PING One-liner (' + r.conteggio + ' IP)',
      `<div class="finfo">Copia e incolla questo comando nel terminale di qualsiasi macchina del lab (<code>kathara connect &lt;dispositivo&gt;</code>) per testare la raggiungibilità di tutti gli IP.</div>
      <pre class="file" id="pingCmdBox" style="max-height:240px;white-space:pre-wrap;word-break:break-all">${esc(r.comando)}</pre>`,
      `<button class="ghost" id="mCancel">Chiudi</button><button id="mCopyPing">📋 Copia comando</button>`,
      {onMount: () => { $('#mCopyPing').onclick = () => copiaTesto(r.comando); }}
    );
  } catch (e) { toast(e.message, 'err'); }
}

async function modalBackups() {
  if (!S.nome) return;
  let list = [];
  try { list = (await api('/api/backups?lab=' + encodeURIComponent(S.nome))).backups || []; }
  catch (e) { toast(e.message, 'err'); return; }
  apriModal(
    'Cronologia Backup e Ripristino — ' + S.nome,
    list.length
      ? `<div class="finfo">Ogni modifica confermata salva automaticamente uno snapshot del lab in <code>.backup_labgenerator/${esc(S.nome)}/</code>. Il ripristino salva prima lo stato attuale.</div>
        <table><tr><th>Snapshot (più recente in alto)</th><th></th></tr>${list.slice(0, 25).map(b =>
          `<tr><td><code>${esc(b)}</code></td><td style="text-align:right"><button class="small warn" data-rest="${esc(b)}">↺ Ripristina</button></td></tr>`).join('')}</table>`
      : '<div class="muted">Nessun backup presente per questo lab. Verranno creati automaticamente alla prima modifica.</div>',
    `<button class="ghost" id="mCancel">Chiudi</button>`,
    {
      onMount: box => {
        box.onclick = async e => {
          const b = e.target.closest('[data-rest]'); if (!b) return;
          const bk = b.dataset.rest;
          b.disabled = true; b.textContent = 'Ripristino…';
          try {
            const r = await apiPost('/api/edit/restore', {lab: S.nome, backup: bk});
            chiudiModal();
            toast('✔ Lab ripristinato a ' + r.ripristinato);
            await apriLab(S.nome, true);
          } catch (err) { modalErrore(err.message); b.disabled = false; b.textContent = '↺ Ripristina'; }
        };
      }
    }
  );
}

function modalStrumentiLab() {
  if (!S.lab) return;
  const inv = S.lab.nomi_non_validi || [];
  apriModal(
    'Strumenti Laboratorio — ' + S.nome,
    `<div class="fgrid">
      <div class="card" style="margin:0"><h3>Routing globale</h3>
        <div class="btns">
          <button class="small ghost" id="stIbgp">⇄ iBGP Full Mesh (per AS)</button>
          <button class="small ghost" id="stAuto">⚙ Costi OSPF a 10 (auto-cost)</button>
        </div>
      </div>
      <div class="card" style="margin:0"><h3>XML &amp; Test rapido</h3>
        <div class="btns">
          <button class="small ghost" id="stPing">📋 Comando PING one-liner</button>
          <button class="small ghost" id="stRegenXml">↻ Rigenera XML</button>
          ${S.lab.xml ? '<button class="small danger" id="stDelXml">✕ Elimina XML (pre-consegna)</button>' : ''}
        </div>
      </div>
      <div class="card" style="margin:0"><h3>Sicurezza &amp; Ripristino</h3>
        <div class="btns">
          <button class="small ghost" id="stBk">↺ Cronologia Backup (${(S.lab.backups || []).length})</button>
          ${inv.length ? `<button class="small danger" id="stFixN">Correggi ${inv.length} nomi non validi Kathará</button>` : '<span class="okline small">✔ Tutti i nomi dispositivo sono validi Kathará</span>'}
        </div>
      </div>
      <div class="card" style="margin:0"><h3>Gestione cartella lab</h3>
        <div class="btns">
          <button class="small warnbtn" id="stResetTopo">↺ RESETTA TOPOLOGIA</button>
          <button class="small danger" id="stDelLab">🗑 Elimina laboratorio (con backup)</button>
        </div>
      </div>
    </div>`,
    `<button class="ghost" id="mCancel">Chiudi</button>`,
    {
      onMount: () => {
        $('#stIbgp').onclick = modalIbgpMesh;
        $('#stAuto').onclick = modalAutoCost;
        $('#stPing').onclick = modalPingOneliner;
        $('#stBk').onclick = modalBackups;
        $('#stRegenXml').onclick = () => eseguiModifica('regen_xml', {});
        const dx = $('#stDelXml'); if (dx) dx.onclick = () => eseguiModifica('delete_xml', {});
        const fn = $('#stFixN'); if (fn) fn.onclick = () => eseguiModifica('fix_names', {});
        $('#stResetTopo').onclick = () => {
          apriModal(
            'Conferma RESETTA TOPOLOGIA — ' + S.nome,
            `<div class="fwarn"><b>Attenzione:</b> questa operazione rimuove <b>tutte le policy BGP</b> (prefix-list, route-map, access-list, local-pref, MED, default-originate), <b>tutti i neighbor BGP</b>, <b>tutti gli annunci di rete BGP/OSPF/RIP</b>, i costi OSPF e le rotte statiche sui router.<br><br>
            Rimangono invece intatti la <b>topologia base</b> (nodi, LAN, interfacce e IP), gli host/WWW/DNS e i <b>protocolli attivati</b> sui router (daemons e numero AS). Potrai verificare le modifiche nell'<b>Anteprima Diff</b> e verrà creato un backup automatico.</div>`,
            `<button class="ghost" id="mCancel">Annulla</button><button class="warnbtn" id="mConfirmReset">↺ Procedi con Anteprima Diff →</button>`,
            {onMount: () => {
              $('#mConfirmReset').onclick = () => eseguiModifica('reset_topology', {});
            }}
          );
        };
        $('#stDelLab').onclick = () => {
          apriModal(
            'Conferma eliminazione lab ' + S.nome,
            `<div class="fwarn">La cartella <code>${esc(S.nome)}</code> verrà rimossa dopo aver salvato una copia di sicurezza in <code>.backup_labgenerator/${esc(S.nome)}/</code>.</div>`,
            `<button class="ghost" id="mCancel">Annulla</button><button class="danger" id="mConfirmDel">Elimina definitivamente</button>`,
            {onMount: () => {
              $('#mConfirmDel').onclick = async () => {
                try {
                  await apiPost('/api/edit/delete_lab', {lab: S.nome});
                  chiudiModal();
                  toast('Lab eliminato (backup salvato)');
                  S.nome = null; S.lab = null; $('#vista').hidden = true; $('#vuoto').hidden = false;
                  await caricaLabs();
                } catch (e) { modalErrore(e.message); }
              };
            }}
          );
        };
      }
    }
  );
}

function modalAddRouter() {
  apriModal(
    'Aggiungi Router',
    `<datalist id="mLanList">${lanDatalistHtml()}</datalist>
    <div class="fgrid">
      <div class="field"><label>Nome router (Kathará)</label><input id="arNome" value="${esc(prossimoNome('r'))}"></div>
      <div class="field"><label>Protocolli attivi</label>
        <div class="chkrow" style="margin-top:6px">
          <label><input type="checkbox" class="arP" value="bgp" checked> BGP</label>
          <label><input type="checkbox" class="arP" value="ospf"> OSPF</label>
          <label><input type="checkbox" class="arP" value="rip"> RIP</label>
          <label><input type="checkbox" class="arP" value="statico"> Statico</label>
        </div>
      </div>
      <div class="field" id="arAsnBox"><label>Numero AS (BGP)</label><input id="arAsn" placeholder="es. 10"></div>
      <div class="field" id="arOspfBox" hidden><label>Area OSPF</label><div class="riga" style="margin:0"><input id="arArea" value="0.0.0.0"><label class="small"><input type="checkbox" id="arStub"> Stub</label></div></div>
      <div class="field full">
        <label>Interfacce e LAN <span class="muted" style="font-weight:400">(trascina ⋮⋮ per riordinare eth0 / eth1 / … · selezionando una LAN esistente l'IP viene suggerito in automatico)</span></label>
        <div id="arIfaces" class="if-list"></div>
        <div><button type="button" class="small ghost" id="arAddIf">＋ Aggiungi interfaccia</button></div>
      </div>
      <div class="field"><label>Loopback opzionali (separate da virgola)</label><input id="arLo" placeholder="es. 1.1.1.1/32"></div>
      <div class="field"><label>Network IGP (vuoto = calcolo automatico)</label><input id="arIgpNets" placeholder="es. 10.0.0.0/8"></div>
      <div class="field"><label>Network BGP extra (oltre alle LAN)</label><input id="arBgpExtra" placeholder="es. 100.0.0.0/8"></div>
      <div class="field"><label>Opzioni BGP / IGP</label>
        <div class="chkrow" style="margin-top:6px">
          <label><input type="checkbox" id="arRed" checked> redistribute bgp in IGP</label>
          <label><input type="checkbox" id="arAutoNb" checked> auto-neighbor BGP su LAN comuni</label>
        </div>
      </div>
      <div class="field full" id="arStatBox" hidden>
        <label>Rotte statiche (una per riga: <code>destinazione next-hop [ethX]</code>, es. <code>0.0.0.0/0 10.0.0.2</code>)</label>
        <textarea id="arStat" rows="2"></textarea>
      </div>
    </div>`,
    `<button class="ghost" id="mCancel">Annulla</button><button id="arGo">Anteprima Diff →</button>`,
    {
      wide: true,
      onMount: box => {
        const ifList = creaListaInterfacceDnd($('#arIfaces'), {ipPlaceholder: 'IP/CIDR (es. 10.0.0.1/24)'});
        ifList.addRow('', '');
        $('#arAddIf').onclick = () => ifList.addRow('', '');
        function syncBoxes() {
          const ps = [...box.querySelectorAll('.arP:checked')].map(c => c.value);
          $('#arAsnBox').hidden = !ps.includes('bgp');
          $('#arOspfBox').hidden = !ps.includes('ospf');
          $('#arStatBox').hidden = !ps.includes('statico');
        }
        box.querySelectorAll('.arP').forEach(c => c.onchange = syncBoxes);
        syncBoxes();
        $('#arGo').onclick = () => {
          const protocols = [...box.querySelectorAll('.arP:checked')].map(c => c.value);
          const interfaces = ifList.getValues().map(x => ({lan: x.lan, ip: x.ip}));
          const loopbacks = $('#arLo').value.split(',').map(s => s.trim()).filter(Boolean);
          const static_routes = $('#arStat').value.split('\n').map(l => l.trim().split(/\s+/)).filter(a => a.length >= 2).map(a => ({dest: a[0], via: a[1], dev: a[2] || ''}));
          eseguiModifica('add_router', {
            nome: $('#arNome').value.trim(),
            protocols,
            asn: $('#arAsn').value.trim(),
            ospf_area: $('#arArea').value.trim() || '0.0.0.0',
            ospf_area_stub: $('#arStub').checked,
            interfaces,
            loopbacks,
            igp_networks: $('#arIgpNets').value.trim() || null,
            bgp_extra_networks: $('#arBgpExtra').value.trim() || null,
            igp_redistribute_bgp: $('#arRed').checked,
            auto_bgp_neighbors: $('#arAutoNb').checked,
            static_routes,
          });
        };
      }
    }
  );
}

function modalEditRouter(d) {
  const hasBgp = d.demoni.includes('bgpd');
  const hasOspf = d.demoni.includes('ospfd');
  const hasRip = d.demoni.includes('ripd');
  const hasStat = (d.static_routes && d.static_routes.length > 0) || (!hasBgp && !hasOspf && !hasRip);
  const igpList = (d.riepilogo && d.riepilogo.igp) || [];
  const ospfObj = igpList.find(g => g.protocollo === 'OSPF');
  const ripObj = igpList.find(g => g.protocollo === 'RIP');

  // Estrai area OSPF, stub e network IGP correnti
  let curArea = '0.0.0.0', curStub = false;
  const igpNetsSet = [];
  if (ospfObj) {
    for (const v of (ospfObj.voci || [])) {
      const ms = v.match(/^area\s+(\S+)\s+stub/i);
      if (ms) { curArea = ms[1]; curStub = true; continue; }
      const mn = v.match(/^(\S+)(?:\s+area\s+(\S+))?/);
      if (mn) {
        if (mn[2] && curArea === '0.0.0.0') curArea = mn[2];
        if (!igpNetsSet.includes(mn[1])) igpNetsSet.push(mn[1]);
      }
    }
  }
  if (ripObj) {
    for (const v of (ripObj.voci || [])) {
      const net = v.split(/\s+/)[0];
      if (net && !igpNetsSet.includes(net)) igpNetsSet.push(net);
    }
  }
  const curBgpNets = (d.riepilogo && d.riepilogo.bgp_networks) || [];
  const curRedBgp = igpList.some(g => (g.redistribute || []).some(r => r.startsWith('bgp')));
  const curStatText = (d.static_routes || []).map(r => [r.dest, r.via, r.dev].filter(Boolean).join(' ')).join('\n');

  apriModal(
    'Modifica Router — ' + d.nome,
    `<datalist id="mLanList">${lanDatalistHtml()}</datalist>
    <div class="finfo">Modifica protocolli, numero AS, interfacce/LAN (trascina ⋮⋮ per spostare tra <code>eth0, eth1…</code>), network IGP e network BGP annunciate. Le policy BGP esistenti vengono preservate e i riferimenti sugli altri dispositivi (<code>remote-as</code>, IP, neighbor, gateway) vengono aggiornati automaticamente.</div>
    <div class="fgrid">
      <div class="field"><label>Router</label><input value="${esc(d.nome)}" disabled></div>
      <div class="field"><label>Protocolli attivi</label>
        <div class="chkrow" style="margin-top:6px">
          <label><input type="checkbox" class="erP" value="bgp" ${hasBgp ? 'checked' : ''}> BGP</label>
          <label><input type="checkbox" class="erP" value="ospf" ${hasOspf ? 'checked' : ''}> OSPF</label>
          <label><input type="checkbox" class="erP" value="rip" ${hasRip ? 'checked' : ''}> RIP</label>
          <label><input type="checkbox" class="erP" value="statico" ${hasStat ? 'checked' : ''}> Statico</label>
        </div>
      </div>
      <div class="field" id="erAsnBox"><label>Numero AS (BGP)</label><input id="erAsn" value="${esc(d.asn || '')}" placeholder="es. 10"></div>
      <div class="field" id="erOspfBox" hidden><label>Area OSPF</label><div class="riga" style="margin:0"><input id="erArea" value="${esc(curArea)}"><label class="small"><input type="checkbox" id="erStub" ${curStub ? 'checked' : ''}> Stub</label></div></div>
      <div class="field full">
        <label>Interfacce e LAN <span class="muted" style="font-weight:400">(trascina ⋮⋮ per cambiare interfaccia eth0 / eth1 / …)</span></label>
        <div id="erIfaces" class="if-list"></div>
        <div><button type="button" class="small ghost" id="erAddIf">＋ Aggiungi interfaccia</button></div>
      </div>
      <div class="field"><label>Loopback (separate da virgola)</label><input id="erLo" value="${esc((d.loopback || []).join(', '))}" placeholder="es. 1.1.1.1/32"></div>
      <div class="field" id="erIgpBox"><label>Network IGP (OSPF/RIP, separate da virgola; vuoto = auto)</label><input id="erIgpNets" value="${esc(igpNetsSet.join(', '))}" placeholder="es. 10.0.0.0/8"></div>
      <div class="field" id="erBgpBox"><label>Network BGP annunciate (separate da virgola)</label><input id="erBgpNets" value="${esc(curBgpNets.join(', '))}" placeholder="es. 10.0.0.0/8, 100.0.0.0/24"></div>
      <div class="field"><label>Opzioni BGP / IGP</label>
        <div class="chkrow" style="margin-top:6px">
          <label><input type="checkbox" id="erRed" ${curRedBgp ? 'checked' : ''}> redistribute bgp in IGP</label>
          <label><input type="checkbox" id="erAutoNb" checked> auto-neighbor BGP su LAN comuni</label>
        </div>
      </div>
      <div class="field full" id="erStatBox" hidden>
        <label>Rotte statiche (una per riga: <code>destinazione next-hop [ethX]</code>, es. <code>0.0.0.0/0 10.0.0.2</code>)</label>
        <textarea id="erStat" rows="2">${esc(curStatText)}</textarea>
      </div>
    </div>`,
    `<button class="ghost" id="mCancel">Annulla</button><button id="erGo">Anteprima Diff →</button>`,
    {
      wide: true,
      onMount: box => {
        const ifList = creaListaInterfacceDnd($('#erIfaces'), {ipPlaceholder: 'IP/CIDR (es. 10.0.0.1/24)'});
        if (d.interfacce && d.interfacce.length) {
          for (const it of d.interfacce) ifList.addRow(it.lan, it.ip, it.dev);
        } else {
          ifList.addRow('', '');
        }
        $('#erAddIf').onclick = () => ifList.addRow('', '');
        function syncBoxes() {
          const ps = [...box.querySelectorAll('.erP:checked')].map(c => c.value);
          $('#erAsnBox').hidden = !ps.includes('bgp');
          $('#erBgpBox').hidden = !ps.includes('bgp');
          $('#erOspfBox').hidden = !ps.includes('ospf');
          $('#erIgpBox').hidden = !(ps.includes('ospf') || ps.includes('rip'));
          $('#erStatBox').hidden = !ps.includes('statico');
        }
        box.querySelectorAll('.erP').forEach(c => c.onchange = syncBoxes);
        syncBoxes();
        $('#erGo').onclick = () => {
          const protocols = [...box.querySelectorAll('.erP:checked')].map(c => c.value);
          const interfaces = ifList.getValues();
          const loopbacks = $('#erLo').value.split(',').map(s => s.trim()).filter(Boolean);
          const static_routes = $('#erStat').value.split('\n').map(l => l.trim().split(/\s+/)).filter(a => a.length >= 2).map(a => ({dest: a[0], via: a[1], dev: a[2] || ''}));
          eseguiModifica('edit_router', {
            nome: d.nome,
            protocols,
            asn: $('#erAsn').value.trim(),
            ospf_area: $('#erArea').value.trim() || '0.0.0.0',
            ospf_area_stub: $('#erStub').checked,
            interfaces,
            loopbacks,
            igp_networks: $('#erIgpNets').value.trim(),
            bgp_networks: $('#erBgpNets').value.trim(),
            igp_redistribute_bgp: $('#erRed').checked,
            auto_bgp_neighbors: $('#erAutoNb').checked,
            static_routes,
          });
        };
      }
    }
  );
}

function modalAddHost() {
  const dnsOpts = dnsLab().map(d => { const ip = (d.interfacce[0] || {}).ip || ''; return `<option value="${esc(ip.split('/')[0])}">${esc(d.nome + ' (' + ip.split('/')[0] + ')')}</option>`; }).join('');
  apriModal(
    'Aggiungi Host / PC',
    `<datalist id="mLanList">${lanDatalistHtml()}</datalist><datalist id="mDnsList">${dnsOpts}</datalist>
    <div class="fgrid">
      <div class="field"><label>Nome host (Kathará)</label><input id="ahNome" value="${esc(prossimoNome('pc'))}"></div>
      <div class="field"><label>Resolver DNS opzionale (resolv.conf)</label><input id="ahRes" list="mDnsList" placeholder="IP nameserver (opzionale)"></div>
      <div class="field full">
        <label>Interfacce e LAN <span class="muted" style="font-weight:400">(trascina ⋮⋮ per riordinare · IP suggerito in automatico su LAN esistente)</span></label>
        <div id="ahIfaces" class="if-list"></div>
        <div><button type="button" class="small ghost" id="ahAddIf">＋ Aggiungi interfaccia</button></div>
      </div>
      <div class="field full"><label>Default Gateway</label>
        <div class="riga" style="margin:0"><input id="ahGw" placeholder="es. 10.0.0.1" style="flex:1"><select id="ahGwPick" style="max-width:220px"><option value="">— scegli router su LAN —</option></select></div>
      </div>
    </div>`,
    `<button class="ghost" id="mCancel">Annulla</button><button id="ahGo">Anteprima Diff →</button>`,
    {
      onMount: () => {
        function aggiornaGwPick() {
          const lans = [...$('#ahIfaces').querySelectorAll('.ifLan')].map(i => i.value.trim()).filter(Boolean);
          const rs = lans.flatMap(l => routerSuLan(l));
          $('#ahGwPick').innerHTML = '<option value="">— scegli router su LAN —</option>' + rs.map(r => `<option value="${esc(r.ip)}">${esc(r.ip + ' (' + r.nome + ')')}</option>`).join('');
          if (rs.length && !$('#ahGw').value) $('#ahGw').value = rs[0].ip;
        }
        $('#ahGwPick').onchange = () => { if ($('#ahGwPick').value) $('#ahGw').value = $('#ahGwPick').value; };
        const ifList = creaListaInterfacceDnd($('#ahIfaces'), {
          ipPlaceholder: 'IP/CIDR (es. 10.0.0.10/24)',
          onLanInput: aggiornaGwPick,
          onChange: aggiornaGwPick,
        });
        ifList.addRow('', '');
        $('#ahAddIf').onclick = () => ifList.addRow('', '');
        $('#ahGo').onclick = () => {
          const interfaces = ifList.getValues().map(x => ({lan: x.lan, ip: x.ip}));
          eseguiModifica('add_host', {nome: $('#ahNome').value.trim(), interfaces, gateway: $('#ahGw').value.trim(), resolver: $('#ahRes').value.trim()});
        };
      }
    }
  );
}

function modalAddWww() {
  apriModal(
    'Aggiungi Server WWW (Apache2)',
    `<datalist id="mLanList">${lanDatalistHtml()}</datalist>
    <div class="fgrid">
      <div class="field"><label>Nome server</label><input id="awNome" value="${esc(prossimoNome('www'))}"></div>
      <div class="field"><label>LAN</label><input id="awLan" list="mLanList" placeholder="es. A"></div>
      <div class="field"><label>IP/CIDR</label><div class="riga" style="margin:0"><input id="awIp" placeholder="es. 10.0.0.80/24" style="flex:1"><button type="button" class="small ghost" id="awSug">Suggerisci IP</button></div></div>
      <div class="field"><label>Default Gateway</label><input id="awGw" placeholder="es. 10.0.0.1"></div>
    </div>`,
    `<button class="ghost" id="mCancel">Annulla</button><button id="awGo">Anteprima Diff →</button>`,
    {
      onMount: () => {
        collegaAutoSuggerisciLan($('#awLan'), $('#awIp'), null, val => {
          const rs = routerSuLan(val); if (rs.length && !$('#awGw').value) $('#awGw').value = rs[0].ip;
        });
        $('#awSug').onclick = () => suggerisciIp($('#awLan').value, $('#awIp'));
        $('#awGo').onclick = () => eseguiModifica('add_www', {nome: $('#awNome').value.trim(), lan: $('#awLan').value.trim(), ip: $('#awIp').value.trim(), gateway: $('#awGw').value.trim()});
      }
    }
  );
}

function modalAddDns() {
  const hasRoot = dnsLab().some(d => d.is_dns_root);
  const nonDns = S.lab.dispositivi.filter(d => d.tipo !== 'dns');
  apriModal(
    'Aggiungi Server DNS (BIND9)',
    `<datalist id="mLanList">${lanDatalistHtml()}</datalist>
    <div class="fgrid">
      <div class="field"><label>Nome server DNS</label><input id="adNome" value="${hasRoot ? esc(prossimoNome('dns')) : 'root'}"></div>
      <div class="field"><label>Ruolo zona "."</label>
        <select id="adRole">
          <option value="master" ${hasRoot ? '' : 'selected'}>Root server (master per ".")</option>
          <option value="hint" ${hasRoot ? 'selected' : ''}>Server autoritativo / resolver (hint verso root)</option>
          <option value="none">Nessuna zona "."</option>
        </select>
      </div>
      <div class="field"><label>LAN</label><input id="adLan" list="mLanList" placeholder="es. A"></div>
      <div class="field"><label>IP/CIDR</label><div class="riga" style="margin:0"><input id="adIp" placeholder="es. 10.0.0.53/24" style="flex:1"><button type="button" class="small ghost" id="adSug">Suggerisci IP</button></div></div>
      <div class="field"><label>Default Gateway</label><input id="adGw" placeholder="es. 10.0.0.1"></div>
      <div class="field" id="adRootIpBox"><label>IP Root server (se hint; vuoto = rileva root nel lab)</label><input id="adRootIp" placeholder="auto"></div>
      <div class="field"><label>allow-recursion (opzionale)</label><input id="adRec" placeholder="es. any  oppure  10.0.0.0/8"></div>
      <div class="field"><label>DNSSEC</label><label style="margin-top:6px"><input type="checkbox" id="adDnssec" checked> dnssec-validation no</label></div>
      <div class="field full" id="adDelBox">
        <label>Deleghe sul root (una per riga: <code>zona nameserver ip</code>, es. <code>com dns.com 20.0.0.3</code>)</label>
        <textarea id="adDel" rows="3"></textarea>
      </div>
      <div class="field full" id="adZoneBox">
        <label>Zona autoritativa opzionale (es. <code>uniroma3.it</code>)</label>
        <input id="adZoneName" placeholder="lascia vuoto se solo resolver">
        <label style="margin-top:6px">Record della zona (uno per riga: <code>nome TIPO valore [glue_ip]</code> — es. <code>www A 10.0.0.80</code>)</label>
        <textarea id="adZoneRecs" rows="3"></textarea>
      </div>
      ${nonDns.length ? `<div class="field full"><label>Imposta questo DNS come resolver (/etc/resolv.conf) su:</label>
        <div class="chkrow">${nonDns.map(d => `<label><input type="checkbox" class="adResTarget" value="${esc(d.nome)}"> ${esc(d.nome)}</label>`).join('')}</div></div>` : ''}
    </div>`,
    `<button class="ghost" id="mCancel">Annulla</button><button id="adGo">Anteprima Diff →</button>`,
    {
      wide: true,
      onMount: box => {
        function syncRole() {
          const r = $('#adRole').value;
          $('#adDelBox').hidden = r !== 'master';
          $('#adRootIpBox').hidden = r !== 'hint';
        }
        $('#adRole').onchange = syncRole; syncRole();
        collegaAutoSuggerisciLan($('#adLan'), $('#adIp'), null, val => {
          const rs = routerSuLan(val); if (rs.length && !$('#adGw').value) $('#adGw').value = rs[0].ip;
        });
        $('#adSug').onclick = () => suggerisciIp($('#adLan').value, $('#adIp'));
        $('#adGo').onclick = () => {
          const delegations = $('#adDel').value.split('\n').map(l => l.trim().split(/\s+/)).filter(a => a.length >= 2).map(a => ({zone: a[0], ns: a[1], ip: a[2] || ''}));
          const zname = $('#adZoneName').value.trim();
          const zones = [];
          if (zname) {
            const records = $('#adZoneRecs').value.split('\n').map(l => l.trim().split(/\s+/)).filter(a => a.length >= 3).map(a => ({name: a[0], type: a[1], value: a[2], extra: a[3] || ''}));
            zones.push({zone: zname, records});
          }
          const set_as_resolver_for = [...box.querySelectorAll('.adResTarget:checked')].map(c => c.value);
          eseguiModifica('add_dns', {
            nome: $('#adNome').value.trim(), lan: $('#adLan').value.trim(), ip: $('#adIp').value.trim(), gateway: $('#adGw').value.trim(),
            root_type: $('#adRole').value, root_server_ip: $('#adRootIp').value.trim(), allow_recursion: $('#adRec').value.trim(),
            dnssec_validation: $('#adDnssec').checked, delegations, zones, set_as_resolver_for,
          });
        };
      }
    }
  );
}

function modalInterfacce(d) {
  const origOrder = (d.interfacce || []).map(it => it.dev);
  apriModal(
    'Interfacce di ' + d.nome,
    `<datalist id="mLanList">${lanDatalistHtml()}</datalist>
    <div class="fhelp" style="margin-bottom:6px">Trascina una riga tramite <b>⋮⋮</b> per spostare una LAN su un'altra interfaccia (<code>eth0 · LAN 0</code>, <code>eth1 · LAN 1</code>, …). L'ordine verrà aggiornato in <code>lab.conf</code>, <code>.startup</code> e <code>frr.conf</code>.</div>
    <div id="exIfList" class="if-list">
      ${(d.interfacce || []).map((it, idx) => `<div class="if-card" draggable="true" data-orig="${esc(it.dev)}">
        <span class="if-handle" title="Trascina per riordinare le interfacce">⋮⋮</span>
        <span class="if-badge">eth${idx} · LAN ${idx}</span>
        <span class="badge" style="font-weight:700">LAN ${esc(it.lan)}</span>
        <code style="flex:1;min-width:120px">${esc(it.ip || '(senza IP)')}</code>
        <span class="muted small if-orig-note"></span>
        <div class="btns" style="margin:0">
          <button type="button" class="small ghost" data-eip="${esc(it.dev)}">Cambia IP</button>
          <button type="button" class="small ghost" data-mov="${esc(it.dev)}">Sposta LAN</button>
          <button type="button" class="small danger" data-rem="${esc(it.dev)}">✕ Rimuovi</button>
        </div>
      </div>`).join('') || '<div class="muted">Nessuna interfaccia</div>'}
    </div>
    <div id="ifReorderBar" class="if-reorder-bar" hidden>
      <span><b>Ordine modificato:</b> le LAN sono state riassegnate alle nuove interfacce.</span>
      <div class="sp"></div>
      <button type="button" class="small ghost" id="ifReordReset">Ripristina</button>
      <button type="button" class="small" id="ifReordSave">Salva ordine (Anteprima Diff →)</button>
    </div>
    <div id="ifAction" style="margin-top:12px"></div>
    <div class="card" style="margin-top:12px;margin-bottom:0">
      <h3>＋ Aggiungi nuova interfaccia</h3>
      <div class="fgrid">
        <div class="field"><label>LAN (esistente o nuova)</label><input id="niLan" list="mLanList" placeholder="es. B"></div>
        <div class="field"><label>IP/CIDR</label><div class="riga" style="margin:0"><input id="niIp" placeholder="es. 10.1.0.1/24" style="flex:1"><button type="button" class="small ghost" id="niSug">Suggerisci IP</button></div></div>
      </div>
      ${d.tipo === 'router' ? `<div class="chkrow" style="margin-top:8px">
        ${d.demoni.includes('bgpd') ? '<label><input type="checkbox" id="niBgp" checked> Annuncia in BGP</label><label><input type="checkbox" id="niNb" checked> Crea neighbor BGP su LAN</label>' : ''}
        ${(d.demoni.includes('ospfd') || d.demoni.includes('ripd')) ? '<label><input type="checkbox" id="niIgp"> Annuncia in IGP</label>' : ''}
      </div>` : ''}
      <div class="riga"><button class="small" id="niAdd">Aggiungi interfaccia (Anteprima →)</button></div>
    </div>`,
    `<button class="ghost" id="mCancel">Chiudi</button>`,
    {
      wide: true,
      onMount: box => {
        const listEl = $('#exIfList');
        let dragSrc = null;
        function syncOrderUi() {
          const cards = [...listEl.querySelectorAll('.if-card')];
          const curOrder = cards.map(c => c.dataset.orig);
          const changed = curOrder.some((v, i) => v !== origOrder[i]);
          cards.forEach((c, i) => {
            c.querySelector('.if-badge').textContent = `eth${i} · LAN ${i}`;
            const note = c.querySelector('.if-orig-note');
            note.textContent = c.dataset.orig !== `eth${i}` ? `(era ${c.dataset.orig})` : '';
          });
          $('#ifReorderBar').hidden = !changed;
        }
        listEl.querySelectorAll('.if-card').forEach(card => {
          card.addEventListener('dragstart', e => {
            if (e.target.closest('button')) { e.preventDefault(); return; }
            dragSrc = card;
            card.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
            try { e.dataTransfer.setData('text/plain', card.dataset.orig); } catch (_) {}
          });
          card.addEventListener('dragover', e => {
            if (!dragSrc || dragSrc === card) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            listEl.querySelectorAll('.if-card').forEach(x => x.classList.remove('drag-over'));
            card.classList.add('drag-over');
          });
          card.addEventListener('dragleave', () => card.classList.remove('drag-over'));
          card.addEventListener('drop', e => {
            e.preventDefault();
            card.classList.remove('drag-over');
            if (!dragSrc || dragSrc === card) return;
            const cards = [...listEl.querySelectorAll('.if-card')];
            if (cards.indexOf(dragSrc) < cards.indexOf(card)) card.after(dragSrc);
            else card.before(dragSrc);
            syncOrderUi();
          });
          card.addEventListener('dragend', () => {
            if (dragSrc) dragSrc.classList.remove('dragging');
            listEl.querySelectorAll('.if-card').forEach(x => x.classList.remove('drag-over'));
            dragSrc = null;
          });
        });
        $('#ifReordReset').onclick = () => {
          for (const devName of origOrder) {
            const c = listEl.querySelector(`.if-card[data-orig="${CSS.escape(devName)}"]`);
            if (c) listEl.appendChild(c);
          }
          syncOrderUi();
        };
        $('#ifReordSave').onclick = () => {
          const order = [...listEl.querySelectorAll('.if-card')].map(c => c.dataset.orig);
          eseguiModifica('reorder_interfaces', {nome: d.nome, order});
        };

        collegaAutoSuggerisciLan($('#niLan'), $('#niIp'));
        $('#niSug').onclick = () => suggerisciIp($('#niLan').value, $('#niIp'));
        $('#niAdd').onclick = () => eseguiModifica('add_interface', {
          nome: d.nome, lan: $('#niLan').value.trim(), ip: $('#niIp').value.trim(),
          announce_bgp: !!($('#niBgp') && $('#niBgp').checked),
          auto_bgp_neighbors: !!($('#niNb') && $('#niNb').checked),
          announce_igp: !!($('#niIgp') && $('#niIgp').checked),
        });
        box.onclick = e => {
          const bIp = e.target.closest('[data-eip]');
          if (bIp) {
            const it = d.interfacce.find(x => x.dev === bIp.dataset.eip);
            const altri = (it.vicini || []).length;
            $('#ifAction').innerHTML = `<div class="card" style="margin:0"><h3>Cambia IP di ${esc(d.nome)} ${esc(it.dev)} (LAN ${esc(it.lan)})</h3>
              <div class="fhelp">L'IP verrà aggiornato automaticamente in tutti i file del lab (startup, frr.conf, annunci BGP/IGP, neighbor BGP, gateway, DNS).</div>
              <div class="fgrid" style="margin-top:8px">
                <div class="field"><label>Nuovo IP/CIDR (attuale: ${esc(it.ip || '-')})</label><input id="ciVal" value="${esc(it.ip || '')}"></div>
                ${altri ? `<div class="field"><label>Se cambi subnet (ci sono altri ${altri} nodi su LAN ${esc(it.lan)})</label>
                  <select id="ciMode"><option value="lan">Rinumera tutta la LAN ${esc(it.lan)} (consigliato)</option><option value="single">Cambia solo questo IP</option></select></div>` : ''}
              </div>
              <div class="riga"><button class="small" id="ciGo">Anteprima Diff →</button></div></div>`;
            $('#ciGo').onclick = () => eseguiModifica('edit_interface_ip', {nome: d.nome, dev: it.dev, new_ip: $('#ciVal').value.trim(), mode: $('#ciMode') ? $('#ciMode').value : 'single'});
            return;
          }
          const bMov = e.target.closest('[data-mov]');
          if (bMov) {
            const it = d.interfacce.find(x => x.dev === bMov.dataset.mov);
            $('#ifAction').innerHTML = `<div class="card" style="margin:0"><h3>Sposta ${esc(d.nome)} ${esc(it.dev)} su un'altra LAN</h3>
              <div class="fgrid">
                <div class="field"><label>Nuova LAN (ora ${esc(it.lan)})</label><input id="mvLan" list="mLanList" placeholder="es. C"></div>
                <div class="field"><label>Nuovo IP/CIDR (suggerito automaticamente su LAN esistente)</label><div class="riga" style="margin:0"><input id="mvIp" placeholder="lascia vuoto per tenere ${esc(it.ip || '-')}" style="flex:1"><button type="button" class="small ghost" id="mvSug">Suggerisci IP</button></div></div>
              </div>
              <div class="riga"><button class="small" id="mvGo">Anteprima Diff →</button></div></div>`;
            collegaAutoSuggerisciLan($('#mvLan'), $('#mvIp'));
            $('#mvSug').onclick = () => suggerisciIp($('#mvLan').value, $('#mvIp'));
            $('#mvGo').onclick = () => eseguiModifica('move_interface', {nome: d.nome, dev: it.dev, new_lan: $('#mvLan').value.trim(), new_ip: $('#mvIp').value.trim()});
            return;
          }
          const bRem = e.target.closest('[data-rem]');
          if (bRem) {
            eseguiModifica('remove_interface', {nome: d.nome, dev: bRem.dataset.rem});
          }
        };
      }
    }
  );
}

function modalRinumeraLan(lanNome) {
  const l = (S.lab.lan || []).find(z => z.nome === lanNome);
  if (!l) return;
  const membri = [];
  for (const d of S.lab.dispositivi) for (const it of d.interfacce) if (it.lan === lanNome) membri.push({dev: d.nome, iface: it.dev, ip: it.ip});
  apriModal(
    'Rinumera rete della LAN ' + lanNome,
    `<div class="finfo">Subnet attuale: <code>${esc(l.subnet || 'non definita')}</code> · Membri: ${membri.map(m => `<b>${esc(m.dev)}</b> (${esc(m.ip)})`).join(', ')}.<br>
      Ogni dispositivo manterrà la stessa parte host quando possibile, e tutti i riferimenti nel lab (neighbor BGP, gateway, DNS) verranno aggiornati automaticamente.</div>
    <div class="fgrid one">
      <div class="field"><label>Nuova rete CIDR della LAN ${esc(lanNome)}</label><input id="rlNet" placeholder="es. 10.0.5.0/24" value="${esc(l.subnet || '')}"></div>
    </div>
    <details style="margin-top:8px"><summary>Override IP specifici per singolo membro (facoltativo)</summary>
      <div class="fgrid" style="margin-top:8px">
        ${membri.map(m => `<div class="field"><label>${esc(m.dev + ' ' + m.iface)} (era ${esc(m.ip)})</label><input class="rlOv" data-k="${esc(m.dev + ':' + m.iface)}" placeholder="auto"></div>`).join('')}
      </div>
    </details>`,
    `<button class="ghost" id="mCancel">Annulla</button><button id="rlGo">Anteprima Diff →</button>`,
    {
      onMount: box => {
        $('#rlGo').onclick = () => {
          const fixed = {};
          box.querySelectorAll('.rlOv').forEach(i => { if (i.value.trim()) fixed[i.dataset.k] = i.value.trim(); });
          eseguiModifica('renumber_lan', {lan: lanNome, new_network: $('#rlNet').value.trim(), fixed});
        };
      }
    }
  );
}

function modalCollegaAllaLan(lanNome) {
  const l = (S.lab.lan || []).find(z => z.nome === lanNome);
  const cand = S.lab.dispositivi;
  apriModal(
    'Collega un dispositivo alla LAN ' + lanNome,
    `<div class="finfo">LAN <b>${esc(lanNome)}</b> (${esc((l && l.subnet) || 'nessuna subnet')}). Verrà creata automaticamente la prossima interfaccia <code>ethN</code> libera.</div>
    <div class="fgrid">
      <div class="field"><label>Dispositivo</label><select id="clDev">${cand.map(d => `<option value="${esc(d.nome)}">${esc(d.nome + ' (' + d.tipo + ')')}</option>`).join('')}</select></div>
      <div class="field"><label>IP/CIDR sulla LAN ${esc(lanNome)}</label><div class="riga" style="margin:0"><input id="clIp" placeholder="es. 10.0.0.5/24" style="flex:1"><button type="button" class="small ghost" id="clSug">Suggerisci</button></div></div>
      <div class="field full"><div class="chkrow"><label><input type="checkbox" id="clBgp" checked> Se router BGP: annuncia rete e crea neighbor BGP sulla LAN</label></div></div>
    </div>`,
    `<button class="ghost" id="mCancel">Annulla</button><button id="clGo">Anteprima Diff →</button>`,
    {
      onMount: () => {
        suggerisciIp(lanNome, $('#clIp'));
        $('#clSug').onclick = () => suggerisciIp(lanNome, $('#clIp'));
        $('#clGo').onclick = () => eseguiModifica('add_interface', {
          nome: $('#clDev').value, lan: lanNome, ip: $('#clIp').value.trim(),
          announce_bgp: $('#clBgp').checked, auto_bgp_neighbors: $('#clBgp').checked,
        });
      }
    }
  );
}

function modalGateway(d) {
  const cands = [];
  for (const it of d.interfacce) for (const r of routerSuLan(it.lan)) cands.push(Object.assign({dev: it.dev, lan: it.lan}, r));
  apriModal(
    'Default Gateway di ' + d.nome,
    `<div class="finfo">Gateway attuale: <code>${esc(d.gateway || 'nessuno')}</code></div>
    <div class="fgrid one">
      ${cands.length ? `<div class="field"><label>Router sulle LAN di ${esc(d.nome)}</label><select id="gwPick"><option value="">— inserimento manuale —</option>${cands.map(c => `<option value="${esc(c.ip)}" data-dev="${esc(c.dev)}">${esc(c.ip + ' (' + c.nome + ', via ' + c.dev + ' / LAN ' + c.lan + ')')}</option>`).join('')}</select></div>` : ''}
      <div class="field"><label>IP Default Gateway (lascia vuoto per rimuoverlo)</label><input id="gwVal" value="${esc(d.gateway || '')}" placeholder="es. 10.0.0.1"></div>
    </div>`,
    `<button class="ghost" id="mCancel">Annulla</button><button id="gwGo">Anteprima Diff →</button>`,
    {
      onMount: () => {
        const pk = $('#gwPick');
        if (pk) pk.onchange = () => { if (pk.value) $('#gwVal').value = pk.value; };
        $('#gwGo').onclick = () => eseguiModifica('change_gateway', {nome: d.nome, gateway: $('#gwVal').value.trim()});
      }
    }
  );
}

function modalCambiaAs(d) {
  apriModal(
    'Cambia numero AS di ' + d.nome,
    `<div class="finfo">AS attuale: <b>AS${esc(d.asn)}</b>. Cambiandolo, verrà aggiornato automaticamente anche <code>remote-as</code> su tutti i router neighbor che puntano a <b>${esc(d.nome)}</b>.</div>
    <div class="fgrid one"><div class="field"><label>Nuovo numero AS</label><input id="asVal" placeholder="es. 30"></div></div>`,
    `<button class="ghost" id="mCancel">Annulla</button><button id="asGo">Anteprima Diff →</button>`,
    {onMount: () => { $('#asGo').onclick = () => eseguiModifica('change_as', {nome: d.nome, new_as: $('#asVal').value.trim()}); }}
  );
}

function modalProtocolli(d) {
  const attivi = ['bgp', 'ospf', 'rip'].filter(p => d.demoni.includes(p + 'd'));
  const mancanti = ['bgp', 'ospf', 'rip'].filter(p => !attivi.includes(p));
  apriModal(
    'Protocolli di ' + d.nome,
    `<div class="finfo">Attualmente attivi: <b>${esc(attivi.map(x => x.toUpperCase()).join(', ') || 'nessuno')}</b></div>
    <div class="fgrid">
      <div class="field"><label>Azione</label><select id="prAct">
        ${mancanti.length ? '<option value="add">Attiva un protocollo</option>' : ''}
        ${attivi.length ? '<option value="remove">Disattiva un protocollo</option>' : ''}
      </select></div>
      <div class="field"><label>Protocollo</label><select id="prProto"></select></div>
    </div>
    <div id="prExtra" style="margin-top:10px"></div>`,
    `<button class="ghost" id="mCancel">Annulla</button><button id="prGo">Anteprima Diff →</button>`,
    {
      onMount: () => {
        function aggiornaProto() {
          const act = $('#prAct').value, list = act === 'add' ? mancanti : attivi;
          $('#prProto').innerHTML = list.map(p => `<option value="${p}">${p.toUpperCase()}</option>`).join('');
          aggiornaExtra();
        }
        function aggiornaExtra() {
          const act = $('#prAct').value, p = $('#prProto').value, ex = $('#prExtra');
          if (act === 'remove') {
            ex.innerHTML = p === 'bgp'
              ? '<div class="chkrow"><label><input type="checkbox" id="prCleanNb" checked> Rimuovi anche le righe neighbor verso ' + esc(d.nome) + ' sugli altri router</label></div>'
              : '<div class="fhelp">Rimuove il blocco <code>router ' + p + '</code> e disattiva <code>' + p + 'd=no</code> in daemons.</div>';
            return;
          }
          if (p === 'bgp') {
            ex.innerHTML = `<div class="fgrid">
              <div class="field"><label>Numero AS</label><input id="prAsn" value="${esc(d.asn || '')}" placeholder="es. 10"></div>
              <div class="field"><label>Network BGP (vuoto = reti delle interfacce)</label><input id="prNets" placeholder="auto"></div>
              <div class="field full"><div class="chkrow">
                <label><input type="checkbox" id="prAutoNb" checked> Crea sessioni BGP con vicini sulle stesse LAN</label>
                <label><input type="checkbox" id="prRed" checked> Aggiungi redistribute bgp in OSPF/RIP</label>
              </div></div></div>`;
          } else {
            ex.innerHTML = `<div class="fgrid">
              <div class="field"><label>Network ${p.toUpperCase()} (vuoto = calcolo automatico)</label><input id="prNets" placeholder="auto"></div>
              ${p === 'ospf' ? '<div class="field"><label>Area OSPF</label><div class="riga" style="margin:0"><input id="prArea" value="0.0.0.0"><label class="small"><input type="checkbox" id="prStub"> Stub</label></div></div>' : ''}
              ${attivi.includes('bgp') ? '<div class="field full"><label><input type="checkbox" id="prRed" checked> Aggiungi redistribute bgp</label></div>' : ''}
            </div>`;
          }
        }
        $('#prAct').onchange = aggiornaProto;
        $('#prProto').onchange = aggiornaExtra;
        aggiornaProto();
        $('#prGo').onclick = () => {
          const act = $('#prAct').value, p = $('#prProto').value;
          const params = {nome: d.nome, action: act, protocol: p};
          if (act === 'add') {
            if ($('#prAsn')) params.asn = $('#prAsn').value.trim();
            if ($('#prNets') && $('#prNets').value.trim()) params.networks = $('#prNets').value.trim();
            if ($('#prArea')) params.ospf_area = $('#prArea').value.trim() || '0.0.0.0';
            if ($('#prStub')) params.ospf_area_stub = $('#prStub').checked;
            if ($('#prRed')) params.redistribute_bgp = $('#prRed').checked;
            if ($('#prAutoNb')) params.auto_bgp_neighbors = $('#prAutoNb').checked;
          } else if ($('#prCleanNb')) {
            params.clean_remote_neighbors = $('#prCleanNb').checked;
          }
          eseguiModifica('manage_protocols', params);
        };
      }
    }
  );
}

function modalBgpPolicy(d, pre) {
  pre = pre || {};
  const neighs = (d.riepilogo && d.riepilogo.neighbor) || [];
  const bgpNets = (d.riepilogo && d.riepilogo.bgp_networks) || [];
  const altriRouter = routerLab().filter(r => r.nome !== d.nome && r.demoni.includes('bgpd'));
  const nbOpts = neighs.map(n => `<option value="${esc(n.ip)}">${esc(n.ip + ' — ' + n.chi + ' (AS' + n.asn + ', ' + n.tipo + ')')}</option>`).join('');

  apriModal(
    'Policy BGP su ' + d.nome + (d.asn ? ' (AS' + d.asn + ')' : ''),
    `<div class="mtabs" id="bpTabs">
      <button data-k="prefix_list" class="on">1. Prefix-list (deny)</button>
      <button data-k="local_pref">2. Local-Pref (in)</button>
      <button data-k="med">3. MED (out)</button>
      <button data-k="access_list">4. Access-list (in)</button>
      <button data-k="cpp">5. Customer / Provider / Peer</button>
      <button data-k="default_originate">6. Default-originate</button>
    </div>
    <div id="bpBody"></div>`,
    `<button class="ghost" id="mCancel">Annulla</button><button id="bpGo">Anteprima Diff →</button>`,
    {
      wide: true,
      onMount: () => {
        let kind = 'prefix_list';
        function nbSelectorHtml() {
          return `<div class="field"><label>Neighbor BGP esistente o nuovo IP</label>
              <div class="riga" style="margin:0">
                <select id="bpNbSel" style="flex:1"><option value="">— IP manuale —</option>${nbOpts}</select>
                <input id="bpNbIp" value="${esc(pre.neighbor_ip || (neighs[0] ? neighs[0].ip : ''))}" placeholder="es. 10.20.0.2" style="width:160px">
              </div>
            </div>
            <div class="field"><label>ASN del neighbor (solo se è un nuovo neighbor non ancora configurato)</label>
              <input id="bpNbAsn" value="${esc(pre.neighbor_asn || '')}" placeholder="lascia vuoto se esiste già"></div>`;
        }
        function renderKind() {
          const b = $('#bpBody');
          if (kind === 'prefix_list') {
            b.innerHTML = `<div class="finfo"><b>Scarta una o più reti</b> con <code>deny ...</code> + <code>permit any</code>.<br>
              <b>IN</b> = blocca rotte <i>ricevute</i> dal neighbor · <b>OUT</b> = blocca rotte <i>annunciate</i> al neighbor.</div>
              <div class="fgrid">${nbSelectorHtml()}
                <div class="field"><label>Direzione</label><select id="bpDir"><option value="in">IN (rotte ricevute dal neighbor)</option><option value="out">OUT (rotte annunciate al neighbor)</option></select></div>
                <div class="field"><label>Reti da bloccare (DENY, separate da virgola)</label><input id="bpNets" placeholder="es. 100.1.0.0/24, 100.2.0.0/24"></div>
              </div>`;
          } else if (kind === 'local_pref') {
            b.innerHTML = `<div class="finfo"><b>Scegli da dove USCIRE</b> (direzione <b>IN</b> sul neighbor da preferire; default = 100, valore più alto vince su tutto l'AS).</div>
              <div class="fgrid">${nbSelectorHtml()}
                <div class="field"><label>Valore local-preference (es. 150 per preferire, 50 per sfavorire)</label><input id="bpVal" type="number" min="0" value="150"></div>
                <div class="field"><label>Solo per queste reti (lascia vuoto = tutte le rotte)</label><input id="bpNets" placeholder="es. 100.1.0.0/24, 100.2.0.0/24"></div>
              </div>`;
          } else if (kind === 'med') {
            b.innerHTML = `<div class="finfo"><b>Suggerisci all'AS vicino da dove ENTRARE</b> (direzione <b>OUT</b> sul link da evitare; default = 0, MED più basso vince).</div>
              <div class="fgrid">${nbSelectorHtml()}
                <div class="field"><label>Valore metric (MED, es. 20 sul link da evitare)</label><input id="bpVal" type="number" min="0" value="20"></div>
              </div>`;
          } else if (kind === 'access_list') {
            b.innerHTML = `<div class="finfo"><b>Scarta una o più reti in ingresso (IN)</b> tramite <code>access-list</code> + <code>route-map</code>. Nota: FRR usa una sola route-map per direzione sul neighbor.</div>
              <div class="fgrid">${nbSelectorHtml()}
                <div class="field full"><label>Reti da bloccare in ingresso (separate da virgola)</label><input id="bpNets" placeholder="es. 30.0.0.0/8"></div>
              </div>`;
          } else if (kind === 'cpp') {
            b.innerHTML = `<div class="finfo"><b>Relazione Customer / Provider / Peer</b>:<br>
              • <b>Provider</b> o <b>Peer</b>: accetta tutto in ingresso (<code>in</code>), annuncia in uscita (<code>out</code>) solo le TUE reti e quelle dei tuoi CLIENTI.<br>
              • <b>Customer</b>: accetta tutto (<code>in</code>) e annuncia tutto (<code>out</code>).<br>
              ${bgpNets.length ? `Reti attualmente annunciate da <b>${esc(d.nome)}</b>: <code>${esc(bgpNets.join(', '))}</code>` : ''}</div>
              <div class="fgrid">
                <div class="field"><label>Router vicino (precompila IP e ASN)</label>
                  <select id="cppR"><option value="">— inserimento manuale —</option>${altriRouter.map(r => {
                    const ips = r.interfacce.filter(i => i.ip).map(i => i.ip.split('/')[0]);
                    return `<option value="${esc(r.nome)}" data-asn="${esc(r.asn||'')}" data-ips="${esc(ips.join(','))}">${esc(r.nome + ' (AS' + (r.asn||'?') + ')')}</option>`;
                  }).join('')}</select>
                </div>
                <div class="field"><label>IP del vicino verso ${esc(d.nome)}</label><input id="cppIp" value="${esc(pre.neighbor_ip || '')}" placeholder="es. 10.20.0.20"></div>
                <div class="field"><label>Nome vicino (per il nome prefix-list)</label><input id="cppName" value="${esc(pre.neighbor_name || '')}" placeholder="es. as20r1"></div>
                <div class="field"><label>ASN del vicino (se neighbor nuovo)</label><input id="cppAsn" value="${esc(pre.neighbor_asn || '')}" placeholder="es. 20"></div>
                <div class="field full"><label>Relazione economica (il vicino è il mio…)</label>
                  <select id="cppRel"><option value="provider">PROVIDER (il vicino è il mio provider)</option><option value="customer">CUSTOMER (il vicino è il mio cliente)</option><option value="peer">PEER (siamo alla pari)</option></select>
                </div>
                <div class="field" id="cppOwnBox"><label>Le TUE reti da annunciare (separate da virgola)</label><input id="cppOwn" value="${esc(bgpNets.join(', '))}" placeholder="es. 10.0.0.0/8"></div>
                <div class="field" id="cppCustBox"><label>Reti dei tuoi CLIENTI (vuoto = nessuna)</label><input id="cppCust" placeholder="es. 30.0.0.0/8"></div>
              </div>`;
            $('#cppR').onchange = () => {
              const opt = $('#cppR').selectedOptions[0];
              if (!opt || !opt.value) return;
              $('#cppName').value = opt.value;
              $('#cppAsn').value = opt.dataset.asn || '';
              const ips = (opt.dataset.ips || '').split(',').filter(Boolean);
              const match = ips.find(ip => neighs.some(n => n.ip === ip)) || ips[0] || '';
              if (match) $('#cppIp').value = match;
            };
            $('#cppRel').onchange = () => {
              const cust = $('#cppRel').value === 'customer';
              $('#cppOwnBox').hidden = cust; $('#cppCustBox').hidden = cust;
            };
          } else if (kind === 'default_originate') {
            b.innerHTML = `<div class="finfo">Invia la default route (<code>neighbor X default-originate</code>) ai neighbor selezionati.</div>
              ${neighs.length ? `<div class="field"><label>Seleziona i neighbor BGP di ${esc(d.nome)}</label>
                <div class="dyn-list">${neighs.map(n => `<label class="dyn-row"><input type="checkbox" class="doNb" value="${esc(n.ip)}" ${pre.neighbor_ip === n.ip || (!pre.neighbor_ip && n.tipo === 'eBGP') ? 'checked' : ''}>
                  <code>${esc(n.ip)}</code> <b>${esc(n.chi)}</b> <span class="badge">${esc(n.tipo)} · AS${esc(n.asn)}</span>${n.default_originate ? '<span class="badge ok">già attivo</span>' : ''}</label>`).join('')}</div></div>
                <div class="chkrow" style="margin-top:8px"><label><input type="checkbox" id="doSolo"> Invia SOLO la default (aggiunge prefix-list out 0.0.0.0/0)</label></div>
                <div class="field" id="doExtBox" style="margin-top:8px" hidden><label>Eventuali altre reti da permettere oltre a 0.0.0.0/0</label><input id="doExt" placeholder="vuoto = solo la default"></div>`
              : '<div class="fwarn">Questo router non ha ancora neighbor BGP configurati.</div>'}`;
            const s = $('#doSolo'); if (s) s.onchange = () => $('#doExtBox').hidden = !s.checked;
          }
          const sel = $('#bpNbSel');
          if (sel) {
            if (pre.neighbor_ip) sel.value = pre.neighbor_ip;
            sel.onchange = () => { if (sel.value) $('#bpNbIp').value = sel.value; };
          }
        }
        $('#bpTabs').onclick = e => {
          const bt = e.target.closest('button'); if (!bt) return;
          kind = bt.dataset.k;
          $('#bpTabs').querySelectorAll('button').forEach(x => x.classList.toggle('on', x === bt));
          renderKind();
        };
        renderKind();
        $('#bpGo').onclick = () => {
          const params = {nome: d.nome, kind};
          if (kind === 'default_originate') {
            params.neighbors = [...$('#bpBody').querySelectorAll('.doNb:checked')].map(c => c.value);
            params.only_default = !!($('#doSolo') && $('#doSolo').checked);
            params.extra_networks = $('#doExt') ? $('#doExt').value.trim() : '';
          } else if (kind === 'cpp') {
            params.neighbor_ip = $('#cppIp').value.trim();
            params.neighbor_name = $('#cppName').value.trim();
            params.neighbor_asn = $('#cppAsn').value.trim();
            params.relation = $('#cppRel').value;
            params.own_networks = $('#cppOwn').value.trim();
            params.customer_networks = $('#cppCust').value.trim();
          } else {
            params.neighbor_ip = $('#bpNbIp').value.trim();
            params.neighbor_asn = $('#bpNbAsn').value.trim();
            if (kind === 'prefix_list') { params.direction = $('#bpDir').value; params.networks = $('#bpNets').value.trim(); }
            if (kind === 'local_pref') { params.value = $('#bpVal').value; params.networks = $('#bpNets').value.trim(); }
            if (kind === 'med') { params.value = $('#bpVal').value; }
            if (kind === 'access_list') { params.networks = $('#bpNets').value.trim(); }
          }
          eseguiModifica('bgp_policy', params);
        };
      }
    }
  );
}

function modalBgpNetwork(d) {
  const cur = (d.riepilogo && d.riepilogo.bgp_networks) || [];
  const prop = d.asn ? `${d.asn}.0.0.0/8` : '';
  apriModal(
    'Modifica / Gestisci network BGP su ' + d.nome,
    `<div class="finfo">Puoi <b>modificare</b> o <b>rimuovere</b> direttamente le reti già annunciate in BGP (con aggiornamento automatico dei riferimenti in prefix-list/access-list), oppure aggiungerne di nuove.</div>
    <div class="field" style="margin-bottom:12px">
      <label>Reti attualmente annunciate in BGP (${cur.length})</label>
      <div id="bnCurList" class="dyn-list">
        ${cur.length ? cur.map((n, i) => `<div class="bgp-net-row" data-old="${esc(n)}">
          <span class="badge">#${i + 1}</span>
          <input class="bnEditVal" value="${esc(n)}" placeholder="es. 100.0.0.0/8">
          <button type="button" class="small bnSaveBtn">Salva modifica</button>
          <button type="button" class="small danger bnDelBtn" title="Rimuovi questo annuncio BGP">✕</button>
        </div>`).join('') : '<div class="muted small">Nessuna network BGP attualmente annunciata.</div>'}
      </div>
    </div>
    <div class="card" style="margin:0">
      <h3>＋ Aggiungi nuove network BGP</h3>
      <div class="fgrid one">
        <div class="field"><label>Reti CIDR da aggiungere (separate da virgola)</label><input id="bnNets" value="${esc(prop)}" placeholder="es. 100.0.0.0/8, 0.0.0.0/0"></div>
        <div class="chkrow"><label><input type="checkbox" id="bnCov"> Rimuovi automaticamente da BGP le sottoreti più specifiche (non di peering) già coperte dall'aggregato</label></div>
      </div>
      <div class="riga"><button class="small" id="bnAddGo">Aggiungi (Anteprima Diff →)</button></div>
    </div>`,
    `<button class="ghost" id="mCancel">Chiudi</button>`,
    {
      wide: true,
      onMount: box => {
        $('#bnCurList').onclick = e => {
          const row = e.target.closest('.bgp-net-row');
          if (!row) return;
          const oldNet = row.dataset.old;
          if (e.target.closest('.bnSaveBtn')) {
            const newNet = row.querySelector('.bnEditVal').value.trim();
            eseguiModifica('bgp_network', {nome: d.nome, action: 'edit', old_network: oldNet, new_network: newNet});
          } else if (e.target.closest('.bnDelBtn')) {
            eseguiModifica('bgp_network', {nome: d.nome, action: 'remove', networks: oldNet});
          }
        };
        $('#bnAddGo').onclick = () => eseguiModifica('bgp_network', {nome: d.nome, action: 'add', networks: $('#bnNets').value.trim(), remove_covered: $('#bnCov').checked});
      }
    }
  );
}

function modalOspfCost(d, preDev) {
  const igpOspf = ((d.riepilogo && d.riepilogo.igp) || []).find(g => g.protocollo === 'OSPF');
  const hasAuto = igpOspf && igpOspf.auto_cost;
  apriModal(
    'Costo OSPF su ' + d.nome,
    `${!hasAuto ? '<div class="fwarn">⚠ Questo router NON ha <code>auto-cost reference-bandwidth 100</code>: in kathara/frr il costo predefinito delle altre interfacce è 10000!</div>' : '<div class="finfo">✔ <code>auto-cost reference-bandwidth ' + esc(hasAuto) + '</code> attivo (costo predefinito = 10).</div>'}
    <div class="fgrid">
      <div class="field"><label>Interfaccia</label><select id="ocDev">${d.interfacce.map(i => `<option value="${esc(i.dev)}" ${i.dev === preDev ? 'selected' : ''}>${esc(i.dev + ' · LAN ' + i.lan + ' (' + (i.ip || '-') + ')' + (i.costo ? ' [attuale=' + i.costo + ']' : ''))}</option>`).join('')}</select></div>
      <div class="field"><label>Costo OSPF (intero ≥ 1)</label><input id="ocVal" type="number" min="1" value="20"></div>
    </div>`,
    `<button class="ghost" id="mCancel">Annulla</button><button class="danger ghost" id="ocRem">Rimuovi costo</button><button id="ocGo">Imposta (Anteprima →)</button>`,
    {
      onMount: () => {
        $('#ocGo').onclick = () => eseguiModifica('ospf_cost', {nome: d.nome, dev: $('#ocDev').value, cost: $('#ocVal').value});
        $('#ocRem').onclick = () => eseguiModifica('ospf_cost', {nome: d.nome, dev: $('#ocDev').value, remove: true});
      }
    }
  );
}

function modalRedistribute(d) {
  const igps = ((d.riepilogo && d.riepilogo.igp) || []).map(g => `${g.protocollo}: ${g.redistribute.join(', ') || 'nessuno'}`).join(' · ');
  apriModal(
    'Ridistribuzione BGP → IGP su ' + d.nome,
    `<div class="finfo">Stato attuale: ${esc(igps || 'nessuna ridistribuzione')}</div>
    <div class="dyn-list">
      <label class="dyn-row"><input type="radio" name="rdM" value="all" checked> <b>Attiva <code>redistribute bgp</code></b> (inietta tutte le rotte BGP in OSPF/RIP)</label>
      <label class="dyn-row"><input type="radio" name="rdM" value="off"> <b>Togli <code>redistribute bgp</code></b> (disattiva sui router di confine che non devono iniettare)</label>
      <label class="dyn-row"><input type="radio" name="rdM" value="ebgp"> <b>Solo rotte eBGP (<code>redistribute bgp route-map eBGP</code>)</b> tramite prefix-list <code>myNeighbors</code></label>
    </div>
    <div class="field" id="rdNetBox" style="margin-top:10px" hidden>
      <label>Rete di collegamento con il neighbor eBGP (es. 50.7.1.0/24)</label>
      <input id="rdNet" placeholder="es. 50.7.1.0/24">
    </div>`,
    `<button class="ghost" id="mCancel">Annulla</button><button id="rdGo">Anteprima Diff →</button>`,
    {
      onMount: box => {
        box.querySelectorAll('input[name=rdM]').forEach(r => r.onchange = () => { $('#rdNetBox').hidden = box.querySelector('input[name=rdM]:checked').value !== 'ebgp'; });
        $('#rdGo').onclick = () => {
          const mode = box.querySelector('input[name=rdM]:checked').value;
          eseguiModifica('redistribute_bgp_igp', {nome: d.nome, mode, neighbor_network: $('#rdNet').value.trim()});
        };
      }
    }
  );
}

function modalDefaultIgp(d) {
  const protos = ['ospf', 'rip'].filter(p => d.demoni.includes(p + 'd'));
  apriModal(
    'Default route in IGP su ' + d.nome,
    `<div class="fgrid one">
      <div class="field"><label>Protocollo IGP</label><select id="diP">${protos.map(p => `<option value="${p}">${p.toUpperCase()}</option>`).join('')}</select></div>
      <div id="diOspf">
        <div class="chkrow"><label><input type="checkbox" id="diAlw" checked> Aggiungi <code>always</code> (annuncia la default anche se il router non ha una rotta 0.0.0.0/0 propria)</label></div>
      </div>
      <div id="diRip" hidden>
        <div class="field"><label>Modalità RIP</label><select id="diRipM"><option value="route">route &lt;rete&gt; (es. route 0.0.0.0/0)</option><option value="originate">default-information originate</option></select></div>
        <div class="field" id="diRipNBox" style="margin-top:8px"><label>Rete da annunciare in RIP</label><input id="diRipN" value="0.0.0.0/0"></div>
      </div>
    </div>`,
    `<button class="ghost" id="mCancel">Annulla</button><button id="diGo">Anteprima Diff →</button>`,
    {
      onMount: () => {
        function sync() {
          const p = $('#diP').value;
          $('#diOspf').hidden = p !== 'ospf'; $('#diRip').hidden = p !== 'rip';
        }
        $('#diP').onchange = sync; sync();
        $('#diRipM').onchange = () => { $('#diRipNBox').hidden = $('#diRipM').value !== 'route'; };
        $('#diGo').onclick = () => eseguiModifica('default_igp', {
          nome: d.nome, protocol: $('#diP').value, always: $('#diAlw').checked,
          rip_mode: $('#diRipM').value, networks: $('#diRipN').value.trim(),
        });
      }
    }
  );
}

function modalLoopback(d) {
  apriModal(
    'Aggiungi interfaccia Loopback (lo) su ' + d.nome,
    `<div class="finfo">Loopback attuali: ${d.loopback.length ? d.loopback.map(x => `<code>${esc(x)}</code>`).join(', ') : '<span class="muted">nessuna</span>'}</div>
    <div class="fgrid one">
      <div class="field"><label>IP Loopback (senza maschera diventa /32)</label><input id="loIp" placeholder="es. 1.1.1.1"></div>
      ${d.tipo === 'router' && (d.demoni.includes('ospfd') || d.demoni.includes('ripd')) ? `<div class="chkrow"><label><input type="checkbox" id="loIgp" checked> Annuncia in OSPF / RIP</label></div>` : ''}
      ${d.tipo === 'router' && d.demoni.includes('ospfd') ? `<div class="field"><label>Area OSPF</label><input id="loArea" value="0.0.0.0"></div>` : ''}
      ${d.tipo === 'router' && d.demoni.includes('bgpd') ? `<div class="chkrow"><label><input type="checkbox" id="loIbgp"> Crea neighbor iBGP su loopback nell'AS</label></div>` : ''}
    </div>`,
    `<button class="ghost" id="mCancel">Annulla</button><button id="loGo">Anteprima Diff →</button>`,
    {onMount: () => {
      $('#loGo').onclick = () => eseguiModifica('add_loopback', {
        nome: d.nome, ip: $('#loIp').value.trim(),
        announce_igp: !$('#loIgp') || $('#loIgp').checked,
        ospf_area: $('#loArea') ? $('#loArea').value.trim() : '0.0.0.0',
        ibgp_loopback: !!($('#loIbgp') && $('#loIbgp').checked),
      });
    }}
  );
}

function modalResolver(d) {
  const dnss = dnsLab();
  apriModal(
    'Resolver DNS (/etc/resolv.conf) per ' + d.nome,
    `<div class="finfo">Attuale: <code>${esc((d.nameserver || []).join(', ') || 'nessuno')}</code></div>
    <div class="fgrid one">
      ${dnss.length ? `<div class="field"><label>Server DNS del lab</label><select id="rsPick"><option value="">— inserimento manuale —</option>${dnss.map(x => {
        const ip = ((x.interfacce[0] || {}).ip || '').split('/')[0];
        return `<option value="${esc(ip)}">${esc(x.nome + ' — ' + ip)}</option>`;
      }).join('')}</select></div>` : ''}
      <div class="field"><label>IP Nameserver (lascia vuoto per rimuovere resolv.conf)</label><input id="rsIp" value="${esc((d.nameserver || [])[0] || '')}" placeholder="es. 20.1.0.3"></div>
    </div>`,
    `<button class="ghost" id="mCancel">Annulla</button><button id="rsGo">Anteprima Diff →</button>`,
    {onMount: () => {
      const pk = $('#rsPick'); if (pk) pk.onchange = () => { if (pk.value) $('#rsIp').value = pk.value; };
      $('#rsGo').onclick = () => eseguiModifica('set_resolver', {nome: d.nome, nameserver: $('#rsIp').value.trim()});
    }}
  );
}

function modalDnsDelegation(d) {
  apriModal(
    'Aggiungi delega DNS sul root ' + d.nome,
    `<div class="finfo">Scrive i record <code>NS</code> e glue <code>A</code> in <code>${esc(d.nome)}/etc/bind/db.root</code> (aggiunge anche il SOA se manca).</div>
    <div class="fgrid">
      <div class="field"><label>Zona TLD da delegare</label><input id="ddZ" placeholder="es. com"></div>
      <div class="field"><label>Nameserver (vuoto = dns.&lt;zona&gt;)</label><input id="ddNs" placeholder="es. dns.com"></div>
      <div class="field full"><label>IP del nameserver (record glue A)</label><input id="ddIp" placeholder="es. 20.1.0.3"></div>
    </div>`,
    `<button class="ghost" id="mCancel">Annulla</button><button id="ddGo">Anteprima Diff →</button>`,
    {onMount: () => { $('#ddGo').onclick = () => eseguiModifica('dns_delegation', {nome: d.nome, zone: $('#ddZ').value.trim(), ns: $('#ddNs').value.trim(), ip: $('#ddIp').value.trim()}); }}
  );
}

function modalIbgpMesh() {
  const cands = asMultiBgp();
  apriModal(
    'Sessioni iBGP Full Mesh (per AS)',
    cands.length
      ? `<div class="fwarn">Controlla il testo dell'esercizio: alcuni scenari (es. butterfly) vietano l'iBGP. Gli IP usati sono quelli delle interfacce verso ciascun peer lungo il percorso interno.</div>
        <div class="fgrid one"><div class="field"><label>Seleziona AS</label><select id="imAs">${cands.map(([a, rs]) => `<option value="${esc(a)}">AS${esc(a)} — ${esc(rs.join(', '))}</option>`).join('')}</select></div></div>`
      : '<div class="muted">Nessun AS nel lab ha almeno 2 router BGP.</div>',
    cands.length ? `<button class="ghost" id="mCancel">Annulla</button><button id="imGo">Anteprima Diff →</button>` : `<button class="ghost" id="mCancel">Chiudi</button>`,
    {onMount: () => { const b = $('#imGo'); if (b) b.onclick = () => eseguiModifica('ibgp_full_mesh', {asn: $('#imAs').value}); }}
  );
}

function modalAutoCost() {
  const isole = (S.lab && S.lab.isole_ospf) || [];
  apriModal(
    'Costi OSPF predefiniti a 10 (auto-cost reference-bandwidth 100)',
    isole.length
      ? `<div class="finfo">In <code>kathara/frr</code> il costo predefinito senza <code>auto-cost reference-bandwidth 100</code> è <b>10000</b> (un costo esplicito "alto" come 90 diventa il più conveniente!).</div>
        <table><tr><th>Dominio OSPF</th><th>Router</th><th>Stato</th><th>Azione</th></tr>
        ${isole.map(x => `<tr><td><b>${esc(x.etichetta)}</b></td><td class="small">${esc(x.router.join(', '))}</td>
          <td><span class="badge ${x.auto_cost_tutti ? 'ok' : 'warn'}">${x.auto_cost_tutti ? 'attivo su tutti' : (x.auto_cost_count + '/' + x.router.length)}</span></td>
          <td>${x.auto_cost_tutti
            ? `<button class="small danger ghost" data-ac="${esc(x.etichetta)}" data-en="0">Rimuovi</button>`
            : `<button class="small" data-ac="${esc(x.etichetta)}" data-en="1">Attiva (=10)</button>`}</td></tr>`).join('')}</table>`
      : '<div class="muted">Nessun router OSPF nel lab.</div>',
    `<button class="ghost" id="mCancel">Chiudi</button>`,
    {onMount: box => {
      box.onclick = e => {
        const b = e.target.closest('[data-ac]'); if (!b) return;
        eseguiModifica('ospf_auto_cost', {island: b.dataset.ac, enable: b.dataset.en === '1'});
      };
    }}
  );
}

function modalEliminaDispositivo(d) {
  apriModal(
    'Elimina ' + d.nome,
    `<div class="fwarn">Verranno rimossi <code>${esc(d.nome)}.startup</code>, la cartella <code>${esc(d.nome)}/</code> e le sue righe in <code>lab.conf</code>. Potrai sempre ripristinare dal backup automatico.</div>
    <div class="chkrow"><label><input type="checkbox" id="ddClean" checked> Rimuovi anche le righe <code>neighbor</code> verso ${esc(d.nome)} sugli altri router</label></div>`,
    `<button class="ghost" id="mCancel">Annulla</button><button class="danger" id="ddGo">Anteprima Diff →</button>`,
    {onMount: () => { $('#ddGo').onclick = () => eseguiModifica('delete_device', {nome: d.nome, clean_neighbors: $('#ddClean').checked}, {onDone: () => { if (S.sel === d.nome) S.sel = null; }}); }}
  );
}

function modalDiagnostica(d) {
  const probs = d.problemi || [];
  apriModal(
    'Diagnostica & Validazione: ' + d.nome,
    (probs.length
      ? `<div class="fwarn">Trovati <b>${probs.length}</b> problemi/avvisi su <b>${esc(d.nome)}</b>:</div>
         <ul class="avvisi">${probs.map(p => `<li class="koline">${esc(p)}</li>`).join('')}</ul>`
      : `<div class="delta-ok">✔ Nessun errore o avviso rilevato su <b>${esc(d.nome)}</b>.</div>`) +
    `<div style="margin-top:12px" class="btns">
      ${!d.nome_valido_kathara ? '<button class="small danger" id="dgFixN">Correggi nome Kathará</button>' : ''}
      ${d.tipo !== 'router' && !d.gateway ? '<button class="small" id="dgGw">Imposta Default Gateway</button>' : ''}
      ${d.has_frr ? '<button class="small" id="dgEd">Apri frr.conf nell\'editor (con auto-fix)</button>' : '<button class="small" id="dgEd">Apri file nell\'editor</button>'}
      <button class="small ghost" id="dgIf">Modifica Interfacce / IP</button>
      ${d.demoni.includes('ospfd') ? '<button class="small ghost" id="dgAc">Verifica auto-cost OSPF</button>' : ''}
      ${d.demoni.includes('bgpd') ? '<button class="small ghost" id="dgIbgp">Verifica iBGP Full Mesh</button>' : ''}
    </div>`,
    `<button class="ghost" id="mCancel">Chiudi</button>`,
    {
      onMount: () => {
        const b1 = $('#dgFixN'); if (b1) b1.onclick = () => eseguiModifica('fix_names', {});
        const b2 = $('#dgGw'); if (b2) b2.onclick = () => modalGateway(d);
        $('#dgEd').onclick = () => modalEditorFile(d, d.has_frr ? `${d.nome}/etc/frr/frr.conf` : null);
        $('#dgIf').onclick = () => modalInterfacce(d);
        const b3 = $('#dgAc'); if (b3) b3.onclick = modalAutoCost;
        const b4 = $('#dgIbgp'); if (b4) b4.onclick = modalIbgpMesh;
      }
    }
  );
}

async function modalEditorFile(d, preFile) {
  let files = [];
  try { files = await api('/api/file?lab=' + encodeURIComponent(S.nome) + '&dev=' + encodeURIComponent(d.nome)); }
  catch (e) { toast(e.message, 'err'); return; }
  if (!files.length) { toast('Nessun file trovato per ' + d.nome, 'warn'); return; }

  let curIdx = Math.max(0, files.findIndex(f => f.file === preFile));
  apriModal(
    'Editor file — ' + d.nome,
    `<div class="riga" style="margin-top:0">
      <label class="small">File: <select id="edSel">${files.map((f, i) => `<option value="${i}" ${i === curIdx ? 'selected' : ''}>${esc(f.file)}</option>`).join('')}</select></label>
      <span class="muted small">Le modifiche vengono verificate con Anteprima Diff prima di scrivere.</span>
    </div>
    <div class="ed-box">
      <pre class="ed-nums" id="edNums">1</pre>
      <textarea class="ed-txt" id="edTxt" spellcheck="false"></textarea>
    </div>
    <div id="edIssues" class="ed-issues"></div>`,
    `<button class="ghost" id="mCancel">Chiudi</button><button id="edSave">Anteprima Diff e Salva →</button>`,
    {
      wide: true,
      noFocus: true,
      onMount: () => {
        const ta = $('#edTxt'), nums = $('#edNums'), sel = $('#edSel'), iss = $('#edIssues');
        let timer = null;
        function aggiornaNumeri() {
          const n = Math.max(1, ta.value.split('\n').length);
          let s = ''; for (let i = 1; i <= n; i++) s += i + '\n';
          nums.textContent = s;
        }
        ta.onscroll = () => { nums.scrollTop = ta.scrollTop; };
        async function controllaFrr() {
          const fn = files[curIdx].file;
          if (!fn.endsWith('frr/frr.conf')) { iss.innerHTML = ''; return; }
          try {
            const r = await apiPost('/api/edit/check_frr', {content: ta.value});
            const list = r.problemi || [];
            if (!list.length) {
              iss.innerHTML = '<div class="okline small">✔ Nessun errore nei riferimenti FRR (route-map / prefix-list / access-list).</div>';
              return;
            }
            iss.innerHTML = list.map((x, idx) => `<div class="ed-issue ${x.gravita === 'errore' ? 'err' : 'warn'}">
              <span><b>Riga ${x.riga}</b>: ${esc(x.messaggio)}</span><div class="sp"></div>
              ${x.correzione ? `<button class="small okbtn" data-fix="${idx}">Applica fix</button>` : ''}
            </div>`).join('');
            iss.onclick = e => {
              const b = e.target.closest('[data-fix]'); if (!b) return;
              const item = list[+b.dataset.fix];
              const lines = ta.value.split('\n');
              if (item && item.correzione && item.riga >= 1 && item.riga <= lines.length) {
                lines[item.riga - 1] = item.correzione;
                ta.value = lines.join('\n');
                aggiornaNumeri();
                controllaFrr();
                toast('Correzione applicata alla riga ' + item.riga);
              }
            };
          } catch (e) {}
        }
        function carica(idx) {
          curIdx = idx;
          ta.value = files[curIdx].testo;
          aggiornaNumeri();
          controllaFrr();
        }
        ta.oninput = () => {
          aggiornaNumeri();
          clearTimeout(timer);
          timer = setTimeout(controllaFrr, 350);
        };
        sel.onchange = () => carica(+sel.value);
        carica(curIdx);
        $('#edSave').onclick = () => eseguiModifica('save_file', {file: files[curIdx].file, content: ta.value});
      }
    }
  );
}

$('#bNuovoLab').onclick = modalNuovoLab;
$('#bImporta').onclick = modalImporta;
$('#bStrumenti').onclick = modalStrumentiLab;
$('#labVal').onclick = () => { if (S.lab) scheda('riep'); };
$('#xmlNota').addEventListener('click', e => {
  if (e.target.id === 'bDelXmlTop') eseguiModifica('delete_xml', {});
});
$('#nomiNota').addEventListener('click', e => {
  if (e.target.id === 'bFixNomiTop') eseguiModifica('fix_names', {});
});
"""
