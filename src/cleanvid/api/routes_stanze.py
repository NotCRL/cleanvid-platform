"""Le stanze: crearne una, entrarci, e restare allineati.

La sincronia passa da un WebSocket, e il motivo sta in
`docs/confronti/RISPOSTA-2.md`: fra i due problemi di una watchparty - la
sincronia e la consegna dei byte - il primo vuole ordine e bassa latenza, e
per quello un WebSocket è lo strumento giusto e costa quasi niente.

**Il token dei segmenti sarà per stanza, non per utente.** Non serve ancora -
oggi ognuno risolve il proprio flusso per conto suo, con la sua qualità e la
sua banda - ma è la decisione che permetterà di aggiungere la condivisione fra
partecipanti senza riscrivere niente. Sta scritta qui perché è qui che
servirà.
"""

from __future__ import annotations

import time
import uuid

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_303_SEE_OTHER

from ..db import fabbrica, sessione
from ..media.estrazione import NonEstraibile, risolvi
from ..media.fonte import Fonte
from ..models import (
    MembroStanza,
    MessaggioStanza,
    RuoloInStanza,
    Stanza,
    Utente,
    Visibilita,
)
from ..rooms import codici, protocol
from ..rooms.hub import Presente, hub
from ..rooms.protocol import (
    CHAT_MASSIMO,
    CHAT_STORIA,
    PERMESSI,
    Messaggio,
    StatoRiproduzione,
    Tipo,
    Verso,
)
from ..web.pagine import modelli
from . import credenziali
from .contesto import Contesto, contesto
from .identita import utente_corrente

router = APIRouter(prefix="/{lingua_url}", include_in_schema=False)

# Quante stanze aperte può avere una persona. Non è avarizia: una stanza tiene
# in piedi delle connessioni, e senza un tetto basta un ciclo distratto per
# riempire il server di stanze vuote.
MASSIMO_PER_UTENTE = 5


async def _sue_aperte(db: AsyncSession, utente_id: uuid.UUID) -> int:
    righe = await db.execute(select(Stanza.id).where(
        Stanza.padrone_id == utente_id, Stanza.aperta.is_(True)))
    return len(righe.all())


@router.get("/stanze", response_class=HTMLResponse)
async def elenco(
    request: Request,
    c: Contesto = Depends(contesto),
    db: AsyncSession = Depends(sessione),
) -> Response:
    """Le stanze pubbliche aperte, più le proprie."""
    pubbliche = (await db.execute(
        select(Stanza)
        .where(Stanza.visibilita == Visibilita.PUBBLICA, Stanza.aperta.is_(True))
        .order_by(Stanza.ultima_attivita.desc())
        .limit(30))).scalars().all()
    mie = (await db.execute(
        select(Stanza)
        .where(Stanza.padrone_id == c.utente.id, Stanza.aperta.is_(True))
        .order_by(Stanza.creata.desc()))).scalars().all()

    return modelli.TemplateResponse(request, "stanze.html", {
        "c": c, "t": c.t, "utente": c.utente,
        "pubbliche": [s for s in pubbliche if s.padrone_id != c.utente.id],
        "mie": mie,
        "quante_dentro": {s.codice: hub.quanti(s.codice)
                          for s in (*pubbliche, *mie)},
    })


@router.post("/stanze/apri")
async def apri(
    lingua_url: str,
    titolo: str = Form(""),
    url: str = Form(""),
    visibilita: str = Form("non_in_elenco"),
    password: str = Form(""),
    utente: Utente = Depends(utente_corrente),
    db: AsyncSession = Depends(sessione),
) -> Response:
    if await _sue_aperte(db, utente.id) >= MASSIMO_PER_UTENTE:
        return RedirectResponse(f"/{lingua_url}/stanze?guaio=troppe",
                                status_code=HTTP_303_SEE_OTHER)

    # si riprova finché non se ne trova uno libero: con diciottomila
    # combinazioni capita quasi mai, ma «quasi mai» non è «mai»
    for _ in range(8):
        codice = codici.nuovo()
        gia = (await db.execute(
            select(Stanza.id).where(Stanza.codice == codice))).first()
        if gia is None:
            break
    else:
        raise HTTPException(status_code=503, detail="riprova fra un momento")

    stanza = Stanza(
        codice=codice,
        titolo=(titolo or "").strip()[:80] or codice,
        padrone_id=utente.id,
        visibilita=(Visibilita(visibilita)
                    if visibilita in {v.value for v in Visibilita}
                    else Visibilita.NON_IN_ELENCO),
        password_hash=credenziali.impronta(password) if password else None,
        url_corrente=url.strip() or None,
    )
    db.add(stanza)
    db.add(MembroStanza(stanza=stanza, utente_id=utente.id,
                        ruolo=RuoloInStanza.PADRONE))
    await db.flush()
    return RedirectResponse(f"/{lingua_url}/stanza/{codice}",
                            status_code=HTTP_303_SEE_OTHER)


