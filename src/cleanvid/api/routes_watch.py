"""Le pagine che una persona apre: home, video, impostazioni, stato.

Stanno tutte sotto `/{lingua}/` - `/it/`, `/en/`, `/es/`. Non e' un vezzo: un
motore di ricerca indicizza indirizzi, e una pagina che cambia lingua in base
a un cookie esiste, per chi cerca, in una lingua sola. Il perche' per esteso
sta in `seo.py`.

Il predefinito e' il lettore nostro, e il lettore della piattaforma e' il
ripiego. La ragione si vede meglio adesso che le funzioni ci sono: dentro
l'iframe di un altro sito non si puo' fare niente di tutto il resto - niente
sponsor saltato, niente piccolo schermo, niente ripresa, niente viste, niente
bagliore, niente qualita' scelta da noi.

Il prezzo e' che l'estrazione costa qualche secondo la prima volta e produce
indirizzi che scadono. Chi preferisce l'altro lo trova a un clic.

Comunque sia andata, quello che esce di qui e' **una sola cosa**: una `Fonte`.
La pagina non deve chiedersi come e' stata trovata.
"""

from __future__ import annotations

import urllib.parse

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from .. import seo
from ..db import sessione
from ..lingue import esiste
from ..media.annunci import segmenti
from ..media.embed import chat_incorporabile, lettore_ufficiale, piattaforma_di
from ..media.estrazione import NonEstraibile, risolvi
from ..media.fonte import Fonte
from ..media.qualita import QUALITA
from ..models import Genere, Utente
from ..web.pagine import modelli
from . import biblioteca
from .contesto import COOKIE_LINGUA, DURATA_COOKIE, Contesto, contesto
from .identita import utente_corrente

router = APIRouter(prefix="/{lingua_url}")


def _normalizza(grezzo: str) -> str:
    """Un indirizzo senza http:// e' l'errore piu' comune: si completa."""
    testo = (grezzo or "").strip()
    if testo and not testo.lower().startswith(("http://", "https://")):
        if "." in testo.split("/")[0]:
            testo = "https://" + testo
    return testo


def _pagina(request: Request, modello: str, c: Contesto,
            **extra: object) -> Response:
    return modelli.TemplateResponse(request, modello, {
        "c": c, "t": c.t, "utente": c.utente, **extra})


@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    c: Contesto = Depends(contesto),
    db: AsyncSession = Depends(sessione),
) -> Response:
    recenti = await biblioteca.elenco(db, c.utente.id, Genere.CRONOLOGIA)
    riprendi = await biblioteca.da_riprendere(db, c.utente.id)
    preferiti_voci = await biblioteca.elenco(db, c.utente.id, Genere.PREFERITO)
    fonti = await biblioteca.elenco(db, c.utente.id, Genere.FONTE, quante=12)
    gruppi = await biblioteca.elenco(db, c.utente.id, Genere.GRUPPO, quante=12)

    # una query sola per sapere quali stelle sono accese, invece di una per
    # riga: con cinque scaffali in pagina la differenza si vede
    preferiti = await biblioteca.quali_preferiti(
        db, c.utente.id,
        [v.url for v in (*recenti, *riprendi, *preferiti_voci, *fonti)])

    return _pagina(request, "home.html", c,
                   recenti=recenti, riprendi=riprendi,
                   preferiti_voci=preferiti_voci, fonti=fonti, gruppi=gruppi,
                   preferiti=preferiti,
                   dati_strutturati=seo.dati_strutturati_home(
                       c.lingua.codice, c.t))


@router.post("/apri")
async def apri(
    lingua_url: str,
    url: str = Form(...),
    utente: Utente = Depends(utente_corrente),
) -> Response:
    """Dal campo della home al video: si passa per un indirizzo condivisibile.

    Un redirect invece di rispondere direttamente, cosi' la pagina del video
    ha un suo indirizzo che si puo' salvare, ricaricare e mandare.
    """
    lingua_url = lingua_url if esiste(lingua_url) else "en"
    pulito = _normalizza(url)
    if not pulito:
        return RedirectResponse(f"/{lingua_url}/", status_code=303)
    return RedirectResponse(
        f"/{lingua_url}/guarda?u=" + urllib.parse.quote(pulito, safe=""),
        status_code=303)


