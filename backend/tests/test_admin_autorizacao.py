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
from app.security import (
    CSRF_COOKIE_NAME,
    JWT_COOKIE_NAME,
    criar_token_acesso,
    criar_token_csrf,
    password_hash,
)
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

    def cabecalhos_csrf(self, cliente=None):
        cliente = cliente or self.client
        resposta = cliente.get("/api/v1/admin/csrf")
        self.assertEqual(resposta.status_code, 200, resposta.text)
        return {
            "Origin": "http://testserver",
            "X-CSRF-Token": resposta.json()["token"],
        }

    def test_painel_retorna_401_ao_visitante_e_403_ao_jogador(self):
        rascunho_id = "00000000-0000-0000-0000-000000000001"
        catalogo_id = "00000000-0000-0000-0000-000000000002"
        importacao = {
            "nome_rascunho": "Autorização", "modo": "NEM_A_PATO",
            "categorias": [], "perguntas_quiz": [], "perguntas_nem_pato": [],
        }
        self.assertEqual(self.client.get("/api/v1/admin/resumo").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/admin/dashboard").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/admin/catalogos").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/admin/perguntas").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/admin/perguntas/opcoes").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/admin/catalogos/rascunhos").status_code, 401)
        self.assertEqual(self.client.get(f"/api/v1/admin/catalogos/rascunhos/{rascunho_id}/validacao").status_code, 401)
        self.assertEqual(self.client.get(f"/api/v1/admin/catalogos/rascunhos/{rascunho_id}/categorias").status_code, 401)
        self.assertEqual(self.client.post(f"/api/v1/admin/catalogos/{catalogo_id}/importacoes/json/previsualizar", json=importacao).status_code, 401)

        self.autenticar(self.jogador)
        resposta = self.client.get("/api/v1/admin/resumo")
        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(resposta.json()["detail"], "acesso exclusivo para administradores")
        dashboard = self.client.get("/api/v1/admin/dashboard")
        self.assertEqual(dashboard.status_code, 403)
        self.assertEqual(
            dashboard.json()["detail"], "acesso exclusivo para administradores"
        )
        self.assertEqual(self.client.get("/api/v1/admin/catalogos").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/admin/perguntas").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/admin/catalogos/rascunhos").status_code, 403)
        self.assertEqual(self.client.get(f"/api/v1/admin/catalogos/rascunhos/{rascunho_id}/validacao").status_code, 403)
        self.assertEqual(self.client.get(f"/api/v1/admin/catalogos/rascunhos/{rascunho_id}/categorias").status_code, 403)
        self.assertEqual(self.client.post(f"/api/v1/admin/catalogos/{catalogo_id}/importacoes/json/previsualizar", json=importacao).status_code, 403)

    def test_admin_acessa_painel_e_sessao_expirada_e_rejeitada(self):
        self.autenticar(self.admin)
        resposta = self.client.get("/api/v1/admin/resumo")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"catalogos": [], "auditorias": []})
        dashboard = self.client.get("/api/v1/admin/dashboard")
        self.assertEqual(dashboard.status_code, 200, dashboard.text)
        corpo = dashboard.json()
        self.assertEqual(corpo["indicadores"]["usuarios"], {
            "total": 2, "ativos": 2,
        })
        self.assertEqual(corpo["indicadores"]["partidas"]["total"], 0)
        self.assertEqual(corpo["indicadores"]["perguntas"]["total"], 0)
        self.assertIsNone(corpo["temporada_ativa"])
        serializado = str(corpo).lower()
        self.assertNotIn("senha_hash", serializado)
        self.assertNotIn("email", serializado)
        self.assertNotIn("token", serializado)
        catalogos = self.client.get("/api/v1/admin/catalogos")
        self.assertEqual(catalogos.status_code, 200, catalogos.text)
        self.assertEqual(catalogos.json(), {"catalogos": []})
        perguntas = self.client.get("/api/v1/admin/perguntas")
        self.assertEqual(perguntas.status_code, 200, perguntas.text)
        self.assertEqual(perguntas.json()["total"], 0)
        inexistente = self.client.get("/api/v1/admin/perguntas/QUIZ_CLASSICO/999999")
        self.assertEqual(inexistente.status_code, 404)
        rascunhos = self.client.get("/api/v1/admin/catalogos/rascunhos")
        self.assertEqual(rascunhos.status_code, 200, rascunhos.text)
        self.assertEqual(rascunhos.json()["total"], 0)
        self.assertEqual(self.client.get("/api/v1/admin/catalogos/rascunhos/00000000-0000-0000-0000-000000000001/validacao").status_code, 404)
        sem_csrf = self.client.post(
            "/api/v1/admin/catalogos/00000000-0000-0000-0000-000000000001/rascunhos",
            json={"nome": "Não deve criar"},
            headers={"Idempotency-Key": "sem-csrf"},
        )
        self.assertEqual(sem_csrf.status_code, 403)
        self.assertEqual(sem_csrf.json()["detail"]["codigo"], "CSRF_TOKEN_AUSENTE")

        self.client.cookies.clear()
        self.autenticar(self.admin, expirado=True)
        self.assertEqual(self.client.get("/api/v1/admin/resumo").status_code, 401)
        escrita = self.client.post(
            "/api/v1/perguntas/importar",
            files={"arquivo": ("perguntas.xlsx", xlsx_valido())},
            headers={
                "Origin": "http://testserver",
                "X-CSRF-Token": "token-inutil",
            },
        )
        self.assertEqual(escrita.status_code, 401)

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
        cabecalhos = self.cabecalhos_csrf()
        resposta = self.client.post(
            "/api/v1/perguntas/importar",
            files={"arquivo": ("perguntas.xlsx", xlsx_valido(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=cabecalhos,
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

    def test_importacao_admin_rejeita_csrf_ausente_invalido_e_divergente(self):
        self.autenticar(self.admin)
        arquivo = {"arquivo": ("perguntas.xlsx", xlsx_valido())}
        ausente = self.client.post(
            "/api/v1/perguntas/importar",
            files=arquivo,
            headers={"Origin": "http://testserver"},
        )
        self.assertEqual(ausente.status_code, 403)
        self.assertEqual(ausente.json()["detail"]["codigo"], "CSRF_TOKEN_AUSENTE")

        cabecalhos = self.cabecalhos_csrf()
        token_valido = cabecalhos["X-CSRF-Token"]
        self.client.cookies.set(
            CSRF_COOKIE_NAME,
            "invalido",
            domain="testserver.local",
            path="/api/v1",
        )
        invalido = self.client.post(
            "/api/v1/perguntas/importar",
            files=arquivo,
            headers={**cabecalhos, "X-CSRF-Token": "invalido"},
        )
        self.assertEqual(invalido.status_code, 403)
        self.assertEqual(
            invalido.json()["detail"]["codigo"], "CSRF_TOKEN_INVALIDO"
        )

        self.client.cookies.set(
            CSRF_COOKIE_NAME,
            "outro-token",
            domain="testserver.local",
            path="/api/v1",
        )
        divergente = self.client.post(
            "/api/v1/perguntas/importar",
            files=arquivo,
            headers={**cabecalhos, "X-CSRF-Token": token_valido},
        )
        self.assertEqual(divergente.status_code, 403)
        self.assertEqual(
            divergente.json()["detail"]["codigo"], "CSRF_TOKEN_DIVERGENTE"
        )

    def test_importacao_admin_rejeita_token_expirado_e_origem_alheia(self):
        self.autenticar(self.admin)
        sessao = self.client.cookies.get(JWT_COOKIE_NAME)
        expirado = criar_token_csrf(
            self.admin.id,
            sessao,
            agora=datetime.now(timezone.utc) - timedelta(hours=1),
            duracao=timedelta(minutes=1),
        )
        self.client.cookies.set(
            CSRF_COOKIE_NAME,
            expirado,
            domain="testserver.local",
            path="/api/v1",
        )
        arquivo = {"arquivo": ("perguntas.xlsx", xlsx_valido())}
        resposta = self.client.post(
            "/api/v1/perguntas/importar",
            files=arquivo,
            headers={
                "Origin": "http://testserver",
                "X-CSRF-Token": expirado,
            },
        )
        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(
            resposta.json()["detail"]["codigo"], "CSRF_TOKEN_INVALIDO"
        )

        self.client.cookies.delete(
            CSRF_COOKIE_NAME, domain="testserver.local", path="/api/v1"
        )
        cabecalhos = self.cabecalhos_csrf()
        origem = self.client.post(
            "/api/v1/perguntas/importar",
            files=arquivo,
            headers={**cabecalhos, "Origin": "https://hostil.example"},
        )
        self.assertEqual(origem.status_code, 403)
        self.assertEqual(
            origem.json()["detail"]["codigo"], "CSRF_ORIGEM_INVALIDA"
        )
        self.assertNotIn(
            cabecalhos["X-CSRF-Token"], origem.text
        )

        with patch.dict(os.environ, {
            "CSRF_TRUSTED_ORIGINS": "https://quizhub.tailef8ba8.ts.net",
            "LEGACY_ADMIN_IMPORT_ENABLED": "false",
        }):
            publica = self.client.post(
                "/api/v1/perguntas/importar",
                files=arquivo,
                headers={
                    **cabecalhos,
                    "Origin": "https://quizhub.tailef8ba8.ts.net",
                    "X-Forwarded-Host": "interno.invalid",
                    "X-Forwarded-Proto": "http",
                },
            )
        self.assertEqual(publica.status_code, 410)

        manipulada = self.client.post(
            "/api/v1/perguntas/importar",
            files=arquivo,
            headers={
                **cabecalhos,
                "Origin": "https://hostil.example",
                "X-Forwarded-Host": "quizhub.tailef8ba8.ts.net",
                "X-Forwarded-Proto": "https",
            },
        )
        self.assertEqual(manipulada.status_code, 403)
        self.assertEqual(
            manipulada.json()["detail"]["codigo"], "CSRF_ORIGEM_INVALIDA"
        )

        sem_origem = self.client.post(
            "/api/v1/perguntas/importar",
            files=arquivo,
            headers={"X-CSRF-Token": cabecalhos["X-CSRF-Token"]},
        )
        self.assertEqual(sem_origem.status_code, 403)
        self.assertEqual(
            sem_origem.json()["detail"]["codigo"], "CSRF_ORIGEM_AUSENTE"
        )

        with patch.dict(os.environ, {"LEGACY_ADMIN_IMPORT_ENABLED": "false"}):
            referer = self.client.post(
                "/api/v1/perguntas/importar",
                files=arquivo,
                headers={
                    "Referer": "http://testserver/admin",
                    "X-CSRF-Token": cabecalhos["X-CSRF-Token"],
                },
            )
        self.assertEqual(referer.status_code, 410)

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
