#!/usr/bin/env bash
set -o errexit

python manage.py migrate --noinput
gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers "${WEB_CONCURRENCY:-3}" --timeout 120
