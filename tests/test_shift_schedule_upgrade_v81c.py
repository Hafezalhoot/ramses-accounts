"""V8.1B database upgrades to configurable V8.1C without rewriting historic shifts."""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OLD_SCHEMA=ROOT/'tests'/'fixtures'/'v81b_schema.sql'
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as tmp:
        from fixture_backup_key import configure as test_backup_key
        test_backup_key(tmp)
        path=Path(tmp)/'old_v81b.sqlite3'
        prior_schema=OLD_SCHEMA.read_text(encoding='utf-8')
        with sqlite3.connect(path) as c:
            c.execute('PRAGMA foreign_keys=ON')
            c.executescript(prior_schema)
            c.execute('INSERT INTO users(username,password_hash,role,created_at) VALUES (?,?,?,?)',
                      ('archive','archived_test_only_hash','owner','2026-10-30T00:00:00Z'))
            c.execute("INSERT INTO funds(code,name,kind) VALUES ('legacyfund','Old Cash','cash')")
            c.execute("""INSERT INTO shift_sessions(business_date,shift,fund_id,responsible_id,
                opened_at,opening_piasters,status,counted_piasters,expected_piasters,variance_piasters)
                VALUES ('2026-10-29','evening',1,1,'2026-10-29T16:00:00Z',20000,
                 'closed',20000,20000,0)""")
        os.environ['RAMSES_DB_PATH']=str(path)
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='staging_strong_password_2026'
        from bootstrap import initialize,connect
        initialize()
        backups=list((Path(tmp)/'pre_billing_v81c_backups').glob('*.rbe'))
        assert len(backups)==1,backups
        from scripts.secure_backup import verify_or_restore
        restored=Path(tmp)/'restored_v81b.sqlite3'
        verify_or_restore(backups[0],restored)
        with sqlite3.connect(restored) as backup:
            assert not backup.execute("SELECT 1 FROM sqlite_master WHERE name='shift_templates'").fetchone()
            assert backup.execute('SELECT opening_piasters FROM shift_sessions WHERE id=1').fetchone()[0]==20000
        with connect() as conn:
            sh=conn.execute('SELECT * FROM shift_sessions WHERE id=1').fetchone()
            assert sh['business_date']=='2026-10-29' and sh['shift']=='evening'
            assert sh['scheduled_start_at'] is None and sh['opening_piasters']==20000
            assert sh['count_version']==0
            assert conn.execute('SELECT count(*) FROM shift_templates').fetchone()[0]==3
            assert conn.execute("SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_one_active_shift_per_fund'").fetchone()[0].endswith("WHERE status='open'")
            assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        initialize()
        assert len(list((Path(tmp)/'pre_billing_v81c_backups').glob('*.rbe')))==1
        print('PASS V8.1C upgrade: historical cashier shifts unchanged, consistent pre-upgrade backup, new schedules and unique-open guard')

if __name__=='__main__':run()
