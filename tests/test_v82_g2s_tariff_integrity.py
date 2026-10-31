"""A stale positive rate must not undercharge an already re-priced night."""
import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def run():
    with tempfile.TemporaryDirectory() as td:
        os.environ.update(RAMSES_DB_PATH=str(Path(td)/'test.sqlite'), RAMSES_ADMIN_USER='owner',
                          RAMSES_ADMIN_PASSWORD='synthetic_rate_integrity_password')
        from bootstrap import initialize,connect
        initialize()
        with connect() as c:
            dept=c.execute("SELECT id FROM departments WHERE code='IPD'").fetchone()[0]
            c.execute("INSERT INTO billing_points(code,name,kind) VALUES ('G2S_RATE_POINT','Synthetic rate point','internal')")
            point=c.execute("SELECT last_insert_rowid()").fetchone()[0]
            c.execute("INSERT INTO billing_patients(code,display_name,created_by,created_at) VALUES ('G2S-RATE-01','Synthetic rate patient',1,'2026-10-01')")
            patient=c.execute("SELECT last_insert_rowid()").fetchone()[0]
            c.execute('''INSERT INTO billing_cases(case_no,patient_id,kind,default_point_id,business_date,opened_by,opened_at)
              VALUES('G2S-RATE-CASE-01',?,'inpatient',?,'2026-10-01',1,'2026-10-01')''',(patient,point))
            case=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.execute('''INSERT INTO billing_services(code,name,department_id,suggested_point,created_by,created_at)
              VALUES('G2S-RATE-SVC','Synthetic rate service',?,'internal',1,'2026-10-01')''',(dept,))
            service=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.execute("INSERT INTO billing_service_prices(service_id,valid_from,price_piasters,created_by,created_at) VALUES (?, '2026-10-01',10000,1,'2026-10-01')",(service,))
            older=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.execute("INSERT INTO billing_service_prices(service_id,valid_from,price_piasters,created_by,created_at) VALUES (?, '2026-10-20',22000,1,'2026-10-20')",(service,))
            newer=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.execute('''INSERT INTO bed_catalog(code,name,kind,service_id,created_by,created_at)
              VALUES('G2S-RATE-BED','Synthetic rate bed','inpatient',?,1,'2026-10-01')''',(service,))
            bed=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.execute('''INSERT INTO bed_stays(bed_id,case_id,start_date,end_date,admission_evidence,release_evidence,
              recorded_by,recorded_at,released_by,released_at)
              VALUES(?,?,'2026-10-01','2026-10-31','SYN-ADMISSION-RATE-01','SYN-RELEASE-RATE-01',1,'2026-10-01',1,'2026-10-31')''',(bed,case))
            stay=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            for price_id,amount,number in [(older,10000,1),(newer,22000,2)]:
                c.execute('''INSERT INTO billing_case_lines(case_id,service_id,price_version_id,
                  service_name_snapshot,department_id,unit_price_piasters,quantity,added_by,added_at)
                  VALUES(?,?,?,?,?,?,1,1,'2026-10-30')''',
                  (case,service,price_id,f'Synthetic night version {number}',dept,amount))
                line=c.execute('SELECT last_insert_rowid()').fetchone()[0]
                c.execute('BEGIN IMMEDIATE')
                try:
                    c.execute('''INSERT INTO bed_night_charges(stay_id,night_date,case_line_id,
                      price_version_id,amount_piasters,ordered_by,ordered_at)
                      VALUES(?,'2026-10-30',?,?,?,1,'2026-10-30')''',(stay,line,price_id,amount))
                except Exception:
                    c.rollback()
                    if number==2:raise AssertionError('Latest price was incorrectly denied')
                else:
                    c.rollback()
                    if number==1:raise AssertionError('Older superseded rate was accepted for a later night')
        print('PASS G2S: stale tariff rejected; latest dated tariff accepted')

if __name__=='__main__':run()
