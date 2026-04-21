#!/usr/bin/env bash
# Orchestrator for legal_ingest pipeline.
# Run: nohup bash run_all.sh > logs/ingest_$(date +%Y%m%d_%H%M).log 2>&1 &
set -euo pipefail

cd "$(dirname "$0")/../.."
export PYTHONUNBUFFERED=1

PY=.venv/bin/python
LOG_DIR="scripts/legal_ingest/logs"
mkdir -p "$LOG_DIR"

echo "[$(date +%H:%M:%S)] ━━━ legal_ingest pipeline START ━━━"

step() {
  local name="$1"
  shift
  echo ""
  echo "[$(date +%H:%M:%S)] ▶ $name"
  if "$@"; then
    echo "[$(date +%H:%M:%S)] ✓ $name OK"
  else
    echo "[$(date +%H:%M:%S)] ✗ $name FAILED"
    exit 1
  fi
}

# 127-FZ ingestion (fast, low risk)
step "01_fetch_127fz"         $PY -m scripts.legal_ingest.01_fetch_127fz
step "02_parse_127fz"         $PY -m scripts.legal_ingest.02_parse_127fz
step "03_load_127fz_to_db"    $PY -m scripts.legal_ingest.03_load_127fz_to_db

# Court practice (long-running)
step "04_fetch_sudact_sitemap"    $PY -m scripts.legal_ingest.04_fetch_sudact_sitemap
step "05_fetch_sudact_cases"      $PY -m scripts.legal_ingest.05_fetch_sudact_cases
step "06_filter_bankruptcy_cases" $PY -m scripts.legal_ingest.06_filter_bankruptcy_cases
step "07_load_cases_to_db"        $PY -m scripts.legal_ingest.07_load_cases_to_db

# Embeddings (depends on DB being populated)
step "08_embed_gemini"            $PY -m scripts.legal_ingest.08_embed_gemini

echo ""
echo "[$(date +%H:%M:%S)] ━━━ pipeline COMPLETE ━━━"
