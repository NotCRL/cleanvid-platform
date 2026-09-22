"""Le due pagine del passo 1: la home e quella che apre un video.

Si prova prima il lettore ufficiale della piattaforma, e solo se non c'e' si
passa all'estrazione. L'ordine non e' casuale: il lettore ufficiale costa
zero, non scade e regge qualunque cosa la piattaforma cambi domani;
l'estrazione costa qualche secondo di CPU, produce indirizzi che scadono, e
va rifatta ogni volta che il sito cambia idea. Si paga quel prezzo solo
quando non c'e' alternativa.

Il rovescio, ed e' bene dirlo: dentro il lettore ufficiale la pubblicita'
della piattaforma resta. Toglierla e' esattamente cio' che l'estrazione sa
fare, e infatti per i siti senza lettore il video esce pulito.
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
from ..media.estrazione import Estratto, NonEstraibile, risolvi
from ..media.qualita import QUALITA
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
    q: str = "",
    utente: Utente = Depends(utente_corrente),
    db: AsyncSession = Depends(sessione),
) -> Response:
    url = _normalizza(u)
    if not url:
        return RedirectResponse("/", status_code=303)

    piattaforma = piattaforma_di(url)
    lettore = lettore_ufficiale(url, host_pagina=request.url.hostname or "localhost")

    estratto: Estratto | None = None
    perche = ""
    if lettore is None:
        try:
            estratto = await risolvi(url, q)
        except NonEstraibile as e:
            # il messaggio di yt-dlp si mostra cosi' com'e': dice quasi sempre
            # la verita' ("video privato", "serve un account"), e riscriverlo
            # in gentile vorrebbe dire nascondere l'unica cosa utile
            perche = str(e)

    # la visita si annota comunque: anche un tentativo andato male e' un
    # tentativo, e ritrovarlo nella cronologia serve a riprovarci
    await biblioteca.annota_visita(
        db, utente.id, url,
        titolo=estratto.titolo if estratto else "",
        piattaforma=piattaforma)

    return pagine.TemplateResponse(request, "guarda.html", {
        "utente": utente,
        "url": url,
        "q": q,
        "qualita_possibili": QUALITA,
        "piattaforma": piattaforma,
        "titolo": estratto.titolo if estratto else "",
        "lettore": lettore,
        "estratto": estratto,
        "perche": perche,
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
