"""La roba di ognuno: preferiti, fonti, gruppi, continua a guardare.

Il filo di tutti questi test e' uno solo, ed e' lo stesso del passo 1: **la
roba di uno non si vede e non si tocca da un altro**. Qui pero' ci sono anche
i bottoni che cancellano, quindi non basta che l'elenco sia separato: deve
essere impossibile cancellare la voce di un altro conoscendone l'id.
"""

from __future__ import annotations

import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from cleanvid.api import biblioteca
from cleanvid.main import app
from cleanvid.models import Genere, Utente, VoceBiblioteca
from cleanvid.web.pagine import mm_ss


async def _utente(db: AsyncSession, nome: str = "Prova 1") -> Utente:
    u = Utente(nome_visibile=nome)
    db.add(u)
    await db.flush()
    return u


# --------------------------------------------------------------------------
# preferiti
# --------------------------------------------------------------------------

async def test_la_stella_si_accende_e_si_spegne(db: AsyncSession) -> None:
    """Un bottone solo per entrambe le direzioni: due rotte separate
    sbaglierebbero con due schede aperte."""
    u = await _utente(db)
    assert await biblioteca.preferito(db, u.id, "https://tale/1") is True
    await db.flush()
    assert await biblioteca.preferito(db, u.id, "https://tale/1") is False


async def test_quali_preferiti_in_una_query_sola(db: AsyncSession) -> None:
    u = await _utente(db)
    await biblioteca.preferito(db, u.id, "https://tale/1")
    await biblioteca.preferito(db, u.id, "https://tale/3")
    await db.flush()
    quali = await biblioteca.quali_preferiti(
        db, u.id, ["https://tale/1", "https://tale/2", "https://tale/3"])
    assert quali == {"https://tale/1", "https://tale/3"}


async def test_i_preferiti_di_uno_non_sono_di_un_altro(db: AsyncSession) -> None:
    uno, due = await _utente(db, "Uno"), await _utente(db, "Due")
    await biblioteca.preferito(db, uno.id, "https://tale/1")
    await db.flush()
    assert await biblioteca.quali_preferiti(db, due.id, ["https://tale/1"]) == set()


# --------------------------------------------------------------------------
# fonti e gruppi
# --------------------------------------------------------------------------

async def test_una_fonte_salva_anche_le_intestazioni(db: AsyncSession) -> None:
    """Senza il Referer la fonte risponde 403, ed e' peggio di non averla:
    fa credere di averla."""
    u = await _utente(db)
    voce = await biblioteca.salva_fonte(
        db, u.id, "https://cdn.tale/live.m3u8",
        {"Referer": "https://tale/"}, nome="la diretta", pagina="https://tale/p")
    assert voce.dati["intestazioni"]["Referer"] == "https://tale/"
    assert voce.dati["pagina"] == "https://tale/p"
    assert voce.genere is Genere.FONTE


async def test_risalvare_un_gruppo_con_lo_stesso_nome_lo_sovrascrive(
        db: AsyncSession) -> None:
    """Chi risistema il proprio muro e lo risalva si aspetta di averne uno."""
    u = await _utente(db)
    await biblioteca.salva_gruppo(db, u.id, "Sera", ["a", "b"])
    await biblioteca.salva_gruppo(db, u.id, "sera", ["a", "b", "c"])
    await db.flush()
    gruppi = await biblioteca.elenco(db, u.id, Genere.GRUPPO)
    assert len(gruppi) == 1
    assert gruppi[0].dati["celle"] == ["a", "b", "c"]


async def test_un_gruppo_tiene_al_massimo_quattro_celle(db: AsyncSession) -> None:
    u = await _utente(db)
    voce = await biblioteca.salva_gruppo(db, u.id, "troppi",
                                         ["a", "b", "c", "d", "e", "f"])
    assert len(voce.dati["celle"]) == 4


# --------------------------------------------------------------------------
# continua a guardare
# --------------------------------------------------------------------------

async def test_l_appena_cominciato_non_e_da_riprendere(db: AsyncSession) -> None:
    u = await _utente(db)
    await biblioteca.annota_visita(db, u.id, "https://tale/1")
    await biblioteca.segna_posizione(db, u.id, "https://tale/1", 8.0, 600.0)
    await db.flush()
    assert await biblioteca.da_riprendere(db, u.id) == []


async def test_il_finito_non_e_da_riprendere(db: AsyncSession) -> None:
    """Vedersi riproporre come «continua» un video guardato fino in fondo e'
    il genere di dettaglio che fa sembrare stupido un programma."""
    u = await _utente(db)
    await biblioteca.annota_visita(db, u.id, "https://tale/1")
    await biblioteca.segna_posizione(db, u.id, "https://tale/1", 595.0, 600.0)
    await db.flush()
    assert await biblioteca.da_riprendere(db, u.id) == []


async def test_il_lasciato_a_meta_si_riprende(db: AsyncSession) -> None:
    u = await _utente(db)
    await biblioteca.annota_visita(db, u.id, "https://tale/1")
    await biblioteca.segna_posizione(db, u.id, "https://tale/1", 300.0, 600.0)
    await db.flush()
    sospesi = await biblioteca.da_riprendere(db, u.id)
    assert [v.url for v in sospesi] == ["https://tale/1"]
    assert biblioteca.riprendi_da(sospesi[0]) == 300.0


