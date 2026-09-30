"""Require the explanations populated before this migration.

Revision ID: 0007
Revises: 0006
"""

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.alter_column("perguntas", "explicacao", existing_type=sa.Text(), nullable=False)


def downgrade() -> None:
    op.alter_column("perguntas", "explicacao", existing_type=sa.Text(), nullable=True)
