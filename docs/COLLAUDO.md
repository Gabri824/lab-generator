# Collaudo finale (fase 7): tennis costruito due volte

Esame: `Esami_IDC/2016-07-01-tennis` (PDF con la figura: IP, LAN, costi OSPF). Si costruisce il lab
da zero due volte, una dalla GUI e una dal terminale; ognuno si modifica poi dall'altra parte; si
avvia, si prova e si confronta con la soluzione ufficiale. Annota il numero del passo e cosa hai
visto quando qualcosa non va.

Tempo indicativo: 1-2 ore. Lavora in una cartella a parte:

```
mkdir -p ~/labs_collaudo
cd ~/Projects/lab-generator
python3 src/labGenerator.py --gui --out ~/labs_collaudo      # GUI
python3 src/labGenerator.py --out ~/labs_collaudo            # terminale
```

Nomi: `ns-local`, `ns-root`, `ns-com` e `web-srv` della figura non sono validi per Kathará; usa
`ns_local`, `ns_root` (o `root`), `ns_com`, `web_srv`.

## Requisiti della traccia e con cosa si fanno

| # | Requisito | GUI | Terminale |
|---|---|---|---|
| R1 | AS2 in RIP; as2r2 inietta in RIP le rotte BGP | zona RIP nell'editor; Modifica → as2r2 → Ridistribuzione | wizard; Opzioni 4 |
| R2 | AS20 in OSPF area 0.0.0.0; i router di confine iniettano BGP in OSPF | area OSPF nell'editor | wizard |
| R3 | Costi OSPF della figura; gli altri predefiniti | clic sull'etichetta dell'interfaccia → Costo OSPF | Opzioni 1 |
| R4 | AS1, AS2, AS10, AS20 annunciano le loro subnet interne; LAN di peering annunciate; nessuna 0.0.0.0/0 | menu dell'AS → network BGP | Opzioni 6 |
| R5 | iBGP fra i router di confine di AS20, IP coerenti con OSPF | menu dell'AS20 → Completa l'iBGP | Opzioni 7 |
| R6 | AS2 preferisce gli annunci dal link D rispetto a E | Policy BGP sul link D (local-preference) o Percorso voluto | Opzioni 2 → 2 |
| R7 | AS2 annuncia ad AS20 in modo che AS20 preferisca il link E a D | MED in uscita da AS2 sul link D | Opzioni 2 → 3 |
| R8 | as10r1 preferisce gli annunci da AS1 rispetto ad AS20 | Policy BGP di as10r1 → local-preference verso AS1 | Opzioni 2 → 2 |
| R9 | DNS: ns_local resolver di pc, ns_root root, ns_com autorità per com, web.com → 2.2.0.2 | server DNS nell'editor (root, zona com, resolver) | wizard |
| R10 | web_srv con apache2 | server WWW nell'editor | wizard |
| R11 | Pagina `http://web.com/~guest/` | non preparata dal programma (sezione 8 del piano): resta KO, va annotato | |
| G1 | pc → 2.2.0.2 per P, M, K, G, F, E, C, A | Verifica percorso, Atteso `P M K G F E C A` | |
| G2 | 2.2.0.2 → pc per A, B, D, F, H, L, P | Verifica percorso dal server web, Atteso `A B D F H L P` | |

## Parte 1: dalla GUI, poi modificato dal terminale

1. **+ Nuovo lab**: disegna tennis dalla figura (router, LAN con le lettere, riquadri AS1, AS2,
   AS10, AS20, zona RIP per AS2, area OSPF 0.0.0.0 per AS20, server DNS e WWW, pc). Scrivi gli IP
   della figura (basta l'ultimo numero se la subnet della LAN è giusta). Nome del lab:
   `tennis_gui`. **Anteprima file**, poi **Crea laboratorio**. Atteso: nessun errore; il lab si apre
   con il disegno come l'hai fatto.
2. Topologia → **Modifica**: R3 (costi), R4 (network), R5 (iBGP), R1 (ridistribuzione se serve).
   Ogni volta anteprima e Applica.
3. R6, R7, R8 con **Policy BGP** (dal router o dal link). In alternativa prova il **Percorso
   voluto** per G1: clic su pc, link P, M, K, G, F, E, C, A (o i link fra AS), destinazione LAN A;
   confronta le proposte con quelle che avresti fatto a mano.
4. Livelli **Policy** e **Sessioni BGP**: le sigle `LP ... in` e `MED ... out` sono sui link giusti?
5. Riepilogo → **Esegui la diagnostica**: atteso nessun errore.
6. Test → **Risoluzione di un nome**, da `pc`, `web.com` (lab spento): atteso ok, catena
   ns_local → root → ns_com.
7. Chiudi la GUI. **Dal terminale**: Opzioni su `tennis_gui` → cambia una cosa (per esempio il
   valore di una local-preference con Opzioni 2, o un costo con Opzioni 1). Riapri la GUI: la
   modifica si vede sul disegno e "Annulla modifica" la propone.

## Parte 2: dal terminale, poi modificato dalla GUI

8. Menu 1 (wizard): crea `tennis_term` con gli stessi dati.
9. Opzioni 1, 2, 4, 6, 7 per R1-R8 (il menu 8 Riepilogo per controllare frase per frase).
10. Opzioni 15: diagnostica di qualche router, atteso nessun errore.
11. Apri la GUI su `tennis_term` → Modifica → cambia una cosa (per esempio un MED). Torna al
    terminale: Opzioni 14 la propone come ultima modifica.

## Parte 3: per entrambi i lab, con Kathará

12. **Avvia** → **Attendi la convergenza**: BGP Established, OSPF Full; tabella Ridistribuzione
    BGP → IGP attiva (Riapplica se serve).
13. **Raggiungibilità**: tutto OK.
14. **Verifica percorso** G1 (da pc verso 2.2.0.2, Atteso `P M K G F E C A`, "deve passare per")
    e G2 (spunta "anche il ritorno", Atteso al ritorno `A B D F H L P`). Guarda i costi OSPF
    mostrati sotto.
15. **Server web** da pc: pagina di 2.2.0.2 e di web.com ricevute. `http://web.com/~guest/`
    (campo links nel pannello di pc): atteso "Not Found" (R11).
16. **Risoluzione di un nome** da pc, web.com, a lab acceso: dig ok sul resolver, rinvio dal root,
    risposta da ns_com.
17. **Ferma**.

## Parte 4: confronto con la soluzione e consegna

18. Confronto con la soluzione ufficiale (per ogni lab):

    ```
    python3 tests/strumenti/confronta_lab.py ~/labs_collaudo/tennis_gui \
        ~/Work/Studio/Materie/InternetAndDataCenters/esercizi/Esami_IDC/2016-07-01-tennis --policy
    ```

    Atteso: controlli base OK; le policy sono elencate per confronto (i nomi possono differire).
19. Scheda **Archivio** su `tennis_gui`: archivio creato senza XML, nome uguale alla cartella.

## Esito

Scrivi i numeri dei passi che non tornano (o "tutto ok"). R11 KO è atteso.
