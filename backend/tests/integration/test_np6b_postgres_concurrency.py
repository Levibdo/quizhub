"""Real PostgreSQL concurrency acceptance tests for NP6B."""

import os
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.conteudo import CATEGORIAS_OFICIAIS, MODO_NEM_A_PATO
from app.db.base import Base  # noqa: F401
from app.models import Categoria, PartidaNemPato, PerguntaNemPato, RodadaNemPato, SalaNemPato
from app.nem_a_pato import RodadaNemPatoStatus
from app.services.salas_nem_a_pato import SalasNemAPatoService

ENV_NAME = "NEM_A_PATO_TEST_DATABASE_URL"
DATABASE_URL = os.getenv(ENV_NAME, "").strip()


@unittest.skipUnless(DATABASE_URL, f"configure {ENV_NAME} for PostgreSQL integration tests")
class TestNP6BPostgresConcurrency(unittest.TestCase):
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
            connect_args={"application_name": "np6b-integration-test"},
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

    def preparar_resultado(self, quantidade=3):
        with self.sessions() as session:
            host = self.service.criar(session, f"Host-{uuid4().hex[:8]}")
        tokens = {"host": host.credencial_participante}
        for indice in range(1, quantidade):
            chave = f"p{indice}"
            with self.sessions() as session:
                entrada = self.service.entrar(
                    session, host.sala.codigo, f"P{indice}-{uuid4().hex[:8]}"
                )
                tokens[chave] = entrada.credencial_participante
        with self.sessions() as session:
            categoria_id = CATEGORIAS_OFICIAIS[MODO_NEM_A_PATO]["geral"]
            if session.get(Categoria, categoria_id) is None:
                self.fail("base category geral missing")
            session.add_all(
                PerguntaNemPato(
                    categoria_id=categoria_id,
                    enunciado=f"PostgreSQL NP6B {uuid4()}",
                    resposta_numerica=600,
                    explicacao="private integration explanation",
                    ativa=True,
                )
                for _ in range(10)
            )
            session.commit()
        with self.sessions() as session:
            self.service.iniciar(session, host.sala.codigo, tokens["host"])
        with self.sessions() as session:
            estado = self.service.iniciar_rodada(session, host.sala.codigo, tokens["host"])
        rodada_id = estado.partida.rodada.id
        with self.sessions() as session:
            self.service.palpitar(
                session, host.sala.codigo, rodada_id, tokens["host"], 500, uuid4()
            )
        with self.sessions() as session:
            self.service.desafiar(
                session, host.sala.codigo, rodada_id, tokens["p1"], uuid4()
            )
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
                if nome == "np6b-waiter":
                    if not lider_bloqueou.wait(10):
                        raise TimeoutError("leader did not lock room")
                    segundo_tentou.set()
                sala = super(ServicoComLockRetido, inner)._sala_bloqueada(db, codigo)
                if nome == "np6b-leader":
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
            lider = executor.submit(executar, "np6b-leader", lider_acao)
            segundo = executor.submit(executar, "np6b-waiter", segundo_acao)
            try:
                self.assertTrue(lider_bloqueou.wait(10))
                self.assertTrue(segundo_tentou.wait(10))
                self.assertTrue(self._esperou_lock_real(pids["np6b-waiter"]))
            finally:
                liberar_lider.set()
            resultados = [lider.result(10), segundo.result(10)]
        self.assertEqual(len(set(pids.values())), 2)
        return resultados

    def test_duplo_avanco_cria_exatamente_um_efeito(self):
        codigo, tokens, rodada_id = self.preparar_resultado()
        with self.sessions() as session:
            versao = session.scalar(
                select(SalaNemPato.estado_versao).where(SalaNemPato.codigo == codigo)
            )
        acao_host = lambda session, service: service.iniciar_proxima_rodada(
            session, codigo, rodada_id, tokens["host"]
        )
        acao_convidado = lambda session, service: service.iniciar_proxima_rodada(
            session, codigo, rodada_id, tokens["p1"]
        )
        resultados = self.corrida(acao_host, acao_convidado)
        self.assertEqual([item[0] for item in resultados].count("accepted"), 1)
        self.assertEqual([item[0] for item in resultados].count("rejected"), 1)
        with self.sessions() as session:
            sala = session.scalar(select(SalaNemPato).where(SalaNemPato.codigo == codigo))
            partida = session.scalar(
                select(PartidaNemPato).where(PartidaNemPato.sala_id == sala.id)
            )
            r2 = session.scalar(
                select(RodadaNemPato).where(
                    RodadaNemPato.partida_id == partida.id,
                    RodadaNemPato.numero == 2,
                )
            )
            iniciadas = session.scalar(
                select(func.count()).select_from(RodadaNemPato).where(
                    RodadaNemPato.partida_id == partida.id,
                    RodadaNemPato.iniciada_em.is_not(None),
                )
            )
        self.assertEqual(partida.rodada_atual, 2)
        self.assertEqual(r2.status, RodadaNemPatoStatus.EM_ANDAMENTO)
        self.assertEqual(iniciadas, 2)
        self.assertEqual(sala.estado_versao, versao + 1)

    def test_avanco_contra_abandono_do_host_serializa(self):
        for abandono_primeiro in (True, False):
            with self.subTest(abandono_primeiro=abandono_primeiro):
                codigo, tokens, rodada_id = self.preparar_resultado(4)
                abandono = lambda session, service: service.abandonar(
                    session, codigo, tokens["host"]
                )
                avanco = lambda session, service: service.iniciar_proxima_rodada(
                    session, codigo, rodada_id, tokens["host"]
                )
                resultados = self.corrida(
                    abandono if abandono_primeiro else avanco,
                    avanco if abandono_primeiro else abandono,
                )
                self.assertEqual(
                    [item[0] for item in resultados], ["accepted", "rejected"]
                )
                with self.sessions() as session:
                    sala = session.scalar(
                        select(SalaNemPato).where(SalaNemPato.codigo == codigo)
                    )
                    partida = session.scalar(
                        select(PartidaNemPato).where(PartidaNemPato.sala_id == sala.id)
                    )
                self.assertEqual(
                    partida.rodada_atual, 1 if abandono_primeiro else 2
                )


if __name__ == "__main__":
    unittest.main()
