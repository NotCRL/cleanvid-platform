/* L'interruttore chiaro/scuro.
 *
 * Va applicato PRIMA che si disegni qualcosa, altrimenti si vede la pagina
 * cambiare colore sotto gli occhi a ogni caricamento. Per questo questo file
 * si carica nella testa e senza `defer`: e' l'unico punto del sito dove
 * bloccare il disegno e' la cosa giusta.
 *
 * Senza una scelta salvata comanda il sistema. La scelta sta nel browser di
 * chi guarda e non sul server: e' una preferenza del singolo schermo - lo
 * stesso utente puo' volere scuro sul portatile la sera e chiaro sul tablet
 * di giorno - e mandarla al server vorrebbe dire una richiesta in piu' per
 * sapere di che colore disegnare.
 */
(() => {
  "use strict";
  try {
    const t = localStorage.getItem("cleanvid.tema");
    if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
  } catch (e) { /* finestra privata, o cookie bloccati: comanda il sistema */ }

  window.cambiaTema = () => {
    const el = document.documentElement;
    const sistemaChiaro = matchMedia("(prefers-color-scheme: light)").matches;
    const oraChiaro = el.dataset.theme
      ? el.dataset.theme === "light" : sistemaChiaro;
    const nuovo = oraChiaro ? "dark" : "light";
    el.dataset.theme = nuovo;
    try { localStorage.setItem("cleanvid.tema", nuovo); } catch (e) {}
    const meta = document.querySelector("meta[name=theme-color]");
    if (meta) meta.content = nuovo === "light" ? "#f4f4f1" : "#0a0a0a";
  };
})();