async def _e_membro(db: AsyncSession, stanza_id: uuid.UUID,
                    utente_id: uuid.UUID) -> bool:
    riga = await db.execute(select(MembroStanza.id).where(
        MembroStanza.stanza_id == stanza_id,
        MembroStanza.utente_id == utente_id))
    return riga.first() is not None


async def _puo_entrare(db: AsyncSession, stanza: Stanza,
                       utente_id: uuid.UUID) -> bool:
    """La password si chiede una volta sola.

    Chi l'ha indovinata diventa membro della stanza, e da quel momento entra
    come chiunque altro: senza, ogni ricarica della pagina - e ogni riconnessione
    del filo dopo un tunnel - la richiederebbe di nuovo.
    """
    if not stanza.protetta or stanza.padrone_id == utente_id:
        return True
    return await _e_membro(db, stanza.id, utente_id)


async def _trova(db: AsyncSession, codice: str) -> Stanza | None:
    if not codici.plausibile(codice):
        return None
    return (await db.execute(
        select(Stanza).where(Stanza.codice == codice))).scalar_one_or_none()


@router.get("/stanza/{codice}", response_class=HTMLResponse)
async def stanza(
    request: Request,
    codice: str,
    u: str = "",
    c: Contesto = Depends(contesto),
    db: AsyncSession = Depends(sessione),
) -> Response:
    """La pagina della stanza.

    **Ognuno risolve il proprio flusso per conto suo.** La stanza si passa
    l'indirizzo della pagina, non quello del flusso: gli indirizzi dei flussi
    scadono e sono legati a chi li ha chiesti, quindi mandarli in giro non
    funzionerebbe comunque. In piu' cosi' ognuno sceglie la propria qualita'
    secondo la propria banda, che in una stanza da dieci non e' un dettaglio.
    """
    trovata = await _trova(db, codice)
    if trovata is None or not trovata.aperta:
        raise HTTPException(status_code=404, detail="stanza non trovata")

    e_padrone = trovata.padrone_id == c.utente.id

    if not await _puo_entrare(db, trovata, c.utente.id):
        return modelli.TemplateResponse(request, "stanza_password.html", {
            "c": c, "t": c.t, "utente": c.utente, "stanza": trovata,
            "sbagliata": request.query_params.get("sbagliata") is not None,
        }, status_code=403)

    # solo il padrone puo' cambiare quello che si guarda
    if u and e_padrone and u != trovata.url_corrente:
        trovata.url_corrente = u
        db.add(trovata)
        await db.flush()

    fonte: Fonte | None = None
    perche = ""
    indirizzo = trovata.url_corrente or ""
    if indirizzo:
        try:
            fonte = await risolvi(indirizzo, lingua=c.lingua.codice)
        except NonEstraibile as e:
            perche = str(e)
        if fonte is None:
            from ..media.embed import lettore_ufficiale
            fonte = lettore_ufficiale(
                indirizzo, host_pagina=request.url.hostname or "localhost")
            if fonte is not None:
                perche = ""

    # gli ultimi messaggi: chi entra a meta' serata deve poter leggere da
    # dove si e' arrivati, non trovare una stanza muta
    recenti = list(reversed((await db.execute(
        select(MessaggioStanza)
        .where(MessaggioStanza.stanza_id == trovata.id)
        .order_by(MessaggioStanza.id.desc())
        .limit(CHAT_STORIA))).scalars().all()))

    return modelli.TemplateResponse(request, "stanza.html", {
        "c": c, "t": c.t, "utente": c.utente,
        "stanza": trovata, "e_padrone": e_padrone, "chat": recenti,
        "chat_massimo": CHAT_MASSIMO,
        "fonte": fonte, "perche": perche,
        "quanti": hub.quanti(codice),
        "soglie": {
            "salto": protocol.SCARTO_SALTO,
            "ok": protocol.SCARTO_OK,
            "correzione": protocol.CORREZIONE_MAX,
            "battito": protocol.BATTITO_OGNI,
        },
    })


