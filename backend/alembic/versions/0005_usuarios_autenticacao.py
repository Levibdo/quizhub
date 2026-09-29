"""Add registered users and link them to player participations.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-29

"""

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("senha_hash", sa.Text(), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_usuarios_email"),
    )
    op.add_column("jogadores", sa.Column("usuario_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_jogadores_usuario_id_usuarios",
        "jogadores",
        "usuarios",
        ["usuario_id"],
        ["id"],
    )
    op.create_index("ix_jogadores_usuario_id", "jogadores", ["usuario_id"])


def downgrade() -> None:
    op.drop_index("ix_jogadores_usuario_id", table_name="jogadores")
    op.drop_constraint(
        "fk_jogadores_usuario_id_usuarios",
        "jogadores",
        type_="foreignkey",
    )
    op.drop_column("jogadores", "usuario_id")
    op.drop_table("usuarios")
