"""G3F genuine frozen G3E SQL -> encrypted pre-DDL backup and old returns fail-closed.

A prior G3E returned lot was historically reused without inspection; never
invent medical release credentials or erase old postings during migration.
"""
import hashlib
import os
import sqlite3
import stat
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
FROZEN=ROOT/'tests/fixtures/schema_v8_1e_g3e_original.sql'
SHA='64bf5c2fd8d7f4f2cab3d9b95c249a09ac68e082c6f0e9abb3a839fd64d3d55b'


def make_g3e(db):
    assert hashlib.sha256(FROZEN.read_bytes()).hexdigest()==SHA,'Historical G3E fixture tampered'
    day='2026-10-30'
    with sqlite3.connect(db) as c:
        c.execute('PRAGMA foreign_keys=ON')
        c.executescript(FROZEN.read_text(encoding='utf-8'))
        for uid,role in ((1,'owner'),(2,'reviewer'),(3,'clerk')):
            c.execute('''INSERT INTO users(id,username,password_hash,role,created_at)
                VALUES(?,?,?,?,?)''',(uid,'synthetic-g3e-'+role,'synthetic-hash',role,day))
        c.execute("INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES('g3e-synthetic-session',2,'synthetic-csrf','2027-01-01')")
        c.execute("INSERT INTO departments(id,code,name) VALUES(101,'OR','Synthetic old OR')")
        for acc,code,kind in ((1,'1100','asset'),(2,'2200','liability'),(3,'5100','expense')):
            c.execute('INSERT INTO gl_accounts(id,code,name,class) VALUES(?,?,?,?)',(acc,code,'Synthetic '+code,kind))
        c.execute("INSERT INTO inventory_vendors(id,code,name) VALUES(17,'G3E_VENDOR','Synthetic frozen G3E supplier')")
        c.execute("INSERT INTO inventory_items(id,code,name,unit) VALUES(18,'G3E_ITEM','Synthetic legacy lot','piece')")

        def posted(jid,debit,credit,amount):
            c.execute('''INSERT INTO gl_journals(id,entry_date,memo,origin,created_by,created_at)
                VALUES(?,?,?,'manual',3,?)''',(jid,day,'SYN-G3E-'+str(jid),day))
            c.execute('''INSERT INTO gl_lines(journal_id,account_id,debit_piasters)
                VALUES(?,?,?)''',(jid,debit,amount))
            c.execute('''INSERT INTO gl_lines(journal_id,account_id,credit_piasters)
                VALUES(?,?,?)''',(jid,credit,amount))
            c.execute("UPDATE gl_journals SET status='posted',reviewed_by=2,reviewed_at=? WHERE id=?",(day,jid))
        c.execute('''INSERT INTO inventory_receipts(id,vendor_id,received_on,invoice_ref,evidence_ref,created_by,created_at)
            VALUES(19,17,?,'G3E-TEST-OLD-INVOICE','G3E-TEST-SIGNED-RECEIPT',3,?)''',(day,day))
        c.execute('''INSERT INTO inventory_receipt_lines(id,receipt_id,item_id,quantity,unit_cost_piasters,batch_ref)
            VALUES(20,19,18,4,1000,'G3E-SYNTHETIC-LOT')''')
        posted(31,1,2,4000)
        c.execute('''UPDATE inventory_receipts SET status='approved',reviewed_by=2,reviewed_at=?,journal_id=31 WHERE id=19''',(day,))
        c.execute('''INSERT INTO inventory_issues(id,department_id,used_on,evidence_ref,created_by,created_at)
            VALUES(40,101,?,'G3E-FIRST-ISSUE-OLD',3,?)''',(day,day))
        c.execute('INSERT INTO inventory_issue_lines(id,issue_id,item_id,quantity) VALUES(41,40,18,3)')
        c.execute('''INSERT INTO inventory_issue_allocations(id,issue_id,issue_line_id,receipt_line_id,quantity,cost_piasters)
            VALUES(42,40,41,20,3,3000)''')
        posted(32,3,1,3000)
        c.execute('''UPDATE inventory_issues SET status='approved',reviewed_by=2,reviewed_at=?,cost_piasters=3000,journal_id=32
            WHERE id=40''',(day,))
        c.execute('''INSERT INTO inventory_issue_returns(id,issue_id,returned_on,evidence_ref,created_by,created_at)
            VALUES(50,40,?,'G3E-OLD-PHYSICAL-RETURN',3,?)''',(day,day))
        c.execute('''INSERT INTO inventory_return_lines(id,return_id,issue_allocation_id,quantity)
            VALUES(51,50,42,2)''')
        posted(33,1,3,2000)
        c.execute('''UPDATE inventory_issue_returns SET status='approved',reviewed_by=2,reviewed_at=?,
            cost_piasters=2000,journal_id=33 WHERE id=50''',(day,))
        # This later G3E document legitimately reused an uninspected returned
        # unit. G3F cannot pretend it was clinically cleared retrospectively.
        c.execute('''INSERT INTO inventory_issues(id,department_id,used_on,evidence_ref,created_by,created_at)
            VALUES(60,101,?,'G3E-SECOND-ISSUE-LEGACY',3,?)''',(day,day))
        c.execute('INSERT INTO inventory_issue_lines(id,issue_id,item_id,quantity) VALUES(61,60,18,2)')
        c.execute('''INSERT INTO inventory_issue_allocations(id,issue_id,issue_line_id,receipt_line_id,quantity,cost_piasters)
            VALUES(62,60,61,20,2,2000)''')
        posted(34,3,1,2000)
        c.execute('''UPDATE inventory_issues SET status='approved',reviewed_by=2,reviewed_at=?,
            cost_piasters=2000,journal_id=34 WHERE id=60''',(day,))
        # A G3E pending issue could have pre-allocated an uninspected return.
        # Its original allocation survives the encrypted migration, but G3F
        # MUST prevent final approval even if a posted journal is attached.
        c.execute('''INSERT INTO inventory_issues(id,department_id,used_on,evidence_ref,created_by,created_at)
            VALUES(70,101,?,'G3E-PENDING-ALLOCATION-MUST-STOP',3,?)''',(day,day))
        c.execute('INSERT INTO inventory_issue_lines(id,issue_id,item_id,quantity) VALUES(71,70,18,1)')
        c.execute('''INSERT INTO inventory_issue_allocations(id,issue_id,issue_line_id,receipt_line_id,quantity,cost_piasters)
            VALUES(72,70,71,20,1,1000)''')
        posted(35,3,1,1000)
        assert c.execute('SELECT count(*) FROM inventory_return_lines').fetchone()[0]==1
        assert not c.execute('PRAGMA foreign_key_check').fetchall()


