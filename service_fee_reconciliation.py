"""Read-only S15 control: reconcile approved fee liability to posted GL account 2320.

This is NOT evidence of a completed payout and never creates a voucher or journal.
All amounts are integer piasters; only the posted journal ledger is authoritative.
"""
from __future__ import annotations

import sqlite3


def reconcile_fee_liability(c: sqlite3.Connection) -> dict:
    """Return independent accrual-vs-ledger evidence without changing database state.

    Matching aggregate amounts alone is insufficient: equal and opposite unknown
    2320 postings or stale/unposted decision journals must still fail the gate.
    """
    account = c.execute("SELECT id,class,control,active FROM gl_accounts WHERE code='2320'").fetchone()
    account_present = account is not None
    account_valid = bool(account_present and account['class'] == 'liability'
                         and account['control'] == '' and account['active'] == 1)
    expense = c.execute("SELECT class,control,active FROM gl_accounts WHERE code='5196'").fetchone()
    expense_account_valid = bool(expense and expense['class'] == 'expense'
                                 and expense['control'] == '' and expense['active'] == 1)
    totals = c.execute('''
        SELECT COALESCE(SUM(CASE WHEN r.id IS NULL THEN d.amount_piasters ELSE 0 END), 0) liability,
               COUNT(*) approvals,
               COUNT(r.id) reversals
        FROM service_fee_decisions d
        LEFT JOIN service_fee_reversals r ON r.decision_id=d.id
        WHERE d.decision='approved'
    ''').fetchone()
    balance = c.execute('''
        SELECT COALESCE(SUM(l.credit_piasters-l.debit_piasters),0)
        FROM gl_lines l JOIN gl_journals j ON j.id=l.journal_id
        JOIN gl_accounts a ON a.id=l.account_id
        WHERE a.code='2320' AND j.status='posted'
    ''').fetchone()[0]
    broken_approvals = c.execute('''
        SELECT COUNT(*) FROM service_fee_decisions d WHERE d.decision='approved'
          AND (COALESCE((SELECT SUM(l.credit_piasters-l.debit_piasters)
                  FROM gl_journals j JOIN gl_lines l ON l.journal_id=j.id
                  JOIN gl_accounts a ON a.id=l.account_id
                  WHERE j.id=d.journal_id AND j.status='posted' AND a.code='2320'),0)
            !=d.amount_piasters OR (SELECT COUNT(*) FROM gl_lines l
                  JOIN gl_accounts a ON a.id=l.account_id
                  JOIN gl_journals j ON j.id=l.journal_id
                  WHERE j.id=d.journal_id AND j.status='posted' AND a.code='2320') != 1
            OR (SELECT COUNT(*) FROM gl_lines l WHERE l.journal_id=d.journal_id) != 2
            OR COALESCE((SELECT SUM(l.debit_piasters-l.credit_piasters)
                FROM gl_journals j JOIN gl_lines l ON l.journal_id=j.id
                JOIN gl_accounts a ON a.id=l.account_id
                WHERE j.id=d.journal_id AND j.status='posted' AND a.code='5196'),0)
                != d.amount_piasters
            OR (SELECT COUNT(*) FROM gl_lines l
                JOIN gl_journals j ON j.id=l.journal_id
                JOIN gl_accounts a ON a.id=l.account_id
                WHERE j.id=d.journal_id AND j.status='posted' AND a.code='5196') != 1)
    ''').fetchone()[0]
    broken_reversals = c.execute('''
        SELECT COUNT(*) FROM service_fee_reversals r
        JOIN service_fee_decisions d ON d.id=r.decision_id
        WHERE d.decision!='approved' OR COALESCE((SELECT SUM(l.debit_piasters-l.credit_piasters)
                  FROM gl_journals j JOIN gl_lines l ON l.journal_id=j.id
                  JOIN gl_accounts a ON a.id=l.account_id
                  WHERE j.id=r.journal_id AND j.status='posted' AND a.code='2320'),0)
            !=d.amount_piasters OR (SELECT COUNT(*) FROM gl_lines l
                  JOIN gl_accounts a ON a.id=l.account_id
                  JOIN gl_journals j ON j.id=l.journal_id
                  WHERE j.id=r.journal_id AND j.status='posted' AND a.code='2320') != 1
            OR (SELECT COUNT(*) FROM gl_lines l WHERE l.journal_id=r.journal_id) != 2
            OR COALESCE((SELECT SUM(l.credit_piasters-l.debit_piasters)
                FROM gl_journals j JOIN gl_lines l ON l.journal_id=j.id
                JOIN gl_accounts a ON a.id=l.account_id
                WHERE j.id=r.journal_id AND j.status='posted' AND a.code='5196'),0)
                != d.amount_piasters
            OR (SELECT COUNT(*) FROM gl_lines l
                JOIN gl_journals j ON j.id=l.journal_id
                JOIN gl_accounts a ON a.id=l.account_id
                WHERE j.id=r.journal_id AND j.status='posted' AND a.code='5196') != 1
    ''').fetchone()[0]
    unlinked_postings = c.execute('''
        SELECT COUNT(DISTINCT j.id)
        FROM gl_journals j JOIN gl_lines l ON l.journal_id=j.id
        JOIN gl_accounts a ON a.id=l.account_id
        WHERE a.code='2320' AND j.status='posted'
          AND NOT EXISTS(SELECT 1 FROM service_fee_decisions d
                         WHERE d.decision='approved' AND d.journal_id=j.id)
          AND NOT EXISTS(SELECT 1 FROM service_fee_reversals r WHERE r.journal_id=j.id)
    ''').fetchone()[0]
    liability = int(totals['liability'])
    ledger = int(balance)
    difference = ledger - liability
    return {
        'account_present': account_present,
        'account_valid': account_valid,
        'expense_account_valid': expense_account_valid,
        'liability_piasters': liability,
        'gl_balance_piasters': ledger,
        'difference_piasters': difference,
        'approved_count': int(totals['approvals']),
        'reversed_count': int(totals['reversals']),
        'broken_approvals': int(broken_approvals),
        'broken_reversals': int(broken_reversals),
        'unlinked_postings': int(unlinked_postings),
        'matched': bool(account_valid and expense_account_valid and liability >= 0 and difference == 0
                        and not (broken_approvals or broken_reversals or unlinked_postings)),
        'certified': False,
    }
