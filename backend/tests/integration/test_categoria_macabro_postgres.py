"""PostgreSQL regression for the reversible 0015 <-> 0016 data migration."""

import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


URL_ENV = "CATEGORIA_MACABRO_TEST_DATABASE_URL"
NAME_ENV = "CATEGORIA_MACABRO_TEST_DATABASE_NAME"
DATABASE_URL = os.getenv(URL_ENV, "").strip()
AUTHORIZED_DATABASE = os.getenv(NAME_ENV, "").strip()
AUTHORIZED_NAME = re.compile(r"^quizhub_macabro_test_[a-z0-9_]+$")
FORBIDDEN_DATABASES = {"quizhub_prod_db", "quiz_estagio_db", "quizhub_loadtest_db"}
MACABRO_ID = "c73ff198-c1de-5787-b796-c74d2df1b696"


@unittest.skipUnless(
    DATABASE_URL and AUTHORIZED_DATABASE,
    f"configure {URL_ENV} and {NAME_ENV} for an empty disposable database",
)
class TestCategoriaMacabroPostgres(unittest.TestCase):
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
            if connection.scalar(text("SELECT current_database()")) != AUTHORIZED_DATABASE:
                raise RuntimeError("connected to an unauthorized database")
            if connection.scalar(text(
                "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"
            )):
                raise RuntimeError("migration regression requires an empty database")
        cls.migrate("upgrade", "0015")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    @classmethod
    def migrate(cls, direction, revision):
        with patch.dict(os.environ, {"DATABASE_URL": DATABASE_URL}):
            getattr(command, direction)(cls.config, revision)

    def category(self):
        with self.engine.connect() as connection:
            return connection.execute(text(
                "SELECT id::text, slug, nome, modo, origem, usuario_id, ativa, excluida_em "
                "FROM categorias WHERE slug = 'macabro' AND modo = 'NEM_A_PATO'"
            )).mappings().one_or_none()

    def test_01_upgrade_creates_only_expected_category(self):
        with self.engine.connect() as connection:
            before = connection.scalar(text("SELECT count(*) FROM categorias"))
        self.migrate("upgrade", "0016")
        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(text("SELECT version_num FROM alembic_version")), "0016")
            self.assertEqual(connection.scalar(text("SELECT count(*) FROM categorias")), before + 1)
        row = self.category()
        self.assertEqual(row["id"], MACABRO_ID)
        self.assertEqual((row["slug"], row["nome"], row["modo"], row["origem"]),
                         ("macabro", "Macabro", "NEM_A_PATO", "OFICIAL"))
        self.assertIsNone(row["usuario_id"])
        self.assertTrue(row["ativa"])
        self.assertIsNone(row["excluida_em"])

    def test_02_downgrade_and_reupgrade_are_reversible_when_unused(self):
        self.migrate("downgrade", "0015")
        self.assertIsNone(self.category())
        self.migrate("upgrade", "0016")
        self.assertIsNotNone(self.category())


if __name__ == "__main__":
    unittest.main()
