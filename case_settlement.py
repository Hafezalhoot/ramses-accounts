"""G2P: financial clearance of an extended case (NOT clinical discharge).

No cash movement and no GL posting; invoices and refunds must already have been settled.
Independent approval re-checks balances under an IMMEDIATE SQLite transaction.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app import audit, db, fail, get_user, month_open, require, stamp
from billing import (available_advance, cairo_today, case_scope, invoice_due,
                     refundable_credit, remember, repeat, request_key, trim)

router = APIRouter(prefix='/api/case-settlement', tags=['Case finance clearance'])
EXTENDED = ('inpatient', 'nicu', 'operation')


class ClearanceRequest(BaseModel):
    evidence_reference: str = Field(min_length=8, max_length=180)
    note: str = Field(min_length=12, max_length=500)
    request_id: str
    mode: Literal['settled','no_charge'] = 'settled'


class ClearanceDecision(BaseModel):
    decision: Literal['approve', 'reject']
    note: str = Field(min_length=12, max_length=500)


def case_preflight(c, case):
    """Compute settlement from immutable subledgers, not requester's estimates."""
    case_id = case['id']
    invoices = c.execute('SELECT id,total_piasters FROM billing_invoices WHERE case_id=?',
                         (case_id,)).fetchall()
    open_lines = c.execute("SELECT count(*) FROM billing_case_lines WHERE case_id=? AND state='ordered'",
                           (case_id,)).fetchone()[0]
    fulfilled_unbilled = c.execute('''SELECT count(*) FROM billing_case_lines l
        WHERE l.case_id=? AND l.state='fulfilled' AND NOT EXISTS (
        SELECT 1 FROM billing_invoice_draft_lines d
        JOIN billing_invoices i ON i.draft_id=d.draft_id WHERE d.case_line_id=l.id)''',
        (case_id,)).fetchone()[0]
    drafts = c.execute('''SELECT count(*) FROM billing_invoice_drafts d
        WHERE d.case_id=? AND NOT EXISTS (SELECT 1 FROM billing_invoices i WHERE i.draft_id=d.id)''',
        (case_id,)).fetchone()[0]
    pending_credits = c.execute('''SELECT count(*) FROM billing_credit_requests
        WHERE case_id=? AND status='pending' ''', (case_id,)).fetchone()[0]
    unpaid_refunds = c.execute("""SELECT count(*) FROM billing_refund_requests
        WHERE case_id=? AND status IN ('pending','approved')""", (case_id,)).fetchone()[0]
    correction_tickets = c.execute('''SELECT count(*) FROM financial_correction_tickets t
        WHERE t.status IN ('open','needs_evidence','triaged') AND (
          (t.source_type='invoice' AND t.source_id IN
              (SELECT id FROM billing_invoices WHERE case_id=?))
          OR (t.source_type='collection' AND t.source_id IN
              (SELECT id FROM billing_collections WHERE case_id=?)))''',
        (case_id, case_id)).fetchone()[0]
    late = bool(c.execute('SELECT 1 FROM billing_late_cases WHERE case_id=?',
                          (case_id,)).fetchone())
    due = sum(invoice_due(c, i['id']) for i in invoices)
    advance = available_advance(c, case_id)
    credit = refundable_credit(c, case_id)
    original_collections = c.execute('SELECT count(*) FROM billing_collections WHERE case_id=?',
                                     (case_id,)).fetchone()[0]
    all_lines = c.execute("SELECT count(*) FROM billing_case_lines WHERE case_id=? AND state!='cancelled'",
                          (case_id,)).fetchone()[0]
    all_drafts = c.execute('SELECT count(*) FROM billing_invoice_drafts WHERE case_id=?',
                           (case_id,)).fetchone()[0]
    all_refunds = c.execute('SELECT count(*) FROM billing_refund_requests WHERE case_id=?',
                            (case_id,)).fetchone()[0]
    no_charge_ready=(case['kind'] in EXTENDED and case['status']=='open' and not invoices
         and not all_lines and not all_drafts and not original_collections and not all_refunds
         and not correction_tickets and not late)
    reasons = []
    if case['kind'] not in EXTENDED:
        reasons.append('التصفية الحالية للحالات الداخلية والحضانات والعمليات فقط')
    if case['status'] != 'open':
        reasons.append('الحالة ليست مفتوحة للتصفية')
    if not invoices:
        reasons.append('لا توجد فاتورة صادرة؛ لا يمكن اعتبار الحالة مصفاة دون مستند مالي')
    if open_lines:
        reasons.append('هناك خدمات مطلوبة لم يتم إثبات تنفيذها أو إلغائها')
    if fulfilled_unbilled:
        reasons.append('هناك خدمات منفذة لم تدخل فاتورة صادرة')
    if drafts:
        reasons.append('هناك مسودات فواتير لم تصدر بعد')
    if due:
        reasons.append('توجد مديونية على المريض لم تسدد')
    if advance:
        reasons.append('يوجد مقدم غير مخصص أو مردود')
    if credit:
        reasons.append('يوجد رصيد دائن لم تتم تسويته أو رده')
    if pending_credits or unpaid_refunds:
        reasons.append('هناك طلب إشعار دائن أو استرداد لم يحسم')
    if correction_tickets:
        reasons.append('هناك بلاغات تصحيح مالية مفتوحة للحالة')
    if late:
        reasons.append('الحالات المستدركة تحتاج مسار تصفية مستقل قبل الإغلاق')
    return {'case_id':case_id, 'case_no':case['case_no'], 'case_kind':case['kind'],
            'status':case['status'], 'ready':not reasons, 'no_charge_ready':no_charge_ready, 'blockers':reasons,
            'invoice_count':len(invoices), 'collection_count':original_collections,
            'invoiced_piasters':sum(i['total_piasters'] for i in invoices),
            'outstanding_piasters':due, 'advance_available_piasters':advance,
            'credit_refundable_piasters':credit,
            'ordered_services':open_lines, 'fulfilled_unbilled':fulfilled_unbilled,
            'unissued_drafts':drafts, 'pending_credits':pending_credits,
            'pending_refunds':unpaid_refunds, 'pending_corrections':correction_tickets,
            'notice':'إغلاق مالي للذمم فقط؛ ليس خروجًا طبيًا ولا اعتمادًا لجرد النقدية أو كشف البنك.'}


