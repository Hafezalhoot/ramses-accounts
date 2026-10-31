"""G2P -> G2Q, original frozen G2P schema fixture, additive migration x2.

The fixture is only SQL DDL from the genuine G2P archive, no patient/cash data.
"""
import hashlib
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FROZEN_SCHEMA = ROOT / 'tests/fixtures/schema_v8_1e_g2p_original.sql'
FROZEN_SHA256 = 'c9e0ca031990491a68639432868cac35488b9de1925768cbe35f3ac6ecb4884c'  # Set by audited extraction below.


def run():
    # Assert actual fixture hash before using it: test never silently updates its own baseline.
    actual = hashlib.sha256(FROZEN_SCHEMA.read_bytes()).hexdigest()
    assert actual == FROZEN_SHA256, (actual, FROZEN_SHA256)
    with tempfile.TemporaryDirectory() as td:
        os.environ['RAMSES_DB_PATH'] = str(Path(td) / 'old-g2p.sqlite3')
        os.environ['RAMSES_ADMIN_USER'] = 'owner'
        os.environ['RAMSES_ADMIN_PASSWORD'] = 'synthetic_only_g2p_migration_pwd'
        os.environ.pop('GOOGLE_SHEET_ID', None)
        db = Path(os.environ['RAMSES_DB_PATH'])
        with sqlite3.connect(db) as c:
            c.executescript(FROZEN_SCHEMA.read_text())
            c.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES (1,'owner','synthetic-g2p-hash','owner','2026-10-31')")
            c.execute("INSERT INTO audit_log(actor_id,action,entity,entity_id,details,created_at) VALUES (1,'old_event','g2p','33','{\"source\":\"G2P\"}','2026-10-31')")
            c.execute("INSERT INTO funds(id,code,name,kind,opening_piasters) VALUES (55,'G2P_QA_CASH','Synthetic G2P fund','cash',0)")
            c.commit()
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='login_rate_events'").fetchone()
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='audit_log_no_update'").fetchone()
        from bootstrap import initialize, connect
        for i in range(2):
            initialize()
            with connect() as c:
                assert c.execute("SELECT details FROM audit_log WHERE entity='g2p'").fetchone()[0] == '{"source":"G2P"}'
                assert c.execute("SELECT name FROM funds WHERE id=55").fetchone()[0] == 'Synthetic G2P fund'
                assert c.execute("SELECT COUNT(*) FROM audit_log WHERE entity='g2p'").fetchone()[0] == 1
                assert c.execute("SELECT 1 FROM sqlite_master WHERE name='login_rate_events'").fetchone()
                assert c.execute("SELECT 1 FROM sqlite_master WHERE name='audit_log_no_update'").fetchone()
                assert not c.execute('PRAGMA foreign_key_check').fetchall()
        print('PASS G2P frozen-schema -> G2Q x2: historical records retained, auth failures table and immutable audit added')


if __name__ == '__main__':
    run()
