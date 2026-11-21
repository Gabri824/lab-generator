"""Stili CSS della GUI web (base + menu contestuale, modali guidati, diff, editor e badge)."""

UI_CSS = r"""
:root{--bg:#f1f5f9;--pan:#fff;--txt:#0f172a;--mut:#64748b;--bor:#e2e8f0;--acc:#2563eb;--ok:#16a34a;--ko:#dc2626;--warn:#d97706;--okbg:#dcfce7;--kobg:#fee2e2;--warnbg:#fef3c7;--code:#0b1220;--codetxt:#e2e8f0;--shadow:0 12px 32px rgba(15,23,42,.22)}
@media (prefers-color-scheme: dark){:root{--bg:#0b1220;--pan:#111a2e;--txt:#e2e8f0;--mut:#94a3b8;--bor:#22304a;--acc:#60a5fa;--ok:#4ade80;--ko:#f87171;--warn:#fbbf24;--okbg:#14321f;--kobg:#3b1515;--warnbg:#3a2a0b;--code:#050912;--codetxt:#cbd5e1;--shadow:0 12px 36px rgba(0,0,0,.55)}}
*{box-sizing:border-box}
[hidden]{display:none !important}
body{margin:0;font:14px/1.45 system-ui,-apple-system,"Segoe UI",Ubuntu,sans-serif;background:var(--bg);color:var(--txt)}
button{font:inherit;border:1px solid var(--acc);background:var(--acc);color:#fff;border-radius:7px;padding:6px 12px;cursor:pointer}
button:hover{filter:brightness(1.08)}
button:disabled{opacity:.5;cursor:default}
button.ghost{background:transparent;color:var(--acc)}
button.danger{background:var(--ko);border-color:var(--ko);color:#fff}
button.danger.ghost{background:transparent;color:var(--ko);border-color:var(--ko)}
button.danger.ghost:hover{background:var(--ko);color:#fff}
button.warnbtn{background:#eab308;border-color:#ca8a04;color:#1c1917;font-weight:700}
button.warnbtn:hover{background:#facc15;border-color:#eab308;filter:none}
button.okbtn{background:var(--ok);border-color:var(--ok);color:#fff}
button.small{padding:3px 8px;font-size:12.5px}
input,select,textarea{font:inherit;padding:5px 8px;border:1px solid var(--bor);border-radius:7px;background:var(--pan);color:var(--txt)}
input:focus,select:focus,textarea:focus{outline:2px solid var(--acc);outline-offset:1px}
code,pre{font-family:ui-monospace,"Cascadia Mono",Consolas,"DejaVu Sans Mono",monospace;font-size:12.5px}
.muted{color:var(--mut)}.small{font-size:12.5px}
.sp{flex:1}
header.top{height:50px;display:flex;align-items:center;gap:10px;padding:0 16px;background:var(--pan);border-bottom:1px solid var(--bor)}
.brand{font-weight:700;font-size:16px}.brand span{color:var(--acc)}
.wrap{display:grid;grid-template-columns:240px 1fr;height:calc(100vh - 50px)}
aside{background:var(--pan);border-right:1px solid var(--bor);overflow:auto;padding:12px;display:flex;flex-direction:column}
.aside-h{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;gap:6px}
.aside-actions{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:10px}
#base{overflow-wrap:anywhere;margin-top:auto;padding-top:8px;border-top:1px solid var(--bor)}
#labs{list-style:none;margin:0 0 12px;padding:0}
#labs li{padding:7px 9px;border-radius:7px;cursor:pointer;display:flex;align-items:center;gap:8px}
#labs li:hover{background:var(--bg)}
#labs li.on{background:var(--acc);color:#fff}
.dot{width:9px;height:9px;border-radius:50%;background:var(--mut);opacity:.5;flex:none}
.dot.acceso{background:var(--ok);opacity:1}
main{display:flex;flex-direction:column;min-width:0;min-height:0}
#scorri{flex:1;overflow:auto;padding:14px 18px}
.vuoto{padding:40px;color:var(--mut)}
.labhead{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.labhead h1{font-size:20px;margin:0}
.badge{font-size:12px;padding:2px 9px;border-radius:20px;background:var(--bor);color:var(--mut);display:inline-flex;align-items:center;gap:4px}
.badge.ok{background:var(--okbg);color:var(--ok)}.badge.ko{background:var(--kobg);color:var(--ko)}.badge.warn{background:var(--warnbg);color:var(--warn)}
.badge.click{cursor:pointer}
.nota{margin:10px 0 0;padding:8px 12px;border-radius:8px;background:var(--warnbg);color:var(--txt);border:1px solid var(--warn);display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.nota.err{background:var(--kobg);border-color:var(--ko)}
nav.tabs{display:flex;gap:4px;margin:14px 0 12px;border-bottom:1px solid var(--bor);flex-wrap:wrap}
nav.tabs button{background:transparent;color:var(--mut);border:none;border-bottom:2px solid transparent;border-radius:0;padding:8px 12px}
nav.tabs button.on{color:var(--acc);border-bottom-color:var(--acc);font-weight:600}
.card{background:var(--pan);border:1px solid var(--bor);border-radius:10px;padding:14px;margin-bottom:14px}
.card h2{font-size:15px;margin:0 0 10px}
.card h3{font-size:14px;margin:0 0 6px}
.topo{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:14px}
.canvas{background:#fff;border:1px solid var(--bor);border-radius:10px;height:max(440px,calc(100vh - 410px));display:flex;flex-direction:column;overflow:hidden;position:relative}
.toolbar{display:flex;gap:8px;align-items:center;padding:7px 10px;border-bottom:1px solid #e2e8f0;flex-wrap:wrap;color:#334155}
.toolbar .muted{color:#64748b}
.toolbar button.ghost{color:#2563eb;border-color:#2563eb}
svg.mappa{flex:1;width:100%;min-height:0;touch-action:none;user-select:none;-webkit-user-select:none}
.side{background:var(--pan);border:1px solid var(--bor);border-radius:10px;padding:12px;max-height:max(440px,calc(100vh - 410px));overflow:auto}
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
.output{height:160px;flex:none;border-top:1px solid var(--bor);background:var(--code);color:var(--codetxt);display:flex;flex-direction:column}
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

.ctxmenu{position:fixed;z-index:2000;min-width:255px;max-width:340px;max-height:82vh;overflow-y:auto;background:var(--pan);color:var(--txt);border:1px solid var(--bor);border-radius:10px;box-shadow:var(--shadow);padding:5px 0;font-size:13.5px}
.ctx-head{padding:6px 12px;font-weight:700;font-size:12.5px;color:var(--mut);border-bottom:1px solid var(--bor);display:flex;align-items:center;justify-content:space-between;gap:8px;background:var(--bg);margin:-5px 0 4px;border-radius:10px 10px 0 0}
.ctx-sec{padding:5px 12px 2px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--mut)}
.ctx-item{display:flex;align-items:center;gap:8px;width:100%;text-align:left;background:transparent;color:var(--txt);border:none;border-radius:0;padding:7px 12px;cursor:pointer;font-size:13.5px}
.ctx-item:hover,.ctx-item:focus{background:var(--acc);color:#fff;outline:none}
.ctx-item:hover .ctx-hint,.ctx-item:focus .ctx-hint{color:rgba(255,255,255,.85)}
.ctx-item.danger{background:transparent;border:none;color:var(--ko);font-weight:600}
.ctx-item.danger:hover,.ctx-item.danger:focus{background:var(--ko);color:#fff}
.ctx-item.warn{color:var(--warn);font-weight:600}
.ctx-item.warn:hover,.ctx-item.warn:focus{background:var(--warn);color:#fff}
.ctx-hint{margin-left:auto;font-size:11.5px;color:var(--mut)}
.ctx-sep{height:1px;background:var(--bor);margin:4px 0}

.modal-bg{position:fixed;inset:0;z-index:3000;background:rgba(15,23,42,.15);display:flex;align-items:center;justify-content:center;padding:16px}
.modal-bg[hidden]{display:none}
.modal{background:var(--pan);color:var(--txt);border:1px solid var(--bor);border-radius:12px;box-shadow:var(--shadow);width:min(760px,96vw);max-height:90vh;display:flex;flex-direction:column;overflow:hidden;position:relative}
.modal.wide{width:min(960px,96vw)}
.modal-h{padding:12px 16px;border-bottom:1px solid var(--bor);display:flex;align-items:center;gap:10px;cursor:grab;user-select:none;-webkit-user-select:none}
.modal-h.dragging{cursor:grabbing}
.modal-drag-hint{font-size:11px;color:var(--mut);font-weight:500;letter-spacing:.02em;padding:2px 6px;border-radius:6px;background:var(--bg);border:1px solid var(--bor)}
.modal-h h2{margin:0;font-size:16px;flex:1}
.modal-x{background:transparent;color:var(--mut);border:none;font-size:20px;line-height:1;padding:2px 8px;cursor:pointer}
.modal-x:hover{color:var(--txt)}
.modal-b{padding:14px 16px;overflow-y:auto;flex:1}
.modal-f{padding:10px 16px;border-top:1px solid var(--bor);display:flex;align-items:center;gap:8px;justify-content:flex-end;background:var(--bg)}
.fgrid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.fgrid.one{grid-template-columns:1fr}
.fgrid.three{grid-template-columns:1fr 1fr 1fr}
.field{display:flex;flex-direction:column;gap:4px}
.field.full{grid-column:1 / -1}
.field label{font-size:12.5px;font-weight:600;color:var(--mut)}
.field input,.field select,.field textarea{width:100%}
.fhelp{font-size:12px;color:var(--mut)}
.ferr{padding:8px 10px;border-radius:8px;background:var(--kobg);color:var(--ko);border:1px solid var(--ko);margin-bottom:10px;font-size:13px}
.finfo{padding:8px 10px;border-radius:8px;background:var(--bg);border:1px solid var(--bor);margin-bottom:10px;font-size:13px}
.fwarn{padding:8px 10px;border-radius:8px;background:var(--warnbg);border:1px solid var(--warn);margin-bottom:10px;font-size:13px}
.mtabs{display:flex;gap:4px;border-bottom:1px solid var(--bor);margin-bottom:12px;flex-wrap:wrap}
.mtabs button{background:transparent;color:var(--mut);border:none;border-bottom:2px solid transparent;border-radius:0;padding:6px 10px;font-size:13px}
.mtabs button.on{color:var(--acc);border-bottom-color:var(--acc);font-weight:600}
.dyn-list{display:flex;flex-direction:column;gap:6px;margin:6px 0}
.dyn-row{display:flex;gap:6px;align-items:center;flex-wrap:wrap;padding:6px;border:1px solid var(--bor);border-radius:8px;background:var(--bg)}
.dyn-row input,.dyn-row select{flex:1;min-width:100px}
.chkrow{display:flex;gap:14px;flex-wrap:wrap;align-items:center}
.chkrow label{display:inline-flex;align-items:center;gap:5px;cursor:pointer;font-weight:500;color:var(--txt)}

.delta-box{display:flex;flex-direction:column;gap:6px;margin-bottom:12px}
.delta-ok{padding:8px 10px;border-radius:8px;background:var(--okbg);border:1px solid var(--ok);font-size:13px}
.delta-ko{padding:8px 10px;border-radius:8px;background:var(--kobg);border:1px solid var(--ko);font-size:13px}
.diff-file{border:1px solid var(--bor);border-radius:8px;margin-bottom:10px;overflow:hidden}
.diff-fh{padding:6px 10px;background:var(--bg);border-bottom:1px solid var(--bor);font-weight:600;font-size:12.5px;display:flex;align-items:center;gap:8px}
.diff-tbl{width:100%;border-collapse:collapse;font-family:ui-monospace,"Cascadia Mono",Consolas,"DejaVu Sans Mono",monospace;font-size:12px}
.diff-tbl td{padding:1px 6px;border:none;white-space:pre-wrap;word-break:break-word}
.diff-tbl td.ln{width:38px;text-align:right;color:var(--mut);user-select:none;border-right:1px solid var(--bor)}
.diff-tbl td.sg{width:18px;text-align:center;font-weight:700;user-select:none}
.diff-tbl tr.d-add{background:var(--okbg);color:var(--ok)}
.diff-tbl tr.d-del{background:var(--kobg);color:var(--ko)}
.diff-tbl tr.d-sep{background:var(--bg);color:var(--mut);text-align:center}

.ed-box{display:grid;grid-template-columns:46px 1fr;border:1px solid var(--bor);border-radius:8px;overflow:hidden;background:var(--code);color:var(--codetxt)}
.ed-nums{margin:0;padding:10px 6px;text-align:right;color:#64748b;background:#070d19;user-select:none;font:12.5px/1.5 ui-monospace,"Cascadia Mono",Consolas,"DejaVu Sans Mono",monospace;overflow:hidden;border-right:1px solid #1e293b}
.ed-txt{margin:0;padding:10px;border:none;border-radius:0;background:transparent;color:var(--codetxt);font:12.5px/1.5 ui-monospace,"Cascadia Mono",Consolas,"DejaVu Sans Mono",monospace;min-height:300px;resize:vertical;white-space:pre;overflow:auto;tab-size:4}
.ed-txt:focus{outline:none}
.ed-issues{margin-top:10px;display:flex;flex-direction:column;gap:6px}
.ed-issue{display:flex;align-items:center;gap:8px;padding:6px 10px;border-radius:8px;font-size:12.5px;border:1px solid var(--bor);background:var(--bg)}
.ed-issue.err{background:var(--kobg);border-color:var(--ko)}
.ed-issue.warn{background:var(--warnbg);border-color:var(--warn)}

#toastWrap{position:fixed;right:18px;bottom:18px;z-index:4000;display:flex;flex-direction:column;gap:8px;pointer-events:none}
.toast{background:var(--code);color:#fff;padding:9px 14px;border-radius:8px;box-shadow:var(--shadow);font-size:13px;border-left:4px solid var(--ok);pointer-events:auto;max-width:380px}
.toast.err{border-left-color:var(--ko)}
.toast.warn{border-left-color:var(--warn)}


.if-list{display:flex;flex-direction:column;gap:8px;margin:6px 0 8px}
.if-card{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:8px 10px;border:1px solid var(--bor);border-left:3px solid var(--acc);border-radius:9px;background:var(--bg);transition:transform .12s ease,border-color .12s ease,background .12s ease,opacity .12s ease}
.if-card:hover{border-color:var(--acc)}
.if-card.dragging{opacity:.45;transform:scale(.99)}
.if-card.drag-over{border-top:3px solid var(--acc);background:var(--pan)}
.if-handle{cursor:grab;color:var(--mut);font-weight:700;font-size:15px;line-height:1;padding:3px 5px;border-radius:5px;user-select:none;-webkit-user-select:none}
.if-handle:hover{background:var(--bor);color:var(--txt)}
.if-badge{font-family:ui-monospace,"Cascadia Mono",Consolas,monospace;font-size:12px;font-weight:700;padding:3px 8px;border-radius:6px;background:var(--pan);border:1px solid var(--bor);color:var(--acc);white-space:nowrap}
.if-card .ifLan{width:115px;flex:0 1 125px;font-weight:600}
.if-card .ifIp{flex:1;min-width:155px;font-family:ui-monospace,"Cascadia Mono",Consolas,monospace}
.if-rm{padding:4px 9px;font-weight:700;line-height:1.2}
.if-reorder-bar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:8px 10px;border-radius:8px;background:var(--warnbg);border:1px solid var(--warn);margin-top:8px;font-size:13px}
.bgp-net-row{display:flex;gap:8px;align-items:center;padding:6px 8px;border:1px solid var(--bor);border-radius:8px;background:var(--bg)}
.bgp-net-row input{flex:1;font-family:ui-monospace,"Cascadia Mono",Consolas,monospace}

@media (max-width:1100px){.topo{grid-template-columns:1fr}.side{max-height:none}}
@media (max-width:700px){.wrap{grid-template-columns:1fr}aside{max-height:190px}.fgrid,.fgrid.three{grid-template-columns:1fr}}
"""
