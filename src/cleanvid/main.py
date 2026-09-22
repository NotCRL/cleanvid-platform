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


@asynccontextmanager
async def ciclo_vita(app: FastAPI) -> AsyncIterator[None]:
    # Il motore del database si apre alla prima richiesta, non qui: cosi' il
    # processo parte anche se Postgres non e' ancora su, e chi sviluppa non
    # deve avere tutto acceso per vedere una pagina statica.
    yield
    await chiudi()
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

    from .api import routes_watch
    app.include_router(routes_watch.router)
    # in arrivo: biblioteca, stanze, websocket delle stanze

    app.mount("/static", StaticFiles(directory="src/cleanvid/web/static"),
              name="static")
    return app


app = crea_app()
