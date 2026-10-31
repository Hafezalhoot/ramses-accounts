"""Old V8.1A database -> V8.1B without silently touching accounting records or patient cases."""
import os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def run():
    with tempfile.TemporaryDirectory() as d:
        dbfile=Path(d)/'ramses_v81a.sqlite3'
        os.environ['RAMSES_DB_PATH']=str(dbfile)
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='test_owner_secret_password_2026'
        from bootstrap import connect,seed,initialize,hash_password,now
        import ledger
        with connect() as c:
            c.executescript((ROOT/'tests/fixtures/schema_v81a.sql').read_text())
            seed(c)
            ledger.seed_chart(c)
            c.execute('INSERT INTO users(id,username,password_hash,role,created_at) VALUES (1,?,?,?,?)',
                      ('owner',hash_password('test_owner_secret_password_2026'),'owner',now()))
            c.execute("INSERT INTO billing_points(code,name,kind) VALUES ('OUTPATIENT','اختبار','external')")
            point=c.execute('SELECT id FROM billing_points').fetchone()[0]
            c.execute("INSERT INTO billing_patients(code,display_name,created_by,created_at) VALUES ('PT-000000000001','مريض قديم تجريبي',1,?)",(now(),))
            pid=c.execute('SELECT id FROM billing_patients').fetchone()[0]
            c.execute("INSERT INTO billing_cases(case_no,patient_id,kind,default_point_id,business_date,opened_by,opened_at) VALUES ('CASE-2026-000001',?,'outpatient',?,'2026-10-30',1,?)",(pid,point,now()))
            before=c.execute('SELECT COUNT(*) FROM billing_cases').fetchone()[0]
        initialize()
        backup=list((Path(d)/'pre_billing_v81b_backups').glob('*.sqlite3'))
        assert len(backup)==1,backup
        with connect() as c:
            assert c.execute('SELECT COUNT(*) FROM billing_cases').fetchone()[0]==before
            assert c.execute("SELECT code FROM billing_patients WHERE id=?",(pid,)).fetchone()[0]=='PT-000000000001'
            assert c.execute("SELECT COUNT(*) FROM gl_accounts WHERE code='2300'").fetchone()[0]==1
            assert c.execute("SELECT COUNT(*) FROM billing_invoices").fetchone()[0]==0
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        initialize()
        assert len(list((Path(d)/'pre_billing_v81b_backups').glob('*.sqlite3')))==1
        print('PASS V8.1A -> V8.1B: pre-upgrade backup, patient case unchanged, new ledger accounts, idempotent start')

if __name__=='__main__':run()
