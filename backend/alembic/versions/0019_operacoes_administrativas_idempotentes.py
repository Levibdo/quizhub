"""Add persistent idempotency records for administrative operations.

Revision ID: 0019
Revises: 0018
"""

from alembic import op
import sqlalchemy as sa


revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "operacoes_administrativas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("administrador_id", sa.Uuid(), nullable=False),
        sa.Column("tipo_operacao", sa.String(length=80), nullable=False),
        sa.Column("recurso_tipo", sa.String(length=80), nullable=False),
        sa.Column("recurso_id", sa.String(length=160), nullable=True),
        sa.Column("chave_idempotencia", sa.String(length=200), nullable=False),
        sa.Column("hash_requisicao", sa.String(length=64), nullable=False),
        sa.Column(
            "estado", sa.String(length=24), nullable=False,
            server_default="EM_ANDAMENTO",
        ),
        sa.Column("codigo_resultado", sa.Integer(), nullable=True),
        sa.Column("resposta_sanitizada", sa.JSON(), nullable=True),
        sa.Column("tentativas", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "criada_em", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "atualizada_em", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("concluida_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "estado IN ('EM_ANDAMENTO', 'CONCLUIDA', 'FALHOU', 'INTERROMPIDA')",
            name="ck_operacoes_admin_estado",
        ),
        sa.CheckConstraint(
            "tentativas >= 1", name="ck_operacoes_admin_tentativas"
        ),
        sa.ForeignKeyConstraint(
            ["administrador_id"], ["usuarios.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "administrador_id", "tipo_operacao", "chave_idempotencia",
            name="uq_operacoes_admin_escopo_chave",
        ),
    )
    op.create_index(
        "ix_operacoes_admin_administrador", "operacoes_administrativas",
        ["administrador_id"], unique=False,
    )
    op.create_index(
        "ix_operacoes_admin_estado_atualizada", "operacoes_administrativas",
        ["estado", "atualizada_em"], unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_operacoes_admin_estado_atualizada",
        table_name="operacoes_administrativas",
    )
    op.drop_index(
        "ix_operacoes_admin_administrador",
        table_name="operacoes_administrativas",
    )
    op.drop_table("operacoes_administrativas")
