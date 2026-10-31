import os
import unittest
from datetime import datetime, timezone
from io import BytesIO
from uuid import UUID
from urllib.parse import urlparse
from unittest.mock import patch

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from app.db.session import get_db
from app.main import app
from app.models import (
    AuditoriaAdministrativa,
    CatalogoOficial,
    Categoria,
    FontePerguntaNemPatoOficial,
    FontePerguntaOficial,
    Pergunta,
    PerguntaNemPato,
    OperacaoAdministrativa,
    Usuario,
)
from app.security import password_hash
from app.services.importador_perguntas import COLUNAS_OBRIGATORIAS


URL_ENV = "QUIZHUB_ADMIN_TEST_DATABASE_URL"
NAME_ENV = "QUIZHUB_ADMIN_TEST_DATABASE_NAME"


def _xlsx() -> bytes:
    workbook = Workbook()
    planilha = workbook.active
    planilha.append(list(COLUNAS_OBRIGATORIAS))
    planilha.append([
        "admin-teste", "Registro oficial artificial PostgreSQL?",
        "A", "B", "C", "D", 0, "Explicação artificial",
    ])
    arquivo = BytesIO()
    workbook.save(arquivo)
    workbook.close()
    return arquivo.getvalue()


@unittest.skipUnless(os.getenv(URL_ENV), f"{URL_ENV} não configurada")
class TestAdminPostgreSQL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = os.environ[URL_ENV]
        esperado = os.getenv(NAME_ENV, "")
        nome_url = urlparse(url.replace("postgresql+psycopg://", "postgresql://")).path.lstrip("/")
        if not esperado.startswith("quizhub_admin_test_") or nome_url != esperado:
            raise RuntimeError("banco administrativo descartável não passou na proteção de nome")
        cls.engine = create_engine(url)
        with cls.engine.connect() as conexao:
            atual = conexao.scalar(text("SELECT current_database()"))
            revisao = conexao.scalar(text("SELECT version_num FROM alembic_version"))
        if atual != esperado or revisao != "0019":
            raise RuntimeError("destino ou revisão do banco descartável divergente")
        cls.factory = sessionmaker(cls.engine, expire_on_commit=False)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        with self.factory() as db:
            db.execute(text("DELETE FROM operacoes_administrativas"))
            db.execute(text("DELETE FROM auditorias_administrativas"))
            db.execute(text("DELETE FROM perguntas_nem_pato"))
            db.execute(text("DELETE FROM perguntas"))
            db.execute(text("DELETE FROM categorias"))
            db.execute(text("DELETE FROM catalogos_oficiais"))
            db.execute(text("DELETE FROM usuarios"))
            self.jogador = Usuario(
                nome="Jogador PG", email="jogador-pg@example.com",
                senha_hash=password_hash.hash("senha-segura"), perfil="JOGADOR",
            )
            self.admin = Usuario(
                nome="Admin PG", email="admin-pg@example.com",
                senha_hash=password_hash.hash("senha-administrativa"), perfil="ADMIN",
            )
            db.add_all([self.jogador, self.admin])
            db.commit()

        def banco_teste():
            with self.factory() as db:
                yield db

        app.dependency_overrides[get_db] = banco_teste
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()

    def _login(self, email, senha):
        resposta = self.client.post(
            "/api/v1/auth/login", json={"email": email, "senha": senha}
        )
        self.assertEqual(resposta.status_code, 200, resposta.text)

    def _csrf(self):
        resposta = self.client.get("/api/v1/admin/csrf")
        self.assertEqual(resposta.status_code, 200, resposta.text)
        return {
            "Origin": "http://testserver",
            "X-CSRF-Token": resposta.json()["token"],
        }

    def _criar_categoria(self):
        with self.factory() as db:
            categoria = Categoria(
                slug="admin-teste", nome="Admin teste",
                modo="QUIZ_CLASSICO", origem="OFICIAL", ativa=True,
            )
            db.add(categoria)
            db.commit()
            return categoria.id

    def test_401_403_admin_importacao_auditoria_e_rotas_publicas(self):
        self.assertEqual(self.client.get("/api/v1/admin/resumo").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/admin/auditorias").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/admin/catalogos").status_code, 401)
        self._login("jogador-pg@example.com", "senha-segura")
        self.assertEqual(self.client.get("/api/v1/admin/resumo").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/admin/auditorias").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/admin/catalogos").status_code, 403)
        self.assertEqual(
            self.client.post(
                "/api/v1/perguntas/importar",
                files={"arquivo": ("teste.xlsx", _xlsx())},
            ).status_code,
            403,
        )
        self.client.post("/api/v1/auth/logout")

        self._criar_categoria()

        self._login("admin-pg@example.com", "senha-administrativa")
        self.assertEqual(self.client.get("/api/v1/admin/resumo").status_code, 200)
        cabecalhos = self._csrf()
        resposta = self.client.post(
            "/api/v1/perguntas/importar",
            files={"arquivo": ("teste.xlsx", _xlsx())},
            headers=cabecalhos,
        )
        self.assertEqual(resposta.status_code, 200, resposta.text)
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count(Pergunta.id))), 1)
            auditoria = db.scalar(select(AuditoriaAdministrativa))
            self.assertEqual(auditoria.administrador_id, self.admin.id)
            self.assertEqual(auditoria.resultado, "SUCESSO")

        self.client.post("/api/v1/auth/logout")
        self.assertEqual(self.client.get("/api/v1/admin/resumo").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/categorias").status_code, 200)
        self.assertNotIn(
            self.client.get("/api/v1/ranking").status_code, {401, 403}
        )

    def test_consulta_catalogos_conta_perguntas_no_postgresql(self):
        categoria_id = self._criar_categoria()
        with self.factory() as db:
            ativo = CatalogoOficial(
                catalogo_id="quiz-c1-postgres", versao=2,
                modo="QUIZ_CLASSICO", status="ATIVO", sha256="c" * 64,
            )
            preparado = CatalogoOficial(
                catalogo_id="quiz-c1-postgres", versao=1,
                modo="QUIZ_CLASSICO", status="PREPARADO", sha256="d" * 64,
            )
            db.add_all([ativo, preparado])
            db.flush()
            db.add_all([
                Pergunta(
                    id=99201 + indice, categoria_id=categoria_id,
                    enunciado=f"Pergunta C1 {indice}?", alternativa_a="A",
                    alternativa_b="B", alternativa_c="C", alternativa_d="D",
                    alternativa_correta=0, explicacao="Teste C1", origem="OFICIAL",
                    catalogo_oficial_id=ativo.id, id_editorial=f"C1-{indice}",
                )
                for indice in range(2)
            ])
            db.commit()

        self._login("admin-pg@example.com", "senha-administrativa")
        resposta = self.client.get("/api/v1/admin/catalogos")
        self.assertEqual(resposta.status_code, 200, resposta.text)
        catalogos = resposta.json()["catalogos"]
        self.assertEqual(len(catalogos), 2)
        self.assertEqual(catalogos[0]["versao"], 2)
        self.assertEqual(catalogos[0]["quantidade_perguntas"], 2)
        self.assertEqual(catalogos[0]["situacao_ativacao"], "ATIVO")
        self.assertEqual(catalogos[1]["quantidade_perguntas"], 0)
        self.assertEqual(catalogos[1]["situacao_ativacao"], "INATIVO")
        self.assertIsNone(catalogos[0]["estado_editorial"])
        serializado = str(catalogos).lower()
        self.assertNotIn("sha256", serializado)
        self.assertNotIn("senha", serializado)

    def test_consulta_perguntas_oficiais_pagina_filtra_e_detalha_no_postgresql(self):
        with self.factory() as db:
            categoria_quiz = Categoria(
                slug="quiz-c2-pg", nome="Quiz C2 PG", modo="QUIZ_CLASSICO",
                origem="OFICIAL", ativa=True,
            )
            categoria_nem = Categoria(
                slug="nem-c2-pg", nome="Nem C2 PG", modo="NEM_A_PATO",
                origem="OFICIAL", ativa=True,
            )
            catalogo_quiz = CatalogoOficial(
                catalogo_id="quiz-c2-pg", versao=2, modo="QUIZ_CLASSICO",
                status="ATIVO", sha256="e" * 64,
            )
            catalogo_nem = CatalogoOficial(
                catalogo_id="nem-c2-pg", versao=1, modo="NEM_A_PATO",
                status="ATIVO", sha256="f" * 64,
            )
            db.add_all([categoria_quiz, categoria_nem, catalogo_quiz, catalogo_nem])
            db.flush()
            quiz = Pergunta(
                id=99401, categoria_id=categoria_quiz.id,
                enunciado="Enunciado pesquisável PostgreSQL?",
                alternativa_a="A", alternativa_b="B", alternativa_c="C",
                alternativa_d="D", alternativa_correta=1,
                explicacao="Explicação C2 PostgreSQL", dificuldade="DIFICIL",
                origem="OFICIAL", ativa=True,
                catalogo_oficial_id=catalogo_quiz.id, id_editorial="C2-PG-QUIZ",
            )
            nem = PerguntaNemPato(
                categoria_id=categoria_nem.id,
                enunciado="Quantos casos perturbadores?", resposta_numerica=42,
                unidade="casos", explicacao="Explicação C2 Nem a Pato",
                origem="OFICIAL", ativa=False,
                catalogo_oficial_id=catalogo_nem.id, id_editorial="C2-PG-NEM",
                natureza_resposta="EXATA",
            )
            db.add_all([quiz, nem])
            db.flush()
            db.add_all([
                FontePerguntaOficial(
                    pergunta_id=quiz.id, ordem=1, titulo="Fonte Quiz C2",
                    url="https://example.org/c2-quiz", acessada_em=datetime.now(timezone.utc).date(),
                ),
                FontePerguntaNemPatoOficial(
                    pergunta_id=nem.id, ordem=1, titulo="Fonte Nem C2",
                    url="https://example.org/c2-nem", acessada_em=datetime.now(timezone.utc).date(),
                ),
            ])
            db.commit()
            quiz_id, nem_id = quiz.id, nem.id

        self._login("admin-pg@example.com", "senha-administrativa")
        pagina = self.client.get("/api/v1/admin/perguntas", params={"limite": 1})
        self.assertEqual(pagina.status_code, 200, pagina.text)
        self.assertEqual(pagina.json()["total"], 2)
        self.assertEqual(pagina.json()["total_paginas"], 2)
        filtrada = self.client.get("/api/v1/admin/perguntas", params={
            "modo": "QUIZ_CLASSICO", "busca": "PESQUISÁVEL",
            "dificuldade": "DIFICIL", "ativa": True,
        })
        self.assertEqual(filtrada.status_code, 200, filtrada.text)
        self.assertEqual(filtrada.json()["total"], 1)
        detalhe_quiz = self.client.get(
            f"/api/v1/admin/perguntas/QUIZ_CLASSICO/{quiz_id}"
        )
        self.assertEqual(detalhe_quiz.status_code, 200, detalhe_quiz.text)
        self.assertEqual(detalhe_quiz.json()["alternativas"], ["A", "B", "C", "D"])
        self.assertEqual(detalhe_quiz.json()["alternativa_correta"], 1)
        self.assertEqual(detalhe_quiz.json()["referencias"][0]["titulo"], "Fonte Quiz C2")
        detalhe_nem = self.client.get(
            f"/api/v1/admin/perguntas/NEM_A_PATO/{nem_id}"
        )
        self.assertEqual(detalhe_nem.status_code, 200, detalhe_nem.text)
        self.assertEqual(detalhe_nem.json()["resposta_numerica"], "42")
        self.assertEqual(detalhe_nem.json()["referencias"][0]["titulo"], "Fonte Nem C2")
        self.assertEqual(
            self.client.get("/api/v1/admin/perguntas/QUIZ_CLASSICO/999999").status_code,
            404,
        )

    def test_consulta_auditoria_pagina_filtra_e_sanitiza_no_postgresql(self):
        instante = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
        with self.factory() as db:
            db.add_all([
                AuditoriaAdministrativa(
                    id=UUID("00000000-0000-0000-0000-000000000001"),
                    administrador_id=self.admin.id, ocorrida_em=instante,
                    operacao="IMPORTAR_PERGUNTAS", recurso_tipo="CATALOGO",
                    recurso_id="lote-alpha", resultado="SUCESSO",
                    detalhes={"quantidade": 400, "token": "segredo"},
                ),
                AuditoriaAdministrativa(
                    id=UUID("00000000-0000-0000-0000-000000000002"),
                    administrador_id=self.admin.id, ocorrida_em=instante,
                    operacao="IMPORTAR_PERGUNTAS", recurso_tipo="CATALOGO",
                    recurso_id="lote-beta", resultado="REJEITADA",
                ),
            ])
            db.commit()
            total_sql = db.scalar(select(func.count(AuditoriaAdministrativa.id)))

        self._login("admin-pg@example.com", "senha-administrativa")
        pagina = self.client.get(
            "/api/v1/admin/auditorias",
            params={"limite": 1, "pagina": 1, "ordem": "desc"},
        )
        self.assertEqual(pagina.status_code, 200, pagina.text)
        self.assertEqual(pagina.json()["total"], total_sql)
        self.assertEqual(pagina.json()["total_paginas"], 2)
        self.assertEqual(pagina.json()["itens"][0]["recurso_id"], "lote-beta")

        filtrada = self.client.get(
            "/api/v1/admin/auditorias",
            params={"busca": "ALPHA", "resultado": "SUCESSO"},
        )
        self.assertEqual(filtrada.status_code, 200, filtrada.text)
        self.assertEqual(filtrada.json()["total"], 1)
        detalhes = filtrada.json()["itens"][0]["detalhes"]
        self.assertEqual(detalhes["quantidade"], 400)
        self.assertEqual(detalhes["token"], "[REMOVIDO]")

    def test_importacao_e_auditoria_sao_atomicas_e_preservam_catalogo_ativo(self):
        categoria_id = self._criar_categoria()
        with self.factory() as db:
            catalogo = CatalogoOficial(
                catalogo_id="quiz-integracao",
                versao=1,
                modo="QUIZ_CLASSICO",
                status="ATIVO",
                sha256="a" * 64,
            )
            db.add(catalogo)
            db.commit()
            catalogo_id = catalogo.id

        self._login("admin-pg@example.com", "senha-administrativa")
        resposta = self.client.post(
            "/api/v1/perguntas/importar",
            files={"arquivo": ("teste.xlsx", _xlsx())},
            headers=self._csrf(),
        )
        self.assertEqual(resposta.status_code, 200, resposta.text)
        with self.factory() as db:
            pergunta = db.scalar(select(Pergunta))
            auditoria = db.scalar(select(AuditoriaAdministrativa))
            catalogo = db.get(CatalogoOficial, catalogo_id)
            self.assertEqual(pergunta.categoria_id, categoria_id)
            self.assertIsNone(pergunta.catalogo_oficial_id)
            self.assertEqual(auditoria.resultado, "SUCESSO")
            self.assertEqual(catalogo.status, "ATIVO")
            self.assertEqual(catalogo.sha256, "a" * 64)

    def test_falha_de_auditoria_reverte_importacao_sem_estado_parcial(self):
        self._criar_categoria()
        self._login("admin-pg@example.com", "senha-administrativa")
        cliente = TestClient(app, raise_server_exceptions=False)
        try:
            login = cliente.post("/api/v1/auth/login", json={
                "email": "admin-pg@example.com",
                "senha": "senha-administrativa",
            })
            self.assertEqual(login.status_code, 200)
            csrf = cliente.get("/api/v1/admin/csrf")
            with patch(
                "app.api.v1.perguntas.registrar_auditoria_administrativa",
                side_effect=RuntimeError("falha artificial de auditoria"),
            ):
                resposta = cliente.post(
                    "/api/v1/perguntas/importar",
                    files={"arquivo": ("teste.xlsx", _xlsx())},
                    headers={
                        "Origin": "http://testserver",
                        "X-CSRF-Token": csrf.json()["token"],
                    },
                )
            self.assertEqual(resposta.status_code, 500)
        finally:
            cliente.close()
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count(Pergunta.id))), 0)
            self.assertEqual(
                db.scalar(select(func.count(AuditoriaAdministrativa.id))), 0
            )

    def test_limite_flag_e_csrf_rejeitam_sem_criar_perguntas(self):
        self._criar_categoria()
        self._login("admin-pg@example.com", "senha-administrativa")

        sem_token = self.client.post(
            "/api/v1/perguntas/importar",
            files={"arquivo": ("teste.xlsx", _xlsx())},
            headers={"Origin": "http://testserver"},
        )
        self.assertEqual(sem_token.status_code, 403)

        cabecalhos = self._csrf()
        origem_hostil = self.client.post(
            "/api/v1/perguntas/importar",
            files={"arquivo": ("teste.xlsx", _xlsx())},
            headers={**cabecalhos, "Origin": "https://hostil.example"},
        )
        self.assertEqual(origem_hostil.status_code, 403)

        with patch.dict(os.environ, {"LEGACY_ADMIN_IMPORT_MAX_BYTES": "16"}):
            grande = self.client.post(
                "/api/v1/perguntas/importar",
                files={"arquivo": ("teste.xlsx", b"x" * 17)},
                headers=cabecalhos,
            )
        self.assertEqual(grande.status_code, 413)

        with patch.dict(os.environ, {"LEGACY_ADMIN_IMPORT_ENABLED": "false"}):
            desabilitado = self.client.post(
                "/api/v1/perguntas/importar",
                files={"arquivo": ("teste.xlsx", _xlsx())},
                headers=cabecalhos,
            )
        self.assertEqual(desabilitado.status_code, 410)
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count(Pergunta.id))), 0)


if __name__ == "__main__":
    unittest.main()
