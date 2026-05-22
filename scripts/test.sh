#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-"$ROOT/.venv/bin/python"}"

if [[ ! -x "$PYTHON" ]]; then
  echo "Expected virtual environment Python at $PYTHON" >&2
  echo "Create it with: python -m venv .venv" >&2
  echo "Then install dev dependencies with: .venv/bin/python -m pip install -e \".[dev]\"" >&2
  exit 1
fi

exec "$PYTHON" -m pytest "$@"
