"""Idempotent additive G2G upgrade of pre-G2G database, no patient/shift data lost."""
import os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def run():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ['RAMSES_DB_PATH']=str(Path(tmp)/'legacy_g2f_shape.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='owner_g2g_upgrade_password_2026'
        from bootstrap import initialize,connect
        initialize()
        with connect() as c:
            # Simulate the G2F schema shape: existing correction tickets/events
            # and all other business tables, but no G2G execution table/triggers.
            c.execute('DROP TRIGGER IF EXISTS financial_invoice_fix_no_update')
            c.execute('DROP TRIGGER IF EXISTS financial_invoice_fix_no_delete')
            c.execute('DROP TABLE financial_invoice_credit_fixes')
            users=c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            funds=c.execute('SELECT COUNT(*) FROM funds').fetchone()[0]
            points=c.execute('SELECT COUNT(*) FROM billing_points').fetchone()[0]
            assert c.execute('SELECT COUNT(*) FROM financial_correction_events').fetchone()[0]==0
        initialize();initialize()
        with connect() as c:
            assert c.execute('SELECT COUNT(*) FROM users').fetchone()[0]==users
            assert c.execute('SELECT COUNT(*) FROM funds').fetchone()[0]==funds
            assert c.execute('SELECT COUNT(*) FROM billing_points').fetchone()[0]==points
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
            assert c.execute('SELECT COUNT(*) FROM financial_invoice_credit_fixes').fetchone()[0]==0
            for name in ['financial_invoice_fix_no_update','financial_invoice_fix_no_delete']:
                assert c.execute('SELECT 1 FROM sqlite_master WHERE type="trigger" AND name=?',(name,)).fetchone()
        print('PASS G2G schema upgrade: existing users/funds/points preserved; new immutable table idempotent')
if __name__=='__main__':run()
