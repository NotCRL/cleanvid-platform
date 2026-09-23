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

---

## 2026-09-22 — In cinema il lettore e la chat non erano alla stessa altezza

**Cosa succedeva.** Con la chat di fianco, la colonna della chat era molto più
alta del video: partiva dal bordo del lettore e finiva sotto il titolo e le
azioni.

**La causa.** Nella griglia, `chat-fianco` dava alla colonna le aree
`"palco accanto"` e `"principale accanto"`: la chat occupava **due righe**, il
lettore una. Con `align-self: stretch` — messo poco prima per tutt'altro
motivo — la chat si prendeva diligentemente tutte e due.

**Il rimedio.** Con la chat di fianco il titolo passa **sotto, a tutta
larghezza**: `"palco accanto"` / `"principale principale"`. Lettore e chat
stanno nella stessa riga, e una riga ha una sola altezza. È anche quello che
«affiancati» vuol dire.

Con la chat sotto il titolo torna di fianco alla colonna, perché lì la colonna
comincia proprio all'altezza del titolo.

**Un numero solo.** L'altezza in cinema la decide il lettore — ora
`min(58vw, 100vh - 128px)`, un po' più alta di prima visto che il titolo non
gli sta più accanto — e la chat la segue perché sta nella stessa riga e si
allunga. Prima erano due valori uguali scritti in due posti: il tipo di cosa
che resta uguale finché qualcuno non ne cambia uno solo.

**Verificato.** 119 test, fra cui uno che fallisce se la chat si riprende
un'altezza sua invece di seguire la riga.

---

## 2026-09-22 — Le bande nere ai lati del video, in cinema

**Cosa succedeva.** In cinema, dentro al lettore comparivano due bande nere ai
lati del video.

**La causa.** L'altezza del riquadro era un numero legato alla finestra
(`min(58vw, 100vh - 128px)`) mentre la larghezza era *tutta quella
disponibile*. Su uno schermo basso e largo — cioè quasi tutti — il riquadro
diventava più largo di 16:9, e `object-fit: contain` faceva diligentemente il
suo lavoro: il video intero, centrato, con il vuoto ai lati.

Il comportamento era corretto. Il problema è **dove** stava quel vuoto: dentro
al lettore, dove sembra un difetto del video.

**Il rimedio: il rapporto è fisso e a variare è la larghezza.** Il lettore è
sempre 16:9 e prende tutto lo spazio che ha, ma non più di quanto gliene
servirebbe per sforare in altezza:

```css
aspect-ratio:16/9;
width:min(100%, calc((100vh - 120px) * 16 / 9));
```

Quando la finestra è bassa il blocco si stringe e resta centrato. Lo spazio
che avanza ai lati è **pagina, non lettore** — e si vede che è un'altra cosa.

**Perché non bastava alzare l'altezza.** Alzandola il riquadro sarebbe
diventato più alto *e* sarebbe sforato sotto la piega, senza smettere di
essere più largo di 16:9 su uno schermo largo. Il numero da cambiare non era
l'altezza: era quale dei due lati comanda.

**Di contorno.** In cinema senza chat il testo sotto il lettore torna in una
colonna da 1060px: una riga di testo lunga un monitor non si legge, si
scansiona.

**Verificato.** 119 test, fra cui uno che fallisce se il lettore in cinema
perde il suo `aspect-ratio`.

---

## 2026-09-22 — Il bagliore dietro al lettore

**Cosa c'è.** In cinema, dietro al lettore c'è un alone che prende i colori
dal video e li allarga ai lati. Si accende e si spegne dal pannello delle
preferenze, e la scelta si ricorda.

**Come è fatto, e perché così.** Si disegna il fotogramma dentro una tela di
**32×18 pixel**, e l'ingrandimento e la sfocatura li fa il CSS.

Non è un trucco per risparmiare: è *il* modo. Sfocare un'immagine grande costa
a ogni fotogramma, mentre ingrandire trentadue pixel è quello che una scheda
video fa senza accorgersene — e a occhio il risultato è lo stesso, perché dopo
cinquanta pixel di sfocatura i dettagli non ci sono comunque più.

**Quattro o cinque fotogrammi al secondo.** Il bagliore deve accompagnare il
video, non inseguirlo. Più spesso si vedrebbe sfarfallare, e si pagherebbe un
lavoro in più per un effetto peggiore.

**Sta nella stessa area della griglia del lettore**, quindi gli finisce
esattamente dietro senza posizionarlo a mano. E siccome in cinema il lettore
può essere più stretto della sua colonna, il bagliore esce ai lati — che è il
punto.

**`overflow: visible clip`.** La sfocatura sborda di una cinquantina di pixel,
e su un blocco largo quanto la finestra creerebbe una barra di scorrimento
orizzontale. `clip` la taglia senza diventare un contenitore che scorre, e
l'asse verticale resta `visible`: con `hidden` il pannello delle preferenze si
ritroverebbe tagliato quando si apre.

