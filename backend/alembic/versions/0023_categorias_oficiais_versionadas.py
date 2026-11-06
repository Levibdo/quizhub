"""Versiona categorias oficiais e preserva seus rótulos históricos.

Revision ID: 0023
Revises: 0022
"""
from alembic import op
import sqlalchemy as sa


revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "categorias_oficiais_versoes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("categoria_id", sa.Uuid(), nullable=False),
        sa.Column("catalogo_oficial_id", sa.Uuid(), nullable=False),
        sa.Column("modo", sa.String(20), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("nome", sa.String(100), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("origem_backfill", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("modo IN ('QUIZ_CLASSICO', 'NEM_A_PATO')", name="ck_cat_of_versoes_modo"),
        sa.CheckConstraint("length(trim(slug)) > 0 AND slug = lower(trim(slug))", name="ck_cat_of_versoes_slug"),
        sa.CheckConstraint("length(trim(nome)) > 0 AND nome = trim(nome)", name="ck_cat_of_versoes_nome"),
        sa.ForeignKeyConstraint(["categoria_id"], ["categorias.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["catalogo_oficial_id"], ["catalogos_oficiais.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("catalogo_oficial_id", "categoria_id", name="uq_cat_of_versoes_catalogo_categoria"),
        sa.UniqueConstraint("catalogo_oficial_id", "slug", name="uq_cat_of_versoes_catalogo_slug"),
    )
    op.create_index("ix_cat_of_versoes_identidade", "categorias_oficiais_versoes", ["categoria_id", "catalogo_oficial_id"])

    op.create_table(
        "categorias_oficiais_rascunhos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rascunho_id", sa.Uuid(), nullable=False),
        sa.Column("categoria_id", sa.Uuid(), nullable=False),
        sa.Column("categoria_versao_origem_id", sa.Uuid(), nullable=True),
        sa.Column("modo", sa.String(20), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("nome", sa.String(100), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("tipo_alteracao", sa.String(16), nullable=False, server_default="INALTERADA"),
        sa.Column("revisao", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("modificado_por_id", sa.Uuid(), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("modo IN ('QUIZ_CLASSICO', 'NEM_A_PATO')", name="ck_cat_of_rascunhos_modo"),
        sa.CheckConstraint("tipo_alteracao IN ('INALTERADA', 'MODIFICADA', 'ADICIONADA', 'REMOVIDA')", name="ck_cat_of_rascunhos_alteracao"),
        sa.CheckConstraint("revisao >= 1", name="ck_cat_of_rascunhos_revisao"),
        sa.CheckConstraint("length(trim(slug)) > 0 AND slug = lower(trim(slug))", name="ck_cat_of_rascunhos_slug"),
        sa.CheckConstraint("length(trim(nome)) > 0 AND nome = trim(nome)", name="ck_cat_of_rascunhos_nome"),
        sa.ForeignKeyConstraint(["rascunho_id"], ["catalogos_oficiais_rascunhos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["categoria_id"], ["categorias.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["categoria_versao_origem_id"], ["categorias_oficiais_versoes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["modificado_por_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rascunho_id", "categoria_id", name="uq_cat_of_rascunhos_identidade"),
        sa.UniqueConstraint("rascunho_id", "slug", name="uq_cat_of_rascunhos_slug"),
    )
    op.create_index("ix_cat_of_rascunhos_rascunho", "categorias_oficiais_rascunhos", ["rascunho_id", "tipo_alteracao"])
    op.add_column("alteracoes_rascunhos_oficiais", sa.Column("categoria_rascunho_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_alteracoes_categoria_rascunho", "alteracoes_rascunhos_oficiais", "categorias_oficiais_rascunhos", ["categoria_rascunho_id"], ["id"], ondelete="CASCADE")

    op.add_column("perguntas", sa.Column("categoria_versao_id", sa.Uuid(), nullable=True))
    op.add_column("perguntas_nem_pato", sa.Column("categoria_versao_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_perguntas_categoria_versao", "perguntas", "categorias_oficiais_versoes", ["categoria_versao_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_perguntas_np_categoria_versao", "perguntas_nem_pato", "categorias_oficiais_versoes", ["categoria_versao_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_perguntas_categoria_versao", "perguntas", ["categoria_versao_id"])
    op.create_index("ix_perguntas_np_categoria_versao", "perguntas_nem_pato", ["categoria_versao_id"])

    for tabela in ("partidas", "partida_perguntas", "rodadas_nem_pato"):
        op.add_column(tabela, sa.Column("categoria_slug_snapshot", sa.String(80), nullable=True))
        op.add_column(tabela, sa.Column("categoria_nome_snapshot", sa.String(100), nullable=True))
        op.add_column(tabela, sa.Column("categoria_snapshot_backfill", sa.Boolean(), nullable=False, server_default=sa.false()))

    # UUID determinístico por catálogo/categoria torna o backfill repetível e auditável.
    op.execute("""
        INSERT INTO categorias_oficiais_versoes
            (id, categoria_id, catalogo_oficial_id, modo, slug, nome, descricao, ativa, origem_backfill)
        SELECT (substr(md5(co.id::text || ':' || c.id::text),1,8)||'-'||substr(md5(co.id::text || ':' || c.id::text),9,4)||'-4'||substr(md5(co.id::text || ':' || c.id::text),14,3)||'-a'||substr(md5(co.id::text || ':' || c.id::text),18,3)||'-'||substr(md5(co.id::text || ':' || c.id::text),21,12))::uuid,
               c.id, co.id, co.modo, c.slug, c.nome, c.descricao, c.ativa, true
        FROM catalogos_oficiais co
        JOIN (
            SELECT catalogo_oficial_id, categoria_id FROM perguntas WHERE origem = 'OFICIAL'
            UNION
            SELECT catalogo_oficial_id, categoria_id FROM perguntas_nem_pato WHERE origem = 'OFICIAL'
        ) usados ON usados.catalogo_oficial_id = co.id
        JOIN categorias c ON c.id = usados.categoria_id
    """)
    op.execute("""UPDATE perguntas p SET categoria_versao_id = cv.id FROM categorias_oficiais_versoes cv WHERE p.origem='OFICIAL' AND cv.catalogo_oficial_id=p.catalogo_oficial_id AND cv.categoria_id=p.categoria_id""")
    op.execute("""UPDATE perguntas_nem_pato p SET categoria_versao_id = cv.id FROM categorias_oficiais_versoes cv WHERE p.origem='OFICIAL' AND cv.catalogo_oficial_id=p.catalogo_oficial_id AND cv.categoria_id=p.categoria_id""")
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM perguntas WHERE origem='OFICIAL' AND categoria_versao_id IS NULL)
             OR EXISTS (SELECT 1 FROM perguntas_nem_pato WHERE origem='OFICIAL' AND categoria_versao_id IS NULL) THEN
            RAISE EXCEPTION '0023: pergunta oficial sem catálogo/categoria versionável';
          END IF;
        END $$
    """)
    op.create_check_constraint("ck_perguntas_categoria_versao_origem", "perguntas", "(origem = 'OFICIAL' AND categoria_versao_id IS NOT NULL) OR (origem = 'USUARIO' AND categoria_versao_id IS NULL)")
    op.create_check_constraint("ck_perguntas_np_categoria_versao_origem", "perguntas_nem_pato", "(origem = 'OFICIAL' AND categoria_versao_id IS NOT NULL) OR (origem = 'USUARIO' AND categoria_versao_id IS NULL)")

    op.execute("""
        INSERT INTO categorias_oficiais_rascunhos
            (id, rascunho_id, categoria_id, categoria_versao_origem_id, modo,
             slug, nome, descricao, ativa, tipo_alteracao, revisao, modificado_por_id)
        SELECT (substr(md5(r.id::text || ':' || c.id::text),1,8)||'-'||substr(md5(r.id::text || ':' || c.id::text),9,4)||'-4'||substr(md5(r.id::text || ':' || c.id::text),14,3)||'-b'||substr(md5(r.id::text || ':' || c.id::text),18,3)||'-'||substr(md5(r.id::text || ':' || c.id::text),21,12))::uuid,
               r.id, c.id, cv.id, r.modo, c.slug, c.nome, c.descricao, c.ativa,
               'INALTERADA', 1, r.modificado_por_id
        FROM catalogos_oficiais_rascunhos r
        JOIN (
            SELECT rascunho_id, categoria_id FROM perguntas_quiz_rascunhos
            UNION
            SELECT rascunho_id, categoria_id FROM perguntas_nem_pato_rascunhos
        ) usadas ON usadas.rascunho_id = r.id
        JOIN categorias c ON c.id = usadas.categoria_id
        LEFT JOIN categorias_oficiais_versoes cv
          ON cv.catalogo_oficial_id = r.catalogo_origem_id AND cv.categoria_id = c.id
    """)

    op.execute("""UPDATE partidas p SET categoria_slug_snapshot=c.slug, categoria_nome_snapshot=c.nome, categoria_snapshot_backfill=true FROM categorias c WHERE c.id=p.categoria_id""")
    op.execute("""UPDATE partida_perguntas p SET categoria_slug_snapshot=c.slug, categoria_nome_snapshot=c.nome, categoria_snapshot_backfill=true FROM categorias c WHERE c.id=p.categoria_id_snapshot""")
    op.execute("""UPDATE rodadas_nem_pato r SET categoria_slug_snapshot=c.slug, categoria_nome_snapshot=c.nome, categoria_snapshot_backfill=true FROM categorias c WHERE c.id=r.categoria_id_snapshot""")
    for tabela in ("partidas", "partida_perguntas", "rodadas_nem_pato"):
        op.alter_column(tabela, "categoria_slug_snapshot", nullable=False)
        op.alter_column(tabela, "categoria_nome_snapshot", nullable=False)


def downgrade():
    for tabela in ("rodadas_nem_pato", "partida_perguntas", "partidas"):
        op.drop_column(tabela, "categoria_snapshot_backfill")
        op.drop_column(tabela, "categoria_nome_snapshot")
        op.drop_column(tabela, "categoria_slug_snapshot")
    op.drop_constraint("ck_perguntas_np_categoria_versao_origem", "perguntas_nem_pato", type_="check")
    op.drop_constraint("ck_perguntas_categoria_versao_origem", "perguntas", type_="check")
    op.drop_index("ix_perguntas_np_categoria_versao", table_name="perguntas_nem_pato")
    op.drop_index("ix_perguntas_categoria_versao", table_name="perguntas")
    op.drop_constraint("fk_perguntas_np_categoria_versao", "perguntas_nem_pato", type_="foreignkey")
    op.drop_constraint("fk_perguntas_categoria_versao", "perguntas", type_="foreignkey")
    op.drop_column("perguntas_nem_pato", "categoria_versao_id")
    op.drop_column("perguntas", "categoria_versao_id")
    op.drop_constraint("fk_alteracoes_categoria_rascunho", "alteracoes_rascunhos_oficiais", type_="foreignkey")
    op.drop_column("alteracoes_rascunhos_oficiais", "categoria_rascunho_id")
    op.drop_index("ix_cat_of_rascunhos_rascunho", table_name="categorias_oficiais_rascunhos")
    op.drop_table("categorias_oficiais_rascunhos")
    op.drop_index("ix_cat_of_versoes_identidade", table_name="categorias_oficiais_versoes")
    op.drop_table("categorias_oficiais_versoes")
