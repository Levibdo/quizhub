"""Create the user-content foundation and immutable question snapshots.

Revision ID: 0011
Revises: 0010
"""

from alembic import op
import sqlalchemy as sa


revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | None = None
depends_on: str | None = None


LEGACY_SLUGS = ("geral", "tecnologia", "matematica", "entretenimento")
CATEGORY_IDS = {
    ("QUIZ_CLASSICO", "geral"): "40f40d1f-fa4a-5cc0-9a2f-910bfbf4b4cb",
    ("QUIZ_CLASSICO", "tecnologia"): "e534376c-ec51-5304-a42c-cac8d6e34bba",
    ("QUIZ_CLASSICO", "matematica"): "bb9a1050-b3d9-5c42-9cdd-d3747548fc66",
    ("QUIZ_CLASSICO", "entretenimento"): "2a01b416-ae0c-53b4-8081-b5f33230048c",
    ("NEM_A_PATO", "geral"): "6cb33fc5-8545-55df-8c46-2e85fc67fe5c",
    ("NEM_A_PATO", "tecnologia"): "968d29fc-c00f-50c5-9f71-e2d1c53a603d",
    ("NEM_A_PATO", "matematica"): "57036809-591b-54a0-a1ea-b2b815ffea01",
    ("NEM_A_PATO", "entretenimento"): "6feed2ed-5be2-58a8-ad78-37077af2cfca",
}

CATEGORY_CONSTRAINTS = {
    "categorias_0011_pkey": "categorias_pkey",
    "categorias_0011_usuario_id_fkey": "categorias_usuario_id_fkey",
    "ck_categorias_0011_modo": "ck_categorias_modo",
    "ck_categorias_0011_origem": "ck_categorias_origem",
    "ck_categorias_0011_origem_usuario": "ck_categorias_origem_usuario",
    "ck_categorias_0011_excluida_inativa": "ck_categorias_excluida_inativa",
    "ck_categorias_0011_oficial_nao_excluida": "ck_categorias_oficial_nao_excluida",
    "ck_categorias_0011_nome_normalizado": "ck_categorias_nome_normalizado",
    "ck_categorias_0011_slug_normalizado": "ck_categorias_slug_normalizado",
    "uq_categorias_0011_id_modo_origem": "uq_categorias_id_modo_origem",
    "uq_categorias_0011_id_usuario": "uq_categorias_id_usuario",
}


def _require_postgresql() -> None:
    if op.get_bind().dialect.name != "postgresql":
        raise RuntimeError("migration 0011 requires PostgreSQL")


def _preflight_upgrade() -> None:
    bind = op.get_bind()
    found = set(bind.execute(sa.text("SELECT id FROM categorias")).scalars())
    expected = set(LEGACY_SLUGS)
    if found != expected:
        unexpected = sorted(found - expected)
        missing = sorted(expected - found)
        raise RuntimeError(
            "0011 preflight failed: legacy categories differ from the expected "
            f"set; unexpected={unexpected}, missing={missing}"
        )


def _category_case(mode: str, column: str = "categoria_id") -> str:
    clauses = " ".join(
        f"WHEN '{slug}' THEN '{CATEGORY_IDS[(mode, slug)]}'::uuid"
        for slug in LEGACY_SLUGS
    )
    return f"CASE {column} {clauses} END"