async def test_in_diretta_non_si_riprende(db: AsyncSession) -> None:
    """Non si torna a dove si era: si va al bordo, che nel frattempo si e' mosso."""
    voce = VoceBiblioteca(utente_id=uuid.uuid4(), genere=Genere.CRONOLOGIA,
                          url="x", posizione=300.0, durata=None)
    assert biblioteca.riprendi_da(voce, diretta=True) == 0.0
    assert biblioteca.riprendi_da(voce, diretta=False) == 300.0


# --------------------------------------------------------------------------
# potatura e limiti
# --------------------------------------------------------------------------

async def test_la_cronologia_non_cresce_all_infinito(db: AsyncSession) -> None:
    """Un elenco infinito e' un posto dove le cose si perdono, non si ritrovano."""
    u = await _utente(db)
    tetto = biblioteca.QUANTI[Genere.CRONOLOGIA]
    for n in range(tetto + 15):
        await biblioteca.annota_visita(db, u.id, f"https://tale/{n}")
        await db.flush()
        await biblioteca.pota(db, u.id, Genere.CRONOLOGIA)
    await db.flush()
    assert len(await biblioteca.elenco(db, u.id, quante=500)) == tetto


# --------------------------------------------------------------------------
# le rotte, e chi puo' toccare cosa
# --------------------------------------------------------------------------

async def test_non_si_cancella_la_voce_di_un_altro(
        visitatore: AsyncClient) -> None:
    """Il test piu' importante di questo file.

    Uno apre un video, l'altro prova a cancellarlo conoscendone l'id. Se
    questo passasse, basterebbe cambiare un numero nell'indirizzo per
    svuotare la cronologia di chiunque.
    """
    await visitatore.post("/it/apri", data={"url": "https://vimeo.com/76979871"})
    pagina = (await visitatore.get("/it/")).text
    import re
    trovato = re.search(r"/voce/([0-9a-f-]{36})/elimina", pagina)
    assert trovato, "la home non mostra il bottone per togliere"
    voce_id = trovato.group(1)

    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://prova",
                           follow_redirects=True) as estraneo:
        await estraneo.post(f"/it/voce/{voce_id}/elimina")

    # la voce di chi l'ha aperta e' ancora li'
    assert "vimeo.com/76979871" in (await visitatore.get("/it/")).text


async def test_il_proprietario_invece_la_cancella(visitatore: AsyncClient) -> None:
    await visitatore.post("/it/apri", data={"url": "https://vimeo.com/76979871"})
    import re
    pagina = (await visitatore.get("/it/")).text
    voce_id = re.search(r"/voce/([0-9a-f-]{36})/elimina", pagina).group(1)
    await visitatore.post(f"/it/voce/{voce_id}/elimina")
    assert "vimeo.com/76979871" not in (await visitatore.get("/it/")).text


async def test_la_stella_dalla_pagina_del_video(visitatore: AsyncClient) -> None:
    indirizzo = "https://vimeo.com/76979871"
    await visitatore.post("/it/preferito", data={"url": indirizzo,
                                                 "titolo": "una prova"})
    home = (await visitatore.get("/it/")).text
    assert "una prova" in home
    assert 'aria-pressed="true"' in home


async def test_il_beacon_della_posizione_risponde_senza_corpo(
        visitatore: AsyncClient) -> None:
    """Chi chiama e' sendBeacon mentre la pagina si chiude: non guarda la
    risposta, e un redirect sarebbe lavoro per nessuno."""
    await visitatore.post("/it/apri", data={"url": "https://vimeo.com/76979871"})
    r = await visitatore.post("/it/posizione", data={
        "url": "https://vimeo.com/76979871", "secondi": "120.5",
        "durata": "600"})
    assert r.status_code == 204
    assert "Continua a guardare" in (await visitatore.get("/it/")).text


async def test_il_referer_di_un_altro_sito_non_porta_via(
        visitatore: AsyncClient) -> None:
    """Un Referer arriva dal browser, e un browser puo' dire qualunque cosa."""
    r = await visitatore.post(
        "/it/preferito", data={"url": "https://tale/1"},
        headers={"Referer": "https://sito-cattivo.tale/"},
        follow_redirects=False)
    assert r.headers["location"] == "/it/"


# --------------------------------------------------------------------------
# le copertine
# --------------------------------------------------------------------------

async def test_una_copertina_senza_firma_viene_rifiutata(
        visitatore: AsyncClient) -> None:
    """Senza, `/copertina?u=<qualunque cosa>` ci fa scaricare quello che pare."""
    r = await visitatore.get("/copertina",
                             params={"u": "https://ovunque.tale/x.jpg", "s": "no"})
    assert r.status_code == 403


def test_il_tempo_si_legge_come_lo_legge_una_persona() -> None:
    assert mm_ss(0) == "0:00"
    assert mm_ss(None) == "0:00"
    assert mm_ss(67) == "1:07"
    assert mm_ss(3661) == "1:01:01"