@router.post("/stanza/{codice}/entra")
async def entra(
    lingua_url: str,
    codice: str,
    password: str = Form(""),
    utente: Utente = Depends(utente_corrente),
    db: AsyncSession = Depends(sessione),
) -> Response:
    """La password della stanza.

    Non e' l'accesso al sito: qui si dimostra solo di essere stati invitati,
    quindi non c'e' niente da contare o da bloccare per email. Il freno e' la
    lentezza di argon2, che su un codice da indovinare a mano basta.
    """
    trovata = await _trova(db, codice)
    if trovata is None or not trovata.aperta:
        raise HTTPException(status_code=404, detail="stanza non trovata")

    if trovata.protetta and not credenziali.verifica(password,
                                                     trovata.password_hash):
        return RedirectResponse(f"/{lingua_url}/stanza/{codice}?sbagliata",
                                status_code=HTTP_303_SEE_OTHER)

    if not await _e_membro(db, trovata.id, utente.id):
        db.add(MembroStanza(stanza_id=trovata.id, utente_id=utente.id,
                            ruolo=RuoloInStanza.OSPITE))
        await db.flush()
    return RedirectResponse(f"/{lingua_url}/stanza/{codice}",
                            status_code=HTTP_303_SEE_OTHER)


@router.post("/stanza/{codice}/chiudi")
async def chiudi(
    lingua_url: str,
    codice: str,
    utente: Utente = Depends(utente_corrente),
    db: AsyncSession = Depends(sessione),
) -> Response:
    trovata = await _trova(db, codice)
    if trovata is None or trovata.padrone_id != utente.id:
        raise HTTPException(status_code=404, detail="stanza non trovata")
    trovata.aperta = False
    db.add(trovata)
    return RedirectResponse(f"/{lingua_url}/stanze", status_code=HTTP_303_SEE_OTHER)


# --------------------------------------------------------------------------
# il filo
# --------------------------------------------------------------------------

@router.websocket("/stanza/{codice}/filo")
async def filo(websocket: WebSocket, lingua_url: str, codice: str) -> None:
    """Il WebSocket della stanza.

    L'identità si legge dal cookie, come in ogni altra pagina: un WebSocket
    porta i cookie del sito da cui è stato aperto, quindi non serve inventare
    un secondo modo di sapere chi è chi.
    """
    from .identita import _leggi_cookie

    identificativo = _leggi_cookie(websocket)   # type: ignore[arg-type]
    if identificativo is None:
        await websocket.close(code=4001)
        return

    async with fabbrica()() as db:
        trovata = await _trova(db, codice)
        utente = await db.get(Utente, identificativo)
        if trovata is None or not trovata.aperta or utente is None:
            await websocket.close(code=4004)
            return
        # stessa regola della pagina: senza password non si entra nemmeno dal
        # filo, altrimenti la porta chiusa davanti avrebbe una finestra dietro
        if not await _puo_entrare(db, trovata, utente.id):
            await websocket.close(code=4003)
            return
        e_padrone = trovata.padrone_id == utente.id
        nome = utente.nome_visibile
        stanza_id = trovata.id

    await websocket.accept()
    chi = Presente(ws=websocket, utente_id=identificativo, nome=nome,
                   comanda=e_padrone)
    await hub.entra(codice, chi)

    try:
        # chi entra riceve subito dove siamo: senza, resterebbe fermo fino al
        # primo battito di chi comanda, che può essere fra quattro secondi
        stato = await hub.stato(codice)
        await websocket.send_json(Messaggio(
            tipo=Tipo.STATO, dati=asdict_stato(stato), t_server=time.time()
        ).json())
        await hub.a_tutti(codice, Messaggio(
            tipo=Tipo.ENTRATO, dati={"nome": nome}), tranne=chi)
        await hub.a_tutti(codice, await hub.elenco(codice))

        while True:
            arrivato = await websocket.receive_json()
            await _gestisci(codice, chi, arrivato, stanza_id)

    except WebSocketDisconnect:
        pass
    finally:
        await hub.esce(codice, chi)
        await hub.a_tutti(codice, Messaggio(
            tipo=Tipo.USCITO, dati={"nome": nome}))
        await hub.a_tutti(codice, await hub.elenco(codice))


