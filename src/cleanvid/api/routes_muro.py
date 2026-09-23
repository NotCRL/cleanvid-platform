"""Il muro: da uno a quattro video insieme, e i gruppi che li riaprono.

Il muro vive quasi tutto nel browser - disposizione, misure, quale riquadro
ha l'audio - perche' sono cose che cambiano dieci volte al minuto mentre
qualcuno sistema le finestre, e mandarle al server a ogni movimento vorrebbe
dire una richiesta per ogni pixel trascinato.

Al server arriva solo quello che deve sopravvivere alla chiusura della scheda:
i gruppi. Il resto sta nel `localStorage`, che e' il posto giusto per una
preferenza di questo schermo.

`/cella` esiste perche' ogni riquadro e' un `iframe`: un `<video>` per
riquadro nella stessa pagina sembrerebbe piu' semplice, e invece no. Con
l'iframe ogni video ha il suo contesto - il suo lettore, il suo HLS, il suo
errore quando c'e' - e uno che si pianta non porta giu' gli altri tre.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import sessione
from ..lingue import testi
from ..media.embed import chat_incorporabile, lettore_ufficiale, piattaforma_di
from ..media.estrazione import NonEstraibile, risolvi
from ..media.fonte import Fonte
from ..media.qualita import QUALITA
from ..models import Genere, Utente
from ..web.pagine import modelli
from . import biblioteca
from .contesto import Contesto, contesto
from .identita import utente_corrente

router = APIRouter(prefix="/{lingua_url}", include_in_schema=False)

# Quattro e' il massimo, e non e' un numero tondo scelto a caso: oltre, su un
# portatile normale i video cominciano a saltare, e su un tablet gia' il
# quarto e' troppo. Meglio un limite dichiarato che quattro video a scatti.
MASSIMO_CELLE = 4


@router.get("/muro")
async def muro(
    request: Request,
    c: Contesto = Depends(contesto),
    db: AsyncSession = Depends(sessione),
) -> Response:
    """La pagina del muro. Quello che c'era dentro lo rimette il browser."""
    recenti = await biblioteca.elenco(db, c.utente.id, Genere.CRONOLOGIA,
                                      quante=18)
    preferiti = await biblioteca.elenco(db, c.utente.id, Genere.PREFERITO,
                                        quante=18)
    gruppi = await biblioteca.elenco(db, c.utente.id, Genere.GRUPPO, quante=20)
    return modelli.TemplateResponse(request, "muro.html", {
        "c": c, "t": c.t, "utente": c.utente,
        "recenti": recenti, "preferiti_voci": preferiti, "gruppi": gruppi,
        "qualita_possibili": QUALITA, "massimo": MASSIMO_CELLE,
        "testi_muro": _testi_per_javascript(c.lingua.codice),
    })


def _testi_per_javascript(codice: str) -> dict[str, str]:
    """Le frasi che servono al muro, passate al javascript in un colpo.

    Il muro costruisce quasi tutta la sua interfaccia da se', quindi quelle
    frasi non possono stare nel modello: gli servono a mano a mano. Si manda
    solo quello che usa - non tutto il catalogo - perche' sono dati che
    finiscono nell'HTML di ogni caricamento.
    """
    catalogo = testi(codice)
    scorta = testi("it")
    return {chiave: catalogo.get(chiave) or scorta.get(chiave, chiave)
            for chiave in scorta
            if chiave.startswith("muro.")
            or chiave in ("guarda.qualita", "guarda.diretta",
                          "guarda.torna_in_diretta", "guarda.come_viene",
                          "azione.elimina")}


