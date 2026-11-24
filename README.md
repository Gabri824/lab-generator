
# Kathará Lab Generator & Live Inspector

Versione modificata del progetto originale di
[sciro24](https://github.com/sciro24). Questa versione aggiunge
un'interfaccia web completa, che si usa al posto del terminale o insieme
a lui, controlli statici e diagnostica dei file, modifica dei laboratori
già creati con anteprima e annullamento, e test sui laboratori in
esecuzione.

Kathará Lab Generator permette di creare e gestire laboratori di rete
per [Kathará](https://www.kathara.org), generando i file di
configurazione per router FRRouting, host Linux e server DNS e WWW.
Terminale e interfaccia web fanno le stesse operazioni con lo stesso
motore: un laboratorio creato o modificato da una parte si apre e si
modifica dall'altra, e i file scritti sono identici.

Il programma funziona senza connessione a Internet e usa solo la
libreria standard di Python. È disponibile per Linux e Windows e può
essere eseguito da una chiavetta USB, anche su computer in cui non si
hanno i permessi di `root` o la cartella `/tmp` non consente di eseguire
i programmi.

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

Un laboratorio Kathará richiede diversi file: `lab.conf`, i `.startup`,
`daemons`, `frr.conf`, `named.conf` e le zone DNS. Anche una piccola
incongruenza, per esempio un nome di dispositivo non valido o una policy
BGP che punta a una route-map inesistente, può causare problemi difficili
da trovare.

-   **Creare un laboratorio:** dal terminale con la procedura guidata,
    oppure nell'interfaccia web disegnandolo (router, host, server, LAN,
    riquadri AS, zone RIP e aree OSPF). Si può anche partire da un
    laboratorio esistente, per esempio la soluzione di un esame, e
    crearne uno nuovo senza perdere le righe già scritte.
-   **Modificare un laboratorio già creato:** IP, LAN, dispositivi,
    protocolli, costi OSPF, network e sessioni BGP, policy (local
    preference, MED, prefix-list, access-list, Customer-Provider-Peer),
    default route, ridistribuzione, loopback, resolver e deleghe DNS.
    Ogni modifica mostra prima le righe che cambiano, fa una copia di
    sicurezza e si può annullare, dal terminale o dalla GUI.
-   **Percorso voluto:** si disegna sulla topologia il percorso chiesto
    dalla traccia e il programma propone le policy BGP per ottenerlo.
-   **Controlli e diagnostica:** avvisi sulle dimenticanze tipiche e
    diagnostica di `frr.conf` (refusi, comandi nel blocco sbagliato, reti
    scritte male, route-map e prefix-list non definite, demoni spenti),
    con le correzioni proposte.
-   **Test sul laboratorio acceso:** raggiungibilità, sessioni BGP e
    OSPF, rotte, traceroute con percorso atteso e costi OSPF, guasto di
    un link, pagine web dai client, risoluzione dei nomi DNS lungo tutta
    la catena di server.

## Avvio

Il programma si avvia con gli eseguibili precompilati, nella sezione
*Releases* di GitHub, oppure direttamente dai sorgenti Python (Python 3.8
o successivo, nessuna libreria di terze parti).

### Linux

Da una chiavetta USB conviene usare lo script `avvia.sh`, pensato per i
computer dei laboratori universitari: filesystem come FAT32 ed exFAT non
conservano i permessi di esecuzione e, in alcuni sistemi, `/tmp` è
montata con l'opzione `noexec`.

``` bash
# Menu interattivo
bash /media/$USER/<NOME_CHIAVETTA>/avvia.sh

# Avvio diretto dell'interfaccia web
bash /media/$USER/<NOME_CHIAVETTA>/avvia.sh --gui
```

Lo script controlla che Docker e Kathará siano disponibili e segnala se
l'utente non appartiene al gruppo `docker`. Copia poi il programma in
`~/.labgenerator` e usa `~/labs` come cartella di lavoro. Se l'eseguibile
non parte, per esempio per la versione di GLIBC o per le restrizioni su
`/tmp`, prova ad avviare il programma con Python.

#### Avvio manuale

``` bash
cp /percorso/labGenerator ~/
chmod +x ~/labGenerator
mkdir -p ~/labs
cd ~/labs
~/labGenerator
# Per aprire direttamente l'interfaccia web:
~/labGenerator --gui
```

Se `/tmp` non consente di eseguire programmi e compare un errore come
`failed to map segment`, indica un'altra cartella temporanea:

``` bash
mkdir -p ~/.lg-tmp
TMPDIR=~/.lg-tmp ~/labGenerator
```

Dai sorgenti:

``` bash
cd ~/labs
python3 /percorso/repo/src/labGenerator.py --gui
```

### Windows

Apri il Prompt dei comandi o PowerShell nella cartella in cui vuoi
lavorare:

``` powershell
C:\percorso\labGenerator.exe
C:\percorso\labGenerator.exe --gui
```

Dai sorgenti:

``` powershell
python C:\percorso\repo\src\labGenerator.py --gui
```

**Nota:** Windows Defender può segnalare come sospetti alcuni eseguibili
creati con PyInstaller. In quel caso puoi verificare il file e, se lo
ritieni attendibile, aggiungere un'eccezione, oppure avviare il programma
dai sorgenti.

## Modalità terminale

Senza l'opzione `--gui` compare il menu principale:

``` text
  1) Crea nuovo Laboratorio
  2) Importa file XML/JSON
  3) Genera file XML
  4) Testa Funzionamento (PING, pagine web e apache2, nomi DNS)
  5) Opzioni Laboratorio
  6) Interfaccia grafica (browser)
  7) Crea archivio per la consegna
  0) Esci
```

### Creazione di un laboratorio

**Crea nuovo Laboratorio** avvia la procedura guidata. Durante
l'inserimento:

-   `<` torna alla domanda precedente;
-   `<<` ricomincia la configurazione del dispositivo corrente.

Prima di scrivere i file il programma mostra un riepilogo e chiede
conferma. I tipi di dispositivo sono:

-   **Router FRR (`kathara/frr`):** BGP, OSPF (anche con più aree e aree
    stub), RIP e rotte statiche, anche insieme. Genera `daemons`,
    `vtysh.conf`, `frr.conf` e lo `.startup`. Trova da solo i neighbor
    eBGP sulle LAN condivise e non annuncia in BGP i collegamenti interni
    all'AS.
-   **Host (`kathara/base`):** una o più interfacce, con il gateway
    controllato rispetto alle subnet.
-   **Server WWW (`kathara/base`):** rete, pagina `index.html` di prova e
    avvio di Apache2.
-   **Server DNS (`kathara/base` e BIND9):** root (SOA, NS, deleghe dei
    TLD con glue), server autoritativi (record `A`, `NS`, `CNAME`,
    `DELEGATION`) e resolver ricorsivi (hint della radice,
    `allow-recursion`, anche nella forma breve `0/0`). Alla fine si
    sceglie il resolver del laboratorio, scritto in `/etc/resolv.conf`.

I metadati del laboratorio (XML) vanno in `.labgenerator/<lab>/`, accanto
ai laboratori e fuori dalla cartella da consegnare.

### Opzioni Laboratorio

**Opzioni Laboratorio** modifica un laboratorio già creato senza
rigenerarlo: cambiano solo le righe interessate, il resto (policy e righe
scritte a mano) resta com'è. Ogni modifica mostra le differenze, chiede
conferma, fa una copia di sicurezza in `.backup_labgenerator/` e si può
annullare (voce 14).

| Voce | Operazione | Descrizione |
|---|---|---|
| 1 | Imposta costo OSPF | Costo di un'interfaccia; se c'è già lo sostituisce, `0` lo toglie. |
| 2 | Policy BGP | Prefix-list in ingresso o uscita, local preference (anche solo per alcune reti), MED, access-list, Customer-Provider-Peer (regole di Gao-Rexford), default-originate anche "solo la default". Invio senza valore annulla. |
| 3 | Loopback | Indirizzo `/32` su `lo`, annunciato negli IGP attivi; con le loopback su più router dello stesso AS anche le sessioni iBGP fra loopback. |
| 4 | Ridistribuzione BGP → IGP | Togli, rimetti o filtra (`redistribute bgp route-map eBGP`) la ridistribuzione in OSPF o RIP. |
| 5 | Resolver DNS | `/etc/resolv.conf` di un dispositivo, proponendo i server DNS del laboratorio. |
| 6 | Network BGP | Aggregato dell'AS, reti interne o `0.0.0.0/0`; propone di togliere le subnet già contenute nell'aggregato. |
| 7 | Sessioni iBGP | Le sessioni mancanti fra i router BGP dello stesso AS (full mesh). |
| 8 | Riepilogo | Controlli statici, configurazione di ogni router e diagnostica di `frr.conf`. |
| 9 | Delega DNS sul root | Delega di un dominio di primo livello in `db.root`, con NS e glue. |
| 10 | Costi OSPF predefiniti uguali | `auto-cost reference-bandwidth 100` su tutti i router OSPF di un AS (vedi [Problemi comuni](#costo-ospf-predefinito)). |
| 11 | Modifica un dispositivo | IP (anche solo l'ultimo numero), LAN (anche rinumerata), gateway, AS, protocolli, rinomina, editor a righe dei file. |
| 12 | Default route | BGP (`default-originate`), RIP e OSPF (`default-information originate`). |
| 13 | Aggiungi o togli un dispositivo | Router, host, server web o DNS su una LAN esistente, con le stesse domande della procedura guidata. |
| 14 | Annulla / copie di sicurezza | Annulla l'ultima modifica (anche fatta dalla GUI) o ripristina una copia di sicurezza. |
| 15 | Diagnostica e correggi `frr.conf` | Problemi numerati con le correzioni (1a, 1b, ...): refusi, comandi fuori blocco, reti con bit host, route-map e prefix-list non definite, demoni spenti, avvio di FRR o Apache2 mancante. `S` applica in blocco i fix sicuri. |
| 16 | Azzera il routing | `frr.conf` ridotto a intestazione e blocchi vuoti, rotte statiche dei router tolte; restano topologia, IP, demoni e host/WWW/DNS. |

Il menu **4 Testa Funzionamento** ha tre voci: comando ping da incollare,
pagine web e Apache2 dai client (con la spiegazione se non arrivano) e
risoluzione di un nome lungo la catena DNS (dai file, e con `dig` se il
laboratorio è acceso).

## Interfaccia web

L'interfaccia web si avvia con `--gui` (o con la voce 6) e risponde a
`http://127.0.0.1:8765`. Il server è locale e tutta la pagina è servita
dal programma, senza librerie da Internet.

Dalla barra in alto si avvia o ferma il laboratorio (`lstart`, `lclean`),
si rileggono i file e si annulla l'ultima modifica. Gli avvisi in alto
segnalano il file XML dentro il laboratorio, i file cambiati dopo l'avvio
dei container e i link lasciati spenti.

### Nuovo laboratorio (editor)

Con **+ Nuovo lab** si disegna il laboratorio: router, host, server WWW e
DNS, nodi LAN o link diretti, riquadri AS, zone RIP e aree OSPF (i
protocolli si ricavano da cosa sta dentro quale riquadro). Nomi, subnet e
IP sono proposti e modificabili; i controlli del motore compaiono mentre
si disegna. **Anteprima file** mostra i file prima di scriverli, **Crea
laboratorio** li scrive. La bozza resta nel browser e si esporta e
importa in JSON.

**Parti da un lab esistente** carica un laboratorio, dall'elenco o da una
cartella qualsiasi, come bozza. Il nuovo laboratorio va creato con un
altro nome: le righe che l'editor non mostra (policy, costi, pagine web,
righe in più degli startup) passano così come sono, e cambiano solo le
righe toccate dalla bozza.

### 1. Topologia

Grafo della rete con i router raggruppati per AS, gli IGP, le subnet e
le interfacce. I nodi si spostano, la disposizione si può cambiare e la
topologia si esporta in SVG. La barra dei **livelli** accende e spegne:
indirizzi, costi OSPF, sessioni BGP (iBGP e sessioni sbagliate in
evidenza), policy (sigle come `LP 150 in`, `MED 20 out` e frecce
Customer-Provider-Peer), segni sui router (`0/0`, ridistribuzione,
loopback), DNS (deleghe e resolver) e avvisi.

Il clic su un dispositivo apre il pannello con i file, la configurazione
in breve, i comandi `vtysh` e `ip`, ping, traceroute e il terminale
(`kathara connect`).

**Modifica** accende la modalità di modifica: un clic su
un'interfaccia, una LAN, la scritta di un AS o un dispositivo apre le sue
azioni (le stesse delle Opzioni del terminale). Ogni azione mostra
l'anteprima delle righe, poi **Applica**; dopo, l'esito propone il test
adatto. Ci sono anche:

-   **Policy BGP** dal router o dal link fra due AS, con
    Customer-Provider-Peer che propone subito il lato opposto;
-   **Percorso voluto:** si clicca sorgente, link o AS e destinazione e
    il programma propone local preference, MED o filtri, uno alla volta;
    a laboratorio acceso propone solo dove serve;
-   **Diagnostica** di ogni dispositivo, con un pulsante per ogni
    correzione e «Applica i fix sicuri»;
-   **Azzera il routing**, network BGP da togliere o cambiare, e la pulizia
    di quello che resta senza uso quando si toglie un dispositivo;
-   scheda **Pronto per la consegna** a semaforo in Riepilogo e Archivio;
-   **Annulla modifica** e le **copie di sicurezza** con il ripristino.

Il programma propone dove può (IP liberi, nomi, valori come 150 e 20),
ma il risultato non è una garanzia: va sempre verificato con i test.

### 2. Riepilogo e controlli

Controlli statici sulla topologia e sui file, controllo dei nomi in
`frr.conf`, diagnostica di `frr.conf` di tutti i dispositivi e, a
laboratorio acceso, sintassi FRR con `vtysh --dryrun` (senza modificare
il router). Sotto, la configurazione di ogni router.

### 3. Interfacce

Le interfacce di tutti i dispositivi con IP, LAN, vicini, IGP, costi
OSPF, sessioni BGP e policy. **Confronta con il lab acceso** confronta i
file con gli indirizzi reali dei container (`ip -j addr`) e lo stato
`UP`.

### 4. Test

Quasi tutti i test richiedono il laboratorio acceso.

-   **Raggiungibilità:** ping fra tutti i dispositivi, in una matrice.
-   **Sessioni BGP e OSPF:** `Established` e `Full`, con l'attesa della
    convergenza (ogni 15 secondi, al massimo 5 minuti) e lo stato della
    ridistribuzione, con **Riapplica** se serve.
-   **Server web:** stato di Apache2 sui server e pagine aperte da un
    client per IP e per nome, con la spiegazione se non arrivano (DNS,
    Apache2 spento, gateway, router senza rotta).
-   **Rotta verso una rete:** rotta scelta e percorsi BGP ricevuti, con
    local preference, AS path, MED e motivo della scelta.
-   **Tabelle di routing:** matrice router × reti del laboratorio.
-   **Ping:** con l'indirizzo sorgente scelto e la spiegazione se fallisce.
-   **Verifica percorso:** traceroute tradotto in router e LAN,
    evidenziato sulla topologia, confrontato con il percorso atteso
    (passa per, sequenza esatta, ritorno), con i costi OSPF delle
    interfacce attraversate.
-   **Risoluzione di un nome:** segue resolver, ricorsione, hint della
    radice, deleghe con glue e record A, e dice il primo anello che
    manca; funziona anche a laboratorio spento. A laboratorio acceso
    interroga con `dig` ogni server della catena.
-   **Guasto di un link:** spegne e riaccende un link con
    `ip link set ethX down/up` per vedere il percorso di riserva.

### 5. Archivio

Crea l'archivio `.tar.gz` o `.zip` del laboratorio, escludendo l'XML e i
file nascosti, e controlla che il nome dell'archivio corrisponda alla
cartella.

### 6. Registro

I comandi Kathará e `vtysh` eseguiti dall'interfaccia, con orario ed
esito.

## Problemi comuni di Kathará e FRR

### Costo OSPF predefinito

Il costo predefinito di un'interfaccia dipende dalla velocità che FRR
legge sul link. Misurato con Kathará sui link veth: **10** senza
auto-cost e **1** con `auto-cost reference-bandwidth 100`. Un costo
scritto a mano (per esempio `90` su un link da rendere secondario) va
quindi confrontato con i costi veri delle altre interfacce, che si
vedono con `show ip ospf interface` (pannello del router) e nella
Verifica percorso.

Il programma segnala i costi scritti a mano senza auto-cost. La voce
**Opzioni Laboratorio → 10**, o il menu dell'AS nella GUI, mette
`auto-cost reference-bandwidth 100` su tutti i router OSPF dell'AS, così
calcolano il costo predefinito allo stesso modo.

### Ridistribuzione BGP in RIP

Con FRR 10.5.3, all'avvio del container `ripd` può non registrare verso
`zebra` la ridistribuzione BGP, anche con `redistribute bgp` in
`frr.conf`. **Test → Sessioni BGP e OSPF** controlla `show zebra client`
e, se non passa nessuna rotta, propone **Riapplica** (`no redistribute
bgp` e `redistribute bgp`).

### Route-map e prefix-list non definite

FRR accetta un neighbor che punta a una `route-map` o `prefix-list`
inesistente: la sessione resta `Established` ma i prefissi vengono
scartati senza messaggi. I controlli statici e la diagnostica trovano i
nomi non definiti, indicano la riga e propongono la correzione quando c'è
una definizione dal nome simile. È il caso, per esempio, di una soluzione
d'esame con `trafficOut` usata e `trafficIn` definita.

### Router-ID OSPF dopo lo spegnimento di un'interfaccia

Se il Router-ID di un router OSPF è l'indirizzo di un'interfaccia che
viene spenta, FRR può sceglierne un altro e la convergenza prevista si
interrompe. Lo spegnimento di un link controlla il Router-ID prima e dopo
e, se cambia, esegue `clear ip ospf process`.

### Nomi dei dispositivi in `lab.conf`

Kathará non accetta nomi con trattini, punti o maiuscole (per esempio
`web-srv`): `lstart` dà `SyntaxError`. Procedura guidata, editor e
importazione controllano i nomi nel formato `[a-z0-9_]+`; aprendo un
laboratorio con nomi non validi viene proposta la rinomina.

## Controlli prima della consegna

-   [ ] **Nome della cartella e dell'archivio:** nel formato chiesto
    dalla traccia, per esempio `<cognome><nome>` in minuscolo, senza
    spazi né caratteri speciali.
-   [ ] **Controlli statici, diagnostica e sintassi:** **Opzioni
    Laboratorio → 8** o la scheda *Riepilogo e controlli*: nessun errore,
    e `vtysh --dryrun` senza righe non valide.
-   [ ] **Convergenza:** sessioni BGP `Established` e adiacenze OSPF
    `Full`.
-   [ ] **Ridistribuzione:** le ridistribuzioni BGP verso IGP passano
    davvero le rotte.
-   [ ] **Costi OSPF:** se la traccia dà dei costi, controlla i costi
    veri e, se serve, l'auto-cost (**Opzioni Laboratorio → 10**).
-   [ ] **Percorsi e raggiungibilità:** ping e Verifica percorso
    richiesti, anche con un link spento.
-   [ ] **Pagine web e nomi:** le pagine si aprono dai client e i nomi si
    risolvono (scheda *Test*).
-   [ ] **File XML:** fuori dal laboratorio (`.labgenerator/`); l'archivio
    creato dalla scheda *Archivio* lo esclude comunque.
-   [ ] **Container:** ferma i laboratori che non servono con
    `kathara lclean`.

## Opzioni da riga di comando

``` text
python3 src/labGenerator.py [OPZIONI]

  --out <cartella>     Cartella di lavoro per creare e leggere i laboratori
                       (predefinita: cartella corrente); anche --output
  --gui                Avvia l'interfaccia web
  --porta <n>          Porta HTTP locale della GUI su 127.0.0.1
                       (predefinita: 8765)
  --from-xml <file>    Crea un laboratorio da un file XML senza procedura guidata
  --from-json <file>   Crea un laboratorio da un file JSON senza procedura guidata
  --force              Con --from-xml o --from-json sostituisce una cartella esistente
  --regen-xml <lab>    Ricrea l'XML dei metadati dai file di un laboratorio
  --help               Mostra le opzioni disponibili
```

Un'opzione non riconosciuta viene segnalata e ignorata.

## Struttura del progetto

Il codice usa solo la libreria standard di Python. Il motore (`core/`) è
lo stesso per terminale e interfaccia web.

``` text
.
├── avvia.sh                     # Avvio portabile su Linux
├── FUNZIONI.txt                 # Descrizione delle voci di menu ed esempi
├── LEGGIMI.txt                  # Istruzioni rapide per l'avvio offline
├── docs/                        # Piano di lavoro, controlli della GUI, scalette di prova
├── .github/workflows/
│   └── build-and-release.yml    # Eseguibili Linux e Windows con PyInstaller
├── src/
│   ├── labGenerator.py          # Avvio, argomenti e menu principale
│   ├── core/
│   │   ├── templates.py         # Template FRR, BIND9, Apache e startup
│   │   ├── cli_io.py            # Input del terminale e validazione
│   │   ├── modello.py           # Modello del laboratorio: completamento e controlli
│   │   ├── generazione.py       # Creazione di un laboratorio dal modello (unica strada)
│   │   ├── generators.py        # File di router, host e server
│   │   ├── net_frr.py           # Subnet e configurazione del routing
│   │   ├── stato.py             # Lettura dei file di un laboratorio
│   │   ├── persistence.py       # XML/JSON e modello letto dai file
│   │   ├── analyzer.py          # Controlli statici e riepilogo
│   │   ├── frr_autofix.py       # Diagnostica di frr.conf con le correzioni
│   │   ├── operazioni.py        # Tutte le modifiche (terminale e GUI): anteprima e piano
│   │   ├── modifiche.py         # Scrittura dei piani con impronte e copie di sicurezza
│   │   ├── storia.py            # Storia delle modifiche e annulla
│   │   ├── unione.py            # Unione a tre vie per "Parti da un lab esistente"
│   │   ├── risoluzione.py       # Catena di risoluzione DNS e spiegazioni di dig
│   │   ├── web.py               # Server web, nomi e spiegazioni di links
│   │   ├── wizard.py            # Procedura guidata
│   │   ├── routing_ops.py       # Menu Opzioni del terminale
│   │   ├── device_editor.py     # Modifica dei dispositivi dal terminale
│   │   └── file_utils.py, archivio.py, supporto.py
│   └── gui/
│       ├── server.py            # Server HTTP locale e controlli di sicurezza
│       ├── api.py               # Opzioni con anteprima e applica, creazione, parti da un lab
│       ├── dati.py              # Dati del laboratorio per la pagina
│       ├── kathara.py           # Comandi Kathará e test di rete
│       ├── percorso_voluto.py   # Proposte di policy dal percorso disegnato
│       ├── terminale_web.py     # Test web e DNS del menu 4 del terminale
│       └── static/              # La pagina: index.html, css/, js/ (moduli), js/editor/, js/componenti/
└── tests/                       # Test Python, test JavaScript (Node) e piloti nel browser
```

I test si lanciano con `python3 -m unittest discover` dalla cartella
`tests/` e con `node --test tests/js/`.

## Crediti

-   **Autore del progetto originale:**
    [sciro24](https://github.com/sciro24).
-   **Nota:** il programma aiuta a creare e verificare laboratori di rete
    con Kathará. Le configurazioni generate vanno comunque controllate
    rispetto ai requisiti dell'esercizio.
