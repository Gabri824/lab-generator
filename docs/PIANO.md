# Piano: generatore bivalente terminale + GUI

Ramo di lavoro: `feat/gui-bivalente`, aperto da `dev/gabri`. Il `main` resta la versione
stabile e non si tocca. Il progetto torna su `dev/gabri` solo a fase stabile, con i test verdi.

---

## 1. Obiettivo

Il generatore deve permettere di **costruire e modificare un lab Kathará completo sia dal
terminale sia dalla GUI**, in modo intercambiabile: si crea in uno, si modifica nell'altro e si
torna indietro senza perdere nulla.

### Nella GUI

1. **Il lab si costruisce disegnandolo.** Guardando la traccia si mettono router, host, server
   WWW e DNS, si tirano i collegamenti (le LAN) e si assegnano indirizzi, subnet, AS e
   protocolli. Non si carica nessuna immagine.
2. **Gli errori si correggono sul disegno**: IP, collegamenti, AS. Su un lab già generato la
   correzione cambia solo le righe interessate, così policy e opzioni già applicate restano.
3. **Tutte le 12 Opzioni e tutte le policy**, costruite **in modo diverso dal terminale**: si
   parte dal disegno o dall'obiettivo della traccia ("il traffico deve passare da…", "questo host
   deve risolvere…"), si sceglie invece di scrivere e si vede l'anteprima delle differenze.
   **Il risultato nei file è identico** a quello del terminale.
4. **Le configurazioni si vedono sul disegno**, a livelli (indirizzi, sessioni BGP, policy, costi
   OSPF, DNS), da qualunque interfaccia siano state fatte.
5. **I test e i comandi Kathará restano tutti**: `lstart`/`lclean`, raggiungibilità, sessioni,
   convergenza, ridistribuzione con Riapplica, rotta verso una rete, tabelle di routing, ping
   diagnostico, traceroute con percorso atteso, guasto di un link, `vtysh --dryrun`, confronto
   con il lab acceso, archivio e registro. In più sono collegati alla costruzione: dopo una
   modifica si verifica subito il risultato.

### Nel terminale

Wizard e menu Opzioni restano completi, con le stesse domande di oggi, e lavorano anche su lab
creati o modificati dalla GUI.

### Regole di fondo

- **Un solo motore.** La logica che decide cosa scrivere è una sola. Terminale e GUI cambiano
  solo nel modo di raccogliere i dati.
- **I file del lab sono l'unica fonte di verità**: `lab.conf`, `.startup`, `frr.conf`, `daemons`,
  file di bind, `resolv.conf`. Entrambe le interfacce rileggono lo stato da lì ogni volta.
- **Prima vedi, poi scrivi.** Ogni modifica mostra le differenze, fa una copia di sicurezza e non
  sovrascrive file cambiati nel frattempo dall'altra interfaccia.
- **Controlli uguali ovunque.** Nella GUI compaiono anche sul disegno e sotto i campi.

### Vincoli

- Funziona offline e senza dipendenze: libreria standard di Python e JavaScript scritto a mano,
  senza CDN. Si avvia da chiavetta, su Linux e Windows, come eseguibile PyInstaller.
- La skill `design-taste-frontend` si usa solo nelle parti adatte a uno strumento di lavoro (vedi
  fase 3).
- **La cartella del lab contiene solo i file della configurazione** ed è sempre consegnabile così
  com'è. I file di supporto del programma stanno fuori (vedi sezione 3).

---

## 2. Stato attuale del codice (punti che il piano deve risolvere)

| Problema | Dove |
|---|---|
| Tre lettori dei file diversi, nessuno completo: il primo perde aree OSPF, network IGP, dettagli DNS e host con più interfacce | `rebuild_lab_metadata_and_export` ([persistence.py](../src/core/persistence.py)), `leggi_dispositivi` ([analyzer.py](../src/core/analyzer.py)), `leggi_lab` ([dati.py](../src/gui/dati.py)) |
| Domande (`input()`) e logica mescolate: circa 65 chiamate | `routing_ops.py` (34), `device_editor.py` (18), `wizard.py` (13) |
| Solo poche Opzioni passano dall'anteprima delle differenze; le altre scrivono direttamente | `_applica_modifiche` usata da `device_editor.py` e dalle due default route di `routing_ops.py` |
| Il menu Opzioni del terminale legge i router dall'XML, fermo alla creazione | `opzioni_laboratorio_menu` ([routing_ops.py](../src/core/routing_ops.py)) |
| Il wizard scrive un dispositivo alla volta, l'import XML tutto alla fine: due percorsi diversi | `esegui_wizard_nuovo_lab` ([wizard.py](../src/core/wizard.py)), `recreate_lab_from_data` ([persistence.py](../src/core/persistence.py)) |
| `recreate_lab_from_data` non gestisce il resolver e chiede conferma con `input()` | [persistence.py](../src/core/persistence.py) |
| Non si possono aggiungere o togliere dispositivi o interfacce a un lab esistente | nessuna funzione |
| L'XML sta dentro il lab e va cancellato prima della consegna | `export_lab_to_xml` |
| L'archivio di consegna esiste solo nella GUI | `crea_archivio` ([kathara.py](../src/gui/kathara.py)) |
| HTML, CSS e JS della GUI stanno tutti in una stringa (circa 1300 righe) | `pagina.py` (fase 3: ora [src/gui/static/](../src/gui/static/)) |
| Nessun test | — |

---

## 3. Decisioni prese

1. **File di supporto fuori dal lab.** Vanno accanto ai lab, come già le copie di sicurezza:

   ```
   ~/labs/
   ├── rossimario/                ← il lab: solo i file della configurazione
   ├── .backup_labgenerator/
   │   └── rossimario/            ← copie di sicurezza (esiste già)
   └── .labgenerator/
       └── rossimario/
           ├── disegno.json       ← posizioni del disegno (nuovo)
           └── rossimario.xml     ← XML dei metadati (spostato qui)
   ```

   - `disegno.json` contiene solo le posizioni di nodi e riquadri AS, lo zoom e i livelli
     attivi, nessuna configurazione. Se si perde, la GUI dispone i nodi in automatico.
   - L'XML diventa solo un'esportazione. L'import da XML accetta qualsiasi percorso.
   - Per i lab vecchi che hanno ancora l'XML dentro, il programma propone di spostarlo.
   - Se la cartella del lab viene rinominata, la GUI propone di riassociare i file di supporto.

2. **L'archivio di consegna resta come oggi**: `.zip` o `.tar.gz`, con il controllo che il nome
   dell'archivio sia uguale a quello della cartella del lab e con l'elenco degli esclusi mostrato
   prima della creazione. Le esclusioni restano anche se i file di supporto non sono più dentro
   il lab, come protezione:

   | Escluso | Perché |
   |---|---|
   | `<lab>.xml` | Lab vecchi che l'XML ce l'hanno ancora dentro |
   | `shared/` vuota | Come oggi |
   | File e cartelle nascosti (`.qualcosa`) | Nuovo |
   | `*~`, `*.swp`, `__pycache__` | Nuovo: residui degli editor |

3. **Ramo di lavoro** `feat/gui-bivalente`, da `dev/gabri`.

---

## 4. Decisioni aperte

| # | Domanda | Proposta |
|---|---|---|
| A | Ordine dei traguardi: prima "disegno e genero" o prima le Opzioni nella GUI con dei form? | Prima "disegno e genero" (fasi 0–4) |
| B | Gli obiettivi della traccia ("percorso richiesto", "risoluzione nome") anche nel terminale? | Solo nella GUI, almeno all'inizio |
| C | Il wizard da terminale scrive i file alla fine invece che un dispositivo alla volta? | Sì: per l'utente non cambia nulla e un'interruzione non lascia lab a metà |
| D | L'archivio di consegna anche da terminale (menu principale e post-creazione)? | Sì, con lo stesso codice della GUI |

---

## 5. Le fasi

**Come si chiude ogni fase** (deciso il 2026-11-22):

1. spiegazione della fase e via dell'autore ("procedi");
2. lavoro e verifiche automatiche (test, pilota in Chromium, confronto con Kathará);
3. commit e resoconto in questo piano;
4. **prova guidata dell'autore**: una lista breve sui lab veri (comando da lanciare, cosa fare,
   cosa si deve vedere), comprese le cose che non si provano in automatico (finestre sul
   desktop, uso a occhio). L'autore riporta cosa va e cosa no;
5. correzioni, se servono; la fase è chiusa solo dopo il via dell'autore.

### Fase 0: rete di test

Obiettivo: poter dimostrare che il refactor non cambia i file prodotti dal terminale.

**Materiale di partenza**

- **Lab reali generati e provati**, copiati in `tests/fixtures/labs/`: 17 lab da `~/labs` e da
  `cli-portable/test-output` (per `red_baron_test`, presente in entrambe, si usa la versione più
  recente di `~/labs`). Coprono BGP, OSPF, RIP, rotte statiche, route-map, prefix-list, local
  preference, MED, access-list, auto-cost, default-originate, redistribute bgp, iBGP su loopback
  e, con `tennis_test`, il DNS. Ognuno contiene ancora il suo XML.
- **Soluzioni ufficiali del corso** (`esercizi/lab-bgp`, 26 esercizi con `solution/` e
  `correction.json`). **Restano fuori dalla repo**: i test che le usano leggono il percorso dalla
  variabile d'ambiente `LABGEN_ESERCIZI` e vengono saltati se manca.
- **`confronta_lab.py`** (da `cli-portable/tools/`), che confronta un lab con la soluzione
  ufficiale. Si porta in `tests/strumenti/`.

**Struttura** (`unittest`, nessuna dipendenza):

```
tests/
├── fixtures/labs/<lab>/     ← lab reali (configurazione + XML)
├── scenari/<scenario>.txt   ← risposte al wizard, una per riga
├── attesi/
│   ├── lettura/<lab>.json   ← cosa restituiscono oggi i tre lettori
│   ├── rigenerazione/<lab>/ ← lab rigenerato oggi dal suo XML
│   ├── opzioni/<lab>.diff   ← differenza tra lab rigenerato e lab reale
│   └── scenari/<scenario>/  ← lab prodotto oggi dal wizard
├── strumenti/
│   ├── confronta_lab.py
│   └── aggiorna_attesi.py   ← rigenera i file attesi (da usare solo di proposito)
└── test_*.py
```

**I test**