async def _scrivi(codice: str, chi: Presente, dati: dict[str, object],
                  stanza_id: uuid.UUID, adesso: float) -> None:
    """Un messaggio di chat: lo scrivono tutti, anche chi non comanda.

    Si salva **prima** di mandarlo in giro. Al contrario, chi lo riceve lo
    vedrebbe comparire e poi sparire alla prima ricarica, e non saprebbe mai
    quali dei messaggi che ha letto esistono davvero.

    Il nome dell'autore si copia adesso invece di leggerlo dopo: se domani
    cambia nome, la chat di ieri deve restare leggibile com'era.
    """
    testo = str(dati.get("testo") or "").strip()[:CHAT_MASSIMO]
    if not testo:
        return
    if not chi.puo_scrivere(adesso):
        await chi.ws.send_json(Messaggio(
            tipo=Tipo.ERRORE, dati={"perche": "troppo_in_fretta"},
            t_server=adesso).json())
        return

    async with fabbrica()() as db:
        riga = MessaggioStanza(stanza_id=stanza_id, autore_id=chi.utente_id,
                               autore_nome=chi.nome, testo=testo)
        db.add(riga)
        await db.commit()

    # Chi l'ha scritto riceve una copia con «mio»: serve alla pagina per
    # disegnarlo dalla sua parte. Non si manda l'id dell'autore a tutti
    # proprio per non farlo: in una stanza si vede un nome, non un
    # identificativo con cui riconoscere la stessa persona altrove.
    await hub.a_tutti(codice, Messaggio(tipo=Tipo.MESSAGGIO, dati={
        "nome": chi.nome, "testo": testo}), tranne=chi)
    await chi.ws.send_json(Messaggio(
        tipo=Tipo.MESSAGGIO, dati={"nome": chi.nome, "testo": testo, "mio": True},
        t_server=adesso).json())


def asdict_stato(s: StatoRiproduzione) -> dict[str, object]:
    return {"url": s.url, "titolo": s.titolo, "posizione": s.posizione,
            "in_corsa": s.in_corsa, "velocita": s.velocita,
            "t_server": s.t_server}


async def _gestisci(codice: str, chi: Presente, arrivato: dict[str, object],
                    stanza_id: uuid.UUID) -> None:
    """Un messaggio in arrivo. Tutto quello che non è previsto si butta.

    La tabella dei permessi sta in `rooms/protocol.py`: qui non si decide
    niente, si guarda. Così aggiungere un messaggio vuol dire aggiungere una
    riga là, e non ricordarsi di mettere un controllo qui.
    """
    try:
        tipo = Tipo(str(arrivato.get("tipo")))
    except ValueError:
        return
    if PERMESSI.get(tipo) not in (Verso.AL_SERVER, Verso.ENTRAMBI):
        return

    dati = arrivato.get("dati")
    dati = dati if isinstance(dati, dict) else {}
    adesso = time.time()

    if tipo is Tipo.PING:
        # serve a chi sta dall'altra parte per misurare quanto è sbagliato il
        # proprio orologio: si rimanda indietro il suo istante e il nostro
        await chi.ws.send_json(Messaggio(
            tipo=Tipo.PONG, dati={"tuo": dati.get("tuo")},
            t_server=adesso).json())
        return

    if tipo is Tipo.MESSAGGIO:
        await _scrivi(codice, chi, dati, stanza_id, adesso)
        return

    if tipo is Tipo.SCRIVE:
        # effimero: non si salva e non torna a chi l'ha mandato. Se si
        # perde per strada non e' successo niente - e' il solo messaggio
        # del protocollo di cui questo sia vero
        await hub.a_tutti(codice, Messaggio(
            tipo=Tipo.SCRIVE, dati={"nome": chi.nome}), tranne=chi)
        return

    if not chi.comanda:
        return          # gli ospiti guardano: non comandano niente

    if tipo in (Tipo.COMANDA, Tipo.BATTITO):
        stato = StatoRiproduzione(
            url=str(dati.get("url") or "") or None,
            titolo=str(dati.get("titolo") or "") or None,
            posizione=float(dati.get("posizione") or 0.0),
            in_corsa=bool(dati.get("in_corsa")),
            velocita=float(dati.get("velocita") or 1.0),
            t_server=adesso,
        )
        await hub.salva_stato(codice, stato)
        await hub.a_tutti(codice, Messaggio(
            tipo=Tipo.STATO, dati=asdict_stato(stato)), tranne=chi)
        return

    if tipo is Tipo.CAMBIA_VIDEO:
        stato = StatoRiproduzione(
            url=str(dati.get("url") or "") or None,
            titolo=str(dati.get("titolo") or "") or None,
            posizione=0.0, in_corsa=False, t_server=adesso)
        await hub.salva_stato(codice, stato)
        async with fabbrica()() as db:
            s = await db.get(Stanza, stanza_id)
            if s is not None:
                s.url_corrente = stato.url
                s.titolo_corrente = stato.titolo
                await db.commit()
        await hub.a_tutti(codice, Messaggio(
            tipo=Tipo.STATO, dati=asdict_stato(stato)))
