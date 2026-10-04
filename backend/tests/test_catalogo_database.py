import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Boolean, Column, MetaData, String, Table, Text, create_engine, inspect, select
from sqlalchemy.orm import Session

from app.data.perguntas import PERGUNTAS
from app.db.base import Base
from app.db.seed import CATEGORIAS_INICIAIS, seed_database
from app.conteudo import CATEGORIAS_OFICIAIS, MODO_QUIZ_CLASSICO
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
        self.assertFalse(tabela.c.explicacao.nullable)
        self.assertIsInstance(tabela.c.explicacao.type, Text)
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


class TestMigration0006(unittest.TestCase):
    def setUp(self):
        migration_path = (
            Path(__file__).parents[1]
            / "alembic"
            / "versions"
            / "0006_perguntas_explicacao_nullable.py"
        )
        spec = importlib.util.spec_from_file_location("migration_0006", migration_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)

    def test_upgrade_adiciona_somente_coluna_nullable(self):
        self.assertEqual(self.migration.revision, "0006")
        self.assertEqual(self.migration.down_revision, "0005")
        with patch.object(self.migration.op, "add_column") as add_column:
            self.migration.upgrade()

        add_column.assert_called_once()
        tabela, coluna = add_column.call_args.args
        self.assertEqual(tabela, "perguntas")
        self.assertEqual(coluna.name, "explicacao")
        self.assertIsInstance(coluna.type, Text)
        self.assertTrue(coluna.nullable)
        self.assertIsNone(coluna.default)
        self.assertIsNone(coluna.server_default)

    def test_downgrade_remove_somente_coluna(self):
        with patch.object(self.migration.op, "drop_column") as drop_column:
            self.migration.downgrade()

        drop_column.assert_called_once_with("perguntas", "explicacao")


class TestMigration0008(unittest.TestCase):
    def setUp(self):
        migration_path = Path(__file__).parents[1] / "alembic/versions/0008_categorias_base.py"
        spec = importlib.util.spec_from_file_location("migration_0008", migration_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        self.engine = create_engine("sqlite://")
        metadata = MetaData()
        self.categorias_legadas = Table(
            "categorias", metadata,
            Column("id", String, primary_key=True),
            Column("nome", String, nullable=False),
            Column("descricao", Text),
            Column("ativa", Boolean, nullable=False, server_default="1"),
        )
        metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def executar_upgrade(self, conexao):
        contexto = MigrationContext.configure(conexao)
        with patch.object(self.migration, "op", Operations(contexto)):
            self.migration.upgrade()

    def test_revision_e_downgrade_nao_destrutivo(self):
        self.assertEqual((self.migration.revision, self.migration.down_revision), ("0008", "0007"))
        with patch.object(self.migration.op, "execute") as execute:
            self.migration.downgrade()
        execute.assert_not_called()

    def test_upgrade_cria_quatro_categorias_e_e_idempotente(self):
        with self.engine.begin() as conexao:
            self.executar_upgrade(conexao)
            self.executar_upgrade(conexao)
        with self.engine.connect() as connection:
            categorias = connection.execute(
                select(self.categorias_legadas).order_by(self.categorias_legadas.c.id)
            ).mappings().all()
        self.assertEqual(
            [(item["id"], item["nome"]) for item in categorias],
            [("entretenimento", "Entretenimento"), ("geral", "Geral"),
             ("matematica", "Matemática"), ("tecnologia", "Tecnologia")],
        )

    def test_upgrade_preserva_customizacoes_e_corrige_apenas_legado(self):
        with self.engine.begin() as connection:
            connection.execute(self.categorias_legadas.insert(), [
                dict(id="geral", nome="Conhecimentos", descricao="Personalizada", ativa=False),
                dict(id="matematica", nome="Matematica", descricao="Legada", ativa=False),
                dict(id="tecnologia", nome="Tecnologia Avançada", descricao="Custom", ativa=True),
                dict(id="macabro", nome="Macabro", descricao="Extra", ativa=True),
            ])
        with self.engine.begin() as conexao:
            self.executar_upgrade(conexao)
        with self.engine.connect() as connection:
            dados = {row["id"]: row for row in connection.execute(select(self.categorias_legadas)).mappings()}
            self.assertEqual((dados["geral"]["nome"], dados["geral"]["descricao"], dados["geral"]["ativa"]), ("Conhecimentos", "Personalizada", False))
            self.assertEqual((dados["matematica"]["nome"], dados["matematica"]["descricao"], dados["matematica"]["ativa"]), ("Matemática", "Legada", False))
            self.assertEqual((dados["tecnologia"]["nome"], dados["tecnologia"]["descricao"]), ("Tecnologia Avançada", "Custom"))
            self.assertEqual((dados["macabro"]["nome"], dados["macabro"]["descricao"]), ("Macabro", "Extra"))
            self.assertEqual(dados["entretenimento"]["nome"], "Entretenimento")

    def test_upgrade_preserva_nome_personalizado_de_matematica(self):
        with self.engine.begin() as connection:
            connection.execute(self.categorias_legadas.insert().values(id="matematica", nome="Matemática e Lógica", descricao="Custom"))
        with self.engine.begin() as conexao:
            self.executar_upgrade(conexao)
        with self.engine.connect() as connection:
            categoria = connection.execute(select(self.categorias_legadas).where(self.categorias_legadas.c.id == "matematica")).mappings().one()
            self.assertEqual((categoria["nome"], categoria["descricao"]), ("Matemática e Lógica", "Custom"))


class TestSeed(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_seed_catalog_and_idempotency(self):
        with Session(self.engine) as session:
            self.assertEqual(seed_database(session), (4, 15))
            self.assertEqual(seed_database(session), (0, 0))
            categorias = session.scalars(
                select(Categoria).order_by(Categoria.nome)
            ).all()
            perguntas = session.scalars(select(Pergunta).order_by(Pergunta.id)).all()

        self.assertEqual(len(CATEGORIAS_INICIAIS), 4)
        self.assertEqual(len(categorias), 4)
        self.assertEqual(
            [categoria.nome for categoria in categorias],
            ["Entretenimento", "Geral", "Matemática", "Tecnologia"],
        )
        self.assertEqual([pergunta.id for pergunta in perguntas], list(range(1, 16)))
        self.assertEqual(
            [pergunta.categoria_id for pergunta in perguntas[:5]],
            [CATEGORIAS_OFICIAIS[MODO_QUIZ_CLASSICO]["geral"]] * 5,
        )
        self.assertEqual(
            [pergunta.categoria_id for pergunta in perguntas[5:10]],
            [CATEGORIAS_OFICIAIS[MODO_QUIZ_CLASSICO]["tecnologia"]] * 5,
        )
        self.assertEqual(
            [pergunta.categoria_id for pergunta in perguntas[10:]],
            [CATEGORIAS_OFICIAIS[MODO_QUIZ_CLASSICO]["matematica"]] * 5,
        )

        for persistida, fonte in zip(perguntas, PERGUNTAS, strict=True):
            self.assertEqual(persistida.explicacao, fonte.explicacao)
            self.assertTrue(persistida.explicacao.strip())
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
