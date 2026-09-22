"""L'icona del sito, disegnata qui invece che tenuta come file.

Serve in quattro misure diverse - il segnalibro di Safari ne vuole 180,
Android 192 e 512, la scheda del browser 32 - e tenerne quattro file sul
disco vuol dire quattro cose da rifare a mano il giorno che il marchio cambia.
Disegnarla costa qualche millisecondo, una volta, e poi sta in memoria.

E' lo stesso segno del marchio in testata: due lame e un taglio. Non un
triangolo di riproduzione generico - quello ce l'hanno tutti, e su una
schermata piena di icone non si distingue da nessun'altra.
"""

from __future__ import annotations

import struct
import zlib
from functools import lru_cache

# Gli stessi colori del foglio di stile, nel tema scuro: l'icona sta quasi
# sempre su una schermata scura, e comunque deve essere la stessa cosa.
FONDO = (0x0A, 0x0A, 0x0A)
LAMA = (0xEC, 0xEC, 0xEE)
TAGLIO = (0xB8, 0xFF, 0x3C)

# Il segno e' disegnato in un riquadro 26x24, come nell'SVG del marchio.
LARGO, ALTO = 26.0, 24.0


def _dentro(punto: tuple[float, float],
            a: tuple[float, float], b: tuple[float, float],
            c: tuple[float, float]) -> bool:
    """Il punto sta dentro il triangolo? Con i segni delle aree, che bastano."""
    def segno(p: tuple[float, float], q: tuple[float, float],
              r: tuple[float, float]) -> float:
        return (p[0] - r[0]) * (q[1] - r[1]) - (q[0] - r[0]) * (p[1] - r[1])

    d1, d2, d3 = segno(punto, a, b), segno(punto, b, c), segno(punto, c, a)
    negativi = d1 < 0 or d2 < 0 or d3 < 0
    positivi = d1 > 0 or d2 > 0 or d3 > 0
    return not (negativi and positivi)


@lru_cache(maxsize=8)
def png(misura: int = 192) -> bytes:
    """Il PNG dell'icona, della misura chiesta."""
    n = max(32, min(512, int(misura)))
    # il segno sta largo dal bordo: Android ritaglia le icone a cerchio, e un
    # segno che tocca i lati si ritrova amputato
    scala = n / max(LARGO, ALTO) * 0.72
    dx = (n - LARGO * scala) / 2
    dy = (n - ALTO * scala) / 2

    def punto(x: float, y: float) -> tuple[float, float]:
        return (x * scala + dx, y * scala + dy)

    alta = (punto(4, 1.6), punto(21.5, 11.1), punto(4, 11.1))
    bassa = (punto(1.5, 12.9), punto(17.5, 12.9), punto(1.5, 21.6))
    taglio_da, taglio_a = punto(0, 11.45)[1], punto(0, 12.45)[1]

    righe = []
    for y in range(n):
        riga = bytearray([0])                 # filtro «nessuno», per ogni riga
        for x in range(n):
            p = (x + 0.5, y + 0.5)
            if taglio_da <= p[1] <= taglio_a:
                colore = TAGLIO
            elif _dentro(p, *alta) or _dentro(p, *bassa):
                colore = LAMA
            else:
                colore = FONDO
            riga += bytes(colore)
        righe.append(bytes(riga))

    dati = zlib.compress(b"".join(righe), 9)

    def pezzo(tag: bytes, corpo: bytes) -> bytes:
        intero = tag + corpo
        return (struct.pack(">I", len(corpo)) + intero
                + struct.pack(">I", zlib.crc32(intero) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + pezzo(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 2, 0, 0, 0))
            + pezzo(b"IDAT", dati)
            + pezzo(b"IEND", b""))
