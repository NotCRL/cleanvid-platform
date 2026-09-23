/* La stanza: restare allo stesso secondo, senza singhiozzare.
 *
 * L'idea che tiene in piedi tutto: **nessuno insegue nessuno.** Chi comanda
 * non manda «vai al secondo 42»: manda «al mio orologio T io ero al 42 e
 * stavo andando». Ogni ospite calcola da solo dove dovrebbe essere adesso, e
 * ci arriva.
 *
 * Perché non basta mandare la posizione: fra il momento in cui la si legge e
 * quello in cui arriva passano centinaia di millisecondi, e un video in corsa
 * in quel tempo si è già mosso. Un numero senza il suo istante nasce vecchio.
 *
 * E gli orologi dei partecipanti sono sbagliati, ognuno a modo suo: il
 * telefono di uno va avanti di tre secondi, il portatile di un altro
 * indietro di dieci. Quindi non si usano. Si misura una volta sola quanto il
 * proprio è sbagliato rispetto a quello del server, e poi si ragiona sempre
 * nel tempo del server.
 *
 * La correzione è la stessa già imparata per le due tracce audio e video:
 * **se lo scarto è piccolo si cambia impercettibilmente la velocità finché
 * rientra, e si salta solo quando un salto si sente meno di uno sfasamento.**
 * Un sistema che salta a ogni messaggio singhiozza, e chi guarda in compagnia
 * nota il singhiozzo molto più di mezzo secondo di ritardo.
 */
