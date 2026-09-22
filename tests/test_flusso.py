"""Il proxy: chi puo' chiedere byte, e cosa succede quando non puo'.

La firma e' l'unica cosa fra noi e l'essere un proxy aperto. Un proxy aperto
viene trovato in ore e usato per far uscire traffico qualunque dalla nostra
macchina, con il nostro indirizzo sopra. Questi test esistono perche' quella
riga non si possa togliere per sbaglio.
"""

from __future__ import annotations

from httpx import AsyncClient

from cleanvid.media import deposito
from cleanvid.media.firme import firma, firma_valida, link_segmento
from cleanvid.media.qualita import selettore_singolo, tetto_altezza


async def test_un_segmento_senza_firma_viene_rifiutato(
        visitatore: AsyncClient) -> None:
    token = await deposito.registra(
        {"tipo": "diretto", "url": "https://cdn.tale/a.ts", "intestazioni": {}})
    risposta = await visitatore.get(
        "/segmento", params={"t": token, "u": "https://ovunque.tale/x", "s": "no"})
    assert risposta.status_code == 403


async def test_la_firma_di_un_flusso_non_vale_per_un_altro() -> None:
    """Altrimenti basterebbe estrarre un video qualunque per aprire il proxy."""
    url = "https://cdn.tale/a.ts"
    assert firma_valida("tok1", url, firma("tok1", url))
    assert not firma_valida("tok2", url, firma("tok1", url))
    assert not firma_valida("tok1", "https://altro.tale/b.ts", firma("tok1", url))


async def test_un_flusso_scaduto_e_404_non_403(visitatore: AsyncClient) -> None:
    """La differenza conta: la pagina deve rifare l'estrazione, non arrendersi."""
    risposta = await visitatore.get("/flusso/inventato")
    assert risposta.status_code == 404


async def test_il_master_hls_si_costruisce_al_volo(
        visitatore: AsyncClient) -> None:
    """Il token serve a scrivere i link dei segmenti: il corpo nasce qui."""
    token = await deposito.registra({
        "tipo": "master",
        "intestazioni": {"User-Agent": "prova"},
        "video": [{"url": "https://t/v.m3u8", "vcodec": "avc1.4d401f",
                   "tbr": 900, "width": 854, "height": 480}],
        "audio": {"url": "https://t/a.m3u8", "acodec": "mp4a.40.2", "abr": 128},
    })
    risposta = await visitatore.get(f"/flusso/{token}")
    assert risposta.status_code == 200
    assert risposta.headers["content-type"].startswith("application/vnd.apple.mpegurl")
    # una playlist in cache e' una diretta di due minuti fa
    assert risposta.headers["cache-control"] == "no-store"
    assert "#EXT-X-STREAM-INF" in risposta.text
    assert "/segmento?" in risposta.text


async def test_i_link_del_master_sono_firmati_e_accettati() -> None:
    """Il giro completo: quello che scriviamo noi deve superare il controllo."""
    collegamento = link_segmento("tok", "https://cdn.tale/a.ts")
    from urllib.parse import parse_qs, urlparse
    q = parse_qs(urlparse(collegamento).query)
    assert firma_valida(q["t"][0], q["u"][0], q["s"][0])


async def test_il_deposito_fa_andata_e_ritorno() -> None:
    dati = {"tipo": "diretto", "url": "https://cdn.tale/a.mp4",
            "intestazioni": {"Referer": "https://tale/"}}
    token = await deposito.registra(dati)
    assert await deposito.leggi(token) == dati
    assert await deposito.leggi("altro") is None


async def test_due_registrazioni_non_condividono_il_token() -> None:
    a = await deposito.registra({"tipo": "diretto", "url": "a", "intestazioni": {}})
    b = await deposito.registra({"tipo": "diretto", "url": "b", "intestazioni": {}})
    assert a != b


async def test_la_cache_dell_estrazione_non_dipende_dall_utente() -> None:
    """E' la decisione che rende sostenibile una stanza da dieci persone."""
    esito = {"token": "t", "titolo": "prova", "diretta": False, "hls": False,
             "token_audio": None, "altezza": 720}
    await deposito.ricorda_estrazione("https://tale/v", "720", esito)
    assert await deposito.estrazione_in_cache("https://tale/v", "720") == esito
    # qualita' diversa, estrazione diversa: sono due flussi diversi davvero
    assert await deposito.estrazione_in_cache("https://tale/v", "480") is None


def test_il_tetto_di_altezza() -> None:
    assert tetto_altezza("720") == 720
    assert tetto_altezza("") is None
    assert tetto_altezza("come viene") is None
    # "basso" e' quello che scrivevano le versioni precedenti: i segnalibri di
    # chi lo usa gia' devono continuare a funzionare
    assert tetto_altezza("basso") == 480
    # fuori scala e' un errore di battitura, non una richiesta
    assert tetto_altezza("99999") is None
    assert tetto_altezza("7") is None


def test_il_selettore_chiede_h264_quando_c_e_un_tetto() -> None:
    assert "height<=480" in selettore_singolo(480)
    assert "height" not in selettore_singolo(None)


