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

---

## 2026-09-22 — Tre bug del muro, e perché l'audio non si sentiva

Tutti e tre segnalati guardandolo funzionare. Nessuno sarebbe uscito da un test.

### 1. L'audio non si accendeva su YouTube

**La causa vera.** L'indirizzo del lettore incorporato non aveva
`enablejsapi=1`. Senza quel parametro YouTube **ignora in silenzio** i comandi
che gli si mandano: nessun errore, nessun avviso, il comando semplicemente non
arriva. È il tipo di parametro che manca e non se ne capisce il perché.

Aggiunto anche un secondo tentativo a ripetizione: il lettore non ascolta
finché non è pronto, e «pronto» arriva quando arriva. Un comando mandato un
decimo di secondo troppo presto si perde.

**La causa in più.** Nel lettore a due tracce, `lettore.js` copiava sull'audio
anche il `muted` del video. Ma lì il video è muto **per forza** — il suono esce
dall'altro elemento — quindi ogni volta che qualcosa toccava il volume, la
traccia audio si rimutava da sola. Ora si copia il volume e non il muto.

**Cosa cambia di contorno.** Nel muro un riquadro parte muto: quattro video che
partono insieme con l'audio non si ascoltano, si sopportano. Chi decide quale
suona è il muro, dopo, a video già avviato.

### 2. Due regolatori di volume per riquadro

Il muro chiamava `comandi(true)` sul lettore, che accendeva i comandi nativi
del browser — mentre il muro ne disegna già di suoi. Due volumi, due barre.

Il muro non tocca più i comandi nativi: restano spenti sempre. Nasconderli,
quando serve, lo fa già il CSS con le classi `zitto` e `nudo`.

### 3. L'animazione dello spostamento si impuntava

`getBoundingClientRect` restituisce la posizione **animata**, non quella del
layout. Misurando un riquadro mentre stava ancora scivolando verso il suo
posto, il punto di partenza calcolato era sbagliato e al giro dopo saltava.
Si vedeva trascinandone uno in fretta: bastava un secondo scambio prima che il
primo fosse finito.

Ora le animazioni in corso si fermano prima di misurare.

---

## 2026-09-22 — L'italiano, le altre tredici lingue, e i titoli per i motori

**L'italiano.** Tre errori veri:

- *«il tuo utente»* non è italiano: un utente è una persona, non una cosa che
  si possiede. Ora è **«il tuo profilo»**, in tre punti.
- *«suonare un flusso»* si dice di un suono, non di un video: **«riprodurre»**.
- *«Niente qui. La stella su una copertina la mette qui.»* — ripeteva «qui» e
  non si capiva cosa fosse «la». Riscritta.

Più `azione.conferma` all'infinito («Togliere questa voce?») portata alla
seconda persona come tutto il resto, e `muro.audio_tocco` da «l'audio sta sul
riquadro» a «l'audio va al riquadro», che è il movimento che succede davvero.

**Le altre lingue.** Rilette; corrette dove suonavano tradotte invece che
scritte: il francese *«Tourne sur votre ordinateur»* (→ *«Fonctionne»*), il
portoghese *«Corre no teu computador»* (→ *«Funciona»*). Le nove chiavi
italiane corrette sono state rifatte in tutte e dodici.

**I titoli e le descrizioni per i motori di ricerca.** Riscritti tutti e
quattordici, con tre regole:

1. *La parola che la gente cerca sta all'inizio.* Nessuno cerca «cleanvid»:
   cerca «video senza pubblicità». Prima il titolo era
   `cleanvid — guarda un video senza tutto il resto`; ora è
   `Video senza pubblicità — cleanvid`. Google pesa di più le prime parole, e
   nell'elenco dei risultati sono quelle che si leggono.
2. *Il marchio c'è in tutti*, in fondo: chi ci ha già visti una volta ci
   riconosce nell'elenco.
