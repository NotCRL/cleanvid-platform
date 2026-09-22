"""Le copertine: un elenco di link e' una lista della spesa.

Un elenco di copertine si riconosce con la coda dell'occhio, e questa e' tutta
la ragione per cui questo file esiste. Non e' decorazione: con trenta voci in
cronologia, senza immagini non si ritrova niente.

**Le immagini le scarica il server, non il browser.** Se mettessimo in pagina
l'indirizzo di `i.ytimg.com`, ogni copertina sarebbe una richiesta dal browser
di chi guarda verso YouTube, con il suo indirizzo IP e i suoi cookie: la home
di cleanvid direbbe a mezzo mondo cosa guardi. Passando da qui, la piattaforma
vede solo noi.

**Si cerca dal modo piu' economico in giu'**, e ci si ferma al primo che
risponde: un indirizzo che si costruisce da soli (YouTube, Twitch) costa zero;
una oEmbed costa una richiesta; leggere l'`og:image` della pagina ne costa una
piu' grande; yt-dlp costa secondi. Chiamare yt-dlp per ogni copertina di una
pagina con venti voci vorrebbe dire venti processi per disegnare una griglia.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import re
import urllib.parse
from pathlib import Path

import httpx

from ..config import impostazioni
from . import deposito
from .manifesto import UA
from .proxy import cliente

# Una copertina trovata vale una settimana: le miniature non cambiano quasi
# mai, e quando cambiano nessuno se ne accorge.
VITA_S = 7 * 24 * 3600
# Un buco si riprova dopo un quarto d'ora, non alla richiesta dopo: senza
# questo, una pagina senza copertina farebbe ripartire la ricerca ogni volta
# che qualcuno apre la home.
VITA_BUCO_S = 15 * 60
MASSIMO_BYTE = 1_500_000

CHIAVE_BUCO = "nocop:"

_OEMBED: tuple[tuple[str, str], ...] = (
    (r"vimeo\.com/", "https://vimeo.com/api/oembed.json?url={0}"),
    (r"dailymotion\.com/", "https://www.dailymotion.com/services/oembed?url={0}"),
    (r"tiktok\.com/", "https://www.tiktok.com/oembed?url={0}"),
    (r"streamable\.com/", "https://api.streamable.com/oembed.json?url={0}"),
    (r"reddit\.com/", "https://www.reddit.com/oembed?url={0}"),
    (r"soundcloud\.com/", "https://soundcloud.com/oembed?format=json&url={0}"),
)

_OG = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:image(?::secure_url)?|twitter:image)'
    r'["\'][^>]*content=["\']([^"\']+)', re.I)
_OG_ROVESCIO = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)='
    r'["\'](?:og:image(?::secure_url)?|twitter:image)', re.I)

_YOUTUBE = re.compile(
    r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|live/|embed/)|youtu\.be/)"
    r"([\w-]{11})")
_TWITCH = re.compile(r"twitch\.tv/(?!videos/|clips/|directory)([a-zA-Z0-9_]{3,25})")

_semaforo: asyncio.Semaphore | None = None


def semaforo() -> asyncio.Semaphore:
    """Poche ricerche insieme: alcune costano un yt-dlp, e la CPU e' una."""
    global _semaforo
    if _semaforo is None:
        _semaforo = asyncio.Semaphore(3)
    return _semaforo


def cartella() -> Path:
    via = Path(impostazioni().cartella_copertine)
    via.mkdir(parents=True, exist_ok=True)
    return via


def _su_disco(url: str) -> Path:
    # su disco e non in Redis: sono immagini da qualche decina di kilobyte
    # l'una, e riempire la memoria di un database con dei JPEG e' il modo di
    # pagare la RAM al prezzo della RAM per tenerci dei file
    nome = hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()[:20]
    return cartella() / nome


def _tipo_di(dati: bytes) -> str:
    if dati[:4] == b"RIFF":
        return "image/webp"
    if dati[:4] == b"\x89PNG":
        return "image/png"
    if dati[:3] == b"GIF":
        return "image/gif"
    return "image/jpeg"


async def _oembed(url: str) -> str | None:
    citato = urllib.parse.quote(url, safe="")
    for schema, punto in _OEMBED:
        if not re.search(schema, url):
            continue
        try:
            r = await cliente().get(punto.format(citato),
                                    headers={"User-Agent": UA}, timeout=8)
            if r.status_code == 200:
                return str(r.json().get("thumbnail_url") or "") or None
        except (httpx.HTTPError, ValueError):
            pass
        return None   # il sito e' riconosciuto: se la sua oEmbed tace, tace
    return None


async def _dalla_pagina(url: str) -> str | None:
    """`og:image`: una sola richiesta, e ce l'hanno quasi tutti."""
    try:
        r = await cliente().get(url, headers={"User-Agent": UA}, timeout=10)
        if r.status_code != 200:
            return None
        testo = r.text[:400_000]   # l'og:image sta nella testa: il resto e' peso
    except (httpx.HTTPError, UnicodeDecodeError):
        return None
    trovato = _OG.search(testo) or _OG_ROVESCIO.search(testo)
    if not trovato:
        return None
    return urllib.parse.urljoin(str(r.url), html.unescape(trovato.group(1)))


