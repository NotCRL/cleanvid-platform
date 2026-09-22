"""La firma che impedisce di usarci come proxy per il mondo.

Il proxy dei segmenti riceve un indirizzo e va a prenderlo. Senza firma,
chiunque potrebbe scrivere `/segmento?u=<qualunque cosa>` e far uscire
traffico dalla nostra macchina verso dove gli pare: e' un proxy aperto, e un
proxy aperto viene trovato e usato nel giro di ore.

La firma lega l'indirizzo al token: vale solo per quel flusso, e solo per
quell'indirizzo. Chi non ha estratto quel video non puo' fabbricarla, perche'
il segreto non esce mai da qui.
"""

from __future__ import annotations

import hashlib
import hmac
import urllib.parse

from ..config import impostazioni


def firma(token: str, url: str) -> str:
    return hmac.new(
        impostazioni().segreto.encode(),
        f"{token}\x00{url}".encode(),
        hashlib.sha256,
    ).hexdigest()[:32]


def firma_valida(token: str, url: str, data: str) -> bool:
    # `compare_digest` e non `==`: il confronto normale esce al primo byte
    # diverso, e quel tempo si misura
    return hmac.compare_digest(data, firma(token, url))


def link_segmento(token: str, url: str) -> str:
    """L'indirizzo, sul nostro proxy, di un pezzo di flusso."""
    q = urllib.parse.urlencode({"t": token, "u": url, "s": firma(token, url)})
    return f"/segmento?{q}"


def firma_semplice(url: str, scopo: str) -> str:
    """Come sopra, ma senza un token davanti: per quello che non ne ha uno.

    `scopo` tiene separati gli usi: una firma nata per una copertina non deve
    valere per il proxy dei video. Riusare la stessa firma per due cose e'
    come riusare una password.
    """
    return hmac.new(
        impostazioni().segreto.encode(),
        f"{scopo}\x00{url}".encode(),
        hashlib.sha256,
    ).hexdigest()[:32]


def link_copertina(url: str) -> str:
    """L'indirizzo, da noi, della copertina di questa pagina.

    Firmato per la stessa ragione del proxy dei segmenti: senza, chiunque
    potrebbe scrivere `/copertina?u=<qualunque cosa>` e farci scaricare quello
    che gli pare.
    """
    q = urllib.parse.urlencode({"u": url, "s": firma_semplice(url, "copertina")})
    return f"/copertina?{q}"
