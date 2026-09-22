"""Attrezzatura comune ai test.

I test parlano con l'applicazione vera, non con finti pezzi: quello che va
dimostrato - che due persone vedono due biblioteche diverse - passa per il
cookie, per il middleware e per il database, e un finto a meta' strada
dimostrerebbe solo che il finto funziona.

Si usa un database a parte: i test cancellano le tabelle a ogni giro, e farlo
su quello di sviluppo vorrebbe dire perdere le proprie cose ogni volta.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest

# prima di importare qualunque cosa del progetto: le impostazioni si leggono
# all'import, e un database di prova va scelto adesso
os.environ.setdefault("CLEANVID_SEGRETO", "segreto-di-prova-lungo-abbastanza-32")
os.environ["CLEANVID_DATABASE_URL"] = os.environ.get(
    "CLEANVID_DATABASE_URL_TEST",
    "postgresql+asyncpg://cleanvid:cleanvid@localhost/cleanvid_test",
)
# stessa ragione per Redis: i test lo svuotano, e svuotare quello di sviluppo
# vorrebbe dire staccare il video a chi sta guardando mentre si prova
os.environ["CLEANVID_REDIS_URL"] = os.environ.get(
    "CLEANVID_REDIS_URL_TEST", "redis://localhost:6379/15")

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402
from starlette.requests import Request  # noqa: E402

from cleanvid.db import fabbrica, motore  # noqa: E402
from cleanvid.main import app  # noqa: E402
from cleanvid.media import deposito, proxy  # noqa: E402
from cleanvid.models import Base  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
async def tabelle() -> AsyncIterator[None]:
    """Tabelle create una volta per sessione, e via alla fine."""
    async with motore().begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
    yield
    async with motore().begin() as c:
        await c.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def visitatore() -> AsyncIterator[AsyncClient]:
    """Un browser: tiene i suoi cookie, come farebbe una persona."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://prova",
        follow_redirects=True,
    ) as c:
        yield c


@pytest.fixture(autouse=True)
async def redis_pulito() -> AsyncIterator[None]:
    """Ogni test parte da un Redis vuoto.

    I token dei flussi hanno una scadenza lunga apposta, quindi senza questo
    un test si troverebbe fra i piedi i flussi registrati da quello prima, e
    un fallimento vero sembrerebbe un successo.
    """
    await deposito.cliente().flushdb()
    yield


@pytest.fixture
async def sito_finto(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Un sito da cui il proxy va a prendere i byte, servito su HTTP vero.

    Non e' una finzione dentro il proxy: e' un'applicazione ASGI con cui httpx
    parla come parlerebbe con la rete, con lo stesso streaming, lo stesso
    Range e le stesse intestazioni. Il bug che ha reso necessari questi test
    stava proprio nel modo in cui httpx consegna i byte: una finzione piu' in
    su non lo avrebbe visto.
    """
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse, Response, StreamingResponse
    from starlette.routing import Route

    from tests.test_flusso import VIDEO_FINTO

    async def video(request: Request) -> Response:
        intervallo = request.headers.get("range")
        if intervallo:
            da, a = intervallo.removeprefix("bytes=").split("-")
            inizio, fine = int(da), int(a)
            pezzo = VIDEO_FINTO[inizio:fine + 1]
            return Response(pezzo, status_code=206, media_type="video/mp4",
                            headers={"Content-Range":
                                     f"bytes {inizio}-{fine}/{len(VIDEO_FINTO)}"})

        async def a_pezzi() -> AsyncIterator[bytes]:
            for i in range(0, len(VIDEO_FINTO), 65536):
                yield VIDEO_FINTO[i:i + 65536]

        return StreamingResponse(a_pezzi(), media_type="video/mp4")

    async def lista(request: Request) -> Response:
        return PlainTextResponse(
            "#EXTM3U\n#EXTINF:4.0,\npezzo0.ts\n",
            media_type="application/vnd.apple.mpegurl")

    async def bugiardo(request: Request) -> Response:
        # etichettato come playlist ma non lo e': e' il caso di googlevideo
        return Response(b"non sono una playlist",
                        media_type="application/vnd.apple.mpegurl")

    async def protetto(request: Request) -> Response:
        if not request.headers.get("referer"):
            return PlainTextResponse("vietato", status_code=403)
        return Response(b"eccolo", media_type="video/mp4")

    finto = Starlette(routes=[
        Route("/video.mp4", video),
        Route("/lista.m3u8", lista),
        Route("/bugiardo.ts", bugiardo),
        Route("/protetto.mp4", protetto),
    ])

    async with AsyncClient(transport=ASGITransport(app=finto)) as c:
        monkeypatch.setattr(proxy, "_cliente", c)
        yield


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    """Una sessione, per i test che parlano con la biblioteca senza passare
    da una pagina. Si annulla tutto alla fine: un test non deve lasciare in
    giro le righe del test prima."""
    async with fabbrica()() as s:
        yield s
        await s.rollback()


@pytest.fixture(autouse=True)
def niente_ytdlp(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nessun test lancia yt-dlp, nemmeno di rimbalzo.

    Senza questo i test che aprono una pagina video finiscono per estrarre
    davvero: la suite passa da un secondo a trenta, dipende dalla rete, dalla
    versione di yt-dlp e dall'umore del sito, e un giorno fallisce per un
    motivo che non ha niente a che fare con il codice.

    Chi vuole provare il caso in cui l'estrazione fallisce se lo rimette a
    modo suo, che e' esattamente quello che fanno i test di quel caso.
    """
    from cleanvid.api import routes_muro, routes_watch
    from cleanvid.media.estrazione import Estratto

    async def finta(url: str, qualita: str = "") -> Estratto:
        return Estratto(token="finto", titolo="Video di prova",
                        altezza=int(qualita) if qualita.isdigit() else 720)

    monkeypatch.setattr(routes_watch, "risolvi", finta)
    monkeypatch.setattr(routes_muro, "risolvi", finta)


@pytest.fixture(autouse=True)
def niente_sponsorblock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stessa ragione: e' un servizio di qualcun altro, su internet."""
    from cleanvid.api import routes_watch

    async def nessuno(url: str) -> list[list[float]]:
        return []

    monkeypatch.setattr(routes_watch, "segmenti", nessuno)
