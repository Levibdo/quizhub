"""Real PostgreSQL concurrency acceptance tests for NP8."""

import os
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.base import Base  # noqa: F401
from app.models import (
    Categoria, DesafioNemPato, JogadorPartidaNemPato, PalpiteNemPato,
    PartidaNemPato, PerguntaNemPato, RodadaNemPato, SalaNemPato,
)
from app.nem_a_pato import RodadaNemPatoStatus
from app.services.salas_nem_a_pato import SalasNemAPatoService

ENV_NAME = "NEM_A_PATO_TEST_DATABASE_URL"
DATABASE_URL = os.getenv(ENV_NAME, "").strip()


@unittest.skipUnless(DATABASE_URL, f"configure {ENV_NAME} for PostgreSQL integration tests")
class TestNP8PostgresConcurrency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parsed = make_url(DATABASE_URL)
        if parsed.get_backend_name() != "postgresql":
            raise RuntimeError(f"{ENV_NAME} must point to PostgreSQL")
        if not parsed.database or not parsed.database.startswith("np3_test_"):
            raise RuntimeError("refusing non-disposable database; expected np3_test_*")
        if parsed.database == "quiz_estagio_db":
            raise RuntimeError("refusing to connect to development database")
        cls.engine = create_engine(DATABASE_URL, pool_size=8, max_overflow=2,
                                   pool_pre_ping=True,
                                   connect_args={"application_name": "np8-integration-test"})
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

    def preparar_r10(self, com_palpite=True):
        with self.sessions() as session:
            host = self.service.criar(session, f"Host-{uuid4().hex[:8]}")
        tokens = {"host": host.credencial_participante}
        for indice in range(1, 3):
            with self.sessions() as session:
                entrada = self.service.entrar(session, host.sala.codigo, f"P{indice}-{uuid4().hex[:8]}")
                tokens[f"p{indice}"] = entrada.credencial_participante
        with self.sessions() as session:
            if session.get(Categoria, "geral") is None:
                self.fail("base category geral missing")
            session.add_all(PerguntaNemPato(
                categoria_id="geral", enunciado=f"PostgreSQL NP8 {uuid4()}",
                resposta_numerica=600, explicacao="private integration explanation",
                ativa=True,
            ) for _ in range(10))
            session.commit()
        with self.sessions() as session:
            self.service.iniciar(session, host.sala.codigo, tokens["host"])
        with self.sessions() as session:
            self.service.iniciar_rodada(session, host.sala.codigo, tokens["host"])
        with self.sessions() as session:
            sala = session.scalar(select(SalaNemPato).where(SalaNemPato.codigo == host.sala.codigo))
            partida = session.scalar(select(PartidaNemPato).where(PartidaNemPato.sala_id == sala.id))
            jogadores = list(session.scalars(select(JogadorPartidaNemPato).where(JogadorPartidaNemPato.partida_id == partida.id).order_by(JogadorPartidaNemPato.ordem_circular)))
            r1 = session.scalar(select(RodadaNemPato).where(RodadaNemPato.partida_id == partida.id, RodadaNemPato.numero == 1))
            r10 = session.scalar(select(RodadaNemPato).where(RodadaNemPato.partida_id == partida.id, RodadaNemPato.numero == 10))
            agora = datetime.now(timezone.utc)
            r1.status = RodadaNemPatoStatus.RESULTADO
            r10.status = RodadaNemPatoStatus.EM_ANDAMENTO
            r10.jogador_inicial_id = jogadores[0].id
            r10.jogador_da_vez_id = jogadores[0].id
            r10.iniciada_em = agora
            r10.termina_em = agora + timedelta(seconds=120)
            partida.rodada_atual = 10
            session.commit()
            rodada_id = r10.id
        if com_palpite:
            with self.sessions() as session:
                self.service.palpitar(session, host.sala.codigo, rodada_id, tokens["host"], 500, uuid4())
        return host.sala.codigo, tokens, rodada_id

    def expirar(self, rodada_id):
        with self.sessions() as session:
            rodada = session.get(RodadaNemPato, rodada_id)
            agora = datetime.now(timezone.utc)
            rodada.iniciada_em = agora - timedelta(seconds=2)
            rodada.termina_em = agora - timedelta(seconds=1)
            session.commit()

    def corrida(self, codigo, tokens, lider_acao, segundo_acao):
        lider_bloqueou = threading.Event()
        segundo_tentou = threading.Event()
        liberar_lider = threading.Event()
        pids = {}

        class ServicoComLockRetido(SalasNemAPatoService):
            def _sala_bloqueada(inner, db, room_code):
                nome = threading.current_thread().name
                if nome == "np8-waiter":
                    if not lider_bloqueou.wait(10):
                        raise TimeoutError("leader did not lock room")
                    segundo_tentou.set()
                sala = super(ServicoComLockRetido, inner)._sala_bloqueada(db, room_code)
                if nome == "np8-leader":
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
            lider = executor.submit(executar, "np8-leader", lider_acao)
            segundo = executor.submit(executar, "np8-waiter", segundo_acao)
            try:
                self.assertTrue(lider_bloqueou.wait(10))
                self.assertTrue(segundo_tentou.wait(10))
                limite = time.monotonic() + 10
                while time.monotonic() < limite:
                    with self.engine.connect() as observador:
                        esperando = observador.scalar(text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"), {"pid": pids["np8-waiter"]})
                    if esperando:
                        break
                    time.sleep(0.01)
                self.assertTrue(esperando)
            finally:
                liberar_lider.set()
            resultados = [lider.result(10), segundo.result(10)]
        self.assertEqual(len(set(pids.values())), 2)
        return resultados

    def estado(self, codigo):
        with self.sessions() as session:
            sala = session.scalar(select(SalaNemPato).where(SalaNemPato.codigo == codigo))
            partida = session.scalar(select(PartidaNemPato).where(PartidaNemPato.sala_id == sala.id))
            rodada = session.scalar(select(RodadaNemPato).where(RodadaNemPato.partida_id == partida.id, RodadaNemPato.numero == 10))
            jogadores = list(session.scalars(select(JogadorPartidaNemPato).where(JogadorPartidaNemPato.partida_id == partida.id).order_by(JogadorPartidaNemPato.ordem_circular)))
            desafios = list(session.scalars(select(DesafioNemPato).where(DesafioNemPato.rodada_id == rodada.id)))
            return sala, partida, rodada, jogadores, desafios

    def test_r10_polling_concorrente_finaliza_e_penaliza_uma_vez(self):
        codigo, tokens, rodada_id = self.preparar_r10()
        self.expirar(rodada_id)
        with self.sessions() as session:
            versao = session.scalar(select(SalaNemPato.estado_versao).where(SalaNemPato.codigo == codigo))
        resultados = self.corrida(
            codigo, tokens,
            lambda session, service: service.recuperar(session, codigo, tokens["host"]),
            lambda session, service: service.recuperar(session, codigo, tokens["p1"]),
        )
        self.assertEqual([item[0] for item in resultados], ["accepted", "accepted"])
        sala, partida, rodada, jogadores, _ = self.estado(codigo)
        self.assertEqual((sala.status.value, partida.status.value, rodada.status.value), ("ENCERRADA", "FINALIZADA", "RESULTADO"))
        self.assertEqual(sala.estado_versao, versao + 1)
        self.assertEqual([j.patos for j in jogadores], [0, 1, 1])
        def classificacao(estado):
            resultado = estado.partida.resultado_final
            return (
                [(j.nome, j.patos) for j in resultado.vencedores],
                [(j.nome, j.patos) for j in resultado.patos_da_partida],
                resultado.empate_geral,
            )
        self.assertEqual(classificacao(resultados[0][1]), classificacao(resultados[1][1]))

    def test_r10_desafio_contra_timeout_resolve_uma_vez_e_requests_tardios_nao_alteram(self):
        codigo, tokens, rodada_id = self.preparar_r10()
        self.expirar(rodada_id)
        resultados = self.corrida(
            codigo, tokens,
            lambda session, service: service.desafiar(session, codigo, rodada_id, tokens["p1"], uuid4()),
            lambda session, service: service.recuperar(session, codigo, tokens["p2"]),
        )
        self.assertEqual(resultados[0][0], "accepted")
        sala, partida, rodada, jogadores, desafios = self.estado(codigo)
        self.assertEqual((sala.status.value, partida.status.value, rodada.tipo_finalizacao.value), ("ENCERRADA", "FINALIZADA", "TEMPO_ESGOTADO"))
        self.assertEqual(len(desafios), 0)
        patos = [j.patos for j in jogadores]
        versao = sala.estado_versao
        with self.sessions() as session:
            with self.assertRaises(HTTPException):
                self.service.palpitar(session, codigo, rodada_id, tokens["host"], 700, uuid4())
        sala2, _, _, jogadores2, desafios2 = self.estado(codigo)
        self.assertEqual((sala2.estado_versao, [j.patos for j in jogadores2], len(desafios2)), (versao, patos, 0))


if __name__ == "__main__":
    unittest.main()
