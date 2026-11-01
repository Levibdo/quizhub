import os
import unittest
from unittest.mock import MagicMock, patch

from app.db.migrations import (
    _target_revision,
    _validate_migration_authorization,
    check_schema,
)


class MigrationStartupTests(unittest.TestCase):
    def test_alvo_explicito_e_head_versionado(self):
        with patch.dict(os.environ, {"QUIZHUB_SCHEMA_REVISION": "0022"}, clear=True):
            self.assertEqual(_target_revision(), "0022")

    def test_recusa_alvo_ausente(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "definida explicitamente"):
                _target_revision()

    def test_recusa_revisao_que_nao_e_head(self):
        with patch.dict(os.environ, {"QUIZHUB_SCHEMA_REVISION": "0019"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "head unico"):
                _target_revision()

    def test_migration_local_exige_banco_e_ambiente_locais(self):
        environment = {
            "DATABASE_URL": "postgresql+psycopg://user:pass@db/quizhub_prod_db",
            "QUIZHUB_MIGRATION_MODE": "local",
            "QUIZHUB_LOCAL_ENVIRONMENT": "development",
        }
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(RuntimeError, "migration local recusada"):
                _validate_migration_authorization()

    def test_migration_local_autorizada(self):
        environment = {
            "DATABASE_URL": "postgresql+psycopg://user:pass@db/quizhub_local_test",
            "QUIZHUB_MIGRATION_MODE": "local",
            "QUIZHUB_LOCAL_ENVIRONMENT": "development",
        }
        with patch.dict(os.environ, environment, clear=True):
            _validate_migration_authorization()

    def test_migration_controlada_exige_autorizacao_separada(self):
        environment = {
            "DATABASE_URL": "postgresql+psycopg://user:pass@db/quizhub_prod_db",
            "QUIZHUB_MIGRATION_MODE": "controlled",
        }
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(RuntimeError, "autorizacao operacional"):
                _validate_migration_authorization()

    def test_migration_controlada_aceita_autorizacao_explicita(self):
        environment = {
            "DATABASE_URL": "postgresql+psycopg://user:pass@db/quizhub_prod_db",
            "QUIZHUB_MIGRATION_MODE": "controlled",
            "QUIZHUB_ALLOW_PERSISTENT_MIGRATIONS": "true",
        }
        with patch.dict(os.environ, environment, clear=True):
            _validate_migration_authorization()

    @patch("app.db.migrations.current_revision", return_value="0021")
    @patch("app.db.migrations.ScriptDirectory.from_config")
    def test_check_interrompe_backend_em_schema_incompativel(self, scripts, _current):
        scripts.return_value.get_revision.return_value = MagicMock()
        scripts.return_value.get_heads.return_value = ["0022"]
        with patch.dict(os.environ, {"QUIZHUB_SCHEMA_REVISION": "0022"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "atual=0021, esperada=0022"):
                check_schema()


if __name__ == "__main__":
    unittest.main()
