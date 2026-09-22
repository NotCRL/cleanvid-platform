"""Stanze: guardare insieme.

Due regole che decidono tutto il resto.

**Il posizionamento non sta qui.** Una stanza dove dieci persone guardano
manda posizione e stato molte volte al minuto. Se quel traffico finisse in
Postgres, il database diventerebbe il collo di bottiglia della festa. Su
disco resta solo cio' che deve sopravvivere a un riavvio: chi possiede la
stanza, chi puo' entrarci, cosa si e' detto in chat. Il polso della
riproduzione vive in Redis, dove nasce e muore con la stanza.

**La visibilita' e' una cosa, la password un'altra.** Una stanza pubblica
puo' avere la password (la trovi nell'elenco ma non entri senza), una
privata puo' non averla (entri solo se hai il link). Tenerle separate da
subito evita di riscrivere le query di ricerca dopo.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (Boolean, DateTime, Enum, ForeignKey, Index, Integer,
                        String, Text, func)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Visibilita(str, enum.Enum):
    PUBBLICA = "pubblica"    # compare nella ricerca delle stanze aperte
    NON_IN_ELENCO = "non_in_elenco"   # esiste, ma la trovi solo col link
    PRIVATA = "privata"      # solo invitati


class RuoloInStanza(str, enum.Enum):
    PADRONE = "padrone"      # comanda la riproduzione
    PRESENTATORE = "presentatore"   # puo' comandarla anche lui
    OSPITE = "ospite"        # guarda e scrive in chat


class Stanza(Base):
    __tablename__ = "stanze"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # quello che finisce nell'indirizzo: /stanza/verde-corsa-42
    codice: Mapped[str] = mapped_column(String(48), unique=True, nullable=False)
    titolo: Mapped[str] = mapped_column(String(80), nullable=False)

    padrone_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("utenti.id", ondelete="CASCADE"), nullable=False, index=True)
    padrone = relationship("Utente", back_populates="stanze")

    visibilita: Mapped[Visibilita] = mapped_column(
        Enum(Visibilita, name="visibilita_stanza"),
        default=Visibilita.NON_IN_ELENCO, nullable=False)
    # separata dalla visibilita' di proposito: sono due domande diverse
    password_hash: Mapped[str | None] = mapped_column(String(255))

    # Cosa si sta guardando. Solo il link e il titolo: il flusso vero lo
    # risolve ogni partecipante per conto suo, con la sua qualita' e la sua
    # banda. Mandare in giro l'indirizzo del flusso non funzionerebbe
    # comunque - quasi tutti scadono e sono legati a chi li ha chiesti.
    url_corrente: Mapped[str | None] = mapped_column(Text)
    titolo_corrente: Mapped[str | None] = mapped_column(String(200))

    aperta: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_persone: Mapped[int] = mapped_column(Integer, default=20, nullable=False)

    creata: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    ultima_attivita: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)

    membri = relationship("MembroStanza", back_populates="stanza",
                          cascade="all, delete-orphan")
    messaggi = relationship("MessaggioStanza", back_populates="stanza",
                            cascade="all, delete-orphan")

    __table_args__ = (
        # la ricerca delle stanze aperte: filtra su queste tre, in quest'ordine
        Index("ix_stanze_ricerca", "visibilita", "aperta", "ultima_attivita"),
    )

    @property
    def protetta(self) -> bool:
        return self.password_hash is not None


class MembroStanza(Base):
    __tablename__ = "membri_stanza"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stanza_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stanze.id", ondelete="CASCADE"), nullable=False)
    utente_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("utenti.id", ondelete="CASCADE"), nullable=False)
    ruolo: Mapped[RuoloInStanza] = mapped_column(
        Enum(RuoloInStanza, name="ruolo_stanza"),
        default=RuoloInStanza.OSPITE, nullable=False)
    entrato: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)

    stanza = relationship("Stanza", back_populates="membri")

    __table_args__ = (
        Index("ix_membri_unici", "stanza_id", "utente_id", unique=True),
    )


class MessaggioStanza(Base):
    """La chat resta su disco: chi entra dopo deve poter leggere l'inizio."""

    __tablename__ = "messaggi_stanza"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stanza_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stanze.id", ondelete="CASCADE"), nullable=False)
    autore_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("utenti.id", ondelete="SET NULL"))
    # copiato al momento: se l'autore cambia nome o sparisce, la chat di ieri
    # deve restare leggibile com'era
    autore_nome: Mapped[str] = mapped_column(String(40), nullable=False)
    testo: Mapped[str] = mapped_column(String(800), nullable=False)
    quando: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)

    stanza = relationship("Stanza", back_populates="messaggi")

    __table_args__ = (
        Index("ix_messaggi_stanza_tempo", "stanza_id", "id"),
    )
