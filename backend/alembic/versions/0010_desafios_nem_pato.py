"""Add persistent challenge resolution for Nem a Pato.

Revision ID: 0010
Revises: 0009
"""

from alembic import op
import sqlalchemy as sa

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | None = None
depends_on: str | None = None

def _bigint_pk() -> sa.BigInteger:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")

def upgrade() -> None:
    op.add_column("jogadores_partida_nem_pato", sa.Column("patos", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.create_check_constraint("ck_jogadores_partida_nem_pato_patos_nao_negativo", "jogadores_partida_nem_pato", "patos >= 0")
    op.create_table(
        "desafios_nem_pato",
        sa.Column("id", _bigint_pk(), autoincrement=True, nullable=False),
        sa.Column("rodada_id", sa.BigInteger(), nullable=False),
        sa.Column("desafiante_jogador_partida_id", sa.Uuid(), nullable=False),
        sa.Column("palpite_desafiado_id", sa.BigInteger(), nullable=False),
        sa.Column("jogador_penalizado_id", sa.Uuid(), nullable=False),
        sa.Column("client_action_id", sa.Uuid(), nullable=False),
        sa.Column("resolvido_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["rodada_id"], ["rodadas_nem_pato.id"]),
        sa.ForeignKeyConstraint(["desafiante_jogador_partida_id"], ["jogadores_partida_nem_pato.id"]),
        sa.ForeignKeyConstraint(["palpite_desafiado_id"], ["palpites_nem_pato.id"]),
        sa.ForeignKeyConstraint(["jogador_penalizado_id"], ["jogadores_partida_nem_pato.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rodada_id", name="uq_desafios_nem_pato_rodada"),
        sa.UniqueConstraint("client_action_id", name="uq_desafios_nem_pato_client_action"),
    )

def downgrade() -> None:
    op.drop_table("desafios_nem_pato")
    op.drop_constraint("ck_jogadores_partida_nem_pato_patos_nao_negativo", "jogadores_partida_nem_pato", type_="check")
    op.drop_column("jogadores_partida_nem_pato", "patos")
