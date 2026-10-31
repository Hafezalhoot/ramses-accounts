"""G2H additive migration from the previous G2G schema shape is idempotent."""
import os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def run():
    with tempfile.TemporaryDirectory() as tmp:
        from fixture_backup_key import configure as test_backup_key
        test_backup_key(tmp)
        os.environ['RAMSES_DB_PATH']=str(Path(tmp)/'g2g_existing.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='owner_upgrade_g2h_secure_2026'
        from bootstrap import initialize,connect
        initialize()
        with connect() as c:
            c.execute('DROP TRIGGER financial_collection_realloc_no_update')
            c.execute('DROP TRIGGER financial_collection_realloc_no_delete')
            c.execute('DROP TABLE financial_collection_reallocations')
            assert c.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name="financial_invoice_credit_fixes"').fetchone()
            n_users=c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            n_points=c.execute('SELECT COUNT(*) FROM billing_points').fetchone()[0]
            n_funds=c.execute('SELECT COUNT(*) FROM funds').fetchone()[0]
        initialize();initialize()
        with connect() as c:
            assert c.execute('SELECT COUNT(*) FROM users').fetchone()[0]==n_users
            assert c.execute('SELECT COUNT(*) FROM billing_points').fetchone()[0]==n_points
            assert c.execute('SELECT COUNT(*) FROM funds').fetchone()[0]==n_funds
            for item in ['financial_collection_reallocations','financial_invoice_credit_fixes']:
                assert c.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name=?',(item,)).fetchone()
            for item in ['financial_collection_realloc_no_update','financial_collection_realloc_no_delete']:
                assert c.execute('SELECT 1 FROM sqlite_master WHERE type="trigger" AND name=?',(item,)).fetchone()
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
        print('PASS G2H additive migration from G2G shape; repeat initialize safe, original records intact')

if __name__=='__main__':run()
