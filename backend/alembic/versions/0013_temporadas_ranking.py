"""Create ranking seasons and assign legacy matches.

Revision ID: 0013
Revises: 0012
"""

from alembic import op
import sqlalchemy as sa


revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | None = None
depends_on: str | None = None


TEMPORADA_LEGADO_ID = "d67057c4-d943-5a65-86b5-703b8f913b6e"


def upgrade() -> None:
    op.create_table(
        "temporadas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("inicia_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("encerra_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "criada_em", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "atualizada_em", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.CheckConstraint("numero > 0", name="ck_temporadas_numero_positivo"),
        sa.CheckConstraint(
            "status IN ('PLANEJADA', 'ATIVA', 'ENCERRADA')",
            name="ck_temporadas_status",
        ),
        sa.CheckConstraint(
            "encerra_em IS NULL OR encerra_em >= inicia_em",
            name="ck_temporadas_periodo_valido",
        ),
        sa.CheckConstraint(
            "(status = 'ENCERRADA' AND encerra_em IS NOT NULL) OR "
            "(status IN ('PLANEJADA', 'ATIVA') AND encerra_em IS NULL)",
            name="ck_temporadas_encerramento_status",
        ),
        sa.CheckConstraint(
            "length(trim(nome)) > 0 AND nome = trim(nome)",
            name="ck_temporadas_nome_normalizado",
        ),
        sa.PrimaryKeyConstraint("id", name="temporadas_pkey"),
    )
    op.create_index("uq_temporadas_numero", "temporadas", ["numero"], unique=True)
    op.create_index(
        "uq_temporadas_ativa",
        "temporadas",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'ATIVA'"),
    )
    op.add_column("partidas", sa.Column("temporada_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "partidas_temporada_id_fkey",
        "partidas", "temporadas", ["temporada_id"], ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_partidas_temporada_id", "partidas", ["temporada_id"], unique=False
    )
    op.create_index(
        "ix_partidas_temporada_status_categoria",
        "partidas", ["temporada_id", "status", "categoria_id"], unique=False,
    )

    op.execute(sa.text(
        """
        INSERT INTO temporadas (id, numero, nome, status, inicia_em)
        SELECT CAST(:id AS UUID), 1, 'Temporada 1 — Legado', 'ATIVA',
               COALESCE(MIN(iniciada_em), CURRENT_TIMESTAMP)
        FROM partidas
        """
    ).bindparams(id=TEMPORADA_LEGADO_ID))
    op.execute(sa.text(
        "UPDATE partidas SET temporada_id = CAST(:id AS UUID) "
        "WHERE temporada_id IS NULL"
    ).bindparams(id=TEMPORADA_LEGADO_ID))

    # Compatibility window: an older API still omits temporada_id. The trigger
    # assigns the active season and takes a shared row lock that conflicts with
    # the exclusive lock used by a controlled season switch.
    op.execute("""
        CREATE FUNCTION quizhub_partida_temporada_ativa()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.temporada_id IS NULL THEN
                SELECT id INTO NEW.temporada_id
                FROM temporadas
                WHERE status = 'ATIVA'
                FOR SHARE;
                IF NEW.temporada_id IS NULL THEN
                    SELECT id INTO NEW.temporada_id
                    FROM temporadas
                    WHERE status = 'ATIVA'
                    FOR SHARE;
                END IF;
                IF NEW.temporada_id IS NULL THEN
                    RAISE EXCEPTION 'não existe temporada ativa';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_partidas_temporada_ativa
        BEFORE INSERT ON partidas
        FOR EACH ROW
        EXECUTE FUNCTION quizhub_partida_temporada_ativa()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_partidas_temporada_ativa ON partidas")
    op.execute("DROP FUNCTION IF EXISTS quizhub_partida_temporada_ativa()")
    op.drop_index("ix_partidas_temporada_status_categoria", table_name="partidas")
    op.drop_index("ix_partidas_temporada_id", table_name="partidas")
    op.drop_constraint("partidas_temporada_id_fkey", "partidas", type_="foreignkey")
    op.drop_column("partidas", "temporada_id")
    op.drop_index("uq_temporadas_ativa", table_name="temporadas")
    op.drop_index("uq_temporadas_numero", table_name="temporadas")
    op.drop_table("temporadas")
