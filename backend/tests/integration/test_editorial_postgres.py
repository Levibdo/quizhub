"""PostgreSQL regression for the reversible 0013 <-> 0014 editorial migration."""

import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


URL_ENV = "EDITORIAL_TEST_DATABASE_URL"
NAME_ENV = "EDITORIAL_TEST_DATABASE_NAME"
DATABASE_URL = os.getenv(URL_ENV, "").strip()
AUTHORIZED_DATABASE = os.getenv(NAME_ENV, "").strip()
AUTHORIZED_NAME = re.compile(r"^quizhub_editorial_test_[a-z0-9_]+$")
FORBIDDEN_DATABASES = {"quizhub_prod_db", "quiz_estagio_db", "quizhub_loadtest_db"}


@unittest.skipUnless(
    DATABASE_URL and AUTHORIZED_DATABASE,
    f"configure {URL_ENV} and {NAME_ENV} for an empty disposable database",
)
class TestEditorialMigrationPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parsed = make_url(DATABASE_URL)
        if parsed.get_backend_name() != "postgresql":
            raise RuntimeError(f"{URL_ENV} must point to PostgreSQL")
        if AUTHORIZED_DATABASE in FORBIDDEN_DATABASES:
            raise RuntimeError("refusing a persistent QuizHub database")
        if not AUTHORIZED_NAME.fullmatch(AUTHORIZED_DATABASE):
            raise RuntimeError("temporary database name is not explicitly authorized")
        if parsed.database != AUTHORIZED_DATABASE:
            raise RuntimeError("database URL and authorized name differ")
        cls.engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        cls.config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
        with cls.engine.connect() as connection:
            banco_atual = connection.scalar(text("SELECT current_database()"))
            if banco_atual != AUTHORIZED_DATABASE:
                raise RuntimeError("connected to an unauthorized database")
            relations = list(connection.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )).scalars())
            if relations:
                raise RuntimeError(
                    "editorial migration regression requires an empty database"
                )
        cls.migrate("upgrade", "0013")
        cls._insert_legacy_rows()

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    @classmethod
    def migrate(cls, direction, revision):
        with patch.dict(os.environ, {"DATABASE_URL": DATABASE_URL}):
            getattr(command, direction)(cls.config, revision)

    @classmethod
    def revision(cls):
        with cls.engine.connect() as connection:
            return connection.scalar(text("SELECT version_num FROM alembic_version"))

    @classmethod
    def _insert_legacy_rows(cls):
        with cls.engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO usuarios (id, nome, email, senha_hash)
                VALUES ('10000000-0000-4000-8000-000000000014',
                        'Editor', 'editorial-0014@example.com', 'hash')
            """))
            connection.execute(text("""
                INSERT INTO categorias
                    (id, slug, nome, modo, origem, usuario_id, ativa)
                VALUES
                    ('20000000-0000-4000-8000-000000000014', 'privada-editorial',
                     'Privada Editorial', 'QUIZ_CLASSICO', 'USUARIO',
                     '10000000-0000-4000-8000-000000000014', true)
            """))
            connection.execute(text("""
                INSERT INTO perguntas
                    (id, categoria_id, enunciado, alternativa_a, alternativa_b,
                     alternativa_c, alternativa_d, alternativa_correta, explicacao,
                     origem, usuario_id)
                VALUES
                    (14001, '40f40d1f-fa4a-5cc0-9a2f-910bfbf4b4cb',
                     'Oficial legada', 'A', 'B', 'C', 'D', 0, 'Explicação',
                     'OFICIAL', NULL),
                    (14002, '20000000-0000-4000-8000-000000000014',
                     'Privada legada', 'A', 'B', 'C', 'D', 1, 'Explicação',
                     'USUARIO', '10000000-0000-4000-8000-000000000014')
            """))
            connection.execute(text("""
                INSERT INTO perguntas_nem_pato
                    (id, categoria_id, enunciado, resposta_numerica, unidade,
                     explicacao, fonte, origem)
                VALUES
                    (14101, '6cb33fc5-8545-55df-8c46-2e85fc67fe5c',
                     'Nem a Pato legada', 14, 'unidades', 'Explicação',
                     'Fonte textual legada', 'OFICIAL')
            """))

    def test_01_upgrade_preserva_legado_e_adiciona_campos_opcionais(self):
        self.migrate("upgrade", "0014")
        self.assertEqual(self.revision(), "0014")
        with self.engine.begin() as connection:
            colunas = {
                (tabela, coluna): (tipo, anulavel)
                for tabela, coluna, tipo, anulavel in connection.execute(text("""
                    SELECT table_name, column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND ((table_name = 'perguntas' AND column_name = 'dificuldade')
                        OR (table_name = 'perguntas_nem_pato'
                            AND column_name IN ('fonte_url', 'fonte_acessada_em')))
                """))
            }
            self.assertEqual(colunas[("perguntas", "dificuldade")],
                             ("character varying", "YES"))
            self.assertEqual(colunas[("perguntas_nem_pato", "fonte_url")],
                             ("text", "YES"))
            self.assertEqual(colunas[("perguntas_nem_pato", "fonte_acessada_em")],
                             ("date", "YES"))
            self.assertEqual(connection.scalar(text(
                "SELECT count(*) FROM perguntas WHERE id IN (14001, 14002) "
                "AND dificuldade IS NULL"
            )), 2)
            self.assertEqual(connection.scalar(text(
                "SELECT count(*) FROM perguntas_nem_pato WHERE id = 14101 "
                "AND fonte_url IS NULL AND fonte_acessada_em IS NULL"
            )), 1)
            connection.execute(text("""
                INSERT INTO perguntas
                    (id, categoria_id, enunciado, alternativa_a, alternativa_b,
                     alternativa_c, alternativa_d, alternativa_correta, explicacao,
                     origem, usuario_id, dificuldade)
                VALUES
                    (14003, '20000000-0000-4000-8000-000000000014',
                     'Privada nova sem dificuldade obrigatória', 'A', 'B', 'C', 'D',
                     2, 'Explicação', 'USUARIO',
                     '10000000-0000-4000-8000-000000000014', NULL)
            """))

    def test_02_constraint_rejeita_dificuldade_invalida(self):
        with self.assertRaises(Exception):
            with self.engine.begin() as connection:
                connection.execute(text(
                    "UPDATE perguntas SET dificuldade = 'EXTREMA' WHERE id = 14001"
                ))

    def test_03_downgrade_e_reupgrade_preservam_registros(self):
        self.migrate("downgrade", "0013")
        self.assertEqual(self.revision(), "0013")
        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(text(
                "SELECT count(*) FROM perguntas WHERE id IN (14001, 14002, 14003)"
            )), 3)
            self.assertEqual(connection.scalar(text(
                "SELECT count(*) FROM perguntas_nem_pato WHERE id = 14101"
            )), 1)
        self.migrate("upgrade", "0014")
        self.assertEqual(self.revision(), "0014")


if __name__ == "__main__":
    unittest.main()
