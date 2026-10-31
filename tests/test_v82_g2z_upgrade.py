"""G2Y -> G2Z schema migration preserves old financial and service source rows.

A genuine frozen G2Y schema is the input. An encrypted pre-upgrade rollback
must be created before any new clinical tables, with a working isolated restore.
"""
import os
import sqlite3
import stat
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
OLD_SQL=ROOT/'tests/fixtures/schema_v8_1e_g2y_original.sql'


def run():
    with tempfile.TemporaryDirectory(prefix='g2z-upgrade-') as td:
        base=Path(td)
        path=base/'legacy-test.sqlite3'
        with sqlite3.connect(path) as c:
            c.execute('PRAGMA foreign_keys=ON')
            c.executescript(OLD_SQL.read_text())
            c.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES(1,'legacy-owner','synthetic-hash','owner','2026-10-10')")
            c.execute("INSERT INTO departments(id,code,name) VALUES(101,'G2ZLAB','Synthetic clinical testing')")
            c.execute("INSERT INTO billing_points(id,code,name,kind) VALUES(107,'G2ZEXT','Synthetic external','external')")
            c.execute("INSERT INTO billing_patients(id,code,display_name,created_by,created_at) VALUES(111,'TEST-PAT-111','Synthetic person not a real patient',1,'2026-10-10')")
            c.execute("INSERT INTO billing_cases(id,case_no,patient_id,kind,default_point_id,business_date,opened_by,opened_at) VALUES(112,'G2Y-CASE-112',111,'outpatient',107,'2026-10-10',1,'2026-10-10')")
            c.execute("INSERT INTO billing_services(id,code,name,department_id,suggested_point,created_by,created_at) VALUES(113,'TESTG2Z','Synthetic legacy priced service',101,'external',1,'2026-10-10')")
            c.execute("INSERT INTO billing_service_prices(id,service_id,valid_from,price_piasters,created_by,created_at) VALUES(114,113,'2026-10-01',17300,1,'2026-10-10')")
            c.execute('''INSERT INTO billing_case_lines(id,case_id,service_id,price_version_id,service_name_snapshot,department_id,
                unit_price_piasters,quantity,added_by,added_at,service_date,fulfilled_by,fulfilled_at,state)
                VALUES(115,112,113,114,'Synthetic legacy priced service',101,17300,1,1,'2026-10-10','2026-10-10',1,'2026-10-10','fulfilled')''')
            c.commit()
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='billing_clinical_attestations'").fetchone()
        os.environ.update(RAMSES_DB_PATH=str(path),RAMSES_ADMIN_USER='owner',
                          RAMSES_ADMIN_PASSWORD='synthetic_admin_upgrade_g2z')
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE_FILE',None)
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE',None)
        from bootstrap import initialize, connect
        try:initialize()
        except (RuntimeError,ValueError) as error:
            assert 'passphrase' in str(error).lower(),str(error)
        else:raise AssertionError('G2Z migration bypassed mandatory rollback encryption')
        with sqlite3.connect(path) as c:
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='billing_clinical_attestations'").fetchone()
            assert c.execute('SELECT unit_price_piasters,state FROM billing_case_lines WHERE id=115').fetchone()==(17300,'fulfilled')
        passphrase=base/'synthetic-clinical-backup-passphrase.txt'
        passphrase.write_text('synthetic-strong-test-only-phrase-G2Z-0001')
        passphrase.chmod(0o600)
        os.environ['RAMSES_BACKUP_PASSPHRASE_FILE']=str(passphrase)
        initialize()
        archives=list((base/'pre_schema_upgrade_backups').glob('*.rbe'))
        assert len(archives)==1,archives
        archive=archives[0]
        assert stat.S_IMODE(archive.stat().st_mode)==0o600
        from scripts.secure_backup import verify_or_restore
        restored=base/'isolated_test_restore.sqlite3'
        verify_or_restore(archive,restored)
        with sqlite3.connect(restored) as c:
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='billing_clinical_attestations'").fetchone()
            assert c.execute('SELECT unit_price_piasters,state FROM billing_case_lines WHERE id=115').fetchone()==(17300,'fulfilled')
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        with connect() as c:
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
            assert c.execute('SELECT unit_price_piasters,state,service_date FROM billing_case_lines WHERE id=115').fetchone()[:]==(17300,'fulfilled','2026-10-10')
            assert c.execute('SELECT COUNT(*) FROM billing_clinical_attestations').fetchone()[0]==0, 'No fake retroactive medical signoff'
            assert c.execute('SELECT COUNT(*) FROM billing_clinical_policies').fetchone()[0]==0, 'Legacy medical departments stay unchanged unless owner opts in'
        initialize()
        assert list((base/'pre_schema_upgrade_backups').glob('*.rbe'))==[archive]
        print('PASS G2Z: encrypted rollback restores pristine G2Y, additive schema retains historical service and policies off')
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE_FILE',None)

if __name__=='__main__':run()
