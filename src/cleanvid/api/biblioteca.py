"""Le voci di ognuno: leggere e scrivere, sempre filtrando per utente.

Una regola sola, e vale per ogni query di questo file e di quelli che
verranno: **`utente_id` nel filtro, non nella fiducia**. Non esiste una
funzione che prenda un id di voce e la restituisca senza sapere di chi e':
sarebbe il giorno in cui qualcuno legge la cronologia di un altro cambiando
un numero nell'indirizzo.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Genere, VoceBiblioteca


async def annota_visita(
    db: AsyncSession,
    utente_id: uuid.UUID,
    url: str,
    titolo: str = "",
    piattaforma: str = "",
) -> VoceBiblioteca:
    """Segna che questo utente ha aperto questo link.

    Riaprire la stessa cosa non aggiunge una riga: aggiorna quella che c'e' e
    la riporta in cima. Una cronologia con dieci volte lo stesso video non
    serve a nessuno.

    Il titolo scelto a mano non viene sovrascritto: chi ha rinominato una voce
    non se la vede tornare com'era alla prossima apertura.
    """
    comando = (
        insert(VoceBiblioteca)
        .values(utente_id=utente_id, genere=Genere.CRONOLOGIA, url=url,
                titolo=titolo, piattaforma=piattaforma)
        .on_conflict_do_update(
            index_elements=["utente_id", "genere", "url"],
            set_={"aggiornata": func.now()},
            where=VoceBiblioteca.titolo_tuo.is_(False),
        )
        .returning(VoceBiblioteca)
    )
    voce = (await db.execute(comando)).scalar_one()
    # il titolo automatico si aggiorna solo se non e' stato scelto a mano
    if titolo and not voce.titolo_tuo and voce.titolo != titolo:
        voce.titolo = titolo
    if piattaforma and not voce.piattaforma:
        voce.piattaforma = piattaforma
    return voce


async def elenco(
    db: AsyncSession,
    utente_id: uuid.UUID,
    genere: Genere = Genere.CRONOLOGIA,
    quante: int = 24,
) -> Sequence[VoceBiblioteca]:
    """Le voci di questo utente, dalla piu' recente."""
    query = (
        select(VoceBiblioteca)
        .where(VoceBiblioteca.utente_id == utente_id,
               VoceBiblioteca.genere == genere)
        .order_by(VoceBiblioteca.aggiornata.desc())
        .limit(quante)
    )
    return (await db.execute(query)).scalars().all()


async def segna_posizione(
    db: AsyncSession,
    utente_id: uuid.UUID,
    url: str,
    posizione: float,
    durata: float | None = None,
) -> None:
    """Dove si era arrivati, per la ripresa.

    Arriva spesso: al passo delle stanze questo traffico finira' in Redis
    (vedi ARCHITETTURA.md). Finche' l'utente e' uno, il database regge.
    """
    query = select(VoceBiblioteca).where(
        VoceBiblioteca.utente_id == utente_id,
        VoceBiblioteca.genere == Genere.CRONOLOGIA,
        VoceBiblioteca.url == url,
    )
    voce = (await db.execute(query)).scalar_one_or_none()
    if voce is None:
        return
    voce.posizione = posizione
    if durata:
        voce.durata = durata
