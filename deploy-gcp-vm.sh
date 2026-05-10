#!/bin/bash

set -euo pipefail

COMPOSE_FILE="docker-compose.prod.yml"
PULL_CHANGES=true
SHOW_LOGS=false

usage() {
    cat <<'EOF'
Usage: ./deploy-gcp-vm.sh [options]

Options:
  --no-pull    Skip git pull before rebuilding containers
  --logs       Show recent service logs after deployment
  --help       Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-pull)
            PULL_CHANGES=false
            shift
            ;;
        --logs)
            SHOW_LOGS=true
            shift
            ;;
        --help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

if [[ ! -f "$COMPOSE_FILE" ]]; then
    echo "Missing $COMPOSE_FILE. Run this script from the repo root."
    exit 1
fi

if [[ ! -f ".env" ]]; then
    echo "Missing .env. Copy .env.gcp.example to .env and fill in your secrets first."
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is not installed or not on PATH."
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose plugin is not available."
    exit 1
fi

echo "Starting GCP VM deployment..."

if [[ "$PULL_CHANGES" == true ]]; then
    if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        if [[ -n "$(git status --porcelain)" ]]; then
            echo "Working tree has local changes. Skipping git pull."
            echo "Use --no-pull to silence this message if that is intentional."
        else
            CURRENT_BRANCH="$(git branch --show-current || true)"
            if [[ -n "$CURRENT_BRANCH" ]]; then
                echo "Pulling latest changes for branch $CURRENT_BRANCH..."
            else
                echo "Pulling latest changes..."
            fi
            git pull --ff-only
        fi
    else
        echo "Git metadata not available. Skipping git pull."
    fi
fi

echo "Building and starting containers..."
docker compose -f "$COMPOSE_FILE" up -d --build

echo
echo "Current service status:"
docker compose -f "$COMPOSE_FILE" ps

if [[ "$SHOW_LOGS" == true ]]; then
    echo
    echo "Recent backend logs:"
    docker compose -f "$COMPOSE_FILE" logs backend --tail=50
    echo
    echo "Recent frontend logs:"
    docker compose -f "$COMPOSE_FILE" logs frontend --tail=50
    echo
    echo "Recent MySQL logs:"
    docker compose -f "$COMPOSE_FILE" logs mysql --tail=50
fi

echo
echo "Deployment complete."
