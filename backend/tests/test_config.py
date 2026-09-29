import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import carregar_variaveis_ambiente


class TestConfig(unittest.TestCase):
    def test_carrega_arquivo_env(self):
        with tempfile.TemporaryDirectory() as diretorio:
            arquivo = Path(diretorio) / ".env"
            arquivo.write_text(
                "DATABASE_URL=postgresql://arquivo\nJWT_SECRET=segredo-arquivo\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                carregar_variaveis_ambiente(arquivo)

                self.assertEqual(
                    os.environ["DATABASE_URL"], "postgresql://arquivo"
                )
                self.assertEqual(os.environ["JWT_SECRET"], "segredo-arquivo")

    def test_variavel_explicita_tem_precedencia_sobre_arquivo_env(self):
        with tempfile.TemporaryDirectory() as diretorio:
            arquivo = Path(diretorio) / ".env"
            arquivo.write_text(
                "DATABASE_URL=postgresql://arquivo\nJWT_SECRET=segredo-arquivo\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"DATABASE_URL": "postgresql://ambiente"},
                clear=True,
            ):
                carregar_variaveis_ambiente(arquivo)

                self.assertEqual(
                    os.environ["DATABASE_URL"], "postgresql://ambiente"
                )
                self.assertEqual(os.environ["JWT_SECRET"], "segredo-arquivo")


if __name__ == "__main__":
    unittest.main()
