"""Il lettore ufficiale di una piattaforma, quando c'e'.

E' il primo pezzo che arriva dal cleanvid a file unico, e il piu' semplice:
riconosce da quale sito viene un link e, se quella piattaforma offre un
lettore incorporabile, costruisce l'indirizzo giusto. Nessuna rete, nessun
processo esterno: solo espressioni regolari.

Cosa NON c'e' ancora, e arrivera' col trasloco vero (passo 2): estrazione con
yt-dlp, manifest HLS, proxy dei byte, diagnosi degli errori. Qui serve
soltanto a dimostrare che il giro completo - link, utente, biblioteca, pagina
- sta in piedi.

Il lettore ufficiale ha un pregio e un difetto, e vanno detti: il link resta
valido nel tempo e si puo' condividere, ma la pubblicita' della piattaforma
rimane.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass

# (nome, come riconoscerlo, come costruire l'indirizzo del lettore)
_SCHEMI: list[tuple[str, str, str]] = [
    ("YouTube",
     r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|live/|embed/)|youtu\.be/)([\w-]{11})",
     "https://www.youtube.com/embed/{0}?autoplay=1&rel=0"),
    ("Vimeo",
     r"vimeo\.com/(?:video/)?(\d+)",
     "https://player.vimeo.com/video/{0}"),
    ("Dailymotion",
     r"dailymotion\.com/(?:video|embed/video)/([a-zA-Z0-9]+)",
     "https://www.dailymotion.com/embed/video/{0}"),
    ("Streamable",
     r"streamable\.com/(?:e/)?(\w+)",
     "https://streamable.com/e/{0}"),
    ("Twitch",          # una diretta di un canale
     r"twitch\.tv/(?!videos/|clips/)([a-zA-Z0-9_]{3,25})/?(?:\?|$)",
     "https://player.twitch.tv/?channel={0}&parent={host}&autoplay=true"),
    ("Twitch",          # una registrazione
     r"twitch\.tv/videos/(\d+)",
     "https://player.twitch.tv/?video={0}&parent={host}&autoplay=true"),
]


@dataclass(slots=True)
class Lettore:
    piattaforma: str
    url_lettore: str
    diretta_probabile: bool = False


def piattaforma_di(url: str) -> str:
    """Il nome del sito, senza toccare la rete. Stringa vuota se sconosciuto."""
    for nome, schema, _ in _SCHEMI:
        if re.search(schema, url, re.I):
            return nome
    host = urllib.parse.urlparse(url).netloc
    return host[4:] if host.startswith("www.") else host


def lettore_ufficiale(url: str, host_pagina: str = "localhost") -> Lettore | None:
    """L'indirizzo del lettore incorporabile, o None se quel sito non ne ha.

    `host_pagina` serve a Twitch, che rifiuta di farsi incorniciare se il
    parametro `parent` non combacia con l'indirizzo da cui la pagina e'
    aperta. E' il tipo di dettaglio che costa un pomeriggio a scoprirsi.
    """
    for nome, schema, modello in _SCHEMI:
        trovato = re.search(schema, url, re.I)
        if not trovato:
            continue
        indirizzo = modello.format(trovato.group(1), host=host_pagina)
        if "{host}" in modello:
            # Twitch accetta piu' parent: cosi' la pagina funziona sia da
            # localhost sia dall'indirizzo di rete, senza rigenerare nulla
            indirizzo = indirizzo.replace(
                f"parent={host_pagina}",
                f"parent={host_pagina}&parent=localhost&parent=127.0.0.1")
        return Lettore(
            piattaforma=nome,
            url_lettore=indirizzo,
            diretta_probabile=(nome == "Twitch" and "/videos/" not in url),
        )
    return None
