/* Le viste del lettore: normale, cinema, schermo intero.
 *
 * **Lo schermo intero e' quello nativo del video, non il nostro.** Mandare a
 * tutto schermo il riquadro che contiene il lettore sembra la stessa cosa e
 * non lo e': si porta dietro la nostra cornice, i nostri bordi e i nostri
 * comandi disegnati, e il risultato e' una pagina ingrandita invece di un
 * video a tutto schermo. Chiedendolo al `<video>` si ottiene quello del
 * browser - gli stessi comandi, gli stessi gesti, le stesse abitudini su
 * ogni sito - e su telefono anche la rotazione automatica.
 *
 * `T` passa al cinema, `F` va a tutto schermo: sono quelle di sempre, e non
 * si inventano tasti nuovi per una cosa che tutti fanno gia' allo stesso modo.
 */
(() => {
  "use strict";

  const CHIAVE = "cleanvid.vista";
  const teatro = document.getElementById("teatro");
  if (!teatro) return;

  const bottoni = document.querySelectorAll("[data-vista]");
  const video = () => document.getElementById("video");
  const telaio = () => document.getElementById("incorniciato");

  function segna(quale) {
    bottoni.forEach((b) => b.classList.toggle("on", b.dataset.vista === quale));
  }

  function aTuttoSchermo() {
    // il video, non il contenitore: si vuole il lettore del browser, non la
    // nostra pagina ingrandita
    const v = video() || telaio();
    if (!v) return;
    if (v.requestFullscreen) v.requestFullscreen().catch(() => {});
    else if (v.webkitEnterFullscreen) v.webkitEnterFullscreen();  // iPhone
  }

  function metti(quale, ricorda) {
    const cinema = quale === "cinema";
    teatro.classList.toggle("cinema", cinema);
    teatro.classList.toggle("normale", !cinema);
    segna(quale);
    if (ricorda) {
      try { localStorage.setItem(CHIAVE, quale); } catch (e) {}
    }
    window.dispatchEvent(new Event("resize"));
  }

  bottoni.forEach((b) => {
    b.addEventListener("click", () => {
      if (b.dataset.vista === "pieno") aTuttoSchermo();
      else metti(b.dataset.vista, true);
    });
  });

  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    // niente scorciatoie mentre si scrive, o si finisce a tutto schermo
    // digitando «f» in un campo
    const tag = ((e.target && e.target.tagName) || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return;
    const v = video();

    switch (e.key.toLowerCase()) {
      case "t":
        metti(teatro.classList.contains("cinema") ? "normale" : "cinema", true);
        break;
      case "f":
        if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
        else aTuttoSchermo();
        break;
      case "i":
        { const b = document.getElementById("pip"); if (b && !b.hidden) b.click(); }
        break;
      case "k":
      case " ":
        if (!v) return;
        e.preventDefault();          // la barra spaziatrice scorrerebbe la pagina
        v.paused ? v.play().catch(() => {}) : v.pause();
        break;
      case "m": {
        if (!v) return;
        // con le due tracce il suono esce dall'elemento audio: mutare il
        // video non farebbe niente
        const suono = document.getElementById("audio") || v;
        suono.muted = !suono.muted;
        break;
      }
      case "arrowleft":
        if (!v) return;
        e.preventDefault();
        v.currentTime = Math.max(0, v.currentTime - 5);
        break;
      case "arrowright":
        if (!v) return;
        e.preventDefault();
        v.currentTime += 5;
        break;
      default:
        break;
    }
  });

  /* Il cinema e' il predefinito: un video si guarda, e la colonna stretta di
     una pagina di testo non e' la forma giusta per guardarlo. Chi preferisce
     il contrario lo sceglie una volta e se lo ritrova. */
  let scelta = "cinema";
  try { scelta = localStorage.getItem(CHIAVE) || "cinema"; } catch (e) {}
  metti(scelta === "normale" ? "normale" : "cinema", false);
})();
