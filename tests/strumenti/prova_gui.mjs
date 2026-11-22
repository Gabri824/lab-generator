#!/usr/bin/env node
// tests/strumenti/prova_gui.mjs
// Prova della GUI in un Chromium senza finestra: apre un lab, legge ogni scheda e, con --kathara,
// preme i pulsanti dei comandi e dei test Kathará (lstart, raggiungibilità, sessioni, rotta,
// tabelle, ping, percorso, guasto di un link, sintassi, interfacce reali, comandi del dispositivo,
// file modificati, lclean), poi archivio e registro. Salva i testi mostrati dalla pagina in un
// JSON, così due versioni della pagina si confrontano (confronta_gui.py). Non preme "Apri
// terminale" (aprirebbe una finestra sul desktop).
//
//   node tests/strumenti/prova_gui.mjs --url http://127.0.0.1:8765/ --lab papillon_mio --out prima.json
//        [--kathara] [--lab-path /percorso/del/lab] [--shots cartella] [--chrome /usr/bin/chromium]
//        [--viste 1440,1024,768]   foto di ogni scheda e della pagina dei componenti a quelle larghezze,
//                                  in chiaro e in scuro, con il controllo di cosa esce dallo schermo
//
// Serve Node 22+ (WebSocket integrato) e Chrome/Chromium. Nessuna dipendenza.
import fs from 'node:fs';
import path from 'node:path';

import { apriBrowser, pausa, trovaChrome } from './cdp.mjs';

const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i > 0 ? process.argv[i + 1] : d; };
const flag = k => process.argv.includes('--' + k);
const URL_GUI = arg('url', 'http://127.0.0.1:8765/');
const LAB = arg('lab');
const OUT = arg('out', 'prova_gui.json');
const SHOTS = arg('shots');
const LAB_PATH = arg('lab-path');
const KATHARA = flag('kathara');
const VISTE = (arg('viste') || '').split(',').filter(Boolean).map(Number);
const CHROME = trovaChrome(arg('chrome'));
if (!LAB || !CHROME) { console.error('servono --lab e Chrome/Chromium (--chrome)'); process.exit(2); }

