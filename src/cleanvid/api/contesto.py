"""Quello che ogni pagina sa di se': la lingua, i suoi indirizzi, i suoi testi.

Sta in un posto solo perche' le `hreflang` devono essere reciproche e
complete: se ogni modello se le scrivesse da se', prima o poi una pagina ne
dimenticherebbe una, e Google butta via in blocco i gruppi che non tornano -
senza dirlo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends, HTTPException, Request

from .. import seo
from ..lingue import (
    LINGUE,
    RIPIEGO,
    Lingua,
    da_accept_language,
    esiste,
    lingua,
    traduttore,
)
from ..models import Utente
from .identita import utente_corrente

COOKIE_LINGUA = "cv_lingua"
DURATA_COOKIE = 400 * 24 * 3600


@dataclass(slots=True)
class Contesto:
    """Tutto quello che base.html ha bisogno di sapere."""

    lingua: Lingua
    t: Any
    percorso: str                       # senza il pezzo della lingua
    utente: Utente
    parametri: dict[str, str] = field(default_factory=dict)
    proposta: Lingua | None = None      # un'altra lingua da suggerire, non imporre

    @property
    def canonico(self) -> str:
        return seo.indirizzo(self.lingua.codice, self.percorso, **self.parametri)

    @property
    def alternative(self) -> list[seo.Alternativa]:
        return seo.alternative(self.percorso, **self.parametri)

    @property
    def lingue(self) -> tuple[Lingua, ...]:
        return LINGUE

    def altrove(self, codice: str) -> str:
        """La stessa pagina in un'altra lingua: e' il link del menu lingue."""
        return seo.indirizzo(codice, self.percorso, **self.parametri)


def scegli_per_chi_arriva(request: Request) -> str:
    """Dove mandare chi apre la radice senza dire in che lingua la vuole.

    L'ordine e' questo e non un altro: **chi ha scelto ha sempre ragione**,
    poi quello che dice il browser, e solo alla fine il ripiego.

    Non si guarda da quale paese arriva la richiesta. Sembra la cosa gentile
    e fa due danni: Google visita quasi sempre da indirizzi americani, quindi
    vedrebbe per sempre la sola versione inglese e non indicizzerebbe le
    altre; e chi vive all'estero o usa una VPN resta inchiodato a una lingua
    che non ha scelto. `Accept-Language` dice che lingua parla una persona,
    l'indirizzo IP dice dov'e' il suo router: sono due domande diverse.
    """
    scelta = request.cookies.get(COOKIE_LINGUA)
    if scelta and esiste(scelta):
        return scelta
    return da_accept_language(request.headers.get("accept-language"))


async def contesto(
    request: Request,
    lingua_url: str,
    utente: Utente = Depends(utente_corrente),
) -> Contesto:
    codice = lingua_url
    if not esiste(codice):
        # 404 vero e non un rimbalzo alla home: un indirizzo inventato deve
        # dire che non esiste, altrimenti si riempie l'indice di pagine
        # fantasma che rispondono 200
        raise HTTPException(status_code=404, detail="lingua sconosciuta")

    percorso = request.url.path.removeprefix(f"/{codice}")
    parametri = {k: v for k, v in request.query_params.items() if k in ("u", "q")}

    # La proposta: se il browser chiede chiaramente un'altra lingua e la
    # persona non ha mai scelto, glielo si dice. Una riga che si chiude, non
    # un rimbalzo: chi ha aperto un link in italiano voleva l'italiano.
    proposta = None
    if utente.lingua is None and not request.cookies.get(COOKIE_LINGUA):
        preferita = da_accept_language(request.headers.get("accept-language"))
        if preferita != codice and preferita != RIPIEGO:
            proposta = lingua(preferita)

    return Contesto(
        lingua=lingua(codice),
        t=traduttore(codice),
        percorso=percorso,
        parametri=parametri,
        utente=utente,
        proposta=proposta,
    )
