"""PostgreSQL regression for the complete, reversible 0011 migration cycle."""

import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

URL_ENV = "C1_MIGRATION_TEST_DATABASE_URL"
NAME_ENV = "C1_MIGRATION_TEST_DATABASE_NAME"
DATABASE_URL = os.getenv(URL_ENV, "").strip()
AUTHORIZED_DATABASE = os.getenv(NAME_ENV, "").strip()
AUTHORIZED_NAME = re.compile(r"^quizhub_c11_test_[a-z0-9_]+$")

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
EXPECTED_CATEGORY_FKS = {
    "partidas": "partidas_categoria_id_fkey",
    "partidas_nem_pato": "partidas_nem_pato_categoria_id_fkey",
    "perguntas": "perguntas_categoria_id_fkey",
    "perguntas_nem_pato": "perguntas_nem_pato_categoria_id_fkey",
}
EXPECTED_CATEGORY_CONSTRAINTS = {
    "categorias_pkey", "categorias_usuario_id_fkey",
    "ck_categorias_modo", "ck_categorias_origem",
    "ck_categorias_origem_usuario", "ck_categorias_excluida_inativa",
    "ck_categorias_oficial_nao_excluida",
    "ck_categorias_nome_normalizado", "ck_categorias_slug_normalizado",
    "uq_categorias_id_modo_origem", "uq_categorias_id_usuario",
}
EXPECTED_CATEGORY_INDEXES = {
    "categorias_pkey", "ix_categorias_catalogo",
    "ix_categorias_usuario_modo", "uq_categorias_id_modo_origem",
    "uq_categorias_id_usuario", "uq_categorias_oficial_modo_slug",
    "uq_categorias_usuario_modo_nome",
}


