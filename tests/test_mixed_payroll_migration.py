"""V7.3 payroll rows and old monthly contracts survive upgrade to mixed-pay schema."""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def run():
    with tempfile.TemporaryDirectory() as tmp:
        from fixture_backup_key import configure as test_backup_key
        test_backup_key(tmp)
        dbpath=Path(tmp)/'v73.sqlite3'
        os.environ.update(RAMSES_DB_PATH=str(dbpath),RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='owner_long_test_password_for_migration')
        with sqlite3.connect(dbpath) as db:
            db.executescript((ROOT/'tests/fixtures/schema_v7_3.sql').read_text())
            db.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES (1,'owner','placeholder','owner','2026-10-15')")
            db.execute("INSERT INTO employees(id,code,name) VALUES (1,'MONTHLY01','Existing monthly staff')")
            db.execute("INSERT INTO salary_terms(employee_id,monthly_piasters,valid_from) VALUES (1,430000,'2026-09-01')")
            db.execute("""INSERT INTO payroll_accruals(employee_id,period,base_piasters,additions_piasters,deductions_piasters,
              net_piasters,approved_by,approved_at) VALUES (1,'2026-09',430000,10000,5000,435000,1,'2026-09-30')""")
        from bootstrap import connect,initialize
        initialize()
        with connect() as c:
            term=c.execute('SELECT monthly_piasters,hourly_piasters,pay_type FROM salary_terms WHERE employee_id=1').fetchone()
            accr=c.execute('SELECT base_piasters,net_piasters,pay_type,hourly_rate_piasters,worked_minutes,signoff_status,adjustment_additions_piasters,adjustment_deductions_piasters FROM payroll_accruals WHERE employee_id=1').fetchone()
            assert tuple(term)==(430000,0,'monthly'),tuple(term)
            assert tuple(accr)==(430000,435000,'monthly',0,0,'legacy',0,0),tuple(accr)
            assert c.execute("SELECT count(*) FROM sqlite_master WHERE name='payroll_work_entries'").fetchone()[0]==1
            assert c.execute("SELECT count(*) FROM sqlite_master WHERE name='payroll_adjustments'").fetchone()[0]==1
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        initialize()
        with connect() as c:
            assert c.execute('SELECT count(*) FROM salary_terms').fetchone()[0]==1
            assert c.execute('SELECT count(*) FROM payroll_accruals').fetchone()[0]==1
        print('PASS — V7.3 monthly salaries, accruals and historical values preserved through idempotent V7.5 migration')

if __name__=='__main__':run()
