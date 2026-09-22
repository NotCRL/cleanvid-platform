"""Il punto di ingresso.

Qui dentro non c'e' logica: solo il montaggio dei pezzi. Se un giorno questo
file cresce, vuol dire che qualcosa e' finito nel posto sbagliato.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

from .api.identita import DA_MARCARE, scrivi_cookie
from .config import impostazioni
from .db import chiudi
from .media import deposito, proxy


@asynccontextmanager
async def ciclo_vita(app: FastAPI) -> AsyncIterator[None]:
    # Il motore del database si apre alla prima richiesta, non qui: cosi' il
    # processo parte anche se Postgres non e' ancora su, e chi sviluppa non
    # deve avere tutto acceso per vedere una pagina statica.
    yield
    await chiudi()
    # le connessioni tenute aperte apposta vanno restituite a mano: senza,
    # uvicorn aspetta il timeout prima di morire a ogni ricarica
    await proxy.chiudi()
    await deposito.chiudi()
    # quando ci saranno le stanze, qui vanno avvisate prima di sparire:
    # await app.state.hub.chiudi_tutto()


def crea_app() -> FastAPI:
    cfg = impostazioni()
    app = FastAPI(
        title="cleanvid",
        docs_url=None if cfg.in_produzione else "/docs",
        lifespan=ciclo_vita,
    )

    @app.middleware("http")
    async def consegna_cookie(
        request: Request,
        chiama_avanti: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Attacca il cookie dell'utente nuovo alla risposta che parte davvero.

        La dipendenza che crea l'utente non puo' farlo da se': quando una
        rotta restituisce una pagina o un redirect, gli header messi
        sull'oggetto Response iniettato vengono persi. Qui invece la risposta
        e' quella vera, qualunque forma abbia.
        """
        risposta = await chiama_avanti(request)
        nuovo = getattr(request.state, DA_MARCARE, None)
        if nuovo is not None:
            scrivi_cookie(risposta, nuovo)
        return risposta

    # L'ordine conta. Starlette prende la prima rotta che combacia, e
    # `/{lingua_url}/` combacia anche con `/robots.txt` - che diventerebbe una
    # lingua inesistente e risponderebbe 404. Le rotte senza lingua vanno
    # registrate prima. E' il tipo di errore che nessuno nota finche' non si
    # guarda perche' il sito non compare su Google.
    from .api import (
        routes_biblioteca,
        routes_copertina,
        routes_flusso,
        routes_seo,
        routes_watch,
    )
    app.mount("/static", StaticFiles(directory="src/cleanvid/web/static"),
              name="static")
    app.include_router(routes_flusso.router)
    app.include_router(routes_copertina.router)
    app.include_router(routes_seo.router)
    app.include_router(routes_biblioteca.router)
    app.include_router(routes_watch.router)
    # in arrivo: stanze e websocket delle stanze
    return app


app = crea_app()