@unittest.skipUnless(
    DATABASE_URL and AUTHORIZED_DATABASE,
    f"configure {URL_ENV} and {NAME_ENV} for an empty disposable database",
)
class TestC11MigrationPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parsed = make_url(DATABASE_URL)
        if parsed.get_backend_name() != "postgresql":
            raise RuntimeError(f"{URL_ENV} must point to PostgreSQL")
        if AUTHORIZED_DATABASE == "quiz_estagio_db":
            raise RuntimeError("refusing the main development database")
        if not AUTHORIZED_NAME.fullmatch(AUTHORIZED_DATABASE):
            raise RuntimeError("temporary database name is not explicitly authorized")
        if parsed.database != AUTHORIZED_DATABASE:
            raise RuntimeError("database URL and authorized name differ")
        cls.engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        cls.config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
        with cls.engine.connect() as connection:
            if connection.scalar(text("SELECT current_database()")) != AUTHORIZED_DATABASE:
                raise RuntimeError("connected to an unauthorized database")
            relations = list(connection.execute(text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' ORDER BY tablename"
            )).scalars())
            application_relations = [
                relation for relation in relations if relation != "alembic_version"
            ]
            if application_relations:
                raise RuntimeError(
                    "C1 migration regression requires an empty database; "
                    f"found={application_relations}"
                )
            if "alembic_version" in relations and connection.scalar(text(
                "SELECT count(*) FROM alembic_version"
            )):
                raise RuntimeError("empty database has an unexpected Alembic revision")
        cls.migrate("upgrade", "0010")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    @classmethod
    def migrate(cls, direction: str, revision: str):
        with patch.dict(os.environ, {"DATABASE_URL": DATABASE_URL}):
            getattr(command, direction)(cls.config, revision)

    @classmethod
    def revision(cls):
        with cls.engine.connect() as connection:
            if connection.scalar(text("SELECT current_database()")) != AUTHORIZED_DATABASE:
                raise RuntimeError("connected to an unauthorized database")
            return connection.scalar(text("SELECT version_num FROM alembic_version"))

    def assert_category_primary_key(self):
        with self.engine.connect() as connection:
            rows = list(connection.execute(text("""
                SELECT source.relname, constraint_.conname, index_.relname
                FROM pg_constraint constraint_
                JOIN pg_class source ON source.oid = constraint_.conrelid
                JOIN pg_class index_ ON index_.oid = constraint_.conindid
                WHERE constraint_.contype = 'p'
                  AND source.relname = 'categorias'
            """)).tuples())
        self.assertEqual(rows, [("categorias", "categorias_pkey", "categorias_pkey")])

    def assert_category_fks(self, expected_type):
        with self.engine.connect() as connection:
            rows = list(connection.execute(text("""
                SELECT source.relname, constraint_.conname,
                       source_column.attname, target.relname,
                       target_column.attname,
                       format_type(source_column.atttypid, source_column.atttypmod)
                FROM pg_constraint constraint_
                JOIN pg_class source ON source.oid = constraint_.conrelid
                JOIN pg_class target ON target.oid = constraint_.confrelid
                JOIN pg_attribute source_column
                  ON source_column.attrelid = source.oid
                 AND source_column.attnum = constraint_.conkey[1]
                JOIN pg_attribute target_column
                  ON target_column.attrelid = target.oid
                 AND target_column.attnum = constraint_.confkey[1]
                WHERE constraint_.contype = 'f'
                  AND source.relname IN
                      ('perguntas', 'partidas', 'perguntas_nem_pato',
                       'partidas_nem_pato')
                  AND source_column.attname = 'categoria_id'
                ORDER BY source.relname
            """)).tuples())
        expected = sorted(
            (table, constraint, "categoria_id", "categorias", "id", expected_type)
            for table, constraint in EXPECTED_CATEGORY_FKS.items()
        )
        self.assertEqual(rows, expected)

    def assert_no_transient_objects(self):
        with self.engine.connect() as connection:
            objects = list(connection.execute(text("""
                SELECT 'relation:' || relation.relkind::text || ':' || relation.relname
                FROM pg_class relation
                JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
                WHERE namespace.nspname = 'public'
                  AND (strpos(relation.relname, '_0010') > 0
                       OR strpos(relation.relname, '_0011') > 0)
                UNION ALL
                SELECT 'constraint:' || constraint_.conname
                FROM pg_constraint constraint_
                JOIN pg_namespace namespace
                  ON namespace.oid = constraint_.connamespace
                WHERE namespace.nspname = 'public'
                  AND (strpos(constraint_.conname, '_0010') > 0
                       OR strpos(constraint_.conname, '_0011') > 0)
                ORDER BY 1
            """)).scalars())
        self.assertEqual(objects, [])

    def assert_0010_structure(self):
        self.assertEqual(self.revision(), "0010")
        self.assert_category_primary_key()
        self.assert_category_fks("character varying")
        self.assert_no_transient_objects()
        with self.engine.connect() as connection:
            column_type = connection.scalar(text("""
                SELECT format_type(atttypid, atttypmod)
                FROM pg_attribute
                WHERE attrelid = 'categorias'::regclass
                  AND attname = 'id' AND NOT attisdropped
            """))
        self.assertEqual(column_type, "character varying")

    def assert_0011_structure(self):
        self.assertEqual(self.revision(), "0011")
        self.assert_category_primary_key()
        self.assert_category_fks("uuid")
        self.assert_no_transient_objects()
        with self.engine.connect() as connection:
            categories = {
                (mode, slug): str(category_id)
                for category_id, slug, mode in connection.execute(text(
                    "SELECT id, slug, modo FROM categorias WHERE origem = 'OFICIAL'"
                ))
            }
            constraints = set(connection.execute(text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'categorias'::regclass"
            )).scalars())
            indexes = set(connection.execute(text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'public' AND tablename = 'categorias'"
            )).scalars())
        self.assertEqual(categories, CATEGORY_IDS)
        self.assertEqual(constraints, EXPECTED_CATEGORY_CONSTRAINTS)
        self.assertEqual(indexes, EXPECTED_CATEGORY_INDEXES)

    def insert_representative_0010_data(self):
        statements = (
            "INSERT INTO usuarios (id,nome,email,senha_hash) VALUES "
            "('10000000-0000-4000-8000-000000000001','Teste C1','c11-migration@example.com','hash')",
            "INSERT INTO jogadores (id,nome,usuario_id) VALUES "
            "('20000000-0000-4000-8000-000000000001','Jogador C1','10000000-0000-4000-8000-000000000001')",
            "INSERT INTO perguntas (id,categoria_id,enunciado,alternativa_a,alternativa_b,alternativa_c,alternativa_d,alternativa_correta,explicacao) VALUES "
            "(9001,'geral','Enunciado clássico preservado','A','B','C','D',2,'Explicação clássica preservada')",
            "INSERT INTO partidas (id,jogador_id,categoria_id) VALUES "
            "('30000000-0000-4000-8000-000000000001','20000000-0000-4000-8000-000000000001','geral')",
            "INSERT INTO partida_perguntas (partida_id,pergunta_id,ordem) VALUES "
            "('30000000-0000-4000-8000-000000000001',9001,1)",
            "INSERT INTO perguntas_nem_pato (id,categoria_id,enunciado,resposta_numerica,unidade,explicacao,fonte) VALUES "
            "(9101,'tecnologia','Enunciado Nem a Pato preservado',42,'unidades','Explicação Nem a Pato preservada','Fonte primária')",
            "INSERT INTO salas_nem_pato (id,codigo,status,estado_versao) VALUES "
            "('40000000-0000-4000-8000-000000000001','C11TESTE','EM_PARTIDA',1)",
            "INSERT INTO participantes_nem_pato (id,sala_id,nome,token_hash,ordem_entrada,eh_anfitriao,status) VALUES "
            "('50000000-0000-4000-8000-000000000001','40000000-0000-4000-8000-000000000001','Host',decode(repeat('00',32),'hex'),1,true,'ATIVO')",
            "INSERT INTO partidas_nem_pato (id,sala_id,categoria_id,numero,status) VALUES "
            "('60000000-0000-4000-8000-000000000001','40000000-0000-4000-8000-000000000001','tecnologia',1,'EM_ANDAMENTO')",
            "INSERT INTO jogadores_partida_nem_pato (id,partida_id,participante_id,nome_snapshot,ordem_circular,status) VALUES "
            "('70000000-0000-4000-8000-000000000001','60000000-0000-4000-8000-000000000001','50000000-0000-4000-8000-000000000001','Host',1,'ATIVO')",
            "INSERT INTO rodadas_nem_pato (partida_id,pergunta_id,numero,status,jogador_inicial_id,jogador_da_vez_id) VALUES "
            "('60000000-0000-4000-8000-000000000001',9101,1,'AGUARDANDO_INICIO','70000000-0000-4000-8000-000000000001','70000000-0000-4000-8000-000000000001')",
        )
        with self.engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))

    def counts(self):
        tables = (
            "categorias", "perguntas", "partidas", "partida_perguntas",
            "perguntas_nem_pato", "partidas_nem_pato", "rodadas_nem_pato",
        )
        with self.engine.connect() as connection:
            return {
                table: connection.scalar(text(f"SELECT count(*) FROM {table}"))
                for table in tables
            }

    def assert_backfills_and_snapshots(self):
        with self.engine.connect() as connection:
            classic = connection.execute(text("""
                SELECT p.categoria_id::text, pp.categoria_id_snapshot::text,
                       pp.enunciado_snapshot, pp.alternativa_correta_snapshot,
                       pp.explicacao_snapshot
                FROM perguntas p JOIN partida_perguntas pp ON pp.pergunta_id=p.id
                WHERE p.id=9001
            """)).one()
            nem = connection.execute(text("""
                SELECT p.categoria_id::text, r.categoria_id_snapshot::text,
                       r.enunciado_snapshot, r.resposta_numerica_snapshot,
                       r.explicacao_snapshot, r.unidade_snapshot, r.fonte_snapshot
                FROM perguntas_nem_pato p
                JOIN rodadas_nem_pato r ON r.pergunta_id=p.id WHERE p.id=9101
            """)).one()
        self.assertEqual(classic, (
            CATEGORY_IDS[("QUIZ_CLASSICO", "geral")],
            CATEGORY_IDS[("QUIZ_CLASSICO", "geral")],
            "Enunciado clássico preservado", 2, "Explicação clássica preservada",
        ))
        self.assertEqual(nem, (
            CATEGORY_IDS[("NEM_A_PATO", "tecnologia")],
            CATEGORY_IDS[("NEM_A_PATO", "tecnologia")],
            "Enunciado Nem a Pato preservado", 42,
            "Explicação Nem a Pato preservada", "unidades", "Fonte primária",
        ))

    def test_real_0010_upgrade_downgrade_and_second_upgrade(self):
        self.assert_0010_structure()
        self.insert_representative_0010_data()
        before = self.counts()

        self.migrate("upgrade", "0011")
        self.assert_0011_structure()
        self.assertEqual(self.counts(), {**before, "categorias": 8})
        self.assert_backfills_and_snapshots()

        with self.engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO usuarios (id,nome,email,senha_hash) VALUES "
                "('10000000-0000-4000-8000-000000000002','Owner','owner-c11@example.com','hash')"
            ))
            connection.execute(text(
                "INSERT INTO categorias (id,slug,nome,modo,origem,usuario_id,ativa) VALUES "
                "('80000000-0000-4000-8000-000000000001','privada','Privada','QUIZ_CLASSICO','USUARIO',"
                "'10000000-0000-4000-8000-000000000002',true)"
            ))
        with self.assertRaises(RuntimeError):
            self.migrate("downgrade", "0010")
        self.assertEqual(self.revision(), "0011")
        with self.engine.begin() as connection:
            connection.execute(text("DELETE FROM categorias WHERE origem='USUARIO'"))
            connection.execute(text("DELETE FROM usuarios WHERE email='owner-c11@example.com'"))

        self.migrate("downgrade", "0010")
        self.assert_0010_structure()
        self.assertEqual(self.counts(), before)

        with self.engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO categorias (id,nome,descricao,ativa) VALUES "
                "('macabro','Macabro','Categoria inesperada',true)"
            ))
        with self.assertRaises(RuntimeError):
            self.migrate("upgrade", "0011")
        self.assert_0010_structure()
        with self.engine.begin() as connection:
            connection.execute(text("DELETE FROM categorias WHERE id='macabro'"))

        self.migrate("upgrade", "0011")
        self.assert_0011_structure()
        self.assertEqual(self.counts(), {**before, "categorias": 8})
        self.assert_backfills_and_snapshots()
        with patch.dict(os.environ, {"DATABASE_URL": DATABASE_URL}):
            command.check(self.config)


if __name__ == "__main__":
    unittest.main()
