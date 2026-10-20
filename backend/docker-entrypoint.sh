#!/bin/sh
set -eu

python -m alembic upgrade 0019
python -m app.db.bootstrap_local

exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
