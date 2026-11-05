"""Immutable correction intake, G2G unpaid credits, G2H receipt reallocations.

Reviewing a ticket never posts money. G2H changes subsidiary receivables only,
not the original receipt, GL control account, shift or physical cash movements.
"""
from __future__ import annotations
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Literal
from app import db, get_user, require, fail, audit, month_open, c_piasters
from billing import can_point, cairo_today, invoice_due
import ledger
import secrets

router=APIRouter(prefix='/api/corrections', tags=['Financial corrections'])
KEY=re.compile(r'^[A-Za-z0-9_-]{16,128}$')

class CorrectionOpen(BaseModel):
    source_type:Literal['invoice','collection','voucher','shift']
    source_id:int=Field(ge=1)
    issue_type:Literal['wrong_patient','wrong_service','wrong_amount','wrong_method','duplicate','wrong_cash_fund','missing_document','other']
    reason:str=Field(min_length=20,max_length=2000)
    proposed_resolution:str=Field(min_length=12,max_length=2000)
    request_key:str=Field(min_length=16,max_length=128)

class CorrectionReview(BaseModel):
    decision:Literal['triage','needs_evidence','dismiss']
    note:str=Field(min_length=16,max_length=1500)

class CorrectionNote(BaseModel):
    note:str=Field(min_length=10,max_length=1500)

class InvoiceCreditFix(BaseModel):
    amount:str=Field(min_length=1,max_length=40)  # EGP, converted precisely to piasters
    expected_due_piasters:int=Field(gt=0)
    evidence_reference:str=Field(min_length=8,max_length=180)
    decision_note:str=Field(min_length=16,max_length=1500)
    request_key:str=Field(min_length=16,max_length=128)


class CollectionReassignPreview(BaseModel):
    target_invoice_id:int=Field(ge=1)
    target_patient_code:str=Field(min_length=15,max_length=15)


class CollectionReassignFix(CollectionReassignPreview):
    expected_source_due_piasters:int=Field(ge=0)
    expected_target_due_piasters:int=Field(gt=0)
    evidence_reference:str=Field(min_length=8,max_length=180)
    decision_note:str=Field(min_length=16,max_length=1500)
    request_key:str=Field(min_length=16,max_length=128)


def stamp():return datetime.now(timezone.utc).isoformat(timespec='seconds')


def ticket_scope(c,user,ticket):
    """Patient-related correction tickets follow the same point grants as files."""
    if ticket['point_id'] is not None and user['role']=='reviewer':
        can_point(c,user,ticket['point_id'])


def target_invoice_scope(c,user,invoice_id):
    if user['role']=='reviewer':
        row=c.execute("""SELECT b.default_point_id FROM billing_invoices i
                JOIN billing_cases b ON b.id=i.case_id WHERE i.id=?""",(invoice_id,)).fetchone()
        if not row:fail('الفاتورة المستهدفة غير موجودة',404)
        can_point(c,user,row['default_point_id'])

def source_summary(c,user,kind,ref):
    """Snapshot minimal financial facts, never editable; enforce point access."""
    if kind=='invoice':
        row=c.execute('''SELECT i.id,i.invoice_no,i.case_id,i.issued_date,i.total_piasters,
             b.default_point_id AS point_id FROM billing_invoices i JOIN billing_cases b
             ON b.id=i.case_id WHERE i.id=?''',(ref,)).fetchone()
        if not row:fail('الفاتورة المشار إليها غير موجودة',404)
        can_point(c,user,row['point_id'])
        return dict(row),row['invoice_no'],row['point_id']
    if kind=='collection':
        row=c.execute('''SELECT id,collection_no,case_id,invoice_id,kind,shift_session_id,
                        point_id,business_date,total_piasters
                      FROM billing_collections WHERE id=?''',(ref,)).fetchone()
        if not row:fail('إيصال التحصيل غير موجود',404)
        can_point(c,user,row['point_id'])
        return dict(row),row['collection_no'],row['point_id']
    if kind=='shift':
        row=c.execute('''SELECT s.id,s.business_date,s.shift,s.point_id,s.fund_id,s.status,
                        s.expected_piasters,s.counted_piasters FROM shift_sessions s WHERE s.id=?''',(ref,)).fetchone()
        if not row:fail('الوردية غير موجودة',404)
        info=dict(row);pid=info['point_id']
        if not pid:
            linked=c.execute('SELECT id FROM billing_points WHERE fund_id=?',(info['fund_id'],)).fetchone()
            pid=linked['id'] if linked else None
        if pid:can_point(c,user,pid)
        elif user['role'] not in ('owner','reviewer'):fail('لا يمكن عرض هذه الوردية خارج نقاطك',403)
        return info,'SH-'+str(ref),pid
    # General vouchers include sensitive payroll, bank and owner movements.
    require(user,'owner','reviewer')
    row=c.execute('''SELECT id,voucher_no,kind,date,amount_piasters,from_fund_id,
                 to_fund_id,status FROM vouchers WHERE id=?''',(ref,)).fetchone()
    if not row:fail('السند المالي غير موجود',404)
    return dict(row),row['voucher_no'],None

