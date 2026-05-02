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

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "Working tree has modified tracked files; commit or stash them before deploy" >&2
  git status --short --untracked-files=no >&2
  exit 1
fi

git fetch origin "$BRANCH"
git pull --ff-only origin "$BRANCH"
export RELEASE_SHA="$(git rev-parse HEAD)"
export BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production up -d --build

# Post-deploy verification — fail loud if RELEASE_SHA didn't make it
# into the running container. Pre-2026-05-02 audit (FIND-007) the
# deploy regularly produced ``release_sha=unknown`` because operators
# would skip this script and run ``docker compose build`` directly,
# losing the env-var. Now that this script IS the canonical path
# (CLAUDE.md §2), the verification step closes the loop: if the
# container reports ``unknown`` after a build that explicitly set
# the SHA, something is broken in the Dockerfile ARG → ENV chain.
echo "Waiting 8s for API to come up before verification..."
sleep 8

VERSION_JSON="$(curl -fsS --max-time 10 https://x-hunter.expert/api/version || echo '{}')"
DEPLOYED_SHA="$(echo "$VERSION_JSON" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("release_sha","unknown"))' 2>/dev/null || echo unknown)"

if [[ "$DEPLOYED_SHA" == "$RELEASE_SHA" ]]; then
  echo "✓ Deploy verified — running RELEASE_SHA=$RELEASE_SHA"
elif [[ "$DEPLOYED_SHA" == "unknown" ]]; then
  echo "✗ /api/version reports release_sha=unknown — Dockerfile ARG/ENV chain broken or build did not consume the env-var" >&2
  echo "  Local: $RELEASE_SHA" >&2
  echo "  Remote: $VERSION_JSON" >&2
  exit 1
else
  echo "⚠ /api/version reports a DIFFERENT sha than this deploy — possible race with another deploy" >&2
  echo "  Local : $RELEASE_SHA" >&2
  echo "  Remote: $DEPLOYED_SHA" >&2
  exit 1
fi
