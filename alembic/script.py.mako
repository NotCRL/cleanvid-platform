"""${message}

Revisione: ${up_revision}
Precedente: ${down_revision | comma,n}
Creata: ${create_date}

Una migrazione si legge come una frase: cosa cambia, e come si torna indietro.
Se `giu()` resta vuota, quella migrazione non si puo' annullare - va detto qui
sopra, non scoperto la sera che serve.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}
revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
