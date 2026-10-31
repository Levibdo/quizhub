"""Add persistent editorial review and approval workflow.

Revision ID: 0021
Revises: 0020
"""
from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def _uuid_pk():
    return sa.Column("id", sa.Uuid(), nullable=False)


def upgrade():
    op.create_table(
        "ciclos_revisao_rascunhos", _uuid_pk(),
        sa.Column("rascunho_id", sa.Uuid(), nullable=False),
        sa.Column("revisao_conteudo", sa.Integer(), nullable=False),
        sa.Column("revisao_editorial", sa.Integer(), nullable=False),
        sa.Column("hash_validacao", sa.String(64), nullable=False),
        sa.Column("versao_regras", sa.String(40), nullable=False),
        sa.Column("total_erros", sa.Integer(), nullable=False),
        sa.Column("total_avisos", sa.Integer(), nullable=False),
        sa.Column("total_informacoes", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(16), nullable=False),
        sa.Column("responsavel_id", sa.Uuid(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("concluido_em", sa.DateTime(timezone=True)),
        sa.Column("invalidado_em", sa.DateTime(timezone=True)),
        sa.Column("motivo_invalidacao", sa.Text()),
        sa.CheckConstraint("estado IN ('EM_ANDAMENTO','CONCLUIDO','INVALIDADO')", name="ck_ciclos_revisao_estado"),
        sa.CheckConstraint("revisao_conteudo >= 1 AND revisao_editorial >= 1", name="ck_ciclos_revisao_revisoes"),
        sa.ForeignKeyConstraint(["rascunho_id"], ["catalogos_oficiais_rascunhos.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["responsavel_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ciclos_revisao_rascunho_estado", "ciclos_revisao_rascunhos", ["rascunho_id", "estado"])
    op.create_index("uq_ciclos_revisao_ativo", "ciclos_revisao_rascunhos", ["rascunho_id"], unique=True, postgresql_where=sa.text("estado = 'EM_ANDAMENTO'"))

    op.create_table(
        "achados_validacao_rascunhos", _uuid_pk(),
        sa.Column("ciclo_id", sa.Uuid(), nullable=False), sa.Column("codigo", sa.String(80), nullable=False),
        sa.Column("severidade", sa.String(16), nullable=False), sa.Column("pergunta_id", sa.Uuid()),
        sa.Column("id_editorial", sa.String(80)), sa.Column("campo", sa.String(80)),
        sa.Column("mensagem", sa.Text(), nullable=False), sa.Column("recomendacao", sa.Text()),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.CheckConstraint("severidade IN ('ERRO','AVISO','INFORMACAO')", name="ck_achados_revisao_severidade"),
        sa.ForeignKeyConstraint(["ciclo_id"], ["ciclos_revisao_rascunhos.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("ciclo_id", "fingerprint", name="uq_achados_revisao_fingerprint"),
    )
    op.create_index("ix_achados_validacao_rascunhos_ciclo_id", "achados_validacao_rascunhos", ["ciclo_id"])

    op.create_table(
        "itens_revisao_perguntas", _uuid_pk(), sa.Column("ciclo_id", sa.Uuid(), nullable=False),
        sa.Column("pergunta_quiz_id", sa.Uuid()), sa.Column("pergunta_nem_pato_id", sa.Uuid()),
        sa.Column("id_editorial", sa.String(80), nullable=False), sa.Column("revisao_pergunta", sa.Integer(), nullable=False),
        sa.Column("revisao_editorial", sa.Integer(), nullable=False), sa.Column("estado", sa.String(24), nullable=False),
        sa.Column("revisor_id", sa.Uuid()),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("(pergunta_quiz_id IS NOT NULL) <> (pergunta_nem_pato_id IS NOT NULL)", name="ck_itens_revisao_uma_pergunta"),
        sa.CheckConstraint("estado IN ('PENDENTE','APROVADA','CORRECAO_SOLICITADA','REPROVADA')", name="ck_itens_revisao_estado"),
        sa.CheckConstraint("revisao_pergunta >= 1 AND revisao_editorial >= 1", name="ck_itens_revisao_revisoes"),
        sa.ForeignKeyConstraint(["ciclo_id"], ["ciclos_revisao_rascunhos.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pergunta_quiz_id"], ["perguntas_quiz_rascunhos.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pergunta_nem_pato_id"], ["perguntas_nem_pato_rascunhos.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["revisor_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("ciclo_id", "id_editorial", name="uq_itens_revisao_editorial"),
    )
    op.create_index("ix_itens_revisao_ciclo_estado", "itens_revisao_perguntas", ["ciclo_id", "estado"])

    op.create_table(
        "decisoes_revisao_perguntas", _uuid_pk(), sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("decisao", sa.String(24), nullable=False), sa.Column("justificativa", sa.Text(), nullable=False),
        sa.Column("relacao_fontes_resposta", sa.Text()), sa.Column("responsavel_id", sa.Uuid(), nullable=False),
        sa.Column("revisao_anterior", sa.Integer(), nullable=False), sa.Column("revisao_nova", sa.Integer(), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("decisao IN ('APROVADA','CORRECAO_SOLICITADA','REPROVADA')", name="ck_decisoes_revisao_decisao"),
        sa.ForeignKeyConstraint(["item_id"], ["itens_revisao_perguntas.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["responsavel_id"], ["usuarios.id"], ondelete="RESTRICT"), sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_decisoes_revisao_perguntas_item_id", "decisoes_revisao_perguntas", ["item_id"])

    op.create_table(
        "verificacoes_fontes_revisao", _uuid_pk(), sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("fonte_quiz_id", sa.BigInteger()), sa.Column("fonte_nem_pato_id", sa.BigInteger()),
        sa.Column("fonte_titulo", sa.String(300), nullable=False), sa.Column("fonte_url", sa.Text(), nullable=False),
        sa.Column("fonte_acessada_em", sa.String(10), nullable=False), sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("resultado", sa.String(16), nullable=False), sa.Column("evidencia_documental", sa.Text(), nullable=False),
        sa.Column("relacao_com_resposta", sa.Text()), sa.Column("justificativa", sa.Text()),
        sa.Column("responsavel_id", sa.Uuid(), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("resultado IN ('CONSULTADA','SUFICIENTE','INSUFICIENTE','REJEITADA')", name="ck_verificacoes_fontes_resultado"),
        sa.CheckConstraint("fonte_quiz_id IS NULL OR fonte_nem_pato_id IS NULL", name="ck_verificacoes_fontes_uma_fonte"),
        sa.ForeignKeyConstraint(["item_id"], ["itens_revisao_perguntas.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["fonte_quiz_id"], ["fontes_perguntas_quiz_rascunhos.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["fonte_nem_pato_id"], ["fontes_perguntas_nem_pato_rascunhos.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["responsavel_id"], ["usuarios.id"], ondelete="RESTRICT"), sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_verificacoes_fontes_item_resultado", "verificacoes_fontes_revisao", ["item_id", "resultado"])

    op.create_table(
        "decisoes_avisos_validacao", _uuid_pk(), sa.Column("ciclo_id", sa.Uuid(), nullable=False),
        sa.Column("achado_id", sa.Uuid(), nullable=False), sa.Column("decisao", sa.String(16), nullable=False),
        sa.Column("justificativa", sa.Text(), nullable=False), sa.Column("responsavel_id", sa.Uuid(), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("decisao IN ('ACEITO','REJEITADO')", name="ck_decisoes_avisos_decisao"),
        sa.ForeignKeyConstraint(["ciclo_id"], ["ciclos_revisao_rascunhos.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["achado_id"], ["achados_validacao_rascunhos.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["responsavel_id"], ["usuarios.id"], ondelete="RESTRICT"), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ciclo_id", "achado_id", name="uq_decisoes_avisos_achado"),
    )

    op.create_table(
        "transicoes_rascunhos_editoriais", _uuid_pk(), sa.Column("rascunho_id", sa.Uuid(), nullable=False),
        sa.Column("estado_anterior", sa.String(24), nullable=False), sa.Column("estado_novo", sa.String(24), nullable=False),
        sa.Column("revisao_conteudo", sa.Integer(), nullable=False), sa.Column("justificativa", sa.Text(), nullable=False),
        sa.Column("responsavel_id", sa.Uuid(), nullable=False), sa.Column("operacao", sa.String(80), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["rascunho_id"], ["catalogos_oficiais_rascunhos.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["responsavel_id"], ["usuarios.id"], ondelete="RESTRICT"), sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transicoes_rascunhos_editoriais_rascunho_id", "transicoes_rascunhos_editoriais", ["rascunho_id"])

    op.create_table(
        "aprovacoes_rascunhos", _uuid_pk(), sa.Column("rascunho_id", sa.Uuid(), nullable=False),
        sa.Column("ciclo_id", sa.Uuid(), nullable=False), sa.Column("revisao_conteudo", sa.Integer(), nullable=False),
        sa.Column("hash_validacao", sa.String(64), nullable=False), sa.Column("responsavel_id", sa.Uuid(), nullable=False),
        sa.Column("confirmacao_explicita", sa.Boolean(), nullable=False), sa.Column("autorrevisao", sa.Boolean(), nullable=False),
        sa.Column("justificativa_autorrevisao", sa.Text()),
        sa.Column("criada_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("valida", sa.Boolean(), nullable=False), sa.Column("invalidada_em", sa.DateTime(timezone=True)),
        sa.Column("motivo_invalidacao", sa.Text()),
        sa.CheckConstraint("revisao_conteudo >= 1", name="ck_aprovacoes_revisao"),
        sa.ForeignKeyConstraint(["rascunho_id"], ["catalogos_oficiais_rascunhos.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ciclo_id"], ["ciclos_revisao_rascunhos.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["responsavel_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("ciclo_id", name="uq_aprovacoes_rascunhos_ciclo"),
    )
    op.create_index("ix_aprovacoes_rascunho_valida", "aprovacoes_rascunhos", ["rascunho_id", "valida"])


def downgrade():
    op.drop_index("ix_aprovacoes_rascunho_valida", table_name="aprovacoes_rascunhos")
    op.drop_table("aprovacoes_rascunhos")
    op.drop_index("ix_transicoes_rascunhos_editoriais_rascunho_id", table_name="transicoes_rascunhos_editoriais")
    op.drop_table("transicoes_rascunhos_editoriais")
    op.drop_table("decisoes_avisos_validacao")
    op.drop_index("ix_verificacoes_fontes_item_resultado", table_name="verificacoes_fontes_revisao")
    op.drop_table("verificacoes_fontes_revisao")
    op.drop_index("ix_decisoes_revisao_perguntas_item_id", table_name="decisoes_revisao_perguntas")
    op.drop_table("decisoes_revisao_perguntas")
    op.drop_index("ix_itens_revisao_ciclo_estado", table_name="itens_revisao_perguntas")
    op.drop_table("itens_revisao_perguntas")
    op.drop_index("ix_achados_validacao_rascunhos_ciclo_id", table_name="achados_validacao_rascunhos")
    op.drop_table("achados_validacao_rascunhos")
    op.drop_index("uq_ciclos_revisao_ativo", table_name="ciclos_revisao_rascunhos")
    op.drop_index("ix_ciclos_revisao_rascunho_estado", table_name="ciclos_revisao_rascunhos")
    op.drop_table("ciclos_revisao_rascunhos")
