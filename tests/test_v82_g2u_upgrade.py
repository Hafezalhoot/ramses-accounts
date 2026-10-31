"""G2U: genuine frozen G2T SQLite schema upgrades safely and idempotently."""
import hashlib
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
FROZEN=ROOT/'tests/fixtures/schema_v8_1e_g2t_original.sql'
FROZEN_SHA256='ba776adfba1ce0dcef282e76b764f05695af84bcb50f522fbdfe3fc9fba4aa9a'


def run():
    assert hashlib.sha256(FROZEN.read_bytes()).hexdigest()==FROZEN_SHA256,'Frozen G2T schema changed'
    with tempfile.TemporaryDirectory() as folder:
        os.environ.update(RAMSES_DB_PATH=str(Path(folder)/'g2t_upgrade.sqlite3'),
                          RAMSES_ADMIN_USER='owner',
                          RAMSES_ADMIN_PASSWORD='synthetic_g2u_upgrade_owner_password')
        os.environ.pop('GOOGLE_SHEET_ID',None)
        with sqlite3.connect(os.environ['RAMSES_DB_PATH']) as c:
            c.execute('PRAGMA foreign_keys=ON')
            c.executescript(FROZEN.read_text())
            assert 'service_date' not in {r[1] for r in c.execute('PRAGMA table_info(billing_case_lines)')}
            c.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES(1,'owner','synthetic-old-hash','owner','2026-09-30')")
            c.execute("INSERT INTO departments(id,code,name) VALUES(91,'G2UIPD','Synthetic archived ward')")
            c.execute("INSERT INTO billing_points(id,code,name,kind) VALUES(91,'G2U_OLD','Synthetic old cashier','internal')")
            c.execute("INSERT INTO billing_patients(id,code,display_name,created_by,created_at) VALUES(91,'G2U_PT','Synthetic legacy patient',1,'2026-09-30')")
            c.execute("""INSERT INTO billing_cases(id,case_no,patient_id,kind,default_point_id,business_date,opened_by,opened_at)
                VALUES(91,'CASE-2026-000091',91,'inpatient',91,'2026-09-30',1,'2026-09-30')""")
            c.execute("""INSERT INTO billing_services(id,code,name,department_id,suggested_point,created_by,created_at)
                VALUES(91,'G2U_OLD_SRV','Synthetic old service',91,'internal',1,'2026-09-30')""")
            c.execute("""INSERT INTO billing_service_prices(id,service_id,valid_from,price_piasters,created_by,created_at)
                VALUES(91,91,'2026-09-01',11000,1,'2026-09-01')""")
            c.execute("""INSERT INTO billing_case_lines(id,case_id,service_id,price_version_id,service_name_snapshot,
                department_id,unit_price_piasters,quantity,state,added_by,added_at,fulfilled_by,fulfilled_at)
                VALUES(91,91,91,91,'Synthetic old service',91,11000,1,'fulfilled',1,'2026-09-30',1,'2026-09-30')""")
            c.execute("""INSERT INTO billing_invoice_drafts(id,draft_no,case_id,point_id,total_piasters,created_by,created_at)
                VALUES(91,'DRAFT-2026-000091',91,91,11000,1,'2026-09-30')""")
            c.execute("""INSERT INTO billing_invoice_draft_lines(id,draft_id,case_line_id,unit_price_piasters,quantity,total_piasters)
                VALUES(91,91,91,11000,1,11000)""")
            c.commit()
        from bootstrap import initialize,connect
        from ledger import coverage
        for attempt in (1,2):
            initialize()
            with connect() as c:
                row=c.execute('SELECT * FROM billing_case_lines WHERE id=91').fetchone()
                assert row['service_date'] is None,'Unknown original service date must NOT be fabricated'
                assert row['unit_price_piasters']==11000 and row['state']=='fulfilled'
                assert c.execute('SELECT COUNT(*) FROM billing_invoice_draft_lines WHERE id=91').fetchone()[0]==1
                assert coverage(c,'2026-09')['unissued_drafts']==1,'Legacy draft stays classified in original month'
                assert not c.execute('PRAGMA foreign_key_check').fetchall()
                assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
                try:
                    c.execute("UPDATE billing_case_lines SET service_date='2026-10-01' WHERE id=91")
                except sqlite3.IntegrityError:
                    pass
                else:
                    raise AssertionError('Historical fulfilled service was silently mutable')
        print('PASS G2U real archived G2T schema x2, 1 unissued old draft preserved, unknown dates NULL, immutable evidence')


if __name__=='__main__':run()
