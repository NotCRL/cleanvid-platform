/* Le copertine arrivano quando sono pronte, e nel frattempo non si aspetta.
 *
 * Il server risponde subito no se non ce l'ha ancora, e intanto la cerca in
 * disparte: cercarla puo' costare venticinque secondi di yt-dlp, e con venti
 * voci in elenco vorrebbe dire una home che non si apre. Qui si riprova
 * qualche volta, con attese via via piu' lunghe, e poi ci si tiene il
 * riquadro colorato con le iniziali - che e' gia' una risposta.
 *
 * Si caricano solo quando entrano nello schermo: con trenta schede in pagina,
 * partire tutte insieme significa trenta richieste prima che si veda niente.
 */
(() => {
  "use strict";

  const TENTATIVI = 4;
  const gia = new WeakSet();

  const prova = (img, giro) => {
    const dove = img.dataset.copertina;
    if (!dove) return;
    const finta = new Image();
    finta.onload = () => {
      img.src = finta.src;
      img.classList.add("pronta");   // il CSS nasconde le iniziali sotto
    };
    finta.onerror = () => {
      if (giro < TENTATIVI) setTimeout(() => prova(img, giro + 1), 900 * giro + 700);
    };
    // il giro finisce nell'indirizzo per non farsi servire dalla cache il no
    // di un attimo prima
    finta.src = dove + "&r=" + giro;
  };

  const guarda = (img) => {
    if (gia.has(img)) return;
    gia.add(img);
    prova(img, 1);
  };

  document.addEventListener("DOMContentLoaded", () => {
    const immagini = document.querySelectorAll("img[data-copertina]");
    if (!("IntersectionObserver" in window)) {
      immagini.forEach(guarda);
      return;
    }
    const osservatore = new IntersectionObserver((voci) => {
      voci.forEach((v) => {
        if (!v.isIntersecting) return;
        osservatore.unobserve(v.target);
        guarda(v.target);
      });
    }, { rootMargin: "300px" });   // un po' prima che si vedano, non dopo
    immagini.forEach((i) => osservatore.observe(i));
  });
})();
