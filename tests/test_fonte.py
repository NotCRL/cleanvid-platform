"""Una fonte sola, comunque sia stata trovata.

Fino a ieri c'erano due tipi per la stessa cosa - `Lettore` ed `Estratto` - e
ogni pagina doveva chiedersi quale avesse in mano. Il costo non era la riga in
piu': era che ogni funzione nuova andava pensata due volte.

Questi test tengono ferma la cosa che quella fusione doveva ottenere: **chi
riceve una fonte non deve sapere come e' stata trovata, deve sapere cosa ci
puo' fare.**
"""

from __future__ import annotations

import pathlib

from cleanvid.media.embed import lettore_ufficiale
from cleanvid.media.fonte import DIRETTA, HLS, INCORNICIATA, Fonte


def test_la_fonte_dice_cosa_ci_si_puo_fare() -> None:
    incorniciata = Fonte(tipo=INCORNICIATA, indirizzo="https://tale/embed/1")
    assert incorniciata.incorniciata
    assert not incorniciata.nostra
    assert not incorniciata.due_tracce

    nostra = Fonte(tipo=DIRETTA, indirizzo="/flusso/abc", token="abc")
    assert nostra.nostra
    assert not nostra.incorniciata
    assert not nostra.e_hls

    a_segmenti = Fonte(tipo=HLS, indirizzo="/flusso/abc", token="abc")
    assert a_segmenti.e_hls and a_segmenti.nostra


def test_due_tracce_si_riconosce_dall_indirizzo_audio() -> None:
    """La seconda traccia c'e' o non c'e': non serve un'altra bandierina."""
    una = Fonte(tipo=DIRETTA, indirizzo="/flusso/v")
    due = Fonte(tipo=DIRETTA, indirizzo="/flusso/v", indirizzo_audio="/flusso/a")
    assert not una.due_tracce
    assert due.due_tracce


def test_il_lettore_di_una_piattaforma_e_una_fonte_come_le_altre() -> None:
    fonte = lettore_ufficiale("https://www.youtube.com/watch?v=kJQP7kiw5Fk")
    assert fonte is not None
    assert fonte.incorniciata
    assert fonte.piattaforma == "YouTube"
    assert "youtube.com/embed/kJQP7kiw5Fk" in fonte.indirizzo


def test_una_diretta_di_twitch_si_sa_dall_indirizzo() -> None:
    """Dentro un iframe non si puo' sapere se e' una diretta. Per Twitch si',
    perche' lo dice la forma del link - ed e' il caso che conta, perche' e'
    l'unico dove serve la chat."""
    diretta = lettore_ufficiale("https://www.twitch.tv/uncanale")
    registrazione = lettore_ufficiale("https://www.twitch.tv/videos/12345")
    assert diretta is not None and diretta.diretta
    assert registrazione is not None and not registrazione.diretta


def test_non_esistono_piu_due_tipi() -> None:
    """Il punto di tutta l'operazione.

    Se qualcuno li reintroduce, ricomincia anche la doppia strada in ogni
    pagina - e quella non si vede finche' non si scrive la funzione dopo.
    """
    sorgente = pathlib.Path("src/cleanvid")
    for f in sorgente.rglob("*.py"):
        testo = f.read_text()
        assert "class Lettore" not in testo, f
        assert "class Estratto" not in testo, f

    for modello in pathlib.Path("src/cleanvid/web/templates").glob("*.html"):
        testo = modello.read_text()
        assert "estratto." not in testo, modello
        assert "lettore.url_lettore" not in testo, modello


def test_il_tipo_e_una_stringa_aperta() -> None:
    """`torrent`, `locale`, `addon` sono altri modi di arrivare a un flusso.

    Il giorno che arrivano non devono cambiare niente qui: per questo `tipo`
    e' una stringa e non un insieme chiuso di casi.
    """
    futura = Fonte(tipo="torrent", indirizzo="/flusso/xyz")
    assert futura.nostra
    assert not futura.incorniciata
