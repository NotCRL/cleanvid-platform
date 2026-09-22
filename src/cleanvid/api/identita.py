"""Chi sta guardando.

Qui si applica la decisione presa in `models/user.py`: **anonimo e registrato
sono la stessa riga**. Chi arriva senza fare niente riceve un utente vero, con
un id vero, e un cookie firmato che lo riporta a quella riga. La sua
cronologia e i suoi preferiti esistono da subito; registrarsi, un giorno,
attacchera' delle credenziali a quella riga senza portargli via niente.

Il cookie contiene solo l'id, firmato. Non e' cifrato: chi lo legge vede un
UUID e nient'altro. E' firmato perche' nessuno possa scriversi l'id di un
altro, che e' la sola cosa che conta.
"""

from __future__ import annotations

import random
import uuid

from fastapi import Depends, Request, Response
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import impostazioni
from ..db import sessione
from ..models import TipoUtente, Utente

COOKIE = "cv_id"
DURATA_COOKIE = 400 * 24 * 3600   # il massimo che i browser accettano

# Nome di partenza per chi non ne ha uno: in una chat tre "anonimo" non si
# distinguono, e chiedere di scegliere un nome prima ancora di guardare un
# video e' il modo migliore per far chiudere la pagina.
_ANIMALI = ("Riccio", "Lontra", "Falco", "Tasso", "Volpe", "Cervo", "Gufo",
            "Martora", "Airone", "Stambecco", "Puledro", "Rondine")


def nome_di_cortesia() -> str:
    # random normale e non secrets: e' un nome da mostrare in chat, non un
    # segreto; l'identita' sta nel cookie firmato, non qui.
    return f"{random.choice(_ANIMALI)} {random.randint(100, 999)}"  # noqa: S311


def _firma() -> URLSafeSerializer:
    return URLSafeSerializer(impostazioni().segreto, salt="identita")


def _leggi_cookie(request: Request) -> uuid.UUID | None:
    grezzo = request.cookies.get(COOKIE)
    if not grezzo:
        return None
    try:
        return uuid.UUID(_firma().loads(grezzo))
    except (BadSignature, ValueError, TypeError):
        return None   # firma alterata o cookie di un'altra installazione


# Nome dell'attributo su request.state dove la dipendenza lascia detto "a
# questo qui va dato il cookie". Non lo scrive lei: vedi sotto il perche'.
DA_MARCARE = "cv_nuovo_utente"


def scrivi_cookie(response: Response, utente_id: uuid.UUID) -> None:
    cfg = impostazioni()
    response.set_cookie(
        COOKIE,
        _firma().dumps(str(utente_id)),
        max_age=DURATA_COOKIE,
        httponly=True,          # il javascript della pagina non deve leggerlo
        samesite="lax",
        secure=cfg.in_produzione,
        path="/",
    )


async def utente_corrente(
    request: Request,
    db: AsyncSession = Depends(sessione),
) -> Utente:
    """L'utente di questa richiesta. Se non c'e', se ne crea uno.

    Nessuna pagina deve poter essere aperta "senza utente": significherebbe
    avere due modi di fare le cose, uno per chi ce l'ha e uno per chi no.

    Il cookie NON viene scritto qui. Quando una rotta restituisce una risposta
    propria - una pagina, un redirect - FastAPI butta via gli header messi
    sull'oggetto Response iniettato in una dipendenza, e il cookie non parte
    mai: ogni richiesta creerebbe un utente nuovo e nessuno ritroverebbe piu'
    niente. Qui si lascia detto a chi ha in mano la risposta vera, cioe' il
    middleware in main.py.
    """
    identificativo = _leggi_cookie(request)
    if identificativo is not None:
        trovato = await db.get(Utente, identificativo)
        if trovato is not None and not trovato.bloccato:
            return trovato
        # cookie valido ma riga sparita (potatura, database ricreato):
        # se ne fa una nuova invece di rispondere con un errore

    nuovo = Utente(
        tipo=TipoUtente.ANONIMO,
        nome_visibile=nome_di_cortesia(),
    )
    db.add(nuovo)
    await db.flush()          # serve l'id adesso, per il cookie
    setattr(request.state, DA_MARCARE, nuovo.id)
    return nuovo


async def conta_utenti(db: AsyncSession) -> int:
    """Comodo nei test e nella pagina di stato."""
    return len((await db.execute(select(Utente.id))).all())
