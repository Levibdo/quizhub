"""PostgreSQL 16 regression for Nem a Pato editorial metadata (0016 <-> 0017)."""

import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.db.base import Base  # noqa: F401 - register models before package exports
from app.models import (
    CatalogoOficial,
    FontePerguntaNemPatoOficial,
    PerguntaNemPato,
)
from app.services.catalogos_oficiais import CatalogosOficiaisService
from app.services.validador_catalogos_oficiais import CatalogoNemPatoEditorial


URL_ENV = "NEM_PATO_EDITORIAL_TEST_DATABASE_URL"
NAME_ENV = "NEM_PATO_EDITORIAL_TEST_DATABASE_NAME"
DATABASE_URL = os.getenv(URL_ENV, "").strip()
AUTHORIZED_DATABASE = os.getenv(NAME_ENV, "").strip()
AUTHORIZED_NAME = re.compile(r"^quizhub_nem_editorial_test_[a-z0-9_]+$")
FORBIDDEN_DATABASES = {"quizhub_prod_db", "quiz_estagio_db", "quizhub_loadtest_db"}
CATALOGO = (
    Path(__file__).parents[2]
    / "dados_oficiais/rascunhos/nem_a_pato_macabro_100_candidato_final.json"
)
CATALOGO_SHA256 = "e8f3f4ce35d352e11bbd0ad5fb05e3dc79f07aa264bf402f994c1edfd57308c5"


