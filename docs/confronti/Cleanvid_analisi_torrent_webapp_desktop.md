# Cleanvid — analisi aggiornata: Universal Media Discovery, Torrent, Web App e Desktop App

Data: 23 settembre 2026

## 1. Punto di partenza

Dopo il confronto con la seconda analisi (Claude) e la precisazione dell'obiettivo, la definizione di Cleanvid che considero più corretta è:

> **Cleanvid non deve essere un player per YouTube, Twitch, Vimeo o altre piattaforme specifiche. Deve essere un motore universale che riceve un URL, individua una sorgente multimediale riproducibile e la porta nel player Cleanvid.**

Questa distinzione è fondamentale.

Il problema principale non è "supportare N piattaforme". È:

```text
URL
 ↓
MEDIA DISCOVERY
 ↓
sorgente video
 ↓
normalizzazione
 ↓
stream
 ↓
player
```

YouTube, Twitch, Vimeo ecc. sono soltanto alcuni casi che il motore può incontrare.

---

# 2. Correzione importante rispetto al primo dossier

Nel primo dossier avevo proposto una struttura con provider espliciti:

```text
sources/
    youtube.py
    twitch.py
    vimeo.py
```

Dopo aver letto la risposta di Claude e chiarito l'obiettivo universale, **non considero più questa la direzione principale**.

Il rischio è trasformare Cleanvid in un elenco di integrazioni per sito.

La direzione preferibile è:

```text
media/
    discovery.py
    resolver.py
    embed.py
    estrazione.py
    manifesto.py
    stream.py
    metadata.py
```

con diversi meccanismi di discovery/resolution:

```text
URL
 │
 ├── direct media resolver
 ├── static HTML resolver
 ├── iframe/embed resolver
 ├── manifest resolver
 ├── yt-dlp resolver
 └── browser/CDP resolver
```

L'obiettivo è trovare la sorgente, non identificare necessariamente il brand della piattaforma.

---

# 3. L'idea di "Universal Media Discovery"

Il modello che considero più promettente è:

```text
                         URL
                          │
                          ▼
                 DISCOVERY ENGINE
                          │
          ┌───────────────┼────────────────┐
          │               │                │
          ▼               ▼                ▼
      DIRECT URL       HTML / EMBED      BROWSER
          │               │                │
          │               ▼                │
          │          iframe/player         │
          │               │                │
          └───────────────┼────────────────┘
                          ▼
                    MEDIA DISCOVERY
                          │
             ┌────────────┼────────────┐
             │            │            │
             ▼            ▼            ▼
            MP4          HLS          DASH
             │            │            │
             └────────────┼────────────┘
                          ▼
                    STREAM MODEL
                          │
                          ▼
                   PROXY / FILTER
                          │
                          ▼
                        PLAYER
```

Il browser/CDP è soprattutto un fallback potente:

```text
yt-dlp / HTML / manifest
       │
       └── se non basta
               ↓
          Chromium + CDP
               ↓
         Network discovery
               ↓
          m3u8/mp4/mpd
               ↓
          Cleanvid player
```

Questo consente di mantenere un'architettura universale senza scrivere un modulo specifico per ogni sito.

---

# 4. Stremio: cosa prenderei

