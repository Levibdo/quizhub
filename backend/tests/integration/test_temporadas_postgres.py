"""PostgreSQL coverage for migration 0013 and season-switch locking.

This module is destructive and only accepts an explicitly named disposable
database containing ``_test_`` and not matching any known persistent database.
"""

import os
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.db.base import Base  # noqa: F401
from app.models import Temporada
from app.services.ranking import RankingService
from app.services.temporadas import (
    TemporadaInexistente,
    TemporadaInvalida,
    TemporadasService,
)
from app.temporadas import TEMPORADA_LEGADO_ID


URL_ENV = "TEMPORADAS_TEST_DATABASE_URL"
NAME_ENV = "TEMPORADAS_TEST_DATABASE_NAME"
FORBIDDEN_DATABASES = {
    "quizhub_prod_db", "quiz_estagio_db", "quizhub_loadtest_db",
}
GENERAL_ID = UUID("40f40d1f-fa4a-5cc0-9a2f-910bfbf4b4cb")


@unittest.skipUnless(
    os.getenv(URL_ENV, "").strip() and os.getenv(NAME_ENV, "").strip(),
    f"configure {URL_ENV} and {NAME_ENV} for an empty disposable database",
)
class TestTemporadasPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = os.environ[URL_ENV].strip()
        cls.database_name = os.environ[NAME_ENV].strip()
        parsed = make_url(cls.database_url)
        if (
            parsed.get_backend_name() != "postgresql"
            or parsed.database != cls.database_name
            or "_test_" not in cls.database_name
            or cls.database_name in FORBIDDEN_DATABASES
        ):
            raise RuntimeError("temporadas tests require an isolated _test_ PostgreSQL database")
        cls.engine = create_engine(cls.database_url, pool_size=8, pool_pre_ping=True)
        cls.config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
        with cls.engine.connect() as connection:
            if connection.scalar(text("SELECT current_database()")) != cls.database_name:
                raise RuntimeError("connected to an unexpected database")
            tables = list(connection.scalars(text(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'"
            )))
            if tables:
                raise RuntimeError(f"temporadas tests require an empty database; found={tables}")
        cls.migrate("upgrade", "0012")
        cls.historical_match_id = uuid4()
        cls.historical_player_id = uuid4()
        with cls.engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO jogadores (id, nome) VALUES (:id, 'Legado')"
            ), {"id": cls.historical_player_id})
            connection.execute(text("""
                INSERT INTO partidas
                    (id, jogador_id, categoria_id, status, pontuacao, acertos,
                     erros, iniciada_em, finalizada_em)
                VALUES
                    (:id, :jogador, :categoria, 'FINALIZADA', 900, 7, 3,
                     CURRENT_TIMESTAMP - INTERVAL '1 day', CURRENT_TIMESTAMP)
            """), {
                "id": cls.historical_match_id,
                "jogador": cls.historical_player_id,
                "categoria": GENERAL_ID,
            })

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    @classmethod
    def migrate(cls, direction, revision):
        with patch.dict(os.environ, {"DATABASE_URL": cls.database_url}):
            getattr(command, direction)(cls.config, revision)

    @classmethod
    def revision(cls):
        with cls.engine.connect() as connection:
            return connection.scalar(text("SELECT version_num FROM alembic_version"))

    def test_01_upgrade_backfill_structure_and_old_backend_trigger(self):
        self.migrate("upgrade", "0013")
        self.assertEqual(self.revision(), "0013")
        with self.engine.begin() as connection:
            row = connection.execute(text("""
                SELECT data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name='partidas'
                  AND column_name='temporada_id'
            """)).one()
            self.assertEqual(row, ("uuid", "YES"))
            self.assertEqual(connection.scalar(text(
                "SELECT temporada_id FROM partidas WHERE id=:id"
            ), {"id": self.historical_match_id}), TEMPORADA_LEGADO_ID)
            self.assertEqual(connection.scalar(text(
                "SELECT count(*) FROM temporadas WHERE status='ATIVA'"
            )), 1)
            self.assertEqual(connection.scalar(text("""
                SELECT count(*) FROM pg_indexes
                WHERE schemaname='public' AND indexname='uq_temporadas_ativa'
                  AND indexdef LIKE '%WHERE%status%ATIVA%'
            """)), 1)
            self.assertEqual(connection.scalar(text("""
                SELECT count(*) FROM pg_trigger
                WHERE tgname='trg_partidas_temporada_ativa' AND NOT tgisinternal
            """)), 1)

            player_id, match_id = uuid4(), uuid4()
            connection.execute(text(
                "INSERT INTO jogadores (id, nome) VALUES (:id, 'API antiga')"
            ), {"id": player_id})
            connection.execute(text("""
                INSERT INTO partidas
                    (id, jogador_id, categoria_id, status)
                VALUES (:id, :jogador, :categoria, 'EM_ANDAMENTO')
            """), {"id": match_id, "jogador": player_id, "categoria": GENERAL_ID})
            self.assertEqual(connection.scalar(text(
                "SELECT temporada_id FROM partidas WHERE id=:id"
            ), {"id": match_id}), TEMPORADA_LEGADO_ID)

    def test_02_ranking_historico_e_temporada_planejada_nao_publica(self):
        planned_id = uuid4()
        with self.engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO temporadas (id, numero, nome, status, inicia_em)
                VALUES (:id, 2, 'Temporada 2', 'PLANEJADA', CURRENT_TIMESTAMP)
            """), {"id": planned_id})
        with Session(self.engine) as session:
            service = RankingService()
            self.assertEqual(
                [item.jogador for item in service.listar(session, temporada=1)],
                ["Legado"],
            )
            with self.assertRaises(TemporadaInexistente):
                service.listar(session, temporada=planned_id)

    def test_03_criacao_e_virada_sao_serializadas(self):
        with self.engine.connect() as connection:
            planned_id = connection.scalar(text(
                "SELECT id FROM temporadas WHERE numero=2"
            ))
        creation_locked = threading.Event()
        release_creation = threading.Event()
        activation_started = threading.Event()
        errors = []
        created_match = uuid4()

        def create_match():
            try:
                with self.engine.begin() as connection:
                    current_id = connection.scalar(text(
                        "SELECT id FROM temporadas WHERE status='ATIVA' FOR SHARE"
                    ))
                    creation_locked.set()
                    if not release_creation.wait(10):
                        raise TimeoutError("creation release was not signaled")
                    player_id = uuid4()
                    connection.execute(text(
                        "INSERT INTO jogadores (id, nome) VALUES (:id, 'Corrida')"
                    ), {"id": player_id})
                    connection.execute(text("""
                        INSERT INTO partidas
                            (id, jogador_id, categoria_id, temporada_id, status)
                        VALUES (:id, :jogador, :categoria, :temporada, 'EM_ANDAMENTO')
                    """), {
                        "id": created_match, "jogador": player_id,
                        "categoria": GENERAL_ID, "temporada": current_id,
                    })
            except Exception as error:  # pragma: no cover - asserted by parent
                errors.append(error)

        def activate():
            try:
                creation_locked.wait(10)
                activation_started.set()
                with Session(self.engine) as session:
                    TemporadasService().ativar(
                        session, planned_id,
                        temporada_atual_id=TEMPORADA_LEGADO_ID,
                    )
                    session.commit()
            except Exception as error:  # pragma: no cover - asserted by parent
                errors.append(error)

        creation = threading.Thread(target=create_match)
        activation = threading.Thread(target=activate)
        creation.start()
        self.assertTrue(creation_locked.wait(10))
        activation.start()
        self.assertTrue(activation_started.wait(10))
        self.assertTrue(activation.is_alive())
        release_creation.set()
        creation.join(10)
        activation.join(10)
        self.assertFalse(creation.is_alive())
        self.assertFalse(activation.is_alive())
        self.assertEqual(errors, [])
        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(text(
                "SELECT temporada_id FROM partidas WHERE id=:id"
            ), {"id": created_match}), TEMPORADA_LEGADO_ID)
            self.assertEqual(connection.scalar(text(
                "SELECT numero FROM temporadas WHERE status='ATIVA'"
            )), 2)
        with Session(self.engine) as session:
            self.assertEqual(RankingService().listar(session), [])

    def test_04_tentativas_concorrentes_de_ativacao_nao_encadeiam(self):
        with self.engine.begin() as connection:
            current_id = connection.scalar(text(
                "SELECT id FROM temporadas WHERE status='ATIVA'"
            ))
            targets = [uuid4(), uuid4()]
            first_number = connection.scalar(text(
                "SELECT max(numero) + 1 FROM temporadas"
            ))
            for number, target in enumerate(targets, start=first_number):
                connection.execute(text("""
                    INSERT INTO temporadas (id, numero, nome, status, inicia_em)
                    VALUES (:id, :numero, :nome, 'PLANEJADA', CURRENT_TIMESTAMP)
                """), {"id": target, "numero": number, "nome": f"Temporada {number}"})

        barrier = threading.Barrier(2)
        successes, failures = [], []

        def activate(target):
            try:
                barrier.wait(10)
                with Session(self.engine) as session:
                    TemporadasService().ativar(
                        session, target, temporada_atual_id=current_id
                    )
                    session.commit()
                successes.append(target)
            except TemporadaInvalida as error:
                failures.append(str(error))

        threads = [threading.Thread(target=activate, args=(target,)) for target in targets]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
            self.assertFalse(thread.is_alive())
        self.assertEqual(len(successes), 1)
        self.assertEqual(failures, ["a temporada ativa mudou durante a ativação"])
        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(text(
                "SELECT count(*) FROM temporadas WHERE status='ATIVA'"
            )), 1)

    def test_03b_backend_antigo_aguarda_virada_e_recebe_nova_temporada(self):
        with self.engine.begin() as connection:
            current_id = connection.scalar(text(
                "SELECT id FROM temporadas WHERE status='ATIVA'"
            ))
            next_number = connection.scalar(text(
                "SELECT max(numero) + 1 FROM temporadas"
            ))
            target_id = uuid4()
            connection.execute(text("""
                INSERT INTO temporadas (id, numero, nome, status, inicia_em)
                VALUES (:id, :numero, :nome, 'PLANEJADA', CURRENT_TIMESTAMP)
            """), {
                "id": target_id, "numero": next_number,
                "nome": f"Temporada {next_number}",
            })

        switch_ready = threading.Event()
        release_switch = threading.Event()
        insert_started = threading.Event()
        errors = []
        match_id = uuid4()

        def switch():
            try:
                with self.engine.begin() as connection:
                    connection.execute(text(
                        "SELECT id FROM temporadas WHERE id=:id FOR UPDATE"
                    ), {"id": current_id})
                    connection.execute(text("""
                        UPDATE temporadas
                        SET status='ENCERRADA', encerra_em=CURRENT_TIMESTAMP,
                            atualizada_em=CURRENT_TIMESTAMP
                        WHERE id=:id
                    """), {"id": current_id})
                    connection.execute(text("""
                        UPDATE temporadas
                        SET status='ATIVA', inicia_em=CURRENT_TIMESTAMP,
                            encerra_em=NULL, atualizada_em=CURRENT_TIMESTAMP
                        WHERE id=:id
                    """), {"id": target_id})
                    switch_ready.set()
                    if not release_switch.wait(10):
                        raise TimeoutError("switch release was not signaled")
            except Exception as error:  # pragma: no cover - asserted by parent
                errors.append(error)

        def old_backend_insert():
            try:
                self.assertTrue(switch_ready.wait(10))
                insert_started.set()
                with self.engine.begin() as connection:
                    player_id = uuid4()
                    connection.execute(text(
                        "INSERT INTO jogadores (id, nome) VALUES (:id, 'API antiga 2')"
                    ), {"id": player_id})
                    connection.execute(text("""
                        INSERT INTO partidas
                            (id, jogador_id, categoria_id, status)
                        VALUES (:id, :jogador, :categoria, 'EM_ANDAMENTO')
                    """), {
                        "id": match_id, "jogador": player_id,
                        "categoria": GENERAL_ID,
                    })
            except Exception as error:  # pragma: no cover - asserted by parent
                errors.append(error)

        switching = threading.Thread(target=switch)
        inserting = threading.Thread(target=old_backend_insert)
        switching.start()
        self.assertTrue(switch_ready.wait(10))
        inserting.start()
        self.assertTrue(insert_started.wait(10))
        self.assertTrue(inserting.is_alive())
        release_switch.set()
        switching.join(10)
        inserting.join(10)
        self.assertEqual(errors, [])
        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(text(
                "SELECT temporada_id FROM partidas WHERE id=:id"
            ), {"id": match_id}), target_id)

    def test_99_downgrade_e_novo_upgrade_preservam_partidas(self):
        count_before = None
        with self.engine.connect() as connection:
            count_before = connection.scalar(text("SELECT count(*) FROM partidas"))
        self.migrate("downgrade", "0012")
        self.assertEqual(self.revision(), "0012")
        with self.engine.connect() as connection:
            self.assertIsNone(connection.scalar(text("""
                SELECT to_regclass('public.temporadas')
            """)))
            self.assertEqual(connection.scalar(text("SELECT count(*) FROM partidas")), count_before)
        self.migrate("upgrade", "0013")
        self.assertEqual(self.revision(), "0013")
        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(text("SELECT count(*) FROM partidas")), count_before)
            self.assertEqual(connection.scalar(text(
                "SELECT count(*) FROM partidas WHERE temporada_id IS NULL"
            )), 0)


if __name__ == "__main__":
    unittest.main()
