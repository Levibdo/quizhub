"""Real PostgreSQL coverage for the global Classic ranking.

The database must be disposable, explicitly named through both environment
variables, and migrated through the current head before this module runs.
"""

import os
import unittest
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.db.base import Base  # noqa: F401
from app.models import Categoria, Jogador, Partida, Usuario
from app.services.ranking import RankingService


URL_ENV = "RANKING_TEST_DATABASE_URL"
NAME_ENV = "RANKING_TEST_DATABASE_NAME"
FORBIDDEN_DATABASES = {
    "quizhub_prod_db",
    "quiz_estagio_db",
    "quizhub_loadtest_db",
}


class TestRankingPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database_url = os.getenv(URL_ENV, "").strip()
        expected_name = os.getenv(NAME_ENV, "").strip()
        if not database_url or not expected_name:
            raise unittest.SkipTest(
                f"configure {URL_ENV} and {NAME_ENV} for ranking PostgreSQL tests"
            )
        configured_name = make_url(database_url).database
        if (
            configured_name != expected_name
            or "_test_" not in expected_name
            or expected_name in FORBIDDEN_DATABASES
        ):
            raise RuntimeError("ranking tests require an explicitly named disposable database")

        cls.engine = create_engine(database_url, pool_pre_ping=True)
        with cls.engine.connect() as connection:
            current_name = connection.scalar(text("SELECT current_database()"))
            revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        if current_name != expected_name:
            cls.engine.dispose()
            raise RuntimeError(
                f"connected to {current_name!r}, expected disposable database {expected_name!r}"
            )
        if revision != "0012":
            cls.engine.dispose()
            raise RuntimeError(f"expected revision 0012, received {revision!r}")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()
        self.session = Session(bind=self.connection, expire_on_commit=False)
        self.service = RankingService()
        self.now = datetime(2026, 10, 12, 18, 0, tzinfo=timezone.utc)
        self.general = self.session.scalar(select(Categoria).where(
            Categoria.slug == "geral",
            Categoria.modo == "QUIZ_CLASSICO",
            Categoria.origem == "OFICIAL",
        ))
        self.technology = self.session.scalar(select(Categoria).where(
            Categoria.slug == "tecnologia",
            Categoria.modo == "QUIZ_CLASSICO",
            Categoria.origem == "OFICIAL",
        ))
        self.nem_pato = self.session.scalar(select(Categoria).where(
            Categoria.slug == "geral",
            Categoria.modo == "NEM_A_PATO",
            Categoria.origem == "OFICIAL",
        ))
        self.assertIsNotNone(self.general)
        self.assertIsNotNone(self.technology)
        self.assertIsNotNone(self.nem_pato)

    def tearDown(self):
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def add_match(
        self,
        *,
        name,
        score,
        hits,
        category=None,
        status="FINALIZADA",
        finished_at=None,
        user_id=None,
        visitor_id=None,
        match_id=None,
    ):
        player = Jogador(
            nome=name,
            usuario_id=user_id,
            visitante_id=visitor_id,
        )
        self.session.add(player)
        self.session.flush()
        match = Partida(
            id=match_id or uuid4(),
            jogador_id=player.id,
            categoria_id=(category or self.general).id,
            status=status,
            pontuacao=score,
            acertos=hits,
            erros=max(0, 10 - hits),
            iniciada_em=self.now - timedelta(minutes=4),
            finalizada_em=(self.now if finished_at is None else finished_at),
        )
        self.session.add(match)
        self.session.flush()
        return match

    def test_window_identity_filters_ties_and_limit(self):
        account = Usuario(
            nome="Conta",
            email=f"ranking-{uuid4()}@example.com",
            senha_hash="hash-de-teste",
        )
        self.session.add(account)
        self.session.flush()
        private = Categoria(
            id=uuid4(),
            slug=f"privada-{uuid4().hex[:8]}",
            nome="Categoria privada",
            modo="QUIZ_CLASSICO",
            origem="USUARIO",
            usuario_id=account.id,
            ativa=True,
        )
        self.session.add(private)
        self.session.flush()

        self.add_match(name="Conta antiga", score=800, hits=6, user_id=account.id)
        self.add_match(name="Conta", score=1600, hits=9, user_id=account.id)
        stable_guest = uuid4()
        self.add_match(name="Visitante", score=900, hits=6, visitor_id=stable_guest)
        self.add_match(name="Visitante", score=1400, hits=8, visitor_id=stable_guest)
        self.add_match(name="Mesmo nome", score=1300, hits=8, visitor_id=uuid4())
        self.add_match(name="Mesmo nome", score=1200, hits=8, visitor_id=uuid4())
        self.add_match(name="Legado", score=1100, hits=7)
        self.add_match(name="Legado", score=1000, hits=7)
        self.add_match(name="Em andamento", score=9999, hits=10, status="EM_ANDAMENTO")
        self.add_match(name="Privado", score=9998, hits=10, category=private)
        self.add_match(name="Nem a Pato", score=9997, hits=10, category=self.nem_pato)
        null_finished = self.add_match(
            name="Sem horário", score=700, hits=5,
            match_id=UUID(int=200),
        )
        null_finished.finalizada_em = None
        self.session.flush()

        ranking = self.service.listar(self.session, limit=100)
        names = [item.jogador for item in ranking]
        self.assertEqual(names[:4], ["Conta", "Visitante", "Mesmo nome", "Mesmo nome"])
        self.assertEqual(names.count("Visitante"), 1)
        self.assertEqual(names.count("Legado"), 2)
        self.assertNotIn("Em andamento", names)
        self.assertNotIn("Privado", names)
        self.assertNotIn("Nem a Pato", names)
        self.assertEqual(names[-1], "Sem horário")
        self.assertEqual([item.posicao for item in ranking], list(range(1, len(ranking) + 1)))
        self.assertEqual(len(self.service.listar(self.session, limit=2)), 2)

    def test_filter_by_slug_and_uuid_runs_in_postgresql(self):
        self.add_match(name="Geral", score=900, hits=6)
        self.add_match(name="Tecnologia", score=1000, hits=7, category=self.technology)
        by_slug = self.service.listar(self.session, categoria="geral")
        by_uuid = self.service.listar(
            self.session,
            categoria=str(self.technology.id),
        )
        self.assertEqual([item.jogador for item in by_slug], ["Geral"])
        self.assertEqual([item.jogador for item in by_uuid], ["Tecnologia"])


if __name__ == "__main__":
    unittest.main()
