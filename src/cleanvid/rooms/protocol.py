"""Il protocollo di una stanza: cosa viaggia sul WebSocket.

L'idea che tiene in piedi tutto: **nessuno insegue nessuno**. Il padrone non
manda "adesso vai al secondo 42"; manda "al mio orologio T io ero al secondo
42 e stavo andando". Ogni ospite calcola da solo dove dovrebbe essere adesso,
e ci arriva.

E' la stessa cosa che fa gia' il player per tenere insieme video e audio
separati, e la soluzione e' la stessa, imparata a suon di prove: **se lo
scarto e' piccolo si cambia impercettibilmente la velocita' finche' rientra,
e si salta solo quando lo scarto e' tale che un salto si sente meno di uno
sfasamento.** Un sistema che salta a ogni messaggio e' un sistema che
singhiozza; e chi guarda insieme a qualcuno nota il singhiozzo molto piu' di
mezzo secondo di ritardo.

Il tempo del server e' l'unico orologio di cui ci si fida: quelli dei
partecipanti sono sbagliati, ognuno a modo suo. Per questo ogni messaggio
porta `t_server`, e il client misura il proprio scarto con un ping iniziale.
"""

from __future__ import annotations

import enum
from dataclasses import asdict, dataclass, field
from typing import Any


class Verso(str, enum.Enum):
    """Chi puo' mandare cosa. Il server rifiuta il resto senza discutere."""
    AL_SERVER = "al_server"
    AI_CLIENTI = "ai_clienti"
    ENTRAMBI = "entrambi"


class Tipo(str, enum.Enum):
    # --- riproduzione ---
    STATO = "stato"            # ai clienti: com'e' messa la stanza adesso
    COMANDA = "comanda"        # al server: play/pausa/salto, da chi puo' farlo
    CAMBIA_VIDEO = "cambia_video"
    BATTITO = "battito"        # ogni pochi secondi: chi comanda dice dov'e'

    # --- presenza ---
    ENTRATO = "entrato"
    USCITO = "uscito"
    ELENCO = "elenco"          # chi c'e' adesso

    # --- chat ---
    MESSAGGIO = "messaggio"
    SCRIVE = "scrive"          # "sta scrivendo", effimero, non si salva

    # --- servizio ---
    PING = "ping"              # misura lo scarto fra gli orologi
    PONG = "pong"
    ERRORE = "errore"


@dataclass(slots=True)
class StatoRiproduzione:
    """Quello che basta a un ospite per sapere dove dovrebbe essere.

    Non si manda "la posizione": si manda la posizione E l'istante in cui era
    quella. Con un video in corsa, un numero senza il suo istante e' gia'
    vecchio quando arriva.
    """
    url: str | None = None
    titolo: str | None = None
    posizione: float = 0.0       # secondi dentro il video
    in_corsa: bool = False
    velocita: float = 1.0
    t_server: float = 0.0        # orologio del server, unico di cui fidarsi

    def prevista(self, adesso: float) -> float:
        """Dove dovrebbe stare un ospite in questo momento."""
        if not self.in_corsa:
            return self.posizione
        return self.posizione + max(0.0, adesso - self.t_server) * self.velocita


@dataclass(slots=True)
class Messaggio:
    tipo: Tipo
    dati: dict[str, Any] = field(default_factory=dict)
    t_server: float = 0.0

    def json(self) -> dict[str, Any]:
        d = asdict(self)
        d["tipo"] = self.tipo.value
        return d


# Chi puo' mandare cosa: la tabella sta qui, non sparsa nei gestori, cosi'
# aggiungere un messaggio vuol dire aggiungere una riga e non ricordarsi di
# mettere un controllo da qualche parte.
PERMESSI: dict[Tipo, Verso] = {
    Tipo.STATO: Verso.AI_CLIENTI,
    Tipo.COMANDA: Verso.AL_SERVER,
    Tipo.CAMBIA_VIDEO: Verso.AL_SERVER,
    Tipo.BATTITO: Verso.AL_SERVER,
    Tipo.ENTRATO: Verso.AI_CLIENTI,
    Tipo.USCITO: Verso.AI_CLIENTI,
    Tipo.ELENCO: Verso.AI_CLIENTI,
    Tipo.MESSAGGIO: Verso.ENTRAMBI,
    Tipo.SCRIVE: Verso.ENTRAMBI,
    Tipo.PING: Verso.AL_SERVER,
    Tipo.PONG: Verso.AI_CLIENTI,
    Tipo.ERRORE: Verso.AI_CLIENTI,
}

# --- le soglie, in un posto solo --------------------------------------------
# Sono i numeri che decidono se guardare insieme e' piacevole o irritante, e
# vanno regolati con gli occhi su uno schermo vero, non a tavolino.
SCARTO_SALTO = 1.2      # s: oltre questo si salta, sotto si insegue piano
SCARTO_OK = 0.15        # s: sotto questo siamo allineati, non si tocca niente
CORREZIONE_MAX = 0.08   # +/- 8% di velocita': oltre, l'orecchio se ne accorge
BATTITO_OGNI = 4.0      # s: ogni quanto chi comanda dice dov'e'
