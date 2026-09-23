"""Chi è dentro una stanza, e a che punto è il video.

Due cose, tenute in due posti diversi per una ragione.

**Le connessioni stanno in memoria.** Un WebSocket è un oggetto vivo di questo
processo: non si può mettere in Redis, e non ha senso provarci.

**Lo stato della riproduzione sta in Redis.** Perché deve sopravvivere a un
ricaricamento del server mentre la gente sta guardando - il che, durante lo
sviluppo, succede ogni due minuti - e perché è il pezzo che un giorno dovrà
essere visto da più processi.

**Il limite di oggi, detto adesso:** con più di un worker le stanze si
spaccherebbero, perché chi è collegato al worker A non riceve quello che
succede sul worker B. Lo stato in Redis è già al posto giusto; quello che
manca è un canale di pubblicazione fra i processi. Finché si gira con un
worker solo, non è un problema - e quando smetterà di esserlo, si sa dove
mettere le mani.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import asdict, dataclass

from fastapi import WebSocket

from ..media import deposito
from .protocol import Messaggio, StatoRiproduzione, Tipo

CHIAVE_STATO = "stanza:"
# Quanto sopravvive lo stato di una stanza senza che nessuno la tocchi. Corto
# abbastanza da non tenersi in casa stanze morte, lungo abbastanza da reggere
# un riavvio e qualcuno che ricarica la pagina.
VITA_S = 6 * 3600


@dataclass(slots=True)
class Presente:
    """Uno che è collegato adesso. Non è un membro: è una finestra aperta."""
    ws: WebSocket
    utente_id: uuid.UUID
    nome: str
    comanda: bool = False


class Hub:
    def __init__(self) -> None:
        self._stanze: dict[str, list[Presente]] = {}
        self._chiave = asyncio.Lock()

    # ---------------------------------------------------------------- stato
    async def stato(self, codice: str) -> StatoRiproduzione:
        grezzo = await deposito.cliente().get(CHIAVE_STATO + codice)
        if not grezzo:
            return StatoRiproduzione()
        return StatoRiproduzione(**json.loads(grezzo))

    async def salva_stato(self, codice: str, stato: StatoRiproduzione) -> None:
        await deposito.cliente().set(CHIAVE_STATO + codice,
                                     json.dumps(asdict(stato)), ex=VITA_S)

    # ------------------------------------------------------------- presenze
    async def entra(self, codice: str, chi: Presente) -> None:
        async with self._chiave:
            self._stanze.setdefault(codice, []).append(chi)

    async def esce(self, codice: str, chi: Presente) -> None:
        async with self._chiave:
            dentro = self._stanze.get(codice)
            if not dentro:
                return
            self._stanze[codice] = [p for p in dentro if p is not chi]
            if not self._stanze[codice]:
                del self._stanze[codice]

    def presenti(self, codice: str) -> list[Presente]:
        return list(self._stanze.get(codice, []))

    def quanti(self, codice: str) -> int:
        return len(self._stanze.get(codice, []))

    # ------------------------------------------------------------- messaggi
    async def a_tutti(self, codice: str, messaggio: Messaggio,
                      tranne: Presente | None = None) -> None:
        """Manda a chi è dentro. Chi non risponde non blocca gli altri.

        Una connessione che si è rotta senza dirlo resta lì finché non si
        prova a scriverci: l'errore che arriva è il modo in cui lo si scopre,
        e a quel punto si toglie di mezzo invece di riprovare per sempre.
        """
        messaggio.t_server = time.time()
        corpo = messaggio.json()
        caduti: list[Presente] = []
        for p in self.presenti(codice):
            if p is tranne:
                continue
            try:
                await p.ws.send_json(corpo)
            except Exception:
                caduti.append(p)
        for p in caduti:
            await self.esce(codice, p)

    async def elenco(self, codice: str) -> Messaggio:
        return Messaggio(tipo=Tipo.ELENCO, dati={
            "persone": [{"nome": p.nome, "comanda": p.comanda}
                        for p in self.presenti(codice)],
        })


# Uno per processo. Non è uno stato globale per pigrizia: è l'elenco delle
# connessioni aperte *di questo processo*, e non può essere altro.
hub = Hub()
