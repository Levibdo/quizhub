import importlib
import os
import unittest
from unittest.mock import MagicMock, patch

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.orm import DeclarativeBase

from app.db.base import Base
from app.db import session


class TestDatabaseConfiguration(unittest.TestCase):
    def setUp(self):
        session._engine = None
        session._session_factory = None

    def tearDown(self):
        session._engine = None
        session._session_factory = None

    def test_base_is_sqlalchemy_declarative_base(self):
        self.assertTrue(issubclass(Base, DeclarativeBase))
        self.assertEqual(
            set(Base.metadata.tables),
            {
                "categorias",
                "perguntas",
                "jogadores",
                "partidas",
                "partida_perguntas",
                "respostas",
                "usuarios",
            },
        )

    def test_import_succeeds_without_database_url(self):
        with patch.dict(os.environ, {}, clear=True):
            imported_main = importlib.import_module("app.main")
            self.assertEqual(imported_main.health(), {"status": "ok"})
            self.assertIsNone(session._engine)

    def test_missing_database_url_fails_only_when_engine_is_requested(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL"):
                session.get_engine()

    def test_postgresql_urls_use_psycopg_3_dialect(self):
        cases = {
            "postgres://user:pass@db/quiz": "postgresql+psycopg://user:pass@db/quiz",
            "postgresql://user:pass@db/quiz": "postgresql+psycopg://user:pass@db/quiz",
            "postgresql+psycopg://user:pass@db/quiz": "postgresql+psycopg://user:pass@db/quiz",
        }
        for configured, expected in cases.items():
            with self.subTest(configured=configured):
                with patch.dict(os.environ, {"DATABASE_URL": configured}, clear=True):
                    self.assertEqual(session.get_database_url(), expected)

    def test_engine_and_session_factory_are_lazy_singletons(self):
        fake_engine = MagicMock()
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite://"}, clear=True):
            with patch("app.db.session.create_engine", return_value=fake_engine) as create:
                first_engine = session.get_engine()
                second_engine = session.get_engine()
                first_factory = session.get_session_factory()
                second_factory = session.get_session_factory()

        self.assertIs(first_engine, fake_engine)
        self.assertIs(second_engine, fake_engine)
        self.assertIs(first_factory, second_factory)
        create.assert_called_once_with("sqlite://", pool_pre_ping=True)

    def test_get_db_closes_session(self):
        database = MagicMock()
        factory = MagicMock(return_value=database)
        with patch("app.db.session.get_session_factory", return_value=factory):
            dependency = session.get_db()
            self.assertIs(next(dependency), database)
            dependency.close()

        database.close.assert_called_once_with()

    def test_get_db_closes_session_when_dependency_raises(self):
        database = MagicMock()
        factory = MagicMock(return_value=database)
        with patch("app.db.session.get_session_factory", return_value=factory):
            dependency = session.get_db()
            self.assertIs(next(dependency), database)
            with self.assertRaisesRegex(RuntimeError, "dependency failed"):
                dependency.throw(RuntimeError("dependency failed"))

        database.close.assert_called_once_with()


class TestAlembicConfiguration(unittest.TestCase):
    def test_configuration_and_script_directory_load_without_database(self):
        config = Config("alembic.ini")
        scripts = ScriptDirectory.from_config(config)

        self.assertTrue(scripts.dir.endswith("alembic"))
        revisions = list(scripts.walk_revisions())
        self.assertEqual(
            [revision.revision for revision in revisions],
            ["0005", "0004", "0003", "0002", "0001"],
        )
        self.assertEqual(scripts.get_current_head(), "0005")


if __name__ == "__main__":
    unittest.main()
