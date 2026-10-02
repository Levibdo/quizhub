"""Real PostgreSQL concurrency tests for the Nem a Pato lobby.

Run against a disposable database after applying Alembic through 0009:

    NEM_A_PATO_TEST_DATABASE_URL=postgresql+psycopg://.../np3_test_db \
        python -m unittest discover -s tests/integration -v

The database name must start with ``np3_test_``. SQLite is not accepted.
"""

import os
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.base import Base  # noqa: F401
from app.models import ParticipanteNemPato, SalaNemPato
from app.nem_a_pato import ParticipanteNemPatoStatus, SalaNemPatoStatus
from app.services.salas_nem_a_pato import SalasNemAPatoService

TEST_DATABASE_ENV = "NEM_A_PATO_TEST_DATABASE_URL"
DATABASE_URL = os.getenv(TEST_DATABASE_ENV, "").strip()


@unittest.skipUnless(DATABASE_URL, f"configure {TEST_DATABASE_ENV} for PostgreSQL integration tests")
class TestNemAPatoPostgresConcurrency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parsed = make_url(DATABASE_URL)
        if parsed.get_backend_name() != "postgresql":
            raise RuntimeError(f"{TEST_DATABASE_ENV} must point to PostgreSQL")
        if not parsed.database or not parsed.database.startswith("np3_test_"):
            raise RuntimeError(
                f"refusing to test database {parsed.database!r}; "
                "database name must start with 'np3_test_'"
            )
        if parsed.database == "quiz_estagio_db":
            raise RuntimeError("refusing to connect to the development database")

        cls.engine = create_engine(
            DATABASE_URL,
            pool_size=8,
            max_overflow=2,
            pool_pre_ping=True,
            connect_args={"application_name": "np3-integration-test"},
        )
        cls.sessions = sessionmaker(bind=cls.engine, expire_on_commit=False)
        with cls.engine.connect() as connection:
            version = connection.scalar(text("SELECT version_num FROM alembic_version"))
        if version != "0009":
            cls.engine.dispose()
            raise RuntimeError(f"expected Alembic revision 0009, got {version!r}")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.service = SalasNemAPatoService()

    def create_room_with_players(self, names):
        with self.sessions() as session:
            created = self.service.criar(session, names[0])
            room_id = session.scalar(
                select(SalaNemPato.id).where(SalaNemPato.codigo == created.sala.codigo)
            )
        for name in names[1:]:
            with self.sessions() as session:
                self.service.entrar(session, created.sala.codigo, name)
        return created.sala.codigo, room_id

    def active_members(self, room_id):
        with self.sessions() as session:
            return list(
                session.scalars(
                    select(ParticipanteNemPato)
                    .where(
                        ParticipanteNemPato.sala_id == room_id,
                        ParticipanteNemPato.status == ParticipanteNemPatoStatus.ATIVO,
                    )
                    .order_by(ParticipanteNemPato.ordem_entrada)
                )
            )

    def observe_real_row_lock_wait(self, waiter_application_name):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with self.engine.connect() as observer:
                waiting = observer.scalar(
                    text(
                        "SELECT EXISTS ("
                        "SELECT 1 FROM pg_stat_activity "
                        "WHERE application_name = :app_name "
                        "AND wait_event_type = 'Lock'"
                        ")"
                    ),
                    {"app_name": waiter_application_name},
                )
            if waiting:
                return True
            time.sleep(0.01)
        return False

    def run_two_contenders(self, room_code, contender_names):
        both_starting = threading.Barrier(2)
        leader_has_room_lock = threading.Event()
        waiter_about_to_lock = threading.Event()
        release_leader = threading.Event()
        waiter_app_name = f"np3-waiter-{uuid4().hex[:12]}"
        leader_app_name = f"np3-leader-{uuid4().hex[:12]}"
        sql_lock = threading.Lock()
        lock_order = {"np3-lock-leader": [], "np3-lock-waiter": []}

        def record_lock_queries(_connection, _cursor, statement, _parameters, _context, _many):
            current = threading.current_thread().name
            normalized = " ".join(statement.lower().split())
            if current not in lock_order or "for update" not in normalized:
                return
            if "from salas_nem_pato" in normalized:
                resource = "sala"
            elif "from participantes_nem_pato" in normalized:
                resource = "participantes"
            else:
                return
            with sql_lock:
                lock_order[current].append(resource)

        class ObservedLockService(SalasNemAPatoService):
            def _sala_bloqueada(inner_self, db, codigo):
                if threading.current_thread().name == "np3-lock-leader":
                    sala = super(ObservedLockService, inner_self)._sala_bloqueada(db, codigo)
                    leader_has_room_lock.set()
                    if not release_leader.wait(timeout=10):
                        raise TimeoutError("test did not release the first room lock")
                    return sala
                if threading.current_thread().name == "np3-lock-waiter":
                    if not leader_has_room_lock.wait(timeout=10):
                        raise TimeoutError("first transaction did not acquire room lock")
                    waiter_about_to_lock.set()
                return super(ObservedLockService, inner_self)._sala_bloqueada(db, codigo)

        service = ObservedLockService()

        def enter(name, application_name):
            with self.sessions() as session:
                session.execute(
                    text("SELECT set_config('application_name', :name, false)"),
                    {"name": application_name},
                )
                both_starting.wait(timeout=10)
                return service.entrar(session, room_code, name)

        event.listen(self.engine, "before_cursor_execute", record_lock_queries)
        try:
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="np3-race") as pool:
                leader = pool.submit(
                    self._run_named, "np3-lock-leader", enter,
                    contender_names[0], leader_app_name,
                )
                waiter = pool.submit(
                    self._run_named, "np3-lock-waiter", enter,
                    contender_names[1], waiter_app_name,
                )
                try:
                    self.assertTrue(leader_has_room_lock.wait(timeout=10))
                    self.assertTrue(waiter_about_to_lock.wait(timeout=10))
                    self.assertTrue(
                        self.observe_real_row_lock_wait(waiter_app_name),
                        "PostgreSQL did not show the second independent session waiting on a lock",
                    )
                finally:
                    release_leader.set()
                results = [leader.result(timeout=10), waiter.result(timeout=10)]
            for resources in lock_order.values():
                self.assertEqual(resources[:2], ["sala", "participantes"], lock_order)
            return results
        finally:
            event.remove(self.engine, "before_cursor_execute", record_lock_queries)

    @staticmethod
    def _run_named(name, function, *args):
        threading.current_thread().name = name
        try:
            return ("accepted", function(*args))
        except HTTPException as error:
            return ("rejected", error.status_code, error.detail)

    def test_only_one_of_two_contenders_takes_sixth_slot(self):
        room_code, room_id = self.create_room_with_players(["A", "B", "C", "D", "E"])
        results = self.run_two_contenders(room_code, ["F", "G"])

        accepted = [result for result in results if result[0] == "accepted"]
        rejected = [result for result in results if result[0] == "rejected"]
        active = self.active_members(room_id)
        self.assertEqual(len(accepted), 1, results)
        self.assertEqual(len(rejected), 1, results)
        self.assertEqual(rejected[0][1:], (409, "sala cheia"), results)
        self.assertEqual(len(active), 6)
        self.assertEqual(len({member.id for member in active}), 6)

    def test_two_concurrent_entries_receive_distinct_monotonic_orders(self):
        room_code, room_id = self.create_room_with_players(["A", "B", "C"])
        results = self.run_two_contenders(room_code, ["D", "E"])

        self.assertEqual([result[0] for result in results], ["accepted", "accepted"])
        active = self.active_members(room_id)
        orders = [member.ordem_entrada for member in active]
        self.assertEqual(orders, [1, 2, 3, 4, 5])
        self.assertEqual(len(set(orders)), len(orders))

    def test_casefold_duplicate_names_are_serialized(self):
        room_code, room_id = self.create_room_with_players(["Anfitriao"])
        results = self.run_two_contenders(room_code, ["Levi", "LEVI"])

        accepted = [result for result in results if result[0] == "accepted"]
        rejected = [result for result in results if result[0] == "rejected"]
        self.assertEqual(len(accepted), 1, results)
        self.assertEqual(len(rejected), 1, results)
        self.assertEqual(rejected[0][1:], (409, "nome já está em uso na sala"), results)
        names = [member.nome.casefold() for member in self.active_members(room_id)]
        self.assertEqual(len(names), len(set(names)), names)

    def test_host_abandonment_transfers_host_atomically_once(self):
        with self.sessions() as session:
            created = self.service.criar(session, "A")
            room_code = created.sala.codigo
            host_token = created.credencial_participante
            room_id = session.scalar(
                select(SalaNemPato.id).where(SalaNemPato.codigo == room_code)
            )
        self.entrar_twice(room_code)
        before = self.active_members(room_id)
        host = next(member for member in before if member.eh_anfitriao)
        with self.sessions() as session:
            version_before = session.get(SalaNemPato, room_id).estado_versao

        with self.sessions() as session:
            state = self.service.abandonar(session, room_code, host_token)

        with self.sessions() as session:
            members = list(
                session.scalars(
                    select(ParticipanteNemPato)
                    .where(ParticipanteNemPato.sala_id == room_id)
                    .order_by(ParticipanteNemPato.ordem_entrada)
                )
            )
            sala = session.get(SalaNemPato, room_id)
        self.assertEqual(members[0].status, ParticipanteNemPatoStatus.ABANDONOU)
        self.assertFalse(members[0].eh_anfitriao)
        active_hosts = [
            member for member in members
            if member.status == ParticipanteNemPatoStatus.ATIVO and member.eh_anfitriao
        ]
        self.assertEqual(len(active_hosts), 1)
        self.assertEqual(active_hosts[0].nome, "B")
        self.assertEqual(sala.estado_versao, version_before + 1)
        self.assertEqual(state.versao, version_before + 1)

    def entrar_twice(self, room_code):
        for name in ("B", "C"):
            with self.sessions() as session:
                self.service.entrar(session, room_code, name)


if __name__ == "__main__":
    unittest.main()
