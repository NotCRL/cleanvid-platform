"""Quello che si fa alla propria roba: preferire, rinominare, togliere.

Tutto `POST`, e non per pignoleria: un `GET` che cancella viene eseguito dal
precaricamento del browser, dall'anteprima di una chat e dal crawler di un
motore di ricerca. La cronologia sparirebbe da sola e nessuno capirebbe
perche'.

Ogni rotta qui passa da `utente_corrente` e ogni query filtra per utente: non
esiste una funzione che prenda un id e restituisca la voce senza sapere di chi
e'. E' scritto anche in `biblioteca.py`, e vale la pena scriverlo due volte.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import sessione
from ..models import Utente
from . import biblioteca
from .identita import utente_corrente

router = APIRouter(prefix="/{lingua_url}", include_in_schema=False)


def _indietro(request: Request, lingua: str) -> str:
    """Dove tornare dopo aver premuto un bottone.

    Si torna da dove si e' arrivati, non a una pagina fissa: chi toglie una
    voce stando in fondo alla cronologia vuole ritrovarsi li', non in cima
    alla home.
    """
    venuto = request.headers.get("referer") or ""
    # solo indirizzi nostri: un Referer arriva dal browser e un browser puo'
    # dire qualunque cosa, compreso un sito dove mandare la gente
    if venuto.startswith(str(request.base_url).rstrip("/")):
        return venuto
    return f"/{lingua}/"


@router.post("/preferito")
async def preferito(
    request: Request,
    lingua_url: str,
    url: str = Form(...),
    titolo: str = Form(""),
    piattaforma: str = Form(""),
    utente: Utente = Depends(utente_corrente),
    db: AsyncSession = Depends(sessione),
) -> Response:
    """Mette o toglie dai preferiti.

    Risponde in due modi, e serve: al javascript restituisce lo stato nuovo,
    cosi' la stella si accende sul posto e **la pagina non si ricarica** - su
    una pagina che sta suonando un video, ricaricare vuol dire farlo
    ripartire da capo per una stella.

    A un modulo mandato senza javascript risponde con il solito rimbalzo,
    perche' quello e' l'unico modo che ha di vedere il risultato.
    """
    adesso = await biblioteca.preferito(db, utente.id, url, titolo, piattaforma)
    if "application/json" in (request.headers.get("accept") or ""):
        return JSONResponse({"preferito": adesso})
    return RedirectResponse(_indietro(request, lingua_url), status_code=303)


@router.post("/voce/{voce_id}/rinomina")
async def rinomina(
    request: Request,
    lingua_url: str,
    voce_id: uuid.UUID,
    titolo: str = Form(...),
    utente: Utente = Depends(utente_corrente),
    db: AsyncSession = Depends(sessione),
) -> Response:
    await biblioteca.rinomina(db, utente.id, voce_id, titolo)
    return RedirectResponse(_indietro(request, lingua_url), status_code=303)


@router.post("/voce/{voce_id}/elimina")
async def elimina(
    request: Request,
    lingua_url: str,
    voce_id: uuid.UUID,
    utente: Utente = Depends(utente_corrente),
    db: AsyncSession = Depends(sessione),
) -> Response:
    await biblioteca.elimina(db, utente.id, voce_id)
    return RedirectResponse(_indietro(request, lingua_url), status_code=303)


@router.post("/posizione")
async def posizione(
    url: str = Form(...),
    secondi: float = Form(...),
    durata: float = Form(0.0),
    utente: Utente = Depends(utente_corrente),
    db: AsyncSession = Depends(sessione),
) -> Response:
    """Dove si e' arrivati. La manda il lettore, non una persona.

    Risponde 204 e non un redirect: chi chiama e' `sendBeacon`, che parte
    mentre la pagina si chiude e non guarda la risposta. Un redirect sarebbe
    lavoro fatto per nessuno.
    """
    await biblioteca.segna_posizione(db, utente.id, url, secondi,
                                     durata or None)
    return Response(status_code=204)
