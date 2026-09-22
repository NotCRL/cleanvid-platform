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

from sqlalchemy import delete, func, or_, select
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


# --------------------------------------------------------------------------
# preferiti, fonti, gruppi
# --------------------------------------------------------------------------
#
# Tutti e tre vivono nella stessa tabella della cronologia, distinti dal
# campo `genere`. La ragione sta in `models/library.py`: hanno gli stessi
# attributi e differiscono solo per il motivo per cui sono li'. Tenerli
# separati vorrebbe dire scrivere tre volte la stessa paginazione, la stessa
# ricerca, la stessa potatura.

# Quanti se ne tengono per genere. Non sono limiti tecnici: sono il punto
# oltre il quale un elenco non si guarda piu', e una cronologia infinita e'
# un posto dove le cose si perdono invece di ritrovarsi.
QUANTI = {
    Genere.CRONOLOGIA: 60,
    Genere.PREFERITO: 80,
    Genere.FONTE: 60,
    Genere.GRUPPO: 40,
}

# Sotto i venti secondi non vale la pena riprendere: si e' appena cominciato.
RIPRENDI_DA = 20.0
# Negli ultimi venticinque il video e' finito, non lasciato a meta'.
RIPRENDI_CODA = 25.0


async def preferito(db: AsyncSession, utente_id: uuid.UUID, url: str,
                    titolo: str = "", piattaforma: str = "") -> bool:
    """Mette o toglie dai preferiti. -> True se adesso c'e'.

    Un solo comando per entrambe le direzioni, perche' nell'interfaccia e' un
    bottone solo: due rotte separate vorrebbero dire che il bottone deve
    sapere lo stato di prima, e sbagliarlo quando due schede sono aperte.
    """
    query = select(VoceBiblioteca).where(
        VoceBiblioteca.utente_id == utente_id,
        VoceBiblioteca.genere == Genere.PREFERITO,
        VoceBiblioteca.url == url)
    gia = (await db.execute(query)).scalar_one_or_none()
    if gia is not None:
        await db.delete(gia)
        return False

    db.add(VoceBiblioteca(utente_id=utente_id, genere=Genere.PREFERITO,
                          url=url, titolo=titolo, piattaforma=piattaforma))
    await pota(db, utente_id, Genere.PREFERITO)
    return True


async def quali_preferiti(db: AsyncSession, utente_id: uuid.UUID,
                          url: Sequence[str]) -> set[str]:
    """Quali di questi indirizzi sono fra i preferiti.

    Una query sola per tutta la pagina, non una per riga: con trenta voci in
    elenco la differenza fra una query e trenta si vede a occhio nudo.
    """
    if not url:
        return set()
    query = select(VoceBiblioteca.url).where(
        VoceBiblioteca.utente_id == utente_id,
        VoceBiblioteca.genere == Genere.PREFERITO,
        VoceBiblioteca.url.in_(url))
    return set((await db.execute(query)).scalars().all())


async def salva_fonte(db: AsyncSession, utente_id: uuid.UUID,
                      flusso: str, intestazioni: dict[str, str],
                      nome: str = "", pagina: str = "") -> VoceBiblioteca:
    """Salva il flusso vero, non la pagina che lo conteneva.

    E' la differenza che conta: la pagina di certi siti cambia indirizzo ogni
    giorno, o pretende che si prema un bottone prima di mostrare il video. Il
    flusso, con le sue intestazioni, si riapre da solo.

    Le intestazioni vanno salvate insieme: senza il `Referer` giusto, quasi
    ogni CDN risponde 403, e una fonte che non si riapre e' peggio di nessuna
    fonte perche' fa credere di averla.
    """
    return await _metti(db, utente_id, Genere.FONTE, flusso,
                        titolo=nome, dati={"intestazioni": dict(intestazioni),
                                           "pagina": pagina})


async def salva_gruppo(db: AsyncSession, utente_id: uuid.UUID, nome: str,
                       celle: Sequence[str], colonne: int = 2) -> VoceBiblioteca:
    """Un gruppo e' l'insieme di video che si aprono insieme, e come stanno.

    La chiave e' il nome: salvare due volte con lo stesso nome sovrascrive
    invece di accumulare. Chi risistema il proprio muro e lo risalva si
    aspetta di averne uno, non due quasi uguali.
    """
    pulito = (nome or "gruppo").strip()[:60]
    return await _metti(
        db, utente_id, Genere.GRUPPO, f"gruppo:{pulito.lower()}",
        titolo=pulito,
        dati={"celle": list(celle)[:4], "colonne": colonne})


