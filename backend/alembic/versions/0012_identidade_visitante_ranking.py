"""Add a stable pseudonymous identity for future guest rankings.

Revision ID: 0012
Revises: 0011
"""

from alembic import op
import sqlalchemy as sa


revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("jogadores", sa.Column("visitante_id", sa.Uuid(), nullable=True))
    op.create_index(
        "ix_jogadores_visitante_id",
        "jogadores",
        ["visitante_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_jogadores_visitante_id", table_name="jogadores")
    op.drop_column("jogadores", "visitante_id")
