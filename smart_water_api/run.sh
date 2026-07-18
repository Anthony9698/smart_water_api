#!/usr/bin/with-contenv bashio

set -e

mkdir -p /data/images

export SMART_WATER_DATABASE_URL="sqlite:////data/smart_water.db"
export SMART_WATER_IMAGE_DIR="/data/images"

exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000