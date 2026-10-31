"""Initialize Ramses accounts and quarantine historical June entries; never post them to funds."""
import argparse
import hashlib
import os
import re
import secrets
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = Path(os.getenv("RAMSES_DB_PATH", str(ROOT / "private" / "ramses.sqlite3")))

DEPARTMENTS = [
 ("ER", "الاستقبال والطوارئ"), ("LAB", "المعمل"), ("RAD", "الأشعة والسونار"),
 ("IPD", "الحجز الداخلي"), ("NICU", "الحضانات"), ("OR", "العمليات"), ("PT", "العلاج الطبيعي"),
 ("DENT", "الأسنان"), ("CLINIC", "العيادات الخارجية"), ("PHARM", "الصيدلية"),
 ("ADMIN", "إداري ومشترك"), ("OTHER", "أقسام أخرى - للمراجعة")
]
CATEGORIES = [
 ("medical_revenue", "إيراد خدمات طبية", "receipt", "revenue"),
 ("other_revenue", "إيرادات تشغيل أخرى", "receipt", "revenue"),
 ("owner_funding", "تمويل من الملاك", "receipt", "equity"),
 ("loan_proceeds", "قرض / تمويل مستلم", "receipt", "liability"),
 ("expense_medical", "مستهلكات طبية مستخدمة", "payment", "expense"),
 ("inventory_buy", "شراء مخزون أدوية ومستلزمات", "payment", "asset"),
 ("doctor_fees", "أتعاب أطباء وفنيين", "payment", "expense"),
 ("lab_external", "معامل خارجية", "payment", "expense"),
 ("rent", "إيجارات", "payment", "expense"),
 ("utilities", "مرافق وخدمات", "payment", "expense"),
 ("maintenance", "صيانة تشغيلية", "payment", "expense"),
 ("marketing", "تسويق وإعلانات", "payment", "expense"),
 ("hospitality", "ضيافة ومصروفات إدارية", "payment", "expense"),
 ("equipment", "شراء أجهزة وتجهيزات", "payment", "asset"),
 ("debt_installment", "سداد أصل دين/قسط", "payment", "liability"),
 ("owner_draw", "مسحوبات ملاك", "payment", "equity"),
 ("salary_payment", "صرف راتب مستحق", "payment", "payroll_payment"),
 ("salary_advance", "سلفة موظف", "payment", "advance"),
 ("cash_shortage", "عجز خزنة معلق للتسوية", "payment", "asset"),
 ("cash_shortage_recovery", "سداد نقدي لعجز خزنة معتمد", "receipt", "asset"),
 ("cash_overage", "زيادة خزنة معلقة للتسوية", "receipt", "liability"),
 ("cash_overage_return", "رد زيادة ظرف لصاحب حق موثق", "payment", "liability"),
 ("pos_processing_fee", "POS acquiring and settlement fees", "payment", "expense"),
 ("late_cash_unallocated", "نقدية مستلمة غير مخصصة - استدراك معتمد", "receipt", "liability")
]
FUNDS = [("cash_main", "الخزنة الرئيسية", "cash"), ("cash_sub", "الخزنة الفرعية", "cash"),
         ("vodafone", "فودافون كاش", "wallet"), ("bank", "حساب بنكي", "bank")]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def to_piasters(value):
    d = Decimal(str(value or 0))
    return int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 290000)
    return "pbkdf2_sha256$290000$" + salt.hex() + "$" + digest.hex()


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, isolation_level=None, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=10000")
    return c


def seed(c):
    for code, name in DEPARTMENTS:
        c.execute("INSERT OR IGNORE INTO departments(code,name) VALUES (?,?)", (code, name))
    for code, name, direction, nature in CATEGORIES:
        c.execute("INSERT OR IGNORE INTO categories(code,name,direction,nature) VALUES (?,?,?,?)", (code,name,direction,nature))
    for code, name, kind in FUNDS:
        c.execute("INSERT OR IGNORE INTO funds(code,name,kind) VALUES (?,?,?)", (code,name,kind))


