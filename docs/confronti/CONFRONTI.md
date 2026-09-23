from pathlib import Path
from datetime import datetime

out = Path("/mnt/data/Cleanvid_analisi_comparativa_Stremio_Hydra.md")

text = r"""# Cleanvid — dossier di analisi e confronto
## Materiale per confronto con Claude / revisione architetturale

Data: 2026-09-23

---

## 0. Obiettivo di questo documento

Questo dossier raccoglie:

- ciò che è emerso dall'analisi del progetto Cleanvid caricato nella conversazione;
- le ricerche pubbliche effettuate su Stremio e Hydra;
- il confronto architetturale tra i tre progetti;
- le idee che sembrano trasferibili a Cleanvid;
- ciò che NON conviene copiare o introdurre;
- una proposta di direzione architetturale, senza ancora modificare il codice.

Il documento è pensato come base da dare anche a un altro modello (es. Claude) per ottenere una seconda analisi indipendente e poi confrontare le conclusioni.

IMPORTANTE: questo documento distingue, dove possibile, tra:
1. fatti osservati nelle fonti;
2. osservazioni sul codice Cleanvid;
3. inferenze/proposte architetturali.

---

# 1. Che cos'è Cleanvid oggi

Il progetto caricato contiene un `cleanvid.py` molto grande e monolitico (7.747 righe nella versione analizzata), accompagnato da file JSON, log e README.

L'idea dichiarata del progetto è un server locale che riduce un link video a una esperienza di playback più controllabile, usando:

- embed ufficiali quando disponibili;
- yt-dlp come fallback per l'estrazione dello stream;
- player HTML5 "nudo";
- proxy locale per gli stream;
- gestione HLS;
- filtri pubblicitari;
- SponsorBlock per YouTube;
- una modalità "ascolto" che usa un browser reale controllato via CDP;
- history/favorites/groups e altri elementi di organizzazione.

Nel codice sono presenti, tra gli altri:

- riconoscimento YouTube, Vimeo, Dailymotion, Streamable, Twitch, Instagram, Facebook e oEmbed;
- estrazione tramite yt-dlp;
- cache metadata e thumbnails;
- proxy HTTP;
- proxy HLS;
- costruzione di master HLS per audio/video separati;
- firme HMAC per gli URL `/seg`;
- autenticazione locale;
- Chromium/CDP;
- blocco di domini pubblicitari;
- cosmetic filtering;
- popup blocking;
- SponsorBlock;
- gestione di marker pubblicitari HLS;
- statistiche dei segmenti pubblicitari rimossi.

La struttura attuale concentra quasi tutto in un unico modulo.

---

# 2. Architettura attuale di Cleanvid

Modello semplificato:

    URL utente
        |
        +--> embed ufficiale
        |
        +--> oEmbed
        |
        +--> yt-dlp
                |
                v
             stream
                |
             proxy
                |
        +-------+--------+
        |                |
       HLS             video
        |
        +--> rewrite playlist
        +--> riscrittura URI
        +--> filtraggio marker/segmenti pubblicitari
        |
        v
      player

Modalità browser/listening:

    URL
     |
     v
   Chromium
     |
     +--> Network.setBlockedURLs
     +--> CDP
     +--> stealth
     +--> cosmetic filtering
     +--> popup blocking
     +--> media discovery
     |
     v
   playback/capture

Questa architettura è già funzionale e relativamente sofisticata, ma il file monolitico rende più difficile:

- testare singole parti;
- sostituire un provider;
- aggiungere nuove piattaforme;
- riutilizzare il motore HLS;
- distinguere core, UI, browser e filtering;
- permettere contributi open-source mirati.

---

# 3. Elementi già forti di Cleanvid

## 3.1 Resolver multi-piattaforma

Il progetto non è legato a una sola piattaforma.

Ha già un concetto implicito di "source resolver", anche se non è formalizzato come interfaccia.

## 3.2 Proxy di streaming

Il proxy permette di:

- controllare gli URL ammessi;
- aggiungere header necessari;
- gestire Range;
- riscrivere playlist HLS;
- proteggere i link `/seg` con firme HMAC.

Questa è una parte importante del progetto.

## 3.3 HLS

Cleanvid possiede già una logica non banale per:

- manifest;
- varianti;
- audio/video separati;
- master HLS;
- URI firmati;
- marker pubblicitari.

La funzione `rewrite_playlist()` è concettualmente quasi un componente autonomo.

## 3.4 Filtering su più livelli

Il filtering non è un singolo "adblock":

1. network filtering;
2. cosmetic filtering;
3. popup handling;
4. HLS ad filtering.

Questa separazione concettuale è importante anche se oggi il codice è nello stesso file.

## 3.5 Player e layout

L'obiettivo del progetto non è solo "rimuovere pubblicità": è creare una esperienza di visione personalizzabile, con possibilità di aggregare contenuti, cambiare sorgente e scegliere layout.

Questa è probabilmente l'identità di prodotto più interessante da preservare.

---

# 4. Stremio: cosa abbiamo verificato

Fonti principali:

- Stremio Core: https://github.com/Stremio/stremio-core
- Stremio Addon SDK: https://github.com/Stremio/stremio-addon-sdk
- Protocollo Add-on: https://github.com/Stremio/stremio-addon-sdk/blob/master/docs/protocol.md
- Stream object: https://github.com/Stremio/stremio-addon-sdk/blob/master/docs/api/responses/stream.md

## 4.1 Stremio Core

Il repository ufficiale descrive `stremio-core` come il motore Rust condiviso dalle app Stremio.

Il core comprende:

- tipi;
- addon manifests/resources;
- metadata;
- streams;
- subtitles;
- library;
- playback state;
- player model;
- addon transport;
- runtime;
- deep links.

Le UI sono descritte come layer sottili sopra il core.

Questo è molto interessante per Cleanvid: separare il "motore" dalla UI.

## 4.2 Add-on come astrazione fondamentale

L'SDK ufficiale descrive Stremio come un media center che scopre, organizza e riproduce video attraverso add-on.

Un add-on è un piccolo servizio HTTP che risponde a richieste per:

- catalog;
- metadata;
- stream;
- subtitles;
- addon catalog.

Stremio legge il manifest dell'add-on e decide quali add-on sono rilevanti per una richiesta.

Il concetto chiave è:

    APP
     |
     +--> catalog
     +--> metadata
     +--> stream
     +--> subtitles
     |
     v
   ADD-ON
     |
     v
 data/source provider

Quindi il core non deve incorporare ogni sorgente.

## 4.3 Il protocollo Stream

La documentazione ufficiale dello SDK mostra che uno stream può essere rappresentato in diversi modi.

Tra quelli documentati:

- URL HTTP/HTTPS/FTP/RTMP;
- YouTube ID;
- torrent tramite `infoHash` e `fileIdx`;
- altri formati/sorgenti supportati.

Questo è un punto architetturale molto importante:

    SOURCE
       |
       v
    STREAM OBJECT
       |
       v
     PLAYER

Il player non deve necessariamente conoscere la provenienza logica dello stream.

## 4.4 Torrent in Stremio

Quindi l'osservazione iniziale dell'utente è corretta in senso tecnico: il protocollo Stremio contempla esplicitamente torrent come tipo di stream.

Ma bisogna distinguere:

- Stremio come applicazione/protocollo;
- add-on che forniscono determinati stream;
- contenuto fornito da quelle sorgenti;
- legalità del singolo contenuto.

Il protocollo torrent è una tecnologia; la liceità dipende dal contenuto e dai diritti relativi a quel contenuto.

Questo dossier non considera legittimo scaricare o distribuire contenuti protetti senza autorizzazione.

---

# 5. Hydra: cosa abbiamo verificato

Fonti principali:

- repository ufficiale: https://github.com/hydralauncher/hydra
- README ufficiale: https://github.com/hydralauncher/hydra/blob/main/README.md

## 5.1 Architettura

Il repository attuale descrive Hydra come piattaforma open-source per la gestione della libreria di giochi.

La stack indicata attualmente comprende:

- Node.js;
- Electron;
- React;
- TypeScript;
- Rust;
- libtorrent.

Il repository dichiara che il motore torrent è basato su libtorrent e che l'integrazione nativa moderna usa un wrapper Rust.

Il README della versione corrente presenta anche una separazione concettuale tra:

- UI;
- logica applicativa;
- motore torrent.

## 5.2 Lezione architetturale di Hydra

La parte da prendere da Hydra non è il dominio "giochi".

È il principio:

    UI
      |
      v
    APPLICATION CORE
      |
      v
    SPECIALIZED ENGINE

Per Cleanvid potrebbe diventare:

    UI
      |
      v
    CLEANVID CORE
      |
      +--> source/resolver engine
      +--> streaming engine
      +--> browser engine
      +--> filtering engine

---

# 6. Confronto Stremio vs Hydra vs Cleanvid

| Concetto | Stremio | Hydra | Cleanvid oggi |
|---|---|---|---|
| UI separata dal core | Sì | Sì | Parzialmente/no |
| Core indipendente | Sì, stremio-core | Sì | No, monolite |
| Sorgenti astratte | Molto | Sì, nel dominio launcher/download | Implicite |
| Plugin/add-on | Centrale | Non centrale nello stesso senso | No |
| Stream abstraction | Molto forte | Download abstraction | Parziale |
| Torrent | Supportato dal protocollo stream | Core del download engine | Non core |
| Player | Core model + app | Launcher/game execution | Player HTML5 |
| Browser/CDP | Non centrale | Non centrale | Molto importante |
| HLS proxy | Non è il focus | No | Molto importante |
| Ad filtering | Non è il focus | No | Core feature |
| History/library | Sì | Sì | Già presente |
| Favorites | Sì | Sì | Già presente |
| Groups/layout | Diverso | Diverso | Identità importante |
| Metadata | Centrale | Centrale | Presente ma distribuito |
| Estendibilità | Add-on protocol | Moduli/engine | Da costruire |
| Testabilità modulare | Alta | Alta | Da migliorare |

---

# 7. L'idea più importante da prendere da Stremio

Non è "integrare torrent".

È:

## SOURCE -> STREAM -> PLAYER

In Cleanvid oggi molte cose sono fuse.

La direzione auspicabile è formalizzare:

    Source
      |
      v
    Resolver
      |
      v
    Stream descriptor
      |
      v
    Playback backend
      |
      v
    Player

Un possibile oggetto concettuale:

    Source:
        provider
        original_url
        title
        thumbnail
        metadata
        capabilities

    Stream:
        kind
        url
        headers
        protocol
        quality
        live
        duration
        subtitles
        source_id

Non è necessario copiare il formato Stremio.

È il principio di separazione che interessa.

---

# 8. Possibile architettura Cleanvid futura

Proposta:

    cleanvid/
    |
    +-- app.py
    |
    +-- core/
    |   +-- config.py
    |   +-- auth.py
    |   +-- models.py
    |   +-- server.py
    |
    +-- sources/
    |   +-- base.py
    |   +-- youtube.py
    |   +-- twitch.py
    |   +-- vimeo.py
    |   +-- dailymotion.py
    |   +-- generic.py
    |
    +-- extraction/
    |   +-- ytdlp.py
    |   +-- embeds.py
    |   +-- metadata.py
    |
    +-- streaming/
    |   +-- proxy.py
    |   +-- hls.py
    |   +-- mux.py
    |   +-- signing.py
    |
    +-- filtering/
    |   +-- network.py
    |   +-- cosmetic.py
    |   +-- popup.py
    |   +-- hls_ads.py
    |
    +-- browser/
    |   +-- chromium.py
    |   +-- cdp.py
    |   +-- capture.py
    |
    +-- ui/
    |   +-- index.html
    |   +-- player.js
    |   +-- styles.css
    |
    +-- tests/
    |   +-- test_sources.py
    |   +-- test_hls.py
    |   +-- test_filtering.py
    |
    +-- README.md
    +-- LICENSE
    +-- .gitignore

Questa è una proposta, NON una decisione già presa.

---

# 9. Source Provider

Una possibile interfaccia futura:

    class VideoSource:
        name = "generic"

        def can_handle(self, url):
            ...

        def metadata(self, url):
            ...

        def resolve(self, url):
            ...

Il core potrebbe fare:

    for source in SOURCES:
        if source.can_handle(url):
            return source.resolve(url)

Questo permetterebbe di aggiungere piattaforme senza modificare il server principale.

---

# 10. Stream abstraction

Una possibile astrazione:

    Stream
      |
      +-- url
      +-- protocol
      +-- headers
      +-- quality
      +-- audio
      +-- video
      +-- live
      +-- subtitles
      +-- source

Il player riceverebbe uno Stream, invece di sapere come è stato trovato.

Questo è il concetto più vicino a Stremio che sembra utile per Cleanvid.

---

# 11. HLS come modulo indipendente

Il codice attuale contiene già una parte abbastanza autonoma.

La funzione:

    rewrite_playlist()

fa concettualmente:

- parse della playlist;
- riconoscimento marker;
- rimozione segmenti;
- riscrittura URI;
- firma URL;
- gestione discontinuità.

Potrebbe diventare:

    streaming/hls.py

con test indipendenti.

Esempi di test possibili:

1. playlist senza ads -> invariata salvo URI proxy;
2. CUE-OUT -> segmenti rimossi;
3. CUE-IN -> ripresa del flusso;
4. DATERANGE Twitch -> filtro;
5. URL relativi -> risoluzione corretta;
6. URI con query -> preservati;
7. playlist master -> varianti mantenute.

Questo è un candidato ideale per il primo refactoring perché non richiede di cambiare la UI.

---

# 12. Filtering come sistema a livelli

Attualmente Cleanvid ha tre/quattro concetti distinti.

## Network

    Browser
       |
       v
    blocked URLs
       |
       X

## Cosmetic

    HTML/DOM
       |
       v
    suspicious overlay/iframe
       |
       X / hide

## Popup

    window.open
       |
       X

## HLS

    manifest
       |
       v
    ad markers
       |
       v
    ad segments
       |
       X

Questi dovrebbero rimanere concettualmente separati.

Non conviene costruire un unico "mega adblocker" che usa semplici substring come `ad`, perché rischia di bloccare CDN o componenti legittimi del player.

---

# 13. Sicurezza

Cleanvid contiene già alcune misure interessanti:

- `STREAMS` come registro degli stream conosciuti;
- firme HMAC per `/seg`;
- autenticazione tramite ticket firmati;
- rate limiting rudimentale dei login;
- modalità pubblica esplicitamente più restrittiva;
- commenti che riconoscono il rischio di esporre il browser autenticato.

Questo è un punto da preservare.

In particolare, la modalità browser/listening è molto più sensibile di un semplice proxy video perché il browser può contenere:

- cookie;
- sessioni;
- account autenticati;
- accesso a siti personali.

Quindi, prima di rendere il progetto pubblico, questo componente merita una security review separata.

---

# 14. Confine legale/di prodotto

Il progetto dovrebbe essere descritto come:

> applicazione locale per aggregare, risolvere e riprodurre contenuti da sorgenti che l'utente è autorizzato a utilizzare.

Da evitare come posizionamento:

> applicazione per trovare copie non autorizzate di contenuti.

Per analogia con Stremio/Hydra, la tecnologia sottostante può essere neutrale, ma questo non rende automaticamente leciti tutti i contenuti che una sorgente può fornire.

Il progetto non dovrebbe essere progettato per:

- bypass DRM;
- bypass paywall;
- furto di cookie/token;
- accesso non autorizzato;
- indicizzazione intenzionale di copie pirata come obiettivo del prodotto.

Il supporto a sorgenti che l'utente è autorizzato a usare è invece un caso d'uso molto più chiaro.

---

# 15. Cosa NON fare

## Non fare subito un mega-refactoring

Il file funziona. Conviene conservarlo come baseline.

## Non trasformare Cleanvid in un clone di Stremio

Prendere il concetto di addon/source è utile; copiare l'intero modello di prodotto no.

## Non trasformarlo in Hydra

Il dominio è diverso.

## Non integrare torrent solo perché Stremio lo fa

Il torrent non risolve il problema principale di Cleanvid.

Il problema principale è:

    aggregazione
    source switching
    playback
    layout
    filtering

## Non rendere tutto un plugin

Prima bisogna definire bene le interfacce interne.

---

# 16. Direzione consigliata

Il prodotto potrebbe evolvere verso:

                     CLEANVID
                        |
              +---------+---------+
              |                   |
             CORE                UI
              |
      +-------+--------+
      |       |        |
   SOURCES STREAMS FILTERS
      |       |        |
      |       |        +-- network
      |       |        +-- cosmetic
      |       |        +-- HLS
      |       |
      |       +-- HTTP
      |       +-- HLS
      |       +-- mux
      |
      +-- YouTube
      +-- Twitch
      +-- Vimeo
      +-- generic

Il Browser/CDP rimane un backend specializzato:

              CORE
                |
             BROWSER
                |
              CDP
                |
            Chromium

---

# 17. Sequenza di lavoro proposta

Non ancora da eseguire automaticamente.

### Fase 1 — congelare la baseline

- salvare il `cleanvid.py` funzionante;
- eseguire compile/test;
- documentare il comportamento attuale.

### Fase 2 — sicurezza/repository

- controllare segreti;
- escludere `auth.key`;
- escludere log personali;
- escludere cache/thumbnails locali;
- preparare `.gitignore`;
- configurare esempio di environment.

### Fase 3 — estrarre moduli puri

Prima:

    streaming/hls.py

Poi:

    sources/base.py
    extraction/ytdlp.py

Poi:

    filtering/

### Fase 4 — introdurre modelli

Creare:

    Source
    Stream
    MediaMetadata

senza cambiare ancora il comportamento.

### Fase 5 — test

Partire dalle funzioni pure:

- HLS;
- URL/signature;
- source recognition;
- metadata;
- filtering.

### Fase 6 — separare UI/backend

Solo quando le interfacce interne sono stabili.

---

# 18. Punti su cui chiedere una seconda opinione a Claude

Le domande più utili da sottoporre a Claude sono:

1. "Guardando Cleanvid, Stremio Core e Hydra, quale architettura modulare consiglieresti?"
2. "È davvero utile introdurre una Source/Stream abstraction oppure sarebbe over-engineering?"
3. "Quali parti di Cleanvid conviene estrarre per prime dal monolite?"
4. "Come progetteresti un Source Provider API?"
5. "Come separeresti HLS proxy, filtering e browser/CDP?"
6. "Quali rischi di sicurezza vedi nella modalità listening?"
7. "Quali parti dovrebbero restare private/local-only?"
8. "Qual è la superficie minima di API pubblica per un progetto GitHub?"
9. "Quali idee di Stremio sono architetturalmente riutilizzabili senza trasformare Cleanvid in un clone?"
10. "Quali sono i punti che potrebbero rendere il progetto difficile da mantenere con contributori esterni?"

---

# 19. Fonti web consultate

Stremio Core:
https://github.com/Stremio/stremio-core

Stremio Add-on SDK:
https://github.com/Stremio/stremio-addon-sdk

Stremio Add-on Protocol:
https://github.com/Stremio/stremio-addon-sdk/blob/master/docs/protocol.md

Stremio Stream Object:
https://github.com/Stremio/stremio-addon-sdk/blob/master/docs/api/responses/stream.md

Hydra:
https://github.com/hydralauncher/hydra

Hydra README:
https://github.com/hydralauncher/hydra/blob/main/README.md

Stremio official website:
https://www.stremio.com/

---

# 20. Sintesi finale

La conclusione provvisoria è:

**Cleanvid non dovrebbe diventare né Hydra né Stremio.**

Ma può prendere il meglio dei due modelli:

### Da Stremio

    Source
      ↓
    Stream
      ↓
    Player

e soprattutto:

    Core
      ↕
    Providers/Add-ons

### Da Hydra

    UI
      ↓
    Application Core
      ↓
    Specialized Engines

### Da Cleanvid

    multi-source
    source switching
    custom layouts
    naked player
    HLS proxy
    filtering
    browser listening
    history
    favorites
    groups

La possibile identità finale è quindi:

> **Cleanvid = un media aggregation/playback engine locale, estensibile per sorgenti, con un player personalizzabile e un layer di filtering/proxy.**

Il vero valore da sviluppare non è il semplice "ad blocker" e non è il torrent.

È l'astrazione:

    qualsiasi sorgente autorizzata
              ↓
           Cleanvid
              ↓
      stream normalizzato
              ↓
        esperienza unica

Prima di modificare il codice, è ragionevole far analizzare questo stesso dossier a un secondo modello e confrontare criticamente le due proposte.
"""

out.write_text(text, encoding="utf-8")
print(f"Creato: {out}")
print(f"Dimensione: {out.stat().st_size} bytes")


stremio:https://www.stremio.com/translation/it
hydra: https://hydralauncher.gg/
