"""G2Z => G3A: encrypted rollback and non-destructive user-role SQLite migration.

The intentional regression this catches is changing the roles CHECK without
preserving every referenced user row and without suspending G2Z viewer grants.
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
ROOT=Path(__file__).resolve().parents[1]


def run():
    with tempfile.TemporaryDirectory(prefix='g3a-legacy-') as temp:
        base=Path(temp)
        db=base/'g2z-legacy.sqlite3'
        with sqlite3.connect(db) as c:
            c.executescript((ROOT/'tests/fixtures/schema_v8_1e_g2z_original.sql').read_text())
            c.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES (1,'synthetic-owner','x','owner','2026-10-01')")
            c.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES (2,'synthetic-viewer','x','viewer','2026-10-01')")
            c.execute("INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES ('synthetic-token',2,'synthetic-csrf','2027-01-01')")
            c.execute("INSERT INTO departments(id,code,name) VALUES (12,'TESTLAB','Synthetic laboratory')")
            c.execute("INSERT INTO billing_clinical_grants(department_id,user_id,active,assigned_by,assigned_at) VALUES (12,2,1,1,'2026-10-01')")
            c.execute("INSERT INTO billing_clinical_policies(department_id,activated_by,activated_at) VALUES (12,1,'2026-10-01')")
            c.execute("INSERT INTO billing_points(id,code,name,kind) VALUES (20,'SYNEXT','Synthetic desk','external')")
            c.execute("INSERT INTO billing_patients(id,code,display_name,created_by,created_at) VALUES (30,'SYN-PT-30','Synthetic historical patient',1,'2026-10-01')")
            c.execute("INSERT INTO billing_cases(id,case_no,patient_id,kind,default_point_id,business_date,opened_by,opened_at) VALUES (40,'SYN-CASE-40',30,'outpatient',20,'2026-10-01',1,'2026-10-01')")
            c.execute("INSERT INTO billing_services(id,code,name,department_id,suggested_point,created_by,created_at) VALUES (50,'SYNTEST','Synthetic historical service',12,'external',1,'2026-10-01')")
            c.execute("INSERT INTO billing_service_prices(id,service_id,valid_from,price_piasters,created_by,created_at) VALUES (60,50,'2026-10-01',8500,1,'2026-10-01')")
            c.execute('''INSERT INTO billing_case_lines(id,case_id,service_id,price_version_id,service_name_snapshot,
                department_id,unit_price_piasters,quantity,added_by,added_at,state,service_date,fulfilled_by,fulfilled_at)
                VALUES (70,40,50,60,'Synthetic historical service',12,8500,1,1,'2026-10-01','fulfilled','2026-10-01',2,'2026-10-01')''')
            c.execute("INSERT INTO billing_clinical_attestations(id,case_line_id,department_id,service_date,evidence_reference,attested_by,attested_at) VALUES (80,70,12,'2026-10-01','SYNTHETIC-G2Z-LEGACY-80',2,'2026-10-01')")
            c.commit()
            assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
        os.environ.update(RAMSES_DB_PATH=str(db),RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='synthetic-clinician-upgrade-owner')
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE_FILE',None)
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE',None)
        from bootstrap import initialize,connect
        try:
            initialize()
        except (ValueError,RuntimeError) as exc:
            assert 'passphrase' in str(exc).lower(),str(exc)
        else:raise AssertionError('G2Z role constraint rebuilt without encrypted rollback')
        with sqlite3.connect(db) as c:
            assert 'clinician' not in c.execute("SELECT sql FROM sqlite_master WHERE name='users'").fetchone()[0]
            assert c.execute('SELECT active FROM billing_clinical_grants').fetchone()[0]==1
        phrase=base/'secret.txt'
        phrase.write_text('synthetic-clinician-upgrade-key-2026-strong',encoding='utf-8')
        phrase.chmod(0o600)
        os.environ['RAMSES_BACKUP_PASSPHRASE_FILE']=str(phrase)
        initialize()
        with connect() as c:
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
            assert 'clinician' in c.execute("SELECT sql FROM sqlite_master WHERE name='users'").fetchone()[0]
            assert [tuple(r) for r in c.execute('SELECT id,username,role FROM users WHERE id IN (1,2) ORDER BY id')]==[
                (1,'synthetic-owner','owner'),(2,'synthetic-viewer','viewer')]
            assert c.execute('SELECT user_id FROM sessions WHERE token_hash=?',('synthetic-token',)).fetchone()[0]==2
            assert c.execute('SELECT active FROM billing_clinical_grants WHERE user_id=2').fetchone()[0]==0
            assert c.execute('SELECT department_id FROM billing_clinical_policies').fetchone()[0]==12
            old_evidence=c.execute('''SELECT a.id,a.evidence_reference,a.attested_by,l.unit_price_piasters
                FROM billing_clinical_attestations a JOIN billing_case_lines l ON l.id=a.case_line_id
                WHERE a.id=80''').fetchone()
            assert tuple(old_evidence)==(80,'SYNTHETIC-G2Z-LEGACY-80',2,8500),tuple(old_evidence)
            # Preserve this historical pilot record for audit, but do not let
            # an obsolete viewer-role witness authorize a *new* G3A invoice.
            from app import app  # register routers in the application's real import order
            from billing import require_invoice_clinical_evidence
            from fastapi import HTTPException
            try:
                require_invoice_clinical_evidence(c,[{'id':70,'department_id':12}])
            except HTTPException as exc:
                assert exc.status_code==409,exc.status_code
            else:
                raise AssertionError('Historical G2Z viewer attestation authorized new G3A invoice')
            c.execute("INSERT INTO users(username,password_hash,role,created_at) VALUES('synthetic-clinician','x','clinician','2026-10-31')")
            assert c.execute('SELECT role FROM users WHERE username=?',('synthetic-clinician',)).fetchone()[0]=='clinician'
        backups=list((base/'pre_schema_upgrade_backups').glob('*.rbe'))
        assert len(backups)==1,backups
        from scripts.secure_backup import verify_or_restore
        restored=base/'restored-g2z.sqlite3'
        verify_or_restore(backups[0],restored)
        with sqlite3.connect(restored) as c:
            assert 'clinician' not in c.execute("SELECT sql FROM sqlite_master WHERE name='users'").fetchone()[0]
            assert c.execute('SELECT active FROM billing_clinical_grants').fetchone()[0]==1
            assert c.execute('SELECT evidence_reference FROM billing_clinical_attestations WHERE id=80').fetchone()[0]=='SYNTHETIC-G2Z-LEGACY-80'
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        initialize()
        assert list((base/'pre_schema_upgrade_backups').glob('*.rbe'))==backups
        print('PASS G3A: actual G2Z schema preserved, encrypted rollback restorable, old viewer grant suspended')
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE_FILE',None)

if __name__=='__main__':run()
