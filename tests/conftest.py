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

from httpx import ASGITransport, AsyncClient  # noqa: E402

from cleanvid.db import motore  # noqa: E402
from cleanvid.main import app  # noqa: E402
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
