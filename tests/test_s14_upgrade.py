"""Exact frozen S13 -> additive S14, with verified encrypted rollback and old draft."""
import os,sys,sqlite3,tempfile,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
FROZEN=ROOT/'tests/fixtures/schema_s13_original.sql'


def run():
    assert hashlib.sha256(FROZEN.read_bytes()).hexdigest()=='331d21461910f23d2939fa9204ef07f5a3d0aa49578b361ca7642ec147068a18'
    with tempfile.TemporaryDirectory(prefix='s14-upgrade-') as folder:
        root=Path(folder);dbpath=root/'s13.sqlite3';key=root/'rollback-key'
        key.write_text('synthetic-S14-encrypted-rollback-passphrase-not-a-real-secret');key.chmod(0o600)
        os.environ.update(RAMSES_DB_PATH=str(dbpath),RAMSES_BACKUP_PASSPHRASE_FILE=str(key))
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE',None)
        for k in ('GOOGLE_SHEET_ID','GOOGLE_SERVICE_ACCOUNT_JSON'):os.environ.pop(k,None)
        with sqlite3.connect(dbpath) as c:
            c.executescript(FROZEN.read_text())
            c.execute("INSERT INTO users VALUES(17,'s13_owner','synthetic_hash','owner',1,'2026-11-04')")
            c.execute("INSERT INTO departments(id,code,name) VALUES(18,'S13_DEPT','قسم وهمي محفوظ')")
            c.execute("INSERT INTO billing_points(id,code,name,kind) VALUES(19,'S13_POINT','نقطة وهمية محفوظة','external')")
            c.execute("INSERT INTO billing_patients VALUES(20,'PT-S13','مريض وهمي محفوظ',17,'2026-11-04')")
            c.execute("INSERT INTO billing_cases VALUES(21,'CASE-S13',20,'outpatient',19,'2026-11-04',17,'2026-11-04','open','')")
            c.execute("INSERT INTO billing_services VALUES(22,'S13_SERVICE','خدمة وهمية محفوظة',18,'external',1,17,'2026-11-04')")
            c.execute("INSERT INTO billing_service_prices VALUES(23,22,'2026-11-01',30000,17,'2026-11-04')")
            c.execute("INSERT INTO billing_case_lines(id,case_id,service_id,price_version_id,service_name_snapshot,department_id,unit_price_piasters,quantity,state,added_by,added_at,service_date,fulfilled_by,fulfilled_at) VALUES(24,21,22,23,'خدمة وهمية محفوظة',18,30000,2,'fulfilled',17,'2026-11-04','2026-11-04',17,'2026-11-04')")
            c.execute("INSERT INTO billing_invoice_drafts VALUES(25,'DRAFT-S13',21,19,60000,17,'2026-11-04','draft')")
            c.execute("INSERT INTO billing_invoice_draft_lines VALUES(26,25,24,30000,2,60000)")
            before={table:c.execute('SELECT * FROM '+table).fetchall() for table in ('users','billing_patients','billing_cases','billing_services','billing_service_prices','billing_case_lines','billing_invoice_drafts','billing_invoice_draft_lines')}
        from bootstrap import initialize,connect
        initialize();initialize()
        with connect() as c:
            for table,rows in before.items():assert [tuple(r) for r in c.execute('SELECT * FROM '+table)]==rows,table
            for table in ('pricing_lists','pricing_rate_versions','pricing_orders','pricing_line_terms','service_fee_decisions','service_fee_reversals'):
                assert c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0
            assert c.execute("SELECT COUNT(*) FROM gl_accounts WHERE code IN ('2320','5196')").fetchone()[0]==2
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not c.execute('PRAGMA foreign_key_check').fetchall()
        backups=list((root/'pre_schema_upgrade_backups').glob('*.rbe'));assert len(backups)==1
        from scripts.secure_backup import verify_or_restore
        restored=root/'restored-s13.sqlite3';verify_or_restore(backups[0],restored)
        with sqlite3.connect(restored) as c:
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='pricing_orders'").fetchone()
            for table,rows in before.items():assert c.execute('SELECT * FROM '+table).fetchall()==rows,table
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        print('PASS S14 authentic frozenS13 upgrade twice, legacy service/evidence/draft unchanged, empty pricing and fee records, encrypted rollback independently restored')


if __name__=='__main__':run()
