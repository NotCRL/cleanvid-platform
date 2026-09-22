/* Il lettore: un file solo, due tracce da tenere allineate, o un flusso HLS.
 *
 * La parte che merita di essere letta e' l'allineamento fra video e audio.
 * Quasi nessun sito serve piu' un file unico: danno un video muto e un audio
 * a parte. Cucirli sul server costa un processo per spettatore; il browser
 * invece sa suonarli tutti e due, uno per elemento, e l'unico lavoro che
 * resta e' impedire che si separino.
 *
 * Le due soglie qui sotto sono state trovate guardando uno schermo, non a
 * tavolino, e sono la ragione per cui questo non singhiozza:
 *
 *  - sotto mezzo secondo di scarto NON si salta. Si cambia impercettibilmente
 *    la velocita' dell'audio finche' rientra. Un salto si sente molto piu'
 *    di un ritardo che si chiude da solo.
 *  - non piu' di un salto al secondo. Senza questo, un video che fatica a
 *    partire entra in un ciclo di salti e non ne esce.
 */
(function () {
  "use strict";

  const SCARTO_MASSIMO = 0.5;     // oltre questo, saltare costa meno che inseguire
  const CORREZIONE = 0.06;        // 6%: sopra si sente, sotto non recupera mai
  const PAUSA_FRA_SALTI = 1000;   // ms

  function allinea(video, audio) {
    let ultimoSalto = 0;

    // l'audio segue il video e mai il contrario: il video e' quello che si
    // vede, e un fotogramma che torna indietro si nota subito
    video.addEventListener("play", () => audio.play().catch(() => {}));
    video.addEventListener("pause", () => audio.pause());
    video.addEventListener("seeking", () => { audio.currentTime = video.currentTime; });
    video.addEventListener("ratechange", () => { audio.playbackRate = video.playbackRate; });
    video.addEventListener("volumechange", () => {
      audio.volume = video.volume;
      audio.muted = video.muted;
    });

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
      // scarto piccolo: si recupera cambiando velocita', senza che si senta
      const spinta = Math.max(-CORREZIONE, Math.min(CORREZIONE, scarto));
      audio.playbackRate = video.playbackRate * (1 + spinta);
    });

    // il video e' muto per forza: l'audio esce dall'altro elemento, e due
    // tracce audio insieme sarebbero un'eco
    video.muted = true;
  }

  function montaHls(video, indirizzo) {
    // Safari e iOS suonano l'HLS da soli e meglio di qualunque libreria:
    // usare hls.js anche li' vorrebbe dire rinunciare al decoder hardware.
    if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = indirizzo;
      return;
    }
    if (typeof Hls === "undefined" || !Hls.isSupported()) {
      video.insertAdjacentHTML("afterend",
        "<p class=avviso>Questo browser non sa suonare questo flusso.</p>");
      return;
    }
    const hls = new Hls({
      // in diretta si parte dal bordo, non da dove comincia il buffer:
      // altrimenti si guarda con mezzo minuto di ritardo senza sapere perche'
      liveSyncDurationCount: 3,
    });
    hls.loadSource(indirizzo);
    hls.attachMedia(video);
    hls.on(Hls.Events.ERROR, (_, guaio) => {
      if (!guaio.fatal) return;
      // un errore di rete in diretta e' normale (un segmento che non c'e'
      // ancora): si riprova invece di arrendersi
      if (guaio.type === Hls.ErrorTypes.NETWORK_ERROR) hls.startLoad();
      else if (guaio.type === Hls.ErrorTypes.MEDIA_ERROR) hls.recoverMediaError();
      else hls.destroy();
    });
    video.hls = hls;
  }

  document.addEventListener("DOMContentLoaded", () => {
    const video = document.getElementById("video");
    if (!video) return;
    const dati = video.dataset;

    if (dati.hls === "1") montaHls(video, dati.flusso);
    else video.src = dati.flusso;

    const audio = document.getElementById("audio");
    if (audio) {
      audio.src = dati.audio;
      allinea(video, audio);
    }

    const torna = document.getElementById("torna-in-diretta");
    if (torna) {
      torna.addEventListener("click", () => {
        // in diretta "la fine" si muove: si va dove arriva il buffer adesso
        const fine = video.seekable.length
          ? video.seekable.end(video.seekable.length - 1) : 0;
        if (fine) video.currentTime = fine - 1;
        video.play().catch(() => {});
      });
    }
  });
})();
