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

---

## 2026-09-22 — Passo 3: la biblioteca completa, con le copertine

**Cosa cambia.** La home non è più un elenco di link: sono scaffali di
copertine. *Continua a guardare*, *Preferiti*, *Fonti salvate*, *Gruppi*,
*Aperti di recente*. Ogni scheda ha la stella e il cestino; sotto quelle
lasciate a metà c'è la barretta di avanzamento e il tempo. La pagina del video
riprende da dove si era rimasti, con un «ricomincia» accanto.

**Come è fatto.**

| Dove | Cosa |
|---|---|
| `media/copertine.py` | trova e scarica l'immagine, dal modo più economico in giù |
| `api/routes_copertina.py` | `/copertina?u=…&s=…`, firmata |
| `api/biblioteca.py` | preferiti, fonti, gruppi, potatura, continua a guardare |
| `api/routes_biblioteca.py` | i bottoni: stella, cestino, rinomina, posizione |
| `web/pagine.py` | un solo ambiente Jinja, con i filtri `copertina` e `mm_ss` |
| `web/templates/_pezzi.html` | la scheda e lo scaffale, scritti una volta sola |

**Le decisioni che contano.**

*Le immagini le scarica il server.* Se in pagina ci fosse l'indirizzo di
`i.ytimg.com`, ogni copertina sarebbe una richiesta dal browser di chi guarda
verso YouTube, con il suo IP e i suoi cookie: la home di cleanvid direbbe a
mezzo mondo cosa guarda. Passando da qui, la piattaforma vede solo noi.

*Si cerca dal modo più economico in giù,* e ci si ferma al primo che risponde:
un indirizzo che si costruisce da soli (YouTube, Twitch) costa zero, una
oEmbed una richiesta, l'`og:image` una richiesta più grande, yt-dlp dei
secondi. Chiamare yt-dlp per ogni copertina di una pagina con venti voci
vorrebbe dire venti processi per disegnare una griglia.

*I buchi si ricordano.* Una pagina senza copertina si riprova dopo un quarto
d'ora, non alla richiesta dopo. Senza, ogni apertura della home farebbe
ripartire la ricerca per tutte le voci che non ne hanno.

*Tutto `POST`, niente `GET` che cancella.* Un `GET` distruttivo viene eseguito
dal precaricamento del browser, dall'anteprima di una chat e dal crawler di un
motore: la cronologia sparirebbe da sola e nessuno capirebbe perché.

*Il `Referer` non si crede sulla parola.* Dopo un bottone si torna da dove si
era, ma solo se l'indirizzo è nostro: un Referer arriva dal browser, e un
browser può dire qualunque cosa, compreso un sito dove mandare la gente.

*Uno scaffale vuoto e senza niente da dire non si mostra.* Un'intestazione
sopra il nulla fa sembrare rotto un sito che funziona.

**Cosa è rimasto a metà, e lo dico invece di nasconderlo.** Il genere `FONTE`
esiste, è testato e non ha ancora niente che lo riempia: nel cleanvid a file
unico le fonti arrivavano dalla modalità ascolto, che qui non passa. Non ho
inventato un bottone «salva la fonte» sul flusso estratto perché gli indirizzi
di googlevideo scadono in poche ore, e una fonte che non si riapre è peggio di
nessuna fonte: fa credere di averla. Lo scaffale resta nascosto finché non c'è
qualcosa da metterci.

**Verificato.** 69 test, fra cui il più importante: un estraneo che conosce
l'id di una voce non riesce a cancellarla, mentre il proprietario sì. Poi a
mano sul server: due video aperti, una stella accesa, `1:35 / 10:00` sotto
quello lasciato a metà, e la copertina servita come `image/webp` da 25 KB.

---

## 2026-09-22 — Lo stile del file unico, portato intero

**Cosa cambia.** Il nuovo progetto ha l'aspetto del vecchio: lo stesso marchio
col segno, lo stesso verde acido come accento, le stesse schede con copertina
e iniziali colorate, gli stessi scaffali che scorrono in orizzontale. E i due
temi, chiaro e scuro, con l'interruttore in alto a destra.

