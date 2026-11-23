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

# editor grafico: disegna un lab con mouse e tastiera veri (circa un minuto)
node tests/strumenti/prova_editor.mjs --url http://127.0.0.1:8791/ --shots foto
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

- [ ] Disegno con AS, LAN, interfacce; "Riordina", "Adatta", livello "Indirizzi" sì/no.
- [ ] Costo OSPF `c<N>` accanto all'interfaccia solo dove `frr.conf` ha `ospf cost`; con
      "Indirizzi" spento resta da solo, sparisce con "Costi OSPF" spento.
- [ ] Trascinamento dei nodi e dello sfondo, rotellina per lo zoom; le posizioni restano dopo
      una nuova apertura.
- [ ] Clic su un dispositivo: pannello con interfacce, file, comandi (`show ip route`,
      `show ip bgp`, `ip -br addr`, ...), ping e traceroute verso un IP, "percorso sulla mappa".
- [ ] **A mano:** "Apri terminale (kathara connect)" apre il terminale o mostra il comando.
- [ ] "Scarica immagine (SVG)".

## Modifica del lab (fase 5)

```bash
# pilota della modalità Modifica su una COPIA del lab (circa un minuto)
node tests/strumenti/prova_modifica.mjs --url http://127.0.0.1:8791/ --lab papillon_mio \
     --lab-path /tmp/labs/papillon_mio --shots foto
```

- [ ] "Modifica" accende la modalità (pulsante blu, etichette delle interfacce sempre visibili).
- [ ] Clic sull'etichetta di un'interfaccia: menu dell'interfaccia; "Costo OSPF" con anteprima e "Applica";
      `c<N>` compare sul disegno. Su un router senza OSPF: avviso, nessun modulo.
- [ ] Clic sulla scritta di un AS: auto-cost (metti o togli, proposta già scelta).
- [ ] Pannello del dispositivo in modalità Modifica: pulsanti delle interfacce e delle azioni.
- [ ] Valore sbagliato (costo 0): errore del motore, niente scritto.
- [ ] File cambiato dopo l'anteprima: "Non ho scritto nulla", "Rifai l'anteprima".
- [ ] "Annulla modifica" (intestazione): anteprima e applica; più volte di fila; anche per le
      modifiche fatte dal terminale. File cambiato a mano dopo: rifiuto con il rimando alle copie.
- [ ] Copie di sicurezza: elenco con data e ora, "Ripristina" con conferma; dopo, storia vuota.
- [ ] Interfaccia (5.2): cambia IP con l'ultimo numero, sposta su un'altra LAN o su una nuova,
      costo OSPF e togli il costo, togli l'interfaccia.
- [ ] LAN: cambia subnet (IP proposti modificabili), collega un dispositivo, aggiungi qui.
- [ ] Dispositivo: rinomina (resta al suo posto sul disegno), gateway, AS, aggiungi e togli
      protocolli, file a righe, togli; "+ Router/Host/Server web/Server DNS" con i valori proposti.
- [ ] Dopo una modifica il disegno non si ridispone: i nodi nuovi compaiono vicino ai vicini.
- [ ] Menu dell'AS (5.3): aggregato con le reti già coperte, completa l'iBGP, auto-cost.
- [ ] Router: loopback (proposta modificabile), network BGP, default route (BGP, OSPF, RIP),
      ridistribuzione (togli, rimetti, route-map eBGP).
- [ ] DNS (5.4): "Resolver" su host, server web e DNS; "Delega una zona" sul server root con
      nameserver e glue proposti.
