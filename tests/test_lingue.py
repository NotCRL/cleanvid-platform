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


def test_i_titoli_per_i_motori_stanno_nei_limiti() -> None:
    """Oltre questi numeri Google taglia, e taglia a meta' frase.

    I limiti veri sono in pixel e non in caratteri, quindi questi sono
    prudenti: 60 per il titolo e 160 per la descrizione lasciano margine
    anche alle lingue che scrivono largo.
    """
    for ling in LINGUE:
        propri = catalogo(ling.codice)
        assert len(propri["meta.home.titolo"]) <= 60, (
            f"{ling.codice}: titolo di {len(propri['meta.home.titolo'])} caratteri")
        assert len(propri["meta.home.descrizione"]) <= 160, (
            f"{ling.codice}: descrizione di "
            f"{len(propri['meta.home.descrizione'])} caratteri")


def test_il_marchio_sta_in_ogni_titolo() -> None:
    """Chi ci ha gia' visti una volta ci riconosce nell'elenco dei risultati."""
    for ling in LINGUE:
        assert "cleanvid" in catalogo(ling.codice)["meta.home.titolo"], ling.codice


def test_il_titolo_non_comincia_col_marchio() -> None:
    """La parola che la gente cerca sta all'inizio, non il nostro nome.

    Nessuno cerca «cleanvid»: cerca «video senza pubblicita'». Google pesa di
    piu' le prime parole, e nell'elenco dei risultati sono quelle che si
    leggono.
    """
    for ling in LINGUE:
        titolo = catalogo(ling.codice)["meta.home.titolo"]
        assert not titolo.lower().startswith("cleanvid"), ling.codice


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


# --------------------------------------------------------------------------
# l'icona e l'installazione sul telefono
# --------------------------------------------------------------------------

async def test_l_icona_si_disegna_in_ogni_misura(visitatore: AsyncClient) -> None:
    """Quattro misure diverse da un disegno solo: Safari ne vuole 180,
    Android 192 e 512, la scheda del browser 32."""
    for n in (32, 180, 192, 512):
        r = await visitatore.get("/icon.png", params={"s": n})
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


async def test_il_manifesto_porta_alla_lingua_di_chi_installa(
        visitatore: AsyncClient) -> None:
    """Chi installa dal giapponese si aspetta di riaprire il giapponese, non
    di essere rispedito alla scelta ogni volta."""
    r = await visitatore.get("/manifest.webmanifest",
                             headers={"Accept-Language": "ja"})
    dati = r.json()
    assert dati["start_url"] == "/ja/"
    assert dati["lang"] == "ja"
    assert any(i["purpose"] == "maskable" for i in dati["icons"])


async def test_la_pagina_dichiara_icona_e_manifesto(
        visitatore: AsyncClient) -> None:
    pagina = (await visitatore.get("/it/")).text
    assert 'rel=manifest href="/manifest.webmanifest"' in pagina
    assert "apple-touch-icon" in pagina


# --------------------------------------------------------------------------
# la pagina «cos'è»
# --------------------------------------------------------------------------

async def test_la_pagina_cos_e_c_e_in_tutte_le_lingue(
        visitatore: AsyncClient) -> None:
    """Non è una pagina di cortesia: è dove sta scritto che cleanvid non
    ospita niente. Se esiste solo in italiano, per tutti gli altri non
    esiste."""
    from markupsafe import escape

    for codice in ("it", "en", "ja", "ar"):
        r = await visitatore.get(f"/{codice}/cos-e")
        assert r.status_code == 200
        assert str(escape(catalogo(codice)["cose.non_fa.1"])) in r.text


async def test_dice_le_quattro_cose_che_non_fa(visitatore: AsyncClient) -> None:
    """«Cosa non fa» è la domanda a cui un servizio che apre contenuti di
    altri deve saper rispondere senza cercare le parole.

    Si confronta con il testo *sfuggito*: in pagina un apostrofo diventa
    `&#39;`, e cercare la frase cruda fallirebbe su tutte quelle che ne hanno
    uno - cioè su quasi tutte, in italiano.
    """
    from markupsafe import escape

    pagina = (await visitatore.get("/it/cos-e")).text
    for n in (1, 2, 3, 4):
        assert str(escape(catalogo("it")[f"cose.non_fa.{n}"])) in pagina
    assert str(escape(catalogo("it")["cose.responsabilita.testo"])) in pagina


async def test_la_pagina_cos_e_si_fa_trovare(visitatore: AsyncClient) -> None:
    """Chi cerca «cos'è cleanvid» deve trovarla: è nella mappa del sito, e
    non è marcata `noindex` come le pagine dei video."""
    assert "noindex" not in (await visitatore.get("/it/cos-e")).text
    mappa = (await visitatore.get("/sitemap.xml")).text
    assert "/it/cos-e</loc>" in mappa
    assert "/ja/cos-e</loc>" in mappa


async def test_il_piede_ci_rimanda(visitatore: AsyncClient) -> None:
    assert 'href="/it/cos-e"' in (await visitatore.get("/it/")).text


async def test_senza_contatto_quella_parte_non_compare(
        visitatore: AsyncClient) -> None:
    """In locale non c'è nessuno a cui scrivere, e una sezione vuota con un
    titolo sopra sembra una cosa rotta. Online vanno riempiti."""
    pagina = (await visitatore.get("/it/cos-e")).text
    assert catalogo("it")["cose.segnalazioni.titolo"] not in pagina
    assert catalogo("it")["cose.chi.titolo"] not in pagina


def test_il_piede_non_promette_piu_cose_che_online_sono_false() -> None:
    """Diceva «Gira sul tuo computer»: vero in locale, falso il giorno della
    pubblicazione. E era una frase sulla privacy, cioè il tipo di
    affermazione che non conviene avere sbagliata."""
    for ling in LINGUE:
        frase = catalogo(ling.codice)["piede.aperto"].lower()
        for parola in ("tuo computer", "your own computer", "propio ordenador",
                       "votre propre ordinateur", "eigenen rechner"):
            assert parola not in frase, ling.codice
