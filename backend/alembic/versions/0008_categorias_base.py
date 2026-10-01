"""Ensure the base categories required by the official catalogs.

Revision ID: 0008
Revises: 0007
"""

from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | None = None
depends_on: str | None = None

CATEGORIAS_BASE = (
    {"id": "geral", "nome": "Geral", "descricao": "Conhecimentos gerais.", "ativa": True},
    {"id": "tecnologia", "nome": "Tecnologia", "descricao": "Fundamentos de tecnologia.", "ativa": True},
    {"id": "matematica", "nome": "Matemática", "descricao": "Conceitos básicos de matemática.", "ativa": True},
    {"id": "entretenimento", "nome": "Entretenimento", "descricao": "Cinema, música, televisão e cultura.", "ativa": True},
)

categorias = sa.table(
    "categorias",
    sa.column("id", sa.String()),
    sa.column("nome", sa.String()),
    sa.column("descricao", sa.Text()),
    sa.column("ativa", sa.Boolean()),
)


def upgrade() -> None:
    conexao = op.get_bind()
    for dados in CATEGORIAS_BASE:
        existente = conexao.execute(
            sa.select(categorias.c.nome).where(categorias.c.id == dados["id"])
        ).scalar_one_or_none()
        if existente is None:
            op.bulk_insert(categorias, [dados])

    conexao.execute(
        categorias.update()
        .where(categorias.c.id == "matematica")
        .where(categorias.c.nome == "Matematica")
        .values(nome="Matemática")
    )


def downgrade() -> None:
    # As categorias podem ter perguntas, partidas ou customizações vinculadas.
    # Removê-las ou reverter nomes tornaria o downgrade destrutivo.
    pass
