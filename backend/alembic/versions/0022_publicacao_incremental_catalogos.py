"""Link drafts to incrementally published catalogs.

Revision ID: 0022
Revises: 0021
"""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("catalogos_oficiais_rascunhos", sa.Column("catalogo_publicado_id", sa.Uuid(), nullable=True))
    op.add_column("catalogos_oficiais_rascunhos", sa.Column("publicado_em", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_rascunhos_catalogo_publicado", "catalogos_oficiais_rascunhos", "catalogos_oficiais", ["catalogo_publicado_id"], ["id"], ondelete="RESTRICT")
    op.create_unique_constraint("uq_rascunhos_catalogo_publicado", "catalogos_oficiais_rascunhos", ["catalogo_publicado_id"])
    # Rascunhos PUBLICADO legados não possuem vínculo recuperável de forma
    # inequívoca. Eles permanecem compatíveis com ambos os campos nulos;
    # publicações feitas a partir de 0022 sempre gravam ambos atomicamente.
    op.create_check_constraint("ck_catalogos_rascunhos_publicacao", "catalogos_oficiais_rascunhos", "(catalogo_publicado_id IS NULL AND publicado_em IS NULL) OR (status = 'PUBLICADO' AND catalogo_publicado_id IS NOT NULL AND publicado_em IS NOT NULL)")


def downgrade():
    op.drop_constraint("ck_catalogos_rascunhos_publicacao", "catalogos_oficiais_rascunhos", type_="check")
    op.drop_constraint("uq_rascunhos_catalogo_publicado", "catalogos_oficiais_rascunhos", type_="unique")
    op.drop_constraint("fk_rascunhos_catalogo_publicado", "catalogos_oficiais_rascunhos", type_="foreignkey")
    op.drop_column("catalogos_oficiais_rascunhos", "publicado_em")
    op.drop_column("catalogos_oficiais_rascunhos", "catalogo_publicado_id")
