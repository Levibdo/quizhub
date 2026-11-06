#!/usr/bin/env python3
"""Cria um dump PostgreSQL sem repassar URLs SQLAlchemy para a libpq."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
from typing import Callable, Mapping, Sequence

from dotenv import dotenv_values
from sqlalchemy.engine import URL, make_url


class BackupError(RuntimeError):
    """Erro operacional seguro para exibição ao operador."""


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _sanitize(message: str, secrets: Sequence[str] = ()) -> str:
    sanitized = message
    for secret in sorted((item for item in secrets if item), key=len, reverse=True):
        sanitized = sanitized.replace(secret, "[REDACTED]")
    sanitized = re.sub(
        r"postgres(?:ql)?(?:\+[A-Za-z0-9_]+)?://\S+",
        "postgresql://[REDACTED]",
        sanitized,
        flags=re.IGNORECASE,
    )
    return sanitized[:2000]


def _load_database_url(*, env_file: Path | None, environ: Mapping[str, str]) -> str:
    value: object | None
    if env_file is not None:
        try:
            value = dotenv_values(env_file).get("DATABASE_URL")
        except OSError as exc:
            raise BackupError("Não foi possível ler o arquivo de ambiente.") from exc
    else:
        value = environ.get("DATABASE_URL")
    if not isinstance(value, str) or not value.strip():
        raise BackupError("DATABASE_URL não está configurada.")
    return value.strip()


def _validated_url(
    raw_url: str,
    *,
    expected_driver: str,
    expected_host: str,
    expected_port: int,
    expected_database: str,
) -> URL:
    try:
        url = make_url(raw_url)
    except Exception as exc:
        raise BackupError("DATABASE_URL inválida.") from exc

    if url.drivername != expected_driver:
        raise BackupError("Dialeto/driver de DATABASE_URL não autorizado.")
    if url.host != expected_host:
        raise BackupError("Host PostgreSQL diferente do alvo autorizado.")
    if url.port != expected_port:
        raise BackupError("Porta PostgreSQL diferente do alvo autorizado.")
    if url.database != expected_database:
        raise BackupError("Banco PostgreSQL diferente do alvo autorizado.")
    if not url.username or url.password is None:
        raise BackupError("DATABASE_URL deve conter usuário e senha.")
    if url.query:
        raise BackupError("Parâmetros adicionais em DATABASE_URL não são permitidos.")
    return url


def _pgpass_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:")


def _child_environment(source: Mapping[str, str], pgpass_file: Path) -> dict[str, str]:
    child = dict(source)
    for key in ("DATABASE_URL", "PGPASSWORD", "PGPASSFILE", "PGSERVICE", "PGSERVICEFILE"):
        child.pop(key, None)
    child["PGPASSFILE"] = str(pgpass_file)
    return child


def _run_checked(
    args: list[str],
    *,
    env: Mapping[str, str],
    runner: Runner,
    secrets: Sequence[str],
    action: str,
) -> subprocess.CompletedProcess[str]:
    try:
        result = runner(
            args,
            env=dict(env),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise BackupError(f"Não foi possível executar {action}.") from exc
    if result.returncode != 0:
        detail = _sanitize(result.stderr or result.stdout or "sem detalhes", secrets)
        raise BackupError(f"{action} falhou: {detail}")
    return result


def create_backup(
    *,
    database_url: str,
    destination: Path,
    expected_driver: str,
    expected_host: str,
    expected_port: int,
    expected_database: str,
    pg_dump: str = "pg_dump",
    pg_restore: str = "pg_restore",
    environ: Mapping[str, str] | None = None,
    runner: Runner = subprocess.run,
) -> Path:
    """Cria, valida e instala atomicamente um dump customizado."""

    url = _validated_url(
        database_url,
        expected_driver=expected_driver,
        expected_host=expected_host,
        expected_port=expected_port,
        expected_database=expected_database,
    )
    destination = destination.resolve()
    if destination.exists():
        raise BackupError("O arquivo de destino já existe; recusando sobrescrita.")
    if not destination.parent.is_dir():
        raise BackupError("O diretório de destino não existe.")

    pg_dump_path = shutil.which(pg_dump) if os.sep not in pg_dump else pg_dump
    pg_restore_path = shutil.which(pg_restore) if os.sep not in pg_restore else pg_restore
    if not pg_dump_path or not pg_restore_path:
        raise BackupError("pg_dump e pg_restore devem estar disponíveis.")

    password = url.password or ""
    username = url.username or ""
    source_env = environ if environ is not None else os.environ
    secrets = (database_url, password)

    with tempfile.TemporaryDirectory(prefix="quizhub-pg-backup-") as auth_dir_name:
        auth_dir = Path(auth_dir_name)
        os.chmod(auth_dir, stat.S_IRWXU)
        pgpass = auth_dir / "pgpass"
        pgpass.write_text(
            ":".join(
                _pgpass_escape(value)
                for value in (
                    expected_host,
                    str(expected_port),
                    expected_database,
                    username,
                    password,
                )
            )
            + "\n",
            encoding="utf-8",
        )
        os.chmod(pgpass, stat.S_IRUSR | stat.S_IWUSR)
        child_env = _child_environment(source_env, pgpass)

        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        os.close(fd)
        temporary_dump = Path(temporary_name)
        os.chmod(temporary_dump, stat.S_IRUSR | stat.S_IWUSR)
        try:
            dump_args = [
                str(pg_dump_path),
                "--format=custom",
                "--no-password",
                "--host",
                expected_host,
                "--port",
                str(expected_port),
                "--username",
                username,
                "--file",
                str(temporary_dump),
                expected_database,
            ]
            _run_checked(
                dump_args,
                env=child_env,
                runner=runner,
                secrets=secrets,
                action="pg_dump",
            )
            if temporary_dump.stat().st_size == 0:
                raise BackupError("pg_dump produziu um arquivo vazio.")
            _run_checked(
                [str(pg_restore_path), "--list", str(temporary_dump)],
                env=child_env,
                runner=runner,
                secrets=secrets,
                action="validação pg_restore --list",
            )
            os.replace(temporary_dump, destination)
            os.chmod(destination, stat.S_IRUSR | stat.S_IWUSR)
        finally:
            temporary_dump.unlink(missing_ok=True)

    return destination


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-driver", default="postgresql+psycopg")
    parser.add_argument("--expected-host", required=True)
    parser.add_argument("--expected-port", required=True, type=int)
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--pg-dump", default="pg_dump")
    parser.add_argument("--pg-restore", default="pg_restore")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        database_url = _load_database_url(env_file=args.env_file, environ=os.environ)
        result = create_backup(
            database_url=database_url,
            destination=args.output,
            expected_driver=args.expected_driver,
            expected_host=args.expected_host,
            expected_port=args.expected_port,
            expected_database=args.expected_database,
            pg_dump=args.pg_dump,
            pg_restore=args.pg_restore,
        )
    except BackupError as exc:
        print(f"ERRO: {exc}", file=os.sys.stderr)
        return 1
    print(f"Backup PostgreSQL validado: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
