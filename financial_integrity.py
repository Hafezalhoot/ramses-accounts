"""Patient subledger / general-ledger integrity gates.

Amounts are integer piasters. Never infer that a balanced trial balance means
that the patient or cashier subledgers agree with the general ledger.
"""
from __future__ import annotations

from collections import defaultdict

# The human journal form must not create receivables, advance/refund liabilities,
# payroll liabilities, cash variances or medical revenue without source documents.
PROTECTED_CODES = frozenset({
    '1200', '2300', '2310', '2350', '1190', '2190',
    '2110', '1120', '4100', '4195',
})


def forbidden_manual_lines(c, lines):
    """Return account codes that may only be booked via validated workflows."""
    ids = tuple({int(x[0]) for x in lines})
    if not ids:
        return []
    placeholders = ','.join('?' for _ in ids)
    return [r['code'] for r in c.execute(
        f'SELECT code FROM gl_accounts WHERE id IN ({placeholders}) '
        "AND (control!='' OR code IN (" + ','.join('?' for _ in PROTECTED_CODES) + '))',
        (*ids, *sorted(PROTECTED_CODES))
    )]


def journal_source(c, journal_id):
    """Detect *every* source-table FK, including old journals mislabeled manual.

    Discover journal_id columns at run time rather than maintain an incomplete
    blacklist. Source objects are immutable; no migration of posted GL is needed.
    """
    for table, in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        if table in ('gl_journals', 'gl_lines'):
            continue
        # Only schema identifiers from SQLite itself, validated before interpolation.
        if not table.replace('_', '').isalnum():
            continue
        if not any(r['name'] == 'journal_id' for r in c.execute(f'PRAGMA table_info("{table}")')):
            continue
        row = c.execute(f'SELECT 1 FROM "{table}" WHERE journal_id=? LIMIT 1', (journal_id,)).fetchone()
        if row:
            return table
    return None


def reversal_guard(c, original_id):
    """Never reverse source-backed entries, even if a legacy journal says manual.

    This is checked both when requesting AND when approving an old pending
    reversal to prevent a previously created reversal from bypassing the fix.
    """
    j = c.execute('SELECT * FROM gl_journals WHERE id=?', (original_id,)).fetchone()
    if not j or j['origin'] != 'manual' or j['status'] != 'posted':
        return 'العكس اليدوي متاح فقط لقيد يدوي أصلي معتمد'
    link = journal_source(c, original_id)
    if link:
        return 'هذا القيد مرتبط بمستند تشغيلي ولا يجوز عكسه يدويًا؛ استخدم تصحيحًا بمستند مستقل'
    lines = c.execute('SELECT account_id FROM gl_lines WHERE journal_id=?', (original_id,)).fetchall()
    if forbidden_manual_lines(c, [(r['account_id'],) for r in lines]):
        return 'قيد يتضمن حسابًا رقابيًا محميًا؛ لا يمكن عكسه دون دورة تصحيح مستندية'
    return None


def _group(c, query, args):
    return {r[0]: int(r[1]) for r in c.execute(query, args)}


