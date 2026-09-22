/* Il bagliore dietro al lettore, in cinema.
 *
 * Prende i colori dal fotogramma vero: si disegna il video dentro una tela
 * minuscola - 32 per 18 pixel - e poi la si lascia ingrandire e sfocare al
 * CSS. Non e' un trucco per risparmiare: e' **il** modo. Sfocare
 * un'immagine grande costa a ogni fotogramma, mentre ingrandire trentadue
 * pixel e' quello che una scheda video fa senza accorgersene, e il risultato
 * a occhio e' lo stesso - perche' dopo cinquanta pixel di sfocatura i
 * dettagli non ci sono comunque piu'.
 *
 * Quattro o cinque volte al secondo bastano: il bagliore deve accompagnare il
 * video, non inseguirlo. Piu' spesso si vedrebbe sfarfallare, e si pagherebbe
 * un lavoro in piu' per un effetto peggiore.
 *
 * Funziona solo con il lettore nostro. Dentro l'iframe di un'altra
 * piattaforma i fotogrammi non ci sono: e' un altro documento, e non c'e'
 * niente da disegnare.
 */
(() => {
  "use strict";

  const CHIAVE = "cleanvid.bagliore";
  const tela = document.getElementById("bagliore");
  const video = document.getElementById("video");
  const teatro = document.getElementById("teatro");
  if (!tela || !video || !teatro) return;

  const LARGO = 32, ALTO = 18;
  const OGNI = 220;                  // ms fra un fotogramma e l'altro
  tela.width = LARGO;
  tela.height = ALTO;
  const pennello = tela.getContext("2d", { alpha: false });
  if (!pennello) return;

  let acceso = true;          // la preferenza: lo vuole o no
  let haFotogramma = false;   // c'e' gia' qualcosa di disegnato sulla tela
  let battito = null;

  /* Il bagliore si vede solo se TUTTE e tre sono vere: lo vuole, c'e' un
   * fotogramma disegnato, e il video sta andando.
   *
   * Finche' il video non parte la tela e' nera, e una tela nera sfocata non
   * e' «niente»: e' un alone scuro che sul tema chiaro si vede benissimo e
   * sembra sporco. Quindi zero, proprio zero, finche' non c'e' qualcosa da
   * mostrare. */
  function rivedi() {
    const visibile = acceso && haFotogramma && !video.paused && !video.ended;
    teatro.classList.toggle("bagliore-acceso", visibile);
  }

  function disegna() {
    if (video.paused || video.readyState < 2) return;
    try {
      pennello.drawImage(video, 0, 0, LARGO, ALTO);
      haFotogramma = true;
      rivedi();
    } catch (e) {
      // un video di un'altra origine sporca la tela. A noi non serve
      // rileggerne i pixel, solo mostrarla, quindi va bene lo stesso - ma se
      // il browser si rifiuta del tutto, si smette invece di riprovare
      // quattro volte al secondo per sempre.
      metti("spento", false);
    }
  }

  function accendi() {
    acceso = true;
    teatro.classList.add("con-bagliore");
    if (battito === null) battito = setInterval(disegna, OGNI);
    disegna();
    rivedi();
  }

  function spegni() {
    acceso = false;
    rivedi();                 // prima sparisce, con la sua dissolvenza
    if (battito !== null) { clearInterval(battito); battito = null; }
    // `con-bagliore` si toglie DOPO: e' quella che leva la tela dalla pagina,
    // e toglierla subito farebbe sparire l'alone di scatto invece che piano
    setTimeout(() => {
      if (!acceso) teatro.classList.remove("con-bagliore");
    }, 650);
  }

  function metti(stato, ricorda) {
    stato === "spento" ? spegni() : accendi();
    document.querySelectorAll("[data-bagliore]").forEach((b) =>
      b.classList.toggle("on", (b.dataset.bagliore === "spento") === !acceso));
    if (ricorda) {
      try { localStorage.setItem(CHIAVE, acceso ? "acceso" : "spento"); }
      catch (e) {}
    }
  }

  /* Il video dice quando c'e' qualcosa da illuminare. `playing` e non `play`:
     il primo vuol dire che sta davvero andando, il secondo solo che glielo
     hanno chiesto - e fra i due, su una diretta, possono passare secondi di
     schermo nero. */
  video.addEventListener("playing", () => { disegna(); rivedi(); });
  video.addEventListener("pause", rivedi);
  video.addEventListener("ended", rivedi);
  video.addEventListener("emptied", () => { haFotogramma = false; rivedi(); });
  video.addEventListener("seeking", disegna);

  document.querySelectorAll("[data-bagliore]").forEach((b) => {
    b.addEventListener("click", () => {
      metti(b.dataset.bagliore, true);
      const pannello = b.closest("details");
      if (pannello) pannello.open = false;
    });
  });

  /* Quando la scheda non si vede il battito si ferma: disegnare fotogrammi
     per una pagina che nessuno sta guardando e' lavoro buttato, e su un
     portatile e' batteria. */
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) { if (battito !== null) { clearInterval(battito); battito = null; } }
    else if (acceso && battito === null) battito = setInterval(disegna, OGNI);
  });

  let scelta = "acceso";
  try { scelta = localStorage.getItem(CHIAVE) || "acceso"; } catch (e) {}
  // chi ha chiesto meno movimento non se lo trova acceso di sua iniziativa
  if (matchMedia("(prefers-reduced-motion: reduce)").matches &&
      localStorage.getItem(CHIAVE) === null) scelta = "spento";
  metti(scelta, false);
})();
