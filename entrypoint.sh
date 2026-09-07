#!/bin/sh
set -e

# Lab-scope simplification: migrations run from the container's own entrypoint rather than a
# separate one-off deploy step (e.g. a CodeDeploy lifecycle hook). Fine at this scale since
# blue/green replaces one task set at a time and Django's migration executor is transactional
# per-migration, but a genuinely concurrent first-migrate from multiple tasks starting at once
# (e.g. autoscaling right after a deploy) is a known race this doesn't fully guard against.
python manage.py migrate --noinput

exec gunicorn todoproject.wsgi:application --bind 0.0.0.0:8080 --workers 3