def patient_reconciliation(c, period):
    """Compare as-of signed GL control balances with independently derived
    invoice, advance and refund subledgers. Include corrections only when their
    effective posting month has reached the requested period.

    This intentionally *does not* claim to reconcile inventory, payroll,
    suspense (2350), bank, or physical tills; they need separate close gates.
    """
    if len(period) != 7 or period[4] != '-' or not period[:4].isdigit():
        raise ValueError('Invalid accounting month')
    invoices = {r['id']: int(r['total_piasters']) for r in c.execute(
        'SELECT id,total_piasters FROM billing_invoices WHERE substr(issued_date,1,7)<=?', (period,))}
    paid = _group(c, '''SELECT CASE WHEN r.id IS NOT NULL AND substr(r.effective_date,1,7)<=?
                    THEN r.to_invoice_id ELSE b.invoice_id END invoice_id,
            SUM(p.amount_piasters) amount
       FROM billing_collections b
       JOIN billing_payment_parts p ON p.collection_id=b.id
       JOIN vouchers v ON v.id=p.voucher_id AND v.status='approved'
       JOIN gl_journals j ON j.origin='voucher' AND j.source_id=v.id AND j.status='posted'
       LEFT JOIN financial_collection_reallocations r ON r.collection_id=b.id
       WHERE b.kind='invoice' AND substr(j.entry_date,1,7)<=?
       GROUP BY 1''', (period,period))
    advance_alloc = _group(c, '''SELECT a.invoice_id,SUM(a.amount_piasters)
       FROM billing_advance_allocations a JOIN gl_journals j ON j.id=a.journal_id
       WHERE j.status='posted' AND substr(j.entry_date,1,7)<=? GROUP BY a.invoice_id''', (period,))
    late_alloc = _group(c, '''SELECT a.invoice_id,SUM(a.amount_piasters)
       FROM late_cash_allocations a JOIN gl_journals j ON j.id=a.journal_id
       WHERE j.status='posted' AND substr(j.entry_date,1,7)<=? GROUP BY a.invoice_id''', (period,))
    mixed = _group(c, '''SELECT l.invoice_id,SUM(l.amount_piasters)
       FROM late_mixed_clearance_lines l
       JOIN late_mixed_clearances m ON m.id=l.clearance_id
       JOIN gl_journals j ON j.id=m.journal_id
       WHERE l.line_kind='patient_receipt' AND j.status='posted'
       AND substr(j.entry_date,1,7)<=? GROUP BY l.invoice_id''', (period,))
    credits = _group(c, '''SELECT r.invoice_id,SUM(r.amount_piasters)
       FROM billing_credit_requests r JOIN gl_journals j ON j.id=r.journal_id
       WHERE r.status='approved' AND j.status='posted' AND substr(j.entry_date,1,7)<=?
       GROUP BY r.invoice_id''', (period,))
    all_allocations = (paid,advance_alloc,late_alloc,mixed,credits)
    unexpected = sorted({invoice_id for group in all_allocations for invoice_id in group if invoice_id not in invoices})
    invoice_due = 0
    credit_overpaid = 0
    overcredited = []
    for iid, total in invoices.items():
        if credits.get(iid,0) > total:
            overcredited.append(iid)
        signed_due = total - sum(group.get(iid,0) for group in all_allocations)
        invoice_due += max(0, signed_due)
        credit_overpaid += max(0, -signed_due)
    advances = c.execute('''SELECT COALESCE(SUM(p.amount_piasters),0)
       FROM billing_collections b JOIN billing_payment_parts p ON p.collection_id=b.id
       JOIN vouchers v ON v.id=p.voucher_id AND v.status='approved'
       JOIN gl_journals j ON j.origin='voucher' AND j.source_id=v.id AND j.status='posted'
       WHERE b.kind='advance' AND substr(j.entry_date,1,7)<=?''',(period,)).fetchone()[0]
    advance_alloc_total = sum(advance_alloc.values())
    refunded = _group(c, '''SELECT r.source, COALESCE(SUM(r.amount_piasters),0)
       FROM billing_refund_requests r
       JOIN vouchers v ON v.id=r.voucher_id AND v.status='approved'
       JOIN gl_journals j ON j.origin='voucher' AND j.source_id=v.id AND j.status='posted'
       WHERE r.status='paid' AND substr(j.entry_date,1,7)<=?
       GROUP BY r.source''', (period,))
    advance_due = advances - advance_alloc_total - refunded.get('advance',0)
    credit_due = credit_overpaid - refunded.get('credit',0)
    expected = {'1200':invoice_due, '2300':-advance_due, '2310':-credit_due}
    ledger = _group(c, '''SELECT a.code,COALESCE(SUM(l.debit_piasters-l.credit_piasters),0)
       FROM gl_accounts a LEFT JOIN gl_lines l ON l.account_id=a.id
       LEFT JOIN gl_journals j ON j.id=l.journal_id
       WHERE a.code IN ('1200','2300','2310')
       AND (j.id IS NULL OR (j.status='posted' AND substr(j.entry_date,1,7)<=?))
       GROUP BY a.code''',(period,))
    names={'1200':'ذمم المرضى', '2300':'مقدمات المرضى', '2310':'التزامات رد مستحقات المرضى'}
    rows=[{'code':code,'name':names[code], 'expected_piasters':expected[code],
           'ledger_piasters':ledger.get(code,0),
           'difference_piasters':ledger.get(code,0)-expected[code],
           'matched':ledger.get(code,0)==expected[code]}
          for code in ('1200','2300','2310')]
    return {'period':period,'matched':all(r['matched'] for r in rows) and not unexpected and not overcredited,
            'checks':rows,'orphan_allocations':unexpected[:20],
            'overcredited_invoices':overcredited[:20],
            'scope':'ذمم ومقدمات والتزامات المرضى فقط؛ لا يشمل جرد الخزن والبنوك والمخزون والأجور'}
