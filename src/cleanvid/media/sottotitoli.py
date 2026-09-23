"""I sottotitoli, scelti fra quelli che il sito offre.

yt-dlp li restituisce insieme al resto, gratis, in due mucchi: quelli scritti
da qualcuno (`subtitles`) e quelli fatti dalla macchina (`automatic_captions`).
Su YouTube i secondi possono essere **piu' di cento**, perche' includono la
traduzione automatica in ogni lingua esistente.

Metterli tutti in pagina sarebbe inutile e dannoso: un menu con cento voci non
si usa, e sono cento richieste che il browser potrebbe fare. Quindi si sceglie,
e la regola e' scritta qui in un posto solo.

Si tiene solo il formato `vtt`: e' l'unico che il tag `<track>` sa leggere.
Gli altri - json3, srv1, ttml - andrebbero convertiti, e convertire sottotitoli
e' un mestiere intero che non ci serve fare finche' il vtt c'e' sempre.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Quante tracce al massimo finiscono in pagina. Otto e' gia' un menu lungo;
# oltre, nessuno cerca piu' e chiude.
MASSIMO = 8
# Di quelle automatiche se ne tengono pochissime: sono una comodita' quando
# non c'e' altro, non un catalogo.
MASSIMO_AUTOMATICHE = 2


@dataclass(slots=True)
class Traccia:
    lingua: str                 # quello che finisce in `srclang`
    nome: str                   # quello che si legge nel menu
    # Vuoto quando la traccia nasce: lo riempie chi la registra nel deposito,
    # perche' e' li' che nasce il token. Questo modulo sceglie, non serve.
    indirizzo: str = ""
    automatica: bool = False


def _codice(chiave: str) -> str:
    """Il codice di lingua, ripulito da quello che ci mette YouTube.

    Le loro chiavi sono tipo `en-nP7-2PuUl7o`: `en` e' la lingua, il resto e'
    l'identificativo della traccia. Ma `en-US` e' una lingua vera, e va
    tenuta: la differenza e' che la seconda parte e' corta e non sembra un
    codice a caso.
    """
    pezzi = chiave.split("-")
    if len(pezzi) >= 2 and re.fullmatch(r"[A-Za-z]{2,3}", pezzi[1]):
        return f"{pezzi[0]}-{pezzi[1]}"
    return pezzi[0]


def _vtt(formati: list[dict[str, Any]]) -> str:
    for f in formati:
        if f.get("ext") == "vtt" and f.get("url"):
            return str(f["url"])
    return ""


def _nome(formati: list[dict[str, Any]], ripiego: str) -> str:
    for f in formati:
        nome = (f.get("name") or "").strip()
        if nome:
            return nome[:60]
    return ripiego


def scegli(info: dict[str, Any], preferita: str = "en") -> list[tuple[str, Traccia]]:
    """-> [(indirizzo_vero, traccia_senza_indirizzo), …]

    Restituisce gli indirizzi veri separati dalle tracce perche' chi chiama
    deve prima registrarli nel deposito: e' li' che nascono i token, e questo
    modulo non ne sa niente di proposito.

    **L'ordine e' quello del menu**, e conta: prima la lingua della pagina,
    poi l'inglese, poi il resto. Chi guarda cerca la propria lingua per prima,
    e se non c'e' prova l'inglese.
    """
    scritte: dict[str, Any] = info.get("subtitles") or {}
    automatiche: dict[str, Any] = info.get("automatic_captions") or {}

    def peso(codice: str) -> int:
        base = codice.split("-")[0]
        if base == preferita.split("-")[0]:
            return 0
        if base == "en":
            return 1
        return 2

    fuori: list[tuple[str, Traccia]] = []
    viste: set[str] = set()

    for chiave, formati in sorted(scritte.items(), key=lambda kv: peso(_codice(kv[0]))):
        indirizzo = _vtt(formati)
        codice = _codice(chiave)
        if not indirizzo or codice in viste:
            continue
        viste.add(codice)
        fuori.append((indirizzo, Traccia(lingua=codice,
                                         nome=_nome(formati, codice))))
        if len(fuori) >= MASSIMO:
            return fuori

    # le automatiche solo dove non c'e' gia' qualcosa di scritto a mano, e
    # solo nelle lingue che servono: la propria e l'inglese
    quante = 0
    for chiave, formati in sorted(automatiche.items(),
                                  key=lambda kv: peso(_codice(kv[0]))):
        codice = _codice(chiave)
        if codice in viste or peso(codice) > 1:
            continue
        indirizzo = _vtt(formati)
        if not indirizzo:
            continue
        viste.add(codice)
        fuori.append((indirizzo, Traccia(lingua=codice,
                                         nome=_nome(formati, codice),
                                         automatica=True)))
        quante += 1
        if quante >= MASSIMO_AUTOMATICHE or len(fuori) >= MASSIMO:
            break

    return fuori
