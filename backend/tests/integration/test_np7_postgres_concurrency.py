"""Real PostgreSQL concurrency acceptance tests for NP7."""

import os
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.conteudo import CATEGORIAS_OFICIAIS, MODO_NEM_A_PATO
from app.db.base import Base  # noqa: F401
from app.models import (Categoria, DesafioNemPato, JogadorPartidaNemPato, PalpiteNemPato, PartidaNemPato, PerguntaNemPato, RodadaNemPato, SalaNemPato)
from app.nem_a_pato import RodadaNemPatoStatus
from app.services.salas_nem_a_pato import SalasNemAPatoService

ENV_NAME = "NEM_A_PATO_TEST_DATABASE_URL"
DATABASE_URL = os.getenv(ENV_NAME, "").strip()


@unittest.skipUnless(DATABASE_URL, f"configure {ENV_NAME} for PostgreSQL integration tests")
class TestNP7PostgresConcurrency(unittest.TestCase):
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
            connect_args={"application_name": "np7-integration-test"},
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

    def preparar(self, quantidade=3, com_palpite=True):
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
                    enunciado=f"PostgreSQL NP7 {uuid4()}",
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
            estado = self.service.iniciar_rodada(
                session, host.sala.codigo, tokens["host"]
            )
        rodada_id = estado.partida.rodada.id
        if com_palpite:
            with self.sessions() as session:
                self.service.palpitar(
                    session, host.sala.codigo, rodada_id,
                    tokens["host"], 500, uuid4(),
                )
        return host.sala.codigo, tokens, rodada_id

    def expirar(self, rodada_id):
        with self.sessions() as session:
            rodada = session.get(RodadaNemPato, rodada_id)
            agora = datetime.now(timezone.utc)
            rodada.iniciada_em = agora - timedelta(seconds=2)
            rodada.termina_em = agora - timedelta(seconds=1)
            session.commit()

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
                if nome == "np7-waiter":
                    if not lider_bloqueou.wait(10):
                        raise TimeoutError("leader did not lock room")
                    segundo_tentou.set()
                sala = super(ServicoComLockRetido, inner)._sala_bloqueada(db, codigo)
                if nome == "np7-leader":
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
            lider = executor.submit(executar, "np7-leader", lider_acao)
            segundo = executor.submit(executar, "np7-waiter", segundo_acao)
            try:
                self.assertTrue(lider_bloqueou.wait(10))
                self.assertTrue(segundo_tentou.wait(10))
                self.assertTrue(self._esperou_lock_real(pids["np7-waiter"]))
            finally:
                liberar_lider.set()
            resultados = [lider.result(10), segundo.result(10)]
        self.assertEqual(len(set(pids.values())), 2)
        return resultados

    def estado(self, codigo):
        with self.sessions() as session:
            sala = session.scalar(select(SalaNemPato).where(SalaNemPato.codigo == codigo))
            partida = session.scalar(select(PartidaNemPato).where(PartidaNemPato.sala_id == sala.id))
            rodada = session.scalar(select(RodadaNemPato).where(RodadaNemPato.partida_id == partida.id, RodadaNemPato.numero == partida.rodada_atual))
            jogadores = list(session.scalars(select(JogadorPartidaNemPato).where(JogadorPartidaNemPato.partida_id == partida.id).order_by(JogadorPartidaNemPato.ordem_circular)))
            palpites = list(session.scalars(select(PalpiteNemPato).where(PalpiteNemPato.rodada_id == rodada.id)))
            desafios = list(session.scalars(select(DesafioNemPato).where(DesafioNemPato.rodada_id == rodada.id)))
            return sala, rodada, jogadores, palpites, desafios

    def test_polling_concorrente_finaliza_uma_vez(self):
        codigo, tokens, rodada_id = self.preparar()
        self.expirar(rodada_id)
        with self.sessions() as session:
            versao = session.scalar(select(SalaNemPato.estado_versao).where(SalaNemPato.codigo == codigo))
        resultados = self.corrida(
            lambda session, service: service.recuperar(session, codigo, tokens["host"]),
            lambda session, service: service.recuperar(session, codigo, tokens["p1"]),
        )
        self.assertEqual([item[0] for item in resultados], ["accepted", "accepted"])
        sala, rodada, jogadores, _, _ = self.estado(codigo)
        self.assertEqual(rodada.status, RodadaNemPatoStatus.RESULTADO)
        self.assertEqual(sala.estado_versao, versao + 1)
        self.assertEqual([j.patos for j in jogadores], [0, 1, 1])

    def test_palpite_e_desafio_nas_duas_fronteiras(self):
        codigo, tokens, rodada_id = self.preparar(com_palpite=False)
        with self.sessions() as session:
            self.service.palpitar(session, codigo, rodada_id, tokens["host"], 400, uuid4())
        self.expirar(rodada_id)
        with self.sessions() as session:
            self.service.palpitar(session, codigo, rodada_id, tokens["p1"], 500, uuid4())
        _, rodada, _, palpites, _ = self.estado(codigo)
        self.assertEqual(rodada.tipo_finalizacao.value, "TEMPO_ESGOTADO")
        self.assertEqual([p.valor for p in palpites], [400])

        codigo2, tokens2, rodada2 = self.preparar()
        with self.sessions() as session:
            self.service.desafiar(session, codigo2, rodada2, tokens2["p1"], uuid4())
        self.expirar(rodada2)
        with self.sessions() as session:
            estado = self.service.recuperar(session, codigo2, tokens2["host"] )
        self.assertEqual(estado.partida.rodada.tipo_finalizacao, "DESAFIO")

        codigo3, tokens3, rodada3 = self.preparar()
        self.expirar(rodada3)
        with self.sessions() as session:
            self.service.desafiar(session, codigo3, rodada3, tokens3["p1"], uuid4())
        _, rodada, _, _, desafios = self.estado(codigo3)
        self.assertEqual(rodada.tipo_finalizacao.value, "TEMPO_ESGOTADO")
        self.assertEqual(desafios, [])

    def test_seis_jogadores_penaliza_exatamente_cinco(self):
        codigo, tokens, rodada_id = self.preparar(6)
        self.expirar(rodada_id)
        with self.sessions() as session:
            self.service.recuperar(session, codigo, tokens["p5"] )
        _, _, jogadores, _, _ = self.estado(codigo)
        self.assertEqual(sum(j.patos for j in jogadores), 5)
        self.assertEqual([j.patos for j in jogadores], [0, 1, 1, 1, 1, 1])


if __name__ == "__main__":
    unittest.main()
