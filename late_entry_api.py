"""Historical cashier incident and independently approved financial settlements.

Opening a paper incident never posts cash. G2D may clear ALREADY POSTED net
suspense against old patient invoices plus evidenced paper-paid expenses; it
posts exactly one GL journal and NEVER adds a fund movement or cash receipt.
"""
from __future__ import annotations
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Literal
from fastapi import APIRouter, Depends, File, UploadFile, Response
from pydantic import BaseModel, Field
from app import audit, c_piasters, db, fail, get_user, require, valid_date
import cashier_ops
import secrets

router=APIRouter(prefix='/api/late-entries',tags=['Late cashier entries'])
REQUEST=re.compile(r'^[A-Za-z0-9_-]{16,128}$')
REF=re.compile(r'^[A-Z0-9\u0600-\u06ff][A-Z0-9\u0600-\u06ff_./-]{1,75}$')
MAX_EVIDENCE=6*1024*1024
MAX_FILES_PER_INCIDENT=10

def stamp():return datetime.now(timezone.utc).isoformat(timespec='seconds')

def check_point(c,user,point_id):
    require(user,'owner','reviewer','clerk')
    row=c.execute('SELECT id,name,fund_id FROM billing_points WHERE id=?',(point_id,)).fetchone()
    if not row:fail('نقطة التحصيل غير موجودة',404)
    if user['role'] in ('clerk','reviewer') and not c.execute('''SELECT 1 FROM billing_point_access
        WHERE point_id=? AND user_id=? AND active=1''',(point_id,user['id'])).fetchone():
        fail('لا يحق لك عرض مستندات هذه النقطة أو مراجعتها',403)
    return row

def scope(c,user,incident_id):
    row=c.execute('SELECT * FROM late_entry_incidents WHERE id=?',(incident_id,)).fetchone()
    if not row:fail('بلاغ الاستدراك غير موجود',404)
    check_point(c,user,row['point_id'])
    if user['role']=='clerk' and row['opened_by']!=user['id']:
        fail('بلاغ موظف آخر ليس ضمن نطاقك',403)
    return row

def event(c,incident_id,action,note,actor):
    c.execute('INSERT INTO late_entry_events(incident_id,action,note,actor_id,created_at) VALUES (?,?,?,?,?)',
              (incident_id,action,note,actor,stamp()))

class NewIncident(BaseModel):
    request_key:str=Field(min_length=16,max_length=128)
    point_id:int=Field(gt=0)
    business_date:str
    shift_code:str=Field(min_length=2,max_length=32)
    incident_reason:Literal['outage','absence','staff_unavailable','other']
    custodian_name:str=Field(min_length=3,max_length=150)
    cash_location:Literal['drawer','envelope','main_safe','other']
    counted_cash:str|None=None
    source_register_ref:str=Field(default='',max_length=120)
    note:str=Field(min_length=16,max_length=1500)

class PaperDocument(BaseModel):
    paper_ref:str=Field(min_length=2,max_length=76)
    kind:Literal['patient_receipt','expense','transfer']
    amount:str
    method:Literal['cash','card','instapay','wallet','transfer','mixed']='cash'
    note:str=Field(default='',max_length=700)

class FinancialLink(BaseModel):
    source_type:Literal['collection','voucher']
    source_id:int=Field(gt=0)
    note:str=Field(min_length=10,max_length=500)

class RecoverPatientCase(BaseModel):
    """Record the clinical visit; not a receipt, payment, or fake old shift."""
    request_id:str=Field(min_length=16,max_length=96)
    patient_code:str=Field(min_length=3,max_length=40)
    kind:Literal['outpatient','inpatient','operation','nicu']
    note:str=Field(min_length=16,max_length=400)

class ClearBookedCash(BaseModel):
    """Allocate a previously posted suspense receipt; NEVER touch cash again."""
    request_id:str=Field(min_length=16,max_length=96)
    invoice_id:int=Field(gt=0)
    voucher_id:int=Field(gt=0)
    note:str=Field(min_length=16,max_length=600)


class MixedPatientLine(BaseModel):
    document_id:int=Field(gt=0)
    invoice_id:int=Field(gt=0)

class MixedExpenseLine(BaseModel):
    document_id:int=Field(gt=0)
    category_code:str=Field(min_length=3,max_length=45)
    department_id:int=Field(gt=0)

class ClearMixedEnvelope(BaseModel):
    request_id:str=Field(min_length=16,max_length=96)
    voucher_id:int=Field(gt=0)
    patients:list[MixedPatientLine]=Field(min_length=1,max_length=60)
    expenses:list[MixedExpenseLine]=Field(min_length=1,max_length=60)
    approve_variance:bool=False
    note:str=Field(min_length=24,max_length=1000)

# Paper-paid expenses must not hit salary liabilities, stock assets or a generic
# revenue account. They are recognized in GL, NOT as a second cash disbursement.
MIXED_EXPENSE_CATEGORIES=frozenset({
    'expense_medical','doctor_fees','lab_external','rent','utilities',
    'maintenance','marketing','hospitality'
})

class MixedShortageRecoveryRequest(BaseModel):
    request_id:str=Field(min_length=16,max_length=96)
    receipt_ref:str=Field(min_length=4,max_length=76)
    source_type:Literal['employee_deposit','recovered_cash']
    payer_name:str=Field(default='',max_length=150)
    amount:str
    note:str=Field(min_length=24,max_length=700)

class MixedShortageRecoveryDecision(BaseModel):
    decision:Literal['approve','reject']
    counted_amount:str|None=None
    reason:str=Field(min_length=20,max_length=700)

class MixedOverageRefundRequest(BaseModel):
    request_id:str=Field(min_length=16,max_length=96)
    claim_ref:str=Field(min_length=4,max_length=76)
    claimant_name:str=Field(min_length=3,max_length=150)
    evidence_id:int=Field(gt=0)
    amount:str
    note:str=Field(min_length=32,max_length=1000)

class MixedOverageRefundDecision(BaseModel):
    decision:Literal['approve','reject']
    counted_amount:str|None=None
    recipient_receipt_verified:bool=False
    receipt_evidence_id:int|None=None
    reason:str=Field(min_length=24,max_length=1000)

class IncidentAction(BaseModel):
    action:Literal['submit','needs_evidence','triage','resolve']
    note:str=Field(min_length=16,max_length=1500)

