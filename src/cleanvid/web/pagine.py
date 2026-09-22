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


# --------------------------------------------------------------------------
# i pezzi grafici che arrivano dal cleanvid a file unico
# --------------------------------------------------------------------------

import hashlib  # noqa: E402
import re  # noqa: E402

# Le icone sono SVG in linea e non un font o dei file: sono una dozzina di
# forme semplici, e un font di icone e' una richiesta in piu' che blocca il
# disegno per mostrare un cestino.
ICONE: dict[str, str] = {
    "cestino": "<svg class=ic viewBox='0 0 24 24'><path d='M4 7h16M10 4.5h4"
               "M6.5 7l.9 12.5h9.2L17.5 7M10 10.5v6M14 10.5v6'/></svg>",
    "penna": "<svg class=ic viewBox='0 0 24 24'><path d='M4 20h4L19.5 8.5a2.1 "
             "2.1 0 0 0-3-3L5 17v3z'/></svg>",
    "stella": "<svg class=ic viewBox='0 0 24 24'><path d='M12 4.2l2.3 4.9 5.2.7"
              "-3.8 3.7.9 5.3L12 16.3l-4.6 2.5.9-5.3-3.8-3.7 5.2-.7z'/></svg>",
    "disco": "<svg class=ic viewBox='0 0 24 24'><circle cx='12' cy='12' r='8.5'/>"
             "<circle cx='12' cy='12' r='3'/></svg>",
    "orologio": "<svg class=ic viewBox='0 0 24 24'><circle cx='12' cy='12' "
                "r='8.5'/><path d='M12 7.5V12l3 1.8'/></svg>",
    "griglia": "<svg class=ic viewBox='0 0 24 24'><path d='M4.5 4.5h6v6h-6z"
               "M13.5 4.5h6v6h-6zM4.5 13.5h6v6h-6zM13.5 13.5h6v6h-6z'/></svg>",
    # i due pezzi vanno uniti con uno spazio: senza, `0 0 0 0` e `15.6`
    # diventano `0 015.6` e il browser rifiuta tutto il tracciato. L'icona
    # spariva e in console restava «Expected number».
    "tema": "<svg class=ic viewBox='0 0 24 24'><path d='M12 4.2a7.8 7.8 0 0 0 0 "
            "15.6 7.8 7.8 0 0 1 0-15.6zM12 4.2v15.6'/></svg>",
    "mondo": "<svg class=ic viewBox='0 0 24 24'><circle cx='12' cy='12' r='8.5'/>"
             "<path d='M3.5 12h17M12 3.5c2.2 2.4 3.3 5.3 3.3 8.5S14.2 18.1 12 "
             "20.5c-2.2-2.4-3.3-5.3-3.3-8.5S9.8 5.9 12 3.5z'/></svg>",
    "info": "<svg class=ic viewBox='0 0 24 24'><circle cx='12' cy='12' r='8.5'/>"
            "<path d='M12 11v5.5M12 7.8v.01'/></svg>",
    "marchio": "<svg class=segno viewBox='0 0 26 24' aria-hidden='true'>"
               "<path class=lama d='M4 1.6 21.5 11.1 4 11.1Z'/>"
               "<path class=lama d='M1.5 12.9 17.5 12.9 1.5 21.6Z'/>"
               "<rect class=taglio x='-1' y='11.45' width='28' height='1'/>"
               "</svg>",
}


def tinta(testo: str) -> int:
    """Una tinta stabile per ogni voce: la stessa cosa ha sempre lo stesso colore.

    Stabile e non casuale, perche' e' meta' del motivo per cui un elenco di
    copertine si riconosce con la coda dell'occhio: il riquadro di un certo
    canale e' sempre di quel colore, anche prima che l'immagine arrivi.
    """
    impronta = hashlib.sha1((testo or "?").encode(),
                            usedforsecurity=False).hexdigest()[:4]
    return int(impronta, 16) % 360


def iniziali(titolo: str) -> str:
    """Cosa si vede finche' la copertina non c'e' o non e' ancora arrivata."""
    parole = [p for p in re.split(r"[\s._/-]+", (titolo or "").strip()) if p]
    if not parole:
        return "?"
    if len(parole) == 1:
        return parole[0][:2]
    return parole[0][:1] + parole[1][:1]


modelli.env.filters["tinta"] = tinta
modelli.env.filters["iniziali"] = iniziali
modelli.env.globals["ICONE"] = ICONE


def nome_voce(voce: object) -> str:
    """Come si chiama una voce quando non ha un titolo.

    Arriva dal `label_of` del file unico, e risolve un problema vero: senza
    titolo si finiva per mostrare l'indirizzo intero, e le iniziali del
    riquadro colorato venivano da li' - «hv» per un link di Vimeo, perche'
    sono le prime lettere di «https» e «vimeo». Il sito da cui viene e' una
    risposta molto migliore, e sta sempre nell'indirizzo.
    """
    titolo = getattr(voce, "titolo", "") or ""
    if titolo:
        return str(titolo)
    import urllib.parse
    sito = urllib.parse.urlparse(str(getattr(voce, "url", ""))).netloc
    if sito.startswith("www."):
        sito = sito[4:]
    return sito or str(getattr(voce, "url", "")) or "?"


modelli.env.filters["nome_voce"] = nome_voce
