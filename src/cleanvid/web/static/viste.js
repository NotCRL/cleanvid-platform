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
 * `T` passa al cinema. Per lo schermo intero non c'e' una scorciatoia: quel
 * bottone ce l'ha gia' il lettore del browser, ed e' li' che la gente lo
 * cerca. Le scorciatoie che restano sono quelle che riguardano la pagina, non
 * quelle che il lettore sa fare da se'.
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
    teatro.classList.toggle("normale", quale === "normale");
    teatro.classList.toggle("cinema", quale === "cinema");
    teatro.classList.toggle("solo", quale === "solo");
    // la pagina sotto non deve scorrere mentre il lettore se la prende tutta
    document.body.classList.toggle("vista-solo", quale === "solo");
    segna(quale);
    if (ricorda) {
      try { localStorage.setItem(CHIAVE, quale); } catch (e) {}
    }
    window.dispatchEvent(new Event("resize"));
  }

  function precedente() {
    // da «solo il lettore» si torna dove si era, non in un posto a caso
    try { return localStorage.getItem(CHIAVE + ".prima") || "cinema"; }
    catch (e) { return "cinema"; }
  }

  bottoni.forEach((b) => {
    b.addEventListener("click", () => {
      if (b.dataset.vista === "solo" && !teatro.classList.contains("solo")) {
        try {
          localStorage.setItem(CHIAVE + ".prima",
            teatro.classList.contains("normale") ? "normale" : "cinema");
        } catch (e) {}
      }
      metti(b.dataset.vista, true);
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
        if (teatro.classList.contains("solo")) break;   // li' non vuol dire niente
        metti(teatro.classList.contains("cinema") ? "normale" : "cinema", true);
        break;
      case "escape":
        if (teatro.classList.contains("solo")) metti(precedente(), true);
        break;
      /* Niente scorciatoia per lo schermo intero, ed e' una scelta: il
         lettore del browser ce l'ha gia' il suo bottone, e una `f` che
         spalanca lo schermo mentre si sta facendo altro sorprende invece di
         aiutare. `T` resta perche' cambia la forma della pagina, che un
         bottone del lettore non puo' fare. */
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

  /* Dove sta la chat: di fianco al video, alla sua stessa altezza, oppure
   * sotto.
   *
   * Di fianco e' il predefinito perche' e' quello che fa una diretta: si
   * guarda e si legge insieme, e mettere la chat sotto vuol dire scorrere
   * avanti e indietro fra due cose che succedono nello stesso momento.
   *
   * Sotto ha senso su uno schermo stretto o quando il video conta piu' della
   * chat, e allora e' una scelta - che si ricorda. */
  const CHIAVE_CHAT = "cleanvid.chat";

  function chatDove(dove, ricorda) {
    const fianco = dove !== "sotto";
    teatro.classList.toggle("chat-fianco", fianco);
    teatro.classList.toggle("chat-sotto", !fianco);
    document.querySelectorAll("[data-chatdove]").forEach((b) =>
      b.classList.toggle("on", (b.dataset.chatdove === "sotto") === !fianco));
    if (ricorda) {
      try { localStorage.setItem(CHIAVE_CHAT, fianco ? "fianco" : "sotto"); }
      catch (e) {}
    }
    window.dispatchEvent(new Event("resize"));
  }

  document.querySelectorAll("[data-chatdove]").forEach((b) => {
    b.addEventListener("click", () => {
      chatDove(b.dataset.chatdove, true);
      // il pannello si chiude da solo: la scelta e' fatta
      const aperto = b.closest("details");
      if (aperto) aperto.open = false;
    });
  });

  const esci = document.getElementById("esci-solo");
  if (esci) esci.addEventListener("click", () => metti(precedente(), true));

  try { chatDove(localStorage.getItem(CHIAVE_CHAT) || "fianco", false); }
  catch (e) { chatDove("fianco", false); }

  /* Il cinema e' il predefinito: un video si guarda, e la colonna stretta di
     una pagina di testo non e' la forma giusta per guardarlo. Chi preferisce
     il contrario lo sceglie una volta e se lo ritrova. */
  let scelta = "cinema";
  try { scelta = localStorage.getItem(CHIAVE) || "cinema"; } catch (e) {}
  if (!["normale", "cinema", "solo"].includes(scelta)) scelta = "cinema";
  metti(scelta, false);
})();