const B = await apriBrowser(CHROME);
const { cdp, js, aspetta, testo, visibile, errori } = B;
const fine = B.chiudi;
const scatta = nome => B.scatta(SHOTS, nome);
// premi un pulsante e aspetta che il risultato compaia in `risultato` (svuotato prima) e che il
// pulsante torni attivo; senza `risultato` si aspetta la fine del lavoro nel riquadro Output
async function premi(bottone, risultato, ms = 180000, pronto = null) {
  await js(`(() => { ${risultato ? `document.querySelector(${JSON.stringify(risultato)}).innerHTML = '';` : ''}
    document.querySelector('#outStato').textContent = '__attesa__';
    document.querySelector(${JSON.stringify(bottone)}).click(); })()`);
  const fatto = risultato
    ? `document.querySelector(${JSON.stringify(risultato)}).innerText.trim() !== ''`
    : `!['__attesa__', ' in corso…', 'in corso…'].includes(document.querySelector('#outStato').textContent)`;
  await aspetta(`(${fatto}) && !document.querySelector(${JSON.stringify(bottone)})?.disabled ${pronto ? '&& (' + pronto + ')' : ''}`, ms, bottone);
}
const valore = (sel, v) => js(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); e.value = ${JSON.stringify(v)};
  e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new Event('change', {bubbles: true})); })()`);
const scheda = t => js(`document.querySelector('#tabs [data-tab="${t}"]').click()`);

const esito = { lab: LAB, passi: {}, errori };
async function passo(nome, f) {
  const t0 = Date.now();
  process.stdout.write(`- ${nome} ... `);
  try { esito.passi[nome] = await f(); console.log(`ok (${Math.round((Date.now() - t0) / 1000)} s)`); }
  catch (e) { esito.passi[nome] = { errore: String(e.message || e) }; console.log('ERRORE: ' + e.message); }
}

try {
  await cdp('Page.navigate', { url: `${URL_GUI}#lab=${encodeURIComponent(LAB)}&tab=topo` });
  await aspetta(`document.querySelector('#labNome')?.textContent === ${JSON.stringify(LAB)}`, 30000, 'apertura del lab');
  await pausa(800);

  await passo('tastiera', async () => {
    // primi Tab dall'inizio della pagina: chi prende il focus e se l'anello si vede
    await js(`document.activeElement && document.activeElement.blur(); window.scrollTo(0, 0)`);
    const tasto = async () => {
      await cdp('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
      await cdp('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
      return js(`(() => { const e = document.activeElement, c = getComputedStyle(e);
        return { el: (e.id ? '#' + e.id : e.tagName.toLowerCase() + (e.className ? '.' + String(e.className).split(' ')[0] : '')) + ' ' + (e.textContent || '').trim().slice(0, 30),
          anello: c.outlineStyle !== 'none' && parseFloat(c.outlineWidth) >= 2 || c.boxShadow !== 'none',
          visibile: (() => { const b = e.getBoundingClientRect(); return b.width > 0 && b.bottom > 0 && b.top < innerHeight; })() }; })()`);
    };
    const passi = [];
    for (let i = 0; i < 8; i++) passi.push(await tasto());
    await js(`document.activeElement && document.activeElement.blur()`);
    return passi;
  });
  await passo('topologia', async () => {
    await scatta('topologia');
    return { nodi: await js(`document.querySelectorAll('#svg [data-id]').length`),
      link: await js(`document.querySelectorAll('#svg .lk').length`),
      etichette: await js(`[...document.querySelectorAll('#svg text')].map(t => t.textContent).sort().join(' ')`),
      lato: await testo('#side') };
  });
  await passo('dispositivo', async () => {
    const primo = await js(`document.querySelector('#side [data-sel]')?.dataset.sel`);
    await js(`document.querySelector('#side [data-sel="${primo}"]').click()`);
    await aspetta(`!document.querySelector('#sFile')`, 15000, 'file del dispositivo');
    await scatta('dispositivo');
    return { nome: primo, testo: await testo('#side'), selezionato: await js(`!!document.querySelector('#svg .sel')`) };
  });
  await passo('riepilogo', async () => { await scheda('riep'); await scatta('riepilogo'); return await testo('#t-riep'); });
  await passo('interfacce', async () => {
    await scheda('intf'); await scatta('interfacce');
    const tutte = await testo('#rIntf');
    await valore('#iFiltro', 'r1');
    const filtrate = await testo('#rIntf');
    await valore('#iFiltro', '');
    return { tutte, filtrate };
  });
  await passo('test (vuoto)', async () => { await scheda('test'); await scatta('test'); return await testo('#t-test'); });
  await passo('archivio', async () => {
    await scheda('arch');
    await valore('#aNome', 'prova_consegna');
    const avviso = await testo('#aAvviso');
    await valore('#aNome', LAB);
    await premi('#bArchivio', '#rArchivio', 30000);
    await scatta('archivio');
    return { avviso, risultato: (await testo('#rArchivio')).replace(/\/\S+\//g, '…/') };
  });

  if (VISTE.length) await passo('larghezze', async () => {
    const out = {};
    // elementi visibili che escono a destra dalla finestra o dal loro riquadro che non scorre
    const fuori = `(() => { const w = innerWidth, r = [];
      if (document.documentElement.scrollWidth > w + 1) r.push('pagina: scorre di lato (' + document.documentElement.scrollWidth + 'px)');
      if (!document.body.classList.contains('prova') && document.documentElement.scrollHeight > innerHeight + 1) r.push('pagina: scorre in verticale (' + document.documentElement.scrollHeight + 'px)');
      for (const e of document.querySelectorAll('body *')) {
        if (!e.offsetParent || e.closest('.scroll, .diff__righe, svg, pre, table, #outTesto, .canvas')) continue;
        const b = e.getBoundingClientRect();
        if (b.width && b.right > w + 1) r.push((e.id ? '#' + e.id : e.tagName.toLowerCase() + '.' + [...e.classList].join('.')) + ' fino a ' + Math.round(b.right) + 'px');
      }
      return [...new Set(r)].slice(0, 15); })()`;
    for (const scuro of [false, true]) {
      await cdp('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: scuro ? 'dark' : 'light' }, { name: 'prefers-reduced-motion', value: 'reduce' }] });
      for (const w of VISTE) {
        await cdp('Emulation.setDeviceMetricsOverride', { width: w, height: 900, deviceScaleFactor: 1, mobile: false });
        for (const t of ['topo', 'riep', 'intf', 'test', 'arch', 'reg']) {
          await scheda(t); await pausa(350);
          await scatta(`${w}-${scuro ? 'scuro' : 'chiaro'}-${t}`);
          const f = await js(fuori); if (f.length) out[`${w} ${scuro ? 'scuro' : 'chiaro'} ${t}`] = f;
        }
      }
    }
    // pagina dei componenti, con l'anteprima e il controllo del modello aperti
    await cdp('Page.navigate', { url: new URL('/static/prova.html', URL_GUI).href });
    await aspetta(`!!document.querySelector('#pAnt') && !!document.querySelector('.livello')`, 15000, 'pagina dei componenti');
    await js(`document.querySelector('#pAnt').click(); document.querySelector('#pControlla').click()`);
    await aspetta(`!!document.querySelector('#rErr .errori')`, 15000, 'controllo del modello');
    for (const scuro of [false, true]) {
      await cdp('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: scuro ? 'dark' : 'light' }, { name: 'prefers-reduced-motion', value: 'reduce' }] });
      for (const w of VISTE) {
        await cdp('Emulation.setDeviceMetricsOverride', { width: w, height: 900, deviceScaleFactor: 1, mobile: false });
        await pausa(300); await scatta(`${w}-${scuro ? 'scuro' : 'chiaro'}-componenti`);
        const f = await js(fuori); if (f.length) out[`${w} ${scuro ? 'scuro' : 'chiaro'} componenti`] = f;
      }
    }
    out.errori_modello = await testo('#rErr');
    out.campo_segnato = await js(`document.querySelector('#rProp [aria-invalid=true]')?.dataset.campo || null`);
    await cdp('Emulation.setEmulatedMedia', { features: [] });
    await cdp('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
    await cdp('Page.navigate', { url: `${URL_GUI}#lab=${encodeURIComponent(LAB)}&tab=topo` });
    await aspetta(`document.querySelector('#labNome')?.textContent === ${JSON.stringify(LAB)}`, 30000, 'ritorno al lab');
    return out;
  });

  if (KATHARA) {
    await passo('lstart + convergenza', async () => {
      await scheda('test');
      await premi('#bStart', '#rSessioni', 600000, `!document.querySelector('#bConv').disabled`);
      return { stato: await testo('#labStato'), sessioni: await testo('#rSessioni') };
    });
    await passo('raggiungibilita', async () => { await premi('#bPing', '#rPing', 300000); await scatta('raggiungibilita'); return await testo('#rPing'); });
    await passo('sessioni', async () => { await premi('#bSessioni', '#rSessioni'); return await testo('#rSessioni'); });
    await passo('riapplica', async () => {
      const c = await js(`document.querySelectorAll('#rSessioni [data-riapplica]').length`);
      if (!c) return 'nessuna ridistribuzione da riapplicare';
      await premi('#rSessioni [data-riapplica]', null);
      return await testo('#rSessioni');
    });
    await passo('rotta', async () => {
      const rete = await js(`[...document.querySelectorAll('#retiList option')].map(o => o.value).pop()`);
      await valore('#rRete', rete);
      await premi('#bRotta', '#rRotta');
      return { router: await js(`document.querySelector('#rDev').value`), rete, testo: await testo('#rRotta') };
    });
    await passo('tabelle', async () => { await premi('#bTabelle', '#rTabelle', 300000); await scatta('tabelle'); return await testo('#rTabelle'); });
    await passo('ping', async () => {
      const src = await js(`[...document.querySelectorAll('#pnSrc option')].map(o => o.value).pop()`);
      const dst = await js(`document.querySelector('#ipList option')?.value`);
      await valore('#pnSrc', src); await valore('#pnDst', dst);
      await premi('#bPn', '#rPn');
      return { da: src, verso: dst, testo: await testo('#rPn') };
    });
    await passo('percorso andata e ritorno', async () => {
      const src = await js(`[...document.querySelectorAll('#pSrc option')].map(o => o.value).pop()`);
      const dst = await js(`document.querySelector('#ipList option')?.value`);
      await valore('#pSrc', src); await valore('#pDst', dst);
      await js(`document.querySelector('#pRit').checked = true`);
      await premi('#bPercorso', '#rPercorso');
      await js(`document.querySelector('#vediMappa').click()`); await pausa(400);
      await scatta('percorso-topologia');
      const evid = await js(`document.querySelectorAll('#svg .ring').length`);
      await scheda('test');
      return { da: src, verso: dst, testo: await testo('#rPercorso'), anelli: evid };
    });
    await passo('guasto di un link', async () => {
      const lan = await js(`document.querySelector('#gLan option')?.value`);
      await valore('#gLan', lan);
      await premi('#gGiu', '#rSessioni', 400000, `!document.querySelector('#bConv').disabled`);
      const spento = { lan, nota: await testo('#linkNota'), guasto: await testo('#rGuasto'),
        tratteggio: await js(`document.querySelectorAll('#svg .lk.off').length`) };
      await premi('#gSu', '#rSessioni', 400000, `!document.querySelector('#bConv').disabled`);
      return { spento, riacceso: { nota_visibile: await visibile('#linkNota'), guasto: await testo('#rGuasto') } };
    });
    await passo('sintassi frr', async () => {
      await scheda('riep');
      await js(`document.querySelector('#outStato').textContent = '__attesa__'; document.querySelector('#bSintassi').click()`);
      await aspetta(`document.querySelector('#t-riep').innerText.includes('sintassi controllata') && !document.querySelector('#t-riep').innerText.includes('non ancora')`, 300000, 'sintassi');
      return await testo('#t-riep');
    });
    await passo('interfacce reali', async () => {
      await scheda('intf');
      await js(`document.querySelector('#outStato').textContent = '__attesa__'; document.querySelector('#bReali').click()`);
      await aspetta(`document.querySelector('#rIntf').innerText.includes('Nel lab acceso') && !document.querySelector('#bReali').disabled`, 300000, 'interfacce reali');
      return await testo('#rIntf');
    });
    await passo('comandi del dispositivo', async () => {
      await scheda('topo');
      const router = await js(`document.querySelector('#rDev option')?.value`);
      await js(`document.querySelector('#side [data-sel=""]')?.click()`);
      await js(`document.querySelector('#side [data-sel="${router}"]').click()`);
      await aspetta(`!!document.querySelector('#side [data-cmd="route"]')`, 10000, 'pannello del router');
      const out = {};
      for (const c of await js(`[...document.querySelectorAll('#side [data-cmd]')].map(b => b.dataset.cmd).filter(c => c !== 'ping' && c !== 'traceroute')`)) {
        await premi(`#side [data-cmd="${c}"]`, null, 60000);
        out[c] = { titolo: await testo('#outTitolo'), stato: await testo('#outStato'), righe: (await testo('#outTesto')).split('\n').length };
      }
      await valore('#sIp', await js(`document.querySelector('#ipList option')?.value`));
      await premi('#side [data-cmd="ping"]', null, 60000);
      out.ping = { titolo: await testo('#outTitolo'), stato: await testo('#outStato') };
      return { router, comandi: out };
    });
    await passo('file modificati dopo l\'avvio', async () => {
      if (!LAB_PATH) return 'saltato (serve --lab-path)';
      const f = fs.readdirSync(LAB_PATH).find(x => x.endsWith('.startup'));
      fs.appendFileSync(path.join(LAB_PATH, f), '# modifica di prova\n');
      await aspetta(`!document.querySelector('#modNota').hidden`, 30000, 'avviso file modificati');
      return await testo('#modNota');
    });
    await passo('lclean', async () => {
      await premi('#bClean', null, 300000);
      await aspetta(`document.querySelector('#labStato').textContent === 'spento'`, 60000, 'lab spento');
      return { stato: await testo('#labStato'), output: await testo('#outStato') };
    });
  }
  await passo('registro', async () => {
    await scheda('reg'); await pausa(800); await scatta('registro');
    return (await testo('#rRegistro')).split('\n').map(r => r.replace(/^\d\d:\d\d:\d\d\s*/, '')).join('\n');
  });
} catch (e) {
  esito.fatale = String(e.message || e);
  console.error('ERRORE: ' + esito.fatale);
}
fs.writeFileSync(OUT, JSON.stringify(esito, null, 1));
console.log(`\n${Object.keys(esito.passi).length} passi, ${errori.length} errori nella console -> ${OUT}`);
for (const e of errori) console.log('  console: ' + e);
fine(esito.fatale ? 1 : 0);
