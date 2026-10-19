"""Add explicit administrator role and administrative audit trail.

Revision ID: 0018
Revises: 0017
"""

from alembic import op
import sqlalchemy as sa


revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "usuarios",
        sa.Column(
            "perfil", sa.String(length=16), nullable=False,
            server_default="JOGADOR",
        ),
    )
    op.create_check_constraint(
        "ck_usuarios_perfil", "usuarios", "perfil IN ('JOGADOR', 'ADMIN')"
    )
    op.create_table(
        "auditorias_administrativas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("administrador_id", sa.Uuid(), nullable=False),
        sa.Column(
            "ocorrida_em", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("operacao", sa.String(length=80), nullable=False),
        sa.Column("recurso_tipo", sa.String(length=80), nullable=False),
        sa.Column("recurso_id", sa.String(length=160), nullable=True),
        sa.Column("resultado", sa.String(length=24), nullable=False),
        sa.Column("catalogo_id", sa.String(length=80), nullable=True),
        sa.Column("catalogo_versao", sa.Integer(), nullable=True),
        sa.Column("detalhes", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["administrador_id"], ["usuarios.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_auditorias_administrativas_ocorrida_em",
        "auditorias_administrativas", ["ocorrida_em"], unique=False,
    )
    op.create_index(
        "ix_auditorias_administrativas_administrador_id",
        "auditorias_administrativas", ["administrador_id"], unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_auditorias_administrativas_administrador_id",
        table_name="auditorias_administrativas",
    )
    op.drop_index(
        "ix_auditorias_administrativas_ocorrida_em",
        table_name="auditorias_administrativas",
    )
    op.drop_table("auditorias_administrativas")
    op.drop_constraint("ck_usuarios_perfil", "usuarios", type_="check")
    op.drop_column("usuarios", "perfil")
