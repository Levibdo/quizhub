"""Concorrência PostgreSQL real da importação privada C1.3B."""

import json
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.conteudo import MODO_NEM_A_PATO, MODO_QUIZ_CLASSICO, ORIGEM_USUARIO
from app.db.base import Base  # noqa: F401
from app.models import Categoria, Pergunta, PerguntaNemPato, Usuario
from app.services.meu_conteudo_categorias import (
    CategoriaComPerguntas,
    meu_conteudo_categorias_service,
)
from app.services.meu_conteudo_importacoes import (
    ConflitoImportacaoPrivada,
    QuotaImportacaoPrivadaAlterada,
    meu_conteudo_importacoes_service,
)


ENV_NAME = "C13B_TEST_DATABASE_URL"
DATABASE_URL = os.getenv(ENV_NAME, "").strip()


@unittest.skipUnless(DATABASE_URL, f"configure {ENV_NAME} para PostgreSQL")
class TestC13BPostgresConcurrency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(DATABASE_URL)
        esperado = os.getenv("C13B_TEST_DATABASE_NAME", "").strip()
        if url.get_backend_name() != "postgresql":
            raise RuntimeError(f"{ENV_NAME} deve apontar para PostgreSQL")
        if (
            not url.database or "_test_" not in url.database
            or url.database == "quiz_estagio_db" or esperado != url.database
        ):
            raise RuntimeError("recusando banco não temporário explicitamente confirmado")
        cls.engine = create_engine(DATABASE_URL, pool_size=8, pool_pre_ping=True)
        cls.sessions = sessionmaker(bind=cls.engine, expire_on_commit=False)
        with cls.engine.connect() as conexao:
            atual = conexao.scalar(text("SELECT current_database()"))
            revisao = conexao.scalar(text("SELECT version_num FROM alembic_version"))
        if atual != esperado or revisao != "0011":
            cls.engine.dispose()
            raise RuntimeError(f"banco/revisão inesperados: {atual!r}, {revisao!r}")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.usuarios = []
        self.categorias = []
        self.env = patch.dict(os.environ, {"JWT_SECRET": "c13b-postgresql-segredo-32-bytes-minimo"})
        self.env.start()

    def tearDown(self):
        with self.sessions() as db:
            db.query(Pergunta).filter(Pergunta.usuario_id.in_(self.usuarios)).delete(
                synchronize_session=False
            )
            db.query(PerguntaNemPato).filter(
                PerguntaNemPato.usuario_id.in_(self.usuarios)
            ).delete(synchronize_session=False)
            db.query(Categoria).filter(Categoria.id.in_(self.categorias)).delete(
                synchronize_session=False
            )
            db.query(Usuario).filter(Usuario.id.in_(self.usuarios)).delete(
                synchronize_session=False
            )
            db.commit()
        self.env.stop()

    def criar_contexto(self, modo):
        usuario_id, categoria_id = uuid4(), uuid4()
        self.usuarios.append(usuario_id)
        self.categorias.append(categoria_id)
        with self.sessions() as db:
            db.add(Usuario(
                id=usuario_id, nome="C13B",
                email=f"c13b-{usuario_id}@example.com", senha_hash="hash",
            ))
            db.flush()
            db.add(Categoria(
                id=categoria_id, slug=f"c13b-{categoria_id.hex[:8]}",
                nome="C13B", modo=modo, origem=ORIGEM_USUARIO,
                usuario_id=usuario_id, ativa=True,
            ))
            db.commit()
        return usuario_id, categoria_id

    @staticmethod
    def lote(modo, categoria_id, prefixo, quantidade):
        if modo == MODO_QUIZ_CLASSICO:
            itens = [{
                "categoria_id": str(categoria_id), "enunciado": f"{prefixo} {i}",
                "alternativa_a": "A", "alternativa_b": "B",
                "alternativa_c": "C", "alternativa_d": "D",
                "alternativa_correta": "A", "explicacao": "E",
            } for i in range(quantidade)]
        else:
            itens = [{
                "categoria_id": str(categoria_id), "enunciado": f"{prefixo} {i}",
                "resposta_numerica": i, "explicacao": "E",
                "unidade": None, "fonte": None,
            } for i in range(quantidade)]
        return json.dumps(itens).encode()

    def popular(self, modo, usuario_id, categoria_id, quantidade):
        with self.sessions() as db:
            if modo == MODO_QUIZ_CLASSICO:
                db.execute(text("LOCK TABLE perguntas IN SHARE ROW EXCLUSIVE MODE"))
                inicio = (db.scalar(select(func.max(Pergunta.id))) or 0) + 1
                db.add_all(Pergunta(
                    id=inicio + i, categoria_id=categoria_id,
                    enunciado=f"Base {i}", alternativa_a="A", alternativa_b="B",
                    alternativa_c="C", alternativa_d="D", alternativa_correta=0,
                    explicacao="E", origem=ORIGEM_USUARIO, usuario_id=usuario_id,
                ) for i in range(quantidade))
            else:
                db.add_all(PerguntaNemPato(
                    categoria_id=categoria_id, enunciado=f"Base {i}",
                    resposta_numerica=i, explicacao="E",
                    origem=ORIGEM_USUARIO, usuario_id=usuario_id,
                ) for i in range(quantidade))
            db.commit()

    def confirmar_concorrente(self, modo):
        usuario_id, categoria_id = self.criar_contexto(modo)
        self.popular(modo, usuario_id, categoria_id, 150)
        lotes = [self.lote(modo, categoria_id, prefixo, 40) for prefixo in ("A", "B")]
        tokens = []
        for lote in lotes:
            with self.sessions() as db:
                tokens.append(meu_conteudo_importacoes_service.validar(
                    db, usuario_id, modo, "lote.json", lote
                ).token_preview)
        barreira = threading.Barrier(2)

        def confirmar(indice):
            barreira.wait(timeout=10)
            try:
                with self.sessions() as db:
                    meu_conteudo_importacoes_service.confirmar(
                        db, usuario_id, tokens[indice], "lote.json", lotes[indice]
                    )
                return "sucesso"
            except QuotaImportacaoPrivadaAlterada:
                return "quota"

        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(executor.map(confirmar, (0, 1)))
        self.assertCountEqual(resultados, ["sucesso", "quota"])
        modelo = Pergunta if modo == MODO_QUIZ_CLASSICO else PerguntaNemPato
        with self.sessions() as db:
            total = db.scalar(select(func.count(modelo.id)).where(
                modelo.usuario_id == usuario_id,
                modelo.excluida_em.is_(None),
            ))
            importadas = db.scalar(select(func.count(modelo.id)).where(
                modelo.usuario_id == usuario_id,
                modelo.enunciado.like("A %") | modelo.enunciado.like("B %"),
            ))
        self.assertEqual((total, importadas), (190, 40))

    def test_quota_classic_150_mais_40_mais_40(self):
        self.confirmar_concorrente(MODO_QUIZ_CLASSICO)

    def test_quota_np_150_mais_40_mais_40(self):
        self.confirmar_concorrente(MODO_NEM_A_PATO)

    def test_duas_importacoes_classic_de_usuarios_distintos_nao_colidem_ids(self):
        contextos = [self.criar_contexto(MODO_QUIZ_CLASSICO) for _ in range(2)]
        lotes = [
            self.lote(MODO_QUIZ_CLASSICO, categoria, f"U{indice}", 20)
            for indice, (_, categoria) in enumerate(contextos)
        ]
        tokens = []
        for (usuario, _), lote in zip(contextos, lotes):
            with self.sessions() as db:
                tokens.append(meu_conteudo_importacoes_service.validar(
                    db, usuario, MODO_QUIZ_CLASSICO, "lote.json", lote
                ).token_preview)
        barreira = threading.Barrier(2)

        def confirmar(indice):
            barreira.wait(timeout=10)
            with self.sessions() as db:
                return meu_conteudo_importacoes_service.confirmar(
                    db, contextos[indice][0], tokens[indice], "lote.json", lotes[indice]
                ).criadas

        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(executor.map(confirmar, (0, 1)))
        self.assertEqual(resultados, [20, 20])
        with self.sessions() as db:
            ids = list(db.scalars(select(Pergunta.id).where(
                Pergunta.usuario_id.in_([usuario for usuario, _ in contextos])
            )))
        self.assertEqual(len(ids), 40)
        self.assertEqual(len(set(ids)), 40)

    def test_delete_categoria_concorre_com_confirmacao_sem_orfandade(self):
        usuario, categoria = self.criar_contexto(MODO_NEM_A_PATO)
        lote = self.lote(MODO_NEM_A_PATO, categoria, "Delete", 10)
        with self.sessions() as db:
            token = meu_conteudo_importacoes_service.validar(
                db, usuario, MODO_NEM_A_PATO, "lote.json", lote
            ).token_preview
        barreira = threading.Barrier(2)

        def confirmar():
            barreira.wait(timeout=10)
            try:
                with self.sessions() as db:
                    meu_conteudo_importacoes_service.confirmar(
                        db, usuario, token, "lote.json", lote
                    )
                return "importou"
            except ConflitoImportacaoPrivada:
                return "conflito"

        def excluir():
            barreira.wait(timeout=10)
            try:
                with self.sessions() as db:
                    meu_conteudo_categorias_service.excluir(db, usuario, categoria)
                return "excluiu"
            except CategoriaComPerguntas:
                return "com_perguntas"

        with ThreadPoolExecutor(max_workers=2) as executor:
            futuro_importar = executor.submit(confirmar)
            futuro_excluir = executor.submit(excluir)
            resultados = {futuro_importar.result(), futuro_excluir.result()}
        self.assertIn(resultados, ({"importou", "com_perguntas"}, {"conflito", "excluiu"}))
        with self.sessions() as db:
            categoria_db = db.get(Categoria, categoria)
            total = db.scalar(select(func.count(PerguntaNemPato.id)).where(
                PerguntaNemPato.usuario_id == usuario
            ))
        self.assertTrue(
            (categoria_db.excluida_em is None and total == 10)
            or (categoria_db.excluida_em is not None and total == 0)
        )
