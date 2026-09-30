"""Add nullable explanation to questions.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-29

"""

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "perguntas",
        sa.Column("explicacao", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("perguntas", "explicacao")
