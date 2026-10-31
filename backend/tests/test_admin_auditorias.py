import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import AuditoriaAdministrativa, Usuario
from app.security import JWT_COOKIE_NAME, criar_token_acesso


class TestConsultaAuditoriaAdministrativa(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(
            self.engine, expire_on_commit=False, autoflush=False
        )
        self.env = patch.dict(os.environ, {
            "JWT_SECRET": "segredo-auditoria-de-teste-com-mais-de-32-bytes",
        })
        self.env.start()
        with self.factory() as db:
            self.admin = Usuario(
                nome="Administradora", email="audit-admin@example.com",
                senha_hash="hash-artificial", perfil="ADMIN", ativo=True,
            )
            self.outro_admin = Usuario(
                nome="Outro admin", email="audit-outro@example.com",
                senha_hash="hash-artificial", perfil="ADMIN", ativo=True,
            )
            self.jogador = Usuario(
                nome="Jogador", email="audit-player@example.com",
                senha_hash="hash-artificial", perfil="JOGADOR", ativo=True,
            )
            self.admin_inativo = Usuario(
                nome="Admin inativo", email="audit-inativo@example.com",
                senha_hash="hash-artificial", perfil="ADMIN", ativo=False,
            )
            db.add_all([
                self.admin, self.outro_admin, self.jogador, self.admin_inativo,
            ])
            db.commit()

        def banco_teste():
            with self.factory() as db:
                yield db

        app.dependency_overrides[get_db] = banco_teste
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.env.stop()
        self.engine.dispose()

    def autenticar(self, usuario):
        self.client.cookies.clear()
        self.client.cookies.set(
            JWT_COOKIE_NAME, criar_token_acesso(usuario.id)
        )

    def registrar(self, *, identificador, administrador=None, dias=0,
                  operacao="IMPORTAR_PERGUNTAS", recurso_id="recurso-1",
                  resultado="SUCESSO", detalhes=None):
        with self.factory() as db:
            db.add(AuditoriaAdministrativa(
                id=UUID(identificador),
                administrador_id=(administrador or self.admin).id,
                ocorrida_em=datetime(2026, 1, 10, 12, tzinfo=timezone.utc)
                + timedelta(days=dias),
                operacao=operacao,
                recurso_tipo="CATALOGO",
                recurso_id=recurso_id,
                resultado=resultado,
                catalogo_id="quiz_classico_v2",
                catalogo_versao=2,
                detalhes=detalhes,
            ))
            db.commit()

    def test_exige_admin_ativo(self):
        self.assertEqual(
            self.client.get("/api/v1/admin/auditorias").status_code, 401
        )
        self.autenticar(self.jogador)
        self.assertEqual(
            self.client.get("/api/v1/admin/auditorias").status_code, 403
        )
        self.autenticar(self.admin_inativo)
        self.assertEqual(
            self.client.get("/api/v1/admin/auditorias").status_code, 401
        )
        self.autenticar(self.admin)
        resposta = self.client.get("/api/v1/admin/auditorias")
        self.assertEqual(resposta.status_code, 200, resposta.text)
        self.assertEqual(resposta.json(), {
            "itens": [], "pagina": 1, "limite": 20,
            "total": 0, "total_paginas": 0,
        })

    def test_pagina_e_ordenacao_sao_estaveis(self):
        self.registrar(
            identificador="00000000-0000-0000-0000-000000000001",
            recurso_id="primeiro",
        )
        self.registrar(
            identificador="00000000-0000-0000-0000-000000000002",
            recurso_id="segundo",
        )
        self.registrar(
            identificador="00000000-0000-0000-0000-000000000003",
            recurso_id="mais-recente", dias=1,
        )
        self.autenticar(self.admin)
        resposta = self.client.get(
            "/api/v1/admin/auditorias", params={"limite": 2, "pagina": 1}
        )
        self.assertEqual(resposta.status_code, 200, resposta.text)
        corpo = resposta.json()
        self.assertEqual(corpo["total"], 3)
        self.assertEqual(corpo["total_paginas"], 2)
        self.assertEqual(
            [item["recurso_id"] for item in corpo["itens"]],
            ["mais-recente", "segundo"],
        )
        segunda = self.client.get(
            "/api/v1/admin/auditorias", params={"limite": 2, "pagina": 2}
        ).json()
        self.assertEqual(
            [item["recurso_id"] for item in segunda["itens"]], ["primeiro"]
        )

    def test_filtros_isolados_e_combinados(self):
        self.registrar(
            identificador="00000000-0000-0000-0000-000000000011",
            recurso_id="lote-alpha", resultado="REJEITADA",
        )
        self.registrar(
            identificador="00000000-0000-0000-0000-000000000012",
            administrador=self.outro_admin, dias=2,
            operacao="ATIVAR_CATALOGO", recurso_id="lote-beta",
        )
        self.autenticar(self.admin)
        casos = [
            ({"resultado": "REJEITADA"}, "lote-alpha"),
            ({"administrador_id": str(self.outro_admin.id)}, "lote-beta"),
            ({"operacao": "ATIVAR_CATALOGO"}, "lote-beta"),
            ({"busca": "BETA"}, "lote-beta"),
            ({
                "resultado": "SUCESSO", "operacao": "ATIVAR_CATALOGO",
                "inicio": "2026-01-11T00:00:00Z",
                "fim": "2026-01-13T00:00:00Z",
            }, "lote-beta"),
        ]
        for parametros, esperado in casos:
            with self.subTest(parametros=parametros):
                resposta = self.client.get(
                    "/api/v1/admin/auditorias", params=parametros
                )
                self.assertEqual(resposta.status_code, 200, resposta.text)
                self.assertEqual(resposta.json()["total"], 1)
                self.assertEqual(
                    resposta.json()["itens"][0]["recurso_id"], esperado
                )

    def test_valida_datas_limites_e_parametros(self):
        self.autenticar(self.admin)
        invalidos = [
            {"limite": 0}, {"limite": 101}, {"pagina": 0},
            {"resultado": "DESCONHECIDO"}, {"ordem": "aleatoria"},
            {"administrador_id": "nao-e-uuid"},
            {"inicio": "2026-01-12T00:00:00Z", "fim": "2026-01-11T00:00:00Z"},
            {"inicio": "2026-01-12T00:00:00"},
        ]
        for parametros in invalidos:
            with self.subTest(parametros=parametros):
                self.assertEqual(self.client.get(
                    "/api/v1/admin/auditorias", params=parametros
                ).status_code, 422)

    def test_sanitiza_detalhes_historicos_na_leitura(self):
        self.registrar(
            identificador="00000000-0000-0000-0000-000000000021",
            detalhes={
                "token_acesso": "nao-deve-sair",
                "senha": "nao-deve-sair",
                "quantidade": 3,
            },
        )
        self.autenticar(self.admin)
        corpo = self.client.get("/api/v1/admin/auditorias").json()
        item = corpo["itens"][0]
        self.assertEqual(item["detalhes"]["token_acesso"], "[REMOVIDO]")
        self.assertEqual(item["detalhes"]["senha"], "[REMOVIDO]")
        self.assertEqual(item["detalhes"]["quantidade"], 3)
        serializado = str(corpo).lower()
        self.assertNotIn("nao-deve-sair", serializado)
        self.assertNotIn("senha_hash", serializado)
        self.assertNotIn("email", serializado)


if __name__ == "__main__":
    unittest.main()