(() => {
  "use strict";

  const dati = document.getElementById("stanza");
  if (!dati) return;
  const S = dati.dataset;

  // le soglie arrivano dal server: stanno in rooms/protocol.py, in un posto
  // solo, perché si regolano con gli occhi su uno schermo vero
  const SALTO = parseFloat(S.scartoSalto);
  const OK = parseFloat(S.scartoOk);
  const CORREZIONE = parseFloat(S.correzioneMax);
  const BATTITO = parseFloat(S.battitoOgni) * 1000;

  const comando = S.comanda === "1";
  const video = () => document.getElementById("video");

  let filo = null;
  let scartoOrologi = 0;      // quanto il mio orologio è avanti sul server
  let ultimoStato = null;
  let riconnessioni = 0;

  const adessoServer = () => Date.now() / 1000 - scartoOrologi;

  function manda(tipo, corpo) {
    if (!filo || filo.readyState !== WebSocket.OPEN) return;
    filo.send(JSON.stringify({ tipo, dati: corpo || {} }));
  }

  /* --- quanto è sbagliato il mio orologio ---------------------------------
     Si manda il proprio istante, torna indietro insieme a quello del server.
     Metà del giro d'andata e ritorno è la stima del viaggio in una direzione:
     è approssimata, ma l'errore che resta è molto più piccolo di quello che
     si vuole correggere. */
  function misuraOrologio() {
    manda("ping", { tuo: Date.now() / 1000 });
  }

  function rispostaPing(messaggio) {
    const tuo = messaggio.dati && messaggio.dati.tuo;
    if (!tuo) return;
    const adesso = Date.now() / 1000;
    const viaggio = (adesso - tuo) / 2;
    const stima = adesso - (messaggio.t_server + viaggio);
    // la prima misura si prende com'è, le successive si mediano: una
    // singola misura presa in un momento sfortunato può essere molto sbagliata
    scartoOrologi = scartoOrologi === 0 ? stima : scartoOrologi * 0.7 + stima * 0.3;
  }

  /* --- dove dovrei essere ------------------------------------------------ */
  function prevista(stato) {
    if (!stato.in_corsa) return stato.posizione;
    const passato = Math.max(0, adessoServer() - stato.t_server);
    return stato.posizione + passato * (stato.velocita || 1);
  }

  function allinea() {
    const v = video();
    if (!v || !ultimoStato || comando) return;
    if (v.readyState < 2) return;

    const dove = prevista(ultimoStato);
    const scarto = dove - v.currentTime;

    if (ultimoStato.in_corsa && v.paused) v.play().catch(() => {});
    if (!ultimoStato.in_corsa && !v.paused) v.pause();

    if (Math.abs(scarto) > SALTO) {
      // troppo lontani: un salto si sente meno di un inseguimento infinito
      v.currentTime = dove;
      v.playbackRate = 1;
      return;
    }
    if (Math.abs(scarto) < OK) {
      v.playbackRate = 1;         // già allineati: non si tocca niente
      return;
    }
    // si insegue cambiando velocità di poco, e si rientra da soli
    const spinta = Math.max(-CORREZIONE, Math.min(CORREZIONE, scarto));
    v.playbackRate = 1 + spinta;
  }

  /* --- chi comanda racconta dov'è ---------------------------------------- */
  function racconta(tipo) {
    const v = video();
    if (!v || !comando) return;
    manda(tipo, {
      url: S.url || "",
      titolo: S.titolo || "",
      posizione: v.currentTime || 0,
      in_corsa: !v.paused && !v.ended,
      velocita: v.playbackRate || 1,
    });
  }

  /* --- il filo ------------------------------------------------------------
     Si riconnette da solo, aspettando sempre un po' di più: una rete che cade
     torna quasi sempre, ma insistere ogni cento millisecondi non la fa
     tornare prima - fa solo scaldare il telefono. */
  function collega() {
    const dove = (location.protocol === "https:" ? "wss://" : "ws://")
      + location.host + S.filo;
    filo = new WebSocket(dove);

    filo.onopen = () => {
      riconnessioni = 0;
      segnala(true);
      misuraOrologio();
      setTimeout(misuraOrologio, 1500);
      if (comando) racconta("battito");
    };

    filo.onmessage = (e) => {
      let messaggio;
      try { messaggio = JSON.parse(e.data); } catch (err) { return; }
      switch (messaggio.tipo) {
        case "pong": rispostaPing(messaggio); break;
        case "stato":
          ultimoStato = messaggio.dati;
          if (!comando) cambiaVideoSeServe(messaggio.dati);
          allinea();
          break;
        case "elenco": disegnaPresenti(messaggio.dati.persone || []); break;
        default: break;
      }
    };

    filo.onclose = () => {
      segnala(false);
      riconnessioni += 1;
      setTimeout(collega, Math.min(20000, 800 * riconnessioni));
    };
  }

  /* Chi comanda cambia video: gli ospiti devono seguire, e l'unico modo è
     ricaricare la pagina su quell'indirizzo - il lettore va rifatto da capo,
     perché il flusso è un altro. */
  function cambiaVideoSeServe(stato) {
    if (!stato.url || stato.url === S.url) return;
    location.href = S.qui + "?u=" + encodeURIComponent(stato.url);
  }

  function segnala(collegato) {
    const spia = document.getElementById("spia");
    if (spia) spia.classList.toggle("giu", !collegato);
  }

  function disegnaPresenti(persone) {
    const dove = document.getElementById("presenti");
    if (!dove) return;
    dove.innerHTML = "";
    persone.forEach((p) => {
      const li = document.createElement("li");
      li.textContent = p.nome;
      if (p.comanda) li.className = "comanda";
      dove.appendChild(li);
    });
    const conta = document.getElementById("quanti");
    if (conta) conta.textContent = String(persone.length);
  }

  /* --- avvio -------------------------------------------------------------- */
  collega();
  setInterval(misuraOrologio, 30000);

  const v = video();
  if (v) {
    if (comando) {
      // chi comanda racconta a ogni gesto, e poi ogni tanto: i gesti dicono
      // «è successo qualcosa», il battito dice «siamo ancora qui»
      ["play", "pause", "seeked", "ratechange"].forEach((evento) =>
        v.addEventListener(evento, () => racconta("comanda")));
      setInterval(() => racconta("battito"), BATTITO);
    } else {
      // gli ospiti si riallineano spesso, ma con una correzione minuscola:
      // è quello che rende il movimento invisibile
      setInterval(allinea, 1000);
      v.addEventListener("playing", allinea);
      // e se un ospite mette in pausa, la stanza non lo aspetta: al
      // riallineamento successivo torna dov'è la stanza
      v.addEventListener("seeked", () => setTimeout(allinea, 300));
    }
  }
})();
