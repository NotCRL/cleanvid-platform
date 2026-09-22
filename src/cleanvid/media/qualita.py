"""Quanto grande chiedere il video, e come si dice a yt-dlp.

Sembra un dettaglio e non lo e': il tetto di altezza e' l'unica leva vera su
un tablet, dove quanti video si possono decodificare insieme lo decide
l'hardware e non il software, e serve anche a chi ha la linea corta.

Qui c'e' solo la traduzione da "cosa ha chiesto la persona" a "cosa si scrive
nel selettore di yt-dlp". Nessuna rete, nessun processo: si prova tutta con
una tabella di casi.
"""

from __future__ import annotations

# Le altezze offerte nei menu. Non e' un limite tecnico: e' l'elenco di scelte
# che ha senso mostrare, perche' tredici voci in un menu non le legge nessuno.
QUALITA = ("1080", "720", "480", "360")


def tetto_altezza(qualita: str) -> int | None:
    """L'altezza massima richiesta, o None per "come viene".

    `basso` resta accettato: e' quello che scrivevano le versioni precedenti
    negli indirizzi e nella memoria dei browser, e vale 480. Toglierlo
    romperebbe i segnalibri di chi lo usa gia'.
    """
    q = (qualita or "").strip()
    if q == "basso":
        return 480
    if q.isdigit():
        n = int(q)
        # sotto i 144 non esiste niente, sopra 4320 (8K) non esiste ancora:
        # fuori da qui e' un errore di battitura, e si ignora invece di
        # chiedere a yt-dlp un formato che non trovera' mai
        return n if 144 <= n <= 4320 else None
    return None


def selettore_singolo(tetto: int | None) -> str:
    """Un solo file che contiene gia' video e audio.

    E' la strada migliore quando c'e': un file solo vuol dire che il salto
    avanti e indietro funziona, che si puo' scaricare, e che non c'e' niente
    da tenere allineato.
    """
    if tetto is None:
        return "best[ext=mp4]/best"
    return f"best[height<={tetto}][ext=mp4]/best[height<={tetto}]/worst[ext=mp4]/worst"


def selettore_separati(tetto: int | None) -> str:
    """Video muto e audio a parte, che e' come servono ormai quasi tutti.

    Si chiede avc1 + mp4a prima di qualunque altra cosa: sono i due codec che
    ogni browser e ogni telefono sanno decodificare in hardware. VP9 e Opus
    sono migliori sulla carta e su un iPhone non partono.
    """
    if tetto is None:
        return "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/bv*+ba/b"
    return (f"bv*[height<={tetto}][vcodec^=avc1]+ba[acodec^=mp4a]/"
            f"bv*[height<={tetto}]+ba/worst[height>=240]")
