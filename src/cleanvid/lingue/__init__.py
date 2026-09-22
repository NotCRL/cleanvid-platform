"""I testi dell'interfaccia, una cartella per lingua.

**L'italiano e' l'originale.** E' la lingua in cui il progetto viene pensato e
scritto, quindi e' quella dove una frase nasce e dove si corregge. L'inglese e'
scritto a mano anche lui, perche' e' la versione che vedra' piu' gente di
tutte e non merita di essere una traduzione automatica. Le altre si generano
con `strumenti/traduci.py` partendo dall'italiano, e poi restano su disco:
si leggono, si correggono e si committano come qualunque altro file.

**Una chiave che manca non fa cadere la pagina.** Ripiega sull'italiano, e si
vede subito perche' in mezzo all'inglese compare una frase italiana. Il
contrario - una pagina che esplode perche' un traduttore ha dimenticato una
riga - sarebbe molto peggio.

I cataloghi si caricano una volta e restano in memoria: sono qualche decina di
chilobyte in tutto, e rileggerli a ogni richiesta sarebbe un accesso al disco
per ogni visitatore.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .catalogo import LINGUE, RIPIEGO, Lingua, da_accept_language, esiste, lingua

__all__ = ["LINGUE", "RIPIEGO", "Lingua", "da_accept_language", "esiste",
           "lingua", "testi", "traduttore"]

CARTELLA = Path(__file__).parent / "testi"

# L'originale: quello da cui si traduce e su cui si ripiega.
ORIGINALE = "it"


@lru_cache
def testi(codice: str) -> dict[str, str]:
    percorso = CARTELLA / f"{codice}.json"
    if not percorso.exists():
        return {}
    with percorso.open(encoding="utf-8") as f:
        dati: dict[str, str] = json.load(f)
    return dati


def traduttore(codice: str) -> Any:
    """La funzione `t` che finisce nei modelli delle pagine.

    Accetta dei segnaposto: `t("saluto", nome="Carlo")`. Si usa `str.format`
    e non le f-string perche' il testo arriva da un file, non dal codice - e
    un file di testo che puo' eseguire espressioni sarebbe un regalo a
    chiunque riesca a modificarlo.
    """
    proprio = testi(codice)
    scorta = testi(ORIGINALE)

    def t(chiave: str, **valori: object) -> str:
        frase = proprio.get(chiave) or scorta.get(chiave) or chiave
        if not valori:
            return frase
        try:
            return frase.format(**valori)
        except (KeyError, IndexError):
            # un segnaposto sbagliato nella traduzione non deve far cadere la
            # pagina: si mostra la frase cruda, che e' brutta ma leggibile
            return frase

    return t
