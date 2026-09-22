/* Le tre viste del lettore: normale, cinema, schermo intero.
 *
 * Sono le stesse tre che trova chiunque abbia usato un sito di video, con le
 * stesse scorciatoie: **T** per il cinema, **F** per lo schermo intero. Non
 * si inventano tasti nuovi per una cosa che tutti fanno gia' allo stesso
 * modo: una scorciatoia diversa dalle altre non si impara, si sbaglia.
 *
 * La scelta si ricorda, ma solo fra normale e cinema. Lo schermo intero no,
 * di proposito: una pagina che si apre da sola a tutto schermo e' una pagina
 * che ha preso il controllo dello schermo senza che nessuno glielo chiedesse,
 * e i browser stessi non lo permettono fuori da un gesto.
 */
(() => {
  "use strict";

  const CHIAVE = "cleanvid.vista";
  const teatro = document.getElementById("teatro");
  if (!teatro) return;

  const bottoni = document.querySelectorAll("[data-vista]");
  const video = () => document.getElementById("video");

  function segna(quale) {
    bottoni.forEach((b) => b.classList.toggle("on", b.dataset.vista === quale));
  }

  function metti(quale, ricorda) {
    if (quale === "pieno") {
      // il vero schermo intero, non una finta a tutta pagina: cosi' sparisce
      // anche la barra del browser, e su un portatile sono due centimetri
      const dove = teatro.requestFullscreen ? teatro : video();
      if (dove && dove.requestFullscreen) dove.requestFullscreen().catch(() => {});
      return;                      // la vista sotto resta quella di prima
    }
    teatro.classList.toggle("cinema", quale === "cinema");
    teatro.classList.toggle("normale", quale !== "cinema");
    segna(quale);
    if (ricorda) {
      try { localStorage.setItem(CHIAVE, quale); } catch (e) {}
    }
    // le maniglie del video cambiano posto quando cambia la larghezza
    window.dispatchEvent(new Event("resize"));
  }

  bottoni.forEach((b) => {
    b.addEventListener("click", () => metti(b.dataset.vista, true));
  });

  document.addEventListener("fullscreenchange", () => {
    const dentro = !!document.fullscreenElement;
    teatro.classList.toggle("a-pieno-schermo", dentro);
    if (!dentro) segna(teatro.classList.contains("cinema") ? "cinema" : "normale");
    else segna("pieno");
  });

  /* Le scorciatoie. Non scattano mentre si scrive in un campo, o si finirebbe
     a schermo intero digitando «f» nel campo di ricerca. */
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const tag = ((e.target && e.target.tagName) || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return;
    const v = video();

    switch (e.key.toLowerCase()) {
      case "t":
        metti(teatro.classList.contains("cinema") ? "normale" : "cinema", true);
        break;
      case "f":
        if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
        else metti("pieno", false);
        break;
      case "escape":
        if (!document.fullscreenElement && teatro.classList.contains("cinema"))
          metti("normale", true);
        break;
      case "k":
      case " ":
        if (!v) return;
        e.preventDefault();        // la barra spaziatrice scorrerebbe la pagina
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

  try {
    if (localStorage.getItem(CHIAVE) === "cinema") metti("cinema", false);
  } catch (e) {}
})();