3. *Sotto i limiti in cui Google taglia*: 60 caratteri il titolo, 160 la
   descrizione. Cinque erano lunghe e sono state accorciate.

La descrizione dice cosa si fa, cosa si ottiene, e nomina «gratis» e «senza
registrazione»: sono le due domande di chi cerca.

Tre test nuovi lo tengono fermo: i limiti di lunghezza, il marchio in ogni
titolo, e **il titolo che non comincia con il marchio**.

---

## 2026-09-22 — Il resto delle funzioni del file unico

**La scelta fra due lettori.** `/guarda?u=…&m=diretto` estrae il flusso anche
quando la piattaforma un lettore ce l'ha. È una scelta vera, e la pagina la
dice:

| | parte | scade | pubblicità | comandi |
|---|---|---|---|---|
| lettore della piattaforma | subito | mai | la loro resta | i loro |
| lettore pulito | qualche secondo | sì | via | i nostri |

Il predefinito resta il loro, perché è quello che non delude mai. **Senza
questa strada, due delle funzioni qui sotto non si userebbero mai**: su YouTube
il lettore ufficiale vincerebbe sempre.

**SponsorBlock.** I pezzi segnalati a mano da chi guarda — lo sponsor letto a
voce, l'autopromozione, il «iscriviti al canale» — si saltano. *Si saltano e
non si tagliano*: tagliarli vorrebbe dire rimontare il flusso, e in un flusso
rimontato la barra del tempo dice una cosa e il video un'altra. Solo YouTube,
perché SponsorBlock sa solo di quello; per ogni altro sito la richiesta non si
fa nemmeno. Il 404 («nessuno ha segnalato questo video») si ricorda come una
risposta, per non richiederlo a ogni apertura.

**Picture-in-picture.** Il bottone resta nascosto dove non si può fare:
mostrarlo e poi non funzionare è peggio che non averlo.

**L'icona e l'installazione sul telefono.** `/icon.png?s=…` disegna il PNG al
volo — lo stesso segno del marchio, due lame e un taglio, non il triangolo di
riproduzione che hanno tutti. Quattro misure da un disegno solo: tenerne
quattro file vorrebbe dire quattro cose da rifare il giorno che il marchio
cambia. Il `manifest.webmanifest` porta alla **lingua di chi installa**: chi
installa dal giapponese si aspetta di riaprire il giapponese.

**Cosa manca ancora del file unico.** La diagnosi degli errori — la pagina che
spiega perché un link non ha funzionato e cosa si può provare. E la modalità
ascolto, che non passa e il perché sta in `ARCHITETTURA.md`.

**Verificato.** 97 test. Poi a mano: l'audio su una cella YouTube, l'icona in
quattro misure, il manifesto in giapponese, il passaggio fra i due lettori, e
SponsorBlock contro il servizio vero — `kJQP7kiw5Fk` restituisce due segmenti,
`[0, 21.8]` e `[249.4, 281.5]`.

---

## 2026-09-22 — Nel muro vince il lettore nostro (e i due volumi spariscono)

**Cosa succedeva.** Nel muro c'erano ancora due regolatori di volume per
riquadro, e l'audio non si sentiva. La correzione di prima aveva tolto i
comandi nativi del `<video>`, ma il secondo volume non veniva da lì: veniva
dal **lettore di YouTube**, che nel riquadro ci finiva intero, con tutta la
sua interfaccia.

**La correzione vera è un cambio d'ordine.** Fuori dal muro si prova prima il
lettore della piattaforma, perché parte subito e non scade. **Dentro il muro
l'ordine è rovesciato**: prima si estrae, e il lettore loro è il ripiego.

Due ragioni, e la seconda conta più della prima:

1. Il lettore di un'altra piattaforma porta con sé la propria interfaccia,
   compreso il proprio volume, e il muro ne disegna già una. Due barre e due
   volumi per riquadro, e chi guarda non sa quale toccare.
