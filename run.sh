#!/usr/bin/env bash
# macOS / Linux equivalent of run.cmd — pull catch reports.
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
if [ ! -f config.env.local ]; then
  echo "[X] config.env.local is missing. Run ./config.sh first to set your key."
  exit 1
fi

# --- Load settings: shared config.env first, then secret config.env.local ---
load_env() {
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"                       # tolerate CRLF line endings
    case "$line" in ''|\#*) continue ;; esac   # skip blanks and comments
    export "${line%%=*}=${line#*=}"
  done < "$1"
}
load_env config.env
load_env config.env.local

# --- Validate the API key --------------------------------------------------
if [ -z "${MT_EXPORT_API_KEY:-}" ]; then
  echo "[X] No API key set. Run ./config.sh, or paste your key into config.env.local."
  exit 1
fi
case "$MT_EXPORT_API_KEY" in
  *tca_live_PASTE_YOUR_KEY_HERE*)
    echo "[X] The API key in config.env.local is still the placeholder."
    echo "    Run ./config.sh to set the key we emailed you."
    exit 1
    ;;
esac

# --- Run the sync ----------------------------------------------------------
echo "Pulling catch reports from the export API ..."
echo
set +e
".venv/bin/python" -m madthinker_export sync
rc=$?
set -e
echo
if [ "$rc" -eq 0 ]; then
  echo "Done. Your data is in \"${MT_EXPORT_DB_PATH:-catch_reports.db}\"."
  if [ -n "${MT_EXPORT_PHOTO_DIR:-}" ]; then
    echo "Photos are in the \"${MT_EXPORT_PHOTO_DIR}\" folder."
  fi
else
  echo "Sync exited with code $rc. See the message above."
fi
exit "$rc"
