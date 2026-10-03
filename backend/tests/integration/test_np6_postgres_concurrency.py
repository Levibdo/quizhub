"""Real PostgreSQL concurrency acceptance tests for NP6."""

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
    DesafioNemPato,
    JogadorPartidaNemPato,
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
class TestNP6PostgresConcurrency(unittest.TestCase):
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
            connect_args={"application_name": "np6-integration-test"},
        )
        cls.sessions = sessionmaker(bind=cls.engine, expire_on_commit=False)
        with cls.engine.connect() as connection:
            revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        if revision != "0010":
            cls.engine.dispose()
            raise RuntimeError(f"expected revision 0010, received {revision!r}")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.service = SalasNemAPatoService()

    def preparar(self):
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
                self.fail("base category geral missing")
            session.add_all([
                PerguntaNemPato(
                    categoria_id="geral",
                    enunciado=f"PostgreSQL NP6 {uuid4()}",
                    resposta_numerica=600,
                    explicacao="private integration explanation",
                    ativa=True,
                )
                for _ in range(10)
            ])
            session.commit()
        with self.sessions() as session:
            self.service.iniciar(session, host.sala.codigo, tokens["host"])
        with self.sessions() as session:
            estado = self.service.iniciar_rodada(session, host.sala.codigo, tokens["host"])
        rodada_id = estado.partida.rodada.id
        with self.sessions() as session:
            rodada = session.get(RodadaNemPato, rodada_id)
            session.get(PerguntaNemPato, rodada.pergunta_id).resposta_numerica = 600
            session.commit()
        with self.sessions() as session:
            self.service.palpitar(session, host.sala.codigo, rodada_id, tokens["host"], 500, uuid4())
        return host.sala.codigo, tokens, rodada_id

    def _esperou_lock_real(self, pid):
        limite = time.monotonic() + 10
        while time.monotonic() < limite:
            with self.engine.connect() as observador:
                esperando = observador.scalar(
                    text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"),
                    {"pid": pid},
                )
            if esperando:
                return True
            time.sleep(0.01)
        return False

    def corrida(self, lider_acao, segundo_acao):
        lider_bloqueou = threading.Event()
        segundo_tentou = threading.Event()
        liberar_lider = threading.Event()
        pids = {}

        class ServicoComLockRetido(SalasNemAPatoService):
            def _sala_bloqueada(inner, db, codigo):
                nome = threading.current_thread().name
                if nome == "np6-waiter":
                    if not lider_bloqueou.wait(10):
                        raise TimeoutError("leader did not lock room")
                    segundo_tentou.set()
                sala = super(ServicoComLockRetido, inner)._sala_bloqueada(db, codigo)
                if nome == "np6-leader":
                    lider_bloqueou.set()
                    if not liberar_lider.wait(30):
                        raise TimeoutError("leader lock was not released")
                return sala

        service = ServicoComLockRetido()

        def executar(nome, acao):
            threading.current_thread().name = nome
            try:
                with self.sessions() as session:
                    pids[nome] = session.scalar(text("SELECT pg_backend_pid()"))
                    return ("accepted", acao(session, service))
            except HTTPException as erro:
                return ("rejected", erro.status_code, erro.detail)

        with ThreadPoolExecutor(max_workers=2) as executor:
            lider = executor.submit(executar, "np6-leader", lider_acao)
            segundo = executor.submit(executar, "np6-waiter", segundo_acao)
            try:
                self.assertTrue(lider_bloqueou.wait(10))
                self.assertTrue(segundo_tentou.wait(10))
                self.assertTrue(self._esperou_lock_real(pids["np6-waiter"]))
            finally:
                liberar_lider.set()
            resultados = [lider.result(10), segundo.result(10)]
        self.assertEqual(len(set(pids.values())), 2)
        return resultados

    def estado(self, codigo, rodada_id):
        with self.sessions() as session:
            sala = session.scalar(select(SalaNemPato).where(SalaNemPato.codigo == codigo))
            partida = session.scalar(select(PartidaNemPato).where(PartidaNemPato.sala_id == sala.id))
            rodada = session.get(RodadaNemPato, rodada_id)
            palpites = list(session.scalars(select(PalpiteNemPato).where(PalpiteNemPato.rodada_id == rodada_id).order_by(PalpiteNemPato.ordem)))
            desafio = session.scalar(select(DesafioNemPato).where(DesafioNemPato.rodada_id == rodada_id))
            jogadores = list(session.scalars(select(JogadorPartidaNemPato).where(JogadorPartidaNemPato.partida_id == partida.id)))
            return sala, rodada, palpites, desafio, jogadores

    def test_desafio_contra_desafio_apenas_um_resolve(self):
        codigo, tokens, rodada_id = self.preparar()
        resultados = self.corrida(
            lambda session, service: service.desafiar(session, codigo, rodada_id, tokens["b"], uuid4()),
            lambda session, service: service.desafiar(session, codigo, rodada_id, tokens["c"], uuid4()),
        )
        self.assertEqual([item[0] for item in resultados].count("accepted"), 1)
        self.assertEqual([item[0] for item in resultados].count("rejected"), 1)
        _, rodada, _, desafio, jogadores = self.estado(codigo, rodada_id)
        self.assertEqual(rodada.status, RodadaNemPatoStatus.RESULTADO)
        self.assertIsNotNone(desafio)
        self.assertEqual(sum(jogador.patos for jogador in jogadores), 1)

    def test_retries_concorrentes_da_mesma_acao_tem_um_efeito(self):
        codigo, tokens, rodada_id = self.preparar()
        action_id = uuid4()
        acao = lambda session, service: service.desafiar(session, codigo, rodada_id, tokens["b"], action_id)
        resultados = self.corrida(acao, acao)
        self.assertEqual([item[0] for item in resultados], ["accepted", "accepted"])
        _, _, _, desafio, jogadores = self.estado(codigo, rodada_id)
        self.assertEqual(desafio.client_action_id, action_id)
        self.assertEqual(sum(jogador.patos for jogador in jogadores), 1)

    def test_palpite_contra_desafio_serializa_nos_dois_sentidos(self):
        for palpite_primeiro in (False, True):
            with self.subTest(palpite_primeiro=palpite_primeiro):
                codigo, tokens, rodada_id = self.preparar()
                palpite = lambda session, service: service.palpitar(session, codigo, rodada_id, tokens["b"], 700, uuid4())
                desafio = lambda session, service: service.desafiar(session, codigo, rodada_id, tokens["c"], uuid4())
                resultados = self.corrida(
                    palpite if palpite_primeiro else desafio,
                    desafio if palpite_primeiro else palpite,
                )
                _, rodada, palpites, resolucao, jogadores = self.estado(codigo, rodada_id)
                self.assertEqual(rodada.status, RodadaNemPatoStatus.RESULTADO)
                self.assertEqual(sum(jogador.patos for jogador in jogadores), 1)
                self.assertIsNotNone(resolucao)
                if palpite_primeiro:
                    self.assertEqual([item[0] for item in resultados], ["accepted", "accepted"])
                    self.assertEqual([item.valor for item in palpites], [500, 700])
                    self.assertEqual(resolucao.palpite_desafiado_id, palpites[-1].id)
                else:
                    self.assertEqual([item[0] for item in resultados], ["accepted", "rejected"])
                    self.assertEqual([item.valor for item in palpites], [500])
                    self.assertEqual(resolucao.palpite_desafiado_id, palpites[0].id)


if __name__ == "__main__":
    unittest.main()
