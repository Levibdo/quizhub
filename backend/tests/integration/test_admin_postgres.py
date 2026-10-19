import os
import unittest
from io import BytesIO
from urllib.parse import urlparse

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from app.db.session import get_db
from app.main import app
from app.models import AuditoriaAdministrativa, Categoria, Pergunta, Usuario
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
        if atual != esperado or revisao != "0018":
            raise RuntimeError("destino ou revisão do banco descartável divergente")
        cls.factory = sessionmaker(cls.engine, expire_on_commit=False)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        with self.factory() as db:
            db.execute(text("DELETE FROM auditorias_administrativas"))
            db.execute(text("DELETE FROM perguntas"))
            db.execute(text("DELETE FROM categorias"))
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

        with self.factory() as db:
            db.add(Categoria(
                slug="admin-teste", nome="Admin teste", modo="QUIZ_CLASSICO",
                origem="OFICIAL", ativa=True,
            ))
            db.commit()

        self._login("admin-pg@example.com", "senha-administrativa")
        self.assertEqual(self.client.get("/api/v1/admin/resumo").status_code, 200)
        resposta = self.client.post(
            "/api/v1/perguntas/importar",
            files={"arquivo": ("teste.xlsx", _xlsx())},
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


if __name__ == "__main__":
    unittest.main()
