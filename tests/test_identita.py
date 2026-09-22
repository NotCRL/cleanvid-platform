"""Quello che il passo 1 deve dimostrare, e che non deve poter regredire.

Un test per ogni affermazione fatta nell'architettura: chi arriva e' subito un
utente, il cookie lo riporta alla sua riga, e due persone non si vedono la
roba a vicenda.

Il terzo test esiste per un bug vero, trovato a mano il 22/09/2026: il cookie
non partiva perche' FastAPI perde gli header messi sull'oggetto Response
iniettato quando la rotta restituisce una pagina. Ogni richiesta creava un
utente nuovo. Nessun test lo avrebbe fermato, perche' non c'era.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from cleanvid.api import routes_watch
from cleanvid.api.identita import COOKIE
from cleanvid.main import app
from cleanvid.media.estrazione import Estratto, NonEstraibile


async def test_chi_arriva_e_subito_un_utente(visitatore: AsyncClient) -> None:
    risposta = await visitatore.get("/")
    assert risposta.status_code == 200
    assert COOKIE in visitatore.cookies, "senza cookie nessuno ritrova le sue cose"


async def test_il_cookie_riporta_alla_stessa_riga(visitatore: AsyncClient) -> None:
    prima = await visitatore.get("/stato")
    dopo = await visitatore.get("/stato")
    # la pagina di stato scrive l'identificativo: due visite, stesso utente
    assert _identificativo(prima.text) == _identificativo(dopo.text)


async def test_due_browser_due_biblioteche(visitatore: AsyncClient) -> None:
    """Il cuore del passo 1: la separazione per utente.

    Uno apre un video, l'altro non deve vederlo. Se questo test passa, la
    biblioteca per persona regge; se fallisce, non serve andare avanti.
    """
    await visitatore.post("/apri", data={"url": "https://youtu.be/kJQP7kiw5Fk"})
    sua_home = (await visitatore.get("/")).text
    assert "kJQP7kiw5Fk" in sua_home

    async with AsyncClient(
        transport=ASGITransport(app=app),   # stessa applicazione, altro browser
        base_url="http://prova",
        follow_redirects=True,
    ) as estraneo:
        altra_home = (await estraneo.get("/")).text
        assert "kJQP7kiw5Fk" not in altra_home
        assert "Ancora niente" in altra_home


async def test_riaprire_non_duplica(visitatore: AsyncClient) -> None:
    """Una cronologia con dieci volte lo stesso video non serve a nessuno.

    Si contano i collegamenti, non le volte che l'indirizzo compare nel testo:
    ogni voce lo scrive due volte (una nel collegamento, una come titolo
    provvisorio finche' non c'e' un titolo vero), e contare quelle avrebbe
    fatto fallire il test con il codice giusto.
    """
    indirizzo = "https://vimeo.com/76979871"
    for _ in range(3):
        await visitatore.post("/apri", data={"url": indirizzo})
    assert (await visitatore.get("/")).text.count('href="/guarda?u=') == 1


async def test_il_lettore_ufficiale_viene_montato(visitatore: AsyncClient) -> None:
    pagina = (await visitatore.get(
        "/guarda", params={"u": "https://www.youtube.com/watch?v=kJQP7kiw5Fk"})).text
    assert "youtube.com/embed/kJQP7kiw5Fk" in pagina


async def test_un_sito_da_cui_non_esce_niente_lo_dice(
        visitatore: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Niente pagina bianca: si riporta il motivo, quello vero.

    L'estrazione si finge invece di farla davvero: chiamare yt-dlp qui
    vorrebbe dire test che dipendono dalla rete, dalla versione di yt-dlp e
    dall'umore del sito. Quello che si vuole provare e' che il motivo arriva
    fino alla pagina, e per quello basta un errore finto.
    """
    async def non_va(url: str, qualita: str = "") -> object:
        raise NonEstraibile("video privato")

    monkeypatch.setattr(routes_watch, "risolvi", non_va)
    pagina = (await visitatore.get(
        "/guarda", params={"u": "https://esempio.invalido/video/1"})).text
    assert "non è uscito un video" in pagina
    assert "video privato" in pagina


async def test_il_lettore_si_monta_su_quello_che_esce_dall_estrazione(
        visitatore: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Le due tracce separate devono arrivare al browser come due elementi."""
    async def finge(url: str, qualita: str = "") -> Estratto:
        return Estratto(token="tv", token_audio="ta", titolo="Prova",
                        altezza=720)

    monkeypatch.setattr(routes_watch, "risolvi", finge)
    pagina = (await visitatore.get(
        "/guarda", params={"u": "https://esempio.invalido/video/1"})).text
    assert 'data-flusso="/flusso/tv"' in pagina
    assert 'data-audio="/flusso/ta"' in pagina
    assert "<audio" in pagina
    assert "due tracce" in pagina


async def test_indirizzo_senza_protocollo(visitatore: AsyncClient) -> None:
    """L'errore piu' comune di chi incolla: si completa invece di rifiutare."""
    risposta = await visitatore.post(
        "/apri", data={"url": "youtube.com/watch?v=kJQP7kiw5Fk"})
    assert "youtube.com/embed/kJQP7kiw5Fk" in risposta.text


def _identificativo(html: str) -> str:
    for riga in html.splitlines():
        if "identificativo" in riga:
            return riga
    raise AssertionError("la pagina di stato non mostra l'identificativo")
