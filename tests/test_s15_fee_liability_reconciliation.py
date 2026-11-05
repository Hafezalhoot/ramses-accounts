"""S15: independent, read-only reconciliation of service-fee accruals with GL 2320.

Synthetic SQLite only.  No hospital DB, payment, or bank transaction is accessed.
"""
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from service_fee_reconciliation import reconcile_fee_liability


def database():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.executescript('''
    CREATE TABLE gl_accounts(id INTEGER PRIMARY KEY,code TEXT UNIQUE,class TEXT,control TEXT,active INTEGER);
    CREATE TABLE gl_journals(id INTEGER PRIMARY KEY,status TEXT NOT NULL,origin TEXT NOT NULL,reversal_of_id INTEGER);
    CREATE TABLE gl_lines(id INTEGER PRIMARY KEY,journal_id INTEGER,account_id INTEGER,debit_piasters INTEGER,credit_piasters INTEGER);
    CREATE TABLE service_fee_decisions(id INTEGER PRIMARY KEY,decision TEXT,amount_piasters INTEGER,journal_id INTEGER);
    CREATE TABLE service_fee_reversals(id INTEGER PRIMARY KEY,decision_id INTEGER,journal_id INTEGER);
    INSERT INTO gl_accounts VALUES(1,'2320','liability','',1),(2,'5196','expense','',1);
    ''')
    return c


def journal(c, journal_id, signed_credit_piasters, *, posted=True, reversal_of_id=None):
    c.execute('INSERT INTO gl_journals VALUES(?,?,?,?)',
              (journal_id, 'posted' if posted else 'pending',
               'manual_reversal' if reversal_of_id is not None else 'manual', reversal_of_id))
    debit = max(0, -signed_credit_piasters)
    credit = max(0, signed_credit_piasters)
    c.execute('INSERT INTO gl_lines(journal_id,account_id,debit_piasters,credit_piasters) VALUES(?,?,?,?)',
              (journal_id, 1, debit, credit))
    c.execute('INSERT INTO gl_lines(journal_id,account_id,debit_piasters,credit_piasters) VALUES(?,?,?,?)',
              (journal_id, 2, credit, debit))


def assert_read_only(c):
    before = c.total_changes
    c.execute('PRAGMA query_only=ON')
    try:
        result = reconcile_fee_liability(c)
    finally:
        c.execute('PRAGMA query_only=OFF')
    assert c.total_changes == before, 'A reconciliation GET must never modify SQLite'
    assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    return result


def run():
    c = database()
    # No invoice activity is neither a GL mismatch nor a certified payout.
    empty = assert_read_only(c)
    assert empty['matched'] and empty['liability_piasters'] == 0
    assert empty['certified'] is False
    c.execute("INSERT INTO service_fee_decisions VALUES(1,'rejected',100, NULL)")
    journal(c, 10, 5000)
    c.execute("INSERT INTO service_fee_decisions VALUES(2,'approved',5000, 10)")
    ok = assert_read_only(c)
    assert (ok['liability_piasters'], ok['gl_balance_piasters'], ok['difference_piasters']) == (5000, 5000, 0)
    assert ok['matched'] and ok['broken_approvals'] == 0 and ok['unlinked_postings'] == 0

    # An unapproved, unlinked GL movement must be visible even if two amounts cancel.
    journal(c, 11, 700)
    journal(c, 12, -700)
    false_match = assert_read_only(c)
    assert not false_match['matched'] and false_match['difference_piasters'] == 0
    assert false_match['unlinked_postings'] == 2
    c.execute("DELETE FROM gl_lines WHERE journal_id IN (11,12)")
    c.execute("DELETE FROM gl_journals WHERE id IN (11,12)")

    # A linked approval with a pending journal is not an actual payable accrual.
    journal(c, 13, 1500, posted=False)
    c.execute("INSERT INTO service_fee_decisions VALUES(3,'approved',1500, 13)")
    pending = assert_read_only(c)
    assert not pending['matched'] and pending['broken_approvals'] == 1
    c.execute("UPDATE gl_journals SET status='posted' WHERE id=13")
    assert assert_read_only(c)['matched']

    # Reversal requires an exact opposite, posted entry. A bare reversal row is not enough.
    journal(c, 14, -5000, posted=False, reversal_of_id=10)
    c.execute("INSERT INTO service_fee_reversals VALUES(1,2,14)")
    bad_reverse = assert_read_only(c)
    assert not bad_reverse['matched'] and bad_reverse['broken_reversals'] == 1
    c.execute("UPDATE gl_journals SET status='posted' WHERE id=14")
    reversed_ok = assert_read_only(c)
    assert reversed_ok['matched'] and reversed_ok['liability_piasters'] == 1500
    assert reversed_ok['gl_balance_piasters'] == 1500

    # Two linked 2320 legs can cancel yet conceal an invalid journal structure.
    c.execute('INSERT INTO gl_lines(journal_id,account_id,debit_piasters,credit_piasters) VALUES(13,1,11,0)')
    c.execute('INSERT INTO gl_lines(journal_id,account_id,debit_piasters,credit_piasters) VALUES(13,1,0,11)')
    assert assert_read_only(c)['broken_approvals'] == 1, 'Multiple 2320 legs require investigation'
    c.execute('DELETE FROM gl_lines WHERE journal_id=13 AND id > (SELECT MIN(id) FROM gl_lines WHERE journal_id=13 AND account_id=1) AND account_id=1')
    assert assert_read_only(c)['matched']

    # An approved amount cannot hide a mismatched journal line for the same decision.
    c.execute('UPDATE service_fee_decisions SET amount_piasters=1400 WHERE id=3')
    wrong_amount = assert_read_only(c)
    assert not wrong_amount['matched'] and wrong_amount['broken_approvals'] == 1
    c.close()

    # The absence of account 2320 must not silently mean the reconciliation passed.
    c = database()
    c.execute('DELETE FROM gl_accounts WHERE code=\'2320\'')
    missing = assert_read_only(c)
    assert missing['account_present'] is False and missing['matched'] is False
    c.close()
    print('PASS S15 fee liability reconciliation: accrual/reversal, unlinked offset, stale posting, owner-only read path contract, and read-only SQLite')


def test_reconcile_fee_liability():
    run()


if __name__ == '__main__':
    run()