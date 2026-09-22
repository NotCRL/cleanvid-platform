# Registro degli interventi

Ogni cosa che entra nel codice lascia una riga qui. Non un elenco di commit —
quello lo fa git — ma il perché: cosa è cambiato, com'è fatto, perché così, e
come si è verificato che funzioni.

La regola, presa il 22/09/2026: **nulla entra nel codice senza la sua riga
qui.** Vale per una funzione nuova, per un bug, per una scelta di struttura.
Le voci si aggiungono in fondo, con la data.

Formato: *Cosa cambia / Come è fatto / Perché così / Verificato*.

---

## 2026-09-22 — Passo 1: database, utente anonimo, una pagina che apre un video

**Cosa cambia.** Il progetto passa da scaffolding a servizio che si apre nel
browser. Chi arriva sulla home riceve un utente vero, incolla un indirizzo,
vede il video, e ritrova quello che ha aperto nella sua cronologia. Nessuna
funzione nuova rispetto a `cleanvid`: serve a dimostrare una cosa sola, cioè
che la biblioteca per persona regge.

**Come è fatto.**

- `db.py` — un solo motore e una sola `sessionmaker` per processo, creati alla
  prima richiesta e non all'import. `pool_pre_ping=True` perché una
  connessione che Postgres ha chiuso nella notte non deve diventare l'errore
  del primo visitatore del mattino. La dipendenza `sessione()` fa commit se la
  richiesta è andata a buon fine e rollback se ha sollevato: nessuna rotta
  deve ricordarsi di farlo.
- `api/identita.py` — `utente_corrente()`. Legge il cookie `cv_id`, firmato con
  `itsdangerous`; se non c'è, o la firma non torna, o la riga non esiste più,
  crea un utente anonimo con un nome di cortesia (`Lontra 417`) e lo segna su
  `request.state`. Il cookie contiene solo l'id, firmato e non cifrato: chi lo
  legge vede un UUID, che non è un segreto; la firma serve a impedire che uno
  si scriva l'id di un altro, che è la sola cosa che conta.
- `main.py` — un middleware attacca il cookie alla risposta che parte davvero.
- `api/biblioteca.py` — `annota_visita()` con `ON CONFLICT ... DO UPDATE`, così
  riaprire lo stesso video sposta in cima la riga che c'è invece di farne una
  nuova. La `WHERE titolo_tuo IS false` protegge i titoli messi a mano.
- `api/routes_watch.py` — `/`, `POST /apri`, `/guarda?u=`, `/stato`.
- `media/embed.py` — prima parte del trasloco della logica video: tabella di
  espressioni regolari per YouTube, Vimeo, Dailymotion, Streamable e Twitch.
- Migrazione `7dbb0c954bd3`: `utenti`, `biblioteca`, `stanze`, `membri_stanza`,
  `messaggi_stanza`.

**Perché così.**

- *Anonimo e registrato sono la stessa riga.* Non esiste una modalità "senza
  utente": significherebbe scrivere due volte ogni funzione, una per chi ha un
  account e una per chi no, e il giorno della registrazione dover travasare la
  cronologia da una parte all'altra. Chi si registrerà attaccherà delle
  credenziali alla riga che ha già, senza perdere niente.
- *`POST /apri` risponde con un redirect,* non con la pagina. Così la pagina
  del video ha un indirizzo suo, che si può ricaricare, salvare e mandare a
  qualcuno — cosa che servirà appena ci saranno le stanze.
- *`utente_id` nel filtro, non nella fiducia.* Ogni query della biblioteca ha
  `utente_id` nel `WHERE`. Non si carica una voce per id sperando che sia di
  chi la chiede.
- *Al passo 1 solo i lettori ufficiali.* Niente yt-dlp, niente processi
  esterni: l'estrazione è il passo successivo, e mescolarla qui avrebbe
  impedito di capire se un problema era dell'identità o dell'estrazione.

**Verificato.** A mano, due browser separati: due utenti distinti (`Airone
450`, `Airone 760`), due voci di cronologia sul primo, zero sul secondo, e nel
database due utenti con un solo proprietario delle due voci. Poi
`tests/test_identita.py`, 7 test, tutti verdi, su un database `cleanvid_test`
separato da quello di sviluppo.

---