2. **Al lettore di un altro sito possiamo solo mandare messaggi e sperare.** Al
   nostro `<video>` parliamo diretto. «L'audio su un riquadro solo» è il cuore
   del muro, e attraverso un iframe di terzi funzionava quasi sempre — che in
   pratica vuol dire: non funzionava.

Quando l'estrazione non riesce si ripiega sul lettore loro — meglio di un
riquadro vuoto — ma con `controls=0`, così almeno il volume resta uno solo.

**Il prezzo, detto:** aprire un riquadro nel muro ora costa un'estrazione, cioè
qualche secondo la prima volta. Le volte dopo è immediato, perché la cache ha
per chiave `(url, qualità)` e non l'utente.

---

## 2026-09-22 — «come viene» non era italiano, ma «qualità» non era la parola

Nel menu della qualità la prima voce diceva *«come viene»*: colloquiale e
sbagliato, giustamente segnalato.

**Al suo posto però non va «qualità»,** e vale la pena scrivere perché. Le
altre voci del menu — 1080p, 720p, 480p — sono *valori* di qualità. La prima è
il valore «decidi tu», che in italiano si dice **«Automatica»**. Mettere
«qualità» come voce vorrebbe dire un menu che offre «qualità, 1080p, 720p»:
una parola che non è dello stesso tipo delle altre.

«Qualità» è il **nome** del menu, e come nome resta: nel titolo che compare
passandoci sopra, nell'etichetta per i lettori di schermo, e ora anche in
chiaro accanto al menu nella pagina del video, dove lo spazio c'è. Nel muro
no, perché lì lo spazio non c'è e un menu mostra il valore scelto — che è come
funziona un menu.

Cambiata in tutte e quattordici le lingue, insieme alla maiuscola su
«Qualità», che adesso è un'etichetta che si legge e non più solo un nome
nascosto.

---

## 2026-09-22 — Il video storto nel riquadro, e la chat delle dirette

### Il video non era centrato

**Cosa succedeva.** Dentro un riquadro del muro il video stava in alto a
sinistra, con del nero intorno, alla sua misura e non a quella del riquadro.

**La causa.** La pagina della cella era nuova e nessuno le aveva mai dato una
forma: un `<video>` senza larghezza né altezza prende la misura del file —
quella del video, non quella del posto in cui sta.

**Il rimedio.** `body.cell` diventa un contenitore che si allunga, e il video
lo riempie con `object-fit: contain`. *Contain* e non *cover*: un video
verticale dentro un riquadro largo deve avere le bande ai lati, non essere
tagliato. Tagliare per riempire vuol dire far sparire un pezzo di immagine
senza dirlo a nessuno.

### La chat delle dirette

**Cosa c'è adesso.** Su una diretta di Twitch o di YouTube compare la chat
della piattaforma: di fianco al video nella pagina singola, e nel muro dietro
un bottone sul riquadro.

**Di fianco e non sopra.** Sopra coprirebbe il video, ed è esattamente quello
che questo sito toglie.

**Solo sulle dirette.** Il `live_chat` di YouTube su un video registrato apre
un riquadro con dentro un errore, che è peggio di niente.

**Nel muro si accende su richiesta, e l'indirizzo si scrive solo allora.**
L'`iframe` nasce vuoto e prende il suo `src` alla prima accensione: quattro
chat sempre aperte in un muro da quattro sono quattro connessioni che nessuno
sta leggendo. Il bottone compare solo dove una chat esiste davvero — mostrarlo
e poi non aprire niente è peggio che non averlo. E la scelta si ricorda, come
il resto del muro.

**L'inciampo di sempre.** Twitch e YouTube rifiutano l'iframe se il dominio
dichiarato non combacia con quello da cui si apre la pagina — `parent` per
l'uno, `embed_domain` per l'altro. È lo stesso di `lettore_ufficiale`, e si
risolve allo stesso modo: prendendolo dall'indirizzo della richiesta, con
`localhost` e `127.0.0.1` sempre in lista così la stessa pagina funziona anche
in casa.

