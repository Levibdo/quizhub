"""Persist match questions and answers.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-28

"""

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "partida_perguntas",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("partida_id", sa.Uuid(), nullable=False),
        sa.Column("pergunta_id", sa.BigInteger(), nullable=False),
        sa.Column("ordem", sa.SmallInteger(), nullable=False),
        sa.Column("disponibilizada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("prazo_resposta_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "ordem >= 1", name="ck_partida_perguntas_ordem_positiva"
        ),
        sa.CheckConstraint(
            "prazo_resposta_em IS NULL OR disponibilizada_em IS NULL "
            "OR prazo_resposta_em > disponibilizada_em",
            name="ck_partida_perguntas_prazo_posterior",
        ),
        sa.ForeignKeyConstraint(["partida_id"], ["partidas.id"]),
        sa.ForeignKeyConstraint(["pergunta_id"], ["perguntas.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "partida_id", "ordem", name="uq_partida_perguntas_partida_ordem"
        ),
        sa.UniqueConstraint(
            "partida_id",
            "pergunta_id",
            name="uq_partida_perguntas_partida_pergunta",
        ),
    )
    op.create_index(
        "ix_partida_perguntas_pergunta_id", "partida_perguntas", ["pergunta_id"]
    )
    op.create_table(
        "respostas",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("partida_pergunta_id", sa.BigInteger(), nullable=False),
        sa.Column("alternativa_selecionada", sa.SmallInteger(), nullable=True),
        sa.Column("correta", sa.Boolean(), nullable=True),
        sa.Column(
            "timeout", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "pontos_ganhos", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "respondida_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "alternativa_selecionada IS NULL "
            "OR alternativa_selecionada BETWEEN 0 AND 3",
            name="ck_respostas_alternativa_valida",
        ),
        sa.CheckConstraint(
            "pontos_ganhos >= 0", name="ck_respostas_pontos_nao_negativos"
        ),
        sa.CheckConstraint(
            "(timeout = true "
            "AND alternativa_selecionada IS NULL "
            "AND correta IS NULL "
            "AND pontos_ganhos = 0) "
            "OR (timeout = false "
            "AND alternativa_selecionada IS NOT NULL "
            "AND correta IS NOT NULL)",
            name="ck_respostas_consistencia_timeout",
        ),
        sa.ForeignKeyConstraint(
            ["partida_pergunta_id"], ["partida_perguntas.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "partida_pergunta_id", name="uq_respostas_partida_pergunta_id"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_partida_perguntas_pergunta_id", table_name="partida_perguntas"
    )
    op.drop_table("respostas")
    op.drop_table("partida_perguntas")