## 2026-09-22 — Bug: il cookie dell'utente non partiva mai

**Cosa succedeva.** Ogni richiesta creava un utente nuovo. Dopo pochi minuti di
prove il database aveva sei utenti e nessuna cronologia: ogni pagina ricaricata
era una persona diversa. Nessun errore, nessun log rosso — semplicemente il
`Set-Cookie` non c'era nella risposta.

**La causa.** `utente_corrente()` scriveva il cookie sull'oggetto `Response`
iniettato da FastAPI nella dipendenza. Quello funziona solo se la rotta
restituisce dei dati e lascia costruire la risposta a FastAPI. Le nostre rotte
restituiscono una risposta propria — `TemplateResponse`, `RedirectResponse` —
e in quel caso gli header messi sull'oggetto iniettato vengono buttati via.

**Il rimedio.** La dipendenza non scrive più il cookie: segna l'id su
`request.state` sotto una chiave nota, e un middleware in `main.py` lo attacca
alla risposta vera, qualunque forma abbia. È l'unico punto del giro che ha in
mano la risposta che parte davvero.

**Perché non un `BackgroundTask` o un decoratore per rotta.** Il primo gira
dopo che la risposta è partita, troppo tardi per un header. Il secondo va
ricordato su ogni rotta nuova, e la prima volta che ci si dimentica il bug
torna identico e silenzioso come la prima volta.