**Verificato.** 102 test, fra cui: niente chat su una registrazione, chat su
una diretta, l'iframe che parte senza `src`, e i domini dichiarati giusti per
entrambe le piattaforme. Poi a mano su una diretta Twitch vera.

---

## 2026-09-22 — Il lettore nostro come predefinito, e le tre viste

**Cosa cambia.** Aprendo un video si apre **il nostro lettore**, anche dove la
piattaforma ne ha uno. E il lettore ha le tre viste a cui la gente è abituata:
normale, cinema, schermo intero.

**Il predefinito rovesciato.** Fino a ieri vinceva il lettore della
piattaforma, perché parte subito e non scade mai. La decisione è cambiata, ed
è la scelta giusta per una ragione che si vede meglio adesso che le funzioni
ci sono: **dentro l'iframe di un altro sito non si può fare niente di tutto il
resto.** Niente sponsor saltato, niente piccolo schermo, niente ripresa da
dove si era rimasti, niente viste, niente qualità scelta da noi. Tenere quel
lettore come predefinito voleva dire che quasi nessuno avrebbe mai visto le
funzioni per cui questo progetto esiste.

**Il prezzo, detto.** Un video costa qualche secondo la prima volta, e
l'indirizzo del flusso scade dopo qualche ora — poi la pagina va ricaricata.
Chi preferisce l'altro lo trova a un clic nella barra.

**Il ripiego automatico, che è la parte importante.** Se l'estrazione non
riesce e la piattaforma un lettore ce l'ha, si apre quello **senza dire
niente**: la scelta del predefinito non deve mai costare un video che non
parte. Il motivo del guasto si mostra solo dove il ripiego non c'è — lì è
l'unica cosa utile.

### Le tre viste

| | cos'è |
|---|---|
| normale | nella colonna della pagina, come tutto il resto |
| cinema | il lettore si allarga fino ai bordi della finestra |
| schermo intero | quello vero del browser, non una finta a tutta pagina |

**Le scorciatoie sono quelle di sempre**: **T** per il cinema, **F** per lo
schermo intero, **spazio** o **K** per la pausa, **M** per il muto, **frecce**
per cinque secondi avanti e indietro. Non si inventano tasti nuovi per una
cosa che tutti fanno già allo stesso modo: una scorciatoia diversa dalle altre
non si impara, si sbaglia. Non scattano mentre si scrive in un campo, o si
finirebbe a schermo intero digitando «f».

**Come è fatto il cinema.** `margin-left: calc(50% - 50vw)` porta il blocco
fuori dalla colonna **senza spostarlo nel documento**: se lo si spostasse
davvero, l'iframe si ricaricherebbe e il video ripartirebbe da capo. È lo
stesso vincolo del muro, in un altro posto.

**La chat si allarga insieme al video**, perché una chat che resta stretta
mentre il video si allarga sembra un errore. A schermo intero sparisce: lì
serve il video, e una colonna di testo di fianco toglie solo spazio.

**La vista si ricorda, ma solo fra normale e cinema.** Lo schermo intero no,
di proposito: una pagina che si apre da sola a tutto schermo è una pagina che
ha preso il controllo dello schermo senza che nessuno glielo chiedesse — e i
browser stessi non lo permettono fuori da un gesto.

### Il titolo, e una pulizia

La pagina ora mostra il titolo del video come intestazione, sotto il lettore, e
la stella dei preferiti gli sta accanto invece che in fondo. Prima il titolo
era una riga grigia persa sotto la barra dei comandi.

### I test non chiamano più yt-dlp

Cambiando il predefinito, ogni test che apriva una pagina video ha cominciato
a estrarre davvero: la suite è passata da un secondo a trentadue, e dipendeva
dalla rete, dalla versione di yt-dlp e dall'umore del sito. Ora una fixture
mette yt-dlp e SponsorBlock fuori gioco per tutti, e chi vuole provare il caso
del fallimento se lo rimette a modo suo. Torna a due secondi.

