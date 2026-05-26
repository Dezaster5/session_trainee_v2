#!/usr/bin/env bash
set -o errexit

python manage.py migrate --noinput

if [ "${AUTO_IMPORT_QUESTIONS:-0}" = "1" ]; then
  echo "AUTO_IMPORT_QUESTIONS=1: starting question import in background"
  python manage.py import_questions &
fi

echo "Starting gunicorn on 0.0.0.0:${PORT:-8000}"
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers "${WEB_CONCURRENCY:-3}" --timeout 120
