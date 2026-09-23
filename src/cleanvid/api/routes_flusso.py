"""Le due rotte da cui escono i byte del video.

`/flusso/{token}` e' quello che finisce nel `src` del tag video: un file
intero, oppure un master HLS scritto da noi.
`/segmento` e' dove tornano tutti i pezzi di un flusso HLS, uno per uno.

Sono separate perche' fanno due mestieri diversi: la prima sa cos'e' quel
token, la seconda deve fidarsi solo di una firma. Tenerle insieme avrebbe
voluto dire una rotta che a volte controlla la firma e a volte no, cioe' il
posto perfetto dove sbagliare.

Nessuna delle due chiede chi sei. Un token e' gia' una prova di aver aperto
quel video, e legarlo all'utente vorrebbe dire che il link di un video non
funziona piu' in una stanza condivisa - che e' tutto il punto delle stanze.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from ..media import deposito, proxy
from ..media.estrazione import master_da
from ..media.firme import firma_valida
from ..media.manifesto import riscrivi_playlist

router = APIRouter(tags=["flusso"])

TIPO_PLAYLIST = "application/vnd.apple.mpegurl"


def _playlist(testo: str) -> Response:
    # `no-store` e non una scadenza breve: in una diretta la playlist cambia
    # ogni pochi secondi, e una copia vecchia in mezzo alla strada fa vedere
    # a chi guarda un pezzo di trasmissione di due minuti fa.
    return Response(content=testo, media_type=TIPO_PLAYLIST,
                    headers={"Cache-Control": "no-store"})


async def _passa(url: str, intestazioni: dict[str, str], token: str,
                 intervallo: str | None) -> Response:
    """Il giro comune: apri, guarda cos'e', riscrivi o lascia scorrere."""
    try:
        sorgente = await proxy.apri(url, intestazioni, intervallo)
    except proxy.Irraggiungibile as e:
        raise HTTPException(status_code=e.codice, detail=str(e)) from e

    if sorgente.e_playlist:
        testo = (await proxy.tutto(sorgente)).decode("utf-8", "replace")
        ripulita = riscrivi_playlist(token, str(sorgente.risposta.url), testo)
        await deposito.segna_annunci(token, ripulita.tolti)

        if ripulita.solo_annunci:
            # preroll: tolti gli spot non e' rimasto niente. Una playlist
            # senza un solo segmento certi lettori la prendono per un errore e
            # si fermano - ed e' il momento in cui sembra che il sito sia
            # rotto. Si serve l'ultima che aveva roba vera: per il lettore e'
            # una diretta che non ha ancora niente di nuovo, cioe' una cosa
            # normale che sa gestire.
            vecchia = await deposito.ultima_playlist(token, url)
            if vecchia is not None:
                return _playlist(vecchia)
        else:
            await deposito.ricorda_playlist(token, url, ripulita.testo)

        return _playlist(ripulita.testo)

    return StreamingResponse(
        proxy.scorri(sorgente),
        status_code=sorgente.risposta.status_code,
        headers=proxy.intestazioni_di_ritorno(sorgente.risposta),
    )


@router.get("/flusso/{token}")
async def flusso(token: str, request: Request) -> Response:
    dati = await deposito.leggi(token)
    if dati is None:
        # 404 e non 403: il token non e' sbagliato, e' scaduto. La pagina che
        # lo riceve deve rifare l'estrazione, non dire "non hai i permessi".
        raise HTTPException(status_code=404,
                            detail="questo flusso e' scaduto, riapri il video")

    await deposito.rinnova(token)

    if dati["tipo"] == "master":
        return _playlist(master_da(dati, token))

    return await _passa(dati["url"], dati["intestazioni"], token,
                        request.headers.get("Range"))


@router.get("/segmento")
async def segmento(
    request: Request,
    t: str = Query(..., description="il flusso a cui appartiene"),
    u: str = Query(..., description="l'indirizzo del pezzo"),
    s: str = Query(..., description="la firma"),
) -> Response:
    if not firma_valida(t, u, s):
        # senza questo controllo siamo un proxy aperto: chiunque potrebbe far
        # uscire traffico qualunque dalla nostra macchina, e verrebbe trovato
        raise HTTPException(status_code=403, detail="richiesta non firmata")

    dati = await deposito.leggi(t)
    if dati is None:
        raise HTTPException(status_code=404, detail="flusso scaduto")

    return await _passa(u, dati["intestazioni"], t,
                        request.headers.get("Range"))


@router.get("/sottotitoli/{token}")
async def sottotitoli(token: str) -> Response:
    """Una traccia di sottotitoli, servita da noi.

    Passa da qui e non diretta per due ragioni: il tag `<track>` pretende che
    il file venga dalla stessa origine della pagina - se no il browser lo
    scarica e poi si rifiuta di usarlo, senza dire perche' - e quegli
    indirizzi vogliono comunque le nostre intestazioni.

    Il tipo si dichiara noi e non si copia da monte: certi siti li servono
    come `text/plain` o come `application/octet-stream`, e con quelli il
    browser non li mostra.
    """
    dati = await deposito.leggi(token)
    if dati is None:
        raise HTTPException(status_code=404, detail="questa traccia e' scaduta")

    try:
        sorgente = await proxy.apri(dati["url"], dati["intestazioni"])
    except proxy.Irraggiungibile as e:
        raise HTTPException(status_code=e.codice, detail=str(e)) from e

    testo = await proxy.tutto(sorgente)
    return Response(testo, media_type="text/vtt; charset=utf-8", headers={
        # sono file piccoli e immutabili: riscaricarli a ogni ricarica della
        # pagina e' banda regalata
        "Cache-Control": "public, max-age=3600",
    })
