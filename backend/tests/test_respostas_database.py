import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    SmallInteger,
    UniqueConstraint,
    Uuid,
    create_engine,
    func,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.seed import seed_database
from app.models import Partida, PartidaPergunta, Pergunta, Resposta


def check_expressions(table):
    return {
        str(constraint.sqltext)
        for constraint in table.constraints
        if hasattr(constraint, "sqltext")
    }


def unique_columns(table):
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


class TestPartidaPerguntaMetadata(unittest.TestCase):
    def test_columns_types_and_nullability(self):
        table = Base.metadata.tables["partida_perguntas"]
        self.assertEqual([column.name for column in table.primary_key], ["id"])
        self.assertIsInstance(table.c.id.type, BigInteger)
        self.assertTrue(table.c.id.autoincrement)
        self.assertIsInstance(table.c.partida_id.type, Uuid)
        self.assertIsInstance(table.c.pergunta_id.type, BigInteger)
        self.assertIsInstance(table.c.ordem.type, SmallInteger)
        for name in ("partida_id", "pergunta_id", "ordem"):
            self.assertFalse(table.c[name].nullable)
        for name in ("disponibilizada_em", "prazo_resposta_em"):
            self.assertTrue(table.c[name].nullable)
            self.assertTrue(table.c[name].type.timezone)

    def test_foreign_keys_uniques_checks_and_index(self):
        table = Base.metadata.tables["partida_perguntas"]
        self.assertEqual(
            {fk.target_fullname for fk in table.c.partida_id.foreign_keys},
            {"partidas.id"},
        )
        self.assertEqual(
            {fk.target_fullname for fk in table.c.pergunta_id.foreign_keys},
            {"perguntas.id"},
        )
        self.assertEqual(
            unique_columns(table),
            {("partida_id", "ordem"), ("partida_id", "pergunta_id")},
        )
        checks = check_expressions(table)
        self.assertIn("ordem >= 1", checks)
        self.assertIn(
            "prazo_resposta_em IS NULL OR disponibilizada_em IS NULL "
            "OR prazo_resposta_em > disponibilizada_em",
            checks,
        )
        self.assertEqual(
            {index.name for index in table.indexes},
            {"ix_partida_perguntas_pergunta_id"},
        )


class TestRespostaMetadata(unittest.TestCase):
    def test_columns_types_nullability_and_defaults(self):
        table = Base.metadata.tables["respostas"]
        self.assertEqual([column.name for column in table.primary_key], ["id"])
        self.assertIsInstance(table.c.id.type, BigInteger)
        self.assertTrue(table.c.id.autoincrement)
        self.assertIsInstance(table.c.partida_pergunta_id.type, BigInteger)
        self.assertFalse(table.c.partida_pergunta_id.nullable)
        self.assertTrue(table.c.alternativa_selecionada.nullable)
        self.assertTrue(table.c.correta.nullable)
        self.assertFalse(table.c.timeout.nullable)
        self.assertFalse(table.c.pontos_ganhos.nullable)
        self.assertFalse(table.c.respondida_em.nullable)
        self.assertTrue(table.c.respondida_em.type.timezone)
        self.assertEqual(str(table.c.timeout.server_default.arg), "false")
        self.assertEqual(str(table.c.pontos_ganhos.server_default.arg), "0")
        self.assertIsNotNone(table.c.respondida_em.server_default)

    def test_foreign_key_unique_and_checks(self):
        table = Base.metadata.tables["respostas"]
        self.assertEqual(
            {fk.target_fullname for fk in table.c.partida_pergunta_id.foreign_keys},
            {"partida_perguntas.id"},
        )
        self.assertEqual(unique_columns(table), {("partida_pergunta_id",)})
        checks = check_expressions(table)
        self.assertIn(
            "alternativa_selecionada IS NULL "
            "OR alternativa_selecionada BETWEEN 0 AND 3",
            checks,
        )
        self.assertIn("pontos_ganhos >= 0", checks)
        self.assertTrue(
            any(
                "timeout = true" in expression and "timeout = false" in expression
                for expression in checks
            )
        )


class TestRelationships(unittest.TestCase):
    def test_match_question_and_answer_relationships(self):
        self.assertIn("perguntas_partida", Partida.__mapper__.relationships)
        self.assertIn("partidas_pergunta", Pergunta.__mapper__.relationships)
        self.assertEqual(
            set(PartidaPergunta.__mapper__.relationships.keys()),
            {"partida", "pergunta", "resposta"},
        )
        self.assertFalse(PartidaPergunta.__mapper__.relationships["resposta"].uselist)
        self.assertEqual(
            set(Resposta.__mapper__.relationships.keys()), {"partida_pergunta"}
        )


class DatabaseConstraintTestCase(unittest.TestCase):
    def create_fixture(self, disponibilizada_em=None, prazo_resposta_em=None):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        partida_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                Base.metadata.tables["categorias"].insert(),
                {"id": "geral", "nome": "Geral", "ativa": True},
            )
            connection.execute(
                Base.metadata.tables["perguntas"].insert(),
                {
                    "id": 1,
                    "categoria_id": "geral",
                    "enunciado": "Pergunta",
                    "alternativa_a": "A",
                    "alternativa_b": "B",
                    "alternativa_c": "C",
                    "alternativa_d": "D",
                    "alternativa_correta": 0,
                    "ativa": True,
                },
            )
            jogador_id = uuid4()
            connection.execute(
                Base.metadata.tables["jogadores"].insert(),
                {"id": jogador_id, "nome": "Jogador"},
            )
            connection.execute(
                Base.metadata.tables["partidas"].insert(),
                {
                    "id": partida_id,
                    "jogador_id": jogador_id,
                    "categoria_id": "geral",
                },
            )
            connection.execute(
                Base.metadata.tables["partida_perguntas"].insert(),
                {
                    "id": 1,
                    "partida_id": partida_id,
                    "pergunta_id": 1,
                    "ordem": 1,
                    "disponibilizada_em": disponibilizada_em,
                    "prazo_resposta_em": prazo_resposta_em,
                },
            )
        return engine


