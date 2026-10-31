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
 opening_piasters INTEGER NOT NULL DEFAULT 0, allow_negative INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1
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
-- Cashier count is a blind count and is reviewed by a distinct approver.
-- Exactly one active (open or submitted) shift per physical fund.
CREATE TABLE IF NOT EXISTS shift_sessions (
 id INTEGER PRIMARY KEY,
 business_date TEXT NOT NULL, shift TEXT NOT NULL CHECK(shift IN ('morning','evening','night')),
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
 ON shift_sessions(fund_id) WHERE status IN ('open','submitted');
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
