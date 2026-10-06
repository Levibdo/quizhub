"""Concorrência PostgreSQL real do CRUD manual de perguntas C1.2C."""

import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.conteudo import MODO_NEM_A_PATO, MODO_QUIZ_CLASSICO, ORIGEM_USUARIO
from app.db.base import Base  # noqa: F401
from app.models import Categoria, Pergunta, PerguntaNemPato, Usuario
from app.schemas.meu_conteudo_perguntas import (
    PerguntaClassicaCriar,
    PerguntaNemPatoCriar,
)
from app.services.meu_conteudo_categorias import (
    CategoriaComPerguntas,
    meu_conteudo_categorias_service,
)
from app.services.meu_conteudo_perguntas import (
    CategoriaPerguntaIndisponivel,
    QuotaPerguntasAtingida,
    meu_conteudo_perguntas_service,
)


ENV_NAME = "C12C_TEST_DATABASE_URL"
DATABASE_URL = os.getenv(ENV_NAME, "").strip()


@unittest.skipUnless(DATABASE_URL, f"configure {ENV_NAME} para PostgreSQL")
class TestC12CPostgresConcurrency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(DATABASE_URL)
        nome_esperado = os.getenv("C12C_TEST_DATABASE_NAME", "").strip()
        if url.get_backend_name() != "postgresql":
            raise RuntimeError(f"{ENV_NAME} deve apontar para PostgreSQL")
        if (
            not url.database or "_test_" not in url.database
            or url.database == "quiz_estagio_db"
            or nome_esperado != url.database
        ):
            raise RuntimeError("recusando banco não temporário explicitamente confirmado")
        cls.engine = create_engine(DATABASE_URL, pool_size=6, pool_pre_ping=True)
        cls.sessions = sessionmaker(bind=cls.engine, expire_on_commit=False)
        with cls.engine.connect() as conexao:
            atual = conexao.scalar(text("SELECT current_database()"))
            revisao = conexao.scalar(text("SELECT version_num FROM alembic_version"))
        if atual != nome_esperado or revisao != "0011":
            cls.engine.dispose()
            raise RuntimeError(f"banco/revisão inesperados: {atual!r}, {revisao!r}")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.usuario_ids = []
        self.categoria_ids = []

    def tearDown(self):
        with self.sessions() as db:
            db.query(Pergunta).filter(Pergunta.usuario_id.in_(self.usuario_ids)).delete(
                synchronize_session=False
            )
            db.query(PerguntaNemPato).filter(
                PerguntaNemPato.usuario_id.in_(self.usuario_ids)
            ).delete(synchronize_session=False)
            db.query(Categoria).filter(Categoria.id.in_(self.categoria_ids)).delete(
                synchronize_session=False
            )
            db.query(Usuario).filter(Usuario.id.in_(self.usuario_ids)).delete(
                synchronize_session=False
            )
            db.commit()

    def criar_usuario_categoria(self, modo):
        usuario_id = uuid4()
        categoria_id = uuid4()
        self.usuario_ids.append(usuario_id)
        self.categoria_ids.append(categoria_id)
        with self.sessions() as db:
            db.add(Usuario(
                id=usuario_id, nome="C12C", email=f"c12c-{usuario_id}@example.com",
                senha_hash="hash",
            ))
            db.flush()
            db.add(Categoria(
                id=categoria_id, slug=f"c12c-{categoria_id.hex[:8]}", nome="C12C",
                modo=modo, origem=ORIGEM_USUARIO, usuario_id=usuario_id, ativa=True,
            ))
            db.commit()
        return usuario_id, categoria_id

    def test_quota_199_mais_duas_criacoes_resulta_em_200(self):
        usuario_id, categoria_id = self.criar_usuario_categoria(MODO_NEM_A_PATO)
        with self.sessions() as db:
            db.add_all(PerguntaNemPato(
                categoria_id=categoria_id, enunciado=f"Base {indice}",
                resposta_numerica=indice, explicacao="E", origem=ORIGEM_USUARIO,
                usuario_id=usuario_id,
            ) for indice in range(199))
            db.commit()
        barreira = threading.Barrier(2)

        def criar(indice):
            barreira.wait(timeout=10)
            try:
                with self.sessions() as db:
                    meu_conteudo_perguntas_service.criar_nem_pato(
                        db, usuario_id, PerguntaNemPatoCriar(
                            categoria_id=categoria_id, enunciado=f"Concorrente {indice}",
                            resposta_numerica=indice, explicacao="E",
                        )
                    )
                return "sucesso"
            except QuotaPerguntasAtingida:
                return "quota"

        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(executor.map(criar, (1, 2)))
        self.assertCountEqual(resultados, ["sucesso", "quota"])
        with self.sessions() as db:
            total = db.scalar(select(func.count(PerguntaNemPato.id)).where(
                PerguntaNemPato.usuario_id == usuario_id,
                PerguntaNemPato.excluida_em.is_(None),
            ))
        self.assertEqual(total, 200)

    def test_delete_categoria_concorre_com_criacao_sem_estado_inconsistente(self):
        usuario_id, categoria_id = self.criar_usuario_categoria(MODO_NEM_A_PATO)
        barreira = threading.Barrier(2)

        def excluir():
            barreira.wait(timeout=10)
            try:
                with self.sessions() as db:
                    meu_conteudo_categorias_service.excluir(
                        db, usuario_id, categoria_id
                    )
                return "delete"
            except CategoriaComPerguntas:
                return "delete-bloqueado"

        def criar():
            barreira.wait(timeout=10)
            try:
                with self.sessions() as db:
                    meu_conteudo_perguntas_service.criar_nem_pato(
                        db, usuario_id, PerguntaNemPatoCriar(
                            categoria_id=categoria_id, enunciado="Corrida",
                            resposta_numerica=1, explicacao="E",
                        )
                    )
                return "create"
            except CategoriaPerguntaIndisponivel:
                return "create-bloqueado"

        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = [executor.submit(excluir), executor.submit(criar)]
            resultados = [futuro.result(timeout=20) for futuro in resultados]
        self.assertIn(
            resultados,
            (["delete", "create-bloqueado"], ["delete-bloqueado", "create"]),
        )
        with self.sessions() as db:
            categoria = db.get(Categoria, categoria_id)
            perguntas_ativas = db.scalar(select(func.count(PerguntaNemPato.id)).where(
                PerguntaNemPato.categoria_id == categoria_id,
                PerguntaNemPato.excluida_em.is_(None),
            ))
        self.assertFalse(categoria.excluida_em is not None and perguntas_ativas)

    def test_ids_classicos_concorrentes_sao_distintos(self):
        usuario_a, categoria_a = self.criar_usuario_categoria(MODO_QUIZ_CLASSICO)
        usuario_b, categoria_b = self.criar_usuario_categoria(MODO_QUIZ_CLASSICO)
        barreira = threading.Barrier(2)

        def criar(dados):
            usuario_id, categoria_id = dados
            barreira.wait(timeout=10)
            with self.sessions() as db:
                pergunta = meu_conteudo_perguntas_service.criar_classica(
                    db, usuario_id, PerguntaClassicaCriar(
                        categoria_id=categoria_id, enunciado="Concorrente",
                        alternativa_a="A", alternativa_b="B", alternativa_c="C",
                        alternativa_d="D", alternativa_correta="A", explicacao="E",
                    )
                )
                return pergunta.id

        with ThreadPoolExecutor(max_workers=2) as executor:
            ids = list(executor.map(criar, ((usuario_a, categoria_a), (usuario_b, categoria_b))))
        self.assertEqual(len(set(ids)), 2)


if __name__ == "__main__":
    unittest.main()
