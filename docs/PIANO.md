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
| HTML, CSS e JS della GUI stanno tutti in una stringa (circa 1300 righe) | [pagina.py](../src/gui/pagina.py) |
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
  - `proposte`: valori proposti per un'operazione;
  - `anteprima`: il piano di modifica, mostrato come differenze;
  - `applica`: scrive, con l'impronta dei file letti per accorgersi dei conflitti.

  Più `anteprima_lab`, che genera il lab in una cartella temporanea e restituisce file e
  contenuti, e `crea_lab`.
- Le operazioni stanno in un elenco fisso, così il server esegue solo quelle previste. Il browser
  manda nomi e parametri, mai percorsi di file. Restano il collegamento solo su `127.0.0.1`, il
  controllo dell'host e l'header `X-Lab-Gen`.

### Fase 3: base della GUI

- HTML, CSS e JS da `pagina.py` a `src/gui/static/`. Nella build PyInstaller si aggiunge
  `--add-data`, che usa `:` come separatore su Linux e `;` su Windows (workflow
  `build-and-release.yml`).
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
   (`svgContenuto` e gestione di trascinamento e zoom in `pagina.py`).
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

### Fase 7: rifinitura e rilascio

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

### Prossimo passo

Fase 1.1: il lettore unico `core/stato.py`.
