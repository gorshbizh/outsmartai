#!/bin/bash

set -euo pipefail

COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env"

if [[ ! -f "$COMPOSE_FILE" || ! -f "$ENV_FILE" ]]; then
    echo "Run this script from the repo root after creating .env."
    exit 1
fi

if grep -q '^DB_AUTO_SEED=' "$ENV_FILE"; then
    sed -i.bak 's/^DB_AUTO_SEED=.*/DB_AUTO_SEED=False/' "$ENV_FILE"
else
    printf '\nDB_AUTO_SEED=False\n' >> "$ENV_FILE"
fi

echo "DB_AUTO_SEED is now False in $ENV_FILE."
echo "Restarting the backend to pick up the change..."
docker compose -f "$COMPOSE_FILE" restart backend

echo
echo "Backend status:"
docker compose -f "$COMPOSE_FILE" ps backend
