"""Add optional editorial metadata to official question catalogs.

Revision ID: 0014
Revises: 0013
"""

from alembic import op
import sqlalchemy as sa


revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "perguntas", sa.Column("dificuldade", sa.String(length=8), nullable=True)
    )
    op.create_check_constraint(
        "ck_perguntas_dificuldade",
        "perguntas",
        "dificuldade IN ('FACIL', 'MEDIA', 'DIFICIL') OR dificuldade IS NULL",
    )
    op.add_column(
        "perguntas_nem_pato", sa.Column("fonte_url", sa.Text(), nullable=True)
    )
    op.add_column(
        "perguntas_nem_pato",
        sa.Column("fonte_acessada_em", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("perguntas_nem_pato", "fonte_acessada_em")
    op.drop_column("perguntas_nem_pato", "fonte_url")
    op.drop_constraint("ck_perguntas_dificuldade", "perguntas", type_="check")
    op.drop_column("perguntas", "dificuldade")
