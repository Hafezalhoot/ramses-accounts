"""G3A -> G3B: source-document columns require authenticated pre-DDL rollback.

Mutation: skipping encrypted rollback, replacing historical evidence, corrupting
user IDs or accepting a G3A attestation as a new source-hashed witness.
"""
import os
import sqlite3
import stat
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory(prefix='g3b-g3a-upgrade-') as td:
        base=Path(td)
        db=base/'frozen_g3a.sqlite3'
        with sqlite3.connect(db) as c:
            c.execute('PRAGMA foreign_keys=ON')
            c.executescript((ROOT/'tests/fixtures/schema_v8_1e_g3a_original.sql').read_text())
            c.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES (1,'synthetic-owner','x','owner','2026-10-31')")
            c.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES (2,'synthetic-clinician','x','clinician','2026-10-31')")
            c.execute("INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES ('g3a-clinical-session',2,'g3a-clinical-csrf','2027-01-01')")
            c.execute("INSERT INTO departments(id,code,name) VALUES(12,'G3BTEST','Synthetic medical lab')")
            c.execute("INSERT INTO billing_clinical_identity_reviews(user_id,professional_name,registration_reference,approved,reviewed_by,reviewed_at,review_note) VALUES (2,'Synthetic verified clinician','SYN-REGISTRATION-G3A',1,1,'2026-10-31','Synthetic manual review for G3B test')")
            c.execute("INSERT INTO billing_clinical_grants(department_id,user_id,active,assigned_by,assigned_at) VALUES(12,2,1,1,'2026-10-31')")
            c.execute("INSERT INTO billing_clinical_policies(department_id,activated_by,activated_at) VALUES(12,1,'2026-10-31')")
            c.execute("INSERT INTO billing_points(id,code,name,kind) VALUES(20,'G3BEXT','Synthetic desk','external')")
            c.execute("INSERT INTO billing_patients(id,code,display_name,created_by,created_at) VALUES (30,'SYN-PT-30','Test patient only',1,'2026-10-31')")
            c.execute("INSERT INTO billing_cases(id,case_no,patient_id,kind,default_point_id,business_date,opened_by,opened_at) VALUES (40,'SYN-CASE-40',30,'outpatient',20,'2026-10-31',1,'2026-10-31')")
            c.execute("INSERT INTO billing_services(id,code,name,department_id,suggested_point,created_by,created_at) VALUES(50,'G3BTEST','Synthetic test service',12,'external',1,'2026-10-31')")
            c.execute("INSERT INTO billing_service_prices(id,service_id,valid_from,price_piasters,created_by,created_at) VALUES (60,50,'2026-10-01',8500,1,'2026-10-31')")
            c.execute('''INSERT INTO billing_case_lines(id,case_id,service_id,price_version_id,service_name_snapshot,
              department_id,unit_price_piasters,quantity,added_by,added_at,state,service_date,fulfilled_by,fulfilled_at)
              VALUES(70,40,50,60,'Synthetic test service',12,8500,1,1,'2026-10-31','fulfilled','2026-10-31',2,'2026-10-31')''')
            c.execute("INSERT INTO billing_clinical_attestations(id,case_line_id,department_id,service_date,evidence_reference,attested_by,attested_at) VALUES (80,70,12,'2026-10-31','SYN-G3A-WITNESS-REFERENCE',2,'2026-10-31')")
            c.commit()
            assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
            assert 'document_sha256' not in {r[1] for r in c.execute('PRAGMA table_info(billing_clinical_attestations)')}
        os.environ.update(RAMSES_DB_PATH=str(db),RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='synthetic_g3b_owner')
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE_FILE',None)
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE',None)
        from bootstrap import initialize,connect
        try: initialize()
        except (RuntimeError,ValueError) as exc:
            assert 'passphrase' in str(exc).lower(),str(exc)
        else: raise AssertionError('G3B source fingerprint DDL bypassed encrypted rollback')
        with sqlite3.connect(db) as c:
            assert 'document_sha256' not in {r[1] for r in c.execute('PRAGMA table_info(billing_clinical_attestations)')}
            assert c.execute('SELECT evidence_reference FROM billing_clinical_attestations WHERE id=80').fetchone()[0]=='SYN-G3A-WITNESS-REFERENCE'
        key=base/'rollback.secret'
        key.write_text('strong-synthetic-g3b-clinical-rollback-passphrase-2026')
        key.chmod(0o600)
        os.environ['RAMSES_BACKUP_PASSPHRASE_FILE']=str(key)
        initialize()
        with connect() as c:
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
            cols={r[1] for r in c.execute('PRAGMA table_info(billing_clinical_attestations)')}
            assert {'document_sha256','document_size','document_media_type'}.issubset(cols),cols
            assert c.execute('SELECT COUNT(*) FROM billing_clinical_document_requirements').fetchone()[0]==0
            old=c.execute('SELECT id,case_line_id,attested_by,evidence_reference,document_sha256 FROM billing_clinical_attestations WHERE id=80').fetchone()
            assert tuple(old)==(80,70,2,'SYN-G3A-WITNESS-REFERENCE',None),tuple(old)
            assert c.execute("SELECT user_id FROM sessions WHERE token_hash='g3a-clinical-session'").fetchone()[0]==2
        backups=list((base/'pre_schema_upgrade_backups').glob('*.rbe'))
        assert len(backups)==1,backups
        assert stat.S_IMODE(backups[0].stat().st_mode)==0o600
        from scripts.secure_backup import verify_or_restore
        restored=base/'restored_g3a.sqlite3'
        verify_or_restore(backups[0],restored)
        with sqlite3.connect(restored) as c:
            assert 'document_sha256' not in {r[1] for r in c.execute('PRAGMA table_info(billing_clinical_attestations)')}
            assert c.execute('SELECT evidence_reference FROM billing_clinical_attestations WHERE id=80').fetchone()[0]=='SYN-G3A-WITNESS-REFERENCE'
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        initialize()
        assert list((base/'pre_schema_upgrade_backups').glob('*.rbe'))==backups
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE_FILE',None)
        print('PASS G3B genuine G3A schema upgrade with encrypted rollback and preserved legacy clinical witnesses')

if __name__=='__main__':run()
