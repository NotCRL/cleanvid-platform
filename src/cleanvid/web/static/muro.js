/* Il muro: da uno a quattro video insieme.
 *
 * Arriva dal cleanvid a file unico, e porta con se' i vincoli che ci sono
 * costati tempo. Quelli vanno letti prima di toccare qualcosa:
 *
 * 1. **Non si ricostruisce mai il muro.** Aggiungere un riquadro rifacendo la
 *    griglia fa ripartire da capo tutti i video che stavano suonando. Ogni
 *    operazione tocca una cella sola: `creaCella` ne aggiunge una, `togli` ne
 *    rimuove una, e le altre non se ne accorgono.
 * 2. **I riquadri non si spostano mai nel DOM.** Spostare un `<iframe>` lo
 *    ricarica. Cambia solo la proprieta' `order`, che la griglia rispetta:
 *    il video non se ne accorge nemmeno.
 * 3. **Il movimento e' fatto con la tecnica FLIP**: si misura dov'erano, si
 *    cambia l'ordine, si misura dove sono finiti, si rimettono al punto di
 *    partenza con una trasformazione e si lasciano andare. Il browser anima
 *    solo `transform`, quindi scorre liscio anche con quattro video accesi.
 * 4. **La qualita' e' parte dell'indirizzo del riquadro.** Cambiarla vuol dire
 *    ricaricare quel riquadro, e un solo posto costruisce quell'indirizzo.
 *
 * Quello che il muro sa di se' sta nel `localStorage`: disposizione, misure,
 * quali video. Cambia dieci volte al minuto mentre si sistemano le finestre, e
 * mandarlo al server a ogni movimento sarebbe una richiesta per ogni pixel.
 * Al server va solo cio' che deve sopravvivere alla scheda chiusa: i gruppi.
 */
