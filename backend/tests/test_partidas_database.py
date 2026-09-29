import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from sqlalchemy import UniqueConstraint, Uuid, create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import Jogador


def check_expressions(table):
    return {
        str(constraint.sqltext)
        for constraint in table.constraints
        if hasattr(constraint, "sqltext")
    }


class TestJogadorMetadata(unittest.TestCase):
    def test_columns_primary_key_uuid_and_timestamp(self):
        table = Base.metadata.tables["jogadores"]
        self.assertEqual([column.name for column in table.primary_key], ["id"])
        self.assertIsInstance(table.c.id.type, Uuid)
        self.assertTrue(table.c.id.type.native_uuid)
        self.assertFalse(table.c.nome.nullable)
        self.assertFalse(table.c.criado_em.nullable)
        self.assertTrue(table.c.criado_em.type.timezone)
        self.assertIsNotNone(table.c.criado_em.server_default)

    def test_name_is_not_unique_and_duplicate_names_can_be_stored(self):
        table = Base.metadata.tables["jogadores"]
        self.assertFalse(table.c.nome.unique)
        self.assertFalse(
            any(
                isinstance(constraint, UniqueConstraint)
                and "nome" in constraint.columns
                for constraint in table.constraints
            )
        )

        engine = create_engine("sqlite://")
        table.create(engine)
        with Session(engine) as session:
            first = Jogador(nome="João")
            second = Jogador(nome="João")
            session.add_all([first, second])
            session.commit()
            self.assertNotEqual(first.id, second.id)
            self.assertIsInstance(first.id, UUID)
        engine.dispose()


class TestPartidaMetadata(unittest.TestCase):
    def test_columns_types_nullability_and_defaults(self):
        table = Base.metadata.tables["partidas"]
        self.assertEqual([column.name for column in table.primary_key], ["id"])
        self.assertIsInstance(table.c.id.type, Uuid)
        self.assertIsInstance(table.c.jogador_id.type, Uuid)
        for name in (
            "jogador_id",
            "categoria_id",
            "status",
            "pontuacao",
            "acertos",
            "erros",
            "iniciada_em",
        ):
            self.assertFalse(table.c[name].nullable)
        self.assertTrue(table.c.finalizada_em.nullable)
        self.assertTrue(table.c.iniciada_em.type.timezone)
        self.assertTrue(table.c.finalizada_em.type.timezone)
        self.assertIsNotNone(table.c.iniciada_em.server_default)
        self.assertEqual(str(table.c.status.server_default.arg), "'EM_ANDAMENTO'")
        for name in ("pontuacao", "acertos", "erros"):
            self.assertEqual(str(table.c[name].server_default.arg), "0")

    def test_foreign_keys_checks_and_indexes(self):
        table = Base.metadata.tables["partidas"]
        self.assertEqual(
            {fk.target_fullname for fk in table.c.jogador_id.foreign_keys},
            {"jogadores.id"},
        )
        self.assertEqual(
            {fk.target_fullname for fk in table.c.categoria_id.foreign_keys},
            {"categorias.id"},
        )
        self.assertEqual(
            check_expressions(table),
            {
                "status IN ('EM_ANDAMENTO', 'FINALIZADA', 'EXPIRADA')",
                "pontuacao >= 0",
                "acertos >= 0",
                "erros >= 0",
            },
        )
        self.assertEqual(
            {index.name for index in table.indexes},
            {
                "ix_partidas_jogador_id",
                "ix_partidas_categoria_id",
                "ix_partidas_status",
            },
        )

    def test_relationships(self):
        self.assertEqual(
            set(Jogador.__mapper__.relationships.keys()),
            {"partidas", "usuario"},
        )
        categoria = Base.registry._class_registry["Categoria"]
        partida = Base.registry._class_registry["Partida"]
        self.assertEqual(
            set(categoria.__mapper__.relationships.keys()), {"perguntas", "partidas"}
        )
        self.assertEqual(
            set(partida.__mapper__.relationships.keys()),
            {"jogador", "categoria", "perguntas_partida"},
        )


class TestMigration0003(unittest.TestCase):
    def setUp(self):
        path = (
            Path(__file__).parents[1]
            / "alembic"
            / "versions"
            / "0003_jogadores_partidas.py"
        )
        spec = importlib.util.spec_from_file_location("migration_0003", path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)

    def test_revision_chain_and_upgrade_scope(self):
        self.assertEqual(self.migration.revision, "0003")
        self.assertEqual(self.migration.down_revision, "0002")
        with (
            patch.object(self.migration.op, "create_table") as create_table,
            patch.object(self.migration.op, "create_index") as create_index,
        ):
            self.migration.upgrade()
        self.assertEqual(
            [call.args[0] for call in create_table.call_args_list],
            ["jogadores", "partidas"],
        )
        self.assertEqual(create_index.call_count, 3)

    def test_downgrade_table_order(self):
        with (
            patch.object(self.migration.op, "drop_index"),
            patch.object(self.migration.op, "drop_table") as drop_table,
        ):
            self.migration.downgrade()
        self.assertEqual(
            [call.args[0] for call in drop_table.call_args_list],
            ["partidas", "jogadores"],
        )


if __name__ == "__main__":
    unittest.main()
