"""Il lettore ufficiale di una piattaforma, quando c'e'.

E' il primo pezzo che arriva dal cleanvid a file unico, e il piu' semplice:
riconosce da quale sito viene un link e, se quella piattaforma offre un
lettore incorporabile, costruisce l'indirizzo giusto. Nessuna rete, nessun
processo esterno: solo espressioni regolari.

E' la prima cosa che si prova, prima dell'estrazione: costa zero, non scade,
e regge qualunque cosa la piattaforma cambi domani. L'estrazione costa CPU e
produce indirizzi che scadono, quindi si paga quel prezzo solo quando qui non
si trova niente.

Il difetto va detto: dentro il lettore ufficiale la pubblicita' della
piattaforma resta. E' il compromesso di questa strada, ed e' il motivo per
cui `estrazione.py` esiste comunque.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass

# (nome, come riconoscerlo, come costruire l'indirizzo del lettore)
_SCHEMI: list[tuple[str, str, str]] = [
    ("YouTube",
     r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|live/|embed/)|youtu\.be/)([\w-]{11})",
     # `enablejsapi=1` non e' un di piu': senza, il lettore di YouTube ignora
     # in silenzio i comandi che gli mandiamo, e nel muro l'audio non si
     # accende. E' il tipo di parametro che manca e non se ne capisce il
     # perche', perche' non c'e' nessun errore da nessuna parte.
     "https://www.youtube.com/embed/{0}?autoplay=1&rel=0&enablejsapi=1"),
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


def lettore_ufficiale(url: str, host_pagina: str = "localhost",
                      per_cella: bool = False) -> Lettore | None:
    """L'indirizzo del lettore incorporabile, o None se quel sito non ne ha.

    `host_pagina` serve a Twitch, che rifiuta di farsi incorniciare se il
    parametro `parent` non combacia con l'indirizzo da cui la pagina e'
    aperta. E' il tipo di dettaglio che costa un pomeriggio a scoprirsi.

    `per_cella` e' per il muro: li' un riquadro deve partire **muto**, perche'
    di quattro video che partono insieme se ne ascolta uno solo. Chi decide
    quale e' il muro, e lo dice al lettore dopo, a video gia' avviato.
    """
    for nome, schema, modello in _SCHEMI:
        trovato = re.search(schema, url, re.I)
        if not trovato:
            continue
        indirizzo = modello.format(trovato.group(1), host=host_pagina)
        if per_cella:
            # Muto, perche' di quattro video che partono insieme se ne ascolta
            # uno. E senza i comandi della piattaforma: dentro un riquadro il
            # muro ne disegna gia' di suoi, e due barre di comandi una sopra
            # l'altra non si capisce quale tocchi.
            # Ogni piattaforma lo scrive a modo suo, e chi non capisce ignora.
            if "youtube" in indirizzo:
                indirizzo += "&mute=1&controls=0&modestbranding=1"
            elif "twitch" in indirizzo:
                indirizzo += "&muted=true&controls=false"
            else:
                indirizzo += "&muted=1&controls=0"
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


def chat_incorporabile(url: str, host_pagina: str = "localhost") -> str | None:
    """L'indirizzo della chat della diretta, o None se non ce n'e' una.

    Vale solo per le dirette: il `live_chat` di YouTube su un video registrato
    apre un riquadro con dentro un errore, che e' peggio di niente. Chi chiama
    deve aver gia' stabilito che si tratta di una diretta.

    Twitch e YouTube accettano l'iframe solo se il dominio dichiarato combacia
    con quello da cui si apre la pagina - `parent` per l'uno, `embed_domain`
    per l'altro. E' lo stesso inciampo del lettore di Twitch, e si risolve
    allo stesso modo: prendendolo dall'indirizzo della richiesta.
    """
    dominio = (host_pagina or "").split(":")[0] or "localhost"

    canale = re.search(r"twitch\.tv/(?!videos/|clips/|directory)"
                       r"([a-zA-Z0-9_]{3,25})", url, re.I)
    if canale:
        # piu' `parent`: cosi' la stessa pagina funziona da localhost e
        # dall'indirizzo di rete senza rigenerare niente
        genitori = dict.fromkeys([dominio, "localhost", "127.0.0.1"])
        parenti = "&".join(f"parent={h}" for h in genitori)
        return (f"https://www.twitch.tv/embed/{canale.group(1)}/chat"
                f"?darkpopout&{parenti}")

    video = re.search(
        r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|live/|embed/)"
        r"|youtu\.be/)([\w-]{11})", url, re.I)
    if video:
        return (f"https://www.youtube.com/live_chat?v={video.group(1)}"
                f"&embed_domain={urllib.parse.quote(dominio)}")
    return None
