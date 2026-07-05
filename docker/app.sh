#!/bin/bash

set -e

python -m app.migrations
export SKIP_STARTUP_MIGRATIONS=1
exec gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind=0.0.0.0:5003