class TestDatabaseCheckSemantics(DatabaseConstraintTestCase):
    def test_temporal_check_accepts_null_or_later_deadline(self):
        now = datetime.now(timezone.utc)
        for available, deadline in (
            (None, None),
            (now, None),
            (None, now),
            (now, now + timedelta(seconds=1)),
        ):
            with self.subTest(available=available, deadline=deadline):
                engine = self.create_fixture(available, deadline)
                engine.dispose()

    def test_temporal_check_rejects_equal_or_earlier_deadline(self):
        now = datetime.now(timezone.utc)
        for deadline in (now, now - timedelta(seconds=1)):
            with self.subTest(deadline=deadline):
                with self.assertRaises(IntegrityError):
                    self.create_fixture(now, deadline)

    def assert_answer_valid(self, **values):
        engine = self.create_fixture()
        with engine.begin() as connection:
            connection.execute(
                Base.metadata.tables["respostas"].insert(),
                {"partida_pergunta_id": 1, **values},
            )
        engine.dispose()

    def assert_answer_invalid(self, **values):
        engine = self.create_fixture()
        with self.assertRaises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    Base.metadata.tables["respostas"].insert(),
                    {"partida_pergunta_id": 1, **values},
                )
        engine.dispose()

    def test_consistency_accepts_normal_and_timeout_answers(self):
        self.assert_answer_valid(
            timeout=False,
            alternativa_selecionada=2,
            correta=True,
            pontos_ganhos=230,
        )
        self.assert_answer_valid(
            timeout=True,
            alternativa_selecionada=None,
            correta=None,
            pontos_ganhos=0,
        )

    def test_consistency_rejects_invalid_timeout_states(self):
        cases = (
            {
                "timeout": True,
                "alternativa_selecionada": 1,
                "correta": None,
                "pontos_ganhos": 0,
            },
            {
                "timeout": True,
                "alternativa_selecionada": None,
                "correta": False,
                "pontos_ganhos": 0,
            },
            {
                "timeout": True,
                "alternativa_selecionada": None,
                "correta": None,
                "pontos_ganhos": 1,
            },
        )
        for values in cases:
            with self.subTest(values=values):
                self.assert_answer_invalid(**values)

    def test_consistency_rejects_incomplete_non_timeout_states(self):
        cases = (
            {
                "timeout": False,
                "alternativa_selecionada": None,
                "correta": False,
                "pontos_ganhos": 0,
            },
            {
                "timeout": False,
                "alternativa_selecionada": 1,
                "correta": None,
                "pontos_ganhos": 0,
            },
        )
        for values in cases:
            with self.subTest(values=values):
                self.assert_answer_invalid(**values)

    def test_alternative_range_and_non_negative_points_are_enforced(self):
        for alternative in (-1, 4):
            with self.subTest(alternative=alternative):
                self.assert_answer_invalid(
                    timeout=False,
                    alternativa_selecionada=alternative,
                    correta=False,
                    pontos_ganhos=0,
                )
        self.assert_answer_invalid(
            timeout=False,
            alternativa_selecionada=0,
            correta=False,
            pontos_ganhos=-1,
        )


class TestMigration0004(unittest.TestCase):
    def setUp(self):
        path = (
            Path(__file__).parents[1]
            / "alembic"
            / "versions"
            / "0004_partida_perguntas_respostas.py"
        )
        spec = importlib.util.spec_from_file_location("migration_0004", path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)

    def test_revision_chain_and_upgrade_scope(self):
        self.assertEqual(self.migration.revision, "0004")
        self.assertEqual(self.migration.down_revision, "0003")
        with (
            patch.object(self.migration.op, "create_table") as create_table,
            patch.object(self.migration.op, "create_index") as create_index,
        ):
            self.migration.upgrade()
        self.assertEqual(
            [call.args[0] for call in create_table.call_args_list],
            ["partida_perguntas", "respostas"],
        )
        create_index.assert_called_once_with(
            "ix_partida_perguntas_pergunta_id",
            "partida_perguntas",
            ["pergunta_id"],
        )

    def test_downgrade_order(self):
        events = []
        with (
            patch.object(
                self.migration.op,
                "drop_index",
                side_effect=lambda *args, **kwargs: events.append(("index", args[0])),
            ),
            patch.object(
                self.migration.op,
                "drop_table",
                side_effect=lambda name: events.append(("table", name)),
            ),
        ):
            self.migration.downgrade()
        self.assertEqual(
            events,
            [
                ("index", "ix_partida_perguntas_pergunta_id"),
                ("table", "respostas"),
                ("table", "partida_perguntas"),
            ],
        )


class TestSeedRegression(unittest.TestCase):
    def test_seed_does_not_create_operational_records(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            self.assertEqual(seed_database(session), (3, 15))
            self.assertEqual(
                session.scalar(select(func.count()).select_from(PartidaPergunta)), 0
            )
            self.assertEqual(session.scalar(select(func.count()).select_from(Resposta)), 0)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