| Test | Su cosa | Controlla |
|---|---|---|
| Lettura | Lab reali (e soluzioni, se c'è `LABGEN_ESERCIZI`) | Che i lettori restituiscano gli stessi dati di oggi. Poi il lettore unico dovrà leggere tutto, anche lo stile delle soluzioni scritte a mano. |
| Rigenerazione | XML di ogni lab reale | Che il lab rigenerato sia identico a oggi. Poi `genera_lab` dovrà dare lo stesso risultato. |
| Opzioni | Differenza tra lab rigenerato e lab reale | È quello che è stato aggiunto con le Opzioni: diventa l'obiettivo che terminale e GUI dovranno saper riprodurre. |
| Soluzioni | `confronta_lab.py` tra lab reale e soluzione ufficiale | Nessun KO nei controlli base (solo con `LABGEN_ESERCIZI`). |
| Scenari | Wizard con risposte scritte in anticipo | Le parti poco coperte dai lab reali: DNS (root, autoritativo, resolver, deleghe), host con più interfacce, aree OSPF stub. |

**Dettagli tecnici**

- Le risposte al wizard si simulano sostituendo `builtins.input`, da cui passa la funzione `input`
  di `cli_io.py`. Il codice non va toccato.
- Il serial delle zone DNS contiene la data (`generators.py`): nel confronto quella riga si
  normalizza.
- I file attesi si generano dal codice di questa repo, non dalla versione vecchia in
  `cli-portable`.

Comando: `python -m unittest discover tests` (con `LABGEN_ESERCIZI=<percorso>/lab-bgp` per i test
sulle soluzioni).

### Fase 1: motore unico (nessuna differenza visibile per l'utente)

1. **Lettore unico `core/stato.py`.** `leggi_stato(lab_path)` ricava dai file il modello completo:
   - dispositivi e tipo, interfacce, LAN con la loro subnet;
   - AS, protocolli, aree OSPF e stub, network IGP, ridistribuzione, rotte statiche, loopback;
   - costi OSPF, auto-cost, default route;
   - sessioni BGP (neighbor, remote-as, eBGP o iBGP) e policy collegate ai neighbor
     (route-map, prefix-list, access-list);
   - DNS: ruolo, zone, record, deleghe, resolver.

   Le righe che non riconosce le segna come "non comprese" e le modifiche non le toccano. I tre
   lettori di oggi diventano adattatori di questo.
2. **Modifiche come dati.** Un piano di modifica è
   `{modifiche: {file: (righe vecchie, righe nuove)}, note, errori}`.
   `scrivi_piano(lab_path, piano)` controlla che i file siano ancora quelli letti (altrimenti si
   ferma per conflitto), fa la copia di sicurezza, scrive e restituisce gli avvisi prima e dopo.
   Nel terminale `_applica_modifiche` diventa: stampa l'anteprima, chiede conferma, chiama
   `scrivi_piano`.
3. **Regole in `core/modello.py`.** `completa_lab` mette i valori proposti, cioè quelli che il
   terminale propone con Invio; `valida_lab` controlla. Ogni errore indica il campo a cui si
   riferisce:

   | Regola | Oggi si trova in |
   |---|---|
   | Nome valido per Kathará e unico, con proposta di correzione | `_chiedi_nome`, `correggi_nome_kathara` |
   | IP/CIDR valido e non già usato | `_chiedi_ip_libero` |
   | Protocolli ammessi; AS presente se c'è BGP | `valida_protocols`, `input_asn` |
   | Area OSPF valida; area di default dal primo router OSPF; stub | `input_area`, `p_area` |
   | Network IGP proposte | `default_igp_networks` |
   | Gateway nella subnet di un'interfaccia; interfaccia del gateway | `p_gw`, `p_gwdev`, `iface_for_nexthop` |
   | Destinazioni, next-hop e interfaccia delle rotte statiche | `input_destinazione`, `valida_gateway` |
   | DNS: primo DNS `root`, record A/NS/CNAME/DELEGATION, deleghe del root | `wizard_dns`, `_chiedi_zone` |
   | `allow-recursion` con `any` o un elenco di reti | `p_rec` |
   | Resolver scelto tra i DNS presenti | `esegui_wizard_nuovo_lab` |

4. **Un'unica funzione `genera_lab(base, nome, modello, sovrascrivi)`** per wizard, import XML e
   GUI. Scrive tutto alla fine: dispositivi, `lab.conf`, neighbor eBGP, pulizia delle network
   interne, resolver. Fa la copia di sicurezza se sovrascrive e restituisce gli esiti di
   `controlla_topologia` e `controlli_configurazione`.
5. **Le Opzioni separate dalle domande.** Ogni Opzione diventa `opzioni_X(stato)`, cioè cosa
   offrire, più `calcola_X(stato, parametri)`, che produce il piano di modifica. Il terminale fa
   le stesse domande di oggi e chiama queste funzioni. Si aggiungono le operazioni nuove
   **aggiungi o rimuovi dispositivo** e **aggiungi o rimuovi interfaccia**, con la loro voce
   anche nel terminale. Questo punto si può fare un'Opzione alla volta, insieme alla fase 5.
6. **Il terminale legge sempre dai file**: le Opzioni non dipendono più dall'XML.
7. **File di supporto fuori dal lab** (decisione 1): XML e `disegno.json` in
   `.labgenerator/<lab>/`, migrazione proposta per i lab vecchi.
8. **Archivio nel motore**: `crea_archivio` passa da `gui/kathara.py` al core, con le esclusioni
   della decisione 2. Test: l'archivio di un lab di prova contiene solo i file della
   configurazione. Se si conferma la decisione D, la voce va anche nel terminale.

### Fase 2: interfaccia del server

- `GET /api/stato_lab`: modello completo, disposizione del disegno e avvisi.
- `POST /api/azione`, con tre azioni generiche:
  - `opzioni`: cosa si può scegliere in un'operazione;
  - `anteprima`: il piano di modifica, mostrato come differenze;
  - `applica`: scrive, con l'impronta dei file letti per accorgersi dei conflitti.

  Più `anteprima_lab`, che genera il lab in una cartella temporanea e restituisce file e
  contenuti, e `crea_lab`.
- Le operazioni stanno in un elenco fisso, così il server esegue solo quelle previste. Il browser
  manda nomi e parametri, mai percorsi di file. Restano il collegamento solo su `127.0.0.1`, il
  controllo dell'host e l'header `X-Lab-Gen`.

### Fase 3: base della GUI

- HTML, CSS e JS da `pagina.py` a `src/gui/static/`. Nella build PyInstaller si aggiunge
  `--add-data "src/gui/static:gui/static"` (con PyInstaller 6 il separatore è `:` su tutti i
  sistemi; `--collect-data gui` non funziona, vedi il resoconto della fase 3).
- Dalla skill `design-taste-frontend` si prende solo:
  - componenti di base: colori, spaziature, raggi, pulsanti;
  - form: etichette visibili sopra i campi, errori sotto il campo giusto, una riga di stato;
  - animazioni leggere al passaggio del mouse e al clic, anello di focus, rispetto di "riduci
    movimento";
  - accessibilità: ogni controllo con un nome, titoli in ordine, navigazione da tastiera,
    contrasto;
  - i componenti `diff-review` e `terminal-run` come modelli per l'anteprima delle modifiche e
    l'output dei comandi;
  - i controlli di larghezza e ingombro (`check.mjs`, `shoot.mjs`) a 1440, 1024 e 768 px.

  Si lasciano fuori: una sezione per schermata, apertura da landing page, fotografie, effetti,
  animazioni legate allo scorrimento, palette estratte a caso, `copy-lint` e `gate.mjs`, che non
  va attivato. I file del kit si prendono solo nelle regole necessarie, perché pesano circa
  190 KB. Niente font esterni.
- Le sei schede attuali si rifanno con questa base senza cambiarne il funzionamento. Tutti i test
  e i comandi Kathará elencati nella sezione 1 diventano una lista di controllo da verificare a
  mano.
- Componenti comuni: pannello proprietà, anteprima delle differenze, elenco errori, interruttori
  dei livelli, annulla/ripeti.

### Fase 4: editor grafico per i lab nuovi

Primo traguardo usabile: **disegnare un lab e generarlo**.

1. La Topologia ha due modalità, "visualizza" e "modifica", e parte dal codice SVG attuale
   (`svgContenuto` e gestione di trascinamento e zoom in `static/js/topologia.js`).
   - Elementi del disegno: dispositivi (router, host, WWW, DNS), nodi LAN con lettera e subnet,
     collegamenti. Un collegamento diretto tra due router crea da solo una LAN /30.
   - I riquadri AS assegnano l'AS (e BGP) ai router che ci stanno dentro.
   - Il pannello proprietà ha una versione per ogni tipo di dispositivo, DNS compreso (ruolo,
     zone, record, deleghe, tipo per `.`, `allow-recursion`, DNSSEC). C'è anche la scelta del
     resolver finale.
2. IP assegnati in automatico (primo IP libero della subnet della LAN), rinumerazione dei membri
   quando cambia la subnet, interfacce `ethN` in ordine di collegamento e riordinabili. I
   controlli girano mentre si lavora (`anteprima_lab`) e gli errori compaiono sul disegno e nel
   pannello.
3. Tasti rapidi (`R`/`H`/`W`/`D` per aggiungere, `L` per collegare, `Canc` per eliminare),
   Ctrl+Z/Ctrl+Y, duplica, selezione multipla. La bozza resta salvata nel browser ed è
   esportabile e importabile in JSON. Si può partire da un XML esistente, con l'avviso che le
   Opzioni non sono nell'XML.
4. "Anteprima file", poi "Crea laboratorio", poi si passa alla modalità per i lab esistenti. Le
   voci del menu post-creazione diventano pulsanti: Genera XML, Raggiungibilità e comando ping,
   Opzioni.

Una bozza non ancora generata esiste solo nella GUI. Dalla generazione in poi il lab è lo stesso
per entrambe le interfacce.

Decisioni (2026-11-22):
- un elemento entra in una zona (AS, RIP, area OSPF) **per posizione**: si trascina dentro il
  riquadro; il pannello mostra a quali zone appartiene;
- nomi automatici dei router `as<AS>r<n>` dentro un riquadro AS, altrimenti `r<n>`; sempre
  modificabili;
- le subnet le scrive l'autore (sono date dalla traccia); "proponi subnet" riempie i link
  punto-punto lasciati vuoti;
- sottofasi: 4.1 modello della bozza, 4.2 editor di base, 4.3 zone, 4.4 pannello proprietà e
  controlli dal vivo, 4.5 anteprima, creazione, bozza salvata, JSON/XML e tasti rapidi. Ogni
  sottofase viene spiegata prima di farla.

### Fase 5: lab esistenti, modifica grafica e Opzioni nella GUI

- Ogni gesto sul disegno diventa un'operazione con anteprima delle differenze, invece di una
  rigenerazione:

  | Gesto | Operazione |
  |---|---|
  | Cambiare un IP | `modifica_ip_interfaccia` |
  | Spostare l'estremo di un collegamento su un'altra LAN | `sposta_interfaccia` |
  | Cambiare la subnet di una LAN | `rinumera_lan` |
  | Spostare un router in un altro riquadro AS | `cambia_as` |
  | Protocolli e gateway dal pannello | `modifica_protocolli`, `cambia_gateway` |
  | Aggiungere o togliere un dispositivo o un'interfaccia | operazioni nuove della fase 1.5 |

- Livelli sul disegno: indirizzi, sessioni BGP, policy, costi OSPF, albero DNS.
- Le 12 Opzioni in forma grafica, sempre con la stessa `calcola_X` del terminale:

  | # | Opzione | Nella GUI | Sul disegno |
  |---|---|---|---|
  | 1 | Costo OSPF | Clic sul lato del collegamento vicino al router, poi il costo | Costo sul collegamento |
  | 2 | Policies BGP | Dalla sessione BGP: local preference, MED, filtri con reti scelte da elenco o sul disegno, default-originate; Customer-Provider-Peer dal collegamento tra due AS | Frecce CPP come nei libri di testo, `LP`, `MED`, filtri |
  | 3 | Loopback | Clic sul router, /32 proposto, scelta dei router dello stesso AS per l'iBGP | Indirizzo sul router |
  | 4 | Ridistribuzione BGP → IGP | Interruttore sul router di confine, filtro con reti spuntate | Simbolo sul router di confine |
  | 5 | Resolver DNS | Linea dall'host al DNS, oppure più host selezionati | Linea tratteggiata |
  | 6 | Network BGP | Riquadro AS, "annuncia aggregato" già calcolato, casella per togliere le reti più specifiche | Reti annunciate per router |
  | 7 | iBGP full-mesh | Riquadro AS, "completa iBGP", con le sessioni mancanti mostrate prima di confermare | Sessioni iBGP tratteggiate |
  | 8 | Riepilogo | Errori e avvisi sul disegno, più la scheda Riepilogo | Elementi in rosso o giallo |
  | 9 | Delega DNS | Albero delle zone (`.` → `com` → `example.com`); glue ricavato dall'IP del server | Albero DNS |
  | 10 | Auto-cost | Interruttore sul riquadro AS | Avviso per costi espliciti senza auto-cost |
  | 11 | Modifica dispositivo | Sul disegno (tabella sopra); editor a righe con controllo FRR nel pannello | Disegno aggiornato |
  | 12 | Default route | Interruttore sulla sessione (BGP) o sul router (OSPF, RIP) | Simbolo `0/0` |

  Ordine di realizzazione: costi OSPF, auto-cost, loopback, network BGP, iBGP, default route,
  ridistribuzione, resolver, delega DNS, policy (local preference, MED, filtri,
  default-originate), Customer-Provider-Peer.

- **Si sceglie, non si scrive**: reti del lab, neighbor esistenti e server DNS si scelgono da
  elenchi o sul disegno, con i valori proposti già compilati.

### Fase 6: obiettivi della traccia e verifica

- **Percorso richiesto.** Si indicano sorgente, destinazione e i router da attraversare o da
  evitare. Il programma propone local preference (sul router dell'AS che decide), MED (verso
  l'AS vicino) o costi OSPF (dentro l'AS), spiegando il perché. Si applica solo con conferma e si
  verifica con il traceroute con percorso atteso che esiste già. Copre i casi tipici degli
  esercizi: è una proposta da confermare, non una garanzia.
- **Risoluzione di un nome.** Il programma controlla resolver e catena di deleghe e propone cosa
  manca. Serve un nuovo test DNS nel container: prima va verificato che `dig` sia disponibile in
  `kathara/base`.
- Dopo ogni operazione la GUI suggerisce il test adatto.

### Fase 7: collaudo, rifinitura e rilascio

- **Collaudo finale, fatto dall'autore prima del merge.** Un esercizio d'esame vero costruito da
  zero due volte, prima dalla GUI e poi dal terminale; ognuno modificato poi dall'altra parte;
  avvio con Kathará, test, confronto con la soluzione ufficiale (`confronta_lab.py`); archivio
  di consegna. I problemi trovati si annotano e si correggono prima di andare avanti.
- Controlli di larghezza e ingombro con `check.mjs` e `shoot.mjs`.
- Prova completa su Windows, anche con l'eseguibile.
- Aggiornamento di `README.md`, `FUNZIONI.txt` e `LEGGIMI.txt`.
- Unione su `dev/gabri`. Il passaggio al `main` lo decide l'autore.

---

## 6. Quando un'operazione è finita

Ogni operazione, vecchia o nuova, è finita solo se:

1. usa la stessa funzione `calcola_*` nel terminale e nella GUI;
2. ha il suo test golden e i test esistenti restano verdi;
3. nel terminale fa le stesse domande di prima;
4. nella GUI mostra l'anteprima delle differenze, poi scrive, poi rilegge il lab;
5. si accorge dei conflitti con modifiche fatte nel frattempo dall'altra interfaccia;
6. si vede sul disegno.

---

## 7. Avanzamento

### Fase 0: completata (2026-11-21)

- 17 lab reali in `tests/fixtures/labs/`, 3 scenari del wizard in `tests/scenari/`
  (`ospf_multiarea_statiche`, `bgp_ibgp_due_as`, `dns_root_auth_resolver`).
- File attesi generati dal codice attuale in `tests/attesi/`.
- `python -m unittest discover tests`: 6 test, meno di un secondo. Con `LABGEN_ESERCIZI`
  vengono eseguiti anche i 2 test sulle soluzioni ufficiali (15 lab abbinati a un esercizio).
- Verifica che i test se ne accorgano: cambiando la riga `redistribute connected` di OSPF nel
  generatore falliscono esattamente gli 8 lab e i 2 scenari con OSPF.

**KO noti rispetto alle soluzioni ufficiali** (registrati come stato di partenza, non dipendono
da errori del generatore):

| Lab | KO |
|---|---|
| `galaxy_mio` | La soluzione non dichiara l'immagine dei router (default `kathara/base`); scelte diverse sulle network BGP di `as1r3` (`0.0.0.0/0`) e `as2r5` |
| `left_spotlight_mio` | Refuso nella soluzione: `1.2.0.0./30` |
| `stairs_mio` | `as1r2` annuncia `1.0.0.0/24` invece dell'aggregato `1.0.0.0/8` |
| `tennis_test` | Indirizzi del link `as20r4`–`as2r1` diversi dalla soluzione (`.4/30` invece di `.0/30`) |

**Osservazioni da riprendere** (comportamento attuale, fotografato dai test così com'è):

- La proposta delle network IGP aggrega per primo ottetto. Nello scenario
  `ospf_multiarea_statiche`, `r2` (area `1.1.1.1` stub) riceve `network 10.0.0.0/8 area 1.1.1.1`,
  che copre anche il link verso `r1`, dichiarato in area `0.0.0.0`. È solo una proposta, ma
  `valida_lab` (fase 1.3) dovrebbe segnalarlo.
- I `resolv.conf` del resolver finale vengono scritti anche sui server DNS stessi.

### Fase 1.1: completata (2026-11-21)

- **`src/core/stato.py`**: `leggi_stato(lab)` legge ogni file una volta e restituisce il modello
  completo (dispositivi, LAN, sessioni BGP con policy, OSPF/RIP, costi, statiche, DNS), con la riga
  di ogni elemento e l'elenco delle righe non riconosciute. Ci si è spostata anche la lettura di
  `lab.conf` (`parse_lab_conf_for_nodes`).
- **Adattatori**, ciascuno nel suo commit, con i test della fase 0 identici:
  `analyzer.leggi_dispositivi` (e le zone DNS), `gui/dati.leggi_lab`,
  `persistence.rebuild_lab_metadata_and_export`.
- **Correzione delle perdite dell'XML rigenerato** (commit separato): ora contiene aree OSPF e
  stub, network IGP, `redistribute bgp` disattivato, rotte statiche (compresa la default dei
  router), loopback, network BGP aggiuntive, host con più interfacce e dati DNS (zone con i record
  com'erano scritti, tipo per `.`, allow-recursion, DNSSEC, deleghe del root). I router si
  riconoscono anche senza `[image]` in `lab.conf`, se hanno `frr.conf`.
- **Verifiche**:
  - nei 17 lab reali e nei 3 scenari nessuna riga non riconosciuta;
  - il modello di `frr.conf` coincide con `_analizza_frr` su 311 file, comprese le 26 soluzioni
    ufficiali;
  - nuovo test di andata e ritorno: XML rigenerato dai file → lab ricreato = lab di partenza, su
    20 lab (prima della correzione: 52 file diversi);
  - prova reale della GUI (pagina, elenco lab, dati, file) e del terminale (rigenerazione XML da
    riga di comando, Riepilogo del menu Opzioni);
  - 12 test in meno di un secondo.

**Limiti noti**

- Il resolver finale (`resolv.conf`) non si può salvare nell'XML: se ne occuperà `genera_lab`
  (fase 1.4).
- Un router con sole rotte statiche (senza FRR) è indistinguibile da un host: viene riletto come
  host con le sue interfacce e il gateway; le altre rotte statiche si perdono.
- ~~Con più aree OSPF sullo stesso router, l'XML ne conserva una sola~~: risolto nella fase 1.8.
- Nelle soluzioni ufficiali restano non riconosciuti solo comandi che il modello non descrive
  (`ip link set`, `bridge vlan add`, `ip link add`, `iptables`) e un refuso (`netwotk`): vengono
  conservati così come sono.
- Altre funzioni leggono ancora i file direttamente: le Opzioni (`routing_ops.py`,
  `device_editor.py`, `net_frr.py`, da convertire nella fase 1.5) e alcuni controlli di
  `analyzer.py` (`collect_lab_ips`, `controlla_topologia`, `isole_ospf`,
  `controlli_configurazione`, `riepilogo_configurazione`).

### Fase 1.2: completata (2026-11-21)

- **Prima i test, sul codice di prima**: 14 operazioni del menu Opzioni che passano da
  `_applica_modifiche`, eseguite con risposte scritte in `tests/operazioni/` (IP di un'interfaccia,
  anche annullata; rete di una LAN; sposta interfaccia; gateway; AS; aggiungi OSPF e BGP; togli
  RIP e BGP; editor a righe; default-originate; default in RIP e in OSPF). Per ognuna sono salvati
  i file cambiati (XML compreso) e il testo stampato.
- **`src/core/modifiche.py`**: `nuovo_piano`, `anteprima`, `scrivi_piano`, `Conflitto`.
  - Il piano gestisce file modificati, nuovi ed eliminati e ricorda l'impronta di ogni file letto.
  - `scrivi_piano` non scrive nulla se un file è cambiato dopo il calcolo; fa la copia di
    sicurezza fuori dal lab; scrive ogni file passando da un file temporaneo; mantiene gli
    startup eseguibili; restituisce i controlli risolti e quelli nuovi.
- **`_applica_modifiche`** ora è solo la parte del terminale (stampa, conferma, esito) sopra il
  nuovo modulo: i 14 test danno gli stessi file e lo stesso testo di prima. Caso nuovo: se un
  file cambia mentre si aspetta "Confermi?", scrive "Nel frattempo sono cambiati: …" e non tocca
  nulla.
- 20 test in poco più di un secondo; prova reale nel terminale (cambio del gateway di un host).

**Nota**: quando una di queste operazioni aggiorna l'XML lo riscrive per intero (cambia, per
esempio, `&quot;` in `"` dentro `lab_conf`). È il comportamento di prima, fotografato dai test;
l'XML uscirà dal lab nella fase 1.7.

### Fase 1.3: completata (2026-11-21)

- **`src/core/modello.py`**:
  - regole su un singolo valore (`errore_*`): restituiscono il messaggio, senza simboli, oppure
    None. Ci sono finite anche le regole pure che stavano in `cli_io.py` (nome Kathará valido,
    AS, area, lettura di un elenco di reti), che `cli_io` reimporta con lo stesso nome;
  - `completa_lab(modello)`: i valori proposti dove mancano (nomi, `ethN`, area OSPF ereditata dal
    primo router OSPF, network IGP, interfaccia di rotte statiche e gateway, tipo DNS);
  - `valida_lab(modello)`: elenco di problemi con campo e gravità. Errori = le regole del wizard;
    avvisi (non bloccano) = controlli nuovi: stub sulla backbone, IP di rete o broadcast, gateway
    di WWW e DNS fuori subnet, interfaccia di una rotta statica inesistente, LAN con subnet
    diverse, link /30 con un solo estremo, gateway che non è di nessun dispositivo, router che
    mettono la stessa LAN in aree OSPF diverse.
- **Terminale**: le domande del wizard e di `cli_io` usano le regole di `modello.py` con gli
  stessi messaggi di prima. Il riepilogo di ogni dispositivo mostra gli avvisi come righe
  `Avviso: ...` (testo semplice). Esempio: nello scenario OSPF, al riepilogo di `r2`, compare
  l'avviso sulle aree diverse nella LAN A.
- **Verifiche**: 14 test nuovi (messaggi identici a prima, domande che rifiutano e richiedono,
  lab pieno di errori voluti, avvisi tra dispositivi, valori proposti); i 17 lab reali e i 3
  scenari, trasformati in modello, non hanno errori e `completa_lab` non li cambia; prova reale
  del wizard dal menu principale. In tutto 34 test.
- **Emoji**: nel programma ci sono circa 130 stampe con emoji, già protette all'avvio
  (`reconfigure(errors='replace')`). L'unica dentro una domanda ("Esiste già. Sovrascrivere?")
  è stata tolta: in una domanda sposta il cursore su alcuni terminali. I messaggi nuovi non
  usano emoji.

### Fase 1.4: completata (2026-11-22)

- **`src/core/generazione.py`**: `genera_lab(base, nome, modello, sovrascrivi, lab_conf_testo,
  tollerante)`, unica strada per creare un lab (wizard, import, e poi GUI).
  - Controlla il modello con `valida_lab`: con errori non scrive nulla, salvo `tollerante`.
  - Costruisce il lab in una cartella temporanea accanto ai lab e lo sposta al suo posto solo
    alla fine. Se sostituisce un lab esistente ne fa prima la copia di sicurezza; se lo spostamento
    finale fallisce rimette il lab di prima; non lascia cartelle temporanee.
  - Non stampa: restituisce i messaggi dei generatori, con il percorso finale.
  - `lab.conf` nell'ordine del wizard (router, host, www, dns); resolver su host, www e DNS.
- **Wizard**: stesse domande e riepiloghi; i file si scrivono tutti alla fine. Se si interrompe
  non resta nulla su disco, e un lab da sostituire resta com'era fino alla fine.
- **Import** (menu e `--from-xml/--from-json`): passa da `genera_lab`, resta tollerante
  (mostra i problemi dei dati e crea comunque); anche `--force` ora fa la copia di sicurezza.
- **XML**: nuovo campo `<resolver>`, scritto dal wizard, dalla rigenerazione dai file (se tutti
  host, www e DNS hanno lo stesso nameserver ed è un DNS del lab) e conservato quando le Opzioni
  aggiornano l'XML. L'import lo legge (`leggi_resolver`). Il test di andata e ritorno non ha più
  eccezioni.
- **Verifiche**: scenari e rigenerazioni con gli stessi file di prima (unica differenza: la riga
  `<resolver>` nell'XML dello scenario DNS); 10 test nuovi (creazione, sostituzione con copia,
  errori, guasto a metà, spostamento finale fallito, wizard interrotto, resolver, ordine di
  `lab.conf`); prove reali dal terminale (creazione, sovrascrittura, import da menu e con
  `--force`). In tutto 44 test.

### Fase 1.5: in corso

Decisioni: anteprima e conferma per tutte le Opzioni; pausa dopo ogni gruppo; operazioni nuove
nella voce 13 del menu Opzioni ("Aggiungi o togli un dispositivo") e dentro Modifica dispositivo.

**Aggiunta al gruppo D: "rinomina dispositivo"** (terminale: dentro Modifica dispositivo; GUI:
doppio clic sul nome). Rinomina file e cartella (eliminati e ricreati nello stesso piano),
aggiorna `lab.conf` e i riferimenti negli altri file (`description Router <nome>` sui vicini,
`hostname` in `vtysh.conf`, record DNS), con anteprima, conferma e copia di sicurezza. La
correzione automatica dei nomi non validi (`correggi_nomi_lab`) userà la stessa operazione.

**Gruppo A completato (2026-11-22)**: costo OSPF, auto-cost, loopback, network BGP, iBGP
full-mesh, default route (BGP, RIP, OSPF).
- `src/core/operazioni.py`: `opzioni_X` / `calcola_X` per ognuna, elenco `OPERAZIONI`,
  `ErroreOperazione`. Le decisioni si prendono dal lettore unico, non dall'XML.
- `file_utils.file_virtuali`: copia dei file in memoria. Gli aiutanti di scrittura
  (`insert_lines_into_protocol_block`, `append_frr_stanza`, `_rimuovi_righe`, ...) passano da
  `_leggi_testo` / `_scrivi_testo` / `_esiste_file`, così `calcola_X` fa girare la logica di
  sempre senza toccare il disco.
- Terminale: stesse domande; ora anteprima, conferma e copia di sicurezza anche per costo OSPF,
  auto-cost, loopback, network BGP e iBGP (prima scrivevano subito). La vecchia domanda
  "Confermi? (S/n)" dell'auto-cost è sostituita dalla conferma dell'anteprima.
- Verifiche: 9 operazioni nuove catturate sul codice di prima; dopo la separazione i file prodotti
  sono identici (cambia solo il testo stampato). Test nuovo: per 12 operazioni la strada della GUI
  (`calcola_X` + `scrivi_piano`) produce gli stessi file del terminale. 48 test.
- Da notare (comportamento di prima, ora visibile nell'anteprima): il costo OSPF aggiunge sempre
  un nuovo blocco `interface`, anche se l'interfaccia ha già un costo; le scritture con
  `_scrivi_righe` tolgono le righe vuote doppie, e l'anteprima lo mostra.

**Gruppo B completato (2026-11-22)**: ridistribuzione (togli e rimetti `redistribute bgp`,
route-map eBGP), resolver, delega DNS.
- `calcola_redistribuzione`, `calcola_redistribuzione_route_map`, `calcola_resolver`,
  `calcola_delega_dns` (con le relative `opzioni_*`), aggiunte a `OPERAZIONI`.
- Terminale: stesse domande, ora con anteprima, conferma e copia di sicurezza. Il resolver non
  crea più cartelle prima della domanda (restavano vuote se si annullava); tolti due rami che non
  si potevano raggiungere.
- Verifiche: 8 operazioni catturate sul codice di prima, file identici dopo la separazione; la
  strada della GUI dà gli stessi file per 6 di esse (le altre 2 non scrivono nulla). 49 test.
- **Difetto trovato nei controlli** (esisteva già): `riferimenti_frr` riconosce
  `match ip address prefix-list` ma non `match ip next-hop prefix-list`, quindi dopo la
  route-map eBGP segnala per sbaglio "prefix-list myNeighbors definita ma non usata". Da
  correggere a parte (cambia gli avvisi registrati nei test).
- Da notare (comportamento di prima): la route-map eBGP inserisce una riga di soli spazi prima
  di `redistribute bgp route-map eBGP`.

- **Corretto** (commit a parte): `riferimenti_frr` riconosce anche `match ip next-hop prefix-list`
  e `match ip next-hop <access-list>`; spariti i falsi avvisi su smile_test e dopo la route-map
  eBGP. Test in `tests/test_controlli.py`.

**Gruppo C completato (2026-11-22)**: policy BGP (prefix-list, local preference, MED,
access-list) e Customer-Provider-Peer.
- `calcola_policy(stato, router, neighbor, tipo, direzione, reti, valore, asn_nuovo)` e
  `calcola_cpp(stato, router, vicino, ip, asn, relazione, reti_out)`, con `opzioni_policy`.
- Le righe che la logica stampa con ⚠️ (route-map sostituita, lista diversa già collegata al
  neighbor, neighbor creato, nessuna rete annunciata) diventano note dell'anteprima: si leggono
  prima di confermare. Se un piano non cambia nulla, il terminale mostra il messaggio della logica.
- Customer-Provider-Peer: il neighbor mancante non viene più scritto prima della domanda sulla
  relazione (prima restava aggiunto anche se la scelta era sbagliata); ora si scrive tutto alla fine.
- Verifiche: 12 operazioni catturate sul codice di prima, file identici dopo la separazione; la
  strada della GUI dà gli stessi file per tutte e 12. 53 test.
- **Codice morto trovato**: `aggiungi_relazioni_bgp_menu` (routing_ops) ed
  `ensure_neighbor_exists` (net_frr) non vengono chiamate da nessuna parte.

**Gruppo D completato (2026-11-22)**: Modifica dispositivo e rinomina dispositivo.
- `calcola_ip_interfaccia`, `calcola_rinumera_lan` (con `proposta_rinumera_lan` per gli IP da
  scegliere a mano), `calcola_sposta_interfaccia`, `calcola_gateway`, `calcola_as`,
  `calcola_aggiungi_protocollo`, `calcola_togli_protocollo`, `calcola_righe`, `calcola_rinomina`.
- Queste operazioni aggiornano anche l'XML dopo la scrittura, come prima: il piano porta la
  trasformazione in `piano['xml']`; il terminale la applica in `_esegui_piano`, la GUI con
  `operazioni.dopo_scrittura`.
- Terminale: stesse domande, stesso ordine e stesso testo stampato di prima (passavano già
  dall'anteprima). Nuova voce "Rinomina il dispositivo" in Modifica dispositivo; dopo la
  rinomina il menu prosegue sul nome nuovo.
- **Rinomina**: lab.conf, cartella e file `<nome>.*` (eliminati e ricreati), `hostname` in
  `vtysh.conf`, `neighbor ... description` sui vicini, XML. Si ferma se la cartella contiene file
  non di testo. L'anteprima mostra i file spostati come "nuovo (era vecchio)" con le sole righe
  cambiate; `scrivi_piano` toglie le cartelle rimaste vuote. `correggi_nomi_lab` (nomi non validi
  all'apertura) usa la stessa operazione, con la copia di sicurezza.
- Verifiche: 7 operazioni in più catturate sul codice di prima; le 18 operazioni di Modifica
  dispositivo danno gli stessi file e lo stesso testo; la strada della GUI dà gli stessi file
  del terminale, XML compreso, per 17 casi (rinomina compresa); test su nomi non validi, nomi già
  usati, file non di testo, correzione automatica di `as60-r1`. 57 test.

**Gruppo E completato (2026-11-22)**: operazioni nuove e controlli sul lettore unico.
- **Opzioni 13 "Aggiungi o togli un dispositivo"**. Aggiungi router, host, www o dns con le stesse
  domande del wizard (nomi e IP del lab già noti, area OSPF ereditata, avvisi nel riepilogo).
  Router BGP: sessioni reciproche con i router BGP sulle sue LAN e pulizia delle network interne
  solo sul router nuovo (non si rifanno i passi automatici su tutto il lab). Host/www/dns: resolver
  del lab proposto. Togli: righe di `lab.conf`, file e cartelle, neighbor sugli altri router; note
  su chi lo usava come gateway o resolver.
- **Modifica dispositivo**: "Aggiungi un'interfaccia" (prima `ethN` libera, IP controllato nella
  rete della LAN) e "Togli un'interfaccia" (le successive scalano, `eth2 -> eth1`, in `lab.conf`,
  startup e `frr.conf`; tolti i neighbor non più raggiungibili, da entrambi i lati; nota sulle
  network che coprono ancora la rete). Le voci nuove stanno dopo "Sposta un'interfaccia": i
  numeri delle voci successive del menu sono scalati.
- **Controlli e Riepilogo**: `controlla_topologia`, `isole_ospf`, `controlli_configurazione`,
  `controlli_host`, `collect_lab_ips`, `riepilogo_configurazione` usano il lettore unico; gli
  avvisi dopo una scrittura e la GUI leggono il lab una volta sola. I dati del Riepilogo per la
  GUI sono quelli di `gui/dati.leggi_lab` (già sul lettore unico).
- Verifiche: 6 operazioni nuove dal terminale, tutte con la strada della GUI che dà gli stessi
  file (XML compreso); errori (nome o IP già usati, IP fuori rete, unica interfaccia); IP del ping,
  gruppi OSPF e stampa del Riepilogo catturati prima del riordino e identici dopo; prove reali dal
  menu e del server della GUI. 58 test.
- Leggono ancora i file direttamente, di proposito: la logica di scrittura delle Opzioni (per
  calcolare le differenze passa dal livello `_leggi_testo`, che lavora anche in memoria),
  l'elenco dei file di testo per le sostituzioni di IP, il ripristino delle copie di sicurezza e
  la visualizzazione dei file nella GUI.

### Fase 1.5: completata (2026-11-22)

Tutte le Opzioni hanno `opzioni_X` / `calcola_X` in `core/operazioni.py`, raccolte in
`OPERAZIONI`; terminale e GUI producono gli stessi file.

### Fase 1.6: completata (2026-11-22)

- `routing_ops.routers_dai_file`: i router (protocolli, AS, interfacce, aree...) dal lettore unico.
  I menu con un ciclo (Opzioni, Policies, Default route, Ridistribuzione, Dispositivi,
  post-creazione, Modifica dispositivo) li rileggono a ogni giro: dopo ogni operazione e anche
  dopo le modifiche fatte dalla GUI o a mano.
- Aprire le Opzioni (menu 5) non crea e non legge più l'XML. L'XML si crea con "Genera file XML"
  e resta aggiornato dalle operazioni che lo aggiornavano già (fino alla fase 1.7).
- Tolti gli aggiornamenti a mano dei dati in memoria dopo network BGP, loopback e
  ridistribuzione: al giro dopo i dati vengono dai file.
- Verifiche: le 71 operazioni registrate, fatte partire dai router ricavati dai file, danno gli
  stessi file e lo stesso testo; test nuovi: BGP aggiunto solo nei file viene visto dal menu
  delle policy (con i dati dell'XML il test fallisce), aprire le Opzioni su un lab senza XML non
  crea l'XML e non cambia nessun file; prova reale wizard -> post-creazione -> Opzioni ->
  Riepilogo. 60 test.

### Fase 1.7: completata (2026-11-22)

Decisioni: XML rigenerato dai file dopo ogni scrittura (tolte le trasformazioni delle singole
operazioni); per i lab vecchi si chiede di spostare l'XML all'apertura delle Opzioni; archivio
anche dal terminale (decisione D).
- **`src/core/supporto.py`**: `cartella_supporto`, `percorso_xml`, `percorso_disegno`,
  `xml_nel_lab`, `sposta_xml_fuori`. L'XML sta in `<cartella dei lab>/.labgenerator/<lab>/`;
  `disegno.json` avrà lo stesso posto (lo scriverà la GUI nella fase 4).
- **XML sempre allineato ai file**: rigenerato (in silenzio) dopo la creazione, dopo ogni Opzione
  dal terminale (`_esegui_piano`) e dalla GUI (`operazioni.dopo_scrittura`), dopo un ripristino.
  `--regen-xml` e "Genera file XML" lo scrivono nello stesso posto. Tolte `_aggiorna_xml`,
  `_xml_sostituisci` e le trasformazioni `piano['xml']`.
- **Lab vecchi**: aprendo le Opzioni, se l'XML è dentro il lab si propone di spostarlo (copia di
  sicurezza; se fuori ce n'è già uno rigenerato, si tiene quello). La GUI lo segnala.
- **Archivio** in `src/core/archivio.py`, usato dalla GUI e dal terminale (voce 7 del menu
  principale, voce 4 del post-creazione). Esclusi: XML dentro il lab, `shared/` vuota, file e
  cartelle nascosti, `*~`, `*.swp`, `__pycache__`. Per un lab normale l'archivio è identico a
  quello di prima (verificato su tennis, `.tar.gz` e `.zip`).
- La voce 4 (comando ping) legge gli IP dai file, non più dall'XML.
- Verifiche: file attesi aggiornati con un controllo automatico che le sole differenze siano l'XML
  che non sta più nel lab e il messaggio "Esportato XML" non più stampato dalle operazioni; test
  nuovi su percorsi, XML rigenerato dopo una scrittura, spostamento dell'XML (diretto e dalle
  Opzioni, anche rifiutato), archivio (residui esclusi, entrambi i formati, dal terminale); prove
  reali (`--regen-xml`, Opzioni su un lab vecchio, voce 7, wizard + archivio, archivio dalla GUI).
  69 test.
- Da aggiornare nella fase 7: README, FUNZIONI.txt e LEGGIMI.txt dicono ancora che l'XML sta nel
  lab e va cancellato prima della consegna.

## Fase 1: completata (2026-11-22)

Il motore è unico per terminale e GUI: lettore unico dei file (`stato.py`), modifiche come piani
(`modifiche.py`), regole del lab (`modello.py`), generazione (`generazione.py`), tutte le Opzioni
come `opzioni_X` / `calcola_X` (`operazioni.py`), file di supporto fuori dal lab (`supporto.py`),
archivio (`archivio.py`).

### Fase 1.8: completata (2026-11-22) — OSPF con più aree per router

Aggiunta dopo la fase 1.7: nelle soluzioni d'esame puzzle, the-thing e clouds ci sono router di
confine (ABR) con 2 o 3 aree, e il generatore ne gestiva una sola per router (era tra i limiti
della fase 1.1). Serve anche all'editor grafico, dove le aree OSPF sono zone che contengono i link.
- Modello: `ospf_aree` = {rete: area} e `ospf_aree_stub` = aree stub; senza, tutte le reti stanno
  in `ospf_area` come prima.
- Generazione: `mk_ospf_stanza` scrive l'area di ogni rete e le aree stub; lettura dai file
  (`dati_da_stato`) con tutte le aree; XML con `<ospf_aree>` e `<ospf_aree_stub>`.
- Controlli: aree valide per ogni rete; la stessa LAN nella stessa area per tutti i router (ora
  con l'area di ogni rete); con più aree, ogni area diversa dalla 0 deve toccare la backbone
  tramite un router di confine; niente stub sulla backbone. Messaggio esplicito per
  un'interfaccia senza IP (trovato un refuso `ip addres add` nella soluzione di puzzle).
- Terminale: "Tutte le network OSPF nell'area X? (S/n)" e, se no, l'area di ogni rete e quali
  aree sono stub; nel wizard e nell'aggiunta di OSPF (Modifica dispositivo). Il riepilogo del
  router mostra "router di confine: ...".
- Verifiche: i router OSPF delle tre soluzioni d'esame, rigenerati dal modello, hanno le stesse
  network con le stesse aree e le stesse aree stub (8 router di confine); scenario del wizard con
  un router di confine (anche nell'andata e ritorno XML); aggiunta di OSPF su due aree dal
  terminale e con la strada della GUI; test dei controlli nuovi. 76 test.

## Fase 2: completata (2026-11-22) — interfaccia del server della GUI

Nuovo modulo `src/gui/api.py`; `server.py` gli passa le azioni e tiene i comandi Kathará.
- `GET /api/stato_lab?nome=`: modello dei file (senza i testi), modello nel formato del wizard,
  disegno salvato, avvisi, XML ancora dentro il lab sì/no.
- `GET /api/operazioni`: le operazioni di `OPERAZIONI` con i parametri di `opzioni_X` e
  `calcola_X` (obbligatori e valori predefiniti), per costruire i moduli della GUI.
- `POST /api/azione`:
  - `opzioni`: cosa si può scegliere (`opzioni_X`);
  - `anteprima`: differenze file per file, note, impronte dei file e firma del piano;
  - `applica`: ricalcola il piano sui file di adesso e scrive solo se impronte e firma sono
    quelle dell'anteprima, altrimenti 409 con i file cambiati. Dopo la scrittura rigenera l'XML
    fuori dal lab e annota l'operazione nel Registro;
  - `valida_lab`: errori e avvisi del modello, più il modello completato con i valori proposti;
  - `anteprima_lab`: genera il lab in una cartella temporanea e restituisce i file;
  - `crea_lab`: se il lab esiste risponde `esiste` e serve `sovrascrivi` (copia di sicurezza
    prima); può salvare subito anche il disegno;
  - `sposta_xml` e `salva_disegno` (in `.labgenerator/<lab>/disegno.json`).
- Parametri in JSON: `assegnati` e `fissi` come liste `[dispositivo, interfaccia, ip]`, `rel`
  con `/` anche su Windows; le risposte hanno insiemi come liste e indirizzi come testo.
- Sicurezza: solo operazioni dell'elenco e solo i parametri della loro firma; dispositivi che
  devono esistere nel lab; LAN esistenti o con nome valido; nessun a capo o carattere di
  controllo nei testi; nomi di lab e dispositivi nuovi controllati prima di scrivere; ogni piano
  controllato perché tocchi solo file dentro il lab; corpo al massimo 4 MB; un'operazione del
  motore alla volta (le stampe sono raccolte per tutto il processo). Restano `127.0.0.1`, il
  controllo dell'Host e l'header `X-Lab-Gen`.
- Codici: 400 richiesta sbagliata, 409 conflitto, 413 troppo grande, 422 operazione non
  possibile con questi valori (messaggio per l'utente), 500 errore del programma.
- Verifiche (`tests/test_api.py`, server HTTP vero): 23 operazioni fatte con anteprima + applica
  danno esattamente i file della strada del terminale; conflitti (file cambiato, parametri
  diversi, impronte mancanti) senza scrivere nulla; richieste rifiutate; stato, disegno,
  spostamento dell'XML; lab nuovi (l'anteprima non scrive, si crea esattamente quello che
  l'anteprima mostra, lab esistente, nomi non validi, errori del modello). Ogni protezione è
  stata tolta una alla volta per controllare che un test se ne accorga. 99 test.

## Fase 3: completata (2026-11-22) — base della GUI

- **Pagina in file veri** (`src/gui/static/`): `index.html`, `css/` (base, layout delle schede,
  componenti), `js/` in moduli ES senza compilazione (comune, main, topologia, dispositivo,
  riepilogo, interfacce, test, archivio, registro). Il codice delle schede è quello di prima,
  diviso con uno script: le funzioni sono identiche, sono cambiati solo `import`/`export`, gli
  errori del server con il codice HTTP (`ErroreServer`, serve per il 409) e `aria-selected`.
  `pagina.py` è tolto.
- **Server**: consegna solo i file di `static/` con estensione prevista (niente `..`, file
  nascosti, collegamenti che escono), con `Content-Security-Policy` (la pagina esegue solo i
  propri script), `nosniff` e `no-referrer`.
- **Aspetto** (dalla skill solo le parti decise): variabili per colori, misure, raggi e
  movimento; pulsante principale pieno solo per "Avvia", gli altri tonali o a contorno;
  etichette sopra i campi; anello di focus subito visibile; "riduci movimento" rispettato;
  chiaro e scuro; Output come terminale con lo stato a pallino; contrasti corretti (verde,
  arancio e rosso più scuri nel chiaro, testo scuro sul rosso nello scuro).
- **Accessibilità**: "Vai al contenuto", schede con i ruoli `tab`/`tabpanel`, un nome per ogni
  campo, icona della scheda (prima: errore 404 su `favicon.ico`). Trovato e corretto un limite di
  prima: l'elenco dei lab non si raggiungeva da tastiera (ora sono pulsanti).
- **Componenti comuni** (`js/componenti/`, prova in `/static/prova.html`): anteprima delle
  modifiche (sulla risposta di `anteprima`, con conflitto e "nessuna modifica"), elenco errori
  (sulla risposta di `valida_lab`, porta al campo e mette l'errore sotto il campo), pannello
  proprietà da uno schema, interruttori dei livelli, annulla/ripeti con Ctrl+Z e Ctrl+Y.
- **PyInstaller**: provato davvero. `--collect-data gui` non includeva nulla (PyInstaller lo
  calcola prima di aggiungere `src` ai percorsi: "gui is not a package") e l'eseguibile
  rispondeva 404; con `--add-data "src/gui/static:gui/static"` l'eseguibile consegna la pagina
  (provato anche il comando esatto del workflow). Windows da provare nella fase 7.
- **Verifiche**:
  - `tests/test_pagina.py`: consegna e intestazioni, ogni file citato e ogni modulo importato
    esiste, ogni nome importato è esportato, niente script in linea, id cercati dal codice
    presenti, niente risorse esterne, percorsi rifiutati (anche i due controlli presi uno per
    volta), workflow che include la pagina; con Node: sintassi e test dei componenti
    (`tests/js/componenti.test.mjs`). Ogni controllo tolto apposta fa fallire un test.
  - `tests/strumenti/prova_gui.mjs` (Chromium senza finestra) e `confronta_gui.py`: con Docker e
    Kathará, 21 passi (lstart, convergenza, raggiungibilità, sessioni, rotta, tabelle, ping,
    percorso con ritorno, guasto di un link, sintassi, interfacce reali, comandi del
    dispositivo, file modificati, lclean, archivio, registro) sulla pagina vecchia e su quella
    nuova, su `papillon_mio` e `tennis_test`: stessi risultati (cambiano solo la forma delle
    etichette e i contatori dal vivo di FRR). Foto a 1440, 1024 e 768 in chiaro e scuro senza
    nulla che esce dallo schermo; tastiera: ordine del Tab e anello visibile.
  - Lista di controllo a mano: [CONTROLLI_GUI.md](CONTROLLI_GUI.md) ("Apri terminale" solo a
    mano). 110 test.

- **Prova guidata dell'autore (2026-11-22): superata**, sui lab veri (`~/labs/papillon_mio`). Emersi:
  - "Apri terminale" non trovava `foot` (problema di prima): ora prova il terminale di
    `~/.config/kathara.conf`, `$TERMINAL`, `xdg-terminal-exec` e una lista più ampia, ognuno con le
    sue opzioni, e passa al successivo se uno esce con errore (`tests/test_terminale.py`).
  - `--output` al posto di `--out` viene ignorato in silenzio: rimandato (sezione 8).

## Fase 4: completata (2026-11-22) — editor grafico per i lab nuovi

### Fase 4.1: completata (2026-11-22) — modello della bozza

- `src/gui/static/js/editor/bozza.js`: la bozza (il disegno come dati, versione 1) e
  `converti(bozza)`, che la traduce nel modello del wizard (`{routers, hosts, wwws, resolver}`).
  Gira nel browser, senza internet (come il resto della pagina) e con Node per i test.
  - Zone per posizione: AS e RIP sul centro del router, aree OSPF sul nodo della LAN o sul punto
    di mezzo del link diretto; router di confine con l'area di ogni rete, la backbone come area
    principale, le aree stub (mai la backbone).
  - Automatici: IP (prima i router, poi gli altri; niente rete, broadcast e IP presi; /31 e /32
    interi), subnet ricavata dal primo IP scritto, gateway dal primo router della LAN, nomi
    `as<AS>r<n>` / `r<n>` / `host<n>` / `www<n>` / `root` / `dns<n>`, lettere delle LAN fino a
    `AA`, `AB`...
  - Network IGP come il wizard (decisione 4.1): sui router con una sola area restano quelle
    proposte dal motore, sugli ABR le reti precise.
  - Problemi del solo disegno, legati all'elemento: subnet mancante o non valida o sovrapposta,
    IP fuori subnet, di rete/broadcast o doppio, link diretto senza due estremi, router in due AS,
    LAN in due aree, server con più interfacce, resolver che non è un DNS, nomi non validi o
    doppi, dispositivo non collegato (avviso).
  - Strumenti per l'editor: `rinumera` (nuova subnet, stessa parte host), `proponiSubnet` (/30
    libere dal blocco del lab, decisione 4.1: il pulsante funziona quando il blocco è scritto),
    `elementoDelCampo` (dal campo di `valida_lab` all'elemento del disegno).
- Scenario nuovo del wizard `ospf_abr_statiche`: `ospf_multiarea_statiche` non si può disegnare
  (la LAN A sta in due aree diverse, che `valida_lab` segnala come avviso); la variante ha la LAN
  A nella sola area 0 e r2 router di confine.
- Verifiche: quattro bozze (`tests/bozze/`) ridisegnano gli scenari del wizard e, generate per la
  strada della GUI (`api.crea_lab`), danno **esattamente** i file del wizard (`tests/test_bozza.py`);
  18 test con Node delle regole (`tests/js/bozza.test.mjs`); ogni regola tolta apposta fa fallire
  un test. 119 test Python (più quelli con Node).

### Fase 4.2: completata (2026-11-22) — editor di base

- "+ Nuovo lab" sopra l'elenco dei lab (o `#nuovo` nell'indirizzo) apre l'editor al posto della
  vista del lab; "Chiudi editor" torna indietro. La bozza resta in memoria finché la pagina è
  aperta (salvataggio nel browser: 4.5).
- Strumenti con i tasti: Router `R`, Host `H`, WWW `W`, DNS `D`, nodo LAN `N`, Collega `L`, Esc
  per Seleziona (e, su Seleziona, per togliere la selezione), Canc per eliminare, Ctrl+Z/Ctrl+Y.
- Decisioni 4.2: trascinare lo sfondo sposta la vista, Maiusc+trascinamento seleziona un'area,
  Maiusc+clic aggiunge alla selezione; un terzo dispositivo collegato a un link diretto lo
  trasforma in nodo LAN (stessa subnet e lettera); griglia di 20 px, disattivabile.
- Disegno con le icone e le etichette della Topologia (riusa le sue funzioni senza cambiarle); le
  etichette delle interfacce appartengono al loro link (un clic lì vale come sul link); IP
  automatici e lettere delle LAN dal vivo; elementi con errori cerchiati in rosso.
- Pannello semplice: nome del dispositivo, interfacce con LAN e IP (vuoto = automatico) e ordine
  eth0, eth1... (frecce); LAN con nome e subnet (cambiandola si rinumera); collegamento con IP;
  problemi del disegno; tasti.
- Codice: `js/editor/azioni.js` (azioni sulla bozza, solo dati), `disegno.js`, `editor.js`;
  `componenti/storia.js` ora accetta quando i tasti valgono (solo a editor aperto).
- Verifiche: 8 test con Node delle azioni (`tests/js/azioni.test.mjs`, ogni azione tolta apposta
  fa fallire un test); `tests/strumenti/prova_editor.mjs` in Chromium con mouse e tastiera veri
  disegna `ospf_abr`, scrive subnet e IP nel pannello e ottiene lo stesso modello della bozza di
  riferimento (senza zone); poi trascinamento con griglia, selezione ad area, eliminazione,
  terzo dispositivo, annulla e ripeti tutto, foto a 1440/1024/768 in chiaro e scuro. Le schede
  di prima restano identiche (`prova_gui.mjs`, ora con le parti comuni in `cdp.mjs`).
- Il pilota dell'editor si lancia a mano (circa un minuto): in Chromium senza finestra alcuni
  movimenti del mouse simulati aspettano 5 secondi la conferma del browser. Non dipende
  dall'editor (non cambia togliendo la cattura del puntatore) e non succede nel browser vero.

### Fase 4.3: completata (2026-11-22) — zone

- Strumenti AS (`A`), RIP (`I`), area OSPF (`O`): si trascina un rettangolo (un clic dà un
  riquadro 240x160); poi si torna a Seleziona con il valore della zona pronto da scrivere.
  Decisioni 4.3: AS da scrivere (errore finché manca), prima area proposta `0.0.0.0`, le altre da
  scrivere; si ridimensiona dai 4 angoli (lato minimo 40), si sposta dall'etichetta o dal bordo.
- Disegno: zone dietro a tutto (le più grandi sotto), il fondo lascia passare i clic; riquadri AS
  nel colore dell'AS e router dello stesso colore; RIP tratteggiata marrone, aree a trattini con
  "stub" nell'etichetta; segno "ABR" sui router di confine.
- Pannelli: zona con valore, stub, elenco di router o LAN e router di confine; router con i
  protocolli ricavati dalle zone; LAN con la sua area.
- `converti`: ogni zona controllata una volta (AS o area mancanti o non validi: errore; zona
  vuota: avviso); un AS non valido non dà BGP; restituisce i membri di ogni zona e i router di
  confine.
- Verifiche: test con Node delle zone (creazione, valori iniziali, ridimensionamento da ogni
  angolo, lato minimo, valore e stub, spostamento ed eliminazione, controlli in `converti`);
  ogni regola tolta apposta fa fallire un test. Il pilota disegna con mouse e tastiera le zone di
  `ospf_abr` e il lab `bgp_ibgp_due_as` (due AS, un'area, nomi scritti nel pannello) e ottiene
  **esattamente** il modello delle bozze di riferimento, che generano gli stessi file del wizard
  (unica differenza voluta: "redistribute bgp: no" di r1, che arriva con il pannello completo
  nella 4.4).

### Fase 4.4: completata (2026-11-22) — pannelli completi e controlli dal vivo

- Pannelli (`js/editor/pannelli.js`):
  - router: "ridistribuisci BGP nell'IGP" (solo con BGP e OSPF/RIP); network OSPF/RIP proposte
    dal motore e sovrascrivibili (decisione 4.4; vuoto = proposte, come Invio nel wizard; sui
    router di confine le decidono le aree); rotte statiche (rete, via, interfaccia);
  - host, WWW e DNS: gateway (vuoto = proposto dal router della LAN);
  - DNS: tipo per "." (master, hint, nessuno), deleghe dal root, zone con la tabella dei record
    (decisione 4.4: A, NS con glue, CNAME, DELEGATION), ricorsione e reti ammesse, "disattiva la
    validazione DNSSEC" (stesso significato del wizard: `dnssec-validation no`);
  - lab: resolver finale, blocco e "Proponi subnet".
- Un DNS nuovo parte con le impostazioni iniziali del wizard; le deleghe valgono solo per chi è
  master di "."; le zone DNS della bozza sono un elenco di righe, tradotto da `converti` nel
  formato del wizard.
- Controlli del motore dal vivo (decisione 4.4): 0,4 s dopo ogni modifica `valida_lab` (modalità
  "lab in costruzione"); errori e avvisi nel pannello del lab (clic = vai all'elemento), sotto il
  campo giusto e cerchiati sul disegno; le risposte vecchie si scartano e il testo che si sta
  scrivendo non viene toccato.
- Verifiche: test con Node delle proprietà e della traduzione (network scritte, record, deleghe,
  impostazioni iniziali del DNS); ogni regola tolta apposta fa fallire un test. Il pilota disegna
  con mouse e tastiera tre lab completi (`ospf_abr`, `bgp_ibgp_due_as` con la ridistribuzione
  tolta, e il lab DNS con router in zona RIP, host e server web con gateway, root con delega,
  autoritativo per `com` con i record, resolver con ricorsione e resolver del lab): i file che il
  server genera sono **identici** a quelli del wizard (14, 14 e 26 file). Un gateway sbagliato
  scritto apposta compare dal vivo con il messaggio del motore e sparisce dopo la correzione.
- La prova con Kathará del lab DNS (avvio, ping, risoluzione dei nomi) si fa a Docker acceso,
  insieme alla fase dei comandi web (sotto).

### Proposta da confermare (2026-11-22): comandi web e apache2

Idea dell'autore durante la 4.4, da fare dopo la fase 4 e la sua prova guidata, in GUI e
terminale:
- `links` sul client per vedere la pagina web (`links -dump http://<IP o nome>` nella GUI, che non
  è un terminale interattivo; dal vivo con `kathara connect`): verifica insieme routing, gateway,
  risoluzione dei nomi e server web;
- a lab acceso, controllo che apache2 sia attivo sui server WWW e, se no, avvio con
  `systemctl start apache2` senza cambiare i file (lo startup lo contiene già).
Verifica fatta (2026-11-22, Docker acceso): il lab DNS generato dalla bozza dell'editor
(`tests/bozze/dns_root_auth_resolver.json`, strada della GUI) si avvia con Kathará; dal client
`host1` il ping al server web risponde, `dig`/`host` risolvono `www.com` e `web.com` (CNAME)
tramite il resolver del lab, `dig +trace` mostra la catena root -> `com.` -> `www.com`, e
`links -dump http://www.com/` (anche per IP e per `web.com`) mostra la pagina "Server www1";
apache2 e bind attivi. In `kathara/base` ci sono `links`, `curl`, `wget`, `dig`, `host`,
`nslookup` (non `lynx` né `w3m`).

### Fase 4.5: completata (2026-11-22) — creare il lab

Decisioni (2026-11-22):
- alla creazione le posizioni del disegno e le zone vanno in `.labgenerator/<lab>/disegno.json`
  (nessuna configurazione) e la Topologia del lab le usa al posto della disposizione automatica;
- "partire da un XML" passa alla fase 5: trasformare un lab esistente in un disegno con le zone
  giuste è lo stesso lavoro della modifica grafica dei lab esistenti;
- dopo la creazione l'editor riparte da un foglio vuoto (il lab si modifica dalla sua vista;
  il JSON si può esportare prima);
- Ctrl+D duplica dispositivi e nodi LAN selezionati e i collegamenti tra loro, spostati di
  40 px, con nomi e IP automatici.

Fatto:
- "Anteprima file" (elenco dei file e contenuto, senza scrivere; errori del motore se il lab non
  si può creare) e "Crea laboratorio" (nome obbligatorio; se il lab esiste chiede conferma e fa
  la copia di sicurezza; poi apre il lab e scrive l'esito nell'Output).
- Bozza salvata nel browser a ogni modifica e ripresa alla riapertura; "Nuova bozza"
  (annullabile); esporta e importa JSON.
- `disegno.json` alla creazione (posizioni `d:<nome>` e `l:<LAN>`, zone); `GET /api/disegno`; la
  Topologia usa nell'ordine le posizioni spostate a mano, quelle del disegno, la disposizione
  automatica.
- Tasti: Ctrl+D duplica, Ctrl+A seleziona tutto, frecce spostano di un passo della griglia, `F`
  adatta la vista.
- Verifiche: test con Node di `duplica`; test di `GET /api/disegno`; il pilota disegna il lab DNS,
  apre l'anteprima (26 file), lo crea: i file su disco sono **gli stessi del wizard**, la
  Topologia mostra i dispositivi dove sono stati disegnati, l'editor riparte vuoto; importa un
  JSON e ricrea lo stesso lab (conferma e copia di sicurezza); bozza ripresa dopo il
  ricaricamento; Ctrl+D, Ctrl+A, frecce, Nuova bozza e annulla. Il pilota avvia Chromium con
  le opzioni che evitano il rallentamento delle schede "in sottofondo" (alcuni passi restano
  lenti: tutto il pilota dura circa 10 minuti).

## Fase 4: lavoro completato (2026-11-22) — prova guidata dell'autore fatta, fase chiusa

L'editor disegna un lab nuovo, con zone, pannelli completi e controlli dal vivo, e lo crea: i
file sono gli stessi del wizard (verificato su quattro lab e con Kathará sul lab DNS).

### Correzioni dalla prova guidata della fase 4 (2026-11-22)

Difficoltà trovate dall'autore ridisegnando papillon, e correzioni approvate:
- **Interfacce:** un menu `eth0`, `eth1`... nei pannelli del router, della LAN e del collegamento;
  scegliere un numero scambia le due interfacce (al posto delle frecce).
- **IP veloci:** il pannello della LAN elenca i dispositivi con interfaccia e IP; la parte fissa
  della subnet è già scritta e basta il numero finale (o le ultime due parti per le reti più
  grandi di una /24); vale anche nel pannello del router, senza scrivere la maschera
  (`completaIp`).
- **Nomi stabili** (cambia la decisione 4.1): il nome si dà quando si mette il dispositivo (`r1`,
  `host1`, `www1`, `dns1`, il primo libero) e non cambia più da solo, né entrando in un AS né
  eliminando altri router; "Rinomina i router come as20r1, as20r2..." nel pannello del riquadro AS,
  solo su richiesta.
- **BGP solo dove serve** (cambia la decisione 4.3): il riquadro AS dà l'AS a tutti i suoi router,
  BGP solo ai router di confine (collegati a un router fuori dal loro AS); "BGP su: tutti i
  router" nel riquadro per i lab con iBGP; eccezione per router (automatico, sì, no); BGP senza
  riquadro AS è un errore. Nel modello l'AS c'è solo con BGP, come nel wizard.
- Verifiche: test con Node delle quattro regole (ogni regola tolta apposta fa fallire un test);
  la bozza di riferimento `bgp_ibgp_due_as` usa "BGP su tutti i router" e le quattro bozze danno
  ancora gli stessi file del wizard; il pilota prova le quattro funzioni nel browser.

- Rinomina e Topologia: dopo la rinomina di un dispositivo (terminale o GUI) la sua posizione nel
  disegno salvato (`disegno.json`, chiave `d:<nome>`) passa al nome nuovo, così la Topologia resta
  disposta come nel disegno (`supporto.rinomina_nel_disegno`, chiamata da `dopo_scrittura`, che
  ora usa anche il terminale). Emerso durante la prova: nomi di client e server sbagliati in un lab
  già creato, corretti dal terminale.

- Costo OSPF sulla Topologia (chiesto nella prova guidata): accanto all'etichetta dell'interfaccia
  compare `c<N>` solo se il `frr.conf` ha `ospf cost` su quell'interfaccia; senza costo scritto
  (quello predefinito) non compare niente. Segue la casella "interfacce"; il passaggio del mouse
  spiega il valore. Le etichette stanno in `js/etichette.js`, senza legami con la pagina, provate
  con Node (`tests/js/etichette.test.mjs`); `test_api` controlla che un costo applicato arrivi ai
  dati della Topologia. Rotture apposta (costo sempre visibile, larghezza senza il costo) fanno
  fallire i test.
- Verificato con Kathará il costo predefinito: su questa macchina (kernel 7.2, veth a 10 Gbit/s)
  è 10 senza `auto-cost` e 1 con `auto-cost reference-bandwidth 100`; i messaggi attuali dicono
  10000 e 10, che valgono solo dove il kernel non dichiara la velocità delle veth (FRR usa allora
  10 Mbit/s). Per questo la Topologia non confronta il costo con un valore predefinito fisso.
  Testi da correggere: vedi la sezione 8.
- Confronto `papillon_mio` / `papillon_gui` della prova: uguali tranne quello aggiunto dopo con
  le Opzioni (auto-cost, costi, aggregati BGP), il costo della prova del punto 9 e la pagina
  `index.html` del server rinominato, che diceva ancora `www1`.
- Rinomina e pagina web: la rinomina (terminale e GUI, `calcola_rinomina`) riscrive anche
  `<server>/var/www/html/index.html` se è ancora la pagina del generatore (`generators.pagina_www`,
  ora unico modello); una pagina cambiata a mano resta com'è, con una nota se cita il nome vecchio.
  Test sulle due strade e sui quattro casi; tre rotture apposta fanno fallire i test.

### Fase 4 chiusa (2026-11-22)

Prova guidata dell'autore fatta su `papillon_gui` (disegnato nell'editor, avviato con Kathará,
modificato dal terminale e riletto nella GUI): ok dopo le correzioni sopra.

## Fase web: comandi web e apache2 — lavoro completato (2026-11-22), prova finale con la fase 5

Decisioni dell'autore: il terminale stampa i comandi da incollare e, se Kathará c'è e il lab è
acceso, chiede se eseguirli; apache2 si avvia solo su richiesta (pulsante "Avvia" o "s").

- `core/web.py` (comune a GUI e terminale): server web (tipo www o apache2 nello startup), nomi
  DNS che portano a loro (record A delle zone autoritative e CNAME, anche in catena), client
  (tutto tranne i router: kathara/frr non ha links), comando `timeout 8 links -dump http://<x>/`
  con l'indirizzo controllato (IP o nome DNS, niente che esca dall'URL), spiegazione degli esiti
  misurati con Kathará e comandi da incollare.
- Esiti di links misurati: pagina (0), `Host not found` (nome non risolto: resolver o DNS spenti,
  record mancante), `Connection refused` (apache2 spento), `Network is unreachable` (client senza
  gateway), codice 124 (nessuna risposta: routing).
- GUI, pannello di host, DNS e server: campo con IP e nomi proposti e pulsante "links"; sui server
  "stato apache2" e "avvia apache2". Scheda Test, "Server web": apache2 su ogni server (con "Avvia"
  se spento, poi nuovo controllo) e pagine da un client scelto, con esito e spiegazione. Il
  Registro ha i comandi `kathara exec` equivalenti.
- Terminale: menu 4 con "Ping" (come prima) e "Pagine web e apache2"; anche nel menu dopo la
  creazione (voce 5). Usa le stesse funzioni della GUI (`gui/terminale_web.py`).
- `kathara.esegui` ora chiude l'output del processo (avvisi ResourceWarning nei test).
- Verifiche: `tests/test_web.py` (16 test: indirizzi, dati dal lab, spiegazioni, Kathará finto per
  GUI, server e terminale); sette rotture apposta fanno fallire i test. Con Kathará: lab DNS
  dall'editor (pagine per IP, `www.com` e CNAME `web.com`; apache2 spento riconosciuto, "Avvia"
  dalla GUI e "s" dal terminale lo riavviano; nome inesistente spiegato) e copia di papillon (pagina
  attraverso i due AS; senza gateway spiegato).

### Correzione dalla prova guidata della fase web (2026-11-22)

- Su `papillon_gui` (senza le Opzioni 6, quindi senza aggregati BGP) la spiegazione diceva
  "controlla il gateway del client", ma il gateway c'era: era r1 a non avere la rotta. `links`
  scrive "Network is unreachable" in entrambi i casi. Ora, per i problemi di rete, la diagnosi
  continua sul client con `ip route get <IP>` (senza rotta = gateway del client) e poi con
  `traceroute -n`, e la spiegazione nomina il router: `!N` = "r1 (20.20.1.1) non ha una rotta
  verso ...: rete da annunciare in BGP (Opzioni 6) e ridistribuire nell'IGP"; `!H`, `!X`; hop che
  rispondono e poi solo `*` = "i pacchetti si fermano dopo r3 ...". Per i nomi si usa l'IP del
  record A. Nel pannello il traceroute compare in Output.
- Verifiche: uscite misurate con Kathará su una copia di `papillon_gui` (router senza rotta al
  primo e al terzo hop, ritorno mancante, client senza gateway); test sulle uscite e con il
  Kathará finto; quattro rotture apposta fanno fallire i test. Prova finale con Kathará sulla
  copia: com'è adesso -> "r1 non ha una rotta"; senza gateway -> gateway; con gli aggregati delle
  Opzioni 6 (stessa `calcola_network_bgp` del terminale) -> pagina ricevuta.

### Prova guidata della fase web: rimandata (decisione dell'autore, 2026-11-22)

Punti 1-7 fatti (il Registro: vedi sezione 8). Il punto 8 (`papillon_gui` con gli aggregati
BGP) e il resto della prova si fanno alla fine della fase 5, quando le Opzioni sono anche nella
GUI.

## Fase 5: completata (2026-11-23) — lab esistenti, modifica grafica e Opzioni nella GUI

Decisioni dell'autore (2026-11-22): si modifica sulla Topologia del lab, un'operazione alla volta
con l'anteprima (non riaprendo il lab nell'editor); ogni modifica si annulla (GUI e terminale) e
si può ripristinare una copia di sicurezza anche dalla GUI; "partire da un lab esistente"
nell'editor diventa l'ultima sottofase (5.7). Prova guidata dell'autore alla fine della fase 5,
insieme al punto 8 della fase web.

Sottofasi: 5.1 base, costo OSPF e auto-cost, annulla e copie; 5.2 dispositivi e indirizzi
(Opzione 11, aggiungi/togli); 5.3 BGP (loopback, network, iBGP, default route, ridistribuzione);
5.4 DNS (resolver, deleghe); 5.5 policy e Customer-Provider-Peer; 5.6 livelli del disegno e
Riepilogo sul disegno; 5.7 partire da un lab esistente.

### Fase 5.1: completata (2026-11-22) — modalità Modifica, annulla e copie

- **Storia delle modifiche** (`core/storia.py`, `.labgenerator/<lab>/storia.json`, fuori dal lab):
  `dopo_scrittura`, chiamata da GUI e terminale, registra ogni piano scritto con il contenuto dei
  file prima e dopo (riletto dal disco); l'operazione `annulla` (in `OPERAZIONI`, quindi con
  anteprima, impronte e firma come le altre) riporta i file a prima dell'ultima modifica e toglie
  la voce. Si annulla in ordine inverso; se un file è cambiato dopo (a mano o fuori dalla storia)
  si rifiuta senza scrivere e rimanda alle copie. La rinomina annullata rimette anche il disegno.
  Ultime 50 voci; storia svuotata quando il lab viene ricreato o ripristinato.
- **Copie di sicurezza nella GUI**: `file_utils.elenco_copie` e `ripristina` (senza domande, usate
  anche dal menu del terminale); azioni `copie` e `ripristina` dell'API (nome della copia preso
  solo dall'elenco), con il Registro.
- **Terminale**: Opzioni 14 "Annulla l'ultima modifica o ripristina una copia di sicurezza".
- **GUI**: pulsante "Modifica" nella Topologia (etichette delle interfacce sempre visibili e
  cliccabili, scritte degli AS cliccabili con un'area trasparente dietro); pannello
  dell'operazione con modulo (componente `creaPannello`), "Anteprima" (`htmlAnteprima`),
  "Applica", conflitto (`htmlConflitto`); esito con file scritti, messaggi, avvisi nuovi e risolti;
  "Annulla modifica" nell'intestazione (anche per le modifiche fatte dal terminale); pannello
  della modalità con le ultime modifiche e le copie di sicurezza. Prime Opzioni: costo OSPF
  (clic sull'etichetta dell'interfaccia o pulsanti nel pannello del router) e auto-cost (clic
  sulla scritta dell'AS o pulsante nel pannello).
- Corretto: il pannello del dispositivo poteva cercare l'elenco dei file dopo essere stato
  ridisegnato (errore nella console).
- Verifiche: `tests/test_storia.py` (tutte le 33 operazioni di prova del motore applicate e
  annullate lasciano il lab identico; ordine inverso, rinomina e disegno, file cambiato, terminale,
  limite, storia illeggibile, ripristino e lab ricreato); `test_api` (annulla, copie, ripristino,
  nomi di copia non validi); otto rotture apposta fanno fallire i test (una nona, righe "dopo"
  prese dal piano invece che dal disco, è equivalente: entrambe le strade scrivono con
  `scrivi_piano`). Pilota `tests/strumenti/prova_modifica.mjs` (9 passi con mouse vero: costo dal
  disegno e dal pannello, costo 0 rifiutato, auto-cost, conflitto, annulla due volte con il lab
  identico all'originale, copie e ripristino); terminale vero: modifica fatta dalla GUI annullata
  dal menu 14. Un giro del pilota su cinque è fallito per i ritardi dei clic di Chromium senza
  finestra (già visti nella fase 4); le scritture della storia hanno comunque un lucchetto.

### Fase 5.2: completata (2026-11-22) — dispositivi e indirizzi

Decisioni dell'autore: il clic su un'interfaccia apre il suo menu di azioni (il costo è una di
queste); spostare un collegamento e cambiare AS si fanno con la scelta nel pannello, non
trascinando (il trascinamento resta per disporre il disegno); costo OSPF corretto anche nel
terminale.

- **Costo OSPF** (`calcola_costo_ospf`, GUI e terminale): se l'interfaccia ha già un costo si
  cambia il numero nella sua riga (tutte, se ci sono blocchi ripetuti, con una nota); se ha un
  blocco `interface` senza costo la riga va dentro; altrimenti il blocco si aggiunge in fondo come
  prima. Costo da 1 a 65535. Operazione nuova `togli_costo_ospf` (torna il predefinito; il blocco
  rimasto vuoto sparisce). Terminale, Opzioni 1: mostra il costo attuale, `0` lo toglie.
- **GUI, modalità Modifica** (`static/js/modifica_lab.js`, proposte in `static/js/proposte.js`):
  - interfaccia (clic sull'etichetta o pulsante ethX nel pannello del dispositivo): cambia IP
    (basta l'ultimo numero), sposta su un'altra LAN o su una LAN nuova (IP proposto), costo OSPF e
    togli il costo, togli l'interfaccia;
  - LAN (clic sul nodo o sull'etichetta del link): cambia subnet (IP nuovi proposti con la stessa
    parte host, modificabili), collega un dispositivo, aggiungi qui un router, host, server web o
    DNS;
  - dispositivo (pannello): rinomina, gateway (candidati sulla LAN o un altro IP), cambia AS,
    aggiungi o togli OSPF, RIP, BGP (network, area, sessioni BGP con i vicini proposte), file a
    righe (editor con anteprima delle differenze), togli il dispositivo (con chi lo usa come
    gateway o resolver);
  - "+ Router / Host / Server web / Server DNS": nome libero (as<AS>r<n> se il lab usa quei nomi;
    il primo DNS è `root`, master per ".", come nel wizard), IP libero, protocolli e gateway dei
    vicini della LAN.
  - Moduli in più passi ("Avanti") e menu di azioni nel pannello; "indietro" torna al passo prima.
- **Topologia**: dopo una modifica i nodi restano dove sono; quelli nuovi vanno vicino ai vicini
  (`completaPosizioni`); la disposizione automatica riparte solo se manca più di metà dei nodi.
  Dopo una rinomina il dispositivo resta al suo posto.
- Verifiche: `test_modifica_gui` (router OSPF e RIP, host, server web, primo DNS e DNS successivo
  aggiunti dalla GUI danno gli stessi file del terminale, che risponde alle domande del wizard
  in base al testo; tre rotture apposta dei dati della GUI fanno fallire il test);
  `test_operazioni` (costo sostituito, altra interfaccia, blocco con altre righe, blocchi
  ripetuti, togli, valori sbagliati; due casi nuovi nei file attesi, annullati esattamente come
  tutti gli altri da `test_storia`); `tests/js/proposte.test.mjs` (IP liberi, completamento
  dell'IP, nomi, vicini, rinumerazione, posizioni); pilota `prova_modifica.mjs` 16 passi su 16
  con mouse vero (subnet di una LAN, IP, LAN nuova, host aggiunto, rinominato e tolto, RIP
  aggiunto, file a righe, poi tutto annullato: lab identico all'originale); Kathará: router OSPF
  e host aggiunti con i dati della GUI a una copia di papillon, raggiungibilità 0 ping falliti su
  11 dispositivi.
- I fallimenti saltuari del pilota nella 5.1 erano con ogni probabilità dovuti a una seconda GUI
  di prova avviata sulla stessa porta (non partiva e il pilota parlava con quella vecchia): con
  la traccia delle scritture della storia, tre giri completi senza errori.

### Fase 5.3: completata (2026-11-22) — BGP dalla Topologia

Decisioni dell'autore: il clic sulla scritta dell'AS apre il menu dell'AS; i segni sul disegno
(loopback, sessioni iBGP, 0/0, ridistribuzione) vanno nella 5.6 con i livelli; la loopback
proposta è la successiva della serie già usata nel lab, sempre modificabile (come ogni proposta).

- **Menu dell'AS** (scritta dell'AS o pulsante "AS<n>" nel pannello): aggregato (network BGP sul
  router BGP dell'AS, quello di confine proposto se ce n'è più d'uno), "Completa l'iBGP" (con
  almeno due router BGP; con l'avviso del terminale sugli esercizi che vietano l'iBGP),
  auto-cost.
- **Pannello del router**: aggiungi loopback (anche su host e server), network BGP, default route
  (menu: BGP default-originate verso i neighbor scelti, eBGP proposti, con "solo la default" e
  reti in più; OSPF con o senza `always`; RIP con `route <rete>` o `default-information
  originate`), ridistribuzione BGP → IGP (togli, rimetti, route-map eBGP con la rete del vicino
  di un altro AS proposta).
- Network BGP in due passi come nel terminale: prima le reti (proposta del motore, `/8` del primo
  ottetto come nel terminale, modificabile), poi, se ci sono, le network già annunciate che le
  nuove coprono, con la casella per toglierle (`opzioni_network_bgp` accetta ora anche `reti` e
  restituisce le `coperte`).
- Parametri costruiti da funzioni senza pagina in `proposte.js` (`listaReti`, `prossimaLoopback`,
  `retiEbgp`, `parametriDefaultBgp`, `parametriDefaultIgp`), provate con Node.
- Verifiche: `test_modifica_gui.TestBgpComeIlTerminale` (per i dieci scenari BGP del terminale,
  aggregato con e senza reti coperte, network, iBGP, loopback con iBGP, default BGP "solo",
  default OSPF e RIP, route-map, togli e rimetti la ridistribuzione, la stessa modifica con i
  parametri della GUI dà esattamente il diff atteso del terminale); rotture apposta prese (una
  dal test Node); pilota con i passi della 5.3 (aggregato con reti coperte, loopback, default
  OSPF e BGP, ridistribuzione tolta, poi tutto annullato: lab identico all'originale; ha trovato
  un errore della pagina, il formato di `default_orig`, corretto); Kathará: copia di
  `papillon_gui` con gli aggregati 20.20.0.0/16 e 30.30.0.0/16 annunciati con i parametri della
  GUI: sessioni BGP Established, 0 ping falliti, pagina web dal client ricevuta (il punto 8 della
  fase web).

### Fase 5.4: completata (2026-11-22) — DNS (strada A, decisione dell'autore)

Prima di aggiungere funzioni, controllo degli esami del corso (`Esami_IDC`, 39 esami, il DNS in 6:
tennis, crab, mirada, palabra, patchwork, Shuriken): usano solo record A e NS, la delega dal root
e, in crab e Shuriken, quella da un dominio di primo livello a un sottodominio (`it` ->
`roma3.it`, `net` -> `rm3.net`), un resolver locale con `allow-recursion` e `dnssec-validation
no`, il `nameserver` sui client (10 in mirada); mai CNAME, MX, forwarders o zone slave. Tutto
questo si crea già con il wizard e con l'editor: per risolvere gli esami non servono operazioni
nuove. Decisione: nella GUI solo le due Opzioni DNS che il terminale ha (resolver e delega dal
root); zone, record e ricorsione di un lab già creato restano a "File a righe" (sezione 8).

- **GUI**: "Resolver" nel pannello di host, server web e DNS (server DNS candidati o un altro IP);
  "Delega una zona" nel pannello del server root (zona e server che la gestirà, poi nameserver
  `dns.<zona>` e IP del glue proposti come nel terminale).
- **Corretto**: `allow-recursion { 0/0; }`, come lo scrivono le soluzioni del corso, era rifiutato
  ("Rete non valida: '0/0'") da `valida_lab` e dal wizard: `parse_reti` accetta ora la forma
  abbreviata di bind (`0/0`, `10/8`, `192.168/16`), completata con gli zeri.
- **Verifica con Kathará**: Shuriken e crab rifatti dal modello come li si fa nel wizard o
  nell'editor (resolver del lab `local`; per crab i router con le rotte statiche della traccia):
  dal client `dig` risolve il nome del web, ping e pagina web ok.
- Verifiche: `test_dns_esami` (forma abbreviata; gerarchia di crab creata con delega verso il
  sottodominio, glue e resolver locale); `test_modifica_gui` con gli scenari `resolver`,
  `resolver_manuale` e `delega_dns` del terminale (stesso diff con i parametri della GUI); pilota
  con un DNS aggiunto (nasce `root`, master), delega di `com` e resolver del client, poi tutto
  annullato.

### Fase 5.5: completata (2026-11-22) — policy BGP (Opzione 2 del terminale)

Controllo degli esami prima di cominciare: su 25 esami con BGP le soluzioni usano
local-preference (12), MED (9), prefix-list (9), access-list (4) e lo stile Customer-Provider-Peer
(pear-to-pear); mai as-path, community, weight o prepend, e le policy non si tolgono mai. Nella GUI
quindi solo le policy che il terminale ha già, nessuna operazione nuova. Decisioni dell'autore:
valori proposti 150 (local-preference) e 20 (MED), modificabili; Customer-Provider-Peer un lato
alla volta con il lato opposto proposto subito dopo; niente "togli policy" (Annulla, la stessa
policy con un altro valore sostituisce la route-map, "File a righe"). "Traccia il percorso" resta
un'opzione in più, non al posto di questa: è la 5.5b.

- **GUI**: "Policy BGP" nel pannello del router (si sceglie il neighbor, con le policy già
  scritte e la relazione, oppure un neighbor non ancora configurato) e "Policy BGP su A verso B"
  nel menu del link fra due AS; poi local-preference in ingresso, MED in uscita, prefix-list
  (in/out), access-list in ingresso, Customer-Provider-Peer. Le reti si scelgono con le caselle
  (le network del lab, prima quelle dell'AS del vicino) o si scrivono.
- **Customer-Provider-Peer**: verso provider e peer le reti proposte sono quelle delle soluzioni
  (pear-to-pear): reti proprie, link con i clienti, reti dei clienti; non i link con provider e
  peer. La relazione si riconosce dai nomi delle prefix-list (`provider_X_out` del programma e
  `providerOut`, `peerIn` delle soluzioni), anche rovesciando quella scritta sull'altro router.
  Dopo l'applica la GUI propone il lato opposto, già compilato (si conferma o si torna indietro).
- **Motore**: `opzioni_policy_bgp` (neighbor con relazione, reti proposte, reti del lab); il
  pannello mostra sopra il passo successivo l'esito di quello appena applicato (`conf.poi`).
- **Verifica con Kathará**: lift e stairs rifatti con i parametri della GUI su una copia senza
  policy: file identici a `lift_mio` e `stairs_mio`; lift: as300r1 preferisce AS400 per
  10.1.0.0/24 e AS500 per 10.2.0.0/24 (local-preference 150), as100r1 non usa as300r1 per le
  10.x (access-list); stairs: MED 20 visto sui link meno preferiti e l'altro scelto,
  local-preference 150 su as4r2 da un vicino iBGP (come la soluzione).
- Verifiche: `test_modifica_gui` con gli 11 scenari di policy e Customer-Provider-Peer del
  terminale (stesso diff con i parametri della GUI; `cpp_provider` con le reti proposte) e
  `TestOpzioniPolicy` (relazioni e proposta); test di `proposte.js`; pilota con local-preference
  dal router, MED e prefix-list dal link F, Customer-Provider-Peer con il lato opposto, poi tutto
  annullato.

### Fase 5.5b: completata (2026-11-22) — "Percorso voluto" (proposte di policy dal disegno)

Opzione in più accanto alla 5.5, non al posto suo (decisione dell'autore: le proposte non sono una
garanzia). Nella GUI si chiama "Percorso voluto" perché "Traccia il percorso" è già il pulsante del
traceroute nella scheda Test. Decisioni dell'autore: funziona a lab spento (solo i file) e acceso
(tabelle BGP vere); le proposte si applicano una alla volta (anteprima, applica o salta); resta solo
nella GUI e scrive solo policy dell'Opzione 2, quindi gli stessi file del terminale.

- **Gesto**: nel pannello iniziale della modalità Modifica "Percorso voluto"; poi clic sulla
  sorgente, sugli AS o sui link fra AS da attraversare e sulla destinazione (LAN o dispositivo),
  evidenziati sul disegno con l'ordine; per AS si può dire "le altre strade sono vietate".
- **Motore** (`gui/percorso_voluto.py`): sequenza di AS (i buchi si riempiono con il cammino più
  corto, i loop si rifiutano), rete BGP di destinazione (la network più specifica che contiene la
  destinazione), e per ogni AS del percorso: un'altra uscita con AS path non più lungo ->
  local-preference 150 sulla sessione voluta per quella rete (unita alle reti che la route-map
  aveva già); solo link paralleli verso lo stesso AS -> MED 20 messo dall'AS successivo sui link da
  non usare; AS con il divieto -> prefix-list deny sulle altre sessioni. A lab acceso legge `show ip
  bgp <rete> json` sui router degli AS del percorso e non propone niente dove la strada è già quella.
  Avvisa se una local-preference già scritta va contro il percorso.
- **Alla fine**: "Verifica percorso" nella scheda Test già compilata (sorgente, IP di destinazione,
  link attesi, "deve passare per").
- **Verifica con Kathará**: stairs senza policy, percorso di as4r2 verso 1.0.0.0/24 lungo H, F, B
  della traccia: a lab acceso le tre proposte sono i tre MED della soluzione; dopo, il traceroute
  passa per J H G F D B e una seconda richiesta non propone più niente. Lift senza policy, as100r1
  verso K lungo A, C, G con il divieto in AS100: prefix-list su as100r1 e local-preference su
  as300r1 come la soluzione; dopo, il traceroute passa per A C G F J (B evitato).
- Verifiche: `test_percorso_voluto` (stairs e lift: proposte uguali alle soluzioni e righe uguali a
  `stairs_mio` e `lift_mio`; tabelle simulate; divieto solo dove chiesto; local-preference che si
  somma; errori); pilota `tests/strumenti/prova_percorso.mjs` (clic sul disegno, tre MED applicati,
  Verifica percorso compilata, divieto e "Salta" su lift, tutto annullato).

Limiti dichiarati: a lab spento conta solo la lunghezza dell'AS path (non spareggi, policy già
scritte diverse da quelle del programma, regole Customer-Provider-Peer); il ritorno è un percorso a
parte; dentro un AS decide l'IGP (costo OSPF, 5.2).

### Fase 5.6: completata (2026-11-23) — livelli del disegno e Riepilogo sul disegno

Decisioni dell'autore: all'apertura accesi Indirizzi, Costi OSPF, Policy, Segni sui router e
Avvisi, spenti Sessioni BGP e DNS (linee in più); il resolver degli host come scritta sotto il nome
(`ns: local`), non come linea; Customer-Provider-Peer con la freccia verso il provider e "peer" fra
pari. Tutto dai file (gli stessi dati del Riepilogo), quindi anche le modifiche fatte dal terminale
o a mano.

- **Barra dei livelli** (componente `creaLivelli` della fase 2, al posto della casella
  "interfacce"; la scelta resta nel browser): Indirizzi; Costi OSPF (con gli indirizzi spenti resta
  il solo `c20`); Sessioni BGP (link eBGP marcati, iBGP come curve tratteggiate del colore dell'AS,
  sessione sbagliata come curva rossa puntinata con "!": vicino senza BGP, neighbor scritto da una
  parte sola, remote-as diverso dall'AS del vicino); Policy (sigle `LP 150 in`, `MED 20 out`,
  `filtro in`, `solo out` sul link vicino al router che le applica, testo completo nel tooltip;
  frecce Customer-Provider-Peer, relazione presa anche da una parte sola); Segni sui router (`0/0`
  su chi manda la default in BGP, OSPF o RIP, `R` su chi ridistribuisce BGP nell'IGP, loopback
  sotto il nome); DNS (deleghe dal server padre al figlio con il nome della zona, resolver sotto il
  nome); Avvisi ("!" sui dispositivi e sugli AS citati dagli avvisi automatici, testo nel tooltip).
- **Riepilogo sul disegno**: il pannello del dispositivo mostra gli avvisi che lo citano e la
  "Configurazione in breve" (IGP, costi, network, neighbor con relazione e policy, default route).
- **Modalità Modifica**: clic su una sigla di policy apre le policy verso quel neighbor (5.5).
- **Dati** (`gui/dati.py`): per ogni policy la sigla (`breve`), per ogni neighbor la relazione
  Customer-Provider-Peer, per ogni router `default` e `redistribute_bgp_igp`, per ogni server DNS
  le deleghe scritte nelle sue zone master. Funzioni pure in `static/js/livelli.js`.
- Verifiche: `tests/js/livelli.test.mjs`; `test_livelli_disegno` (lift, stairs, candy con
  Customer-Provider-Peer da una parte, galaxy, una sessione rotta, tennis); golden della lettura
  aggiornati (solo campi aggiunti); tutte le soluzioni di Esami_IDC lette senza errori; pilota
  `tests/strumenti/prova_livelli.mjs`; schermate controllate su pear-to-pear (frecce e peer),
  stairs, lift, tennis, galaxy, Shuriken.

### Fase 5.7: completata (2026-11-23) — parti da un lab esistente

Misura di partenza (39 soluzioni di Esami_IDC rilette e ricreate dal modello): si perdevano tutte le
righe delle Opzioni (policy, `neighbor` che le collegano, costi, `debug`, `hostname`, `iptables`,
pagine web scritte a mano), i router con sole rotte statiche di crab diventavano host e i resolver
di un solo dispositivo (pc di palabra) sparivano; 4 data center non si caricano. Decisioni
dell'autore: le righe delle Opzioni passano nel nuovo lab; si parte dall'elenco dei lab o da una
cartella qualunque; resolver di un dispositivo nel modello, nell'editor e nell'XML (wizard invariato).

- **Unione a tre vie** (`core/unione.py`): nuovo lab = file del lab di partenza + (file dal
  modello della bozza - file dal modello iniziale della bozza). Senza modifiche il nuovo lab è
  identico al lab di partenza; ogni modifica cambia solo le sue righe; i file che il generatore non
  scrive (pagine, `resolv.conf` dei router di mirada) seguono il dispositivo, anche rinominato;
  quelli che il generatore aggiungerebbe ma il lab non aveva (es. `daemons`) non si creano. Avviso
  per le righe conservate che citano un IP sparito dalla bozza.
- **Modello** (`persistence.modello_da_stato`): router senza FRR con almeno due interfacce e rotte
  statiche verso altre reti = router `statico` (crab, chair-01, chair-02); `nameserver` per host,
  www e DNS che usano un resolver diverso da quello del lab (tennis, palabra, crab, Shuriken),
  scritto dal generatore, letto e scritto nell'XML, controllato da `valida_lab`; uguale all'Opzione
  5 del terminale.
- **Editor**: "Parti da un lab esistente" (elenco dei lab o cartella); bozza costruita da
  `editor/da_lab.js` con le posizioni spostate a mano, poi il disegno salvato, poi la disposizione
  della Topologia (`disposizione.js`, ora un modulo a sé); riquadri AS (anche i router interni
  dello stesso AS), zone RIP e aree OSPF intorno ai membri, o uno per membro se il riquadro di
  gruppo prenderebbe dentro altro; eccezione nuova "OSPF: no" per il router RIP sul confine con
  OSPF (maracas, street-light, up-arrow); campo "Resolver solo di questo dispositivo". Riquadro del
  lab di partenza (con le differenze di rappresentazione, se ci sono) e "Crea solo dalla bozza".
  Anteprima e creazione mandano l'origine al server (`lab_come_modello`, `origine` in
  `anteprima_lab` e `crea_lab`).
- **Verifiche**: 17 lab di prova e 35 soluzioni d'esame caricabili diventano bozze con lo stesso
  modello (t2-c1 ha IP sbagliati nella soluzione: l'editor li segnala) e, senza modifiche, ridanno
  file identici; con un host in più nessuna riga originale si perde; `test_unione`, `test_da_lab`,
  `tests/js/da_lab.test.mjs`; pilota `tests/strumenti/prova_da_lab.mjs` (lift caricato, router
  rinominato dal pannello, anteprima e creazione con policy e filtro conservati, cartella non valida
  e data center rifiutati con la spiegazione); Kathará: crab2 da crab con un host in più (dig e
  ping attraverso i router con sole statiche).

### Prova guidata della fase 5: fatta (2026-11-23), scaletta in `docs/PROVA_FASE5.md`

- 2026-11-23, `papillon_gui` (modalità Modifica, annulla e copie, dispositivi, aggregati BGP di
  AS20 e AS30, default route e policy in anteprima, livelli): tutto ok. **Punto 8 della fase web
  fatto**: con gli aggregati la pagina del server arriva al client. Corretta la scaletta: anche
  AS30 va annunciato (la `network 30.30.0.0/16` di r5 è nel blocco RIP, non in BGP).
- 2026-11-23, `stairs_senza_policy` (policy dal router e dal link, Customer-Provider-Peer con il
  lato opposto, Percorso voluto con Salta, Verifica percorso con Kathará e "niente da fare" a lab
  acceso): tutto ok.
- Corretto dalla prova: in "Parti da un lab esistente" l'elenco dei lab parte dal lab aperto e,
  se era scelto un lab, la cartella scritta veniva ignorata (si ricaricava lift invece di crab).
  Ora la cartella scritta vince; scrivendo la cartella l'elenco torna vuoto e viceversa (pilota
  aggiornato con questo caso).
- 2026-11-23, `tennis_test` (resolver, delega, livello DNS) e "Parti da un lab esistente" (lift_mio
  con rinomina e creazione, soluzione di crab, patchwork rifiutato): tutto ok dopo la correzione.
- 2026-11-23, `lift_senza_policy` con il Percorso voluto (K via AS400 e L via AS500 senza il link B,
  divieto in AS100), verificato con Kathará (Verifica percorso e Rotta verso una rete): tutto ok.

- 2026-11-23, terminale: MED dalle Opzioni 2 visto nella GUI (disegno e "Annulla modifica") e
  annullato dalle Opzioni 14: ok. **Fase 5 chiusa**, con il punto 8 della fase web.

## Fase 6: completata (2026-11-23) — obiettivi della traccia e verifica

Controllo degli esami prima di cominciare: nei costi OSPF (maracas, eye, hour-glass,
twin-pan-balance, tennis, ...) i costi li dà la traccia e il percorso è da verificare, non da
progettare; il DNS serve in tennis, crab, Shuriken, mirada, palabra (e patchwork). Decisioni
dell'autore: niente proposta di costi OSPF (bastano Costo OSPF e Verifica percorso); risoluzione
di un nome dai file e dal lab acceso, GUI e terminale; test suggerito dopo ogni modifica; la pagina
`~guest` di tennis resta nella sezione 8 (la soluzione ufficiale non la prepara).

- **Costi OSPF**: l'avviso sul costo predefinito non dice più "10000": dipende dalla velocità che
  FRR legge sul link (misurato con Kathará: 10 senza auto-cost, 1 con `reference-bandwidth 100`),
  con il rimando a `show ip ospf interface`; stessi messaggi corretti nell'auto-cost (Opzioni 10).
  La Verifica percorso mostra il costo dell'interfaccia di uscita di ogni router OSPF del percorso
  (`show ip ospf interface json`) e la somma; se il percorso è diverso dall'atteso, ricorda che
  dentro un AS vince la somma più bassa.
- **Risoluzione di un nome** (`core/risoluzione.py`): dai file segue resolver del client,
  ricorsione permessa (`allow-recursion`, anche `0/0` e il default di bind), db.root del resolver,
  deleghe con il glue fino al record A (CNAME seguiti) e dice il primo anello che manca con
  l'operazione che lo sistema; a lab acceso `dig` dal client e `dig +norecurse @server` su ogni
  server della catena, con la spiegazione (risposta, rinvio, inesistente, rifiutata, SERVFAIL, non
  risponde). GUI: card nella scheda Test (anche a lab spento); terminale: menu 4, voce 3 (stesse
  funzioni, `kathara.risoluzione`).
- **Test suggerito**: dopo "Applica" l'esito propone la prova adatta (Verifica percorso, Sessioni,
  Raggiungibilità, Risoluzione di un nome, già sul dispositivo) e ricorda di avviare o riavviare
  il lab.
- Verifiche: le soluzioni dei 6 esami con DNS danno "ok" con la catena giusta; `test_risoluzione`
  (crab giusto, cinque anelli rotti apposta riconosciuti con il rimedio, CNAME, spiegazioni di dig,
  GUI e terminale uguali); file attesi aggiornati (solo i messaggi del costo); Kathará su tennis:
  catena e dig a lab acceso, nome inesistente, ricorsione rifiutata, costi OSPF sul percorso;
  pilota `tests/strumenti/prova_fase6.mjs` e pilota della modalità Modifica.

- Prova guidata dell'autore (2026-11-23, `tennis_test`: risoluzione a lab spento e acceso, nome
  inesistente, test suggerito dopo il Resolver, costi OSPF nella Verifica percorso, terminale):
  tutto ok.

## Diagnostica di frr.conf (2026-11-23)

Nuovo `core/frr_autofix.py`: diagnostica di frr.conf con correzioni. Misurata sulle 39 soluzioni
d'esame: trova errori veri (stairs: route-map `trafficOut` non definita su as1r2 e as2r1, quindi i
MED della soluzione non funzionano; Galaxy: `netwotk`; incognita: `ripd` non abilitato; puzzle:
rete con bit host; garden-umbrella e lift: righe `neighbor` fuori da `router bgp`). Tre regole che
davano falsi allarmi sono state ridotte: auto-cost tolta (c'è già l'avviso dell'analyzer),
import-check solo `info`, ebgp-requires-policy solo per neighbor eBGP senza policy (avviso).

- **Motore**: operazione `correggi_frr` (Opzioni 15 / GUI): `opzioni_correggi_frr` = i problemi con
  le correzioni; `calcola_correggi_frr` applica la correzione scelta (testo di frr.conf, demone in
  `daemons`, avvio di frr/apache2 nello startup, neighbor speculare) come piano: anteprima,
  impronte, storia e Annulla, copie. Le correzioni che sono altre operazioni rimandano a quelle
  (gateway, iBGP, rinomina).
- **GUI**: "Diagnostica" nel pannello di ogni dispositivo in modalità Modifica (problemi + un
  pulsante per correzione; dopo l'applica la diagnostica si rifà); card nel Riepilogo; problemi del
  file sotto "File a righe"; gli errori diventano "!" nel livello Avvisi.
- **Terminale**: Opzioni 15 "Diagnostica e correggi frr.conf" (problemi numerati, correzioni 1a,
  1b..., anteprima e conferma); la diagnostica anche nel Riepilogo (Opzioni 8).
- Verifiche: `test_diagnosi` (sui lab di prova solo i problemi veri; route-map sbagliata corretta e
  annullata; refuso; demone; problema già corretto; terminale = GUI); pilota
  `tests/strumenti/prova_diagnosi.mjs`; Kathará: la soluzione ufficiale di stairs corretta con la
  diagnostica (e con l'immagine kathara/frr nel lab.conf, che la soluzione non indica): as2r2 riceve
  da as1r2 il MED 20 e sceglie l'altra strada.

### Prossimo passo

Fase 7 (collaudo, rifinitura e rilascio): spiegata, in attesa delle quattro decisioni dell'autore
(esame del collaudo, Windows, sezione 8, ordine).

---

## 8. Da riprendere in futuro

Cose trovate durante il lavoro e messe da parte di proposito. Non bloccano le fasi in corso.

| Cosa | Dove | Note |
|---|---|---|
| Codice morto: `aggiungi_relazioni_bgp_menu` | `src/core/routing_ops.py` | Non è chiamata da nessun menu. Lasciata dov'è (decisione del 2026-11-22). |
| Codice morto: `ensure_neighbor_exists` | `src/core/net_frr.py` | Non è chiamata da nessuna parte. Lasciata dov'è. |
| La proposta delle network IGP aggrega per primo ottetto | `net_frr.default_igp_networks` | Può mettere in un'area OSPF un link dichiarato in un'altra; ora `valida_lab` lo segnala come avviso. |
| Il resolver finale viene scritto anche sui server DNS | `generazione._scrivi_lab` | Lasciato così (decisione della fase 1.4). |
| Riga di soli spazi prima di `redistribute bgp route-map eBGP` | `operazioni.calcola_redistribuzione_route_map` | Viene da `insert_lines_into_protocol_block` con una riga vuota. |
| Quando le Opzioni aggiornano l'XML lo riscrivono per intero | `persistence._aggiorna_xml` | Cambia, per esempio, `&quot;` in `"` dentro `lab_conf`. Da decidere nella fase 1.7 (XML fuori dal lab, forse rigenerato dai file). |
| `--output` (o un'opzione scritta male) viene ignorato in silenzio | `main` in [labGenerator.py](../src/labGenerator.py) (`parse_known_args`) | Visto nella prova guidata della fase 3: la GUI partiva sulla cartella corrente senza lab. Proposta: `--output` come sinonimo di `--out` e un avviso per le opzioni non riconosciute. |
| Il Registro della GUI è solo in memoria e contiene solo le operazioni della GUI | `gui/kathara.Lavori` | Visto nella prova guidata della fase web: chiudendo la GUI si svuota, e le operazioni del terminale non ci sono. Idea: salvarlo per lab in `.labgenerator/<lab>/` e aggiungere le operazioni fatte dal terminale del generatore. Non urgente (decisione dell'autore). |
| Zone, record e ricorsione di un lab già creato si cambiano solo con "File a righe" | GUI e terminale | Decisione della 5.4 (strada A): agli esami non servono, il wizard e l'editor li creano. Se servisse: aggiungi zona, aggiungi/togli record A e delega da qualunque zona, ricorsione, resolver per più dispositivi. |
| Data center senza IPv4 sulle interfacce non si caricano | `persistence.modello_da_stato`, editor (5.7) | puzzle, ceci-n'est-pas-une-pipe, exapus, patchwork (spine/leaf): il modello descrive solo interfacce con un IP. L'editor lo spiega. Da valutare se servono. |
| I dispositivi aggiunti nella bozza finiscono in cima a `lab.conf` | `core/unione.unisci` (5.7) | Il generatore li mette in ordine di nome; l'unione li inserisce dopo l'ultima riga comune che li precede. Solo estetica. |
| Pagina personale di un utente su apache (`http://web.com/~guest/`, modulo userdir) | tennis (Esami_IDC) | Chiesta dalla traccia di tennis; il generatore non la prepara. Da valutare per la fase web. |
| Circa 130 stampe con emoji | tutto il terminale | Protette all'avvio (`reconfigure(errors='replace')`); nessuna è più dentro una domanda. |
