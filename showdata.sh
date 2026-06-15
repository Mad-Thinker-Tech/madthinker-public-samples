#!/usr/bin/env bash
# macOS / Linux equivalent of showdata.cmd — print the local mirror.
set -euo pipefail
cd "$(dirname "$0")"

# --- Preconditions ---------------------------------------------------------
if [ ! -x ".venv/bin/python" ]; then
  echo "[X] Not set up yet. Run ./config.sh first."
  exit 1
fi
if [ ! -f config.env ]; then
  echo "[X] config.env is missing from this folder."
  exit 1
fi

# Load shared settings (we only need the database path; no API key required
# just to view what has already been pulled).
load_env() {
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    case "$line" in ''|\#*) continue ;; esac
    export "${line%%=*}=${line#*=}"
  done < "$1"
}
load_env config.env

exec ".venv/bin/python" -m madthinker_export show
