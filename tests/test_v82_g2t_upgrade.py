"""Frozen untouched G2S schema (archived ZIP) -> G2T twice, no source data loss."""
import hashlib
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
FROZEN=ROOT/'tests/fixtures/schema_v8_1e_g2s_original.sql'
FROZEN_SHA256='ee231c9753ecb9045616e84d440e5428766fde2fa3410cbc9aa1c0077af587b2'


def run():
    assert hashlib.sha256(FROZEN.read_bytes()).hexdigest()==FROZEN_SHA256,'Source schema must remain immutable'
    with tempfile.TemporaryDirectory() as td:
        from fixture_backup_key import configure as test_backup_key
        test_backup_key(td)
        os.environ.update(RAMSES_DB_PATH=str(Path(td)/'historical-g2s.sqlite3'),
                          RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='synthetic_upgrade_g2s_owner_password')
        os.environ.pop('GOOGLE_SHEET_ID',None)
        with sqlite3.connect(os.environ['RAMSES_DB_PATH']) as c:
            c.executescript(FROZEN.read_text())
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='inventory_receipts'").fetchone()
            c.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES(1,'owner','synthetic-g2s-hash','owner','2026-10-31')")
            c.execute("INSERT INTO audit_log(actor_id,action,entity,entity_id,details,created_at) VALUES(1,'historical','g2s','91','{}','2026-10-31')")
            c.execute("INSERT INTO funds(id,code,name,kind,opening_piasters) VALUES(93,'STOCK_UPGRADE_CASH','Synthetic old treasury','cash',0)")
            c.execute("INSERT INTO departments(id,code,name) VALUES(91,'IPD','Legacy synthetic inpatient ward')")
            c.commit()
        from bootstrap import initialize, connect
        for attempt in (1,2):
            initialize()
            with connect() as c:
                assert c.execute("SELECT name FROM funds WHERE id=93").fetchone()[0]=='Synthetic old treasury'
                assert c.execute("SELECT name FROM departments WHERE id=91").fetchone()[0]=='Legacy synthetic inpatient ward'
                assert c.execute("SELECT COUNT(*) FROM audit_log WHERE entity='g2s'").fetchone()[0]==1
                for name in ('inventory_vendors','inventory_items','inventory_access','inventory_receipts',
                             'inventory_receipt_lines','inventory_issues','inventory_issue_lines','inventory_issue_allocations'):
                    assert c.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name=?',(name,)).fetchone(),(attempt,name)
                    assert c.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0]==0,name
                assert not c.execute('PRAGMA foreign_key_check').fetchall()
                assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        print('PASS G2T actual archived G2S DDL -> G2T x2, preserved users/funds/departments/audit, no new stock')

if __name__=='__main__':run()