**Tre cose che spengono il battito:**

- la scheda non è in vista — disegnare per una pagina che nessuno guarda è
  lavoro buttato, e su un portatile è batteria;
- il video è in pausa o non è ancora arrivato niente;
- il browser rifiuta di disegnare quel video su una tela. A noi non serve
  rileggerne i pixel, solo mostrarla, quindi di norma va bene lo stesso; ma se
  si rifiuta del tutto si smette, invece di riprovare quattro volte al secondo
  per sempre.

**Chi ha chiesto meno movimento non se lo trova acceso** di nostra iniziativa —
ma se lo accende lui, resta acceso.

**Col lettore della piattaforma non c'è**, e non è una dimenticanza: dentro
quell'iframe i fotogrammi non ci sono, è un altro documento, e non c'è niente
da disegnare.

**Il pannello delle preferenze ora compare anche senza chat**, perché ha
qualcosa da offrire: il bagliore vale su ogni video col lettore nostro. Mostra
quello che si applica, e quando non si applica niente non c'è affatto.

**Verificato.** 121 test.

---

## 2026-09-22 — La stella non ricarica più la pagina

**Cosa succedeva.** Mettere o togliere dai preferiti faceva un giro completo:
modulo, rimbalzo, pagina rifatta. Sulla pagina del video **questo faceva
ripartire il video da capo** — per una stella.

**Il rimedio.** Il javascript intercetta il modulo e fa la stessa cosa di
lato; la rotta risponde in JSON a chi lo chiede, e col solito rimbalzo a
tutti gli altri. Il modulo HTML resta e funziona da solo: senza javascript la
stella va lo stesso, con il ricaricamento. È la forma vecchia, ed è quella che
regge quando il resto non c'è.

Se la rete non risponde si lascia fare al modulo. Fallire in silenzio su un
bottone è il modo di far credere a qualcuno di aver salvato una cosa che non
ha salvato.

---

## 2026-09-22 — Il bagliore doveva essere zero, e non lo era

**Cosa succedeva.** Prima che il video partisse si intravedeva comunque un
alone. La tela era già in pagina con la sua opacità, e una tela **nera**
sfocata non è «niente»: è un alone scuro, che sul tema chiaro si vede
benissimo e sembra sporco.

**Il rimedio.** Opacità zero, proprio zero. Il bagliore compare solo se sono
vere tutte e tre:

1. lo vuoi (preferenza accesa);
2. c'è un fotogramma davvero disegnato sulla tela;
3. il video sta andando.

**`playing`, non `play`.** Il primo vuol dire che sta davvero andando, il
secondo solo che glielo hanno chiesto — e fra i due, su una diretta, possono
passare secondi di schermo nero. Con `play` si sarebbe acceso su quel nero.

**Entra e esce in dissolvenza**, 0,6 secondi. È una luce, e una luce che
compare di colpo è un lampo. Vale anche allo spegnimento dalle preferenze:
la classe che toglie la tela dalla pagina si rimuove **dopo** la dissolvenza,
altrimenti l'alone sparirebbe di scatto.

Si spegne in pausa e a fine video, e si riaccende ripartendo.

**Verificato.** 125 test.

---

## 2026-09-22 — Il lettore si bloccava. Tre cause, tutte vere

Segnalato come «il player è pieno di bug e si blocca di continuo». Cercandole
ne sono venute fuori tre, e sono tre cose diverse.

### 1. Non c'era nessuna difesa

Il lettore sapeva far partire un video e non sapeva farlo **ripartire**. Un
flusso si ferma per mille motivi che non sono colpa di nessuno — un segmento
che tarda, la rete che cambia, un indirizzo che scade dopo qualche ora — e il
browser, quando succede, non fa niente: resta fermo.

Ora c'è un guardiano che guarda se il tempo avanza. Se non avanza per sei
secondi, prova a rimettere in moto con una scala di rimedi, dal più leggero
al più pesante:

| | |
|---|---|
| 1 | una spinta di un decimo di secondo — il decoder si impunta su un fotogramma e quasi sempre basta |
| 2-4 | si riapre il flusso e si torna dov'eravamo |
| oltre | si ricarica la pagina, che rifà l'estrazione |

La riestrazione **una volta sola per pagina**: se anche la seconda non regge,
ricaricare all'infinito non aiuta nessuno e nasconde il problema vero.

Un `404` o `403` su un flusso non passa nemmeno per la scala: vuol dire che
l'indirizzo è morto, e lì non c'è niente da riprovare.

**Le due tracce ora si fermano insieme.** Se una resta senza dati e l'altra
continua, quando tornano si ritrovano a secondi di distanza: si sente come un
doppiaggio sbagliato, e il recupero costa un salto brutto. Meglio mezzo
secondo di attesa.

