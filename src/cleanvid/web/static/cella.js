/* Un riquadro del muro, visto da dentro.
 *
 * Il muro sta nella pagina che ci contiene e non puo' toccare il nostro
 * `<video>`: e' un altro documento. Questo file espone `window.cellApi`, che
 * e' il filo con cui il muro comanda questo riquadro - audio, pausa, salto,
 * ricarica - e l'unico punto in cui i due si parlano.
 *
 * Perche' un filo esplicito e non i comandi nativi del browser: dentro un
 * riquadro piccolo Chrome toglie da solo il volume e lo schermo intero, e su
 * una diretta mostra una durata che non vuol dire niente. Allora il riquadro
 * si tiene i suoi comandi, disegnati dal muro, e questi metodi glieli fanno
 * arrivare qui dentro.
 */
(() => {
  "use strict";

  const video = () => document.getElementById("video");
  const audio = () => document.getElementById("audio");
  const telaio = () => document.getElementById("incorniciato");

  /* Con le due tracce separate il suono esce dall'elemento audio e il video
     resta muto per forza: toccare il volume del video non farebbe niente, e
     accenderlo darebbe un'eco. */
  const suono = () => audio() || video();

  const diretta = () => document.body.dataset.diretta === "1";

  window.cellApi = {
    attiva() {
      const s = suono();
      if (s) {
        // iOS accetta l'accensione dell'audio solo dentro il gesto di chi
        // tocca, e vuole che la riproduzione riparta nello stesso momento
        s.muted = false;
        s.volume = 1;
        const p = s.play();
        if (p && p.catch) p.catch(() => {});
        const v = video();
        if (v && v !== s) v.play().catch(() => {});
        return true;
      }
      return this._aYouTube("unMute");
    },
    silenzia() {
      const s = suono();
      if (s) { s.muted = true; return true; }
      return this._aYouTube("mute");
    },
    _aYouTube(comando) {
      /* Lettore incorporato: l'unico comando che passa e' quello a messaggi,
       * e passa solo se l'indirizzo ha `enablejsapi=1` - altrimenti YouTube
       * lo ignora senza dire niente. Quel parametro lo mette `media/embed.py`.
       *
       * Si riprova qualche volta perche' il lettore non ascolta finche' non
       * e' pronto, e «pronto» arriva quando arriva: un comando mandato un
       * decimo di secondo troppo presto si perde, e l'audio resta spento
       * senza che nessuno capisca perche'.
       */
      const f = telaio();
      if (!f || !/youtube/.test(f.src)) return false;
      this._muto = comando === "mute";
      let giro = 0;
      const manda = () => {
        try {
          f.contentWindow.postMessage(JSON.stringify(
            { event: "command", func: comando, args: [] }),
            "https://www.youtube.com");
        } catch (e) {}
        // se nel frattempo il muro ha cambiato idea, si smette
        if (++giro < 6 && this._muto === (comando === "mute")) {
          setTimeout(manda, 250 * giro);
        }
      };
      manda();
      return true;
    },
    comandi(mostra) {
      const v = video();
      if (v) { v.controls = !!mostra; return true; }
      return false;
    },
    comandabile() {
      return !!video() || !!(telaio() && /youtube/.test(telaio().src));
    },
    titolo() { return (document.title || "").split(" · ")[0]; },
    inDiretta() { return diretta(); },
    alterna() {
      const v = video();
      if (!v) return false;
      v.paused ? v.play().catch(() => {}) : v.pause();
      return true;
    },
    volume(x) {
      const s = suono();
      if (!s) return false;
      s.volume = Math.max(0, Math.min(1, x));
      s.muted = s.volume === 0;
      return true;
    },
    cerca(secondi) {
      const v = video();
      if (!v) return false;
      v.currentTime = secondi;
      return true;
    },
    alBordo() {
      const v = video();
      if (!v || !v.seekable.length) return false;
      v.currentTime = v.seekable.end(v.seekable.length - 1) - 1;
      v.play().catch(() => {});
      return true;
    },
    ricarica() { location.reload(); return true; },
    schermoIntero() {
      const v = video();
      if (v && v.requestFullscreen) { v.requestFullscreen().catch(() => {}); return true; }
      return false;
    },
    /* La chat della diretta, quando la piattaforma ne ha una.
     *
     * Si accende su richiesta e non da sola: in un muro da quattro, quattro
     * chat sempre aperte sono quattro connessioni che nessuno sta leggendo.
     * E l'`src` si scrive alla prima accensione, non prima. */
    haChat() { return !!document.getElementById("chat"); },
    chat(mostra) {
      const c = document.getElementById("chat");
      if (!c) return false;
      const dentro = c.querySelector("iframe");
      if (mostra && !dentro.src) dentro.src = c.dataset.chat;
      document.body.classList.toggle("conchat", !!mostra);
      return true;
    },
    chatAccesa() { return document.body.classList.contains("conchat"); },
    /* Dove sta la chat: «destra» o «sotto». Di fianco e' il predefinito
       perche' sotto mangia l'altezza, e in un muro da quattro l'altezza e'
       la cosa che manca. */
    chatDove(dove) {
      document.body.classList.toggle("chat-sotto", dove === "sotto");
      return true;
    },

    stato() {
      const v = video();
      if (!v) return null;
      const s = suono();
      return {
        pausa: v.paused,
        volume: s ? s.volume : 1,
        muto: s ? s.muted : true,
        tempo: v.currentTime || 0,
        durata: isFinite(v.duration) ? v.duration : 0,
        live: diretta(),
      };
    },
  };

  /* Chi tocca un riquadro vuole il suo audio. Lo dice al muro, che lo toglie
     agli altri: quattro video che suonano insieme non si ascoltano, si
     sopportano. */
  document.addEventListener("pointerdown", () => {
    try { parent.postMessage({ cleanvid: "fuoco" }, location.origin); }
    catch (e) {}
  });
})();
