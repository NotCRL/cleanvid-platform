"""Ambiente delle migrazioni.

L'indirizzo del database arriva dalle impostazioni, non dal file .ini: esiste
un posto solo dove cambiarlo, e nessuno rischia di far girare una migrazione
sul database sbagliato perche' due file dicevano cose diverse.

I modelli si importano tutti, altrimenti `--autogenerate` non vede le tabelle
che non sono state caricate e propone allegramente di cancellarle.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

from cleanvid.config import impostazioni
from cleanvid.models import Base  # noqa: F401  (importa tutte le tabelle)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", impostazioni().database_url)
target_metadata = Base.metadata


def esegui_migrazioni_offline() -> None:
    """Genera l'SQL senza collegarsi: utile per farlo rivedere a qualcuno."""
    context.configure(
        url=impostazioni().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _migra(connessione) -> None:
    context.configure(
        connection=connessione,
        target_metadata=target_metadata,
        # senza questo un cambio di tipo passa inosservato e il disallineamento
        # si scopre in produzione
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def esegui_migrazioni_online() -> None:
    motore = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,     # una migrazione non ha bisogno di un pool
    )
    async with motore.connect() as connessione:
        await connessione.run_sync(_migra)
    await motore.dispose()


if context.is_offline_mode():
    esegui_migrazioni_offline()
else:
    asyncio.run(esegui_migrazioni_online())