@router.get('')
def list_incidents(month:str='',user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    if month and (not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',month)):
        fail('الشهر غير صحيح')
    sql='''SELECT i.id,i.point_id,p.name point_name,i.business_date,i.shift_code,
            i.incident_reason,i.cash_location,i.custodian_name,i.counted_cash_piasters,
            i.status,i.opened_by,i.opened_at,i.reviewed_at,
            (SELECT m.variance_piasters FROM late_mixed_clearances m WHERE m.incident_id=i.id) mixed_variance_piasters,
            (SELECT COALESCE(SUM(r.amount_piasters),0) FROM late_mixed_shortage_recovery_requests r
             JOIN late_mixed_clearances m ON m.id=r.clearance_id
             WHERE m.incident_id=i.id AND r.status='approved') mixed_recovered_piasters,
            (SELECT count(*) FROM late_entry_documents d WHERE d.incident_id=i.id) doc_count,
            (SELECT count(*) FROM late_entry_documents d WHERE d.incident_id=i.id AND
             (d.linked_id IS NOT NULL OR EXISTS
               (SELECT 1 FROM late_cash_allocations a WHERE a.document_id=d.id) OR EXISTS
               (SELECT 1 FROM late_mixed_clearance_lines ml WHERE ml.document_id=d.id))) linked_count
            FROM late_entry_incidents i JOIN billing_points p ON p.id=i.point_id WHERE 1=1'''
    args=[]
    if month:sql+=' AND substr(i.business_date,1,7)=?';args.append(month)
    if user['role']=='clerk':sql+=' AND i.opened_by=?';args.append(user['id'])
    if user['role']=='reviewer':
        sql+=''' AND EXISTS (SELECT 1 FROM billing_point_access a
             WHERE a.point_id=i.point_id AND a.user_id=? AND a.active=1)'''
        args.append(user['id'])
    sql+=' ORDER BY i.business_date DESC,i.id DESC LIMIT 200'
    return {'items':[dict(r) for r in c.execute(sql,args)],
            'notice':'فتح البلاغ لا يرحّل أموالًا؛ التسويات المالية اللاحقة تحتاج مصادر مثبتة ومراجعة مستقلة وتظهر منفصلة.'}

@router.post('')
def open_incident(body:NewIncident,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','clerk')
    if not REQUEST.fullmatch(body.request_key):fail('رمز الطلب غير صالح')
    day=valid_date(body.business_date).isoformat()
    if day>datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat():fail('لا يمكن تسجيل واقعة مستقبلية')
    if not cashier_ops.CODE.fullmatch(body.shift_code):fail('كود الوردية غير صالح')
    counted=c_piasters(body.counted_cash,allow_zero=True) if body.counted_cash not in ('',None) else None
    if len(body.note.strip())<16 or len(body.custodian_name.strip())<3:fail('أكمل بيانات الواقعة')
    payload={'point_id':body.point_id,'business_date':day,'shift_code':body.shift_code,
        'incident_reason':body.incident_reason,'custodian_name':body.custodian_name.strip(),
        'cash_location':body.cash_location,'counted_cash_piasters':counted,
        'source_register_ref':body.source_register_ref.strip(),'note':body.note.strip()}
    checksum=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    with c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT id,opened_by,request_hash FROM late_entry_incidents WHERE request_key=?',(body.request_key,)).fetchone()
        if row:
            if row['opened_by']!=user['id'] or row['request_hash']!=checksum:fail('رمز الطلب مستخدم لواقعة أخرى',409)
            # Idempotency is not an access-control bypass after staff reassignment.
            check_point(c,user,body.point_id)
            return {'id':row['id'],'replayed':True}
        check_point(c,user,body.point_id)
        expected=[x['code'] for x in cashier_ops.slots_for(c,body.point_id,day)]
        historical=c.execute('SELECT 1 FROM shift_sessions WHERE point_id=? AND business_date=? AND shift=?',
                             (body.point_id,day,body.shift_code)).fetchone()
        if body.shift_code not in expected and not historical:
            fail('الوردية غير متوقعة في هذا التاريخ؛ راجع جدول تشغيل النقطة أولًا',409)
        cur=c.execute('''INSERT INTO late_entry_incidents(request_key,request_hash,point_id,
          business_date,shift_code,incident_reason,custodian_name,cash_location,counted_cash_piasters,
          source_register_ref,note,opened_by,opened_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
          (body.request_key,checksum,body.point_id,day,body.shift_code,body.incident_reason,
           payload['custodian_name'],body.cash_location,counted,payload['source_register_ref'],
           payload['note'],user['id'],stamp()))
        event(c,cur.lastrowid,'opened',body.note.strip(),user['id'])
        audit(c,user['id'],'late_incident_opened','late_entry_incident',cur.lastrowid,
              {'point_id':body.point_id,'day':day,'shift':body.shift_code,'financial_posted':False})
    return {'id':cur.lastrowid,'replayed':False,'financial_posted':False}

@router.get('/shortage-open')
def mixed_shortage_board(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    # Minimal worklist; cashier does not see another patient's invoice.

    require(user,'owner','reviewer','clerk')
    user_filter=''
    args=[]
    if user['role']=='clerk':
        user_filter=''' AND EXISTS (SELECT 1 FROM billing_point_access a
           JOIN shift_sessions s ON s.fund_id=p.fund_id
           WHERE a.point_id=p.id AND a.user_id=? AND a.active=1
             AND s.responsible_id=? AND s.status='open' AND s.business_date=?)'''
        args=[user['id'],user['id'],datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()]
    elif user['role']=='reviewer':
        user_filter=''' AND EXISTS (SELECT 1 FROM billing_point_access a
          WHERE a.point_id=p.id AND a.user_id=? AND a.active=1)'''
        args=[user['id']]
    cases=[dict(row) for row in c.execute('''SELECT m.id clearance_id,i.id incident_id,
        i.business_date,i.source_register_ref,p.name point_name,p.id point_id,
        -m.variance_piasters original_shortage_piasters,
        (SELECT COALESCE(SUM(r.amount_piasters),0)
           FROM late_mixed_shortage_recovery_requests r
           WHERE r.clearance_id=m.id AND r.status='approved') recovered_piasters
        FROM late_mixed_clearances m
        JOIN late_entry_incidents i ON i.id=m.incident_id
        JOIN billing_points p ON p.id=i.point_id AND p.kind='internal'
        JOIN gl_journals j ON j.id=m.journal_id AND j.status='posted'
        WHERE m.variance_piasters<0 AND -m.variance_piasters >
          (SELECT COALESCE(SUM(rr.amount_piasters),0)
           FROM late_mixed_shortage_recovery_requests rr
           WHERE rr.clearance_id=m.id AND rr.status='approved')'''+user_filter+'''
        ORDER BY i.business_date DESC,m.id DESC LIMIT 100''',args)]
    for row in cases:
        row['outstanding_piasters']=row['original_shortage_piasters']-row['recovered_piasters']
    return {'items':cases,'notice':'القائمة لا تعرض بيانات المرضى؛ المبالغ الموجودة هنا عجز تاريخي مُعتمد وليس مديونية على الموظف تلقائيًا.'}

@router.get('/overage-open')
def mixed_overage_board(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    extra='';args=[]
    if user['role']=='clerk':
        extra=''' AND EXISTS (SELECT 1 FROM billing_point_access a
          JOIN shift_sessions s ON s.fund_id=p.fund_id
          WHERE a.point_id=p.id AND a.user_id=? AND a.active=1
            AND s.responsible_id=? AND s.status='open' AND s.business_date=?)'''
        args=[user['id'],user['id'],datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()]
    elif user['role']=='reviewer':
        extra=''' AND EXISTS (SELECT 1 FROM billing_point_access a
          WHERE a.point_id=p.id AND a.user_id=? AND a.active=1)'''
        args=[user['id']]
    cases=[dict(row) for row in c.execute('''SELECT m.id clearance_id,i.id incident_id,
       i.business_date,i.source_register_ref,p.name point_name,p.id point_id,
       m.variance_piasters original_overage_piasters,
       (SELECT COALESCE(SUM(r.amount_piasters),0) FROM late_mixed_overage_refund_requests r
        WHERE r.clearance_id=m.id AND r.status='approved') refunded_piasters
       FROM late_mixed_clearances m
       JOIN late_entry_incidents i ON i.id=m.incident_id
       JOIN billing_points p ON p.id=i.point_id AND p.kind='internal'
       JOIN gl_journals j ON j.id=m.journal_id AND j.status='posted'
       WHERE m.variance_piasters>0 AND m.variance_piasters>
         (SELECT COALESCE(SUM(r.amount_piasters),0) FROM late_mixed_overage_refund_requests r
          WHERE r.clearance_id=m.id AND r.status='approved')'''+extra+'''
       ORDER BY i.business_date DESC,m.id DESC LIMIT 100''',args)]
    for row in cases:
        row['outstanding_piasters']=row['original_overage_piasters']-row['refunded_piasters']
    return {'items':cases,'notice':'زيادة العهدة التزام قيد التحقيق، وليست إيرادًا. لا صرف إلا لمستحق موثق بتسليم فعلي واعتماد مستقل.'}

@router.get('/{incident_id}')
def detail(incident_id:int,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    row=scope(c,user,incident_id)
    docs=[dict(r) for r in c.execute('''SELECT d.id,d.paper_ref,d.kind,d.method,d.amount_piasters,
          d.linked_kind,d.linked_id,d.created_at,
          (SELECT a.id FROM late_cash_allocations a WHERE a.document_id=d.id) cash_clearance_id,
          (SELECT ml.clearance_id FROM late_mixed_clearance_lines ml WHERE ml.document_id=d.id) mixed_clearance_id
          FROM late_entry_documents d WHERE d.incident_id=? ORDER BY d.id''',(incident_id,))]
    events=[dict(r) for r in c.execute('''SELECT e.action,e.note,e.actor_id,e.created_at,u.username
          FROM late_entry_events e JOIN users u ON u.id=e.actor_id WHERE e.incident_id=? ORDER BY e.id''',(incident_id,))]
    proofs=[dict(r) for r in c.execute('''SELECT id,filename,mime,sha256,uploaded_at
          FROM late_entry_evidence WHERE incident_id=? ORDER BY id''',(incident_id,))]
    recovered=[dict(r) for r in c.execute('''SELECT l.case_id,l.paper_document_id,l.original_business_date,
       b.case_no,b.kind,(SELECT i.invoice_no FROM billing_invoices i WHERE i.case_id=b.id
       ORDER BY i.id DESC LIMIT 1) issued_invoice_no,
       (SELECT i.id FROM billing_invoices i WHERE i.case_id=b.id
       ORDER BY i.id DESC LIMIT 1) issued_invoice_id
       FROM billing_late_cases l JOIN billing_cases b ON b.id=l.case_id
       WHERE l.incident_id=? ORDER BY l.case_id''',(incident_id,))]
    allocations=[dict(r) for r in c.execute('''SELECT a.id,a.document_id,a.invoice_id,a.voucher_id,
       a.amount_piasters,a.journal_id,a.authorized_at,a.authorized_by,v.voucher_no
       FROM late_cash_allocations a JOIN vouchers v ON v.id=a.voucher_id
       WHERE a.incident_id=? ORDER BY a.id''',(incident_id,))]
    mixed=c.execute('SELECT * FROM late_mixed_clearances WHERE incident_id=?',(incident_id,)).fetchone()
    mixed_lines=[dict(r) for r in c.execute('''SELECT ml.document_id,ml.line_kind,ml.invoice_id,
        ml.category_id,ml.department_id,ml.amount_piasters FROM late_mixed_clearance_lines ml
        JOIN late_mixed_clearances mc ON mc.id=ml.clearance_id WHERE mc.incident_id=?''',(incident_id,))]
    recovery=[dict(r) for r in c.execute('''SELECT r.id,r.clearance_id,r.receipt_ref,r.source_type,
        r.payer_name,r.amount_piasters,r.evidence_note,r.status,r.proposed_by,r.proposed_at,
        r.decided_by,r.decided_at,r.decision_note,r.voucher_id,
        u.username proposed_by_name,rev.username decided_by_name,v.voucher_no
        FROM late_mixed_shortage_recovery_requests r
        JOIN users u ON u.id=r.proposed_by
        LEFT JOIN users rev ON rev.id=r.decided_by
        LEFT JOIN vouchers v ON v.id=r.voucher_id
        WHERE r.clearance_id=(SELECT id FROM late_mixed_clearances WHERE incident_id=?)
        ORDER BY r.id''',(incident_id,))]
    overage_refunds=[dict(r) for r in c.execute('''SELECT r.id,r.claim_ref,r.claimant_name,
       r.evidence_id,r.amount_piasters,r.evidence_note,r.status,r.proposed_by,r.proposed_at,
       r.decided_by,r.decided_at,r.decision_note,r.voucher_id,
       maker.username proposed_by_name,rev.username decided_by_name,v.voucher_no
       FROM late_mixed_overage_refund_requests r
       JOIN users maker ON maker.id=r.proposed_by
       LEFT JOIN users rev ON rev.id=r.decided_by
       LEFT JOIN vouchers v ON v.id=r.voucher_id
       WHERE r.clearance_id=(SELECT id FROM late_mixed_clearances WHERE incident_id=?)
       ORDER BY r.id''',(incident_id,))]
    overage_total=max(0,int(mixed['variance_piasters'])) if mixed else 0
    overage_returned=sum(x['amount_piasters'] for x in overage_refunds if x['status']=='approved')
    shortage_total=max(0,-int(mixed['variance_piasters'])) if mixed else 0
    repaid_total=sum(x['amount_piasters'] for x in recovery if x['status']=='approved')
    return {'point_kind':c.execute('SELECT kind FROM billing_points WHERE id=?',(row['point_id'],)).fetchone()[0],
            'mixed_clearance':dict(mixed) if mixed else None,'mixed_lines':mixed_lines,
            'shortage_total_piasters':shortage_total,'shortage_recovered_piasters':repaid_total,
            'shortage_outstanding_piasters':shortage_total-repaid_total,
            'mixed_shortage_recovery_requests':recovery,
            'overage_total_piasters':overage_total,
            'overage_refunded_piasters':overage_returned,
            'overage_outstanding_piasters':overage_total-overage_returned,
            'mixed_overage_refund_requests':overage_refunds,
            'incident':dict(row),'documents':docs,'events':events,'evidence':proofs,
            'recovered_cases':recovered,'cash_allocations':allocations,
            'cash_reallocated_piasters':sum(a['amount_piasters'] for a in allocations),
            'cash_newly_booked_piasters':0}

@router.post('/{incident_id}/documents')
def add_document(incident_id:int,body:PaperDocument,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','clerk')
    paper_ref=body.paper_ref.strip().upper()
    if not REF.fullmatch(paper_ref):fail('مرجع الورقة يجب أن يتكون من حروف وأرقام وشرطات فقط')
    amount=c_piasters(body.amount)
    if body.kind!='patient_receipt' and body.method!='cash':fail('المصروف والتحويل النقدي يجب تسجيلهما كحركة نقدية',409)
    with c:
        c.execute('BEGIN IMMEDIATE')
        inc=scope(c,user,incident_id)
        if inc['status'] not in ('draft','needs_evidence'):fail('لا يمكن إضافة مستند بعد تقديم البلاغ للمراجعة',409)
        try:
            cur=c.execute('''INSERT INTO late_entry_documents(incident_id,point_id,business_date,
             paper_ref,kind,method,amount_piasters,note,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)''',
             (incident_id,inc['point_id'],inc['business_date'],paper_ref,body.kind,
              body.method,amount,body.note.strip(),user['id'],stamp()))
        except sqlite3.IntegrityError:fail('هذا المرجع الورقي مكرر في يوم نفس نقطة التحصيل',409)
        event(c,incident_id,'document_added','المستند '+paper_ref,user['id'])
        audit(c,user['id'],'late_document_added','late_entry_document',cur.lastrowid,
              {'incident_id':incident_id,'amount_piasters':amount,'financial_posted':False})
    return {'id':cur.lastrowid,'financial_posted':False}

@router.post('/{incident_id}/documents/{document_id}/link')
def match_document(incident_id:int,document_id:int,body:FinancialLink,
                   user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    with c:
        c.execute('BEGIN IMMEDIATE')
        inc=scope(c,user,incident_id)
        doc=c.execute('SELECT * FROM late_entry_documents WHERE id=? AND incident_id=?',
                      (document_id,incident_id)).fetchone()
        if not doc:fail('المستند الورقي غير موجود',404)
        if doc['linked_id'] is not None:fail('المستند مربوط بالفعل بحركة أصلية',409)
        if c.execute('SELECT 1 FROM late_mixed_clearance_lines WHERE document_id=?',(document_id,)).fetchone():
            fail('المستند مستخدم في تسوية ظرف مختلط معتمدة',409)
        if c.execute('SELECT 1 FROM late_cash_allocations WHERE document_id=?',(document_id,)).fetchone():
            fail('المستند سُوّي مسبقًا مع النقدية غير المخصصة؛ لا تربطه بإيصال آخر',409)
        if inc['opened_by']==user['id']:fail('لا يجوز لصاحب البلاغ مطابقة مستنداته بنفسه',403)
        if inc['status'] not in ('submitted','triaged'):fail('يجب تقديم البلاغ للمراجعة أولًا',409)
        if doc['kind']=='patient_receipt':
            if body.source_type!='collection':fail('التحصيل يجب أن يطابق إيصال مريض إلكترونيًا',409)
            original=c.execute('''SELECT b.id,b.point_id,b.business_date,b.total_piasters,
                    s.shift actual_shift FROM billing_collections b
                    JOIN shift_sessions s ON s.id=b.shift_session_id WHERE b.id=?''',
                    (body.source_id,)).fetchone()
            if (not original or original['point_id']!=inc['point_id'] or
                original['business_date']!=inc['business_date'] or
                original['total_piasters']!=doc['amount_piasters'] or
                original['actual_shift']!=inc['shift_code']):
                fail('الإيصال الإلكتروني لا يطابق النقطة والوردية والتاريخ والمبلغ الوارد في المستند',409)
            # Once this paper evidence spawned a recovered case, it must not be
            # silently settled by a different patient's receipt of same amount.
            old_case=c.execute('SELECT case_id FROM billing_late_cases WHERE paper_document_id=?',
                               (doc['id'],)).fetchone()
            if old_case and c.execute('SELECT case_id FROM billing_collections WHERE id=?',
                                      (body.source_id,)).fetchone()[0]!=old_case['case_id']:
                fail('هذه الورقة مرتبطة بملف مريض مستدرك مختلف؛ لا يمكن تخصيص قبض مريض آخر لها',409)
            methods={r[0] for r in c.execute('SELECT DISTINCT method FROM billing_payment_parts WHERE collection_id=?',(body.source_id,))}
            if (doc['method']=='mixed' and len(methods)<2) or (
                doc['method']!='mixed' and methods!={doc['method']}):
                fail('وسيلة الدفع لا تطابق الإيصال الإلكتروني',409)
        else:
            if body.source_type!='voucher':fail('المصروف أو التحويل يطابق سندًا معتمدًا',409)
            original=c.execute('''SELECT v.* FROM vouchers v WHERE v.id=?''',
                               (body.source_id,)).fetchone()
            expected_kind={'expense':'payment','transfer':'transfer'}[doc['kind']]
            point=c.execute('SELECT fund_id FROM billing_points WHERE id=?',(inc['point_id'],)).fetchone()
            if (not original or original['status']!='approved' or
                original['kind']!=expected_kind or
                original['amount_piasters']!=doc['amount_piasters'] or
                original['from_fund_id']!=point['fund_id']):
                fail('السند الإلكتروني المعتمد لا يطابق نوع الحركة أو خزنتها أو مبلغها',409)
            # A genuine cashier-to-treasury handoff is booked on its actual
            # receipt date, which may be the NEXT day. Match the SOURCE shift
            # rather than mistakenly requiring the treasury deposit date.
            deposit=c.execute('''SELECT s.shift,s.business_date FROM cashier_treasury_transfers t
                  JOIN shift_sessions s ON s.id=t.source_shift_id
                  WHERE t.voucher_id=?''',(body.source_id,)).fetchone()
            if doc['kind']=='transfer' and deposit:
                if deposit['business_date']!=inc['business_date'] or deposit['shift']!=inc['shift_code']:
                    fail('هذه التوريدة تخص وردية أصلية مختلفة',409)
            else:
                if original['date']!=inc['business_date']:
                    fail('تاريخ سند المصروف أو التحويل لا يطابق الواقعة',409)
                posted_shift=c.execute('''SELECT s.shift FROM fund_movements m
                        JOIN shift_sessions s ON s.id=m.shift_session_id
                        WHERE m.voucher_id=? AND m.fund_id=?''',
                        (body.source_id,point['fund_id'])).fetchone()
                if not posted_shift or posted_shift['shift']!=inc['shift_code']:
                    fail('السند المعتمد ليس مرحلًا على عهدة الوردية الأصلية المحددة',409)
        try:
            changed=c.execute('''UPDATE late_entry_documents SET linked_kind=?,linked_id=?,linked_by=?,linked_at=?
               WHERE id=? AND linked_id IS NULL''',(body.source_type,body.source_id,user['id'],stamp(),doc['id']))
        except sqlite3.IntegrityError:fail('هذه الحركة الإلكترونية مستخدمة بالفعل في مستند آخر',409)
        if changed.rowcount!=1:fail('تمت مطابقة المستند من قبل',409)
        event(c,incident_id,'linked',doc['paper_ref']+' ← '+body.source_type+' #'+str(body.source_id)+' — '+body.note.strip(),user['id'])
        audit(c,user['id'],'late_document_linked','late_entry_document',doc['id'],
             {'source_type':body.source_type,'source_id':body.source_id,'financial_posted':False})
    return {'id':document_id,'linked':True,'financial_posted':False}

@router.post('/{incident_id}/documents/{document_id}/recover-case')
def recover_case(incident_id:int,document_id:int,body:RecoverPatientCase,
                 user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    """Backfill an old unrecorded VISIT, not an old CASH event.

    A separate reviewer must have triaged the incident; a unique paper
    document may be used once. Services use prices effective on the original
    day, while invoices post to today's OPEN month. No GL or cash movements here.
    """
    require(user,'owner','clerk')
    import billing
    key=billing.request_key(body.request_id)
    note=billing.trim(body.note,'سبب الاستدراك',16,400)
    patient_code=body.patient_code.strip().upper()
    payload={'incident_id':incident_id,'document_id':document_id,
             'patient_code':patient_code,'kind':body.kind,'note':note}
    with c:
        c.execute('BEGIN IMMEDIATE')
        incident=scope(c,user,incident_id)
        check_point(c,user,incident['point_id'])
        prior,fingerprint=billing.repeat(c,key,'recover_case',user['id'],payload)
        if prior:
            # New assignment/revocation cannot be bypassed using an old key.
            billing.can_point(c,user,incident['point_id'],write=True)
            return {'id':prior,'replayed':True,'financial_posted':False}
        if incident['status']!='triaged' or not incident['reviewed_by'] or incident['reviewed_by']==user['id']:
            fail('يجب أن يراجع شخص مستقل بلاغ الاستدراك أولًا',409)
        doc=c.execute('SELECT * FROM late_entry_documents WHERE id=? AND incident_id=?',
                      (document_id,incident_id)).fetchone()
        if not doc or doc['kind']!='patient_receipt' or doc['linked_id'] is not None:
            fail('اختر مستند مريض غير مرتبط من نفس الواقعة',409)
        if c.execute('SELECT 1 FROM billing_late_cases WHERE paper_document_id=?',(document_id,)).fetchone():
            fail('تم استخدام هذا المستند في تسجيل ملف حالة سابق؛ لا تكرره',409)
        point=c.execute('SELECT * FROM billing_points WHERE id=?',(incident['point_id'],)).fetchone()
        billing.can_point(c,user,point['id'],write=True)
        if point['kind']!=billing.POINT_DEFAULTS[body.kind]:
            fail('نوع الحالة لا يطابق نقطة التحصيل القديمة؛ يلزم إعادة فحص الأصل',409)
        patient=c.execute('SELECT * FROM billing_patients WHERE code=?',(patient_code,)).fetchone()
        if not patient:fail('كود المريض غير موجود؛ أنشئ ملفه أولًا إلكترونيًا',404)
        # Historical closed accounting months are never reopened.
        current=billing.cairo_today()
        billing.month_open(c,current[:7])
        if incident['business_date']>current:fail('تاريخ الواقعة مستقبلي',409)
        cur=c.execute("""INSERT INTO billing_cases(case_no,patient_id,kind,default_point_id,business_date,
                opened_by,opened_at,notes) VALUES (?,?,?,?,?,?,?,?)""",
              ('OPEN-'+secrets.token_hex(6),patient['id'],body.kind,point['id'],
               incident['business_date'],user['id'],stamp(),'استدراك موثق: '+note))
        case_id=cur.lastrowid
        num='CASE-'+incident['business_date'][:4]+'-'+f'{case_id:06d}'
        c.execute('UPDATE billing_cases SET case_no=? WHERE id=?',(num,case_id))
        c.execute("""INSERT INTO billing_late_cases(case_id,incident_id,paper_document_id,
            original_business_date,recorded_accounting_date,recorded_by,recorded_at,authorization_note) VALUES (?,?,?,?,?,?,?,?)""",
            (case_id,incident_id,document_id,incident['business_date'],current,user['id'],stamp(),note))
        billing.remember(c,key,'recover_case',user['id'],fingerprint,case_id)
        event(c,incident_id,'patient_case_recorded',
              'تم تسجيل ملف '+num+' من مستند '+doc['paper_ref']+'؛ دون تحصيل أو ترحيل مالي',user['id'])
        audit(c,user['id'],'billing_late_case_created','billing_case',case_id,
              {'incident_id':incident_id,'paper_document_id':document_id,
               'original_service_date':incident['business_date'],'posted_cash':False})
    return {'id':case_id,'case_no':num,'original_business_date':incident['business_date'],
            'recorded_on':current,'financial_posted':False,'cash_posted':False,'replayed':False,
            'next_step':'أدخل الخدمات وأثبت تنفيذها مع المراجع ثم أصدر الفاتورة في الشهر المفتوح. لا تسجل قبضًا قديمًا.'}


@router.post('/{incident_id}/documents/{document_id}/clear-booked-cash')
def clear_booked_cash(incident_id:int,document_id:int,body:ClearBookedCash,
                      user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    """G2C: DR 2350 / CR 1200. No fund movement, new patient receipt, or old-period edit.

    An independently approved suspense voucher is the ONLY acceptable source.
    One such voucher may cover several cash paper receipts from the same envelope.
    """
    require(user,'owner','reviewer')
    import billing,ledger
    key=billing.request_key(body.request_id)
    note=billing.trim(body.note,'سبب تسوية النقدية التاريخية',16,600)
    payload={'incident_id':incident_id,'document_id':document_id,
             'invoice_id':body.invoice_id,'voucher_id':body.voucher_id,'note':note}
    with c:
        c.execute('BEGIN IMMEDIATE')
        inc=scope(c,user,incident_id)
        previous,fingerprint=billing.repeat(c,key,'clear_booked_late_cash',user['id'],payload)
        if previous:
            return {'id':previous,'replayed':True,'cash_newly_booked_piasters':0}
        if inc['status']!='triaged' or not inc['reviewed_by']:
            fail('الواقعة غير جاهزة للتسوية؛ يلزم فحص مستقل أولًا',409)
        if inc['opened_by']==user['id'] or inc['reviewed_by']==inc['opened_by']:
            fail('المطابقة المالية تحتاج شخصًا مستقلًا عن صاحب البلاغ',403)
        doc=c.execute('SELECT * FROM late_entry_documents WHERE id=? AND incident_id=?',
                      (document_id,incident_id)).fetchone()
        if not doc or doc['kind']!='patient_receipt' or doc['method']!='cash' or doc['linked_id']:
            fail('هذه التسوية مخصصة لإيصال مريض نقدي لم يسبق ربطه',409)
        if c.execute('SELECT 1 FROM late_cash_allocations WHERE document_id=?',(document_id,)).fetchone():
            fail('تمت تسوية المستند مسبقًا',409)
        if c.execute('SELECT 1 FROM late_mixed_clearances WHERE incident_id=?',(incident_id,)).fetchone():
            fail('الظرف تمت تسويته بالكامل كظرف مختلط',409)
        if c.execute("SELECT 1 FROM late_entry_documents WHERE incident_id=? AND kind='expense' AND linked_id IS NULL",(incident_id,)).fetchone():
            fail('الظرف فيه مصروف نقدي غير مسجل؛ استخدم تسوية الظرف المختلط بدل تخصيص النقدية منفردة',409)
        if not inc['source_register_ref'] or inc['counted_cash_piasters'] is None:
            fail('يلزم رقم الظرف وقيمة جرد فعلية موثقة قبل تخصيص النقدية',409)
        late=c.execute('''SELECT l.case_id,l.recorded_by,i.id invoice_id,i.issued_by,
              i.total_piasters,j.status posted_status FROM billing_late_cases l
              JOIN billing_invoices i ON i.case_id=l.case_id
              JOIN gl_journals j ON j.id=i.journal_id
              WHERE l.paper_document_id=? AND l.incident_id=? AND i.id=?''',
              (document_id,incident_id,body.invoice_id)).fetchone()
        if not late or late['posted_status']!='posted':
            fail('يجب إصدار فاتورة الحالة المستدركة وترحيلها للأستاذ أولًا',409)
        voucher=c.execute('''SELECT v.*,cat.code category_code,f.kind fund_kind,f.active fund_active
             FROM vouchers v JOIN categories cat ON cat.id=v.category_id
             JOIN funds f ON f.id=v.from_fund_id WHERE v.id=?''',(body.voucher_id,)).fetchone()
        if (not voucher or voucher['kind']!='receipt' or voucher['status']!='approved'
            or voucher['category_code']!='late_cash_unallocated'
            or voucher['fund_kind']!='cash' or not voucher['fund_active']):
            fail('سند المصدر يجب أن يكون قبض نقدية غير مخصصة معتمدًا ومُرحّلًا',409)
        if not c.execute('''SELECT 1 FROM billing_points WHERE kind='internal' AND fund_id=?''',
                         (voucher['from_fund_id'],)).fetchone():
            fail('سند النقدية غير المخصصة ليس من الخزنة الرئيسية الداخلية',409)
        if voucher['date']<inc['business_date'] or voucher['date']>billing.cairo_today():
            fail('تاريخ استلام الظرف لا يتفق مع تاريخ الواقعة',409)
        if voucher['reference_no'].strip().upper()!=inc['source_register_ref'].strip().upper():
            fail('مرجع سند الخزنة مختلف عن رقم الظرف المثبت في الواقعة',409)
        if voucher['amount_piasters']!=inc['counted_cash_piasters']:
            fail('النقدية المعتمدة بالخزنة تختلف عن جرد الظرف؛ يجب التحقيق في الفرق أولًا',409)
        if not voucher['reviewed_by'] or voucher['reviewed_by']==voucher['created_by']:
            fail('سند النقدية الأصلية يحتاج اعتماد شخص غير منشئ السند',409)
        cash_journal=c.execute('''SELECT j.id FROM gl_journals j JOIN gl_lines l ON l.journal_id=j.id
           WHERE j.origin='voucher' AND j.source_id=? AND j.status='posted'
           AND l.account_id=? AND l.credit_piasters=?''',
           (voucher['id'],ledger.account_by_code(c,'2350'),voucher['amount_piasters'])).fetchone()
        if not cash_journal:
            fail('لا يوجد قيد نقدية غير مخصصة معتمد ومتوازن في دفتر الأستاذ',409)
        if user['id'] in (late['recorded_by'],late['issued_by'],voucher['created_by'],doc['created_by']):
            fail('لا يجوز لمُدخل المستند أو مُصدر الفاتورة أو مُنشئ القبض اعتماد تسويته',403)
        if c.execute('''SELECT 1 FROM late_cash_allocations
              WHERE voucher_id=? AND incident_id<>? LIMIT 1''',(voucher['id'],incident_id)).fetchone():
            fail('الظرف سبق تخصيصه لواقعة أخرى',409)
        allocated=c.execute('''SELECT COALESCE(SUM(amount_piasters),0) FROM late_cash_allocations
             WHERE voucher_id=?''',(voucher['id'],)).fetchone()[0]
        amount=doc['amount_piasters']
        if amount>voucher['amount_piasters']-allocated:
            fail('مبلغ إيصال المريض أكبر من المتبقي في الظرف المُرحّل',409)
        if billing.invoice_due(c,body.invoice_id)!=amount:
            fail('للتسوية الآلية يجب أن يطابق إيصال المريض كامل الرصيد المتبقي للفاتورة',409)
        today=billing.cairo_today();billing.month_open(c,today[:7])
        journal=ledger._journal(c,entry_date=today,
           memo='تخصيص عهدة نقدية تاريخية '+inc['source_register_ref']+' إلى فاتورة #'+str(body.invoice_id),
           origin='manual',source_id=None,created_by=late['recorded_by'],reviewed_by=user['id'],
           lines=[(ledger.account_by_code(c,'2350'),amount,0,None),
                  (ledger.account_by_code(c,'1200'),0,amount,None)])
        cur=c.execute('''INSERT INTO late_cash_allocations(incident_id,document_id,case_id,invoice_id,
             voucher_id,amount_piasters,journal_id,authorized_by,authorized_at,reason)
             VALUES (?,?,?,?,?,?,?,?,?,?)''',
             (incident_id,document_id,late['case_id'],body.invoice_id,voucher['id'],amount,
              journal,user['id'],stamp(),note))
        billing.remember(c,key,'clear_booked_late_cash',user['id'],fingerprint,cur.lastrowid)
        event(c,incident_id,'cash_cleared','ورقة '+doc['paper_ref']+' ← سند '+voucher['voucher_no']+
              ' / فاتورة #'+str(body.invoice_id)+' — '+note,user['id'])
        audit(c,user['id'],'late_cash_cleared','late_cash_allocation',cur.lastrowid,
              {'voucher_id':voucher['id'],'invoice_id':body.invoice_id,'amount_piasters':amount,
               'journal_id':journal,'cash_newly_booked_piasters':0})
    return {'id':cur.lastrowid,'journal_id':journal,'amount_piasters':amount,
            'replayed':False,'cash_newly_booked_piasters':0,
            'next_step':'راجع بقية مستندات الظرف ثم اعتمد انتهاء الواقعة رقابيًا.'}


@router.post('/{incident_id}/clear-mixed-envelope')
def clear_mixed_envelope(incident_id:int,body:ClearMixedEnvelope,
                        user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    '''G2D: clear posted NET suspense and documented historical paper expenses.

    Example: gross patient receipts 1500; spent 200 from those receipts;
    counted NET banked cash 1300. DR suspense 1300, DR expense 200, CR AR 1500.
    This is NOT a voucher, a patient cash receipt, or a fund movement.
    '''
    require(user,'owner','reviewer')
    import billing,ledger
    key=billing.request_key(body.request_id)
    note=billing.trim(body.note,'سبب التسوية المختلطة',24,1000)
    if len({x.document_id for x in body.patients+body.expenses})!=len(body.patients)+len(body.expenses):
        fail('المستند مكرر في تفاصيل التسوية',409)
    if len({x.invoice_id for x in body.patients})!=len(body.patients):
        fail('لا يمكن استخدام الفاتورة نفسها مرتين',409)
    payload={'incident_id':incident_id,'voucher_id':body.voucher_id,
      'patients':[x.model_dump() for x in body.patients],
      'expenses':[x.model_dump() for x in body.expenses],
      'approve_variance':body.approve_variance,'note':note}
    checksum=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    with c:
        c.execute('BEGIN IMMEDIATE')
        inc=scope(c,user,incident_id)
        existing=c.execute('SELECT * FROM late_mixed_clearances WHERE request_key=?',(key,)).fetchone()
        if existing:
            if existing['authorized_by']!=user['id'] or existing['request_hash']!=checksum:
                fail('رمز التسوية مستخدم في عملية أخرى',409)
            return {'id':existing['id'],'replayed':True,'journal_id':existing['journal_id'],
                    'variance_piasters':existing['variance_piasters'],'cash_newly_booked_piasters':0}
        if inc['status']!='triaged' or not inc['reviewed_by'] or inc['opened_by']==user['id']:
            fail('التسوية تتطلب واقعة راجعها شخص مستقل عن صاحبها',403)
        if not inc['source_register_ref'] or inc['counted_cash_piasters'] is None:
            fail('يلزم رقم الظرف وجرد فعلي موثق',409)
        point=c.execute('SELECT kind FROM billing_points WHERE id=?',(inc['point_id'],)).fetchone()
        if not point or point['kind']!='internal':
            fail('تسوية المصروف من نفس التحصيل متاحة للخزنة الداخلية فقط؛ الخارجي يحتاج تسليم عهدة موثق',409)
        if c.execute('SELECT 1 FROM late_mixed_clearances WHERE incident_id=? OR voucher_id=?',
                     (incident_id,body.voucher_id)).fetchone():
            fail('هذه الواقعة أو سند الظرف تمت تسويته من قبل',409)
        if c.execute('SELECT 1 FROM late_cash_allocations WHERE incident_id=? OR voucher_id=?',
                     (incident_id,body.voucher_id)).fetchone():
            fail('بدأ تخصيص نقدية من هذا الظرف بالفعل؛ يجب إنهاؤه في المسار الأصلي',409)
        documents=list(c.execute('SELECT * FROM late_entry_documents WHERE incident_id=?',(incident_id,)))
        if len(documents)!=len(body.patients)+len(body.expenses):
            fail('لا يمكن اعتماد الظرف حتى تُدرج جميع مستنداته مرة واحدة، بدون تحويلات مختلطة',409)
        docs={x['id']:x for x in documents}
        if any(x['kind'] not in ('patient_receipt','expense') or x['method']!='cash'
               or x['linked_id'] is not None for x in documents):
            fail('الظرف المختلط يقبل إيصالات مرضى ومصروفات نقدية غير مرحّلة فقط؛ التحويلات تحتاج مطابقة منفصلة',409)
        if any(x['kind']!='patient_receipt' for x in (docs.get(a.document_id) for a in body.patients) if x is not None) or any(
              x['kind']!='expense' for x in (docs.get(a.document_id) for a in body.expenses) if x is not None):
            fail('نوع المستند لا يطابق تفاصيل التسوية',409)
        if set(docs)!={x.document_id for x in body.patients+body.expenses}:
            fail('جميع إيصالات المرضى والمصروفات يجب تمثيلها في التسوية',409)
        if not c.execute('SELECT 1 FROM late_entry_evidence WHERE incident_id=?',(incident_id,)).fetchone():
            fail('يلزم مستند إثبات مرفوع عند اعتماد مصروف مدفوع من ظرف قديم',409)
        voucher=c.execute('''SELECT v.*,cat.code category_code,f.kind fund_kind,f.active fund_active
               FROM vouchers v JOIN categories cat ON cat.id=v.category_id
               JOIN funds f ON f.id=v.from_fund_id WHERE v.id=?''',(body.voucher_id,)).fetchone()
        if not voucher or voucher['kind']!='receipt' or voucher['status']!='approved' or voucher['category_code']!='late_cash_unallocated' or voucher['fund_kind']!='cash' or not voucher['fund_active']:
            fail('سند الظرف يجب أن يكون نقدية غير مخصصة معتمدة ومُرحّلة',409)
        if not c.execute("SELECT 1 FROM billing_points WHERE kind='internal' AND fund_id=?",(voucher['from_fund_id'],)).fetchone():
            fail('السند ليس من الخزنة الرئيسية',409)
        if (voucher['reference_no'].strip().upper()!=inc['source_register_ref'].strip().upper() or
            voucher['amount_piasters']!=inc['counted_cash_piasters'] or
            voucher['date']<inc['business_date'] or voucher['date']>billing.cairo_today()):
            fail('مرجع الظرف وتاريخه والنقدية المستلمة لا تطابق السند المعتمد',409)
        if not voucher['reviewed_by'] or voucher['created_by']==voucher['reviewed_by']:
            fail('سند استلام النقدية يحتاج اعتمادًا مستقلًا',409)
        if user['id'] in (voucher['created_by'],inc['opened_by']) or any(
            x['created_by']==user['id'] for x in documents):
            fail('لا يجوز لمُدخل مستندات الظرف أو منشئ السند اعتماد التسوية',403)
        source=c.execute('''SELECT j.id FROM gl_journals j JOIN gl_lines l ON l.journal_id=j.id
              WHERE j.origin='voucher' AND j.source_id=? AND j.status='posted'
              AND l.account_id=? AND l.credit_piasters=?''',
              (voucher['id'],ledger.account_by_code(c,'2350'),voucher['amount_piasters'])).fetchone()
        if not source:fail('سند الظرف غير مثبت في دفتر الأستاذ بحساب النقدية غير المخصصة',409)
        patients=[];expenses=[]
        for item in body.patients:
            doc=docs[item.document_id]
            late=c.execute('''SELECT l.case_id,l.recorded_by,i.id invoice_id,i.issued_by,
                j.status posted_status FROM billing_late_cases l
                JOIN billing_invoices i ON i.case_id=l.case_id
                JOIN gl_journals j ON j.id=i.journal_id
                WHERE l.incident_id=? AND l.paper_document_id=? AND i.id=?''',
                (incident_id,item.document_id,item.invoice_id)).fetchone()
            if not late or late['posted_status']!='posted' or user['id'] in (late['recorded_by'],late['issued_by']):
                fail('كل فاتورة يجب أن تكون صادرة من واقعة الاستدراك ومثبتة ومستقلة عن معتمد التسوية',409)
            if billing.invoice_due(c,item.invoice_id)!=doc['amount_piasters']:
                fail('الرصيد المتبقي للفاتورة لا يطابق كامل مبلغ إيصال المريض',409)
            if c.execute('SELECT 1 FROM late_mixed_clearance_lines WHERE invoice_id=?',(item.invoice_id,)).fetchone():
                fail('تمت تسوية الفاتورة سابقًا بظرف مختلط',409)
            patients.append((doc,item.invoice_id,late['case_id']))
        for item in body.expenses:
            doc=docs[item.document_id]
            if len(doc['note'].strip())<12:fail('كل مصروف تاريخي يحتاج بيانًا مفصلًا على المستند',409)
            if item.category_code not in MIXED_EXPENSE_CATEGORIES:
                fail('التصنيف غير مسموح لتسوية مصروفات ظرف تاريخي',409)
            category=c.execute("SELECT id,direction,active FROM categories WHERE code=?",(item.category_code,)).fetchone()
            department=c.execute('SELECT id FROM departments WHERE id=? AND active=1',(item.department_id,)).fetchone()
            if not category or not category['active'] or category['direction']!='payment' or not department:
                fail('تصنيف المصروف أو مركز تكلفته غير متاح',409)
            account=ledger.account_by_code(c,ledger.CATEGORY_TO_ACCOUNT[item.category_code])
            expenses.append((doc,category['id'],item.department_id,account))
        gross=sum(doc['amount_piasters'] for doc,_,_ in patients)
        spent=sum(doc['amount_piasters'] for doc,_,_,_ in expenses)
        if spent>=gross:fail('المصروفات تستنفد تحصيل المرضى؛ يلزم إثبات مصدر نقدية مستقل',409)
        expected=gross-spent
        actual=int(inc['counted_cash_piasters'])
        variance=actual-expected
        if variance:
            if not body.approve_variance:
                fail('يوجد فرق جرد، ولا يمكن إقفال الظرف دون موافقة استثنائية صريحة',409)
            grant=c.execute('''SELECT can_approve FROM cashier_variance_permissions WHERE user_id=?''',
                            (user['id'],)).fetchone()
            if user['role']!='owner' and (not grant or not grant['can_approve']):
                fail('قبول العجز أو الزيادة يحتاج تفويضًا مستقلًا من مالك النظام',403)
            if len(note)<36:fail('موافقة فرق العهدة تحتاج شرحًا مفصلًا',409)
        else:
            if body.approve_variance:fail('لا يوجد فرق جرد لاعتماد استثنائي',409)
        today=billing.cairo_today();billing.month_open(c,today[:7])
        lines=[(ledger.account_by_code(c,'2350'),actual,0,None)]
        lines.extend((account,doc['amount_piasters'],0,dept) for doc,_,dept,account in expenses)
        if variance<0:lines.append((ledger.account_by_code(c,'1190'),-variance,0,None))
        lines.extend((ledger.account_by_code(c,'1200'),0,doc['amount_piasters'],None) for doc,_,_ in patients)
        if variance>0:lines.append((ledger.account_by_code(c,'2190'),0,variance,None))
        journal=ledger._journal(c,entry_date=today,memo='تسوية ظرف مختلط '+inc['source_register_ref']+' — '+note,
            origin='manual',source_id=None,created_by=inc['opened_by'],reviewed_by=user['id'],lines=lines)
        cur=c.execute('''INSERT INTO late_mixed_clearances(incident_id,voucher_id,journal_id,request_key,
             request_hash,gross_receipts_piasters,expense_piasters,actual_cash_piasters,
             variance_piasters,approved_exception,authorized_by,authorized_at,reason)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
             (incident_id,voucher['id'],journal,key,checksum,gross,spent,actual,variance,
              int(bool(variance)),user['id'],stamp(),note))
        clearance=cur.lastrowid
        for doc,inv,case in patients:
            c.execute('''INSERT INTO late_mixed_clearance_lines(clearance_id,document_id,
                  line_kind,invoice_id,case_id,amount_piasters) VALUES (?,?,'patient_receipt',?,?,?)''',
                  (clearance,doc['id'],inv,case,doc['amount_piasters']))
        for doc,category,dept,_ in expenses:
            c.execute('''INSERT INTO late_mixed_clearance_lines(clearance_id,document_id,
                  line_kind,category_id,department_id,amount_piasters)
                  VALUES (?,?,'expense',?,?,?)''',(clearance,doc['id'],category,dept,doc['amount_piasters']))
        event(c,incident_id,'mixed_envelope_cleared',
              'تسوية فعلية نقدية '+str(actual)+' / المرضى '+str(gross)+' / مصروفات '+str(spent)+
              ' / فرق '+str(variance)+' — '+note,user['id'])
        audit(c,user['id'],'late_mixed_cleared','late_mixed_clearance',clearance,
              {'journal_id':journal,'voucher_id':voucher['id'],'gross_piasters':gross,
               'expenses_piasters':spent,'actual_cash_piasters':actual,'variance_piasters':variance,
               'cash_newly_booked_piasters':0})
    return {'id':clearance,'journal_id':journal,'replayed':False,
            'gross_receipts_piasters':gross,'expense_piasters':spent,
            'actual_cash_piasters':actual,'variance_piasters':variance,
            'cash_newly_booked_piasters':0,
            'status':'exception_approved' if variance else 'balanced'}


@router.post('/{incident_id}/action')
def transition(incident_id:int,body:IncidentAction,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    with c:
        c.execute('BEGIN IMMEDIATE')
        inc=scope(c,user,incident_id)
        if body.action=='submit':
            require(user,'owner','clerk')
            if inc['opened_by']!=user['id'] and user['role']!='owner':fail('صاحب البلاغ فقط يقدمه',403)
            if inc['status'] not in ('draft','needs_evidence'):fail('البلاغ سبق تقديمه',409)
            count=c.execute('SELECT COUNT(*) FROM late_entry_documents WHERE incident_id=?',(incident_id,)).fetchone()[0]
            if count==0:fail('أضف مستندًا واحدًا على الأقل أو سجل الوردية بلا معاملات بالمسار المخصص',409)
            state='submitted';reviewer=None
        else:
            require(user,'owner','reviewer')
            if inc['opened_by']==user['id']:fail('لا يجوز مراجعة البلاغ الذي فتحته بنفسك',403)
            if inc['status'] not in ('submitted','triaged'):fail('البلاغ ليس جاهزًا لهذا القرار',409)
            if body.action=='resolve':
                total,unlinked=c.execute('''SELECT COUNT(*),
                    COALESCE(SUM(CASE WHEN d.linked_id IS NULL AND NOT EXISTS
                       (SELECT 1 FROM late_cash_allocations a WHERE a.document_id=d.id) AND NOT EXISTS
                       (SELECT 1 FROM late_mixed_clearance_lines ml WHERE ml.document_id=d.id)
                       THEN 1 ELSE 0 END),0)
                    FROM late_entry_documents d WHERE d.incident_id=?''',(incident_id,)).fetchone()
                if not total or unlinked:
                    fail('لا يمكن إنهاء الاستدراك قبل إثبات مستندات وربطها بحركات إلكترونية فعلية',409)
                leftover=c.execute('''SELECT 1 FROM late_cash_allocations a JOIN vouchers v
                   ON v.id=a.voucher_id WHERE a.incident_id=? GROUP BY a.voucher_id
                   HAVING SUM(a.amount_piasters)<>MAX(v.amount_piasters) LIMIT 1''',(incident_id,)).fetchone()
                if leftover:
                    fail('الظرف ما زال به نقدية غير مخصصة؛ أكمل الربط أو افتح تحقيق فرق عهدة',409)
                unfinished=c.execute('''SELECT l.case_id FROM billing_late_cases l
                  WHERE l.incident_id=? AND NOT EXISTS
                  (SELECT 1 FROM billing_invoices bi WHERE bi.case_id=l.case_id) LIMIT 1''',(incident_id,)).fetchone()
                if unfinished:
                    fail('الواقعة فيها ملف مريض مستدرك لم تصدر فاتورته؛ لا يمكن إنهاؤها',409)
                state='resolved'
            elif body.action=='triage':state='triaged'
            else:
                if (c.execute('SELECT 1 FROM late_cash_allocations WHERE incident_id=?',(incident_id,)).fetchone() or
                    c.execute('SELECT 1 FROM late_mixed_clearances WHERE incident_id=?',(incident_id,)).fetchone()):
                    fail('توجد تسوية مالية نهائية؛ التصحيح اللاحق يحتاج بلاغ تصحيح مالي مستقل',409)
                state='needs_evidence'
            reviewer=user['id']
        c.execute('''UPDATE late_entry_incidents SET status=?,reviewed_by=?,reviewed_at=?,review_note=? WHERE id=?''',
                  (state,reviewer,stamp() if reviewer else None,body.note.strip() if reviewer else '',incident_id))
        event(c,incident_id,state,body.note.strip(),user['id'])
        financial_posted=bool(c.execute('SELECT 1 FROM late_cash_allocations WHERE incident_id=?',(incident_id,)).fetchone() or
                    c.execute('SELECT 1 FROM late_mixed_clearances WHERE incident_id=?',(incident_id,)).fetchone())
        audit(c,user['id'],'late_incident_'+state,'late_entry_incident',incident_id,
              {'status':state,'financial_posted':financial_posted})
    return {'id':incident_id,'status':state,'financial_posted':financial_posted}

@router.post('/{incident_id}/evidence')
def upload_evidence(incident_id:int,file:UploadFile=File(...),user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    inc=scope(c,user,incident_id)
    late_overage_proof=(user['role'] in ('owner','reviewer') and
        c.execute('''SELECT 1 FROM late_mixed_clearances m JOIN gl_journals j ON j.id=m.journal_id
          WHERE m.incident_id=? AND m.variance_piasters>0 AND j.status='posted' ''',
          (incident_id,)).fetchone() is not None)
    if (user['role']=='reviewer' and not late_overage_proof) or (
        inc['status'] not in ('draft','needs_evidence') and not late_overage_proof):
        fail('المرفقات مقفلة بعد تقديم البلاغ؛ يسمح فقط بإضافة إثبات المطالبة بزيادة معتمدة',409)
    content=file.file.read(MAX_EVIDENCE+1)
    if not content or len(content)>MAX_EVIDENCE:fail('الصورة أو الملف يتجاوز 6 ميجابايت',413)
    mime=('image/jpeg' if content[:3]==b'\xff\xd8\xff' else 'image/png' if content[:8]==b'\x89PNG\r\n\x1a\n'
          else 'application/pdf' if content[:5]==b'%PDF-' else None)
    if not mime:fail('المسموح صورة JPG أو PNG أو ملف PDF فقط',415)
    name=(file.filename or 'evidence')[-120:]
    sha=hashlib.sha256(content).hexdigest()
    with c:
        c.execute('BEGIN IMMEDIATE')
        count=c.execute('SELECT COUNT(*) FROM late_entry_evidence WHERE incident_id=?',
                        (incident_id,)).fetchone()[0]
        if count>=MAX_FILES_PER_INCIDENT:
            fail('الحد الأقصى عشرة مرفقات لكل واقعة؛ تواصل مع المراجع',409)
        try:
            cur=c.execute('''INSERT INTO late_entry_evidence(incident_id,filename,mime,sha256,content,
                uploaded_by,uploaded_at) VALUES (?,?,?,?,?,?,?)''',
                (incident_id,name,mime,sha,content,user['id'],stamp()))
        except sqlite3.IntegrityError:fail('تم رفع هذا الملف بالفعل',409)
        event(c,incident_id,'overage_proof_added' if late_overage_proof else 'evidence_added',
              name+' sha256='+sha[:16],user['id'])
        audit(c,user['id'],'late_evidence_added','late_entry_incident',incident_id,{'sha256':sha})
    return {'id':cur.lastrowid,'sha256':sha}

@router.get('/evidence/{evidence_id}/download')
def download_evidence(evidence_id:int,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    doc=c.execute('SELECT * FROM late_entry_evidence WHERE id=?',(evidence_id,)).fetchone()
    if not doc:fail('المرفق غير موجود',404)
    scope(c,user,doc['incident_id'])
    return Response(content=doc['content'],media_type='application/octet-stream',headers={
       'Content-Disposition':f'attachment; filename="late-{evidence_id}.dat"',
       'X-Content-Type-Options':'nosniff','Cache-Control':'no-store','Content-Security-Policy':'sandbox'})


# G2E: a new, physically confirmed recovery for a PREVIOUSLY POSTED shortage.
# Unlike allocating already-booked cash, this is a genuinely NEW cash receipt
# into TODAY'S open main safe, so the independent approval posts exactly once.
def mixed_shortage_remaining(c,clearance_id):
    mixed=c.execute('SELECT id,variance_piasters,journal_id FROM late_mixed_clearances WHERE id=?',
                    (clearance_id,)).fetchone()
    if not mixed or mixed['variance_piasters']>=0:
        fail('لا يوجد عجز ظرف مختلط معتمد على هذه الواقعة',409)
    posted=c.execute("SELECT 1 FROM gl_journals WHERE id=? AND status='posted'",(mixed['journal_id'],)).fetchone()
    if not posted:fail('فرق العهدة الأصلي لم يُرحّل إلى الأستاذ',409)
    paid=c.execute('''SELECT COALESCE(SUM(amount_piasters),0) FROM late_mixed_shortage_recovery_requests
        WHERE clearance_id=? AND status='approved' ''',(clearance_id,)).fetchone()[0]
    outstanding=-mixed['variance_piasters']-paid
    if outstanding<0:fail('تجاوز في قيود التسوية؛ يحتاج تحقيق محاسبي',409)
    return outstanding


def open_main_recovery_shift(c,user):
    from app import authorize_cashbook_fund
    today=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
    shift=c.execute('''SELECT sh.*,p.id point_id FROM shift_sessions sh
      JOIN billing_points p ON p.fund_id=sh.fund_id AND p.kind='internal' AND p.active=1
      JOIN funds f ON f.id=sh.fund_id AND f.kind='cash' AND f.active=1
      WHERE sh.status='open' AND sh.business_date=? AND sh.responsible_id=?
      ORDER BY sh.id DESC LIMIT 1''',(today,user['id'])).fetchone()
    if not shift:fail('يجب أن يستلم النقدية مسؤول وردية الخزنة الرئيسية المفتوحة اليوم',409)
    check_point(c,user,shift['point_id'])
    authorize_cashbook_fund(c,user,shift['fund_id'])
    return shift,today


@router.post('/{incident_id}/shortage-recoveries')
def propose_mixed_shortage_recovery(incident_id:int,body:MixedShortageRecoveryRequest,
    user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','clerk')
    import billing
    key=billing.request_key(body.request_id)
    amount=c_piasters(body.amount)
    reference=body.receipt_ref.strip().upper()
    if not REF.fullmatch(reference):fail('رقم محضر استلام السداد غير صالح')
    note=billing.trim(body.note,'سبب الاستلام الفعلي',24,700)
    payer=body.payer_name.strip()
    if body.source_type=='employee_deposit' and len(payer)<3:
        fail('حدّد اسم صاحب الإيداع الفعلي دون افتراض مسؤولية موظف عن العجز',409)
    if body.source_type=='recovered_cash' and payer:
        fail('النقدية التي عثر عليها مجددًا لا تُنسب إلى موظف كمُودع',409)
    payload={'incident_id':incident_id,'receipt_ref':reference,'source_type':body.source_type,
       'payer_name':payer,'amount_piasters':amount,'note':note}
    checksum=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    with c:
        c.execute('BEGIN IMMEDIATE')
        old=c.execute('SELECT * FROM late_mixed_shortage_recovery_requests WHERE request_key=?',(key,)).fetchone()
        if old:
            if old['proposed_by']!=user['id'] or old['request_hash']!=checksum:
                fail('رمز الطلب مستخدم لإثبات نقدية مختلف',409)
            check_point(c,user,c.execute('''SELECT i.point_id FROM late_entry_incidents i
                 JOIN late_mixed_clearances m ON m.incident_id=i.id WHERE m.id=?''',
                 (old['clearance_id'],)).fetchone()[0])
            return {'id':old['id'],'status':old['status'],'replayed':True,'amount_piasters':amount}
        inc=c.execute('SELECT * FROM late_entry_incidents WHERE id=?',(incident_id,)).fetchone()
        if not inc:fail('بلاغ الاستدراك غير موجود',404)
        check_point(c,user,inc['point_id'])
        clear=c.execute('SELECT * FROM late_mixed_clearances WHERE incident_id=?',(incident_id,)).fetchone()
        if not clear:fail('لا يوجد ظرف مختلط معتمد لتسجيل السداد',409)
        remaining=mixed_shortage_remaining(c,clear['id'])
        if amount>remaining:fail('المبلغ يتجاوز العجز المتبقي',409)
        shift,today=open_main_recovery_shift(c,user)
        from app import month_open
        month_open(c,today[:7])
        if c.execute('''SELECT 1 FROM late_mixed_shortage_recovery_requests
            WHERE receipt_ref=?''',(reference,)).fetchone():
            fail('هذا المرجع استُخدم في طلب استلام آخر، لا تسجل نفس النقدية مرتين',409)
        if c.execute('''SELECT 1 FROM vouchers v WHERE UPPER(TRIM(v.reference_no))=?
             AND v.kind='receipt' AND v.status IN ('pending','approved') LIMIT 1''',
             (reference,)).fetchone():
            fail('هذا المحضر سبق تسجيله كسند قبض آخر',409)
        cur=c.execute('''INSERT INTO late_mixed_shortage_recovery_requests(
             clearance_id,request_key,request_hash,receipt_ref,source_type,payer_name,
             amount_piasters,evidence_note,central_shift_id,main_fund_id,proposed_by,proposed_at)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
             (clear['id'],key,checksum,reference,body.source_type,payer,amount,note,
              shift['id'],shift['fund_id'],user['id'],stamp()))
        event(c,incident_id,'shortage_recovery_proposed',
              'طلب إثبات استلام نقدية فعلية #'+str(cur.lastrowid)+' — '+str(amount)+' قرش',user['id'])
        audit(c,user['id'],'late_shortage_recovery_proposed','late_mixed_shortage_recovery',cur.lastrowid,
              {'incident_id':incident_id,'amount_piasters':amount,'cash_booked':False})
    return {'id':cur.lastrowid,'status':'pending','amount_piasters':amount,
            'cash_booked_piasters':0,'replayed':False,'remaining_piasters':remaining}


@router.post('/{incident_id}/shortage-recoveries/{recovery_id}/decision')
def decide_mixed_shortage_recovery(incident_id:int,recovery_id:int,body:MixedShortageRecoveryDecision,
   user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    import billing,ledger
    from app import authorize_bank_review,authorize_cashbook_fund,month_open,shift_for_posting
    note=billing.trim(body.reason,'قرار مراجعة استلام النقدية',20,700)
    with c:
        c.execute('BEGIN IMMEDIATE')
        item=c.execute('''SELECT r.*,m.incident_id,m.variance_piasters FROM late_mixed_shortage_recovery_requests r
          JOIN late_mixed_clearances m ON m.id=r.clearance_id WHERE r.id=? AND m.incident_id=?''',
          (recovery_id,incident_id)).fetchone()
        if not item:fail('طلب السداد غير موجود',404)
        if item['status']!='pending':fail('سبق حسم هذا الطلب؛ راجع سجل القرار بدلاً من تكراره',409)
        if item['proposed_by']==user['id']:fail('المستلم الفعلي لا يعتمد استلامه بنفسه',403)
        if user['role']!='owner':
            grant=c.execute('''SELECT can_approve FROM cashier_variance_permissions WHERE user_id=?''',
                            (user['id'],)).fetchone()
            if not grant or not grant['can_approve']:
                fail('اعتماد أو رفض سداد فرق العهدة يحتاج تفويضًا من المالك',403)
        authorize_bank_review(c,user,item['main_fund_id'])
        voucher_id=None
        if body.decision=='approve':
            confirmed=c_piasters(body.counted_amount)
            if confirmed!=item['amount_piasters']:
                fail('المبلغ المؤكد بالجرد لا يطابق الاستلام المقدم؛ ارفض الطلب وسجل استلامًا صحيحًا',409)
            if confirmed>mixed_shortage_remaining(c,item['clearance_id']):
                fail('المبلغ يتجاوز العجز المتبقي بعد تسويات أخرى',409)
            maker=c.execute('SELECT id,role,active FROM users WHERE id=?',(item['proposed_by'],)).fetchone()
            if not maker or not maker['active']:
                fail('حساب مستلم النقدية غير نشط؛ يجب رفض الطلب والتحقق من عهدته',409)
            authorize_cashbook_fund(c,dict(maker),item['main_fund_id'])
            today=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
            current=c.execute('''SELECT s.id,s.status,s.business_date,s.responsible_id,p.kind point_kind
              FROM shift_sessions s JOIN billing_points p ON p.fund_id=s.fund_id
              WHERE s.id=? AND s.fund_id=?''',(item['central_shift_id'],item['main_fund_id'])).fetchone()
            if not current or current['point_kind']!='internal' or current['status']!='open' or current['business_date']!=today or current['responsible_id']!=item['proposed_by']:
                fail('وردية الاستلام أُغلقت أو تغير يومها؛ لا يمكن تسجيل النقدية في وردية قديمة',409)
            month_open(c,today[:7])
            shift_id=shift_for_posting(c,item['main_fund_id'],today,'central')
            if shift_id!=item['central_shift_id']:fail('وردية الخزنة الحالية ليست وردية الاستلام الأصلية',409)
            if c.execute('''SELECT 1 FROM vouchers v WHERE UPPER(TRIM(v.reference_no))=?
                AND v.kind='receipt' AND v.status IN ('pending','approved') LIMIT 1''',
                (item['receipt_ref'],)).fetchone():
                fail('مرجع الاستلام سبق تسجيله كسند نقدي آخر',409)
            category=c.execute("SELECT id FROM categories WHERE code='cash_shortage_recovery' AND active=1").fetchone()
            dept=c.execute("SELECT id FROM departments WHERE code='ADMIN' AND active=1").fetchone()
            if not category or not dept:fail('فئة أو قسم سداد العجز غير مهيأ',409)
            cur=c.execute('''INSERT INTO vouchers(voucher_no,date,kind,department_id,category_id,
                from_fund_id,shift,amount_piasters,description,reference_no,status,created_by,
                reviewed_by,created_at,reviewed_at,review_reason)
                VALUES (?,?,?,?,?,?,'central',?,?,?,'approved',?,?,?,?,?)''',
                ('DRAFT-'+secrets.token_hex(8),today,'receipt',dept['id'],category['id'],
                 item['main_fund_id'],confirmed,'استرداد عجز ظرف تاريخي #'+str(item['clearance_id'])+' — '+item['evidence_note'][:350],
                 item['receipt_ref'],item['proposed_by'],user['id'],stamp(),stamp(),note))
            voucher_id=cur.lastrowid
            c.execute('UPDATE vouchers SET voucher_no=? WHERE id=?',
                      (f'LREC-{today[:4]}-{voucher_id:06d}',voucher_id))
            c.execute('''INSERT INTO fund_movements(voucher_id,fund_id,amount_piasters,booked_on,shift_session_id)
                         VALUES (?,?,?,?,?)''',
                      (voucher_id,item['main_fund_id'],confirmed,today,item['central_shift_id']))
            ledger.post_voucher(c,c.execute('SELECT * FROM vouchers WHERE id=?',(voucher_id,)).fetchone(),user['id'])
        c.execute('''UPDATE late_mixed_shortage_recovery_requests SET status=?,decided_by=?,
                decided_at=?,decision_note=?,voucher_id=? WHERE id=?''',
                ('approved' if body.decision=='approve' else 'rejected',user['id'],stamp(),note,voucher_id,recovery_id))
        after=mixed_shortage_remaining(c,item['clearance_id'])
        event(c,incident_id,'shortage_recovery_'+('approved' if voucher_id else 'rejected'),
              'قرار استلام نقدية لاحقة #'+str(recovery_id)+' — '+note,user['id'])
        audit(c,user['id'],'late_shortage_recovery_'+body.decision,'late_mixed_shortage_recovery',recovery_id,
              {'voucher_id':voucher_id,'remaining_piasters':after,'amount_piasters':item['amount_piasters'],
               'cash_booked_piasters':item['amount_piasters'] if voucher_id else 0})
    return {'id':recovery_id,'status':'approved' if voucher_id else 'rejected',
            'voucher_id':voucher_id,'remaining_piasters':after,
            'cash_booked_piasters':item['amount_piasters'] if voucher_id else 0}


# G2F: overage in 2190 is already CASH ON HAND but not hospital income.
# Refund to an identified claimant moves cash OUT only after a reviewed,
# signed handover. No part of this workflow recognizes new revenue.
def mixed_overage_remaining(c,clearance_id):
    clear=c.execute('SELECT variance_piasters,journal_id FROM late_mixed_clearances WHERE id=?',
                    (clearance_id,)).fetchone()
    if not clear or clear['variance_piasters']<=0:
        fail('لا توجد زيادة عهدة معتمدة لهذه الواقعة',409)
    if not c.execute("SELECT 1 FROM gl_journals WHERE id=? AND status='posted'",
                     (clear['journal_id'],)).fetchone():
        fail('فرق العهدة الأصلي لم يرحل إلى دفتر الأستاذ',409)
    returned=c.execute('''SELECT COALESCE(SUM(amount_piasters),0)
         FROM late_mixed_overage_refund_requests WHERE clearance_id=? AND status='approved' ''',
         (clearance_id,)).fetchone()[0]
    remaining=int(clear['variance_piasters'])-returned
    if remaining<0:fail('خلل في عهدة الزيادة يحتاج تحقيقًا محاسبيًا',409)
    return remaining


@router.post('/{incident_id}/overage-refunds')
def propose_mixed_overage_refund(incident_id:int,body:MixedOverageRefundRequest,
    user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','clerk')
    import billing
    key=billing.request_key(body.request_id)
    amount=c_piasters(body.amount)
    claim=body.claim_ref.strip().upper()
    if not REF.fullmatch(claim):fail('مرجع المطالبة غير صالح')
    claimant=billing.trim(body.claimant_name,'اسم صاحب الحق',3,150)
    explanation=billing.trim(body.note,'مستند المطالبة والسبب',32,1000)
    payload={'incident_id':incident_id,'claim_ref':claim,'claimant_name':claimant,
             'evidence_id':body.evidence_id,'amount_piasters':amount,'note':explanation}
    checksum=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    with c:
        c.execute('BEGIN IMMEDIATE')
        old=c.execute('SELECT * FROM late_mixed_overage_refund_requests WHERE request_key=?',
                      (key,)).fetchone()
        if old:
            if old['proposed_by']!=user['id'] or old['request_hash']!=checksum:
                fail('رقم الطلب مستخدم لمطالبة أخرى',409)
            incident=c.execute('''SELECT i.point_id FROM late_entry_incidents i
                JOIN late_mixed_clearances m ON m.incident_id=i.id WHERE m.id=?''',
                (old['clearance_id'],)).fetchone()
            if not incident:fail('واقعة المطالبة لم تعد موجودة',409)
            check_point(c,user,incident['point_id'])
            return {'id':old['id'],'status':old['status'],'replayed':True}
        incident=c.execute('SELECT * FROM late_entry_incidents WHERE id=?',(incident_id,)).fetchone()
        if not incident:fail('واقعة الاستدراك غير موجودة',404)
        check_point(c,user,incident['point_id'])
        mixed=c.execute('SELECT * FROM late_mixed_clearances WHERE incident_id=?',(incident_id,)).fetchone()
        if not mixed:fail('يجب اعتماد تسوية ظرف مختلط أولاً',409)
        remaining=mixed_overage_remaining(c,mixed['id'])
        reserved=c.execute('''SELECT COALESCE(SUM(amount_piasters),0)
             FROM late_mixed_overage_refund_requests
             WHERE clearance_id=? AND status='pending' ''',(mixed['id'],)).fetchone()[0]
        if amount>remaining-reserved:fail('المبلغ يتجاوز الزيادة المتاحة بعد الطلبات المعلقة',409)
        proof=c.execute('SELECT id FROM late_entry_evidence WHERE id=? AND incident_id=?',
                        (body.evidence_id,incident_id)).fetchone()
        if not proof:fail('أرفق إثبات مطالبة لصاحب الحق على نفس الواقعة',409)
        if c.execute('SELECT 1 FROM late_mixed_overage_refund_requests WHERE claim_ref=?',(claim,)).fetchone():
            fail('مرجع المطالبة سبق استخدامه في رد آخر',409)
        if c.execute('''SELECT 1 FROM vouchers WHERE UPPER(TRIM(reference_no))=?
            AND status IN ('pending','approved') LIMIT 1''',(claim,)).fetchone():
            fail('مرجع المطالبة مستخدم في سند مالي آخر',409)
        shift,today=open_main_recovery_shift(c,user)
        from app import month_open
        month_open(c,today[:7])
        cur=c.execute('''INSERT INTO late_mixed_overage_refund_requests
           (clearance_id,request_key,request_hash,claim_ref,claimant_name,evidence_id,
            amount_piasters,evidence_note,central_shift_id,main_fund_id,proposed_by,proposed_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
            (mixed['id'],key,checksum,claim,claimant,body.evidence_id,amount,explanation,
             shift['id'],shift['fund_id'],user['id'],stamp()))
        event(c,incident_id,'overage_refund_proposed',
              'طلب رد مبلغ من الزيادة #'+str(cur.lastrowid)+' دون صرف قبل الاعتماد',user['id'])
        audit(c,user['id'],'overage_refund_proposed','late_mixed_overage_refund',cur.lastrowid,
              {'incident_id':incident_id,'amount_piasters':amount,'cash_paid_piasters':0})
    return {'id':cur.lastrowid,'status':'pending','replayed':False,
            'cash_paid_piasters':0,'amount_piasters':amount,
            'remaining_unreserved_piasters':remaining-reserved-amount}


@router.post('/{incident_id}/overage-refunds/{refund_id}/decision')
def decide_mixed_overage_refund(incident_id:int,refund_id:int,body:MixedOverageRefundDecision,
    user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    import billing,ledger
    from app import authorize_bank_review,authorize_cashbook_fund,month_open,book_movements
    reason=billing.trim(body.reason,'قرار رد الزيادة',24,1000)
    with c:
        c.execute('BEGIN IMMEDIATE')
        item=c.execute('''SELECT r.*,m.incident_id FROM late_mixed_overage_refund_requests r
             JOIN late_mixed_clearances m ON m.id=r.clearance_id
             WHERE r.id=? AND m.incident_id=?''',(refund_id,incident_id)).fetchone()
        if not item:fail('طلب رد الزيادة غير موجود',404)
        if item['status']!='pending':fail('هذا الطلب صدر بشأنه قرار بالفعل',409)
        if item['proposed_by']==user['id']:fail('صاحب طلب التسليم لا يعتمد صرفه لنفسه',403)
        if user['role']!='owner':
            perm=c.execute('''SELECT can_approve FROM cashier_variance_permissions WHERE user_id=?''',
                           (user['id'],)).fetchone()
            if not perm or not perm['can_approve']:
                fail('اعتماد رد الزيادة يحتاج تفويض مالك النظام',403)
        authorize_bank_review(c,user,item['main_fund_id'])
        voucher_id=None
        signed_proof=None
        if body.decision=='approve':
            amt=c_piasters(body.counted_amount)
            if amt!=item['amount_piasters']:
                fail('المبلغ المعدود عند التسليم مختلف؛ ارفض الطلب ثم أنشئ تصحيحًا موثقًا',409)
            if not body.recipient_receipt_verified or not body.receipt_evidence_id:
                fail('يجب تأكيد الاستلام ورفع إيصال تسلّم موقع من صاحب الحق',409)
            signed_proof=c.execute('''SELECT id,sha256 FROM late_entry_evidence
                 WHERE id=? AND incident_id=?''',(body.receipt_evidence_id,incident_id)).fetchone()
            if not signed_proof or signed_proof['id']==item['evidence_id']:
                fail('إثبات تسلم صاحب الحق يجب أن يكون مرفقًا آخر مستقلًا على نفس الواقعة',409)
            if amt>mixed_overage_remaining(c,item['clearance_id']):
                fail('المبلغ يتجاوز الزيادة المتبقية بعد تسويات أخرى',409)
            maker=c.execute('SELECT id,role,active FROM users WHERE id=?',(item['proposed_by'],)).fetchone()
            if not maker or not maker['active']:fail('الموظف الذي يسلّم العهدة غير نشط',409)
            authorize_cashbook_fund(c,dict(maker),item['main_fund_id'])
            today=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
            sh=c.execute('''SELECT s.id,s.status,s.business_date,s.responsible_id,p.kind
                FROM shift_sessions s JOIN billing_points p ON p.fund_id=s.fund_id
                WHERE s.id=? AND s.fund_id=?''',
                (item['central_shift_id'],item['main_fund_id'])).fetchone()
            if (not sh or sh['kind']!='internal' or sh['status']!='open' or
                sh['business_date']!=today or sh['responsible_id']!=item['proposed_by']):
                fail('وردية الخزنة الأصلية أغلقت؛ ارفض الطلب وأنشئ طلبًا جديدًا في وردية حالية',409)
            month_open(c,today[:7])
            if c.execute('''SELECT 1 FROM vouchers WHERE UPPER(TRIM(reference_no))=?
                AND status IN ('pending','approved') LIMIT 1''',(item['claim_ref'],)).fetchone():
                fail('رقم المطالبة سبق استخدامه في سند مالي',409)
            category=c.execute("SELECT id FROM categories WHERE code='cash_overage_return' AND active=1").fetchone()
            dept=c.execute("SELECT id FROM departments WHERE code='ADMIN' AND active=1").fetchone()
            if not category or not dept:fail('فئة رد الزيادة أو قسم الحسابات غير مهيأ',409)
            cur=c.execute('''INSERT INTO vouchers(voucher_no,date,kind,department_id,category_id,
               from_fund_id,shift,amount_piasters,description,reference_no,status,created_by,
               reviewed_by,created_at,reviewed_at,review_reason)
               VALUES (?,?,?,?,?,?,'central',?,?,?,'approved',?,?,?,?,?)''',
               ('DRAFT-'+secrets.token_hex(8),today,'payment',dept['id'],category['id'],
                item['main_fund_id'],amt,
                'رد زيادة عهدة تاريخية #'+str(item['clearance_id'])+' إلى صاحب الحق '+item['claimant_name'],
                item['claim_ref'],item['proposed_by'],user['id'],stamp(),stamp(),reason))
            voucher_id=cur.lastrowid
            c.execute('UPDATE vouchers SET voucher_no=? WHERE id=?',
                      (f'LOVR-{today[:4]}-{voucher_id:06d}',voucher_id))
            voucher=c.execute('SELECT * FROM vouchers WHERE id=?',(voucher_id,)).fetchone()
            book_movements(c,voucher)  # includes actual shift custody and physical cash limits
            ledger.post_voucher(c,voucher,user['id'])
        c.execute('''UPDATE late_mixed_overage_refund_requests SET status=?,decided_by=?,
             decided_at=?,decision_note=?,receipt_evidence_id=?,voucher_id=? WHERE id=?''',
             ('approved' if voucher_id else 'rejected',user['id'],stamp(),reason,
              signed_proof['id'] if signed_proof else None,voucher_id,refund_id))
        left=mixed_overage_remaining(c,item['clearance_id'])
        event(c,incident_id,'overage_refund_'+('approved' if voucher_id else 'rejected'),
              'قرار رد زيادة عهدة #'+str(refund_id)+' — '+reason,user['id'])
        audit(c,user['id'],'overage_refund_'+body.decision,'late_mixed_overage_refund',refund_id,
              {'voucher_id':voucher_id,'remaining_piasters':left,
               'cash_paid_piasters':item['amount_piasters'] if voucher_id else 0})
    return {'id':refund_id,'status':'approved' if voucher_id else 'rejected',
            'voucher_id':voucher_id,'remaining_piasters':left,
            'cash_paid_piasters':item['amount_piasters'] if voucher_id else 0}