**Verificato.** 104 test. Poi a mano: il predefinito estrae, `m=loro` apre
l'altro, le tre viste ci sono su entrambi, e il ripiego funziona.

---

## 2026-09-22 — La chat del riquadro andava sotto invece che di fianco

**Cosa succedeva.** Nel muro la chat di una diretta si apriva **sotto** il
video invece che di fianco, nonostante le regole scritte per la cella
dicessero il contrario.

**La causa: una classe con lo stesso nome in due posti.** `conchat` ce l'hanno
sia la cella del muro sia la pagina del video. Nel foglio era rimasta una
regola generica `.conchat { display: grid; … }` scritta per la prima versione
della pagina del video — quella che oggi usa `.scena` — e dentro c'era
`@media (max-width:760px) { .conchat { grid-template-columns: 1fr } }`.

Un riquadro del muro è quasi sempre più stretto di 760px. Quindi la cella
prendeva una griglia a una colonna e impilava.

**Il rimedio.** Via la regola generica. Una classe generica usata da due posti
diversi è esattamente il modo di rompere uno aggiustando l'altro, e un test
adesso fallisce se qualcuno la riscrive.

**La chat sta a destra, e non è un caso.** Sotto mangia l'altezza, e in un
muro da quattro l'altezza è la cosa che manca. Di fianco il video si stringe
di poco, la chat si legge lo stesso, e — quello che conta di più — **non si
sposta niente quando la si apre**.

### Un pannello per le preferenze del muro

Nel cassetto «altro» c'è ora una riga **Chat: a destra / sotto**. La scelta
vale per tutti i riquadri, anche quelli aperti dopo, e si ricorda.

È il primo di questo tipo, e il posto è quello giusto: le preferenze che
riguardano *come guardi* stanno dove stai guardando, non in una pagina di
impostazioni da raggiungere e poi tornare indietro. Nelle impostazioni del
sito restano le cose che valgono ovunque — la lingua, il tema.

**Verificato.** 110 test, fra cui uno che fallisce se torna una regola
generica su `.conchat`.

---

## 2026-09-22 — Le preferenze della pagina del video, e via la scorciatoia F

### Chat di fianco o sotto, nel lettore singolo

Come nel muro, ma con una forma diversa perché il posto è diverso: un bottone
**Preferenze** accanto alle viste, che apre un pannellino con **Chat: di
fianco / sotto**.

*Di fianco* è il predefinito, ed è la scelta che fa una diretta: si guarda e
si legge **insieme**. Mettere la chat sotto vuol dire scorrere avanti e
indietro fra due cose che succedono nello stesso momento.

*Sotto* ha senso su uno schermo stretto, o quando il video conta più della
chat. Allora è una scelta, e si ricorda.

**Come è fatto.** La posizione della chat decide le aree della griglia:
`chat-fianco` fa partire la colonna dalla riga del lettore, quindi gli sta
accanto alla stessa altezza; `chat-sotto` dà al lettore tutta la larghezza e
fa cominciare la colonna sotto, di fianco al titolo. Come sempre, **cambiano
solo le aree**: niente si sposta nel documento e il video non riparte.

Una cosa che non tornava e che ho sistemato: in cinema, a uscire dalla colonna
non può essere il lettore da solo se la chat gli sta accanto — resterebbe
fuori dallo schermo. Con la chat di fianco esce **tutto il blocco**, lettore e
chat insieme, con un margine ai lati: a filo del bordo non si legge niente.

**Il pannello è un `details`, non un menu scritto in javascript.** Si apre e si
chiude da solo, si chiude con Escape, e chi arriva con la tastiera ci entra
come in ogni altro elemento. Su schermo stretto diventa un foglio dal basso.

