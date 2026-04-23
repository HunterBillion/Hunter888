#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v git >/dev/null 2>&1; then
  echo "git is required" >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi

BRANCH="${DEPLOY_BRANCH:-main}"
export RELEASE_SHA="${RELEASE_SHA:-$(git rev-parse HEAD)}"
export BUILD_TIME="${BUILD_TIME:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"

if [[ "$(git rev-parse --abbrev-ref HEAD)" != "$BRANCH" ]]; then
  echo "Expected branch $BRANCH, got $(git rev-parse --abbrev-ref HEAD)" >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is dirty; commit or stash changes before deploy" >&2
  exit 1
fi

git fetch origin "$BRANCH"
git pull --ff-only origin "$BRANCH"
export RELEASE_SHA="$(git rev-parse HEAD)"
export BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production up -d --build

echo "Deployed RELEASE_SHA=$RELEASE_SHA"
echo "Verify: curl -s https://x-hunter.expert/api/version"
