"""Chi usa cleanvid.

LA DECISIONE PIU' IMPORTANTE DI TUTTO IL PROGETTO sta in questo file, e va
presa adesso perche' dopo costa carissima: **anonimo e registrato sono la
stessa riga**, non due mondi separati.

Chi arriva senza fare niente riceve comunque un utente vero, con un id vero,
e un cookie firmato che lo riporta a quella riga. La sua cronologia, i suoi
preferiti, le sue stanze esistono da subito. Registrarsi non crea un account
nuovo: **attacca delle credenziali alla riga che gia' c'e'**. Cosi' nessuno
perde niente iscrivendosi, che e' esattamente il momento in cui la gente
abbandona.

L'alternativa - anonimi tenuti nel browser, registrati nel database - sembra
piu' semplice il primo giorno e diventa impossibile il giorno che vuoi le
stanze: una stanza ha bisogno di sapere chi e' il padrone e chi sono gli
ospiti, e "un oggetto nel localStorage di qualcuno" non e' un proprietario.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class TipoUtente(str, enum.Enum):
    ANONIMO = "anonimo"        # ha solo un cookie: esiste, ma nessuno sa chi e'
    REGISTRATO = "registrato"  # ha attaccato email e password alla sua riga


class Utente(Base):
    __tablename__ = "utenti"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tipo: Mapped[TipoUtente] = mapped_column(
        Enum(TipoUtente, name="tipo_utente"), default=TipoUtente.ANONIMO,
        nullable=False, index=True)

    # Nulli finche' resta anonimo. Quando si registra si riempiono QUESTI,
    # non si crea una riga nuova: tutto quello che aveva resta suo.
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    nome: Mapped[str | None] = mapped_column(String(40))

    # Il nome che si vede nelle stanze. Un anonimo ne ha uno generato
    # ("Ospite 4712") perche' in una chat "anonimo" tre volte non si distingue.
    nome_visibile: Mapped[str] = mapped_column(String(40), nullable=False)

    # La lingua scelta. Non e' "quella del browser": e' quella che la persona
    # ha deciso, e vale piu' di qualunque cosa dica l'intestazione del
    # browser o l'indirizzo da cui arriva. Vuota finche' non sceglie: cosi' si
    # distingue "non ha mai scelto" da "ha scelto l'inglese", che sono due
    # cose diverse quando si decide se proporgliene un'altra.
    lingua: Mapped[str | None] = mapped_column(String(8))

    creato: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    visto: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    bloccato: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    biblioteca = relationship("VoceBiblioteca", back_populates="utente",
                              cascade="all, delete-orphan")
    stanze = relationship("Stanza", back_populates="padrone",
                          cascade="all, delete-orphan")

    __table_args__ = (
        # gli anonimi mai piu' tornati si potano: senza questo indice la
        # pulizia diventa una scansione dell'intera tabella
        Index("ix_utenti_potatura", "tipo", "visto"),
    )

    @property
    def e_registrato(self) -> bool:
        return self.tipo is TipoUtente.REGISTRATO
