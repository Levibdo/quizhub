"""Add versioned official catalogs and complete editorial provenance.

Revision ID: 0015
Revises: 0014
"""

from alembic import op
import sqlalchemy as sa


revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "catalogos_oficiais",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("catalogo_id", sa.String(length=80), nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False),
        sa.Column("modo", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="PREPARADO", nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ativado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("arquivado_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("modo IN ('QUIZ_CLASSICO', 'NEM_A_PATO')", name="ck_catalogos_oficiais_modo"),
        sa.CheckConstraint("status IN ('PREPARADO', 'ATIVO', 'ARQUIVADO')", name="ck_catalogos_oficiais_status"),
        sa.CheckConstraint("versao >= 1", name="ck_catalogos_oficiais_versao_positiva"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("catalogo_id", "versao", name="uq_catalogos_oficiais_id_versao"),
    )
    op.create_index(
        "uq_catalogos_oficiais_modo_ativo", "catalogos_oficiais", ["modo"],
        unique=True, postgresql_where=sa.text("status = 'ATIVO'"),
        sqlite_where=sa.text("status = 'ATIVO'"),
    )
    for tabela, nome_uq in (
        ("perguntas", "uq_perguntas_catalogo_id_editorial"),
        ("perguntas_nem_pato", "uq_perguntas_nem_pato_catalogo_id_editorial"),
    ):
        op.add_column(tabela, sa.Column("catalogo_oficial_id", sa.Uuid(), nullable=True))
        op.add_column(tabela, sa.Column("id_editorial", sa.String(length=80), nullable=True))
        op.create_foreign_key(
            f"fk_{tabela}_catalogo_oficial_id", tabela, "catalogos_oficiais",
            ["catalogo_oficial_id"], ["id"], ondelete="RESTRICT",
        )
        op.create_unique_constraint(
            nome_uq, tabela, ["catalogo_oficial_id", "id_editorial"]
        )
        op.create_index(f"ix_{tabela}_catalogo_oficial_id", tabela, ["catalogo_oficial_id"])

    op.create_table(
        "fontes_perguntas_oficiais",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("pergunta_id", sa.BigInteger(), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(length=300), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("acessada_em", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["pergunta_id"], ["perguntas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pergunta_id", "ordem", name="uq_fontes_perguntas_oficiais_ordem"),
    )
    op.create_index(
        "ix_fontes_perguntas_oficiais_pergunta_id",
        "fontes_perguntas_oficiais", ["pergunta_id"],
    )
    op.create_table(
        "fontes_perguntas_nem_pato_oficiais",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("pergunta_id", sa.BigInteger(), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(length=300), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("acessada_em", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["pergunta_id"], ["perguntas_nem_pato.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pergunta_id", "ordem", name="uq_fontes_perguntas_nem_pato_oficiais_ordem"),
    )
    op.create_index(
        "ix_fontes_perguntas_nem_pato_oficiais_pergunta_id",
        "fontes_perguntas_nem_pato_oficiais", ["pergunta_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fontes_perguntas_nem_pato_oficiais_pergunta_id",
        table_name="fontes_perguntas_nem_pato_oficiais",
    )
    op.drop_table("fontes_perguntas_nem_pato_oficiais")
    op.drop_index(
        "ix_fontes_perguntas_oficiais_pergunta_id",
        table_name="fontes_perguntas_oficiais",
    )
    op.drop_table("fontes_perguntas_oficiais")
    for tabela, nome_uq in (
        ("perguntas_nem_pato", "uq_perguntas_nem_pato_catalogo_id_editorial"),
        ("perguntas", "uq_perguntas_catalogo_id_editorial"),
    ):
        op.drop_index(f"ix_{tabela}_catalogo_oficial_id", table_name=tabela)
        op.drop_constraint(nome_uq, tabela, type_="unique")
        op.drop_constraint(f"fk_{tabela}_catalogo_oficial_id", tabela, type_="foreignkey")
        op.drop_column(tabela, "id_editorial")
        op.drop_column(tabela, "catalogo_oficial_id")
    op.drop_index("uq_catalogos_oficiais_modo_ativo", table_name="catalogos_oficiais")
    op.drop_table("catalogos_oficiais")
