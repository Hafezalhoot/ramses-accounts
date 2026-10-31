PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('owner','reviewer','clerk','viewer')), active INTEGER NOT NULL DEFAULT 1,
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
