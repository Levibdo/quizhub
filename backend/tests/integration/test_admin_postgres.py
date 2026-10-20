import os
import unittest
from io import BytesIO
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
    Pergunta,
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
        self._login("jogador-pg@example.com", "senha-segura")
        self.assertEqual(self.client.get("/api/v1/admin/resumo").status_code, 403)
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
