#!/usr/bin/env bash
# Launch the iTakt web dashboard.
# Usage: bash scripts/dashboard.sh [--port 8787]
set -euo pipefail
cd "$(dirname "$0")/.."
exec .venv/bin/python -m itakt.web_dashboard "$@"
