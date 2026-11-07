import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.conteudo import CATEGORIAS_OFICIAIS, MODO_QUIZ_CLASSICO
from app.db.base import Base
from app.db.seed import seed_database
from app.models import CatalogoOficial, Partida, PartidaPergunta, Pergunta, Resposta
from app.services.partidas import PartidasPersistentes


URL = os.getenv("CLASSIC_RECOVERY_TEST_DATABASE_URL", "").strip()
NAME = os.getenv("CLASSIC_RECOVERY_TEST_DATABASE_NAME", "").strip()


@unittest.skipUnless(URL and NAME, "configure PostgreSQL descartável de recuperação clássica")
class TestRecuperacaoClassicaPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(URL)
        if (
            url.get_backend_name() != "postgresql"
            or url.host not in {"127.0.0.1", "localhost"}
            or url.port in {None, 5432}
            or url.database != NAME
            or not NAME.startswith("quizhub_classic_recovery_test_")
        ):
            raise RuntimeError("exige PostgreSQL descartável local fora da porta 5432")
        cls.engine = create_engine(URL, pool_size=6, max_overflow=2, pool_pre_ping=True)
        cls.sessions = sessionmaker(cls.engine, expire_on_commit=False)
        Base.metadata.drop_all(cls.engine)
        Base.metadata.create_all(cls.engine)
        with cls.sessions() as db:
            seed_database(db)
            catalogo = CatalogoOficial(
                catalogo_id="quiz-classico-concorrencia",
                versao=1,
                modo=MODO_QUIZ_CLASSICO,
                status="ATIVO",
                sha256="c" * 64,
            )
            db.add(catalogo)
            db.flush()
            for pergunta in db.scalars(select(Pergunta).where(Pergunta.origem == "OFICIAL")):
                pergunta.catalogo_oficial_id = catalogo.id
                pergunta.id_editorial = f"PG-{pergunta.id}"
            proximo_id = (db.scalar(select(func.max(Pergunta.id))) or 0) + 1
            for numero in range(15):
                db.add(Pergunta(
                    id=proximo_id + numero,
                    categoria_id=CATEGORIAS_OFICIAIS[MODO_QUIZ_CLASSICO]["tecnologia"],
                    enunciado=f"Pergunta PostgreSQL {numero}",
                    alternativa_a="A", alternativa_b="B", alternativa_c="C", alternativa_d="D",
                    alternativa_correta=0,
                    explicacao="Explicação de integração PostgreSQL.",
                    catalogo_oficial_id=catalogo.id,
                    id_editorial=f"PG-{proximo_id + numero}",
                ))
            db.commit()
        cls.agora = datetime(2026, 11, 7, 15, 0, tzinfo=timezone.utc)
        cls.servico = PartidasPersistentes(lambda: cls.agora)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def _criar(self):
        visitante_id = uuid4()
        with self.sessions() as db:
            criada = self.servico.criar(
                db, "Concorrência", "tecnologia", visitante_id=visitante_id
            )
        return criada, visitante_id

    def test_duas_respostas_concorrentes_persistem_uma_unica_resposta(self):
        criada, visitante_id = self._criar()
        barreira = Barrier(2)

        def responder():
            try:
                with self.sessions() as db:
                    barreira.wait(timeout=5)
                    resultado = self.servico.responder(
                        db, criada.partida_id, criada.pergunta_atual.id, 0,
                        None, visitante_id,
                    )
                    return resultado.pontos_ganhos
            except HTTPException as erro:
                return erro.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(lambda _: responder(), range(2)))

        self.assertEqual(sum(isinstance(item, int) and item == 409 for item in resultados), 1)
        with self.sessions() as db:
            partida = db.get(Partida, UUID(criada.partida_id))
            respostas = db.scalar(
                select(func.count())
                .select_from(Resposta)
                .join(PartidaPergunta)
                .where(PartidaPergunta.partida_id == UUID(criada.partida_id))
            )
            self.assertEqual(respostas, 1)
            self.assertEqual(partida.acertos + partida.erros, 1)
            self.assertEqual(partida.pontuacao, max(item for item in resultados if item != 409))

    def test_resposta_e_avanco_simultaneos_nao_corrompem_transicao(self):
        criada, visitante_id = self._criar()
        barreira = Barrier(2)

        def executar(operacao):
            try:
                with self.sessions() as db:
                    barreira.wait(timeout=5)
                    if operacao == "responder":
                        self.servico.responder(
                            db, criada.partida_id, criada.pergunta_atual.id, 0,
                            None, visitante_id,
                        )
                    else:
                        self.servico.avancar(
                            db, criada.partida_id, criada.pergunta_atual.id,
                            None, visitante_id,
                        )
                    return 200
            except HTTPException as erro:
                return erro.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(executar, ("responder", "avancar")))

        self.assertIn(resultados, ([200, 200], [200, 409]))
        with self.sessions() as db:
            ocorrencias = list(db.scalars(
                select(PartidaPergunta)
                .where(PartidaPergunta.partida_id == UUID(criada.partida_id))
                .order_by(PartidaPergunta.ordem)
            ))
            respostas = db.scalar(
                select(func.count())
                .select_from(Resposta)
                .join(PartidaPergunta)
                .where(PartidaPergunta.partida_id == UUID(criada.partida_id))
            )
            self.assertEqual(respostas, 1)
            disponibilizadas = [item for item in ocorrencias if item.disponibilizada_em is not None]
            self.assertIn(len(disponibilizadas), (1, 2))
            self.assertIsNotNone(ocorrencias[0].resposta)
            if len(disponibilizadas) == 2:
                self.assertEqual(disponibilizadas[1].ordem, 2)
                self.assertIsNotNone(disponibilizadas[1].prazo_resposta_em)
