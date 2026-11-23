# Prova guidata della fase 5 (e punto 8 della fase web)

Scaletta da seguire con la GUI aperta. Per ogni passo: cosa fare e cosa deve succedere. Se
qualcosa non va come scritto, annota il numero del passo e cosa hai visto: lo correggiamo dopo.

Tempo indicativo: 60-90 minuti (le parti con Kathará sono le più lente).

## 0. Preparazione

La cartella di prova `~/labs_prova` è già pronta, con copie dei lab: quelli in `~/labs` non si
toccano. Contiene:

| Lab | A cosa serve |
|---|---|
| `papillon_gui` | modalità Modifica, BGP, punto 8 della fase web |
| `lift_mio`, `stairs_mio` | livelli del disegno (policy già scritte) |
| `lift_senza_policy`, `stairs_senza_policy` | policy BGP e "Percorso voluto" partendo da zero |
| `tennis_test` | DNS (resolver, deleghe, livello DNS) |

Avvio della GUI sulla cartella di prova:

```
cd ~/Projects/lab-generator
python3 src/labGenerator.py --gui --out ~/labs_prova
```

Si apre il browser. Se a metà vuoi ricominciare un lab da capo: "Annulla modifica" più volte,
oppure, in modalità Modifica, "Copie di sicurezza" e "Ripristina".

---

## 1. Modalità Modifica, annulla e copie (5.1)

Lab `papillon_gui`, scheda Topologia.

1. Premi **Modifica** (si colora di blu). Atteso: le etichette delle interfacce restano visibili,
   a destra il pannello "Modifica del lab".
2. Clic sull'etichetta di **r1 eth1** sul disegno → "Costo OSPF" → scrivi `20` → Anteprima.
   Atteso: si vede la riga `ip ospf cost 20` nel blocco `interface eth1`. → Applica. Atteso:
   "Fatto: Costo OSPF di r1 eth1: 20", sul disegno compare `c20` accanto a eth1.
3. Rifai lo stesso su r1 eth1 con `30`. Atteso: la riga del costo viene **sostituita** (non ne
   compare una seconda).
