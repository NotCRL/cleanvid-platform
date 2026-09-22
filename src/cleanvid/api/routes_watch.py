"""Le due pagine del passo 1: la home e quella che apre un video.

Non c'e' ancora l'estrazione (passo 2): qui si apre con il lettore ufficiale
della piattaforma, che non richiede ne' yt-dlp ne' processi esterni. Basta a
dimostrare la cosa che va dimostrata adesso: che il giro completo - chi sei,
cosa hai aperto, cosa ritrovi - regge una persona alla volta.
"""

from __future__ import annotations

import urllib.parse

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from ..db import sessione
from ..media.embed import lettore_ufficiale, piattaforma_di
from ..models import Genere, Utente
from . import biblioteca
from .identita import utente_corrente

router = APIRouter()
pagine = Jinja2Templates(directory="src/cleanvid/web/templates")


def _normalizza(grezzo: str) -> str:
    """Un indirizzo senza http:// e' l'errore piu' comune: si completa."""
    testo = (grezzo or "").strip()
    if testo and not testo.lower().startswith(("http://", "https://")):
        if "." in testo.split("/")[0]:
            testo = "https://" + testo
    return testo


@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    utente: Utente = Depends(utente_corrente),
    db: AsyncSession = Depends(sessione),
) -> Response:
    recenti = await biblioteca.elenco(db, utente.id, Genere.CRONOLOGIA)
    return pagine.TemplateResponse(request, "home.html", {
        "utente": utente,
        "recenti": recenti,
    })


@router.post("/apri")
async def apri(
    url: str = Form(...),
    utente: Utente = Depends(utente_corrente),
) -> Response:
    """Dal campo della home al video: si passa per un indirizzo condivisibile.

    Un redirect invece di rispondere direttamente, cosi' la pagina del video
    ha un suo indirizzo che si puo' salvare, ricaricare e mandare.
    """
    pulito = _normalizza(url)
    if not pulito:
        return RedirectResponse("/", status_code=303)
    return RedirectResponse(
        "/guarda?u=" + urllib.parse.quote(pulito, safe=""), status_code=303)


@router.get("/guarda", response_class=HTMLResponse)
async def guarda(
    request: Request,
    u: str = "",
    utente: Utente = Depends(utente_corrente),
    db: AsyncSession = Depends(sessione),
) -> Response:
    url = _normalizza(u)
    if not url:
        return RedirectResponse("/", status_code=303)

    piattaforma = piattaforma_di(url)
    lettore = lettore_ufficiale(url, host_pagina=request.url.hostname or "localhost")

    # la visita si annota comunque: anche un tentativo andato male e' un
    # tentativo, e ritrovarlo nella cronologia serve a riprovarci
    await biblioteca.annota_visita(db, utente.id, url,
                                   titolo="", piattaforma=piattaforma)

    return pagine.TemplateResponse(request, "guarda.html", {
        "utente": utente,
        "url": url,
        "piattaforma": piattaforma,
        "lettore": lettore,
    })


@router.get("/stato", response_class=HTMLResponse)
async def stato(
    request: Request,
    utente: Utente = Depends(utente_corrente),
    db: AsyncSession = Depends(sessione),
) -> Response:
    """Una pagina di servizio: dice chi sei e quanto hai nella tua biblioteca.

    Serve adesso per vedere con gli occhi che la separazione per utente
    funziona; quando ci saranno pagine vere andra' via.
    """
    recenti = await biblioteca.elenco(db, utente.id, Genere.CRONOLOGIA, quante=100)
    return pagine.TemplateResponse(request, "stato.html", {
        "utente": utente,
        "quante": len(recenti),
    })
