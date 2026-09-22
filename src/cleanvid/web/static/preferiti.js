/* La stella si accende sul posto, senza ricaricare la pagina.
 *
 * Il modulo HTML c'e' lo stesso e funziona da solo: questo lo intercetta e fa
 * la stessa cosa di lato. Senza javascript la stella funziona comunque, con
 * un rimbalzo - e' la forma vecchia, ed e' quella che regge quando il resto
 * non c'e'.
 *
 * Il motivo per cui vale la pena: su una pagina che sta suonando un video,
 * ricaricare vuol dire farlo ripartire da capo. Per una stella.
 */
(() => {
  "use strict";

  function aggiorna(bottone, acceso) {
    bottone.classList.toggle("acceso", acceso);
    bottone.setAttribute("aria-pressed", acceso ? "true" : "false");
    const segno = bottone.querySelector("i");
    if (segno) segno.textContent = acceso ? "★" : "☆";
    const scritta = bottone.querySelector("span");
    const nuovo = acceso ? bottone.dataset.si : bottone.dataset.no;
    if (scritta && nuovo) scritta.textContent = nuovo;
    bottone.title = nuovo || bottone.title;
  }

  document.addEventListener("submit", async (e) => {
    const modulo = e.target.closest("form[data-preferito]");
    if (!modulo) return;
    e.preventDefault();

    const bottone = modulo.querySelector("button");
    if (bottone) bottone.disabled = true;
    try {
      const r = await fetch(modulo.action, {
        method: "POST",
        body: new FormData(modulo),
        headers: { Accept: "application/json" },
      });
      if (!r.ok) throw new Error(String(r.status));
      const esito = await r.json();
      if (bottone) aggiorna(bottone, !!esito.preferito);
    } catch (err) {
      // se la rete non risponde si lascia fare al modulo, che almeno dira'
      // qualcosa: fallire in silenzio su un bottone e' il modo di far
      // credere a qualcuno di aver salvato una cosa che non ha salvato
      if (bottone) bottone.disabled = false;
      modulo.submit();
      return;
    }
    if (bottone) bottone.disabled = false;
  });
})();
