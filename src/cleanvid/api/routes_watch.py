"""Le pagine che una persona apre: home, video, impostazioni, stato.

Stanno tutte sotto `/{lingua}/` - `/it/`, `/en/`, `/es/`. Non e' un vezzo: un
motore di ricerca indicizza indirizzi, e una pagina che cambia lingua in base
a un cookie esiste, per chi cerca, in una lingua sola. Il perche' per esteso
sta in `seo.py`.

Si prova prima il lettore ufficiale della piattaforma, e solo se non c'e' si
passa all'estrazione. L'ordine non e' casuale: il lettore ufficiale costa
zero, non scade e regge qualunque cosa la piattaforma cambi domani;
l'estrazione costa qualche secondo di CPU, produce indirizzi che scadono, e va
rifatta ogni volta che il sito cambia idea. Si paga quel prezzo solo quando
non c'e' alternativa.

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

from .. import seo
from ..db import sessione
from ..lingue import esiste
from ..media.embed import lettore_ufficiale, piattaforma_di
from ..media.estrazione import Estratto, NonEstraibile, risolvi
from ..media.qualita import QUALITA
from ..models import Genere, Utente
from . import biblioteca
from .contesto import COOKIE_LINGUA, DURATA_COOKIE, Contesto, contesto
from .identita import utente_corrente

router = APIRouter(prefix="/{lingua_url}")
pagine = Jinja2Templates(directory="src/cleanvid/web/templates")


def _normalizza(grezzo: str) -> str:
    """Un indirizzo senza http:// e' l'errore piu' comune: si completa."""
    testo = (grezzo or "").strip()
    if testo and not testo.lower().startswith(("http://", "https://")):
        if "." in testo.split("/")[0]:
            testo = "https://" + testo
    return testo


def _pagina(request: Request, modello: str, c: Contesto,
            **extra: object) -> Response:
    return pagine.TemplateResponse(request, modello, {
        "c": c, "t": c.t, "utente": c.utente, **extra})


@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    c: Contesto = Depends(contesto),
    db: AsyncSession = Depends(sessione),
) -> Response:
    recenti = await biblioteca.elenco(db, c.utente.id, Genere.CRONOLOGIA)
    return _pagina(request, "home.html", c,
                   recenti=recenti,
                   dati_strutturati=seo.dati_strutturati_home(
                       c.lingua.codice, c.t))


@router.post("/apri")
async def apri(
    lingua_url: str,
    url: str = Form(...),
    utente: Utente = Depends(utente_corrente),
) -> Response:
    """Dal campo della home al video: si passa per un indirizzo condivisibile.

    Un redirect invece di rispondere direttamente, cosi' la pagina del video
    ha un suo indirizzo che si puo' salvare, ricaricare e mandare.
    """
    lingua_url = lingua_url if esiste(lingua_url) else "en"
    pulito = _normalizza(url)
    if not pulito:
        return RedirectResponse(f"/{lingua_url}/", status_code=303)
    return RedirectResponse(
        f"/{lingua_url}/guarda?u=" + urllib.parse.quote(pulito, safe=""),
        status_code=303)


@router.get("/guarda", response_class=HTMLResponse)
async def guarda(
    request: Request,
    u: str = "",
    q: str = "",
    c: Contesto = Depends(contesto),
    db: AsyncSession = Depends(sessione),
) -> Response:
    url = _normalizza(u)
    if not url:
        return RedirectResponse(f"/{c.lingua.codice}/", status_code=303)

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
        db, c.utente.id, url,
        titolo=estratto.titolo if estratto else "",
        piattaforma=piattaforma)

    return _pagina(request, "guarda.html", c,
                   url=url, q=q, qualita_possibili=QUALITA,
                   piattaforma=piattaforma,
                   titolo=estratto.titolo if estratto else "",
                   lettore=lettore, estratto=estratto, perche=perche)


@router.get("/impostazioni", response_class=HTMLResponse)
async def impostazioni_pagina(
    request: Request,
    salvato: int = 0,
    c: Contesto = Depends(contesto),
) -> Response:
    return _pagina(request, "impostazioni.html", c, salvato=bool(salvato))


@router.post("/impostazioni/lingua")
async def cambia_lingua(
    lingua_url: str,
    scelta: str = Form(...),
    utente: Utente = Depends(utente_corrente),
    db: AsyncSession = Depends(sessione),
) -> Response:
    """La scelta si scrive in due posti, e servono tutti e due.

    Sulla riga dell'utente, perche' lo segua su ogni dispositivo dove ha il
    suo cookie; e in un cookie a parte, perche' chi apre la radice venga
    mandato subito nella lingua giusta senza aspettare il database.
    """
    codice = scelta if esiste(scelta) else lingua_url
    utente.lingua = codice
    db.add(utente)

    risposta = RedirectResponse(f"/{codice}/impostazioni?salvato=1",
                                status_code=303)
    risposta.set_cookie(COOKIE_LINGUA, codice, max_age=DURATA_COOKIE,
                        samesite="lax", path="/")
    return risposta


@router.get("/stato", response_class=HTMLResponse)
async def stato(
    request: Request,
    c: Contesto = Depends(contesto),
    db: AsyncSession = Depends(sessione),
) -> Response:
    """Una pagina di servizio: dice chi sei e quanto hai nella tua biblioteca.

    Serve adesso per vedere con gli occhi che la separazione per utente
    funziona; quando ci saranno pagine vere andra' via.
    """
    recenti = await biblioteca.elenco(db, c.utente.id, Genere.CRONOLOGIA,
                                      quante=100)
    return _pagina(request, "stato.html", c, quante=len(recenti))
