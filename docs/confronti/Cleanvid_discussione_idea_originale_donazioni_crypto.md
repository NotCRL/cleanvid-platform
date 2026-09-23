# Cleanvid — discussione aggiornata: idea originale, gratuito, donazioni e sviluppo futuro

Data: 23 settembre 2026

## 1. Il punto di partenza reale

L'idea originale di Cleanvid è molto più semplice di tutto ciò che è nato successivamente:

> Prendere un singolo URL, cercare/scoprire le fonti video disponibili, mostrarle all'utente e permettergli di scegliere quale fonte riprodurre.

Questa funzione è il cuore del progetto.

Non nasce come catalogo di film, come alternativa a Netflix, come clone di Stremio o come piattaforma torrent. YouTube, Twitch, Vimeo e gli altri siti sono esempi di sorgenti che Cleanvid può incontrare, non il perimetro concettuale del prodotto.

La direzione corretta resta quindi:

```text
URL
 ↓
Universal Media Discovery
 ↓
fonti video individuate
 ↓
scelta dell'utente
 ↓
player
```

## 2. La parte che vorrei lasciare gratuita

La parte fondamentale dovrebbe essere libera:

- inserire un URL;
- cercare/scoprire la sorgente video;
- individuare eventuali fonti alternative;
- mostrare all'utente le fonti disponibili;
- permettere di scegliere la fonte;
- riprodurre il contenuto;
- usare le funzionalità base del player.

Questa non dovrebbe essere una funzione artificiosamente limitata per spingere l'utente a pagare.

L'idea è che Cleanvid sia utile già da solo, anche senza account e senza pagamento.

## 3. Tutto il resto è nato dopo

Nel corso dello sviluppo sono emerse altre idee:

- registrazione/account;
- stanze;
- watch party;
- chat;
- sincronizzazione;
- biblioteca personale;
- eventuale P2P;
- eventuale torrent;
- addon;
- web app;
- applicazione desktop;
- eventuali servizi persistenti.

Queste funzionalità non sostituiscono il cuore originale: gli si costruiscono attorno.

La distinzione concettuale diventa:

```text
                         CLEANVID
                            │
              ┌─────────────┴─────────────┐
              │                           │
        CORE ORIGINALE               SERVIZI EXTRA
              │                           │
       URL → Discovery                    │
              ↓                           │
       fonti disponibili                  │
              ↓                           │
       scelta dell'utente                │
              ↓                           │
           Player                         │
                                          │
                  stanze / account / sync /
                  chat / biblioteca / ecc.
```

## 4. Una precisazione importante sul "pagamento"

Il termine pagamento rischia di descrivere male l'idea originale.

Non stavo pensando necessariamente a un modello:

> "paghi e sblocchi il player".

L'idea era molto più casereccia e semplice: **una forma di donazione al progetto**.

In questo senso, l'utente può usare Cleanvid gratuitamente e, se gli piace il progetto e vuole sostenerlo, può contribuire economicamente.

Quindi il modello iniziale immaginato è più vicino a:

```text
Cleanvid
   │
   ├── utilizzo gratuito
   │
   └── "Ti piace? Puoi sostenere il progetto"
             │
             ├── PayPal o servizio simile
             └── crypto
```

La crypto, quindi, non nasce dall'idea di creare una "economia Cleanvid" o un token proprietario. È semplicemente uno dei possibili strumenti con cui una persona può fare una donazione.

## 5. Donazione ≠ Premium

È importante non confondere due concetti che possono essere valutati separatamente in futuro.

### Donazione

L'utente paga perché vuole sostenere il progetto.

Non necessariamente riceve funzionalità aggiuntive.

```text
uso gratuito
      +
donazione volontaria
      ↓
sostegno al progetto
```

### Premium

L'utente paga perché riceve qualcosa in cambio, per esempio servizi che hanno un costo infrastrutturale:

- stanze più grandi;
- maggiore durata delle stanze;
- sincronizzazione cloud;
- biblioteca sincronizzata;
- maggiore spazio;
- relay/infrastruttura;
- altre funzioni che richiedono risorse del server.

Questo secondo modello potrebbe eventualmente arrivare più avanti, ma **non è la premessa da cui è nato Cleanvid**.

## 6. Perché questa distinzione è importante

La distinzione mantiene l'identità del progetto.

Il rischio sarebbe trasformare progressivamente:

```text
"uno strumento gratuito che risolve un problema"
```

in:

```text
"un servizio a pagamento che offre accesso ai contenuti"
```

Sono due prodotti concettualmente diversi.

L'idea originale è invece:

