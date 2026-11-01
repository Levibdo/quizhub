#!/bin/sh
set -eu

case "${1:-serve}" in
  migrate)
    exec python -m app.db.migrations migrate
    ;;
  serve)
    python -m app.db.migrations check
    if [ "${QUIZHUB_BOOTSTRAP_OFFICIAL_CATALOGS:-}" = "true" ]; then
      python -m app.db.bootstrap_local
    fi
    ;;
  *)
    echo "uso: docker-entrypoint.sh [migrate|serve]" >&2
    exit 64
    ;;
esac

exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
