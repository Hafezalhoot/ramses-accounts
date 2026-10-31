"""Self-host security invariants; no live data, no external network."""
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def run():
    # First-run setup must keep credentials off the distributed project and refuse overwrites.
    with tempfile.TemporaryDirectory() as folder:
        setup_root = Path(folder)
        (setup_root / "scripts").mkdir()
        shutil.copy2(ROOT / "scripts" / "setup_local.py", setup_root / "scripts" / "setup_local.py")
        setup = subprocess.run([sys.executable, str(setup_root / "scripts" / "setup_local.py")],
                               capture_output=True, text=True, check=True)
        env_file = setup_root / ".env"
        assert env_file.is_file() and stat.S_IMODE(env_file.stat().st_mode) == 0o600
        assert len(next(line for line in env_file.read_text().splitlines() if line.startswith("RAMSES_ADMIN_PASSWORD=")).split("=", 1)[1]) >= 20
        assert all((setup_root / name).is_dir() for name in ("data", "backups", "secrets"))
        repeated = subprocess.run([sys.executable, str(setup_root / "scripts" / "setup_local.py")],
                                  capture_output=True, text=True)
        assert repeated.returncode != 0
    with tempfile.TemporaryDirectory() as temp:
        dbfile = Path(temp) / "ledger.db"
        os.environ["RAMSES_DB_PATH"] = str(dbfile)
        os.environ["RAMSES_ADMIN_USER"] = "owner"
        os.environ["RAMSES_ADMIN_PASSWORD"] = "initial_password_very_long_abc_123"
        from bootstrap import initialize
        initialize()
        with sqlite3.connect(dbfile) as c:
            assert c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
        # A leaked one-time bootstrap credential need not stay in .env forever.
        os.environ.pop("RAMSES_ADMIN_PASSWORD")
        initialize()
        with sqlite3.connect(dbfile) as c:
            assert c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
        from app import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        assert client.get("/health").status_code == 200
        assert client.get("/api/vouchers").status_code == 401
        snap = Path(temp) / "backup.db"
        with sqlite3.connect(dbfile) as source, sqlite3.connect(snap) as target:
            source.backup(target)
        check = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_backup.py"), str(snap)],
                               capture_output=True, text=True, check=True)
        assert "PASS" in check.stdout
        # Missing admin secret on a fresh database must still fail.
        child_env = os.environ.copy()
        child_env["RAMSES_DB_PATH"] = str(Path(temp) / "fresh.db")
        child_env.pop("RAMSES_ADMIN_PASSWORD", None)
        p = subprocess.run([sys.executable, "-c", "from bootstrap import initialize; initialize()"],
                           cwd=ROOT, env=child_env, capture_output=True, text=True)
        assert p.returncode != 0 and "16+" in p.stderr, (p.stdout, p.stderr)
        print("PASS: first-run secret, restart without secret, backup verify, private API")

if __name__ == "__main__":
    run()