def import_legacy(c, path):
    if not Path(path).exists():
        return 0
    import openpyxl
    w = openpyxl.load_workbook(path, read_only=True, data_only=True)
    s = w["شهر 6"]
    seen = 0
    for row_i, r in enumerate(s.iter_rows(min_row=2, max_row=1000, max_col=19, values_only=True), 2):
        if str(r[4] or "") not in ("إيراد", "منصرف"):
            continue
        total = to_piasters(r[11]); cash = to_piasters(r[10]); wallet = to_piasters(r[9]);
        tr_date = r[3].date().isoformat() if isinstance(r[3], datetime) else (r[3].isoformat() if isinstance(r[3], date) else str(r[3])[:10] if r[3] else None)
        preview = os.getenv("RAMSES_ENVIRONMENT") == "free-preview"
        # Keep the authentic amounts/dates while hiding names/references in a shared trial.
        c.execute("""INSERT OR IGNORE INTO legacy_entries(source_row,transaction_date,kind,department_raw,shift_raw,category_raw,
                 cash_piasters,wallet_piasters,total_piasters,reference_no,description,employee_raw,salary_period_raw,review_mark)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (row_i,tr_date,r[4],str(r[5] or ""),str(r[6] or ""),str(r[7] or ""),cash,wallet,total,
                "" if preview else str(r[1] or ""),
                "حركة أرشيفية - التفاصيل الشخصية محجوبة" if preview else str(r[8] or ""),
                "" if preview else str(r[12] or ""),str(r[13] or ""),
                "تحت المراجعة" if preview and str(r[0] or "").strip() not in ("", "تمت المراجعة") else ("" if preview else str(r[0] or ""))))
        seen += 1
        if total == 0: issue(c,row_i,"zero_amount","حركة أرشيفية بمبلغ صفر تحتاج مراجعة")
        if not tr_date: issue(c,row_i,"missing_date","إيراد / مصروف بدون تاريخ")
        if abs(cash+wallet-total)>1: issue(c,row_i,"split_mismatch","مجموع النقد والمحفظة لا يساوي إجمالي الحركة")
        if r[4]=="منصرف" and not str(r[7] or "").strip(): issue(c,row_i,"missing_category","مصروف بلا تصنيف")
        if str(r[0] or "").strip() not in ("", "تمت المراجعة"):
            issue(c,row_i,"needs_review","ملاحظة مراجعة أرشيفية محجوبة" if preview else str(r[0]))
        if str(r[7] or "").strip()=="رواتب" and not str(r[13] or "").strip(): issue(c,row_i,"missing_salary_period","حركة راتب بلا شهر استحقاق")
    w.close()
    return seen


def issue(c,row_i,kind,message):
    c.execute("INSERT OR IGNORE INTO legacy_issues(source_row,issue_type,details) VALUES (?,?,?)",(row_i,kind,message))


def import_employee_roster(c,path):
    """Import names/jobs as unverified roster only; never guess salary or department."""
    if not Path(path).exists(): return 0
    import openpyxl
    w=openpyxl.load_workbook(path,read_only=True,data_only=True)
    if "إعدادات" not in w.sheetnames:
        w.close();return 0
    s=w["إعدادات"]
    names=set();created=0
    for row in s.iter_rows(min_row=2,max_row=90,min_col=10,max_col=11,values_only=True):
        name=str(row[0] or "").strip()
        job=str(row[1] or "").strip()
        if len(name)<3 or name in names:continue
        names.add(name)
        code=f"LEGEMP{created+1:03d}"
        if os.getenv("RAMSES_ENVIRONMENT") == "free-preview":
            name=f"موظف تجريبي من الأرشيف {created+1:03d}"
            job="بيانات الوظيفة محجوبة"
        cur=c.execute("INSERT OR IGNORE INTO employees(code,name,job_title) VALUES (?,?,?)",(code,name,job))
        created+=int(cur.rowcount>0)
    w.close()
    return created


def backup_before_schema_upgrade(c):
    """Fail closed with one encrypted, verifiable pre-DDL snapshot when needed.

    Both old migrations and new tables must be backed up before executescript().
    The passphrase is never invented or stored in application source.
    """
    if not DB.exists() or not DB.stat().st_size:
        return None
    objects={(row['type'],row['name']) for row in c.execute(
        "SELECT type,name FROM sqlite_master WHERE type IN ('table','index','trigger')")}
    tables={name for kind,name in objects if kind=='table'}
    if not {'users', 'vouchers', 'fund_movements'}.issubset(tables):
        raise ValueError('Existing database is not recognized as a Ramses database; migration refused')
    if 'gl_journals' not in tables:
        folder, prefix = 'pre_gl_upgrade_backups', 'before_v8'
    elif 'billing_points' not in tables:
        folder, prefix = 'pre_billing_upgrade_backups', 'before_v81'
    elif 'billing_invoices' not in tables:
        folder, prefix = 'pre_billing_v81b_backups', 'before_v81b'
    elif 'shift_templates' not in tables:
        folder, prefix = 'pre_billing_v81c_backups', 'before_v81c'
    elif ('billing_case_lines' in tables and
          'service_date' not in {r['name'] for r in c.execute('PRAGMA table_info(billing_case_lines)')}):
        folder, prefix = 'pre_g2u_upgrade_backups', 'before_g2u'
    else:
        # Other version additions use CREATE ... IF NOT EXISTS. Detect the
        # objects before the SQL script writes them, not just four old stages.
        source = (ROOT/'schema.sql').read_text(encoding='utf8')
        expected = re.findall(
            r'CREATE\s+(TABLE|TRIGGER|(?:UNIQUE\s+)?INDEX)\s+IF\s+NOT\s+EXISTS\s+(\w+)',
            source, flags=re.IGNORECASE)
        missing = any((kind.split()[-1].lower(), name) not in objects for kind,name in expected)
        # Some historical ALTER TABLE migrations live in bootstrap rather than
        # schema.sql. A partial upgrade must also have a safe rollback point.
        columns = {
            'funds': ('cash_restricted',),
            'user_fund_grants': ('can_approve',),
            'fund_movements': ('shift_session_id',),
            'shift_sessions': ('scheduled_start_at', 'scheduled_end_at',
                               'count_version', 'point_id', 'envelope_present'),
            'cashier_schedule_versions': ('operating_days',),
            'salary_terms': ('pay_type', 'hourly_piasters'),
            'payroll_accruals': ('pay_type', 'hourly_rate_piasters',
                                 'worked_minutes', 'work_entries_count',
                                 'adjustment_additions_piasters', 'adjustment_deductions_piasters',
                                 'signoff_status', 'signed_off_by', 'signed_off_at', 'signoff_note'),
            'billing_clinical_attestations': ('document_sha256', 'document_size',
                                               'document_media_type'),
        }
        for table, fields in columns.items():
            if table not in tables:
                missing = True
                continue
            known = {r['name'] for r in c.execute(f'PRAGMA table_info("{table}")')}
            if any(column not in known for column in fields):
                missing = True
        if not {('trigger', 'billing_fulfilled_line_no_update'),
                ('trigger', 'billing_fulfilled_line_no_delete')}.issubset(objects):
            missing = True
        # A new clinician role changes the existing users CHECK constraint,
        # even when all table names already exist. Back up BEFORE rebuilding.
        if 'users' in tables:
            users_sql=c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()['sql']
            if "'clinician'" not in users_sql:
                missing=True
        if not missing:
            return None
        folder, prefix = 'pre_schema_upgrade_backups', 'before_schema'
    from scripts.secure_backup import create_preupgrade
    name=prefix+'_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')+'_'+secrets.token_hex(4)+'.rbe'
    return create_preupgrade(c, DB.parent/folder, name)


def migrate_clinician_role(c):
    '''Copy users inside one FK-checked transaction after encrypted rollback.

    SQLite cannot ALTER a CHECK constraint. Preserve original integer IDs and
    linked sessions/financial/clinical records, never synthesize credentials.
    Existing G2Z viewer witness grants are suspended, not promoted to doctors.
    '''
    row=c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
    if not row or "'clinician'" in row['sql']:
        return False
    if c.in_transaction:
        raise RuntimeError('Cannot rebuild clinical account role inside another transaction')
    c.execute('PRAGMA foreign_keys=OFF')
    try:
        c.execute('BEGIN IMMEDIATE')
        c.execute('''CREATE TABLE users_g3a (
            id INTEGER PRIMARY KEY,username TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('owner','reviewer','clerk','viewer','clinician')),
            active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL)''')
        c.execute('''INSERT INTO users_g3a(id,username,password_hash,role,active,created_at)
            SELECT id,username,password_hash,role,active,created_at FROM users''')
        # SQLite validates all triggers during RENAME. The legacy medical
        # trigger joins users and must be re-created from schema.sql afterward.
        c.execute('DROP TRIGGER IF EXISTS billing_clinical_attestation_validate_insert')
        c.execute('DROP TABLE users')
        c.execute('ALTER TABLE users_g3a RENAME TO users')
        # Safety: historical pilot witnesses stay for audit; old viewer grants
        # can no longer certify services after role separation.
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='billing_clinical_grants'").fetchone():
            c.execute("UPDATE billing_clinical_grants SET active=0 WHERE user_id IN (SELECT id FROM users WHERE role='viewer')")
        errors=c.execute('PRAGMA foreign_key_check').fetchall()
        if errors:
            raise RuntimeError('Foreign keys failed after clinician-role migration: '+str(len(errors)))
        c.commit()
    except BaseException:
        c.rollback()
        raise
    finally:
        c.execute('PRAGMA foreign_keys=ON')
    if not c.execute('PRAGMA foreign_keys').fetchone()[0]:
        raise RuntimeError('Foreign keys were not re-enabled after clinical role upgrade')
    return True


def initialize(legacy_path=None):
    if os.getenv("RENDER", "").lower()=="true" and os.getenv("RAMSES_SECURE_COOKIES", "0")!="1":
        raise RuntimeError("Refusing Render deployment without Secure session cookies")
    user = os.getenv("RAMSES_ADMIN_USER", "").strip().lower()
    pw = os.getenv("RAMSES_ADMIN_PASSWORD", "")
    # The bootstrap password is necessary only when the owner account is first created.
    # Once created, it may be deleted from .env without affecting restarts.
    prior_database=DB.exists() and DB.stat().st_size>0
    c=connect()
    try:
        if prior_database:
            backup = backup_before_schema_upgrade(c)
            if backup:
                print('Verified encrypted pre-upgrade rollback:', backup)
            if migrate_clinician_role(c):
                print('G3A clinician role added with original user IDs and old viewer grants suspended')
        with c:
            # Existing G2Z SQLite triggers contain the obsolete viewer witness
            # rule. Re-create only that trigger against the new clinician policy.
            witness=c.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name='billing_clinical_attestation_validate_insert'").fetchone()
            if witness and "u.role='viewer'" in witness['sql']:
                c.execute('DROP TRIGGER billing_clinical_attestation_validate_insert')
            # G3B additive clinical fingerprint; back up old schema first (above).
            # Existing witness rows remain NULL; never invent a signed document.
            has_attest=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='billing_clinical_attestations'").fetchone()
            if has_attest:
                known={r['name'] for r in c.execute('PRAGMA table_info(billing_clinical_attestations)')}
                for col in ('document_sha256','document_size','document_media_type'):
                    if col not in known:
                        c.execute(f'ALTER TABLE billing_clinical_attestations ADD COLUMN {col} '+
                                  ('INTEGER' if col=='document_size' else 'TEXT'))
            # G3D: the G2T lot guard used gross issues only; recreate it once,
            # under the verified encrypted pre-upgrade backup, for return-aware FIFO.
            if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_issue_returns'").fetchone():
                c.execute('DROP TRIGGER IF EXISTS inv_issue_allocation_guard')
            c.executescript((ROOT / "schema.sql").read_text(encoding="utf8"))
            # G2U additive, preservation-first migration: old dates stay unknown.
            if 'service_date' not in {r['name'] for r in c.execute('PRAGMA table_info(billing_case_lines)')}:
                c.execute('ALTER TABLE billing_case_lines ADD COLUMN service_date TEXT')
            # Fulfilled evidence and its tariff cannot be rewritten, including
            # through direct SQLite access, after the dated service is attested.
            c.execute('''CREATE TRIGGER IF NOT EXISTS billing_fulfilled_line_no_update
                BEFORE UPDATE ON billing_case_lines WHEN OLD.state='fulfilled'
                BEGIN SELECT RAISE(ABORT,'Fulfilled service evidence is immutable'); END''')
            c.execute('''CREATE TRIGGER IF NOT EXISTS billing_fulfilled_line_no_delete
                BEFORE DELETE ON billing_case_lines WHEN OLD.state='fulfilled'
                BEGIN SELECT RAISE(ABORT,'Fulfilled service evidence is immutable'); END''')
            # Existing cash funds retain their historical configuration until the owner
            # explicitly activates restricted cash operations; newly created tills start restricted.
            fund_columns={r[1] for r in c.execute('PRAGMA table_info(funds)')}
            if 'cash_restricted' not in fund_columns:
                c.execute('ALTER TABLE funds ADD COLUMN cash_restricted INTEGER NOT NULL DEFAULT 0 CHECK(cash_restricted IN (0,1))')
            # Existing deployments created bank grants before review permissions existed.
            # Never infer approval permission from submission permission.
            columns={r[1] for r in c.execute('PRAGMA table_info(user_fund_grants)')}
            if 'can_approve' not in columns:
                c.execute('ALTER TABLE user_fund_grants ADD COLUMN can_approve INTEGER NOT NULL DEFAULT 0 CHECK(can_approve IN (0,1))')
            # Safe, additive migration for V7.1-V7.2 databases.
            columns={r[1] for r in c.execute("PRAGMA table_info(fund_movements)")}
            if "shift_session_id" not in columns:
                c.execute("ALTER TABLE fund_movements ADD COLUMN shift_session_id INTEGER REFERENCES shift_sessions(id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_movements_shift ON fund_movements(shift_session_id)")
            shift_columns={r[1] for r in c.execute("PRAGMA table_info(shift_sessions)")}
            for name,definition in {
                'scheduled_start_at':'TEXT',
                'scheduled_end_at':'TEXT',
                'count_version':'INTEGER NOT NULL DEFAULT 0',
            }.items():
                if name not in shift_columns:
                    c.execute(f'ALTER TABLE shift_sessions ADD COLUMN {name} {definition}')
            # Old V7 unique index also locked submitted shifts. A documented,
            # accepted, discrepancy-free handoff may now roll into the next shift
            # while the accountant's historical signoff is pending.
            c.execute('DROP INDEX IF EXISTS idx_one_active_shift_per_fund')
            c.execute("CREATE UNIQUE INDEX idx_one_active_shift_per_fund ON shift_sessions(fund_id) WHERE status='open'")
            for code,start in [('night',0),('morning',480),('evening',960)]:
                c.execute('INSERT OR IGNORE INTO shift_templates(code,start_minute) VALUES (?,?)',(code,start))
            c.execute('INSERT OR IGNORE INTO shift_settings(id,enforce_clock) VALUES (1,0)')
            # Additive V7.4 upgrade: old salary terms and signed-off payroll remain intact.
            for table,fields in {
                'salary_terms': {
                    'pay_type': "TEXT NOT NULL DEFAULT 'monthly' CHECK(pay_type IN ('monthly','hourly'))",
                    'hourly_piasters': 'INTEGER NOT NULL DEFAULT 0 CHECK(hourly_piasters >= 0)',
                },
                'payroll_accruals': {
                    'pay_type': "TEXT NOT NULL DEFAULT 'monthly' CHECK(pay_type IN ('monthly','hourly'))",
                    'hourly_rate_piasters': 'INTEGER NOT NULL DEFAULT 0',
                    'worked_minutes': 'INTEGER NOT NULL DEFAULT 0',
                    'work_entries_count': 'INTEGER NOT NULL DEFAULT 0',
                    'adjustment_additions_piasters': 'INTEGER NOT NULL DEFAULT 0',
                    'adjustment_deductions_piasters': 'INTEGER NOT NULL DEFAULT 0',
                    'signoff_status': "TEXT NOT NULL DEFAULT 'legacy' CHECK(signoff_status IN ('legacy','pending','approved','rejected'))",
                    'signed_off_by': 'INTEGER REFERENCES users(id)',
                    'signed_off_at': 'TEXT',
                    'signoff_note': "TEXT NOT NULL DEFAULT ''",
                },
            }.items():
                existing={row[1] for row in c.execute(f'PRAGMA table_info({table})')}
                for column,definition in fields.items():
                    if column not in existing:
                        c.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
            seed(c)
            # These categories cannot be used through the generic voucher form.
            c.execute("INSERT OR IGNORE INTO categories(code,name,direction,nature) VALUES ('billing_invoice_receipt','تحصيل مديونية فاتورة مريض','receipt','asset')")
            c.execute("INSERT OR IGNORE INTO categories(code,name,direction,nature) VALUES ('billing_advance_receipt','مقدم تحت حساب مريض','receipt','liability')")
            c.execute("INSERT OR IGNORE INTO categories(code,name,direction,nature) VALUES ('billing_credit_refund','Patient credit refund','payment','liability')")
            c.execute("INSERT OR IGNORE INTO categories(code,name,direction,nature) VALUES ('billing_advance_refund','Patient unallocated advance refund','payment','liability')")
            from ledger import seed_chart
            seed_chart(c)
            # Station identities are seeded without attaching a physical fund or real prices.
            # Owner configures cash drawers and staff access explicitly before future collections.
            c.execute("INSERT OR IGNORE INTO billing_points(code,name,kind) VALUES (?,?,?)",
                      ('OUTPATIENT','الكاشير الخارجي','external'))
            c.execute("INSERT OR IGNORE INTO billing_points(code,name,kind) VALUES (?,?,?)",
                      ('INPATIENT','خزينة الحسابات الداخلية','internal'))
            if c.execute("SELECT count(*) FROM users").fetchone()[0]==0:
                if not user or len(pw) < 16:
                    raise RuntimeError("First startup needs RAMSES_ADMIN_USER and a 16+ character RAMSES_ADMIN_PASSWORD")
                c.execute("INSERT INTO users(username,password_hash,role,created_at) VALUES (?,?,?,?)",(user,hash_password(pw),"owner",now()))
            if legacy_path:
                import_legacy(c,legacy_path)
                import_employee_roster(c,legacy_path)
        from cashier_ops import upgrade_shift_table, seed_schedules
        upgraded=upgrade_shift_table(c,DB)
        if upgraded:
            print('Upgraded legacy shift names after an encrypted rollback snapshot')
        with c:
            c.execute('BEGIN IMMEDIATE')
            cols={r['name'] for r in c.execute('PRAGMA table_info(shift_sessions)')}
            if 'point_id' not in cols:
                c.execute('ALTER TABLE shift_sessions ADD COLUMN point_id INTEGER REFERENCES billing_points(id)')
            if 'envelope_present' not in cols:
                c.execute('ALTER TABLE shift_sessions ADD COLUMN envelope_present INTEGER NOT NULL DEFAULT 0')
            cv={r['name'] for r in c.execute('PRAGMA table_info(cashier_schedule_versions)')}
            if 'operating_days' not in cv:
                c.execute("ALTER TABLE cashier_schedule_versions ADD COLUMN operating_days TEXT NOT NULL DEFAULT '0123456'")
            seed_schedules(c)
        print("Database initialized:",DB)
        print("Historical rows:",c.execute("SELECT count(*) FROM legacy_entries").fetchone()[0],"(quarantined, not posted)")
    finally:
        c.close()


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--legacy", default=None, help="Optional historical source; never posted as live balances")
    args=p.parse_args()
    initialize(args.legacy)
