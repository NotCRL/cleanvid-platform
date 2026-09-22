"""La roba di ognuno: preferiti, fonti, gruppi, continua a guardare.

Il filo di tutti questi test e' uno solo, ed e' lo stesso del passo 1: **la
roba di uno non si vede e non si tocca da un altro**. Qui pero' ci sono anche
i bottoni che cancellano, quindi non basta che l'elenco sia separato: deve
essere impossibile cancellare la voce di un altro conoscendone l'id.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from cleanvid.api import biblioteca, routes_muro, routes_watch
from cleanvid.main import app
from cleanvid.media.estrazione import Estratto, NonEstraibile
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


# --------------------------------------------------------------------------
# lo stile portato dal file unico
# --------------------------------------------------------------------------

def test_il_nome_di_una_voce_senza_titolo_e_il_sito() -> None:
    """Senza questo le iniziali del riquadro venivano dall'indirizzo: «hv»
    per un link di Vimeo, cioe' le prime lettere di «https» e «vimeo»."""
    from cleanvid.web.pagine import iniziali, nome_voce

    class Finta:
        titolo = ""
        url = "https://www.vimeo.com/76979871"

    assert nome_voce(Finta()) == "vimeo.com"
    assert iniziali(nome_voce(Finta())) == "vc"

    class ConTitolo(Finta):
        titolo = "Despacito ft. Daddy Yankee"

    assert nome_voce(ConTitolo()) == "Despacito ft. Daddy Yankee"
    # «Df» e non «Dd»: «ft.» conta come parola. E' il comportamento del file
    # unico, portato qui tale e quale; se un giorno dara' fastidio si
    # salteranno le paroline, ma allora sara' una decisione, non una svista.
    assert iniziali(nome_voce(ConTitolo())) == "Df"


def test_la_tinta_di_una_voce_non_cambia_mai() -> None:
    """E' meta' del motivo per cui un elenco si riconosce con la coda
    dell'occhio: lo stesso canale ha sempre lo stesso riquadro."""
    from cleanvid.web.pagine import tinta

    assert tinta("Sky News") == tinta("Sky News")
    assert tinta("Sky News") != tinta("Rai News")
    assert 0 <= tinta("") < 360


async def test_la_pagina_usa_il_foglio_di_stile_del_progetto(
        visitatore: AsyncClient) -> None:
    """Niente stile in linea: e' un file solo, che il browser tiene in cache."""
    pagina = (await visitatore.get("/it/")).text
    assert '<link rel=stylesheet href="/static/stile.css">' in pagina
    assert "<style>" not in pagina


async def test_il_tema_si_applica_prima_del_disegno(
        visitatore: AsyncClient) -> None:
    """Con `defer` si vedrebbe la pagina cambiare colore a ogni caricamento."""
    pagina = (await visitatore.get("/it/")).text
    testa = pagina.split("<main", 1)[0]
    assert '<script src="/static/tema.js"></script>' in testa
    assert "defer" not in testa


async def test_le_schede_hanno_il_markup_a_cui_parla_lo_stile(
        visitatore: AsyncClient) -> None:
    await visitatore.post("/it/apri", data={"url": "https://vimeo.com/76979871"})
    pagina = (await visitatore.get("/it/")).text
    for pezzo in ("class=shelf", 'class="rack scorre"', "class=vcard",
                  "class=vgo", "class=poster", "class=mono", "class=vtitle"):
        assert pezzo in pagina, pezzo


async def test_la_copertina_non_blocca_la_pagina(visitatore: AsyncClient) -> None:
    """Il server dice subito no e la cerca in disparte: cercarla puo' costare
    venticinque secondi di yt-dlp, e con venti voci sarebbe una home ferma."""
    await visitatore.post("/it/apri", data={"url": "https://vimeo.com/76979871"})
    pagina = (await visitatore.get("/it/")).text
    # `data-copertina` e non `src`: la mette il javascript quando c'e'
    assert "data-copertina=" in pagina
    assert 'src="/copertina' not in pagina


# --------------------------------------------------------------------------
# il muro
# --------------------------------------------------------------------------

async def test_il_muro_si_apre(visitatore: AsyncClient) -> None:
    pagina = (await visitatore.get("/it/muro")).text
    for pezzo in ("id=wall", "id=grid", "id=addform", "window.MURO",
                  "window.TESTI", "/static/muro.js"):
        assert pezzo in pagina, pezzo
    # fuori dall'indice: e' uno strumento, non una pagina da trovare cercando
    assert 'content="noindex,nofollow"' in pagina


