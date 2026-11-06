"""PostgreSQL regression for the reversible 0014 <-> 0015 catalog migration."""

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
    CatalogoOficial, FontePerguntaNemPatoOficial, FontePerguntaOficial,
    Pergunta, PerguntaNemPato,
)
from app.services.catalogos_oficiais import (
    CatalogosOficiaisService, predicado_catalogo_ativo,
)
from app.services.validador_catalogos_oficiais import (
    CatalogoNemPatoEditorial, CatalogoQuizEditorial,
)
from tests.test_catalogos_oficiais import catalogo_nem_pato, catalogo_quiz


URL_ENV = "CATALOGOS_OFICIAIS_TEST_DATABASE_URL"
NAME_ENV = "CATALOGOS_OFICIAIS_TEST_DATABASE_NAME"
DATABASE_URL = os.getenv(URL_ENV, "").strip()
AUTHORIZED_DATABASE = os.getenv(NAME_ENV, "").strip()
AUTHORIZED_NAME = re.compile(r"^quizhub_catalogos_test_[a-z0-9_]+$")
FORBIDDEN_DATABASES = {"quizhub_prod_db", "quiz_estagio_db", "quizhub_loadtest_db"}


@unittest.skipUnless(
    DATABASE_URL and AUTHORIZED_DATABASE,
    f"configure {URL_ENV} and {NAME_ENV} for an empty disposable database",
)
class TestCatalogosOficiaisMigrationPostgres(unittest.TestCase):
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
                raise RuntimeError("catalog migration regression requires an empty database")
        cls.migrate("upgrade", "0014")
        cls._insert_legacy_rows()

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

    @classmethod
    def _insert_legacy_rows(cls):
        with cls.engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO perguntas
                    (id, categoria_id, enunciado, alternativa_a, alternativa_b,
                     alternativa_c, alternativa_d, alternativa_correta, explicacao,
                     origem, dificuldade)
                VALUES
                    (15001, '40f40d1f-fa4a-5cc0-9a2f-910bfbf4b4cb',
                     'Oficial legada 0015', 'A', 'B', 'C', 'D', 0,
                     'Explicação', 'OFICIAL', 'FACIL')
            """))
            connection.execute(text("""
                INSERT INTO perguntas_nem_pato
                    (id, categoria_id, enunciado, resposta_numerica, unidade,
                     explicacao, origem)
                VALUES
                    (15101, '6cb33fc5-8545-55df-8c46-2e85fc67fe5c',
                     'Nem a Pato legada 0015', 15, 'unidades',
                     'Explicação', 'OFICIAL')
            """))

    def test_01_upgrade_cria_estrutura_e_preserva_legado(self):
        self.migrate("upgrade", "0015")
        self.assertEqual(self.revision(), "0015")
        with self.engine.connect() as connection:
            tabelas = set(connection.execute(text("""
                SELECT tablename FROM pg_tables WHERE schemaname = 'public'
            """)).scalars())
            self.assertTrue({
                "catalogos_oficiais", "fontes_perguntas_oficiais",
                "fontes_perguntas_nem_pato_oficiais",
            }.issubset(tabelas))
            self.assertEqual(connection.scalar(text("""
                SELECT count(*) FROM perguntas
                WHERE id = 15001 AND catalogo_oficial_id IS NULL
                  AND id_editorial IS NULL
            """)), 1)
            self.assertEqual(connection.scalar(text("""
                SELECT count(*) FROM perguntas_nem_pato
                WHERE id = 15101 AND catalogo_oficial_id IS NULL
                  AND id_editorial IS NULL
            """)), 1)
            indice = connection.execute(text("""
                SELECT indexdef FROM pg_indexes
                WHERE schemaname = 'public'
                  AND indexname = 'uq_catalogos_oficiais_modo_ativo'
            """)).scalar_one()
            self.assertIn("UNIQUE", indice)
            self.assertIn("status", indice)

    def test_02_integridade_referencial_impede_excluir_catalogo_em_uso(self):
        with self.engine.begin() as connection:
            catalogo_id = connection.scalar(text("""
                INSERT INTO catalogos_oficiais
                    (id, catalogo_id, versao, modo, status, sha256)
                VALUES
                    ('15000000-0000-4000-8000-000000000015', 'teste_catalogo', 1,
                     'QUIZ_CLASSICO', 'PREPARADO', repeat('a', 64))
                RETURNING id
            """))
            connection.execute(text("""
                UPDATE perguntas SET catalogo_oficial_id = :catalogo,
                    id_editorial = 'teste-0015'
                WHERE id = 15001
            """), {"catalogo": catalogo_id})
        with self.assertRaises(Exception):
            with self.engine.begin() as connection:
                connection.execute(text("""
                    DELETE FROM catalogos_oficiais
                    WHERE id = '15000000-0000-4000-8000-000000000015'
                """))
        # Reverte apenas os dados artificiais deste teste para que os cenários
        # seguintes recebam novamente a linha histórica sem versionamento.
        with self.engine.begin() as connection:
            connection.execute(text("""
                UPDATE perguntas SET catalogo_oficial_id = NULL,
                    id_editorial = NULL
                WHERE id = 15001
            """))
            connection.execute(text("""
                DELETE FROM catalogos_oficiais
                WHERE id = '15000000-0000-4000-8000-000000000015'
            """))

    def test_03_downgrade_e_reupgrade_preservam_perguntas(self):
        self.migrate("downgrade", "0014")
        self.assertEqual(self.revision(), "0014")
        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(text(
                "SELECT count(*) FROM perguntas WHERE id = 15001"
            )), 1)
            self.assertEqual(connection.scalar(text(
                "SELECT count(*) FROM perguntas_nem_pato WHERE id = 15101"
            )), 1)
        self.migrate("upgrade", "0015")
        self.assertEqual(self.revision(), "0015")

    def test_04_importador_idempotencia_rollback_ativacao_e_isolamento(self):
        # Os três testes anteriores exercitam deliberadamente o esquema histórico
        # 0015. O importador abaixo usa os modelos ORM atuais, portanto precisa do
        # esquema atual para não misturar classes 0023 com tabelas históricas.
        self.migrate("upgrade", "0023")
        self.assertEqual(self.revision(), "0023")

        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(text("""
                SELECT count(*) FROM perguntas
                WHERE id = 15001 AND proveniencia_legada IS TRUE
                  AND catalogo_oficial_id IS NULL
                  AND categoria_versao_id IS NULL
            """)), 1)
            self.assertEqual(connection.scalar(text("""
                SELECT count(*) FROM perguntas_nem_pato
                WHERE id = 15101 AND proveniencia_legada IS TRUE
                  AND catalogo_oficial_id IS NULL
                  AND categoria_versao_id IS NULL
            """)), 1)

        with self.engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO categorias
                    (id, slug, nome, modo, origem, ativa)
                VALUES
                    ('15000000-0000-4000-8000-000000000099', 'macabro',
                     'Macabro', 'NEM_A_PATO', 'OFICIAL', true)
                ON CONFLICT DO NOTHING
            """))

        servico = CatalogosOficiaisService()
        bruto_quiz = catalogo_quiz()
        bruto_quiz["catalogo_id"] = "quiz_classico_homologacao"
        documento_quiz = CatalogoQuizEditorial.model_validate(bruto_quiz)
        bruto_nem_pato = catalogo_nem_pato()
        bruto_nem_pato["catalogo_id"] = "nem_pato_homologacao"
        bruto_nem_pato["categoria"]["perguntas"][0]["fontes"].append({
            "titulo": "Fonte complementar",
            "url": "https://example.org/fonte-complementar",
            "acessada_em": "2026-10-14",
        })
        documento_nem_pato = CatalogoNemPatoEditorial.model_validate(
            bruto_nem_pato
        )

        with Session(self.engine) as session:
            quiz = servico._preparar_quiz(
                session, documento_quiz, "b" * 64
            )
            nem_pato = servico._preparar_nem_pato(
                session, documento_nem_pato, "c" * 64
            )
            session.commit()
            self.assertEqual((quiz.criadas, nem_pato.criadas), (400, 100))
            self.assertEqual(session.scalar(text("""
                SELECT count(*) FROM perguntas
                WHERE catalogo_oficial_id IS NOT NULL
                  AND proveniencia_legada IS FALSE
                  AND categoria_versao_id IS NOT NULL
            """)), 400)
            self.assertEqual(session.scalar(text("""
                SELECT count(*) FROM perguntas_nem_pato
                WHERE catalogo_oficial_id IS NOT NULL
                  AND proveniencia_legada IS FALSE
                  AND categoria_versao_id IS NOT NULL
            """)), 100)
            self.assertEqual(session.scalar(select(func.count(
                FontePerguntaOficial.id
            ))), 400)
            self.assertEqual(session.scalar(select(func.count(
                FontePerguntaNemPatoOficial.id
            ))), 101)

            repeticao = servico._preparar_quiz(
                session, documento_quiz, "b" * 64
            )
            self.assertEqual((repeticao.criadas, repeticao.existentes), (0, 400))

            servico.ativar(session, "quiz_classico_homologacao", 2)
            session.commit()
            selecionadas = session.scalar(select(func.count(Pergunta.id)).where(
                predicado_catalogo_ativo(Pergunta, "QUIZ_CLASSICO")
            ))
            self.assertEqual(selecionadas, 400)
            self.assertEqual(session.scalar(select(func.count(Pergunta.id)).where(
                Pergunta.id == 15001,
                predicado_catalogo_ativo(Pergunta, "QUIZ_CLASSICO"),
            )), 0)

            servico.reverter_para_legado(session, "QUIZ_CLASSICO")
            session.commit()
            self.assertEqual(session.scalar(select(func.count(Pergunta.id)).where(
                predicado_catalogo_ativo(Pergunta, "QUIZ_CLASSICO")
            )), 0)
            self.assertEqual(session.scalar(select(func.count(Pergunta.id)).where(
                Pergunta.id == 15001,
                Pergunta.catalogo_oficial_id.is_(None),
                Pergunta.id_editorial.is_(None),
            )), 1)

            rollback = catalogo_quiz()
            rollback["catalogo_id"] = "quiz_classico_rollback"
            rollback["versao"] = 99
            servico._preparar_quiz(
                session, CatalogoQuizEditorial.model_validate(rollback), "d" * 64
            )
            session.rollback()
            self.assertEqual(session.scalar(select(func.count(
                CatalogoOficial.id
            )).where(
                CatalogoOficial.catalogo_id == "quiz_classico_rollback"
            )), 0)
            self.assertEqual(session.scalar(select(func.count(PerguntaNemPato.id)).where(
                PerguntaNemPato.catalogo_oficial_id.is_not(None)
            )), 100)


if __name__ == "__main__":
    unittest.main()
