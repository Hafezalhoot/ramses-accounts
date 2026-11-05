"""Individual service fee proposals and independently approved payable accruals.

Reads derive proposals from immutable pricing terms and current invoice receipts.
Only an explicit individual approval creates a payable and balanced GL journal.
"""
from __future__ import annotations

import hashlib
import heapq
import json
import sqlite3
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from fractions import Fraction
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import ledger
from app import (audit, c_piasters, db, fail, get_user, month_open, require,
                 require_reviewer_shift_fund, stamp)
from billing import (cairo_today, case_scope, invoice_receipted, remember,
                     repeat, request_key, trim)

router = APIRouter(prefix='/api/service-fees', tags=['service-fees'])


def _split(total, weights):
    """Largest remainder allocation, with input order breaking equal remainders."""
    weight = sum(weights)
    if weight <= 0:
        return [0] * len(weights)
    parts = [total * value // weight for value in weights]
    left = total - sum(parts)
    order = sorted(range(len(weights)), key=lambda i: (-(total * weights[i] % weight), i))
    for index in order[:left]:
        parts[index] += 1
    return parts


def _allocate_received(total, weights):
    """Exact highest-averages allocation; later receipts never reduce a line.

    Largest remainder can retract one line's piaster as the invoice receives
    more cash. D'Hondt is house-monotone. Every lower quota is already selected
    by its quotient ranking; fewer than len(weights) remaining seats require
    exact rational comparisons, independently of the monetary amount.
    """
    denominator = sum(weights)
    if denominator <= 0:
        return [0] * len(weights)
    parts = [total * weight // denominator for weight in weights]
    next_seats = [(-Fraction(weight, parts[index] + 1), index)
                  for index, weight in enumerate(weights) if weight > 0]
    heapq.heapify(next_seats)
    for _ in range(total - sum(parts)):
        _, index = heapq.heappop(next_seats)
        parts[index] += 1
        heapq.heappush(next_seats, (-Fraction(weights[index], parts[index] + 1), index))
    return parts


def calculate_rule_shares(c, rule, performer_ids, base_piasters, quantity=1):
    """Project total rule shares, using the supplied full percentage basis.

    ``base_piasters`` already includes quantity; percent never multiplies it.
    Fixed amounts share each occurrence separately, then sum across quantity. The
    caller chooses gross/net/received basis. Eligibility uses actual performers
    except an explicit person/always rule. Historical inactive people remain
    entitled to fees earned under their accepted service contract.
    """
    if not isinstance(rule, dict) or not isinstance(quantity, int) or quantity < 1:
        fail('قاعدة أتعاب غير صالحة')
    if rule.get('distribution', 'shared') != 'shared':
        fail('توزيع الأتعاب غير صالح')
    if (not isinstance(base_piasters, (int, Decimal)) or base_piasters < 0
            or (isinstance(base_piasters, Decimal) and not base_piasters.is_finite())):
        fail('أساس احتساب الأتعاب غير صالح')
    target = rule.get('target')
    when = rule.get('when', 'performed')
    if target not in ('person', 'category') or when not in ('always', 'performed') or (when == 'always' and target != 'person'):
        fail('جهة استحقاق الأتعاب غير صالحة')
    try:
        performers = sorted(set(int(person_id) for person_id in performer_ids))
        person_id = int(rule.get('person_id', 0)) if target == 'person' else None
    except (TypeError, ValueError):
        fail('مقدمو الخدمة غير صالحين')
    if target == 'person':
        ids = [person_id] if when == 'always' or person_id in performers else []
    else:
        ids = performers
    people = []
    if ids:
        people = c.execute('SELECT id,name,category FROM pricing_people WHERE id IN (' + ','.join('?' for _ in ids) + ') ORDER BY id', ids).fetchall()
    if target == 'category':
        category = rule.get('category')
        if category not in ('doctor', 'nurse', 'technician', 'other'):
            fail('فئة مقدم الخدمة غير صالحة')
        people = [person for person in people if person['category'] == category]
    kind = rule.get('kind', 'percent')
    if kind == 'fixed':
        occurrence_amounts = [c_piasters(rule.get('fixed_amount'), allow_zero=True)] * quantity
    elif kind == 'percent':
        try:
            percentage = Decimal(str(rule.get('percentage', '0')))
            if not percentage.is_finite() or not 0 <= percentage <= 100:
                fail('نسبة الأتعاب غير صالحة')
        except (InvalidOperation, ValueError, TypeError):
            fail('نسبة الأتعاب غير صالحة')
        bases = _split(base_piasters, [1] * quantity) if isinstance(base_piasters, int) else [base_piasters / quantity] * quantity
        occurrence_amounts = [int((Decimal(base) * percentage / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                              for base in bases]
    else:
        fail('نوع الأتعاب غير صالح')
    amounts = [0] * len(people)
    for amount in occurrence_amounts:
        amounts = [prior + share for prior, share in zip(amounts, _split(amount, [1] * len(people)))]
    return [{'person_id': person['id'], 'person_name': person['name'], 'amount_piasters': amount}
            for person, amount in zip(people, amounts) if amount > 0]


def has_active_approvals(c, invoice_id):
    """Correction guard: approved fees must be independently reversed first."""
    return bool(c.execute('''SELECT 1 FROM service_fee_decisions d
        WHERE d.invoice_id=? AND d.decision='approved'
          AND NOT EXISTS(SELECT 1 FROM service_fee_reversals r WHERE r.decision_id=d.id)
        LIMIT 1''', (invoice_id,)).fetchone())


def _scope(c, user, case_id, invoice_id, *, approve=False):
    case = case_scope(c, user, case_id)
    point = c.execute('SELECT fund_id FROM billing_points WHERE id=?', (case['default_point_id'],)).fetchone()
    fund_ids = {point['fund_id']} if point and point['fund_id'] else set()
    # The current receipt assignment controls visibility, including corrections.
    fund_ids.update(row['fund_id'] for row in c.execute('''
        SELECT DISTINCT p.fund_id FROM billing_collections b
        JOIN billing_payment_parts p ON p.collection_id=b.id
        LEFT JOIN financial_collection_reallocations r ON r.collection_id=b.id
        WHERE (b.kind='invoice' AND COALESCE(r.to_invoice_id,b.invoice_id)=?)
           OR (b.kind='advance' AND COALESCE(r.to_case_id,b.case_id)=?
             AND EXISTS(SELECT 1 FROM billing_advance_allocations a WHERE a.invoice_id=?))
        ''', (invoice_id, case_id, invoice_id)))
    fund_ids.update(row['from_fund_id'] for row in c.execute('''
        SELECT v.from_fund_id FROM late_cash_allocations a
        JOIN vouchers v ON v.id=a.voucher_id WHERE a.invoice_id=?
        UNION
        SELECT v.from_fund_id FROM late_mixed_clearance_lines l
        JOIN late_mixed_clearances m ON m.id=l.clearance_id
        JOIN vouchers v ON v.id=m.voucher_id
        WHERE l.invoice_id=? AND l.line_kind='patient_receipt'
        ''', (invoice_id, invoice_id)) if row['from_fund_id'] is not None)
    for fund_id in sorted(fund_ids):
        require_reviewer_shift_fund(c, user, fund_id, approve=approve)
    return case


def _visible(c, user, case_id, invoice_id):
    try:
        _scope(c, user, case_id, invoice_id)
        return True
    except HTTPException as error:
        if error.status_code in (403, 404):
            return False
        raise


def _invoice_received(c, invoice):
    credits = c.execute("SELECT COALESCE(SUM(amount_piasters),0) FROM billing_credit_requests WHERE invoice_id=? AND status='approved'", (invoice['id'],)).fetchone()[0]
    if credits > invoice['total_piasters']:
        fail('إشعارات دائنة تتجاوز قيمة الفاتورة', 500)
    received = invoice_receipted(c, invoice['id'])
    for table in ('billing_advance_allocations', 'late_cash_allocations'):
        received += c.execute('SELECT COALESCE(SUM(amount_piasters),0) FROM ' + table + ' WHERE invoice_id=?', (invoice['id'],)).fetchone()[0]
    received += c.execute("SELECT COALESCE(SUM(amount_piasters),0) FROM late_mixed_clearance_lines WHERE invoice_id=? AND line_kind='patient_receipt'", (invoice['id'],)).fetchone()[0]
    net = max(0, invoice['total_piasters'] - credits)
    return min(max(0, received), net), credits


def _invoice_proposals(c, invoice, selector=None):
    """Yield fee deltas deterministically; selector bypasses display pagination."""
    rows = c.execute('''SELECT l.id line_id,l.case_id,l.service_name_snapshot,l.department_id,
        l.quantity,l.state,dl.total_piasters,t.gross_piasters,t.net_piasters,t.terms_json,
        o.created_by maker_id,b.case_no
        FROM billing_invoice_draft_lines dl JOIN billing_case_lines l ON l.id=dl.case_line_id
        JOIN billing_cases b ON b.id=l.case_id
        LEFT JOIN pricing_line_terms t ON t.case_line_id=l.id
        LEFT JOIN pricing_orders o ON o.id=t.order_id
        WHERE dl.draft_id=? ORDER BY dl.id''', (invoice['draft_id'],)).fetchall()
    received, credits = _invoice_received(c, invoice)
    effective_nets = _split(max(0, invoice['total_piasters'] - credits), [r['total_piasters'] for r in rows])
    received_lines = _allocate_received(received, effective_nets)
    history = {}
    for row in c.execute('''SELECT d.*,r.id reversal_id FROM service_fee_decisions d
        LEFT JOIN service_fee_reversals r ON r.decision_id=d.id
        WHERE d.invoice_id=? ORDER BY d.id''', (invoice['id'],)):
        key = (row['line_id'], row['occurrence_no'], row['rule_index'], row['person_id'])
        history.setdefault(key, []).append(row)
    for row, line_net, line_received in zip(rows, effective_nets, received_lines):
        if row['terms_json'] is None or row['state'] != 'fulfilled' or (selector and row['line_id'] != selector[0]):
            continue
        terms = json.loads(row['terms_json'])
        quantity = row['quantity']
        occurrence_people = {entry['occurrence_no']: entry['person_ids']
                             for entry in terms.get('occurrence_performers', [])}
        gross_parts = _split(row['gross_piasters'], [1] * quantity)
        net_parts = _split(line_net, [1] * quantity)
        collected_parts = _split(line_received, [1] * quantity)
        # A line with fractional piasters receives deterministic occurrence shares.
        # Cache rule math for equal occurrence bases without extra people queries.
        share_cache = {}
        occurrences = [selector[1] - 1] if selector and 1 <= selector[1] <= quantity else range(quantity) if not selector else []
        for occurrence in occurrences:
            performer_ids = occurrence_people.get(occurrence + 1, terms.get('performer_ids', []))
            for rule_index, rule in enumerate(terms.get('rules', [])):
                if selector and rule_index != selector[2]:
                    continue
                kind = rule.get('kind', 'percent')
                base = collected_parts[occurrence]
                if kind == 'percent' and not rule.get('discount_affects', True):
                    # Use the line's collection fraction: discounted occurrence
                    # net may round to zero while its gross fee remains earned.
                    base = Decimal(gross_parts[occurrence]) * line_received / line_net if line_net else 0
                cache_key = (rule_index, base, tuple(sorted(set(performer_ids))))
                if cache_key not in share_cache:
                    share_cache[cache_key] = calculate_rule_shares(c, rule, performer_ids, base)
                for share in share_cache[cache_key]:
                    if selector and share['person_id'] != selector[3]:
                        continue
                    key = (row['line_id'], occurrence + 1, rule_index, share['person_id'])
                    prior = history.get(key, [])
                    if any(d['decision'] == 'rejected' or d['reversal_id'] is not None for d in prior):
                        continue
                    approved = sum(d['amount_piasters'] for d in prior if d['decision'] == 'approved')
                    delta = share['amount_piasters'] - approved
                    if delta <= 0:
                        continue
                    item = {'line_id': row['line_id'], 'occurrence_no': occurrence + 1,
                            'rule_index': rule_index, 'person_id': share['person_id'], 'person_name': share['person_name'],
                            'invoice_id': invoice['id'], 'invoice_no': invoice['invoice_no'],
                            'case_id': row['case_id'], 'case_no': row['case_no'], 'service_name': row['service_name_snapshot'],
                            'amount_piasters': delta, 'collected_piasters': collected_parts[occurrence],
                            'basis': 'collected', 'kind': kind, 'gross_piasters': gross_parts[occurrence],
                            'net_piasters': net_parts[occurrence], 'previously_approved_piasters': approved}
                    evidence = {'proposal': item, 'rule': rule, 'performer_ids': performer_ids,
                                'terms': terms, 'invoice_received_piasters': received, 'invoice_credit_piasters': credits,
                                'maker_id': row['maker_id'], 'department_id': row['department_id'],
                                'prior_decision_ids': [d['id'] for d in prior]}
                    item['calculation_hash'] = hashlib.sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
                    yield item, evidence


@router.get('/queue')
def queue(limit: int = Query(500, ge=1, le=2000), user=Depends(get_user), c: sqlite3.Connection=Depends(db)):
    require(user, 'owner', 'reviewer')
    items = []
    count = 0
    for invoice in c.execute('''SELECT DISTINCT i.* FROM billing_invoices i
        JOIN billing_invoice_draft_lines dl ON dl.draft_id=i.draft_id
        JOIN pricing_line_terms t ON t.case_line_id=dl.case_line_id ORDER BY i.id''').fetchall():
        if not _visible(c, user, invoice['case_id'], invoice['id']):
            continue
        for item, _ in _invoice_proposals(c, invoice):
            count += 1
            if len(items) < limit:
                items.append(item)
    return {'items': items, 'total_proposals': count, 'truncated': count > len(items)}


class DecisionForm(BaseModel):
    line_id: int = Field(gt=0)
    occurrence_no: int = Field(gt=0)
    rule_index: int = Field(ge=0)
    person_id: int = Field(gt=0)
    expected_amount_piasters: int = Field(gt=0)
    calculation_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    decision: Literal['approve', 'reject']
    reason: str
    request_id: str


class ReverseForm(BaseModel):
    reason: str
    request_id: str


def _decision_result(row, *, replayed=False):
    return {'id': row['id'], 'status': row['decision'], 'amount_piasters': row['amount_piasters'],
            'journal_id': row['journal_id'], 'replayed': replayed}


def _invoice_for_line(c, line_id):
    row = c.execute('''SELECT i.* FROM billing_invoices i
        JOIN billing_invoice_draft_lines dl ON dl.draft_id=i.draft_id
        JOIN pricing_line_terms t ON t.case_line_id=dl.case_line_id
        WHERE dl.case_line_id=?''', (line_id,)).fetchone()
    if not row:
        fail('خدمة مسعرة منفذة ومفوترة مطلوبة للمراجعة', 404)
    return row


def _accounts(c):
    for code, name, category in (('5196', 'أتعاب خدمات معتمدة مستحقة', 'expense'), ('2320', 'مستحقات مقدمي الخدمات المعتمدة', 'liability')):
        c.execute('INSERT OR IGNORE INTO gl_accounts(code,name,class) VALUES(?,?,?)', (code, name, category))
        account = c.execute('SELECT id,class,active,control FROM gl_accounts WHERE code=?', (code,)).fetchone()
        if account['class'] != category or not account['active'] or account['control']:
            fail('حساب أتعاب الخدمات يحتاج مراجعة دليل الحسابات', 409)
    return ledger.account_by_code(c, '5196'), ledger.account_by_code(c, '2320')


@router.post('/decisions')
def decide(body: DecisionForm, user=Depends(get_user), c: sqlite3.Connection=Depends(db)):
    require(user, 'owner', 'reviewer')
    key = request_key(body.request_id)
    reason = trim(body.reason, 'سبب المراجعة', 8, 500)
    with c:
        c.execute('BEGIN IMMEDIATE')
        invoice = _invoice_for_line(c, body.line_id)
        _scope(c, user, invoice['case_id'], invoice['id'], approve=True)
        previous, fingerprint = repeat(c, key, 'service_fee_decision', user['id'], body.model_dump())
        if previous:
            return _decision_result(c.execute('SELECT * FROM service_fee_decisions WHERE id=?', (previous,)).fetchone(), replayed=True)
        maker = c.execute('''SELECT o.created_by FROM pricing_line_terms t
            JOIN pricing_orders o ON o.id=t.order_id WHERE t.case_line_id=?''', (body.line_id,)).fetchone()[0]
        if maker == user['id']:
            fail('من أنشأ طلب الخدمة لا يعتمد أو يرفض مستحقاته بنفسه', 403)
        selector = (body.line_id, body.occurrence_no, body.rule_index, body.person_id)
        candidates = list(_invoice_proposals(c, invoice, selector))
        if not candidates:
            fail('تغير اقتراح الأتعاب أو سبق حسمه؛ أعد تحميل قائمة المراجعة', 409)
        item, evidence = candidates[0]
        if body.expected_amount_piasters != item['amount_piasters'] or body.calculation_hash != item['calculation_hash']:
            fail('تغير أساس الأتعاب منذ المعاينة؛ أعد تحميل قائمة المراجعة', 409)
        journal = None
        if body.decision == 'approve':
            day = cairo_today()
            month_open(c, day[:7])
            expense, payable = _accounts(c)
            amount = item['amount_piasters']
            journal = ledger._journal(c, entry_date=day, memo='اعتماد أتعاب خدمة ' + invoice['invoice_no'],
                origin='manual', source_id=None, created_by=maker, reviewed_by=user['id'],
                lines=[(expense, amount, 0, evidence['department_id']), (payable, 0, amount, evidence['department_id'])])
        status = 'approved' if body.decision == 'approve' else 'rejected'
        cur = c.execute('''INSERT INTO service_fee_decisions(line_id,invoice_id,occurrence_no,rule_index,person_id,
            person_name_snapshot,amount_piasters,calculation_hash,snapshot_json,decision,reason,maker_id,decided_by,decided_at,journal_id)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (body.line_id, invoice['id'], body.occurrence_no, body.rule_index,
            body.person_id, item['person_name'], item['amount_piasters'], item['calculation_hash'],
            json.dumps(evidence, sort_keys=True, ensure_ascii=False), status, reason, maker, user['id'], stamp(), journal))
        remember(c, key, 'service_fee_decision', user['id'], fingerprint, cur.lastrowid)
        audit(c, user['id'], 'service_fee_' + status, 'service_fee_decision', cur.lastrowid,
              {'invoice_id': invoice['id'], 'person_id': body.person_id, 'amount_piasters': item['amount_piasters'], 'journal_id': journal})
        return _decision_result(c.execute('SELECT * FROM service_fee_decisions WHERE id=?', (cur.lastrowid,)).fetchone())


@router.post('/decisions/{decision_id}/reverse')
def reverse(decision_id: int, body: ReverseForm, user=Depends(get_user), c: sqlite3.Connection=Depends(db)):
    require(user, 'owner', 'reviewer')
    key = request_key(body.request_id)
    reason = trim(body.reason, 'سبب العكس', 8, 500)
    with c:
        c.execute('BEGIN IMMEDIATE')
        decision = c.execute('SELECT * FROM service_fee_decisions WHERE id=?', (decision_id,)).fetchone()
        if not decision:
            fail('قرار الأتعاب غير موجود', 404)
        invoice = c.execute('SELECT * FROM billing_invoices WHERE id=?', (decision['invoice_id'],)).fetchone()
        _scope(c, user, invoice['case_id'], invoice['id'], approve=True)
        previous, fingerprint = repeat(c, key, 'service_fee_reverse', user['id'], {'decision_id': decision_id, **body.model_dump()})
        if previous:
            row = c.execute('SELECT * FROM service_fee_reversals WHERE id=?', (previous,)).fetchone()
            return {'id': row['id'], 'decision_id': decision_id, 'status': 'reversed', 'journal_id': row['journal_id'], 'replayed': True}
        if user['id'] in (decision['maker_id'], decision['decided_by']):
            fail('عكس المستحقات يتطلب مراجعًا مستقلًا عن منشئ الطلب ومعتمد الأتعاب', 403)
        if decision['decision'] != 'approved' or c.execute('SELECT 1 FROM service_fee_reversals WHERE decision_id=?', (decision_id,)).fetchone():
            fail('يمكن عكس اعتماد قائم مرة واحدة فقط', 409)
        day = cairo_today()
        month_open(c, day[:7])
        original_lines = c.execute('SELECT * FROM gl_lines WHERE journal_id=? ORDER BY id', (decision['journal_id'],)).fetchall()
        journal = ledger._journal(c, entry_date=day, memo='عكس اعتماد أتعاب #' + str(decision_id), origin='manual_reversal',
            source_id=None, reversal_of=decision['journal_id'], created_by=user['id'], reviewed_by=user['id'],
            lines=[(row['account_id'], row['credit_piasters'], row['debit_piasters'], row['department_id']) for row in original_lines])
        cur = c.execute('INSERT INTO service_fee_reversals(decision_id,reason,reversed_by,reversed_at,journal_id) VALUES(?,?,?,?,?)',
                        (decision_id, reason, user['id'], stamp(), journal))
        remember(c, key, 'service_fee_reverse', user['id'], fingerprint, cur.lastrowid)
        audit(c, user['id'], 'service_fee_reversed', 'service_fee_reversal', cur.lastrowid, {'decision_id': decision_id, 'journal_id': journal})
        return {'id': cur.lastrowid, 'decision_id': decision_id, 'status': 'reversed', 'journal_id': journal, 'replayed': False}


@router.get('/balances')
def balances(limit: int = Query(1000, ge=1, le=5000), user=Depends(get_user), c: sqlite3.Connection=Depends(db)):
    require(user, 'owner', 'reviewer')
    rows = c.execute('''SELECT d.*,r.id reversal_id,i.case_id,i.invoice_no,b.case_no,l.service_name_snapshot service_name
        FROM service_fee_decisions d JOIN billing_invoices i ON i.id=d.invoice_id
        JOIN billing_cases b ON b.id=i.case_id JOIN billing_case_lines l ON l.id=d.line_id
        LEFT JOIN service_fee_reversals r ON r.decision_id=d.id ORDER BY d.id DESC''').fetchall()
    visible = {}
    totals = {}
    decisions = []
    count = 0
    for row in rows:
        if row['invoice_id'] not in visible:
            visible[row['invoice_id']] = _visible(c, user, row['case_id'], row['invoice_id'])
        if not visible[row['invoice_id']]:
            continue
        count += 1
        if row['decision'] == 'approved' and row['reversal_id'] is None:
            entry = totals.setdefault(row['person_id'], {'person_id': row['person_id'], 'person_name': row['person_name_snapshot'], 'amount_piasters': 0})
            entry['amount_piasters'] += row['amount_piasters']
        if len(decisions) < limit:
            item = {key: row[key] for key in ('id', 'line_id', 'occurrence_no', 'rule_index', 'person_id', 'invoice_id', 'invoice_no',
                    'case_no', 'service_name', 'amount_piasters', 'decision', 'reason', 'decided_by', 'decided_at', 'journal_id', 'reversal_id')}
            item.update(person_name=row['person_name_snapshot'], reversed=row['reversal_id'] is not None)
            decisions.append(item)
    return {'items': [totals[key] for key in sorted(totals)], 'decisions': decisions,
            'total_decisions': count, 'truncated': count > len(decisions)}
