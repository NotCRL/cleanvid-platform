"""I byte del video che passano da noi, e perche' devono passare da noi.

Tre ragioni, tutte concrete:

1. **Le intestazioni.** Quasi ogni sito rifiuta di servire il proprio flusso
   se non arriva con il `Referer` e lo `User-Agent` giusti. Il tag `<video>`
   del browser non li manda e non si possono aggiungere.
2. **Le origini.** Il browser non lascia leggere un flusso che viene da un
   altro dominio senza il permesso di quel dominio, che nessuno da'.
3. **La pubblicita' cucita dentro.** Quella che arriva negli stessi byte del
   video non la vede nessun blocco lato browser. Si toglie solo qui, mentre
   la playlist passa.

Il prezzo e' che i byte passano dalla nostra rete. E' il costo vero del
servizio, ed e' bene averlo in mente quando si guarda una bolletta.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

# 256 KiB: abbastanza grande da non fare mille passaggi per un segmento,
# abbastanza piccolo da non tenere mezzo megabyte per spettatore in memoria.
BOCCONE = 262144

# Le uniche intestazioni che ha senso riportare indietro. Copiarle tutte
# vorrebbe dire ripassare al browser i cookie e le tracciature del sito da
# cui arriva il flusso, che e' esattamente cio' che si voleva evitare.
DA_RIPORTARE = ("Content-Type", "Content-Length", "Content-Range",
                "Accept-Ranges", "Cache-Control")

_cliente: httpx.AsyncClient | None = None


def cliente() -> httpx.AsyncClient:
    """Un cliente HTTP per tutto il processo, con le connessioni riusate.

    Aprirne uno per richiesta significa rifare handshake TLS a ogni segmento,
    e un flusso HLS e' un segmento ogni due secondi per ogni spettatore.
    """
    global _cliente
    if _cliente is None:
        _cliente = httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(30.0, read=60.0),
            limits=httpx.Limits(max_connections=200,
                                max_keepalive_connections=50),
        )
    return _cliente


async def chiudi() -> None:
    global _cliente
    if _cliente is not None:
        await _cliente.aclose()
    _cliente = None


class Irraggiungibile(RuntimeError):
    """Il sito da cui viene il flusso non ha risposto, o ha detto di no."""

    def __init__(self, messaggio: str, codice: int = 502) -> None:
        super().__init__(messaggio)
        self.codice = codice


@dataclass(slots=True)
class Sorgente:
    """Un flusso aperto a monte, con il primo boccone gia' in mano.

    Esiste per un motivo solo, e vale la pena scriverlo: **lo stream di httpx
    si legge una volta sola**. Chiamare `aiter_bytes` una seconda volta
    solleva `StreamConsumed`, anche se la prima si era fermata dopo sette
    byte. Quindi l'iteratore si apre qui, una volta, e passa di mano intero;
    i byte gia' letti viaggiano con lui, perche' non si possono rimettere
    dentro.
    """

    risposta: httpx.Response
    primi: bytes
    pezzi: AsyncIterator[bytes]

    @property
    def e_playlist(self) -> bool:
        # i server di Google etichettano come `mpegurl` anche i segmenti veri:
        # l'unico criterio affidabile e' guardare come comincia il contenuto
        return self.primi.startswith(b"#EXTM3U")


async def apri(url: str, intestazioni: dict[str, str],
               intervallo: str | None = None) -> Sorgente:
    """Apre il flusso a monte e legge il primo boccone."""
    testa = dict(intestazioni)
    if intervallo:
        # il salto avanti e indietro nel video e' tutto qui: il browser chiede
        # un pezzo, e quel pezzo va chiesto identico a monte
        testa["Range"] = intervallo

    richiesta = cliente().build_request("GET", url, headers=testa)
    try:
        risposta = await cliente().send(richiesta, stream=True)
    except httpx.HTTPError as e:
        raise Irraggiungibile(f"il sito non risponde: {e}") from e

    if risposta.status_code >= 400:
        await risposta.aclose()
        raise Irraggiungibile(f"il sito ha risposto {risposta.status_code}",
                              codice=risposta.status_code)

    pezzi = risposta.aiter_bytes(BOCCONE)
    primi = await anext(pezzi, b"")
    return Sorgente(risposta=risposta, primi=primi, pezzi=pezzi)


async def scorri(s: Sorgente) -> AsyncIterator[bytes]:
    """I byte, dal principio, senza perdere quelli gia' letti."""
    try:
        if s.primi:
            yield s.primi
        async for pezzo in s.pezzi:
            yield pezzo
    finally:
        # va chiusa comunque: se il player fa un salto, la connessione dalla
        # sua parte sparisce a meta', e senza questo la nostra resterebbe
        # aperta verso il sito a scaricare byte che nessuno guarda
        await s.risposta.aclose()


async def tutto(s: Sorgente) -> bytes:
    """Il contenuto intero, per le playlist: sono piccole e vanno riscritte."""
    try:
        pezzi = [s.primi]
        async for pezzo in s.pezzi:
            pezzi.append(pezzo)
        return b"".join(pezzi)
    finally:
        await s.risposta.aclose()


def intestazioni_di_ritorno(risposta: httpx.Response) -> dict[str, str]:
    fuori: dict[str, str] = {}
    for nome in DA_RIPORTARE:
        valore = risposta.headers.get(nome)
        if valore:
            fuori[nome] = valore
    tipo = fuori.get("Content-Type", "").lower()
    if "mpegurl" in tipo:
        # arrivati qui si e' gia' stabilito che non e' una playlist: e' un
        # segmento etichettato male, e dirlo al browser lo fa inciampare
        fuori["Content-Type"] = "video/mp2t"
    return fuori
