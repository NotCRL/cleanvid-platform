"""Il pezzo con piu' casi strani del progetto, provato senza toccare la rete.

`riscrivi_playlist` decide, riga per riga, cosa arriva al player. Se sbaglia
si vede subito ma non si capisce perche': il video va a scatti, salta un pezzo
o si ferma su uno spot. Entra testo, esce testo, quindi si puo' provare tutto.

Le playlist qui sotto sono ridotte all'osso ma hanno la forma di quelle vere,
comprese le parti che ci sono costate tempo: la SSAI di Twitch, il preroll, e
i marker senza durata dichiarata.
"""

from __future__ import annotations

from cleanvid.media.manifesto import (
    Master,
    corpo_master,
    durata_interruzione,
    riscrivi_playlist,
)

SEMPLICE = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:4
#EXTINF:4.000,
segmento0.ts
#EXTINF:4.000,
sotto/segmento1.ts
"""


def test_i_segmenti_passano_dal_nostro_proxy() -> None:
    esito = riscrivi_playlist("tok", "https://cdn.tale/live/index.m3u8", SEMPLICE)
    righe = esito.testo.splitlines()
    assert all(not r.startswith("segmento") for r in righe)
    assert sum(r.startswith("/segmento?") for r in righe) == 2
    assert esito.tolti == 0


def test_gli_indirizzi_relativi_diventano_interi() -> None:
    """Un `sotto/segmento1.ts` senza base e' un indirizzo che non esiste."""
    esito = riscrivi_playlist("tok", "https://cdn.tale/live/index.m3u8", SEMPLICE)
    assert "cdn.tale%2Flive%2Fsotto%2Fsegmento1.ts" in esito.testo


def test_la_firma_c_e_su_ogni_segmento() -> None:
    esito = riscrivi_playlist("tok", "https://cdn.tale/x.m3u8", SEMPLICE)
    for riga in esito.testo.splitlines():
        if riga.startswith("/segmento?"):
            assert "&s=" in riga


CON_SPOT = """#EXTM3U
#EXT-X-TARGETDURATION:4
#EXTINF:4.000,
vero0.ts
#EXT-X-CUE-OUT:8.000
#EXTINF:4.000,
spot0.ts
#EXTINF:4.000,
spot1.ts
#EXT-X-CUE-IN
#EXTINF:4.000,
vero1.ts
"""


def test_gli_spot_spariscono_e_il_resto_no() -> None:
    esito = riscrivi_playlist("tok", "https://cdn.tale/x.m3u8", CON_SPOT)
    assert esito.tolti == 2
    assert "spot0.ts" not in esito.testo and "spot1.ts" not in esito.testo
    assert esito.testo.count("/segmento?") == 2      # vero0 e vero1
    assert not esito.solo_annunci


def test_l_extinf_di_uno_spot_se_ne_va_col_suo_segmento() -> None:
    """Se resta orfano, il player conta male la durata e il video singhiozza.

    E' il motivo per cui questa funzione lavora a stati invece che con una
    espressione regolare sull'intero testo.
    """
    esito = riscrivi_playlist("tok", "https://cdn.tale/x.m3u8", CON_SPOT)
    assert esito.testo.count("#EXTINF") == esito.testo.count("/segmento?")


def test_dopo_uno_spot_si_dichiara_la_discontinuita() -> None:
    """Senza, il decoder inciampa sul salto e mostra un fotogramma rotto."""
    esito = riscrivi_playlist("tok", "https://cdn.tale/x.m3u8", CON_SPOT)
    assert "#EXT-X-DISCONTINUITY" in esito.testo


TWITCH = """#EXTM3U
#EXT-X-DATERANGE:ID="stitched-ad-1",CLASS="twitch-stitched-ad",DURATION=30.0
#EXTINF:2.000,
ad0.ts
#EXTINF:2.000,
ad1.ts
"""


def test_la_pubblicita_cucita_di_twitch() -> None:
    """Quella che nessun blocco lato browser puo' vedere: sono gli stessi byte."""
    esito = riscrivi_playlist("tok", "https://usher.tale/x.m3u8", TWITCH)
    assert esito.tolti == 2
    assert "/segmento?" not in esito.testo


