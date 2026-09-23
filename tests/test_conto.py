"""Registrarsi, entrare, uscire.

La cosa che questi test devono tenere ferma è la decisione presa il primo
giorno in `models/user.py`: **anonimo e registrato sono la stessa riga**.
Registrarsi non crea un utente nuovo, gli attacca delle credenziali — e chi ha
usato il sito per mezz'ora non perde niente.

È il momento in cui la gente abbandona, e l'unico modo di non sbagliarlo è
non poterlo sbagliare.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from cleanvid.api import credenziali
from cleanvid.main import app


async def _apri_un_video(cliente: AsyncClient, url: str) -> None:
    await cliente.post("/it/apri", data={"url": url})


# --------------------------------------------------------------------------
# registrarsi
# --------------------------------------------------------------------------

async def test_registrarsi_non_fa_perdere_niente(visitatore: AsyncClient) -> None:
    """IL test di questo file.

    Si usa il sito da anonimi, si apre un video, poi ci si registra: quel
    video deve essere ancora lì. Se questo fallisce, la promessa fatta nella
    pagina «entra» è falsa.
    """
    await _apri_un_video(visitatore, "https://vimeo.com/76979871")
    assert "vimeo.com" in (await visitatore.get("/it/")).text

    r = await visitatore.post("/it/registrati", data={
        "email": "tale@esempio.it", "password": "una password lunga"})
    assert r.status_code == 200          # il rimbalzo porta alla home

    assert "vimeo.com" in (await visitatore.get("/it/")).text
    pagina = (await visitatore.get("/it/entra")).text
    assert "tale@esempio.it" in pagina


async def test_l_email_non_si_puo_usare_due_volte(visitatore: AsyncClient) -> None:
    await visitatore.post("/it/registrati", data={
        "email": "uno@esempio.it", "password": "una password lunga"})

    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://prova",
                           follow_redirects=True) as altro:
        r = await altro.post("/it/registrati", data={
            "email": "UNO@Esempio.it", "password": "un'altra password"})
        # maiuscole e minuscole non fanno una email diversa
        assert "email_usata" in str(r.url) or "già un accesso" in r.text


async def test_la_password_corta_si_rifiuta(visitatore: AsyncClient) -> None:
    """Una password lunga batte una password complicata: le regole del tipo
    «una maiuscola, un numero» producono `Password1!` e basta."""
    r = await visitatore.post("/it/registrati", data={
        "email": "corta@esempio.it", "password": "abc"})
    assert "password_corta" in str(r.url)


async def test_non_ci_si_registra_due_volte_sullo_stesso_utente(
        visitatore: AsyncClient) -> None:
    await visitatore.post("/it/registrati", data={
        "email": "due@esempio.it", "password": "una password lunga"})
    r = await visitatore.post("/it/registrati", data={
        "email": "tre@esempio.it", "password": "una password lunga"})
    assert "gia_registrato" in str(r.url)


# --------------------------------------------------------------------------
# entrare
# --------------------------------------------------------------------------

async def test_entrare_riporta_alla_propria_riga(visitatore: AsyncClient) -> None:
    await _apri_un_video(visitatore, "https://vimeo.com/76979871")
    await visitatore.post("/it/registrati", data={
        "email": "torno@esempio.it", "password": "una password lunga"})

    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://prova",
                           follow_redirects=True) as altrove:
        # un altro browser: parte da zero
        assert "vimeo.com" not in (await altrove.get("/it/")).text
        await altrove.post("/it/accedi", data={
            "email": "torno@esempio.it", "password": "una password lunga"})
        # e adesso ritrova la sua roba
        assert "vimeo.com" in (await altrove.get("/it/")).text


async def test_la_sessione_anonima_non_si_travasa(visitatore: AsyncClient) -> None:
    """Su un computer prestato, ereditare la cronologia di chi lo ha usato
    prima sarebbe una sorpresa sgradevole."""
    await visitatore.post("/it/registrati", data={
        "email": "mio@esempio.it", "password": "una password lunga"})

    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://prova",
                           follow_redirects=True) as prestato:
        await _apri_un_video(prestato, "https://vimeo.com/11111111")
        await prestato.post("/it/accedi", data={
            "email": "mio@esempio.it", "password": "una password lunga"})
        # quello che c'era nella sessione anonima resta dov'era
        assert "vimeo.com%2F11111111" not in (await prestato.get("/it/")).text


async def test_password_sbagliata_non_entra(visitatore: AsyncClient) -> None:
    await visitatore.post("/it/registrati", data={
        "email": "chiuso@esempio.it", "password": "una password lunga"})
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://prova",
                           follow_redirects=True) as tentativo:
        r = await tentativo.post("/it/accedi", data={
            "email": "chiuso@esempio.it", "password": "indovinata male"})
        assert "credenziali" in str(r.url)


async def test_un_indirizzo_che_non_esiste_dice_la_stessa_cosa(
        visitatore: AsyncClient) -> None:
    """Lo stesso messaggio della password sbagliata, di proposito: dire
    «questa email non esiste» sarebbe un modo per scoprire chi e' iscritto."""
    r = await visitatore.post("/it/accedi", data={
        "email": "nessuno@esempio.it", "password": "una password lunga"})
    assert "credenziali" in str(r.url)


