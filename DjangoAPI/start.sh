#!/bin/sh
set -eu

PORT="${PORT:-8080}"
mkdir -p /app/staticfiles
mkdir -p "${U2NET_HOME:-/app/.u2net}"

echo "[migrating] migrate..."
python manage.py migrate --noinput


# ---------------------------------------------------

echo "[start] gunicorn..."
exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT}" \
  --workers "${WEB_CONCURRENCY:-1}"
