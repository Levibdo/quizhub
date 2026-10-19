import os
import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import patch

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import AuditoriaAdministrativa, Categoria, Pergunta, Usuario
from app.security import JWT_COOKIE_NAME, criar_token_acesso, password_hash
from app.services.auth import Autenticacao
from app.services.importador_perguntas import COLUNAS_OBRIGATORIAS


def xlsx_valido() -> bytes:
    workbook = Workbook()
    planilha = workbook.active
    planilha.append(list(COLUNAS_OBRIGATORIAS))
    planilha.append([
        "seguranca", "Pergunta administrativa artificial?",
        "A", "B", "C", "D", 0, "Explicação artificial",
    ])
    arquivo = BytesIO()
    workbook.save(arquivo)
    workbook.close()
    return arquivo.getvalue()


class TestAutorizacaoAdministrativa(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(
            self.engine, expire_on_commit=False, autoflush=False
        )
        self.session = self.factory()
        self.env = patch.dict(
            os.environ,
            {"JWT_SECRET": "segredo-administrativo-de-teste-com-32-bytes"},
        )
        self.env.start()

        self.jogador = Usuario(
            nome="Jogador", email="jogador@example.com",
            senha_hash=password_hash.hash("senha-segura"), perfil="JOGADOR",
        )
        self.admin = Usuario(
            nome="Admin", email="admin@example.com",
            senha_hash=password_hash.hash("senha-administrativa"), perfil="ADMIN",
        )
        self.session.add_all([self.jogador, self.admin])
        self.session.commit()

        def banco_teste():
            with self.factory() as db:
                yield db

        app.dependency_overrides[get_db] = banco_teste
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.session.close()
        self.engine.dispose()
        self.env.stop()

    def autenticar(self, usuario, *, expirado=False):
        agora = datetime.now(timezone.utc)
        token = criar_token_acesso(
            usuario.id,
            agora=agora - timedelta(hours=9) if expirado else agora,
        )
        self.client.cookies.set(JWT_COOKIE_NAME, token)

    def test_painel_retorna_401_ao_visitante_e_403_ao_jogador(self):
        self.assertEqual(self.client.get("/api/v1/admin/resumo").status_code, 401)

        self.autenticar(self.jogador)
        resposta = self.client.get("/api/v1/admin/resumo")
        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(resposta.json()["detail"], "acesso exclusivo para administradores")

    def test_admin_acessa_painel_e_sessao_expirada_e_rejeitada(self):
        self.autenticar(self.admin)
        resposta = self.client.get("/api/v1/admin/resumo")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"catalogos": [], "auditorias": []})

        self.client.cookies.clear()
        self.autenticar(self.admin, expirado=True)
        self.assertEqual(self.client.get("/api/v1/admin/resumo").status_code, 401)

    def test_logout_invalida_cookie_no_cliente(self):
        resposta_login = self.client.post("/api/v1/auth/login", json={
            "email": self.admin.email,
            "senha": "senha-administrativa",
        })
        self.assertEqual(resposta_login.status_code, 200)
        self.assertEqual(self.client.get("/api/v1/admin/resumo").status_code, 200)
        self.assertEqual(self.client.post("/api/v1/auth/logout").status_code, 204)
        self.assertEqual(self.client.get("/api/v1/admin/resumo").status_code, 401)

    def test_importador_alternativo_exige_admin_antes_de_escrever(self):
        arquivo = {"arquivo": ("perguntas.xlsx", xlsx_valido(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        self.assertEqual(
            self.client.post("/api/v1/perguntas/importar", files=arquivo).status_code,
            401,
        )
        self.autenticar(self.jogador)
        self.assertEqual(
            self.client.post("/api/v1/perguntas/importar", files=arquivo).status_code,
            403,
        )
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count(Pergunta.id))), 0)
            self.assertEqual(db.scalar(select(func.count(AuditoriaAdministrativa.id))), 0)

    def test_admin_importa_dado_artificial_e_operacao_e_auditada(self):
        with self.factory() as db:
            db.add(Categoria(
                slug="seguranca", nome="Segurança", modo="QUIZ_CLASSICO",
                origem="OFICIAL", ativa=True,
            ))
            db.commit()
        self.autenticar(self.admin)
        resposta = self.client.post(
            "/api/v1/perguntas/importar",
            files={"arquivo": ("perguntas.xlsx", xlsx_valido(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        self.assertEqual(resposta.status_code, 200, resposta.text)
        self.assertEqual(resposta.json()["criadas"], 1)
        with self.factory() as db:
            pergunta = db.scalar(select(Pergunta))
            auditoria = db.scalar(select(AuditoriaAdministrativa))
            self.assertEqual(pergunta.enunciado, "Pergunta administrativa artificial?")
            self.assertEqual(auditoria.administrador_id, self.admin.id)
            self.assertEqual(auditoria.resultado, "SUCESSO")
            self.assertNotIn("senha", str(auditoria.detalhes).lower())

    def test_cadastro_comum_nao_concede_admin_e_bootstrap_e_unico(self):
        with self.factory() as db:
            # Remove o admin artificial para exercitar o bootstrap inicial.
            db.query(AuditoriaAdministrativa).delete()
            db.query(Usuario).filter(Usuario.perfil == "ADMIN").delete()
            db.commit()
            servico = Autenticacao()
            novo = servico.cadastrar(
                db, "Nova Jogadora", "nova@example.com", "senha-segura"
            )
            self.assertEqual(novo.perfil, "JOGADOR")
            administrador = servico.criar_admin_inicial(
                db, "Admin Inicial", "inicial@example.com", "senha-admin-forte"
            )
            self.assertEqual(administrador.perfil, "ADMIN")
            with self.assertRaisesRegex(ValueError, "já existe"):
                servico.criar_admin_inicial(
                    db, "Outro", "outro@example.com", "outra-senha-forte"
                )

    def test_jogos_e_ranking_continuam_publicos(self):
        self.assertEqual(self.client.get("/api/v1/categorias").status_code, 200)
        resposta = self.client.get("/api/v1/ranking")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), [])


if __name__ == "__main__":
    unittest.main()
