
# Kathará Lab Generator & Live Inspector

Versione modificata del progetto originale di
[sciro24](https://github.com/sciro24). Questa versione include controlli
statici aggiuntivi, strumenti per modificare i laboratori senza
rigenerarli e un'interfaccia web locale per ispezionare e testare i
laboratori in esecuzione.

Kathará Lab Generator permette di creare e gestire laboratori di rete
per [Kathará](https://www.kathara.org), generando i file di
configurazione necessari per router FRRouting, host Linux e server DNS e
WWW. Il programma include anche alcuni controlli sulle configurazioni e
strumenti per verificare il comportamento della rete quando i container
sono avviati.

Il programma può essere utilizzato senza una connessione a Internet. È
disponibile per Linux e Windows e può essere eseguito da una chiavetta
USB. Sui sistemi Linux è previsto anche un avvio alternativo per i
computer in cui non si dispone dei permessi di `root` o la cartella
`/tmp` non consente l'esecuzione dei binari.

## Indice

1.  [Funzionalità principali](#funzionalità-principali)
2.  [Avvio](#avvio)
3.  [Modalità terminale](#modalità-terminale)
4.  [Interfaccia web](#interfaccia-web)
5.  [Problemi comuni di Kathará e
    FRR](#problemi-comuni-di-kathará-e-frr)
6.  [Controlli prima della consegna](#controlli-prima-della-consegna)
7.  [Opzioni da riga di comando](#opzioni-da-riga-di-comando)
8.  [Struttura del progetto](#struttura-del-progetto)
9.  [Crediti](#crediti)

## Funzionalità principali

Un laboratorio Kathará richiede la preparazione di diversi file, tra cui
`lab.conf`, i file `.startup`, `daemons`, `frr.conf`, `named.conf` e le
eventuali zone DNS. Anche una piccola incongruenza, per esempio un nome
di dispositivo non valido o una policy BGP riferita a un oggetto
inesistente, può causare problemi difficili da individuare.

Il programma offre due modalità di lavoro:

-   **Terminale:** una procedura guidata consente di creare il
    laboratorio e configurare router, host e server. Dal menu delle
    opzioni è possibile intervenire successivamente sulla
    configurazione, per esempio aggiungendo policy BGP, sessioni iBGP,
    costi OSPF o deleghe DNS. Le modifiche ai file esistenti possono
    essere accompagnate da un confronto delle differenze e da una copia
    di sicurezza.
-   **Interfaccia web locale:** permette di consultare la topologia,
    controllare i file e confrontare la configurazione salvata con lo
    stato dei container. Quando il laboratorio è avviato sono
    disponibili anche test di connettività, controlli sulle sessioni di
    routing, traceroute e simulazioni di guasto dei collegamenti.

## Avvio

Il programma può essere avviato tramite gli eseguibili precompilati,
disponibili nella sezione *Releases* di GitHub, oppure direttamente dai
sorgenti Python. Per quest'ultima modalità è necessario Python 3.8 o
successivo. Non sono richieste librerie Python di terze parti.

### Linux

Per utilizzare il programma da una chiavetta USB, è possibile eseguire
lo script `avvia.sh`. È utile soprattutto sui computer dei laboratori
universitari: filesystem come FAT32 ed exFAT non conservano i permessi
di esecuzione e, in alcuni sistemi, `/tmp` è montata con l'opzione
`noexec`.

``` bash
# Menu interattivo
bash /media/$USER/<NOME_CHIAVETTA>/avvia.sh

# Avvio diretto dell'interfaccia web
bash /media/$USER/<NOME_CHIAVETTA>/avvia.sh --gui
```

Lo script controlla che Docker e Kathará siano disponibili e segnala se
l'utente non appartiene al gruppo `docker`. Copia poi il programma in
`~/.labgenerator` e utilizza `~/labs` come directory di lavoro. Se
l'eseguibile non può essere avviato, per esempio per un'incompatibilità
con la versione di GLIBC o per le restrizioni su `/tmp`, prova a
eseguire il programma tramite Python.

#### Avvio manuale

In alternativa, è possibile copiare l'eseguibile nella propria home e
avviarlo da lì:

``` bash
cp /percorso/labGenerator ~/
chmod +x ~/labGenerator
mkdir -p ~/labs
cd ~/labs
~/labGenerator
# Per aprire direttamente l'interfaccia web:
~/labGenerator --gui
```

Se `/tmp` non consente l'esecuzione dei programmi e compare un errore
come `failed to map segment`, si può indicare una directory temporanea
diversa:

``` bash
mkdir -p ~/.lg-tmp
TMPDIR=~/.lg-tmp ~/labGenerator
```

È anche possibile avviare direttamente il sorgente:

``` bash
cd ~/labs
python3 /percorso/repo/src/labGenerator.py --gui
```

### Windows

Aprire il Prompt dei comandi o PowerShell nella directory in cui si
desidera lavorare e avviare l'eseguibile:

``` powershell
C:\percorso\labGenerator.exe
C:\percorso\labGenerator.exe --gui
```

In alternativa, dai sorgenti Python:

``` powershell
python C:\percorso\repo\src\labGenerator.py --gui
```

**Nota:** Windows Defender può segnalare come sospetti alcuni eseguibili
creati con PyInstaller. Se succede, è possibile verificare il file e, se
si ritiene attendibile, aggiungere un'eccezione per la cartella oppure
avviare il programma dai sorgenti Python.

## Modalità terminale

Avviando il programma senza l'opzione `--gui` viene mostrato il menu
principale:

``` text
  1) Crea nuovo Laboratorio
  2) Importa file XML/JSON
  3) Genera file XML
  4) Testa Funzionamento (PING)
  5) Opzioni Laboratorio
  6) Interfaccia grafica (browser)
  0) Esci
```

### Creazione di un laboratorio

La voce **Crea nuovo Laboratorio** avvia una procedura guidata per
inserire i dispositivi e le relative configurazioni. Durante
l'inserimento sono disponibili due comandi:

-   `<` torna alla domanda precedente;
-   `<<` ricomincia la configurazione del dispositivo corrente.

Prima di scrivere i file su disco, il programma mostra un riepilogo dei
dati inseriti e chiede conferma.

La procedura gestisce questi tipi di dispositivi:

-   **Router FRR (`kathara/frr`):** supporta BGP, OSPF, RIP e routing
    statico, anche in combinazione. Genera `daemons`, `vtysh.conf`,
    `frr.conf` e il file `.startup`. Per i router collegati alla stessa
    LAN individua automaticamente i neighbor eBGP. Inoltre, evita di
    annunciare tramite BGP i collegamenti interni all'AS, che possono
    essere gestiti dall'IGP.
-   **Host (`kathara/base`):** consente di configurare una o più
    interfacce. Il gateway viene verificato rispetto alle subnet delle
    interfacce configurate.
-   **Server WWW (`kathara/base`):** genera la configurazione di rete,
    una pagina `index.html` di prova e l'avvio di Apache2.
-   **Server DNS (`kathara/base` e BIND9):** il primo server può essere
    configurato come root DNS, con SOA, record NS, deleghe dei TLD e
    glue record. Gli altri server possono essere configurati come
    autoritativi, con record `A`, `NS`, `CNAME` e `DELEGATION`, oppure
    come resolver ricorsivi con riferimento al root tramite record hint
    e configurazione `allow-recursion`. Al termine è possibile scegliere
    un DNS da assegnare agli altri host come resolver tramite
    `/etc/resolv.conf`.

Durante la creazione viene anche prodotto un file `<nome_lab>.xml`, che
contiene i metadati necessari per reimportare il laboratorio. Il file è
utile durante il lavoro, ma deve essere eliminato prima della consegna,
se non richiesto dalla traccia.

### Opzioni Laboratorio

La voce **Opzioni Laboratorio** permette di intervenire su un
laboratorio già creato, senza doverlo generare nuovamente. Le modifiche
vengono applicate ai file esistenti, cercando di preservare le
configurazioni già presenti.

  ---------------------------------------------------------------------------------------------
  Voce                    Operazione              Descrizione
  ----------------------- ----------------------- ---------------------------------------------
  1                       Imposta costo OSPF      Aggiunge `ip ospf cost <N>` all'interfaccia
                                                  selezionata.

  2                       Aggiungi policy BGP     Configura prefix-list in ingresso o in
                                                  uscita, Local Preference, MED, Access-list e
                                                  Route-map. Include anche le policy
                                                  Customer-Provider-Peer basate sulle regole di
                                                  Gao-Rexford e l'opzione Default-Originate,
                                                  anche in modalità *solo default*. Premendo
                                                  Invio senza inserire un valore si annulla il
                                                  sottomenu corrente.

  3                       Aggiungi loopback       Configura un indirizzo `/32` sull'interfaccia
                                                  `lo` e lo annuncia negli IGP attivi, non in
                                                  BGP. Se entrambi i router dispongono della
                                                  loopback, può configurare le sessioni iBGP su
                                                  questi indirizzi.

  4                       Ridistribuzione BGP     Consente di attivare, disattivare o filtrare
                          verso IGP               la ridistribuzione delle rotte BGP in OSPF o
                                                  RIP tramite
                                                  `redistribute bgp route-map eBGP`.

  5                       Assegna resolver DNS    Scrive `/etc/resolv.conf` sul dispositivo
                                                  selezionato, proponendo gli indirizzi dei
                                                  server DNS presenti nel laboratorio.

  6                       Aggiungi network BGP    Annuncia aggregati dell'AS, per esempio
                                                  `100.0.0.0/8`, oppure `0.0.0.0/0`. Può
                                                  proporre la rimozione delle subnet più
                                                  specifiche già annunciate.

  7                       Sessioni iBGP           Crea le sessioni iBGP mancanti tra i router
                          (full-mesh)             dello stesso AS. L'indirizzo del peer viene
                                                  ricavato dall'interfaccia raggiungibile
                                                  tramite il percorso IGP interno; non è quindi
                                                  necessario configurare `update-source`.

  8                       Riepilogo               Esegue i controlli statici e mostra le
                          configurazione          informazioni principali di ciascun
                                                  dispositivo: AS, network, costi, neighbor e
                                                  policy.

  9                       Delega DNS sul root     Aggiunge al file `db.root` la delega di un
                                                  dominio di primo livello, includendo record
                                                  NS e glue A.

  10                      Costi OSPF predefiniti  Imposta `auto-cost reference-bandwidth 100`
                          a 10                    sui router OSPF dell'AS. Il motivo è spiegato
                                                  nella sezione [Problemi comuni di Kathará e
                                                  FRR](#problemi-comuni-di-kathará-e-frr).

  11                      Modifica un dispositivo Permette di modificare IP, LAN, gateway, AS e
                                                  protocolli. È possibile rinumerare una LAN
                                                  aggiornando i dispositivi coinvolti e il file
                                                  XML, spostare un'interfaccia su un'altra LAN
                                                  oppure modificare direttamente il file
                                                  tramite un editor a righe. L'editor segnala
                                                  gli errori FRR e crea copie di sicurezza in
                                                  `.backup_labgenerator/`.

  12                      Default route           Gestisce le rotte predefinite per BGP
                                                  (`default-originate`), RIP (`route 0.0.0.0/0`
                                                  e `default-information originate`) e OSPF
                                                  (`default-information originate [always]`).
  ---------------------------------------------------------------------------------------------

## Interfaccia web

L'interfaccia web viene avviata con l'opzione `--gui` ed è
raggiungibile, per impostazione predefinita, all'indirizzo
`http://127.0.0.1:8765`. Il server è locale: l'interfaccia e le relative
risorse HTML, CSS e JavaScript sono fornite dal programma, senza dover
caricare librerie da Internet.

Dalla barra superiore si possono avviare o arrestare i laboratori
tramite `lstart` e `lclean`, oltre a rileggere i file di configurazione.
Prima dell'avvio, il programma controlla se il laboratorio è già in
esecuzione e, in quel caso, propone un riavvio pulito.

Sono inoltre mostrati alcuni avvisi relativi allo stato del laboratorio:

-   presenza del file XML dei metadati, che va rimosso prima della
    consegna;
-   modifiche ai file effettuate dopo l'avvio dei container, per le
    quali viene proposto il riavvio;
-   presenza di collegamenti lasciati spenti dopo una simulazione di
    guasto, con la possibilità di riattivarli.

L'interfaccia è suddivisa in sei schede.

### 1. Topologia

Mostra la rete attraverso un grafo interattivo. I router sono
raggruppati per AS e sono indicati i protocolli IGP utilizzati, le
subnet delle LAN e le interfacce dei dispositivi.

È possibile spostare i nodi, modificare la disposizione del grafo,
spostare la vista e utilizzare lo zoom. Le posizioni dei nodi vengono
conservate in `localStorage` e la topologia può essere esportata in SVG.

Selezionando un dispositivo si apre un pannello laterale dal quale è
possibile consultare i file di configurazione (`startup`, `frr.conf`,
`named.conf` e altri), eseguire comandi `vtysh` o `ip` e aprire un
terminale tramite `kathara connect`.

### 2. Riepilogo e controlli

Questa scheda raccoglie i controlli statici sulla topologia e sui file
di configurazione. Verifica, tra le altre cose, la presenza di
riferimenti FRR non validi e di alcune configurazioni mancanti.

Quando il laboratorio è acceso è disponibile anche il controllo della
sintassi di FRR tramite `vtysh --dryrun`. Il comando viene eseguito
all'interno dei container e consente di individuare le righe di
`frr.conf` che FRR non accetterebbe, senza modificare la configurazione
del router in esecuzione.

### 3. Interfacce

La scheda mostra in forma tabellare le interfacce di tutti i
dispositivi, con indirizzi IP, LAN di appartenenza, dispositivi
collegati, IGP, costi OSPF, sessioni BGP e relative policy.

Con **Confronta con il lab acceso** il programma interroga i container
tramite `ip -j addr` e confronta gli indirizzi effettivamente assegnati
con quelli indicati nei file. Viene controllato anche che le interfacce
risultino nello stato `UP`.

### 4. Test

I test di questa scheda richiedono che il laboratorio sia avviato.

-   **Raggiungibilità:** esegue ping paralleli tra i dispositivi e
    costruisce una matrice con l'esito dei test (`OK` o `KO`).
-   **Sessioni BGP e OSPF:** controlla lo stato dei neighbor,
    verificando che le sessioni BGP raggiungano `Established` e le
    adiacenze OSPF `Full`. La funzione di attesa della convergenza
    ripete il controllo ogni 15 secondi, fino a un massimo di 5 minuti.
-   **Ridistribuzione BGP verso IGP:** mostra lo stato della
    ridistribuzione e può individuare il problema di FRR descritto nella
    sezione successiva. Se necessario, permette di applicare nuovamente
    il comando tramite il pulsante **Riapplica**.
-   **Rotta verso una rete:** mostra la rotta selezionata da FRR con
    `show ip route <rete> json` e i percorsi BGP ricevuti con
    `show ip bgp <rete> json`. Per i percorsi BGP vengono riportati
    attributi come Local Preference, AS-Path e MED, insieme alle
    informazioni sul motivo della scelta del *best path*.
-   **Tabelle di routing:** presenta una matrice
    `Router × Reti del lab`, utile per individuare reti non
    raggiungibili o presenti soltanto attraverso rotte aggregate.
-   **Ping diagnostico:** consente di specificare l'indirizzo IP
    sorgente tramite `ping -I`. In caso di errore, il programma prova a
    distinguere tra assenza di una rotta e mancata pubblicazione in BGP
    della subnet sorgente, che può impedire il ritorno della risposta.
-   **Traceroute:** traduce gli indirizzi IP degli hop nei nomi dei
    router e nelle lettere delle LAN, mostrando il percorso anche sulla
    topologia. È possibile indicare un percorso atteso, verificare che
    il traffico passi per determinati nodi oppure che segua una sequenza
    esatta. Il controllo può essere esteso al percorso di ritorno e alla
    ricerca di eventuali routing loop.
-   **Guasto di un link:** permette di spegnere e riaccendere
    un'interfaccia con `ip link set ethX down/up`, così da verificare il
    comportamento dei percorsi alternativi senza modificare i file di
    configurazione.

### 5. Archivio

Crea un archivio `.tar.gz` o `.zip` del laboratorio. Il file XML dei
metadati e la directory `shared/` vuota vengono esclusi automaticamente.
Prima della creazione viene anche controllato che il nome dell'archivio
corrisponda a quello della cartella del laboratorio.

### 6. Registro

Mostra lo storico dei comandi Kathará e `vtysh` eseguiti
dall'interfaccia, con orario, comando e relativo esito.

## Problemi comuni di Kathará e FRR

Durante la preparazione dei laboratori possono presentarsi alcune
situazioni che non dipendono necessariamente da errori nella
configurazione scritta. Il programma include controlli e funzioni che
aiutano a individuarle.

### Costo OSPF predefinito

Nelle versioni recenti dell'immagine `kathara/frr`, la reference
bandwidth predefinita può portare il costo di un'interfaccia Ethernet a
`10000`, anziché a `10`, valore spesso utilizzato negli esercizi.

Questo può produrre un risultato inatteso. Per esempio, impostando
`ip ospf cost 90` su un collegamento che si vorrebbe rendere secondario,
il costo esplicito `90` risulta comunque inferiore a `10000` e il
collegamento può essere preferito.

Per uniformare i costi al valore atteso negli esercizi, il programma
segnala questa condizione nei controlli statici. La voce **Opzioni
Laboratorio → 10** applica `auto-cost reference-bandwidth 100` ai router
OSPF dell'AS, riportando il costo predefinito a `10`.

### Ridistribuzione BGP in RIP

Con FRR 10.5.3 può verificarsi un problema per cui, all'avvio del
container, `ripd` non registra correttamente verso `zebra` la
ridistribuzione BGP, anche se `redistribute bgp` è presente in
`frr.conf`.

La scheda **Test → Sessioni BGP e OSPF** controlla l'output di
`show zebra client`. Se non risultano rotte trasferite, viene proposto
il pulsante **Riapplica**, che esegue nuovamente `no redistribute bgp` e
`redistribute bgp`.

### Route-map e prefix-list non definite

FRR può accettare una configurazione in cui un neighbor fa riferimento a
una `route-map` o a una `prefix-list` inesistente. In questo caso la
sessione BGP può comunque raggiungere lo stato `Established`, ma i
prefissi possono essere scartati senza un messaggio evidente.

I controlli statici confrontano i riferimenti presenti in `frr.conf` con
le definizioni effettive e segnalano i nomi non trovati, indicando la
riga interessata e, quando possibile, una definizione dal nome simile.

### Router-ID OSPF dopo lo spegnimento di un'interfaccia

Se il Router-ID di un router OSPF coincide con l'indirizzo di
un'interfaccia che viene disattivata, FRR può selezionare un Router-ID
diverso. Questo cambiamento può interrompere la convergenza prevista
durante una simulazione di guasto.

La funzione di spegnimento di un link controlla il Router-ID prima e
dopo l'operazione. Se rileva una variazione, esegue
`clear ip ospf process`.

### Nomi dei dispositivi in `lab.conf`

Kathará non accetta tutti i caratteri nei nomi dei dispositivi. In
particolare, nomi con trattini, punti o lettere maiuscole, come
`web-srv`, possono causare un `SyntaxError` durante `lstart`.

Il wizard e l'importatore controllano i nomi e li normalizzano nel
formato `[a-z0-9_]+`. Quando si apre un laboratorio già esistente con
nomi non validi, viene proposta la rinomina dei dispositivi.

## Controlli prima della consegna

Prima di consegnare il laboratorio, è opportuno verificare i seguenti
punti:

-   [ ] **Nome della cartella e dell'archivio:** entrambi devono seguire
    il formato richiesto dalla traccia, ad esempio `<cognome><nome>` in
    minuscolo e senza spazi o caratteri speciali.
-   [ ] **Controlli statici e sintassi:** eseguire la voce **Opzioni
    Laboratorio → 8** oppure aprire la scheda *Riepilogo e controlli*.
    Verificare che non siano presenti errori e che `vtysh --dryrun` non
    segnali righe non valide.
-   [ ] **Convergenza:** con il laboratorio avviato, controllare che le
    sessioni BGP siano `Established` e le adiacenze OSPF `Full`.
-   [ ] **Ridistribuzione:** verificare che le eventuali ridistribuzioni
    BGP verso IGP siano effettivamente attive.
-   [ ] **Costi OSPF:** se la traccia richiede costi espliciti,
    controllare la reference bandwidth e, se necessario, utilizzare
    **Opzioni Laboratorio → 10**.
-   [ ] **Percorsi e raggiungibilità:** eseguire i ping e i traceroute
    richiesti, includendo eventuali prove con un collegamento
    disattivato.
-   [ ] **File XML:** eliminare `<cognome><nome>/<cognome><nome>.xml`,
    oppure creare l'archivio dalla scheda *Archivio*, che esclude
    automaticamente il file.
-   [ ] **Container:** arrestare e pulire i laboratori non più necessari
    con `kathara lclean`.

## Opzioni da riga di comando

Il programma accetta le seguenti opzioni:

``` text
python3 src/labGenerator.py [OPZIONI]

  --out <cartella>     Cartella di lavoro per creare e leggere i laboratori
                       (predefinita: directory corrente)
  --gui                Avvia l'interfaccia web
  --porta <n>          Porta HTTP locale della GUI su 127.0.0.1
                       (predefinita: 8765)
  --from-xml <file>    Genera un laboratorio da un file XML senza procedura guidata
  --from-json <file>   Genera un laboratorio da un file JSON senza procedura guidata
  --force              Con --from-xml o --from-json sovrascrive una cartella esistente
  --regen-xml <lab>    Ricrea il file XML a partire dai file di un laboratorio esistente
  --help               Mostra le opzioni disponibili
```

## Struttura del progetto

Il codice è organizzato in moduli. Le funzionalità principali utilizzano
esclusivamente la libreria standard di Python.

``` text
.
├── avvia.sh                     # Avvio portabile su Linux
├── FUNZIONI.txt                 # Descrizione delle voci di menu ed esempi BGP
├── LEGGIMI.txt                  # Istruzioni rapide per l'avvio offline
├── .github/workflows/
│   └── build-and-release.yml    # Compilazione Linux e Windows con PyInstaller
└── src/
    ├── labGenerator.py          # Entry point, argomenti e menu principale
    ├── core/
    │   ├── __init__.py          # Interfaccia pubblica del modulo
    │   ├── templates.py         # Template FRR, BIND9, Apache e file startup
    │   ├── cli_io.py            # Input, cronologia e validazione dei dati
    │   ├── file_utils.py        # Operazioni sui file, backup e diff
    │   ├── net_frr.py           # Calcolo subnet e configurazioni di routing
    │   ├── generators.py        # Generazione dei file per router, host e server
    │   ├── persistence.py       # Import/export XML e JSON e gestione dei nodi
    │   ├── analyzer.py          # Analisi dei file e controlli di configurazione
    │   ├── wizard.py            # Procedura guidata per creare un laboratorio
    │   ├── routing_ops.py       # Policy BGP, OSPF, iBGP e configurazione DNS
    │   └── device_editor.py     # Modifica dei dispositivi ed editor dei file
    └── gui/
        ├── __init__.py
        ├── dati.py              # Lettura e rappresentazione dello stato del lab
        ├── kathara.py           # Comandi Docker/Kathará e test di rete
        ├── api.py               # Stato del lab, Opzioni con anteprima e applica, creazione lab
        ├── server.py            # Server HTTP locale e controlli di sicurezza
        └── static/              # La pagina: index.html, css/, js/ (moduli) e js/componenti/
```

## Crediti

-   **Autore del progetto originale:**
    [sciro24](https://github.com/sciro24).
-   **Nota:** il programma è pensato per facilitare la creazione e la
    verifica di laboratori di rete con Kathará. Le configurazioni
    generate devono comunque essere controllate rispetto ai requisiti
    specifici dell'esercizio.