# --------------------------------------------------------------------------
# il proxy contro un sito finto, ma con HTTP vero
# --------------------------------------------------------------------------
#
# Questi esistono per un bug trovato con le mani il 22/09/2026: lo stream di
# httpx si puo' leggere una volta sola, e leggerne sette byte per capire cosa
# fosse bruciava tutto il resto. Il video si apriva, dichiarava la lunghezza
# giusta, e poi non arrivava un byte. Un sito finto servito su HTTP vero lo
# prende; una finzione piu' in su del proxy non lo avrebbe preso mai.

VIDEO_FINTO = bytes(range(256)) * 4000          # ~1 MB, piu' di un boccone


async def test_i_byte_arrivano_tutti(visitatore: AsyncClient,
                                     sito_finto: None) -> None:
    token = await deposito.registra(
        {"tipo": "diretto", "url": "http://sito/video.mp4", "intestazioni": {}})
    risposta = await visitatore.get(f"/flusso/{token}")
    assert risposta.status_code == 200
    assert risposta.content == VIDEO_FINTO


async def test_il_salto_nel_video_chiede_solo_il_pezzo(
        visitatore: AsyncClient, sito_finto: None) -> None:
    """Senza il passaggio del Range, saltare avanti riscarica tutto da capo."""
    token = await deposito.registra(
        {"tipo": "diretto", "url": "http://sito/video.mp4", "intestazioni": {}})
    risposta = await visitatore.get(f"/flusso/{token}",
                                    headers={"Range": "bytes=10-19"})
    assert risposta.status_code == 206
    assert risposta.content == VIDEO_FINTO[10:20]
    assert risposta.headers["content-range"] == f"bytes 10-19/{len(VIDEO_FINTO)}"


async def test_una_playlist_torna_riscritta(visitatore: AsyncClient,
                                            sito_finto: None) -> None:
    token = await deposito.registra(
        {"tipo": "diretto", "url": "http://sito/lista.m3u8", "intestazioni": {}})
    risposta = await visitatore.get(f"/flusso/{token}")
    assert "/segmento?" in risposta.text
    assert "pezzo0.ts" not in risposta.text.replace("%2Fpezzo0.ts", "")


async def test_un_segmento_etichettato_male_si_corregge(
        visitatore: AsyncClient, sito_finto: None) -> None:
    """googlevideo chiama `mpegurl` anche i segmenti: al browser va detto giusto."""
    token = await deposito.registra(
        {"tipo": "diretto", "url": "http://sito/bugiardo.ts", "intestazioni": {}})
    risposta = await visitatore.get(f"/flusso/{token}")
    assert risposta.headers["content-type"] == "video/mp2t"
    assert risposta.content == b"non sono una playlist"


async def test_le_intestazioni_richieste_dal_sito_arrivano(
        visitatore: AsyncClient, sito_finto: None) -> None:
    """Il Referer e' il motivo per cui questo proxy esiste: senza, e' 403."""
    token = await deposito.registra({
        "tipo": "diretto", "url": "http://sito/protetto.mp4",
        "intestazioni": {"Referer": "https://tale/"}})
    assert (await visitatore.get(f"/flusso/{token}")).status_code == 200

    scoperto = await deposito.registra(
        {"tipo": "diretto", "url": "http://sito/protetto.mp4", "intestazioni": {}})
    assert (await visitatore.get(f"/flusso/{scoperto}")).status_code == 403


async def test_durante_un_preroll_si_serve_l_ultima_buona(
        visitatore: AsyncClient, sito_finto: None) -> None:
    """Tolti gli spot puo' non restare niente: e' il preroll.

    Una playlist senza un solo segmento certi lettori la prendono per un
    errore e si fermano - ed e' esattamente il momento in cui sembra che il
    sito sia rotto. Si serve l'ultima che aveva roba vera: per il lettore e'
    una diretta che non ha ancora niente di nuovo, cioe' una cosa normale.
    """
    token = await deposito.registra(
        {"tipo": "diretto", "url": "http://sito/lista.m3u8", "intestazioni": {}})

    # prima passata: c'e' roba vera, e si mette da parte
    buona = (await visitatore.get(f"/flusso/{token}")).text
    assert "/segmento?" in buona
    assert await deposito.ultima_playlist(token, "http://sito/lista.m3u8") is not None

    # ora il sito serve solo spot: si deve rivedere quella di prima
    solo_spot = (await visitatore.get(f"/flusso/{token}",
                                      params={"finto": "solo-spot"})).text
    assert solo_spot == buona or "/segmento?" in solo_spot


async def test_senza_una_buona_da_parte_si_dice_come_sta(
        visitatore: AsyncClient, sito_finto: None) -> None:
    """Al primo colpo non c'e' niente da parte: si risponde quello che c'e',
    invece di inventare."""
    token = await deposito.registra(
        {"tipo": "diretto", "url": "http://sito/solospot.m3u8",
         "intestazioni": {}})
    r = await visitatore.get(f"/flusso/{token}")
    assert r.status_code == 200
    assert "/segmento?" not in r.text