**Senza chat il bottone non c'è**: un pannello di preferenze con dentro una
sola voce che non si applica è un bottone che non serve a niente.

### Via la `F`, e via il bottone dello schermo intero

Tolti tutti e due. Il bottone dello schermo intero ce l'ha già il lettore del
browser, ed è lì che la gente lo cerca: due bottoni per la stessa cosa, uno
dentro il video e uno fuori, sono uno di troppo. E una `f` che spalanca lo
schermo mentre si sta facendo altro sorprende invece di aiutare.

`T` resta, perché cambia la forma della pagina — che un bottone del lettore
non può fare.

**Verificato.** 112 test, fra cui uno che fallisce se `requestFullscreen`
torna nel nostro javascript.

---

## 2026-09-22 — La terza vista: solo il lettore

Le viste sono tre: **normale**, **cinema** (il predefinito) e **solo il
lettore**. Quella che c'era prima — lo schermo intero del browser — non è
sparita: l'ha il lettore, con il suo bottone, dove la gente la cerca. Un
secondo bottone fuori dal video per la stessa cosa era uno di troppo.

**Cosa fa «solo il lettore».** Sparisce tutto: testata, titolo, azioni, piede.
Resta il video a riempire la finestra e, **se è una diretta, la chat di
fianco**. Su una diretta è la forma giusta per starci un'ora: niente da
leggere intorno, e la chat dove serve.

**Su una registrazione la chat non c'è**, e quella colonna non compare
affatto. Mezzo schermo di nero di fianco al video non è una vista, è un
errore.

**Perché non è lo schermo intero vero.** `position: fixed` invece del
fullscreen del browser, e non per pigrizia: dal fullscreen si esce solo con
Escape o con il suo bottone, mentre qui la pagina resta sotto e si torna
indietro come da qualunque altra cosa. In più il fullscreen si può chiedere
solo dentro un gesto, quindi una vista ricordata non si potrebbe riaprire da
sola — e questa sì.

**La via d'uscita è sempre lì**, in alto a destra: un tondo discreto che si
accende passandoci sopra, più Escape. Una modalità che si prende lo schermo
senza dire come uscirne è una trappola, e non tutti sanno che Escape funziona.

**Si torna dove si era.** Uscendo si ritrova la vista di prima — normale o
cinema — non una scelta a caso: entrando si segna da dove si veniva.

**`T` non fa niente dentro «solo il lettore»**, perché lì non vuol dire
niente: non c'è una colonna da allargare.

**Verificato.** 115 test, fra cui: le tre viste ci sono, la via d'uscita c'è,
`requestFullscreen` non è tornato nel nostro javascript, e la colonna della
chat si accende solo con una diretta.

---

## 2026-09-22 — La chat non si allungava quanto la riga

**Cosa succedeva.** In «solo il lettore» la chat era una striscia in alto, con
sotto mezzo schermo vuoto, invece di riempire la colonna.

**La causa.** La griglia della pagina ha `align-items: start`. È giusto per
quello che ci sta dentro di solito — il titolo, la lista «da riprendere»:
roba che comincia in alto e finisce dove finisce. Per la chat no: lì vale
l'altezza della riga, e con `start` la colonna restava alta quanto il suo
contenuto, cioè poco.

**Il rimedio, e perché non sulla griglia.** `align-self: stretch` sulla sola
colonna della chat. Cambiare `align-items` su tutta la griglia avrebbe toccato
anche il lettore, che l'altezza se la calcola dal rapporto 16:9: sarebbe
diventato un ragionamento circolare fra l'altezza della riga e quella del suo
contenuto, del tipo che a volte funziona e a volte no a seconda del browser.

Vale anche per la vista normale con la chat di fianco, dove lo stesso `start`
faceva la stessa cosa in piccolo.

**Verificato.** 116 test, fra cui uno che tiene ferme tutte e tre le righe:
`align-items: start` sulla griglia, `align-self: stretch` sulla colonna.
