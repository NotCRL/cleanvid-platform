#!/usr/bin/env python3
"""Traduce i testi dell'interfaccia con Claude, e lascia il risultato su disco.

    python strumenti/traduci.py            # tutte le lingue che mancano
    python strumenti/traduci.py es fr      # solo queste
    python strumenti/traduci.py --tutto    # rifa' tutto da capo
    python strumenti/traduci.py --controlla # dice cosa manca, non chiama niente

**Perche' si traduce adesso e non mentre qualcuno guarda la pagina.** Tradurre
a ogni richiesta sarebbe piu' comodo da scrivere e sbagliato per tre motivi,
in ordine di gravita':

1. *I motori di ricerca.* Un testo che cambia a ogni visita e' un testo di cui
   Google non sa cosa indicizzare. Una traduzione stabile, sempre uguale, e'
   una pagina vera; una generata al volo e' una pagina che oggi dice una cosa
   e domani un'altra, e non si posiziona.
2. *Nessuno la rilegge.* Una traduzione automatica messa online senza che
   qualcuno l'abbia guardata e' esattamente cio' che Google chiama contenuto
   di scarto. Qui il risultato finisce in un file, entra in un commit, e si
   puo' correggere a mano - e la correzione resta.
3. *Il costo e il tempo.* Una chiamata a un modello per ogni pagina significa
   pagare ogni visita e aspettare un secondo prima di mostrare qualcosa.

**Le impronte.** Accanto ai testi si tiene `.impronte.json`: per ogni lingua e
per ogni chiave, l'impronta della frase italiana da cui e' nata la traduzione.
Cosi' quando una frase italiana cambia, il programma sa quali traduzioni sono
diventate vecchie - senza, l'unico modo sarebbe ritradurre tutto ogni volta,
o non accorgersene mai. Le correzioni fatte a mano restano: si ritraduce solo
cio' che e' cambiato davvero.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE / "src"))

from cleanvid.lingue import ORIGINALE  # noqa: E402
from cleanvid.lingue.catalogo import LINGUE, lingua  # noqa: E402

TESTI = RADICE / "src" / "cleanvid" / "lingue" / "testi"
IMPRONTE = TESTI / ".impronte.json"

# Sonnet e non il modello piu' grande: tradurre una frase corta e' un lavoro
# che sa fare benissimo, costa molto meno, e qui le frasi sono qualche
# centinaio per lingua.
MODELLO = "claude-sonnet-5"

ISTRUZIONI = """Sei il traduttore di cleanvid, un servizio che apre il video di \
una pagina web togliendo tutto il resto: banner, popup, pubblicità.

Traduci dall'italiano al {lingua} ({codice}) il dizionario JSON che ricevi.

Regole, in ordine di importanza:

1. Rispondi SOLO con un oggetto JSON valido, le stesse identiche chiavi che \
hai ricevuto. Nessun commento, nessun testo prima o dopo.
2. I segnaposto fra graffe — {{titolo}}, {{piattaforma}}, {{lingua}} — vanno \
riportati identici, graffe comprese. Se ne sposti uno o ne cambi il nome, la \
pagina mostra testo rotto.
3. Non tradurre "cleanvid", "HLS", "yt-dlp", né i nomi delle piattaforme.
4. È l'interfaccia di un sito, non un documento: frasi corte, tono diretto e \
cortese, del tipo che si usa sui bottoni e nei menu. Se la tua lingua \
distingue fra registro formale e informale, usa quello che un sito \
tecnologico userebbe con un adulto sconosciuto.
5. Le chiavi che cominciano per "meta." sono titoli e descrizioni per i \
motori di ricerca. Devono restare invitanti e sotto i 155 caratteri, e vanno \
adattate alla lingua invece che tradotte parola per parola.
6. Adatta, non ricalcare. Una frase che in italiano è un modo di dire va resa \
con quello che direbbe davvero una persona in {lingua}."""


def carica(percorso: Path) -> dict[str, str]:
    if not percorso.exists():
        return {}
    with percorso.open(encoding="utf-8") as f:
        dati: dict[str, str] = json.load(f)
    return dati


def salva(percorso: Path, dati: dict[str, object]) -> None:
    # ordinate per chiave e con l'unicode vero dentro: cosi' un `git diff` si
    # legge, invece di essere una riga sola piena di é
    with percorso.open("w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def impronta(frase: str) -> str:
    return hashlib.sha256(frase.encode()).hexdigest()[:16]


def da_fare(codice: str, originale: dict[str, str],
            impronte: dict[str, dict[str, str]],
            tutto: bool = False) -> dict[str, str]:
    """Le chiavi da tradurre: quelle che mancano e quelle invecchiate."""
    if tutto:
        return dict(originale)
    esistenti = carica(TESTI / f"{codice}.json")
    sue = impronte.get(codice, {})
    return {
        chiave: frase for chiave, frase in originale.items()
        if chiave not in esistenti or sue.get(chiave) != impronta(frase)
    }


def traduci(codice: str, pezzo: dict[str, str]) -> dict[str, str]:
    from anthropic import Anthropic

    ling = lingua(codice)
    cliente = Anthropic()
    risposta = cliente.messages.create(
        model=MODELLO,
        max_tokens=8000,
        system=ISTRUZIONI.format(lingua=ling.nome, codice=ling.codice),
        messages=[{"role": "user",
                   "content": json.dumps(pezzo, ensure_ascii=False, indent=2)}],
    )
    testo = "".join(b.text for b in risposta.content if b.type == "text").strip()
    # certi modelli incorniciano il JSON in un blocco di codice anche quando
    # gli si dice di non farlo: si toglie invece di fallire
    if testo.startswith("```"):
        testo = testo.split("\n", 1)[1].rsplit("```", 1)[0]
    return dict(json.loads(testo))


def controlla_segnaposto(chiave: str, prima: str, dopo: str) -> str | None:
    """I segnaposto devono restare quelli. Se cambiano, la pagina mostra testo rotto."""
    import re
    attesi = set(re.findall(r"\{(\w+)\}", prima))
    trovati = set(re.findall(r"\{(\w+)\}", dopo))
    if attesi != trovati:
        return (f"{chiave}: segnaposto cambiati "
                f"({sorted(attesi)} -> {sorted(trovati)})")
    return None


def main() -> int:
    argomenti = sys.argv[1:]
    tutto = "--tutto" in argomenti
    solo_controllo = "--controlla" in argomenti
    scelte = [a for a in argomenti if not a.startswith("--")]

    originale = carica(TESTI / f"{ORIGINALE}.json")
    if not originale:
        print(f"manca {ORIGINALE}.json: non c'e' niente da cui tradurre")
        return 1
    impronte = carica(IMPRONTE)  # type: ignore[assignment]

    codici = scelte or [ling.codice for ling in LINGUE
                        if ling.codice not in (ORIGINALE, "en")]

    lavoro = {c: da_fare(c, originale, impronte, tutto) for c in codici}
    manca = {c: p for c, p in lavoro.items() if p}

    if not manca:
        print("tutto tradotto e aggiornato.")
        return 0

    for codice, pezzo in manca.items():
        print(f"  {codice}: {len(pezzo)} frasi da tradurre")
    if solo_controllo:
        return 0

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\nserve ANTHROPIC_API_KEY per tradurre.")
        return 1

    problemi: list[str] = []
    for codice, pezzo in manca.items():
        print(f"\n{codice}: traduco {len(pezzo)} frasi...", flush=True)
        nuove = traduci(codice, pezzo)

        for chiave, frase in pezzo.items():
            if chiave not in nuove:
                problemi.append(f"{codice}/{chiave}: non tradotta")
                continue
            guaio = controlla_segnaposto(chiave, frase, nuove[chiave])
            if guaio:
                problemi.append(f"{codice}/{guaio}")

        # le frasi gia' corrette a mano restano: si sovrascrivono solo quelle
        # che erano da rifare
        esistenti = carica(TESTI / f"{codice}.json")
        esistenti.update({k: v for k, v in nuove.items() if k in pezzo})
        salva(TESTI / f"{codice}.json", dict(esistenti))

        sue = impronte.setdefault(codice, {})
        for chiave in pezzo:
            if chiave in nuove:
                sue[chiave] = impronta(originale[chiave])
        salva(IMPRONTE, dict(impronte))
        print(f"{codice}: scritto {codice}.json")

    if problemi:
        print("\nda guardare a mano:")
        for p in problemi:
            print(f"  {p}")
        return 1

    print("\nfatto. Ora rileggile: una traduzione non riletta e' una bozza.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