(() => {
  "use strict";

  const M = window.MURO || {};
  const T = (chiave) => (window.TESTI && window.TESTI[chiave]) || chiave;

  const wrap = document.getElementById("gridwrap");
  const grid = document.getElementById("grid");
  const form = document.getElementById("addform");
  const field = document.getElementById("addurl");
  const muro = document.getElementById("wall");
  const CHIAVE = "cleanvid.muro";

  let celle = [];            // {id, url, title, q, zitto, battito}
  let audioAcceso = null;    // l'id del riquadro che suona: uno solo
  let disposizione = "griglia";
  let nCol = 2;
  let leggero = false;
  let fracCol = [], fracRig = [];

  /* ---------- memoria ---------- */
  const salva = () => {
    try {
      localStorage.setItem(CHIAVE, JSON.stringify({
        // il battito resta fuori: e' un timer, non un dato
        celle: celle.map((c) => ({ url: c.url, title: c.title,
                                   zitto: !!c.zitto, q: c.q || "" })),
        disposizione, nCol, fracCol, fracRig,
      }));
    } catch (e) {}
  };
  const ripristina = () => {
    try { return JSON.parse(localStorage.getItem(CHIAVE) || "null"); }
    catch (e) { return null; }
  };

  /* ---------- disposizione ---------- */
  function colonneEffettive() {
    if (disposizione === "riga") return Math.max(1, celle.length);
    if (disposizione === "colonna") return 1;
    return Math.min(nCol, Math.max(1, celle.length));
  }

  function applicaGriglia(azzera) {
    const nc = colonneEffettive();
    const nr = Math.max(1, Math.ceil(celle.length / nc));
    if (azzera || fracCol.length !== nc) fracCol = Array(nc).fill(1);
    if (azzera || fracRig.length !== nr) fracRig = Array(nr).fill(1);
    grid.style.gridTemplateColumns = fracCol.map((f) => f.toFixed(4) + "fr").join(" ");
    grid.style.gridTemplateRows = fracRig.map((f) => f.toFixed(4) + "fr").join(" ");
    requestAnimationFrame(posizionaManici);
    salva();
  }

  /* ---------- maniglie fra un riquadro e l'altro ---------- */
  function posizionaManici() {
    wrap.querySelectorAll(".manico").forEach((m) => m.remove());
    if (celle.length < 2) return;
    const stile = getComputedStyle(grid);
    const vuoto = parseFloat(stile.gap) || 8;
    const larghezze = stile.gridTemplateColumns.split(" ").map(parseFloat);
    const altezze = stile.gridTemplateRows.split(" ").map(parseFloat);

    let x = 0;
    for (let i = 0; i < larghezze.length - 1; i++) {
      x += larghezze[i] + vuoto;
      crea("col", i, x - vuoto / 2, null);
    }
    let y = 0;
    for (let i = 0; i < altezze.length - 1; i++) {
      y += altezze[i] + vuoto;
      crea("rig", i, null, y - vuoto / 2);
    }

    function crea(tipo, indice, px, py) {
      const m = document.createElement("div");
      m.className = "manico " + tipo;
      if (tipo === "col") m.style.left = px + "px";
      else m.style.top = py + "px";
      m.addEventListener("pointerdown", (ev) => avviaTrascino(ev, tipo, indice));
      wrap.appendChild(m);
    }
  }

  function avviaTrascino(ev, tipo, indice) {
    ev.preventDefault();
    const box = grid.getBoundingClientRect();
    const frazioni = tipo === "col" ? fracCol : fracRig;
    const totale = frazioni.reduce((a, b) => a + b, 0);
    const misura = tipo === "col" ? box.width : box.height;
    const partenza = tipo === "col" ? ev.clientX : ev.clientY;
    const primaA = frazioni[indice], primaB = frazioni[indice + 1];
    document.body.classList.add(tipo === "col" ? "trascina-col" : "trascina-rig");

    const muovi = (e) => {
      const delta = (tipo === "col" ? e.clientX : e.clientY) - partenza;
      const dFraz = (delta / misura) * totale;
      // sotto il 15% un riquadro non si guarda piu': si smette di stringerlo
      const minimo = 0.15;
      let a = primaA + dFraz, b = primaB - dFraz;
      if (a < minimo) { b -= (minimo - a); a = minimo; }
      if (b < minimo) { a -= (minimo - b); b = minimo; }
      frazioni[indice] = a; frazioni[indice + 1] = b;
      grid.style.gridTemplateColumns = fracCol.map((f) => f.toFixed(4) + "fr").join(" ");
      grid.style.gridTemplateRows = fracRig.map((f) => f.toFixed(4) + "fr").join(" ");
    };
    const ferma = () => {
      document.removeEventListener("pointermove", muovi);
      document.removeEventListener("pointerup", ferma);
      document.body.classList.remove("trascina-col", "trascina-rig");
      posizionaManici(); salva();
    };
    document.addEventListener("pointermove", muovi);
    document.addEventListener("pointerup", ferma);
  }

  /* ---------- l'audio: uno solo alla volta ----------------------------------
     Quattro video che suonano insieme non si ascoltano, si sopportano. */
  const riquadro = (id) => grid.querySelector('[data-cell="' + id + '"]');

  function applicaAudio() {
    celle.forEach((c) => {
      const box = riquadro(c.id);
      if (!box) return;
      const acceso = c.id === audioAcceso;
      box.classList.toggle("live-audio", acceso);
      try {
        const api = box.querySelector("iframe").contentWindow.cellApi;
        acceso ? api.attiva() : api.silenzia();
      } catch (e) {}
      const i = box.querySelector(".audio i");
      if (i) i.innerHTML = acceso ? "&#128266;&#65038;" : "&#128263;&#65038;";
    });
  }

  /* ---------- una cella alla volta: mai ricostruire il muro ---------- */
  function srcCella(c) {
    return M.cella + "?u=" + encodeURIComponent(c.url)
         + (c.q ? "&q=" + encodeURIComponent(c.q) : "");
  }

  function creaCella(c) {
    const box = document.createElement("div");
    box.className = "cell";
    box.dataset.cell = c.id;
    const opzioni = (M.qualita || []).map((v) =>
      '<option value="' + v.valore + '"'
      + (c.q === v.valore || (!c.q && !v.valore) ? " selected" : "") + ">"
      + v.etichetta + "</option>").join("");

    box.innerHTML =
      '<iframe src="' + srcCella(c) + '" allow="autoplay; fullscreen; '
      + 'encrypted-media" allowfullscreen></iframe>'
      + '<div class=cellbar>'
      + '<button class="iconbtn only presa" title="' + T("muro.sposta") + '"'
      + ' aria-label="' + T("muro.sposta") + '">&#8942;&#8942;</button>'
      + '<span class=celltitle>' + (c.title || "…") + "</span>"
      + '<select class=qual aria-label="' + T("guarda.qualita") + '" title="'
      + T("guarda.qualita") + '">' + opzioni + "</select>"
      + '<button class="iconbtn only audio" title="' + T("muro.ascolta")
      + '" aria-label="' + T("muro.ascolta") + '"><i>&#128263;&#65038;</i></button>'
      + '<button class="iconbtn only live" title="' + T("guarda.torna_in_diretta")
      + '" aria-label="' + T("guarda.torna_in_diretta") + '"><i>&#9679;</i></button>'
      + '<button class="iconbtn only redo" title="' + T("muro.ricarica")
      + '" aria-label="' + T("muro.ricarica") + '"><i>&#8635;</i></button>'
      + '<button class="iconbtn only occhio" title="' + T("muro.nascondi_comandi")
      + '" aria-label="' + T("muro.nascondi_comandi") + '"><i>&#128065;&#65038;</i></button>'
      + '<button class="iconbtn only del" title="' + T("muro.togli")
      + '" aria-label="' + T("muro.togli") + '"><i>&times;</i></button>'
      + "</div>"
      + '<div class=cellfondo>'
      + '<button class="iconbtn only gioca" aria-label="' + T("muro.pausa")
      + '"><i>&#10074;&#10074;</i></button>'
      + '<input class=vol type=range min=0 max=1 step=0.02 value=1 aria-label="'
      + T("muro.volume") + '">'
      + "<span class=tempo></span>"
      + '<input class=barra type=range min=0 max=1000 step=1 value=0 aria-label="'
      + T("muro.punto") + '">'
      + '<button class="iconbtn only pieno" aria-label="' + T("muro.schermo_intero")
      + '"><i>&#9974;</i></button>'
      + "</div>";
    grid.appendChild(box);

    const f = box.querySelector("iframe");

    box.addEventListener("click", () => {
      audioAcceso = c.id; applicaAudio();
      // su tocco non c'e' il passaggio del mouse: la barra si mostra a chi
      // tocca, e si toglie dagli altri
      grid.querySelectorAll(".cell.tocco").forEach((b) => b.classList.remove("tocco"));
      box.classList.add("tocco");
    });
    box.querySelector(".audio").onclick = (e) => {
      e.stopPropagation();
      audioAcceso = (audioAcceso === c.id ? null : c.id);
      applicaAudio();
    };
    box.querySelector(".redo").onclick = (e) => {
      e.stopPropagation();
      try { f.contentWindow.cellApi.ricarica(); } catch (err) { f.src = f.src; }
    };
    const menuQ = box.querySelector(".qual");
    menuQ.onclick = (e) => e.stopPropagation();
    menuQ.onchange = (e) => {
      e.stopPropagation();
      c.q = menuQ.value;
      f.src = srcCella(c);            // gli altri riquadri non si toccano
      salva();
      notify(T("muro.qualita_cambiata"), c.title || "", "ok");
    };
    box.querySelector(".live").onclick = (e) => {
      e.stopPropagation();
      try { f.contentWindow.cellApi.alBordo(); } catch (err) {}
    };
    box.querySelector(".del").onclick = (e) => { e.stopPropagation(); togli(c.id); };

    const presa = box.querySelector(".presa");
    presa.addEventListener("pointerdown", (e) => iniziaTrascinoCella(e, c, box));
    presa.addEventListener("click", (e) => e.stopPropagation());
    presa.addEventListener("keydown", (e) => {
      // anche con le frecce: chi usa la tastiera deve poter riordinare
      const dove = celle.findIndex((x) => x.id === c.id);
      let verso = 0;
      if (e.key === "ArrowLeft" || e.key === "ArrowUp") verso = -1;
      if (e.key === "ArrowRight" || e.key === "ArrowDown") verso = 1;
      if (!verso) return;
      e.preventDefault();
      if (spostaA(c.id, dove + verso)) presa.focus();
    });

    /* I comandi del riquadro. Quelli nativi non bastano: sotto una certa
       larghezza Chrome toglie da solo volume e schermo intero, e su una
       diretta mostra una durata che non vuol dire niente. */
    const fondo = box.querySelector(".cellfondo");
    const bGioca = fondo.querySelector(".gioca");
    const slVol = fondo.querySelector(".vol");
    const slBarra = fondo.querySelector(".barra");
    const etTempo = fondo.querySelector(".tempo");
    const api = () => { try { return f.contentWindow.cellApi; } catch (e) { return null; } };
    const mmss = (t) => {
      t = Math.max(0, Math.round(t));
      const h = Math.floor(t / 3600), m = Math.floor(t / 60) % 60, s = t % 60;
      return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":"
           + String(s).padStart(2, "0");
    };

    fondo.onclick = (e) => e.stopPropagation();
    bGioca.onclick = (e) => { e.stopPropagation(); const a = api(); if (a) a.alterna(); };
    slVol.oninput = (e) => {
      e.stopPropagation();
      const a = api();
      if (!a) return;
      a.volume(parseFloat(slVol.value));
      if (parseFloat(slVol.value) > 0 && audioAcceso !== c.id) {
        audioAcceso = c.id; applicaAudio();
      }
    };
    let trascinoBarra = false;
    slBarra.onpointerdown = () => { trascinoBarra = true; };
    slBarra.onchange = (e) => {
      e.stopPropagation();
      trascinoBarra = false;
      const a = api(); const st = a && a.stato();
      if (a && st && st.durata) a.cerca(st.durata * (slBarra.value / 1000));
    };
    fondo.querySelector(".pieno").onclick = (e) => {
      e.stopPropagation();
      if (document.fullscreenElement) { document.exitFullscreen(); return; }
      box.requestFullscreen ? box.requestFullscreen().catch(() => {})
                            : (api() && api().schermoIntero());
    };

    /* Un battito per riquadro e non uno per tutto il muro: ogni riquadro
       nasce e muore quando lo fa lui, e un battito solo dovrebbe sapere chi
       c'e' ancora. */
    c.battito = setInterval(() => {
      const st = api() && api().stato();
      if (!st) return;
      bGioca.innerHTML = st.pausa ? "<i>&#9654;</i>" : "<i>&#10074;&#10074;</i>";
      bGioca.title = st.pausa ? T("muro.riprendi") : T("muro.pausa");
      if (document.activeElement !== slVol) slVol.value = st.muto ? 0 : st.volume;
      const inDiretta = st.live || !st.durata;
      slBarra.hidden = inDiretta;
      etTempo.textContent = inDiretta ? T("guarda.diretta")
                                      : mmss(st.tempo) + " / " + mmss(st.durata);
      if (!inDiretta && !trascinoBarra)
        slBarra.value = Math.round((st.tempo / st.durata) * 1000);
    }, 500);

    const zittisci = (attivo) => {
      c.zitto = attivo;
      box.classList.toggle("zitto", attivo);
      try { f.contentWindow.cellApi.comandi(!attivo); } catch (err) {}
      salva();
    };
    box.querySelector(".occhio").onclick = (e) => { e.stopPropagation(); zittisci(true); };

    // il ritorno: piccolo e sbiadito, ma sempre li'. Nascondere i comandi
    // senza lasciare un modo di riaverli e' un vicolo cieco.
    const ritorno = document.createElement("button");
    ritorno.className = "ritorno";
    ritorno.title = T("muro.rimetti_comandi");
    ritorno.setAttribute("aria-label", T("muro.rimetti_comandi"));
    ritorno.innerHTML = "<i>&#128066;&#65038;</i>";
    ritorno.onclick = (e) => { e.stopPropagation(); zittisci(false); };
    box.appendChild(ritorno);
    box.addEventListener("dblclick", () => {
      if (box.classList.contains("zitto")) zittisci(false);
    });
    if (c.zitto) setTimeout(() => zittisci(true), 600);

    f.addEventListener("load", () => setTimeout(() => {
      try {
        const a = f.contentWindow.cellApi;
        c.title = a.titolo() || c.url;
        box.querySelector(".celltitle").textContent = c.title;
        if (!a.inDiretta()) box.querySelector(".live").style.display = "none";
        salva();
      } catch (e) {
        box.querySelector(".celltitle").textContent = c.url;
      }
      applicaAudio();
    }, 400));
  }

  /* ---------- spostare un riquadro senza farlo ripartire ---------- */
  const ORDINE_MS = 260;

  function applicaOrdine() {
    celle.forEach((c, i) => {
      const box = riquadro(c.id);
      if (box) box.style.order = i;
    });
  }

  function misura() {
    const m = new Map();
    celle.forEach((c) => {
      const box = riquadro(c.id);
      if (box) m.set(c.id, box.getBoundingClientRect());
    });
    return m;
  }

  function animaVerso(prima, escluso) {
    celle.forEach((c) => {
      if (c.id === escluso) return;
      const box = riquadro(c.id);
      const era = prima.get(c.id);
      if (!box || !era) return;
      const ora = box.getBoundingClientRect();
      const dx = era.left - ora.left, dy = era.top - ora.top;
      if (!dx && !dy) return;
      box.style.transition = "none";
      box.style.transform = "translate(" + dx + "px," + dy + "px)";
      box.offsetHeight;                     // forza il calcolo, o non anima
      box.style.transition = "transform " + ORDINE_MS + "ms cubic-bezier(.2,.9,.2,1)";
      box.style.transform = "";
      setTimeout(() => { box.style.transition = ""; }, ORDINE_MS + 40);
    });
  }

  function spostaA(id, nuovo) {
    const vecchio = celle.findIndex((c) => c.id === id);
    if (vecchio < 0 || nuovo < 0 || nuovo >= celle.length || nuovo === vecchio)
      return false;
    const prima = misura();
    const [preso] = celle.splice(vecchio, 1);
    celle.splice(nuovo, 0, preso);
    applicaOrdine();
    animaVerso(prima, id);
    salva();
    return true;
  }

  function iniziaTrascinoCella(ev, c, box) {
    if (celle.length < 2) return;
    ev.preventDefault();
    ev.stopPropagation();
    const presa = box.querySelector(".presa");
    try { presa.setPointerCapture(ev.pointerId); } catch (e) {}
    document.body.classList.add("trascina-cella");
    box.classList.add("in-mano");

    const partenza = { x: ev.clientX, y: ev.clientY };
    let base = { x: 0, y: 0 };

    const muovi = (e) => {
      const dx = base.x + e.clientX - partenza.x;
      const dy = base.y + e.clientY - partenza.y;
      box.style.transform = "translate(" + dx + "px," + dy + "px) scale(1.03)";

      let bersaglio = -1, minimo = Infinity;
      celle.forEach((altra, i) => {
        if (altra.id === c.id) return;
        const r = riquadro(altra.id).getBoundingClientRect();
        const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
        const d = Math.hypot(e.clientX - cx, e.clientY - cy);
        // solo se ci sono davvero sopra, non se gli passo vicino
        if (e.clientX >= r.left && e.clientX <= r.right &&
            e.clientY >= r.top && e.clientY <= r.bottom && d < minimo) {
          minimo = d; bersaglio = i;
        }
      });
      if (bersaglio >= 0) {
        const eraQui = box.getBoundingClientRect();
        if (spostaA(c.id, bersaglio)) {
          // il mio posto e' cambiato: correggo lo scostamento, cosi' resto
          // incollato al dito invece di saltare nella casella nuova
          box.style.transform = "";
          const oraQui = box.getBoundingClientRect();
          base.x += eraQui.left - oraQui.left;
          base.y += eraQui.top - oraQui.top;
          box.style.transform =
            "translate(" + (base.x + e.clientX - partenza.x) + "px,"
            + (base.y + e.clientY - partenza.y) + "px) scale(1.03)";
        }
      }
    };

    const molla = () => {
      presa.removeEventListener("pointermove", muovi);
      presa.removeEventListener("pointerup", molla);
      presa.removeEventListener("pointercancel", molla);
      document.body.classList.remove("trascina-cella");
      box.style.transition = "transform " + ORDINE_MS + "ms cubic-bezier(.2,.9,.2,1)";
      box.style.transform = "";
      setTimeout(() => {
        box.style.transition = "";
        box.classList.remove("in-mano");
        requestAnimationFrame(posizionaManici);
      }, ORDINE_MS + 40);
      salva();
    };

    presa.addEventListener("pointermove", muovi);
    presa.addEventListener("pointerup", molla);
    presa.addEventListener("pointercancel", molla);
  }

  /* ---------- aggiungere e togliere ---------- */
  function aggiungi(url, titolo, zitto, q) {
    if (!/^https?:\/\//i.test(url)) return;
    if (celle.length >= (M.massimo || 4)) {
      notify(T("muro.pieno.t"), T("muro.pieno.d"), "warn");
      return;
    }
    const c = { id: Math.random().toString(36).slice(2, 8), url,
                title: titolo || "", zitto: !!zitto,
                q: q !== undefined ? q : (leggero ? "480" : "") };
    celle.push(c);
    creaCella(c);                   // solo la nuova: le altre non si toccano
    applicaOrdine();
    if (celle.length === 1) audioAcceso = c.id;
    applicaGriglia(true);
    applicaAudio();
    aggiornaSuggerimento();
  }

  function togli(id) {
    const box = riquadro(id);
    if (box) box.remove();          // via solo questa, le altre continuano
    const andata = celle.find((c) => c.id === id);
    if (andata && andata.battito) clearInterval(andata.battito);
    celle = celle.filter((c) => c.id !== id);
    applicaOrdine();
    if (audioAcceso === id) audioAcceso = celle.length ? celle[0].id : null;
    applicaGriglia(true);
    applicaAudio();
    aggiornaSuggerimento();
  }

  function aggiornaSuggerimento() {
    const vuoto = document.getElementById("vuoto");
    if (vuoto) vuoto.hidden = celle.length > 0;
    const hint = document.getElementById("wallhint");
    if (hint) {
      hint.textContent = celle.length > 1 ? T("muro.bordi")
        : (celle.length ? T("muro.audio_tocco") : T("muro.vuoto"));
    }
    document.querySelectorAll(".colscelta").forEach((x) => {
      x.style.display = disposizione === "griglia" ? "" : "none";
    });
  }

  /* ---------- i comandi della barra ---------- */
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    let v = field.value.trim();
    if (v && !/^https?:\/\//i.test(v) && /\w+\.\w{2,}/.test(v)) v = "https://" + v;
    aggiungi(v);
    field.value = "";
  });

  document.querySelectorAll("[data-disp]").forEach((b) => {
    b.onclick = () => {
      document.querySelectorAll("[data-disp]").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      disposizione = b.dataset.disp;
      applicaGriglia(true); aggiornaSuggerimento();
    };
  });
  document.querySelectorAll("[data-cols]").forEach((b) => {
    b.onclick = () => {
      document.querySelectorAll("[data-cols]").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
      nCol = parseInt(b.dataset.cols, 10);
      disposizione = "griglia";
      document.querySelectorAll("[data-disp]").forEach((x) =>
        x.classList.toggle("on", x.dataset.disp === "griglia"));
      applicaGriglia(true); aggiornaSuggerimento();
    };
  });
  document.getElementById("reset").onclick = () => applicaGriglia(true);

  /* Qualita' ridotta per tutti: su tablet e telefoni quanti video si possono
     decodificare insieme lo decide l'hardware, e abbassare la risoluzione e'
     l'unica leva che abbiamo. */
  function impostaLeggero(attivo, ricarica) {
    leggero = attivo;
    const b = document.getElementById("leggero");
    b.classList.toggle("on", attivo);
    try { localStorage.setItem(CHIAVE + ".leggero", attivo ? "1" : "0"); } catch (e) {}
    if (!ricarica) return;
    // comando d'insieme: porta tutti allo stesso gradino, e le scelte fatte
    // una per una si rifanno dal menu del riquadro
    celle.forEach((c) => {
      c.q = attivo ? "480" : "";
      const box = riquadro(c.id);
      if (!box) return;
      const menu = box.querySelector(".qual");
      if (menu) menu.value = c.q;
      box.querySelector("iframe").src = srcCella(c);
    });
    salva();
    notify(attivo ? T("muro.tutti_480.t") : T("muro.tutti_auto.t"),
           attivo ? T("muro.tutti_480.d") : T("muro.tutti_auto.d"), "ok");
  }
  document.getElementById("leggero").onclick = () => impostaLeggero(!leggero, true);
  try {
    const scelto = localStorage.getItem(CHIAVE + ".leggero");
    // su un dispositivo a tocco senza mouse e' la partenza giusta
    const tablet = matchMedia("(pointer: coarse)").matches;
    if (scelto === "1" || (tablet && scelto === null)) impostaLeggero(true, false);
  } catch (e) {}

  /* ---------- solo i video ---------- */
  function soloVideo(attivo) {
    muro.classList.toggle("nudo", attivo);
    grid.querySelectorAll(".cell").forEach((b) => {
      const zitto = b.classList.contains("zitto");
      try {
        b.querySelector("iframe").contentWindow.cellApi.comandi(!attivo && !zitto);
      } catch (e) {}
    });
    const b = document.getElementById("nudo");
    b.classList.toggle("on", attivo);
    b.title = attivo ? T("muro.rimetti_comandi") : T("muro.solo_video");
    try { localStorage.setItem(CHIAVE + ".nudo", attivo ? "1" : "0"); } catch (e) {}
    requestAnimationFrame(posizionaManici);
  }
  document.getElementById("nudo").onclick = () =>
    soloVideo(!muro.classList.contains("nudo"));

  /* ---------- i gruppi ---------- */
  async function aggiornaGruppi(selezionato) {
    const sel = document.getElementById("apregruppo");
    const d = await fetch(M.gruppi).then((r) => r.json()).catch(() => null);
    if (!d) return;
    sel.innerHTML = '<option value="">' + T("muro.gruppi") + "</option>";
    (d.gruppi || []).forEach((g) => {
      const o = document.createElement("option");
      o.value = g.id;
      o.textContent = g.nome + " (" + g.quanti + ")";
      if (g.id === selezionato) o.selected = true;
      sel.appendChild(o);
    });
  }

  document.getElementById("salvagruppo").onclick = async () => {
    if (!celle.length) {
      return notify(T("muro.niente_da_salvare.t"), T("muro.niente_da_salvare.d"),
                    "warn");
    }
    const suggerito = celle.map((c) => (c.title || "").split(" ")[0])
                           .filter(Boolean).slice(0, 2).join(" + ") || "gruppo";
    const nome = prompt(T("muro.nome_gruppo"), suggerito);
    if (!nome) return;
    const corpo = new FormData();
    corpo.append("nome", nome);
    corpo.append("celle", JSON.stringify(
      celle.map((c) => ({ url: c.url, title: c.title || "" }))));
    corpo.append("disposizione", disposizione);
    corpo.append("colonne", String(nCol));
    const r = await fetch(M.salvaGruppo, { method: "POST", body: corpo })
      .then((x) => x.json()).catch(() => null);
    if (r && r.ok) {
      notify(T("muro.gruppo_salvato"), nome, "ok");
      aggiornaGruppi(r.id);
    } else {
      notify(T("muro.non_salvato"), (r && r.perche) || "", "warn");
    }
  };

  async function apriGruppo(id) {
    const g = await fetch(M.gruppo + id + ".json").then((r) => r.json())
      .catch(() => null);
    if (!g || !g.celle) return notify(T("muro.gruppo_non_trovato"), "", "warn");
    grid.querySelectorAll(".cell").forEach((b) => b.remove());
    celle.forEach((c) => c.battito && clearInterval(c.battito));
    celle = []; audioAcceso = null;
    disposizione = g.disposizione || "griglia";
    nCol = g.colonne || 2;
    segnaScelte();
    g.celle.forEach((c) => aggiungi(c.url, c.title));
    notify(T("muro.gruppo_aperto"), g.nome, "ok");
  }
  document.getElementById("apregruppo").onchange = (e) => {
    if (e.target.value) apriGruppo(e.target.value);
  };

  function segnaScelte() {
    document.querySelectorAll("[data-disp]").forEach((x) =>
      x.classList.toggle("on", x.dataset.disp === disposizione));
    document.querySelectorAll("[data-cols]").forEach((x) =>
      x.classList.toggle("on", parseInt(x.dataset.cols, 10) === nCol));
  }

  /* ---------- il cassetto "altro" ---------- */
  (() => {
    const foglio = document.getElementById("extra");
    const velo = document.getElementById("extravelo");
    const bottone = document.getElementById("piu");
    const chiudi = () => {
      foglio.classList.remove("on"); velo.classList.remove("on");
      bottone.setAttribute("aria-expanded", "false");
    };
    bottone.onclick = () => {
      const apri = !foglio.classList.contains("on");
      foglio.classList.toggle("on", apri);
      velo.classList.toggle("on", apri);
      bottone.setAttribute("aria-expanded", String(apri));
    };
    velo.onclick = chiudi;
    document.getElementById("extrax").onclick = chiudi;
    // una scelta fatta, il foglio si toglie di mezzo da solo
    foglio.addEventListener("click", (e) => {
      if (e.target.closest("button,select") && e.target.id !== "extrax")
        setTimeout(chiudi, 120);
    });
    addEventListener("keydown", (e) => { if (e.key === "Escape") chiudi(); });
  })();

  /* ---------- il pannello dei salvati ---------- */
  (() => {
    const pannello = document.getElementById("salvati");
    const bottone = document.getElementById("wallpick");
    if (!pannello || !bottone) return;
    bottone.onclick = () => pannello.classList.toggle("on");
    pannello.addEventListener("click", (e) => {
      const voce = e.target.closest("[data-add]");
      if (voce) {
        e.preventDefault();
        aggiungi(voce.dataset.add, voce.dataset.titolo || "");
        pannello.classList.remove("on");
        return;
      }
      const gr = e.target.closest("[data-gruppo]");
      if (gr) {
        e.preventDefault();
        apriGruppo(gr.dataset.gruppo);
        pannello.classList.remove("on");
      }
    });
  })();

  /* ---------- il muro vuoto: scegliere invece di digitare ---------- */
  (() => {
    const vuoto = document.getElementById("vuoto");
    if (!vuoto) return;
    vuoto.addEventListener("click", (e) => {
      const voce = e.target.closest("[data-add]");
      if (voce) { e.preventDefault(); aggiungi(voce.dataset.add, voce.dataset.titolo || ""); return; }
      const gr = e.target.closest("[data-gruppo]");
      if (gr) { e.preventDefault(); apriGruppo(gr.dataset.gruppo); }
    });
    const incolla = document.getElementById("vuotoincolla");
    if (incolla) {
      incolla.onclick = async () => {
        // dove il browser lo permette il testo arriva da solo; altrimenti si
        // finisce comunque nel campo giusto, gia' a fuoco
        try {
          const t = (await navigator.clipboard.readText() || "").trim();
          if (/^https?:\/\//i.test(t)) { aggiungi(t); return; }
        } catch (e) {}
        field.focus();
        notify(T("muro.incolla.t"), T("muro.incolla.d"), "ok");
      };
    }
  })();

  /* ---------- un link trascinato dentro ---------- */
  let sganci = 0;
  const haLink = (e) => [...(e.dataTransfer && e.dataTransfer.types || [])]
    .some((t) => t === "text/uri-list" || t === "text/plain");
  addEventListener("dragenter", (e) => {
    if (!haLink(e)) return;
    e.preventDefault(); sganci++; muro.classList.add("sganciami");
  });
  addEventListener("dragover", (e) => { if (haLink(e)) e.preventDefault(); });
  addEventListener("dragleave", (e) => {
    if (!haLink(e)) return;
    if (--sganci <= 0) { sganci = 0; muro.classList.remove("sganciami"); }
  });
  addEventListener("drop", (e) => {
    if (!e.dataTransfer) return;
    e.preventDefault();
    sganci = 0; muro.classList.remove("sganciami");
    const testo = (e.dataTransfer.getData("text/uri-list")
                || e.dataTransfer.getData("text/plain") || "").trim();
    const link = testo.split(/\s+/).find((t) => /^https?:\/\//i.test(t)) || "";
    if (link) aggiungi(link);
    else notify(T("muro.non_link.t"), T("muro.non_link.d"), "warn");
  });

  /* ---------- tastiera e dintorni ---------- */
  document.addEventListener("mousemove", (e) => {
    // con i comandi nascosti la barra torna avvicinando il puntatore al bordo
    if (!muro.classList.contains("nudo")) return;
    muro.classList.toggle("sbircia", e.clientY < 8);
  });
  document.addEventListener("keydown", (e) => {
    const tag = ((e.target && e.target.tagName) || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return;
    if (e.key === "h" || e.key === "H") soloVideo(!muro.classList.contains("nudo"));
    if (e.key === "Escape" && muro.classList.contains("nudo")) soloVideo(false);
  });

  window.addEventListener("message", (e) => {
    if (e.origin !== location.origin || !e.data || e.data.cleanvid !== "fuoco") return;
    const box = [...grid.querySelectorAll(".cell")]
      .find((b) => b.querySelector("iframe").contentWindow === e.source);
    if (box) { audioAcceso = box.dataset.cell; applicaAudio(); }
  });

  window.addEventListener("resize", () => requestAnimationFrame(posizionaManici));

  /* ---------- ripresa: un gruppo chiesto nell'indirizzo, o l'ultimo muro --- */
  aggiornaGruppi();
  const chiesto = new URLSearchParams(location.search).get("gruppo");
  if (chiesto) {
    apriGruppo(chiesto).then(() => aggiornaGruppi(chiesto));
    aggiornaSuggerimento();
    field.focus();
    return;
  }
  const vecchio = ripristina();
  if (vecchio && vecchio.celle) {
    disposizione = vecchio.disposizione || "griglia";
    nCol = vecchio.nCol || 2;
    segnaScelte();
    vecchio.celle.slice(0, M.massimo || 4).forEach((c) =>
      aggiungi(c.url, c.title, c.zitto, c.q || ""));
    if (vecchio.fracCol && vecchio.fracCol.length === colonneEffettive()) {
      fracCol = vecchio.fracCol;
      fracRig = vecchio.fracRig || fracRig;
      applicaGriglia(false);
    }
  }
  aggiornaSuggerimento();
  applicaGriglia(celle.length === 0);
  try {
    if (localStorage.getItem(CHIAVE + ".nudo") === "1") soloVideo(true);
  } catch (e) {}
  field.focus();
})();
