"""Real PostgreSQL concurrency acceptance tests for NP5.

The harness refuses the development database and accepts only disposable
databases whose name starts with np3_test_.
"""

import os
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.base import Base  # noqa: F401
from app.models import (
    Categoria,
    PalpiteNemPato,
    PartidaNemPato,
    PerguntaNemPato,
    RodadaNemPato,
    SalaNemPato,
)
from app.nem_a_pato import RodadaNemPatoStatus
from app.services.salas_nem_a_pato import SalasNemAPatoService

ENV_NAME = "NEM_A_PATO_TEST_DATABASE_URL"
DATABASE_URL = os.getenv(ENV_NAME, "").strip()


@unittest.skipUnless(DATABASE_URL, f"configure {ENV_NAME} for PostgreSQL integration tests")
class TestNemAPatoRoundPostgresConcurrency(unittest.TestCase):
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
            connect_args={"application_name": "np5-integration-test"},
        )
        cls.sessions = sessionmaker(bind=cls.engine, expire_on_commit=False)
        with cls.engine.connect() as connection:
            revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        if revision != "0009":
            cls.engine.dispose()
            raise RuntimeError(f"expected revision 0009, received {revision!r}")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.service = SalasNemAPatoService()

    def preparar(self, *, iniciar_rodada=True):
        with self.sessions() as session:
            host = self.service.criar(session, f"Host-{uuid4().hex[:8]}")
        tokens = {"host": host.credencial_participante}
        for chave in ("b", "c"):
            with self.sessions() as session:
                entrada = self.service.entrar(
                    session, host.sala.codigo, f"{chave.upper()}-{uuid4().hex[:8]}"
                )
                tokens[chave] = entrada.credencial_participante
        with self.sessions() as session:
            if session.get(Categoria, "geral") is None:
                self.fail("base category geral missing from migration 0009")
            session.add_all([
                PerguntaNemPato(
                    categoria_id="geral",
                    enunciado=f"PostgreSQL NP5 {uuid4()}",
                    resposta_numerica=indice,
                    explicacao="private integration explanation",
                    ativa=True,
                )
                for indice in range(10)
            ])
            session.commit()
        with self.sessions() as session:
            self.service.iniciar(
                session, host.sala.codigo, host.credencial_participante
            )
        if iniciar_rodada:
            with self.sessions() as session:
                estado = self.service.iniciar_rodada(
                    session, host.sala.codigo, host.credencial_participante
                )
            rodada_id = estado.partida.rodada.id
        else:
            rodada_id = None
        return host.sala.codigo, tokens, rodada_id

    def _esperou_lock_real(self, pid):
        limite = time.monotonic() + 10
        while time.monotonic() < limite:
            with self.engine.connect() as observador:
                esperando = observador.scalar(
                    text(
                        "SELECT wait_event_type = 'Lock' "
                        "FROM pg_stat_activity WHERE pid = :pid"
                    ),
                    {"pid": pid},
                )
            if esperando:
                return True
            time.sleep(0.01)
        return False

    def corrida(self, acao):
        lider_bloqueou = threading.Event()
        segundo_tentou = threading.Event()
        liberar_lider = threading.Event()
        pids = {}

        class ServicoComLockRetido(SalasNemAPatoService):
            def _sala_bloqueada(inner, db, codigo):
                nome = threading.current_thread().name
                if nome == "np5-waiter":
                    if not lider_bloqueou.wait(10):
                        raise TimeoutError("leader did not lock room")
                    segundo_tentou.set()
                sala = super(ServicoComLockRetido, inner)._sala_bloqueada(db, codigo)
                if nome == "np5-leader":
                    lider_bloqueou.set()
                    if not liberar_lider.wait(30):
                        raise TimeoutError("leader lock was not released")
                return sala

        service = ServicoComLockRetido()

        def executar(nome):
            threading.current_thread().name = nome
            try:
                with self.sessions() as session:
                    pids[nome] = session.scalar(text("SELECT pg_backend_pid()"))
                    return ("accepted", acao(session, service))
            except HTTPException as erro:
                return ("rejected", erro.status_code, erro.detail)

        with ThreadPoolExecutor(max_workers=2) as executor:
            lider = executor.submit(executar, "np5-leader")
            segundo = executor.submit(executar, "np5-waiter")
            try:
                self.assertTrue(lider_bloqueou.wait(10))
                self.assertTrue(segundo_tentou.wait(10))
                self.assertTrue(self._esperou_lock_real(pids["np5-waiter"]))
            finally:
                liberar_lider.set()
            resultados = [lider.result(10), segundo.result(10)]
        self.assertEqual(len(set(pids.values())), 2)
        return resultados

    def estado_persistido(self, codigo, rodada_id):
        with self.sessions() as session:
            sala = session.scalar(select(SalaNemPato).where(SalaNemPato.codigo == codigo))
            partida = session.scalar(
                select(PartidaNemPato).where(PartidaNemPato.sala_id == sala.id)
            )
            rodada = session.get(RodadaNemPato, rodada_id)
            palpites = list(session.scalars(
                select(PalpiteNemPato)
                .where(PalpiteNemPato.rodada_id == rodada_id)
                .order_by(PalpiteNemPato.ordem)
            ))
            return sala, partida, rodada, palpites

    def test_two_actions_same_turn_accept_exactly_one(self):
        codigo, tokens, rodada_id = self.preparar()

        def acao(session, service):
            return service.palpitar(
                session, codigo, rodada_id, tokens["host"], 100, uuid4()
            )

        resultados = self.corrida(acao)
        self.assertEqual([r[0] for r in resultados].count("accepted"), 1)
        self.assertEqual([r[0] for r in resultados].count("rejected"), 1)
        sala, _, rodada, palpites = self.estado_persistido(codigo, rodada_id)
        self.assertEqual(len(palpites), 1)
        self.assertEqual(palpites[0].ordem, 1)
        self.assertNotEqual(rodada.jogador_da_vez_id, palpites[0].jogador_partida_id)
        self.assertEqual(sala.estado_versao, 5)

    def test_two_simultaneous_retries_are_idempotent(self):
        codigo, tokens, rodada_id = self.preparar()
        action_id = uuid4()

        def acao(session, service):
            return service.palpitar(
                session, codigo, rodada_id, tokens["host"], 100, action_id
            )

        resultados = self.corrida(acao)
        self.assertEqual([r[0] for r in resultados], ["accepted", "accepted"])
        sala, _, rodada, palpites = self.estado_persistido(codigo, rodada_id)
        self.assertEqual(len(palpites), 1)
        self.assertEqual(palpites[0].client_action_id, action_id)
        self.assertNotEqual(rodada.jogador_da_vez_id, palpites[0].jogador_partida_id)
        self.assertEqual(sala.estado_versao, 5)

    def test_two_simultaneous_round_starts_transition_once(self):
        codigo, tokens, _ = self.preparar(iniciar_rodada=False)

        def acao(session, service):
            return service.iniciar_rodada(session, codigo, tokens["host"])

        resultados = self.corrida(acao)
        self.assertEqual([r[0] for r in resultados].count("accepted"), 1)
        self.assertEqual([r[0] for r in resultados].count("rejected"), 1)
        with self.sessions() as session:
            sala = session.scalar(select(SalaNemPato).where(SalaNemPato.codigo == codigo))
            partida = session.scalar(
                select(PartidaNemPato).where(PartidaNemPato.sala_id == sala.id)
            )
            rodada = session.scalar(select(RodadaNemPato).where(
                RodadaNemPato.partida_id == partida.id,
                RodadaNemPato.numero == 1,
            ))
        self.assertEqual(rodada.status, RodadaNemPatoStatus.EM_ANDAMENTO)
        self.assertIsNotNone(rodada.iniciada_em)
        self.assertIsNotNone(rodada.termina_em)
        self.assertEqual(sala.estado_versao, 4)


if __name__ == "__main__":
    unittest.main()