@router.get("/guarda", response_class=HTMLResponse)
async def guarda(
    request: Request,
    u: str = "",
    q: str = "",
    m: str = "",
    c: Contesto = Depends(contesto),
    db: AsyncSession = Depends(sessione),
) -> Response:
    url = _normalizza(u)
    if not url:
        return RedirectResponse(f"/{c.lingua.codice}/", status_code=303)

    piattaforma = piattaforma_di(url)
    loro_ce_l_hanno = lettore_ufficiale(
        url, host_pagina=request.url.hostname or "localhost")

    # IL PREDEFINITO E' IL LETTORE NOSTRO. Si chiede il loro con `m=loro`.
    #
    #   il nostro - il video esce pulito, si salta lo sponsor letto a voce,
    #               funzionano il piccolo schermo, la ripresa e le tre viste.
    #               Costa qualche secondo la prima volta, e l'indirizzo del
    #               flusso scade dopo qualche ora.
    #   il loro   - parte subito e non scade mai, ma la loro pubblicita'
    #               resta, i comandi sono i loro, e dentro quell'iframe non
    #               possiamo fare niente di tutto il resto.
    #
    # Il loro resta come ripiego automatico: se l'estrazione non riesce si
    # apre quello invece di mostrare una pagina vuota. Cosi' la scelta del
    # predefinito non costa mai un video che non parte.
    loro = m == "loro"
    ha_lettore_loro = loro_ce_l_hanno is not None

    fonte: Fonte | None = None
    perche = ""
    if not loro:
        try:
            fonte = await risolvi(url, q, lingua=c.lingua.codice)
        except NonEstraibile as e:
            # il messaggio di yt-dlp si mostra cosi' com'e': dice quasi sempre
            # la verita' ("video privato", "serve un account"), e riscriverlo
            # in gentile vorrebbe dire nascondere l'unica cosa utile
            perche = str(e)

    if fonte is None and ha_lettore_loro:
        fonte = loro_ce_l_hanno
        perche = ""             # si ripiega sul loro: non c'e' niente da dire

    # la piattaforma la sappiamo dall'indirizzo anche quando la fonte non ce
    # l'ha detto, perche' e' una proprieta' del link e non del flusso
    if fonte is not None and not fonte.piattaforma:
        fonte.piattaforma = piattaforma

    # la visita si annota comunque: anche un tentativo andato male e' un
    # tentativo, e ritrovarlo nella cronologia serve a riprovarci
    voce = await biblioteca.annota_visita(
        db, c.utente.id, url,
        titolo=fonte.titolo if fonte else "",
        piattaforma=piattaforma)

    # I segmenti da saltare si chiedono solo se c'e' un video da guardare, e
    # solo per YouTube: per tutto il resto e' una richiesta buttata.
    # Solo sul lettore nostro: dentro l'iframe della piattaforma non possiamo
    # spostare il tempo del video, quindi chiederli sarebbe inutile.
    da_saltare = await segmenti(url) if (fonte and fonte.nostra) else []

    chat = chat_incorporabile(
        url, request.url.hostname or "localhost") if (
            fonte and fonte.diretta) else None

    # La colonna di fianco, quando non c'e' la chat: prima quello lasciato a
    # meta', poi il resto della cronologia. E' il posto dove si guarda per
    # decidere cosa viene dopo, e riproporre quello che si sta gia' guardando
    # sarebbe l'unica cosa che li' non serve.
    accanto = []
    if chat is None:
        sospesi = await biblioteca.da_riprendere(db, c.utente.id, quante=4)
        recenti = await biblioteca.elenco(db, c.utente.id, Genere.CRONOLOGIA,
                                          quante=12)
        visti = {url}
        for voce in (*sospesi, *recenti):
            if voce.url in visti:
                continue
            visti.add(voce.url)
            accanto.append(voce)
        accanto = accanto[:8]

    return _pagina(request, "guarda.html", c,
                   salti=da_saltare, chat=chat, accanto=accanto,
                   ha_lettore_loro=ha_lettore_loro,
                   url=url, q=q, qualita_possibili=QUALITA,
                   piattaforma=piattaforma,
                   titolo=fonte.titolo if fonte else "",
                   fonte=fonte, perche=perche,
                   riprendi=biblioteca.riprendi_da(
                       voce, diretta=bool(fonte and fonte.diretta)),
                   e_preferito=bool(await biblioteca.quali_preferiti(
                       db, c.utente.id, [url])))


@router.get("/impostazioni", response_class=HTMLResponse)
async def impostazioni_pagina(
    request: Request,
    salvato: int = 0,
    c: Contesto = Depends(contesto),
) -> Response:
    return _pagina(request, "impostazioni.html", c, salvato=bool(salvato))


@router.post("/impostazioni/lingua")
async def cambia_lingua(
    lingua_url: str,
    scelta: str = Form(...),
    utente: Utente = Depends(utente_corrente),
    db: AsyncSession = Depends(sessione),
) -> Response:
    """La scelta si scrive in due posti, e servono tutti e due.

    Sulla riga dell'utente, perche' lo segua su ogni dispositivo dove ha il
    suo cookie; e in un cookie a parte, perche' chi apre la radice venga
    mandato subito nella lingua giusta senza aspettare il database.
    """
    codice = scelta if esiste(scelta) else lingua_url
    utente.lingua = codice
    db.add(utente)

    risposta = RedirectResponse(f"/{codice}/impostazioni?salvato=1",
                                status_code=303)
    risposta.set_cookie(COOKIE_LINGUA, codice, max_age=DURATA_COOKIE,
                        samesite="lax", path="/")
    return risposta


@router.get("/stato", response_class=HTMLResponse)
async def stato(
    request: Request,
    c: Contesto = Depends(contesto),
    db: AsyncSession = Depends(sessione),
) -> Response:
    """Una pagina di servizio: dice chi sei e quanto hai nella tua biblioteca.

    Serve adesso per vedere con gli occhi che la separazione per utente
    funziona; quando ci saranno pagine vere andra' via.
    """
    recenti = await biblioteca.elenco(db, c.utente.id, Genere.CRONOLOGIA,
                                      quante=100)
    return _pagina(request, "stato.html", c, quante=len(recenti))
