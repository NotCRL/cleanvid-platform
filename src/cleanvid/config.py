"""Configurazione: tutto da variabili d'ambiente, niente valori cuciti dentro.

Regola: se un valore cambia fra il tuo computer e il server, sta qui. Se non
cambia mai, sta nel codice. La via di mezzo - un default comodo che in
produzione e' sbagliato - e' il modo classico di mandare in rete un servizio
con la chiave di firma di sviluppo.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Impostazioni(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLEANVID_",
                                      env_file=".env", extra="ignore")

    ambiente: str = "sviluppo"          # sviluppo | produzione
    segreto: str = Field(min_length=32) # firma dei cookie: NIENTE default
    base_url: str = "http://localhost:8000"

    database_url: str = "postgresql+asyncpg://cleanvid:cleanvid@localhost/cleanvid"
    redis_url: str = "redis://localhost:6379/0"

    # --- estrazione ---
    # Quanto vale un'estrazione prima di rifarla. Corto, perche' gli indirizzi
    # dei flussi scadono; ma non cortissimo, perche' e' la cosa piu' cara che
    # facciamo e in una stanza da dieci persone deve costare una volta sola.
    cache_estrazione_s: int = 1800
    estrazioni_insieme: int = 4         # yt-dlp contemporanei: oltre, la CPU muore
    timeout_estrazione_s: int = 45

    # --- limiti, perche' e' aperto al mondo ---
    aperture_al_minuto: int = 20
    stanze_per_utente: int = 5
    messaggi_al_minuto: int = 30

    # --- potatura ---
    giorni_anonimi_inattivi: int = 90   # poi la riga si cancella
    ore_stanze_morte: int = 12

    @property
    def in_produzione(self) -> bool:
        return self.ambiente == "produzione"


@lru_cache
def impostazioni() -> Impostazioni:
    return Impostazioni()
