import os
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

from app.security import criar_token_csrf, validar_token_csrf

from app.services.seguranca_administrativa import (
    ArquivoAdministrativoMuitoGrande,
    importacao_legada_habilitada,
    ler_upload_limitado,
    limite_importacao_legada,
    sanitizar_detalhes_auditoria,
)


class TestSegurancaAdministrativa(unittest.TestCase):
    def test_importador_legado_habilitado_por_padrao_aceita_desativacao(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(importacao_legada_habilitada())
        with patch.dict(os.environ, {"LEGACY_ADMIN_IMPORT_ENABLED": "false"}):
            self.assertFalse(importacao_legada_habilitada())

    def test_upload_limitado_nao_le_conteudo_arbitrariamente_grande(self):
        self.assertEqual(ler_upload_limitado(BytesIO(b"1234"), 4), b"1234")
        with self.assertRaises(ArquivoAdministrativoMuitoGrande):
            ler_upload_limitado(BytesIO(b"12345"), 4)

    def test_limite_invalido_falha_de_forma_explicita(self):
        with patch.dict(os.environ, {"LEGACY_ADMIN_IMPORT_MAX_BYTES": "0"}):
            with self.assertRaises(RuntimeError):
                limite_importacao_legada()

    def test_detalhes_de_auditoria_removem_segredos(self):
        detalhes = sanitizar_detalhes_auditoria({
            "resultado": "ok",
            "senha": "nao-persistir",
            "interno": {"access_token": "nao-persistir", "quantidade": 2},
        })
        self.assertEqual(detalhes["resultado"], "ok")
        self.assertEqual(detalhes["senha"], "[REMOVIDO]")
        self.assertEqual(detalhes["interno"]["access_token"], "[REMOVIDO]")
        self.assertEqual(detalhes["interno"]["quantidade"], 2)

    def test_detalhes_extensos_sao_limitados(self):
        detalhes = sanitizar_detalhes_auditoria({"texto": "x" * 20_000})
        self.assertLessEqual(len(detalhes["texto"]), 500)

    def test_token_csrf_e_vinculado_a_sessao(self):
        usuario = SimpleNamespace(id=uuid4())
        with patch.dict(
            os.environ,
            {"JWT_SECRET": "segredo-csrf-de-teste-com-32-bytes"},
        ):
            token = criar_token_csrf(usuario.id, "sessao-original")
            validar_token_csrf(token, "sessao-original", usuario)
            with self.assertRaises(HTTPException) as erro:
                validar_token_csrf(token, "outra-sessao", usuario)
        self.assertEqual(erro.exception.status_code, 403)
        self.assertEqual(
            erro.exception.detail["codigo"], "CSRF_TOKEN_INVALIDO"
        )


if __name__ == "__main__":
    unittest.main()
