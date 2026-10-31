"""Real G2Q frozen DDL -> additive G2R x2. Synthetic records only."""
import hashlib
import os
import sqlite3
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT))
FROZEN=ROOT/'tests/fixtures/schema_v8_1e_g2q_original.sql'
FROZEN_SHA256='cd543db7e848100157c9687e02723390df0d0e91c52a39c444445100c1261642'


def run():
    assert hashlib.sha256(FROZEN.read_bytes()).hexdigest()==FROZEN_SHA256
    with tempfile.TemporaryDirectory() as td:
        from fixture_backup_key import configure as test_backup_key
        test_backup_key(td)
        os.environ.update(RAMSES_DB_PATH=str(Path(td)/'old-g2q.sqlite3'),
                          RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='synthetic_only_g2r_migration_pwd')
        with sqlite3.connect(os.environ['RAMSES_DB_PATH']) as c:
            c.executescript(FROZEN.read_text())
            c.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES (1,'owner','synthetic-g2q-hash','owner','2026-10-31')")
            c.execute("INSERT INTO audit_log(actor_id,action,entity,entity_id,details,created_at) VALUES (1,'old_g2q_event','g2q','33','{\"source\":\"G2Q\"}','2026-10-31')")
            c.execute("INSERT INTO funds(id,code,name,kind,opening_piasters) VALUES (55,'G2Q_QA_CASH','Synthetic G2Q original fund','cash',0)")
            c.commit()
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='bed_stays'").fetchone()
        from bootstrap import initialize,connect
        for i in range(2):
            initialize()
            with connect() as c:
                assert c.execute("SELECT details FROM audit_log WHERE entity='g2q'").fetchone()[0]=='{"source":"G2Q"}'
                assert c.execute('SELECT name FROM funds WHERE id=55').fetchone()[0]=='Synthetic G2Q original fund'
                for table in ('bed_catalog','bed_stays','bed_night_charges'):
                    assert c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
                assert c.execute('SELECT COUNT(*) FROM audit_log WHERE entity=?',('g2q',)).fetchone()[0]==1
                assert not c.execute('PRAGMA foreign_key_check').fetchall()
        print('PASS G2Q frozen-schema -> G2R x2: original records retained, new bed tables added')

if __name__=='__main__':run()
