"""S15: account 2320 matching must not hide incorrect counterpart accounts."""
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from service_fee_reconciliation import reconcile_fee_liability


def database():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE gl_accounts(id INTEGER PRIMARY KEY, code TEXT, class TEXT, control TEXT, active INTEGER);
        CREATE TABLE gl_journals(id INTEGER PRIMARY KEY, status TEXT, origin TEXT, reversal_of_id INTEGER);
        CREATE TABLE gl_lines(id INTEGER PRIMARY KEY, journal_id INTEGER, account_id INTEGER, debit_piasters INTEGER, credit_piasters INTEGER);
        CREATE TABLE service_fee_decisions(id INTEGER PRIMARY KEY, decision TEXT, amount_piasters INTEGER, journal_id INTEGER);
        CREATE TABLE service_fee_reversals(id INTEGER PRIMARY KEY, decision_id INTEGER, journal_id INTEGER);
        INSERT INTO gl_accounts VALUES (1,'2320','liability','',1), (2,'5196','expense','',1), (3,'1100','asset','',1);
        INSERT INTO gl_journals VALUES (10,'posted','manual',NULL),(11,'posted','manual_reversal',10);
        INSERT INTO service_fee_decisions VALUES (1,'approved',5000,10);
        INSERT INTO gl_lines(journal_id,account_id,debit_piasters,credit_piasters) VALUES
          (10,1,0,5000),(10,2,5000,0);
    ''')
    return conn


def test_valid_accrual_and_reversal():
    c=database()
    assert reconcile_fee_liability(c)['matched'] is True
    c.executescript('''
      INSERT INTO gl_lines(journal_id,account_id,debit_piasters,credit_piasters) VALUES
        (11,1,5000,0),(11,2,0,5000);
      INSERT INTO service_fee_reversals VALUES (1,1,11);
    ''')
    assert reconcile_fee_liability(c)['matched'] is True


def test_approval_wrong_counter_account():
    c=database()
    c.execute('UPDATE gl_lines SET account_id=3 WHERE journal_id=10 AND account_id=2')
    result=reconcile_fee_liability(c)
    assert result['difference_piasters']==0
    assert result['matched'] is False, result
    assert result['broken_approvals']==1


def test_approval_wrong_counter_amount_with_balanced_extra_account():
    c=database()
    c.execute('UPDATE gl_lines SET debit_piasters=2500 WHERE journal_id=10 AND account_id=2')
    c.execute('INSERT INTO gl_lines(journal_id,account_id,debit_piasters,credit_piasters) VALUES(10,3,2500,0)')
    result=reconcile_fee_liability(c)
    assert result['matched'] is False, result
    assert result['broken_approvals']==1


def test_reversal_wrong_counter_account():
    c=database()
    c.executescript('''
      INSERT INTO gl_lines(journal_id,account_id,debit_piasters,credit_piasters) VALUES
        (11,1,5000,0),(11,3,0,5000);
      INSERT INTO service_fee_reversals VALUES (1,1,11);
    ''')
    result=reconcile_fee_liability(c)
    assert result['difference_piasters']==0
    assert result['matched'] is False, result
    assert result['broken_reversals']==1


def test_expense_account_must_be_valid_and_active():
    c=database()
    c.execute("UPDATE gl_accounts SET class='asset' WHERE code='5196'")
    result=reconcile_fee_liability(c)
    assert result['matched'] is False, result
    assert result['expense_account_valid'] is False


def test_expense_account_must_be_active():
    c=database()
    c.execute("UPDATE gl_accounts SET active=0 WHERE code='5196'")
    result=reconcile_fee_liability(c)
    assert result['matched'] is False, result
    assert result['expense_account_valid'] is False


def test_approval_must_not_be_a_reversal_journal():
    c = database()
    c.execute('UPDATE gl_journals SET reversal_of_id=999 WHERE id=10')
    result = reconcile_fee_liability(c)
    assert result['difference_piasters'] == 0
    assert result['broken_approvals'] == 1
    assert result['matched'] is False


def test_reversal_must_reference_original_approval():
    c = database()
    c.executescript('''
      INSERT INTO gl_lines(journal_id,account_id,debit_piasters,credit_piasters) VALUES
        (11,1,5000,0),(11,2,0,5000);
      INSERT INTO service_fee_reversals VALUES (1,1,11);
    ''')
    c.execute('UPDATE gl_journals SET reversal_of_id=999 WHERE id=11')
    result = reconcile_fee_liability(c)
    assert result['difference_piasters'] == 0
    assert result['broken_reversals'] == 1
    assert result['matched'] is False


def test_reversal_must_have_reversal_origin():
    c = database()
    c.executescript('''
      INSERT INTO gl_lines(journal_id,account_id,debit_piasters,credit_piasters) VALUES
        (11,1,5000,0),(11,2,0,5000);
      INSERT INTO service_fee_reversals VALUES (1,1,11);
    ''')
    c.execute("UPDATE gl_journals SET origin='manual' WHERE id=11")
    result = reconcile_fee_liability(c)
    assert result['difference_piasters'] == 0
    assert result['broken_reversals'] == 1
    assert result['matched'] is False


if __name__ == "__main__":
    test_valid_accrual_and_reversal()
    test_approval_wrong_counter_account()
    test_approval_wrong_counter_amount_with_balanced_extra_account()
    test_reversal_wrong_counter_account()
    test_expense_account_must_be_valid_and_active()
    test_expense_account_must_be_active()
    test_approval_must_not_be_a_reversal_journal()
    test_reversal_must_reference_original_approval()
    test_reversal_must_have_reversal_origin()
    print("PASS S15 fee dual-entry and journal-lineage controls: 9 synthetic tests")