def test_il_preroll_si_riconosce() -> None:
    """Tolti gli spot non resta niente: chi guarda deve vedere "aspetta".

    Se questo non si distinguesse da un errore, il preroll di ogni diretta di
    Twitch sembrerebbe un guasto nostro.
    """
    esito = riscrivi_playlist("tok", "https://usher.tale/x.m3u8", TWITCH)
    assert esito.solo_annunci


def test_un_marker_senza_durata_non_mangia_il_flusso() -> None:
    """Senza CUE-IN e senza durata si taglia per un tetto, non per sempre."""
    assert durata_interruzione("#EXT-X-CUE-OUT") == 0.0
    assert durata_interruzione("#EXT-X-CUE-OUT:15.5") == 15.5
    assert durata_interruzione('#EXT-X-DATERANGE:ID="x",SCTE35-OUT=0xFC') == 0.0
    assert durata_interruzione("#EXTINF:4.0,") is None
    assert durata_interruzione("#EXT-X-VERSION:3") is None


def test_le_righe_uri_vengono_riscritte() -> None:
    """Le chiavi di cifratura e le mappe di inizializzazione stanno li'."""
    testo = '#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="chiave.bin"\n'
    esito = riscrivi_playlist("tok", "https://cdn.tale/live/x.m3u8", testo)
    assert 'URI="/segmento?' in esito.testo
    assert "chiave.bin" not in esito.testo.replace("%2Fchiave.bin", "")


def test_il_master_costruito_ha_audio_e_tutte_le_qualita() -> None:
    master = Master(
        video=[
            {"url": "https://t/480.m3u8", "vcodec": "avc1.4d401f", "tbr": 800,
             "width": 854, "height": 480},
            {"url": "https://t/1080.m3u8", "vcodec": "avc1.640028", "tbr": 4500,
             "width": 1920, "height": 1080},
        ],
        audio={"url": "https://t/audio.m3u8", "acodec": "none", "abr": 128},
    )
    corpo = corpo_master("tok", master)
    assert corpo.startswith("#EXTM3U")
    assert corpo.count("#EXT-X-STREAM-INF") == 2
    assert "RESOLUTION=1920x1080" in corpo
    # YouTube non dichiara l'acodec sui suoi HLS audio-only: si mette AAC-LC,
    # perche' un CODECS senza audio fa rifiutare il master a Safari
    assert "mp4a.40.2" in corpo
    assert 'GROUP-ID="aud"' in corpo


# --------------------------------------------------------------------------
# la numerazione dei segmenti
# --------------------------------------------------------------------------

DIRETTA_CON_SPOT = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:4
#EXT-X-MEDIA-SEQUENCE:1200
#EXT-X-CUE-OUT:8.000
#EXTINF:4.000,
spot0.ts
#EXTINF:4.000,
spot1.ts
#EXT-X-CUE-IN
#EXTINF:4.000,
vero0.ts
#EXTINF:4.000,
vero1.ts
"""


def test_la_numerazione_si_aggiorna_togliendo_i_primi_segmenti() -> None:
    """E' il numero del primo segmento della lista, e serve al player per
    capire quali segmenti sono nuovi fra un aggiornamento e l'altro.

    Togliendo i primi due senza toccarlo, il player crede che il primo sia
    ancora quello di prima: riscarica roba che ha gia', ne salta altra, e in
    diretta si pianta. Senza nessun messaggio: il video si ferma e basta.
    """
    esito = riscrivi_playlist("tok", "https://usher.tale/x.m3u8", DIRETTA_CON_SPOT)
    assert esito.tolti == 2
    assert "#EXT-X-MEDIA-SEQUENCE:1202" in esito.testo
    assert "#EXT-X-MEDIA-SEQUENCE:1200" not in esito.testo


def test_la_numerazione_non_si_tocca_se_non_si_toglie_niente_in_testa() -> None:
    """Gli spot in mezzo o in fondo non spostano il primo segmento."""
    in_fondo = """#EXTM3U
