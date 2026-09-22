"""Il multilingua e la SEO: le cose che, se si rompono, nessuno se ne accorge.

E' il motivo per cui questi test sono piu' pedanti degli altri. Un bug qui non
si vede: il sito funziona, le pagine si aprono, e semplicemente non compare
piu' su Google in tredici lingue su quattordici. Ci si accorge mesi dopo,
guardando le statistiche.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from httpx import AsyncClient

from cleanvid.lingue import ORIGINALE
from cleanvid.lingue import testi as catalogo
from cleanvid.lingue.catalogo import LINGUE, da_accept_language

TESTI = Path("src/cleanvid/lingue/testi")


# --------------------------------------------------------------------------
# i cataloghi
# --------------------------------------------------------------------------

def test_ogni_lingua_ha_tutte_le_chiavi() -> None:
    """Una chiave che manca ripiega sull'italiano: si vede, ed e' brutto.

    Meglio scoprirlo qui che vedere una frase italiana in mezzo al giapponese.
    """
    attese = set(catalogo(ORIGINALE))
    assert attese, "il catalogo originale e' vuoto"
    for ling in LINGUE:
        sue = set(catalogo(ling.codice))
        assert sue == attese, (
            f"{ling.codice}: mancano {sorted(attese - sue)}, "
            f"in piu' {sorted(sue - attese)}")


def test_i_segnaposto_restano_quelli() -> None:
    """Se una traduzione sposta o rinomina {titolo}, la pagina mostra testo rotto."""
    originale = catalogo(ORIGINALE)
    for ling in LINGUE:
        propri = catalogo(ling.codice)
        for chiave, frase in originale.items():
            attesi = set(re.findall(r"\{(\w+)\}", frase))
            trovati = set(re.findall(r"\{(\w+)\}", propri[chiave]))
            assert attesi == trovati, f"{ling.codice}/{chiave}"


def test_i_titoli_per_i_motori_non_sono_troppo_lunghi() -> None:
    """Oltre i 155 caratteri Google taglia la descrizione a meta' frase."""
    for ling in LINGUE:
        propri = catalogo(ling.codice)
        assert len(propri["meta.home.descrizione"]) <= 200, ling.codice
        assert len(propri["meta.home.titolo"]) <= 70, ling.codice


def test_i_cataloghi_sono_json_valido_e_leggibile() -> None:
    """`ensure_ascii` disattivato: un diff pieno di \\u00e9 non si rilegge."""
    for percorso in TESTI.glob("*.json"):
        if percorso.name.startswith("."):
            continue
        grezzo = percorso.read_text(encoding="utf-8")
        json.loads(grezzo)
        assert "\\u" not in grezzo, f"{percorso.name} ha unicode scappato"


# --------------------------------------------------------------------------
# la scelta della lingua
# --------------------------------------------------------------------------

def test_accept_language() -> None:
    assert da_accept_language("it-IT,it;q=0.9,en;q=0.8") == "it"
    assert da_accept_language("de-DE,de;q=0.9") == "de"
    # pt-BR non e' una lingua a se': ricade su pt
    assert da_accept_language("pt-BR,pt;q=0.9") == "pt"
    # una lingua che non abbiamo: ripiego, non errore
    assert da_accept_language("sv-SE") == "en"
    assert da_accept_language(None) == "en"
    assert da_accept_language("") == "en"
    # i pesi contano: qui l'italiano vince anche se viene dopo
    assert da_accept_language("de;q=0.2,it;q=0.9") == "it"


