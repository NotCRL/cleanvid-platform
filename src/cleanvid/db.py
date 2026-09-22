"""La connessione al database.

Una sola fabbrica di sessioni per tutto il processo: aprire un motore per
richiesta vorrebbe dire rifare il pool di connessioni ogni volta, che e' il
modo piu' rapido di mettere in ginocchio Postgres sotto carico.

La sessione invece vive quanto la richiesta: nasce all'inizio, si chiude alla
fine, e se qualcosa esplode nel mezzo torna indietro da sola.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import impostazioni

_motore: AsyncEngine | None = None
_sessioni: async_sessionmaker[AsyncSession] | None = None


def motore() -> AsyncEngine:
    global _motore
    if _motore is None:
        cfg = impostazioni()
        _motore = create_async_engine(
            cfg.database_url,
            # in sviluppo si vogliono vedere le query; in produzione sarebbero
            # rumore, e finirebbero nei log con dentro i dati delle persone
            echo=not cfg.in_produzione,
            pool_size=10,
            max_overflow=20,
            # una connessione ferma da un'ora puo' essere gia' stata chiusa
            # dall'altra parte: meglio verificarla che scoprirlo a meta' query
            pool_pre_ping=True,
        )
    return _motore


def fabbrica() -> async_sessionmaker[AsyncSession]:
    global _sessioni
    if _sessioni is None:
        _sessioni = async_sessionmaker(
            motore(),
            expire_on_commit=False,   # dopo il commit gli oggetti restano usabili
            autoflush=False,
        )
    return _sessioni


async def sessione() -> AsyncIterator[AsyncSession]:
    """Dipendenza FastAPI: una sessione per richiesta."""
    async with fabbrica()() as s:
        try:
            yield s
            await s.commit()
        except Exception:
            await s.rollback()
            raise


async def chiudi() -> None:
    """Alla chiusura del processo: si restituiscono le connessioni."""
    global _motore, _sessioni
    if _motore is not None:
        await _motore.dispose()
    _motore = None
    _sessioni = None