#EXT-X-MEDIA-SEQUENCE:900
#EXTINF:4.000,
vero0.ts
#EXT-X-CUE-OUT:4.000
#EXTINF:4.000,
spot0.ts
"""
    esito = riscrivi_playlist("tok", "https://usher.tale/x.m3u8", in_fondo)
    assert esito.tolti == 1
    assert "#EXT-X-MEDIA-SEQUENCE:900" in esito.testo


def test_una_playlist_senza_numerazione_non_ne_inventa_una() -> None:
    """I video registrati non ce l'hanno: aggiungerla cambierebbe il senso."""
    esito = riscrivi_playlist("tok", "https://cdn.tale/x.m3u8", CON_SPOT)
    assert "MEDIA-SEQUENCE" not in esito.testo


# --------------------------------------------------------------------------
# la pubblicita' di Twitch, riconosciuta dal titolo del segmento
# --------------------------------------------------------------------------

TWITCH_VERA = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:6
#EXT-X-MEDIA-SEQUENCE:7982
#EXT-X-TWITCH-LIVE-SEQUENCE:7982
#EXT-X-TWITCH-ELAPSED-SECS:15962.450
#EXT-X-PROGRAM-DATE-TIME:2026-09-22T21:48:09.234Z
#EXTINF:2.000,live
pezzo0.ts
#EXT-X-PROGRAM-DATE-TIME:2026-09-22T21:48:11.234Z
#EXTINF:2.000,live
pezzo1.ts
"""

TWITCH_CON_SPOT = """#EXTM3U
#EXT-X-TARGETDURATION:6
#EXT-X-MEDIA-SEQUENCE:100
#EXT-X-TWITCH-LIVE-SEQUENCE:100
#EXTINF:2.000,Amazon
spot0.ts
#EXTINF:2.000,Amazon
spot1.ts
#EXT-X-DISCONTINUITY
#EXTINF:2.000,live
pezzo0.ts
#EXTINF:2.000,live
pezzo1.ts
"""


def test_su_twitch_lo_spot_si_riconosce_dal_titolo_del_segmento() -> None:
    """E' il criterio che usano tutti i blocchi pubblicita' per Twitch che
    funzionano.

    I marker standard - CUE-OUT, DATERANGE di classe twitch-stitched-ad - a
    volte ci sono e a volte no. Il titolo dell'EXTINF c'e' sempre, perche'
    serve a loro: per i pezzi della diretta vera dice `live`, per gli spot
    dice il nome dell'inserzionista o niente.
    """
    esito = riscrivi_playlist("tok", "https://usher.tale/x.m3u8", TWITCH_CON_SPOT)
    assert esito.tolti == 2
    assert "spot0.ts" not in esito.testo and "spot1.ts" not in esito.testo
    assert esito.testo.count("/segmento?") == 2
    # e la numerazione segue: i due tolti stavano in testa
    assert "#EXT-X-MEDIA-SEQUENCE:102" in esito.testo


def test_una_diretta_pulita_di_twitch_non_si_tocca() -> None:
    """La regola e' severa: se sbagliasse, butterebbe via tutta la diretta."""
    esito = riscrivi_playlist("tok", "https://usher.tale/x.m3u8", TWITCH_VERA)
    assert esito.tolti == 0
    assert esito.testo.count("/segmento?") == 2
    assert "#EXT-X-MEDIA-SEQUENCE:7982" in esito.testo


def test_la_regola_di_twitch_non_si_applica_agli_altri_siti() -> None:
    """Altrove il titolo dell'EXTINF e' vuoto o dice altro, e applicarla
    vorrebbe dire buttare via l'intero video."""
    altrove = """#EXTM3U
#EXT-X-MEDIA-SEQUENCE:5
#EXTINF:4.000,
pezzo0.ts
#EXTINF:4.000,qualcosa
pezzo1.ts
"""
    esito = riscrivi_playlist("tok", "https://cdn.tale/x.m3u8", altrove)
    assert esito.tolti == 0
    assert esito.testo.count("/segmento?") == 2