**E la diretta non si tiene più in memoria tutta**: `backBufferLength: 60`.
Su una diretta lunga erano centinaia di megabyte, e la scheda muore.

### 2. La numerazione dei segmenti non veniva aggiornata

**Questa è probabilmente la causa dei blocchi su Twitch.**

`#EXT-X-MEDIA-SEQUENCE` è il numero del primo segmento della lista, e serve al
player per capire quali segmenti sono nuovi fra un aggiornamento e l'altro.
Togliendo i primi N segmenti — cioè quello che facciamo a ogni pubblicità —
**senza toccarlo**, il player crede che il primo sia ancora quello di prima:
si ritrova con una numerazione che non torna, riscarica roba che ha già, ne
salta altra, e in diretta si pianta.

Non dà nessun messaggio. Il video si ferma e basta.

### 3. Durante un preroll servivamo una playlist vuota

Misurato dal vivo su una diretta Twitch, mentre scrivevo questo:

```
giro 1: sequenza 0 -> 3 | segmenti 0 | spot tolti 3 | solo spot: True
giro 2: sequenza 0 -> 5 | segmenti 0 | spot tolti 5 | solo spot: True
```

Tolti gli spot non restava **niente**: è il preroll, la reclame che passa
prima che la diretta cominci davvero. E una playlist senza un solo segmento
certi lettori la prendono per un errore e si fermano — nel momento esatto in
cui sembra che il sito sia rotto.

Ora si tiene da parte l'ultima playlist che aveva roba vera e si serve quella:
per il lettore è una diretta che non ha ancora niente di nuovo, cioè una cosa
normalissima che sa gestire. I segmenti non li riscarica, perché li riconosce
dal numero. Vita breve, un minuto: se la pubblicità dura di più, ripetere
roba vecchia all'infinito sarebbe peggio che dire la verità.

---

## 2026-09-22 — Il pannello delle preferenze finiva dietro all'indirizzo

Si apriva sotto al blocco dell'indirizzo: visibile a metà e non cliccabile.
La riga delle azioni non aveva un contesto di impilamento, quindi il pannello
— per quanto alto fosse il suo `z-index` — finiva dietro a un blocco che nel
documento veniva dopo. Ora `.azioni` sta sopra, e `.indirizzo` sotto.

Un pannello che si apre dentro una riga deve stare sopra alla riga sotto,
sempre.

---

## 2026-09-22 — La pubblicità di Twitch: si riconosce dal titolo del segmento

**Segnalato:** «vedo ancora pubblicità su Twitch». Vero, e il motivo è preciso.

**Cosa guardavamo.** I marker standard: `#EXT-X-CUE-OUT`, `#EXT-X-DATERANGE`
di classe `twitch-stitched-ad`, i SCTE-35. **A volte ci sono e a volte no.**

**Cosa guardano i blocchi pubblicità che funzionano.** Il titolo del segmento.
Twitch scrive dopo la virgola dell'`#EXTINF` a cosa serve quel pezzo, e per la
diretta vera dice sempre `live`.

Misurato adesso, su due canali in diretta nello stesso momento:

```
xqc:    titoli ['live']                  → 15 segmenti tenuti, 0 tolti
gaules: titoli ['Amazon|2474283100494']  → 0 segmenti tenuti, 3 tolti
```

Su `gaules` c'era una pubblicità in corso e **nessun marker standard**: solo
quel titolo. Con il vecchio criterio passava intera.

**La regola nuova.** Se la playlist è di Twitch — lo dicono i suoi tag
`#EXT-X-TWITCH-` — ogni segmento il cui titolo non è `live` è pubblicità.

**Vale solo per Twitch, e la severità è voluta.** Su qualunque altro sito il
titolo dell'`#EXTINF` è vuoto o dice altro, e applicare questa regola vorrebbe
dire buttare via l'intero video. Per questo si controlla prima che sia davvero
una playlist di Twitch, e c'è un test che passa una diretta pulita per essere
sicuri che non venga toccata.

**Di contorno: una lista senza segmenti non è un guasto.** Durante
un'interruzione, tolti gli spot, può non restare niente. hls.js lo segnala
come `LEVEL_EMPTY_ERROR` fatale, e il nostro gestore avrebbe ricaricato la
pagina **a ogni interruzione pubblicitaria**. Ora si aspetta due secondi e si
riprova, che è quello che sta succedendo davvero: fra poco torna roba vera.

**Verificato.** 139 test, fra cui una playlist Twitch vera copiata così com'è,
una con dentro `Amazon`, e una di un altro sito che non deve essere toccata.

---

## 2026-09-22 — «Non parte il video»: cosa succedeva davvero

Provato con un browser vero in headless, su due canali Twitch in diretta nello
stesso momento. Il risultato è stato utile e in parte inatteso.

