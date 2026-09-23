"""Le stanze: aprirne una, entrarci, e non entrarci.

Quello che questi test tengono fermo non è la sincronia - quella la misura un
orologio, non un'asserzione - ma **chi può fare cosa**: chi comanda, chi
guarda, chi non entra affatto. È la parte che, se si rompe, si rompe in
silenzio: la stanza continua a funzionare benissimo, solo per le persone
sbagliate.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cleanvid.api.routes_stanze import MASSIMO_PER_UTENTE
from cleanvid.main import app
from cleanvid.models import MessaggioStanza, Stanza
from cleanvid.rooms import codici
from cleanvid.rooms.hub import Presente


@pytest.fixture
async def altro() -> AsyncIterator[AsyncClient]:
    """Una seconda persona: un secondo browser, con i suoi cookie."""
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://prova",
                           follow_redirects=True) as c:
        yield c


async def _apri(cliente: AsyncClient, **campi: str) -> str:
    """Apre una stanza e restituisce il codice, letto dall'indirizzo dove si
    è finiti: è l'unico posto dove il codice arriva a chi l'ha aperta."""
    dati = {"titolo": "Prova", "visibilita": "non_in_elenco"}
    dati.update(campi)
    r = await cliente.post("/it/stanze/apri", data=dati)
    assert r.status_code == 200
    return str(r.url).rsplit("/", 1)[-1].split("?")[0]


# --------------------------------------------------------------------------
# i codici
# --------------------------------------------------------------------------

def test_un_codice_si_puo_dettare_al_telefono() -> None:
    codice = codici.nuovo()
    colore, cosa, numero = codice.split("-")
    assert colore.isalpha() and cosa.isalpha()
    assert 10 <= int(numero) <= 99


def test_si_scartano_gli_indirizzi_inventati() -> None:
    assert codici.plausibile("verde-corsa-42")
    assert not codici.plausibile("a")                    # troppo corto
    assert not codici.plausibile("x" * 49)               # troppo lungo
    assert not codici.plausibile("../../etc/passwd")     # e soprattutto questo


# --------------------------------------------------------------------------
# aprire
# --------------------------------------------------------------------------

async def test_chi_apre_la_stanza_la_comanda(visitatore: AsyncClient) -> None:
    codice = await _apri(visitatore, titolo="Serata film")
    pagina = (await visitatore.get(f"/it/stanza/{codice}")).text
    assert codice in pagina
    assert "Serata film" in pagina


async def test_chi_entra_non_comanda_e_non_chiude(
    visitatore: AsyncClient, altro: AsyncClient
) -> None:
    """La differenza fra padrone e ospite non può stare solo nella pagina:
    un bottone che non si vede si chiama lo stesso a mano."""
    codice = await _apri(visitatore)

    assert (await altro.get(f"/it/stanza/{codice}")).status_code == 200
    r = await altro.post(f"/it/stanza/{codice}/chiudi")
    assert r.status_code == 404

    # e la stanza è ancora aperta per chi l'ha fatta
    assert (await visitatore.get(f"/it/stanza/{codice}")).status_code == 200


async def test_solo_il_padrone_cambia_quello_che_si_guarda(
    visitatore: AsyncClient, altro: AsyncClient
) -> None:
    codice = await _apri(visitatore)
    suo = "https://vimeo.com/76979871"
    intruso = "https://vimeo.com/000000"

    await altro.get(f"/it/stanza/{codice}?u={intruso}")
    assert intruso not in (await visitatore.get(f"/it/stanza/{codice}")).text

    await visitatore.get(f"/it/stanza/{codice}?u={suo}")
    assert suo in (await altro.get(f"/it/stanza/{codice}")).text


async def test_non_si_possono_aprire_stanze_all_infinito(
    visitatore: AsyncClient,
) -> None:
    for _ in range(MASSIMO_PER_UTENTE):
        await _apri(visitatore)
    r = await visitatore.post("/it/stanze/apri", data={"titolo": "una di troppo"})
    assert "guaio=troppe" in str(r.url)


# --------------------------------------------------------------------------
# l'elenco
# --------------------------------------------------------------------------

async def test_nell_elenco_ci_vanno_solo_le_pubbliche(
    visitatore: AsyncClient, altro: AsyncClient
) -> None:
    nascosta = await _apri(visitatore, visibilita="non_in_elenco")
    in_piazza = await _apri(visitatore, visibilita="pubblica")

    elenco = (await altro.get("/it/stanze")).text
    assert in_piazza in elenco
    assert nascosta not in elenco
    # ma col codice ci si entra lo stesso: non in elenco non vuol dire chiusa
    assert (await altro.get(f"/it/stanza/{nascosta}")).status_code == 200


async def test_una_stanza_chiusa_non_si_apre_piu(
    visitatore: AsyncClient, altro: AsyncClient
) -> None:
    codice = await _apri(visitatore)
    await visitatore.post(f"/it/stanza/{codice}/chiudi")
    assert (await altro.get(f"/it/stanza/{codice}")).status_code == 404


# --------------------------------------------------------------------------
# la password
# --------------------------------------------------------------------------

async def test_senza_password_non_si_vede_niente_della_stanza(
    visitatore: AsyncClient, altro: AsyncClient
) -> None:
    codice = await _apri(visitatore, titolo="Riservata",
                         password="la parola giusta",
                         url="https://vimeo.com/76979871")

    r = await altro.get(f"/it/stanza/{codice}")
    assert r.status_code == 403
    # il titolo si vede - serve a capire di essere nel posto giusto -
    # ma quello che si sta guardando no
    assert "Riservata" in r.text
    assert "vimeo.com/76979871" not in r.text


async def test_la_password_giusta_apre_e_resta_aperta(
    visitatore: AsyncClient, altro: AsyncClient
) -> None:
    codice = await _apri(visitatore, password="la parola giusta")

    r = await altro.post(f"/it/stanza/{codice}/entra",
                         data={"password": "quella sbagliata"})
    assert "sbagliata" in str(r.url)

    r = await altro.post(f"/it/stanza/{codice}/entra",
                         data={"password": "la parola giusta"})
    assert r.status_code == 200
    # e la seconda volta non la richiede: si diventa membri una volta sola
    assert (await altro.get(f"/it/stanza/{codice}")).status_code == 200


async def test_chi_ha_aperto_la_stanza_non_si_chiede_la_password(
    visitatore: AsyncClient,
) -> None:
    codice = await _apri(visitatore, password="la parola giusta")
    assert (await visitatore.get(f"/it/stanza/{codice}")).status_code == 200


# --------------------------------------------------------------------------
# la chat
# --------------------------------------------------------------------------

def test_il_freno_alla_raffica_si_apre_da_solo() -> None:
    """Non è una punizione: è un freno. Passata la finestra si riscrive."""
    from cleanvid.rooms.protocol import CHAT_FINESTRA, CHAT_RAFFICA

    chi = Presente(ws=None, utente_id=uuid.uuid4(), nome="tale")  # type: ignore[arg-type]
    assert all(chi.puo_scrivere(100.0) for _ in range(CHAT_RAFFICA))
    assert not chi.puo_scrivere(100.0)
    assert chi.puo_scrivere(100.0 + CHAT_FINESTRA + 0.1)


async def test_chi_entra_a_meta_serata_legge_da_dove_si_e_arrivati(
    visitatore: AsyncClient, altro: AsyncClient, db: AsyncSession
) -> None:
    codice = await _apri(visitatore)
    stanza = (await db.execute(
        select(Stanza).where(Stanza.codice == codice))).scalar_one()
    db.add(MessaggioStanza(stanza_id=stanza.id, autore_nome="tale",
                           testo="siamo al minuto dieci"))
    await db.commit()

    assert "siamo al minuto dieci" in (await altro.get(f"/it/stanza/{codice}")).text


async def test_quello_che_scrive_uno_non_diventa_codice_per_gli_altri(
    visitatore: AsyncClient, altro: AsyncClient, db: AsyncSession
) -> None:
    """L'unico posto del sito dove il testo di una persona finisce sullo
    schermo di un'altra. Se salta questo, salta tutto il resto con lui."""
    codice = await _apri(visitatore)
    stanza = (await db.execute(
        select(Stanza).where(Stanza.codice == codice))).scalar_one()
    db.add(MessaggioStanza(stanza_id=stanza.id, autore_nome="<b>furbo</b>",
                           testo="<script>alert(1)</script>"))
    await db.commit()

    pagina = (await altro.get(f"/it/stanza/{codice}")).text
    assert "<script>alert(1)</script>" not in pagina
    assert "&lt;script&gt;" in pagina
    assert "<b>furbo</b>" not in pagina


async def test_la_chat_di_una_stanza_non_si_legge_senza_password(
    visitatore: AsyncClient, altro: AsyncClient, db: AsyncSession
) -> None:
    codice = await _apri(visitatore, password="la parola giusta")
    stanza = (await db.execute(
        select(Stanza).where(Stanza.codice == codice))).scalar_one()
    db.add(MessaggioStanza(stanza_id=stanza.id, autore_nome="tale",
                           testo="una cosa privata"))
    await db.commit()

    assert "una cosa privata" not in (await altro.get(f"/it/stanza/{codice}")).text
