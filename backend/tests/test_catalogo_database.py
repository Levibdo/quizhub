import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app.data.perguntas import PERGUNTAS
from app.db.base import Base
from app.db.seed import CATEGORIAS_INICIAIS, seed_database
from app.models import Categoria, Pergunta


class TestCatalogoMetadata(unittest.TestCase):
    def test_categoria_columns(self):
        tabela = Base.metadata.tables["categorias"]
        self.assertEqual([column.name for column in tabela.primary_key], ["id"])
        self.assertFalse(tabela.c.nome.nullable)
        self.assertFalse(tabela.c.ativa.nullable)
        self.assertIsNotNone(tabela.c.ativa.server_default)

    def test_pergunta_columns_foreign_key_and_check(self):
        tabela = Base.metadata.tables["perguntas"]
        self.assertEqual([column.name for column in tabela.primary_key], ["id"])
        for nome in (
            "alternativa_a",
            "alternativa_b",
            "alternativa_c",
            "alternativa_d",
            "alternativa_correta",
            "ativa",
            "criada_em",
        ):
            self.assertFalse(tabela.c[nome].nullable)
        self.assertEqual(
            {fk.target_fullname for fk in tabela.c.categoria_id.foreign_keys},
            {"categorias.id"},
        )
        self.assertTrue(tabela.c.criada_em.type.timezone)
        checks = {
            str(constraint.sqltext)
            for constraint in tabela.constraints
            if hasattr(constraint, "sqltext")
        }
        self.assertIn(
            "alternativa_correta >= 0 AND alternativa_correta <= 3", checks
        )


class TestMigration0002(unittest.TestCase):
    def setUp(self):
        migration_path = (
            Path(__file__).parents[1]
            / "alembic"
            / "versions"
            / "0002_categorias_perguntas.py"
        )
        spec = importlib.util.spec_from_file_location("migration_0002", migration_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)

    def test_revision_chain_and_upgrade_scope(self):
        self.assertEqual(self.migration.revision, "0002")
        self.assertEqual(self.migration.down_revision, "0001")
        with patch.object(self.migration.op, "create_table") as create_table:
            self.migration.upgrade()
        self.assertEqual(
            [call.args[0] for call in create_table.call_args_list],
            ["categorias", "perguntas"],
        )

    def test_downgrade_order(self):
        with patch.object(self.migration.op, "drop_table") as drop_table:
            self.migration.downgrade()
        self.assertEqual(
            [call.args[0] for call in drop_table.call_args_list],
            ["perguntas", "categorias"],
        )


class TestSeed(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_seed_catalog_and_idempotency(self):
        with Session(self.engine) as session:
            self.assertEqual(seed_database(session), (3, 15))
            self.assertEqual(seed_database(session), (0, 0))
            categorias = session.scalars(
                select(Categoria).order_by(Categoria.id)
            ).all()
            perguntas = session.scalars(select(Pergunta).order_by(Pergunta.id)).all()

        self.assertEqual(len(CATEGORIAS_INICIAIS), 3)
        self.assertEqual(len(categorias), 3)
        self.assertEqual([pergunta.id for pergunta in perguntas], list(range(1, 16)))
        self.assertEqual(
            [pergunta.categoria_id for pergunta in perguntas[:5]], ["geral"] * 5
        )
        self.assertEqual(
            [pergunta.categoria_id for pergunta in perguntas[5:10]],
            ["tecnologia"] * 5,
        )
        self.assertEqual(
            [pergunta.categoria_id for pergunta in perguntas[10:]],
            ["matematica"] * 5,
        )

        for persistida, fonte in zip(perguntas, PERGUNTAS, strict=True):
            self.assertEqual(persistida.enunciado, fonte.pergunta)
            self.assertEqual(
                (
                    persistida.alternativa_a,
                    persistida.alternativa_b,
                    persistida.alternativa_c,
                    persistida.alternativa_d,
                ),
                fonte.alternativas,
            )
            self.assertEqual(persistida.alternativa_correta, fonte.correta)

    def test_seed_does_not_overwrite_existing_records(self):
        with Session(self.engine) as session:
            seed_database(session)
            pergunta = session.get(Pergunta, 1)
            pergunta.enunciado = "Texto customizado"
            session.commit()
            self.assertEqual(seed_database(session), (0, 0))
            self.assertEqual(
                session.get(Pergunta, 1).enunciado, "Texto customizado"
            )

    def test_database_enforces_correct_answer_range(self):
        constraints = inspect(self.engine).get_check_constraints("perguntas")
        self.assertTrue(
            any("alternativa_correta" in item["sqltext"] for item in constraints)
        )


if __name__ == "__main__":
    unittest.main()
