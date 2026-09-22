"""Le tre cose che stanno fuori dalle lingue: la radice, robots, la mappa.

Vanno registrate **prima** del router delle lingue. Starlette prende la prima
rotta che combacia, e `/{lingua_url}` combacia anche con `/robots.txt`: se
l'ordine si inverte, robots diventa una lingua che non esiste e risponde 404.
E' il tipo di errore che nessuno nota finche' non si guarda perche' il sito
non compare su Google.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response

from .. import seo
from .contesto import scegli_per_chi_arriva

router = APIRouter(include_in_schema=False)


@router.get("/")
async def radice(request: Request) -> Response:
    """Chi arriva senza dire in che lingua la vuole.

    307 e non 301: la destinazione dipende da chi chiede, e un reindirizzamento
    permanente verrebbe messo in cache dal browser e dagli intermediari - dopo
    di che cambiare lingua dalle impostazioni non funzionerebbe piu', e
    capirne il motivo costerebbe un pomeriggio.
    """
    return RedirectResponse(f"/{scegli_per_chi_arriva(request)}/",
                            status_code=307)


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots() -> Response:
    return PlainTextResponse(seo.robots())


@router.get("/sitemap.xml")
async def sitemap() -> Response:
    return Response(seo.sitemap(), media_type="application/xml")