async def _da_yt_dlp(url: str) -> str | None:
    """L'ultima spiaggia, e si vede: costa secondi."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp", "--no-playlist", "--no-warnings", "--skip-download",
            "--get-thumbnail", url,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    except FileNotFoundError:
        return None
    try:
        uscita, _ = await asyncio.wait_for(proc.communicate(), timeout=25)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return None
    righe = uscita.decode("utf-8", "replace").strip().splitlines()
    return righe[0].strip() if righe and righe[0].startswith("http") else None


async def dove_sta(url: str) -> str | None:
    """L'indirizzo dell'immagine, dal modo piu' economico in giu'."""
    trovato = _YOUTUBE.search(url)
    if trovato:
        # mqdefault e non maxres: quest'ultima non esiste per tutti i video e
        # risponde 404, che vorrebbe dire una richiesta buttata su ogni voce
        return f"https://i.ytimg.com/vi/{trovato.group(1)}/mqdefault.jpg"

    trovato = _TWITCH.search(url)
    if trovato:
        return ("https://static-cdn.jtvnw.net/previews-ttv/"
                f"live_user_{trovato.group(1).lower()}-640x360.jpg")

    return (await _oembed(url)
            or await _dalla_pagina(url)
            or await _da_yt_dlp(url))


async def scarica(indirizzo: str, da_dove: str) -> tuple[bytes, str] | None:
    """L'immagine vera. `da_dove` e' il Referer: certi CDN senza lo rifiutano."""
    try:
        r = await cliente().get(indirizzo, timeout=15, headers={
            "User-Agent": UA, "Referer": da_dove, "Accept": "image/*,*/*"})
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    if not r.headers.get("content-type", "").lower().startswith("image/"):
        return None
    dati = r.content[:MASSIMO_BYTE]
    # sotto il mezzo kilobyte non e' una copertina: e' il pixel trasparente
    # che certi siti servono al posto di un 404
    return (dati, _tipo_di(dati)) if len(dati) > 512 else None


def pronta(url: str) -> tuple[bytes, str] | None:
    """La copertina se e' gia' su disco, senza toccare la rete.

    Esiste separata da `copertina()` perche' la pagina non deve aspettare:
    cercare una copertina puo' costare venticinque secondi di yt-dlp, e con
    venti voci in elenco vorrebbe dire una home che non si apre. Chi chiede
    una copertina non pronta riceve subito un no, la ricerca parte in
    disparte, e il browser riprova fra un po'.
    """
    via = _su_disco(url)
    if not via.exists():
        return None
    dati = via.read_bytes()
    return dati, _tipo_di(dati)


_in_corso: set[str] = set()


def scalda(url: str) -> None:
    """Fa partire la ricerca in disparte, una sola volta per indirizzo.

    Senza il registro di quelle in corso, quattro tentativi del browser sulla
    stessa copertina farebbero partire quattro ricerche - e quella di yt-dlp
    costa un processo l'una.
    """
    if url in _in_corso:
        return
    _in_corso.add(url)

    async def lavora() -> None:
        try:
            await copertina(url)
        finally:
            _in_corso.discard(url)

    # il riferimento si tiene, altrimenti il raccoglitore di rifiuti puo'
    # portarsi via il compito a meta' - e capirne il motivo costa un giorno
    compito = asyncio.create_task(lavora())
    _compiti.add(compito)
    compito.add_done_callback(_compiti.discard)


_compiti: set[asyncio.Task[None]] = set()


async def copertina(url: str) -> tuple[bytes, str] | None:
    """La copertina di questa pagina, dalla cache o cercandola adesso."""
    gia = pronta(url)
    if gia is not None:
        return gia

    if await deposito.cliente().get(CHIAVE_BUCO + _su_disco(url).name):
        return None   # cercata da poco e non trovata: non si riprova subito

    via = _su_disco(url)
    async with semaforo():
        # secondo controllo dentro il semaforo: mentre si aspettava, la stessa
        # copertina puo' essere arrivata per un'altra richiesta
        if via.exists():
            dati = via.read_bytes()
            return dati, _tipo_di(dati)

        indirizzo = await dove_sta(url)
        trovata = await scarica(indirizzo, url) if indirizzo else None

    if trovata is None:
        await deposito.cliente().set(CHIAVE_BUCO + via.name, "1",
                                     ex=VITA_BUCO_S)
        return None

    via.write_bytes(trovata[0])
    return trovata


def pota(ora: float, quanti_giorni: int = 30) -> int:
    """Le copertine piu' vecchie di tanto se ne vanno.

    Non e' una pulizia di cortesia: una cartella che cresce e non si svuota
    mai e' un disco che un giorno finisce, di notte, mentre nessuno guarda.
    """
    tolte = 0
    for f in cartella().iterdir():
        if f.is_file() and ora - f.stat().st_mtime > quanti_giorni * 86400:
            f.unlink(missing_ok=True)
            tolte += 1
    return tolte
