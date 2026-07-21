#!/bin/bash
# Local dev launcher: seed the mock DB, then serve API + built UI on :8014.
set -e
cd "$(dirname "$0")"
export BIDDING_MOCK=0
export SQLITE_DATA_DIR="${SQLITE_DATA_DIR:-/tmp/bidding-dev}"
export PYTHONPATH=.
../.venv/bin/python seed.py || true
exec ../.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8014
