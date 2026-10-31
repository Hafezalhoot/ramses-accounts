"""G2R archived DDL -> G2S upgrade twice, preserving real old bed evidence."""
import hashlib
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
FROZEN=ROOT/'tests/fixtures/schema_v8_1e_g2r_original.sql'
FROZEN_SHA256='5a35b7dd0a5781464d5206fbfb046b6f8ef7a454bce506de7e7e71c416c942dd'

def run():
    assert hashlib.sha256(FROZEN.read_bytes()).hexdigest()==FROZEN_SHA256
    with tempfile.TemporaryDirectory() as td:
        os.environ.update(RAMSES_DB_PATH=str(Path(td)/'frozen-g2r.sqlite3'),
                          RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='synthetic_g2r_to_g2s_password')
        with sqlite3.connect(os.environ['RAMSES_DB_PATH']) as c:
            c.executescript(FROZEN.read_text())
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='bed_transfers'").fetchone()
            c.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES(1,'owner','synthetic-upgrade-hash','owner','2026-10-31')")
            c.execute("INSERT INTO departments(id,code,name) VALUES(89,'IPD','Synthetic legacy internal ward')")
            c.execute("INSERT INTO billing_points(id,code,name,kind) VALUES(89,'G2R_TEST','Synthetic G2R point','internal')")
            c.execute("INSERT INTO billing_patients(id,code,display_name,created_by,created_at) VALUES(89,'G2R-PT-89','Synthetic legacy patient',1,'2026-10-29')")
            c.execute("""INSERT INTO billing_cases(id,case_no,patient_id,kind,default_point_id,business_date,opened_by,opened_at)
                 VALUES(89,'G2R-CASE-89',89,'inpatient',89,'2026-10-29',1,'2026-10-29')""")
            c.execute("""INSERT INTO billing_services(id,code,name,department_id,suggested_point,created_by,created_at)
                 VALUES(89,'G2R-STAY-89','Synthetic legacy nightly fee',89,'internal',1,'2026-10-29')""")
            c.execute("""INSERT INTO billing_service_prices(id,service_id,valid_from,price_piasters,created_by,created_at)
                 VALUES(89,89,'2026-10-01',9000,1,'2026-10-01')""")
            c.execute("""INSERT INTO bed_catalog(id,code,name,kind,service_id,created_by,created_at)
                 VALUES(89,'G2R-BED-89','Synthetic G2R bed','inpatient',89,1,'2026-10-29')""")
            c.execute("""INSERT INTO bed_stays(id,bed_id,case_id,start_date,end_date,admission_evidence,
                 release_evidence,recorded_by,recorded_at,released_by,released_at)
                 VALUES(89,89,89,'2026-10-29','2026-10-30','SYN-OLD-ADMISSION-89',
                 'SYN-OLD-RELEASE-89',1,'2026-10-29',1,'2026-10-30')""")
            c.execute("""INSERT INTO billing_case_lines(id,case_id,service_id,price_version_id,service_name_snapshot,
                 department_id,unit_price_piasters,quantity,added_by,added_at)
                 VALUES(89,89,89,89,'Synthetic old night',89,9000,1,1,'2026-10-29')""")
            c.execute("""INSERT INTO bed_night_charges(id,stay_id,night_date,case_line_id,price_version_id,
                 amount_piasters,ordered_by,ordered_at)
                 VALUES(89,89,'2026-10-29',89,89,9000,1,'2026-10-29')""")
            c.execute("""INSERT INTO audit_log(actor_id,action,entity,entity_id,details,created_at)
                 VALUES(1,'old_stay','bed_stay','89','{}','2026-10-29')""")
            c.commit()
        from bootstrap import initialize,connect
        for _ in range(2):
            initialize()
            with connect() as c:
                assert c.execute('SELECT amount_piasters FROM bed_night_charges WHERE id=89').fetchone()[0]==9000
                assert c.execute('SELECT end_date FROM bed_stays WHERE id=89').fetchone()[0]=='2026-10-30'
                assert c.execute('SELECT display_name FROM billing_patients WHERE id=89').fetchone()[0]=='Synthetic legacy patient'
                assert c.execute('SELECT count(*) FROM audit_log WHERE entity=?',('bed_stay',)).fetchone()[0]==1
                assert c.execute("SELECT 1 FROM sqlite_master WHERE name='bed_transfers'").fetchone()
                assert c.execute("SELECT 1 FROM sqlite_master WHERE name='bed_charge_sealed_month'").fetchone()
                assert c.execute('SELECT count(*) FROM bed_transfers').fetchone()[0]==0
                assert not c.execute('PRAGMA foreign_key_check').fetchall()
        print('PASS G2R frozen-schema -> G2S twice, old bed/charge/patient/audit rows preserved')

if __name__=='__main__':run()
