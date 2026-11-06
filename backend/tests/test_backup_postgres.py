import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.backup_postgres import BackupError, _load_database_url, create_backup


SYNTHETIC_PASSWORD = "synthetic-secret-not-real"
VALID_URL = (
    "postgresql+psycopg://backup_user:"
    f"{SYNTHETIC_PASSWORD}@127.0.0.1:55432/quizhub_backup_test"
)


class RecordingRunner:
    def __init__(
        self,
        *,
        dump_returncode=0,
        dump_stderr="",
        restore_returncode=0,
        restore_stderr="",
    ):
        self.calls = []
        self.pgpass_paths = []
        self.pgpass_modes = []
        self.pgpass_had_password = []
        self.dump_returncode = dump_returncode
        self.dump_stderr = dump_stderr
        self.restore_returncode = restore_returncode
        self.restore_stderr = restore_stderr

    def __call__(self, args, **kwargs):
        args = list(args)
        env = kwargs["env"]
        self.calls.append((args, dict(env)))
        pgpass = Path(env["PGPASSFILE"])
        self.pgpass_paths.append(pgpass)
        self.pgpass_modes.append(stat.S_IMODE(pgpass.stat().st_mode))
        self.pgpass_had_password.append(SYNTHETIC_PASSWORD in pgpass.read_text())
        if "--format=custom" in args:
            output = Path(args[args.index("--file") + 1])
            output.write_bytes(b"synthetic custom dump")
            return subprocess.CompletedProcess(
                args, self.dump_returncode, "", self.dump_stderr
            )
        return subprocess.CompletedProcess(
            args, self.restore_returncode, "synthetic list", self.restore_stderr
        )


def run_backup(tmp: str, runner: RecordingRunner) -> Path:
    return create_backup(
        database_url=VALID_URL,
        destination=Path(tmp) / "database.dump",
        expected_driver="postgresql+psycopg",
        expected_host="127.0.0.1",
        expected_port=55432,
        expected_database="quizhub_backup_test",
        pg_dump="/usr/bin/pg_dump",
        pg_restore="/usr/bin/pg_restore",
        environ={"DATABASE_URL": VALID_URL, "PGPASSWORD": SYNTHETIC_PASSWORD},
        runner=runner,
    )


class BackupPostgresTests(unittest.TestCase):
    def test_url_valida_usa_argumentos_separados_e_pgpass_temporario(self):
        runner = RecordingRunner()
        with tempfile.TemporaryDirectory() as tmp:
            result = run_backup(tmp, runner)
            self.assertTrue(result.is_file())
            self.assertEqual(stat.S_IMODE(result.stat().st_mode), 0o600)

        self.assertEqual(len(runner.calls), 2)
        dump_args, dump_env = runner.calls[0]
        joined_args = " ".join(dump_args)
        self.assertNotIn(SYNTHETIC_PASSWORD, joined_args)
        self.assertNotIn(VALID_URL, joined_args)
        self.assertNotIn("DATABASE_URL", dump_env)
        self.assertNotIn("PGPASSWORD", dump_env)
        self.assertEqual(runner.pgpass_modes, [0o600, 0o600])
        self.assertEqual(runner.pgpass_had_password, [True, True])
        self.assertTrue(all(not path.exists() for path in runner.pgpass_paths))

    def test_rejeita_url_invalida_sem_reproduzi_la(self):
        secret_input = "not-a-url-with-secret"
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(BackupError) as caught:
                create_backup(
                    database_url=secret_input,
                    destination=Path(tmp) / "database.dump",
                    expected_driver="postgresql+psycopg",
                    expected_host="127.0.0.1",
                    expected_port=55432,
                    expected_database="quizhub_backup_test",
                    pg_dump="/usr/bin/pg_dump",
                    pg_restore="/usr/bin/pg_restore",
                )
        self.assertNotIn(secret_input, str(caught.exception))

    def test_rejeita_host_inesperado(self):
        url = VALID_URL.replace("127.0.0.1", "db.example.invalid")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(BackupError, "Host PostgreSQL"):
                create_backup(
                    database_url=url,
                    destination=Path(tmp) / "database.dump",
                    expected_driver="postgresql+psycopg",
                    expected_host="127.0.0.1",
                    expected_port=55432,
                    expected_database="quizhub_backup_test",
                    pg_dump="/usr/bin/pg_dump",
                    pg_restore="/usr/bin/pg_restore",
                )

    def test_rejeita_banco_inesperado(self):
        url = VALID_URL.replace("quizhub_backup_test", "quizhub_prod_db")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(BackupError, "Banco PostgreSQL"):
                create_backup(
                    database_url=url,
                    destination=Path(tmp) / "database.dump",
                    expected_driver="postgresql+psycopg",
                    expected_host="127.0.0.1",
                    expected_port=55432,
                    expected_database="quizhub_backup_test",
                    pg_dump="/usr/bin/pg_dump",
                    pg_restore="/usr/bin/pg_restore",
                )

    def test_falha_autenticacao_e_sanitizada_e_remove_temporarios(self):
        runner = RecordingRunner(
            dump_returncode=1,
            dump_stderr=f"auth failed for {VALID_URL}; password={SYNTHETIC_PASSWORD}",
        )
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "database.dump"
            with self.assertRaises(BackupError) as caught:
                run_backup(tmp, runner)
            self.assertFalse(destination.exists())
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])
        message = str(caught.exception)
        self.assertNotIn(VALID_URL, message)
        self.assertNotIn(SYNTHETIC_PASSWORD, message)
        self.assertIn("[REDACTED]", message)
        self.assertTrue(all(not path.exists() for path in runner.pgpass_paths))

    def test_falha_execucao_pg_dump_nao_expoe_url(self):
        def missing_binary(*args, **kwargs):
            raise OSError("synthetic execution failure")

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(BackupError) as caught:
                create_backup(
                    database_url=VALID_URL,
                    destination=Path(tmp) / "database.dump",
                    expected_driver="postgresql+psycopg",
                    expected_host="127.0.0.1",
                    expected_port=55432,
                    expected_database="quizhub_backup_test",
                    pg_dump="/usr/bin/pg_dump",
                    pg_restore="/usr/bin/pg_restore",
                    runner=missing_binary,
                )
        self.assertNotIn(VALID_URL, str(caught.exception))
        self.assertNotIn(SYNTHETIC_PASSWORD, str(caught.exception))

    def test_falha_validacao_pg_restore_remove_dump_incompleto(self):
        runner = RecordingRunner(
            restore_returncode=1,
            restore_stderr=f"invalid archive from {VALID_URL}",
        )
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "database.dump"
            with self.assertRaises(BackupError) as caught:
                run_backup(tmp, runner)
            self.assertFalse(destination.exists())
        self.assertNotIn(VALID_URL, str(caught.exception))
        self.assertNotIn(SYNTHETIC_PASSWORD, str(caught.exception))

    def test_recusa_sobrescrever_backup_existente(self):
        runner = RecordingRunner()
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "database.dump"
            destination.write_bytes(b"preserve me")
            with self.assertRaisesRegex(BackupError, "recusando sobrescrita"):
                run_backup(tmp, runner)
            self.assertEqual(destination.read_bytes(), b"preserve me")
        self.assertEqual(runner.calls, [])

    def test_carrega_env_file_sem_alterar_ambiente(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(f"DATABASE_URL={VALID_URL}\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                loaded = _load_database_url(env_file=env_file, environ=os.environ)
                self.assertEqual(loaded, VALID_URL)
                self.assertNotIn("DATABASE_URL", os.environ)


if __name__ == "__main__":
    unittest.main()
