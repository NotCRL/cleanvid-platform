# Risposta al dossier comparativo

Seconda lettura del documento [`CONFRONTI.md`](CONFRONTI.md), che confronta
cleanvid con Stremio e Hydra e propone una direzione architetturale.

Data: 23 settembre 2026.

---

## In breve

Il dossier è un lavoro competente: fonti vere e verificabili, distinzione
esplicita fra fatti osservati, osservazioni sul codice e inferenze,
conclusioni prudenti. Su torrent e modalità ascolto arriva alle stesse
conclusioni a cui eravamo arrivati noi, per strade diverse.

Ha però un problema alla radice: **ha analizzato il progetto sbagliato**. E
tre sezioni su venti contengono roba che vale la pena prendere davvero.

---

## 1. Il problema alla radice

Il dossier descrive `~/cleanvid` — il file unico da 7.747 righe — e propone
una roadmap in sei fasi per modularizzarlo.

**Quelle sei fasi sono già state fatte**, il 21 e 22 settembre 2026, in
`cleanvid-platform`: la cartella dentro cui il dossier stesso è stato
salvato.

| Il dossier propone (§17) | Da noi si chiama | Quando |
|---|---|---|
| Fase 1 — congelare la baseline | `~/cleanvid` resta in piedi e committato | 22/09 |
| Fase 2 — segreti, `.gitignore`, env d'esempio | passo 1 | 22/09 |
| Fase 3 — estrarre per primo `streaming/hls.py` | `media/manifesto.py` | passo 2 |
| Fase 3 — poi `sources/`, `extraction/ytdlp.py` | `media/embed.py`, `media/estrazione.py` | passo 2 |
| Fase 4 — introdurre i modelli | `models/` + migrazioni Alembic | passo 1 |
| Fase 5 — test dalle funzioni pure | 141 test | in corso |
| Fase 6 — separare UI e backend | `api/` + `web/` + `models/` | passo 1 |

I sette test proposti al §11 — playlist senza spot invariata, `CUE-OUT`,
`CUE-IN`, `DATERANGE` di Twitch, URL relativi, URI con query, master con le
varianti — **esistono già, uno per uno**, in `tests/test_manifesto.py`.

Non è una colpa del dossier: gli è stato dato in pasto il file vecchio. Ma
seguirlo così com'è scritto vuol dire rifare due giorni di lavoro.

---

## 2. Dove converge, e perché conta

Un'analisi indipendente, partita da zero e con un altro modello, ha scelto
**la stessa prima mossa**: estrarre per primo il modulo HLS, perché è codice
puro — entra testo, esce testo — e non obbliga a toccare la UI.

Converge anche su altre due decisioni che avevamo già preso:

- **niente torrent** (§15): non risolve il problema di cleanvid, che è
  aggregazione, cambio sorgente, riproduzione, disposizione, filtraggio;
- **la modalità ascolto è il pezzo più pericoloso** (§13): un browser vero
  con dentro cookie e sessioni, guidato da chi sta dall'altra parte.

Quando due strade indipendenti arrivano allo stesso punto, quel punto era
probabilmente giusto. È il valore vero di questo dossier: non il piano, la
conferma.

---

## 3. Le tre cose che vale la pena prendere

### 3.1 `Source → Stream → Player`, ma in piccolo

Qui il dossier ha ragione su un difetto vero del nostro codice, e lo vede da
fuori meglio di come lo vedevamo da dentro.

Abbiamo **due tipi diversi per la stessa cosa**:

- `Lettore` (`media/embed.py`) — il lettore incorporabile di una piattaforma;
- `Estratto` (`media/estrazione.py`) — il flusso estratto da noi.

La pagina deve distinguerli **22 volte in `guarda.html`**, 8 in `cella.html`,
4 in `routes_watch.py`, 2 in `routes_muro.py`. Ogni funzione nuova — il
bagliore, le viste, il piccolo schermo, la ripresa — va pensata due volte, e
ogni volta si decide di nuovo cosa fare nel caso dell'iframe.

Unificarli in un solo descrittore è lavoro vero e utile.

**Quello che invece non prenderei** è il registro di provider con
`can_handle()` / `resolve()` del §9. Abbiamo due resolver, e **yt-dlp è già
il sistema a plugin**, per circa 1.800 siti. Un'interfaccia costruita per
contenere due implementazioni è cerimonia: aggiunge un livello da leggere e
non toglie niente da scrivere.

Lo dice il dossier stesso al §15 — *«Non rendere tutto un plugin. Prima
bisogna definire bene le interfacce interne»* — e poi al §9 propone
esattamente quello. È l'unica contraddizione interna del documento.

### 3.2 I sottotitoli

