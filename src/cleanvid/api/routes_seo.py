"""Le tre cose che stanno fuori dalle lingue: la radice, robots, la mappa.

Vanno registrate **prima** del router delle lingue. Starlette prende la prima
rotta che combacia, e `/{lingua_url}` combacia anche con `/robots.txt`: se
l'ordine si inverte, robots diventa una lingua che non esiste e risponde 404.
E' il tipo di errore che nessuno nota finche' non si guarda perche' il sito
non compare su Google.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import (
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)

from .. import seo
from ..lingue import testi
from ..media.icona import png
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


@router.get("/icon.png")
async def icona(s: int = Query(192, description="la misura in pixel")) -> Response:
    """L'icona, disegnata al volo e tenuta in memoria.

    Una `Cache-Control` lunga: e' un disegno che cambia quando cambia il
    marchio, cioe' quasi mai, e senza questa ogni pagina se la riscarica.
    """
    return Response(png(s), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@router.get("/manifest.webmanifest")
async def manifesto(request: Request) -> Response:
    """Con questo il sito si installa come un'applicazione.

    Icona sulla schermata, avvio a tutto schermo, niente barre del browser.
    Su iPhone e iPad e' l'unico modo di avere cleanvid come un'app, visto che
    sull'App Store non ci finira' mai.

    `start_url` porta alla lingua di chi installa, non alla radice: chi
    installa dall'italiano si aspetta di riaprire l'italiano, non di essere
    rispedito alla scelta ogni volta.
    """
    codice = scegli_per_chi_arriva(request)
    t = testi(codice)
    return JSONResponse({
        "name": "cleanvid",
        "short_name": "cleanvid",
        "description": t.get("meta.home.descrizione", ""),
        "lang": codice,
        "start_url": f"/{codice}/",
        "scope": "/",
        "display": "standalone",
        "orientation": "any",
        "background_color": "#0a0a0a",
        "theme_color": "#0a0a0a",
        "icons": [
            {"src": "/icon.png?s=192", "sizes": "192x192",
             "type": "image/png", "purpose": "any"},
            {"src": "/icon.png?s=512", "sizes": "512x512",
             "type": "image/png", "purpose": "any"},
            {"src": "/icon.png?s=512", "sizes": "512x512",
             "type": "image/png", "purpose": "maskable"},
        ],
        "shortcuts": [
            {"name": t.get("muro.titolo", "muro"), "url": f"/{codice}/muro"},
        ],
    }, media_type="application/manifest+json",
        headers={"Cache-Control": "public, max-age=3600"})
