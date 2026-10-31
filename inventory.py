"""G2T provisional central *non-drug* consumables inventory and supplier payables.

Physical receipts and consumption only become stock/GL after a second operator
approves the immutable document. No supplier cash payment or VAT is inferred.
The existing GL has a closed origin enum: source-linked system journals use
`origin=manual` and are protected from reversal via their document journal_id.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app import audit, c_piasters, db, fail, get_user, month_open, require, stamp, valid_date, valid_month
from billing import case_scope, cairo_today, remember, repeat, request_key, trim, CODE_PATTERN
import ledger

router=APIRouter(prefix='/api/inventory',tags=['central-consumables'])


class VendorForm(BaseModel):
    code:str=Field(min_length=3,max_length=36)
    name:str=Field(min_length=3,max_length=100)


class ItemForm(BaseModel):
    code:str=Field(min_length=3,max_length=36)
    name:str=Field(min_length=3,max_length=120)
    unit:Literal['piece','box','pack','bottle','meter']='piece'


class GrantForm(BaseModel):
    user_id:int
    can_prepare:bool=False
    can_approve:bool=False
    reason:str=Field(min_length=8,max_length=200)


class ReceiptLineForm(BaseModel):
    item_id:int
    quantity:int=Field(ge=1,le=1000000)
    unit_cost:str
    batch_ref:str=Field(default='',max_length=90)
    expiry_date:str|None=None


class ReceiptForm(BaseModel):
    vendor_id:int
    received_on:str
    invoice_ref:str=Field(min_length=6,max_length=90)
    evidence_ref:str=Field(min_length=8,max_length=180)
    request_id:str
    lines:list[ReceiptLineForm]=Field(min_length=1,max_length=50)


class IssueLineForm(BaseModel):
    item_id:int
    quantity:int=Field(ge=1,le=1000000)


class IssueForm(BaseModel):
    department_id:int
    case_id:int|None=None
    used_on:str
    evidence_ref:str=Field(min_length=8,max_length=180)
    request_id:str
    lines:list[IssueLineForm]=Field(min_length=1,max_length=50)


class ReviewForm(BaseModel):
    decision:Literal['approve','reject']
    note:str=Field(min_length=8,max_length=300)


def permission(c,user,ability='read'):
    if user['role']=='owner':return
    if user['role'] not in ('clerk','reviewer'):
        fail('المخزن المركزي غير متاح لهذا الحساب',403)
    grants=c.execute('SELECT can_prepare,can_approve FROM inventory_access WHERE user_id=?',(user['id'],)).fetchone()
    if not grants or (ability=='prepare' and not grants['can_prepare']) or (ability=='approve' and not grants['can_approve']) or (ability=='read' and not (grants['can_prepare'] or grants['can_approve'])):
        fail('لا يوجد تفويض حالي لهذه العملية في المخزن',403)


def business_day(value):
    day=valid_date(value)
    if day>date.fromisoformat(cairo_today()):
        fail('لا تسمح دورة المخزون بمستند بتاريخ مستقبلي',409)
    return day.isoformat()


def code(value):
    normalized=(value or '').strip().upper()
    if not CODE_PATTERN.fullmatch(normalized):fail('كود المورد أو الصنف غير صالح')
    return normalized


def ledger_post(c,entry_date,memo,doc_id,created_by,reviewer_id,debit_code,credit_code,amount,dept_id=None):
    """Use existing balanced ledger; document FK prevents manual reverse later."""
    if amount<=0:fail('لا يجوز اعتماد مستند مخزون بقيمة صفر',409)
    lines=[(ledger.account_by_code(c,debit_code),amount,0,dept_id),
           (ledger.account_by_code(c,credit_code),0,amount,dept_id)]
    return ledger._journal(c,entry_date=entry_date,memo=f'INV:{memo}#{doc_id}',
        origin='manual',source_id=None,created_by=created_by,reviewed_by=reviewer_id,lines=lines)


def receipt_sum(c,rid):
    return c.execute('SELECT COALESCE(SUM(quantity*unit_cost_piasters),0) FROM inventory_receipt_lines WHERE receipt_id=?',(rid,)).fetchone()[0]


@router.post('/access')
def change_access(body:GrantForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    reason=trim(body.reason,'سبب التفويض',8,200)
    with c:
        c.execute('BEGIN IMMEDIATE')
        who=c.execute('SELECT * FROM users WHERE id=?',(body.user_id,)).fetchone()
        if not who or not who['active'] or who['role'] not in ('clerk','reviewer'):
            fail('تفويض المخزن لمستخدم نشط بدور موظف أو مراجع فقط',409)
        c.execute('''INSERT INTO inventory_access(user_id,can_prepare,can_approve,changed_by,changed_at,reason)
          VALUES(?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
          can_prepare=excluded.can_prepare,can_approve=excluded.can_approve,
          changed_by=excluded.changed_by,changed_at=excluded.changed_at,reason=excluded.reason''',
          (who['id'],int(body.can_prepare),int(body.can_approve),user['id'],stamp(),reason))
        audit(c,user['id'],'inventory_grant_updated','user',who['id'],{'prepare':body.can_prepare,'approve':body.can_approve})
    return {'user_id':body.user_id,'can_prepare':body.can_prepare,'can_approve':body.can_approve}


@router.post('/vendors')
def create_vendor(body:VendorForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    vendor_code=code(body.code)
    with c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM inventory_vendors WHERE code=?',(vendor_code,)).fetchone():fail('كود المورد مستخدم',409)
        result=c.execute('INSERT INTO inventory_vendors(code,name) VALUES(?,?)',(vendor_code,trim(body.name,'اسم المورد',3,100)))
        audit(c,user['id'],'inventory_vendor_created','inventory_vendor',result.lastrowid)
    return {'id':result.lastrowid,'code':vendor_code}


@router.post('/items')
def create_item(body:ItemForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    item_code=code(body.code)
    with c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM inventory_items WHERE code=?',(item_code,)).fetchone():fail('كود المستلزم مستخدم',409)
        result=c.execute('INSERT INTO inventory_items(code,name,unit) VALUES(?,?,?)',
                         (item_code,trim(body.name,'اسم المستلزم',3,120),body.unit))
        audit(c,user['id'],'inventory_item_created','inventory_item',result.lastrowid)
    return {'id':result.lastrowid,'code':item_code}


def stock_asof(c,period=None):
    upto=(period+'-31') if period else '9999-12-31'
    # Inventory lots count only approved supplier receipts; unapproved requests are not stock.
    return [dict(r) for r in c.execute('''SELECT it.id,it.code,it.name,it.unit,
      COALESCE(SUM(CASE WHEN r.status='approved' AND r.received_on<=? THEN l.quantity ELSE 0 END),0)-
      COALESCE((SELECT SUM(a.quantity) FROM inventory_issue_allocations a
         JOIN inventory_issues i ON i.id=a.issue_id AND i.status='approved'
         JOIN inventory_receipt_lines k ON k.id=a.receipt_line_id
         WHERE k.item_id=it.id AND i.used_on<=?),0) AS quantity_on_hand,
      COALESCE(SUM(CASE WHEN r.status='approved' AND r.received_on<=? THEN l.quantity*l.unit_cost_piasters ELSE 0 END),0)-
      COALESCE((SELECT SUM(a.cost_piasters) FROM inventory_issue_allocations a
         JOIN inventory_issues i ON i.id=a.issue_id AND i.status='approved'
         JOIN inventory_receipt_lines k ON k.id=a.receipt_line_id
         WHERE k.item_id=it.id AND i.used_on<=?),0) AS value_piasters
      FROM inventory_items it
      LEFT JOIN inventory_receipt_lines l ON l.item_id=it.id
      LEFT JOIN inventory_receipts r ON r.id=l.receipt_id
      GROUP BY it.id ORDER BY it.id''',(upto,upto,upto,upto))]


@router.get('/overview')
def overview(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user)
    return {'vendors':[dict(v) for v in c.execute('SELECT * FROM inventory_vendors WHERE active=1 ORDER BY id')],
            'items':stock_asof(c),
            'receipts':[dict(r) for r in c.execute('''SELECT r.*,v.name vendor_name,
               (SELECT COALESCE(SUM(quantity*unit_cost_piasters),0) FROM inventory_receipt_lines l WHERE l.receipt_id=r.id) total_piasters
               FROM inventory_receipts r JOIN inventory_vendors v ON v.id=r.vendor_id ORDER BY r.id DESC LIMIT 60''')],
            'issues':[dict(i) for i in c.execute('SELECT * FROM inventory_issues ORDER BY id DESC LIMIT 60')],
            'grants':dict(c.execute('SELECT can_prepare,can_approve FROM inventory_access WHERE user_id=?',(user['id'],)).fetchone() or {'can_prepare':0,'can_approve':0}),
            'role':user['role'],
            'notice':'مخزن مستلزمات تجريبي واحد؛ لا يعادل صرف دواء، ولا يسدد فاتورة المورد نقدًا.'}


@router.post('/receipts')
def prepare_receipt(body:ReceiptForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user,'prepare')
    key=request_key(body.request_id)
    day=business_day(body.received_on)
    ref=trim(body.invoice_ref,'مرجع فاتورة المورد',6,90).upper()
    proof=trim(body.evidence_ref,'محضر الاستلام',8,180)
    lines=[]
    for row in body.lines:
        batch=trim(row.batch_ref,'مرجع الدفعة',0,90)
        expiry=valid_date(row.expiry_date).isoformat() if row.expiry_date else None
        if expiry and expiry<day:fail('لا يمكن استلام دفعة منتهية قبل تاريخ الاستلام',409)
        lines.append({'item_id':row.item_id,'quantity':row.quantity,'unit_cost_piasters':c_piasters(row.unit_cost),
                      'batch_ref':batch,'expiry_date':expiry})
    payload={'vendor_id':body.vendor_id,'received_on':day,'invoice_ref':ref,'evidence_ref':proof,'lines':lines}
    with c:
        c.execute('BEGIN IMMEDIATE')
        permission(c,user,'prepare')  # Recheck revoked grants inside the write transaction.
        prior,digest=repeat(c,key,'inventory_receipt',user['id'],payload)
        if prior:return {'id':prior,'replayed':True}
        month_open(c,day[:7])
        if not c.execute('SELECT 1 FROM inventory_vendors WHERE id=? AND active=1',(body.vendor_id,)).fetchone():fail('المورد غير نشط',409)
        if c.execute('SELECT 1 FROM inventory_receipts WHERE vendor_id=? AND invoice_ref=? AND status IN ("pending","approved")',(body.vendor_id,ref)).fetchone():
            fail('فاتورة المورد مسجلة سابقًا ولا يجوز تكرارها',409)
        for line in lines:
            if not c.execute('SELECT 1 FROM inventory_items WHERE id=? AND active=1',(line['item_id'],)).fetchone():fail('مستلزم غير نشط أو غير موجود',409)
        cur=c.execute('''INSERT INTO inventory_receipts(vendor_id,received_on,invoice_ref,evidence_ref,created_by,created_at)
               VALUES(?,?,?,?,?,?)''',(body.vendor_id,day,ref,proof,user['id'],stamp()))
        for line in lines:
            c.execute('''INSERT INTO inventory_receipt_lines(receipt_id,item_id,quantity,unit_cost_piasters,batch_ref,expiry_date)
               VALUES(?,?,?,?,?,?)''',(cur.lastrowid,*[line[k] for k in ('item_id','quantity','unit_cost_piasters','batch_ref','expiry_date')]))
        remember(c,key,'inventory_receipt',user['id'],digest,cur.lastrowid)
        audit(c,user['id'],'inventory_receipt_requested','inventory_receipt',cur.lastrowid,
              {'received_on':day,'total_piasters':sum(x['quantity']*x['unit_cost_piasters'] for x in lines)})
    return {'id':cur.lastrowid,'status':'pending'}


@router.post('/receipts/{receipt_id}/decision')
def decide_receipt(receipt_id:int,body:ReviewForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user,'approve')
    note=trim(body.note,'محضر المراجعة',8,300)
    with c:
        c.execute('BEGIN IMMEDIATE')
        permission(c,user,'approve')  # Revocation must win before GL posting.
        r=c.execute('SELECT * FROM inventory_receipts WHERE id=?',(receipt_id,)).fetchone()
        if not r:fail('محضر التوريد غير موجود',404)
        if r['status']!='pending':fail('تم البت في محضر التوريد بالفعل',409)
        if r['created_by']==user['id']:fail('لا يجوز اعتماد مستند توريد أعددته بنفسك',403)
        month_open(c,r['received_on'][:7])
        if body.decision=='approve':
            amount=receipt_sum(c,receipt_id)
            jid=ledger_post(c,r['received_on'],'PURCHASE',receipt_id,r['created_by'],user['id'],'1100','2200',amount)
            newstatus='approved'
        else:
            jid=None
            newstatus='rejected'
        c.execute('''UPDATE inventory_receipts SET status=?,reviewed_by=?,reviewed_at=?,review_note=?,journal_id=? WHERE id=?''',
                  (newstatus,user['id'],stamp(),note,jid,receipt_id))
        audit(c,user['id'],'inventory_receipt_'+newstatus,'inventory_receipt',receipt_id,
              {'journal_id':jid,'invoice_ref':r['invoice_ref']})
    return {'id':receipt_id,'status':newstatus,'journal_id':jid}


@router.post('/issues')
def prepare_issue(body:IssueForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user,'prepare')
    key=request_key(body.request_id)
    day=business_day(body.used_on)
    proof=trim(body.evidence_ref,'إذن الصرف',8,180)
    seen=set()
    lines=[]
    for line in body.lines:
        if line.item_id in seen:fail('لا تكرر نفس الصنف في إذن الصرف',409)
        seen.add(line.item_id)
        lines.append({'item_id':line.item_id,'quantity':line.quantity})
    payload={'department_id':body.department_id,'case_id':body.case_id,'used_on':day,'evidence_ref':proof,'lines':lines}
    with c:
        c.execute('BEGIN IMMEDIATE')
        permission(c,user,'prepare')  # Recheck revoked grants inside the write transaction.
        prior,digest=repeat(c,key,'inventory_issue',user['id'],payload)
        if prior:return {'id':prior,'replayed':True}
        month_open(c,day[:7])
        dept=c.execute('SELECT 1 FROM departments WHERE id=? AND active=1',(body.department_id,)).fetchone()
        if not dept:fail('مركز التكلفة غير موجود أو غير نشط',409)
        if body.case_id is not None:
            case=case_scope(c,user,body.case_id)
            if case['status']!='open' or case['business_date']>day:
                fail('لا يجوز صرف مستلزمات على ملف مغلق أو قبل فتح الحالة',409)
        for line in lines:
            if not c.execute('SELECT 1 FROM inventory_items WHERE id=? AND active=1',(line['item_id'],)).fetchone():fail('المستلزم غير موجود أو غير نشط',409)
        cur=c.execute('''INSERT INTO inventory_issues(department_id,case_id,used_on,evidence_ref,created_by,created_at)
               VALUES(?,?,?,?,?,?)''',(body.department_id,body.case_id,day,proof,user['id'],stamp()))
        for line in lines:
            c.execute('INSERT INTO inventory_issue_lines(issue_id,item_id,quantity) VALUES(?,?,?)',(cur.lastrowid,line['item_id'],line['quantity']))
        remember(c,key,'inventory_issue',user['id'],digest,cur.lastrowid)
        audit(c,user['id'],'inventory_issue_requested','inventory_issue',cur.lastrowid,{'department_id':body.department_id,'case_id':body.case_id})
    return {'id':cur.lastrowid,'status':'pending'}


def fifo_allocate(c,issue):
    """Serialize approvals with BEGIN IMMEDIATE, use only in-date approved lots."""
    total=0
    for line in c.execute('SELECT * FROM inventory_issue_lines WHERE issue_id=? ORDER BY id',(issue['id'],)).fetchall():
        remaining=line['quantity']
        lots=c.execute('''SELECT l.id,l.quantity,l.unit_cost_piasters,
           COALESCE((SELECT SUM(a.quantity) FROM inventory_issue_allocations a WHERE a.receipt_line_id=l.id),0) used
           FROM inventory_receipt_lines l JOIN inventory_receipts r ON r.id=l.receipt_id
           WHERE l.item_id=? AND r.status='approved' AND r.received_on<=?
             AND (l.expiry_date IS NULL OR l.expiry_date>=?)
           ORDER BY r.received_on,l.id''',(line['item_id'],issue['used_on'],issue['used_on'])).fetchall()
        for lot in lots:
            available=lot['quantity']-lot['used']
            take=min(remaining,available)
            if take<=0:continue
            cost=take*lot['unit_cost_piasters']
            c.execute('''INSERT INTO inventory_issue_allocations(issue_id,issue_line_id,receipt_line_id,quantity,cost_piasters)
               VALUES(?,?,?,?,?)''',(issue['id'],line['id'],lot['id'],take,cost))
            total+=cost
            remaining-=take
            if not remaining:break
        if remaining:
            fail('الرصيد المتاح غير كافٍ للصنف #'+str(line['item_id'])+' أو الدفعات منتهية',409)
    return total


@router.post('/issues/{issue_id}/decision')
def decide_issue(issue_id:int,body:ReviewForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user,'approve')
    note=trim(body.note,'محضر مراجعة الصرف',8,300)
    with c:
        c.execute('BEGIN IMMEDIATE')
        permission(c,user,'approve')  # Revocation must win before GL posting.
        i=c.execute('SELECT * FROM inventory_issues WHERE id=?',(issue_id,)).fetchone()
        if not i:fail('إذن الصرف غير موجود',404)
        if i['status']!='pending':fail('تم البت في إذن الصرف بالفعل',409)
        if i['created_by']==user['id']:fail('لا يجوز اعتماد إذن صرف أعددته بنفسك',403)
        month_open(c,i['used_on'][:7])
        if i['case_id'] is not None:
            case=c.execute('SELECT status FROM billing_cases WHERE id=?',(i['case_id'],)).fetchone()
            if not case or case['status']!='open':fail('ملف الحالة أُغلق أثناء انتظار اعتماد الصرف',409)
        if body.decision=='approve':
            cost=fifo_allocate(c,i)
            jid=ledger_post(c,i['used_on'],'CONSUMPTION',issue_id,i['created_by'],user['id'],'5100','1100',cost,i['department_id'])
            status='approved'
        else:
            cost=0
            jid=None
            status='rejected'
        c.execute('''UPDATE inventory_issues SET status=?,reviewed_by=?,reviewed_at=?,review_note=?,cost_piasters=?,journal_id=? WHERE id=?''',
                  (status,user['id'],stamp(),note,cost,jid,issue_id))
        audit(c,user['id'],'inventory_issue_'+status,'inventory_issue',issue_id,{'cost_piasters':cost,'journal_id':jid,'case_id':i['case_id']})
    return {'id':issue_id,'status':status,'cost_piasters':cost,'journal_id':jid}


def reconciliation(c,period):
    """Source documents vs attached posted GL, no claim on historical uncounted stock."""
    period=valid_month(period)
    errors=[]
    receipts=c.execute("""SELECT r.id,r.journal_id,COALESCE(SUM(l.quantity*l.unit_cost_piasters),0) total
      FROM inventory_receipts r LEFT JOIN inventory_receipt_lines l ON l.receipt_id=r.id
      WHERE r.status='approved' AND substr(r.received_on,1,7)<=? GROUP BY r.id""",(period,)).fetchall()
    issues=c.execute('''SELECT id,journal_id,cost_piasters total FROM inventory_issues
       WHERE status='approved' AND substr(used_on,1,7)<=?''',(period,)).fetchall()
    expected_balance=sum(int(r['total']) for r in receipts)-sum(int(i['total']) for i in issues)
    actual_balance=0
    for group,debit,credit in ((receipts,'1100','2200'),(issues,'5100','1100')):
        for item in group:
            if not item['journal_id']:
                errors.append('Missing GL for inventory document #'+str(item['id']))
                continue
            gl=c.execute('''SELECT a.code,COALESCE(SUM(l.debit_piasters-l.credit_piasters),0) signed,
                MAX(j.status) status FROM gl_journals j JOIN gl_lines l ON l.journal_id=j.id
                JOIN gl_accounts a ON a.id=l.account_id WHERE j.id=? GROUP BY a.code''',(item['journal_id'],)).fetchall()
            signed={r['code']:r['signed'] for r in gl}
            if len(gl)!=2 or signed.get(debit)!=item['total'] or signed.get(credit)!=-item['total'] or any(r['status']!='posted' for r in gl):
                errors.append('Mismatched GL for inventory document #'+str(item['id']))
            actual_balance+=int(signed.get('1100',0))
    items=stock_asof(c,period)
    physical_value=sum(int(x['value_piasters']) for x in items)
    physical_qty=sum(int(x['quantity_on_hand']) for x in items)
    if actual_balance!=expected_balance or physical_value!=expected_balance or any(x['quantity_on_hand']<0 for x in items):
        errors.append('FIFO subledger / source-backed inventory GL mismatch')
    return {'period':period,'matched':not errors,'errors':errors[:20],
            'quantity_on_hand':physical_qty,'value_piasters':physical_value,
            'inventory_gl_piasters':actual_balance,'approved_receipts':len(receipts),'approved_issues':len(issues),
            'scope':'مستلزمات تجريبية مرتبطة بمستندات G2T فقط؛ لا تشمل رصيد مخزون افتتاحي قديم أو مشتريات سندات V8 أو دواء أو تسويات الموردين.'}


@router.get('/reconciliation')
def inventory_reconciliation(period:str,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user)
    return reconciliation(c,period)


def month_close_inventory_issue(c,period):
    """Only inventory evidence in this month blocks closing; prior periods remain independent."""
    if c.execute("SELECT 1 FROM inventory_receipts WHERE substr(received_on,1,7)=? AND status='pending' LIMIT 1",(period,)).fetchone():
        return 'محاضر توريد مستلزمات تنتظر اعتماد مراجع مستقل'
    if c.execute("SELECT 1 FROM inventory_issues WHERE substr(used_on,1,7)=? AND status='pending' LIMIT 1",(period,)).fetchone():
        return 'أذون صرف مستلزمات تنتظر اعتماد مراجع مستقل'
    # Before period closure, compare all approved inventory documents up to the month.
    report=reconciliation(c,period)
    return 'مخزون المستلزمات لا يطابق قيوده ومستنداته؛ راجع تقرير المطابقة' if not report['matched'] else None
