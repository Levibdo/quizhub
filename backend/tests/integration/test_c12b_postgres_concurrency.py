"""Concorrência e unicidade PostgreSQL reais do CRUD de categorias C1.2B."""

import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.conteudo import MODO_QUIZ_CLASSICO, ORIGEM_USUARIO
from app.db.base import Base  # noqa: F401
from app.models import Categoria, Usuario
from app.schemas.meu_conteudo import CategoriaUsuarioCriar
from app.services.meu_conteudo_categorias import (
    NomeCategoriaDuplicado,
    QuotaCategoriasAtingida,
    meu_conteudo_categorias_service,
)


ENV_NAME = "C12B_TEST_DATABASE_URL"
DATABASE_URL = os.getenv(ENV_NAME, "").strip()


@unittest.skipUnless(DATABASE_URL, f"configure {ENV_NAME} para PostgreSQL")
class TestC12BPostgresConcurrency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(DATABASE_URL)
        if url.get_backend_name() != "postgresql":
            raise RuntimeError(f"{ENV_NAME} deve apontar para PostgreSQL")
        if (
            not url.database
            or "_test_" not in url.database
            or url.database == "quiz_estagio_db"
        ):
            raise RuntimeError("recusando banco não temporário explicitamente autorizado")
        nome_esperado = os.getenv("C12B_TEST_DATABASE_NAME", "").strip()
        if not nome_esperado or nome_esperado != url.database:
            raise RuntimeError("C12B_TEST_DATABASE_NAME deve confirmar exatamente o banco")
        cls.engine = create_engine(DATABASE_URL, pool_size=4, pool_pre_ping=True)
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
        self.usuario_id = uuid4()
        with self.sessions() as db:
            db.add(Usuario(
                id=self.usuario_id,
                nome="C12B concorrência",
                email=f"c12b-{self.usuario_id}@example.com",
                senha_hash="hash",
            ))
            db.commit()

    def tearDown(self):
        with self.sessions() as db:
            db.query(Categoria).filter(Categoria.usuario_id == self.usuario_id).delete()
            db.query(Usuario).filter(Usuario.id == self.usuario_id).delete()
            db.commit()

    def test_nove_mais_duas_criacoes_resultam_em_dez(self):
        with self.sessions() as db:
            for indice in range(9):
                dados = CategoriaUsuarioCriar(
                    nome=f"Categoria {indice}", modo=MODO_QUIZ_CLASSICO
                )
                meu_conteudo_categorias_service.criar(db, self.usuario_id, dados)

        barreira = threading.Barrier(2)

        def criar(indice):
            barreira.wait(timeout=10)
            try:
                with self.sessions() as db:
                    meu_conteudo_categorias_service.criar(
                        db,
                        self.usuario_id,
                        CategoriaUsuarioCriar(
                            nome=f"Concorrente {indice}", modo=MODO_QUIZ_CLASSICO
                        ),
                    )
                return "sucesso"
            except QuotaCategoriasAtingida:
                return "quota"

        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(executor.map(criar, (1, 2)))
        self.assertCountEqual(resultados, ["sucesso", "quota"])
        with self.sessions() as db:
            total = db.scalar(select(func.count(Categoria.id)).where(
                Categoria.usuario_id == self.usuario_id,
                Categoria.origem == ORIGEM_USUARIO,
                Categoria.modo == MODO_QUIZ_CLASSICO,
                Categoria.excluida_em.is_(None),
            ))
        self.assertEqual(total, 10)

    def test_indice_parcial_lower_trim_e_acento(self):
        with self.sessions() as db:
            meu_conteudo_categorias_service.criar(
                db,
                self.usuario_id,
                CategoriaUsuarioCriar(nome="Ciência", modo=MODO_QUIZ_CLASSICO),
            )
        with self.sessions() as db:
            with self.assertRaises(NomeCategoriaDuplicado):
                meu_conteudo_categorias_service.criar(
                    db,
                    self.usuario_id,
                    CategoriaUsuarioCriar(nome=" CIÊNCIA ", modo=MODO_QUIZ_CLASSICO),
                )
        with self.sessions() as db:
            criada = meu_conteudo_categorias_service.criar(
                db,
                self.usuario_id,
                CategoriaUsuarioCriar(nome="Ciencia", modo=MODO_QUIZ_CLASSICO),
            )
        self.assertEqual(criada.nome, "Ciencia")


if __name__ == "__main__":
    unittest.main()
