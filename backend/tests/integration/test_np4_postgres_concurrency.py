"""Real PostgreSQL concurrency tests for NP4 match start.

Run against a disposable PostgreSQL database, migrated to 0009:

    NEM_A_PATO_TEST_DATABASE_URL=postgresql+psycopg://.../np3_test_local \
        python -m unittest discover -s tests/integration -v

The shared integration harness refuses databases outside the np3_test_* namespace.
"""

import os
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.conteudo import CATEGORIAS_OFICIAIS, MODO_NEM_A_PATO
from app.db.base import Base  # noqa: F401
from app.models import (
    Categoria,
    JogadorPartidaNemPato,
    PartidaNemPato,
    ParticipanteNemPato,
    PerguntaNemPato,
    RodadaNemPato,
    SalaNemPato,
)
from app.nem_a_pato import PartidaNemPatoStatus, SalaNemPatoStatus
from app.services.salas_nem_a_pato import SalasNemAPatoService

ENV_NAME = "NEM_A_PATO_TEST_DATABASE_URL"
DATABASE_URL = os.getenv(ENV_NAME, "").strip()


@unittest.skipUnless(DATABASE_URL, f"configure {ENV_NAME} for PostgreSQL integration tests")
class TestNemAPatoStartPostgresConcurrency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parsed = make_url(DATABASE_URL)
        if parsed.get_backend_name() != "postgresql":
            raise RuntimeError(f"{ENV_NAME} must point to PostgreSQL")
        if not parsed.database or not parsed.database.startswith("np3_test_"):
            raise RuntimeError("refusing non-disposable database; expected np3_test_*")
        if parsed.database == "quiz_estagio_db":
            raise RuntimeError("refusing to connect to development database")
        cls.engine = create_engine(
            DATABASE_URL,
            pool_size=8,
            max_overflow=2,
            pool_pre_ping=True,
            connect_args={"application_name": "np4-integration-test"},
        )
        cls.sessions = sessionmaker(bind=cls.engine, expire_on_commit=False)
        with cls.engine.connect() as connection:
            revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        if revision != "0011":
            cls.engine.dispose()
            raise RuntimeError(f"expected revision 0011, received {revision!r}")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.service = SalasNemAPatoService()

    def room_with_three(self):
        with self.sessions() as session:
            created = self.service.criar(session, f"Host-{uuid4().hex[:6]}")
            room_id = session.scalar(
                select(SalaNemPato.id).where(SalaNemPato.codigo == created.sala.codigo)
            )
        for name in (f"B-{uuid4().hex[:6]}", f"C-{uuid4().hex[:6]}"):
            with self.sessions() as session:
                self.service.entrar(session, created.sala.codigo, name)
        return created.sala.codigo, room_id, created.credencial_participante

    def add_ten_active_questions(self):
        with self.sessions() as session:
            categoria_id = CATEGORIAS_OFICIAIS[MODO_NEM_A_PATO]["geral"]
            if session.get(Categoria, categoria_id) is None:
                self.fail("base category 'geral' missing from migration 0009")
            session.add_all([
                PerguntaNemPato(
                    categoria_id=categoria_id,
                    enunciado=f"Postgres NP4 {uuid4()}",
                    resposta_numerica=index,
                    explicacao="private test explanation",
                    ativa=True,
                )
                for index in range(10)
            ])
            session.commit()

    def assert_waiting_on_postgres_lock(self, backend_pid):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with self.engine.connect() as observer:
                waiting = observer.scalar(
                    text(
                        "SELECT wait_event_type = 'Lock' "
                        "FROM pg_stat_activity WHERE pid = :pid"
                    ),
                    {"pid": backend_pid},
                )
            if waiting:
                return True
            time.sleep(0.01)
        with self.engine.connect() as observer:
            details = observer.execute(
                text(
                    "SELECT pid, application_name, state, wait_event_type, wait_event, "
                    "pg_blocking_pids(pid), left(query, 100) "
                    "FROM pg_stat_activity WHERE application_name LIKE 'np4-%' "
                    "OR pid = :pid ORDER BY pid"
                ),
                {"pid": backend_pid},
            ).all()
        self.last_lock_wait_details = details
        return False

    def race_actions(self, room_code, host_token, join_name=None):
        barrier = threading.Barrier(2)
        leader_locked = threading.Event()
        waiter_attempting = threading.Event()
        release_leader = threading.Event()
        app_names = {
            "np4-start-leader": f"np4-leader-{uuid4().hex[:10]}",
            "np4-start-waiter": f"np4-waiter-{uuid4().hex[:10]}",
        }
        backend_pids = {}
        lock_order = {name: [] for name in app_names}
        record_lock = threading.Lock()

        def observe_sql(_conn, _cursor, statement, _params, _context, _many):
            thread_name = threading.current_thread().name
            normalized = " ".join(statement.lower().split())
            if thread_name not in lock_order or "for update" not in normalized:
                return
            if "from salas_nem_pato" in normalized:
                lock_target = "sala"
            elif "from participantes_nem_pato" in normalized:
                lock_target = "participantes"
            elif "from partidas_nem_pato" in normalized:
                lock_target = "partida"
            else:
                return
            with record_lock:
                lock_order[thread_name].append(lock_target)

        class HeldRoomLockService(SalasNemAPatoService):
            def _sala_bloqueada(inner, db, codigo):
                is_leader = threading.current_thread().name == "np4-start-leader"
                is_waiter = threading.current_thread().name == "np4-start-waiter"
                if is_waiter:
                    if not leader_locked.wait(timeout=10):
                        raise TimeoutError("leader did not acquire the room lock first")
                    waiter_attempting.set()
                sala = super(HeldRoomLockService, inner)._sala_bloqueada(db, codigo)
                if is_leader:
                    leader_locked.set()
                    if not release_leader.wait(timeout=30):
                        raise TimeoutError("start leader lock was not released")
                return sala

        service = HeldRoomLockService()

        def action(application_name):
            with self.sessions() as session:
                session.execute(
                    text("SELECT set_config('application_name', :app, true)"),
                    {"app": application_name},
                )
                backend_pids[threading.current_thread().name] = session.scalar(
                    text("SELECT pg_backend_pid()")
                )
                barrier.wait(timeout=10)
                if join_name is not None and threading.current_thread().name == "np4-start-waiter":
                    return service.entrar(session, room_code, join_name)
                return service.iniciar(session, room_code, host_token)

        event.listen(self.engine, "before_cursor_execute", observe_sql)
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                leader = executor.submit(
                    self._capture_result, "np4-start-leader", action,
                    app_names["np4-start-leader"],
                )
                waiter = executor.submit(
                    self._capture_result, "np4-start-waiter", action,
                    app_names["np4-start-waiter"],
                )
                try:
                    self.assertTrue(leader_locked.wait(10))
                    self.assertTrue(waiter_attempting.wait(10))
                    lock_wait_seen = self.assert_waiting_on_postgres_lock(
                        backend_pids["np4-start-waiter"],
                    )
                finally:
                    release_leader.set()
                results = [leader.result(timeout=10), waiter.result(timeout=10)]
                self.assertTrue(
                    lock_wait_seen,
                    "second PostgreSQL transaction did not wait on a real row lock: "
                    f"pids={backend_pids!r}; activity="
                    f"{getattr(self, 'last_lock_wait_details', None)!r}; results={results!r}",
                )
            self.assertEqual(len(set(backend_pids.values())), 2, backend_pids)
            for thread_name, acquired in lock_order.items():
                self.assertEqual(acquired[0], "sala", lock_order)
                if thread_name == "np4-start-leader" or join_name is not None:
                    self.assertEqual(acquired[1], "participantes", lock_order)
            return results
        finally:
            event.remove(self.engine, "before_cursor_execute", observe_sql)

    @staticmethod
    def _capture_result(thread_name, function, *args):
        threading.current_thread().name = thread_name
        try:
            return ("accepted", function(*args))
        except HTTPException as error:
            return ("rejected", error.status_code, error.detail)

    def test_two_concurrent_host_start_requests_create_one_complete_match(self):
        room_code, room_id, host_token = self.room_with_three()
        self.add_ten_active_questions()
        results = self.race_actions(room_code, host_token)

        accepted = [result for result in results if result[0] == "accepted"]
        rejected = [result for result in results if result[0] == "rejected"]
        self.assertEqual(len(accepted), 1, results)
        self.assertEqual(len(rejected), 1, results)
        self.assertEqual(rejected[0][1], 409)
        with self.sessions() as session:
            room = session.get(SalaNemPato, room_id)
            matches = list(session.scalars(select(PartidaNemPato).where(
                PartidaNemPato.sala_id == room_id,
                PartidaNemPato.status == PartidaNemPatoStatus.EM_ANDAMENTO,
            )))
            self.assertEqual(room.status, SalaNemPatoStatus.EM_PARTIDA)
            self.assertEqual(room.estado_versao, 3)
            self.assertEqual(len(matches), 1)
            players = list(session.scalars(select(JogadorPartidaNemPato).where(
                JogadorPartidaNemPato.partida_id == matches[0].id
            )))
            rounds = list(session.scalars(select(RodadaNemPato).where(
                RodadaNemPato.partida_id == matches[0].id
            )))
            self.assertEqual(len(players), 3)
            self.assertEqual(len(rounds), 10)
            self.assertEqual(len({round_.pergunta_id for round_ in rounds}), 10)

    def test_start_serializes_against_join_and_excludes_mid_start_participant(self):
        room_code, room_id, host_token = self.room_with_three()
        self.add_ten_active_questions()
        results = self.race_actions(room_code, host_token, join_name=f"Late-{uuid4().hex[:6]}")

        accepted = [result for result in results if result[0] == "accepted"]
        rejected = [result for result in results if result[0] == "rejected"]
        self.assertEqual(len(accepted), 1, results)
        self.assertEqual(len(rejected), 1, results)
        self.assertEqual(rejected[0][1:], (409, "sala não está aguardando"), results)
        with self.sessions() as session:
            room = session.get(SalaNemPato, room_id)
            players = list(session.scalars(select(JogadorPartidaNemPato).join(
                PartidaNemPato,
                JogadorPartidaNemPato.partida_id == PartidaNemPato.id,
            ).where(PartidaNemPato.sala_id == room_id)))
            members = list(session.scalars(select(ParticipanteNemPato).where(
                ParticipanteNemPato.sala_id == room_id,
                ParticipanteNemPato.status == "ATIVO",
            )))
        self.assertEqual(room.status, SalaNemPatoStatus.EM_PARTIDA)
        self.assertEqual(len(players), 3)
        self.assertEqual(len(members), 3)


if __name__ == "__main__":
    unittest.main()