**Verificato.** `test_chi_arriva_e_subito_un_utente` (il cookie c'è) e
`test_il_cookie_riporta_alla_stessa_riga` (due visite, stesso identificativo).
Con il codice di prima entrambi falliscono: è stato provato rimettendo la
vecchia versione prima di considerare il bug chiuso.

---

## 2026-09-22 — Test: un solo ciclo asyncio per tutta la sessione

**Cosa cambia.** In `pyproject.toml`, `asyncio_default_fixture_loop_scope` e
`asyncio_default_test_loop_scope` a `"session"`.

**Perché.** Con i valori predefiniti pytest-asyncio apre un ciclo nuovo per
ogni test, mentre il motore del database e le sue connessioni nascono nel
ciclo della prima fixture. asyncpg non accetta di essere usato da un ciclo
diverso da quello in cui è nato, e dal secondo test in poi arriva
`attached to a different loop`. Non è un problema dei test: è la stessa
ragione per cui il motore deve essere uno solo per processo.

**Verificato.** `pytest -q` → 7 passed.

---

## 2026-09-22 — Un test sbagliato che accusava il codice giusto

Vale la pena tenerne traccia. `test_riaprire_non_duplica` contava quante volte
l'indirizzo comparisse nella home e si aspettava 1, trovando 2: sembrava che
`ON CONFLICT` non funzionasse. In realtà ogni voce scrive l'indirizzo due
volte — una nel collegamento e una come titolo provvisorio, finché un titolo
vero non c'è. Il codice era giusto, il test no.

Prima di toccare il codice si è guardato cosa fossero davvero quelle due
occorrenze. Ora il test conta i collegamenti (`href="/guarda?u=`), che è la
cosa che si voleva misurare.

---

## 2026-09-22 — Ruff e mypy puliti, e cosa si è scelto di ignorare

**Cosa cambia.** `ruff check src tests` e `mypy src` passano senza errori, e da
ora è la condizione per considerare finito un intervento.

**Cosa è stato messo a posto davvero.** Annotazioni di ritorno mancanti sulle
rotte e sul middleware, `dict` senza argomenti nel campo JSONB, import fuori
ordine.

**Cosa è stato ignorato, e perché.** Un avviso che si mette a tacere senza
scriverne il motivo torna utile a nessuno.

- `B008` — `Depends(...)` nei valori predefiniti non è una svista: è il modo
  in cui si scrive FastAPI.
- `UP042` — `str, Enum` invece di `StrEnum` è voluto: così il valore che
  finisce nella colonna Postgres è la stringa scritta nel modello, leggibile
  in un `psql`, e non dipende da come l'enum viene serializzato.
- `S101` solo in `tests/` — gli assert sono il linguaggio dei test.
- `S311` sul nome di cortesia — `random` e non `secrets` perché è un nome da
  mostrare in chat, non un segreto; l'identità sta nel cookie firmato.

**Verificato.** `ruff check src tests` → all checks passed; `mypy src` → no
issues in 17 files; `make prova` → 7 passed.


---

## 2026-09-22 — Passo 2: il trasloco di `media/`

**Cosa cambia.** Un link senza lettore ufficiale ora dà comunque un video. Si
estrae il flusso con yt-dlp, si serve dal nostro proxy con le intestazioni
giuste, e la pubblicità cucita dentro il flusso sparisce per strada.

**Come è fatto.** Sei moduli, ognuno con un mestiere solo:

| Modulo | Cosa fa |
|---|---|
| `qualita.py` | da «720» al selettore di yt-dlp. Nessuna rete: si prova tutto |
| `estrazione.py` | lancia yt-dlp, decide fra file unico, due tracce e master HLS |
| `manifesto.py` | costruisce i master, riscrive le playlist, toglie gli spot |
| `firme.py` | l'HMAC che ci impedisce di essere un proxy aperto |
| `proxy.py` | i byte, con Range e connessioni riusate |
| `deposito.py` | dove vivono i flussi e la cache, cioè Redis |

**Le quattro decisioni che contano.**

*Il dizionario globale non poteva passare.* Nel file unico i flussi stavano in
`STREAMS[token]`: un processo solo, un utente solo. Con più worker il token
registrato dal worker A arriva al worker B che non sa cosa sia — il video
parte una volta su quattro e nessuno capisce perché. E niente scadeva mai.
Ora è Redis, con una scadenza su ogni chiave.

*La cache ha per chiave `(url, qualità)` e non l'utente.* yt-dlp costa cinque
secondi di CPU misurati; dieci persone nella stessa stanza devono costarne
uno. Un'estrazione non ha niente di personale — è una proprietà del link, non
di chi lo apre — quindi condividerla non mescola le cose di nessuno. Il
controllo si rifà **dentro** il semaforo: senza, dieci aperture simultanee
farebbero dieci estrazioni, cioè esattamente ciò che la cache doveva evitare.

*Asincrono, non `subprocess.run`.* Nel file unico ogni richiesta aveva il suo
thread. Qui c'è un ciclo di eventi solo: cinque secondi bloccanti sono cinque
secondi in cui non si muove nient'altro — non le altre pagine, non le chat
delle stanze, non i byte dei video già in corso.

*Il muxing in diretta non è passato.* yt-dlp e ffmpeg che cuciono video e
audio mentre si guarda costano un processo per spettatore, non permettono di
saltare avanti e producono un formato che metà browser non suona. In locale
era un ripiego accettabile; su un servizio aperto è il modo di far cadere la
macchina con dieci persone. Al suo posto: due tracce separate che il browser
tiene allineate da solo, e il master HLS per le dirette. Costo sul server:
zero, a parte i byte.

**Verificato, su flussi veri e non finti.**

```
video 480p, due tracce: True, "Luis Fonsi - Despacito ft. Daddy Yankee"
  video: 206 video/mp4 -> 2000000 byte
  audio: 206 audio/mp4 -> 2000000 byte
prima estrazione 5.01s | dalla cache 0.00s, stesso token
diretta (Sky News): hls=True, master con 4 qualità
  variante: 200, 445 segmenti riscritti sul nostro proxy
```

Più 34 test automatici, di cui 12 sul solo `manifesto.py`: è il pezzo con più
casi strani del progetto, ed è tutto testo che entra e testo che esce, quindi
si può provare davvero.

---

## 2026-09-22 — Bug: il video si apriva e non arrivava un byte

**Cosa succedeva.** Il proxy rispondeva 206, con il `Content-Range` giusto, e
poi il corpo era vuoto. Nessun errore nei log.

**La causa.** Per capire se quello che arriva è una playlist o un pezzo di
video bisogna guardare i primi sette byte — i server di Google etichettano
`mpegurl` anche i segmenti, quindi il `Content-Type` non si può credere.
Leggevo quei sette byte con `aiter_bytes(7)`, e poi riaprivo l'iterazione per
servire il resto. Ma **lo stream di httpx si legge una volta sola**: la
seconda `aiter_bytes` solleva `StreamConsumed`, anche se la prima si era
fermata dopo sette byte.

**Il rimedio.** Una dataclass `Sorgente` che tiene insieme la risposta,
l'iteratore aperto **una volta sola**, e il primo boccone già letto. I byte
già letti viaggiano con lei, perché rimetterli dentro non si può.

**Perché non bufferizzare tutto e poi decidere.** Un segmento sono megabyte, e
un film sono gigabyte: tenerli in memoria per guardarne l'inizio vorrebbe dire
un server che muore al terzo spettatore.

**Verificato.** Cinque test contro un sito finto servito su **HTTP vero** — una
applicazione ASGI con cui httpx parla come parlerebbe con la rete, stesso
streaming, stesso Range, stesse intestazioni. Una finzione messa più in su del
proxy non avrebbe visto niente, perché il bug stava proprio nel modo in cui
httpx consegna i byte. Poi di nuovo a mano contro googlevideo: 2 MB richiesti,
2 MB arrivati, su entrambe le tracce.

---

## 2026-09-22 — Il sito in quattordici lingue, e la SEO che lo rende utile

**Cosa cambia.** Le pagine stanno sotto `/{lingua}/`, in quattordici lingue.
La lingua si cambia dalle impostazioni (l'ingranaggio in alto a destra, che
mostra anche quella attuale). Chi arriva sulla radice viene mandato nella
lingua del suo browser. C'è uno strumento che traduce i testi con Claude e
lascia il risultato su disco.

**Come è fatto e perché così:** per esteso in
[`LINGUE-E-SEO.md`](LINGUE-E-SEO.md). In breve, le cinque decisioni:

1. la lingua sta nell'indirizzo e non in un cookie — un motore indicizza
   indirizzi, non sessioni;
2. non si reindirizza in base al paese — Google visita da indirizzi americani e
   non vedrebbe mai le altre tredici lingue, e chi usa una VPN resterebbe
   inchiodato a una lingua che non ha scelto;
3. le hreflang si generano da una funzione sola, perché devono essere
   reciproche e Google butta via in blocco i gruppi che non tornano;
4. `/guarda` è `noindex` — uno spazio di indirizzi infinito di pagine sottili
   con dentro roba di altri non ci premia, ci classifica come sito di scarto;
5. si traduce prima e non a richiesta, e il risultato si committa e si rilegge.

**Cosa NON è stato fatto, ed è una scelta.** Niente geolocalizzazione per IP.
Era nella richiesta, e per la lingua è lo strumento sbagliato: dice dov'è il
router, non che lingua parla la persona. `Accept-Language` risponde alla
domanda giusta, e un italiano a Berlino ha ancora `it` in cima. Se un giorno
servirà davvero — per il fuso orario, o per quali piattaforme mostrare — si
aggiungerà per quello, non per la lingua.

**Verificato.** 51 test, fra cui: i quattordici cataloghi hanno le stesse 68
chiavi e gli stessi segnaposto; i gruppi di hreflang di tre lingue diverse sono
identici; ogni domanda dichiarata nei dati strutturati compare davvero
nell'HTML. Poi a mano, sul server: `/ar/` esce con `dir=rtl`, `/ja/` con il
titolo giapponese, il cambio lingua dalle impostazioni cambia anche dove porta
la radice, e un browser tedesco su una pagina italiana si vede proporre il
tedesco senza essere portato via.

---

## 2026-09-22 — Bug: la mappa del sito e il canonical dicevano indirizzi diversi

**Cosa succedeva.** `sitemap.xml` dichiarava `https://…/it`, l'HTML della
stessa pagina dichiarava `rel=canonical https://…/it/`. Per un motore di
ricerca sono **due indirizzi diversi**: ci si contraddiceva da soli su ogni
pagina del sito, in quattordici lingue.

**La causa.** La home era scritta come percorso vuoto nell'elenco delle pagine
indicizzabili, mentre il `canonical` nasce dal percorso della richiesta, che
per la home è `/`.

**Il rimedio.** La home è `/` anche nell'elenco. Una riga, con sopra scritto il
perché.

**Come si è trovato.** Da un test che confrontava le due cose. Non si sarebbe
visto in nessun altro modo: il sito funzionava, le pagine si aprivano, e
l'effetto sarebbe comparso mesi dopo nelle statistiche di ricerca. È il motivo
per cui i test su questa parte sono più pedanti degli altri.
