/* Il lettore: due tracce da tenere insieme, HLS, e un guardiano.
 *
 * La parte che ha richiesto piu' lavoro non e' far partire un video: e' farlo
 * ripartire. Un flusso si ferma per mille motivi che non sono colpa di
 * nessuno - un segmento che tarda, la rete che cambia, un indirizzo che
 * scade dopo qualche ora - e un lettore che si ferma e basta e' un lettore
 * rotto, anche se il codice e' giusto.
 *
 * Quindi qui dentro ci sono due cose: quello che fa suonare il video, e
 * quello che lo rimette in piedi quando si pianta. La seconda e' piu' lunga
 * della prima.
 */
(() => {
  "use strict";

  const video = document.getElementById("video");
  if (!video) return;
  const dati = video.dataset;
  const audio = document.getElementById("audio");

  // --------------------------------------------------------------------
  // 1. due tracce tenute insieme
  // --------------------------------------------------------------------
  /* Quasi nessun sito serve piu' un file unico: danno un video muto e un
   * audio a parte. Cucirli sul server costa un processo per spettatore; il
   * browser invece sa suonarli tutti e due, e l'unico lavoro che resta e'
   * impedire che si separino.
   *
   * Le soglie sono state trovate guardando uno schermo, non a tavolino:
   *  - sotto mezzo secondo di scarto NON si salta: si cambia
   *    impercettibilmente la velocita' dell'audio finche' rientra. Un salto
   *    si sente molto piu' di un ritardo che si chiude da solo;
   *  - non piu' di un salto al secondo, o un video che fatica a partire entra
   *    in un ciclo di salti e non ne esce.
   */
  const SCARTO_MASSIMO = 0.5;
  const CORREZIONE = 0.06;          // 6%: sopra si sente, sotto non recupera
  const PAUSA_FRA_SALTI = 1000;

  let vuoleSuonare = false;         // cosa ha chiesto chi guarda, non cosa fa

  function allinea() {
    let ultimoSalto = 0;

    video.addEventListener("play", () => {
      vuoleSuonare = true;
      audio.play().catch(() => {});
    });
    video.addEventListener("pause", () => {
      // solo se e' una pausa vera: quella per mancanza di dati la gestisce
      // il guardiano, e fermare l'audio li' farebbe perdere l'allineamento
      if (!video.seeking) vuoleSuonare = !video.paused;
      audio.pause();
    });
    video.addEventListener("seeking", () => { audio.currentTime = video.currentTime; });
    video.addEventListener("ratechange", () => { audio.playbackRate = video.playbackRate; });
    // il volume si copia, il muto NO: il video qui e' muto per forza, e
    // copiarlo rimuterebbe la traccia audio a ogni tocco del volume
    video.addEventListener("volumechange", () => { audio.volume = video.volume; });

    video.addEventListener("timeupdate", () => {
      if (audio.readyState < 2) return;
      const scarto = video.currentTime - audio.currentTime;
      const adesso = Date.now();
      if (Math.abs(scarto) > SCARTO_MASSIMO) {
        if (adesso - ultimoSalto < PAUSA_FRA_SALTI) return;
        ultimoSalto = adesso;
        audio.currentTime = video.currentTime;
        audio.playbackRate = video.playbackRate;
        return;
      }
      const spinta = Math.max(-CORREZIONE, Math.min(CORREZIONE, scarto));
      audio.playbackRate = video.playbackRate * (1 + spinta);
    });

    /* Se una delle due si ferma per mancanza di dati si ferma anche l'altra.
     * Senza, quella che ha i dati continua da sola e quando l'altra torna si
     * ritrovano a secondi di distanza: si sente come un doppiaggio sbagliato,
     * e il recupero costa un salto brutto. Meglio mezzo secondo di attesa. */
    const aspetta = () => { if (vuoleSuonare) { video.pause(); audio.pause(); } };
    const riparti = () => {
      if (!vuoleSuonare) return;
      if (video.readyState >= 3 && audio.readyState >= 3) {
        audio.currentTime = video.currentTime;
        video.play().catch(() => {});
        audio.play().catch(() => {});
      }
    };
    audio.addEventListener("waiting", aspetta);
    video.addEventListener("waiting", aspetta);
    audio.addEventListener("canplay", riparti);
    video.addEventListener("canplay", riparti);

    video.muted = true;             // il suono esce dall'altro elemento
  }

  // --------------------------------------------------------------------
  // 2. HLS
  // --------------------------------------------------------------------
  function montaHls(indirizzo) {
    // Safari e iOS suonano l'HLS da soli e meglio di qualunque libreria:
    // usarne una anche li' vuol dire rinunciare al decoder hardware
    if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = indirizzo;
      return;
    }
    if (typeof Hls === "undefined" || !Hls.isSupported()) {
      avvisa(dati.nienteFlusso || "");
      return;
    }
    const hls = new Hls({
      // in diretta si parte dal bordo, non da dove comincia il buffer:
      // altrimenti si guarda con mezzo minuto di ritardo senza sapere perche'
      liveSyncDurationCount: 3,
      // non si tiene in memoria tutto quello che e' gia' passato: su una
      // diretta lunga sono centinaia di megabyte, e la scheda muore
      backBufferLength: 60,
      maxBufferLength: 30,
      // piu' tentativi dei predefiniti: i nostri segmenti passano da un
      // proxy, e un proxy ha un inciampo in piu' della rete diretta
      fragLoadingMaxRetry: 6,
      levelLoadingMaxRetry: 4,
      manifestLoadingMaxRetry: 4,
    });
    hls.loadSource(indirizzo);
    hls.attachMedia(video);
    video.hlsjs = hls;

    let guastiMedia = 0;
    hls.on(Hls.Events.ERROR, (_, guaio) => {
      if (!guaio.fatal) return;
      /* Una lista senza segmenti non e' un guasto: e' una diretta che in
         questo momento sta mandando solo pubblicita', e noi l'abbiamo
         tolta. Fra qualche secondo tornera' della roba vera. Trattarla come
         un errore vorrebbe dire ricaricare la pagina ogni interruzione. */
      if (guaio.details === Hls.ErrorDetails.LEVEL_EMPTY_ERROR) {
        setTimeout(() => hls.startLoad(), 2000);
        return;
      }
      if (guaio.type === Hls.ErrorTypes.NETWORK_ERROR) {
        // un indirizzo scaduto risponde 404 o 403: li' non c'e' niente da
        // riprovare, il flusso va estratto di nuovo
        const codice = guaio.response && guaio.response.code;
        if (codice === 404 || codice === 403) { riestrai(); return; }
        hls.startLoad();
        return;
      }
      if (guaio.type === Hls.ErrorTypes.MEDIA_ERROR) {
        guastiMedia += 1;
        if (guastiMedia === 1) hls.recoverMediaError();
        // la seconda volta si cambia anche il codec audio: e' il rimedio che
        // la libreria stessa suggerisce quando il primo non basta
        else if (guastiMedia === 2) { hls.swapAudioCodec(); hls.recoverMediaError(); }
        else riestrai();
        return;
      }
      riestrai();
    });
  }

  // --------------------------------------------------------------------
  // 3. il guardiano
  // --------------------------------------------------------------------
  /* Un flusso si ferma per mille motivi che non sono colpa di nessuno. Il
   * browser, quando succede, non fa niente: resta fermo. Questo guarda se il
   * tempo avanza, e se non avanza prova a rimettere in moto - con una scala
   * di rimedi, dal piu' leggero al piu' pesante.
   */
  const FERMO_MS = 6000;            // quanto si aspetta prima di intervenire
  const TENTATIVI_MASSIMI = 4;

  let ultimoTempo = -1;
  let ultimoMovimento = Date.now();
  let tentativi = 0;

  function riestrai() {
    /* Ultima spiaggia: si ricarica la pagina, che rifa' l'estrazione. La
     * posizione non si perde - e' gia' sul server, e la ripresa la rimette.
     *
     * Una volta sola per pagina: se anche la seconda estrazione non regge,
     * ricaricare all'infinito non aiuta nessuno e nasconde il problema vero. */
    try {
      if (sessionStorage.getItem("cleanvid.riestratto") === dati.pagina) {
        avvisa(dati.nienteFlusso || "");
        return;
      }
      sessionStorage.setItem("cleanvid.riestratto", dati.pagina || "1");
    } catch (e) {}
    location.reload();
  }

  /* Su una diretta di Twitch, «fermo» quasi sempre vuol dire «pubblicita'».
   *
   * I loro spot sono cuciti dentro il flusso e noi li buttiamo via: finche'
   * dura l'interruzione non c'e' NIENTE da mandare, e il lettore aspetta. E'
   * il comportamento giusto - meglio aspettare che guardare la reclame - ma
   * uno schermo nero senza spiegazioni sembra un guasto nostro.
   *
   * Quindi lo si dice. Non un errore: una riga che si toglie da sola appena
   * torna il video. */
  function forseAnnuncio() {
    return dati.diretta === "1" &&
           (dati.piattaforma || "").toLowerCase() === "twitch";
  }

  function aspettaAnnuncio(mostra) {
    const gia = document.getElementById("attesa-annuncio");
    if (!mostra) { if (gia) gia.remove(); return; }
    if (gia || !dati.attesaAnnuncio) return;
    const riga = document.createElement("p");
    riga.id = "attesa-annuncio";
    riga.className = "attesa";
    riga.textContent = dati.attesaAnnuncio;
    (video.parentElement || document.body).insertAdjacentElement("afterend", riga);
  }

  function rianima() {
    tentativi += 1;
    if (forseAnnuncio()) {
      // niente scala di rimedi: non c'e' niente di rotto da rimettere a
      // posto, c'e' da aspettare. Si continua a chiedere, e si dice perche'.
      aspettaAnnuncio(true);
      const hls = video.hlsjs;
      if (hls) hls.startLoad();
      return;
    }
    if (tentativi > TENTATIVI_MASSIMI) { riestrai(); return; }

    const hls = video.hlsjs;
    if (hls) { hls.startLoad(); video.play().catch(() => {}); return; }

    // file diretto: prima una spinta, che quasi sempre basta - il decoder si
    // impunta su un fotogramma e un decimo di secondo lo sblocca
    if (tentativi === 1) {
      video.currentTime = video.currentTime + 0.1;
      video.play().catch(() => {});
      return;
    }
    // poi si riapre il flusso e si torna dov'eravamo
    const dove = video.currentTime;
    const sep = dati.flusso.includes("?") ? "&" : "?";
    video.src = dati.flusso + sep + "r=" + tentativi;
    video.load();
    const torna = () => {
      video.currentTime = dove;
      video.play().catch(() => {});
      video.removeEventListener("loadedmetadata", torna);
    };
    video.addEventListener("loadedmetadata", torna);
  }

  setInterval(() => {
    if (video.paused || video.ended || document.hidden) {
      ultimoMovimento = Date.now();
      return;
    }
    if (video.currentTime !== ultimoTempo) {
      ultimoTempo = video.currentTime;
      ultimoMovimento = Date.now();
      tentativi = 0;                // e' ripartito da solo: si ricomincia
      aspettaAnnuncio(false);       // e se c'era l'avviso, se ne va
      return;
    }
    if (Date.now() - ultimoMovimento < FERMO_MS) return;
    ultimoMovimento = Date.now();
    rianima();
  }, 1000);

  /* Un errore del `<video>` non e' recuperabile da solo: la sorgente e'
     caduta, e l'unica cosa sensata e' riprovare la scala dei rimedi. */
  video.addEventListener("error", () => { if (!video.hlsjs) rianima(); });

  function avvisa(testo) {
    if (!testo || document.getElementById("guasto-lettore")) return;
    const riga = document.createElement("p");
    riga.id = "guasto-lettore";
    riga.className = "err";
    riga.textContent = testo;
    (video.parentElement || document.body).insertAdjacentElement("afterend", riga);
  }

  // --------------------------------------------------------------------
  // 4. avvio
  // --------------------------------------------------------------------
  if (dati.hls === "1") montaHls(dati.flusso);
  else video.src = dati.flusso;

  if (audio) {
    audio.src = dati.audio;
    allinea();
  }

  const torna = document.getElementById("torna-in-diretta");
  if (torna) {
    torna.addEventListener("click", () => {
      // in diretta «la fine» si muove: si va dove arriva il buffer adesso
      const fine = video.seekable.length
        ? video.seekable.end(video.seekable.length - 1) : 0;
      if (fine) video.currentTime = fine - 1;
      video.play().catch(() => {});
    });
  }

  // --------------------------------------------------------------------
  // 5. riprendere, e ricordarsi dove si e' arrivati
  // --------------------------------------------------------------------
  /* La posizione va sul server e non nel browser di chi guarda: il punto deve
   * valere su tutti gli schermi. Si lascia a meta' sul computer e si riprende
   * dal tablet, che di cleanvid e' il telecomando. */
  if (dati.posizione) {
    const OGNI = 15000;

    const da = parseFloat(dati.riprendi || "0");
    if (da > 0) {
      // si aspetta che il video sappia quanto e' lungo: prima di allora
      // impostare currentTime non fa niente, in silenzio
      const vai = () => {
        video.currentTime = da;
        video.removeEventListener("loadedmetadata", vai);
      };
      if (video.readyState >= 1) vai();
      else video.addEventListener("loadedmetadata", vai);

      const ricomincia = document.getElementById("ricomincia");
      if (ricomincia) {
        ricomincia.addEventListener("click", () => {
          video.currentTime = 0;
          video.play().catch(() => {});
          const riga = document.getElementById("ripresa");
          if (riga) riga.remove();
        });
      }
    }

    let ultimo = 0;
    const salva = (chiudendo) => {
      if (!video.duration || !isFinite(video.duration)) return;   // diretta
      const corpo = new FormData();
      corpo.append("url", dati.pagina);
      corpo.append("secondi", video.currentTime.toFixed(1));
      corpo.append("durata", video.duration.toFixed(1));
      // sendBeacon e non fetch: parte anche mentre la pagina si chiude, che
      // e' esattamente il momento in cui serve di piu'. Con fetch il browser
      // annulla la richiesta a meta' e l'ultimo minuto guardato si perde.
      if (chiudendo && navigator.sendBeacon) {
        navigator.sendBeacon(dati.posizione, corpo);
      } else {
        fetch(dati.posizione, { method: "POST", body: corpo, keepalive: true })
          .catch(() => {});
      }
    };

    video.addEventListener("timeupdate", () => {
      const adesso = Date.now();
      if (adesso - ultimo < OGNI) return;
      ultimo = adesso;
      salva(false);
    });
    video.addEventListener("pause", () => salva(false));
    // `pagehide` e non `unload`: su iOS `unload` non scatta quasi mai
    window.addEventListener("pagehide", () => salva(true));
  }

  // --------------------------------------------------------------------
  // 6. saltare gli sponsor, e il piccolo schermo
  // --------------------------------------------------------------------
  /* I segmenti arrivano da SponsorBlock, segnalati a mano da chi guarda: lo
   * sponsor letto a voce, l'autopromozione, il «iscriviti al canale».
   * Si saltano, non si tagliano: in un flusso rimontato la barra del tempo
   * dice una cosa e il video un'altra. */
  const MARGINE = 0.3;              // si salta poco prima: il taglio si sente

  let salti = [];
  try { salti = JSON.parse(dati.salti || "[]"); } catch (e) {}

  if (salti.length) {
    let ultimoSaltato = -1;
    video.addEventListener("timeupdate", () => {
      const t = video.currentTime;
      for (let i = 0; i < salti.length; i++) {
        const [da, a] = salti[i];
        // se chi guarda e' tornato indietro apposta dentro il pezzo, non
        // glielo si porta via una seconda volta
        if (i === ultimoSaltato) continue;
        if (t >= da - MARGINE && t < a - 0.5) {
          ultimoSaltato = i;
          video.currentTime = a;
          return;
        }
      }
    });
    video.addEventListener("seeked", () => { ultimoSaltato = -1; });
  }

  const pip = document.getElementById("pip");
  if (pip && document.pictureInPictureEnabled && !video.disablePictureInPicture) {
    pip.hidden = false;
    pip.addEventListener("click", () => {
      if (document.pictureInPictureElement) {
        document.exitPictureInPicture().catch(() => {});
        return;
      }
      video.requestPictureInPicture().catch(() => {});
    });
  }
})();
