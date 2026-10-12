"""Real PostgreSQL concurrency acceptance tests for NP9."""

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
from app.models import (
    Categoria, JogadorPartidaNemPato, PartidaNemPato, PerguntaNemPato,
    RodadaNemPato, SalaNemPato,
)
from app.nem_a_pato import (
    PartidaNemPatoStatus,
    RodadaNemPatoStatus,
    SalaNemPatoStatus,
)
from app.services.salas_nem_a_pato import SalasNemAPatoService

ENV_NAME = "NEM_A_PATO_TEST_DATABASE_URL"
DATABASE_URL = os.getenv(ENV_NAME, "").strip()


@unittest.skipUnless(DATABASE_URL, f"configure {ENV_NAME} for PostgreSQL integration tests")
class TestNP9PostgresConcurrency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parsed = make_url(DATABASE_URL)
        if parsed.get_backend_name() != "postgresql":
            raise RuntimeError(f"{ENV_NAME} must point to PostgreSQL")
        if not parsed.database or not parsed.database.startswith("np3_test_"):
            raise RuntimeError("refusing non-disposable database; expected np3_test_*")
        if parsed.database == "quiz_estagio_db":
            raise RuntimeError("refusing development database")
        cls.engine = create_engine(
            DATABASE_URL, pool_size=8, max_overflow=2, pool_pre_ping=True,
            connect_args={"application_name": "np9-integration-test"},
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

    def preparar_finalizada(self):
        with self.sessions() as session:
            host = self.service.criar(session, f"Host-{uuid4().hex[:8]}")
        tokens = {"host": host.credencial_participante}
        for indice in range(1, 3):
            with self.sessions() as session:
                entrada = self.service.entrar(session, host.sala.codigo, f"P{indice}-{uuid4().hex[:8]}")
                tokens[f"p{indice}"] = entrada.credencial_participante
        with self.sessions() as session:
            categoria_id = CATEGORIAS_OFICIAIS[MODO_NEM_A_PATO]["geral"]
            if session.get(Categoria, categoria_id) is None:
                self.fail("base category geral missing")
            session.add_all(PerguntaNemPato(
                categoria_id=categoria_id, enunciado=f"PostgreSQL NP9 {uuid4()}",
                resposta_numerica=600, explicacao="private integration explanation",
                ativa=True,
            ) for _ in range(30))
            session.commit()
        with self.sessions() as session:
            self.service.iniciar(session, host.sala.codigo, tokens["host"])
        with self.sessions() as session:
            self.service.iniciar_rodada(session, host.sala.codigo, tokens["host"])
        with self.sessions() as session:
            sala = session.scalar(select(SalaNemPato).where(SalaNemPato.codigo == host.sala.codigo))
            partida = session.scalar(select(PartidaNemPato).where(PartidaNemPato.sala_id == sala.id))
            jogadores = list(partida.jogadores)
            r1 = session.scalar(select(RodadaNemPato).where(RodadaNemPato.partida_id == partida.id, RodadaNemPato.numero == 1))
            r10 = session.scalar(select(RodadaNemPato).where(RodadaNemPato.partida_id == partida.id, RodadaNemPato.numero == 10))
            agora = datetime.now(timezone.utc)
            r1.status = RodadaNemPatoStatus.RESULTADO
            r10.status = RodadaNemPatoStatus.EM_ANDAMENTO
            r10.jogador_inicial_id = jogadores[0].id
            r10.jogador_da_vez_id = jogadores[0].id
            r10.iniciada_em = agora - timedelta(seconds=2)
            r10.termina_em = agora - timedelta(seconds=1)
            partida.rodada_atual = 10
            session.commit()
        with self.sessions() as session:
            final = self.service.recuperar(session, host.sala.codigo, tokens["host"])
        return host.sala.codigo, tokens, final

    def corrida(self, codigo, lider_acao, segundo_acao):
        lider_bloqueou = threading.Event()
        segundo_tentou = threading.Event()
        liberar_lider = threading.Event()
        pids = {}

        class ServicoComLockRetido(SalasNemAPatoService):
            def _sala_bloqueada(inner, db, room_code):
                nome = threading.current_thread().name
                if nome == "np9-waiter":
                    if not lider_bloqueou.wait(10):
                        raise TimeoutError("leader did not lock room")
                    segundo_tentou.set()
                sala = super(ServicoComLockRetido, inner)._sala_bloqueada(db, room_code)
                if nome == "np9-leader":
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
            lider = executor.submit(executar, "np9-leader", lider_acao)
            segundo = executor.submit(executar, "np9-waiter", segundo_acao)
            try:
                self.assertTrue(lider_bloqueou.wait(10))
                self.assertTrue(segundo_tentou.wait(10))
                limite = time.monotonic() + 10
                esperando = False
                while time.monotonic() < limite:
                    with self.engine.connect() as observador:
                        esperando = observador.scalar(text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"), {"pid": pids["np9-waiter"]})
                    if esperando:
                        break
                    time.sleep(0.01)
                self.assertTrue(esperando)
            finally:
                liberar_lider.set()
            return [lider.result(10), segundo.result(10)]

    def estado(self, codigo):
        with self.sessions() as session:
            sala = session.scalar(select(SalaNemPato).where(SalaNemPato.codigo == codigo))
            partidas = list(session.scalars(select(PartidaNemPato).where(PartidaNemPato.sala_id == sala.id).order_by(PartidaNemPato.numero)))
            retorno = []
            for partida in partidas:
                jogadores = list(partida.jogadores)
                rodadas = list(session.scalars(select(RodadaNemPato).where(RodadaNemPato.partida_id == partida.id).order_by(RodadaNemPato.numero)))
                retorno.append((partida, jogadores, rodadas))
            return sala, retorno

    def test_duplo_clique_cria_uma_revanche_e_preserva_historico(self):
        codigo, tokens, final = self.preparar_finalizada()
        sala_antes, partidas_antes = self.estado(codigo)
        historico = ([(j.id, j.patos) for j in partidas_antes[0][1]], [r.pergunta_id for r in partidas_antes[0][2]])
        resultados = self.corrida(
            codigo,
            lambda session, service: service.jogar_novamente(session, codigo, tokens["host"]),
            lambda session, service: service.jogar_novamente(session, codigo, tokens["host"]),
        )
        self.assertEqual(sorted(item[0] for item in resultados), ["accepted", "rejected"])
        sala, partidas = self.estado(codigo)
        self.assertEqual(len(partidas), 2)
        self.assertEqual(sum(p.status.value == "EM_ANDAMENTO" for p, _, _ in partidas), 1)
        self.assertEqual((partidas[1][0].numero, len(partidas[1][1]), len(partidas[1][2])), (2, 3, 10))
        self.assertEqual([j.patos for j in partidas[1][1]], [0, 0, 0])
        self.assertEqual(sala.estado_versao, sala_antes.estado_versao + 1)
        self.assertEqual(([(j.id, j.patos) for j in partidas[0][1]], [r.pergunta_id for r in partidas[0][2]]), historico)
        self.assertTrue(set(historico[1]).isdisjoint({r.pergunta_id for r in partidas[1][2]}))

    def test_polling_concorrente_converge_para_nova_partida(self):
        codigo, tokens, _ = self.preparar_finalizada()
        lider_bloqueou = threading.Event()
        liberar_lider = threading.Event()

        class ServicoComRevanchePausada(SalasNemAPatoService):
            def _sala_bloqueada(inner, db, room_code):
                sala = super(ServicoComRevanchePausada, inner)._sala_bloqueada(
                    db, room_code
                )
                if threading.current_thread().name == "np9-revanche":
                    lider_bloqueou.set()
                    if not liberar_lider.wait(10):
                        raise TimeoutError("test did not release revenge transaction")
                return sala

        service = ServicoComRevanchePausada()

        def criar_revanche():
            threading.current_thread().name = "np9-revanche"
            with self.sessions() as session:
                return service.jogar_novamente(session, codigo, tokens["host"])

        with ThreadPoolExecutor(max_workers=1) as executor:
            revanche = executor.submit(criar_revanche)
            try:
                self.assertTrue(lider_bloqueou.wait(10))
                with self.sessions() as session:
                    concorrente = service.recuperar(session, codigo, tokens["p1"])
            finally:
                liberar_lider.set()
            nova = revanche.result(10)

        # A leitura concorrente pode linearizar antes ou depois do commit, mas
        # deve sempre representar uma versao completa do estado.
        self.assertIn(concorrente.partida.numero, (1, 2))
        if concorrente.partida.numero == 1:
            self.assertEqual(
                concorrente.sala.status, SalaNemPatoStatus.ENCERRADA.value
            )
            self.assertEqual(
                concorrente.partida.status, PartidaNemPatoStatus.FINALIZADA.value
            )
        else:
            self.assertEqual(
                concorrente.sala.status, SalaNemPatoStatus.EM_PARTIDA.value
            )
            self.assertEqual(
                concorrente.partida.status, PartidaNemPatoStatus.EM_ANDAMENTO.value
            )

        with self.sessions() as session:
            convergente = service.recuperar(session, codigo, tokens["p1"])
        self.assertEqual(convergente.sala.codigo, nova.sala.codigo)
        self.assertEqual(convergente.partida.id, nova.partida.id)
        self.assertEqual(convergente.partida.numero, 2)
        self.assertEqual([j.patos for j in convergente.partida.jogadores], [0, 0, 0])
        _, partidas = self.estado(codigo)
        self.assertEqual(len(partidas), 2)

    def test_polling_nao_mistura_sala_antiga_com_revanche_confirmada(self):
        codigo, tokens, _ = self.preparar_finalizada()
        sala_lida = threading.Event()
        liberar_leitura = threading.Event()

        class ServicoComLeituraPausada(SalasNemAPatoService):
            pausou = False
            leituras_sala = 0

            def _obter_participante_autenticado(inner, db, room_code, token):
                resultado = super(
                    ServicoComLeituraPausada, inner
                )._obter_participante_autenticado(db, room_code, token)
                inner.leituras_sala += 1
                if (
                    threading.current_thread().name == "np9-leitor-hibrido"
                    and not inner.pausou
                ):
                    inner.pausou = True
                    sala_lida.set()
                    if not liberar_leitura.wait(10):
                        raise TimeoutError("test did not release state reconstruction")
                return resultado

        service = ServicoComLeituraPausada()

        def recuperar_pausado():
            threading.current_thread().name = "np9-leitor-hibrido"
            with self.sessions() as session:
                return service.recuperar(session, codigo, tokens["p1"])

        with ThreadPoolExecutor(max_workers=1) as executor:
            leitura = executor.submit(recuperar_pausado)
            try:
                self.assertTrue(sala_lida.wait(10))
                with self.sessions() as session:
                    revanche = service.jogar_novamente(
                        session, codigo, tokens["host"]
                    )
            finally:
                liberar_leitura.set()
            estado = leitura.result(10)

        self.assertEqual(estado.sala.codigo, revanche.sala.codigo)
        self.assertGreaterEqual(service.leituras_sala, 2)
        self.assertEqual(estado.sala.status, SalaNemPatoStatus.EM_PARTIDA.value)
        self.assertEqual(estado.partida.id, revanche.partida.id)
        self.assertEqual(estado.partida.numero, 2)
        self.assertEqual(
            estado.partida.status, PartidaNemPatoStatus.EM_ANDAMENTO.value
        )
        self.assertEqual(estado.sala.versao, revanche.sala.versao)
        self.assertEqual([j.patos for j in estado.partida.jogadores], [0, 0, 0])

    def test_fallback_compartilhado_bloqueia_quarta_mutacao(self):
        codigo, tokens, inicial = self.preparar_finalizada()
        leituras = [threading.Event() for _ in range(3)]
        liberar_leituras = [threading.Event() for _ in range(3)]
        fallback_montado = threading.Event()
        liberar_fallback = threading.Event()
        quarta_iniciou = threading.Event()
        pid_quarta = {}

        class ServicoComTresConflitos(SalasNemAPatoService):
            tentativa = 0
            em_fallback = False

            def _obter_participante_autenticado(inner, db, room_code, token):
                resultado = super(
                    ServicoComTresConflitos, inner
                )._obter_participante_autenticado(db, room_code, token)
                if (
                    threading.current_thread().name == "np9-leitor-fallback"
                    and inner.tentativa < 3
                ):
                    indice = inner.tentativa
                    inner.tentativa += 1
                    leituras[indice].set()
                    if not liberar_leituras[indice].wait(10):
                        raise TimeoutError("test did not release optimistic read")
                return resultado

            def _recuperar_com_lock_compartilhado(inner, *args, **kwargs):
                inner.em_fallback = True
                try:
                    return super(
                        ServicoComTresConflitos, inner
                    )._recuperar_com_lock_compartilhado(*args, **kwargs)
                finally:
                    inner.em_fallback = False

            def _montar_estado_recuperado(inner, *args, **kwargs):
                estado = super(
                    ServicoComTresConflitos, inner
                )._montar_estado_recuperado(*args, **kwargs)
                if inner.em_fallback:
                    fallback_montado.set()
                    if not liberar_fallback.wait(10):
                        raise TimeoutError("test did not release shared fallback")
                return estado

        service = ServicoComTresConflitos()

        def recuperar_com_conflitos():
            threading.current_thread().name = "np9-leitor-fallback"
            with self.sessions() as session:
                return service.recuperar(session, codigo, tokens["p1"])

        def incrementar_versao():
            with self.sessions() as session:
                sala = session.scalar(
                    select(SalaNemPato)
                    .where(SalaNemPato.codigo == codigo)
                    .with_for_update()
                )
                sala.estado_versao += 1
                session.commit()
                return sala.estado_versao

        def quarta_mutacao():
            threading.current_thread().name = "np9-quarta-mutacao"
            with self.sessions() as session:
                pid_quarta["pid"] = session.scalar(text("SELECT pg_backend_pid()"))
                quarta_iniciou.set()
                sala = session.scalar(
                    select(SalaNemPato)
                    .where(SalaNemPato.codigo == codigo)
                    .with_for_update()
                )
                sala.estado_versao += 1
                session.commit()
                return sala.estado_versao

        with ThreadPoolExecutor(max_workers=2) as executor:
            leitura = executor.submit(recuperar_com_conflitos)
            for indice in range(3):
                self.assertTrue(leituras[indice].wait(10))
                incrementar_versao()
                liberar_leituras[indice].set()

            self.assertTrue(fallback_montado.wait(10))
            quarta = executor.submit(quarta_mutacao)
            self.assertTrue(quarta_iniciou.wait(10))
            limite = time.monotonic() + 10
            esperando = False
            while time.monotonic() < limite:
                with self.engine.connect() as observador:
                    esperando = observador.scalar(
                        text(
                            "SELECT wait_event_type = 'Lock' "
                            "FROM pg_stat_activity WHERE pid = :pid"
                        ),
                        {"pid": pid_quarta["pid"]},
                    )
                if esperando:
                    break
                time.sleep(0.01)
            self.assertTrue(esperando)
            liberar_fallback.set()
            estado_fallback = leitura.result(10)
            versao_final = quarta.result(10)

        self.assertEqual(service.tentativa, 3)
        self.assertEqual(
            estado_fallback.sala.versao,
            inicial.sala.versao + 3,
        )
        self.assertEqual(versao_final, inicial.sala.versao + 4)
        self.assertEqual(
            estado_fallback.sala.status,
            SalaNemPatoStatus.ENCERRADA.value,
        )
        self.assertEqual(
            estado_fallback.partida.status,
            PartidaNemPatoStatus.FINALIZADA.value,
        )
        with self.sessions() as session:
            convergente = service.recuperar(session, codigo, tokens["p1"])
        self.assertEqual(convergente.sala.versao, versao_final)


if __name__ == "__main__":
    unittest.main()
