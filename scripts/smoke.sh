#!/usr/bin/env bash
# Run the iTakt VG smoke test.
# Usage: bash scripts/smoke.sh
set -euo pipefail
cd "$(dirname "$0")/.."
exec .venv/bin/python scripts/smoke_test.py "$@"
