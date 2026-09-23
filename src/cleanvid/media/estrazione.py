"""Dal link al flusso: la cosa piu' cara che facciamo.

yt-dlp costa qualche secondo di CPU per chiamata. Tutto quello che c'e' qui
gira attorno a quel numero: la cache condivisa, il semaforo, il fatto che il
processo si lanci senza bloccare il resto del server.

**Perche' asincrono e non `subprocess.run`.** Nel file unico ogni richiesta
aveva il suo thread e bloccare non faceva danno. Qui c'e' un solo ciclo di
eventi: cinque secondi di `subprocess.run` sono cinque secondi in cui non si
muove nient'altro - non le altre pagine, non le chat delle stanze, non i
byte dei video gia' in corso. Con `create_subprocess_exec` il ciclo resta
libero e aspetta solo chi ha chiesto quell'estrazione.

**Cosa non e' passato dal file unico.** Il muxing in diretta - yt-dlp e ffmpeg
che cuciono video e audio mentre si guarda - costa un processo per spettatore,
non permette di saltare avanti e produce un formato che meta' browser non
suona. In locale era un ripiego accettabile; su un servizio aperto e' il modo
di far cadere la macchina con dieci persone. Al suo posto ci sono le due
tracce separate, che il browser tiene allineate da solo, e il master HLS per
le dirette: costo sul server, zero.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from typing import Any

from ..config import impostazioni
from . import deposito
from .fonte import DIRETTA, HLS, Fonte
from .manifesto import UA, corpo_master, scegli_tracce
from .qualita import selettore_separati, selettore_singolo, tetto_altezza
from .sottotitoli import Traccia
from .sottotitoli import scegli as scegli_sottotitoli


class NonEstraibile(RuntimeError):
    """Da questo link non esce un video, e si sa dire perche'."""


def _comando(*extra: str) -> list[str]:
    return ["yt-dlp", "--no-playlist", "--no-warnings", *extra]


def in_diretta(info: dict[str, Any]) -> bool:
    return bool(info.get("is_live")) or info.get("live_status") in (
        "is_live", "post_live")


