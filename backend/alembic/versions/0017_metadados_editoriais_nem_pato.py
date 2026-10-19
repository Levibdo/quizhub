"""Persist Nem a Pato editorial metadata without changing legacy rows.

Revision ID: 0017
Revises: 0016

Downgrading after versioned catalogs have been imported permanently discards
these three editorial metadata fields. Use downgrade only on an appropriate
disposable database or after an explicit data-retention decision.
"""

from alembic import op
import sqlalchemy as sa


revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "perguntas_nem_pato",
        sa.Column("tema_editorial", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "perguntas_nem_pato",
        sa.Column("natureza_resposta", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "perguntas_nem_pato",
        sa.Column("qualificacao_estimativa", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "ck_perguntas_nem_pato_natureza_resposta",
        "perguntas_nem_pato",
        "natureza_resposta IS NULL OR natureza_resposta IN ('EXATA', 'ESTIMATIVA')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_perguntas_nem_pato_natureza_resposta",
        "perguntas_nem_pato",
        type_="check",
    )
    op.drop_column("perguntas_nem_pato", "qualificacao_estimativa")
    op.drop_column("perguntas_nem_pato", "natureza_resposta")
    op.drop_column("perguntas_nem_pato", "tema_editorial")
