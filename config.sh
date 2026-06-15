#!/usr/bin/env bash
# macOS / Linux equivalent of config.cmd — one-time setup.
set -euo pipefail
cd "$(dirname "$0")"

echo "============================================================"
echo "  TCA Catch Reports Export - one-time setup"
echo "============================================================"
echo

# --- 1. Find a usable Python (3.10+) ---------------------------------------
PY=""
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
fi

if [ -z "$PY" ]; then
  echo "[X] Python was not found on this machine."
  echo
  echo "    Install Python 3.10 or newer, then run ./config.sh again:"
  echo "      brew install python        (if you use Homebrew)"
  echo "      or download from https://www.python.org/downloads/"
  exit 1
fi

if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "[X] Found Python, but it is older than 3.10. Please install 3.10+."
  "$PY" --version
  exit 1
fi
echo "[OK] $("$PY" --version)"

# --- 2. Create the virtual environment -------------------------------------
if [ ! -x ".venv/bin/python" ]; then
  echo "[..] Creating virtual environment (.venv) ..."
  "$PY" -m venv .venv
fi
VENVPY=".venv/bin/python"
echo "[OK] Virtual environment ready."

# --- 3. Install dependencies -----------------------------------------------
echo "[..] Installing dependencies (this can take a minute the first time) ..."
"$VENVPY" -m pip install --upgrade pip >/dev/null 2>&1 || true
"$VENVPY" -m pip install -e . >/dev/null
echo "[OK] Dependencies installed."

# --- 4. Make sure config files exist ---------------------------------------
if [ ! -f config.env ]; then
  echo "[X] config.env is missing from this folder."
  exit 1
fi

# config.env.local holds your private key and is not tracked by git.
# Recreate it from a template if this is a fresh clone.
if [ ! -f config.env.local ]; then
  echo "[..] Creating config.env.local for your private API key ..."
  cat > config.env.local <<'EOF'
# Local secrets - NOT tracked by git. Holds your private API key.
# config.sh fills this in for you, or paste your key after the = sign.
MT_EXPORT_API_KEY=tca_live_PASTE_YOUR_KEY_HERE
EOF
fi

# --- 5. Offer to store the API key -----------------------------------------
if ! grep -q "tca_live_PASTE_YOUR_KEY_HERE" config.env.local; then
  echo "[OK] An API key is already set in config.env.local."
  echo
  echo "Setup complete. Now run:  ./run.sh"
  exit 0
fi

echo
echo "The last step is your API key (we emailed it; it looks like tca_live_...)."
printf "Paste the API key and press Enter (or just Enter to do it later): "
read -r USERKEY || USERKEY=""

if [ -z "$USERKEY" ]; then
  echo
  echo "No key entered. Open config.env.local, paste your key after"
  echo "  MT_EXPORT_API_KEY="
  echo "then run:  ./run.sh"
  exit 0
fi

"$VENVPY" -c "import re,sys; p='config.env.local'; s=open(p,encoding='utf-8').read(); s=re.sub(r'(?m)^MT_EXPORT_API_KEY=.*$', 'MT_EXPORT_API_KEY='+sys.argv[1].strip(), s); open(p,'w',encoding='utf-8').write(s)" "$USERKEY"
echo "[OK] API key saved to config.env.local."
echo
echo "Setup complete. Now run:  ./run.sh"
