"""Email e password: come si attaccano, come si verificano, come si difendono.

**Registrarsi non crea un utente nuovo: attacca delle credenziali alla riga
che c'e' gia'.** E' la decisione presa in `models/user.py` il primo giorno, e
qui si vede cosa significa in pratica: chi si registra dopo aver usato il sito
per mezz'ora **non perde niente** - la cronologia, i preferiti e i gruppi sono
gia' suoi, perche' sono sempre stati sulla stessa riga.

E' anche il momento in cui la gente abbandona, e la ragione per cui vale la
pena averlo deciso prima.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from ..media import deposito

# Argon2 e non bcrypt e non sha: bcrypt taglia la password a 72 byte senza
# dirlo, e sha - anche con il sale - si prova a miliardi al secondo su una
# scheda video. Argon2 e' fatto apposta per costare memoria, che e' la cosa
# che una scheda video non ha in abbondanza.
_hasher = PasswordHasher()

# Una password lunga batte una password complicata. Le regole del tipo «una
# maiuscola, un numero, un simbolo» producono `Password1!` e basta: sono un
# teatro che non aggiunge niente e che fa scrivere le password sui foglietti.
MINIMO_PASSWORD = 8

# Quanti tentativi sbagliati prima di fermarsi, e per quanto.
TENTATIVI = 8
FINESTRA_S = 15 * 60
CHIAVE_TENTATIVI = "accessi:"

# Un hash finto su cui perdere lo stesso tempo quando l'email non esiste.
# Senza, il tempo di risposta direbbe a chiunque **quali indirizzi sono
# registrati**: piu' corto se non c'e', piu' lungo se c'e'.
_FINTO = _hasher.hash("una password che non e' di nessuno")


class NonValida(ValueError):
    """La richiesta non si puo' soddisfare, e si sa dire perche'."""

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


def normalizza(email: str) -> str:
    """Le email non distinguono le maiuscole, e uno spazio in fondo capita."""
    return (email or "").strip().lower()


def impronta(password: str) -> str:
    if len(password or "") < MINIMO_PASSWORD:
        raise NonValida("password_corta")
    return _hasher.hash(password)


def verifica(password: str, custodita: str | None) -> bool:
    """Confronta, e impiega lo stesso tempo anche quando non c'e' niente da
    confrontare."""
    try:
        _hasher.verify(custodita or _FINTO, password or "")
        return custodita is not None
    except (VerifyMismatchError, InvalidHashError):
        return False


def va_riscritta(custodita: str) -> bool:
    """Argon2 alza i suoi parametri nel tempo: una password verificata con
    quelli vecchi si ricalcola mentre si ha in mano quella in chiaro, che e'
    l'unico momento in cui si puo' fare."""
    try:
        return bool(_hasher.check_needs_rehash(custodita))
    except InvalidHashError:
        return True


# --------------------------------------------------------------------------
# la difesa contro chi prova a indovinare
# --------------------------------------------------------------------------

async def troppi_tentativi(email: str) -> bool:
    quanti = await deposito.cliente().get(CHIAVE_TENTATIVI + normalizza(email))
    return int(quanti or 0) >= TENTATIVI


async def segna_tentativo(email: str) -> None:
    """Si contano solo quelli sbagliati, e per indirizzo.

    Per indirizzo e non per chi chiede: chi prova a indovinare cambia rete in
    un secondo, mentre l'indirizzo che vuole forzare resta quello. Il prezzo
    e' che qualcuno puo' far bloccare l'accesso a un altro conoscendone
    l'email - per questo la finestra e' corta e non c'e' nessuno da sbloccare
    a mano.
    """
    chiave = CHIAVE_TENTATIVI + normalizza(email)
    c = deposito.cliente()
    await c.incr(chiave)
    await c.expire(chiave, FINESTRA_S)


async def dimentica_tentativi(email: str) -> None:
    """Entrato: il conto riparte da zero."""
    await deposito.cliente().delete(CHIAVE_TENTATIVI + normalizza(email))