async def test_una_cella_e_solo_il_lettore(
        visitatore: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Niente testata, niente piede: dentro un riquadro darebbero fastidio
    e ruberebbero spazio al video."""
    async def finge(url: str, qualita: str = "") -> Estratto:
        return Estratto(token="tv", titolo="Prova")

    monkeypatch.setattr(routes_muro, "risolvi", finge)
    pagina = (await visitatore.get(
        "/it/cella", params={"u": "https://www.youtube.com/watch?v=kJQP7kiw5Fk"})).text
    assert "/static/cella.js" in pagina
    assert "class=testata" not in pagina
    assert "class=foot" not in pagina


async def test_nel_muro_vince_il_lettore_nostro(
        visitatore: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fuori dal muro vince quello della piattaforma; dentro no.

    Dentro un riquadro il lettore loro porta la sua interfaccia, compreso il
    suo volume, e il muro ne disegna gia' una: due barre per riquadro. E al
    nostro <video> parliamo diretto, quindi «l'audio su un riquadro solo»
    funziona davvero invece che quasi sempre.
    """
    async def finge(url: str, qualita: str = "") -> Estratto:
        return Estratto(token="tv", token_audio="ta", titolo="Prova")

    monkeypatch.setattr(routes_muro, "risolvi", finge)
    pagina = (await visitatore.get(
        "/it/cella", params={"u": "https://www.youtube.com/watch?v=kJQP7kiw5Fk"})).text
    assert 'data-flusso="/flusso/tv"' in pagina
    assert "youtube.com/embed" not in pagina
    # nessun comando nativo: quelli li disegna il muro, e due volumi per
    # riquadro non si capisce quale tocchi
    assert "controls" not in pagina


async def test_se_l_estrazione_fallisce_la_cella_ripiega(
        visitatore: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Meglio il lettore loro che un riquadro vuoto — ma senza i suoi comandi."""
    async def non_va(url: str, qualita: str = "") -> object:
        raise NonEstraibile("niente da fare")

    monkeypatch.setattr(routes_muro, "risolvi", non_va)
    pagina = (await visitatore.get(
        "/it/cella", params={"u": "https://www.youtube.com/watch?v=kJQP7kiw5Fk"})).text
    assert "youtube.com/embed" in pagina
    assert "mute=1" in pagina        # di quattro video se ne ascolta uno
    assert "controls=0" in pagina    # il volume resta uno solo
    assert "enablejsapi=1" in pagina  # o i comandi non arrivano, in silenzio


async def test_una_cella_non_finisce_in_cronologia(visitatore: AsyncClient) -> None:
    """Un muro da quattro, ricaricato, riempirebbe la cronologia ogni volta.

    In cronologia ci va quello che si apre di proposito, non i riquadri.
    """
    await visitatore.get("/it/cella",
                         params={"u": "https://www.youtube.com/watch?v=kJQP7kiw5Fk"})
    assert "kJQP7kiw5Fk" not in (await visitatore.get("/it/")).text


async def test_un_gruppo_si_salva_e_si_rilegge(visitatore: AsyncClient) -> None:
    r = await visitatore.post("/it/gruppo", data={
        "nome": "Sera",
        "celle": '[{"url":"https://vimeo.com/76979871","title":"uno"},'
                 '{"url":"https://youtu.be/kJQP7kiw5Fk","title":"due"}]',
        "colonne": "2", "disposizione": "riga"})
    assert r.json()["ok"] is True
    gruppo_id = r.json()["id"]

    elenco = (await visitatore.get("/it/gruppi.json")).json()["gruppi"]
    assert [g["nome"] for g in elenco] == ["Sera"]
    assert elenco[0]["quanti"] == 2

    uno = (await visitatore.get(f"/it/gruppo/{gruppo_id}.json")).json()
    assert uno["disposizione"] == "riga"
    assert [c["title"] for c in uno["celle"]] == ["uno", "due"]


async def test_il_gruppo_di_un_altro_non_si_legge(visitatore: AsyncClient) -> None:
    """404 e non 403: dire «esiste ma non e' tuo» direbbe a chi prova a
    indovinare un id se ha indovinato."""
    r = await visitatore.post("/it/gruppo", data={
        "nome": "Mio", "celle": '[{"url":"https://vimeo.com/76979871"}]'})
    gruppo_id = r.json()["id"]

    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://prova",
                           follow_redirects=True) as estraneo:
        assert (await estraneo.get(f"/it/gruppo/{gruppo_id}.json")).status_code == 404
        assert (await estraneo.get("/it/gruppi.json")).json()["gruppi"] == []


async def test_un_gruppo_non_tiene_piu_di_quattro_celle(
        visitatore: AsyncClient) -> None:
    celle = [{"url": f"https://tale/{n}"} for n in range(9)]
    import json as _json
    r = await visitatore.post("/it/gruppo", data={
        "nome": "Troppi", "celle": _json.dumps(celle)})
    uno = (await visitatore.get(f"/it/gruppo/{r.json()['id']}.json")).json()
    assert len(uno["celle"]) == 4


async def test_quello_che_arriva_dal_browser_non_si_copia_intero(
        visitatore: AsyncClient) -> None:
    """Si tiene solo indirizzo e titolo. Copiare il resto vorrebbe dire
    salvare qualunque cosa a qualcuno venga in mente di mandare."""
    r = await visitatore.post("/it/gruppo", data={
        "nome": "Furbo",
        "celle": '[{"url":"https://vimeo.com/1","title":"ok",'
                 '"sorpresa":"non deve restare","admin":true}]'})
    uno = (await visitatore.get(f"/it/gruppo/{r.json()['id']}.json")).json()
    assert set(uno["celle"][0]) == {"url", "title"}


async def test_un_indirizzo_che_non_e_un_indirizzo_viene_scartato(
        visitatore: AsyncClient) -> None:
    r = await visitatore.post("/it/gruppo", data={
        "nome": "Niente", "celle": '[{"url":"javascript:alert(1)"}]'})
    assert r.status_code == 400
    assert r.json()["ok"] is False


async def test_i_testi_del_muro_arrivano_al_javascript(
        visitatore: AsyncClient) -> None:
    """Il muro costruisce la sua interfaccia da se': senza questi, i bottoni
    avrebbero per etichetta il nome della chiave."""
    import json as _json
    import re as _re
    pagina = (await visitatore.get("/ja/muro")).text
    grezzo = _re.search(r"window\.TESTI = (\{.*?\});", pagina, _re.S)
    assert grezzo
    testi_js = _json.loads(grezzo.group(1))
    assert testi_js["muro.pieno.t"] == "いっぱいです"
    # si manda solo quello che serve, non tutto il catalogo
    assert "home.faq.1.r" not in testi_js


async def test_una_cella_parte_muta(
        visitatore: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Quattro video che partono insieme con l'audio non si ascoltano.

    Chi decide quale suona e' il muro, dopo, a video gia' avviato.
    """
    async def finge(url: str, qualita: str = "") -> Estratto:
        return Estratto(token="tv", titolo="Prova")

    monkeypatch.setattr(routes_muro, "risolvi", finge)
    pagina = (await visitatore.get(
        "/it/cella", params={"u": "https://vimeo.com/76979871"})).text
    assert "<video" in pagina and " muted" in pagina


async def test_fuori_dal_muro_il_video_non_parte_muto(
        visitatore: AsyncClient) -> None:
    """Una pagina sola: l'audio si vuole subito, non dopo un clic."""
    pagina = (await visitatore.get(
        "/it/guarda", params={"u": "https://www.youtube.com/watch?v=kJQP7kiw5Fk"})).text
    assert "mute=1" not in pagina


# --------------------------------------------------------------------------
# la scelta fra il lettore loro e il nostro
# --------------------------------------------------------------------------

async def test_il_predefinito_e_il_lettore_della_piattaforma(
        visitatore: AsyncClient) -> None:
    """Parte subito e non scade mai: e' quello che non delude."""
    pagina = (await visitatore.get(
        "/it/guarda", params={"u": "https://www.youtube.com/watch?v=kJQP7kiw5Fk"})).text
    assert "youtube.com/embed" in pagina
    # ma la strada per l'altro deve essere in vista
    assert "m=diretto" in pagina


async def test_il_lettore_pulito_si_puo_chiedere(
        visitatore: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Su YouTube il lettore ufficiale vincerebbe sempre: senza questa strada
    lo SponsorBlock e il piccolo schermo non si userebbero mai."""
    async def finge(url: str, qualita: str = "") -> Estratto:
        return Estratto(token="tv", titolo="Prova", altezza=1080)

    monkeypatch.setattr(routes_watch, "risolvi", finge)
    pagina = (await visitatore.get("/it/guarda", params={
        "u": "https://www.youtube.com/watch?v=kJQP7kiw5Fk",
        "m": "diretto"})).text
    assert "youtube.com/embed" not in pagina
    assert 'data-flusso="/flusso/tv"' in pagina
    # e la strada per tornare indietro
    assert "Lettore della piattaforma" in pagina


async def test_cambiare_qualita_non_fa_tornare_al_lettore_loro(
        visitatore: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Il modulo della qualita' deve portarsi dietro `m`, o al primo cambio
    si torna nel lettore della piattaforma senza averlo chiesto."""
    async def finge(url: str, qualita: str = "") -> Estratto:
        return Estratto(token="tv", titolo="Prova")

    monkeypatch.setattr(routes_watch, "risolvi", finge)
    pagina = (await visitatore.get("/it/guarda", params={
        "u": "https://www.youtube.com/watch?v=kJQP7kiw5Fk",
        "m": "diretto"})).text
    assert '<input type=hidden name=m value=diretto>' in pagina


async def test_i_segmenti_da_saltare_arrivano_al_lettore(
        visitatore: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def finge(url: str, qualita: str = "") -> Estratto:
        return Estratto(token="tv", titolo="Prova")

    async def finti_segmenti(url: str) -> list[list[float]]:
        return [[0.0, 21.8], [249.4, 281.5]]

    monkeypatch.setattr(routes_watch, "risolvi", finge)
    monkeypatch.setattr(routes_watch, "segmenti", finti_segmenti)
    pagina = (await visitatore.get("/it/guarda", params={
        "u": "https://www.youtube.com/watch?v=kJQP7kiw5Fk",
        "m": "diretto"})).text
    assert "249.4" in pagina and "21.8" in pagina


def test_sponsorblock_si_chiede_solo_a_youtube() -> None:
    """Per ogni altro sito sarebbe una richiesta buttata: SponsorBlock non
    sa niente di loro."""
    from cleanvid.media.annunci import video_youtube

    assert video_youtube("https://youtu.be/kJQP7kiw5Fk") == "kJQP7kiw5Fk"
    assert video_youtube("https://www.youtube.com/watch?v=kJQP7kiw5Fk") == "kJQP7kiw5Fk"
    assert video_youtube("https://vimeo.com/76979871") == ""


# --------------------------------------------------------------------------
# la chat delle dirette
# --------------------------------------------------------------------------

async def test_la_chat_c_e_solo_se_e_una_diretta(
        visitatore: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Il `live_chat` di YouTube su un video registrato apre un riquadro con
    dentro un errore, che e' peggio di niente."""
    async def registrazione(url: str, qualita: str = "") -> Estratto:
        return Estratto(token="tv", titolo="Prova", diretta=False)

    monkeypatch.setattr(routes_muro, "risolvi", registrazione)
    pagina = (await visitatore.get(
        "/it/cella", params={"u": "https://www.youtube.com/watch?v=kJQP7kiw5Fk"})).text
    assert "id=chat" not in pagina

    async def diretta(url: str, qualita: str = "") -> Estratto:
        return Estratto(token="tv", titolo="Prova", diretta=True, hls=True)

    monkeypatch.setattr(routes_muro, "risolvi", diretta)
    pagina = (await visitatore.get(
        "/it/cella", params={"u": "https://www.youtube.com/watch?v=kJQP7kiw5Fk"})).text
    assert "id=chat" in pagina
    assert "youtube.com/live_chat" in pagina


async def test_la_chat_non_si_carica_finche_non_la_chiedi(
        visitatore: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Quattro chat sempre accese in un muro da quattro sono quattro
    connessioni aperte che nessuno sta leggendo."""
    async def diretta(url: str, qualita: str = "") -> Estratto:
        return Estratto(token="tv", titolo="Prova", diretta=True)

    monkeypatch.setattr(routes_muro, "risolvi", diretta)
    pagina = (await visitatore.get(
        "/it/cella", params={"u": "https://www.twitch.tv/unaltro"})).text
    # l'indirizzo sta in un attributo a parte, l'iframe parte vuoto
    assert 'data-chat="https://www.twitch.tv/embed/' in pagina
    assert "<iframe title=\"chat\"></iframe>" in pagina


def test_la_chat_dichiara_il_dominio_da_cui_si_apre() -> None:
    """Twitch e YouTube rifiutano l'iframe se non combacia: `parent` per
    l'uno, `embed_domain` per l'altro. E' lo stesso inciampo del lettore."""
    from cleanvid.media.embed import chat_incorporabile

    twitch = chat_incorporabile("https://www.twitch.tv/tale", "cleanvid.example")
    assert twitch is not None
    assert "parent=cleanvid.example" in twitch
    assert "parent=localhost" in twitch      # cosi' vale anche in casa

    youtube = chat_incorporabile("https://youtu.be/kJQP7kiw5Fk", "cleanvid.example")
    assert youtube is not None
    assert "embed_domain=cleanvid.example" in youtube

    # un sito qualunque non ha una chat da incorniciare
    assert chat_incorporabile("https://vimeo.com/76979871", "x") is None
    # e nemmeno una registrazione di Twitch
    assert chat_incorporabile("https://www.twitch.tv/videos/12345", "x") is None


async def test_nella_pagina_del_video_la_chat_sta_di_fianco(
        visitatore: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sopra coprirebbe il video, ed e' esattamente quello che questo sito toglie."""
    async def diretta(url: str, qualita: str = "") -> Estratto:
        return Estratto(token="tv", titolo="Prova", diretta=True)

    monkeypatch.setattr(routes_watch, "risolvi", diretta)
    pagina = (await visitatore.get("/it/guarda", params={
        "u": "https://www.twitch.tv/unaltro", "m": "diretto"})).text
    assert 'class="conchat"' in pagina
    assert "<aside class=chat>" in pagina
