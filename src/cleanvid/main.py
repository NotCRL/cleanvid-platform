"""Il punto di ingresso.

Qui dentro non c'e' logica: solo il montaggio dei pezzi. Se un giorno questo
file cresce, vuol dire che qualcosa e' finito nel posto sbagliato.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import impostazioni


@asynccontextmanager
async def ciclo_vita(app: FastAPI):
    # connessioni aperte una volta sola, non a ogni richiesta
    # app.state.db = await apri_database()
    # app.state.redis = await apri_redis()
    yield
    # chiusura pulita: le stanze aperte vanno avvisate prima di sparire
    # await app.state.hub.chiudi_tutto()


def crea_app() -> FastAPI:
    cfg = impostazioni()
    app = FastAPI(
        title="cleanvid",
        docs_url=None if cfg.in_produzione else "/docs",
        lifespan=ciclo_vita,
    )

    # from .api import routes_watch, routes_library, routes_rooms, ws_rooms
    # app.include_router(routes_watch.router)
    # app.include_router(routes_library.router, prefix="/biblioteca")
    # app.include_router(routes_rooms.router, prefix="/stanze")
    # app.include_router(ws_rooms.router)

    app.mount("/static", StaticFiles(directory="src/cleanvid/web/static"),
              name="static")
    return app


app = crea_app()
