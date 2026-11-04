"""HTTPS preview seeding must honor Secure cookies without disabling them."""
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]


def run():
    with tempfile.TemporaryDirectory(prefix='ramses-s12-preview-') as folder:
        root=Path(folder)
        (root/'data').mkdir()
        os.environ.update(RAMSES_DB_PATH=str(root/'data/free-preview.sqlite3'),
            RAMSES_ENVIRONMENT='free-preview',RAMSES_SECURE_COOKIES='1',
            RAMSES_ADMIN_USER='s12_preview_owner',
            RAMSES_ADMIN_PASSWORD='synthetic_s12_preview_owner_password_long')
        for key in ('GOOGLE_SHEET_ID','GOOGLE_SERVICE_ACCOUNT_JSON','GOOGLE_SHEET_TARGET'):
            os.environ.pop(key,None)
        from bootstrap import initialize,connect
        from seed_preview_demo import seed_demo
        initialize()
        result=seed_demo(root,os.environ['RAMSES_ADMIN_PASSWORD'])
        assert result['seeded']==3,result
        assert os.environ['RAMSES_SECURE_COOKIES']=='1','Seeder weakened cookie security'
        with connect() as c:
            assert c.execute("SELECT COUNT(*) FROM vouchers WHERE status='approved'").fetchone()[0]==3
            assert c.execute("SELECT COUNT(*) FROM users WHERE username='preview_reviewer'").fetchone()[0]==1
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
        repeated=seed_demo(root,os.environ['RAMSES_ADMIN_PASSWORD'])
        assert repeated.get('skipped'),repeated
        print('PASS S12 protected preview seed: Secure cookies retained,3 fabricated vouchers, no duplicate seeding')


if __name__=='__main__':
    run()
