PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('owner','reviewer','clerk','viewer','clinician')), active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), csrf TEXT NOT NULL, expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS login_attempts (id INTEGER PRIMARY KEY, username TEXT NOT NULL, occurred_at TEXT NOT NULL);
-- G2Q: only failed attempts from the same observed source may throttle a user;
-- do not apply an attacker-controlled username-only lock across the hospital.
CREATE TABLE IF NOT EXISTS login_rate_events (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL, source_key TEXT NOT NULL,
 occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_login_rate_source_time ON login_rate_events(source_key, occurred_at);
CREATE INDEX IF NOT EXISTS idx_login_rate_source_user ON login_rate_events(source_key, username, occurred_at);

CREATE TABLE IF NOT EXISTS departments (
 id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL UNIQUE, active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS categories (
 id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL UNIQUE,
 direction TEXT NOT NULL CHECK(direction IN ('receipt','payment')),
 nature TEXT NOT NULL CHECK(nature IN ('revenue','expense','asset','liability','equity','payroll_payment','advance')),
 active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS funds (
 id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL UNIQUE,
 kind TEXT NOT NULL CHECK(kind IN ('cash','wallet','bank')),
 opening_piasters INTEGER NOT NULL DEFAULT 0, allow_negative INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
 cash_restricted INTEGER NOT NULL DEFAULT 0 CHECK(cash_restricted IN (0,1))
);
-- Explicit grants for sensitive bank/wallet cashbook submission. Never inferred
-- from the broad login role; owner can revoke from the active server instantly.
CREATE TABLE IF NOT EXISTS user_fund_grants (
 user_id INTEGER NOT NULL REFERENCES users(id),
 fund_id INTEGER NOT NULL REFERENCES funds(id),
 can_submit INTEGER NOT NULL DEFAULT 0 CHECK(can_submit IN (0,1)),
 can_approve INTEGER NOT NULL DEFAULT 0 CHECK(can_approve IN (0,1)),
 changed_by INTEGER NOT NULL REFERENCES users(id),
 changed_at TEXT NOT NULL,
 reason TEXT NOT NULL,
 PRIMARY KEY(user_id,fund_id)
);
CREATE TABLE IF NOT EXISTS employees (
 id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL, job_title TEXT DEFAULT '',
 department_id INTEGER REFERENCES departments(id), active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS salary_terms (
 id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id),
 monthly_piasters INTEGER NOT NULL CHECK(monthly_piasters >= 0), valid_from TEXT NOT NULL,
 valid_to TEXT, note TEXT DEFAULT '',
 pay_type TEXT NOT NULL DEFAULT 'monthly' CHECK(pay_type IN ('monthly','hourly')),
 hourly_piasters INTEGER NOT NULL DEFAULT 0 CHECK(hourly_piasters >= 0),
 CHECK(valid_to IS NULL OR valid_to >= valid_from)
);
-- Approved work minutes are the audit source for hourly payroll; never infer hours from cash shifts.
CREATE TABLE IF NOT EXISTS payroll_work_entries (
 id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id),
 work_date TEXT NOT NULL, shift TEXT NOT NULL CHECK(shift IN ('morning','evening','night','central')),
 work_minutes INTEGER NOT NULL CHECK(work_minutes > 0 AND work_minutes <= 1440),
 note TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'pending'
 CHECK(status IN ('pending','approved','rejected','voided')),
 created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
 reviewed_by INTEGER REFERENCES users(id), reviewed_at TEXT, review_note TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_work_entry_active
 ON payroll_work_entries(employee_id,work_date,shift) WHERE status IN ('pending','approved');
CREATE INDEX IF NOT EXISTS idx_work_entry_month ON payroll_work_entries(work_date,status,employee_id);
CREATE TABLE IF NOT EXISTS periods (
 period TEXT PRIMARY KEY, closed_by INTEGER REFERENCES users(id), closed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vouchers (
 id INTEGER PRIMARY KEY, voucher_no TEXT NOT NULL UNIQUE, date TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('receipt','payment','transfer')),
 department_id INTEGER REFERENCES departments(id), category_id INTEGER REFERENCES categories(id),
 from_fund_id INTEGER NOT NULL REFERENCES funds(id), to_fund_id INTEGER REFERENCES funds(id),
 shift TEXT NOT NULL CHECK(shift IN ('morning','evening','night','central')),
 employee_id INTEGER REFERENCES employees(id), salary_period TEXT,
 amount_piasters INTEGER NOT NULL CHECK(amount_piasters > 0),
 description TEXT NOT NULL, reference_no TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'pending'
 CHECK(status IN ('pending','approved','rejected','reversed')),
 created_by INTEGER NOT NULL REFERENCES users(id), reviewed_by INTEGER REFERENCES users(id),
 created_at TEXT NOT NULL, reviewed_at TEXT, review_reason TEXT,
 reversal_of_id INTEGER UNIQUE REFERENCES vouchers(id)
);
CREATE TABLE IF NOT EXISTS voucher_request_keys (
 request_id TEXT PRIMARY KEY, voucher_id INTEGER NOT NULL UNIQUE REFERENCES vouchers(id),
 payload_hash TEXT NOT NULL, created_by INTEGER NOT NULL REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_vouchers_date ON vouchers(date,status);
CREATE INDEX IF NOT EXISTS idx_vouchers_employee ON vouchers(employee_id,salary_period);
CREATE TABLE IF NOT EXISTS fund_movements (
 id INTEGER PRIMARY KEY, voucher_id INTEGER NOT NULL REFERENCES vouchers(id),
 fund_id INTEGER NOT NULL REFERENCES funds(id), amount_piasters INTEGER NOT NULL CHECK(amount_piasters <> 0),
 booked_on TEXT NOT NULL, shift_session_id INTEGER REFERENCES shift_sessions(id),
 UNIQUE(voucher_id,fund_id)
);
-- G2J: posted cashbook legs are append-only; reversal is a NEW voucher.
-- No released workflow changes or deletes a physical fund movement.
CREATE TRIGGER IF NOT EXISTS fund_movement_no_update BEFORE UPDATE ON fund_movements
 BEGIN SELECT RAISE(ABORT,'Cashbook movements are immutable'); END;
CREATE TRIGGER IF NOT EXISTS fund_movement_no_delete BEFORE DELETE ON fund_movements
 BEGIN SELECT RAISE(ABORT,'Cashbook movements are immutable'); END;
-- Cashier count is a blind count and is reviewed by a distinct approver.
-- Exactly one active (open or submitted) shift per physical fund.
CREATE TABLE IF NOT EXISTS shift_sessions (
 id INTEGER PRIMARY KEY,
 business_date TEXT NOT NULL, shift TEXT NOT NULL,
 fund_id INTEGER NOT NULL REFERENCES funds(id), responsible_id INTEGER NOT NULL REFERENCES users(id),
 opened_at TEXT NOT NULL, opening_piasters INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','submitted','closed')),
 counted_piasters INTEGER CHECK(counted_piasters>=0), expected_piasters INTEGER,
 variance_piasters INTEGER, note TEXT NOT NULL DEFAULT '',
 submitted_by INTEGER REFERENCES users(id), submitted_at TEXT,
 reviewed_by INTEGER REFERENCES users(id), reviewed_at TEXT, review_note TEXT NOT NULL DEFAULT '',
 UNIQUE(business_date,shift,fund_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_shift_per_fund
 ON shift_sessions(fund_id) WHERE status='open';
CREATE INDEX IF NOT EXISTS idx_shifts_month ON shift_sessions(business_date,status);
CREATE INDEX IF NOT EXISTS idx_movements_fund_date ON fund_movements(fund_id,booked_on);
CREATE TABLE IF NOT EXISTS payroll_accruals (
 id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id),
 period TEXT NOT NULL, base_piasters INTEGER NOT NULL, additions_piasters INTEGER NOT NULL DEFAULT 0,
 deductions_piasters INTEGER NOT NULL DEFAULT 0,
 net_piasters INTEGER NOT NULL CHECK(net_piasters >= 0),
 approved_by INTEGER NOT NULL REFERENCES users(id), approved_at TEXT NOT NULL,
 pay_type TEXT NOT NULL DEFAULT 'monthly' CHECK(pay_type IN ('monthly','hourly')),
 hourly_rate_piasters INTEGER NOT NULL DEFAULT 0,
 worked_minutes INTEGER NOT NULL DEFAULT 0,
 work_entries_count INTEGER NOT NULL DEFAULT 0,
 adjustment_additions_piasters INTEGER NOT NULL DEFAULT 0,
 adjustment_deductions_piasters INTEGER NOT NULL DEFAULT 0,
 signoff_status TEXT NOT NULL DEFAULT 'legacy' CHECK(signoff_status IN ('legacy','pending','approved','rejected')),
 signed_off_by INTEGER REFERENCES users(id), signed_off_at TEXT, signoff_note TEXT NOT NULL DEFAULT '',
 UNIQUE(employee_id, period)
);
CREATE TABLE IF NOT EXISTS payroll_accrual_corrections (
 id INTEGER PRIMARY KEY,
 accrual_id INTEGER NOT NULL REFERENCES payroll_accruals(id),
 old_additions INTEGER NOT NULL,old_deductions INTEGER NOT NULL,old_net INTEGER NOT NULL,
 new_additions INTEGER NOT NULL,new_deductions INTEGER NOT NULL,new_net INTEGER NOT NULL,
 reason TEXT NOT NULL,actor_id INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL
);
-- Adjustment requests are explicit amounts, not automatic statutory deductions.
-- Approver must differ from originator; accepted items are frozen into the payroll accrual.
CREATE TABLE IF NOT EXISTS payroll_adjustments (
 id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id),
 period TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('overtime_premium','paid_leave_credit','bonus','other_addition',
                                  'lateness_deduction','absence_deduction','other_deduction')),
 amount_piasters INTEGER NOT NULL CHECK(amount_piasters > 0),
 note TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
 CHECK(status IN ('pending','approved','rejected','voided')),
 created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
 reviewed_by INTEGER REFERENCES users(id), reviewed_at TEXT, review_note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_adjustments_period ON payroll_adjustments(period,status,employee_id);
CREATE TABLE IF NOT EXISTS advance_allocations (
 id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id), period TEXT NOT NULL,
 amount_piasters INTEGER NOT NULL CHECK(amount_piasters > 0),
 actor_id INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL
);
-- Financial evidence remains inside SQLite: online backups capture binary documents atomically.
-- Evidence cannot be altered after the associated voucher leaves pending state.
CREATE TABLE IF NOT EXISTS voucher_attachments (
 id INTEGER PRIMARY KEY,
 voucher_id INTEGER NOT NULL REFERENCES vouchers(id),
 file_name TEXT NOT NULL,
 media_type TEXT NOT NULL CHECK(media_type IN ('application/pdf','image/jpeg','image/png')),
 file_size INTEGER NOT NULL CHECK(file_size > 0 AND file_size <= 6291456),
 sha256 TEXT NOT NULL,
 content BLOB NOT NULL,
 uploaded_by INTEGER NOT NULL REFERENCES users(id),
 created_at TEXT NOT NULL,
 UNIQUE(voucher_id,sha256)
);
CREATE INDEX IF NOT EXISTS idx_attachments_voucher ON voucher_attachments(voucher_id);
-- Counted cash can be short/over only after independent investigation and owner signoff.
CREATE TABLE IF NOT EXISTS shift_variance_cases (
 id INTEGER PRIMARY KEY,
 shift_session_id INTEGER NOT NULL REFERENCES shift_sessions(id),
 variance_piasters INTEGER NOT NULL CHECK(variance_piasters <> 0),
 explanation TEXT NOT NULL,
 proposed_by INTEGER NOT NULL REFERENCES users(id),
 proposed_at TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'proposed' CHECK(status IN ('proposed','approved','rejected')),
 decided_by INTEGER REFERENCES users(id),
 decided_at TEXT, decision_note TEXT NOT NULL DEFAULT '',
 adjustment_voucher_id INTEGER UNIQUE REFERENCES vouchers(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_active_shift_variance
 ON shift_variance_cases(shift_session_id) WHERE status IN ('proposed','approved');
-- V7.6: statement evidence is separate from ledger. No bank import posts cash.
-- Only one non-voided statement per bank fund and month; signed reconciliations are immutable.
CREATE TABLE IF NOT EXISTS bank_statement_batches (
 id INTEGER PRIMARY KEY,
 fund_id INTEGER NOT NULL REFERENCES funds(id),
 period TEXT NOT NULL,
 file_name TEXT NOT NULL,
 sha256 TEXT NOT NULL,
 raw_csv BLOB NOT NULL CHECK(length(raw_csv) > 0 AND length(raw_csv) <= 524288),
 opening_piasters INTEGER NOT NULL CHECK(opening_piasters >= 0),
 closing_piasters INTEGER NOT NULL CHECK(closing_piasters >= 0),
 imported_by INTEGER NOT NULL REFERENCES users(id),
 imported_at TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved','voided')),
 approved_by INTEGER REFERENCES users(id),
 approved_at TEXT, approval_note TEXT NOT NULL DEFAULT '',
 voided_by INTEGER REFERENCES users(id), voided_at TEXT, void_reason TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_bank_one_active_period
 ON bank_statement_batches(fund_id,period) WHERE status != 'voided';
CREATE TABLE IF NOT EXISTS bank_statement_lines (
 id INTEGER PRIMARY KEY,
 batch_id INTEGER NOT NULL REFERENCES bank_statement_batches(id),
 line_no INTEGER NOT NULL,
 tx_date TEXT NOT NULL,
 description TEXT NOT NULL,
 reference TEXT NOT NULL DEFAULT '',
 amount_piasters INTEGER NOT NULL CHECK(amount_piasters <> 0),
 UNIQUE(batch_id,line_no)
);
CREATE INDEX IF NOT EXISTS idx_bank_lines_batch ON bank_statement_lines(batch_id,tx_date);
-- Retain unmatching decisions rather than delete history. Unique active match per side.
CREATE TABLE IF NOT EXISTS bank_statement_matches (
 id INTEGER PRIMARY KEY,
 line_id INTEGER NOT NULL REFERENCES bank_statement_lines(id),
 movement_id INTEGER NOT NULL REFERENCES fund_movements(id),
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','voided')),
 matched_by INTEGER NOT NULL REFERENCES users(id), matched_at TEXT NOT NULL,
 note TEXT NOT NULL DEFAULT '',
 voided_by INTEGER REFERENCES users(id), voided_at TEXT, void_reason TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_bank_one_match_line
 ON bank_statement_matches(line_id) WHERE status='active';
CREATE UNIQUE INDEX IF NOT EXISTS idx_bank_one_match_movement
 ON bank_statement_matches(movement_id) WHERE status='active';
-- G2J: once independently signed, a bank statement and its evidence cannot
-- be edited in-place (including matches). Draft cancellation remains possible.
CREATE TRIGGER IF NOT EXISTS signed_bank_batch_no_update BEFORE UPDATE ON bank_statement_batches
 WHEN OLD.status='approved' BEGIN SELECT RAISE(ABORT,'Signed bank statement is immutable'); END;
CREATE TRIGGER IF NOT EXISTS signed_bank_batch_no_delete BEFORE DELETE ON bank_statement_batches
 WHEN OLD.status='approved' BEGIN SELECT RAISE(ABORT,'Signed bank statement is immutable'); END;
CREATE TRIGGER IF NOT EXISTS signed_bank_line_no_update BEFORE UPDATE ON bank_statement_lines
 WHEN (SELECT status FROM bank_statement_batches WHERE id=OLD.batch_id)='approved'
 BEGIN SELECT RAISE(ABORT,'Signed bank evidence is immutable'); END;
CREATE TRIGGER IF NOT EXISTS signed_bank_line_no_delete BEFORE DELETE ON bank_statement_lines
 WHEN (SELECT status FROM bank_statement_batches WHERE id=OLD.batch_id)='approved'
 BEGIN SELECT RAISE(ABORT,'Signed bank evidence is immutable'); END;
CREATE TRIGGER IF NOT EXISTS signed_bank_line_no_insert BEFORE INSERT ON bank_statement_lines
 WHEN (SELECT status FROM bank_statement_batches WHERE id=NEW.batch_id)='approved'
 BEGIN SELECT RAISE(ABORT,'Signed bank evidence is immutable'); END;
CREATE TRIGGER IF NOT EXISTS signed_bank_match_no_update BEFORE UPDATE ON bank_statement_matches
 WHEN (SELECT b.status FROM bank_statement_lines l JOIN bank_statement_batches b ON b.id=l.batch_id WHERE l.id=OLD.line_id)='approved'
 BEGIN SELECT RAISE(ABORT,'Signed bank matches are immutable'); END;
CREATE TRIGGER IF NOT EXISTS signed_bank_match_no_delete BEFORE DELETE ON bank_statement_matches
 WHEN (SELECT b.status FROM bank_statement_lines l JOIN bank_statement_batches b ON b.id=l.batch_id WHERE l.id=OLD.line_id)='approved'
 BEGIN SELECT RAISE(ABORT,'Signed bank matches are immutable'); END;
CREATE TRIGGER IF NOT EXISTS signed_bank_match_no_insert BEFORE INSERT ON bank_statement_matches
 WHEN (SELECT b.status FROM bank_statement_lines l JOIN bank_statement_batches b ON b.id=l.batch_id WHERE l.id=NEW.line_id)='approved'
 BEGIN SELECT RAISE(ABORT,'Signed bank matches are immutable'); END;
CREATE TABLE IF NOT EXISTS legacy_entries (
 id INTEGER PRIMARY KEY, source_row INTEGER NOT NULL UNIQUE, transaction_date TEXT,
 kind TEXT, department_raw TEXT, shift_raw TEXT, category_raw TEXT,
 cash_piasters INTEGER NOT NULL, wallet_piasters INTEGER NOT NULL,
 total_piasters INTEGER NOT NULL, reference_no TEXT, description TEXT,
 employee_raw TEXT, salary_period_raw TEXT, review_mark TEXT, import_status TEXT NOT NULL DEFAULT 'archive_unverified'
);
CREATE TABLE IF NOT EXISTS legacy_issues (
 id INTEGER PRIMARY KEY, source_row INTEGER NOT NULL, issue_type TEXT NOT NULL, details TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'open', UNIQUE(source_row, issue_type)
);
CREATE TABLE IF NOT EXISTS audit_log (
 id INTEGER PRIMARY KEY, actor_id INTEGER REFERENCES users(id), action TEXT NOT NULL,
 entity TEXT NOT NULL, entity_id TEXT NOT NULL, details TEXT DEFAULT '{}', created_at TEXT NOT NULL
);
-- G2Q: app-level SQL immutability. A privileged OS/DB administrator could
-- still replace the database or drop triggers: use off-device tamper-evident
-- archival audit storage for production-grade forensic protection.
CREATE TRIGGER IF NOT EXISTS audit_log_no_update BEFORE UPDATE ON audit_log
 BEGIN SELECT RAISE(ABORT,'Approved audit events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_delete BEFORE DELETE ON audit_log
 BEGIN SELECT RAISE(ABORT,'Approved audit events are append-only'); END;
CREATE TABLE IF NOT EXISTS sync_status (
 id INTEGER PRIMARY KEY CHECK(id=1), dirty INTEGER NOT NULL DEFAULT 1, revision INTEGER NOT NULL DEFAULT 0, synced_revision INTEGER NOT NULL DEFAULT 0, last_synced_at TEXT, last_error TEXT
);
INSERT OR IGNORE INTO sync_status(id,dirty) VALUES (1,1);

-- V8.0 accounting foundation.  Operational cashbook remains the source for cash balances.
-- These journals are a separate, auditable general-ledger layer, not certified financial statements.
CREATE TABLE IF NOT EXISTS gl_accounts (
 id INTEGER PRIMARY KEY,
 code TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL,
 class TEXT NOT NULL CHECK(class IN ('asset','liability','equity','revenue','expense')),
 control TEXT NOT NULL DEFAULT '' CHECK(control IN ('','fund')),
 active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS gl_fund_accounts (
 fund_id INTEGER PRIMARY KEY REFERENCES funds(id),
 account_id INTEGER NOT NULL UNIQUE REFERENCES gl_accounts(id)
);
CREATE TABLE IF NOT EXISTS gl_journals (
 id INTEGER PRIMARY KEY,
 entry_date TEXT NOT NULL,
 memo TEXT NOT NULL,
 origin TEXT NOT NULL CHECK(origin IN ('voucher','payroll','allocation','manual','manual_reversal')),
 source_id INTEGER,
 reversal_of_id INTEGER REFERENCES gl_journals(id),
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','posted','rejected')),
 created_by INTEGER NOT NULL REFERENCES users(id),
 created_at TEXT NOT NULL,
 reviewed_by INTEGER REFERENCES users(id),
 reviewed_at TEXT,
 review_reason TEXT NOT NULL DEFAULT '',
 UNIQUE(origin,source_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_gl_one_active_reversal
 ON gl_journals(reversal_of_id) WHERE reversal_of_id IS NOT NULL AND status != 'rejected';
CREATE INDEX IF NOT EXISTS idx_gl_journals_date ON gl_journals(entry_date,status);
CREATE TABLE IF NOT EXISTS gl_lines (
 id INTEGER PRIMARY KEY,
 journal_id INTEGER NOT NULL REFERENCES gl_journals(id),
 account_id INTEGER NOT NULL REFERENCES gl_accounts(id),
 department_id INTEGER REFERENCES departments(id),
 debit_piasters INTEGER NOT NULL DEFAULT 0 CHECK(debit_piasters>=0),
 credit_piasters INTEGER NOT NULL DEFAULT 0 CHECK(credit_piasters>=0),
 CHECK((debit_piasters>0 AND credit_piasters=0) OR (credit_piasters>0 AND debit_piasters=0))
);
CREATE INDEX IF NOT EXISTS idx_gl_lines_account ON gl_lines(account_id,journal_id);
-- A posted journal must balance; postings and their lines are immutable even from direct SQL.
CREATE TRIGGER IF NOT EXISTS gl_insert_pending_only BEFORE INSERT ON gl_journals
 WHEN NEW.status!='pending' BEGIN SELECT RAISE(ABORT,'New GL journal must start pending'); END;
CREATE TRIGGER IF NOT EXISTS gl_must_balance BEFORE UPDATE OF status ON gl_journals
 WHEN NEW.status='posted' AND (
   (SELECT COUNT(*) FROM gl_lines WHERE journal_id=OLD.id)<2 OR
   (SELECT COALESCE(SUM(debit_piasters-credit_piasters),0) FROM gl_lines WHERE journal_id=OLD.id)!=0
 )
 BEGIN SELECT RAISE(ABORT,'Unbalanced journal'); END;
CREATE TRIGGER IF NOT EXISTS gl_no_posted_journal_update BEFORE UPDATE ON gl_journals
 WHEN OLD.status='posted' BEGIN SELECT RAISE(ABORT,'Posted journal is immutable'); END;
CREATE TRIGGER IF NOT EXISTS gl_no_posted_journal_delete BEFORE DELETE ON gl_journals
 WHEN OLD.status='posted' BEGIN SELECT RAISE(ABORT,'Posted journal is immutable'); END;
CREATE TRIGGER IF NOT EXISTS gl_no_posted_line_insert BEFORE INSERT ON gl_lines
 WHEN (SELECT status FROM gl_journals WHERE id=NEW.journal_id)!='pending'
 BEGIN SELECT RAISE(ABORT,'Journal lines are frozen'); END;
CREATE TRIGGER IF NOT EXISTS gl_no_posted_line_update BEFORE UPDATE ON gl_lines
 WHEN (SELECT status FROM gl_journals WHERE id=OLD.journal_id)!='pending'
 BEGIN SELECT RAISE(ABORT,'Journal lines are frozen'); END;
CREATE TRIGGER IF NOT EXISTS gl_no_posted_line_delete BEFORE DELETE ON gl_lines
 WHEN (SELECT status FROM gl_journals WHERE id=OLD.journal_id)!='pending'
 BEGIN SELECT RAISE(ABORT,'Journal lines are frozen'); END;

-- V8.1A: patient finance and dual cashier stations; DRAFT billing ONLY.
-- No bill here is a tax invoice, earned revenue, receivable, or cash collection yet.
CREATE TABLE IF NOT EXISTS billing_points (
 id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL UNIQUE, kind TEXT NOT NULL CHECK(kind IN ('external','internal')),
 fund_id INTEGER UNIQUE REFERENCES funds(id), active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS billing_point_access (
 point_id INTEGER NOT NULL REFERENCES billing_points(id),
 user_id INTEGER NOT NULL REFERENCES users(id),
 assigned_by INTEGER NOT NULL REFERENCES users(id), assigned_at TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(point_id,user_id)
);
CREATE TABLE IF NOT EXISTS billing_patients (
 id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE,
 display_name TEXT NOT NULL CHECK(length(display_name) BETWEEN 3 AND 120),
 created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS billing_cases (
 id INTEGER PRIMARY KEY, case_no TEXT NOT NULL UNIQUE,
 patient_id INTEGER NOT NULL REFERENCES billing_patients(id),
 kind TEXT NOT NULL CHECK(kind IN ('outpatient','inpatient','operation','nicu')),
 default_point_id INTEGER NOT NULL REFERENCES billing_points(id),
 business_date TEXT NOT NULL, opened_by INTEGER NOT NULL REFERENCES users(id),
 opened_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','closed')),
 notes TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_billing_cases_patient ON billing_cases(patient_id,id);
CREATE INDEX IF NOT EXISTS idx_billing_cases_point ON billing_cases(default_point_id,business_date);
CREATE TABLE IF NOT EXISTS billing_services (
 id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL, department_id INTEGER NOT NULL REFERENCES departments(id),
 suggested_point TEXT NOT NULL CHECK(suggested_point IN ('external','internal','either')),
 active INTEGER NOT NULL DEFAULT 1, created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS billing_service_prices (
 id INTEGER PRIMARY KEY, service_id INTEGER NOT NULL REFERENCES billing_services(id),
 valid_from TEXT NOT NULL, price_piasters INTEGER NOT NULL CHECK(price_piasters>0),
 created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
 UNIQUE(service_id,valid_from)
);
CREATE TABLE IF NOT EXISTS billing_case_lines (
 id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES billing_cases(id),
 service_id INTEGER NOT NULL REFERENCES billing_services(id),
 price_version_id INTEGER NOT NULL REFERENCES billing_service_prices(id),
 service_name_snapshot TEXT NOT NULL, department_id INTEGER NOT NULL REFERENCES departments(id),
 unit_price_piasters INTEGER NOT NULL CHECK(unit_price_piasters>0),
 quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 10000),
 state TEXT NOT NULL DEFAULT 'ordered' CHECK(state IN ('ordered','fulfilled','cancelled')),
 added_by INTEGER NOT NULL REFERENCES users(id), added_at TEXT NOT NULL,
 service_date TEXT,
 fulfilled_by INTEGER REFERENCES users(id), fulfilled_at TEXT, cancelled_by INTEGER REFERENCES users(id),
 cancelled_at TEXT, reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_billing_lines_case ON billing_case_lines(case_id,state,id);
CREATE TABLE IF NOT EXISTS billing_invoice_drafts (
 id INTEGER PRIMARY KEY, draft_no TEXT NOT NULL UNIQUE,
 case_id INTEGER NOT NULL REFERENCES billing_cases(id),
 point_id INTEGER NOT NULL REFERENCES billing_points(id),
 total_piasters INTEGER NOT NULL CHECK(total_piasters>0),
 created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft'))
);
CREATE TABLE IF NOT EXISTS billing_invoice_draft_lines (
 id INTEGER PRIMARY KEY, draft_id INTEGER NOT NULL REFERENCES billing_invoice_drafts(id),
 case_line_id INTEGER NOT NULL UNIQUE REFERENCES billing_case_lines(id),
 unit_price_piasters INTEGER NOT NULL CHECK(unit_price_piasters>0),
 quantity INTEGER NOT NULL CHECK(quantity>0),
 total_piasters INTEGER NOT NULL CHECK(total_piasters>0)
);
-- Request token prevents double submission on retry; fingerprint detects key misuse.
CREATE TABLE IF NOT EXISTS billing_request_keys (
 request_id TEXT PRIMARY KEY, action TEXT NOT NULL,
 entity_id INTEGER NOT NULL, payload_hash TEXT NOT NULL,
 created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL
);


-- V8.1B: one immutable issued invoice per draft. No backdated automatic migration.
CREATE TABLE IF NOT EXISTS billing_invoices (
 id INTEGER PRIMARY KEY, invoice_no TEXT NOT NULL UNIQUE,
 draft_id INTEGER NOT NULL UNIQUE REFERENCES billing_invoice_drafts(id),
 case_id INTEGER NOT NULL REFERENCES billing_cases(id),
 issued_date TEXT NOT NULL, total_piasters INTEGER NOT NULL CHECK(total_piasters>0),
 issued_by INTEGER NOT NULL REFERENCES users(id), issued_at TEXT NOT NULL,
 journal_id INTEGER NOT NULL UNIQUE REFERENCES gl_journals(id),
 status TEXT NOT NULL DEFAULT 'issued' CHECK(status='issued')
);
CREATE INDEX IF NOT EXISTS idx_billing_invoices_case ON billing_invoices(case_id,issued_date);
-- Non-cash settlement amounts reside in designated clearing wallets, NEVER in a bank account pre-settlement.
CREATE TABLE IF NOT EXISTS billing_payment_channels (
 method TEXT PRIMARY KEY CHECK(method IN ('card','instapay','wallet','transfer')),
 fund_id INTEGER NOT NULL UNIQUE REFERENCES funds(id),
 configured_by INTEGER NOT NULL REFERENCES users(id), configured_at TEXT NOT NULL
);
-- A collection is one cashier action; splits are separate immutable vouchers and GL entries.
CREATE TABLE IF NOT EXISTS billing_collections (
 id INTEGER PRIMARY KEY, collection_no TEXT NOT NULL UNIQUE,
 case_id INTEGER NOT NULL REFERENCES billing_cases(id),
 invoice_id INTEGER REFERENCES billing_invoices(id),
 point_id INTEGER NOT NULL REFERENCES billing_points(id),
 shift_session_id INTEGER NOT NULL REFERENCES shift_sessions(id),
 kind TEXT NOT NULL CHECK(kind IN ('advance','invoice')),
 business_date TEXT NOT NULL, total_piasters INTEGER NOT NULL CHECK(total_piasters>0),
 created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
 CHECK((kind='invoice' AND invoice_id IS NOT NULL) OR (kind='advance' AND invoice_id IS NULL))
);
CREATE TABLE IF NOT EXISTS billing_payment_parts (
 id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL REFERENCES billing_collections(id),
 method TEXT NOT NULL CHECK(method IN ('cash','card','instapay','wallet','transfer')),
 fund_id INTEGER NOT NULL REFERENCES funds(id), voucher_id INTEGER NOT NULL UNIQUE REFERENCES vouchers(id),
 amount_piasters INTEGER NOT NULL CHECK(amount_piasters>0)
);
CREATE INDEX IF NOT EXISTS idx_billing_payments_collection ON billing_payment_parts(collection_id);
-- Applying an advance only transfers liabilities to receivables, never moves cash again.
CREATE TABLE IF NOT EXISTS billing_advance_allocations (
 id INTEGER PRIMARY KEY,
 case_id INTEGER NOT NULL REFERENCES billing_cases(id),
 invoice_id INTEGER NOT NULL REFERENCES billing_invoices(id),
 amount_piasters INTEGER NOT NULL CHECK(amount_piasters>0),
 allocated_by INTEGER NOT NULL REFERENCES users(id), allocated_at TEXT NOT NULL,
 journal_id INTEGER NOT NULL UNIQUE REFERENCES gl_journals(id)
);
CREATE INDEX IF NOT EXISTS idx_billing_alloc_case ON billing_advance_allocations(case_id,invoice_id);
-- Posted draft details are financial evidence. SQL changes to billed lines are forbidden.
CREATE TRIGGER IF NOT EXISTS billing_no_issued_draftline_update BEFORE UPDATE ON billing_invoice_draft_lines
 WHEN EXISTS (SELECT 1 FROM billing_invoices WHERE draft_id=OLD.draft_id)
 BEGIN SELECT RAISE(ABORT,'Issued invoice lines are immutable'); END;
CREATE TRIGGER IF NOT EXISTS billing_no_issued_draftline_delete BEFORE DELETE ON billing_invoice_draft_lines
 WHEN EXISTS (SELECT 1 FROM billing_invoices WHERE draft_id=OLD.draft_id)
 BEGIN SELECT RAISE(ABORT,'Issued invoice lines are immutable'); END;
CREATE TRIGGER IF NOT EXISTS billing_no_issued_draftline_insert BEFORE INSERT ON billing_invoice_draft_lines
 WHEN EXISTS (SELECT 1 FROM billing_invoices WHERE draft_id=NEW.draft_id)
 BEGIN SELECT RAISE(ABORT,'Issued invoice lines are immutable'); END;
CREATE TRIGGER IF NOT EXISTS billing_no_invoice_mutation BEFORE UPDATE ON billing_invoices
 BEGIN SELECT RAISE(ABORT,'Issued invoice is immutable'); END;
CREATE TRIGGER IF NOT EXISTS billing_no_invoice_delete BEFORE DELETE ON billing_invoices
 BEGIN SELECT RAISE(ABORT,'Issued invoice is immutable'); END;
CREATE TRIGGER IF NOT EXISTS billing_no_collection_mutation BEFORE UPDATE ON billing_collections
 BEGIN SELECT RAISE(ABORT,'Posted collection is immutable'); END;
CREATE TRIGGER IF NOT EXISTS billing_no_collection_delete BEFORE DELETE ON billing_collections
 BEGIN SELECT RAISE(ABORT,'Posted collection is immutable'); END;
CREATE TRIGGER IF NOT EXISTS billing_no_payment_mutation BEFORE UPDATE ON billing_payment_parts
 BEGIN SELECT RAISE(ABORT,'Payment split is immutable'); END;
CREATE TRIGGER IF NOT EXISTS billing_no_payment_delete BEFORE DELETE ON billing_payment_parts
 BEGIN SELECT RAISE(ABORT,'Payment split is immutable'); END;
CREATE TRIGGER IF NOT EXISTS billing_no_allocation_mutation BEFORE UPDATE ON billing_advance_allocations
 BEGIN SELECT RAISE(ABORT,'Advance allocation is immutable'); END;
CREATE TRIGGER IF NOT EXISTS billing_no_allocation_delete BEFORE DELETE ON billing_advance_allocations
 BEGIN SELECT RAISE(ABORT,'Advance allocation is immutable'); END;

-- V8.1C: editable shift starts. Each window ends at the next configured start.
CREATE TABLE IF NOT EXISTS shift_templates (
 code TEXT PRIMARY KEY CHECK(code IN ('night','morning','evening')),
 start_minute INTEGER NOT NULL CHECK(start_minute BETWEEN 0 AND 1439)
);
-- Actual clock intervals are frozen at shift opening; old records stay unchanged.
CREATE TABLE IF NOT EXISTS shift_handoffs (
 id INTEGER PRIMARY KEY, shift_session_id INTEGER NOT NULL REFERENCES shift_sessions(id),
 count_version INTEGER NOT NULL CHECK(count_version > 0),
 received_by INTEGER NOT NULL REFERENCES users(id), received_at TEXT NOT NULL,
 counted_piasters INTEGER NOT NULL CHECK(counted_piasters >= 0),
 decision TEXT NOT NULL CHECK(decision IN ('accepted','rejected')),
 note TEXT NOT NULL DEFAULT '',
 UNIQUE(shift_session_id,count_version)
);
CREATE INDEX IF NOT EXISTS idx_handoffs_shift ON shift_handoffs(shift_session_id,count_version);
CREATE TABLE IF NOT EXISTS shift_settings (
 id INTEGER PRIMARY KEY CHECK(id=1), enforce_clock INTEGER NOT NULL DEFAULT 0 CHECK(enforce_clock IN (0,1))
);

-- V8.1C: independently approved invoice credit notes and patient refunds.
-- A credit note reverses earned revenue and offsets AR or creates refundable liability.
-- Actual cash leaves the till only after reviewer approval and cashier execution.
CREATE TABLE IF NOT EXISTS billing_credit_requests (
 id INTEGER PRIMARY KEY, credit_no TEXT NOT NULL UNIQUE,
 invoice_id INTEGER NOT NULL REFERENCES billing_invoices(id),
 case_id INTEGER NOT NULL REFERENCES billing_cases(id),
 amount_piasters INTEGER NOT NULL CHECK(amount_piasters>0),
 reason TEXT NOT NULL, requested_by INTEGER NOT NULL REFERENCES users(id),
 requested_at TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 decided_by INTEGER REFERENCES users(id), decided_at TEXT,
 decision_note TEXT NOT NULL DEFAULT '', journal_id INTEGER UNIQUE REFERENCES gl_journals(id)
);
CREATE INDEX IF NOT EXISTS idx_credit_requests_case ON billing_credit_requests(case_id,invoice_id,status);
CREATE TABLE IF NOT EXISTS billing_refund_requests (
 id INTEGER PRIMARY KEY, refund_no TEXT NOT NULL UNIQUE,
 case_id INTEGER NOT NULL REFERENCES billing_cases(id),
 point_id INTEGER NOT NULL REFERENCES billing_points(id),
 source TEXT NOT NULL CHECK(source IN ('credit','advance')),
 method TEXT NOT NULL CHECK(method IN ('cash','card','instapay','wallet','transfer')),
 amount_piasters INTEGER NOT NULL CHECK(amount_piasters>0),
 reason TEXT NOT NULL, requested_by INTEGER NOT NULL REFERENCES users(id),
 requested_at TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected','paid')),
 decided_by INTEGER REFERENCES users(id), decided_at TEXT,decision_note TEXT NOT NULL DEFAULT '',
 paid_by INTEGER REFERENCES users(id),paid_at TEXT,
 paid_shift_id INTEGER REFERENCES shift_sessions(id),
 voucher_id INTEGER UNIQUE REFERENCES vouchers(id)
);
CREATE INDEX IF NOT EXISTS idx_refund_requests_case ON billing_refund_requests(case_id,status);
CREATE TRIGGER IF NOT EXISTS billing_credit_immutable BEFORE UPDATE ON billing_credit_requests
 WHEN OLD.status IN ('approved','rejected')
 BEGIN SELECT RAISE(ABORT,'Approved credit note is immutable'); END;
CREATE TRIGGER IF NOT EXISTS billing_credit_no_delete BEFORE DELETE ON billing_credit_requests
 BEGIN SELECT RAISE(ABORT,'Credit request must remain in audit trail'); END;
CREATE TRIGGER IF NOT EXISTS billing_refund_immutable BEFORE UPDATE ON billing_refund_requests
 WHEN OLD.status IN ('paid','rejected')
 BEGIN SELECT RAISE(ABORT,'Paid/refused refund request is immutable'); END;
CREATE TRIGGER IF NOT EXISTS billing_refund_no_delete BEFORE DELETE ON billing_refund_requests
 BEGIN SELECT RAISE(ABORT,'Refund request must remain in audit trail'); END;

-- V8.1E P4: cash the employee actually deposited to settle an independently approved shortage.
-- The source case must have been independently approved and debited to GL 1190.
CREATE TABLE IF NOT EXISTS cashier_shortage_repayments (
 id INTEGER PRIMARY KEY,
 variance_case_id INTEGER NOT NULL REFERENCES shift_variance_cases(id),
 central_shift_id INTEGER NOT NULL REFERENCES shift_sessions(id),
 payer_user_id INTEGER NOT NULL REFERENCES users(id),
 amount_piasters INTEGER NOT NULL CHECK(amount_piasters>0),
 receipt_key TEXT NOT NULL UNIQUE,
 evidence_note TEXT NOT NULL,
 recorded_by INTEGER NOT NULL REFERENCES users(id), recorded_at TEXT NOT NULL,
 voucher_id INTEGER NOT NULL UNIQUE REFERENCES vouchers(id)
);
CREATE INDEX IF NOT EXISTS idx_shortage_repayments_case ON cashier_shortage_repayments(variance_case_id);
CREATE TRIGGER IF NOT EXISTS shortage_repayments_no_update BEFORE UPDATE ON cashier_shortage_repayments
 BEGIN SELECT RAISE(ABORT,'Shortage repayment is immutable'); END;
CREATE TRIGGER IF NOT EXISTS shortage_repayments_no_delete BEFORE DELETE ON cashier_shortage_repayments
 BEGIN SELECT RAISE(ABORT,'Shortage repayment must remain in audit trail'); END;

-- V8.1E: versioned expected shifts (immutable by date; not financial postings).
CREATE TABLE IF NOT EXISTS cashier_schedule_versions (
 id INTEGER PRIMARY KEY, point_id INTEGER NOT NULL REFERENCES billing_points(id),
 starts_on TEXT NOT NULL, operating_days TEXT NOT NULL DEFAULT '0123456', created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL,
 reason TEXT NOT NULL DEFAULT '', UNIQUE(point_id,starts_on)
);
CREATE TABLE IF NOT EXISTS cashier_schedule_slots (
 id INTEGER PRIMARY KEY,version_id INTEGER NOT NULL REFERENCES cashier_schedule_versions(id),
 code TEXT NOT NULL,name TEXT NOT NULL,start_minute INTEGER NOT NULL CHECK(start_minute BETWEEN 0 AND 1439),
 UNIQUE(version_id,code), UNIQUE(version_id,start_minute)
);
CREATE TABLE IF NOT EXISTS cashier_point_lifecycle (
 point_id INTEGER NOT NULL REFERENCES billing_points(id), starts_on TEXT NOT NULL,
 enabled INTEGER NOT NULL CHECK(enabled IN (0,1)), PRIMARY KEY(point_id,starts_on)
);
CREATE TABLE IF NOT EXISTS cashier_point_policies (
 point_id INTEGER PRIMARY KEY REFERENCES billing_points(id),
 grace_minutes INTEGER NOT NULL DEFAULT 120 CHECK(grace_minutes BETWEEN 0 AND 10080),
 require_shift_image INTEGER NOT NULL DEFAULT 0 CHECK(require_shift_image IN (0,1)),
 require_envelope_image INTEGER NOT NULL DEFAULT 0 CHECK(require_envelope_image IN (0,1))
);

-- V8.1E: immutable records of every submitted count and independently received cash.
CREATE TABLE IF NOT EXISTS cashier_count_history (
 id INTEGER PRIMARY KEY,shift_session_id INTEGER NOT NULL REFERENCES shift_sessions(id),
 count_version INTEGER NOT NULL,actor_id INTEGER NOT NULL REFERENCES users(id),
 event TEXT NOT NULL CHECK(event IN ('submit','recount_requested')),
 counted_piasters INTEGER,expected_piasters INTEGER,variance_piasters INTEGER,
 reason TEXT NOT NULL DEFAULT '',recorded_at TEXT NOT NULL,
 UNIQUE(shift_session_id,count_version,event)
);
CREATE TRIGGER IF NOT EXISTS cashier_count_history_immutable_update BEFORE UPDATE ON cashier_count_history
 BEGIN SELECT RAISE(ABORT,'Cash count audit versions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS cashier_count_history_immutable_delete BEFORE DELETE ON cashier_count_history
 BEGIN SELECT RAISE(ABORT,'Cash count audit versions are immutable'); END;
-- Granting an accounting reviewer a sensitive approval is a separate owner decision.
CREATE TABLE IF NOT EXISTS cashier_variance_permissions (
 user_id INTEGER PRIMARY KEY REFERENCES users(id),can_approve INTEGER NOT NULL DEFAULT 0 CHECK(can_approve IN (0,1)),
 changed_by INTEGER NOT NULL REFERENCES users(id),changed_at TEXT NOT NULL
);

-- A physical, independently acknowledged cashier deposit is not patient revenue.
-- Source movement is intentionally not attached to a COUNTED shift: it happened
-- after its sealed count. Target movement belongs to the open central-treasury shift.
CREATE TABLE IF NOT EXISTS cashier_treasury_transfers (
 id INTEGER PRIMARY KEY,
 source_shift_id INTEGER NOT NULL REFERENCES shift_sessions(id),
 target_shift_id INTEGER NOT NULL REFERENCES shift_sessions(id),
 handoff_id INTEGER NOT NULL REFERENCES shift_handoffs(id),
 amount_piasters INTEGER NOT NULL CHECK(amount_piasters>0),
 voucher_id INTEGER NOT NULL UNIQUE REFERENCES vouchers(id),
 received_by INTEGER NOT NULL REFERENCES users(id), received_at TEXT NOT NULL,
 note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_cashier_treasury_source ON cashier_treasury_transfers(source_shift_id);
CREATE TRIGGER IF NOT EXISTS cashier_treasury_transfer_no_update BEFORE UPDATE ON cashier_treasury_transfers
 BEGIN SELECT RAISE(ABORT,'Treasury cash receipt is immutable'); END;
CREATE TRIGGER IF NOT EXISTS cashier_treasury_transfer_no_delete BEFORE DELETE ON cashier_treasury_transfers
 BEGIN SELECT RAISE(ABORT,'Treasury cash receipt is immutable'); END;

-- Receipt/report images are evidence, not a second transaction register.
CREATE TABLE IF NOT EXISTS cashier_shift_attachments (
 id INTEGER PRIMARY KEY,shift_session_id INTEGER NOT NULL REFERENCES shift_sessions(id),
 kind TEXT NOT NULL CHECK(kind IN ('report','envelope')),
 file_name TEXT NOT NULL, media_type TEXT NOT NULL, file_size INTEGER NOT NULL,
 sha256 TEXT NOT NULL, content BLOB NOT NULL,
 uploaded_by INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL,
 UNIQUE(shift_session_id,kind,sha256)
);
CREATE TRIGGER IF NOT EXISTS cashier_shift_attachment_no_update BEFORE UPDATE ON cashier_shift_attachments
 BEGIN SELECT RAISE(ABORT,'Shift evidence is immutable'); END;
CREATE TRIGGER IF NOT EXISTS cashier_shift_attachment_no_delete BEFORE DELETE ON cashier_shift_attachments
 BEGIN SELECT RAISE(ABORT,'Shift evidence is immutable'); END;

-- Effective permission for a clerk per cashier station; no row means legacy point-wide access.
-- A saved empty rule means no shifts permitted. All permission changes are audit-logged.
CREATE TABLE IF NOT EXISTS cashier_shift_staff_rules (
 point_id INTEGER NOT NULL REFERENCES billing_points(id),
 user_id INTEGER NOT NULL REFERENCES users(id),
 allowed_codes TEXT NOT NULL DEFAULT '',
 changed_by INTEGER NOT NULL REFERENCES users(id),
 changed_at TEXT NOT NULL,
 PRIMARY KEY(point_id,user_id)
);

-- V8.1E-P5: correction reports only. Triage never posts money.
CREATE TABLE IF NOT EXISTS financial_correction_tickets (
 id INTEGER PRIMARY KEY,
 request_key TEXT NOT NULL UNIQUE,
 request_hash TEXT NOT NULL,
 source_type TEXT NOT NULL CHECK(source_type IN ('invoice','collection','voucher','shift')),
 source_id INTEGER NOT NULL CHECK(source_id>0),
 source_ref TEXT NOT NULL,
 point_id INTEGER REFERENCES billing_points(id),
 issue_type TEXT NOT NULL CHECK(issue_type IN ('wrong_patient','wrong_service','wrong_amount','wrong_method','duplicate','wrong_cash_fund','missing_document','other')),
 reason TEXT NOT NULL CHECK(length(reason)>=20),
 proposed_resolution TEXT NOT NULL CHECK(length(proposed_resolution)>=12),
 source_snapshot_json TEXT NOT NULL,
 opened_by INTEGER NOT NULL REFERENCES users(id),
 opened_at TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','needs_evidence','triaged','dismissed')),
 reviewed_by INTEGER REFERENCES users(id),
 reviewed_at TEXT,
 review_note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_correction_status ON financial_correction_tickets(status,opened_at);
CREATE INDEX IF NOT EXISTS idx_correction_source ON financial_correction_tickets(source_type,source_id);
CREATE TRIGGER IF NOT EXISTS correction_no_source_edit BEFORE UPDATE OF
 request_key,request_hash,source_type,source_id,source_ref,point_id,issue_type,reason,proposed_resolution,
 source_snapshot_json,opened_by,opened_at ON financial_correction_tickets
 BEGIN SELECT RAISE(ABORT,'Correction origin is immutable'); END;
CREATE TRIGGER IF NOT EXISTS correction_no_delete BEFORE DELETE ON financial_correction_tickets
 BEGIN SELECT RAISE(ABORT,'Correction ticket must not be deleted'); END;
CREATE TABLE IF NOT EXISTS financial_correction_events (
 id INTEGER PRIMARY KEY,
 ticket_id INTEGER NOT NULL REFERENCES financial_correction_tickets(id),
 action TEXT NOT NULL CHECK(action IN ('opened','note','needs_evidence','triaged','dismissed')),
 note TEXT NOT NULL,
 actor_id INTEGER NOT NULL REFERENCES users(id),
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_correction_events_ticket ON financial_correction_events(ticket_id,id);
CREATE TRIGGER IF NOT EXISTS correction_event_immutable_update BEFORE UPDATE ON financial_correction_events
 BEGIN SELECT RAISE(ABORT,'Correction history cannot change'); END;
CREATE TRIGGER IF NOT EXISTS correction_event_immutable_delete BEFORE DELETE ON financial_correction_events
 BEGIN SELECT RAISE(ABORT,'Correction history cannot be deleted'); END;

-- V8.1E-G2G: independently reviewed reduction of an ISSUED, wholly unpaid
-- invoice. No change to the original invoice, old shifts, cash or closed periods.
CREATE TABLE IF NOT EXISTS financial_invoice_credit_fixes (
 id INTEGER PRIMARY KEY,
 ticket_id INTEGER NOT NULL UNIQUE REFERENCES financial_correction_tickets(id),
 invoice_id INTEGER NOT NULL UNIQUE REFERENCES billing_invoices(id),
 credit_id INTEGER NOT NULL UNIQUE REFERENCES billing_credit_requests(id),
 journal_id INTEGER NOT NULL UNIQUE REFERENCES gl_journals(id),
 request_key TEXT NOT NULL UNIQUE,
 request_hash TEXT NOT NULL,
 original_due_piasters INTEGER NOT NULL CHECK(original_due_piasters>0),
 amount_piasters INTEGER NOT NULL CHECK(amount_piasters>0),
 new_due_piasters INTEGER NOT NULL CHECK(new_due_piasters>=0),
 evidence_reference TEXT NOT NULL CHECK(length(evidence_reference)>=8),
 decision_note TEXT NOT NULL CHECK(length(decision_note)>=16),
 approved_by INTEGER NOT NULL REFERENCES users(id),
 approved_at TEXT NOT NULL,
 CHECK(original_due_piasters=amount_piasters+new_due_piasters)
);
CREATE TRIGGER IF NOT EXISTS financial_invoice_fix_no_update BEFORE UPDATE ON financial_invoice_credit_fixes
 BEGIN SELECT RAISE(ABORT,'Posted correction is immutable'); END;
CREATE TRIGGER IF NOT EXISTS financial_invoice_fix_no_delete BEFORE DELETE ON financial_invoice_credit_fixes
 BEGIN SELECT RAISE(ABORT,'Posted correction must remain in audit trail'); END;

-- V8.1E-G2H: full reassignment of one posted invoice receipt to a different
-- patient's issued invoice. The ORIGINAL receipt, its split, voucher, shift,
-- cash movement and GL stay immutable; only the subsidiary AR allocation moves.
CREATE TABLE IF NOT EXISTS financial_collection_reallocations (
 id INTEGER PRIMARY KEY,
 ticket_id INTEGER NOT NULL UNIQUE REFERENCES financial_correction_tickets(id),
 collection_id INTEGER NOT NULL UNIQUE REFERENCES billing_collections(id),
 from_invoice_id INTEGER NOT NULL REFERENCES billing_invoices(id),
 to_invoice_id INTEGER NOT NULL REFERENCES billing_invoices(id),
 from_case_id INTEGER NOT NULL REFERENCES billing_cases(id),
 to_case_id INTEGER NOT NULL REFERENCES billing_cases(id),
 amount_piasters INTEGER NOT NULL CHECK(amount_piasters>0),
 before_source_due_piasters INTEGER NOT NULL CHECK(before_source_due_piasters>=0),
 after_source_due_piasters INTEGER NOT NULL CHECK(after_source_due_piasters>=0),
 before_target_due_piasters INTEGER NOT NULL CHECK(before_target_due_piasters>0),
 after_target_due_piasters INTEGER NOT NULL CHECK(after_target_due_piasters>=0),
 effective_date TEXT NOT NULL,
 evidence_reference TEXT NOT NULL CHECK(length(evidence_reference)>=8),
 decision_note TEXT NOT NULL CHECK(length(decision_note)>=16),
 request_key TEXT NOT NULL UNIQUE,
 request_hash TEXT NOT NULL,
 approved_by INTEGER NOT NULL REFERENCES users(id),
 approved_at TEXT NOT NULL,
 CHECK(from_invoice_id<>to_invoice_id AND from_case_id<>to_case_id),
 CHECK(after_source_due_piasters=before_source_due_piasters+amount_piasters),
 CHECK(before_target_due_piasters=after_target_due_piasters+amount_piasters)
);
CREATE INDEX IF NOT EXISTS idx_collection_realloc_to_invoice
 ON financial_collection_reallocations(to_invoice_id);
CREATE INDEX IF NOT EXISTS idx_collection_realloc_to_case
 ON financial_collection_reallocations(to_case_id);
CREATE TRIGGER IF NOT EXISTS financial_collection_realloc_no_update BEFORE UPDATE
 ON financial_collection_reallocations
 BEGIN SELECT RAISE(ABORT,'Receipt allocation is immutable'); END;
CREATE TRIGGER IF NOT EXISTS financial_collection_realloc_no_delete BEFORE DELETE
 ON financial_collection_reallocations
 BEGIN SELECT RAISE(ABORT,'Receipt allocation must remain in audit trail'); END;


-- V8.1E G2A: outage/absence recovery intake is NON-POSTING by design.
-- The cash envelope, a receipt already posted, and a newly entered patient receipt
-- are three different things. No trigger here may book a fund or GL movement.
CREATE TABLE IF NOT EXISTS late_entry_incidents (
 id INTEGER PRIMARY KEY,
 request_key TEXT NOT NULL UNIQUE,
 request_hash TEXT NOT NULL,
 point_id INTEGER NOT NULL REFERENCES billing_points(id),
 business_date TEXT NOT NULL,
 shift_code TEXT NOT NULL,
 incident_reason TEXT NOT NULL CHECK(incident_reason IN ('outage','absence','staff_unavailable','other')),
 custodian_name TEXT NOT NULL,
 cash_location TEXT NOT NULL CHECK(cash_location IN ('drawer','envelope','main_safe','other')),
 counted_cash_piasters INTEGER CHECK(counted_cash_piasters IS NULL OR counted_cash_piasters>=0),
 source_register_ref TEXT NOT NULL DEFAULT '',
 note TEXT NOT NULL,
 opened_by INTEGER NOT NULL REFERENCES users(id), opened_at TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','submitted','needs_evidence','triaged','resolved')),
 reviewed_by INTEGER REFERENCES users(id), reviewed_at TEXT, review_note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_late_incident_day ON late_entry_incidents(business_date,status,point_id);
CREATE TRIGGER IF NOT EXISTS late_incident_origin_immutable BEFORE UPDATE OF
 request_key,request_hash,point_id,business_date,shift_code,incident_reason,
 custodian_name,cash_location,counted_cash_piasters,source_register_ref,note,opened_by,opened_at
 ON late_entry_incidents BEGIN SELECT RAISE(ABORT,'Late incident origin immutable'); END;
CREATE TRIGGER IF NOT EXISTS late_incident_no_delete BEFORE DELETE ON late_entry_incidents
 BEGIN SELECT RAISE(ABORT,'Late incident must not be deleted'); END;
CREATE TABLE IF NOT EXISTS late_entry_documents (
 id INTEGER PRIMARY KEY,
 incident_id INTEGER NOT NULL REFERENCES late_entry_incidents(id),
 point_id INTEGER NOT NULL REFERENCES billing_points(id), business_date TEXT NOT NULL,
 paper_ref TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('patient_receipt','expense','transfer')),
 method TEXT NOT NULL CHECK(method IN ('cash','card','instapay','wallet','transfer','mixed')),
 amount_piasters INTEGER NOT NULL CHECK(amount_piasters>0),
 note TEXT NOT NULL DEFAULT '',
 linked_kind TEXT CHECK(linked_kind IN ('collection','voucher')),
 linked_id INTEGER CHECK(linked_id>0),
 linked_by INTEGER REFERENCES users(id), linked_at TEXT,
 created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
 UNIQUE(point_id,business_date,paper_ref),
 CHECK((linked_kind IS NULL AND linked_id IS NULL AND linked_by IS NULL AND linked_at IS NULL)
    OR (linked_kind IS NOT NULL AND linked_id IS NOT NULL AND linked_by IS NOT NULL AND linked_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_late_document_financial_link
 ON late_entry_documents(linked_kind,linked_id) WHERE linked_kind IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_late_documents_incident ON late_entry_documents(incident_id);
CREATE TRIGGER IF NOT EXISTS late_document_no_origin_edit BEFORE UPDATE OF
 incident_id,point_id,business_date,paper_ref,kind,method,amount_piasters,note,created_by,created_at
 ON late_entry_documents BEGIN SELECT RAISE(ABORT,'Late document origin immutable'); END;
CREATE TRIGGER IF NOT EXISTS late_document_no_delete BEFORE DELETE ON late_entry_documents
 BEGIN SELECT RAISE(ABORT,'Late document cannot be deleted'); END;
CREATE TABLE IF NOT EXISTS late_entry_events (
 id INTEGER PRIMARY KEY, incident_id INTEGER NOT NULL REFERENCES late_entry_incidents(id),
 action TEXT NOT NULL, note TEXT NOT NULL,
 actor_id INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_late_events_incident ON late_entry_events(incident_id,id);
CREATE TRIGGER IF NOT EXISTS late_event_no_update BEFORE UPDATE ON late_entry_events
 BEGIN SELECT RAISE(ABORT,'Late event immutable'); END;
CREATE TRIGGER IF NOT EXISTS late_event_no_delete BEFORE DELETE ON late_entry_events
 BEGIN SELECT RAISE(ABORT,'Late event immutable'); END;
CREATE TABLE IF NOT EXISTS late_entry_evidence (
 id INTEGER PRIMARY KEY, incident_id INTEGER NOT NULL REFERENCES late_entry_incidents(id),
 filename TEXT NOT NULL, mime TEXT NOT NULL,
 sha256 TEXT NOT NULL, content BLOB NOT NULL,
 uploaded_by INTEGER NOT NULL REFERENCES users(id),uploaded_at TEXT NOT NULL,
 UNIQUE(incident_id,sha256)
);
CREATE TRIGGER IF NOT EXISTS late_evidence_no_update BEFORE UPDATE ON late_entry_evidence
 BEGIN SELECT RAISE(ABORT,'Evidence immutable'); END;
CREATE TRIGGER IF NOT EXISTS late_evidence_no_delete BEFORE DELETE ON late_entry_evidence
 BEGIN SELECT RAISE(ABORT,'Evidence immutable'); END;


-- G2B: an independently triaged old paper receipt may introduce a CASE,
-- never a cash collection or backdated journal. An original paper document
-- must never spawn two case files silently.
CREATE TABLE IF NOT EXISTS billing_late_cases (
 case_id INTEGER PRIMARY KEY REFERENCES billing_cases(id),
 incident_id INTEGER NOT NULL REFERENCES late_entry_incidents(id),
 paper_document_id INTEGER NOT NULL UNIQUE REFERENCES late_entry_documents(id),
 original_business_date TEXT NOT NULL,
 recorded_accounting_date TEXT NOT NULL,
 recorded_by INTEGER NOT NULL REFERENCES users(id),
 recorded_at TEXT NOT NULL,
 authorization_note TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_billing_late_cases_incident ON billing_late_cases(incident_id);
CREATE TRIGGER IF NOT EXISTS billing_late_case_no_update BEFORE UPDATE ON billing_late_cases
 BEGIN SELECT RAISE(ABORT,'Late case provenance immutable'); END;
CREATE TRIGGER IF NOT EXISTS billing_late_case_no_delete BEFORE DELETE ON billing_late_cases
 BEGIN SELECT RAISE(ABORT,'Late case provenance immutable'); END;

-- G2C: allocate an ALREADY APPROVED unallocated-cash receipt to an issued
-- late invoice. This table and its GL journal do not book fund cash again.
-- One envelope voucher may cover multiple patient receipts of one incident.
CREATE TABLE IF NOT EXISTS late_cash_allocations (
 id INTEGER PRIMARY KEY,
 incident_id INTEGER NOT NULL REFERENCES late_entry_incidents(id),
 document_id INTEGER NOT NULL UNIQUE REFERENCES late_entry_documents(id),
 case_id INTEGER NOT NULL REFERENCES billing_cases(id),
 invoice_id INTEGER NOT NULL UNIQUE REFERENCES billing_invoices(id),
 voucher_id INTEGER NOT NULL REFERENCES vouchers(id),
 amount_piasters INTEGER NOT NULL CHECK(amount_piasters>0),
 journal_id INTEGER NOT NULL UNIQUE REFERENCES gl_journals(id),
 authorized_by INTEGER NOT NULL REFERENCES users(id),
 authorized_at TEXT NOT NULL,
 reason TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_late_cash_source ON late_cash_allocations(voucher_id,incident_id);
CREATE TRIGGER IF NOT EXISTS late_cash_allocation_no_edit BEFORE UPDATE ON late_cash_allocations
 BEGIN SELECT RAISE(ABORT,'Late cash allocation immutable'); END;
CREATE TRIGGER IF NOT EXISTS late_cash_allocation_no_delete BEFORE DELETE ON late_cash_allocations
 BEGIN SELECT RAISE(ABORT,'Late cash allocation immutable'); END;


-- G2D: One reviewed mixed envelope can settle historical patient receivables
-- and recognize PAPER-ONLY cash expenses from the gross receipts before the
-- NET physical cash reached the main safe. Never book a second cash movement.
-- Short/over-cash remains in separate GL suspense; never blame an employee by default.
CREATE TABLE IF NOT EXISTS late_mixed_clearances (
 id INTEGER PRIMARY KEY,
 incident_id INTEGER NOT NULL UNIQUE REFERENCES late_entry_incidents(id),
 voucher_id INTEGER NOT NULL UNIQUE REFERENCES vouchers(id),
 journal_id INTEGER NOT NULL UNIQUE REFERENCES gl_journals(id),
 request_key TEXT NOT NULL UNIQUE,
 request_hash TEXT NOT NULL,
 gross_receipts_piasters INTEGER NOT NULL CHECK(gross_receipts_piasters>0),
 expense_piasters INTEGER NOT NULL CHECK(expense_piasters>0),
 actual_cash_piasters INTEGER NOT NULL CHECK(actual_cash_piasters>0),
 variance_piasters INTEGER NOT NULL,
 approved_exception INTEGER NOT NULL CHECK(approved_exception IN (0,1)),
 authorized_by INTEGER NOT NULL REFERENCES users(id),authorized_at TEXT NOT NULL,
 reason TEXT NOT NULL CHECK(length(reason)>=24),
 CHECK(approved_exception=1 OR variance_piasters=0)
);
CREATE TABLE IF NOT EXISTS late_mixed_clearance_lines (
 id INTEGER PRIMARY KEY,
 clearance_id INTEGER NOT NULL REFERENCES late_mixed_clearances(id),
 document_id INTEGER NOT NULL UNIQUE REFERENCES late_entry_documents(id),
 line_kind TEXT NOT NULL CHECK(line_kind IN ('patient_receipt','expense')),
 invoice_id INTEGER UNIQUE REFERENCES billing_invoices(id),
 case_id INTEGER REFERENCES billing_cases(id),
 category_id INTEGER REFERENCES categories(id),
 department_id INTEGER REFERENCES departments(id),
 amount_piasters INTEGER NOT NULL CHECK(amount_piasters>0),
 CHECK((line_kind='patient_receipt' AND invoice_id IS NOT NULL AND case_id IS NOT NULL
    AND category_id IS NULL AND department_id IS NULL) OR
   (line_kind='expense' AND invoice_id IS NULL AND case_id IS NULL
    AND category_id IS NOT NULL AND department_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_late_mixed_line_clearance ON late_mixed_clearance_lines(clearance_id);
CREATE TRIGGER IF NOT EXISTS late_mixed_clearance_no_update BEFORE UPDATE ON late_mixed_clearances
 BEGIN SELECT RAISE(ABORT,'Mixed clearance immutable'); END;
CREATE TRIGGER IF NOT EXISTS late_mixed_clearance_no_delete BEFORE DELETE ON late_mixed_clearances
 BEGIN SELECT RAISE(ABORT,'Mixed clearance immutable'); END;
CREATE TRIGGER IF NOT EXISTS late_mixed_line_no_update BEFORE UPDATE ON late_mixed_clearance_lines
 BEGIN SELECT RAISE(ABORT,'Mixed clearance line immutable'); END;
CREATE TRIGGER IF NOT EXISTS late_mixed_line_no_delete BEFORE DELETE ON late_mixed_clearance_lines
 BEGIN SELECT RAISE(ABORT,'Mixed clearance line immutable'); END;


-- G2E: independent custody and approval of REAL money recovered after a
-- mixed-envelope shortage. The request is never a cash transaction until
-- independently confirmed and posted against the open main-safe shift.
CREATE TABLE IF NOT EXISTS late_mixed_shortage_recovery_requests (
 id INTEGER PRIMARY KEY,
 clearance_id INTEGER NOT NULL REFERENCES late_mixed_clearances(id),
 request_key TEXT NOT NULL UNIQUE,
 request_hash TEXT NOT NULL,
 receipt_ref TEXT NOT NULL COLLATE NOCASE UNIQUE,
 source_type TEXT NOT NULL CHECK(source_type IN ('employee_deposit','recovered_cash')),
 payer_name TEXT NOT NULL DEFAULT '',
 amount_piasters INTEGER NOT NULL CHECK(amount_piasters>0),
 evidence_note TEXT NOT NULL CHECK(length(evidence_note)>=24),
 central_shift_id INTEGER NOT NULL REFERENCES shift_sessions(id),
 main_fund_id INTEGER NOT NULL REFERENCES funds(id),
 proposed_by INTEGER NOT NULL REFERENCES users(id),
 proposed_at TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 decided_by INTEGER REFERENCES users(id),decided_at TEXT,
 decision_note TEXT NOT NULL DEFAULT '',
 voucher_id INTEGER UNIQUE REFERENCES vouchers(id),
 CHECK((status='pending' AND decided_by IS NULL AND voucher_id IS NULL) OR
       (status='rejected' AND decided_by IS NOT NULL AND voucher_id IS NULL) OR
       (status='approved' AND decided_by IS NOT NULL AND voucher_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_mixed_recovery_clearance ON late_mixed_shortage_recovery_requests(clearance_id,status);
CREATE TRIGGER IF NOT EXISTS mixed_recovery_request_immutable_fields BEFORE UPDATE OF
 clearance_id,request_key,request_hash,receipt_ref,source_type,payer_name,
 amount_piasters,evidence_note,central_shift_id,main_fund_id,proposed_by,proposed_at
 ON late_mixed_shortage_recovery_requests
 BEGIN SELECT RAISE(ABORT,'Recovery request provenance is immutable'); END;
CREATE TRIGGER IF NOT EXISTS mixed_recovery_final_locked BEFORE UPDATE ON late_mixed_shortage_recovery_requests
 WHEN OLD.status!='pending'
 BEGIN SELECT RAISE(ABORT,'Final recovery decision is immutable'); END;
CREATE TRIGGER IF NOT EXISTS mixed_recovery_no_delete BEFORE DELETE ON late_mixed_shortage_recovery_requests
 BEGIN SELECT RAISE(ABORT,'Recovery records cannot be deleted'); END;


-- G2F: verified refund of historical mixed-envelope surplus from account 2190.
-- No patient-income recognition; the ACTUAL current-safe payment is posted once
-- only when an independent reviewer confirms recipient and signed receipt.
CREATE TABLE IF NOT EXISTS late_mixed_overage_refund_requests (
 id INTEGER PRIMARY KEY,
 clearance_id INTEGER NOT NULL REFERENCES late_mixed_clearances(id),
 request_key TEXT NOT NULL UNIQUE,
 request_hash TEXT NOT NULL,
 claim_ref TEXT NOT NULL COLLATE NOCASE UNIQUE,
 claimant_name TEXT NOT NULL CHECK(length(claimant_name)>=3),
 evidence_id INTEGER NOT NULL REFERENCES late_entry_evidence(id),
 amount_piasters INTEGER NOT NULL CHECK(amount_piasters>0),
 evidence_note TEXT NOT NULL CHECK(length(evidence_note)>=32),
 central_shift_id INTEGER NOT NULL REFERENCES shift_sessions(id),
 main_fund_id INTEGER NOT NULL REFERENCES funds(id),
 proposed_by INTEGER NOT NULL REFERENCES users(id),
 proposed_at TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 decided_by INTEGER REFERENCES users(id),decided_at TEXT,
 decision_note TEXT NOT NULL DEFAULT '',
 receipt_evidence_id INTEGER UNIQUE REFERENCES late_entry_evidence(id),
 voucher_id INTEGER UNIQUE REFERENCES vouchers(id),
 CHECK((status='pending' AND decided_by IS NULL AND voucher_id IS NULL AND receipt_evidence_id IS NULL) OR
       (status='rejected' AND decided_by IS NOT NULL AND voucher_id IS NULL AND receipt_evidence_id IS NULL) OR
       (status='approved' AND decided_by IS NOT NULL AND voucher_id IS NOT NULL AND receipt_evidence_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_mixed_overage_clearance ON late_mixed_overage_refund_requests(clearance_id,status);
CREATE TRIGGER IF NOT EXISTS mixed_overage_refund_provenance_locked BEFORE UPDATE OF
 clearance_id,request_key,request_hash,claim_ref,claimant_name,evidence_id,amount_piasters,
 evidence_note,central_shift_id,main_fund_id,proposed_by,proposed_at
 ON late_mixed_overage_refund_requests
 BEGIN SELECT RAISE(ABORT,'Overage refund provenance is immutable'); END;
CREATE TRIGGER IF NOT EXISTS mixed_overage_refund_final_locked BEFORE UPDATE ON late_mixed_overage_refund_requests
 WHEN OLD.status!='pending' BEGIN SELECT RAISE(ABORT,'Final overage decision is immutable'); END;
CREATE TRIGGER IF NOT EXISTS mixed_overage_refund_no_delete BEFORE DELETE ON late_mixed_overage_refund_requests
 BEGIN SELECT RAISE(ABORT,'Overage refund records cannot be deleted'); END;

-- G2K: settlement of approved patient card receipts through a dedicated
-- POS clearing wallet into the bank NET of acquiring fees.
-- Proof of bank arrival is separate and must be signed via bank reconciliation.
CREATE TABLE IF NOT EXISTS pos_settlements (
 id INTEGER PRIMARY KEY,
 clearing_fund_id INTEGER NOT NULL REFERENCES funds(id),
 bank_fund_id INTEGER NOT NULL REFERENCES funds(id),
 settlement_date TEXT NOT NULL,
 settlement_ref TEXT NOT NULL,
 evidence_note TEXT NOT NULL,
 gross_piasters INTEGER NOT NULL CHECK(gross_piasters > 0),
 fee_piasters INTEGER NOT NULL CHECK(fee_piasters >= 0 AND fee_piasters < gross_piasters),
 net_piasters INTEGER NOT NULL CHECK(net_piasters > 0 AND net_piasters = gross_piasters-fee_piasters),
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 request_key TEXT NOT NULL UNIQUE,
 request_hash TEXT NOT NULL,
 created_by INTEGER NOT NULL REFERENCES users(id),
 created_at TEXT NOT NULL,
 reviewed_by INTEGER REFERENCES users(id),
 reviewed_at TEXT,
 decision_note TEXT NOT NULL DEFAULT '',
 transfer_voucher_id INTEGER UNIQUE REFERENCES vouchers(id),
 fee_voucher_id INTEGER UNIQUE REFERENCES vouchers(id),
 CHECK(clearing_fund_id != bank_fund_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pos_active_ref
 ON pos_settlements(clearing_fund_id,settlement_ref) WHERE status IN ('pending','approved');
CREATE INDEX IF NOT EXISTS idx_pos_period ON pos_settlements(settlement_date,status);
CREATE TABLE IF NOT EXISTS pos_settlement_parts (
 id INTEGER PRIMARY KEY,
 settlement_id INTEGER NOT NULL REFERENCES pos_settlements(id),
 payment_part_id INTEGER NOT NULL REFERENCES billing_payment_parts(id),
 amount_piasters INTEGER NOT NULL CHECK(amount_piasters > 0),
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
 UNIQUE(settlement_id,payment_part_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pos_one_active_part
 ON pos_settlement_parts(payment_part_id) WHERE active=1;
CREATE TRIGGER IF NOT EXISTS pos_approved_no_update BEFORE UPDATE ON pos_settlements
 WHEN OLD.status='approved' BEGIN SELECT RAISE(ABORT,'Approved POS settlement is immutable'); END;
CREATE TRIGGER IF NOT EXISTS pos_approved_no_delete BEFORE DELETE ON pos_settlements
 WHEN OLD.status='approved' BEGIN SELECT RAISE(ABORT,'Approved POS settlement is immutable'); END;
CREATE TRIGGER IF NOT EXISTS pos_parts_no_modify AFTER UPDATE ON pos_settlement_parts
 WHEN (SELECT status FROM pos_settlements WHERE id=OLD.settlement_id)='approved'
 BEGIN SELECT RAISE(ABORT,'Approved POS parts are immutable'); END;
CREATE TRIGGER IF NOT EXISTS pos_parts_no_delete BEFORE DELETE ON pos_settlement_parts
 WHEN (SELECT status FROM pos_settlements WHERE id=OLD.settlement_id)='approved'
 BEGIN SELECT RAISE(ABORT,'Approved POS parts are immutable'); END;
CREATE TRIGGER IF NOT EXISTS pos_parts_no_insert BEFORE INSERT ON pos_settlement_parts
 WHEN (SELECT status FROM pos_settlements WHERE id=NEW.settlement_id)!='pending'
 BEGIN SELECT RAISE(ABORT,'Cannot add parts after POS settlement decision'); END;

-- G2L: independent source-backed verification of pre-existing fund balances.
-- The voucher cashbook never gains a fake receipt when an opening is posted.
CREATE TABLE IF NOT EXISTS fund_opening_reviews (
 id INTEGER PRIMARY KEY,
 fund_id INTEGER NOT NULL REFERENCES funds(id),
 amount_piasters INTEGER NOT NULL CHECK(amount_piasters >= 0),
 effective_date TEXT NOT NULL,
 evidence_kind TEXT NOT NULL CHECK(evidence_kind IN ('cash_count','bank_statement','wallet_statement')),
 evidence_reference TEXT NOT NULL CHECK(length(trim(evidence_reference)) BETWEEN 6 AND 140),
 evidence_note TEXT NOT NULL CHECK(length(trim(evidence_note)) BETWEEN 12 AND 500),
 offset_account_id INTEGER REFERENCES gl_accounts(id),
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 created_by INTEGER NOT NULL REFERENCES users(id),
 created_at TEXT NOT NULL,
 reviewed_by INTEGER REFERENCES users(id),
 reviewed_at TEXT,
 decision_note TEXT NOT NULL DEFAULT '',
 journal_id INTEGER UNIQUE REFERENCES gl_journals(id),
 CHECK(status != 'approved' OR (reviewed_by IS NOT NULL AND reviewed_by != created_by)),
 CHECK(status != 'approved' OR amount_piasters = 0 OR (offset_account_id IS NOT NULL AND journal_id IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_fund_opening_active
 ON fund_opening_reviews(fund_id) WHERE status IN ('pending','approved');
CREATE INDEX IF NOT EXISTS idx_fund_opening_date ON fund_opening_reviews(effective_date,status);
CREATE TRIGGER IF NOT EXISTS fund_opening_approved_no_change BEFORE UPDATE ON fund_opening_reviews
 WHEN OLD.status='approved' BEGIN SELECT RAISE(ABORT,'Approved fund opening is immutable'); END;
CREATE TRIGGER IF NOT EXISTS fund_opening_rejected_no_change BEFORE UPDATE ON fund_opening_reviews
 WHEN OLD.status='rejected' BEGIN SELECT RAISE(ABORT,'Rejected opening evidence is immutable'); END;
CREATE TRIGGER IF NOT EXISTS fund_opening_final_no_delete BEFORE DELETE ON fund_opening_reviews
 BEGIN SELECT RAISE(ABORT,'Opening evidence is immutable'); END;
-- Reject EVERY cashbook writer (including specialized cashier APIs) if a
-- historical movement predates an independently approved opening.
CREATE TRIGGER IF NOT EXISTS fund_movement_not_before_opening BEFORE INSERT ON fund_movements
 WHEN EXISTS (SELECT 1 FROM fund_opening_reviews r
             WHERE r.fund_id=NEW.fund_id AND r.status='approved'
               AND NEW.booked_on < r.effective_date)
 BEGIN SELECT RAISE(ABORT,'Movement predates approved fund opening'); END;
CREATE TRIGGER IF NOT EXISTS fund_opening_lock_amount BEFORE UPDATE OF opening_piasters ON funds
 WHEN EXISTS (SELECT 1 FROM fund_opening_reviews r
     WHERE r.fund_id=OLD.id AND r.status IN ('pending','approved'))
 BEGIN SELECT RAISE(ABORT,'Opening amount has a submitted or approved review'); END;

-- G2P: controlled financial clearance of an extended-case ledger.
-- Medical discharge is OUT OF SCOPE; no clinical sign-off is represented here.
CREATE TABLE IF NOT EXISTS billing_case_clearance_requests (
 id INTEGER PRIMARY KEY,
 case_id INTEGER NOT NULL REFERENCES billing_cases(id),
 point_id INTEGER NOT NULL REFERENCES billing_points(id),
 evidence_reference TEXT NOT NULL CHECK(length(trim(evidence_reference)) BETWEEN 8 AND 180),
 note TEXT NOT NULL CHECK(length(trim(note)) BETWEEN 12 AND 500),
 requested_by INTEGER NOT NULL REFERENCES users(id),
 requested_at TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 clearance_mode TEXT NOT NULL DEFAULT 'settled' CHECK(clearance_mode IN ('settled','no_charge')),
 reviewed_by INTEGER REFERENCES users(id),
 reviewed_at TEXT,
 decision_note TEXT NOT NULL DEFAULT '',
 closed_on TEXT,
 snapshot_json TEXT NOT NULL DEFAULT '',
 CHECK(status!='approved' OR (reviewed_by IS NOT NULL AND reviewed_by!=requested_by AND closed_on IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_case_clearance_pending
 ON billing_case_clearance_requests(case_id) WHERE status='pending';
CREATE UNIQUE INDEX IF NOT EXISTS idx_case_clearance_approved
 ON billing_case_clearance_requests(case_id) WHERE status='approved';
CREATE TRIGGER IF NOT EXISTS case_clearance_evidence_immutable BEFORE UPDATE OF
 case_id,point_id,evidence_reference,note,requested_by,requested_at,clearance_mode
 ON billing_case_clearance_requests
 BEGIN SELECT RAISE(ABORT,'Clearance evidence is immutable'); END;
CREATE TRIGGER IF NOT EXISTS case_clearance_final_immutable BEFORE UPDATE
 ON billing_case_clearance_requests WHEN OLD.status!='pending'
 BEGIN SELECT RAISE(ABORT,'Final clearance decision is immutable'); END;
CREATE TRIGGER IF NOT EXISTS case_clearance_no_delete BEFORE DELETE ON billing_case_clearance_requests
 BEGIN SELECT RAISE(ABORT,'Financial clearance history is immutable'); END;
-- Closing the case is only possible with an approved independent review.
CREATE TRIGGER IF NOT EXISTS billing_case_closure_needs_approval BEFORE UPDATE OF status ON billing_cases
 WHEN NEW.status='closed' AND OLD.status!='closed' AND NOT EXISTS
    (SELECT 1 FROM billing_case_clearance_requests r WHERE r.case_id=OLD.id AND r.status='approved')
 BEGIN SELECT RAISE(ABORT,'Financial closure requires reviewed clearance'); END;
CREATE TRIGGER IF NOT EXISTS billing_case_no_reopen BEFORE UPDATE OF status ON billing_cases
 WHEN OLD.status='closed' AND NEW.status!='closed'
 BEGIN SELECT RAISE(ABORT,'Case financial closure is immutable'); END;
-- Deny direct or alternate-endpoint mutations after financial closure.
CREATE TRIGGER IF NOT EXISTS billing_closed_no_new_line BEFORE INSERT ON billing_case_lines
 WHEN (SELECT status FROM billing_cases WHERE id=NEW.case_id)='closed'
 BEGIN SELECT RAISE(ABORT,'Closed case cannot receive new services'); END;
CREATE TRIGGER IF NOT EXISTS billing_closed_no_draft BEFORE INSERT ON billing_invoice_drafts
 WHEN (SELECT status FROM billing_cases WHERE id=NEW.case_id)='closed'
 BEGIN SELECT RAISE(ABORT,'Closed case cannot receive invoices'); END;
CREATE TRIGGER IF NOT EXISTS billing_closed_no_invoice BEFORE INSERT ON billing_invoices
 WHEN (SELECT status FROM billing_cases WHERE id=NEW.case_id)='closed'
 BEGIN SELECT RAISE(ABORT,'Closed case cannot receive invoices'); END;
CREATE TRIGGER IF NOT EXISTS billing_closed_no_collection BEFORE INSERT ON billing_collections
 WHEN (SELECT status FROM billing_cases WHERE id=NEW.case_id)='closed'
 BEGIN SELECT RAISE(ABORT,'Closed case cannot collect again'); END;
CREATE TRIGGER IF NOT EXISTS billing_closed_no_allocation BEFORE INSERT ON billing_advance_allocations
 WHEN (SELECT status FROM billing_cases WHERE id=NEW.case_id)='closed'
 BEGIN SELECT RAISE(ABORT,'Closed case cannot allocate advances'); END;
CREATE TRIGGER IF NOT EXISTS billing_closed_no_credit BEFORE INSERT ON billing_credit_requests
 WHEN (SELECT status FROM billing_cases WHERE id=NEW.case_id)='closed'
 BEGIN SELECT RAISE(ABORT,'Closed case requires a controlled post-close correction'); END;
CREATE TRIGGER IF NOT EXISTS billing_closed_no_refund BEFORE INSERT ON billing_refund_requests
 WHEN (SELECT status FROM billing_cases WHERE id=NEW.case_id)='closed'
 BEGIN SELECT RAISE(ABORT,'Closed case requires a controlled post-close correction'); END;
CREATE TRIGGER IF NOT EXISTS billing_closed_no_reallocation BEFORE INSERT ON financial_collection_reallocations
 WHEN (SELECT status FROM billing_cases WHERE id=NEW.from_case_id)='closed'
 OR (SELECT status FROM billing_cases WHERE id=NEW.to_case_id)='closed'
 BEGIN SELECT RAISE(ABORT,'Closed case receipt cannot be reallocated'); END;

CREATE TRIGGER IF NOT EXISTS billing_closed_no_line_changes BEFORE UPDATE ON billing_case_lines
 WHEN (SELECT status FROM billing_cases WHERE id=OLD.case_id)='closed'
 BEGIN SELECT RAISE(ABORT,'Closed case service lines are immutable'); END;
CREATE TRIGGER IF NOT EXISTS billing_closed_no_advance_allocation_update BEFORE UPDATE ON billing_advance_allocations
 WHEN (SELECT status FROM billing_cases WHERE id=OLD.case_id)='closed'
 BEGIN SELECT RAISE(ABORT,'Closed case allocation is immutable'); END;
CREATE TRIGGER IF NOT EXISTS billing_closed_no_refund_update BEFORE UPDATE ON billing_refund_requests
 WHEN (SELECT status FROM billing_cases WHERE id=OLD.case_id)='closed'
 BEGIN SELECT RAISE(ABORT,'Closed case refund is immutable'); END;
CREATE TRIGGER IF NOT EXISTS billing_closed_no_credit_update BEFORE UPDATE ON billing_credit_requests
 WHEN (SELECT status FROM billing_cases WHERE id=OLD.case_id)='closed'
 BEGIN SELECT RAISE(ABORT,'Closed case credit is immutable'); END;

-- G2P hardening: a financially closed case is an immutable audit anchor.
CREATE TRIGGER IF NOT EXISTS billing_closed_no_case_core_changes BEFORE UPDATE OF
 patient_id,case_no,kind,default_point_id,business_date ON billing_cases
 WHEN OLD.status='closed'
 BEGIN SELECT RAISE(ABORT,'Closed case identity and provenance are immutable'); END;
CREATE TRIGGER IF NOT EXISTS billing_closed_no_case_delete BEFORE DELETE ON billing_cases
 WHEN OLD.status='closed'
 BEGIN SELECT RAISE(ABORT,'Closed case cannot be deleted'); END;
CREATE TRIGGER IF NOT EXISTS billing_closed_no_line_delete BEFORE DELETE ON billing_case_lines
 WHEN (SELECT status FROM billing_cases WHERE id=OLD.case_id)='closed'
 BEGIN SELECT RAISE(ABORT,'Closed case services cannot be deleted'); END;
CREATE TRIGGER IF NOT EXISTS billing_closed_no_payment_insert BEFORE INSERT ON billing_payment_parts
 WHEN (SELECT b.status FROM billing_collections c
       JOIN billing_cases b ON b.id=c.case_id WHERE c.id=NEW.collection_id)='closed'
 BEGIN SELECT RAISE(ABORT,'Closed case collections are immutable'); END;

-- G2R M4: physically occupied beds and priced calendar nights. This is NOT a
-- clinical discharge, and recording an occupied night NEVER posts cash or GL.
-- Only explicit invoice issuance posts revenue via the existing reviewed flow.
CREATE TABLE IF NOT EXISTS bed_catalog (
 id INTEGER PRIMARY KEY,
 code TEXT NOT NULL UNIQUE,
 name TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('inpatient','nicu')),
 service_id INTEGER NOT NULL REFERENCES billing_services(id),
 created_by INTEGER NOT NULL REFERENCES users(id),
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bed_stays (
 id INTEGER PRIMARY KEY,
 bed_id INTEGER NOT NULL REFERENCES bed_catalog(id),
 case_id INTEGER NOT NULL REFERENCES billing_cases(id),
 start_date TEXT NOT NULL,
 end_date TEXT,
 admission_evidence TEXT NOT NULL CHECK(length(trim(admission_evidence)) BETWEEN 8 AND 180),
 release_evidence TEXT,
 recorded_by INTEGER NOT NULL REFERENCES users(id),
 recorded_at TEXT NOT NULL,
 released_by INTEGER REFERENCES users(id),
 released_at TEXT,
 CHECK(end_date IS NULL OR end_date>=start_date)
);
CREATE INDEX IF NOT EXISTS idx_bed_stays_case ON bed_stays(case_id,start_date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_bed_one_open_stay ON bed_stays(bed_id) WHERE end_date IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_case_one_open_bed ON bed_stays(case_id) WHERE end_date IS NULL;
CREATE TRIGGER IF NOT EXISTS bed_stays_no_overlap_insert BEFORE INSERT ON bed_stays
 WHEN EXISTS (SELECT 1 FROM bed_stays s WHERE (s.bed_id=NEW.bed_id OR s.case_id=NEW.case_id)
   AND NEW.start_date<COALESCE(s.end_date,'9999-12-31')
   AND s.start_date<COALESCE(NEW.end_date,'9999-12-31'))
 BEGIN SELECT RAISE(ABORT,'Overlapping bed/case occupancy'); END;
CREATE TRIGGER IF NOT EXISTS bed_stays_no_overlap_update BEFORE UPDATE ON bed_stays
 WHEN EXISTS (SELECT 1 FROM bed_stays s WHERE s.id!=OLD.id
   AND (s.bed_id=NEW.bed_id OR s.case_id=NEW.case_id)
   AND NEW.start_date<COALESCE(s.end_date,'9999-12-31')
   AND s.start_date<COALESCE(NEW.end_date,'9999-12-31'))
 BEGIN SELECT RAISE(ABORT,'Overlapping bed/case occupancy'); END;
CREATE TRIGGER IF NOT EXISTS bed_stay_provenance_locked BEFORE UPDATE OF
 bed_id,case_id,start_date,admission_evidence,recorded_by,recorded_at ON bed_stays
 BEGIN SELECT RAISE(ABORT,'Bed admission provenance is immutable'); END;
CREATE TRIGGER IF NOT EXISTS bed_stay_release_once BEFORE UPDATE ON bed_stays
 WHEN OLD.end_date IS NOT NULL
 BEGIN SELECT RAISE(ABORT,'Bed release is immutable'); END;
CREATE TRIGGER IF NOT EXISTS bed_stay_no_delete BEFORE DELETE ON bed_stays
 BEGIN SELECT RAISE(ABORT,'Bed occupancy history is immutable'); END;
CREATE TRIGGER IF NOT EXISTS bed_stay_closed_case_insert BEFORE INSERT ON bed_stays
 WHEN (SELECT status FROM billing_cases WHERE id=NEW.case_id)='closed'
 BEGIN SELECT RAISE(ABORT,'Closed case cannot acquire a bed'); END;
CREATE TRIGGER IF NOT EXISTS bed_catalog_no_update BEFORE UPDATE ON bed_catalog
 BEGIN SELECT RAISE(ABORT,'Bed identity requires controlled replacement'); END;
CREATE TRIGGER IF NOT EXISTS bed_catalog_no_delete BEFORE DELETE ON bed_catalog
 BEGIN SELECT RAISE(ABORT,'Bed identity with pricing history is immutable'); END;
CREATE TABLE IF NOT EXISTS bed_night_charges (
 id INTEGER PRIMARY KEY,
 stay_id INTEGER NOT NULL REFERENCES bed_stays(id),
 night_date TEXT NOT NULL,
 case_line_id INTEGER NOT NULL UNIQUE REFERENCES billing_case_lines(id),
 price_version_id INTEGER NOT NULL REFERENCES billing_service_prices(id),
 amount_piasters INTEGER NOT NULL CHECK(amount_piasters>0),
 ordered_by INTEGER NOT NULL REFERENCES users(id),
 ordered_at TEXT NOT NULL,
 UNIQUE(stay_id,night_date)
);
CREATE INDEX IF NOT EXISTS idx_bed_charge_stay ON bed_night_charges(stay_id,night_date);
CREATE TRIGGER IF NOT EXISTS bed_charge_no_update BEFORE UPDATE ON bed_night_charges
 BEGIN SELECT RAISE(ABORT,'Night charge evidence is immutable'); END;
CREATE TRIGGER IF NOT EXISTS bed_charge_no_delete BEFORE DELETE ON bed_night_charges
 BEGIN SELECT RAISE(ABORT,'Night charge evidence is immutable'); END;
CREATE TRIGGER IF NOT EXISTS bed_charge_no_closed_case BEFORE INSERT ON bed_night_charges
 WHEN (SELECT b.status FROM bed_stays s JOIN billing_cases b ON b.id=s.case_id WHERE s.id=NEW.stay_id)='closed'
 BEGIN SELECT RAISE(ABORT,'Closed case cannot receive bed charges'); END;
CREATE TRIGGER IF NOT EXISTS bed_charge_line_no_cancel BEFORE UPDATE OF state ON billing_case_lines
 WHEN NEW.state='cancelled' AND EXISTS (SELECT 1 FROM bed_night_charges ch WHERE ch.case_line_id=OLD.id)
 BEGIN SELECT RAISE(ABORT,'Recorded bed night requires controlled financial correction'); END;
CREATE TRIGGER IF NOT EXISTS bed_charge_line_core_immutable BEFORE UPDATE OF
 case_id,service_id,price_version_id,service_name_snapshot,department_id,unit_price_piasters,quantity
 ON billing_case_lines
 WHEN EXISTS (SELECT 1 FROM bed_night_charges ch WHERE ch.case_line_id=OLD.id)
 BEGIN SELECT RAISE(ABORT,'Recorded bed night financial snapshot is immutable'); END;
CREATE TRIGGER IF NOT EXISTS bed_charge_line_no_delete BEFORE DELETE ON billing_case_lines
 WHEN EXISTS (SELECT 1 FROM bed_night_charges ch WHERE ch.case_line_id=OLD.id)
 BEGIN SELECT RAISE(ABORT,'Recorded bed night line cannot be deleted'); END;
CREATE TRIGGER IF NOT EXISTS bed_stay_case_kind_guard BEFORE INSERT ON bed_stays
 WHEN NEW.start_date<(SELECT business_date FROM billing_cases WHERE id=NEW.case_id)
 OR (SELECT kind FROM billing_cases WHERE id=NEW.case_id)='outpatient'
 OR ((SELECT kind FROM billing_cases WHERE id=NEW.case_id)='nicu'
     AND (SELECT kind FROM bed_catalog WHERE id=NEW.bed_id)!='nicu')
 OR ((SELECT kind FROM billing_cases WHERE id=NEW.case_id)!='nicu'
     AND (SELECT kind FROM bed_catalog WHERE id=NEW.bed_id)!='inpatient')
 BEGIN SELECT RAISE(ABORT,'Bed kind/date does not match patient case'); END;
CREATE TRIGGER IF NOT EXISTS bed_stay_release_evidence_guard BEFORE UPDATE OF end_date ON bed_stays
 WHEN NEW.end_date IS NOT NULL AND
      (NEW.release_evidence IS NULL OR length(trim(NEW.release_evidence))<8 OR
       NEW.released_by IS NULL OR NEW.released_at IS NULL)
 BEGIN SELECT RAISE(ABORT,'Bed release requires evidence and custodian'); END;
CREATE TRIGGER IF NOT EXISTS bed_charge_case_and_price_guard BEFORE INSERT ON bed_night_charges
 WHEN NOT EXISTS (
    SELECT 1 FROM bed_stays st
    JOIN bed_catalog b ON b.id=st.bed_id
    JOIN billing_case_lines l ON l.id=NEW.case_line_id
    JOIN billing_service_prices p ON p.id=NEW.price_version_id
    WHERE st.id=NEW.stay_id
      AND l.case_id=st.case_id AND l.service_id=b.service_id
      AND l.price_version_id=NEW.price_version_id
      AND p.service_id=b.service_id
      AND p.valid_from<=NEW.night_date
      AND p.price_piasters=NEW.amount_piasters
      AND l.unit_price_piasters=NEW.amount_piasters
      AND l.quantity=1 AND l.state='ordered'
      AND NEW.night_date>=st.start_date
      AND (st.end_date IS NULL OR NEW.night_date<st.end_date)
  )
 BEGIN SELECT RAISE(ABORT,'Bed night must match stay, patient, tariff and amount'); END;
-- Defense in depth: direct status updates must not circumvent the G2R preflight.
CREATE TRIGGER IF NOT EXISTS bed_stay_case_close_guard BEFORE UPDATE OF status ON billing_cases
 WHEN OLD.status!='closed' AND NEW.status='closed' AND (
   EXISTS (SELECT 1 FROM bed_stays s WHERE s.case_id=OLD.id AND s.end_date IS NULL)
   OR EXISTS (SELECT 1 FROM bed_stays s WHERE s.case_id=OLD.id AND s.end_date IS NOT NULL
       AND CAST(julianday(s.end_date)-julianday(s.start_date) AS INTEGER) !=
         (SELECT COUNT(*) FROM bed_night_charges ch WHERE ch.stay_id=s.id))
 )
 BEGIN SELECT RAISE(ABORT,'Financial closure cannot skip occupied beds or missing nights'); END;

-- G2S physical bed transfer evidence. No cash, revenue, or medical discharge.
CREATE TABLE IF NOT EXISTS bed_transfers (
 id INTEGER PRIMARY KEY,
 from_stay_id INTEGER NOT NULL UNIQUE REFERENCES bed_stays(id),
 to_stay_id INTEGER NOT NULL UNIQUE REFERENCES bed_stays(id),
 transfer_date TEXT NOT NULL,
 evidence_reference TEXT NOT NULL CHECK(length(trim(evidence_reference)) BETWEEN 8 AND 180),
 transferred_by INTEGER NOT NULL REFERENCES users(id),
 transferred_at TEXT NOT NULL,
 CHECK(from_stay_id!=to_stay_id)
);
CREATE TRIGGER IF NOT EXISTS bed_transfer_history_locked BEFORE UPDATE ON bed_transfers
 BEGIN SELECT RAISE(ABORT,'Bed transfer history cannot be changed'); END;
CREATE TRIGGER IF NOT EXISTS bed_transfer_history_no_delete BEFORE DELETE ON bed_transfers
 BEGIN SELECT RAISE(ABORT,'Bed transfer history cannot be deleted'); END;
CREATE TRIGGER IF NOT EXISTS bed_transfer_consistency BEFORE INSERT ON bed_transfers
 WHEN NOT EXISTS (SELECT 1 FROM bed_stays source JOIN bed_stays target
    ON source.case_id=target.case_id WHERE source.id=NEW.from_stay_id
    AND target.id=NEW.to_stay_id AND source.bed_id!=target.bed_id
    AND source.end_date=NEW.transfer_date AND target.start_date=NEW.transfer_date
    AND source.release_evidence=NEW.evidence_reference
    AND target.admission_evidence=NEW.evidence_reference)
 BEGIN SELECT RAISE(ABORT,'Bed transfer source/destination evidence mismatch'); END;

-- G2S period controls below the API: sealed nights and custody cannot be backdated.
CREATE TRIGGER IF NOT EXISTS bed_admission_sealed_month BEFORE INSERT ON bed_stays
 WHEN EXISTS (SELECT 1 FROM periods WHERE period=substr(NEW.start_date,1,7))
 BEGIN SELECT RAISE(ABORT,'Sealed month cannot receive a bed admission'); END;
CREATE TRIGGER IF NOT EXISTS bed_release_sealed_month BEFORE UPDATE OF end_date ON bed_stays
 WHEN NEW.end_date IS NOT NULL AND EXISTS
      (SELECT 1 FROM periods WHERE period=substr(NEW.end_date,1,7))
 BEGIN SELECT RAISE(ABORT,'Sealed month cannot receive a bed release'); END;
CREATE TRIGGER IF NOT EXISTS bed_release_after_charged_nights BEFORE UPDATE OF end_date ON bed_stays
 WHEN NEW.end_date IS NOT NULL AND EXISTS
      (SELECT 1 FROM bed_night_charges WHERE stay_id=OLD.id AND night_date>=NEW.end_date)
 BEGIN SELECT RAISE(ABORT,'Bed release date conflicts with booked nights'); END;
CREATE TRIGGER IF NOT EXISTS bed_charge_sealed_month BEFORE INSERT ON bed_night_charges
 WHEN EXISTS (SELECT 1 FROM periods WHERE period=substr(NEW.night_date,1,7))
 BEGIN SELECT RAISE(ABORT,'Sealed month cannot receive bed night charges'); END;

-- G2S: the historical service price used on a night must be the LATEST
-- effective date for that service, not any earlier valid-but-superseded tariff.
CREATE TRIGGER IF NOT EXISTS bed_night_latest_tariff BEFORE INSERT ON bed_night_charges
 WHEN NEW.price_version_id != (SELECT p.id FROM billing_service_prices p
    JOIN bed_stays s ON s.id=NEW.stay_id
    JOIN bed_catalog b ON b.id=s.bed_id
    WHERE p.service_id=b.service_id AND p.valid_from<=NEW.night_date
    ORDER BY p.valid_from DESC,p.id DESC LIMIT 1)
 BEGIN SELECT RAISE(ABORT,'Night charge must use latest effective-dated tariff'); END;

-- G2T (TEST ONLY): immutable central consumables warehouse subledger.
-- Medical prescriptions, pharmacy, VAT and cash settlement are OUT OF SCOPE.
CREATE TABLE IF NOT EXISTS inventory_vendors (
 id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
);
CREATE TABLE IF NOT EXISTS inventory_items (
 id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
 unit TEXT NOT NULL CHECK(unit IN ('piece','box','pack','bottle','meter')),
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
);
CREATE TABLE IF NOT EXISTS inventory_access (
 user_id INTEGER PRIMARY KEY REFERENCES users(id),
 can_prepare INTEGER NOT NULL DEFAULT 0 CHECK(can_prepare IN (0,1)),
 can_approve INTEGER NOT NULL DEFAULT 0 CHECK(can_approve IN (0,1)),
 changed_by INTEGER NOT NULL REFERENCES users(id), changed_at TEXT NOT NULL,
 reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inventory_receipts (
 id INTEGER PRIMARY KEY, vendor_id INTEGER NOT NULL REFERENCES inventory_vendors(id),
 received_on TEXT NOT NULL, invoice_ref TEXT NOT NULL, evidence_ref TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
 reviewed_by INTEGER REFERENCES users(id), reviewed_at TEXT, review_note TEXT,
 journal_id INTEGER UNIQUE REFERENCES gl_journals(id),
 CHECK(status!='approved' OR (reviewed_by IS NOT NULL AND reviewed_by!=created_by AND journal_id IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_inventory_supplier_invoice ON inventory_receipts(vendor_id,invoice_ref)
 WHERE status IN ('pending','approved');
CREATE INDEX IF NOT EXISTS idx_inventory_receipts_day ON inventory_receipts(received_on,status);
CREATE TABLE IF NOT EXISTS inventory_receipt_lines (
 id INTEGER PRIMARY KEY, receipt_id INTEGER NOT NULL REFERENCES inventory_receipts(id),
 item_id INTEGER NOT NULL REFERENCES inventory_items(id),
 quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 1000000),
 unit_cost_piasters INTEGER NOT NULL CHECK(unit_cost_piasters BETWEEN 1 AND 100000000000),
 batch_ref TEXT NOT NULL DEFAULT '', expiry_date TEXT,
 CHECK(expiry_date IS NULL OR length(expiry_date)=10)
);
CREATE INDEX IF NOT EXISTS idx_inventory_receipt_lines_item ON inventory_receipt_lines(item_id,receipt_id);
CREATE TABLE IF NOT EXISTS inventory_issues (
 id INTEGER PRIMARY KEY, department_id INTEGER NOT NULL REFERENCES departments(id),
 case_id INTEGER REFERENCES billing_cases(id), used_on TEXT NOT NULL,
 evidence_ref TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
 reviewed_by INTEGER REFERENCES users(id), reviewed_at TEXT, review_note TEXT,
 cost_piasters INTEGER NOT NULL DEFAULT 0 CHECK(cost_piasters>=0),
 journal_id INTEGER UNIQUE REFERENCES gl_journals(id),
 CHECK(status!='approved' OR (reviewed_by IS NOT NULL AND reviewed_by!=created_by AND journal_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_inventory_issues_day ON inventory_issues(used_on,status);
CREATE TABLE IF NOT EXISTS inventory_issue_lines (
 id INTEGER PRIMARY KEY, issue_id INTEGER NOT NULL REFERENCES inventory_issues(id),
 item_id INTEGER NOT NULL REFERENCES inventory_items(id),
 quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 1000000),
 UNIQUE(issue_id,item_id)
);
CREATE TABLE IF NOT EXISTS inventory_issue_allocations (
 id INTEGER PRIMARY KEY, issue_id INTEGER NOT NULL REFERENCES inventory_issues(id),
 issue_line_id INTEGER NOT NULL REFERENCES inventory_issue_lines(id),
 receipt_line_id INTEGER NOT NULL REFERENCES inventory_receipt_lines(id),
 quantity INTEGER NOT NULL CHECK(quantity>0),
 cost_piasters INTEGER NOT NULL CHECK(cost_piasters>0),
 UNIQUE(issue_line_id,receipt_line_id)
);
CREATE INDEX IF NOT EXISTS idx_inventory_lot_allocation ON inventory_issue_allocations(receipt_line_id);

CREATE TRIGGER IF NOT EXISTS inv_receipt_pending_only BEFORE INSERT ON inventory_receipts
 WHEN NEW.status!='pending' BEGIN SELECT RAISE(ABORT,'Inventory receipt must begin pending'); END;
CREATE TRIGGER IF NOT EXISTS inv_receipt_final_immutable BEFORE UPDATE ON inventory_receipts
 WHEN OLD.status!='pending' BEGIN SELECT RAISE(ABORT,'Final inventory receipt is immutable'); END;
CREATE TRIGGER IF NOT EXISTS inv_receipt_core_immutable BEFORE UPDATE OF
 vendor_id,received_on,invoice_ref,evidence_ref,created_by,created_at ON inventory_receipts
 BEGIN SELECT RAISE(ABORT,'Inventory evidence immutable'); END;
CREATE TRIGGER IF NOT EXISTS inv_receipt_no_delete BEFORE DELETE ON inventory_receipts
 BEGIN SELECT RAISE(ABORT,'Inventory receipt cannot be deleted'); END;
CREATE TRIGGER IF NOT EXISTS inv_receipt_line_pending BEFORE INSERT ON inventory_receipt_lines
 WHEN NOT EXISTS (SELECT 1 FROM inventory_receipts r WHERE r.id=NEW.receipt_id AND r.status='pending')
 BEGIN SELECT RAISE(ABORT,'Inventory receipt lines require pending source'); END;
CREATE TRIGGER IF NOT EXISTS inv_receipt_line_no_update BEFORE UPDATE ON inventory_receipt_lines
 BEGIN SELECT RAISE(ABORT,'Inventory lot immutable'); END;
CREATE TRIGGER IF NOT EXISTS inv_receipt_line_no_delete BEFORE DELETE ON inventory_receipt_lines
 BEGIN SELECT RAISE(ABORT,'Inventory lot immutable'); END;
CREATE TRIGGER IF NOT EXISTS inv_receipt_approval_guard BEFORE UPDATE OF status ON inventory_receipts
 WHEN NEW.status='approved' AND (
   NEW.reviewed_by IS NULL OR NEW.reviewed_by=NEW.created_by OR NEW.journal_id IS NULL OR
   NOT EXISTS(SELECT 1 FROM gl_journals j WHERE j.id=NEW.journal_id AND j.status='posted') OR
   NOT EXISTS(SELECT 1 FROM inventory_receipt_lines l WHERE l.receipt_id=NEW.id)
 ) BEGIN SELECT RAISE(ABORT,'Approval requires signed inventory journal'); END;

CREATE TRIGGER IF NOT EXISTS inv_issue_pending_only BEFORE INSERT ON inventory_issues
 WHEN NEW.status!='pending' BEGIN SELECT RAISE(ABORT,'Inventory issue must begin pending'); END;
CREATE TRIGGER IF NOT EXISTS inv_issue_final_immutable BEFORE UPDATE ON inventory_issues
 WHEN OLD.status!='pending' BEGIN SELECT RAISE(ABORT,'Final inventory issue immutable'); END;
CREATE TRIGGER IF NOT EXISTS inv_issue_core_immutable BEFORE UPDATE OF
 department_id,case_id,used_on,evidence_ref,created_by,created_at ON inventory_issues
 BEGIN SELECT RAISE(ABORT,'Inventory issue evidence immutable'); END;
CREATE TRIGGER IF NOT EXISTS inv_issue_no_delete BEFORE DELETE ON inventory_issues
 BEGIN SELECT RAISE(ABORT,'Inventory issue immutable'); END;
CREATE TRIGGER IF NOT EXISTS inv_issue_line_pending BEFORE INSERT ON inventory_issue_lines
 WHEN NOT EXISTS (SELECT 1 FROM inventory_issues i WHERE i.id=NEW.issue_id AND i.status='pending')
 BEGIN SELECT RAISE(ABORT,'Inventory issue lines require pending source'); END;
CREATE TRIGGER IF NOT EXISTS inv_issue_line_no_update BEFORE UPDATE ON inventory_issue_lines
 BEGIN SELECT RAISE(ABORT,'Inventory issue evidence immutable'); END;
CREATE TRIGGER IF NOT EXISTS inv_issue_line_no_delete BEFORE DELETE ON inventory_issue_lines
 BEGIN SELECT RAISE(ABORT,'Inventory issue evidence immutable'); END;
CREATE TRIGGER IF NOT EXISTS inv_issue_allocation_guard BEFORE INSERT ON inventory_issue_allocations
 WHEN NOT EXISTS (
   SELECT 1 FROM inventory_issue_lines l
   JOIN inventory_issues i ON i.id=l.issue_id
   JOIN inventory_receipt_lines rl ON rl.id=NEW.receipt_line_id AND rl.item_id=l.item_id
   JOIN inventory_receipts r ON r.id=rl.receipt_id
   WHERE l.id=NEW.issue_line_id AND l.issue_id=NEW.issue_id AND i.status='pending'
      AND r.status='approved' AND r.received_on<=i.used_on
      AND (rl.expiry_date IS NULL OR rl.expiry_date>=i.used_on)
      AND NEW.cost_piasters=NEW.quantity*rl.unit_cost_piasters
      AND NEW.quantity + COALESCE((SELECT SUM(a.quantity) FROM inventory_issue_allocations a
          WHERE a.receipt_line_id=rl.id),0)-
        COALESCE((SELECT SUM(rt.quantity) FROM inventory_return_lines rt
          JOIN inventory_issue_returns ret ON ret.id=rt.return_id AND ret.status='approved'
          JOIN inventory_issue_allocations a ON a.id=rt.issue_allocation_id
          WHERE a.receipt_line_id=rl.id AND ret.returned_on<=i.used_on),0)<=rl.quantity
 ) BEGIN SELECT RAISE(ABORT,'Invalid or insufficient FIFO lot allocation'); END;
CREATE TRIGGER IF NOT EXISTS inv_allocation_no_update BEFORE UPDATE ON inventory_issue_allocations
 BEGIN SELECT RAISE(ABORT,'Stock allocations immutable'); END;
CREATE TRIGGER IF NOT EXISTS inv_allocation_no_delete BEFORE DELETE ON inventory_issue_allocations
 BEGIN SELECT RAISE(ABORT,'Stock allocations immutable'); END;
CREATE TRIGGER IF NOT EXISTS inv_issue_approval_guard BEFORE UPDATE OF status ON inventory_issues
 WHEN NEW.status='approved' AND (
   NEW.reviewed_by IS NULL OR NEW.reviewed_by=NEW.created_by OR NEW.journal_id IS NULL OR
   NOT EXISTS(SELECT 1 FROM gl_journals j WHERE j.id=NEW.journal_id AND j.status='posted') OR
   NEW.cost_piasters<=0 OR
   EXISTS (SELECT 1 FROM inventory_issue_lines l WHERE l.issue_id=NEW.id AND
      l.quantity != COALESCE((SELECT SUM(a.quantity) FROM inventory_issue_allocations a WHERE a.issue_line_id=l.id),0))
 ) BEGIN SELECT RAISE(ABORT,'Approved issue requires all allocated units and journal'); END;

-- No retroactive stock history edits after the accounting month has been sealed.
CREATE TRIGGER IF NOT EXISTS inv_receipt_no_closed_month BEFORE INSERT ON inventory_receipts
 WHEN EXISTS(SELECT 1 FROM periods WHERE period=substr(NEW.received_on,1,7))
 BEGIN SELECT RAISE(ABORT,'Closed inventory receipt month'); END;
CREATE TRIGGER IF NOT EXISTS inv_issue_no_closed_month BEFORE INSERT ON inventory_issues
 WHEN EXISTS(SELECT 1 FROM periods WHERE period=substr(NEW.used_on,1,7))
 BEGIN SELECT RAISE(ABORT,'Closed inventory issue month'); END;
CREATE TRIGGER IF NOT EXISTS inv_issue_closed_patient_case BEFORE INSERT ON inventory_issues
 WHEN NEW.case_id IS NOT NULL AND EXISTS(SELECT 1 FROM billing_cases b
  WHERE b.id=NEW.case_id AND (b.status!='open' OR b.business_date>NEW.used_on))
 BEGIN SELECT RAISE(ABORT,'Cannot issue consumables to a closed or not-yet-open case'); END;
CREATE TRIGGER IF NOT EXISTS inv_issue_approval_closed_patient_case BEFORE UPDATE OF status ON inventory_issues
 WHEN NEW.status='approved' AND NEW.case_id IS NOT NULL AND EXISTS(SELECT 1 FROM billing_cases b
   WHERE b.id=NEW.case_id AND b.status!='open')
 BEGIN SELECT RAISE(ABORT,'Cannot approve consumables for a closed patient case'); END;
CREATE TRIGGER IF NOT EXISTS inv_receipt_no_closed_month_decision BEFORE UPDATE OF status ON inventory_receipts
 WHEN EXISTS(SELECT 1 FROM periods WHERE period=substr(OLD.received_on,1,7))
 BEGIN SELECT RAISE(ABORT,'Sealed month inventory receipt decision forbidden'); END;
CREATE TRIGGER IF NOT EXISTS inv_issue_no_closed_month_decision BEFORE UPDATE OF status ON inventory_issues
 WHEN EXISTS(SELECT 1 FROM periods WHERE period=substr(OLD.used_on,1,7))
 BEGIN SELECT RAISE(ABORT,'Sealed month inventory issue decision forbidden'); END;

-- G2Z (test-only): independent per-department medical evidence gate.
-- G3A: a separate clinician login, manually reviewed by the owner for this TEST ONLY pilot.
-- A review is a hospital-admin attestation, NOT license-registry verification or legal e-signature.
CREATE TABLE IF NOT EXISTS billing_clinical_identity_reviews (
 user_id INTEGER PRIMARY KEY REFERENCES users(id),
 professional_name TEXT NOT NULL CHECK(length(trim(professional_name)) BETWEEN 3 AND 120),
 registration_reference TEXT NOT NULL CHECK(length(trim(registration_reference)) BETWEEN 8 AND 100),
 approved INTEGER NOT NULL CHECK(approved IN (0,1)),
 reviewed_by INTEGER NOT NULL REFERENCES users(id),
 reviewed_at TEXT NOT NULL,
 review_note TEXT NOT NULL CHECK(length(trim(review_note)) BETWEEN 12 AND 400)
);
CREATE TRIGGER IF NOT EXISTS billing_clinical_identity_role_guard_insert
 BEFORE INSERT ON billing_clinical_identity_reviews
 WHEN NOT EXISTS(SELECT 1 FROM users WHERE id=NEW.user_id AND role='clinician' AND active=1)
 BEGIN SELECT RAISE(ABORT,'Only active clinical accounts may be manually reviewed'); END;
CREATE TRIGGER IF NOT EXISTS billing_clinical_identity_role_guard_update
 BEFORE UPDATE ON billing_clinical_identity_reviews
 WHEN NOT EXISTS(SELECT 1 FROM users WHERE id=NEW.user_id AND role='clinician' AND active=1)
 BEGIN SELECT RAISE(ABORT,'Only active clinical accounts may be manually reviewed'); END;
CREATE TABLE IF NOT EXISTS billing_clinical_grants (
 department_id INTEGER NOT NULL REFERENCES departments(id),
 user_id INTEGER NOT NULL REFERENCES users(id),
 active INTEGER NOT NULL CHECK(active IN (0,1)),
 assigned_by INTEGER NOT NULL REFERENCES users(id), assigned_at TEXT NOT NULL,
 PRIMARY KEY(department_id,user_id)
);
CREATE TABLE IF NOT EXISTS billing_clinical_policies (
 department_id INTEGER PRIMARY KEY REFERENCES departments(id),
 activated_by INTEGER NOT NULL REFERENCES users(id), activated_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS billing_clinical_policy_no_update BEFORE UPDATE ON billing_clinical_policies
 BEGIN SELECT RAISE(ABORT,'Clinical attestation activation cannot be silently disabled'); END;
CREATE TRIGGER IF NOT EXISTS billing_clinical_policy_no_delete BEFORE DELETE ON billing_clinical_policies
 BEGIN SELECT RAISE(ABORT,'Clinical attestation activation cannot be silently removed'); END;
CREATE TABLE IF NOT EXISTS billing_clinical_attestations (
 id INTEGER PRIMARY KEY,
 case_line_id INTEGER NOT NULL UNIQUE REFERENCES billing_case_lines(id),
 department_id INTEGER NOT NULL REFERENCES departments(id),
 service_date TEXT NOT NULL,
 evidence_reference TEXT NOT NULL CHECK(length(trim(evidence_reference)) BETWEEN 8 AND 180),
 attested_by INTEGER NOT NULL REFERENCES users(id), attested_at TEXT NOT NULL,
 -- G3B: exact-source fingerprint; source bytes and original file name are NEVER archived.
 document_sha256 TEXT,document_size INTEGER,document_media_type TEXT
);
-- G3B one-way owner opt-in; no backdating an existing witness to a different file.
CREATE TABLE IF NOT EXISTS billing_clinical_document_requirements (
 department_id INTEGER PRIMARY KEY REFERENCES departments(id),
 activated_by INTEGER NOT NULL REFERENCES users(id),activated_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS billing_clinical_document_requirement_no_update
 BEFORE UPDATE ON billing_clinical_document_requirements
 BEGIN SELECT RAISE(ABORT,'Clinical document requirement cannot be disabled'); END;
CREATE TRIGGER IF NOT EXISTS billing_clinical_document_requirement_no_delete
 BEFORE DELETE ON billing_clinical_document_requirements
 BEGIN SELECT RAISE(ABORT,'Clinical document requirement cannot be deleted'); END;
CREATE TRIGGER IF NOT EXISTS billing_clinical_document_hash_guard
 BEFORE INSERT ON billing_clinical_attestations
 WHEN (EXISTS(SELECT 1 FROM billing_clinical_document_requirements d
              WHERE d.department_id=NEW.department_id) AND NEW.document_sha256 IS NULL)
   OR (NEW.document_sha256 IS NULL AND
       (NEW.document_size IS NOT NULL OR NEW.document_media_type IS NOT NULL))
   OR (NEW.document_sha256 IS NOT NULL AND
       (length(NEW.document_sha256)!=64 OR NEW.document_sha256 GLOB '*[^0-9a-f]*'
        OR NEW.document_size IS NULL OR NEW.document_size NOT BETWEEN 1 AND 6291456
        OR NEW.document_media_type IS NULL OR
           NEW.document_media_type NOT IN ('application/pdf','image/png','image/jpeg')))
 BEGIN SELECT RAISE(ABORT,'Invalid or missing source document fingerprint'); END;
CREATE TRIGGER IF NOT EXISTS billing_clinical_attestation_no_update BEFORE UPDATE ON billing_clinical_attestations
 BEGIN SELECT RAISE(ABORT,'Clinical witness reference is immutable'); END;
CREATE TRIGGER IF NOT EXISTS billing_clinical_attestation_no_delete BEFORE DELETE ON billing_clinical_attestations
 BEGIN SELECT RAISE(ABORT,'Clinical witness reference is immutable'); END;
CREATE TRIGGER IF NOT EXISTS billing_clinical_attestation_validate_insert
 BEFORE INSERT ON billing_clinical_attestations
 WHEN NOT EXISTS (SELECT 1 FROM billing_clinical_policies p WHERE p.department_id=NEW.department_id)
   OR NEW.department_id!=(SELECT department_id FROM billing_case_lines WHERE id=NEW.case_line_id)
   OR NEW.service_date!=(SELECT service_date FROM billing_case_lines WHERE id=NEW.case_line_id)
   OR (SELECT state FROM billing_case_lines WHERE id=NEW.case_line_id)!='fulfilled'
   OR NOT EXISTS (SELECT 1 FROM billing_clinical_grants g JOIN users u ON u.id=g.user_id
                  WHERE g.department_id=NEW.department_id AND g.user_id=NEW.attested_by
                    AND g.active=1 AND u.active=1 AND u.role='clinician'
                    AND EXISTS (SELECT 1 FROM billing_clinical_identity_reviews i
                                WHERE i.user_id=u.id AND i.approved=1))
   OR EXISTS (SELECT 1 FROM billing_invoice_draft_lines dl JOIN billing_invoices i
              ON i.draft_id=dl.draft_id WHERE dl.case_line_id=NEW.case_line_id)
 BEGIN SELECT RAISE(ABORT,'Invalid clinical attestation provenance'); END;

-- G3C: a new backdated document must not rewrite already-approved FIFO order.
-- With day-resolution source dates, same-day approvals deliberately use commit order.
CREATE TRIGGER IF NOT EXISTS inv_receipt_fifo_date_guard BEFORE UPDATE OF status ON inventory_receipts
 WHEN NEW.status='approved' AND EXISTS (
  SELECT 1 FROM inventory_receipt_lines rl
  JOIN inventory_issue_lines il ON il.item_id=rl.item_id
  JOIN inventory_issues i ON i.id=il.issue_id
  WHERE rl.receipt_id=OLD.id AND i.status='approved' AND i.used_on>OLD.received_on
 ) BEGIN SELECT RAISE(ABORT,'Backdated receipt would invalidate approved FIFO issue'); END;
CREATE TRIGGER IF NOT EXISTS inv_issue_fifo_date_guard BEFORE UPDATE OF status ON inventory_issues
 WHEN NEW.status='approved' AND EXISTS (
  SELECT 1 FROM inventory_issue_lines il
  JOIN inventory_issue_lines later_line ON later_line.item_id=il.item_id
  JOIN inventory_issues later_issue ON later_issue.id=later_line.issue_id
  WHERE il.issue_id=OLD.id AND later_issue.status='approved'
    AND later_issue.used_on>OLD.used_on
 ) BEGIN SELECT RAISE(ABORT,'Backdated issue would invalidate approved FIFO issue'); END;


-- G3D: physical, non-drug unused supplies returned to their exact original FIFO allocations.
-- The old issue/allocation and cost journal are never mutated; the return is separately signed.
CREATE TABLE IF NOT EXISTS inventory_issue_returns (
 id INTEGER PRIMARY KEY, issue_id INTEGER NOT NULL REFERENCES inventory_issues(id),
 returned_on TEXT NOT NULL, evidence_ref TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
 reviewed_by INTEGER REFERENCES users(id), reviewed_at TEXT, review_note TEXT,
 cost_piasters INTEGER NOT NULL DEFAULT 0 CHECK(cost_piasters>=0),
 journal_id INTEGER UNIQUE REFERENCES gl_journals(id),
 CHECK(status!='approved' OR (reviewed_by IS NOT NULL AND reviewed_by!=created_by AND journal_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_inventory_returns_day ON inventory_issue_returns(returned_on,status);
CREATE TABLE IF NOT EXISTS inventory_return_lines (
 id INTEGER PRIMARY KEY,
 return_id INTEGER NOT NULL REFERENCES inventory_issue_returns(id),
 issue_allocation_id INTEGER NOT NULL REFERENCES inventory_issue_allocations(id),
 quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 1000000),
 UNIQUE(return_id,issue_allocation_id)
);
CREATE INDEX IF NOT EXISTS idx_inventory_returns_alloc ON inventory_return_lines(issue_allocation_id);
CREATE TRIGGER IF NOT EXISTS inv_return_pending_only BEFORE INSERT ON inventory_issue_returns
 WHEN NEW.status!='pending' OR NOT EXISTS (
  SELECT 1 FROM inventory_issues i WHERE i.id=NEW.issue_id AND i.status='approved'
    AND i.used_on<=NEW.returned_on AND (i.case_id IS NULL OR EXISTS (
     SELECT 1 FROM billing_cases b WHERE b.id=i.case_id AND b.status='open'))
 ) OR EXISTS (SELECT 1 FROM periods p WHERE p.period=substr(NEW.returned_on,1,7))
 BEGIN SELECT RAISE(ABORT,'Return must begin pending on open case and month after approved issue'); END;
CREATE TRIGGER IF NOT EXISTS inv_return_header_immutable BEFORE UPDATE OF
 issue_id,returned_on,evidence_ref,created_by,created_at ON inventory_issue_returns
 BEGIN SELECT RAISE(ABORT,'Original return evidence immutable'); END;
CREATE TRIGGER IF NOT EXISTS inv_return_final_immutable BEFORE UPDATE ON inventory_issue_returns
 WHEN OLD.status!='pending' BEGIN SELECT RAISE(ABORT,'Final inventory return immutable'); END;
CREATE TRIGGER IF NOT EXISTS inv_return_no_delete BEFORE DELETE ON inventory_issue_returns
 BEGIN SELECT RAISE(ABORT,'Inventory return immutable'); END;
CREATE TRIGGER IF NOT EXISTS inv_return_line_valid BEFORE INSERT ON inventory_return_lines
 WHEN NOT EXISTS (
   SELECT 1 FROM inventory_issue_returns ret
   JOIN inventory_issues i ON i.id=ret.issue_id AND i.status='approved'
   JOIN inventory_issue_allocations a ON a.id=NEW.issue_allocation_id AND a.issue_id=i.id
   JOIN inventory_receipt_lines lot ON lot.id=a.receipt_line_id
   WHERE ret.id=NEW.return_id AND ret.status='pending' AND i.used_on<=ret.returned_on
     AND (lot.expiry_date IS NULL OR lot.expiry_date>=ret.returned_on)
     AND (i.case_id IS NULL OR EXISTS (SELECT 1 FROM billing_cases b
           WHERE b.id=i.case_id AND b.status='open'))
     AND NEW.quantity + COALESCE((SELECT SUM(rl.quantity) FROM inventory_return_lines rl
         JOIN inventory_issue_returns prev ON prev.id=rl.return_id
         WHERE rl.issue_allocation_id=a.id AND prev.status IN ('pending','approved')),0)<=a.quantity
 ) BEGIN SELECT RAISE(ABORT,'Invalid or excess physical return allocation'); END;
CREATE TRIGGER IF NOT EXISTS inv_return_line_no_update BEFORE UPDATE ON inventory_return_lines
 BEGIN SELECT RAISE(ABORT,'Inventory return lines immutable'); END;
CREATE TRIGGER IF NOT EXISTS inv_return_line_no_delete BEFORE DELETE ON inventory_return_lines
 BEGIN SELECT RAISE(ABORT,'Inventory return lines immutable'); END;
CREATE TRIGGER IF NOT EXISTS inv_return_approval_guard BEFORE UPDATE OF status ON inventory_issue_returns
 WHEN EXISTS(SELECT 1 FROM periods WHERE period=substr(OLD.returned_on,1,7))
 OR (NEW.status='approved' AND (
   NEW.reviewed_by IS NULL OR NEW.reviewed_by=NEW.created_by OR NEW.journal_id IS NULL OR
   NOT EXISTS(SELECT 1 FROM gl_journals j WHERE j.id=NEW.journal_id AND j.status='posted') OR
   NOT EXISTS(SELECT 1 FROM inventory_return_lines rl WHERE rl.return_id=OLD.id) OR
   NEW.cost_piasters<=0 OR NEW.cost_piasters != (
      SELECT COALESCE(SUM(rl.quantity*lot.unit_cost_piasters),0)
      FROM inventory_return_lines rl
      JOIN inventory_issue_allocations a ON a.id=rl.issue_allocation_id
      JOIN inventory_receipt_lines lot ON lot.id=a.receipt_line_id
      WHERE rl.return_id=OLD.id) OR
   EXISTS (SELECT 1 FROM inventory_issues i WHERE i.id=OLD.issue_id
      AND i.case_id IS NOT NULL AND EXISTS(
        SELECT 1 FROM billing_cases b WHERE b.id=i.case_id AND b.status!='open')) OR
   EXISTS (SELECT 1 FROM inventory_return_lines rl
      JOIN inventory_issue_allocations a ON a.id=rl.issue_allocation_id
      JOIN inventory_receipt_lines lot ON lot.id=a.receipt_line_id
      JOIN inventory_issue_lines later_line ON later_line.item_id=lot.item_id
      JOIN inventory_issues later_issue ON later_issue.id=later_line.issue_id
      WHERE rl.return_id=OLD.id AND later_issue.status='approved'
        AND later_issue.used_on>OLD.returned_on)
 )) BEGIN SELECT RAISE(ABORT,'Return approval requires current period, signed original lot costs and valid FIFO date'); END;

-- G3D chronological guard: a return cannot be a source of stock for
-- a subsequently approved, backdated issue before that physical return date.
CREATE TRIGGER IF NOT EXISTS inv_issue_postreturn_date_guard BEFORE UPDATE OF status ON inventory_issues
 WHEN NEW.status='approved' AND EXISTS (
    SELECT 1 FROM inventory_issue_lines il
    JOIN inventory_issue_lines source ON source.item_id=il.item_id
    JOIN inventory_issue_allocations a ON a.issue_line_id=source.id
    JOIN inventory_return_lines rl ON rl.issue_allocation_id=a.id
    JOIN inventory_issue_returns ret ON ret.id=rl.return_id AND ret.status='approved'
    WHERE il.issue_id=OLD.id AND ret.returned_on>OLD.used_on
 ) BEGIN SELECT RAISE(ABORT,'Backdated issue predates a physical inventory return'); END;

-- G3D: a pending physical return is a financial-close blocker, even for direct SQL.
CREATE TRIGGER IF NOT EXISTS inv_return_case_close_pending_guard BEFORE UPDATE OF status ON billing_cases
 WHEN NEW.status='closed' AND OLD.status!='closed' AND EXISTS (
   SELECT 1 FROM inventory_issue_returns ret
   JOIN inventory_issues issue ON issue.id=ret.issue_id
   WHERE issue.case_id=OLD.id AND ret.status='pending'
 ) BEGIN SELECT RAISE(ABORT,'Pending inventory return prevents case financial closure'); END;
