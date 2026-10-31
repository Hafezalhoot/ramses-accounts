"""Self-contained G2O-to-G2P additive schema migration, with preserved test rows."""
import os
import sys
import tempfile
import sqlite3
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as temp:
        db_path=Path(temp)/'original_g2o.sqlite3'
        os.environ.update(RAMSES_DB_PATH=str(db_path),RAMSES_ADMIN_USER='owner',
                          RAMSES_ADMIN_PASSWORD='test_2026_g2p_upgrade_secure_pass')
        import bootstrap
        old_schema=(ROOT/'schema.sql').read_text().split('-- G2P: controlled financial clearance')[0]
        assert 'billing_case_clearance_requests' not in old_schema
        c=sqlite3.connect(db_path)
        c.execute('PRAGMA foreign_keys=ON')
        c.executescript(old_schema)
        c.execute('INSERT INTO users(username,password_hash,role,created_at) VALUES (?,?,?,?)',
                  ('owner',bootstrap.hash_password('test_2026_g2p_upgrade_secure_pass'),'owner',bootstrap.now()))
        c.execute('INSERT INTO billing_points(code,name,kind) VALUES (?,?,?)',('LEGACY_G2O','G2O old point','internal'))
        point=c.execute("SELECT id FROM billing_points WHERE code='LEGACY_G2O'").fetchone()[0]
        c.execute('INSERT INTO billing_patients(code,display_name,created_by,created_at) VALUES (?,?,?,?)',
                  ('PT-ABCDEF123456','Synthetic old-case file',1,bootstrap.now()))
        day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        c.execute('''INSERT INTO billing_cases(case_no,patient_id,kind,default_point_id,
            business_date,opened_by,opened_at) VALUES (?,?,?,?,?,?,?)''',
            ('CASE-G2O-000001',1,'inpatient',point,day,1,bootstrap.now()))
        c.commit()
        c.close()
        for cycle in range(2):
            bootstrap.initialize()
            with bootstrap.connect() as conn:
                old=conn.execute("SELECT case_no,kind,status FROM billing_cases WHERE case_no='CASE-G2O-000001'").fetchone()
                assert old and old['kind']=='inpatient' and old['status']=='open',dict(old) if old else None
                assert conn.execute('SELECT count(*) FROM billing_case_clearance_requests').fetchone()[0]==0
                assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
                assert not conn.execute('PRAGMA foreign_key_check').fetchall()
        print('PASS: G2O table migration twice without lost old cases or broken FKs')

if __name__=='__main__':run()
