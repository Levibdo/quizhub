"""Execucao controlada e verificacao da revisao Alembic do QuizHub."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Sequence

from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.db.session import get_database_url


MIGRATION_LOCK_ID = 7_264_982_211
TRUE_VALUES = {"1", "true", "yes"}


def _target_revision() -> str:
    target = os.getenv("QUIZHUB_SCHEMA_REVISION", "").strip()
    if not target:
        raise RuntimeError("QUIZHUB_SCHEMA_REVISION deve ser definida explicitamente")

    script = ScriptDirectory.from_config(_alembic_config())
    if script.get_revision(target) is None:
        raise RuntimeError(f"revisao Alembic desconhecida: {target}")
    if script.get_heads() != [target]:
        raise RuntimeError(
            f"a revisao alvo {target} nao corresponde ao head unico versionado"
        )
    return target


def _alembic_config():
    from alembic.config import Config

    return Config("alembic.ini")


def _validate_migration_authorization() -> None:
    mode = os.getenv("QUIZHUB_MIGRATION_MODE", "").strip().casefold()
    database_name = make_url(get_database_url()).database or ""

    if mode == "local":
        environment = os.getenv("QUIZHUB_LOCAL_ENVIRONMENT", "").strip().casefold()
        if environment != "development" or not database_name.startswith("quizhub_local"):
            raise RuntimeError(
                "migration local recusada: use ambiente development e banco quizhub_local*"
            )
        return

    if mode == "controlled":
        allowed = os.getenv("QUIZHUB_ALLOW_PERSISTENT_MIGRATIONS", "").strip().casefold()
        if allowed not in TRUE_VALUES:
            raise RuntimeError(
                "migration persistente recusada: falta autorizacao operacional explicita"
            )
        return

    raise RuntimeError("QUIZHUB_MIGRATION_MODE deve ser 'local' ou 'controlled'")


def current_revision() -> str | None:
    engine = create_engine(get_database_url(), pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def check_schema() -> str:
    target = _target_revision()
    current = current_revision()
    if current != target:
        raise RuntimeError(
            f"schema incompatível: revisao atual={current or 'nenhuma'}, esperada={target}"
        )
    return target


def migrate() -> str:
    _validate_migration_authorization()
    target = _target_revision()
    engine = create_engine(get_database_url(), pool_pre_ping=True)
    try:
        with engine.connect() as lock_connection:
            if lock_connection.dialect.name != "postgresql":
                raise RuntimeError("migrations controladas exigem PostgreSQL")
            lock_connection.execute(
                text("SELECT pg_advisory_lock(:lock_id)"),
                {"lock_id": MIGRATION_LOCK_ID},
            )
            try:
                subprocess.run(
                    [sys.executable, "-m", "alembic", "upgrade", target],
                    check=True,
                )
            finally:
                lock_connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": MIGRATION_LOCK_ID},
                )
    finally:
        engine.dispose()

    return check_schema()


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("migrate", "check"))
    args = parser.parse_args(argv)
    revision = migrate() if args.action == "migrate" else check_schema()
    print(f"Alembic revision: {revision}")


if __name__ == "__main__":
    main()
