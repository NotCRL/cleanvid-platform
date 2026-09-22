/* Gli avvisi in alto a destra.
 *
 * Arrivano dal file unico. Servono perche' nel muro quasi tutto succede senza
 * cambiare pagina: se cambi la qualita' di un riquadro o salvi un gruppo e
 * non succede niente di visibile, non sai se ha funzionato.
 *
 * Chi ha un'azione da premere resta finche' non lo chiudi tu; gli altri se ne
 * vanno da soli. Un errore resta piu' a lungo di una conferma, perche' va
 * letto e non solo intravisto.
 */
(() => {
  "use strict";

  window.notify = function (titolo, testo, genere, azione) {
    const cassetta = document.getElementById("notif");
    if (!cassetta) return null;

    const n = document.createElement("div");
    n.className = "note " + (genere || "");
    const x = document.createElement("i");
    x.className = "x";
    x.textContent = "×";
    x.onclick = () => via();
    n.appendChild(x);

    const b = document.createElement("b");
    b.textContent = titolo;
    n.appendChild(b);
    if (testo) {
      const s = document.createElement("span");
      s.textContent = testo;
      n.appendChild(s);
    }
    if (azione) {
      const a = document.createElement("a");
      a.textContent = azione.etichetta;
      a.href = azione.href || "#";
      if (azione.fai) {
        a.onclick = (e) => { e.preventDefault(); azione.fai(); via(); };
      }
      n.appendChild(a);
    }
    cassetta.appendChild(n);
    requestAnimationFrame(() => n.classList.add("on"));

    let orologio = null;
    function via() {
      clearTimeout(orologio);
      n.classList.remove("on");
      setTimeout(() => n.remove(), 220);
    }
    if (!azione) orologio = setTimeout(via, genere === "err" ? 7000 : 4000);
    return via;
  };
})();