@router.get('')
def tickets(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    if user['role']=='clerk':
        rows=c.execute('''SELECT t.id,t.source_type,t.source_id,t.source_ref,t.issue_type,t.reason,
              t.proposed_resolution,t.status,t.opened_by,t.opened_at,t.reviewed_at,t.review_note,
              u.username opened_by_name, fx.credit_id AS resolved_credit_id,
              fx.amount_piasters AS resolved_amount_piasters,
              rr.id AS resolved_reallocation_id, rr.amount_piasters AS reallocated_amount_piasters
              FROM financial_correction_tickets t JOIN users u ON u.id=t.opened_by
              LEFT JOIN financial_invoice_credit_fixes fx ON fx.ticket_id=t.id
              LEFT JOIN financial_collection_reallocations rr ON rr.ticket_id=t.id
              WHERE t.opened_by=? ORDER BY t.id DESC LIMIT 150''',(user['id'],)).fetchall()
    else:
        scope=''
        args=[]
        if user['role']=='reviewer':
            scope='''WHERE (t.point_id IS NULL OR EXISTS (
                SELECT 1 FROM billing_point_access a WHERE a.point_id=t.point_id
                AND a.user_id=? AND a.active=1))'''
            args=[user['id']]
        rows=c.execute('''SELECT t.id,t.source_type,t.source_id,t.source_ref,t.issue_type,t.reason,
              t.proposed_resolution,t.status,t.opened_by,t.opened_at,t.reviewed_at,t.review_note,
              u.username opened_by_name, fx.credit_id AS resolved_credit_id,
              fx.amount_piasters AS resolved_amount_piasters,
              rr.id AS resolved_reallocation_id, rr.amount_piasters AS reallocated_amount_piasters
              FROM financial_correction_tickets t JOIN users u ON u.id=t.opened_by
              LEFT JOIN financial_invoice_credit_fixes fx ON fx.ticket_id=t.id
              LEFT JOIN financial_collection_reallocations rr ON rr.ticket_id=t.id
              '''+scope+' ORDER BY t.id DESC LIMIT 150',args).fetchall()
    return {'tickets':[dict(r) for r in rows],
            'notice':'Triage never posts money. G2G reduces unpaid invoices with a credit note; G2H reallocates a full receipt without a new cash or GL control posting.'}

@router.post('')
def open_ticket(body:CorrectionOpen,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    if not KEY.fullmatch(body.request_key):fail('رمز طلب التصحيح غير صالح')
    reason=body.reason.strip();proposal=body.proposed_resolution.strip()
    if len(reason)<20 or len(proposal)<12:fail('أكمل شرح الخطأ والتصحيح المطلوب')
    payload={'source_type':body.source_type,'source_id':body.source_id,'issue_type':body.issue_type,
             'reason':reason,'proposed_resolution':proposal}
    digest=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    with c:
        c.execute('BEGIN IMMEDIATE')
        old=c.execute('SELECT id,request_hash,opened_by FROM financial_correction_tickets WHERE request_key=?',(body.request_key,)).fetchone()
        if old:
            if old['opened_by']!=user['id'] or old['request_hash']!=digest:
                fail('رمز الطلب مستخدم لعملية أخرى',409)
            return {'id':old['id'],'replayed':True,'status':'open_or_reviewed'}
        summary,ref,point_id=source_summary(c,user,body.source_type,body.source_id)
        at=stamp()
        row=c.execute('''INSERT INTO financial_correction_tickets(request_key,request_hash,source_type,
           source_id,source_ref,point_id,issue_type,reason,proposed_resolution,source_snapshot_json,opened_by,opened_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
           (body.request_key,digest,body.source_type,body.source_id,ref,point_id,body.issue_type,
            reason,proposal,json.dumps(summary,ensure_ascii=False,sort_keys=True),user['id'],at))
        c.execute('''INSERT INTO financial_correction_events(ticket_id,action,note,actor_id,created_at)
                     VALUES (?,?,?,?,?)''',(row.lastrowid,'opened',reason,user['id'],at))
        audit(c,user['id'],'financial_correction_ticket_opened','financial_correction_ticket',row.lastrowid,
              {'source_type':body.source_type,'source_id':body.source_id,'issue_type':body.issue_type})
    return {'id':row.lastrowid,'replayed':False,'status':'open'}

@router.get('/{ticket_id}/history')
def history(ticket_id:int,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    row=c.execute('SELECT * FROM financial_correction_tickets WHERE id=?',(ticket_id,)).fetchone()
    if not row:fail('البلاغ غير موجود',404)
    ticket_scope(c,user,row)
    if user['role']=='clerk' and user['id']!=row['opened_by']:fail('لا صلاحية لرؤية بلاغ غيرك',403)
    events=[dict(r) for r in c.execute('''SELECT e.action,e.note,e.actor_id,e.created_at,u.username
       FROM financial_correction_events e JOIN users u ON u.id=e.actor_id
       WHERE e.ticket_id=? ORDER BY e.id''',(ticket_id,))]
    fixed=c.execute('''SELECT id,ticket_id,invoice_id,credit_id,journal_id,amount_piasters,
           original_due_piasters,new_due_piasters,evidence_reference,decision_note,
           approved_by,approved_at FROM financial_invoice_credit_fixes WHERE ticket_id=?''',(ticket_id,)).fetchone()
    reallocated=c.execute('''SELECT id,collection_id,from_invoice_id,to_invoice_id,
           from_case_id,to_case_id,amount_piasters,before_source_due_piasters,
           after_source_due_piasters,before_target_due_piasters,after_target_due_piasters,
           effective_date,evidence_reference,decision_note,approved_by,approved_at
           FROM financial_collection_reallocations WHERE ticket_id=?''',(ticket_id,)).fetchone()
    return {'ticket':dict(row),'events':events,
            'financial_execution':dict(fixed) if fixed else None,
            'collection_reallocation':dict(reallocated) if reallocated else None}

@router.post('/{ticket_id}/note')
def append_note(ticket_id:int,body:CorrectionNote,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    note=body.note.strip()
    if len(note)<10:fail('الملاحظة أقصر من المطلوب')
    with c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM financial_correction_tickets WHERE id=?',(ticket_id,)).fetchone()
        if not row:fail('البلاغ غير موجود',404)
        ticket_scope(c,user,row)
        if user['role']=='clerk' and user['id']!=row['opened_by']:fail('لا صلاحية',403)
        if row['status'] in ('triaged','dismissed'):fail('البلاغ استُلم للمراجعة أو أُغلق؛ لا يمكن تعديله',409)
        at=stamp()
        c.execute('''INSERT INTO financial_correction_events(ticket_id,action,note,actor_id,created_at)
                     VALUES (?,?,?,?,?)''',(ticket_id,'note',note,user['id'],at))
        if row['status']=='needs_evidence' and user['id']==row['opened_by']:
            c.execute('UPDATE financial_correction_tickets SET status=? WHERE id=?',('open',ticket_id))
        audit(c,user['id'],'financial_correction_note','financial_correction_ticket',ticket_id,{'length':len(note)})
    return {'id':ticket_id,'ok':True}

@router.post('/{ticket_id}/review')
def review(ticket_id:int,body:CorrectionReview,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    note=body.note.strip()
    if len(note)<16:fail('سبب المراجعة مطلوب')
    target={'triage':'triaged','needs_evidence':'needs_evidence','dismiss':'dismissed'}[body.decision]
    with c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM financial_correction_tickets WHERE id=?',(ticket_id,)).fetchone()
        if not row:fail('البلاغ غير موجود',404)
        ticket_scope(c,user,row)
        if row['opened_by']==user['id']:fail('لا يجوز لمقدم البلاغ مراجعته بنفسه',403)
        if row['status']!='open':fail('البلاغ ليس مفتوحًا للمراجعة',409)
        at=stamp()
        c.execute('''UPDATE financial_correction_tickets SET status=?,reviewed_by=?,reviewed_at=?,review_note=?
                     WHERE id=?''',(target,user['id'],at,note,ticket_id))
        c.execute('''INSERT INTO financial_correction_events(ticket_id,action,note,actor_id,created_at)
                     VALUES (?,?,?,?,?)''',(ticket_id,target,note,user['id'],at))
        audit(c,user['id'],'financial_correction_reviewed','financial_correction_ticket',ticket_id,
              {'decision':body.decision,'no_financial_posting':True})
    return {'id':ticket_id,'status':target,'financial_posted':False}


# V8.1E G2G — the only supported posted correction is a reduction of an unpaid
# issued invoice, using the SAME standard credit-note accounting as billing.py.
# No voucher, cash movement, reissued invoice or reopening of the old month.

def _credit_eligibility(c,ticket):
    if ticket['source_type']!='invoice' or ticket['issue_type']!='wrong_amount':
        return None, 'التصحيح المالي الحالي متاح فقط لتخفيض مبلغ فاتورة صادرة'
    invoice=c.execute('''SELECT i.*,j.status AS journal_status FROM billing_invoices i
          LEFT JOIN gl_journals j ON j.id=i.journal_id WHERE i.id=?''',(ticket['source_id'],)).fetchone()
    if not invoice or invoice['journal_status']!='posted':
        return None,'الفاتورة الأصلية غير مرحلة بصورة صحيحة'
    if c.execute("SELECT status FROM billing_cases WHERE id=?",(invoice['case_id'],)).fetchone()[0]!='open':
        return None,'الحالة مصفاة ماليًا وتحتاج طلب تصحيح ما بعد التصفية'
    previous=json.loads(ticket['source_snapshot_json'])
    if (previous.get('id')!=invoice['id'] or previous.get('case_id')!=invoice['case_id']
        or previous.get('total_piasters')!=invoice['total_piasters']
        or previous.get('invoice_no')!=invoice['invoice_no']):
        return None,'بيانات الفاتورة الأصلية تغيرت بعد فتح البلاغ'
    if c.execute('''SELECT 1 FROM billing_credit_requests
                   WHERE invoice_id=? AND status IN ('pending','approved')''',(invoice['id'],)).fetchone():
        return None,'يوجد إشعار دائن سابق أو معلق على الفاتورة؛ يلزم مسار مراجعة منفصل'
    if invoice_due(c,invoice['id'])!=invoice['total_piasters']:
        return None,'الفاتورة عليها تحصيل أو تخصيص نقدية أو مقدم؛ لا يمكن تخفيضها بهذا المسار'
    if c.execute('SELECT 1 FROM financial_invoice_credit_fixes WHERE invoice_id=?',(invoice['id'],)).fetchone():
        return None,'الفاتورة سبق تصحيحها ماليًا بهذا المسار'
    return invoice,None

@router.get('/{ticket_id}/invoice-credit-preview')
def invoice_credit_preview(ticket_id:int,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    ticket=c.execute('SELECT * FROM financial_correction_tickets WHERE id=?',(ticket_id,)).fetchone()
    if not ticket:fail('البلاغ غير موجود',404)
    ticket_scope(c,user,ticket)
    if ticket['opened_by']==user['id']:fail('لا يمكنك التصديق على تصحيح بلاغك',403)
    prior=c.execute('''SELECT id,credit_id,journal_id,amount_piasters,original_due_piasters,
           new_due_piasters,evidence_reference,approved_at FROM financial_invoice_credit_fixes
           WHERE ticket_id=?''',(ticket_id,)).fetchone()
    if prior:
        return {'eligible':False,'resolved':True,'execution':dict(prior),
                'reason':'سبق تنفيذ التصحيح ولا يمكن تسجيله مرة ثانية'}
    if ticket['status']!='triaged' or not ticket['reviewed_by']:
        return {'eligible':False,'resolved':False,'reason':'البلاغ لم يُراجع ويُقبل بصورة مستقلة'}
    invoice,reason=_credit_eligibility(c,ticket)
    return {'eligible':bool(invoice),'resolved':False,'reason':reason,
            'invoice_no':invoice['invoice_no'] if invoice else ticket['source_ref'],
            'invoice_id':invoice['id'] if invoice else ticket['source_id'],
            'before_due_piasters':invoice['total_piasters'] if invoice else None,
            'max_reduction_piasters':invoice['total_piasters'] if invoice else None,
            'requires':'مستند إثبات ومبلغ تخفيض محدد واعتماد مراجع مستقل'}

@router.post('/{ticket_id}/execute-invoice-credit')
def execute_invoice_credit(ticket_id:int,body:InvoiceCreditFix,
                           user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    amount=c_piasters(body.amount)
    evidence=body.evidence_reference.strip()
    note=body.decision_note.strip()
    if not KEY.fullmatch(body.request_key):fail('مفتاح طلب التصحيح غير صالح')
    if len(evidence)<8 or any(ord(x)<32 for x in evidence):fail('يلزم مرجع مستند إثبات صحيح')
    if len(note)<16 or any(ord(x)<32 for x in note):fail('يلزم مبرر اعتماد مفصل')
    payload={'ticket_id':ticket_id,'amount_piasters':amount,'expected_due_piasters':body.expected_due_piasters,
             'evidence_reference':evidence,'decision_note':note}
    digest=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    with c:
        c.execute('BEGIN IMMEDIATE')
        ticket=c.execute('SELECT * FROM financial_correction_tickets WHERE id=?',(ticket_id,)).fetchone()
        if not ticket:fail('البلاغ غير موجود',404)
        ticket_scope(c,user,ticket)
        if ticket['opened_by']==user['id']:fail('لا يجوز لمن قدّم البلاغ اعتماد تصحيحه',403)
        old=c.execute('SELECT * FROM financial_invoice_credit_fixes WHERE ticket_id=? OR request_key=?',
                      (ticket_id,body.request_key)).fetchone()
        if old:
            if (old['ticket_id']!=ticket_id or old['request_hash']!=digest
                 or old['approved_by']!=user['id'] or old['request_key']!=body.request_key):
                fail('التصحيح منفذ بالفعل أو رمز الطلب مستخدم بتفاصيل أخرى',409)
            return {'id':old['id'],'credit_id':old['credit_id'],'journal_id':old['journal_id'],
                    'new_due_piasters':old['new_due_piasters'],'replayed':True,'cash_movement_created':False}
        if ticket['status']!='triaged' or not ticket['reviewed_by']:
            fail('البلاغ ليس معتمدًا للمراجعة المالية المستقلة',409)
        invoice,reason=_credit_eligibility(c,ticket)
        if reason:fail(reason,409)
        from service_fees import has_active_approvals
        if has_active_approvals(c,invoice['id']):fail('اعكس الأتعاب المعتمدة قبل تصحيح الفاتورة',409)
        if body.expected_due_piasters!=invoice['total_piasters']:
            fail('رصيد الفاتورة تغير؛ راجع المعاينة وأعد المحاولة',409)
        if amount>invoice['total_piasters']:
            fail('التخفيض أكبر من مبلغ الفاتورة غير المحصل',409)
        day=cairo_today();month_open(c,day[:7])
        credit_no='CR-FIX-'+secrets.token_hex(6)
        journal=ledger._journal(c,entry_date=day,
          memo='تصحيح فاتورة '+invoice['invoice_no']+' / بلاغ #'+str(ticket_id)+' / '+credit_no,
          origin='manual',source_id=None,created_by=ticket['opened_by'],reviewed_by=user['id'],
          lines=[(ledger.account_by_code(c,'4195'),amount,0,None),
                 (ledger.account_by_code(c,'1200'),0,amount,None)])
        now=stamp()
        credit=c.execute('''INSERT INTO billing_credit_requests(credit_no,invoice_id,case_id,
             amount_piasters,reason,requested_by,requested_at,status,decided_by,decided_at,
             decision_note,journal_id) VALUES (?,?,?,?,?,?,?,'approved',?,?,?,?)''',
             (credit_no,invoice['id'],invoice['case_id'],amount,
              'تصحيح مبلغ فاتورة معتمدة بالبلاغ #'+str(ticket_id)+' / '+ticket['reason'],
              ticket['opened_by'],ticket['opened_at'],user['id'],now,note,journal))
        new_due=invoice_due(c,invoice['id'])
        if new_due!=invoice['total_piasters']-amount:
            raise ValueError('Post-correction patient balance mismatch')
        fix=c.execute('''INSERT INTO financial_invoice_credit_fixes(ticket_id,invoice_id,credit_id,
            journal_id,request_key,request_hash,original_due_piasters,amount_piasters,new_due_piasters,
            evidence_reference,decision_note,approved_by,approved_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (ticket_id,invoice['id'],credit.lastrowid,journal,body.request_key,digest,
             invoice['total_piasters'],amount,new_due,evidence,note,user['id'],now))
        c.execute('''INSERT INTO financial_correction_events(ticket_id,action,note,actor_id,created_at)
                     VALUES (?,?,?,?,?)''',(ticket_id,'note',
                    'تصحيح معتمد G2G / إشعار دائن '+credit_no+' / مرجع إثبات '+evidence+' / '+note,user['id'],now))
        audit(c,user['id'],'financial_invoice_credit_fixed','financial_correction_ticket',ticket_id,
              {'invoice_id':invoice['id'],'credit_id':credit.lastrowid,'journal_id':journal,
               'amount_piasters':amount,'original_due_piasters':invoice['total_piasters'],
               'new_due_piasters':new_due,'cash_movement_created':False})
    return {'id':fix.lastrowid,'credit_id':credit.lastrowid,'journal_id':journal,
            'new_due_piasters':new_due,'replayed':False,'cash_movement_created':False}

# V8.1E-G2H — a wrong-patient invoice receipt may be reassigned IN FULL to
# one different patient's open invoice. The posted cashbook and 1200 GL control
# balance are already correct: this creates a dated, immutable SUBLEDGER entry.
# The source receipt remains discoverable under its original shift and case.

def _reassign_eligibility(c,ticket,target_invoice_id,patient_code):
    if ticket['source_type']!='collection' or ticket['issue_type']!='wrong_patient':
        return None,None,'هذا المسار مخصص لإيصال فاتورة مسجل على مريض غير صحيح'
    source=c.execute('''SELECT b.*,i.total_piasters AS source_invoice_total,
          j.status AS source_gl_status,bc.patient_id AS source_patient_id
          FROM billing_collections b
          JOIN billing_invoices i ON i.id=b.invoice_id
          JOIN gl_journals j ON j.id=i.journal_id
          JOIN billing_cases bc ON bc.id=b.case_id
          WHERE b.id=? AND b.kind='invoice' ''',(ticket['source_id'],)).fetchone()
    if not source or source['source_gl_status']!='posted':
        return None,None,'إيصال المصدر ليس تحصيل فاتورة مرحلة بصورة صحيحة'
    if c.execute("SELECT status FROM billing_cases WHERE id=?",(source['case_id'],)).fetchone()[0]!='open':
        return None,None,'الحالة الأصلية مصفاة ماليًا، فلا يمكن إعادة تخصيص تحصيلها'
    snapshot=json.loads(ticket['source_snapshot_json'])
    required=('id','invoice_id','case_id','kind','point_id',
              'shift_session_id','business_date','total_piasters','collection_no')
    if any(snapshot.get(k)!=source[k] for k in required):
        return None,None,'بيانات إيصال المصدر غير مكتملة أو تغيرت؛ يلزم بلاغ جديد ومراجعة مستقلة'
    if c.execute('SELECT 1 FROM financial_collection_reallocations WHERE collection_id=?',
                 (source['id'],)).fetchone():
        return None,None,'هذا الإيصال سبق تخصيصه إلى فاتورة أخرى'
    # Patient code is a deliberate second factor: do not enumerate patients by
    # invoice ID in the review preview or the execution endpoint.
    code=(patient_code or '').strip().upper()
    if not re.fullmatch(r'PT-[A-F0-9]{12}',code):
        return None,None,'رقم الفاتورة وكود المريض غير متطابقين'
    target=c.execute('''SELECT i.*,j.status AS target_gl_status,b.patient_id AS target_patient_id,
             b.status AS target_case_status, b.case_no AS target_case_no
             FROM billing_invoices i JOIN billing_cases b ON b.id=i.case_id
             JOIN billing_patients p ON p.id=b.patient_id
             JOIN gl_journals j ON j.id=i.journal_id
             WHERE i.id=? AND p.code=?''',(target_invoice_id,code)).fetchone()
    if not target:
        return None,None,'رقم الفاتورة وكود المريض غير متطابقين'
    if target['target_gl_status']!='posted' or target['target_case_status']!='open':
        return None,None,'الفاتورة المستهدفة غير مرحلة أو الحالة المستهدفة مقفلة'
    if target['case_id']==source['case_id'] or target['target_patient_id']==source['source_patient_id']:
        return None,None,'يجب أن تتبع الفاتورة المستهدفة مريضًا آخر فعليًا'
    # The first controlled scope excludes overlapping credits, refunds, historic
    # envelopes and existing reallocations; they need a separate reconciliation.
    invoice_ids=(source['invoice_id'],target['id'])
    case_ids=(source['case_id'],target['case_id'])
    for q,params,message in (
        ('''SELECT 1 FROM financial_collection_reallocations
            WHERE from_invoice_id IN (?,?) OR to_invoice_id IN (?,?)''',
         invoice_ids+invoice_ids,'يوجد تخصيص تحصيل سابق على إحدى الفاتورتين'),
        ('''SELECT 1 FROM billing_credit_requests WHERE invoice_id IN (?,?)
             AND status IN ('pending','approved')''',
         invoice_ids,'توجد إشعارات دائنة مرتبطة بإحدى الفاتورتين'),
        ('''SELECT 1 FROM billing_refund_requests WHERE case_id IN (?,?)
             AND status IN ('pending','approved','paid')''',
         case_ids,'توجد طلبات رد أو مبالغ مردودة لإحدى الحالتين'),
        ('SELECT 1 FROM billing_advance_allocations WHERE invoice_id IN (?,?)',
         invoice_ids,'تم تخصيص مقدم مسبقًا لإحدى الفاتورتين'),
        ('SELECT 1 FROM billing_late_cases WHERE case_id IN (?,?)',
         case_ids,'إحدى الحالتين مستدركة من يوم سابق وتحتاج تسوية مستقلة'),
        ('SELECT 1 FROM late_cash_allocations WHERE invoice_id IN (?,?)',
         invoice_ids,'إحدى الفاتورتين مرتبطة بنقدية تاريخية'),
        ('''SELECT 1 FROM late_mixed_clearance_lines
            WHERE line_kind='patient_receipt' AND invoice_id IN (?,?)''',
         invoice_ids,'إحدى الفاتورتين مرتبطة بظرف مختلط')
    ):
        if c.execute(q,params).fetchone():return None,None,message
    # Validate ALL split vouchers and journals, not merely the receipt header.
    parts=c.execute('''SELECT p.amount_piasters,v.status AS voucher_status,
          j.status AS journal_status,
          (SELECT COUNT(*) FROM vouchers reverse
           WHERE reverse.reversal_of_id=v.id AND reverse.status<>'rejected') AS reversals
          FROM billing_payment_parts p JOIN vouchers v ON v.id=p.voucher_id
          LEFT JOIN gl_journals j ON j.origin='voucher' AND j.source_id=v.id
          WHERE p.collection_id=?''',(source['id'],)).fetchall()
    if (not parts or sum(p['amount_piasters'] for p in parts)!=source['total_piasters']
        or any(p['voucher_status']!='approved' or p['journal_status']!='posted' or p['reversals'] for p in parts)):
        return None,None,'أجزاء السداد أو قيود القبض غير سليمة؛ يمنع التصحيح الآلي'
    if invoice_due(c,target['id'])<source['total_piasters']:
        return None,None,'المبلغ المنقول أكبر من الذمة المستحقة في الفاتورة الصحيحة'
    if invoice_due(c,source['invoice_id'])+source['total_piasters']>source['source_invoice_total']:
        return None,None,'توجد زيادة أو تداخل في رصيد الفاتورة الأصلية؛ يلزم مراجعة منفصلة'
    return source,target,None


@router.post('/{ticket_id}/collection-reassign-preview')
def collection_reassign_preview(ticket_id:int,body:CollectionReassignPreview,
                                user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    ticket=c.execute('SELECT * FROM financial_correction_tickets WHERE id=?',(ticket_id,)).fetchone()
    if not ticket:fail('البلاغ غير موجود',404)
    ticket_scope(c,user,ticket)
    if ticket['opened_by']==user['id']:fail('مقدم البلاغ لا يعتمد تصحيحه',403)
    old=c.execute('''SELECT id,collection_id,to_invoice_id,amount_piasters,
             effective_date FROM financial_collection_reallocations WHERE ticket_id=?''',(ticket_id,)).fetchone()
    if old:return {'eligible':False,'resolved':True,'execution':dict(old),
                   'reason':'سبق تنفيذ إعادة التخصيص على هذا الإيصال'}
    if ticket['status']!='triaged' or not ticket['reviewed_by']:
        return {'eligible':False,'resolved':False,'reason':'بلاغ التصحيح لم يُقبل للمراجعة المستقلة'}
    target_invoice_scope(c,user,body.target_invoice_id)
    source,target,reason=_reassign_eligibility(c,ticket,body.target_invoice_id,body.target_patient_code)
    if reason:return {'eligible':False,'resolved':False,'reason':reason}
    return {'eligible':True,'resolved':False,'source_receipt_no':source['collection_no'],
            'source_invoice_id':source['invoice_id'],'target_invoice_id':target['id'],
            'target_invoice_no':target['invoice_no'],
            'target_case_no':target['target_case_no'],
            'amount_piasters':source['total_piasters'],
            'before_source_due_piasters':invoice_due(c,source['invoice_id']),
            'before_target_due_piasters':invoice_due(c,target['id']),
            'cash_movement_created':False,'gl_control_movement_created':False}


@router.post('/{ticket_id}/execute-collection-reassign')
def execute_collection_reassign(ticket_id:int,body:CollectionReassignFix,
                                user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    evidence=body.evidence_reference.strip();note=body.decision_note.strip()
    if not KEY.fullmatch(body.request_key):fail('رمز طلب إعادة التخصيص غير صالح')
    if len(evidence)<8 or any(ord(x)<32 for x in evidence):fail('مرجع الإثبات غير صالح')
    if len(note)<16 or any(ord(x)<32 for x in note):fail('اكتب سبب الاعتماد المستقل بالتفصيل')
    payload={'ticket_id':ticket_id,'target_invoice_id':body.target_invoice_id,
             'target_patient_code':body.target_patient_code.strip().upper(),
             'expected_source_due_piasters':body.expected_source_due_piasters,
             'expected_target_due_piasters':body.expected_target_due_piasters,
             'evidence_reference':evidence,'decision_note':note}
    digest=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    with c:
        c.execute('BEGIN IMMEDIATE')
        ticket=c.execute('SELECT * FROM financial_correction_tickets WHERE id=?',(ticket_id,)).fetchone()
        if not ticket:fail('البلاغ غير موجود',404)
        ticket_scope(c,user,ticket)
        if ticket['opened_by']==user['id']:fail('لا يجوز اعتماد تصحيح البلاغ بواسطة مقدمه',403)
        old=c.execute('''SELECT * FROM financial_collection_reallocations
                 WHERE ticket_id=? OR request_key=? OR collection_id=?''',
                 (ticket_id,body.request_key,ticket['source_id'] if ticket['source_type']=='collection' else -1)).fetchone()
        if old:
            if (old['ticket_id']!=ticket_id or old['request_key']!=body.request_key
                or old['request_hash']!=digest or old['approved_by']!=user['id']):
                fail('الإيصال مصحح بالفعل أو رمز الطلب مستخدم لعملية أخرى',409)
            return {'id':old['id'],'amount_piasters':old['amount_piasters'],
                    'after_source_due_piasters':old['after_source_due_piasters'],
                    'after_target_due_piasters':old['after_target_due_piasters'],
                    'replayed':True,'cash_movement_created':False,'gl_control_movement_created':False}
        if ticket['status']!='triaged' or not ticket['reviewed_by']:
            fail('البلاغ لم يُقبل للمراجعة المستقلة',409)
        target_invoice_scope(c,user,body.target_invoice_id)
        source,target,reason=_reassign_eligibility(c,ticket,body.target_invoice_id,body.target_patient_code)
        if reason:fail(reason,409)
        from service_fees import has_active_approvals
        if has_active_approvals(c,source['invoice_id']) or has_active_approvals(c,target['id']):
            fail('اعكس الأتعاب المعتمدة قبل تغيير تخصيص القبض',409)
        before_source=invoice_due(c,source['invoice_id'])
        before_target=invoice_due(c,target['id'])
        if (before_source!=body.expected_source_due_piasters
            or before_target!=body.expected_target_due_piasters):
            fail('تغير رصيد إحدى الفاتورتين بعد المعاينة؛ أعد مراجعة الأرصدة',409)
        day=cairo_today();month_open(c,day[:7]);approved_at=stamp()
        amount=source['total_piasters']
        row=c.execute('''INSERT INTO financial_collection_reallocations(
          ticket_id,collection_id,from_invoice_id,to_invoice_id,from_case_id,to_case_id,
          amount_piasters,before_source_due_piasters,after_source_due_piasters,
          before_target_due_piasters,after_target_due_piasters,effective_date,
          evidence_reference,decision_note,request_key,request_hash,approved_by,approved_at)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
          (ticket_id,source['id'],source['invoice_id'],target['id'],source['case_id'],
           target['case_id'],amount,before_source,before_source+amount,
           before_target,before_target-amount,day,evidence,note,body.request_key,digest,
           user['id'],approved_at))
        if (invoice_due(c,source['invoice_id'])!=before_source+amount
            or invoice_due(c,target['id'])!=before_target-amount):
            raise ValueError('Receipt reallocation did not reconcile both patient ledgers')
        c.execute('''INSERT INTO financial_correction_events(ticket_id,action,note,actor_id,created_at)
                     VALUES (?,'note',?,?,?)''',
                  (ticket_id,'G2H / نقل تخصيص كامل للإيصال '+source['collection_no']+
                   ' من فاتورة '+str(source['invoice_id'])+' إلى '+target['invoice_no']+
                   ' / إثبات '+evidence+' / '+note,user['id'],approved_at))
        audit(c,user['id'],'financial_receipt_reallocated','financial_correction_ticket',ticket_id,
              {'collection_id':source['id'],'from_invoice_id':source['invoice_id'],
               'to_invoice_id':target['id'],'amount_piasters':amount,
               'before_source_due_piasters':before_source,'after_source_due_piasters':before_source+amount,
               'before_target_due_piasters':before_target,'after_target_due_piasters':before_target-amount,
               'effective_date':day,'cash_movement_created':False,'gl_control_movement_created':False})
    return {'id':row.lastrowid,'amount_piasters':amount,
            'after_source_due_piasters':before_source+amount,
            'after_target_due_piasters':before_target-amount,'replayed':False,
            'cash_movement_created':False,'gl_control_movement_created':False}
