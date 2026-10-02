"""Create the persistence foundation for Nem a Pato.

Revision ID: 0009
Revises: 0008
"""

from alembic import op
import sqlalchemy as sa


revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | None = None
depends_on: str | None = None


def _bigint_pk() -> sa.BigInteger:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "perguntas_nem_pato",
        sa.Column("id", _bigint_pk(), autoincrement=True, nullable=False),
        sa.Column("categoria_id", sa.String(), nullable=False),
        sa.Column("enunciado", sa.Text(), nullable=False),
        sa.Column("resposta_numerica", sa.BigInteger(), nullable=False),
        sa.Column("unidade", sa.String(), nullable=True),
        sa.Column("explicacao", sa.Text(), nullable=False),
        sa.Column("fonte", sa.String(), nullable=True),
        sa.Column("ativa", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "criada_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "resposta_numerica >= 0",
            name="ck_perguntas_nem_pato_resposta_nao_negativa",
        ),
        sa.CheckConstraint(
            "length(trim(enunciado)) > 0",
            name="ck_perguntas_nem_pato_enunciado_nao_vazio",
        ),
        sa.ForeignKeyConstraint(["categoria_id"], ["categorias.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_perguntas_nem_pato_categoria_ativa",
        "perguntas_nem_pato",
        ["categoria_id", "ativa"],
    )

    op.create_table(
        "salas_nem_pato",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column(
            "status", sa.String(length=24), server_default=sa.text("'AGUARDANDO'"), nullable=False
        ),
        sa.Column("estado_versao", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "criada_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("encerrada_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('AGUARDANDO', 'EM_PARTIDA', 'ENCERRADA')",
            name="ck_salas_nem_pato_status",
        ),
        sa.CheckConstraint(
            "estado_versao >= 0", name="ck_salas_nem_pato_estado_versao_nao_negativo"
        ),
        sa.CheckConstraint(
            "length(trim(codigo)) > 0", name="ck_salas_nem_pato_codigo_nao_vazio"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("codigo", name="uq_salas_nem_pato_codigo"),
    )

    op.create_table(
        "participantes_nem_pato",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sala_id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.String(length=100), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column("ordem_entrada", sa.SmallInteger(), nullable=False),
        sa.Column("eh_anfitriao", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'ATIVO'"), nullable=False),
        sa.Column(
            "entrou_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("saiu_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('ATIVO', 'ABANDONOU')",
            name="ck_participantes_nem_pato_status",
        ),
        sa.CheckConstraint(
            "ordem_entrada >= 1",
            name="ck_participantes_nem_pato_ordem_entrada_positiva",
        ),
        sa.CheckConstraint(
            "length(trim(nome)) > 0", name="ck_participantes_nem_pato_nome_nao_vazio"
        ),
        sa.CheckConstraint(
            "length(token_hash) = 32",
            name="ck_participantes_nem_pato_token_hash_tamanho",
        ),
        sa.ForeignKeyConstraint(["sala_id"], ["salas_nem_pato.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sala_id", "nome", name="uq_participantes_nem_pato_sala_nome"
        ),
        sa.UniqueConstraint(
            "sala_id", "ordem_entrada", name="uq_participantes_nem_pato_sala_ordem"
        ),
        sa.UniqueConstraint("token_hash", name="uq_participantes_nem_pato_token_hash"),
    )
    op.create_index(
        "ix_participantes_nem_pato_sala_status",
        "participantes_nem_pato",
        ["sala_id", "status"],
    )
    op.create_index(
        "uq_participantes_nem_pato_anfitriao_ativo",
        "participantes_nem_pato",
        ["sala_id"],
        unique=True,
        postgresql_where=sa.text("eh_anfitriao IS TRUE AND status = 'ATIVO'"),
        sqlite_where=sa.text("eh_anfitriao IS TRUE AND status = 'ATIVO'"),
    )

    op.create_table(
        "partidas_nem_pato",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sala_id", sa.Uuid(), nullable=False),
        sa.Column("categoria_id", sa.String(), nullable=False),
        sa.Column("numero", sa.SmallInteger(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'EM_ANDAMENTO'"), nullable=False
        ),
        sa.Column("rodada_atual", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_rodadas", sa.SmallInteger(), server_default=sa.text("10"), nullable=False),
        sa.Column(
            "duracao_rodada_segundos",
            sa.SmallInteger(),
            server_default=sa.text("120"),
            nullable=False,
        ),
        sa.Column(
            "iniciada_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finalizada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_encerramento", sa.String(length=80), nullable=True),
        sa.CheckConstraint(
            "status IN ('EM_ANDAMENTO', 'FINALIZADA', 'CANCELADA')",
            name="ck_partidas_nem_pato_status",
        ),
        sa.CheckConstraint("numero >= 1", name="ck_partidas_nem_pato_numero_positivo"),
        sa.CheckConstraint(
            "total_rodadas = 10", name="ck_partidas_nem_pato_total_rodadas_mvp"
        ),
        sa.CheckConstraint(
            "duracao_rodada_segundos = 120",
            name="ck_partidas_nem_pato_duracao_rodada_mvp",
        ),
        sa.CheckConstraint(
            "rodada_atual >= 0 AND rodada_atual <= total_rodadas",
            name="ck_partidas_nem_pato_rodada_atual_intervalo",
        ),
        sa.ForeignKeyConstraint(["categoria_id"], ["categorias.id"]),
        sa.ForeignKeyConstraint(["sala_id"], ["salas_nem_pato.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sala_id", "numero", name="uq_partidas_nem_pato_sala_numero"),
    )
    op.create_index(
        "uq_partidas_nem_pato_sala_em_andamento",
        "partidas_nem_pato",
        ["sala_id"],
        unique=True,
        postgresql_where=sa.text("status = 'EM_ANDAMENTO'"),
        sqlite_where=sa.text("status = 'EM_ANDAMENTO'"),
    )

    op.create_table(
        "jogadores_partida_nem_pato",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("partida_id", sa.Uuid(), nullable=False),
        sa.Column("participante_id", sa.Uuid(), nullable=False),
        sa.Column("nome_snapshot", sa.String(length=100), nullable=False),
        sa.Column("ordem_circular", sa.SmallInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'ATIVO'"), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("saiu_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('ATIVO', 'ABANDONOU')",
            name="ck_jogadores_partida_nem_pato_status",
        ),
        sa.CheckConstraint(
            "ordem_circular >= 1",
            name="ck_jogadores_partida_nem_pato_ordem_circular_positiva",
        ),
        sa.CheckConstraint(
            "length(trim(nome_snapshot)) > 0",
            name="ck_jogadores_partida_nem_pato_nome_snapshot_nao_vazio",
        ),
        sa.ForeignKeyConstraint(["partida_id"], ["partidas_nem_pato.id"]),
        sa.ForeignKeyConstraint(["participante_id"], ["participantes_nem_pato.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "partida_id",
            "participante_id",
            name="uq_jogadores_partida_nem_pato_partida_participante",
        ),
        sa.UniqueConstraint(
            "partida_id",
            "ordem_circular",
            name="uq_jogadores_partida_nem_pato_partida_ordem",
        ),
    )

    op.create_table(
        "rodadas_nem_pato",
        sa.Column("id", _bigint_pk(), autoincrement=True, nullable=False),
        sa.Column("partida_id", sa.Uuid(), nullable=False),
        sa.Column("pergunta_id", sa.BigInteger(), nullable=False),
        sa.Column("numero", sa.SmallInteger(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'AGUARDANDO_INICIO'"),
            nullable=False,
        ),
        sa.Column("jogador_inicial_id", sa.Uuid(), nullable=False),
        sa.Column("jogador_da_vez_id", sa.Uuid(), nullable=True),
        sa.Column("iniciada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("termina_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalizada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tipo_finalizacao", sa.String(length=24), nullable=True),
        sa.CheckConstraint(
            "status IN ('AGUARDANDO_INICIO', 'EM_ANDAMENTO', 'RESULTADO')",
            name="ck_rodadas_nem_pato_status",
        ),
        sa.CheckConstraint(
            "tipo_finalizacao IS NULL OR tipo_finalizacao IN "
            "('DESAFIO', 'TEMPO_ESGOTADO', 'SEM_PALPITE')",
            name="ck_rodadas_nem_pato_tipo_finalizacao",
        ),
        sa.CheckConstraint(
            "numero BETWEEN 1 AND 10", name="ck_rodadas_nem_pato_numero_intervalo"
        ),
        sa.CheckConstraint(
            "termina_em IS NULL OR iniciada_em IS NULL OR termina_em > iniciada_em",
            name="ck_rodadas_nem_pato_termina_depois_de_iniciada",
        ),
        sa.ForeignKeyConstraint(["partida_id"], ["partidas_nem_pato.id"]),
        sa.ForeignKeyConstraint(["pergunta_id"], ["perguntas_nem_pato.id"]),
        sa.ForeignKeyConstraint(
            ["jogador_inicial_id"], ["jogadores_partida_nem_pato.id"]
        ),
        sa.ForeignKeyConstraint(
            ["jogador_da_vez_id"], ["jogadores_partida_nem_pato.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "partida_id", "numero", name="uq_rodadas_nem_pato_partida_numero"
        ),
        sa.UniqueConstraint(
            "partida_id", "pergunta_id", name="uq_rodadas_nem_pato_partida_pergunta"
        ),
    )

    op.create_table(
        "palpites_nem_pato",
        sa.Column("id", _bigint_pk(), autoincrement=True, nullable=False),
        sa.Column("rodada_id", sa.BigInteger(), nullable=False),
        sa.Column("jogador_partida_id", sa.Uuid(), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("valor", sa.BigInteger(), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("client_action_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("ordem >= 1", name="ck_palpites_nem_pato_ordem_positiva"),
        sa.CheckConstraint(
            "valor >= 0", name="ck_palpites_nem_pato_valor_nao_negativo"
        ),
        sa.ForeignKeyConstraint(["rodada_id"], ["rodadas_nem_pato.id"]),
        sa.ForeignKeyConstraint(
            ["jogador_partida_id"], ["jogadores_partida_nem_pato.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "rodada_id", "ordem", name="uq_palpites_nem_pato_rodada_ordem"
        ),
        sa.UniqueConstraint(
            "rodada_id",
            "client_action_id",
            name="uq_palpites_nem_pato_rodada_client_action",
        ),
    )
    op.create_index(
        "ix_palpites_nem_pato_rodada_ordem",
        "palpites_nem_pato",
        ["rodada_id", "ordem"],
    )


def downgrade() -> None:
    op.drop_table("palpites_nem_pato")
    op.drop_table("rodadas_nem_pato")
    op.drop_table("jogadores_partida_nem_pato")
    op.drop_index(
        "uq_partidas_nem_pato_sala_em_andamento", table_name="partidas_nem_pato"
    )
    op.drop_table("partidas_nem_pato")
    op.drop_index(
        "uq_participantes_nem_pato_anfitriao_ativo",
        table_name="participantes_nem_pato",
    )
    op.drop_index(
        "ix_participantes_nem_pato_sala_status",
        table_name="participantes_nem_pato",
    )
    op.drop_table("participantes_nem_pato")
    op.drop_table("salas_nem_pato")
    op.drop_index(
        "ix_perguntas_nem_pato_categoria_ativa", table_name="perguntas_nem_pato"
    )
    op.drop_table("perguntas_nem_pato")