@unittest.skipUnless(
    DATABASE_URL and AUTHORIZED_DATABASE,
    f"configure {URL_ENV} and {NAME_ENV} for an empty disposable database",
)
class TestMetadadosNemPatoPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parsed = make_url(DATABASE_URL)
        if parsed.get_backend_name() != "postgresql":
            raise RuntimeError(f"{URL_ENV} must point to PostgreSQL")
        if AUTHORIZED_DATABASE in FORBIDDEN_DATABASES:
            raise RuntimeError("refusing a persistent QuizHub database")
        if not AUTHORIZED_NAME.fullmatch(AUTHORIZED_DATABASE):
            raise RuntimeError("temporary database name is not explicitly authorized")
        if parsed.database != AUTHORIZED_DATABASE:
            raise RuntimeError("database URL and authorized name differ")
        cls.engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        cls.config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
        with cls.engine.connect() as connection:
            if connection.scalar(text("SELECT current_database()")) != AUTHORIZED_DATABASE:
                raise RuntimeError("connected to an unauthorized database")
            relations = list(connection.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )).scalars())
            if relations:
                raise RuntimeError("metadata regression requires an empty database")
        cls.migrate("upgrade", "0016")
        with cls.engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO perguntas_nem_pato
                    (id, categoria_id, enunciado, resposta_numerica, unidade,
                     explicacao, origem)
                VALUES
                    (17001, 'c73ff198-c1de-5787-b796-c74d2df1b696',
                     'Pergunta legada preservada?', 17, 'unidades',
                     'Registro anterior à migration 0017.', 'OFICIAL')
            """))

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    @classmethod
    def migrate(cls, direction, revision):
        with patch.dict(os.environ, {"DATABASE_URL": DATABASE_URL}):
            getattr(command, direction)(cls.config, revision)

    @classmethod
    def revision(cls):
        with cls.engine.connect() as connection:
            return connection.scalar(text("SELECT version_num FROM alembic_version"))

    def test_01_upgrade_downgrade_e_legado(self):
        self.migrate("upgrade", "0017")
        self.assertEqual(self.revision(), "0017")
        with self.engine.connect() as connection:
            colunas = {
                row.column_name: (row.data_type, row.is_nullable)
                for row in connection.execute(text("""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'perguntas_nem_pato'
                      AND column_name IN (
                          'tema_editorial', 'natureza_resposta',
                          'qualificacao_estimativa'
                      )
                """)).mappings()
            }
            self.assertEqual(colunas, {
                "tema_editorial": ("character varying", "YES"),
                "natureza_resposta": ("character varying", "YES"),
                "qualificacao_estimativa": ("text", "YES"),
            })
            legado = connection.execute(text("""
                SELECT tema_editorial, natureza_resposta, qualificacao_estimativa
                FROM perguntas_nem_pato WHERE id = 17001
            """)).one()
            self.assertEqual(tuple(legado), (None, None, None))

        self.migrate("downgrade", "0016")
        self.assertEqual(self.revision(), "0016")
        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(text(
                "SELECT count(*) FROM perguntas_nem_pato WHERE id = 17001"
            )), 1)
        self.migrate("upgrade", "0017")
        self.assertEqual(self.revision(), "0017")

    def test_02_ciclo_completo_compara_catalogo_e_fontes(self):
        import hashlib
        import json

        bruto = CATALOGO.read_bytes()
        self.assertEqual(hashlib.sha256(bruto).hexdigest(), CATALOGO_SHA256)
        documento = CatalogoNemPatoEditorial.model_validate(json.loads(bruto))
        servico = CatalogosOficiaisService()

        with Session(self.engine) as session:
            resultado = servico._preparar_nem_pato(
                session, documento, CATALOGO_SHA256
            )
            session.commit()
            self.assertEqual((resultado.criadas, resultado.existentes), (100, 0))

            catalogo = session.scalar(select(CatalogoOficial).where(
                CatalogoOficial.catalogo_id == documento.catalogo_id,
                CatalogoOficial.versao == documento.versao,
            ))
            self.assertIsNotNone(catalogo)
            self.assertEqual(catalogo.status, "PREPARADO")
            persistidas = list(session.scalars(
                select(PerguntaNemPato)
                .where(PerguntaNemPato.catalogo_oficial_id == catalogo.id)
                .order_by(PerguntaNemPato.id_editorial)
            ))
            esperadas = sorted(
                documento.categoria.perguntas,
                key=lambda item: item.id_editorial,
            )
            self.assertEqual(len(persistidas), 100)
            self.assertEqual(len(esperadas), 100)
            for persistida, esperada in zip(persistidas, esperadas, strict=True):
                self.assertEqual(persistida.id_editorial, esperada.id_editorial)
                self.assertEqual(persistida.enunciado, esperada.enunciado)
                self.assertEqual(persistida.resposta_numerica, esperada.resposta_numerica)
                self.assertEqual(persistida.unidade, esperada.unidade)
                self.assertEqual(persistida.explicacao, esperada.explicacao)
                self.assertEqual(persistida.tema_editorial, esperada.tema_editorial)
                self.assertEqual(persistida.natureza_resposta, esperada.natureza_resposta)
                self.assertEqual(
                    persistida.qualificacao_estimativa,
                    esperada.qualificacao_estimativa,
                )
                self.assertEqual(
                    [
                        (fonte.titulo, fonte.url, fonte.acessada_em)
                        for fonte in persistida.fontes_editoriais
                    ],
                    [
                        (fonte.titulo, str(fonte.url), fonte.acessada_em)
                        for fonte in esperada.fontes
                    ],
                )
                self.assertEqual(persistida.categoria.slug, documento.categoria.slug)
                self.assertEqual(persistida.catalogo_oficial_id, catalogo.id)

            repeticao = servico._preparar_nem_pato(
                session, documento, CATALOGO_SHA256
            )
            session.commit()
            self.assertEqual((repeticao.criadas, repeticao.existentes), (0, 100))
            self.assertEqual(session.scalar(select(func.count(PerguntaNemPato.id)).where(
                PerguntaNemPato.catalogo_oficial_id == catalogo.id
            )), 100)
            self.assertEqual(session.scalar(select(func.count(
                FontePerguntaNemPatoOficial.id
            )).where(
                FontePerguntaNemPatoOficial.pergunta.has(
                    PerguntaNemPato.catalogo_oficial_id == catalogo.id
                )
            )), 102)
            self.assertEqual(session.scalar(select(func.count(CatalogoOficial.id)).where(
                CatalogoOficial.status == "ATIVO"
            )), 0)
            fontes_orfas = session.scalar(select(func.count(
                FontePerguntaNemPatoOficial.id
            )).where(~FontePerguntaNemPatoOficial.pergunta.has()))
            self.assertEqual(fontes_orfas, 0)
            legado = session.get(PerguntaNemPato, 17001)
            self.assertIsNotNone(legado)
            self.assertIsNone(legado.tema_editorial)
            self.assertIsNone(legado.natureza_resposta)
            self.assertIsNone(legado.qualificacao_estimativa)


if __name__ == "__main__":
    unittest.main()