4. Clic sulla scritta **AS20** → "Auto-cost". Atteso: proposta già scelta ("Metti ...", perché
   oggi nessun router di AS20 ce l'ha); Anteprima mostra `auto-cost reference-bandwidth 100` su
   r1-r4. Non applicare (o applica e annulla).
5. Premi **Annulla modifica** (in alto) e Applica, due volte. Atteso: `c20`/`c30` sparisce, il
   pannello dice "Annullato: ...".
6. Dal pannello iniziale: **Copie di sicurezza** → "Mostra le copie". Atteso: elenco con data e ora.
   Non serve ripristinare adesso.

## 2. Dispositivi e indirizzi (5.2)

Sempre `papillon_gui` in modalità Modifica.

1. Clic sulla LAN **A** (la pillola sul link o il nodo) → "Aggiungi qui un host". Atteso: nome e
   IP già proposti (modificabili). Anteprima → Applica. Atteso: l'host compare **vicino alla LAN
   A**, il resto del disegno non si sposta.
2. Clic sull'host nuovo → **Rinomina** in `ospite`. Atteso: resta allo stesso posto sul disegno.
3. Clic sull'etichetta di un'interfaccia di ospite → "Cambia IP" → scrivi solo l'ultimo numero
   (es. `77`). Atteso: l'anteprima completa l'IP con la subnet della LAN.
4. Clic su ospite → **Togli il dispositivo**. Atteso: sparisce da disegno e lab.conf.
5. Premi "Annulla modifica" fino a riavere ospite, poi ancora fino a toglierlo: tutto torna com'era.

## 3. BGP e punto 8 della fase web (5.3 + fase web)

`papillon_gui`: oggi r3 (AS20) e r5 (AS30) annunciano in BGP solo il link 10.1.0.0/30, non le reti
dei loro AS (la `network 30.30.0.0/16` di r5 è nel blocco RIP, non in quello BGP).

1. Clic sulla scritta **AS20** → "Annuncia l'aggregato (network BGP)". Atteso: già annunciata
   `10.1.0.0/30`, proposta del motore `20.0.0.0/8` (come il terminale), modificabile: scrivi
   `20.20.0.0/16` se preferisci l'aggregato esatto. "Avanti" → Anteprima → Applica. Atteso: la
   riga `network ...` nel blocco `router bgp 20` di r3.
   Poi lo stesso per **AS30**: proposta `30.0.0.0/8` (o `30.30.0.0/16`), riga `network ...` nel
   blocco `router bgp 30` di r5. Senza questo r3 non ha la rotta verso il server.
2. Pannello di **r3** → "Default route" → "BGP: manda la default a dei neighbor". Solo guardare:
   il vicino eBGP (r5) è già spuntato. Torna "indietro" senza applicare.
3. Pannello di **r1** → "Aggiungi loopback". Atteso: IP proposto, Anteprima con `lo` nello
   startup e la network nell'IGP. Non applicare (o applica e poi annulla).
4. Esci dalla modalità Modifica. **Avvia (lstart)** il lab e attendi la convergenza (scheda Test,
   "Attendi la convergenza", o un paio di minuti).
5. **Punto 8 della fase web.** Scheda Test, card "Server web": "Prova le pagine" dal **client**.
   Atteso: apache2 attivo su `server`, pagina di `30.30.1.2` ricevuta. Se non arriva, la
   spiegazione deve nominare il router che non ha la rotta (non più "controlla il gateway").
6. Pannello di **client**: campo links con `30.30.1.2` → "links". Atteso: il testo della pagina
   in Output.
7. **Ferma (lclean)** il lab.

## 4. DNS (5.4)

Lab `tennis_test`, modalità Modifica.

1. Pannello di **pc** → "Resolver". Atteso: i server DNS del lab come scelte, oppure un altro IP.
   Guarda l'anteprima del `resolv.conf`, poi "indietro".
2. Pannello di **root** → "Delega una zona" → zona `org`. Atteso: nameserver `dns.org` e IP del
   glue proposti. Anteprima con le righe `org. IN NS dns.org.`; non serve applicare.

## 5. Policy BGP (5.5)

Lab `stairs_senza_policy`, modalità Modifica.

1. Pannello di **as1r2** → "Policy BGP". Atteso: elenco dei neighbor (con AS, eBGP/iBGP, policy già
   scritte) e "Un neighbor non ancora configurato".
2. Scegli il neighbor **as2r2** → "MED (metric) in uscita". Atteso: valore proposto `20`.
   Anteprima → Applica. Atteso: route-map `LOCALMED_OUT_...` con `set metric 20`.
3. Clic sulla pillola del link **I** (fra AS3 e AS4) → "Policy BGP su as4r2 verso as3r2" →
   "Local-preference in ingresso". Atteso: `150` proposto e le reti del lab come caselle. Spunta
   `1.0.0.0/24` → Anteprima: route-map con `match ... prefix-list` e `set local-preference 150`.
   Non applicare.
4. Pannello di **as2r1** → Policy BGP → neighbor as1r1 → **Customer-Provider-Peer** →
   "il vicino è il mio provider" → Avanti. Atteso: reti proposte spuntate (le proprie e dei
   clienti, non i link con provider/peer). Applica. Atteso: subito dopo compare **"Lato opposto"**
   su as1r1 con "customer". Applica anche quello.
5. "Annulla modifica" più volte fino a tornare senza policy.

## 6. Percorso voluto (5.5b)

Lab `stairs_senza_policy`, modalità Modifica. La traccia di stairs chiede che il traffico di
as4r2 verso 1.0.0.2 passi per i link J, H, G, F, D, B, A.

1. Pannello iniziale → **"Percorso voluto (proposte di policy)"**.
2. Clic in ordine: router **as4r2**, link **H**, link **F**, link **B**, router **as1r1**.
   Atteso: punti elencati nel pannello, numerati e evidenziati sul disegno; "Togli l'ultimo"
   funziona.
3. **Avanti**. Atteso: "Percorso voluto: AS4 → AS3 → AS2 → AS1", rete `1.0.0.0/24`, "Lab spento:
   proposte basate solo sui file", e 3 proposte.
4. "Vedi le proposte una alla volta". Atteso: tre **MED 20** (as3r2 verso as4r2, as2r1 verso
   as3r1, as1r2 verso as2r2), ognuno con il perché. Applica il primo, **Salta** il secondo,
   applica il terzo. Atteso: dopo ogni applica la proposta successiva, con l'esito sopra.
5. "Annulla modifica" fino a togliere tutto. Rifai i passi 1-4 applicando **tutte e tre**.
6. "Verifica percorso (scheda Test)". Atteso: scheda Test con Da `as4r2`, Verso `1.0.0.1`,
   Atteso `H F B` già scritti.
7. **Avvia** il lab, attendi la convergenza, poi "Traccia il percorso" nella card Verifica
   percorso. Atteso: il percorso passa per J H G F D B ed è segnato come conforme.
8. Facoltativo, a lab acceso: rifai "Percorso voluto" con gli stessi punti. Atteso: per ogni AS
   "usa già ... niente da fare" e nessuna proposta.
9. **Ferma** il lab.

Facoltativo su `lift_senza_policy`: as100r1 → link A → link C → link G → LAN K, con la casella
"vietate" su **AS100**. Atteso: prefix-list su as100r1 (scarta 10.1.0.0/24 da as300r1) e
local-preference 150 su as300r1 da as400r1.

## 7. Livelli del disegno (5.6)

Lab `lift_mio`, modalità Modifica **spenta**.

1. Barra dei livelli sopra il disegno. Atteso: accesi Indirizzi, Costi OSPF, Policy, Segni sui
   router, Avvisi; spenti Sessioni BGP e DNS.
2. Atteso: `LP 150 in` sui link di as300r1 verso as400r1 e as500r1, `filtro in` su as100r1 verso
   as300r1. Passa il mouse su una sigla: il testo completo della policy.
3. Accendi **Sessioni BGP**. Atteso: link eBGP più spessi, curve tratteggiate per l'iBGP (in AS10).
4. Spegni **Indirizzi**. Atteso: niente etichette delle interfacce. Ricarica la pagina: la scelta
   resta.
5. Clic su **as300r1**. Atteso: nel pannello "Configurazione in breve" con le local-preference.
6. Accendi **Modifica** e clic sulla sigla `LP 150 in`. Atteso: si apre "Policy su as300r1 verso
   1.0.0.14".
7. Lab `stairs_mio`: atteso `MED 20 out` sui tre link e la `R` sui router che ridistribuiscono.
   Lab `tennis_test` con **DNS** acceso: atteso la linea della delega `com` dal root e `ns: ...`
   sotto pc.

## 8. Parti da un lab esistente (5.7)

1. **+ Nuovo lab** → "Parti da un lab esistente" → scegli **lift_mio** → "Carica nella bozza".
   Atteso: disegno con i riquadri AS, riquadro "Bozza partita da lift_mio".
2. Clic su **as100r1** nel disegno → nel pannello cambia il nome in `as100r9`.
3. Nome del lab in alto: `lift_copia` → **Anteprima file**. Atteso: "Dal lab di partenza: righe ...
   conservate in N file"; apri `as100r9/etc/frr/frr.conf`: c'è ancora `FILTER_IN_1_0_0_10`; in
   `as300r1/etc/frr/frr.conf` ci sono le `set local-preference 150`.
4. **Crea laboratorio**. Atteso: si apre `lift_copia`; `lift_mio` non è cambiato.
5. Di nuovo "Parti da un lab esistente", ma nella cartella scrivi la soluzione d'esame di crab:
   `~/Work/Studio/Materie/InternetAndDataCenters/esercizi/Esami_IDC/2017-11-10-crab/solution/lab`.
   Atteso: r1-r4 sono **router** con le loro rotte statiche (pannello: "Rotte statiche"), il
   client ha "Resolver solo di questo dispositivo" = 20.0.0.3.
6. Prova anche la cartella di patchwork (`.../2024-01-22-patchwork/solution/lab`). Atteso:
   messaggio "interfacce senza indirizzo IPv4", niente caricato.
7. "Nuova bozza" per ripulire l'editor.

## 9. Terminale (bivalenza, controllo veloce)

Con la GUI chiusa o aperta su un altro lab:

```
python3 src/labGenerator.py --out ~/labs_prova
```

1. Menu principale **5) Opzioni Laboratorio** → scegli `stairs_senza_policy` → **2** (Policies
   BGP) → **3** (MED): router `as1r2`, neighbor `10.0.0.6`, valore `20`, conferma. Atteso: stesse
   righe del passo 5.2.
2. Apri la GUI su `stairs_senza_policy`: atteso `MED 20 out` sul disegno e "Annulla modifica"
   attivo con quella voce.
3. Dal terminale, Opzioni **14** (Annulla l'ultima modifica). Atteso: tolta; ricaricando il lab
   nella GUI la sigla sparisce.

---

Alla fine: scrivimi l'esito (anche solo "tutto ok" o i numeri dei passi che non tornano) e se
vuoi tenere o cancellare `~/labs_prova`.
