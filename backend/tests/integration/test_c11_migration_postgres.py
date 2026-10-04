"""PostgreSQL regression for the reversible 0011 migration cycle."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError


ENV_NAME = "C1_MIGRATION_TEST_DATABASE_URL"
DATABASE_URL = os.getenv(ENV_NAME, "").strip()
EXPECTED_CATEGORY_FKS = {
    "partidas": "partidas_categoria_id_fkey",
    "partidas_nem_pato": "partidas_nem_pato_categoria_id_fkey",
    "perguntas": "perguntas_categoria_id_fkey",
    "perguntas_nem_pato": "perguntas_nem_pato_categoria_id_fkey",
}
EXPECTED_CATEGORY_TABLES = tuple(EXPECTED_CATEGORY_FKS)


@unittest.skipUnless(
    DATABASE_URL,
    f"configure {ENV_NAME} for the disposable C1 migration database",
)
class TestC11MigrationPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parsed = make_url(DATABASE_URL)
        if parsed.get_backend_name() != "postgresql":
            raise RuntimeError(f"{ENV_NAME} must point to PostgreSQL")
        if parsed.database != "quizhub_c11_test_20261004":
            raise RuntimeError("refusing database outside the authorized C1 test database")
        cls.engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        cls.config = Config(str(Path(__file__).parents[2] / "alembic.ini"))

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    @classmethod
    def revision(cls):
        with cls.engine.connect() as connection:
            if connection.scalar(text("SELECT current_database()")) != (
                "quizhub_c11_test_20261004"
            ):
                raise RuntimeError("connected to an unauthorized database")
            return connection.scalar(text("SELECT version_num FROM alembic_version"))

    @classmethod
    def migrate(cls, direction: str, revision: str):
        with patch.dict(os.environ, {"DATABASE_URL": DATABASE_URL}):
            getattr(command, direction)(cls.config, revision)

    def assert_category_fks(self, expected_type: str):
        with self.engine.connect() as connection:
            rows = connection.execute(text("""
                SELECT source.relname AS source_table,
                       constraint_.conname,
                       source_column.attname AS source_column,
                       target.relname AS target_table,
                       target_column.attname AS target_column,
                       format_type(source_column.atttypid, source_column.atttypmod)
                           AS source_type
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
            """)).tuples()
        expected = sorted(
            (
                table,
                EXPECTED_CATEGORY_FKS[table],
                "categoria_id",
                "categorias",
                "id",
                expected_type,
            )
            for table in EXPECTED_CATEGORY_TABLES
        )
        self.assertEqual(list(rows), expected)

    def assert_no_0011_objects(self):
        with self.engine.connect() as connection:
            objects = list(connection.execute(text("""
                SELECT 'relation:' || relation.relkind::text || ':' || relation.relname
                FROM pg_class relation
                JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
                WHERE namespace.nspname = 'public'
                  AND strpos(relation.relname, '_0011') > 0
                UNION ALL
                SELECT 'constraint:' || constraint_.conname
                FROM pg_constraint constraint_
                JOIN pg_namespace namespace
                  ON namespace.oid = constraint_.connamespace
                WHERE namespace.nspname = 'public'
                  AND strpos(constraint_.conname, '_0011') > 0
                ORDER BY 1
            """)).scalars())
        self.assertEqual(objects, [])

    def test_upgrade_downgrade_recria_fks_originais_e_permita_novo_upgrade(self):
        self.assertEqual(self.revision(), "0010")
        self.assert_category_fks("character varying")
        self.assert_no_0011_objects()

        self.migrate("upgrade", "0011")
        self.assertEqual(self.revision(), "0011")
        self.assert_category_fks("uuid")
        self.assert_no_0011_objects()

        with self.engine.connect() as connection:
            category_constraints = set(connection.execute(text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'categorias'::regclass"
            )).scalars())
            category_indexes = set(connection.execute(text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'public' AND tablename = 'categorias'"
            )).scalars())
        self.assertIn("uq_categorias_id_modo_origem", category_constraints)
        self.assertIn("uq_categorias_id_usuario", category_constraints)
        self.assertIn("uq_categorias_usuario_modo_nome", category_indexes)
        self.assertFalse(any("_0011" in name for name in category_constraints))
        self.assertFalse(any("_0011" in name for name in category_indexes))

        with self.engine.connect() as connection:
            outer = connection.begin()
            connection.execute(text(
                "INSERT INTO usuarios (id, nome, email, senha_hash) VALUES "
                "('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'A', "
                "'a-c11@example.com', 'hash'), "
                "('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', 'B', "
                "'b-c11@example.com', 'hash')"
            ))

            def insert_category(category_id, slug, nome, modo, usuario_id):
                connection.execute(text(
                    "INSERT INTO categorias "
                    "(id, slug, nome, modo, origem, usuario_id, ativa) VALUES "
                    "(:id, :slug, :nome, :modo, 'USUARIO', :usuario_id, true)"
                ), {
                    "id": category_id,
                    "slug": slug,
                    "nome": nome,
                    "modo": modo,
                    "usuario_id": usuario_id,
                })

            def assert_rejected(*args):
                savepoint = connection.begin_nested()
                with self.assertRaises(IntegrityError):
                    insert_category(*args)
                savepoint.rollback()

            insert_category(
                "10000000-0000-4000-8000-000000000001",
                "ciencias-a", "Ciências", "QUIZ_CLASSICO",
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            )
            assert_rejected(
                "10000000-0000-4000-8000-000000000002",
                "ciencias-minuscula", "ciências", "QUIZ_CLASSICO",
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            )
            assert_rejected(
                "10000000-0000-4000-8000-000000000003",
                "ciencias-espacos", "  ciências  ", "QUIZ_CLASSICO",
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            )
            insert_category(
                "10000000-0000-4000-8000-000000000004",
                "ciencias-b", "Ciências", "QUIZ_CLASSICO",
                "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            )
            insert_category(
                "10000000-0000-4000-8000-000000000005",
                "ciencias-nem", "Ciências", "NEM_A_PATO",
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            )
            insert_category(
                "10000000-0000-4000-8000-000000000006",
                "cafe-sem-acento", "Cafe", "QUIZ_CLASSICO",
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            )
            insert_category(
                "10000000-0000-4000-8000-000000000007",
                "cafe-com-acento", "Café", "QUIZ_CLASSICO",
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            )
            outer.rollback()

        self.migrate("downgrade", "0010")
        self.assertEqual(self.revision(), "0010")
        self.assert_category_fks("character varying")
        self.assert_no_0011_objects()

        self.migrate("upgrade", "0011")
        self.assertEqual(self.revision(), "0011")
        self.assert_category_fks("uuid")
        self.assert_no_0011_objects()


if __name__ == "__main__":
    unittest.main()
