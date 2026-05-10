#!/bin/bash

set -euo pipefail

COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env"

require_file() {
    local path="$1"
    if [[ ! -f "$path" ]]; then
        echo "Missing $path. Run this script from the repo root."
        exit 1
    fi
}

get_env_value() {
    local key="$1"
    awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, "", $0); print $0}' "$ENV_FILE" | tail -n 1
}

set_env_value() {
    local key="$1"
    local value="$2"
    if grep -q "^${key}=" "$ENV_FILE"; then
        sed -i.bak "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
    else
        printf '\n%s=%s\n' "$key" "$value" >> "$ENV_FILE"
    fi
}

ensure_non_placeholder() {
    local key="$1"
    local value
    value="$(get_env_value "$key")"
    if [[ -z "$value" || "$value" == replace_with_* || "$value" == your_* || "$value" == change-me* ]]; then
        echo "Set a real value for $key in $ENV_FILE before running this script."
        exit 1
    fi
}

require_file "$COMPOSE_FILE"
require_file "$ENV_FILE"

ensure_non_placeholder "MYSQL_PASSWORD"
ensure_non_placeholder "MYSQL_ROOT_PASSWORD"
ensure_non_placeholder "ADMIN_PASSWORD"
ensure_non_placeholder "FLASK_SECRET_KEY"

set_env_value "DB_AUTO_INIT" "True"
set_env_value "DB_AUTO_SEED" "True"
set_env_value "ENABLE_FORMALGEO" "False"

echo "This will remove the Docker MySQL volume and recreate the database from scratch."
echo "Use this for the first VM setup, or when you intentionally want a clean reset."
read -r -p "Continue? [y/N] " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo "Resetting the stack and MySQL volume..."
docker compose -f "$COMPOSE_FILE" down -v

echo "Starting the stack..."
docker compose -f "$COMPOSE_FILE" up -d

echo
echo "Current service status:"
docker compose -f "$COMPOSE_FILE" ps

echo
echo "Recent backend logs:"
docker compose -f "$COMPOSE_FILE" logs backend --tail=80

echo
echo "MySQL bootstrap complete."
echo "Login username: $(get_env_value "ADMIN_USERNAME")"
echo "Login password: $(get_env_value "ADMIN_PASSWORD")"
echo "When login works, run ./scripts/set-vm-regular-mode.sh to disable reseeding."
