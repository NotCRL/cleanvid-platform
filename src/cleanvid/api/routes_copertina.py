"""La copertina di una pagina, servita da noi.

Sta fuori dal prefisso delle lingue perche' un'immagine non ha lingua, e
perche' cosi' la stessa copertina vale per tutte e quattordici invece di
essere riscaricata quattordici volte.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from ..media.copertine import VITA_S, pronta, scalda
from ..media.firme import firma_semplice

router = APIRouter(include_in_schema=False)


@router.get("/copertina")
async def immagine(
    u: str = Query(..., description="la pagina di cui si vuole la copertina"),
    s: str = Query(..., description="la firma"),
    r: int = Query(0, description="il giro di tentativo, per non farsi "
                                  "servire dalla cache il no di prima"),
) -> Response:
    import hmac
    if not hmac.compare_digest(s, firma_semplice(u, "copertina")):
        raise HTTPException(status_code=403, detail="richiesta non firmata")

    trovata = pronta(u)
    if trovata is None:
        # Non si aspetta: cercarla puo' costare venticinque secondi di yt-dlp,
        # e con venti voci in elenco sarebbe una home che non si apre. Si
        # risponde no, la ricerca parte in disparte, e il browser riprova.
        # Nel frattempo si vede il riquadro con le iniziali, che e' gia' una
        # risposta - e comunque meglio di una pagina ferma.
        scalda(u)
        raise HTTPException(status_code=404, detail="non ancora pronta")

    dati, tipo = trovata
    return Response(dati, media_type=tipo, headers={
        # la lascia tenere al browser: sono immagini che non cambiano mai, e
        # ricaricarle a ogni visita della home e' banda regalata
        "Cache-Control": f"public, max-age={VITA_S}, immutable",
    })