def run():
    with tempfile.TemporaryDirectory(prefix='g3f-real-g3e-upgrade-') as td:
        base=Path(td);source=base/'g3e-old.sqlite3'
        make_g3e(source)
        os.environ.update(RAMSES_DB_PATH=str(source),RAMSES_ADMIN_USER='owner',
                          RAMSES_ADMIN_PASSWORD='synthetic_g3f_upgrade_owner')
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE',None)
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE_FILE',None)
        from bootstrap import initialize,connect
        try:initialize()
        except (ValueError,RuntimeError) as error:
            assert 'passphrase' in str(error).lower(),str(error)
        else:raise AssertionError('G3E live-like schema upgraded without encrypted backup secret')
        with sqlite3.connect(source) as c:
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='inventory_return_inspections'").fetchone()
            assert c.execute('SELECT count(*) FROM inventory_issue_allocations').fetchone()[0]==3
        secret=base/'synthetic-secure-backup.secret'
        secret.write_text('synthetic-g3f-upgrade-secret-backup-2026-not-live')
        secret.chmod(0o600)
        os.environ['RAMSES_BACKUP_PASSPHRASE_FILE']=str(secret)
        initialize()
        from app import app  # register inventory routes before direct module imports
        from inventory import stock_asof,reconciliation
        with connect() as c:
            stock=stock_asof(c)[0]
            assert (stock['quantity_on_hand'],stock['quarantined_quantity'],stock['available_quantity'])==(1,1,0),stock
            assert c.execute('SELECT count(*) FROM inventory_return_inspections').fetchone()[0]==0
            old_return=c.execute('SELECT status,journal_id FROM inventory_issue_returns WHERE id=50').fetchone()
            assert (old_return['status'],old_return['journal_id'])==('approved',33)
            assert c.execute('SELECT journal_id FROM inventory_issues WHERE id=60').fetchone()['journal_id']==34
            assert c.execute('SELECT count(*) FROM gl_journals WHERE status="posted"').fetchone()[0]==5
            assert c.execute('SELECT user_id FROM sessions WHERE token_hash=?',('g3e-synthetic-session',)).fetchone()[0]==2
            assert 'inventory_return_inspections' in c.execute('''SELECT sql FROM sqlite_master
                WHERE type='trigger' AND name='inv_issue_allocation_guard' ''').fetchone()[0]
            assert reconciliation(c,'2026-10')['matched']
            try:
                c.execute('''UPDATE inventory_issues SET status='approved',reviewed_by=2,
                    reviewed_at='2026-10-30',cost_piasters=1000,journal_id=35 WHERE id=70''')
            except sqlite3.IntegrityError:
                c.rollback()
            else:
                raise AssertionError('G3E pending allocation on uninspected return was approved after migration')
            assert c.execute('SELECT status FROM inventory_issues WHERE id=70').fetchone()[0]=='pending'
            # G3E consumed a unit before any clinical release record existed.
            # A clinician may not certify all two original returned units as
            # present without a separate physical legacy-stock reconciliation.
            c.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES(4,'synthetic-old-inspector','x','clinician','2026-10-31')")
            c.execute('''INSERT INTO billing_clinical_identity_reviews
                (user_id,professional_name,registration_reference,approved,reviewed_by,reviewed_at,review_note)
                VALUES(4,'Synthetic migration examiner','SYN-G3F-MIGRATION-REFERENCE',1,1,'2026-10-31',
                'Synthetic only manually reviewed professional identity')''')
            c.execute('''INSERT INTO billing_clinical_grants(department_id,user_id,active,assigned_by,assigned_at)
                VALUES(101,4,1,1,'2026-10-31')''')
            try:
                c.execute('''INSERT INTO inventory_return_inspections
                    (return_line_id,decision,inspected_on,evidence_ref,note,
                     unused_confirmed,packaging_intact,infection_control_clearance,inspected_by,inspected_at)
                    VALUES(51,'released','2026-10-31','G3F-LEGACY-UNTRACEABLE-RELEASE',
                    'Attempt to clinically certify previously reissued return',1,1,1,4,'2026-10-31')''')
            except sqlite3.IntegrityError:
                c.rollback()
            else:
                raise AssertionError('Legacy G3E reissued return was falsely released without reconciliation')
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        backups=list((base/'pre_schema_upgrade_backups').glob('*.rbe'))
        assert len(backups)==1,backups
        assert stat.S_IMODE(backups[0].stat().st_mode)==0o600
        from scripts.secure_backup import verify_or_restore
        restored=base/'g3e-rollback-restored.sqlite3'
        verify_or_restore(backups[0],restored)
        with sqlite3.connect(restored) as c:
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='inventory_return_inspections'").fetchone()
            assert c.execute('SELECT cost_piasters FROM inventory_issue_returns WHERE id=50').fetchone()[0]==2000
            assert 'inventory_return_inspections' not in c.execute("SELECT sql FROM sqlite_master WHERE name='inv_issue_allocation_guard'").fetchone()[0]
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
        initialize()
        assert len(list((base/'pre_schema_upgrade_backups').glob('*.rbe')))==1
        os.environ.pop('RAMSES_BACKUP_PASSPHRASE_FILE',None)
        print('PASS G3F frozen G3E encrypted upgrade, G3E reuse history unchanged and old returned units quarantined, independent restore')

if __name__=='__main__':run()