**Come è fatto.** Le 1.366 righe di CSS del file unico sono diventate
`web/static/stile.css`, prese intere. I modelli delle pagine sono stati
riscritti per usare il markup a cui quello stile parla — `vcard`, `vgo`,
`poster`, `mono`, `rack`, `shelf` — invece di nomi nuovi.

**Perché intero e non «ispirato a».** Un servizio che si presenta diverso da
sé stesso a seconda di dove gira non è un servizio, sono due. E riscrivere il
markup con nomi nuovi avrebbe voluto dire riscrivere anche millequattrocento
righe di CSS già provate, per ottenere qualcosa di leggermente diverso.

Nel foglio ci sono regole per pezzi che qui non esistono ancora — il muro, il
pannello della modalità ascolto. Non sono avanzi: sono il posto già
apparecchiato per quando quei pezzi arriveranno.

**Quello che non si poteva portare così com'era.** `.stage`, `.bar` e `.note`
del file unico sono scritte per la pagina a schermo intero, che ha un'altra
forma: qui il lettore vive dentro la pagina, con sotto l'indirizzo e la
stella. Per queste, e per i pezzi che nel file unico non c'erano — la testata
col cambio tema, la proposta di lingua, l'elenco delle lingue, le domande
frequenti — c'è un blocco in fondo al foglio, con l'intestazione che dice da
dove arriva. Usa gli stessi nomi di colore: aggiungere una seconda tavolozza
vorrebbe dire averne due che dopo un mese non combaciano più.

**Le copertine non bloccano più la pagina.** Prima `/copertina` aspettava di
averla trovata: con venti voci in elenco e una che richiede yt-dlp, è una home
che non si apre. Ora il server risponde subito di no, fa partire la ricerca in
disparte, e il javascript riprova quattro volte con attese crescenti. Nel
frattempo si vede il riquadro colorato con le iniziali, che è già una
risposta. Anche il caricamento pigro è portato dal file unico: con trenta
schede in pagina, partire tutte insieme sono trenta richieste prima che si
veda qualcosa.

**Un bug portato dietro e corretto.** Una voce senza titolo mostrava
l'indirizzo intero, e le iniziali del riquadro venivano da lì: «hv» per un
link di Vimeo, cioè le prime lettere di «https» e «vimeo». Ora, senza titolo,
si mostra il sito — `vimeo.com`, iniziali `vc`. È il `label_of` del file
unico, che questa parte non aveva ancora.

**Il testo in fondo alla pagina** è cambiato in tutte e quattordici le lingue:
*«Gira sul tuo computer: i link che apri e quelli che salvi restano qui, non
passano da nessun servizio esterno.»*

**Attenzione, ed è il motivo per cui lo scrivo qui.** Quella frase è vera
adesso, che il servizio gira in locale. **Il giorno in cui questo va online su
un dominio pubblico diventa falsa**, ed è una frase sulla privacy: è il tipo
di affermazione che non conviene avere sbagliata. Prima di pubblicare, la
chiave `piede.aperto` va cambiata in tutte e quattordici le lingue.

**Verificato.** 75 test, fra cui: la pagina non ha stile in linea, il tema si
applica prima del disegno, le schede hanno il markup a cui lo stile parla, e
la copertina arriva con `data-copertina` e non con `src`. Poi a mano:
`stile.css` servito, 78 KB, tema e copertine caricati, iniziali e tinte
stabili.

---

## 2026-09-22 — Il muro: da uno a quattro video insieme

**Cosa cambia.** `/{lingua}/muro`: si incollano fino a quattro link e si
guardano insieme. Affiancati, incolonnati o a griglia; i bordi fra i riquadri
si trascinano per cambiarne le misure; un riquadro si sposta prendendolo per
la presa, o con le frecce. L'audio sta su uno solo — quello che tocchi.
Ogni riquadro ha la sua qualità, e c'è un comando «leggero» che li porta tutti
a 480p. I gruppi si salvano e si riaprono, dalla home o dal menu del muro.

