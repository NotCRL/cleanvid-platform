"""Il codice che finisce nell'indirizzo di una stanza.

`/stanza/verde-corsa-42` e non `/stanza/9f3a1c...`: un codice si detta al
telefono, si scrive in una chat senza copiarlo, e si riconosce se è quello
giusto. Un UUID no.

Le parole sono scelte per essere **distinguibili a voce**: niente coppie che
si confondono, niente parole che in un'altra lingua suonano male. Il numero
in fondo esiste perché due stanze con lo stesso nome capitano prima di quanto
si pensi.
"""

from __future__ import annotations

import secrets

_COLORI = ("verde", "rosso", "blu", "giallo", "viola", "arancio", "nero",
           "bianco", "grigio", "rosa", "oro", "bronzo")
_COSE = ("corsa", "luna", "ponte", "faro", "bosco", "fiume", "monte", "vela",
         "lampo", "neve", "onda", "pietra", "fuoco", "vento", "stella")


def nuovo() -> str:
    """Un codice a caso. Con dodici colori, quindici cose e cento numeri fanno
    diciottomila combinazioni: abbastanza perché due stanze aperte nello
    stesso momento non si scontrino, e comunque chi lo genera ricontrolla."""
    colore = secrets.choice(_COLORI)
    cosa = secrets.choice(_COSE)
    numero = secrets.randbelow(90) + 10
    return f"{colore}-{cosa}-{numero}"


def plausibile(codice: str) -> bool:
    """Serve a scartare le richieste inventate prima di interrogare il
    database: un indirizzo lungo duemila caratteri non è una stanza."""
    if not 5 <= len(codice) <= 48:
        return False
    return all(c.isalnum() or c == "-" for c in codice)