async def _metti(db: AsyncSession, utente_id: uuid.UUID, genere: Genere,
                 url: str, titolo: str,
                 dati: dict[str, object]) -> VoceBiblioteca:
    comando = (
        insert(VoceBiblioteca)
        .values(utente_id=utente_id, genere=genere, url=url,
                titolo=titolo, dati=dati)
        .on_conflict_do_update(
            index_elements=["utente_id", "genere", "url"],
            set_={"dati": dati, "titolo": titolo, "aggiornata": func.now()})
        .returning(VoceBiblioteca)
    )
    voce = (await db.execute(comando)).scalar_one()
    await pota(db, utente_id, genere)
    return voce


# --------------------------------------------------------------------------
# modificare e togliere
# --------------------------------------------------------------------------

async def rinomina(db: AsyncSession, utente_id: uuid.UUID,
                   voce_id: uuid.UUID, titolo: str) -> bool:
    """Il titolo scelto a mano vince su quello che trovera' yt-dlp.

    E' quello che significa `titolo_tuo`: chi ha rinominato "il canale di
    nonna" non se lo vede tornare "Live stream #4821" alla prossima apertura.
    """
    voce = await _mia(db, utente_id, voce_id)
    if voce is None:
        return False
    voce.titolo = titolo.strip()[:300]
    voce.titolo_tuo = bool(voce.titolo)
    return True


async def elimina(db: AsyncSession, utente_id: uuid.UUID,
                  voce_id: uuid.UUID) -> bool:
    voce = await _mia(db, utente_id, voce_id)
    if voce is None:
        return False
    await db.delete(voce)
    return True


async def _mia(db: AsyncSession, utente_id: uuid.UUID,
               voce_id: uuid.UUID) -> VoceBiblioteca | None:
    """Una voce per id, ma **solo se e' di chi la chiede**.

    Non esiste in questo file una funzione che prenda un id e restituisca la
    voce senza guardare di chi e'. Sarebbe il giorno in cui qualcuno legge o
    cancella la cronologia di un altro cambiando un numero nell'indirizzo.
    """
    query = select(VoceBiblioteca).where(
        VoceBiblioteca.id == voce_id,
        VoceBiblioteca.utente_id == utente_id)
    return (await db.execute(query)).scalar_one_or_none()


async def pota(db: AsyncSession, utente_id: uuid.UUID, genere: Genere) -> int:
    """Tiene l'elenco entro il suo limite, togliendo dal fondo."""
    tetto = QUANTI[genere]
    troppe = (
        select(VoceBiblioteca.id)
        .where(VoceBiblioteca.utente_id == utente_id,
               VoceBiblioteca.genere == genere)
        .order_by(VoceBiblioteca.aggiornata.desc())
        .offset(tetto)
    )
    id_da_togliere = list((await db.execute(troppe)).scalars().all())
    if not id_da_togliere:
        return 0
    await db.execute(
        delete(VoceBiblioteca).where(VoceBiblioteca.id.in_(id_da_togliere)))
    return len(id_da_togliere)


# --------------------------------------------------------------------------
# continua a guardare
# --------------------------------------------------------------------------

async def da_riprendere(db: AsyncSession, utente_id: uuid.UUID,
                        quante: int = 8) -> Sequence[VoceBiblioteca]:
    """Quello che e' stato lasciato a meta'.

    Fuori restano due cose: l'appena cominciato, perche' riprendere da venti
    secondi non e' riprendere; e il finito, perche' un video guardato fino in
    fondo non e' in sospeso - e vederselo riproposto come "continua" e' il
    genere di dettaglio che fa sembrare stupido un programma.
    """
    query = (
        select(VoceBiblioteca)
        .where(VoceBiblioteca.utente_id == utente_id,
               VoceBiblioteca.genere == Genere.CRONOLOGIA,
               VoceBiblioteca.posizione.is_not(None),
               VoceBiblioteca.posizione >= RIPRENDI_DA,
               # senza durata nota non si puo' dire se e' finito: si tiene,
               # perche' il danno di mostrarlo di troppo e' minore di quello
               # di nasconderlo
               or_(VoceBiblioteca.durata.is_(None),
                   VoceBiblioteca.posizione
                   < VoceBiblioteca.durata - RIPRENDI_CODA))
        .order_by(VoceBiblioteca.aggiornata.desc())
        .limit(quante)
    )
    return (await db.execute(query)).scalars().all()


def riprendi_da(voce: VoceBiblioteca | None, diretta: bool = False) -> float:
    """I secondi da cui ripartire. In diretta non si riprende: si va al bordo."""
    if diretta or voce is None or not voce.posizione:
        return 0.0
    if voce.durata and voce.posizione > voce.durata - RIPRENDI_CODA:
        return 0.0
    return voce.posizione if voce.posizione >= RIPRENDI_DA else 0.0
