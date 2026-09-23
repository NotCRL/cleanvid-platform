"""La roba di ognuno: preferiti, fonti, gruppi, continua a guardare.

Il filo di tutti questi test e' uno solo, ed e' lo stesso del passo 1: **la
roba di uno non si vede e non si tocca da un altro**. Qui pero' ci sono anche
i bottoni che cancellano, quindi non basta che l'elenco sia separato: deve
essere impossibile cancellare la voce di un altro conoscendone l'id.
"""

from __future__ import annotations

import pathlib
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from cleanvid.api import biblioteca, routes_muro, routes_watch
from cleanvid.main import app
from cleanvid.media.estrazione import NonEstraibile
from cleanvid.media.fonte import DIRETTA, HLS, Fonte
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
    async def finge(url: str, qualita: str = "", lingua: str = "en") -> Fonte:
        return Fonte(tipo=DIRETTA, indirizzo="/flusso/tv", token="tv",
                     titolo="Prova")

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
    async def finge(url: str, qualita: str = "", lingua: str = "en") -> Fonte:
        return Fonte(tipo=DIRETTA, indirizzo="/flusso/tv", token="tv",
                     indirizzo_audio="/flusso/ta", token_audio="ta",
                     titolo="Prova")

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
    async def non_va(url: str, qualita: str = "", lingua: str = "en") -> object:
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
    async def finge(url: str, qualita: str = "", lingua: str = "en") -> Fonte:
        return Fonte(tipo=DIRETTA, indirizzo="/flusso/tv", token="tv",
                     titolo="Prova")

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