Stremio documenta un oggetto `Stream` che può rappresentare una sorgente HTTP/HTTPS/RTMP, un YouTube ID, oppure un torrent tramite `infoHash` e `fileIdx`. La documentazione ufficiale mostra quindi chiaramente la separazione concettuale tra sorgente e player. [Fonte: Stremio Add-on SDK](https://github.com/Stremio/stremio-addon-sdk/blob/master/docs/api/responses/stream.md)

Il concetto utile per Cleanvid è:

```text
SOURCE
  ↓
STREAM
  ↓
PLAYER
```

Ma Cleanvid deve aggiungere un livello prima:

```text
URL
  ↓
DISCOVERY
  ↓
SOURCE
  ↓
STREAM
  ↓
PLAYER
```

Stremio è quindi una fonte di ispirazione architetturale, non il modello completo da copiare.

---

# 5. Hydra: cosa prenderei

Hydra è utile soprattutto come esempio di separazione fra:

```text
UI
 ↓
APPLICATION CORE
 ↓
SPECIALIZED ENGINE
```

Per Cleanvid:

```text
UI
 ↓
CLEANVID CORE
 ↓
 ├── discovery engine
 ├── streaming engine
 ├── filtering engine
 └── browser engine
```

Non vedo invece un motivo per trasformare Cleanvid in un clone di Hydra.

---

# 6. La risposta di Claude: cosa considero corretto

La seconda analisi ha evidenziato che il progetto reale è già più avanti del vecchio `cleanvid.py`.

In particolare segnala:

- `models/`;
- `api/`;
- `web/`;
- `media/manifesto.py`;
- `media/embed.py`;
- `media/estrazione.py`;
- test già presenti;
- database/Alembic;
- futura registrazione;
- stanze/watchparty/chat.

Quindi **non bisogna ripetere la roadmap di modularizzazione del vecchio file**.

La prima cosa da verificare è se l'architettura attuale supporta già bene il concetto di Universal Media Discovery.

Claude propone inoltre di unificare `Lettore` ed `Estratto` in un descrittore comune. Questo è coerente con l'obiettivo:

```text
"ho trovato una sorgente riproducibile"
```

anziché:

```text
"questa è una sorgente YouTube"
"questa è una sorgente estratta"
```

Considero questa una buona direzione.

---

# 7. Torrent: la mia valutazione

## Sì, può avere senso.

Ma **non lo metterei al centro del progetto**.

Il torrent dovrebbe essere un ulteriore tipo di `Stream`, non la definizione di Cleanvid.

Quindi:

```text
Stream
 ├── HTTP
 ├── HLS
 ├── DASH
 ├── file locale
 └── Torrent
```

Questo è molto simile alla logica dello Stream Object documentata da Stremio.

La documentazione ufficiale di Stremio prevede infatti `infoHash` + `fileIdx` come sorgente torrent. citeturn0search1

---

# 8. Perché il torrent potrebbe essere interessante

Un torrent può essere trattato come una sorgente che il motore trasforma in uno stream leggibile dal player:

```text
magnet / .torrent
       │
       ▼
 torrent engine
       │
       ▼
 file / byte stream
       │
       ▼
 Cleanvid stream
       │
       ▼
 player
```

Il vantaggio architetturale è che il player non deve necessariamente sapere che dietro c'è BitTorrent.

Per lui è semplicemente:

```text
stream riproducibile
```

Questo mantiene pulita l'astrazione.

---

# 9. Torrent nel browser vs desktop

Qui emerge una differenza tecnica molto importante.

## Web App

WebTorrent documenta un client torrent funzionante direttamente nel browser tramite WebRTC. Può aggiungere un magnet/torrent e riprodurre file video prima che il download sia completo. citeturn0search0turn0search5

Ma c'è una limitazione importante:

> un client torrent nel browser non è equivalente a un client BitTorrent desktop completo.

La documentazione WebTorrent spiega che il browser comunica con peer compatibili WebRTC/WebTorrent; non può semplicemente comportarsi come un client TCP/uTP generico verso qualsiasi peer BitTorrent. citeturn0search5

Quindi:

```text
WEB APP
  ↓
WebTorrent/WebRTC
  ↓
web-compatible peers
```

mentre:

```text
DESKTOP APP
  ↓
native torrent engine
  ↓
rete BitTorrent completa
```

Sono due implementazioni diverse.

---

# 10. Questo rende molto interessante avere due front-end

Una possibile architettura futura:

```text
                    CLEANVID CORE
                         │
              ┌──────────┴──────────┐
              │                     │
          WEB CLIENT            DESKTOP APP
              │                     │
          browser APIs          native APIs
              │                     │
        WebTorrent/WebRTC       native torrent
        quando disponibile       engine
              │                     │
              └──────────┬──────────┘
                         ▼
                       PLAYER
```

Il core concettuale resta lo stesso.

La differenza è nel backend disponibile.

---

# 11. Web App: vantaggi

Una Web App avrebbe senso per:

- accesso immediato;
- nessuna installazione;
- condivisione di stanze;
- watchparty;
- chat;
- gestione account;
- player universale per URL compatibili;
- contenuti HTTP/HLS/DASH;
- eventuale WebTorrent per torrent compatibili.

Il browser è inoltre un ambiente naturale per il player.

---

# 12. Web App: limite importante

Non darei per scontato che una Web App possa replicare tutte le capacità dell'app desktop.

In particolare:

```text
browser
  ↓
CORS
  ↓
sandbox
  ↓
WebRTC
  ↓
accesso limitato alla rete
```

Una pagina web non può avere lo stesso controllo di un'app nativa sul sistema operativo.

Per esempio il browser non può semplicemente:

- intercettare qualsiasi richiesta di un altro processo;
- usare liberamente qualsiasi socket TCP;
- gestire qualsiasi client torrent;
- leggere qualsiasi file locale;
- usare Chromium "esterno" come motore di discovery senza permessi/integrazione.

Quindi la Web App deve essere progettata per ciò che il browser può realmente fare.

---

# 13. Desktop App: vantaggi

La Desktop App potrebbe essere il vero "Cleanvid completo":

```text
Cleanvid Desktop
 │
 ├── Universal Media Discovery
 ├── yt-dlp
 ├── browser/CDP
 ├── local files
 ├── native HTTP/HLS
 ├── torrent engine
 ├── player
 └── cache
```

Può avere un motore nativo per il torrent e, se necessario, un browser Chromium controllato localmente.

Questo risolve molte delle limitazioni della Web App.

---

# 14. Ma non farei due progetti

Questo è importante.

Non:

```text
Cleanvid Web
Cleanvid Desktop
```

come due codebase completamente diverse.

Meglio:

```text
                 CLEANVID PLATFORM
                        │
                     CORE/API
                        │
          ┌─────────────┴─────────────┐
          │                           │
      Web Client                 Desktop Client
          │                           │
       browser                   native bridge
```

Le due applicazioni condividono:

- modello Media;
- Stream;
- metadata;
- history;
- favorites;
- rooms;
- playback state;
- API;
- concetti di discovery.

Cambiano solamente i backend che il runtime può usare.

---

# 15. Dove mettere il torrent

Non:

```text
torrent/
    applicazione principale
```

ma qualcosa come:

```text
streaming/
    stream.py
    http.py
    hls.py
    dash.py
    torrent.py
```

Il torrent diventa un backend.

Concettualmente:

```text
class StreamBackend:

    HTTP
    HLS
    DASH
    TORRENT
```

Non è necessario implementare ora una classe Python letterale; è il confine architetturale che conta.

---

# 16. Torrent + Universal Discovery

Una possibile pipeline futura:

```text
URL
 │
 ▼
Discovery
 │
 ├── direct URL
 ├── HTML
 ├── iframe
 ├── manifest
 ├── yt-dlp
 ├── browser
 └── torrent/magnet
          │
          ▼
       Stream
          │
          ▼
       Player
```

Ma bisogna distinguere:

### URL pagina

```text
https://example.com/video
```

→ discovery.

### URL manifest

```text
https://example.com/live.m3u8
```

→ stream diretto.

### Magnet

```text
magnet:?xt=...
```

→ torrent backend.

### `.torrent`

→ torrent backend.

Quindi il torrent può essere integrato elegantemente senza contaminare il resolver.

---

# 17. La parte legale/prodotto

Qui bisogna essere particolarmente chiari.

L'integrazione BitTorrent **non rende automaticamente Cleanvid illecito**, così come BitTorrent/WebTorrent sono tecnologie generiche.

WebTorrent stesso presenta esempi con materiale Creative Commons e Internet Archive. citeturn0search3turn0search6

Stremio documenta il torrent come una tipologia di stream nel proprio SDK. citeturn0search1

Ma il contenuto specifico resta determinante.

Quindi se Cleanvid viene open-source, io documenterei chiaramente:

```text
Cleanvid provides media playback and discovery functionality.

Users are responsible for ensuring that they have the
right to access and reproduce the media they provide.

Cleanvid does not provide copyrighted media catalogs
or intentionally facilitate unauthorized access.
```

E manterrei fuori dal progetto qualsiasi meccanismo progettato specificamente per indicizzare o distribuire copie non autorizzate.

---

# 18. Non farei un catalogo torrent di film

Questa è una distinzione importante.

Sono due prodotti completamente diversi:

### A

```text
utente
 ↓
incolla magnet/torrent autorizzato
 ↓
Cleanvid
 ↓
riproduce
```

### B

```text
utente
 ↓
cerca "film X"
 ↓
Cleanvid trova torrent pirata
 ↓
scarica
```

Il secondo modello cambia completamente il rischio e il posizionamento del progetto.

Se l'obiettivo è costruire un player universale/open-source, **non serve B**.

---

# 19. Una possibile architettura definitiva

Questa è, al momento, la mia proposta preferita:

```text
                         CLEANVID
                            │
                     ┌──────┴──────┐
                     │             │
                    CORE          UI
                     │             │
        ┌────────────┼─────────────┐
        │            │             │
   DISCOVERY      STREAMING      PLATFORM
        │            │             │
        │            │        accounts/rooms
        │            │        history/chat
        │            │
        │        ┌───┼────┬────┐
        │        │   │    │    │
        │       HTTP HLS DASH Torrent
        │
   ┌────┼─────┬─────┬──────┐
   │    │     │     │      │
 direct HTML iframe yt-dlp browser
   │    │     │     │      │
   └────┴─────┴─────┴──────┘
                  │
                  ▼
              MEDIA/STREAM
                  │
             ┌────┴────┐
             │         │
           filter    subtitles
             │         │
             └────┬────┘
                  ▼
                PLAYER
```

---

# 20. Web App + Desktop App

Io vedrei il prodotto finale così:

```text
                  Cleanvid Platform
                         │
             ┌───────────┴───────────┐
             │                       │
          WEB APP                DESKTOP APP
             │                       │
        browser player          native player
        WebTorrent*             native torrent
        rooms                   browser/CDP
        chat                    local files
        accounts                cache
             │                       │
             └───────────┬───────────┘
                         │
                      shared
                    API / models
```

`*` WebTorrent sarebbe disponibile solo nei casi compatibili con il modello WebRTC/WebTorrent.

---

# 21. La mia raccomandazione sul torrent

### Lo integrerei?

**Sì, come backend di streaming opzionale.**

### Lo metterei al centro?

**No.**

### Lo userei per costruire un catalogo di film?

**No.**

### Lo renderei parte del modello `Stream`?

**Sì.**

### Farei subito un client torrent nativo?

**No.** Prima stabilirei il modello `Media/Stream` e l'interfaccia backend.

### Fare una Web App?

**Sì, soprattutto per il futuro sistema di stanze/watchparty e per il player universale.**

### Fare una Desktop App?

**Sì, se vogliamo tutte le capacità di Cleanvid, soprattutto browser/CDP, file locali e torrent nativo.**

---

# 22. La questione più importante da risolvere prima

Prima di decidere se usare WebTorrent, libtorrent o un altro motore, bisogna definire precisamente:

```text
Media
Stream
Playback
Discovery
Backend
```

Se queste cinque astrazioni sono corrette, il torrent diventa semplicemente:

```text
un backend in più
```

e non una decisione che condiziona tutta l'architettura.

---

# 23. Cosa chiederei a Claude adesso

Gli darei questo documento e chiederei esplicitamente di non ripartire dal vecchio Cleanvid.

Domande:

1. La definizione "Universal Media Discovery" è architetturalmente corretta?
2. `Source → Stream → Player` è sufficiente oppure serve `URL → Discovery → Source → Stream → Player`?
3. È corretto evitare provider-specific modules e usare yt-dlp/browser/manifest/direct URL come resolver?
4. Come dovrebbe essere definito il modello `Media/Stream`?
5. Il torrent dovrebbe essere un `StreamBackend`?
6. WebTorrent è adatto alla Web App oppure servirebbe un backend server-side?
7. Quando conviene un motore torrent nativo nella Desktop App?
8. Come condividere il core tra Web App e Desktop App?
9. Come separare Media Engine e Platform/Watchparty?
10. Quali sono i rischi tecnici e di sicurezza di una Web App + torrent?
11. Quali sono i rischi di privacy del browser/CDP?
12. Quale sarebbe il minimo MVP architetturale prima di aggiungere torrent?
13. Quali decisioni prendere oggi e quali lasciare reversibili?

---

# 24. Conclusione

La mia posizione attuale è:

> **Sì al torrent, ma come capacità del motore di streaming, non come identità di Cleanvid.**

Il cuore deve rimanere:

```text
                QUALSIASI URL
                      ↓
             UNIVERSAL DISCOVERY
                      ↓
              MEDIA / STREAM
                      ↓
           ┌──────────┼──────────┐
           ↓          ↓          ↓
          HTTP       HLS       TORRENT
           │          │          │
           └──────────┼──────────┘
                      ↓
                    PLAYER
```

E sopra questo motore possiamo costruire:

```text
              CLEANVID PLATFORM
                     │
             ┌───────┴───────┐
             │               │
           WEB             DESKTOP
             │               │
          rooms          full engine
          chat           torrent
          sharing        browser/CDP
```

Questa mi sembra una direzione più coerente con l'idea originale di Cleanvid: **non una collezione di player per siti specifici, ma un layer universale tra "URL che l'utente vuole vedere" e "sorgente video effettivamente riproducibile".**

## Fonti tecniche consultate

- Stremio Add-on SDK — Stream Object: https://github.com/Stremio/stremio-addon-sdk/blob/master/docs/api/responses/stream.md
- WebTorrent documentation: https://webtorrent.io/docs
- WebTorrent FAQ: https://webtorrent.io/faq
- WebTorrent site: https://webtorrent.io/
- Stremio example add-on: https://github.com/Stremio/addon-helloworld-python
