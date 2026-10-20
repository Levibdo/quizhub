import os
import unittest
from unittest.mock import patch

from app.db.bootstrap_local import _validar_banco_local


class BootstrapLocalTests(unittest.TestCase):
    def test_exige_habilitacao_explicita(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "habilite explicitamente"):
                _validar_banco_local()

    def test_recusa_banco_sem_prefixo_local(self):
        ambiente = {
            "QUIZHUB_LOCAL_ENVIRONMENT": "development",
            "QUIZHUB_BOOTSTRAP_OFFICIAL_CATALOGS": "true",
            "DATABASE_URL": "postgresql+psycopg://user:pass@db/quizhub_prod_db",
        }
        with patch.dict(os.environ, ambiente, clear=True):
            with self.assertRaisesRegex(RuntimeError, "prefixo 'quizhub_local'"):
                _validar_banco_local()

    def test_aceita_banco_local_explicitamente_habilitado(self):
        ambiente = {
            "QUIZHUB_LOCAL_ENVIRONMENT": "development",
            "QUIZHUB_BOOTSTRAP_OFFICIAL_CATALOGS": "true",
            "DATABASE_URL": "postgresql+psycopg://user:pass@db/quizhub_local_team",
        }
        with patch.dict(os.environ, ambiente, clear=True):
            self.assertEqual(_validar_banco_local(), "quizhub_local_team")


if __name__ == "__main__":
    unittest.main()
