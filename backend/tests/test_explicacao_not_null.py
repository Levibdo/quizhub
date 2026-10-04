import importlib.util
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.seed import seed_database
from app.conteudo import CATEGORIAS_OFICIAIS, MODO_QUIZ_CLASSICO
from app.data.perguntas import PERGUNTAS
from app.models import Pergunta
from app.services.backfill_explicacoes import ler_explicacoes


class TestMigration0007(unittest.TestCase):
    def test_upgrade_e_downgrade_somente_nullabilidade(self):
        path = Path(__file__).parents[1] / "alembic/versions/0007_perguntas_explicacao_not_null.py"
        spec = importlib.util.spec_from_file_location("migration_0007", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        self.assertEqual((migration.revision, migration.down_revision), ("0007", "0006"))
        for metodo, sql in (
            (migration.upgrade, "ALTER TABLE perguntas ALTER COLUMN explicacao SET NOT NULL;"),
            (migration.downgrade, "ALTER TABLE perguntas ALTER COLUMN explicacao DROP NOT NULL;"),
        ):
            output = StringIO()
            context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
            with patch.object(migration, "op", Operations(context)):
                metodo()
            self.assertEqual(output.getvalue().strip(), sql)


class TestExplicacaoObrigatoria(unittest.TestCase):
    def test_banco_rejeita_insert_sem_explicacao_e_update_null(self):
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            seed_database(session)
        tabela = Pergunta.__table__
        with self.assertRaises(IntegrityError), engine.begin() as conn:
            conn.execute(tabela.insert().values(
                id=999, categoria_id=CATEGORIAS_OFICIAIS[MODO_QUIZ_CLASSICO]["geral"], enunciado="Teste",
                alternativa_a="A", alternativa_b="B", alternativa_c="C",
                alternativa_d="D", alternativa_correta=0,
            ))
        with self.assertRaises(IntegrityError), engine.begin() as conn:
            conn.execute(tabela.update().where(tabela.c.id == 1).values(explicacao=None))

    def test_seed_preserva_explicacao_existente(self):
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            seed_database(session)
            session.get(Pergunta, 1).explicacao = "Explicacao preservada"
            session.commit()
            antes = session.execute(select(Pergunta.__table__).order_by(Pergunta.id)).all()
            session.commit()
            self.assertEqual(seed_database(session), (0, 0))
            depois = session.execute(select(Pergunta.__table__).order_by(Pergunta.id)).all()
            self.assertEqual(antes, depois)

    def test_explicacoes_seed_iguais_ao_catalogo_oficial(self):
        path = Path(__file__).parents[1] / "dados/perguntas_oficiais_com_explicacoes.xlsx"
        oficial = ler_explicacoes(path.read_bytes())
        for pergunta in PERGUNTAS:
            self.assertEqual(pergunta.explicacao, oficial[(pergunta.categoria, pergunta.pergunta)])