async def test_la_radice_manda_alla_lingua_del_browser(
        visitatore: AsyncClient) -> None:
    r = await visitatore.get("/", headers={"Accept-Language": "de-DE,de;q=0.9"},
                             follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/de/"


async def test_la_radice_non_e_un_301(visitatore: AsyncClient) -> None:
    """307 e non 301: la destinazione dipende da chi chiede.

    Un permanente verrebbe messo in cache dal browser, e dopo cambiare lingua
    dalle impostazioni non funzionerebbe piu'.
    """
    r = await visitatore.get("/", follow_redirects=False)
    assert r.status_code == 307


async def test_una_lingua_che_non_esiste_e_404(visitatore: AsyncClient) -> None:
    """Non un rimbalzo alla home: un 200 su un indirizzo inventato riempie
    l'indice di pagine fantasma."""
    assert (await visitatore.get("/xx/")).status_code == 404


async def test_la_scelta_vince_sul_browser(visitatore: AsyncClient) -> None:
    await visitatore.post("/it/impostazioni/lingua", data={"scelta": "ja"})
    r = await visitatore.get("/", headers={"Accept-Language": "de-DE"},
                             follow_redirects=False)
    assert r.headers["location"] == "/ja/"


# --------------------------------------------------------------------------
# quello che vedono i motori di ricerca
# --------------------------------------------------------------------------

async def test_le_hreflang_sono_complete_e_reciproche(
        visitatore: AsyncClient) -> None:
    """Google butta via in blocco i gruppi che non tornano, senza dirlo.

    Si controllano tre lingue: se il gruppo di una combacia con quello di
    un'altra, combaciano tutti, perche' li genera la stessa funzione.
    """
    gruppi = []
    for codice in ("it", "en", "ja"):
        pagina = (await visitatore.get(f"/{codice}/")).text
        trovate = set(re.findall(r'hreflang="([\w-]+)" href="([^"]+)"', pagina))
        gruppi.append(trovate)
        codici = {c for c, _ in trovate}
        assert codici == {ling.codice for ling in LINGUE} | {"x-default"}
    assert gruppi[0] == gruppi[1] == gruppi[2], "i gruppi non sono reciproci"


async def test_ogni_lingua_ha_il_suo_canonico(visitatore: AsyncClient) -> None:
    for codice in ("it", "fr", "ar"):
        pagina = (await visitatore.get(f"/{codice}/")).text
        assert re.search(rf'rel=canonical href="[^"]+/{codice}/"', pagina)


async def test_la_pagina_dichiara_la_sua_lingua(visitatore: AsyncClient) -> None:
    """`lang` sbagliato e i traduttori automatici, e i lettori di schermo,
    leggono la pagina nella lingua sbagliata."""
    assert '<html lang="ja"' in (await visitatore.get("/ja/")).text
    # l'arabo si scrive da destra a sinistra, e va detto
    assert 'dir=rtl' in (await visitatore.get("/ar/")).text


async def test_le_pagine_dei_video_restano_fuori_dall_indice(
        visitatore: AsyncClient) -> None:
    """`guarda?u=...` e' uno spazio di indirizzi infinito di pagine sottili.

    Indicizzarlo non ci premia: ci classifica come sito di scarto, e si porta
    dietro anche la home.
    """
    pagina = (await visitatore.get(
        "/it/guarda", params={"u": "https://youtu.be/kJQP7kiw5Fk"})).text
    assert 'content="noindex,nofollow"' in pagina

    robot = (await visitatore.get("/robots.txt")).text
    assert "Disallow: /it/guarda" in robot
    assert "Disallow: /flusso/" in robot     # byte di video: banda buttata


async def test_la_home_invece_ci_sta(visitatore: AsyncClient) -> None:
    assert "noindex" not in (await visitatore.get("/it/")).text


async def test_la_mappa_elenca_tutte_le_lingue(visitatore: AsyncClient) -> None:
    mappa = (await visitatore.get("/sitemap.xml")).text
    for ling in LINGUE:
        assert f"/{ling.codice}/</loc>" in mappa
    assert 'hreflang="x-default"' in mappa
    # e NON le pagine dei video
    assert "/guarda" not in mappa


async def test_i_dati_strutturati_dicono_quello_che_c_e_sulla_pagina(
        visitatore: AsyncClient) -> None:
    """Dichiarare domande che sulla pagina non ci sono fa togliere il riquadro."""
    pagina = (await visitatore.get("/it/")).text
    grezzo = re.search(r'type="application/ld\+json">(.*?)</script>',
                       pagina, re.S)
    assert grezzo
    dati = json.loads(grezzo.group(1))
    faq = next(n for n in dati["@graph"] if n["@type"] == "FAQPage")
    assert len(faq["mainEntity"]) == 5
    for domanda in faq["mainEntity"]:
        assert domanda["name"] in pagina
        assert domanda["acceptedAnswer"]["text"] in pagina


async def test_i_testi_cambiano_davvero_con_la_lingua(
        visitatore: AsyncClient) -> None:
    it = (await visitatore.get("/it/")).text
    ja = (await visitatore.get("/ja/")).text
    assert catalogo("it")["home.apri"] in it
    assert catalogo("ja")["home.apri"] in ja
    assert catalogo("it")["home.faq.1.d"] not in ja
