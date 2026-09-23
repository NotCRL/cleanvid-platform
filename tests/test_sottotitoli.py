"""I sottotitoli: quali si tengono, e perché non tutti.

Su YouTube le tracce automatiche possono essere **più di cento**, perché
includono la traduzione in ogni lingua esistente. Metterle tutte in pagina
sarebbe inutile e dannoso: un menu con cento voci non si usa.

La regola di scelta sta in un posto solo, e questi test la tengono ferma.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from cleanvid.media.sottotitoli import MASSIMO, MASSIMO_AUTOMATICHE, _codice, scegli


def _vtt(nome: str = "") -> list[dict[str, Any]]:
    return [{"ext": "json3", "url": "https://tale/x.json3"},
            {"ext": "vtt", "url": "https://tale/x.vtt", "name": nome}]


def test_si_tiene_solo_il_vtt() -> None:
    """E' l'unico che il tag `<track>` sa leggere. Convertire gli altri e' un
    mestiere intero che non serve fare finche' il vtt c'e' sempre."""
    solo_json = {"it": [{"ext": "json3", "url": "https://tale/x.json3"}]}
    assert scegli({"subtitles": solo_json}) == []

    con_vtt = {"it": _vtt("Italiano")}
    scelte = scegli({"subtitles": con_vtt})
    assert [i for i, _ in scelte] == ["https://tale/x.vtt"]


def test_il_codice_di_lingua_si_ripulisce() -> None:
    """Le chiavi di YouTube sono tipo `en-nP7-2PuUl7o`: `en` e' la lingua, il
    resto e' l'identificativo della traccia. Ma `en-US` e' una lingua vera."""
    assert _codice("en-nP7-2PuUl7o") == "en"
    assert _codice("en-US") == "en-US"
    assert _codice("pt-BR") == "pt-BR"
    assert _codice("it") == "it"


def test_prima_la_lingua_della_pagina_poi_l_inglese() -> None:
    """Chi guarda cerca la propria lingua per prima, e se non c'e' prova
    l'inglese. L'ordine della lista e' l'ordine del menu."""
    dati = {"subtitles": {"de": _vtt("Deutsch"), "en": _vtt("English"),
                          "it": _vtt("Italiano")}}
    scelte = scegli(dati, preferita="it")
    assert [t.lingua for _, t in scelte][:2] == ["it", "en"]

    scelte = scegli(dati, preferita="de")
    assert [t.lingua for _, t in scelte][:2] == ["de", "en"]


def test_le_automatiche_solo_dove_non_c_e_gia_niente() -> None:
    """Una traccia scritta da una persona batte sempre quella della macchina."""
    dati = {
        "subtitles": {"it": _vtt("Italiano")},
        "automatic_captions": {"it": _vtt(), "en": _vtt()},
    }
    scelte = scegli(dati, preferita="it")
    per_lingua = {t.lingua: t for _, t in scelte}
    assert not per_lingua["it"].automatica       # quella scritta ha vinto
    assert per_lingua["en"].automatica


def test_le_automatiche_non_diventano_un_catalogo() -> None:
    """Sono una comodita' quando non c'e' altro, non un elenco di lingue."""
    tante = {f"l{n}": _vtt() for n in range(60)}
    tante.update({"it": _vtt(), "en": _vtt()})
    scelte = scegli({"automatic_captions": tante}, preferita="it")
    assert len(scelte) <= MASSIMO_AUTOMATICHE
    # e sono le due che servono davvero
    assert {t.lingua for _, t in scelte} == {"it", "en"}


def test_non_si_supera_mai_il_tetto() -> None:
    """Un menu con cento voci non si usa: si chiude."""
    tantissime = {f"l{n}": _vtt(f"Lingua {n}") for n in range(50)}
    scelte = scegli({"subtitles": tantissime})
    assert len(scelte) == MASSIMO


def test_una_lingua_sola_anche_se_le_chiavi_sono_diverse() -> None:
    """YouTube da' piu' tracce per la stessa lingua, con chiavi diverse.
    Nel menu devono comparire una volta sola."""
    dati = {"subtitles": {"en-aaaaaaaaaa": _vtt("English"),
                          "en-bbbbbbbbbb": _vtt("English (altro)")}}
    scelte = scegli(dati)
    assert [t.lingua for _, t in scelte] == ["en"]


async def test_una_traccia_scaduta_e_404(visitatore: AsyncClient) -> None:
    assert (await visitatore.get("/sottotitoli/inventato")).status_code == 404


async def test_il_tipo_lo_dichiariamo_noi(visitatore: AsyncClient,
                                          sito_finto: None) -> None:
    """Certi siti servono i sottotitoli come `text/plain`, e con quelli il
    browser non li mostra. Il tipo non si copia da monte."""
    from cleanvid.media import deposito

    token = await deposito.registra({
        "tipo": "sottotitoli", "url": "http://sito/sottotitoli.txt",
        "intestazioni": {}})
    r = await visitatore.get(f"/sottotitoli/{token}")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/vtt")
    assert r.text.startswith("WEBVTT")
