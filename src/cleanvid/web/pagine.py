"""I modelli delle pagine, con i filtri che servono a scriverli.

Un solo oggetto per tutto il processo: `Jinja2Templates` compila i modelli la
prima volta e poi li tiene, e crearne uno per modulo vorrebbe dire ricompilare
tutto tante volte quante sono le rotte - e, peggio, avere filtri disponibili
in una pagina e non nell'altra.
"""

from __future__ import annotations

from fastapi.templating import Jinja2Templates

from ..media.firme import link_copertina

modelli = Jinja2Templates(directory="src/cleanvid/web/templates")


def mm_ss(secondi: float | None) -> str:
    """Un tempo come lo legge una persona: 4:07, non 247.0."""
    if not secondi or secondi < 0:
        return "0:00"
    interi = int(secondi)
    ore, resto = divmod(interi, 3600)
    minuti, sec = divmod(resto, 60)
    if ore:
        return f"{ore}:{minuti:02d}:{sec:02d}"
    return f"{minuti}:{sec:02d}"


# I filtri si registrano qui, una volta. `copertina` e' un filtro e non una
# funzione chiamata nel modello perche' cosi' nel modello si legge
# `voce.url | copertina`, che dice cosa fa senza spiegazioni.
modelli.env.filters["copertina"] = link_copertina
modelli.env.filters["mm_ss"] = mm_ss
