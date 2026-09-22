"""La roba di ognuno: cronologia, preferiti, fonti, gruppi.

Nella versione di adesso sono quattro liste globali in memoria, salvate su
quattro file JSON. Qui sono UNA tabella, con `utente_id` su ogni riga e un
campo `genere` che dice cos'e'.

Perche' una sola: cronologia, preferiti e fonti hanno gli stessi identici
attributi (un link, un titolo, quando, da dove viene) e differiscono solo per
il motivo per cui sono li'. Tenerle separate vorrebbe dire scrivere tre volte
la stessa paginazione, la stessa ricerca, la stessa potatura.

Il campo `dati` in JSONB regge quello che cambia da genere a genere - gli
header di una fonte, le celle di un gruppo - senza una migrazione ogni volta
che aggiungi un attributo.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (DateTime, Enum, Float, ForeignKey, Index, String, Text,
                        func)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Genere(str, enum.Enum):
    CRONOLOGIA = "cronologia"
    PREFERITO = "preferito"
    FONTE = "fonte"        # un flusso estratto, con i suoi header
    GRUPPO = "gruppo"      # piu' video da riaprire insieme nel muro


class VoceBiblioteca(Base):
    __tablename__ = "biblioteca"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    utente_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("utenti.id", ondelete="CASCADE"), nullable=False)
    genere: Mapped[Genere] = mapped_column(
        Enum(Genere, name="genere_voce"), nullable=False)

    url: Mapped[str] = mapped_column(Text, nullable=False)
    titolo: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    # titolo messo a mano: non va sovrascritto da quello che trova yt-dlp
    titolo_tuo: Mapped[bool] = mapped_column(default=False, nullable=False)
    piattaforma: Mapped[str] = mapped_column(String(40), default="", nullable=False)

    # continua a guardare
    posizione: Mapped[float | None] = mapped_column(Float)
    durata: Mapped[float | None] = mapped_column(Float)

    dati: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    creata: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    aggiornata: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False)

    utente = relationship("Utente", back_populates="biblioteca")

    __table_args__ = (
        # "la mia cronologia, dalla piu' recente": la query di ogni home
        Index("ix_biblioteca_mia", "utente_id", "genere", "aggiornata"),
        # "questo link ce l'ho gia'?": per non duplicare a ogni apertura
        Index("ix_biblioteca_link", "utente_id", "genere", "url", unique=True),
    )