@router.get("/cella")
async def cella(
    request: Request,
    u: str = "",
    q: str = "",
    c: Contesto = Depends(contesto),
) -> Response:
    """Un riquadro del muro: solo il lettore, niente intorno.

    Non annota la visita in cronologia. Aprire un muro da quattro non deve
    riempire la cronologia di quattro voci ogni volta che si ricarica la
    pagina: in cronologia ci va quello che si e' aperto di proposito.
    """
    if not u.startswith(("http://", "https://")):
        return RedirectResponse(f"/{c.lingua.codice}/muro", status_code=303)

    # NEL MURO L'ORDINE E' ROVESCIATO rispetto alla pagina singola: prima si
    # prova a estrarre, e il lettore della piattaforma e' il ripiego.
    #
    # Fuori dal muro vince il lettore loro perche' parte subito e non scade.
    # Dentro un riquadro pero' porta con se' tutta la sua interfaccia -
    # compreso il suo volume - e il muro ne disegna gia' una: due barre e due
    # volumi per riquadro, e chi guarda non sa quale toccare.
    #
    # E c'e' una ragione piu' grossa: al lettore di un altro sito possiamo
    # solo mandare messaggi e sperare. Al nostro <video> parliamo diretto, e
    # «l'audio su un riquadro solo» - che e' il cuore del muro - funziona
    # davvero invece che quasi sempre.
    fonte: Fonte | None = None
    perche = ""
    try:
        fonte = await risolvi(u, q, lingua=c.lingua.codice)
    except NonEstraibile as e:
        perche = str(e)

    if fonte is None:
        # non si e' potuto estrarre: meglio il lettore loro che un riquadro
        # vuoto. I suoi comandi si spengono con `controls=0`, cosi' almeno il
        # volume resta uno solo.
        fonte = lettore_ufficiale(
            u, host_pagina=request.url.hostname or "localhost", per_cella=True)
        if fonte is not None:
            perche = ""

    # La chat solo se e' una diretta: il `live_chat` di YouTube su un video
    # registrato apre un riquadro con dentro un errore, che e' peggio di
    # niente.
    chat = chat_incorporabile(
        u, request.url.hostname or "localhost") if (
            fonte and fonte.diretta) else None

    return modelli.TemplateResponse(request, "cella.html", {
        "c": c, "t": c.t, "url": u, "q": q,
        "piattaforma": piattaforma_di(u),
        "fonte": fonte, "perche": perche, "chat": chat,
    })


# --------------------------------------------------------------------------
# i gruppi
# --------------------------------------------------------------------------

def _riassunto(voce: Any) -> dict[str, Any]:
    celle = voce.dati.get("celle") or []
    return {"id": str(voce.id), "nome": voce.titolo,
            "quanti": len(celle), "colonne": voce.dati.get("colonne", 2),
            "disposizione": voce.dati.get("disposizione", "griglia"),
            "celle": celle}


@router.get("/gruppi.json")
async def elenco_gruppi(
    utente: Utente = Depends(utente_corrente),
    db: AsyncSession = Depends(sessione),
) -> Response:
    voci = await biblioteca.elenco(db, utente.id, Genere.GRUPPO, quante=40)
    return JSONResponse({"gruppi": [_riassunto(v) for v in voci]})


@router.get("/gruppo/{gruppo_id}.json")
async def un_gruppo(
    gruppo_id: uuid.UUID,
    utente: Utente = Depends(utente_corrente),
    db: AsyncSession = Depends(sessione),
) -> Response:
    voce = await biblioteca.mia(db, utente.id, gruppo_id)
    if voce is None or voce.genere is not Genere.GRUPPO:
        # 404 anche quando il gruppo esiste ma e' di un altro: rispondere
        # "esiste ma non e' tuo" direbbe a chiunque provi a indovinare un id
        # se ha indovinato
        return JSONResponse({"errore": "non trovato"}, status_code=404)
    return JSONResponse(_riassunto(voce))


@router.post("/gruppo")
async def salva_gruppo(
    nome: str = Form(...),
    celle: str = Form(...),
    disposizione: str = Form("griglia"),
    colonne: int = Form(2),
    utente: Utente = Depends(utente_corrente),
    db: AsyncSession = Depends(sessione),
) -> Response:
    try:
        dati = json.loads(celle)
    except json.JSONDecodeError:
        return JSONResponse({"ok": False, "perche": "celle illeggibili"},
                            status_code=400)
    if not isinstance(dati, list) or not dati:
        return JSONResponse({"ok": False, "perche": "nessuna cella"},
                            status_code=400)

    # si tiene solo quello che serve a riaprire: indirizzo e titolo. Quello
    # che arriva dal browser non si copia mai intero in un campo JSON, o si
    # finisce per salvare qualunque cosa a qualcuno venga in mente di mandare
    pulite = [{"url": str(v.get("url", ""))[:2000],
               "title": str(v.get("title", ""))[:300]}
              for v in dati[:MASSIMO_CELLE]
              if str(v.get("url", "")).startswith(("http://", "https://"))]
    if not pulite:
        return JSONResponse({"ok": False, "perche": "nessun indirizzo valido"},
                            status_code=400)

    voce = await biblioteca.salva_gruppo(
        db, utente.id, nome, [dict(p) for p in pulite],
        colonne=max(1, min(4, colonne)), disposizione=disposizione)
    await db.flush()
    return JSONResponse({"ok": True, "id": str(voce.id)})


@router.get("/muro/apri")
async def apri_gruppo(
    gruppo: uuid.UUID = Query(...),
    c: Contesto = Depends(contesto),
) -> Response:
    """Scorciatoia: dalla home, un gruppo si apre nel muro."""
    return RedirectResponse(f"/{c.lingua.codice}/muro?gruppo={gruppo}",
                            status_code=303)