Compaiono nel suo oggetto `Stream` (§7, §10) quasi di sfuggita, e da noi
**non esistono proprio**. yt-dlp li restituisce gratis insieme al resto.

È la cosa con il miglior rapporto fra valore e costo di tutto il dossier, e
ci arriva di sponda: non la propone, la elenca. Ma elencandola mostra un buco
che non avevamo notato.

### 3.3 Il confine legale e di prodotto (§14)

È la parte migliore del documento, e la più urgente — più di qualunque
questione di architettura.

Rafforza una cosa già segnalata nel registro: la riga in fondo a ogni pagina
dice *«Gira sul tuo computer: i link che apri e quelli che salvi restano
qui»*, ed è vera **finché il servizio gira in locale**. Il giorno che va
online su un dominio pubblico diventa falsa, ed è una frase sulla privacy.

Da fare prima di pubblicare, non dopo:

- cambiare quella riga in tutte e quattordici le lingue;
- una pagina «cos'è», con il posizionamento scritto nero su bianco;
- un contatto per le segnalazioni.

---

## 4. Dove manderebbe indietro

### 4.1 L'albero del §8

Mette `filtering/network.py`, `filtering/cosmetic.py`, `filtering/popup.py` e
tutto `browser/` fra i moduli **centrali**.

Quei tre filtri e il browser appartengono alla modalità ascolto, che su un
servizio pubblico **non può esistere** — decisione già presa e scritta in
[`ARCHITETTURA.md`](../ARCHITETTURA.md), sezione *Cosa non passa di qui*.
Apre un Chromium vero sulla macchina che ospita e lo lascia guidare da chi
sta dall'altra parte: in casa è una comodità, online è dare il proprio
browser a chiunque.

Costruire quella struttura vuol dire apparecchiare per una funzione che
abbiamo deliberatamente lasciato indietro.

### 4.2 Il §12 dice una cosa giusta e ne manca una

*«Non costruire un unico mega adblocker che usa substring come `ad`, perché
rischia di bloccare CDN o componenti legittimi del player»* — giusto, e
infatti non lo facciamo.

Ma non poteva sapere quello che si è misurato la notte del 22: **su Twitch il
segnale della pubblicità non sono i marker, è il titolo del segmento.**
`#EXTINF:2.000,live` è diretta vera; `#EXTINF:2.000,Amazon|2474283100494` è
uno spot. I marker standard — `CUE-OUT`, `DATERANGE` di classe
`twitch-stitched-ad` — a volte ci sono e a volte no.

Un'analisi fatta leggendo il codice, senza aprire una playlist in diretta,
a quella conclusione non ci arriva. È il limite di questo genere di dossier,
e vale la pena tenerlo a mente per i prossimi.

---

## 5. Il punto cieco

Il dossier non nomina mai **registrazione, stanze, watchparty, chat**.

Cioè l'intero motivo per cui `cleanvid-platform` esiste invece di essere una
ripulita del file unico. La domanda *«come si condivide una sessione di
visione fra dieci persone»* non compare in venti sezioni — ed è quella che
decide più cose di qualunque astrazione `Source`: decide il database, decide
che anonimo e registrato siano la stessa riga, decide che il polso della
riproduzione vada in Redis e non su disco.

Ha analizzato uno strumento locale monoutente, e quindi propone l'architettura
di uno strumento locale monoutente. Coerente con quello che ha letto, e a
lato rispetto a dove stiamo andando.

---

## 6. Cosa faremmo, in ordine

1. **Unificare `Lettore` ed `Estratto`** in un solo descrittore. Mezza
   giornata, toglie 36 ramificazioni sparse fra modelli e rotte.
2. **Sottotitoli.** yt-dlp li dà già; mancano del tutto.
3. **Testo legale, pagina «cos'è», contatto.** Prima di pubblicare.
4. **Registrazione** (passo 4) e poi **stanze** (passo 5-7): la cosa più
   importante, e quella che il dossier non vede.

Il resto è già fatto, oppure è apparato per funzioni che non porteremo.

---

## 7. Una nota sul metodo

Il dossier chiede, al §18, una seconda opinione su dieci domande. Vale la pena
rispondere alla più generale — *«è davvero utile introdurre una Source/Stream
abstraction oppure sarebbe over-engineering?»* — perché la risposta non è né
sì né no:

> È utile **come unificazione di due tipi che esistono già e si fanno
> concorrenza**. È over-engineering **come interfaccia a plugin per sorgenti
> future che non sappiamo se arriveranno**.

La differenza fra le due non sta nel codice, che somiglia: sta nel fatto che
la prima toglie qualcosa che oggi fa male, la seconda aggiunge qualcosa in
previsione di un male che forse non verrà.

È lo stesso criterio che sta in [`CONVENZIONI.md`](../CONVENZIONI.md), e vale
anche qui.
