"""Quali lingue esistono, e come si decide quella di chi arriva.

**La lingua sta nell'indirizzo, non in un cookie.** E' la decisione che regge
tutto il resto, ed e' per i motori di ricerca: Google indicizza indirizzi, non
sessioni. Se la stessa pagina cambia lingua a seconda di un cookie, il motore
ne vede una sola versione - quella che gli capita - e le altre sette non
esistono per nessuno. Con `/it/`, `/en/`, `/es/` ogni lingua ha la sua pagina,
la sua voce nell'indice, e i suoi risultati di ricerca.

**Non si reindirizza in base al paese da cui arriva la richiesta.** E' la cosa
che sembra piu' gentile e fa piu' danno: Google visita il sito quasi sempre da
indirizzi americani, quindi vedrebbe per sempre la sola versione inglese e non
indicizzerebbe mai le altre. In piu' chi vive all'estero, o usa una VPN, si
ritrova inchiodato a una lingua che non ha scelto e non riesce a uscirne.
Quello che si fa invece: la lingua del browser si usa **una volta sola**, per
decidere dove mandare chi arriva sulla radice, e poi si propone - non si
impone - se l'indirizzo aperto e' in un'altra lingua.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Lingua:
    codice: str        # quello che finisce nell'indirizzo e in `lang=`
    nome: str          # come si chiama nella propria lingua, non nella nostra
    bandiera: str      # solo decorazione: una bandiera non e' una lingua
    rtl: bool = False  # si scrive da destra a sinistra


# L'ordine e' quello del menu. L'inglese e' primo perche' e' la scelta di
# ripiego per chi non rientra in nessuna delle altre.
LINGUE: tuple[Lingua, ...] = (
    Lingua("en", "English", "🇬🇧"),
    Lingua("it", "Italiano", "🇮🇹"),
    Lingua("es", "Español", "🇪🇸"),
    Lingua("pt", "Português", "🇵🇹"),
    Lingua("fr", "Français", "🇫🇷"),
    Lingua("de", "Deutsch", "🇩🇪"),
    Lingua("pl", "Polski", "🇵🇱"),
    Lingua("tr", "Türkçe", "🇹🇷"),
    Lingua("ru", "Русский", "🇷🇺"),
    Lingua("ar", "العربية", "🇸🇦", rtl=True),
    Lingua("hi", "हिन्दी", "🇮🇳"),
    Lingua("id", "Bahasa Indonesia", "🇮🇩"),
    Lingua("ja", "日本語", "🇯🇵"),
    Lingua("zh", "中文", "🇨🇳"),
)

PER_CODICE = {ling.codice: ling for ling in LINGUE}

# Quella che vede chi non rientra in nessuna, e quella che si dichiara come
# `x-default` ai motori di ricerca.
RIPIEGO = "en"


def esiste(codice: str) -> bool:
    return codice in PER_CODICE


def lingua(codice: str) -> Lingua:
    return PER_CODICE.get(codice, PER_CODICE[RIPIEGO])


def da_accept_language(intestazione: str | None) -> str:
    """La lingua preferita del browser, fra quelle che abbiamo.

    `Accept-Language` e' molto piu' affidabile dell'indirizzo IP per sapere
    che lingua parla una persona: dice cosa ha scelto nelle impostazioni del
    proprio sistema, non dove si trova il router. Un italiano a Berlino ha
    ancora `it` in cima, e il suo IP dice Germania.

    Si guarda anche il pezzo prima del trattino: `pt-BR` e `pt-PT` sono
    abbastanza vicini da non valere due cataloghi, almeno finche' qualcuno non
    si lamenta - e allora si aggiunge `pt-BR` come lingua a se'.
    """
    if not intestazione:
        return RIPIEGO

    voci: list[tuple[float, str]] = []
    for pezzo in intestazione.split(","):
        parti = pezzo.strip().split(";q=")
        codice = parti[0].strip().lower()
        if not codice or codice == "*":
            continue
        try:
            peso = float(parti[1]) if len(parti) > 1 else 1.0
        except ValueError:
            peso = 1.0
        voci.append((peso, codice))

    for _, codice in sorted(voci, key=lambda v: -v[0]):
        if esiste(codice):
            return codice
        radice = codice.split("-")[0]
        if esiste(radice):
            return radice
    return RIPIEGO
