# Controlli della GUI

Lista da ripassare dopo ogni modifica della pagina (`src/gui/static/`). Quasi tutto è anche
automatico:

```bash
# test della pagina e del server (anche senza Kathará)
python -m unittest discover -s tests

# GUI di prova su una copia del lab, poi il pilota in Chromium senza finestra
python -c "import sys; sys.path.insert(0, 'src'); import core; from gui import server; server.avvia('/tmp/labs', core, 8791, apri_browser=False)" &
node tests/strumenti/prova_gui.mjs --url http://127.0.0.1:8791/ --lab papillon_mio --out dopo.json \
     --kathara --lab-path /tmp/labs/papillon_mio --viste 1440,1024,768 --shots foto
python tests/strumenti/confronta_gui.py prima.json dopo.json
```

`prova_gui.mjs` non preme "Apri terminale" (aprirebbe una finestra sul desktop): quello va
provato a mano. Con `--kathara` avvia e ferma davvero il lab (`lstart`, `lclean`): usare una
copia, non i lab veri.

## Avvio e lab

- [ ] `labGenerator --gui` apre il browser sulla pagina; l'icona della scheda c'è.
- [ ] Elenco dei lab a sinistra, pallino verde per i lab accesi, "Aggiorna".
- [ ] Indirizzo diretto `#lab=<nome>&tab=<scheda>` apre il lab sulla scheda giusta.
- [ ] Lab con l'XML dentro: compare la nota gialla.
- [ ] "Avvia (lstart)": Output in diretta, poi da solo "Attendi convergenza"; su un lab già
      acceso chiede se riavviarlo.
- [ ] "Ferma (lclean)": chiede conferma, poi il lab risulta spento.
- [ ] "Rileggi i file" dopo una modifica fatta dal terminale.
- [ ] File modificati dopo l'avvio: nota con "Riavvia ora".
- [ ] "Chiudi GUI": chiede conferma e chiude il server.

## Topologia

- [ ] Disegno con AS, LAN, interfacce; "Riordina", "Adatta", interfacce sì/no.
- [ ] Trascinamento dei nodi e dello sfondo, rotellina per lo zoom; le posizioni restano dopo
      una nuova apertura.
- [ ] Clic su un dispositivo: pannello con interfacce, file, comandi (`show ip route`,
      `show ip bgp`, `ip -br addr`, ...), ping e traceroute verso un IP, "percorso sulla mappa".
- [ ] **A mano:** "Apri terminale (kathara connect)" apre il terminale o mostra il comando.
- [ ] "Scarica immagine (SVG)".

## Riepilogo, Interfacce, Test

- [ ] Riepilogo: controlli automatici, controllo dei nomi di frr.conf, "Controlla la sintassi".
- [ ] Interfacce: filtro, "solo righe con avvisi", "Confronta con il lab acceso", clic sul nome
      porta alla topologia.
- [ ] Raggiungibilità (matrice), Sessioni BGP/OSPF con ridistribuzione e "Riapplica" quando
      compare, Rotta verso una rete (con i pulsanti degli annunci per vicino), Tabelle di routing.
- [ ] Ping con origine scelta; Verifica percorso con atteso, sequenza esatta e ritorno;
      evidenziazione sulla topologia e "Togli evidenziazione".
- [ ] Guasto di un link: "Spegni" (tratteggio rosso, nota in alto), "Riaccendi".

## Archivio e Registro

- [ ] Archivio `.tar.gz` e `.zip`, avviso se il nome è diverso da quello del lab, "Scarica".
- [ ] Registro con tutte le operazioni e i comandi equivalenti.

## Aspetto e accessibilità

- [ ] Chiaro e scuro (impostazione del sistema); 1440, 1024 e 768 px senza scorrimento laterale.
- [ ] Tab dalla tastiera: "Vai al contenuto" per primo, anello di focus visibile su ogni
      controllo, schede raggiungibili.
- [ ] Con "riduci movimento" del sistema niente animazioni.
- [ ] Pagina dei componenti `/static/prova.html`: anteprima, conflitto, errori sotto i campi,
      livelli, annulla/ripeti con Ctrl+Z e Ctrl+Y.

## Eseguibile

- [ ] L'eseguibile di PyInstaller (Linux e Windows) mostra la pagina: se risponde 404 manca
      `--add-data "src/gui/static:gui/static"` nella build.
