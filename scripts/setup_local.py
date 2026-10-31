"""One-time local installer: private directories, random bootstrap password, no cloud secrets."""
from pathlib import Path
import os
import secrets

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / ".env"
if TARGET.exists():
    raise SystemExit(".env exists. Refusing to overwrite settings or rotate an existing password.")
password = secrets.token_urlsafe(28)  # strong random credential; no $ to confuse Compose.
for name in ("data", "backups", "secrets"):
    p = ROOT / name
    p.mkdir(mode=0o700, exist_ok=True)
    p.chmod(0o700)
text = ("RAMSES_ADMIN_USER=owner\n"
        + "RAMSES_ADMIN_PASSWORD=" + password + "\n"
        + "RAMSES_ENVIRONMENT=staging\n"
        + "# GOOGLE_SHEET_ID=1BIjVrtYUlt8lOtaarZPyz4Cci0XIp5eWIJwOCfUfTTk\n"
        + "# GOOGLE_SERVICE_ACCOUNT_JSON=/secrets/service-account.json\n")
fd = os.open(TARGET, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as fh:
    fh.write(text)
print("Local config created: .env (mode 0600).")
print("IMPORTANT: Save this FIRST-RUN password securely, then remove it from .env after first successful login.")
print("owner password:", password)
print("Before docker compose up: sudo chown -R 10001:10001 data backups secrets")
