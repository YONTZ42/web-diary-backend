#!/bin/sh
set -eu

PORT="${PORT:-8080}"
mkdir -p /app/staticfiles

echo "[start] making migrations.."
python manage.py makemigrations
echo "[migrating] migrate..."
python manage.py migrate --noinput

#echo "[start] collectstatic..."
#python manage.py collectstatic --noinput || true

# ---- Create superuser (email-based custom User) ----
# Required envs:
#   CREATE_SUPERUSER=1
#   DJANGO_SUPERUSER_EMAIL
#   DJANGO_SUPERUSER_PASSWORD
echo "[start] checking CREATE_SUPERUSER env: '$CREATE_SUPERUSER'"
if [ "${CREATE_SUPERUSER:-0}" = "1" ]; then
  echo "[start] ensure superuser..."
  python manage.py shell -c "
from django.contrib.auth import get_user_model
import os

User = get_user_model()
email = os.environ.get('DJANGO_SUPERUSER_EMAIL')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')

assert email and password, 'Missing DJANGO_SUPERUSER_EMAIL or PASSWORD'

if not User.objects.filter(email=email).exists():
    User.objects.create_superuser(
        email=email,
        password=password,
        is_staff=True,
        is_superuser=True,
    )
    print('created superuser:', email)
else:
    print('superuser already exists:', email)
"
fi
# ---------------------------------------------------

echo "[start] gunicorn..."
exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT}" \
  --workers "${WEB_CONCURRENCY:-2}"