async def test_dopo_troppi_tentativi_si_aspetta(visitatore: AsyncClient) -> None:
    for _ in range(credenziali.TENTATIVI):
        await visitatore.post("/it/accedi", data={
            "email": "forzato@esempio.it", "password": "sbagliata"})
    r = await visitatore.post("/it/accedi", data={
        "email": "forzato@esempio.it", "password": "sbagliata"})
    assert "troppi_tentativi" in str(r.url)


async def test_entrare_azzera_il_conto_dei_tentativi(
        visitatore: AsyncClient) -> None:
    await visitatore.post("/it/registrati", data={
        "email": "riprovo@esempio.it", "password": "una password lunga"})
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://prova",
                           follow_redirects=True) as c:
        for _ in range(3):
            await c.post("/it/accedi", data={
                "email": "riprovo@esempio.it", "password": "sbagliata"})
        await c.post("/it/accedi", data={
            "email": "riprovo@esempio.it", "password": "una password lunga"})
        assert not await credenziali.troppi_tentativi("riprovo@esempio.it")


# --------------------------------------------------------------------------
# uscire
# --------------------------------------------------------------------------

async def test_uscire_non_e_cancellarsi(visitatore: AsyncClient) -> None:
    await _apri_un_video(visitatore, "https://vimeo.com/76979871")
    await visitatore.post("/it/registrati", data={
        "email": "esco@esempio.it", "password": "una password lunga"})
    await visitatore.post("/it/esci")

    # chi torna e' un anonimo nuovo
    assert "vimeo.com" not in (await visitatore.get("/it/")).text
    # ma la riga del conto e' ancora la' con tutto quello che aveva
    await visitatore.post("/it/accedi", data={
        "email": "esco@esempio.it", "password": "una password lunga"})
    assert "vimeo.com" in (await visitatore.get("/it/")).text


# --------------------------------------------------------------------------
# come si custodiscono le password
# --------------------------------------------------------------------------

def test_la_password_non_si_puo_rileggere() -> None:
    """Argon2 e non sha: anche con il sale, sha si prova a miliardi al secondo
    su una scheda video."""
    custodita = credenziali.impronta("una password lunga")
    assert custodita.startswith("$argon2")
    assert "una password lunga" not in custodita
    assert credenziali.verifica("una password lunga", custodita)
    assert not credenziali.verifica("quasi la stessa", custodita)


def test_due_uguali_danno_impronte_diverse() -> None:
    """Il sale: senza, due persone con la stessa password si riconoscono
    guardando la tabella."""
    assert credenziali.impronta("la stessa password") != credenziali.impronta(
        "la stessa password")


def test_verificare_contro_il_nulla_non_riesce_ma_costa_lo_stesso() -> None:
    """Se non costasse, il tempo di risposta direbbe quali indirizzi sono
    registrati: piu' corto se non c'e', piu' lungo se c'e'."""
    assert not credenziali.verifica("qualunque cosa", None)


def test_l_email_si_normalizza() -> None:
    assert credenziali.normalizza("  Tale@Esempio.IT ") == "tale@esempio.it"


def test_la_password_si_riscrive_se_l_impronta_e_vecchia() -> None:
    """Argon2 alza i suoi parametri nel tempo, e l'unico momento in cui si
    puo' rifare e' quando si ha in mano quella in chiaro."""
    assert credenziali.va_riscritta("non e' nemmeno un hash")
    assert not credenziali.va_riscritta(credenziali.impronta("appena fatta"))


def test_password_corta_solleva() -> None:
    with pytest.raises(credenziali.NonValida):
        credenziali.impronta("corta")