async def test_il_predefinito_e_il_lettore_nostro(
        visitatore: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Anche dove la piattaforma un lettore ce l'ha.

    E' la scelta che fa funzionare tutto il resto: lo sponsor saltato, il
    piccolo schermo, la ripresa, le tre viste. Dentro l'iframe di un altro
    sito nessuna di quelle cose si puo' fare.
    """
    async def finge(url: str, qualita: str = "", lingua: str = "en") -> Fonte:
        return Fonte(tipo=DIRETTA, indirizzo="/flusso/tv", token="tv",
                     titolo="Prova")

    monkeypatch.setattr(routes_watch, "risolvi", finge)
    pagina = (await visitatore.get(
        "/it/guarda", params={"u": "https://www.youtube.com/watch?v=kJQP7kiw5Fk"})).text
    assert 'data-flusso="/flusso/tv"' in pagina
    assert "youtube.com/embed" not in pagina
    # ma la strada per il loro deve restare in vista
    assert "m=loro" in pagina


async def test_se_l_estrazione_fallisce_si_apre_il_loro(
        visitatore: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """La scelta del predefinito non deve mai costare un video che non parte.

    Meglio il lettore della piattaforma, con la sua pubblicita', che una
    pagina che dice «non e' uscito niente» quando un modo per vederlo c'era.
    """
    async def non_va(url: str, qualita: str = "", lingua: str = "en") -> object:
        raise NonEstraibile("yt-dlp non ce la fa")

    monkeypatch.setattr(routes_watch, "risolvi", non_va)
    pagina = (await visitatore.get(
        "/it/guarda", params={"u": "https://www.youtube.com/watch?v=kJQP7kiw5Fk"})).text
    assert "youtube.com/embed" in pagina
    # e non si spiega un guasto che non c'e' stato
    assert "yt-dlp non ce la fa" not in pagina


async def test_su_un_sito_senza_lettore_il_guasto_si_spiega(
        visitatore: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Li' il ripiego non c'e', quindi il motivo e' l'unica cosa utile."""
    async def non_va(url: str, qualita: str = "", lingua: str = "en") -> object:
        raise NonEstraibile("video privato")

    monkeypatch.setattr(routes_watch, "risolvi", non_va)
    pagina = (await visitatore.get(
        "/it/guarda", params={"u": "https://esempio.invalido/v/1"})).text
    assert "video privato" in pagina


async def test_il_lettore_della_piattaforma_si_puo_chiedere(
        visitatore: AsyncClient) -> None:
    """Resta a un clic, per chi lo preferisce o quando il nostro fa i capricci."""
    pagina = (await visitatore.get("/it/guarda", params={
        "u": "https://www.youtube.com/watch?v=kJQP7kiw5Fk", "m": "loro"})).text
    assert "youtube.com/embed" in pagina
    # e la strada per tornare al nostro
    assert "Lettore pulito" in pagina


async def test_le_tre_viste_ci_sono(
        visitatore: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Normale, cinema, schermo intero: le stesse tre di qualunque sito di
    video, con le stesse scorciatoie."""
    async def finge(url: str, qualita: str = "", lingua: str = "en") -> Fonte:
        return Fonte(tipo=DIRETTA, indirizzo="/flusso/tv", token="tv",
                     titolo="Prova")

    monkeypatch.setattr(routes_watch, "risolvi", finge)
    pagina = (await visitatore.get("/it/guarda", params={
        "u": "https://www.youtube.com/watch?v=kJQP7kiw5Fk"})).text
    for vista in ("normale", "cinema", "solo"):
        assert f'data-vista={vista}' in pagina
    assert "(T)" in pagina
    # la terza non e' lo schermo intero del browser: quello ce l'ha gia' il
    # lettore, ed e' li' che la gente lo cerca
    assert "data-vista=pieno" not in pagina
    assert "(F)" not in pagina
    assert "/static/viste.js" in pagina
    # e da «solo il lettore» si deve poter uscire senza sapere di Escape
    assert 'id=esci-solo' in pagina


async def test_i_segmenti_da_saltare_arrivano_al_lettore(
        visitatore: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def finge(url: str, qualita: str = "", lingua: str = "en") -> Fonte:
        return Fonte(tipo=DIRETTA, indirizzo="/flusso/tv", token="tv",
                     titolo="Prova")

    async def finti_segmenti(url: str) -> list[list[float]]:
        return [[0.0, 21.8], [249.4, 281.5]]

    monkeypatch.setattr(routes_watch, "risolvi", finge)
    monkeypatch.setattr(routes_watch, "segmenti", finti_segmenti)
    pagina = (await visitatore.get("/it/guarda", params={
        "u": "https://www.youtube.com/watch?v=kJQP7kiw5Fk"})).text
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
    async def registrazione(url: str, qualita: str = "", lingua: str = "en") -> Fonte:
        return Fonte(tipo=DIRETTA, indirizzo="/flusso/tv", token="tv",
                     titolo="Prova", diretta=False)

    monkeypatch.setattr(routes_muro, "risolvi", registrazione)
    pagina = (await visitatore.get(
        "/it/cella", params={"u": "https://www.youtube.com/watch?v=kJQP7kiw5Fk"})).text
    assert "id=chat" not in pagina

    async def diretta(url: str, qualita: str = "", lingua: str = "en") -> Fonte:
        return Fonte(tipo=HLS, indirizzo="/flusso/tv", token="tv",
                     titolo="Prova", diretta=True)

    monkeypatch.setattr(routes_muro, "risolvi", diretta)
    pagina = (await visitatore.get(
        "/it/cella", params={"u": "https://www.youtube.com/watch?v=kJQP7kiw5Fk"})).text
    assert "id=chat" in pagina
    assert "youtube.com/live_chat" in pagina


async def test_la_chat_non_si_carica_finche_non_la_chiedi(
        visitatore: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Quattro chat sempre accese in un muro da quattro sono quattro
    connessioni aperte che nessuno sta leggendo."""
    async def diretta(url: str, qualita: str = "", lingua: str = "en") -> Fonte:
        return Fonte(tipo=DIRETTA, indirizzo="/flusso/tv", token="tv",
                     titolo="Prova", diretta=True)

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
    async def diretta(url: str, qualita: str = "", lingua: str = "en") -> Fonte:
        return Fonte(tipo=DIRETTA, indirizzo="/flusso/tv", token="tv",
                     titolo="Prova", diretta=True)

    monkeypatch.setattr(routes_watch, "risolvi", diretta)
    pagina = (await visitatore.get("/it/guarda", params={
        "u": "https://www.twitch.tv/unaltro"})).text
    assert "conchat" in pagina
    assert "<div class=chat>" in pagina
    # la chat prende il posto della lista «da riprendere»: di roba da
    # guardare dopo, durante una diretta, non interessa a nessuno
    assert "class=seguito" not in pagina


# --------------------------------------------------------------------------
# le viste e la forma della pagina
# --------------------------------------------------------------------------

async def test_il_cinema_e_il_predefinito(visitatore: AsyncClient) -> None:
    """Un video si guarda, e la colonna stretta di una pagina di testo non e'
    la forma giusta per guardarlo."""
    pagina = (await visitatore.get(
        "/it/guarda", params={"u": "https://vimeo.com/76979871"})).text
    assert 'class="scena cinema' in pagina


def test_lo_schermo_intero_lo_fa_il_lettore() -> None:
    """Nessuna scorciatoia nostra per lo schermo intero.

    Il bottone ce l'ha gia' il lettore del browser, ed e' li' che la gente lo
    cerca. Una `f` che spalanca lo schermo mentre si sta facendo altro
    sorprende invece di aiutare.

    Si guarda il codice e non la pagina: e' una decisione che vive nel
    javascript, e l'HTML non la dice.
    """
    codice = pathlib.Path("src/cleanvid/web/static/viste.js").read_text()
    assert 'case "f":' not in codice
    assert "requestFullscreen" not in codice


async def test_la_colonna_di_fianco_non_ripropone_questo_video(
        visitatore: AsyncClient) -> None:
    """Riproporre quello che si sta gia' guardando e' l'unica cosa che li'
    non serve."""
    await visitatore.post("/it/apri", data={"url": "https://vimeo.com/76979871"})
    await visitatore.post("/it/apri", data={"url": "https://vimeo.com/11111111"})
    pagina = (await visitatore.get(
        "/it/guarda", params={"u": "https://vimeo.com/76979871"})).text
    dopo = pagina.split("class=seguito", 1)[1] if "class=seguito" in pagina else ""
    assert "vimeo.com%2F11111111" in dopo
    assert "vimeo.com%2F76979871" not in dopo


async def test_il_nome_del_piccolo_schermo_e_quello_vero(
        visitatore: AsyncClient) -> None:
    """«Guarda in un angolo» era una perifrasi: il nome della cosa e' quello,
    e chi lo cerca cerca quello."""
    pagina = (await visitatore.get(
        "/it/guarda", params={"u": "https://vimeo.com/76979871"})).text
    assert "Picture-in-Picture" in pagina
    assert "angolo" not in pagina


async def test_la_chat_del_riquadro_nasce_a_destra(visitatore: AsyncClient) -> None:
    """Sotto mangia l'altezza, e in un muro da quattro l'altezza e' la cosa
    che manca."""
    pagina = (await visitatore.get("/it/muro")).text
    assert 'data-chatdove=destra class=on' in pagina
    assert "data-chatdove=sotto" in pagina


def test_la_cella_non_eredita_la_griglia_della_pagina_del_video() -> None:
    """Una classe generica usata da due posti diversi e' il modo di rompere
    uno aggiustando l'altro.

    `conchat` ce l'hanno sia la cella del muro sia la pagina del video. Una
    regola scritta per la seconda impilava la chat sotto il video nella prima,
    perche' un riquadro e' quasi sempre piu' stretto di 760px.
    """
    foglio = pathlib.Path("src/cleanvid/web/static/stile.css").read_text()
    for riga in foglio.splitlines():
        pulita = riga.strip()
        if pulita.startswith(".conchat"):
            raise AssertionError(f"regola generica su .conchat: {pulita}")


async def test_su_una_diretta_c_e_il_pannello_delle_preferenze(
        visitatore: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Le preferenze di questa pagina stanno in questa pagina: una cosa che
    si vuole provare a occhio non si va a cambiare altrove e poi si torna."""
    async def diretta(url: str, qualita: str = "", lingua: str = "en") -> Fonte:
        return Fonte(tipo=DIRETTA, indirizzo="/flusso/tv", token="tv",
                     titolo="Prova", diretta=True)

    monkeypatch.setattr(routes_watch, "risolvi", diretta)
    pagina = (await visitatore.get("/it/guarda", params={
        "u": "https://www.twitch.tv/unaltro"})).text
    assert "class=preferenze" in pagina
    assert "data-chatdove=fianco class=on" in pagina
    assert "data-chatdove=sotto" in pagina


async def test_senza_chat_il_pannello_ha_comunque_il_bagliore(
        visitatore: AsyncClient) -> None:
    """Il pannello c'e' finche' ha qualcosa da offrire.

    Il bagliore vale su ogni video col lettore nostro; la posizione della
    chat solo sulle dirette. Il pannello mostra quello che si applica, e
    quando non si applica niente non c'e' affatto.
    """
    pagina = (await visitatore.get(
        "/it/guarda", params={"u": "https://vimeo.com/76979871"})).text
    assert "class=preferenze" in pagina
    assert "data-bagliore=acceso" in pagina
    assert "data-chatdove" not in pagina


async def test_col_lettore_della_piattaforma_niente_bagliore(
        visitatore: AsyncClient) -> None:
    """Dentro l'iframe di un'altra piattaforma i fotogrammi non ci sono: e'
    un altro documento, e non c'e' niente da disegnare."""
    pagina = (await visitatore.get("/it/guarda", params={
        "u": "https://www.youtube.com/watch?v=kJQP7kiw5Fk", "m": "loro"})).text
    assert "id=bagliore" not in pagina
    assert "bagliore.js" not in pagina


def test_il_bagliore_disegna_una_tela_minuscola() -> None:
    """Sfocare un'immagine grande costa a ogni fotogramma; ingrandire
    trentadue pixel e' quello che una scheda video fa senza accorgersene.

    E dopo cinquanta pixel di sfocatura i dettagli non ci sono comunque piu',
    quindi a occhio il risultato e' lo stesso.
    """
    codice = pathlib.Path("src/cleanvid/web/static/bagliore.js").read_text()
    assert "const LARGO = 32, ALTO = 18;" in codice
    # e si ferma quando la scheda non si vede: su un portatile e' batteria
    assert "visibilitychange" in codice


def test_solo_il_lettore_resta_dentro_la_pagina() -> None:
    """Non e' lo schermo intero del browser, ed e' voluto: da quello si esce
    solo con Escape o col suo bottone, da qui si torna indietro come da
    qualunque altra cosa."""
    foglio = pathlib.Path("src/cleanvid/web/static/stile.css").read_text()
    assert ".scena.solo{position:fixed" in foglio
    codice = pathlib.Path("src/cleanvid/web/static/viste.js").read_text()
    assert "requestFullscreen" not in codice


def test_in_solo_la_chat_si_accende_solo_con_la_diretta() -> None:
    """Su una registrazione quella colonna sarebbe vuota, e mezzo schermo di
    nero di fianco al video non e' una vista, e' un errore."""
    foglio = pathlib.Path("src/cleanvid/web/static/stile.css").read_text()
    assert ".scena.solo > .accanto{display:none}" in foglio
    assert ".scena.solo.conchat > .accanto{display:flex" in foglio


async def test_una_registrazione_non_ha_la_colonna_della_chat(
        visitatore: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def registrazione(url: str, qualita: str = "", lingua: str = "en") -> Fonte:
        return Fonte(tipo=DIRETTA, indirizzo="/flusso/tv", token="tv",
                     titolo="Prova", diretta=False)

    monkeypatch.setattr(routes_watch, "risolvi", registrazione)
    pagina = (await visitatore.get(
        "/it/guarda", params={"u": "https://www.twitch.tv/unaltro"})).text
    assert "conchat" not in pagina


def test_la_chat_si_allunga_quanto_la_riga() -> None:
    """La griglia ha `align-items: start`, giusto per il titolo e per la
    lista «da riprendere» - roba che comincia in alto e finisce dove finisce.

    Per la chat no: li' vale l'altezza della riga. Con `start` la colonna
    restava alta quanto il suo contenuto, cioe' poco, e in «solo il lettore»
    si vedeva una striscia di chat con sotto mezzo schermo vuoto.
    """
    foglio = pathlib.Path("src/cleanvid/web/static/stile.css").read_text()
    # si corregge sulla colonna, non sulla griglia: `align-items: stretch`
    # avrebbe toccato anche il lettore, che l'altezza se la calcola da 16:9
    assert ".scena.conchat.solo > .accanto{align-self:stretch" in foglio
    assert ".scena.conchat.chat-fianco > .accanto," in foglio
    assert ".scena{display:grid;gap:16px 24px;align-items:start" in foglio


def test_il_pulsante_di_ritorno_del_muro_fa_qualcosa() -> None:
    """In «solo i video» e' l'unica cosa visibile sullo schermo.

    Era nel modello ma senza javascript: un bottone in vista che non fa
    niente e' peggio di un bottone che non c'e', perche' chi lo preme pensa
    di aver sbagliato lui.
    """
    modello = pathlib.Path("src/cleanvid/web/templates/muro.html").read_text()
    codice = pathlib.Path("src/cleanvid/web/static/muro.js").read_text()
    assert 'id=pilota' in modello
    assert 'getElementById("pilota")' in codice
    assert "soloVideo(false)" in codice


def test_con_la_chat_di_fianco_il_titolo_passa_sotto() -> None:
    """«Affiancati» vuol dire alla stessa altezza.

    Tenendo il titolo nella colonna di sinistra, la colonna della chat si
    allungava anche sopra di lui e finiva molto piu' alta del video. Con il
    titolo a tutta larghezza sotto, lettore e chat stanno nella stessa riga e
    la riga e' una sola altezza.
    """
    foglio = pathlib.Path("src/cleanvid/web/static/stile.css").read_text()
    assert ('.scena.chat-fianco{grid-template-areas:"palco accanto" '
            '"principale principale"}') in foglio
    # e con la chat sotto il titolo torna di fianco alla colonna
    assert ('.scena.chat-sotto{grid-template-areas:"palco palco" '
            '"principale accanto"}') in foglio


def test_in_cinema_il_lettore_resta_sedici_noni() -> None:
    """Con l'altezza legata alla finestra e la larghezza tutta disponibile,
    su uno schermo basso e largo il riquadro diventava piu' largo di 16:9 e
    dentro comparivano due bande nere ai lati del video.

    `object-fit: contain` faceva il suo lavoro, ma quelle bande sono dentro al
    lettore e sembrano un difetto. Ora il rapporto e' fisso e a variare e' la
    larghezza.
    """
    foglio = pathlib.Path("src/cleanvid/web/static/stile.css").read_text()
    blocco = foglio.split(".scena.cinema > .palco")[1][:240]
    assert "aspect-ratio:16/9" in blocco
    assert "width:min(100%," in blocco      # si stringe invece di allargarsi
    assert "height:auto" in blocco
    # e la chat non ha un'altezza sua: segue la riga
    assert ".scena.cinema.conchat.chat-fianco .chat{height:" not in foglio


def test_il_bagliore_parte_da_zero() -> None:
    """Finche' il video non parte la tela e' nera, e una tela nera sfocata
    non e' «niente»: e' un alone scuro che sul tema chiaro si vede benissimo
    e sembra sporco. Quindi zero, proprio zero."""
    foglio = pathlib.Path("src/cleanvid/web/static/stile.css").read_text()
    spento = ".scena.cinema.con-bagliore > #bagliore{display:block"
    blocco = foglio.split(spento)[1][:300]
    assert "opacity:0" in blocco
    assert "transition:opacity" in blocco      # entra e esce in dissolvenza
    acceso = ".scena.cinema.con-bagliore.bagliore-acceso > #bagliore"
    assert acceso + "{opacity:.62}" in foglio


def test_il_bagliore_si_accende_solo_quando_il_video_va() -> None:
    """Tre condizioni insieme: lo vuoi, c'e' un fotogramma disegnato, e il
    video sta davvero andando."""
    codice = pathlib.Path("src/cleanvid/web/static/bagliore.js").read_text()
    assert "acceso && haFotogramma && !video.paused && !video.ended" in codice
    # `playing` e non `play`: fra i due, su una diretta, passano secondi di
    # schermo nero
    assert 'video.addEventListener("playing"' in codice
    assert 'video.addEventListener("pause", rivedi)' in codice


async def test_la_stella_risponde_in_json_a_chi_lo_chiede(
        visitatore: AsyncClient) -> None:
    """Su una pagina che sta suonando un video, ricaricare vuol dire farlo
    ripartire da capo. Per una stella."""
    r = await visitatore.post(
        "/it/preferito", data={"url": "https://vimeo.com/76979871"},
        headers={"Accept": "application/json"})
    assert r.json() == {"preferito": True}
    r = await visitatore.post(
        "/it/preferito", data={"url": "https://vimeo.com/76979871"},
        headers={"Accept": "application/json"})
    assert r.json() == {"preferito": False}


async def test_senza_javascript_la_stella_funziona_lo_stesso(
        visitatore: AsyncClient) -> None:
    """Il modulo HTML c'e' e rimbalza: e' la forma vecchia, ed e' quella che
    regge quando il resto non c'e'."""
    r = await visitatore.post(
        "/it/preferito", data={"url": "https://vimeo.com/76979871"},
        follow_redirects=False)
    assert r.status_code == 303


def test_il_pannello_delle_preferenze_sta_sopra_a_quello_che_viene_dopo() -> None:
    """Si apriva dietro al blocco dell'indirizzo: visibile a meta' e non
    cliccabile. Un pannello che si apre dentro una riga deve stare sopra alla
    riga sotto, sempre."""
    foglio = pathlib.Path("src/cleanvid/web/static/stile.css").read_text()
    assert ".azioni{position:relative;z-index:5" in foglio
    assert ".indirizzo{position:relative;z-index:1" in foglio
    assert ".preferenze[open]{z-index:40}" in foglio


# --------------------------------------------------------------------------
# il guardiano del lettore
# --------------------------------------------------------------------------

def test_il_lettore_ha_un_guardiano() -> None:
    """Un flusso si ferma per mille motivi che non sono colpa di nessuno, e
    il browser quando succede non fa niente: resta fermo.

    Il guardiano guarda se il tempo avanza e, se non avanza, prova a
    rimettere in moto con una scala di rimedi dal piu' leggero al piu' pesante.
    """
    codice = pathlib.Path("src/cleanvid/web/static/lettore.js").read_text()
    assert "const FERMO_MS = 6000;" in codice
    assert "function rianima()" in codice
    # la scala: spinta, riapertura del flusso, e in fondo la riestrazione
    assert "video.currentTime + 0.1" in codice
    assert "video.load();" in codice
    assert "function riestrai()" in codice


def test_un_indirizzo_scaduto_fa_riestrarre_e_non_riprovare() -> None:
    """404 o 403 su un flusso vuol dire che l'indirizzo e' morto: li' non
    c'e' niente da riprovare, il flusso va estratto di nuovo."""
    codice = pathlib.Path("src/cleanvid/web/static/lettore.js").read_text()
    assert "codice === 404 || codice === 403" in codice
    # e una volta sola: ricaricare all'infinito nasconde il problema vero
    assert 'sessionStorage.getItem("cleanvid.riestratto")' in codice


def test_le_due_tracce_si_fermano_insieme() -> None:
    """Se una si ferma per mancanza di dati e l'altra continua, quando
    tornano si ritrovano a secondi di distanza: si sente come un doppiaggio
    sbagliato, e il recupero costa un salto brutto."""
    codice = pathlib.Path("src/cleanvid/web/static/lettore.js").read_text()
    assert 'audio.addEventListener("waiting", aspetta)' in codice
    assert 'video.addEventListener("waiting", aspetta)' in codice
    assert 'audio.addEventListener("canplay", riparti)' in codice


def test_la_diretta_non_si_tiene_in_memoria_tutta() -> None:
    """Su una diretta lunga sono centinaia di megabyte, e la scheda muore."""
    codice = pathlib.Path("src/cleanvid/web/static/lettore.js").read_text()
    assert "backBufferLength: 60" in codice


def test_una_lista_senza_segmenti_non_e_un_guasto() -> None:
    """E' una diretta che in questo momento manda solo pubblicita', e noi
    l'abbiamo tolta. Trattarla come un errore vorrebbe dire ricaricare la
    pagina a ogni interruzione."""
    codice = pathlib.Path("src/cleanvid/web/static/lettore.js").read_text()
    assert "Hls.ErrorDetails.LEVEL_EMPTY_ERROR" in codice
    assert "setTimeout(() => hls.startLoad(), 2000)" in codice


async def test_su_una_diretta_di_twitch_l_attesa_si_spiega(
        visitatore: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """I loro spot sono cuciti nel flusso e noi li buttiamo via: finche'
    dura l'interruzione non c'e' niente da mandare, e il lettore aspetta.

    E' il comportamento giusto - meglio aspettare che guardare la reclame -
    ma uno schermo nero senza spiegazioni sembra un guasto nostro.
    """
    async def diretta(url: str, qualita: str = "", lingua: str = "en") -> Fonte:
        return Fonte(tipo=HLS, indirizzo="/flusso/tv", token="tv",
                     titolo="Prova", diretta=True)

    monkeypatch.setattr(routes_watch, "risolvi", diretta)
    pagina = (await visitatore.get(
        "/it/guarda", params={"u": "https://www.twitch.tv/unaltro"})).text
    assert 'data-diretta="1"' in pagina
    assert 'data-piattaforma="Twitch"' in pagina
    assert "data-attesa-annuncio=" in pagina


def test_l_attesa_non_ha_la_faccia_di_un_errore() -> None:
    """Non c'e' niente di rotto, c'e' da aspettare qualche secondo. Un
    messaggio rosso su una cosa che si risolve da sola fa credere a un
    guasto."""
    foglio = pathlib.Path("src/cleanvid/web/static/stile.css").read_text()
    blocco = foglio.split(".attesa{")[1][:220]
    assert "--accent-soft" in blocco          # e non --err-bg
    codice = pathlib.Path("src/cleanvid/web/static/lettore.js").read_text()
    # e su una diretta di Twitch non si fa nemmeno la scala dei rimedi: non
    # c'e' niente da rimettere a posto
    assert "function forseAnnuncio()" in codice
    assert "aspettaAnnuncio(false)" in codice
