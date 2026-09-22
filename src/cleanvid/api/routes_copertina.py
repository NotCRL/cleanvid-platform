"""La copertina di una pagina, servita da noi.

Sta fuori dal prefisso delle lingue perche' un'immagine non ha lingua, e
perche' cosi' la stessa copertina vale per tutte e quattordici invece di
essere riscaricata quattordici volte.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from ..media.copertine import VITA_S, copertina
from ..media.firme import firma_semplice

router = APIRouter(include_in_schema=False)


@router.get("/copertina")
async def immagine(
    u: str = Query(..., description="la pagina di cui si vuole la copertina"),
    s: str = Query(..., description="la firma"),
) -> Response:
    import hmac
    if not hmac.compare_digest(s, firma_semplice(u, "copertina")):
        raise HTTPException(status_code=403, detail="richiesta non firmata")

    trovata = await copertina(u)
    if trovata is None:
        # 404 e non un'immagine di scorta: cosi' il browser mostra il riquadro
        # vuoto che abbiamo disegnato noi, invece di una finta copertina
        # uguale per tutti che farebbe sembrare l'elenco tutto uguale
        raise HTTPException(status_code=404, detail="nessuna copertina")

    dati, tipo = trovata
    return Response(dati, media_type=tipo, headers={
        # la lascia tenere al browser: sono immagini che non cambiano mai, e
        # ricaricarle a ogni visita della home e' banda regalata
        "Cache-Control": f"public, max-age={VITA_S}, immutable",
    })
