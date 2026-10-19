"""Create the official Macabro category for Nem a Pato catalogs.

Revision ID: 0016
Revises: 0015
"""

from alembic import op
import sqlalchemy as sa


revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | None = None
depends_on: str | None = None

MACABRO_ID = "c73ff198-c1de-5787-b796-c74d2df1b696"
MACABRO_SLUG = "macabro"
MACABRO_MODE = "NEM_A_PATO"


def upgrade() -> None:
    bind = op.get_bind()
    by_id = bind.execute(sa.text(
        "SELECT slug, nome, modo, origem, usuario_id, ativa, excluida_em "
        "FROM categorias WHERE id = CAST(:id AS uuid)"
    ), {"id": MACABRO_ID}).mappings().one_or_none()
    by_slug = bind.execute(sa.text(
        "SELECT id, nome, origem FROM categorias "
        "WHERE modo = :modo AND slug = :slug AND origem = 'OFICIAL'"
    ), {"modo": MACABRO_MODE, "slug": MACABRO_SLUG}).mappings().one_or_none()

    if by_id is not None:
        expected = (
            by_id["slug"] == MACABRO_SLUG
            and by_id["nome"] == "Macabro"
            and by_id["modo"] == MACABRO_MODE
            and by_id["origem"] == "OFICIAL"
            and by_id["usuario_id"] is None
            and by_id["ativa"] is True
            and by_id["excluida_em"] is None
        )
        if not expected:
            raise RuntimeError("0016 preflight failed: Macabro UUID is already in conflicting use")
        return
    if by_slug is not None:
        raise RuntimeError(
            "0016 preflight failed: official NEM_A_PATO/macabro slug already "
            f"uses UUID {by_slug['id']}"
        )

    bind.execute(sa.text(
        "INSERT INTO categorias "
        "(id, slug, nome, descricao, modo, origem, usuario_id, ativa) "
        "VALUES (CAST(:id AS uuid), :slug, 'Macabro', "
        "'História macabra, mistérios e fatos sombrios documentados.', "
        ":modo, 'OFICIAL', NULL, true)"
    ), {"id": MACABRO_ID, "slug": MACABRO_SLUG, "modo": MACABRO_MODE})


def downgrade() -> None:
    # Never remove a category after questions or historical matches reference it.
    op.get_bind().execute(sa.text(
        "DELETE FROM categorias c "
        "WHERE c.id = CAST(:id AS uuid) "
        "AND c.slug = :slug AND c.modo = :modo AND c.origem = 'OFICIAL' "
        "AND NOT EXISTS (SELECT 1 FROM perguntas_nem_pato p WHERE p.categoria_id = c.id) "
        "AND NOT EXISTS (SELECT 1 FROM partidas_nem_pato p WHERE p.categoria_id = c.id)"
    ), {"id": MACABRO_ID, "slug": MACABRO_SLUG, "modo": MACABRO_MODE})