def _add_content_columns(table: str, constraint_prefix: str) -> None:
    op.add_column(
        table,
        sa.Column("origem", sa.String(length=16), server_default="OFICIAL", nullable=False),
    )
    op.add_column(table, sa.Column("usuario_id", sa.Uuid(), nullable=True))
    op.add_column(
        table,
        sa.Column(
            "atualizada_em", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.add_column(table, sa.Column("excluida_em", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        f"{table}_usuario_id_fkey", table, "usuarios", ["usuario_id"], ["id"]
    )
    op.create_check_constraint(
        f"ck_{constraint_prefix}_origem", table,
        "origem IN ('OFICIAL', 'USUARIO')",
    )
    op.create_check_constraint(
        f"ck_{constraint_prefix}_origem_usuario", table,
        "(origem = 'OFICIAL' AND usuario_id IS NULL) OR "
        "(origem = 'USUARIO' AND usuario_id IS NOT NULL)",
    )
    op.create_check_constraint(
        f"ck_{constraint_prefix}_excluida_inativa", table,
        "excluida_em IS NULL OR ativa IS FALSE",
    )
    op.create_check_constraint(
        f"ck_{constraint_prefix}_oficial_nao_excluida", table,
        "origem <> 'OFICIAL' OR excluida_em IS NULL",
    )
    op.execute(f"UPDATE {table} SET atualizada_em = criada_em")


def upgrade() -> None:
    _require_postgresql()
    _preflight_upgrade()

    op.create_table(
        "categorias_0011",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("nome", sa.String(length=100), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("modo", sa.String(length=20), nullable=False),
        sa.Column("origem", sa.String(length=16), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=True),
        sa.Column("ativa", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizada_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("excluida_em", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="categorias_0011_pkey"),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"],
            name="categorias_0011_usuario_id_fkey",
        ),
        sa.CheckConstraint("modo IN ('QUIZ_CLASSICO', 'NEM_A_PATO')", name="ck_categorias_0011_modo"),
        sa.CheckConstraint("origem IN ('OFICIAL', 'USUARIO')", name="ck_categorias_0011_origem"),
        sa.CheckConstraint(
            "(origem = 'OFICIAL' AND usuario_id IS NULL) OR "
            "(origem = 'USUARIO' AND usuario_id IS NOT NULL)",
            name="ck_categorias_0011_origem_usuario",
        ),
        sa.CheckConstraint("excluida_em IS NULL OR ativa IS FALSE", name="ck_categorias_0011_excluida_inativa"),
        sa.CheckConstraint("origem <> 'OFICIAL' OR excluida_em IS NULL", name="ck_categorias_0011_oficial_nao_excluida"),
        sa.CheckConstraint("length(trim(nome)) > 0 AND nome = trim(nome)", name="ck_categorias_0011_nome_normalizado"),
        sa.CheckConstraint("length(trim(slug)) > 0 AND slug = lower(trim(slug))", name="ck_categorias_0011_slug_normalizado"),
        sa.UniqueConstraint("id", "modo", "origem", name="uq_categorias_0011_id_modo_origem"),
        sa.UniqueConstraint("id", "usuario_id", name="uq_categorias_0011_id_usuario"),
    )

    bind = op.get_bind()
    legacy = {
        row.id: row
        for row in bind.execute(sa.text(
            "SELECT id, nome, descricao, ativa FROM categorias"
        )).mappings()
    }
    for mode in ("QUIZ_CLASSICO", "NEM_A_PATO"):
        for slug in LEGACY_SLUGS:
            item = legacy[slug]
            bind.execute(
                sa.text(
                    "INSERT INTO categorias_0011 "
                    "(id, slug, nome, descricao, modo, origem, usuario_id, ativa) "
                    "VALUES (:id, :slug, :nome, :descricao, :modo, 'OFICIAL', NULL, :ativa)"
                ),
                dict(
                    id=CATEGORY_IDS[(mode, slug)], slug=slug, nome=item["nome"],
                    descricao=item["descricao"], modo=mode, ativa=item["ativa"],
                ),
            )

    for table in ("perguntas", "partidas", "perguntas_nem_pato", "partidas_nem_pato"):
        op.add_column(table, sa.Column("categoria_uuid", sa.Uuid(), nullable=True))
    op.execute(f"UPDATE perguntas SET categoria_uuid = {_category_case('QUIZ_CLASSICO')}")
    op.execute(f"UPDATE partidas SET categoria_uuid = {_category_case('QUIZ_CLASSICO')}")
    op.execute(f"UPDATE perguntas_nem_pato SET categoria_uuid = {_category_case('NEM_A_PATO')}")
    op.execute(f"UPDATE partidas_nem_pato SET categoria_uuid = {_category_case('NEM_A_PATO')}")
    for table in ("perguntas", "partidas", "perguntas_nem_pato", "partidas_nem_pato"):
        if bind.scalar(sa.text(f"SELECT count(*) FROM {table} WHERE categoria_uuid IS NULL")):
            raise RuntimeError(f"0011 backfill failed: orphan category in {table}")
        op.alter_column(table, "categoria_uuid", nullable=False)
        op.create_foreign_key(
            f"fk_{table}_categoria_0011", table, "categorias_0011",
            ["categoria_uuid"], ["id"],
        )

    _add_content_columns("perguntas", "perguntas")
    _add_content_columns("perguntas_nem_pato", "perguntas_nem_pato")

    for table in ("salas_nem_pato", "partidas_nem_pato"):
        op.add_column(table, sa.Column("catalogo_usuario_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            f"{table}_catalogo_usuario_id_fkey", table, "usuarios",
            ["catalogo_usuario_id"], ["id"],
        )

    classic_snapshots = (
        ("categoria_id_snapshot", sa.Uuid()),
        ("enunciado_snapshot", sa.Text()),
        ("alternativa_a_snapshot", sa.Text()),
        ("alternativa_b_snapshot", sa.Text()),
        ("alternativa_c_snapshot", sa.Text()),
        ("alternativa_d_snapshot", sa.Text()),
        ("alternativa_correta_snapshot", sa.SmallInteger()),
        ("explicacao_snapshot", sa.Text()),
    )
    for name, type_ in classic_snapshots:
        op.add_column("partida_perguntas", sa.Column(name, type_, nullable=True))
    op.execute(
        "UPDATE partida_perguntas pp SET "
        "categoria_id_snapshot = p.categoria_uuid, enunciado_snapshot = p.enunciado, "
        "alternativa_a_snapshot = p.alternativa_a, alternativa_b_snapshot = p.alternativa_b, "
        "alternativa_c_snapshot = p.alternativa_c, alternativa_d_snapshot = p.alternativa_d, "
        "alternativa_correta_snapshot = p.alternativa_correta, explicacao_snapshot = p.explicacao "
        "FROM perguntas p WHERE p.id = pp.pergunta_id"
    )
    for name, type_ in classic_snapshots:
        op.alter_column("partida_perguntas", name, existing_type=type_, nullable=False)

    nem_snapshots = (
        ("categoria_id_snapshot", sa.Uuid()),
        ("enunciado_snapshot", sa.Text()),
        ("resposta_numerica_snapshot", sa.BigInteger()),
        ("explicacao_snapshot", sa.Text()),
        ("unidade_snapshot", sa.String()),
        ("fonte_snapshot", sa.String()),
    )
    for name, type_ in nem_snapshots:
        op.add_column("rodadas_nem_pato", sa.Column(name, type_, nullable=True))
    op.execute(
        "UPDATE rodadas_nem_pato r SET "
        "categoria_id_snapshot = p.categoria_uuid, enunciado_snapshot = p.enunciado, "
        "resposta_numerica_snapshot = p.resposta_numerica, explicacao_snapshot = p.explicacao, "
        "unidade_snapshot = p.unidade, fonte_snapshot = p.fonte "
        "FROM perguntas_nem_pato p WHERE p.id = r.pergunta_id"
    )
    for name, type_ in nem_snapshots[:4]:
        op.alter_column("rodadas_nem_pato", name, existing_type=type_, nullable=False)

    op.drop_index("ix_partidas_categoria_id", table_name="partidas")
    op.drop_index("ix_perguntas_nem_pato_categoria_ativa", table_name="perguntas_nem_pato")
    for table in ("perguntas", "partidas", "perguntas_nem_pato", "partidas_nem_pato"):
        op.drop_constraint(f"{table}_categoria_id_fkey", table, type_="foreignkey")
        op.drop_column(table, "categoria_id")
        op.alter_column(table, "categoria_uuid", new_column_name="categoria_id")
        op.execute(
            f"ALTER TABLE {table} RENAME CONSTRAINT "
            f"fk_{table}_categoria_0011 TO {table}_categoria_id_fkey"
        )
    op.drop_table("categorias")
    op.rename_table("categorias_0011", "categorias")
    for temporary_name, canonical_name in CATEGORY_CONSTRAINTS.items():
        op.execute(
            f"ALTER TABLE categorias RENAME CONSTRAINT "
            f"{temporary_name} TO {canonical_name}"
        )

    op.create_index("ix_partidas_categoria_id", "partidas", ["categoria_id"])
    op.create_index("ix_perguntas_nem_pato_categoria_ativa", "perguntas_nem_pato", ["categoria_id", "ativa"])
    op.create_index("ix_categorias_usuario_modo", "categorias", ["usuario_id", "modo"])
    op.create_index("ix_categorias_catalogo", "categorias", ["modo", "origem", "ativa"])
    op.create_index(
        "uq_categorias_oficial_modo_slug", "categorias", ["modo", "slug"],
        unique=True, postgresql_where=sa.text("origem = 'OFICIAL'"),
    )
    op.create_index(
        "uq_categorias_usuario_modo_nome", "categorias",
        [
            "usuario_id",
            "modo",
            sa.func.lower(sa.func.trim(sa.text("BOTH FROM nome"))),
        ], unique=True,
        postgresql_where=sa.text("origem = 'USUARIO' AND excluida_em IS NULL"),
    )


def _preflight_downgrade() -> None:
    bind = op.get_bind()
    checks = {
        "categorias USUARIO": "SELECT count(*) FROM categorias WHERE origem = 'USUARIO'",
        "perguntas USUARIO": "SELECT count(*) FROM perguntas WHERE origem = 'USUARIO'",
        "perguntas_nem_pato USUARIO": "SELECT count(*) FROM perguntas_nem_pato WHERE origem = 'USUARIO'",
        "salas com catálogo privado": "SELECT count(*) FROM salas_nem_pato WHERE catalogo_usuario_id IS NOT NULL",
        "partidas com catálogo privado": "SELECT count(*) FROM partidas_nem_pato WHERE catalogo_usuario_id IS NOT NULL",
    }
    blocked = [name for name, query in checks.items() if bind.scalar(sa.text(query))]
    if blocked:
        raise RuntimeError(
            "0011 downgrade blocked to preserve C1 data: " + ", ".join(blocked)
        )


def downgrade() -> None:
    _require_postgresql()
    _preflight_downgrade()
    bind = op.get_bind()

    op.create_table(
        "categorias_0010",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("nome", sa.String(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("ativa", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="categorias_0010_pkey"),
    )
    op.execute(
        "INSERT INTO categorias_0010 (id, nome, descricao, ativa) "
        "SELECT slug, nome, descricao, ativa FROM categorias "
        "WHERE modo = 'QUIZ_CLASSICO' AND origem = 'OFICIAL'"
    )
    if bind.scalar(sa.text("SELECT count(*) FROM categorias_0010")) != 4:
        raise RuntimeError("0011 downgrade failed: official classic categories are incomplete")

    for table in ("perguntas", "partidas", "perguntas_nem_pato", "partidas_nem_pato"):
        op.add_column(table, sa.Column("categoria_slug", sa.String(), nullable=True))
        op.execute(
            f"UPDATE {table} t SET categoria_slug = c.slug "
            f"FROM categorias c WHERE c.id = t.categoria_id"
        )
        op.alter_column(table, "categoria_slug", nullable=False)

    op.drop_index("ix_partidas_categoria_id", table_name="partidas")
    op.drop_index("ix_perguntas_nem_pato_categoria_ativa", table_name="perguntas_nem_pato")
    for table in ("perguntas", "partidas", "perguntas_nem_pato", "partidas_nem_pato"):
        op.drop_constraint(f"{table}_categoria_id_fkey", table, type_="foreignkey")
        op.drop_column(table, "categoria_id")
        op.alter_column(table, "categoria_slug", new_column_name="categoria_id")
        op.create_foreign_key(
            f"{table}_categoria_id_fkey", table, "categorias_0010",
            ["categoria_id"], ["id"],
        )
    op.drop_table("categorias")
    op.rename_table("categorias_0010", "categorias")
    op.execute(
        "ALTER TABLE categorias RENAME CONSTRAINT "
        "categorias_0010_pkey TO categorias_pkey"
    )
    op.create_index("ix_partidas_categoria_id", "partidas", ["categoria_id"])
    op.create_index("ix_perguntas_nem_pato_categoria_ativa", "perguntas_nem_pato", ["categoria_id", "ativa"])

    for table in ("salas_nem_pato", "partidas_nem_pato"):
        op.drop_constraint(f"{table}_catalogo_usuario_id_fkey", table, type_="foreignkey")
        op.drop_column(table, "catalogo_usuario_id")

    for table, prefix in (("perguntas", "perguntas"), ("perguntas_nem_pato", "perguntas_nem_pato")):
        op.drop_constraint(f"{table}_usuario_id_fkey", table, type_="foreignkey")
        for suffix in ("origem", "origem_usuario", "excluida_inativa", "oficial_nao_excluida"):
            op.drop_constraint(f"ck_{prefix}_{suffix}", table, type_="check")
        for column in ("excluida_em", "atualizada_em", "usuario_id", "origem"):
            op.drop_column(table, column)

    for column in (
        "explicacao_snapshot", "alternativa_correta_snapshot",
        "alternativa_d_snapshot", "alternativa_c_snapshot",
        "alternativa_b_snapshot", "alternativa_a_snapshot",
        "enunciado_snapshot", "categoria_id_snapshot",
    ):
        op.drop_column("partida_perguntas", column)
    for column in (
        "fonte_snapshot", "unidade_snapshot", "explicacao_snapshot",
        "resposta_numerica_snapshot", "enunciado_snapshot", "categoria_id_snapshot",
    ):
        op.drop_column("rodadas_nem_pato", column)
