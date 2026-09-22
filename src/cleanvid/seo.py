"""Farsi trovare: cosa diciamo ai motori di ricerca, e cosa gli nascondiamo.

Il grosso della SEO di un sito come questo non sta nei trucchi, sta in tre
decisioni di struttura. Sono qui perche' si possano leggere insieme.

**1. Una lingua, un indirizzo.** Un motore indicizza indirizzi, non sessioni.
Se `/` cambiasse lingua in base a un cookie, di quattordici versioni ne
esisterebbe una sola per chi cerca. Con `/it/`, `/en/`, `/es/` ognuna e' una
pagina vera, e le `hreflang` dicono al motore che sono la stessa cosa in
lingue diverse - cosi' non vengono scambiate per copie l'una dell'altra, che
e' il modo classico di farsi togliere tredici pagine su quattordici.

**2. Le `hreflang` devono essere reciproche.** Se la pagina italiana dichiara
quella spagnola, quella spagnola deve dichiarare l'italiana. Google butta via
in blocco i gruppi che non tornano, senza dire niente. Per questo qui si
genera sempre l'elenco completo, per ogni pagina, dalla stessa funzione:
scriverle a mano in quattordici modelli e' garanzia che prima o poi uno resti
indietro.

**3. Le pagine dei video NON si indicizzano.** Questa sembra rinunciare a
qualcosa e invece e' l'unica scelta sana. `/guarda?u=...` e' uno spazio di
indirizzi infinito: ogni link che qualcuno incolla e' una pagina nuova, tutte
uguali tranne un iframe, e il contenuto dentro e' di qualcun altro. Un motore
che ci trova dentro un milione di pagine sottili e duplicate non ci premia:
ci classifica come un sito di scarto, e ci porta dietro anche la home. Si
indicizza quello che abbiamo scritto noi - la home, le spiegazioni, le
risposte alle domande - e il resto si marca `noindex`.

Quello che resta sono dettagli, ma dettagli che si pagano se mancano: il
titolo e la descrizione diversi per lingua, il `lang` giusto sull'HTML, i dati
strutturati per le domande frequenti, le anteprime per chi condivide il link.
"""

from __future__ import annotations

import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass

from .config import impostazioni
from .lingue import LINGUE, RIPIEGO, lingua


@dataclass(frozen=True, slots=True)
class Alternativa:
    codice: str      # quello che finisce in hreflang
    url: str


def base() -> str:
    return impostazioni().base_url.rstrip("/")


def indirizzo(codice: str, percorso: str = "", **parametri: str) -> str:
    """L'indirizzo intero di una pagina in una lingua.

    Intero e non relativo: canonical e hreflang vogliono indirizzi assoluti, e
    uno relativo li' viene ignorato in silenzio.
    """
    coda = f"?{urllib.parse.urlencode(parametri)}" if parametri else ""
    return f"{base()}/{codice}{percorso}{coda}"


def alternative(percorso: str = "", **parametri: str) -> list[Alternativa]:
    """Tutte le lingue della stessa pagina, piu' `x-default`.

    `x-default` e' quella che il motore propone a chi non rientra in nessuna
    delle altre. Qui e' l'inglese: e' la lingua che, fra quelle che abbiamo,
    lascia fuori meno gente.
    """
    elenco = [Alternativa(ling.codice,
                          indirizzo(ling.codice, percorso, **parametri))
              for ling in LINGUE]
    elenco.append(Alternativa("x-default",
                              indirizzo(RIPIEGO, percorso, **parametri)))
    return elenco


def robots() -> str:
    """Cosa possono visitare i motori.

    `/guarda` e `/flusso` sono chiusi per ragioni diverse: il primo perche'
    non vogliamo un milione di pagine sottili nell'indice, il secondo perche'
    sono byte di video e farli scaricare a un robot e' banda buttata - la
    nostra, e con questi volumi si sente.
    """
    righe = [
        "User-agent: *",
        "Disallow: /guarda",
        "Disallow: /flusso/",
        "Disallow: /segmento",
        "Disallow: /stato",
        *(f"Disallow: /{ling.codice}/guarda" for ling in LINGUE),
        *(f"Disallow: /{ling.codice}/stato" for ling in LINGUE),
        "",
        f"Sitemap: {base()}/sitemap.xml",
        "",
    ]
    return "\n".join(righe)


# Le pagine che vale la pena far trovare: quelle che abbiamo scritto noi.
# Non c'e' `/guarda`, e non e' una dimenticanza: vedi sopra.
#
# La home e' `/` e non stringa vuota, e la differenza non e' un dettaglio:
# `/it` e `/it/` sono due indirizzi per un motore di ricerca. Se la mappa
# dichiarasse uno e il `canonical` della pagina l'altro, ci contraddiremmo da
# soli su ogni pagina del sito.
INDICIZZABILI: tuple[tuple[str, str], ...] = (
    ("/", "1.0"),                 # la home
    ("/impostazioni", "0.3"),
)


def sitemap() -> str:
    """La mappa, con dentro le hreflang: e' il posto dove Google le preferisce.

    Ripeterle qui oltre che nell'HTML non e' ridondanza inutile: la mappa
    viene letta anche per le pagine che il crawler non ha ancora visitato, e
    per un sito nuovo e' la strada piu' veloce perche' tutte e quattordici le
    versioni vengano scoperte insieme invece che una alla volta.
    """
    fuori = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
             'xmlns:xhtml="http://www.w3.org/1999/xhtml">']
    for percorso, priorita in INDICIZZABILI:
        alt = alternative(percorso)
        for ling in LINGUE:
            fuori.append("  <url>")
            fuori.append(f"    <loc>{indirizzo(ling.codice, percorso)}</loc>")
            for a in alt:
                fuori.append(
                    f'    <xhtml:link rel="alternate" hreflang="{a.codice}" '
                    f'href="{a.url}"/>')
            fuori.append(f"    <priority>{priorita}</priority>")
            fuori.append("  </url>")
    fuori.append("</urlset>")
    return "\n".join(fuori) + "\n"


def dati_strutturati_home(codice: str,
                          t: Callable[..., str]) -> dict[str, object]:
    """I dati che diventano il riquadro delle domande nei risultati.

    Le domande e le risposte sono le stesse della pagina, prese dallo stesso
    catalogo: dichiarare qui qualcosa che sulla pagina non c'e' e' il modo di
    farsi togliere il riquadro, e a volte di peggio.
    """
    ling = lingua(codice)
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "@id": f"{base()}/#sito",
                "url": indirizzo(codice),
                "name": t("marchio.nome"),
                "description": t("meta.home.descrizione"),
                "inLanguage": ling.codice,
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": t(f"home.faq.{n}.d"),
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": t(f"home.faq.{n}.r"),
                        },
                    }
                    for n in range(1, 6)
                ],
            },
        ],
    }