async def interroga(url: str, formato: str | None) -> tuple[dict[str, Any] | None, str]:
    """-> (quello che dice yt-dlp, "") oppure (None, perche' non ha funzionato)."""
    args = ["-J"] + (["-f", formato] if formato else [])
    try:
        proc = await asyncio.create_subprocess_exec(
            *_comando(*args, url),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return None, "yt-dlp non e' installato su questa macchina"

    attesa = impostazioni().timeout_estrazione_s
    try:
        uscita, errori = await asyncio.wait_for(proc.communicate(), timeout=attesa)
    except TimeoutError:
        # il processo va ucciso a mano: wait_for annulla l'attesa, non il figlio,
        # e un yt-dlp orfano resta a consumare rete finche' non si arrende
        proc.kill()
        await proc.wait()
        return None, f"yt-dlp non ha risposto entro {attesa} secondi"

    if proc.returncode != 0:
        righe = (errori.decode("utf-8", "replace")).strip().splitlines()
        return None, righe[-1] if righe else "yt-dlp ha fallito"
    try:
        return json.loads(uscita), ""
    except json.JSONDecodeError:
        return None, "yt-dlp ha risposto qualcosa di illeggibile"


def _intestazioni(fmt: dict[str, Any], info: dict[str, Any]) -> dict[str, str]:
    h = dict(fmt.get("http_headers") or info.get("http_headers") or {})
    h.setdefault("User-Agent", UA)
    return h


def _coppia(info: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Video muto e audio a parte, se e' cosi' che arrivano.

    Si rifiuta la coppia quando le tracce sono a segmenti (HLS o DASH): quelle
    vanno servite con un manifest, non come due file interi, e chiamare
    l'indirizzo di una playlist "il file video" non porta lontano.
    """
    fmts = info.get("requested_formats") or []
    if len(fmts) != 2:
        return None
    video = next((f for f in fmts if (f.get("vcodec") or "none") != "none"), None)
    audio = next((f for f in fmts if (f.get("vcodec") or "none") == "none"), None)
    if not (video and audio and video.get("url") and audio.get("url")):
        return None
    for f in (video, audio):
        protocollo = f.get("protocol") or ""
        if "m3u8" in protocollo or "dash" in protocollo:
            return None
    return video, audio


async def risolvi(url: str, qualita: str = "", lingua: str = "en") -> Fonte:
    """Il flusso da dare al browser. Solleva NonEstraibile se non se ne cava.

    La cache si guarda prima del semaforo: chi arriva su un video gia' estratto
    non deve mettersi in coda dietro a quattro estrazioni in corso.
    """
    ricordato = await deposito.estrazione_in_cache(url, qualita)
    if ricordato:
        return _dal_ricordo(ricordato)

    async with deposito.semaforo():
        # secondo controllo dentro il semaforo: mentre si aspettava il turno,
        # qualcun altro puo' aver estratto esattamente questo. Senza, dieci
        # persone che aprono insieme lo stesso link fanno dieci estrazioni -
        # cioe' esattamente quello che la cache doveva evitare.
        ricordato = await deposito.estrazione_in_cache(url, qualita)
        if ricordato:
            return _dal_ricordo(ricordato)

        esito = await _estrai(url, qualita, lingua)

    await deposito.ricorda_estrazione(url, qualita, asdict(esito))
    return esito


async def _sottotitoli(info: dict[str, Any], lingua: str) -> list[Traccia]:
    """Le tracce scelte, gia' registrate e pronte da mettere in pagina.

    Si registrano come tutto il resto che serviamo noi: un `<track>` deve
    venire dalla stessa origine della pagina, o il browser si rifiuta di
    leggerlo - e comunque quegli indirizzi vogliono le nostre intestazioni.
    """
    fuori: list[Traccia] = []
    for indirizzo, traccia in scegli_sottotitoli(info, lingua):
        token = await deposito.registra({
            "tipo": "sottotitoli", "url": indirizzo,
            "intestazioni": {"User-Agent": UA}})
        traccia.indirizzo = f"/sottotitoli/{token}"
        fuori.append(traccia)
    return fuori


def _flusso(token: str) -> str:
    """L'indirizzo con cui il browser chiede un nostro flusso.

    E' l'unico punto in cui `media/` conosce un indirizzo delle rotte, ed e'
    voluto: l'alternativa era far costruire quell'indirizzo a ognuna delle
    quattro pagine che mostrano un video, cioe' avere la stessa riga scritta
    quattro volte in posti che nessuno guarda insieme.
    """
    return f"/flusso/{token}"


def _dal_ricordo(dati: dict[str, Any]) -> Fonte:
    """Rimette in piedi una Fonte da quello che stava in Redis.

    Le tracce dei sottotitoli, passando per JSON, tornano come dizionari: qui
    ridiventano quello che erano. Senza, i modelli si troverebbero dei
    dizionari dove si aspettano un oggetto, e fallirebbero solo sui video che
    i sottotitoli ce l'hanno - cioe' a volte.
    """
    dati = dict(dati)
    dati["sottotitoli"] = [Traccia(**t) for t in dati.get("sottotitoli") or []]
    return Fonte(**dati)


async def _estrai(url: str, qualita: str, lingua: str = "en") -> Fonte:
    tetto = tetto_altezza(qualita)

    info, perche = await interroga(url, selettore_singolo(tetto))
    separati = False
    if info is None:
        info, perche2 = await interroga(url, selettore_separati(tetto))
        if info is None:
            raise NonEstraibile(perche2 or perche)
        separati = True

    titolo = info.get("title") or "video"
    diretta = in_diretta(info)

    # Una diretta con sole tracce separate va molto meglio con un master HLS
    # che con due file: il player ottiene il bordo della diretta e si riprende
    # da solo dopo un buco di rete, cose che due mp4 non sanno fare.
    if separati and diretta:
        master = scegli_tracce(info, tetto)
        if master is not None:
            token = await deposito.registra({
                "tipo": "master",
                "intestazioni": master.intestazioni,
                "video": [_essenziale(v) for v in master.video],
                "audio": _essenziale(master.audio),
            })
            # il corpo si costruisce al volo alla richiesta, non qui: il token
            # serve per scriverci dentro i link dei segmenti
            return Fonte(tipo=HLS, indirizzo=_flusso(token), token=token,
                         titolo=titolo, diretta=True,
                         sottotitoli=await _sottotitoli(info, lingua))

    if separati:
        coppia = _coppia(info)
        if coppia is None:
            raise NonEstraibile(
                "questo sito serve video e audio separati in un modo che non "
                "sappiamo ancora rimettere insieme")
        video, audio = coppia
        t_video = await deposito.registra({
            "tipo": "diretto", "url": video["url"],
            "intestazioni": _intestazioni(video, info)})
        t_audio = await deposito.registra({
            "tipo": "diretto", "url": audio["url"],
            "intestazioni": _intestazioni(audio, info)})
        return Fonte(
            tipo=DIRETTA, indirizzo=_flusso(t_video), token=t_video,
            indirizzo_audio=_flusso(t_audio), token_audio=t_audio,
            titolo=titolo, diretta=diretta, altezza=video.get("height") or 0,
            sottotitoli=await _sottotitoli(info, lingua),
        )

    flusso = info.get("url")
    if not flusso:
        raise NonEstraibile("nessun flusso riproducibile in un file solo")
    token = await deposito.registra({
        "tipo": "diretto", "url": flusso,
        "intestazioni": _intestazioni(info, info)})
    return Fonte(
        tipo=HLS if ".m3u8" in flusso.split("?")[0] else DIRETTA,
        indirizzo=_flusso(token), token=token,
        titolo=titolo, diretta=diretta, altezza=info.get("height") or 0,
        sottotitoli=await _sottotitoli(info, lingua),
    )


def _essenziale(f: dict[str, Any]) -> dict[str, Any]:
    """Solo i campi che servono a scrivere il master.

    yt-dlp restituisce dizionari da decine di chilobyte per formato; metterli
    interi in Redis vorrebbe dire riempirlo di roba che non guarderemo mai.
    """
    return {k: f.get(k) for k in
            ("url", "vcodec", "acodec", "tbr", "abr", "width", "height")}


def master_da(dati: dict[str, Any], token: str) -> str:
    """Il testo del master HLS a partire da quello che si era messo da parte."""
    from .manifesto import Master
    return corpo_master(token, Master(video=dati["video"], audio=dati["audio"],
                                      intestazioni=dati["intestazioni"]))
