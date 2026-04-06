#!/bin/bash
# Run audit fix tests inside Docker or locally.
#
# Usage:
#   ./run_tests.sh                    # Run all tests
#   ./run_tests.sh -k "TestJWT"       # Run specific test class
#   ./run_tests.sh -v                 # Verbose output
#
# Docker usage (if not running locally):
#   docker compose exec api bash -c "cd /app && pip install pytest pytest-asyncio && python -m pytest tests/test_audit_fixes.py -v"

set -e
cd "$(dirname "$0")"

echo "=== Hunter888 Audit Fix Tests ==="
echo ""

# Check if we're in Docker or local
if command -v python -m pytest &>/dev/null; then
    python -m pytest tests/test_audit_fixes.py tests/test_auth.py -v --tb=short "$@"
else
    echo "pytest not found. Install with: pip install pytest pytest-asyncio"
    echo ""
    echo "Or run inside Docker:"
    echo "  docker compose exec api bash -c 'python -m pytest tests/test_audit_fixes.py -v'"
    exit 1
fi