def requests(c, case_id):
    return [dict(r) for r in c.execute('''SELECT id,case_id,status,clearance_mode,evidence_reference,note,
        requested_by,requested_at,reviewed_by,reviewed_at,decision_note,closed_on
        FROM billing_case_clearance_requests WHERE case_id=? ORDER BY id DESC LIMIT 20''',
        (case_id,))]


@router.get('/cases/{case_id}')
def status(case_id: int, user=Depends(get_user), c: sqlite3.Connection=Depends(db)):
    require(user, 'owner', 'reviewer', 'clerk')
    case = case_scope(c, user, case_id)
    return {'preflight':case_preflight(c,case), 'requests':requests(c,case_id)}


@router.post('/cases/{case_id}/request')
def request_clearance(case_id: int, body: ClearanceRequest,
                      user=Depends(get_user), c: sqlite3.Connection=Depends(db)):
    require(user, 'owner', 'clerk')
    key = request_key(body.request_id)
    evidence = trim(body.evidence_reference,'مرجع مستند التصفية أو إلغاء الحجز',8,180)
    note = trim(body.note,'ملخص طلب التصفية',12,500)
    payload = {'case_id':case_id, 'reference':evidence, 'note':note,'mode':body.mode}
    with c:
        c.execute('BEGIN IMMEDIATE')
        case = case_scope(c,user,case_id,write=True)
        prior, digest = repeat(c,key,'case_financial_clearance',user['id'],payload)
        if prior:
            return {'id':prior,'status':c.execute('SELECT status FROM billing_case_clearance_requests WHERE id=?',
                                                  (prior,)).fetchone()[0],'replayed':True}
        if c.execute("SELECT 1 FROM billing_case_clearance_requests WHERE case_id=? AND status='pending'",
                     (case_id,)).fetchone():
            fail('هناك طلب تصفية قيد المراجعة بالفعل',409)
        report = case_preflight(c,case)
        if body.mode=='no_charge' and user['role']!='owner':
            fail('إلغاء حالة بلا أي معاملة مالية يحتاج تقديم الطلب بواسطة المالك',403)
        if body.mode=='no_charge' and not report['no_charge_ready']:
            fail('لا يمكن إلغاء حالة بلا رسوم بعد تسجيل خدمة أو مسودة أو أي تحصيل',409)
        if body.mode=='settled' and not report['ready']:
            fail('لا يمكن طلب التصفية: '+'؛ '.join(report['blockers']),409)
        cur=c.execute('''INSERT INTO billing_case_clearance_requests
             (case_id,point_id,evidence_reference,note,requested_by,requested_at,clearance_mode)
             VALUES (?,?,?,?,?,?,?)''',(case_id,case['default_point_id'],evidence,note,user['id'],stamp(),body.mode))
        remember(c,key,'case_financial_clearance',user['id'],digest,cur.lastrowid)
        audit(c,user['id'],'case_financial_clearance_requested','billing_case',case_id,
              {'clearance_id':cur.lastrowid,'evidence_reference':evidence,'mode':body.mode})
    return {'id':cur.lastrowid,'status':'pending'}


