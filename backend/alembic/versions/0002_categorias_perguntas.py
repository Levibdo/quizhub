"""Persist categories and questions.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-28

"""

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "categorias",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("nome", sa.String(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("ativa", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "perguntas",
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("categoria_id", sa.String(), nullable=False),
        sa.Column("enunciado", sa.Text(), nullable=False),
        sa.Column("alternativa_a", sa.Text(), nullable=False),
        sa.Column("alternativa_b", sa.Text(), nullable=False),
        sa.Column("alternativa_c", sa.Text(), nullable=False),
        sa.Column("alternativa_d", sa.Text(), nullable=False),
        sa.Column("alternativa_correta", sa.SmallInteger(), nullable=False),
        sa.Column("ativa", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "criada_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "alternativa_correta >= 0 AND alternativa_correta <= 3",
            name="ck_perguntas_alternativa_correta",
        ),
        sa.ForeignKeyConstraint(["categoria_id"], ["categorias.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("perguntas")
    op.drop_table("categorias")
