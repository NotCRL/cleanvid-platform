"""I manifest HLS: costruirne uno, e ripulire quelli che arrivano.

Due mestieri diversi che stanno insieme perche' parlano la stessa lingua.

**Costruire.** Quando un sito offre solo flussi separati - video da una parte,
audio dall'altra - e si tratta di una diretta, un master HLS scritto da noi
e' molto meglio di un file cucito a mano: il player ottiene il bordo della
diretta, il DVR, il cambio di qualita' e il recupero automatico dopo un buco
di rete. Tutte cose che dentro un mp4 non esistono.

**Ripulire.** Le playlist che arrivano vanno riscritte comunque, perche' gli
indirizzi dei segmenti devono passare dal nostro proxy. Visto che si riscrive
riga per riga, e' il punto giusto per togliere la pubblicita' cucita dentro il
flusso - quella che nessun blocco lato browser puo' vedere, perche' arriva
dagli stessi byte del video vero.

Nessuna rete qui dentro: entra testo, esce testo. E' il pezzo con piu' casi
strani di tutto il progetto, ed e' l'unico modo per poterlo provare davvero.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from .firme import link_segmento

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# Senza durata dichiarata si prende un tetto prudente: senza il CUE-IN che
# chiude l'interruzione, tagliare all'infinito vorrebbe dire mangiarsi il
# flusso vero. Tre minuti e' piu' lunga di qualunque interruzione reale.
TETTO_INTERRUZIONE_S = 180.0


@dataclass(slots=True)
class Master:
    """Le tracce scelte per un master costruito da noi."""
    video: list[dict[str, Any]]
    audio: dict[str, Any]
    intestazioni: dict[str, str] = field(default_factory=dict)


def _e_hls(f: dict[str, Any]) -> bool:
    return "m3u8" in (f.get("protocol") or "") and bool(f.get("url"))


def scegli_tracce(info: dict[str, Any], tetto: int | None = None) -> Master | None:
    """Il miglior audio e tutte le varianti video h264, dal peggiore al migliore."""
    video = sorted(
        (f for f in info.get("formats") or []
         if _e_hls(f) and (f.get("vcodec") or "none").startswith("avc1")),
        key=lambda f: f.get("tbr") or 0,
    )

    audio = None
    for f in info.get("formats") or []:
        # YouTube non dichiara l'acodec sui suoi HLS audio-only: l'assenza di
        # video e' l'unico criterio che regge
        if not _e_hls(f) or (f.get("vcodec") or "none") != "none":
            continue
        ritmo = f.get("tbr") or f.get("abr") or 0
        if audio is None or ritmo > (audio.get("tbr") or audio.get("abr") or 0):
            audio = f

    if tetto and video:
        sotto = [f for f in video if (f.get("height") or 9999) <= tetto]
        # se sotto il tetto non c'e' niente si tiene la piu' bassa: meglio un
        # video piu' grande del voluto che nessun video
        video = sotto or video[:1]

    if not video or not audio:
        return None

    intestazioni = dict(video[-1].get("http_headers")
                        or info.get("http_headers") or {})
    intestazioni.setdefault("User-Agent", UA)
    return Master(video=video, audio=audio, intestazioni=intestazioni)


def corpo_master(token: str, master: Master) -> str:
    """Il testo del master: le qualita' video, e l'audio come traccia a parte."""
    acodec = master.audio.get("acodec")
    if not acodec or acodec == "none":
        acodec = "mp4a.40.2"          # gli HLS audio-only di YouTube sono AAC-LC
    abr = master.audio.get("abr") or 128

    righe = [
        "#EXTM3U",
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aud",NAME="audio",DEFAULT=YES,'
        f'AUTOSELECT=YES,URI="{link_segmento(token, master.audio["url"])}"',
    ]
    for v in master.video:
        codecs = ",".join(c for c in (v.get("vcodec"), acodec)
                          if c and c != "none")
        risoluzione = (f",RESOLUTION={v['width']}x{v['height']}"
                       if v.get("width") and v.get("height") else "")
        banda = int(((v.get("tbr") or 3000) + abr) * 1000)
        righe.append(f"#EXT-X-STREAM-INF:BANDWIDTH={banda},"
                     f'CODECS="{codecs}"{risoluzione},AUDIO="aud"')
        righe.append(link_segmento(token, v["url"]))
    return "\n".join(righe) + "\n"


# --------------------------------------------------------------------------
# la pubblicita' cucita dentro il flusso
# --------------------------------------------------------------------------

def durata_interruzione(riga: str) -> float | None:
    """I secondi di pubblicita' annunciati da questa riga, o None se non lo e'.

    Copre la SSAI di Twitch (`EXT-X-DATERANGE` di classe `twitch-stitched-ad`)
    e i marker SCTE-35 che usano quasi tutti i broadcaster. Restituisce 0.0
    quando l'interruzione e' annunciata ma senza durata: e' comunque una
    risposta diversa da "non e' un marker", e chi chiama deve distinguerle.
    """
    su = riga.upper()
    if su.startswith("#EXT-X-CUE-OUT"):
        m = re.search(r"[:,]\s*(?:DURATION[=:])?([0-9.]+)", riga)
        return float(m.group(1)) if m else 0.0
    if su.startswith("#EXT-X-DATERANGE") and (
            "TWITCH-STITCHED-AD" in su or "SCTE35-OUT" in su or 'CLASS="AD' in su):
        m = re.search(r"DURATION=([0-9.]+)", riga)
        return float(m.group(1)) if m else 0.0
    return None


@dataclass(slots=True)
class Ripulita:
    testo: str
    tolti: int = 0          # quanti segmenti di pubblicita' sono spariti
    solo_annunci: bool = False   # tolti quelli, non e' rimasto niente


def riscrivi_playlist(token: str, base: str, testo: str) -> Ripulita:
    """Manda i segmenti sul nostro proxy e toglie quelli pubblicitari.

    Si lavora a stati e non a espressioni regolari sull'intero testo, perche'
    un `#EXTINF` e la riga dell'indirizzo che lo segue vanno tolti insieme: se
    ne resta uno, il player conta male la durata e il video va a scatti.
    """
    fuori: list[str] = []
    restano = 0.0       # secondi di pubblicita' ancora da saltare
    sospeso: float | None = None   # un #EXTINF che aspetta il suo indirizzo
    tolti = 0

    for riga in testo.splitlines():
        pulita = riga.strip()
        su = pulita.upper()

        if pulita.startswith("#"):
            durata = durata_interruzione(pulita)
            if durata is not None:
                restano = max(restano, durata or TETTO_INTERRUZIONE_S)
                continue          # il marker stesso al player non serve
            if su.startswith("#EXT-X-CUE-IN"):
                restano = 0.0
                fuori.append("#EXT-X-DISCONTINUITY")
                continue
            if su.startswith("#EXTINF"):
                if restano > 0:
                    m = re.match(r"#EXTINF:\s*([0-9.]+)", pulita)
                    sospeso = float(m.group(1)) if m else 0.0
                    continue
                fuori.append(riga)
                continue
            if su.startswith("#EXT-X-DISCONTINUITY") and restano > 0:
                continue          # discontinuita' interna al blocco di spot

            def sostituisci(m: re.Match[str]) -> str:
                intero = urllib.parse.urljoin(base, m.group(1))
                return f'URI="{link_segmento(token, intero)}"'

            fuori.append(re.sub(r'URI="([^"]+)"', sostituisci, riga))

        elif pulita:
            if sospeso is not None:      # l'indirizzo di un segmento di spot
                restano -= sospeso
                sospeso = None
                tolti += 1
                if restano <= 0:
                    restano = 0.0
                    # una discontinuita' dice al player "qui il flusso cambia":
                    # senza, il decoder inciampa sul salto
                    fuori.append("#EXT-X-DISCONTINUITY")
                continue
            fuori.append(link_segmento(token, urllib.parse.urljoin(base, pulita)))
        else:
            fuori.append(riga)

    return Ripulita(
        testo="\n".join(fuori) + "\n",
        tolti=tolti,
        # se tolti gli spot non resta un solo segmento, siamo dentro un
        # preroll: il flusso vero non e' ancora cominciato, e chi guarda deve
        # vedere "aspetta" e non "errore"
        solo_annunci=bool(tolti) and not any(
            r.startswith("/segmento?") for r in fuori),
    )
