#!/bin/bash
# Ramses Accounts — one-click development preview (Mac only).
# Never starts an unprotected public tunnel; localhost is the default.
set -euo pipefail
cd "$(dirname "$0")"
printf '\n================================================\n'
printf '  Ramses Accounts | Test Preview V8.1E-G2R (test only)\n'
printf '================================================\n\n'
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Python 3 is missing. Install Python 3.11+ from python.org first.'
  echo 'Then open this file again.'
  read -r -p 'Press Enter to close...' _ || true
  exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
  echo 'Python 3.11+ is required. Install a supported Python version and reopen.'
  read -r -p 'Press Enter to close...' _ || true
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  echo 'Preparing isolated Python environment for Ramses ...'
  python3 -m venv .venv
fi
PYTHON="$(pwd)/.venv/bin/python"
if ! "$PYTHON" -c 'import fastapi, uvicorn, pydantic, openpyxl, httpx, google.auth, cryptography' >/dev/null 2>&1; then
  echo 'Installing Ramses dependencies once. No hosting subscription needed ...'
  "$PYTHON" -m pip install -r requirements.txt
fi
printf '\nChoose test mode:\n'
printf '  1) Local DEMO (recommended to start)\n'
printf '  2) Private HTTPS link to your email (Cloudflare Quick Tunnel)\n'
printf '  3) Local redacted June archive (618 historic entries)\n'
printf '  4) Security / Google / database diagnostic\n'
printf '  5) Create a password-encrypted private database backup\n'
printf '  6) Verify an existing encrypted backup (no restore)\n'
printf '\n'
read -r -p 'Enter 1-6: ' MODE
case "$MODE" in
  1) exec "$PYTHON" scripts/free_preview.py --local-only --demo ;;
  2)
    if ! command -v cloudflared >/dev/null 2>&1; then
      printf '\ncloudflared is not installed.\n'
      printf 'Install it with: brew install cloudflared\n'
      printf 'Official download: https://developers.cloudflare.com/tunnel/downloads/\n'
      printf 'The program will NOT fall back to a publicly accessible unprotected link.\n'
      read -r -p 'Press Enter to close...' _ || true
      exit 1
    fi
    read -r -p 'Exact email authorized to see this preview: ' ALLOWED_EMAIL
    # The Python launcher validates email syntax and keeps the tunnel email-protected.
    exec "$PYTHON" scripts/free_preview.py --email "$ALLOWED_EMAIL" --demo ;;
  3) exec "$PYTHON" scripts/free_preview.py --local-only --archive ;;
  4) "$PYTHON" scripts/preview_doctor.py; read -r -p 'Press Enter to close...' _ || true ;;
  5)
    read -r -p 'Full path to SQLite database (e.g. data/free-preview.sqlite3): ' SQLITE_PATH
    if [ -z "$SQLITE_PATH" ]; then echo 'No database selected; no backup created.'; exit 2; fi
    "$PYTHON" scripts/secure_backup.py create --db "$SQLITE_PATH" --output-dir "${HOME}/Ramses_Encrypted_Backups"
    echo 'IMPORTANT: Copy the encrypted .rbe file to a separate secure device/location.'
    read -r -p 'Press Enter to close...' _ || true ;;
  6)
    read -r -p 'Full path to encrypted .rbe backup: ' BACKUP_PATH
    if [ -z "$BACKUP_PATH" ]; then echo 'No backup selected.'; exit 2; fi
    "$PYTHON" scripts/secure_backup.py verify --input "$BACKUP_PATH"
    read -r -p 'Press Enter to close...' _ || true ;;
  *) echo 'Unknown choice; no service started.'; exit 2 ;;
esac
