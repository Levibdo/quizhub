"""Persist players and matches.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-28

"""

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "jogadores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.String(), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "partidas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("jogador_id", sa.Uuid(), nullable=False),
        sa.Column("categoria_id", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.String(),
            server_default=sa.text("'EM_ANDAMENTO'"),
            nullable=False,
        ),
        sa.Column("pontuacao", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("acertos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("erros", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "iniciada_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finalizada_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('EM_ANDAMENTO', 'FINALIZADA', 'EXPIRADA')",
            name="ck_partidas_status",
        ),
        sa.CheckConstraint(
            "pontuacao >= 0", name="ck_partidas_pontuacao_nao_negativa"
        ),
        sa.CheckConstraint("acertos >= 0", name="ck_partidas_acertos_nao_negativos"),
        sa.CheckConstraint("erros >= 0", name="ck_partidas_erros_nao_negativos"),
        sa.ForeignKeyConstraint(["categoria_id"], ["categorias.id"]),
        sa.ForeignKeyConstraint(["jogador_id"], ["jogadores.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_partidas_jogador_id", "partidas", ["jogador_id"])
    op.create_index("ix_partidas_categoria_id", "partidas", ["categoria_id"])
    op.create_index("ix_partidas_status", "partidas", ["status"])


def downgrade() -> None:
    op.drop_index("ix_partidas_status", table_name="partidas")
    op.drop_index("ix_partidas_categoria_id", table_name="partidas")
    op.drop_index("ix_partidas_jogador_id", table_name="partidas")
    op.drop_table("partidas")
    op.drop_table("jogadores")