> Cleanvid non vende il contenuto. Fornisce uno strumento per scoprire e riprodurre una sorgente indicata dall'utente.

Eventuali servizi a pagamento, se arriveranno, dovrebbero stare principalmente intorno a questa funzione.

## 7. Crypto, PayPal e semplicità

Per una prima versione pubblica, la filosofia potrebbe essere estremamente semplice:

- nessun token proprietario;
- nessuna blockchain necessaria al funzionamento;
- nessun sistema di crediti complicato;
- nessuna economia interna;
- nessun obbligo di pagamento.

Semplicemente un'area del tipo:

> "Se Cleanvid ti è utile e vuoi sostenere il progetto, puoi fare una donazione."

Con uno o più metodi di pagamento.

Crypto e PayPal (o servizi analoghi) sono quindi **metodi di donazione**, non caratteristiche fondamentali del prodotto.

Le implicazioni fiscali, normative e operative di una raccolta di donazioni vanno comunque verificate prima di pubblicare il servizio, soprattutto se diventa un progetto pubblico e continuativo.

## 8. Come si collega a torrent e P2P

La stessa filosofia vale per il torrent.

Il torrent può essere considerato un possibile backend/mezzo tecnico:

```text
Stream
 ├── HTTP
 ├── HLS
 ├── DASH
 ├── locale
 └── torrent
```

ma non deve diventare l'identità di Cleanvid.

La discussione precedente ha inoltre evidenziato una distinzione importante:

- il torrent può avere senso come tecnologia di consegna;
- la sincronizzazione delle watch party è un problema diverso;
- il P2P può ridurre la banda del server, ma ha conseguenze sulla visibilità degli IP;
- un client desktop è il luogo più naturale per funzioni come torrent nativo, browser/CDP e file locali.

Il documento precedente concludeva inoltre che non si dovrebbe costruire un catalogo finalizzato a trovare copie non autorizzate.

## 9. Web app e desktop app

La visione che sta emergendo è quindi quella di due superfici diverse:

### Web app

Pensata soprattutto per:

- player;
- discovery;
- account;
- stanze;
- chat;
- watch party;
- servizi online.

### Desktop app

Pensata per funzioni che richiedono il controllo della macchina dell'utente:

- browser/CDP;
- sorgenti locali;
- torrent nativo;
- eventuali addon;
- cache e altre funzioni locali.

Non è necessario che web e desktop condividano tutto il codice. È più importante che condividano gli stessi concetti e modelli, dove conviene.

## 10. Architettura concettuale aggiornata

La parte centrale resta:

```text
                         URL
                          │
                          ▼
                UNIVERSAL DISCOVERY
                          │
          ┌───────────────┼────────────────┐
          ▼               ▼                ▼
       direct          HTML/embed      yt-dlp/browser
          │               │                │
          └───────────────┼────────────────┘
                          ▼
                    MEDIA / STREAM
                          │
          ┌───────────────┼────────────────┐
          ▼               ▼                ▼
        HTTP             HLS            Torrent
          │               │                │
          └───────────────┼────────────────┘
                          ▼
                        PLAYER
```

Sopra questo nucleo possono esistere:

```text
account
stanze
watch party
chat
biblioteca
sincronizzazione
eventuali servizi premium
donazioni
```

## 11. Principio guida

Una formulazione che potrebbe diventare importante per il progetto è:

> **Il valore fondamentale di Cleanvid è la scoperta e la riproduzione universale delle fonti. Questa parte resta gratuita. Il sostegno economico, inizialmente, può essere semplicemente volontario; eventuali servizi premium potranno essere valutati in seguito in base ai costi reali e all'uso del progetto.**

Questo permette di non decidere oggi un modello economico definitivo.

Prima si costruisce qualcosa che le persone trovano utile.

Poi si osserva cosa usano davvero.

Solo dopo si decide se e quali servizi meritano un modello Premium.

## 12. Punto da portare nella prossima discussione con Claude

La domanda non dovrebbe più essere semplicemente:

> "Come facciamo pagare Cleanvid?"

Meglio:

> "Considerando che la funzione originale — URL → discovery delle fonti → scelta della fonte → player — deve rimanere gratuita, come progetteresti il progetto affinché possa essere sostenuto economicamente tramite donazioni volontarie (PayPal/crypto o simili), lasciando aperta la possibilità futura di servizi Premium che coprano i costi infrastrutturali?"

E insieme:

> "Quali parti dovrebbero rimanere assolutamente gratuite per non perdere l'identità originale di Cleanvid, e quali servizi futuri potrebbero ragionevolmente richiedere infrastruttura a pagamento?"

Questo è il punto da cui continuare la progettazione.
