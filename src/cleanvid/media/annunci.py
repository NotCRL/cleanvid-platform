"""SponsorBlock: i pezzi di video che nessuno vuole guardare.

Non e' la pubblicita' della piattaforma - quella si toglie altrove, nel
manifesto - ma i pezzi che ci ha messo chi ha caricato il video: lo sponsor
letto a voce, l'autopromozione, il «iscriviti al canale». Li segnala a mano
una comunita' di persone, e il servizio li restituisce come intervalli.

**Si saltano, non si tagliano.** Tagliarli vorrebbe dire rimontare il flusso,
e un flusso rimontato non si puo' piu' cercare: la barra del tempo direbbe
una cosa e il video un'altra. Saltarli e' un `currentTime` che si sposta, e
chi guarda vede solo che il video prosegue.

Il servizio a volte non risponde, o risponde 404 perche' quel video non l'ha
segnalato nessuno. Nessuno dei due casi e' un errore: si guarda il video
senza salti, che e' quello che sarebbe successo comunque.
"""

from __future__ import annotations

import json
import re

import httpx

from . import deposito
from .proxy import cliente

PUNTO = "https://sponsor.ajay.app/api/skipSegments"

# Le categorie che si saltano. Fuori restano quelle in cui la gente non e'
# d'accordo - per esempio la sigla, che a molti piace.
CATEGORIE = ("sponsor", "selfpromo", "interaction", "music_offtopic")

# Sotto il mezzo secondo un salto si sente piu' del pezzo saltato.
MINIMO_S = 0.5

CHIAVE = "sponsor:"
VITA_S = 12 * 3600

_YOUTUBE = re.compile(
    r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|live/|embed/)|youtu\.be/)"
    r"([\w-]{11})")


def video_youtube(url: str) -> str:
    trovato = _YOUTUBE.search(url)
    return trovato.group(1) if trovato else ""


async def segmenti(url: str) -> list[list[float]]:
    """Gli intervalli da saltare: `[[inizio, fine], ...]`. Vuoto se non si sa.

    Solo YouTube: SponsorBlock e' fatto per quello, e chiedergli di un altro
    sito e' una richiesta buttata.
    """
    video = video_youtube(url)
    if not video:
        return []

    ricordati = await deposito.cliente().get(CHIAVE + video)
    if ricordati is not None:
        risposta: list[list[float]] = json.loads(ricordati)
        return risposta

    try:
        r = await cliente().get(PUNTO, timeout=8, params={
            "videoID": video,
            "categories": json.dumps(list(CATEGORIE)),
        })
    except httpx.HTTPError:
        return []            # il servizio non risponde: si guarda e basta

    trovati: list[list[float]] = []
    if r.status_code == 200:
        try:
            for voce in r.json():
                inizio, fine = (voce.get("segment") or [0, 0])[:2]
                if fine - inizio > MINIMO_S:
                    trovati.append([float(inizio), float(fine)])
        except (ValueError, TypeError):
            trovati = []
    # 404 vuol dire che quel video non l'ha segnalato nessuno: e' una
    # risposta, e si ricorda come le altre per non richiederla a ogni apertura

    trovati.sort()
    await deposito.cliente().set(CHIAVE + video, json.dumps(trovati), ex=VITA_S)
    return trovati