@router.post('/requests/{clearance_id}/decision')
def decide_clearance(clearance_id: int, body: ClearanceDecision,
                     user=Depends(get_user), c: sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    note = trim(body.note,'سبب قرار المراجعة',12,500)
    with c:
        c.execute('BEGIN IMMEDIATE')
        req=c.execute('SELECT * FROM billing_case_clearance_requests WHERE id=?',
                      (clearance_id,)).fetchone()
        if not req:fail('طلب التصفية غير موجود',404)
        case=case_scope(c,user,req['case_id'])
        if req['status']!='pending':fail('سبق حسم طلب التصفية',409)
        if req['requested_by']==user['id']:fail('يجب أن يراجع التصفية موظف آخر مستقل',403)
        if body.decision=='reject':
            c.execute('''UPDATE billing_case_clearance_requests SET status='rejected',
                reviewed_by=?,reviewed_at=?,decision_note=? WHERE id=?''',
                (user['id'],stamp(),note,clearance_id))
            audit(c,user['id'],'case_financial_clearance_rejected','billing_case',req['case_id'],
                  {'clearance_id':clearance_id})
            return {'id':clearance_id,'status':'rejected'}
        report=case_preflight(c,case)
        if req['clearance_mode']=='no_charge':
            if not report['no_charge_ready']:
                fail('تمت إضافة خدمة أو معاملة مالية بعد تقديم طلب الإلغاء؛ يمنع اعتماده',409)
        elif not report['ready']:
            fail('تغيرت ذمم الحالة بعد طلب التصفية: '+'؛ '.join(report['blockers']),409)
        day=cairo_today(); month_open(c,day[:7])
        c.execute('''UPDATE billing_case_clearance_requests SET status='approved',
            reviewed_by=?,reviewed_at=?,decision_note=?,closed_on=?,snapshot_json=? WHERE id=?''',
            (user['id'],stamp(),note,day,json.dumps(report,ensure_ascii=False,sort_keys=True),clearance_id))
        c.execute("UPDATE billing_cases SET status='closed' WHERE id=? AND status='open'",(req['case_id'],))
        audit(c,user['id'],'case_financial_clearance_approved','billing_case',req['case_id'],
              {'clearance_id':clearance_id,'invoice_count':report['invoice_count'],
               'invoiced_piasters':report['invoiced_piasters'],'financial_closure_date':day,
               'mode':req['clearance_mode']})
    return {'id':clearance_id,'status':'approved','closed_on':day,
            'receipt_created':False,'journal_created':False,
            'notice':'إغلاق مالي للذمم، وليس إقرارًا بخروج طبي أو بمطابقة خزنة.'}