**Il lettore funziona.** Su entrambi i canali il video parte: si vede dal
bagliore, che si accende solo quando c'è un fotogramma disegnato *e* il video
sta andando. Nessun errore dei nostri script in console.

**Quello che non funzionava era il silenzio.** Su un canale c'era una
pubblicità in corso: i loro spot sono cuciti dentro il flusso e noi li
buttiamo via, quindi finché dura l'interruzione **non c'è niente da mandare** e
il lettore aspetta. È il comportamento giusto — meglio aspettare che guardare
la reclame — ma uno schermo nero senza spiegazioni sembra un guasto nostro.

Ora lo si dice, con una riga che si toglie da sola appena torna il video:

> *Pubblicità in corso: la stiamo togliendo. Il video riparte appena finisce.*

Non ha la faccia di un errore, perché non lo è: fondo verde tenue e un puntino
che respira, non un riquadro rosso. Un messaggio d'errore su una cosa che si
risolve da sola fa credere a un guasto.

**E su una diretta di Twitch il guardiano non fa più la scala dei rimedi.**
Spinta, riapertura, riestrazione: non c'è niente di rotto da rimettere a
posto. Si continua a chiedere la playlist e si aspetta, che è l'unica cosa
sensata.

**Due difetti trovati dalla console mentre ero lì.**

L'icona del tema era rotta: nel codice il tracciato `d` era spezzato su due
righe e i pezzi venivano uniti senza spazio, quindi `0 0 0 0` e `15.6`
diventavano `0 015.6`. Il browser rifiutava l'intero tracciato e l'icona
spariva, lasciando in console «Expected number».

E `apple-mobile-web-app-capable` da solo è deprecato: adesso c'è anche
`mobile-web-app-capable`, che è il nome standard. Servono tutti e due —
Safari conosce ancora solo il primo.

**Cosa resta vero.** Durante una pubblicità lunga il video non c'è. Non è
aggirabile da qui: gli spot arrivano dentro gli stessi byte del video, e
l'unico modo di non aspettarli sarebbe chiedere a Twitch un flusso diverso —
cosa che richiede rifare la loro procedura di autorizzazione, non un ritocco.

---

## 2026-09-23 — Risposta al dossier comparativo

Arrivato un dossier scritto da un altro modello che confronta cleanvid con
Stremio e Hydra e propone una direzione architetturale. Sta in
[`confronti/CONFRONTI.md`](confronti/CONFRONTI.md); la lettura critica in
[`confronti/RISPOSTA.md`](confronti/RISPOSTA.md).

**Il punto principale.** Il dossier analizza il file unico e propone una
roadmap in sei fasi per modularizzarlo. Quelle sei fasi sono già state fatte
il 21 e 22 settembre, in questo progetto — compresi i sette test su HLS che
propone al §11, che esistono già uno per uno in `tests/test_manifesto.py`.
Seguirlo com'è scritto vuol dire rifare due giorni di lavoro.

**Quello che vale la pena prendere, in ordine:**

1. *Unificare `Lettore` ed `Estratto`.* Due tipi per la stessa cosa, che la
   pagina deve distinguere 22 volte in `guarda.html`, 8 in `cella.html`, 6
   nelle rotte. Ogni funzione nuova va pensata due volte. Questo il dossier
   lo vede da fuori meglio di come lo vedevamo da dentro.
2. *I sottotitoli.* Compaiono nel suo oggetto `Stream` quasi di sfuggita, e
   da noi non esistono proprio. yt-dlp li dà gratis.
3. *Il confine legale (§14).* La parte migliore del documento, e la più
   urgente. Rafforza quello che è già scritto qui sopra sulla riga in fondo
   alla pagina, che diventa falsa il giorno che si pubblica.

**Quello che non prenderemmo:** il registro di provider con
`can_handle`/`resolve`. Abbiamo due resolver, e yt-dlp è già il sistema a
plugin per 1.800 siti. È anche l'unica contraddizione interna del dossier,
che al §15 dice di non fare tutto un plugin e al §9 lo propone.

**Quello che manderebbe indietro:** l'albero del §8 mette `filtering/` e
`browser/` fra i moduli centrali. Appartengono alla modalità ascolto, che su
un servizio pubblico non può esistere.

**Il punto cieco:** non nomina mai registrazione, stanze e watchparty, cioè
l'intero motivo per cui questo progetto esiste. Ha analizzato uno strumento
locale monoutente e propone l'architettura di uno strumento locale
monoutente.

**Dove converge, e conta.** Ha scelto in autonomia la stessa prima mossa —
estrarre per primo il modulo HLS perché è codice puro — ed è arrivato alle
stesse conclusioni su torrent e modalità ascolto. Il valore di questo dossier
non è il piano: è la conferma.
