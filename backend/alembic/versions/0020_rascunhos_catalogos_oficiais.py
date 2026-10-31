"""Add isolated editable drafts for official catalogs.

Revision ID: 0020
Revises: 0019
"""

from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def _common_question_columns():
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rascunho_id", sa.Uuid(), nullable=False),
        sa.Column("pergunta_origem_id", sa.BigInteger(), nullable=True),
        sa.Column("id_editorial", sa.String(80), nullable=False),
        sa.Column("categoria_id", sa.Uuid(), nullable=False),
        sa.Column("categoria_slug_snapshot", sa.String(80), nullable=False),
        sa.Column("categoria_nome_snapshot", sa.String(100), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("enunciado", sa.Text(), nullable=False),
        sa.Column("explicacao", sa.Text(), nullable=False),
        sa.Column("ativa", sa.Boolean(), nullable=False),
        sa.Column("tipo_alteracao", sa.String(16), nullable=False),
        sa.Column("revisao", sa.Integer(), nullable=False),
        sa.Column("modificado_por_id", sa.Uuid(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade():
    op.create_table(
        "catalogos_oficiais_rascunhos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("catalogo_origem_id", sa.Uuid(), nullable=False),
        sa.Column("catalogo_id", sa.String(80), nullable=False),
        sa.Column("modo", sa.String(20), nullable=False),
        sa.Column("versao_base", sa.Integer(), nullable=False),
        sa.Column("numero_rascunho", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(160), nullable=False),
        sa.Column("status", sa.String(24), server_default="EM_EDICAO", nullable=False),
        sa.Column("revisao", sa.Integer(), server_default="1", nullable=False),
        sa.Column("criado_por_id", sa.Uuid(), nullable=False),
        sa.Column("modificado_por_id", sa.Uuid(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("descartado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_descarte", sa.Text(), nullable=True),
        sa.CheckConstraint("modo IN ('QUIZ_CLASSICO', 'NEM_A_PATO')", name="ck_catalogos_rascunhos_modo"),
        sa.CheckConstraint("status IN ('EM_EDICAO', 'EM_VALIDACAO', 'EM_REVISAO', 'APROVADO', 'DESCARTADO', 'PUBLICADO')", name="ck_catalogos_rascunhos_status"),
        sa.CheckConstraint("versao_base >= 1", name="ck_catalogos_rascunhos_versao_base"),
        sa.CheckConstraint("numero_rascunho >= 1", name="ck_catalogos_rascunhos_numero"),
        sa.CheckConstraint("revisao >= 1", name="ck_catalogos_rascunhos_revisao"),
        sa.CheckConstraint("(status = 'DESCARTADO' AND descartado_em IS NOT NULL) OR (status <> 'DESCARTADO' AND descartado_em IS NULL)", name="ck_catalogos_rascunhos_descarte"),
        sa.ForeignKeyConstraint(["catalogo_origem_id"], ["catalogos_oficiais.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["criado_por_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["modificado_por_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("catalogo_id", "numero_rascunho", name="uq_catalogos_rascunhos_numero"),
    )
    op.create_index("ix_catalogos_rascunhos_origem_status", "catalogos_oficiais_rascunhos", ["catalogo_origem_id", "status"])
    op.create_index("ix_catalogos_rascunhos_status_atualizado", "catalogos_oficiais_rascunhos", ["status", "atualizado_em"])

    op.create_table(
        "perguntas_quiz_rascunhos",
        *_common_question_columns(),
        sa.Column("alternativa_a", sa.Text(), nullable=False), sa.Column("alternativa_b", sa.Text(), nullable=False),
        sa.Column("alternativa_c", sa.Text(), nullable=False), sa.Column("alternativa_d", sa.Text(), nullable=False),
        sa.Column("alternativa_correta", sa.SmallInteger(), nullable=False),
        sa.Column("dificuldade", sa.String(8), nullable=False),
        sa.CheckConstraint("alternativa_correta BETWEEN 0 AND 3", name="ck_perguntas_quiz_rascunhos_gabarito"),
        sa.CheckConstraint("dificuldade IN ('FACIL', 'MEDIA', 'DIFICIL')", name="ck_perguntas_quiz_rascunhos_dificuldade"),
        sa.CheckConstraint("tipo_alteracao IN ('INALTERADA', 'MODIFICADA', 'ADICIONADA', 'REMOVIDA')", name="ck_perguntas_quiz_rascunhos_alteracao"),
        sa.CheckConstraint("revisao >= 1", name="ck_perguntas_quiz_rascunhos_revisao"),
        sa.ForeignKeyConstraint(["rascunho_id"], ["catalogos_oficiais_rascunhos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pergunta_origem_id"], ["perguntas.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["categoria_id"], ["categorias.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["modificado_por_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rascunho_id", "id_editorial", name="uq_perguntas_quiz_rascunhos_editorial"),
        sa.UniqueConstraint("rascunho_id", "ordem", name="uq_perguntas_quiz_rascunhos_ordem"),
    )
    op.create_index("ix_perguntas_quiz_rascunhos_categoria", "perguntas_quiz_rascunhos", ["rascunho_id", "categoria_id"])

    op.create_table(
        "perguntas_nem_pato_rascunhos",
        *_common_question_columns(),
        sa.Column("resposta_numerica", sa.BigInteger(), nullable=False),
        sa.Column("unidade", sa.String(), nullable=True), sa.Column("fonte", sa.String(), nullable=True),
        sa.Column("fonte_url", sa.Text(), nullable=True), sa.Column("fonte_acessada_em", sa.Date(), nullable=True),
        sa.Column("tema_editorial", sa.String(100), nullable=True),
        sa.Column("natureza_resposta", sa.String(16), nullable=False),
        sa.Column("qualificacao_estimativa", sa.Text(), nullable=True),
        sa.CheckConstraint("resposta_numerica >= 0", name="ck_perguntas_np_rascunhos_resposta"),
        sa.CheckConstraint("natureza_resposta IN ('EXATA', 'ESTIMATIVA')", name="ck_perguntas_np_rascunhos_natureza"),
        sa.CheckConstraint("tipo_alteracao IN ('INALTERADA', 'MODIFICADA', 'ADICIONADA', 'REMOVIDA')", name="ck_perguntas_np_rascunhos_alteracao"),
        sa.CheckConstraint("revisao >= 1", name="ck_perguntas_np_rascunhos_revisao"),
        sa.ForeignKeyConstraint(["rascunho_id"], ["catalogos_oficiais_rascunhos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pergunta_origem_id"], ["perguntas_nem_pato.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["categoria_id"], ["categorias.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["modificado_por_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rascunho_id", "id_editorial", name="uq_perguntas_np_rascunhos_editorial"),
        sa.UniqueConstraint("rascunho_id", "ordem", name="uq_perguntas_np_rascunhos_ordem"),
    )
    op.create_index("ix_perguntas_np_rascunhos_categoria", "perguntas_nem_pato_rascunhos", ["rascunho_id", "categoria_id"])

    for tabela, pergunta, uq in (("fontes_perguntas_quiz_rascunhos", "perguntas_quiz_rascunhos", "uq_fontes_quiz_rascunhos_ordem"), ("fontes_perguntas_nem_pato_rascunhos", "perguntas_nem_pato_rascunhos", "uq_fontes_np_rascunhos_ordem")):
        op.create_table(tabela, sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False), sa.Column("pergunta_rascunho_id", sa.Uuid(), nullable=False), sa.Column("ordem", sa.Integer(), nullable=False), sa.Column("titulo", sa.String(300), nullable=False), sa.Column("url", sa.Text(), nullable=False), sa.Column("acessada_em", sa.Date(), nullable=False), sa.ForeignKeyConstraint(["pergunta_rascunho_id"], [f"{pergunta}.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("pergunta_rascunho_id", "ordem", name=uq))
        op.create_index(f"ix_{tabela}_pergunta_rascunho_id", tabela, ["pergunta_rascunho_id"])

    op.create_table(
        "alteracoes_rascunhos_oficiais",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("rascunho_id", sa.Uuid(), nullable=False),
        sa.Column("pergunta_quiz_rascunho_id", sa.Uuid(), nullable=True),
        sa.Column("pergunta_nem_pato_rascunho_id", sa.Uuid(), nullable=True),
        sa.Column("administrador_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.String(16), nullable=False), sa.Column("id_editorial", sa.String(80), nullable=True),
        sa.Column("revisao_anterior", sa.Integer(), nullable=True), sa.Column("revisao_nova", sa.Integer(), nullable=False),
        sa.Column("campos_alterados", sa.JSON(), nullable=True), sa.Column("ocorrida_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("tipo IN ('CRIACAO', 'EDICAO', 'ADICAO', 'REMOCAO', 'RESTAURACAO', 'DESCARTE')", name="ck_alteracoes_rascunhos_tipo"),
        sa.CheckConstraint("NOT (pergunta_quiz_rascunho_id IS NOT NULL AND pergunta_nem_pato_rascunho_id IS NOT NULL)", name="ck_alteracoes_rascunhos_uma_pergunta"),
        sa.ForeignKeyConstraint(["rascunho_id"], ["catalogos_oficiais_rascunhos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pergunta_quiz_rascunho_id"], ["perguntas_quiz_rascunhos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pergunta_nem_pato_rascunho_id"], ["perguntas_nem_pato_rascunhos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["administrador_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alteracoes_rascunhos_rascunho_data", "alteracoes_rascunhos_oficiais", ["rascunho_id", "ocorrida_em"])


def downgrade():
    op.drop_index("ix_alteracoes_rascunhos_rascunho_data", table_name="alteracoes_rascunhos_oficiais")
    op.drop_table("alteracoes_rascunhos_oficiais")
    for tabela in ("fontes_perguntas_nem_pato_rascunhos", "fontes_perguntas_quiz_rascunhos"):
        op.drop_index(f"ix_{tabela}_pergunta_rascunho_id", table_name=tabela)
        op.drop_table(tabela)
    op.drop_index("ix_perguntas_np_rascunhos_categoria", table_name="perguntas_nem_pato_rascunhos")
    op.drop_table("perguntas_nem_pato_rascunhos")
    op.drop_index("ix_perguntas_quiz_rascunhos_categoria", table_name="perguntas_quiz_rascunhos")
    op.drop_table("perguntas_quiz_rascunhos")
    op.drop_index("ix_catalogos_rascunhos_status_atualizado", table_name="catalogos_oficiais_rascunhos")
    op.drop_index("ix_catalogos_rascunhos_origem_status", table_name="catalogos_oficiais_rascunhos")
    op.drop_table("catalogos_oficiais_rascunhos")