**Come è fatto.** `api/routes_muro.py`, `web/static/muro.js` (il grosso),
`web/static/cella.js`, `web/static/avvisi.js`, e i due modelli `muro.html` e
`cella.html`.

**I quattro vincoli che decidono tutto.** Arrivano dal file unico e sono costati
tempo la prima volta. Vanno letti prima di toccare qualcosa:

1. **Non si ricostruisce mai il muro.** Aggiungere un riquadro rifacendo la
   griglia fa ripartire da capo tutti i video che stavano suonando — è il bug
   che avevi segnalato allora, e la misura fu 8,3 s → 14,3 s → 20,3 s di
   riavvii. Ogni operazione tocca una cella sola.
2. **I riquadri non si spostano mai nel DOM.** Spostare un `<iframe>` lo
   ricarica. Cambia solo la proprietà `order`, che la griglia rispetta: il
   video non se ne accorge nemmeno.
3. **Il movimento è fatto con la tecnica FLIP.** Si misura dov'erano, si cambia
   l'ordine, si misura dove sono finiti, si rimettono al punto di partenza con
   una trasformazione e si lasciano andare. Il browser anima solo `transform`,
   quindi scorre liscio anche con quattro video accesi.
4. **La qualità è parte dell'indirizzo del riquadro.** Cambiarla vuol dire
   ricaricare quel riquadro — e un solo posto costruisce quell'indirizzo.

**Perché ogni riquadro è un iframe.** Quattro `<video>` nella stessa pagina
sembrano più semplici e non lo sono: con l'iframe ogni video ha il suo
contesto — il suo lettore, il suo HLS, il suo errore quando c'è — e uno che si
pianta non porta giù gli altri tre. Il prezzo è che il muro non può toccare
quei `<video>`, ed è il motivo per cui esiste `cellApi`: il filo con cui la
pagina di fuori comanda il riquadro.

**Perché il riquadro si disegna i suoi comandi** invece di usare quelli del
browser: dentro un riquadro piccolo Chrome toglie da solo volume e schermo
intero, e su una diretta mostra una durata che non vuol dire niente.

**Cosa sta dove.** Disposizione, misure, quali video, quale ha l'audio: nel
`localStorage`. Cambiano dieci volte al minuto mentre si sistemano le
finestre, e mandarle al server sarebbe una richiesta per ogni pixel
trascinato. Al server va solo ciò che deve sopravvivere alla scheda chiusa: i
gruppi.

**Le due cose che il server non si fida a fare.**

*Una cella non finisce in cronologia.* Un muro da quattro, ricaricato,
riempirebbe la cronologia ogni volta. In cronologia ci va quello che si apre
di proposito.

*Di un gruppo si salva solo indirizzo e titolo.* Quello che arriva dal browser
non si copia mai intero in un campo JSON, o si finisce per salvare qualunque
cosa a qualcuno venga in mente di mandare. E un gruppo di un altro risponde
404, non 403: dire «esiste ma non è tuo» direbbe a chi prova a indovinare un
id se ha indovinato.

**I testi.** Il muro costruisce quasi tutta la sua interfaccia da sé, quindi le
frasi non possono stare nel modello: arrivano al javascript in `window.TESTI`,
e si manda **solo** quello che usa, non tutto il catalogo — sono dati che
finiscono nell'HTML di ogni caricamento. 48 chiavi nuove, in tutte e
quattordici le lingue.

**Cosa non è passato.** Il cassetto laterale condiviso con le altre pagine: qui
i salvati servono al muro soltanto, e un cassetto generico usato da un posto
solo è complicazione senza guadagno. Al suo posto un pannello che vive nella
pagina del muro, già pieno: aprirlo non deve costare una richiesta.

**Verificato.** 84 test, fra cui: un estraneo non legge il gruppo di un altro
nemmeno conoscendone l'id; una cella non sporca la cronologia; un gruppo non
tiene più di quattro celle; un campo in più mandato dal browser non viene
salvato; `javascript:` come indirizzo viene rifiutato; e i testi giapponesi
arrivano davvero al javascript. Poi a mano sul server: muro, cella, salvataggio
e rilettura di un gruppo.
