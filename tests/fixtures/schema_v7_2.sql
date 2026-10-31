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
 valid_to TEXT, note TEXT DEFAULT '', CHECK(valid_to IS NULL OR valid_to >= valid_from)
);
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
 UNIQUE(employee_id, period)
);
CREATE TABLE IF NOT EXISTS advance_allocations (
 id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id), period TEXT NOT NULL,
 amount_piasters INTEGER NOT NULL CHECK(amount_piasters > 0),
 actor_id INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL
);
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
