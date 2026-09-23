"""Entrare, registrarsi, uscire.

La pagina e' una sola, con due moduli: chi ha gia' un conto entra, chi non ce
l'ha se lo fa. Tenerli separati in due pagine vorrebbe dire far scegliere una
strada prima di sapere quale serve, e per meta' della gente e' quella
sbagliata.

**Registrarsi non crea un utente nuovo**: attacca email e password alla riga
che c'e' gia'. Chi ha usato il sito per mezz'ora e poi si registra non perde
niente, perche' non c'e' niente da spostare.

**Entrare invece cambia riga**, e quello che c'era nella sessione anonima
resta dov'era. Non si travasa: su un computer prestato, ereditare la
cronologia di chi lo ha usato prima sarebbe una sorpresa sgradevole - e le
sorprese, quando riguardano la roba delle persone, si evitano anche a costo
di essere meno comodi.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_303_SEE_OTHER

from ..db import sessione
from ..models import TipoUtente, Utente
from ..web.pagine import modelli
from . import credenziali
from .contesto import Contesto, contesto
from .identita import scrivi_cookie, utente_corrente

router = APIRouter(prefix="/{lingua_url}", include_in_schema=False)


@router.get("/entra", response_class=HTMLResponse)
async def pagina(
    request: Request,
    guaio: str = "",
    c: Contesto = Depends(contesto),
) -> Response:
    return modelli.TemplateResponse(request, "entra.html", {
        "c": c, "t": c.t, "utente": c.utente, "guaio": guaio,
        "minimo": credenziali.MINIMO_PASSWORD,
    })


def _torna(lingua: str, guaio: str = "") -> Response:
    dove = f"/{lingua}/entra" + (f"?guaio={guaio}" if guaio else "")
    return RedirectResponse(dove, status_code=HTTP_303_SEE_OTHER)


@router.post("/registrati")
async def registrati(
    lingua_url: str,
    email: str = Form(...),
    password: str = Form(...),
    utente: Utente = Depends(utente_corrente),
    db: AsyncSession = Depends(sessione),
) -> Response:
    """Attacca le credenziali alla riga che c'e' gia'."""
    if utente.e_registrato:
        return _torna(lingua_url, "gia_registrato")

    indirizzo = credenziali.normalizza(email)
    if "@" not in indirizzo or len(indirizzo) < 5:
        return _torna(lingua_url, "email_strana")

    try:
        utente.password_hash = credenziali.impronta(password)
    except credenziali.NonValida as e:
        return _torna(lingua_url, e.motivo)

    utente.email = indirizzo
    utente.tipo = TipoUtente.REGISTRATO
    db.add(utente)
    try:
        await db.flush()
    except IntegrityError:
        # l'unico vincolo che puo' saltare qui e' l'unicita' dell'email: si
        # lascia dire al database invece di andarla a cercare prima, perche'
        # fra il controllo e la scrittura ci sta un'altra registrazione
        await db.rollback()
        return _torna(lingua_url, "email_usata")

    return RedirectResponse(f"/{lingua_url}/", status_code=HTTP_303_SEE_OTHER)


@router.post("/accedi")
async def accedi(
    lingua_url: str,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(sessione),
) -> Response:
    """Cambia la riga a cui il cookie rimanda."""
    indirizzo = credenziali.normalizza(email)
    if await credenziali.troppi_tentativi(indirizzo):
        return _torna(lingua_url, "troppi_tentativi")

    trovato = (await db.execute(
        select(Utente).where(Utente.email == indirizzo))).scalar_one_or_none()

    # la verifica si fa comunque, anche quando non c'e' nessuno da verificare:
    # se no il tempo di risposta direbbe quali indirizzi sono registrati
    giusta = credenziali.verifica(password, trovato.password_hash if trovato else None)

    if not giusta or trovato is None or trovato.bloccato:
        await credenziali.segna_tentativo(indirizzo)
        return _torna(lingua_url, "credenziali")

    if credenziali.va_riscritta(trovato.password_hash or ""):
        # e' l'unico momento in cui si ha in mano la password in chiaro
        trovato.password_hash = credenziali.impronta(password)
        db.add(trovato)

    await credenziali.dimentica_tentativi(indirizzo)
    risposta = RedirectResponse(f"/{lingua_url}/", status_code=HTTP_303_SEE_OTHER)
    scrivi_cookie(risposta, trovato.id)
    return risposta


@router.post("/esci")
async def esci(lingua_url: str) -> Response:
    """Si toglie il cookie, e basta.

    Chi torna riceve un utente anonimo nuovo, come la prima volta. La riga del
    conto resta dov'era con tutto quello che aveva: uscire non e' cancellarsi.
    """
    risposta = RedirectResponse(f"/{lingua_url}/", status_code=HTTP_303_SEE_OTHER)
    risposta.delete_cookie("cv_id", path="/")
    return risposta
