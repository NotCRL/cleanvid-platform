"""Una sorgente riproducibile, comunque sia stata trovata.

Fino a ieri c'erano **due tipi diversi per la stessa cosa**: `Lettore`, il
lettore incorporabile di una piattaforma, ed `Estratto`, il flusso tirato
fuori da noi. Due forme, due nomi, e ogni pagina costretta a chiedersi quale
delle due avesse in mano: 22 volte in `guarda.html`, 8 in `cella.html`, 6
nelle rotte.

Il costo non era la riga in piu': era che **ogni funzione nuova andava
pensata due volte**. Il bagliore, le viste, il piccolo schermo, la ripresa -
per ognuna si ricominciava da capo a decidere cosa fare nel caso dell'iframe.

Adesso c'e' una cosa sola: una fonte. Chi la riceve non deve sapere come e'
stata trovata, deve sapere **cosa ci puo' fare**, e per quello bastano due
domande: e' incorniciata? ha due tracce?

`tipo` e' una stringa e non un insieme chiuso di casi, perche' la porta resta
aperta: `torrent`, `locale`, `addon` sono altri modi di arrivare a un flusso,
e il giorno che arrivano non cambiano niente qui.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- come ci arriva il video -----------------------------------------------
# `incorniciata`: e' il lettore di un altro sito dentro un iframe. Non
#   possiamo toccarlo: niente qualita', niente salti, niente bagliore.
# `diretta`: un file che serviamo noi, un pezzo alla volta.
# `hls`: un manifest che serviamo noi. Come sopra, ma a segmenti.
INCORNICIATA = "incorniciata"
DIRETTA = "diretta"
HLS = "hls"


@dataclass(slots=True)
class Fonte:
    """Qualcosa che si puo' guardare, e quello che si puo' farci."""

    tipo: str
    # cosa finisce nel `src`: il loro lettore, oppure il nostro flusso
    indirizzo: str
    titolo: str = ""
    piattaforma: str = ""
    diretta: bool = False       # e' una diretta, non una registrazione
    altezza: int = 0
    indirizzo_audio: str = ""   # la seconda traccia, quando ce ne sono due
    token: str = ""             # il nostro flusso, per chi deve parlarne al deposito
    token_audio: str = ""

    @property
    def incorniciata(self) -> bool:
        """E' il lettore di un altro sito. Da fuori non si comanda."""
        return self.tipo == INCORNICIATA

    @property
    def nostra(self) -> bool:
        """I byte passano da noi: si puo' fare tutto il resto."""
        return not self.incorniciata

    @property
    def e_hls(self) -> bool:
        return self.tipo == HLS

    @property
    def due_tracce(self) -> bool:
        """Video muto e audio a parte, da tenere allineati nel browser."""
        return bool(self.indirizzo_audio)
