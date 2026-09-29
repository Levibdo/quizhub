import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import HTTPException, Response
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.v1.auth import cadastrar, login, logout, me
from app.db.base import Base
from app.models import Usuario
from app.schemas.auth import CadastroUsuario, LoginUsuario, UsuarioPublico
from app.security import (
    JWT_COOKIE_NAME,
    criar_token_acesso,
    identificar_usuario,
    obter_segredo_jwt,
    password_hash,
    usuario_atual,
)
from app.services.auth import ERRO_CREDENCIAIS, Autenticacao


class TestAutenticacao(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        self.servico = Autenticacao()
        self.env = patch.dict(
            os.environ,
            {"JWT_SECRET": "segredo-de-teste-com-tamanho-adequado"},
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.session.close()
        self.engine.dispose()

    def cadastrar_usuario(self, email="pessoa@example.com"):
        usuario = self.servico.cadastrar(
            self.session,
            "Pessoa Teste",
            email,
            "uma-senha-segura",
        )
        self.session.commit()
        self.session.refresh(usuario)
        return usuario

    def test_cadastro_valido_normaliza_email_e_armazena_hash(self):
        entrada = CadastroUsuario(
            nome="  Pessoa Teste  ",
            email="  PESSOA@EXAMPLE.COM  ",
            senha="uma-senha-segura",
        )
        usuario = self.servico.cadastrar(
            self.session, entrada.nome, entrada.email, entrada.senha
        )

        self.assertEqual(usuario.nome, "Pessoa Teste")
        self.assertEqual(usuario.email, "pessoa@example.com")
        self.assertNotEqual(usuario.senha_hash, entrada.senha)
        self.assertTrue(password_hash.verify(entrada.senha, usuario.senha_hash))
        self.assertNotIn(
            "senha_hash",
            UsuarioPublico.model_validate(usuario).model_dump(),
        )

    def test_cadastro_duplicado_retorna_409(self):
        self.cadastrar_usuario("  PESSOA@EXAMPLE.COM  ")
        with self.assertRaises(HTTPException) as error:
            self.cadastrar_usuario("pessoa@example.com")
        self.assertEqual(error.exception.status_code, 409)

    def test_campos_invalidos_sao_rejeitados(self):
        casos = (
            {"nome": " ", "email": "pessoa@example.com", "senha": "12345678"},
            {"nome": "Pessoa", "email": "invalido", "senha": "12345678"},
            {"nome": "Pessoa", "email": "pessoa@example.com", "senha": "curta"},
        )
        for dados in casos:
            with self.subTest(dados=dados), self.assertRaises(ValidationError):
                CadastroUsuario(**dados)

    def test_login_correto_cria_cookie_e_jwt_valido(self):
        usuario = self.cadastrar_usuario()
        response = Response()
        retornado = login(
            LoginUsuario(email=usuario.email, senha="uma-senha-segura"),
            response,
            self.session,
        )

        self.assertEqual(retornado.id, usuario.id)
        cookie = response.headers["set-cookie"]
        self.assertIn(f"{JWT_COOKIE_NAME}=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=lax", cookie)
        self.assertIn("Max-Age=28800", cookie)
        self.assertNotIn("Secure", cookie)
        token = cookie.split(";", 1)[0].split("=", 1)[1]
        self.assertEqual(identificar_usuario(token, self.session).id, usuario.id)

    def test_cookie_secure_e_segredo_sao_configuraveis(self):
        usuario = self.cadastrar_usuario()
        with patch.dict(os.environ, {"JWT_COOKIE_SECURE": "true"}):
            response = Response()
            login(
                LoginUsuario(email=usuario.email, senha="uma-senha-segura"),
                response,
                self.session,
            )
        self.assertIn("Secure", response.headers["set-cookie"])

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "JWT_SECRET"):
                obter_segredo_jwt()

    def test_cadastro_endpoint_tambem_cria_cookie(self):
        response = Response()
        usuario = cadastrar(
            CadastroUsuario(
                nome="Nova Pessoa",
                email="nova@example.com",
                senha="uma-senha-segura",
            ),
            response,
            self.session,
        )
        self.assertEqual(usuario.email, "nova@example.com")
        self.assertIn("HttpOnly", response.headers["set-cookie"])

    def test_falha_ao_criar_jwt_desfaz_cadastro(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "JWT_SECRET"):
                cadastrar(
                    CadastroUsuario(
                        nome="Cadastro Incompleto",
                        email="incompleto@example.com",
                        senha="uma-senha-segura",
                    ),
                    Response(),
                    self.session,
                )

        usuario = self.session.scalar(
            select(Usuario).where(Usuario.email == "incompleto@example.com")
        )
        self.assertIsNone(usuario)

    def test_login_invalido_usa_mensagem_generica(self):
        self.cadastrar_usuario()
        casos = (
            LoginUsuario(email="pessoa@example.com", senha="senha-incorreta"),
            LoginUsuario(email="ausente@example.com", senha="senha-incorreta"),
        )
        for entrada in casos:
            with self.subTest(email=entrada.email), self.assertRaises(HTTPException) as error:
                self.servico.autenticar(self.session, entrada.email, entrada.senha)
            self.assertEqual(error.exception.status_code, 401)
            self.assertEqual(error.exception.detail, ERRO_CREDENCIAIS)

    def test_usuario_inativo_nao_pode_entrar(self):
        usuario = self.cadastrar_usuario()
        usuario.ativo = False
        self.session.commit()
        with self.assertRaises(HTTPException) as error:
            self.servico.autenticar(
                self.session, usuario.email, "uma-senha-segura"
            )
        self.assertEqual(error.exception.status_code, 401)
        self.assertEqual(error.exception.detail, ERRO_CREDENCIAIS)

    def test_jwt_expirado_e_adulterado_sao_rejeitados(self):
        usuario = self.cadastrar_usuario()
        expirado = criar_token_acesso(
            usuario.id,
            agora=datetime.now(timezone.utc) - timedelta(hours=9),
        )
        valido = criar_token_acesso(usuario.id)
        adulterado = valido[:-1] + ("a" if valido[-1] != "a" else "b")

        for token in (expirado, adulterado):
            with self.subTest(token=token[-8:]), self.assertRaises(HTTPException) as error:
                identificar_usuario(token, self.session)
            self.assertEqual(error.exception.status_code, 401)

    def test_me_sem_autenticacao_e_logout(self):
        with self.assertRaises(HTTPException) as error:
            usuario_atual(None)
        self.assertEqual(error.exception.status_code, 401)

        usuario = self.cadastrar_usuario()
        self.assertEqual(me(usuario).id, usuario.id)

        response = Response()
        logout(response)
        cookie = response.headers["set-cookie"]
        self.assertIn(f"{JWT_COOKIE_NAME}=", cookie)
        self.assertIn("Max-Age=0", cookie)


if __name__ == "__main__":
    unittest.main()