- [ ] Policy BGP (5.5): dal pannello del router (neighbor dall'elenco o nuovo) e dal link fra due
      AS; local-preference 150 e MED 20 proposti, prefix-list in/out e access-list con le caselle
      delle reti; Customer-Provider-Peer con le reti proposte e il lato opposto subito dopo.
- [ ] Percorso voluto (5.5b): clic su sorgente, link o AS, destinazione (evidenziati con l'ordine),
      "Togli l'ultimo", divieto per AS; proposte una alla volta con Salta; a lab acceso "niente da
      fare" dove la strada è già quella; alla fine Verifica percorso già compilata.
- [ ] Livelli del disegno (5.6): interruttori (accesi all'apertura tutti tranne Sessioni BGP e
      DNS, scelta ricordata); sigle delle policy e frecce Customer-Provider-Peer; sessioni iBGP e
      sessione sbagliata in rosso; `0/0`, `R`, loopback; deleghe DNS e `ns:`; "!" degli avvisi;
      "Configurazione in breve" nel pannello; clic su una sigla in modalità Modifica.
- [ ] Editor, "Parti da un lab esistente" (5.7): dall'elenco o da una cartella (es. una soluzione);
      disegno con riquadri giusti; riquadro del lab di partenza; rinomina, aggiungi, Anteprima con
      "Dal lab di partenza"; Crea con un altro nome: policy e righe in più conservate, lab di
      partenza non toccato; cartella non valida e data center spiegati; "Resolver solo di questo
      dispositivo"; "OSPF: no" sul router RIP di confine.

## Riepilogo, Interfacce, Test

- [ ] Riepilogo: controlli automatici, controllo dei nomi di frr.conf, "Controlla la sintassi".
- [ ] Interfacce: filtro, "solo righe con avvisi", "Confronta con il lab acceso", clic sul nome
      porta alla topologia.
- [ ] Raggiungibilità (matrice), Sessioni BGP/OSPF con ridistribuzione e "Riapplica" quando
      compare, Rotta verso una rete (con i pulsanti degli annunci per vicino), Tabelle di routing.
- [ ] Ping con origine scelta; Verifica percorso con atteso, sequenza esatta e ritorno;
      evidenziazione sulla topologia e "Togli evidenziazione".
- [ ] Guasto di un link: "Spegni" (tratteggio rosso, nota in alto), "Riaccendi".
- [ ] Server web: "Prova le pagine" da un client (IP e nomi DNS dei server), stato di apache2,
      "Avvia" quando è spento; spiegazione per DNS, apache2, gateway, routing.
- [ ] Pannello di host, DNS e server: "links" verso un IP o un nome (proposti dall'elenco); sui
      server "stato apache2" e "avvia apache2".

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

## Editor grafico (lab nuovi)

- [ ] "+ Nuovo lab" apre l'editor; "Chiudi editor" torna al lab o alla pagina iniziale.
- [ ] R, H, W, D, N mettono router, host, WWW, DNS, nodo LAN con un clic; Esc torna a Seleziona.
- [ ] L: dispositivo -> dispositivo (link diretto), -> nodo LAN, -> linea di un link diretto
      (diventa nodo LAN).
- [ ] Subnet sulla LAN, IP automatici sul disegno, IP scritto a mano nel pannello, frecce per
      l'ordine delle interfacce.
- [ ] Trascinamento con la griglia, selezione con Maiusc, Canc, Ctrl+Z e Ctrl+Y.
- [ ] A, I, O: riquadro AS, zona RIP, area OSPF trascinando; valore da scrivere (prima area
      0.0.0.0), stub, ridimensionamento dagli angoli; router colorati per AS, segno ABR.
- [ ] Pannelli: ridistribuzione, network OSPF/RIP, rotte statiche; gateway; DNS (tipo per ".",
      deleghe, zone e record, ricorsione, DNSSEC); resolver del lab e "Proponi subnet".
- [ ] Controlli dal vivo: un errore (es. gateway fuori rete) compare dopo mezzo secondo sotto il
      campo e sul disegno, e sparisce quando si corregge.
- [ ] Anteprima file; Crea laboratorio (nome obbligatorio, conferma e copia di sicurezza se esiste);
      il lab si apre con la Topologia disposta come nel disegno; l'editor riparte vuoto.
- [ ] Bozza ripresa dopo aver chiuso la pagina; Nuova bozza; esporta e importa JSON.
- [ ] Ctrl+D, Ctrl+A, frecce, F.

## Eseguibile

- [ ] L'eseguibile di PyInstaller (Linux e Windows) mostra la pagina: se risponde 404 manca
      `--add-data "src/gui/static:gui/static"` nella build.
