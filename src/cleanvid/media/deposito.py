"""Dove vivono i flussi estratti, e il semaforo che regola le estrazioni.

Nel cleanvid a file unico questo era un dizionario globale: `STREAMS[token]`.
Funzionava perche' il processo era uno solo e l'utente pure. Qui no.

Due ragioni per cui un dizionario non basta piu':

1. **Piu' processi.** Un servizio pubblico gira con piu' worker. Il token che
   ha registrato il worker A arriva al worker B, che non sa cosa sia: il video
   parte una volta su quattro e nessuno capisce perche'.
2. **Niente scade.** Quel dizionario cresceva finche' il processo viveva. Un
   indirizzo di googlevideo dura qualche ora, ma la riga restava per sempre.

Quindi Redis, con una scadenza su ogni chiave. E' gia' nell'architettura per
il polso delle stanze; qui fa lo stesso mestiere, tenere cose che devono
sparire da sole.

**La cache dell'estrazione ha per chiave `(url, qualita)` e non l'utente.**
E' la decisione che rende sostenibile una stanza da dieci persone: yt-dlp
costa qualche secondo di CPU, e dieci spettatori dello stesso video devono
costarne uno. Non c'e' niente di personale in un'estrazione - e' una proprieta'
del link, non di chi lo apre - quindi condividerla non mescola le cose di
nessuno.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from typing import Any

import redis.asyncio as redis

from ..config import impostazioni

_cliente: redis.Redis | None = None

# I prefissi stanno qui e non sparsi nel codice: un giorno si vorranno contare
# o svuotare, e serve sapere come si chiamano.
CHIAVE_FLUSSO = "flusso:"       # token -> cosa proxare
# `estr2`: la forma di cio' che si ricorda e' cambiata quando `Lettore` ed
# `Estratto` sono diventati una cosa sola. Cambiare prefisso fa ignorare le
# righe vecchie invece di leggerle male.
CHIAVE_ESTRAZIONE = "estr2:"     # (url, qualita) -> il risultato dell'estrazione
CHIAVE_ANNUNCI = "ads:"         # token -> quanti segmenti pubblicitari tolti
CHIAVE_ULTIMA = "lista:"        # l'ultima playlist con dentro roba vera

# Un flusso registrato vive piu' della sua cache di estrazione: chi sta
# guardando non deve vedersi staccare il video quando la cache scade.
VITA_FLUSSO_S = 6 * 3600


def cliente() -> redis.Redis:
    global _cliente
    if _cliente is None:
        _cliente = redis.from_url(
            impostazioni().redis_url,
            decode_responses=True,
            # se Redis e' giu', meglio un errore subito che una richiesta
            # appesa finche' il browser non si stanca
            socket_connect_timeout=3,
            socket_timeout=5,
        )
    return _cliente


async def chiudi() -> None:
    global _cliente
    if _cliente is not None:
        await _cliente.aclose()
    _cliente = None


# --------------------------------------------------------------------------
# i flussi registrati
# --------------------------------------------------------------------------

async def registra(dati: dict[str, Any]) -> str:
    """Mette da parte cosa proxare e restituisce il token per richiamarlo.

    Il token e' casuale e non dice niente di se': chi lo vede non sa ne' che
    video sia ne' di chi. L'alternativa - un token che si porta dentro
    l'indirizzo vero, firmato - eviterebbe Redis, ma finirebbe nei log di ogni
    intermediario e renderebbe l'indirizzo di googlevideo leggibile a chiunque
    guardi il traffico.
    """
    token = secrets.token_urlsafe(12)
    await cliente().set(CHIAVE_FLUSSO + token, json.dumps(dati),
                        ex=VITA_FLUSSO_S)
    return token


async def leggi(token: str) -> dict[str, Any] | None:
    grezzo = await cliente().get(CHIAVE_FLUSSO + token)
    return json.loads(grezzo) if grezzo else None


async def rinnova(token: str) -> None:
    """Chi sta ancora guardando tiene vivo il suo flusso."""
    await cliente().expire(CHIAVE_FLUSSO + token, VITA_FLUSSO_S)


# --------------------------------------------------------------------------
# la cache delle estrazioni
# --------------------------------------------------------------------------

def _chiave(url: str, qualita: str) -> str:
    # l'indirizzo va nella chiave passato per un digest: certi link sono
    # lunghissimi, e Redis non e' il posto dove tenere l'elenco in chiaro di
    # cosa guarda la gente
    impronta = hashlib.sha256(f"{url}\x00{qualita}".encode()).hexdigest()[:32]
    return CHIAVE_ESTRAZIONE + impronta


async def estrazione_in_cache(url: str, qualita: str) -> dict[str, Any] | None:
    grezzo = await cliente().get(_chiave(url, qualita))
    return json.loads(grezzo) if grezzo else None


async def ricorda_estrazione(url: str, qualita: str,
                             esito: dict[str, Any]) -> None:
    await cliente().set(_chiave(url, qualita), json.dumps(esito),
                        ex=impostazioni().cache_estrazione_s)


async def dimentica_estrazione(url: str, qualita: str) -> None:
    """Quando il flusso in cache non va piu': si rifa', non si insiste."""
    await cliente().delete(_chiave(url, qualita))


# --------------------------------------------------------------------------
# il semaforo
# --------------------------------------------------------------------------

_semaforo: asyncio.Semaphore | None = None


def semaforo() -> asyncio.Semaphore:
    """Quante estrazioni possono girare insieme in questo processo.

    yt-dlp e' un processo esterno che consuma CPU e rete per qualche secondo.
    Senza un tetto, venti persone che aprono un link nello stesso momento
    aprono venti yt-dlp, la macchina va in ginocchio e falliscono tutte e
    venti - anche quelle che da sole sarebbero riuscite. Con il tetto, le
    prime quattro passano e le altre aspettano il loro turno.

    E' per processo e non per macchina: basta a proteggere la CPU, e un
    semaforo distribuito su Redis sarebbe una serratura in piu' da manutenere
    per un guadagno che non si vede.
    """
    global _semaforo
    if _semaforo is None:
        _semaforo = asyncio.Semaphore(impostazioni().estrazioni_insieme)
    return _semaforo


# --------------------------------------------------------------------------
# il conto della pubblicita' tolta
# --------------------------------------------------------------------------

async def segna_annunci(token: str, quanti: int) -> None:
    if quanti <= 0:
        return
    c = cliente()
    await c.incrby(CHIAVE_ANNUNCI + token, quanti)
    await c.expire(CHIAVE_ANNUNCI + token, VITA_FLUSSO_S)


async def annunci_tolti(token: str) -> int:
    return int(await cliente().get(CHIAVE_ANNUNCI + token) or 0)


# --------------------------------------------------------------------------
# l'ultima playlist buona
# --------------------------------------------------------------------------
#
# Durante una pubblicita' cucita dentro una diretta puo' succedere che, tolti
# gli spot, non resti NIENTE: e' il preroll, il pezzo di reclame che va prima
# che la diretta cominci davvero. Li' una playlist senza un solo segmento non
# e' una risposta utile - certi lettori la prendono per un errore e si
# fermano, ed e' esattamente il momento in cui sembra che il sito sia rotto.
#
# Si tiene da parte l'ultima che aveva roba vera, e si serve quella: per il
# lettore e' una diretta che non ha ancora niente di nuovo, cioe' una cosa
# normalissima che sa gestire. I segmenti non li riscarica, perche' li conosce
# gia' dal loro numero.
#
# Vita breve: se la pubblicita' dura piu' di un minuto, ripetere all'infinito
# roba vecchia sarebbe peggio che dire la verita'.
VITA_ULTIMA_S = 60


def _chiave_lista(token: str, url: str) -> str:
    impronta = hashlib.sha256(url.encode()).hexdigest()[:16]
    return f"{CHIAVE_ULTIMA}{token}:{impronta}"


async def ricorda_playlist(token: str, url: str, testo: str) -> None:
    await cliente().set(_chiave_lista(token, url), testo, ex=VITA_ULTIMA_S)


async def ultima_playlist(token: str, url: str) -> str | None:
    trovata = await cliente().get(_chiave_lista(token, url))
    # il cliente e' aperto con `decode_responses`, quindi quello che torna e'
    # gia' testo; il controllo e' per chi legge, non per il programma
    return trovata if isinstance(trovata, str) else None
