"""G2T provisional central *non-drug* consumables inventory and supplier payables.

Physical receipts and consumption only become stock/GL after a second operator
approves the immutable document. No supplier cash payment or VAT is inferred.
The existing GL has a closed origin enum: source-linked system journals use
`origin=manual` and are protected from reversal via their document journal_id.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app import audit, c_piasters, db, fail, get_user, month_open, require, stamp, valid_date, valid_month
from billing import case_scope, cairo_today, remember, repeat, request_key, trim, CODE_PATTERN, require_clinical_grant
import ledger
from supplier_subledger import supplier_control_ledger, supplier_opening_snapshot
import financial_integrity

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
    purchase_order_id:int|None=None
    invoice_ref:str=Field(min_length=6,max_length=90)
    evidence_ref:str=Field(min_length=8,max_length=180)
    request_id:str
    lines:list[ReceiptLineForm]=Field(min_length=1,max_length=50)


class PurchaseOrderLineForm(BaseModel):
    item_id:int=Field(gt=0)
    quantity:int=Field(ge=1,le=1000000)
    unit_cost:str


class PurchaseOrderForm(BaseModel):
    vendor_id:int=Field(gt=0)
    ordered_on:str
    order_ref:str=Field(min_length=6,max_length=90)
    evidence_ref:str=Field(min_length=8,max_length=180)
    request_id:str
    lines:list[PurchaseOrderLineForm]=Field(min_length=1,max_length=50)


class SupplierInvoiceMatchForm(BaseModel):
    receipt_id:int=Field(gt=0)
    lines:list[PurchaseOrderLineForm]=Field(min_length=1,max_length=50)
    invoice_date:str
    invoice_ref:str=Field(min_length=6,max_length=90)
    amount:str
    evidence_ref:str=Field(min_length=8,max_length=180)
    request_id:str


class SupplierDueLineForm(BaseModel):
    due_on:str
    amount:str


class SupplierPaymentRequestForm(BaseModel):
    due_line_id:int=Field(gt=0)
    requested_on:str
    amount:str
    evidence_ref:str=Field(min_length=8,max_length=180)
    request_id:str


class SupplierAttributionForm(BaseModel):
    journal_id:int=Field(gt=0)
    vendor_id:int=Field(gt=0)
    evidence_ref:str=Field(min_length=8,max_length=180)
    reason:str=Field(min_length=12,max_length=300)
    request_id:str


class SupplierOpeningStatementForm(BaseModel):
    vendor_id:int=Field(gt=0)
    as_of:str
    statement_balance:str
    evidence_ref:str=Field(min_length=8,max_length=180)
    reason:str=Field(min_length=12,max_length=300)
    request_id:str


class SupplierBankVoucherForm(BaseModel):
    booked_on:str
    bank_fund_id:int=Field(gt=0)
    bank_reference:str=Field(min_length=8,max_length=100)
    request_id:str


class SupplierDueForm(BaseModel):
    invoice_match_id:int=Field(gt=0)
    scheduled_on:str
    terms_ref:str=Field(min_length=8,max_length=180)
    request_id:str
    lines:list[SupplierDueLineForm]=Field(min_length=1,max_length=12)


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


class ReturnLineForm(BaseModel):
    issue_allocation_id:int=Field(gt=0)
    quantity:int=Field(ge=1,le=1000000)


class ReturnForm(BaseModel):
    issue_id:int=Field(gt=0)
    returned_on:str
    evidence_ref:str=Field(min_length=8,max_length=180)
    request_id:str
    lines:list[ReturnLineForm]=Field(min_length=1,max_length=50)


class ReviewForm(BaseModel):
    decision:Literal['approve','reject']
    note:str=Field(min_length=8,max_length=300)


class ReturnInspectionForm(BaseModel):
    decision:Literal['release','reject']
    inspected_on:str
    evidence_ref:str=Field(min_length=8,max_length=180)
    note:str=Field(min_length=12,max_length=300)
    unused_confirmed:bool=False
    packaging_intact:bool=False
    infection_control_clearance:bool=False



class WriteoffForm(BaseModel):
    return_line_id:int=Field(gt=0)
    quantity:int=Field(ge=1,le=1000000)
    disposed_on:str
    reason:Literal['damaged','contaminated','expired','other']
    evidence_ref:str=Field(min_length=8,max_length=180)
    physical_disposal_confirmed:bool=False
    request_id:str

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
    items=[dict(r) for r in c.execute('''SELECT it.id,it.code,it.name,it.unit,
      COALESCE(SUM(CASE WHEN r.status='approved' AND r.received_on<=? THEN l.quantity ELSE 0 END),0)-
      COALESCE((SELECT SUM(a.quantity) FROM inventory_issue_allocations a
         JOIN inventory_issues i ON i.id=a.issue_id AND i.status='approved'
         JOIN inventory_receipt_lines k ON k.id=a.receipt_line_id
         WHERE k.item_id=it.id AND i.used_on<=?),0)+
      COALESCE((SELECT SUM(rl.quantity) FROM inventory_return_lines rl
         JOIN inventory_issue_returns ret ON ret.id=rl.return_id AND ret.status='approved'
         JOIN inventory_issue_allocations a ON a.id=rl.issue_allocation_id
         JOIN inventory_receipt_lines k ON k.id=a.receipt_line_id
         WHERE k.item_id=it.id AND ret.returned_on<=?),0)-
      COALESCE((SELECT SUM(w.quantity) FROM inventory_return_writeoffs w
         JOIN inventory_return_lines rl ON rl.id=w.return_line_id
         JOIN inventory_issue_allocations a ON a.id=rl.issue_allocation_id
         JOIN inventory_receipt_lines k ON k.id=a.receipt_line_id
         WHERE k.item_id=it.id AND w.status='approved' AND w.disposed_on<=?),0) AS quantity_on_hand,
      COALESCE(SUM(CASE WHEN r.status='approved' AND r.received_on<=? THEN l.quantity*l.unit_cost_piasters ELSE 0 END),0)-
      COALESCE((SELECT SUM(a.cost_piasters) FROM inventory_issue_allocations a
         JOIN inventory_issues i ON i.id=a.issue_id AND i.status='approved'
         JOIN inventory_receipt_lines k ON k.id=a.receipt_line_id
         WHERE k.item_id=it.id AND i.used_on<=?),0)+
      COALESCE((SELECT SUM(rl.quantity*k.unit_cost_piasters) FROM inventory_return_lines rl
         JOIN inventory_issue_returns ret ON ret.id=rl.return_id AND ret.status='approved'
         JOIN inventory_issue_allocations a ON a.id=rl.issue_allocation_id
         JOIN inventory_receipt_lines k ON k.id=a.receipt_line_id
         WHERE k.item_id=it.id AND ret.returned_on<=?),0)-
      COALESCE((SELECT SUM(w.quantity*k.unit_cost_piasters) FROM inventory_return_writeoffs w
         JOIN inventory_return_lines rl ON rl.id=w.return_line_id
         JOIN inventory_issue_allocations a ON a.id=rl.issue_allocation_id
         JOIN inventory_receipt_lines k ON k.id=a.receipt_line_id
         WHERE k.item_id=it.id AND w.status='approved' AND w.disposed_on<=?),0) AS value_piasters
      FROM inventory_items it
      LEFT JOIN inventory_receipt_lines l ON l.item_id=it.id
      LEFT JOIN inventory_receipts r ON r.id=l.receipt_id
      GROUP BY it.id ORDER BY it.id''',(upto,upto,upto,upto,upto,upto,upto,upto))]
    for item in items:
        # A return is a hospital asset once financially approved, but cannot be
        # consumed a second time without an independent *dated* clinical release.
        # Conservative clamp covers historical G3D releases which may already
        # have been consumed before clinical tracking existed (manual review due).
        blocked=c.execute('''SELECT COALESCE(SUM(rl.quantity),0)
            FROM inventory_return_lines rl
            JOIN inventory_issue_returns ret ON ret.id=rl.return_id AND ret.status='approved'
            JOIN inventory_issue_allocations a ON a.id=rl.issue_allocation_id
            JOIN inventory_receipt_lines lot ON lot.id=a.receipt_line_id
            LEFT JOIN inventory_return_inspections med ON med.return_line_id=rl.id
            WHERE lot.item_id=? AND ret.returned_on<=?
              AND (med.decision IS NULL OR med.decision!='released' OR med.inspected_on>?)''',
              (item['id'],upto,upto)).fetchone()[0]
        disposed=c.execute('''SELECT COALESCE(SUM(w.quantity),0) FROM inventory_return_writeoffs w
             JOIN inventory_return_lines rl ON rl.id=w.return_line_id
             JOIN inventory_issue_allocations alloc ON alloc.id=rl.issue_allocation_id
             JOIN inventory_receipt_lines lot ON lot.id=alloc.receipt_line_id
             WHERE lot.item_id=? AND w.status='approved' AND w.disposed_on<=?''',
             (item['id'],upto)).fetchone()[0]
        item['quarantined_quantity']=min(max(0,item['quantity_on_hand']),int(blocked)-int(disposed))
        item['available_quantity']=max(0,item['quantity_on_hand']-item['quarantined_quantity'])
    return items


def visible_issue_scope(user):
    # Patient case access is separate from warehouse access and can be revoked live.
    if user['role']=='owner':
        return '1=1',()
    return ('''(i.case_id IS NULL OR EXISTS (
        SELECT 1 FROM billing_cases b
        JOIN billing_point_access a ON a.point_id=b.default_point_id
        JOIN users u ON u.id=a.user_id
        WHERE b.id=i.case_id AND a.user_id=? AND a.active=1 AND u.active=1))''',
        (user['id'],))



def writeoff_candidates(c):
    """A stock-team-only worklist, with no patient or clinical notes."""
    return [dict(r) for r in c.execute('''SELECT rl.id return_line_id,ret.returned_on,
         med.inspected_on,lot.batch_ref,it.code item_code,it.name item_name,
         lot.unit_cost_piasters,rl.quantity,
         rl.quantity-COALESCE((SELECT SUM(w.quantity) FROM inventory_return_writeoffs w
            WHERE w.return_line_id=rl.id AND w.status IN ('pending','approved')),0) remaining_quantity
       FROM inventory_return_lines rl
       JOIN inventory_issue_returns ret ON ret.id=rl.return_id AND ret.status='approved'
       JOIN inventory_return_inspections med ON med.return_line_id=rl.id AND med.decision='rejected'
       JOIN inventory_issue_allocations alloc ON alloc.id=rl.issue_allocation_id
       JOIN inventory_receipt_lines lot ON lot.id=alloc.receipt_line_id
       JOIN inventory_items it ON it.id=lot.item_id
       ORDER BY med.inspected_on DESC,rl.id DESC LIMIT 100''').fetchall()
            if r['remaining_quantity']>0]


def writeoff_documents(c):
    return [dict(r) for r in c.execute('''SELECT w.id,w.return_line_id,w.quantity,w.disposed_on,
         w.reason,w.evidence_ref,w.status,w.created_by,w.cost_piasters,w.journal_id,
         it.code item_code,it.name item_name,lot.batch_ref
       FROM inventory_return_writeoffs w
       JOIN inventory_return_lines rl ON rl.id=w.return_line_id
       JOIN inventory_issue_allocations a ON a.id=rl.issue_allocation_id
       JOIN inventory_receipt_lines lot ON lot.id=a.receipt_line_id
       JOIN inventory_items it ON it.id=lot.item_id
       ORDER BY w.id DESC LIMIT 100''')]

@router.get('/overview')
def overview(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user)
    scope,params=visible_issue_scope(user)
    due_docs=supplier_due_documents(c)
    payment_requests=supplier_payment_request_documents(c)
    return {'vendors':[dict(v) for v in c.execute('SELECT * FROM inventory_vendors WHERE active=1 ORDER BY id')],
            'items':stock_asof(c),
            'receipts':[dict(r) for r in c.execute('''SELECT r.*,v.name vendor_name,
               (SELECT COALESCE(SUM(quantity*unit_cost_piasters),0) FROM inventory_receipt_lines l WHERE l.receipt_id=r.id) total_piasters
               FROM inventory_receipts r JOIN inventory_vendors v ON v.id=r.vendor_id ORDER BY r.id DESC LIMIT 60''')],
            'issues':[dict(i) for i in c.execute(f'''SELECT i.* FROM inventory_issues i
                WHERE {scope} ORDER BY i.id DESC LIMIT 60''',params)],
            'returns':[dict(r) for r in c.execute(f'''SELECT ret.id,ret.issue_id,ret.returned_on,ret.evidence_ref,ret.status,ret.created_by,ret.cost_piasters
                FROM inventory_issue_returns ret JOIN inventory_issues i ON i.id=ret.issue_id
                WHERE {scope} ORDER BY ret.id DESC LIMIT 60''',params)],
            'supplier_summary':supplier_payables(user=user,c=c),
            'purchase_orders':purchase_order_docs(c),
            'supplier_invoice_matches':supplier_invoice_docs(c),
            'supplier_due_schedules':due_docs['schedules'],
            'supplier_due_lines':due_docs['lines'],
            'supplier_due_eligible_invoices':due_docs['eligible_invoices'],
            'supplier_aging':supplier_due_aging(c,cairo_today()),
            'supplier_payment_requests':payment_requests['requests'],
            'supplier_settlements':supplier_settlement_documents(c),
            'supplier_control_ledger':supplier_control_ledger(c,cairo_today()),
            'supplier_attribution_documents':supplier_attribution_documents(c,user),
            'supplier_opening_statements':supplier_opening_docs(c,user),
            'supplier_payment_eligible_lines':payment_requests['eligible_lines'],
            'purchase_receipts':[dict(r) for r in c.execute('''SELECT r.id,r.vendor_id,r.invoice_ref,r.received_on,
              r.created_by,l.purchase_order_id,v.name vendor_name,
              (SELECT COALESCE(SUM(rl.quantity*rl.unit_cost_piasters),0) FROM inventory_receipt_lines rl
               WHERE rl.receipt_id=r.id) total_piasters
              FROM inventory_receipts r JOIN inventory_receipt_purchase_links l ON l.receipt_id=r.id
              JOIN inventory_vendors v ON v.id=r.vendor_id WHERE r.status='approved'
              AND NOT EXISTS (SELECT 1 FROM inventory_supplier_invoice_matches m
                 WHERE m.receipt_id=r.id AND m.status IN ('pending','approved'))
              ORDER BY r.id DESC LIMIT 100''')],
            'purchase_receipt_lines':[dict(x) for x in c.execute('''SELECT rl.receipt_id,rl.item_id,
                 it.code item_code,it.name item_name,rl.quantity,rl.unit_cost_piasters
               FROM inventory_receipt_lines rl
               JOIN inventory_receipt_purchase_links link ON link.receipt_id=rl.receipt_id
               JOIN inventory_items it ON it.id=rl.item_id
               JOIN inventory_receipts r ON r.id=rl.receipt_id AND r.status='approved'
               WHERE NOT EXISTS(SELECT 1 FROM inventory_supplier_invoice_matches m
                    WHERE m.receipt_id=r.id AND m.status IN ('pending','approved'))
               ORDER BY rl.receipt_id DESC,rl.id''')],
            'writeoffs':writeoff_documents(c),
            'writeoff_candidates':writeoff_candidates(c),
            'grants':dict(c.execute('SELECT can_prepare,can_approve FROM inventory_access WHERE user_id=?',(user['id'],)).fetchone() or {'can_prepare':0,'can_approve':0}),
            'role':user['role'],
            'notice':'مخزن مستلزمات تجريبي واحد؛ لا يعادل صرف دواء، ولا يسدد فاتورة المورد نقدًا.'}


def purchase_order_docs(c):
    return [dict(r) for r in c.execute('''SELECT p.id,p.vendor_id,p.ordered_on,p.order_ref,p.evidence_ref,
        p.status,p.created_by,p.reviewed_by,v.name vendor_name,
        COALESCE(SUM(l.quantity*l.unit_cost_piasters),0) total_piasters
        FROM inventory_purchase_orders p JOIN inventory_vendors v ON v.id=p.vendor_id
        LEFT JOIN inventory_purchase_order_lines l ON l.order_id=p.id
        GROUP BY p.id ORDER BY p.id DESC LIMIT 100''')]


def supplier_invoice_docs(c):
    return [dict(r) for r in c.execute('''SELECT m.id,m.receipt_id,m.invoice_ref,m.invoice_date,m.evidence_ref,
         m.amount_piasters,m.status,m.created_by,m.reviewed_by,r.vendor_id,v.name vendor_name
         FROM inventory_supplier_invoice_matches m JOIN inventory_receipts r ON r.id=m.receipt_id
         JOIN inventory_vendors v ON v.id=r.vendor_id ORDER BY m.id DESC LIMIT 100''')]


def validate_po_receipt(c,receipt_id,po_id):
    po=c.execute('SELECT * FROM inventory_purchase_orders WHERE id=?',(po_id,)).fetchone()
    r=c.execute('SELECT * FROM inventory_receipts WHERE id=?',(receipt_id,)).fetchone()
    if not po or po['status']!='approved' or po['vendor_id']!=r['vendor_id'] or r['received_on']<po['ordered_on']:
        fail('الاستلام يتطلب أمر شراء معتمدًا من المورد نفسه وقبل تاريخ الاستلام',409)
    lines=c.execute('SELECT * FROM inventory_receipt_lines WHERE receipt_id=?',(receipt_id,)).fetchall()
    if not lines or len({x['item_id'] for x in lines})!=len(lines):
        fail('يجب تحديد أصناف استلام فريدة وغير فارغة',409)
    for line in lines:
        planned=c.execute('SELECT * FROM inventory_purchase_order_lines WHERE order_id=? AND item_id=?',
                          (po_id,line['item_id'])).fetchone()
        if not planned or planned['unit_cost_piasters']!=line['unit_cost_piasters']:
            fail('الصنف أو سعر الوحدة لا يطابق أمر الشراء المعتمد',409)
        already=c.execute('''SELECT COALESCE(SUM(rl.quantity),0) FROM inventory_receipt_purchase_links link
          JOIN inventory_receipts rec ON rec.id=link.receipt_id AND rec.status IN ('pending','approved')
          JOIN inventory_receipt_lines rl ON rl.receipt_id=rec.id AND rl.item_id=?
          WHERE link.purchase_order_id=?''',(line['item_id'],po_id)).fetchone()[0]
        if already+line['quantity']>planned['quantity']:
            fail('الكمية المستلمة والمعلقة تتجاوز أمر الشراء',409)


@router.get('/purchase-orders')
def purchase_orders(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user)
    return {'orders':purchase_order_docs(c),
            'notice':'أوامر شراء تجريبية لمستلزمات غير دوائية؛ لا تنشئ دينًا أو دفعة مالية.'}


@router.post('/purchase-orders')
def prepare_purchase_order(body:PurchaseOrderForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user,'prepare')
    key=request_key(body.request_id)
    day=business_day(body.ordered_on)
    ref=trim(body.order_ref,'رقم أمر الشراء',6,90).upper()
    evidence=trim(body.evidence_ref,'مرجع اعتماد الشراء',8,180)
    lines=[{'item_id':row.item_id,'quantity':row.quantity,'unit_cost_piasters':c_piasters(row.unit_cost)} for row in body.lines]
    if len({x['item_id'] for x in lines})!=len(lines):fail('لا يجوز تكرار الصنف في أمر شراء',409)
    payload={'vendor_id':body.vendor_id,'ordered_on':day,'order_ref':ref,'evidence_ref':evidence,'lines':lines}
    with c:
        c.execute('BEGIN IMMEDIATE')
        permission(c,user,'prepare')
        prior,digest=repeat(c,key,'inventory_purchase_order',user['id'],payload)
        if prior:return {'id':prior,'replayed':True}
        month_open(c,day[:7])
        if not c.execute('SELECT 1 FROM inventory_vendors WHERE id=? AND active=1',(body.vendor_id,)).fetchone():
            fail('مورد غير نشط',409)
        if c.execute('SELECT 1 FROM inventory_purchase_orders WHERE vendor_id=? AND order_ref=?',
                     (body.vendor_id,ref)).fetchone():fail('رقم أمر الشراء مسجل سابقًا',409)
        for line in lines:
            if not c.execute('SELECT 1 FROM inventory_items WHERE id=? AND active=1',(line['item_id'],)).fetchone():
                fail('صنف غير موجود أو غير نشط',409)
        cur=c.execute('''INSERT INTO inventory_purchase_orders
              (vendor_id,ordered_on,order_ref,evidence_ref,created_by,created_at) VALUES (?,?,?,?,?,?)''',
              (body.vendor_id,day,ref,evidence,user['id'],stamp()))
        for line in lines:
            c.execute('INSERT INTO inventory_purchase_order_lines(order_id,item_id,quantity,unit_cost_piasters) VALUES (?,?,?,?)',
                      (cur.lastrowid,line['item_id'],line['quantity'],line['unit_cost_piasters']))
        remember(c,key,'inventory_purchase_order',user['id'],digest,cur.lastrowid)
        audit(c,user['id'],'inventory_purchase_order_requested','inventory_purchase_order',cur.lastrowid,
              {'vendor_id':body.vendor_id,'total_piasters':sum(x['quantity']*x['unit_cost_piasters'] for x in lines)})
    return {'id':cur.lastrowid,'status':'pending'}


@router.post('/purchase-orders/{order_id}/decision')
def decide_purchase_order(order_id:int,body:ReviewForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user,'approve')
    note=trim(body.note,'مراجعة أمر الشراء',8,300)
    with c:
        c.execute('BEGIN IMMEDIATE')
        permission(c,user,'approve')
        order=c.execute('SELECT * FROM inventory_purchase_orders WHERE id=?',(order_id,)).fetchone()
        if not order:fail('أمر الشراء غير موجود',404)
        if order['status']!='pending':fail('أمر الشراء تمت مراجعته بالفعل',409)
        if order['created_by']==user['id']:fail('لا يجوز اعتماد أمر شراء أعددته بنفسك',403)
        month_open(c,order['ordered_on'][:7])
        status='approved' if body.decision=='approve' else 'rejected'
        c.execute('UPDATE inventory_purchase_orders SET status=?,reviewed_by=?,reviewed_at=?,review_note=? WHERE id=?',
                  (status,user['id'],stamp(),note,order_id))
        audit(c,user['id'],'inventory_purchase_order_'+status,'inventory_purchase_order',order_id)
    return {'id':order_id,'status':status,'journal_id':None}


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
    payload={'vendor_id':body.vendor_id,'received_on':day,'invoice_ref':ref,'evidence_ref':proof,'purchase_order_id':body.purchase_order_id,'lines':lines}
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
        if body.purchase_order_id is not None:
            validate_po_receipt(c,cur.lastrowid,body.purchase_order_id)
            c.execute('INSERT INTO inventory_receipt_purchase_links(receipt_id,purchase_order_id) VALUES (?,?)',
                      (cur.lastrowid,body.purchase_order_id))
        remember(c,key,'inventory_receipt',user['id'],digest,cur.lastrowid)
        audit(c,user['id'],'inventory_receipt_requested','inventory_receipt',cur.lastrowid,
              {'received_on':day,'total_piasters':sum(x['quantity']*x['unit_cost_piasters'] for x in lines)})
    return {'id':cur.lastrowid,'status':'pending'}


def ensure_fifo_date_order(c,kind,document_id,entry_day):
    """Existing posted future issues make earlier-dated FIFO valuation ambiguous.

    Same-day stock movement follows approval order: only business *dates* are
    recorded in the legacy subledger. No historical GL allocations are rewritten.
    """
    source = ('inventory_receipt_lines','receipt_id') if kind=='receipt' else ('inventory_issue_lines','issue_id')
    table,field = source
    later=c.execute(f'''SELECT 1 FROM {table} l
        JOIN inventory_issue_lines other_line ON other_line.item_id=l.item_id
        JOIN inventory_issues later_issue ON later_issue.id=other_line.issue_id
        WHERE l.{field}=? AND later_issue.status='approved'
          AND later_issue.used_on>? LIMIT 1''',(document_id,entry_day)).fetchone()
    if later:
        fail('اعتماد المستند بأثر رجعي سيغير ترتيب FIFO بعد صرف مخزون معتمد؛ يلزم تسوية مستقلة',409)
    if kind=='issue' and c.execute('''SELECT 1 FROM inventory_issue_lines line
          JOIN inventory_issue_lines source ON source.item_id=line.item_id
          JOIN inventory_issue_allocations a ON a.issue_line_id=source.id
          JOIN inventory_return_lines retline ON retline.issue_allocation_id=a.id
          JOIN inventory_issue_returns ret ON ret.id=retline.return_id AND ret.status='approved'
          WHERE line.issue_id=? AND ret.returned_on>? LIMIT 1''',(document_id,entry_day)).fetchone():
        fail('لا يجوز صرف كمية بأثر رجعي قبل تاريخ إرجاع دفعتها للمخزن',409)



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
            link=c.execute('SELECT purchase_order_id FROM inventory_receipt_purchase_links WHERE receipt_id=?',
                           (receipt_id,)).fetchone()
            if link:
                # Existing reservation counts this GRN; SQL trigger also revalidates.
                po=c.execute('SELECT * FROM inventory_purchase_orders WHERE id=?',
                             (link['purchase_order_id'],)).fetchone()
                if not po or po['status']!='approved' or po['vendor_id']!=r['vendor_id']:
                    fail('أمر الشراء لم يعد صالحًا للاعتماد',409)
            ensure_fifo_date_order(c,'receipt',receipt_id,r['received_on'])
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


@router.get('/supplier-payables')
def supplier_payables(period:str='',user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user)
    period=valid_month(period or cairo_today()[:7])
    # Only GRN-backed 2200; no claim about voucher/bank settlements or other AP.
    lines=[dict(x) for x in c.execute('''SELECT v.id vendor_id,v.code vendor_code,v.name vendor_name,
       COUNT(r.id) approved_grns,
       COALESCE(SUM((SELECT SUM(l.quantity*l.unit_cost_piasters)
          FROM inventory_receipt_lines l WHERE l.receipt_id=r.id)),0) grn_accrued_piasters,
       COALESCE(SUM(CASE WHEN EXISTS(SELECT 1 FROM inventory_supplier_invoice_matches m
           WHERE m.receipt_id=r.id AND m.status='approved') THEN
          (SELECT SUM(l.quantity*l.unit_cost_piasters) FROM inventory_receipt_lines l WHERE l.receipt_id=r.id)
           ELSE 0 END),0) confirmed_piasters
       FROM inventory_vendors v JOIN inventory_receipts r ON r.vendor_id=v.id AND r.status='approved'
       WHERE substr(r.received_on,1,7)<=? GROUP BY v.id ORDER BY v.name''',(period,))]
    for row in lines:
        row['unmatched_piasters']=row['grn_accrued_piasters']-row['confirmed_piasters']
    return {'period':period,'vendors':lines,
            'total_grn_accrued_piasters':sum(x['grn_accrued_piasters'] for x in lines),
            'confirmed_piasters':sum(x['confirmed_piasters'] for x in lines),
            'unmatched_piasters':sum(x['unmatched_piasters'] for x in lines),
            'payment_posted_piasters':0,
            'scope':'GRN-backed supplier accrual only; no payment, VAT, credit notes, opening AP or reconciliation to external bank statements.'}


@router.get('/supplier-invoices')
def supplier_invoices(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user)
    return {'matches':supplier_invoice_docs(c)}


@router.post('/supplier-invoices')
def prepare_supplier_invoice(body:SupplierInvoiceMatchForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user,'prepare')
    key=request_key(body.request_id)
    day=business_day(body.invoice_date)
    ref=trim(body.invoice_ref,'مرجع فاتورة المورد',6,90).upper()
    evidence=trim(body.evidence_ref,'مرجع صورة فاتورة المورد',8,180)
    amount=c_piasters(body.amount)
    lines=[{'item_id':line.item_id,'quantity':line.quantity,'unit_cost_piasters':c_piasters(line.unit_cost)}
           for line in body.lines]
    if len({x['item_id'] for x in lines})!=len(lines):fail('لا يجوز تكرار نفس الصنف في فاتورة المورد',409)
    if sum(x['quantity']*x['unit_cost_piasters'] for x in lines)!=amount:
        fail('إجمالي بنود فاتورة المورد لا يساوي الإجمالي المقدم',409)
    payload={'receipt_id':body.receipt_id,'invoice_date':day,'invoice_ref':ref,
             'evidence_ref':evidence,'amount_piasters':amount,'lines':lines}
    with c:
        c.execute('BEGIN IMMEDIATE')
        permission(c,user,'prepare')
        prior,digest=repeat(c,key,'inventory_supplier_invoice',user['id'],payload)
        if prior:return {'id':prior,'replayed':True}
        month_open(c,day[:7])
        r=c.execute('''SELECT r.*,p.ordered_on FROM inventory_receipts r
             JOIN inventory_receipt_purchase_links l ON l.receipt_id=r.id
             JOIN inventory_purchase_orders p ON p.id=l.purchase_order_id AND p.status='approved'
             WHERE r.id=?''',(body.receipt_id,)).fetchone()
        if not r or r['status']!='approved' or not r['journal_id']:
            fail('فاتورة المورد لا تطابق استلامًا معتمدًا مرتبطًا بأمر شراء',409)
        if r['invoice_ref']!=ref or day<r['ordered_on'] or receipt_sum(c,body.receipt_id)!=amount:
            fail('مخالفة في رقم الفاتورة أو التاريخ أو الإجمالي بالمطابقة الثلاثية',409)
        stock_lines=[dict(x) for x in c.execute('SELECT item_id,quantity,unit_cost_piasters FROM inventory_receipt_lines WHERE receipt_id=?',
                                                (body.receipt_id,))]
        if sorted((x['item_id'],x['quantity'],x['unit_cost_piasters']) for x in stock_lines)!=\
           sorted((x['item_id'],x['quantity'],x['unit_cost_piasters']) for x in lines):
            fail('بنود فاتورة المورد لا تطابق أصناف وكميات وأسعار محضر الاستلام',409)
        if c.execute("SELECT 1 FROM inventory_supplier_invoice_matches WHERE receipt_id=? AND status IN ('pending','approved')",
                     (body.receipt_id,)).fetchone():fail('فاتورة استلام سبق تسجيل مطابقة نشطة لها',409)
        cur=c.execute('''INSERT INTO inventory_supplier_invoice_matches
            (receipt_id,invoice_date,invoice_ref,amount_piasters,evidence_ref,created_by,created_at)
            VALUES (?,?,?,?,?,?,?)''',(body.receipt_id,day,ref,amount,evidence,user['id'],stamp()))
        for line in lines:
            c.execute('''INSERT INTO inventory_supplier_invoice_match_lines
                     (match_id,item_id,quantity,unit_cost_piasters) VALUES (?,?,?,?)''',
                      (cur.lastrowid,line['item_id'],line['quantity'],line['unit_cost_piasters']))
        remember(c,key,'inventory_supplier_invoice',user['id'],digest,cur.lastrowid)
        audit(c,user['id'],'inventory_supplier_invoice_requested','inventory_supplier_invoice',cur.lastrowid,
              {'receipt_id':body.receipt_id,'amount_piasters':amount})
    return {'id':cur.lastrowid,'status':'pending','journal_id':None}


@router.post('/supplier-invoices/{match_id}/decision')
def decide_supplier_invoice(match_id:int,body:ReviewForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user,'approve')
    note=trim(body.note,'مراجعة المطابقة الثلاثية',8,300)
    with c:
        c.execute('BEGIN IMMEDIATE')
        permission(c,user,'approve')
        match=c.execute('''SELECT m.*,r.created_by receipt_creator,r.status receipt_status,
               r.invoice_ref receipt_ref,r.journal_id,p.ordered_on
            FROM inventory_supplier_invoice_matches m
            JOIN inventory_receipts r ON r.id=m.receipt_id
            JOIN inventory_receipt_purchase_links l ON l.receipt_id=r.id
            JOIN inventory_purchase_orders p ON p.id=l.purchase_order_id AND p.status='approved'
            WHERE m.id=?''',(match_id,)).fetchone()
        if not match:fail('مطابقة فاتورة المورد غير موجودة',404)
        if match['status']!='pending':fail('تم البت في مطابقة الفاتورة بالفعل',409)
        if match['created_by']==user['id'] or match['receipt_creator']==user['id']:
            fail('لا يجوز اعتماد مطابقة قمت بإعدادها أو استلامها بنفسك',403)
        month_open(c,match['invoice_date'][:7])
        if body.decision=='approve':
            if match['receipt_status']!='approved' or match['invoice_ref']!=match['receipt_ref'] or \
                    receipt_sum(c,match['receipt_id'])!=match['amount_piasters'] or match['invoice_date']<match['ordered_on']:
                fail('تغيرت مستندات المطابقة الثلاثية؛ لا يجوز الاعتماد',409)
            source=[tuple(x) for x in c.execute('SELECT item_id,quantity,unit_cost_piasters FROM inventory_receipt_lines WHERE receipt_id=?',
                                                (match['receipt_id'],))]
            invoice=[tuple(x) for x in c.execute('SELECT item_id,quantity,unit_cost_piasters FROM inventory_supplier_invoice_match_lines WHERE match_id=?',
                                                 (match_id,))]
            if sorted(source)!=sorted(invoice):fail('بنود فاتورة المورد لم تعد تطابق محضر الاستلام',409)
            journal=c.execute('SELECT status FROM gl_journals WHERE id=?',(match['journal_id'],)).fetchone()
            if not journal or journal['status']!='posted':fail('قيد استلام المورد غير مرحل',409)
        status='approved' if body.decision=='approve' else 'rejected'
        c.execute('UPDATE inventory_supplier_invoice_matches SET status=?,reviewed_by=?,reviewed_at=?,review_note=? WHERE id=?',
                  (status,user['id'],stamp(),note,match_id))
        audit(c,user['id'],'inventory_supplier_invoice_'+status,'inventory_supplier_invoice',match_id,
              {'receipt_id':match['receipt_id'],'no_new_journal':True})
    return {'id':match_id,'status':status,'journal_id':None}


# G3I: maturity timing for approved supplier invoices; no cash/GL posting.
def supplier_due_documents(c):
    schedules=[dict(x) for x in c.execute('''SELECT s.*,m.invoice_ref,m.invoice_date,
       m.amount_piasters,v.id vendor_id,v.name vendor_name,
       m.created_by invoice_creator,r.created_by receipt_creator
       FROM inventory_supplier_due_schedules s
       JOIN inventory_supplier_invoice_matches m ON m.id=s.invoice_match_id
       JOIN inventory_receipts r ON r.id=m.receipt_id
       JOIN inventory_vendors v ON v.id=r.vendor_id
       ORDER BY s.id DESC LIMIT 100''')]
    ids=[x['id'] for x in schedules]
    lines=[]
    if ids:
        marks=','.join('?'*len(ids))
        lines=[dict(x) for x in c.execute(f'''SELECT id,schedule_id,line_no,due_on,amount_piasters
            FROM inventory_supplier_due_lines WHERE schedule_id IN ({marks})
            ORDER BY schedule_id DESC,line_no''',ids)]
    eligible=[dict(x) for x in c.execute('''SELECT m.id,m.invoice_ref,m.invoice_date,m.amount_piasters,
      v.name vendor_name,r.vendor_id FROM inventory_supplier_invoice_matches m
      JOIN inventory_receipts r ON r.id=m.receipt_id
      JOIN inventory_vendors v ON v.id=r.vendor_id
      WHERE m.status='approved' AND NOT EXISTS (
        SELECT 1 FROM inventory_supplier_due_schedules s
        WHERE s.invoice_match_id=m.id AND s.status IN ('pending','approved'))
      ORDER BY m.id DESC LIMIT 100''')]
    return {'schedules':schedules,'lines':lines,'eligible_invoices':eligible}


def supplier_due_aging(c,as_of):
    point=valid_date(as_of)
    keys=('future','due_today','over_1_30','over_31_60','over_61_90','over_90')
    totals={key+'_piasters':0 for key in keys}
    vendors={}
    approved=[dict(r) for r in c.execute('''SELECT m.id,m.amount_piasters,v.id vendor_id,v.name vendor_name
      FROM inventory_supplier_invoice_matches m
      JOIN inventory_receipts r ON r.id=m.receipt_id
      JOIN inventory_vendors v ON v.id=r.vendor_id WHERE m.status='approved' ''')]
    scheduled_rows=[dict(r) for r in c.execute('''SELECT m.id match_id,l.due_on,l.amount_piasters
       FROM inventory_supplier_due_schedules s
       JOIN inventory_supplier_invoice_matches m ON m.id=s.invoice_match_id AND m.status='approved'
       JOIN inventory_supplier_due_lines l ON l.schedule_id=s.id
       WHERE s.status='approved' ''')]
    schedule_ids={r['match_id'] for r in scheduled_rows}
    vendor_lookup={r['id']:r for r in approved}
    for row in approved:
        vendors.setdefault(row['vendor_id'],{'vendor_id':row['vendor_id'],
             'vendor_name':row['vendor_name'],**{key+'_piasters':0 for key in keys},
             'unscheduled_total_piasters':0})
    for row in approved:
        if row['id'] not in schedule_ids:
            vendors[row['vendor_id']]['unscheduled_total_piasters']+=row['amount_piasters']
    for row in scheduled_rows:
        when=date.fromisoformat(row['due_on']); days=(point-when).days
        key='future' if days<0 else 'due_today' if days==0 else \
            'over_1_30' if days<=30 else 'over_31_60' if days<=60 else \
            'over_61_90' if days<=90 else 'over_90'
        totals[key+'_piasters']+=row['amount_piasters']
        vendors[vendor_lookup[row['match_id']]['vendor_id']][key+'_piasters']+=row['amount_piasters']
    total=sum(r['amount_piasters'] for r in approved)
    unscheduled=sum(v['unscheduled_total_piasters'] for v in vendors.values())
    finance=supplier_settlement_documents(c)
    return {'as_of':point.isoformat(),'approved_invoice_total_piasters':total,
       'scheduled_total_piasters':total-unscheduled,'unscheduled_total_piasters':unscheduled,
       **totals,'over_30_piasters':sum(totals[k+'_piasters'] for k in ('over_31_60','over_61_90','over_90')),
       'payment_posted_piasters':finance['supplier_booked_piasters'],
       'bank_confirmed_piasters':finance['bank_confirmed_piasters'],
       'scoped_outstanding_book_piasters':finance['supplier_outstanding_book_piasters'],
       'vendors':list(vendors.values()),
       'notice':'فئات التأخر هنا بقيمة الأقساط الإجمالية قبل خصم السداد. راجع تسويات G3K لمعرفة المسجل دفتريًا أو المؤكد بكشف بنك معتمد.'}


@router.get('/supplier-due-schedules')
def supplier_due_list(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user)
    return supplier_due_documents(c)


@router.get('/supplier-aging')
def supplier_aging(as_of:str='',user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user)
    return supplier_due_aging(c,as_of or cairo_today())


@router.post('/supplier-due-schedules')
def prepare_supplier_due(body:SupplierDueForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user,'prepare')
    key=request_key(body.request_id)
    scheduled_on=business_day(body.scheduled_on)
    terms=trim(body.terms_ref,'مرجع شروط السداد',8,180)
    lines=[]
    for n,row in enumerate(body.lines,1):
        due=valid_date(row.due_on).isoformat() # Due dates may be in the future.
        money=c_piasters(row.amount)
        if money<=0:fail('يجب أن يكون مبلغ القسط أكبر من صفر',409)
        lines.append({'line_no':n,'due_on':due,'amount_piasters':money})
    payload={'invoice_match_id':body.invoice_match_id,'scheduled_on':scheduled_on,
             'terms_ref':terms,'lines':lines}
    with c:
        c.execute('BEGIN IMMEDIATE')
        permission(c,user,'prepare')
        prior,digest=repeat(c,key,'inventory_supplier_due',user['id'],payload)
        if prior:return {'id':prior,'replayed':True}
        month_open(c,scheduled_on[:7])
        matched=c.execute('''SELECT m.*,r.created_by receipt_creator FROM inventory_supplier_invoice_matches m
             JOIN inventory_receipts r ON r.id=m.receipt_id WHERE m.id=?''',(body.invoice_match_id,)).fetchone()
        if not matched or matched['status']!='approved':fail('فاتورة المورد تحتاج مطابقة ثلاثية معتمدة',409)
        if any(x['due_on']<matched['invoice_date'] for x in lines):
            fail('لا يجوز أن يسبق استحقاق القسط تاريخ فاتورة المورد',409)
        if sum(x['amount_piasters'] for x in lines)!=matched['amount_piasters']:
            fail('مجموع الأقساط يجب أن يطابق إجمالي فاتورة المورد بالقروش',409)
        if c.execute('''SELECT 1 FROM inventory_supplier_due_schedules
            WHERE invoice_match_id=? AND status IN ('pending','approved')''',(body.invoice_match_id,)).fetchone():
            fail('هناك جدول استحقاق نشط لنفس فاتورة المورد',409)
        cur=c.execute('''INSERT INTO inventory_supplier_due_schedules
              (invoice_match_id,scheduled_on,terms_ref,created_by,created_at)
              VALUES(?,?,?,?,?)''',(body.invoice_match_id,scheduled_on,terms,user['id'],stamp()))
        for row in lines:
            c.execute('''INSERT INTO inventory_supplier_due_lines
                (schedule_id,line_no,due_on,amount_piasters) VALUES(?,?,?,?)''',
                (cur.lastrowid,row['line_no'],row['due_on'],row['amount_piasters']))
        remember(c,key,'inventory_supplier_due',user['id'],digest,cur.lastrowid)
        audit(c,user['id'],'inventory_supplier_due_requested','inventory_supplier_due',cur.lastrowid,
              {'invoice_match_id':body.invoice_match_id,'amount_piasters':matched['amount_piasters']})
    return {'id':cur.lastrowid,'status':'pending','journal_id':None}


@router.post('/supplier-due-schedules/{schedule_id}/decision')
def decide_supplier_due(schedule_id:int,body:ReviewForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user,'approve')
    note=trim(body.note,'مراجعة شروط السداد',8,300)
    with c:
        c.execute('BEGIN IMMEDIATE')
        permission(c,user,'approve')
        row=c.execute('''SELECT s.*,m.invoice_date,m.amount_piasters,m.status match_status,
           m.created_by invoice_creator,r.created_by receipt_creator
           FROM inventory_supplier_due_schedules s
           JOIN inventory_supplier_invoice_matches m ON m.id=s.invoice_match_id
           JOIN inventory_receipts r ON r.id=m.receipt_id WHERE s.id=?''',(schedule_id,)).fetchone()
        if not row:fail('جدول الاستحقاق غير موجود',404)
        if row['status']!='pending':fail('تمت مراجعة هذا الجدول من قبل',409)
        if user['id'] in (row['created_by'],row['invoice_creator'],row['receipt_creator']):
            fail('الاعتماد المستقل يمنع مُعد الجدول أو الفاتورة أو الاستلام',403)
        month_open(c,row['scheduled_on'][:7])
        if body.decision=='approve':
            detail=list(c.execute('SELECT due_on,amount_piasters FROM inventory_supplier_due_lines WHERE schedule_id=?',
                                  (schedule_id,)))
            if row['match_status']!='approved' or not 1<=len(detail)<=12 or \
                  sum(x['amount_piasters'] for x in detail)!=row['amount_piasters'] or \
                  any(x['due_on']<row['invoice_date'] for x in detail):
                fail('بنود شروط السداد لا تطابق الفاتورة المعتمدة',409)
        status='approved' if body.decision=='approve' else 'rejected'
        c.execute('''UPDATE inventory_supplier_due_schedules
           SET status=?,reviewed_by=?,reviewed_at=?,review_note=? WHERE id=?''',
           (status,user['id'],stamp(),note,schedule_id))
        audit(c,user['id'],'inventory_supplier_due_'+status,'inventory_supplier_due',schedule_id,
              {'no_new_ledger_entry':True})
    return {'id':schedule_id,'status':status,'journal_id':None}


def supplier_payment_request_documents(c):
    """The authorization queue deliberately does NOT imply any cashbook/bank payment."""
    requests=[dict(x) for x in c.execute('''SELECT p.*,l.due_on,l.line_no,l.amount_piasters installment_piasters,
      s.created_by schedule_creator,m.created_by invoice_creator,r.created_by receipt_creator,
      m.invoice_ref,m.amount_piasters invoice_piasters,v.name vendor_name,v.id vendor_id,v.active vendor_active
      FROM inventory_supplier_payment_requests p
      JOIN inventory_supplier_due_lines l ON l.id=p.due_line_id
      JOIN inventory_supplier_due_schedules s ON s.id=l.schedule_id
      JOIN inventory_supplier_invoice_matches m ON m.id=s.invoice_match_id
      JOIN inventory_receipts r ON r.id=m.receipt_id
      JOIN inventory_vendors v ON v.id=r.vendor_id
      ORDER BY p.id DESC LIMIT 100''')]
    eligible=[dict(x) for x in c.execute('''SELECT l.id,l.due_on,l.line_no,l.amount_piasters,
       s.id schedule_id,m.invoice_ref,v.id vendor_id,v.name vendor_name,
       COALESCE((SELECT SUM(p.amount_piasters) FROM inventory_supplier_payment_requests p
         WHERE p.due_line_id=l.id AND p.status IN ('pending','approved')),0) reserved_piasters
       FROM inventory_supplier_due_lines l
       JOIN inventory_supplier_due_schedules s ON s.id=l.schedule_id AND s.status='approved'
       JOIN inventory_supplier_invoice_matches m ON m.id=s.invoice_match_id AND m.status='approved'
       JOIN inventory_receipts r ON r.id=m.receipt_id AND r.status='approved'
       JOIN inventory_vendors v ON v.id=r.vendor_id AND v.active=1
       ORDER BY l.due_on,l.id''')]
    for row in eligible:
        row['available_to_request_piasters']=row['amount_piasters']-row['reserved_piasters']
    return {'requests':requests,'eligible_lines':eligible,'scope':'AUTHORIZATION_ONLY_NO_PAYMENT',
            'notice':'هذه طلبات اعتماد تمهيدية فقط؛ لا تمثل سدادًا بنكيًا أو نقديًا أو تخفيضًا للمديونية.'}


@router.get('/supplier-payment-requests')
def supplier_payment_requests(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user)
    return supplier_payment_request_documents(c)


@router.post('/supplier-payment-requests')
def prepare_supplier_payment_request(body:SupplierPaymentRequestForm,user=Depends(get_user),
                                     c:sqlite3.Connection=Depends(db)):
    permission(c,user,'prepare')
    key=request_key(body.request_id)
    day=business_day(body.requested_on)
    amount=c_piasters(body.amount)
    if amount<=0:fail('مبلغ الطلب التمهيدي يجب أن يكون أكبر من صفر',409)
    ref=trim(body.evidence_ref,'مرجع طلب الصرف التمهيدي',8,180)
    payload={'due_line_id':body.due_line_id,'requested_on':day,'amount_piasters':amount,'evidence_ref':ref}
    with c:
        c.execute('BEGIN IMMEDIATE')
        permission(c,user,'prepare')
        previous,digest=repeat(c,key,'inventory_supplier_payment_request',user['id'],payload)
        if previous:return {'id':previous,'replayed':True,'money_moved':False}
        month_open(c,day[:7])
        row=c.execute('''SELECT l.amount_piasters,s.status schedule_status,m.status invoice_status,
                r.status receipt_status,v.active vendor_active
              FROM inventory_supplier_due_lines l
              JOIN inventory_supplier_due_schedules s ON s.id=l.schedule_id
              JOIN inventory_supplier_invoice_matches m ON m.id=s.invoice_match_id
              JOIN inventory_receipts r ON r.id=m.receipt_id
              JOIN inventory_vendors v ON v.id=r.vendor_id
              WHERE l.id=?''',(body.due_line_id,)).fetchone()
        if not row or any(row[k]!=expected for k,expected in (
            ('schedule_status','approved'),('invoice_status','approved'),
            ('receipt_status','approved'),('vendor_active',1))):
            fail('طلب الصرف يحتاج قسط فاتورة مورد صالحًا ومعتمدًا',409)
        reserved=c.execute('''SELECT COALESCE(SUM(amount_piasters),0) FROM inventory_supplier_payment_requests
               WHERE due_line_id=? AND status IN ('pending','approved')''',(body.due_line_id,)).fetchone()[0]
        if amount+reserved>row['amount_piasters']:
            fail('طلب الصرف يتجاوز المتاح لطلب الموافقة لهذا القسط',409)
        cur=c.execute('''INSERT INTO inventory_supplier_payment_requests
          (due_line_id,requested_on,amount_piasters,evidence_ref,created_by,created_at)
          VALUES (?,?,?,?,?,?)''',(body.due_line_id,day,amount,ref,user['id'],stamp()))
        remember(c,key,'inventory_supplier_payment_request',user['id'],digest,cur.lastrowid)
        audit(c,user['id'],'supplier_payment_requested','supplier_payment_request',cur.lastrowid,
              {'money_moved':False,'amount_piasters':amount,'due_line_id':body.due_line_id})
    return {'id':cur.lastrowid,'status':'pending','money_moved':False,'journal_id':None}


@router.post('/supplier-payment-requests/{payment_request_id}/decision')
def decide_supplier_payment_request(payment_request_id:int,body:ReviewForm,user=Depends(get_user),
                                    c:sqlite3.Connection=Depends(db)):
    permission(c,user,'approve')
    note=trim(body.note,'مراجعة طلب صرف المورد التمهيدي',8,300)
    with c:
        c.execute('BEGIN IMMEDIATE')
        permission(c,user,'approve')
        row=c.execute('''SELECT p.*,s.created_by schedule_creator,m.created_by invoice_creator,
             r.created_by receipt_creator,r.status receipt_status,v.active vendor_active,
             s.status schedule_status,m.status invoice_status
           FROM inventory_supplier_payment_requests p
           JOIN inventory_supplier_due_lines l ON l.id=p.due_line_id
           JOIN inventory_supplier_due_schedules s ON s.id=l.schedule_id
           JOIN inventory_supplier_invoice_matches m ON m.id=s.invoice_match_id
           JOIN inventory_receipts r ON r.id=m.receipt_id
           JOIN inventory_vendors v ON v.id=r.vendor_id WHERE p.id=?''',(payment_request_id,)).fetchone()
        if not row:fail('طلب صرف المورد التمهيدي غير موجود',404)
        if row['status']!='pending':fail('تمت مراجعة طلب الصرف بالفعل',409)
        if user['id'] in (row['created_by'],row['schedule_creator'],row['invoice_creator'],row['receipt_creator']):
            fail('لا يجوز اعتماد طلب صرف أعددت أصل فاتورته أو استلامه أو شروطه',403)
        month_open(c,row['requested_on'][:7])
        if row['schedule_status']!='approved' or row['invoice_status']!='approved':
            fail('أصل المستند لم يعد معتمدًا',409)
        if body.decision=='approve' and (row['receipt_status']!='approved' or row['vendor_active']!=1):
            fail('لا يمكن اعتماد صرف تمهيدي لمورد موقوف أو استلام غير معتمد',409)
        status='approved' if body.decision=='approve' else 'rejected'
        c.execute('''UPDATE inventory_supplier_payment_requests
           SET status=?,reviewed_by=?,reviewed_at=?,review_note=? WHERE id=?''',
           (status,user['id'],stamp(),note,payment_request_id))
        audit(c,user['id'],'supplier_payment_request_'+status,'supplier_payment_request',payment_request_id,
              {'money_moved':False,'journal_id':None})
    return {'id':payment_request_id,'status':status,'money_moved':False,'journal_id':None}


# G3K: supplier AP settlement uses the EXISTING voucher and signed bank evidence.
# A posted cashbook voucher is NOT the same as bank-confirmed beneficiary payment.
def check_supplier_bank_voucher_approval(c,v,user):
    row=c.execute('''SELECT link.voucher_id,p.created_by request_creator,p.reviewed_by request_reviewer,
       s.created_by schedule_creator,im.created_by invoice_creator,r.created_by receipt_creator,
       p.amount_piasters,p.requested_on,p.status request_status,
       s.status schedule_status,im.status invoice_status,r.status receipt_status,
       vendor.active vendor_active
       FROM inventory_supplier_bank_vouchers link
       JOIN inventory_supplier_payment_requests p ON p.id=link.payment_request_id
       JOIN inventory_supplier_due_lines l ON l.id=p.due_line_id
       JOIN inventory_supplier_due_schedules s ON s.id=l.schedule_id
       JOIN inventory_supplier_invoice_matches im ON im.id=s.invoice_match_id
       JOIN inventory_receipts r ON r.id=im.receipt_id
       JOIN inventory_vendors vendor ON vendor.id=r.vendor_id
       WHERE link.voucher_id=?''',(v['id'],)).fetchone()
    if not row or user['id'] in tuple(row[k] for k in (
         'request_creator','request_reviewer','schedule_creator','invoice_creator','receipt_creator')):
        fail('اعتماد سند المورد يتطلب مراجعًا ماليًا مستقلًا عن مستندات المورد',403)
    if v['kind']!='payment' or row['amount_piasters']!=v['amount_piasters'] or v['date']<row['requested_on']:
        fail('سند المورد غير مطابق للطلب المعتمد',409)
    if any(row[k]!=expected for k,expected in (('request_status','approved'),('schedule_status','approved'),
            ('invoice_status','approved'),('receipt_status','approved'),('vendor_active',1))):
        fail('أصل المستند غير معتمد أو المورد متوقف',409)


@router.post('/supplier-payment-requests/{payment_request_id}/bank-voucher')
def create_supplier_bank_voucher(payment_request_id:int,body:SupplierBankVoucherForm,
                                 user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    # Posting occurs only from the existing /api/vouchers/{id}/decision.
    from app import authorize_cashbook_fund, shift_for_posting
    permission(c,user,'prepare')
    day=business_day(body.booked_on)
    reference=trim(body.bank_reference,'مرجع تعليمات صرف المورد البنكية',8,100)
    key=request_key(body.request_id)
    payload={'payment_request_id':payment_request_id,'bank_fund_id':body.bank_fund_id,
             'booked_on':day,'bank_reference':reference}
    with c:
        c.execute('BEGIN IMMEDIATE')
        permission(c,user,'prepare')
        previous,digest=repeat(c,key,'inventory_supplier_bank_voucher',user['id'],payload)
        if previous:
            return {'voucher_id':previous,'status':c.execute('SELECT status FROM vouchers WHERE id=?',
                   (previous,)).fetchone()[0],'replayed':True,'bank_transfer_initiated':False}
        month_open(c,day[:7])
        fund=c.execute("SELECT * FROM funds WHERE id=? AND active=1 AND kind='bank'",
                       (body.bank_fund_id,)).fetchone()
        if not fund:fail('صرف المورد مربوط فقط بحساب بنكي نشط',409)
        if c.execute("SELECT 1 FROM billing_payment_channels WHERE method='card' AND fund_id=?",
                     (body.bank_fund_id,)).fetchone():
            fail('لا يجوز استخدام حساب تحصيل POS لتسوية الموردين',409)
        authorize_cashbook_fund(c,user,body.bank_fund_id)
        shift_for_posting(c,body.bank_fund_id,day,'central')
        row=c.execute('''SELECT p.*,s.created_by schedule_creator,im.created_by invoice_creator,
           r.created_by receipt_creator,v.name vendor_name,v.active vendor_active,
           r.status receipt_status,im.status invoice_status,s.status schedule_status
           FROM inventory_supplier_payment_requests p
           JOIN inventory_supplier_due_lines l ON l.id=p.due_line_id
           JOIN inventory_supplier_due_schedules s ON s.id=l.schedule_id
           JOIN inventory_supplier_invoice_matches im ON im.id=s.invoice_match_id
           JOIN inventory_receipts r ON r.id=im.receipt_id
           JOIN inventory_vendors v ON v.id=r.vendor_id WHERE p.id=?''',(payment_request_id,)).fetchone()
        if not row:fail('طلب سداد المورد غير موجود',404)
        if row['status']!='approved' or row['receipt_status']!='approved' or row['invoice_status']!='approved' or row['schedule_status']!='approved' or row['vendor_active']!=1:
            fail('سند البنك يحتاج طلبًا معتمدًا وموردًا نشطًا',409)
        if user['id'] in (row['created_by'],row['reviewed_by'],row['schedule_creator'],
                          row['invoice_creator'],row['receipt_creator']):
            fail('منفذ سند البنك يجب أن يستقل عن معدّي ومراجعي مستندات المورد',403)
        if day<row['requested_on']:fail('تاريخ سند البنك لا يسبق الطلب المعتمد',409)
        if c.execute("""SELECT 1 FROM inventory_supplier_bank_vouchers link
            JOIN vouchers old_voucher ON old_voucher.id=link.voucher_id
            WHERE old_voucher.status!='rejected' AND old_voucher.from_fund_id=?
              AND UPPER(TRIM(old_voucher.reference_no))=UPPER(?)""",
            (body.bank_fund_id,reference)).fetchone():
            fail('مرجع تعليمات البنك مستخدم بالفعل لسند مورد نشط',409)
        if c.execute('''SELECT 1 FROM inventory_supplier_bank_vouchers link
              JOIN vouchers v ON v.id=link.voucher_id
              WHERE link.payment_request_id=? AND v.status NOT IN ('rejected','reversed') ''',(payment_request_id,)).fetchone():
            fail('طلب المورد له سند بنك معلّق أو معتمد بالفعل',409)
        category=c.execute("SELECT id FROM categories WHERE code='supplier_ap_settlement' AND active=1").fetchone()
        department=c.execute("SELECT id FROM departments WHERE code='ADMIN' AND active=1").fetchone()
        if not category or not department:fail('تصنيف سداد المورد أو القسم الإداري غير مفعل',409)
        import secrets
        cur=c.execute('''INSERT INTO vouchers(voucher_no,date,kind,department_id,category_id,from_fund_id,
           shift,amount_piasters,description,reference_no,status,created_by,created_at)
           VALUES (?,?,'payment',?, ?,?,'central',?,?,?,'pending',?,?)''',
           ('PENDING-'+secrets.token_hex(8),day,department[0],category[0],body.bank_fund_id,
            row['amount_piasters'],'سداد التزام مورد: '+row['vendor_name'],reference,user['id'],stamp()))
        voucher_id=cur.lastrowid
        voucher_no=f'RAM-{day[:4]}-{voucher_id:06d}'
        c.execute('UPDATE vouchers SET voucher_no=? WHERE id=?',(voucher_no,voucher_id))
        c.execute('INSERT INTO inventory_supplier_bank_vouchers(payment_request_id,voucher_id,created_by,created_at) VALUES (?,?,?,?)',
                  (payment_request_id,voucher_id,user['id'],stamp()))
        remember(c,key,'inventory_supplier_bank_voucher',user['id'],digest,voucher_id)
        audit(c,user['id'],'supplier_bank_voucher_requested','voucher',voucher_id,
              {'payment_request_id':payment_request_id,'amount_piasters':row['amount_piasters'],
               'bank_transfer_initiated':False})
    return {'voucher_id':voucher_id,'voucher_no':voucher_no,'status':'pending',
            'bank_transfer_initiated':False}


def supplier_settlement_documents(c):
    """Separate posted cashbook, active statement match, and SIGNED reference match."""
    records=[dict(r) for r in c.execute('''SELECT p.id payment_request_id,p.amount_piasters,
       p.due_line_id,im.invoice_ref,im.amount_piasters invoice_piasters,
       ven.id vendor_id,ven.name vendor_name,link.voucher_id,
       v.voucher_no,v.status voucher_status,v.date booked_on,v.reference_no bank_reference,
       v.from_fund_id,
       (SELECT j.id FROM gl_journals j WHERE j.origin='voucher' AND j.source_id=v.id AND j.status='posted') posted_journal_id,
       fm.id movement_id,fm.amount_piasters movement_piasters,
       bm.id match_id,bl.reference statement_reference,bl.id statement_line_id,
       bs.id statement_batch_id,bs.status bank_statement_status
       FROM inventory_supplier_payment_requests p
       JOIN inventory_supplier_due_lines l ON l.id=p.due_line_id
       JOIN inventory_supplier_due_schedules s ON s.id=l.schedule_id
       JOIN inventory_supplier_invoice_matches im ON im.id=s.invoice_match_id
       JOIN inventory_receipts r ON r.id=im.receipt_id
       JOIN inventory_vendors ven ON ven.id=r.vendor_id
       LEFT JOIN inventory_supplier_bank_vouchers link ON link.payment_request_id=p.id
       LEFT JOIN vouchers v ON v.id=link.voucher_id
       LEFT JOIN fund_movements fm ON fm.voucher_id=v.id AND fm.fund_id=v.from_fund_id
       LEFT JOIN bank_statement_matches bm ON bm.movement_id=fm.id AND bm.status='active'
       LEFT JOIN bank_statement_lines bl ON bl.id=bm.line_id
       LEFT JOIN bank_statement_batches bs ON bs.id=bl.batch_id AND bs.status!='voided'
       WHERE p.status='approved' ORDER BY p.id DESC''')]
    for item in records:
        booked=bool(item['voucher_status']=='approved' and item['posted_journal_id']
            and item['movement_piasters']==-item['amount_piasters'])
        item['booked_piasters']=item['amount_piasters'] if booked else 0
        item['bank_matched_piasters']=item['amount_piasters'] if booked and item['match_id'] and item['bank_statement_status'] else 0
        ref_ok=(bool(item['statement_reference']) and
                str(item['statement_reference']).strip().upper()==str(item['bank_reference']).strip().upper())
        item['bank_reference_verified']=ref_ok
        item['bank_confirmed_piasters']=item['amount_piasters'] if booked and ref_ok and item['bank_statement_status']=='approved' else 0
    # Count invoices from G3H only. Do not pretend this is the global control-account balance.
    invoices=[dict(r) for r in c.execute('''SELECT im.amount_piasters,ven.id vendor_id,ven.name vendor_name
       FROM inventory_supplier_invoice_matches im
       JOIN inventory_receipts r ON r.id=im.receipt_id
       JOIN inventory_vendors ven ON ven.id=r.vendor_id
       WHERE im.status='approved' ''')]
    total=sum(r['amount_piasters'] for r in invoices)
    booked=sum(r['booked_piasters'] for r in records)
    matched=sum(r['bank_matched_piasters'] for r in records)
    confirmed=sum(r['bank_confirmed_piasters'] for r in records)
    by_vendor={}
    for row in invoices:
        v=by_vendor.setdefault(row['vendor_id'],{'vendor_id':row['vendor_id'],
          'vendor_name':row['vendor_name'],'invoice_piasters':0,'booked_piasters':0,
          'bank_confirmed_piasters':0})
        v['invoice_piasters']+=row['amount_piasters']
    for row in records:
        v=by_vendor[row['vendor_id']]
        v['booked_piasters']+=row['booked_piasters']
        v['bank_confirmed_piasters']+=row['bank_confirmed_piasters']
    for v in by_vendor.values():
        v['outstanding_book_piasters']=v['invoice_piasters']-v['booked_piasters']
        v['outstanding_confirmed_piasters']=v['invoice_piasters']-v['bank_confirmed_piasters']
    return {'items':records,'vendors':list(by_vendor.values()),
      'supplier_invoice_total_piasters':total,'supplier_booked_piasters':booked,
      'bank_matched_piasters':matched,'bank_confirmed_piasters':confirmed,
      'supplier_outstanding_book_piasters':total-booked,
      'supplier_outstanding_confirmed_piasters':total-confirmed,
      'notice':'إجمالي مطابقات المخزون فقط. القيد البنكي ليس إثبات تحويل للمستفيد؛ تأكيد البنك هنا يعني كشفًا معتمدًا بمرجع مطابق، ولا يغني عن إثبات اسم المستفيد.'}


@router.get('/supplier-settlements')
def supplier_settlements(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user,'read')
    return supplier_settlement_documents(c)


def supplier_attribution_documents(c,user=None):
    rows=[dict(r) for r in c.execute("""SELECT m.*,j.entry_date,j.created_by original_creator,
        j.reviewed_by original_reviewer,v.name vendor_name,v.code vendor_code,
        (SELECT SUM(l.credit_piasters-l.debit_piasters) FROM gl_lines l
         JOIN gl_accounts a ON a.id=l.account_id AND a.code='2200'
         WHERE l.journal_id=m.gl_journal_id) ap_delta_piasters
        FROM supplier_journal_attributions m
        JOIN inventory_vendors v ON v.id=m.vendor_id
        JOIN gl_journals j ON j.id=m.gl_journal_id
        ORDER BY m.id DESC LIMIT 100""")]
    return [r for r in rows if user is None or user['role']!='clerk' or r['created_by']==user['id']]


def supplier_attribution_source(c,journal_id):
    j=c.execute("""SELECT j.* FROM gl_journals j WHERE j.id=?""",(journal_id,)).fetchone()
    if not j or j['status']!='posted' or j['origin']!='manual' or j['source_id'] is not None or j['reversal_of_id'] is not None:
        fail('القيد غير معتمد أو مرتبط بمصدر آخر؛ لا يجوز نسبته تلقائيًا',409)
    if financial_integrity.journal_source(c,journal_id):
        fail('القيد مربوط بالفعل بمستند تشغيلي؛ لا يجوز نسبته مرة أخرى',409)
    amount=c.execute("""SELECT l.credit_piasters-l.debit_piasters
           FROM gl_lines l JOIN gl_accounts a ON a.id=l.account_id AND a.code='2200'
           WHERE l.journal_id=?""",(journal_id,)).fetchall()
    if len(amount)!=1 or int(amount[0][0])==0:
        fail('هذا القيد لا يحتوي على سطر واحد صالح لحساب 2200؛ يحتاج معالجة خاصة',409)
    return dict(j),int(amount[0][0])


@router.get('/supplier-attributions')
def supplier_attributions(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user,'read')
    return {'documents':supplier_attribution_documents(c,user),
            'notice':'إثبات نسب قيد قديم إلى مورد لا ينشئ أي قيد أو يسدد أي دين؛ الدليل وموافقة المراجع المالي إلزاميان.'}


@router.post('/supplier-attributions')
def propose_supplier_attribution(body:SupplierAttributionForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user,'prepare')
    if user['role'] not in ('owner','clerk'):fail('إعداد ربط القيد متاح لصاحب النظام أو الموظف المفوض فقط',403)
    key=request_key(body.request_id)
    evidence=trim(body.evidence_ref,'مرجع دليل القيد الأصلي',8,180)
    reason=trim(body.reason,'شرح وجه استحقاق المورد',12,300)
    payload={'journal_id':body.journal_id,'vendor_id':body.vendor_id,'evidence_ref':evidence,'reason':reason}
    with c:
        c.execute('BEGIN IMMEDIATE')
        permission(c,user,'prepare')
        prior,digest=repeat(c,key,'supplier_gl_attribution',user['id'],payload)
        if prior:
            current=c.execute('SELECT status FROM supplier_journal_attributions WHERE id=?',(prior,)).fetchone()
            return {'id':prior,'status':current['status'],'replayed':True,'money_moved':False}
        supplier_attribution_source(c,body.journal_id)
        vendor=c.execute('SELECT 1 FROM inventory_vendors WHERE id=? AND active=1',(body.vendor_id,)).fetchone()
        if not vendor:fail('المورد غير موجود أو موقوف',409)
        if c.execute("SELECT 1 FROM supplier_journal_attributions WHERE gl_journal_id=? AND status IN ('pending','approved')",(body.journal_id,)).fetchone():
            fail('يوجد ربط قائم لهذا القيد؛ لا يمكن تكرار النسب',409)
        cur=c.execute("""INSERT INTO supplier_journal_attributions
            (gl_journal_id,vendor_id,evidence_ref,reason,created_by,created_at)
            VALUES (?,?,?,?,?,?)""",(body.journal_id,body.vendor_id,evidence,reason,user['id'],stamp()))
        remember(c,key,'supplier_gl_attribution',user['id'],digest,cur.lastrowid)
        audit(c,user['id'],'supplier_attribution_proposed','supplier_journal_attribution',cur.lastrowid,
              {'gl_journal_id':body.journal_id,'vendor_id':body.vendor_id,'no_gl_posting':True})
    return {'id':cur.lastrowid,'status':'pending','money_moved':False}


@router.post('/supplier-attributions/{attribution_id}/decision')
def review_supplier_attribution(attribution_id:int,body:ReviewForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user,'approve')
    if user['role'] not in ('owner','reviewer'):fail('المراجعة المالية تتطلب دور مراجع مستقل',403)
    note=trim(body.note,'سبب قرار المراجع',8,300)
    with c:
        c.execute('BEGIN IMMEDIATE')
        permission(c,user,'approve')
        doc=c.execute("""SELECT m.*,j.created_by original_creator,j.reviewed_by original_reviewer
              FROM supplier_journal_attributions m JOIN gl_journals j ON j.id=m.gl_journal_id
              WHERE m.id=?""",(attribution_id,)).fetchone()
        if not doc:fail('مستند نسبة المورد غير موجود',404)
        if doc['status']!='pending':fail('تم اتخاذ القرار بالفعل',409)
        if user['id'] in (doc['created_by'],doc['original_creator'],doc['original_reviewer']):
            fail('يجب فصل مراجع النسب عن منشئ القيد وأي مراجع سابق',403)
        if body.decision=='approve':
            supplier_attribution_source(c,doc['gl_journal_id'])
            if not c.execute('SELECT 1 FROM inventory_vendors WHERE id=? AND active=1',(doc['vendor_id'],)).fetchone():
                fail('المورد توقف؛ لا يمكن اعتماد النسب',409)
        status='approved' if body.decision=='approve' else 'rejected'
        c.execute("""UPDATE supplier_journal_attributions SET status=?,reviewed_by=?,reviewed_at=?,review_note=?
                     WHERE id=?""",(status,user['id'],stamp(),note,attribution_id))
        audit(c,user['id'],'supplier_attribution_'+status,'supplier_journal_attribution',attribution_id,
              {'source_gl_journal_id':doc['gl_journal_id'],'no_gl_posting':True})
    return {'id':attribution_id,'status':status,'money_moved':False}


def opening_month_end(value: str) -> str:
    day=valid_date(value)
    current=date.fromisoformat(cairo_today())
    if day>=current.replace(day=1) or (day+timedelta(days=1)).day!=1:
        fail('محضر رصيد افتتاحي يُعد فقط بنهاية شهر سابق مكتمل',409)
    return day.isoformat()


def supplier_opening_docs(c, user=None):
    rows=[dict(x) for x in c.execute('''SELECT s.*,v.name vendor_name,v.code vendor_code,
            v.active vendor_active FROM supplier_opening_statements s
            JOIN inventory_vendors v ON v.id=s.vendor_id ORDER BY s.id DESC LIMIT 100''')]
    visible=[row for row in rows if user is None or user['role']!='clerk' or row['created_by']==user['id']]
    cache={}
    for doc in visible:
        key=(doc['as_of'],doc['vendor_id'])
        if key not in cache:cache[key]=supplier_opening_snapshot(c,*key)
        snap=cache[key]
        doc['source_changed']=snap['source_digest']!=doc['source_digest']
        doc['current_ledger_piasters']=snap['ledger_piasters']
        doc['review_blocked']=(doc['source_changed'] or doc['statement_piasters']!=snap['ledger_piasters']
                    or not snap['reconciled'] or snap['ledger_piasters']<0)
    return visible


@router.get('/supplier-opening-statements')
def supplier_opening_statements(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user,'read')
    docs=supplier_opening_docs(c,user)
    return {'documents':docs,'money_moved':False,
        'notice':'مطابقة مستند كشف مورد لآخر شهر مكتمل. هذه مراجعة رقابية لا تنشئ رصيداً افتتاحياً أو قيداً مالياً.'}


@router.post('/supplier-opening-statements')
def propose_supplier_opening(body:SupplierOpeningStatementForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user,'prepare')
    if user['role'] not in ('owner','clerk'):fail('إعداد مستند المورد لموظف مفوض فقط',403)
    cutoff=opening_month_end(body.as_of)
    amount=c_piasters(body.statement_balance,allow_zero=True)
    evidence=trim(body.evidence_ref,'مرجع كشف المورد الموقع',8,180)
    reason=trim(body.reason,'سبب اعتماد المطابقة الافتتاحية',12,300)
    key=request_key(body.request_id)
    payload={'vendor_id':body.vendor_id,'as_of':cutoff,'statement_piasters':amount,
             'evidence_ref':evidence,'reason':reason}
    with c:
        c.execute('BEGIN IMMEDIATE')
        permission(c,user,'prepare')
        old,digest=repeat(c,key,'supplier_opening_statement',user['id'],payload)
        if old:
            previous=c.execute('SELECT status FROM supplier_opening_statements WHERE id=?',(old,)).fetchone()
            return {'id':old,'status':previous['status'],'replayed':True,'money_moved':False}
        vendor=c.execute('SELECT id FROM inventory_vendors WHERE id=? AND active=1',(body.vendor_id,)).fetchone()
        if not vendor:fail('المورد غير موجود أو موقوف',409)
        if c.execute("SELECT 1 FROM supplier_opening_statements WHERE vendor_id=? AND as_of=? AND status IN ('pending','approved')",
                     (body.vendor_id,cutoff)).fetchone():fail('يوجد محضر قائم لهذا المورد في نهاية هذا الشهر',409)
        snap=supplier_opening_snapshot(c,cutoff,body.vendor_id)
        cur=c.execute('''INSERT INTO supplier_opening_statements
            (vendor_id,as_of,statement_piasters,ledger_piasters,control_piasters,
             attributed_piasters,unattributed_count,anomaly_count,source_digest,
             evidence_ref,reason,created_by,created_at)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
             (body.vendor_id,cutoff,amount,snap['ledger_piasters'],snap['control_piasters'],
              snap['attributed_piasters'],snap['unattributed_count'],snap['anomaly_count'],
              snap['source_digest'],evidence,reason,user['id'],stamp()))
        remember(c,key,'supplier_opening_statement',user['id'],digest,cur.lastrowid)
        audit(c,user['id'],'supplier_opening_proposed','supplier_opening_statement',cur.lastrowid,
            {'vendor_id':body.vendor_id,'cutoff':cutoff,'no_gl_posting':True})
    return {'id':cur.lastrowid,'status':'pending','money_moved':False}


@router.post('/supplier-opening-statements/{statement_id}/decision')
def decide_supplier_opening(statement_id:int,body:ReviewForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user,'approve')
    if user['role'] not in ('owner','reviewer'):fail('المراجع المالي المستقل فقط يمكنه اتخاذ القرار',403)
    note=trim(body.note,'سبب قرار مراجعة كشف المورد',8,300)
    with c:
        c.execute('BEGIN IMMEDIATE')
        permission(c,user,'approve')
        doc=c.execute('SELECT * FROM supplier_opening_statements WHERE id=?',(statement_id,)).fetchone()
        if not doc:fail('مستند مراجعة الرصيد غير موجود',404)
        if doc['status']!='pending':fail('تمت مراجعة المستند بالفعل',409)
        if doc['created_by']==user['id']:fail('لا يجوز اعتماد مستند أعددته بنفسك',403)
        if body.decision=='approve':
            snap=supplier_opening_snapshot(c,doc['as_of'],doc['vendor_id'])
            if snap['source_digest']!=doc['source_digest']:
                fail('مصادر حساب المورد تغيرت بعد تقديم المستند؛ ارفض وأعد التقديم بكشف جديد',409)
            if not snap['reconciled'] or snap['ledger_piasters']<0 or doc['statement_piasters']!=snap['ledger_piasters']:
                fail('لا يمكن اعتماد رصيد افتتاحي مع فرق أو قيد غير منسوب أو كشف مورد غير مطابق',409)
            if not c.execute('SELECT 1 FROM inventory_vendors WHERE id=? AND active=1',(doc['vendor_id'],)).fetchone():
                fail('المورد موقوف ولا يجوز اعتماد المحضر',409)
        result='approved' if body.decision=='approve' else 'rejected'
        c.execute('''UPDATE supplier_opening_statements SET status=?,reviewed_by=?,reviewed_at=?,review_note=?
                     WHERE id=?''',(result,user['id'],stamp(),note,statement_id))
        audit(c,user['id'],'supplier_opening_'+result,'supplier_opening_statement',statement_id,
              {'vendor_id':doc['vendor_id'],'as_of':doc['as_of'],'no_gl_posting':True})
    return {'id':statement_id,'status':result,'money_moved':False}


@router.get('/supplier-control-ledger')
def supplier_control_ledger_report(as_of:str='',user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user,'read')
    day=business_day(as_of or cairo_today())
    return supplier_control_ledger(c,day)


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
           COALESCE((SELECT SUM(a.quantity) FROM inventory_issue_allocations a WHERE a.receipt_line_id=l.id),0)-
           COALESCE((SELECT SUM(rl.quantity) FROM inventory_return_lines rl
             JOIN inventory_issue_returns ret ON ret.id=rl.return_id AND ret.status='approved'
             JOIN inventory_return_inspections medical ON medical.return_line_id=rl.id
                 AND medical.decision='released' AND medical.inspected_on<=?
             JOIN inventory_issue_allocations a ON a.id=rl.issue_allocation_id
             WHERE a.receipt_line_id=l.id AND ret.returned_on<=?),0) used
           FROM inventory_receipt_lines l JOIN inventory_receipts r ON r.id=l.receipt_id
           WHERE l.item_id=? AND r.status='approved' AND r.received_on<=?
             AND (l.expiry_date IS NULL OR l.expiry_date>=?)
           ORDER BY r.received_on,l.id''',(issue['used_on'],issue['used_on'],line['item_id'],issue['used_on'],issue['used_on'])).fetchall()
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
        # Authorize the specific patient case before revealing its decision status.
        case=case_scope(c,user,i['case_id']) if i['case_id'] is not None else None
        if i['status']!='pending':fail('تم البت في إذن الصرف بالفعل',409)
        if i['created_by']==user['id']:fail('لا يجوز اعتماد إذن صرف أعددته بنفسك',403)
        month_open(c,i['used_on'][:7])
        if case is not None and case['status']!='open':
            fail('ملف الحالة أُغلق أثناء انتظار اعتماد الصرف',409)
        if body.decision=='approve':
            ensure_fifo_date_order(c,'issue',issue_id,i['used_on'])
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



@router.get('/issues/{issue_id}/returnable')
def issue_returnable(issue_id:int,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user)
    issue=c.execute('SELECT * FROM inventory_issues WHERE id=?',(issue_id,)).fetchone()
    if not issue:fail('إذن الصرف غير موجود',404)
    if issue['case_id'] is not None:case_scope(c,user,issue['case_id'])
    if issue['status']!='approved':fail('يمكن رد مستلزمات إذن صرف معتمد فقط',409)
    allocations=c.execute('''SELECT a.id issue_allocation_id,a.quantity quantity_issued,
       a.quantity-COALESCE((SELECT SUM(rl.quantity) FROM inventory_return_lines rl
           JOIN inventory_issue_returns ret ON ret.id=rl.return_id
           WHERE rl.issue_allocation_id=a.id AND ret.status IN ('pending','approved')),0) returnable_quantity,
       rl.item_id,it.code item_code,it.name item_name,rl.unit_cost_piasters,rl.expiry_date
       FROM inventory_issue_allocations a
       JOIN inventory_receipt_lines rl ON rl.id=a.receipt_line_id
       JOIN inventory_items it ON it.id=rl.item_id
       WHERE a.issue_id=? ORDER BY a.id''',(issue_id,)).fetchall()
    return {'issue_id':issue_id,'case_id':issue['case_id'],'used_on':issue['used_on'],
            'allocations':[dict(a) for a in allocations]}


def return_cost(c,return_id):
    return c.execute('''SELECT COALESCE(SUM(l.quantity*lot.unit_cost_piasters),0)
      FROM inventory_return_lines l
      JOIN inventory_issue_allocations a ON a.id=l.issue_allocation_id
      JOIN inventory_receipt_lines lot ON lot.id=a.receipt_line_id
      WHERE l.return_id=?''',(return_id,)).fetchone()[0]


def ensure_return_day(c,issue_id,day):
    """No retroactive return that would change valuation of later-day issues."""
    if c.execute('''SELECT 1 FROM inventory_issue_allocations a
          JOIN inventory_receipt_lines lot ON lot.id=a.receipt_line_id
          JOIN inventory_issue_lines later ON later.item_id=lot.item_id
          JOIN inventory_issues later_issue ON later_issue.id=later.issue_id
          WHERE a.issue_id=? AND later_issue.status='approved'
          AND later_issue.used_on>? LIMIT 1''',(issue_id,day)).fetchone():
        fail('مرتجع بأثر رجعي يغير ترتيب FIFO لصرف معتمد لاحق؛ يلزم تسوية منفصلة',409)


@router.post('/returns')
def prepare_return(body:ReturnForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user,'prepare')
    day=business_day(body.returned_on)
    evidence=trim(body.evidence_ref,'محضر الاسترجاع المادي',8,180)
    key=request_key(body.request_id)
    seen=set()
    lines=[]
    for line in body.lines:
        if line.issue_allocation_id in seen:fail('لا تكرر نفس دفعة الصرف في المرتجع',409)
        seen.add(line.issue_allocation_id)
        lines.append({'issue_allocation_id':line.issue_allocation_id,'quantity':line.quantity})
    payload={'issue_id':body.issue_id,'returned_on':day,'evidence_ref':evidence,'lines':lines}
    with c:
        c.execute('BEGIN IMMEDIATE')
        permission(c,user,'prepare')
        issue=c.execute('SELECT * FROM inventory_issues WHERE id=?',(body.issue_id,)).fetchone()
        if not issue:fail('إذن الصرف غير معتمد أو غير موجود',409)
        case=case_scope(c,user,issue['case_id']) if issue['case_id'] is not None else None
        if issue['status']!='approved':fail('إذن الصرف غير معتمد أو غير موجود',409)
        if issue['used_on']>day:fail('تاريخ الرد يسبق الصرف الأصلي',409)
        if case is not None and case['status']!='open':
            fail('ملف الحالة مغلق ويحتاج تسوية محاسبية منفصلة',409)
        # Idempotent replay must not outlive the user's current patient grant.
        prior,digest=repeat(c,key,'inventory_return',user['id'],payload)
        if prior:return {'id':prior,'replayed':True}
        month_open(c,day[:7])
        ensure_return_day(c,body.issue_id,day)
        current={r['id']:r for r in c.execute('''SELECT a.id,a.quantity,lot.expiry_date,
            COALESCE((SELECT SUM(rl.quantity) FROM inventory_return_lines rl
                JOIN inventory_issue_returns ret ON ret.id=rl.return_id
                WHERE rl.issue_allocation_id=a.id AND ret.status IN ('pending','approved')),0) already
            FROM inventory_issue_allocations a
            JOIN inventory_receipt_lines lot ON lot.id=a.receipt_line_id WHERE a.issue_id=?''',(body.issue_id,))}
        for line in lines:
            a=current.get(line['issue_allocation_id'])
            if not a or a['already']+line['quantity']>a['quantity']:
                fail('الكمية المرتجعة تجاوزت الوحدات المصروفة من الدفعة الأصلية',409)
            if a['expiry_date'] and a['expiry_date']<day:
                fail('لا يجوز إعادة مستلزمات منتهية الصلاحية للمخزون القابل للصرف',409)
        cur=c.execute('''INSERT INTO inventory_issue_returns
            (issue_id,returned_on,evidence_ref,created_by,created_at) VALUES(?,?,?,?,?)''',
            (body.issue_id,day,evidence,user['id'],stamp()))
        return_id=cur.lastrowid
        for line in lines:
            c.execute('''INSERT INTO inventory_return_lines(return_id,issue_allocation_id,quantity)
               VALUES(?,?,?)''',(return_id,line['issue_allocation_id'],line['quantity']))
        remember(c,key,'inventory_return',user['id'],digest,return_id)
        audit(c,user['id'],'inventory_return_requested','inventory_issue_return',return_id,
              {'issue_id':body.issue_id,'case_id':issue['case_id']})
    return {'id':return_id,'status':'pending'}


@router.post('/returns/{return_id}/decision')
def decide_return(return_id:int,body:ReviewForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user,'approve')
    note=trim(body.note,'مراجعة المرتجع',8,300)
    with c:
        c.execute('BEGIN IMMEDIATE')
        permission(c,user,'approve')
        ret=c.execute('''SELECT ret.*,i.department_id,i.case_id,i.used_on
            FROM inventory_issue_returns ret JOIN inventory_issues i ON i.id=ret.issue_id
            WHERE ret.id=?''',(return_id,)).fetchone()
        if not ret:fail('محضر المرتجع غير موجود',404)
        case=case_scope(c,user,ret['case_id']) if ret['case_id'] is not None else None
        if ret['status']!='pending':fail('تم البت في محضر المرتجع بالفعل',409)
        if ret['created_by']==user['id']:fail('لا يجوز اعتماد محضر مرتجع أعددته بنفسك',403)
        month_open(c,ret['returned_on'][:7])
        if case is not None and case['status']!='open':
            fail('ملف الحالة أُغلق أثناء انتظار اعتماد المرتجع',409)
        if body.decision=='approve':
            ensure_return_day(c,ret['issue_id'],ret['returned_on'])
            cost=return_cost(c,return_id)
            jid=ledger_post(c,ret['returned_on'],'RETURN',return_id,ret['created_by'],user['id'],
                            '1100','5100',cost,ret['department_id'])
            status='approved'
        else:
            cost=0
            jid=None
            status='rejected'
        c.execute('''UPDATE inventory_issue_returns SET status=?,reviewed_by=?,reviewed_at=?,
            review_note=?,cost_piasters=?,journal_id=? WHERE id=?''',
            (status,user['id'],stamp(),note,cost,jid,return_id))
        audit(c,user['id'],'inventory_return_'+status,'inventory_issue_return',return_id,
              {'journal_id':jid,'cost_piasters':cost,'issue_id':ret['issue_id']})
    return {'id':return_id,'status':status,'cost_piasters':cost,'journal_id':jid}


@router.get('/inspections/queue')
def pending_medical_inspections(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    """A department-scoped clinical worklist. Never disclose patient or financial data."""
    require(user,'clinician')
    if not c.execute('''SELECT 1 FROM billing_clinical_identity_reviews
                 WHERE user_id=? AND approved=1''',(user['id'],)).fetchone():
        fail('الحساب الطبي يحتاج مراجعة هوية مهنية سارية',403)
    if not c.execute('''SELECT 1 FROM billing_clinical_grants
                 WHERE user_id=? AND active=1''',(user['id'],)).fetchone():
        fail('لا توجد أقسام مفوضة للحساب الطبي',403)
    rows=c.execute('''SELECT rl.id return_line_id,ret.id return_id,ret.returned_on,
            i.department_id,d.name department_name,lot.batch_ref,lot.expiry_date,
            it.code item_code,it.name item_name,rl.quantity
        FROM inventory_return_lines rl
        JOIN inventory_issue_returns ret ON ret.id=rl.return_id AND ret.status='approved'
        JOIN inventory_issues i ON i.id=ret.issue_id
        JOIN billing_clinical_grants g ON g.department_id=i.department_id
             AND g.user_id=? AND g.active=1
        JOIN departments d ON d.id=i.department_id
        JOIN inventory_issue_allocations a ON a.id=rl.issue_allocation_id
        JOIN inventory_receipt_lines lot ON lot.id=a.receipt_line_id
        JOIN inventory_items it ON it.id=lot.item_id
        WHERE NOT EXISTS(SELECT 1 FROM inventory_return_inspections med WHERE med.return_line_id=rl.id)
        ORDER BY ret.returned_on,rl.id LIMIT 75''',(user['id'],)).fetchall()
    return {'items':[dict(x) for x in rows],
            'scope':'Clinical review of financially accepted returns. No patient IDs, costs, source documents or patient invoices.'}


@router.post('/inspections/{return_line_id}/decision')
def decide_return_inspection(return_line_id:int,body:ReturnInspectionForm,
                             user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'clinician')
    day=business_day(body.inspected_on)
    if day!=cairo_today():
        fail('الفحص الطبي لا يسجل بأثر رجعي؛ استخدم تاريخ اليوم الفعلي',409)
    evidence=trim(body.evidence_ref,'مرجع الفحص الطبي',8,180)
    note=trim(body.note,'ملاحظات الفحص الطبي',12,300)
    if body.decision=='release' and not (body.unused_confirmed and body.packaging_intact and body.infection_control_clearance):
        fail('لا يسمح بإعادة الصرف دون تأكيد عدم الاستخدام وسلامة العبوة وموافقة مكافحة العدوى',409)
    with c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('''SELECT rl.id,ret.id return_id,ret.status return_status,ret.returned_on,
                      i.department_id,lot.expiry_date,lot.id lot_id,lot.quantity lot_quantity
              FROM inventory_return_lines rl
              JOIN inventory_issue_returns ret ON ret.id=rl.return_id
              JOIN inventory_issues i ON i.id=ret.issue_id
              JOIN inventory_issue_allocations a ON a.id=rl.issue_allocation_id
              JOIN inventory_receipt_lines lot ON lot.id=a.receipt_line_id
              WHERE rl.id=?''',(return_line_id,)).fetchone()
        if not row:fail('محضر الفحص غير موجود',404)
        # Current clinical identity + department grant checked under the same
        # write lock as INSERT; revocation wins even with a live browser session.
        require_clinical_grant(c,user,row['department_id'])
        if row['return_status']!='approved':fail('المستلزمات لم تعتمد محاسبيًا بعد',409)
        if c.execute('SELECT 1 FROM inventory_return_inspections WHERE return_line_id=?',
                     (return_line_id,)).fetchone():
            fail('تم اتخاذ قرار طبي نهائي بالفعل؛ لا يمكن تعديل المحضر',409)
        if row['returned_on']>day:fail('تاريخ الفحص يسبق رد المستلزم',409)
        month_open(c,day[:7])
        if body.decision=='release':
            if row['expiry_date'] and row['expiry_date']<day:
                fail('المستلزم منتهي الصلاحية؛ لا يجوز إعادته للصرف',409)
            historical=c.execute('''SELECT
                (SELECT COALESCE(SUM(quantity),0) FROM inventory_issue_allocations
                 WHERE receipt_line_id=?) gross_allocated,
                (SELECT COALESCE(SUM(prior.quantity),0) FROM inventory_return_lines prior
                 JOIN inventory_issue_allocations allocation ON allocation.id=prior.issue_allocation_id
                 JOIN inventory_issue_returns ret ON ret.id=prior.return_id AND ret.status='approved'
                 JOIN inventory_return_inspections med ON med.return_line_id=prior.id
                    AND med.decision='released' AND med.inspected_on<=?
                 WHERE allocation.receipt_line_id=? AND ret.returned_on<=?) prior_released''',
                 (row['lot_id'],day,row['lot_id'],day)).fetchone()
            if historical['gross_allocated']>row['lot_quantity']+historical['prior_released']:
                fail('يوجد صرف تاريخي لمستلزمات مرتجعة قبل الفحص؛ يلزم جرد وتسوية مستقلة قبل الإفراج',409)
        status='released' if body.decision=='release' else 'rejected'
        c.execute('''INSERT INTO inventory_return_inspections
              (return_line_id,decision,inspected_on,evidence_ref,note,
               unused_confirmed,packaging_intact,infection_control_clearance,inspected_by,inspected_at)
              VALUES (?,?,?,?,?,?,?,?,?,?)''',
              (return_line_id,status,day,evidence,note,
               int(body.unused_confirmed),int(body.packaging_intact),int(body.infection_control_clearance),
               user['id'],stamp()))
        # Audit records only the source line and decision; reference notes stay
        # in the restricted clinical table rather than finance audit exports.
        audit(c,user['id'],'inventory_return_inspected','inventory_return_line',return_line_id,
              {'decision':status,'return_id':row['return_id'],'department_id':row['department_id']})
    return {'return_line_id':return_line_id,'status':status,
            'financial_return_unchanged':True,'clinical_pilot_only':True}



@router.get('/writeoffs/queue')
def rejected_return_writeoff_queue(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user)
    return {'items':writeoff_candidates(c),'documents':writeoff_documents(c),
            'scope':'Only rejected non-drug lots. No patient data or clinical inspection notes.'}


@router.post('/writeoffs')
def prepare_return_writeoff(body:WriteoffForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user,'prepare')
    key=request_key(body.request_id)
    day=business_day(body.disposed_on)
    evidence=trim(body.evidence_ref,'محضر التلف أو الإعدام',8,180)
    if not body.physical_disposal_confirmed:
        fail('لا يجوز تسجيل شطب مخزون دون تأكيد إزالة المستلزم فعليًا ومحضر إثبات',409)
    payload={'return_line_id':body.return_line_id,'quantity':body.quantity,
             'disposed_on':day,'reason':body.reason,'evidence_ref':evidence,
             'physical_disposal_confirmed':True}
    with c:
        c.execute('BEGIN IMMEDIATE')
        permission(c,user,'prepare')
        prior,digest=repeat(c,key,'inventory_writeoff',user['id'],payload)
        if prior:return {'id':prior,'replayed':True}
        month_open(c,day[:7])
        row=c.execute('''SELECT rl.quantity,ret.returned_on,med.inspected_on,med.decision,
             ret.status,lot.id lot_id,lot.quantity lot_quantity
             FROM inventory_return_lines rl
             JOIN inventory_issue_returns ret ON ret.id=rl.return_id
             LEFT JOIN inventory_return_inspections med ON med.return_line_id=rl.id
             JOIN inventory_issue_allocations alloc ON alloc.id=rl.issue_allocation_id
             JOIN inventory_receipt_lines lot ON lot.id=alloc.receipt_line_id
             WHERE rl.id=?''',(body.return_line_id,)).fetchone()
        if not row or row['status']!='approved' or row['decision']!='rejected':
            fail('لا توجد كمية مرتجعة مرفوضة طبيًا وقابلة للتسوية المالية',409)
        if day<max(row['returned_on'],row['inspected_on']):
            fail('لا يجوز إثبات تلف قبل رد أو رفض المستلزم طبيًا',409)
        already=c.execute('''SELECT COALESCE(SUM(quantity),0) FROM inventory_return_writeoffs
            WHERE return_line_id=? AND status IN ('pending','approved')''',(body.return_line_id,)).fetchone()[0]
        if already+body.quantity>row['quantity']:
            fail('كمية الشطب تتجاوز الرصيد المحجوز غير المسوى',409)
        cur=c.execute('''INSERT INTO inventory_return_writeoffs
           (return_line_id,quantity,disposed_on,reason,evidence_ref,physical_disposal_confirmed,
            created_by,created_at) VALUES(?,?,?,?,?,1,?,?)''',
           (body.return_line_id,body.quantity,day,body.reason,evidence,user['id'],stamp()))
        remember(c,key,'inventory_writeoff',user['id'],digest,cur.lastrowid)
        audit(c,user['id'],'inventory_writeoff_requested','inventory_return_writeoff',cur.lastrowid,
              {'return_line_id':body.return_line_id,'quantity':body.quantity,'reason':body.reason})
    return {'id':cur.lastrowid,'status':'pending'}


@router.post('/writeoffs/{writeoff_id}/decision')
def decide_return_writeoff(writeoff_id:int,body:ReviewForm,
                           user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    permission(c,user,'approve')
    note=trim(body.note,'مراجعة محضر التلف أو الإعدام',8,300)
    with c:
        c.execute('BEGIN IMMEDIATE')
        permission(c,user,'approve')
        row=c.execute('''SELECT w.*,ret.status return_status,ret.returned_on,
             med.decision medical_decision,med.inspected_on,
             lot.id lot_id,lot.quantity lot_quantity,lot.unit_cost_piasters,
             issue.department_id
          FROM inventory_return_writeoffs w
          JOIN inventory_return_lines rl ON rl.id=w.return_line_id
          JOIN inventory_issue_returns ret ON ret.id=rl.return_id
          JOIN inventory_issue_allocations a ON a.id=rl.issue_allocation_id
          JOIN inventory_issues issue ON issue.id=ret.issue_id
          JOIN inventory_receipt_lines lot ON lot.id=a.receipt_line_id
          LEFT JOIN inventory_return_inspections med ON med.return_line_id=rl.id
          WHERE w.id=?''',(writeoff_id,)).fetchone()
        if not row:fail('مستند تسوية التلف غير موجود',404)
        if row['status']!='pending':fail('تم البت في مستند التسوية بالفعل',409)
        if row['created_by']==user['id']:fail('لا يجوز اعتماد تسوية تلف أعددتها بنفسك',403)
        month_open(c,row['disposed_on'][:7])
        if row['return_status']!='approved' or row['medical_decision']!='rejected' or row['disposed_on']<row['inspected_on']:
            fail('مستند تسوية التلف ليس مرتبطًا برفض طبي معتمد',409)
        if body.decision=='approve':
            # Historical G3E may have reused uninspected returns. Such lots
            # need a human physical count, not a fictitious retroactive writeoff.
            historical=c.execute('''SELECT
              (SELECT COALESCE(SUM(quantity),0) FROM inventory_issue_allocations
               WHERE receipt_line_id=?) gross,
              (SELECT COALESCE(SUM(prior.quantity),0) FROM inventory_return_lines prior
               JOIN inventory_issue_allocations a ON a.id=prior.issue_allocation_id
               JOIN inventory_issue_returns ret ON ret.id=prior.return_id AND ret.status='approved'
               JOIN inventory_return_inspections med ON med.return_line_id=prior.id
                  AND med.decision='released' AND med.inspected_on<=?
               WHERE a.receipt_line_id=? AND ret.returned_on<=?) released''',
               (row['lot_id'],row['disposed_on'],row['lot_id'],row['disposed_on'])).fetchone()
            if historical['gross']>row['lot_quantity']+historical['released']:
                fail('دفعة قديمة أُعيد صرفها دون فحص؛ يلزم جرد فعلي وتصحيح مستقل قبل الشطب',409)
            cost=row['quantity']*row['unit_cost_piasters']
            jid=ledger_post(c,row['disposed_on'],'WRITE_OFF',writeoff_id,row['created_by'],user['id'],
                            '5195','1100',cost,row['department_id'])
            status='approved'
        else:
            cost=0;jid=None;status='rejected'
        c.execute('''UPDATE inventory_return_writeoffs SET status=?,reviewed_by=?,reviewed_at=?,
              review_note=?,cost_piasters=?,journal_id=? WHERE id=?''',
              (status,user['id'],stamp(),note,cost,jid,writeoff_id))
        audit(c,user['id'],'inventory_writeoff_'+status,'inventory_return_writeoff',writeoff_id,
              {'cost_piasters':cost,'journal_id':jid,'quantity':row['quantity']})
    return {'id':writeoff_id,'status':status,'cost_piasters':cost,'journal_id':jid}

@router.get('/cases/{case_id}/cost')
def case_consumables_cost(case_id:int,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    """Trace already-posted FIFO cost per authorized patient case; never infer profit."""
    permission(c,user)
    case=case_scope(c,user,case_id)  # Warehouse access alone must not reveal a patient case.
    rows=c.execute('''SELECT i.id issue_id,i.used_on,i.department_id,l.item_id,
             it.code item_code,it.name item_name,
             SUM(a.quantity)-COALESCE((SELECT SUM(rl.quantity) FROM inventory_return_lines rl
               JOIN inventory_issue_returns ret ON ret.id=rl.return_id AND ret.status='approved'
               JOIN inventory_issue_allocations allocation ON allocation.id=rl.issue_allocation_id
               WHERE allocation.issue_line_id=l.id),0) AS quantity,
             SUM(a.cost_piasters)-COALESCE((SELECT SUM(rl.quantity*lot.unit_cost_piasters) FROM inventory_return_lines rl
               JOIN inventory_issue_returns ret ON ret.id=rl.return_id AND ret.status='approved'
               JOIN inventory_issue_allocations allocation ON allocation.id=rl.issue_allocation_id
               JOIN inventory_receipt_lines lot ON lot.id=allocation.receipt_line_id
               WHERE allocation.issue_line_id=l.id),0) AS cost_piasters,
             SUM(a.quantity) gross_quantity,SUM(a.cost_piasters) gross_cost_piasters,
             COALESCE((SELECT SUM(rl.quantity) FROM inventory_return_lines rl
               JOIN inventory_issue_returns ret ON ret.id=rl.return_id AND ret.status='approved'
               JOIN inventory_issue_allocations allocation ON allocation.id=rl.issue_allocation_id
               WHERE allocation.issue_line_id=l.id),0) returned_quantity
        FROM inventory_issues i
        JOIN inventory_issue_lines l ON l.issue_id=i.id
        JOIN inventory_items it ON it.id=l.item_id
        JOIN inventory_issue_allocations a ON a.issue_line_id=l.id AND a.issue_id=i.id
        WHERE i.case_id=? AND i.status='approved'
        GROUP BY i.id,l.id ORDER BY i.used_on,i.id,l.id''',(case_id,)).fetchall()
    lines=[{**dict(row), 'net_quantity':row['quantity']} for row in rows]
    pending=c.execute("SELECT COUNT(*) FROM inventory_issues WHERE case_id=? AND status='pending'",
                      (case_id,)).fetchone()[0]
    return {'case_id':case_id,'case_no':case['case_no'],
            'total_cost_piasters':sum(x['cost_piasters'] for x in lines),
            'total_returned_piasters':sum(x['gross_cost_piasters']-x['cost_piasters'] for x in lines),
            'approved_issue_count':len({x['issue_id'] for x in lines}),
            'pending_issue_count':pending,'lines':lines,
            'source':'approved_fifo_consumables_only',
            'scope':'NET approved FIFO issues less physically approved original-lot returns. Excludes unlinked stock, drugs, doctor fees and opening inventory. No profit or patient invoice.'}



def reconciliation(c,period):
    """Source documents vs attached posted GL, no claim on historical uncounted stock."""
    period=valid_month(period)
    errors=[]
    receipts=c.execute("""SELECT r.id,r.journal_id,COALESCE(SUM(l.quantity*l.unit_cost_piasters),0) total
      FROM inventory_receipts r LEFT JOIN inventory_receipt_lines l ON l.receipt_id=r.id
      WHERE r.status='approved' AND substr(r.received_on,1,7)<=? GROUP BY r.id""",(period,)).fetchall()
    issues=c.execute('''SELECT id,journal_id,cost_piasters total FROM inventory_issues
       WHERE status='approved' AND substr(used_on,1,7)<=?''',(period,)).fetchall()
    returns=c.execute('''SELECT id,journal_id,cost_piasters total FROM inventory_issue_returns
       WHERE status='approved' AND substr(returned_on,1,7)<=?''',(period,)).fetchall()
    writeoffs=c.execute('''SELECT id,journal_id,cost_piasters total FROM inventory_return_writeoffs
       WHERE status='approved' AND substr(disposed_on,1,7)<=?''',(period,)).fetchall()
    expected_balance=sum(int(r['total']) for r in receipts)-sum(int(i['total']) for i in issues)+sum(int(r['total']) for r in returns)-sum(int(w['total']) for w in writeoffs)
    actual_balance=0
    for group,debit,credit in ((receipts,'1100','2200'),(issues,'5100','1100'),(returns,'1100','5100'),(writeoffs,'5195','1100')):
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
            'quarantined_quantity':sum(x['quarantined_quantity'] for x in items),
            'available_quantity':sum(x['available_quantity'] for x in items),
            'inventory_gl_piasters':actual_balance,'approved_receipts':len(receipts),'approved_issues':len(issues),
            'approved_returns':len(returns),'approved_writeoffs':len(writeoffs),
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
    if c.execute("SELECT 1 FROM inventory_issue_returns WHERE substr(returned_on,1,7)=? AND status='pending' LIMIT 1",(period,)).fetchone():
        return 'محاضر مرتجع مستلزمات تنتظر اعتماد مراجع مستقل'
    # Prevent orphaned outstanding PO reviews in a period which cannot be reopened.
    if c.execute("SELECT 1 FROM inventory_purchase_orders WHERE status='pending' AND substr(ordered_on,1,7)=? LIMIT 1",(period,)).fetchone():
        return 'أوامر شراء مستلزمات لم تراجع قبل إقفال الشهر'
    # Pilot-only PO-linked GRNs demand resolved supplier invoice evidence before sealing.
    if c.execute('''SELECT 1 FROM inventory_receipts r JOIN inventory_receipt_purchase_links l
        ON l.receipt_id=r.id WHERE r.status='approved' AND substr(r.received_on,1,7)=?
        AND NOT EXISTS(SELECT 1 FROM inventory_supplier_invoice_matches m
           WHERE m.receipt_id=r.id AND m.status='approved') LIMIT 1''',(period,)).fetchone():
        return 'استلام من أمر شراء معتمد دون مطابقة ثلاثية نهائية لفاتورة المورد'
    if c.execute("SELECT 1 FROM inventory_return_writeoffs WHERE substr(disposed_on,1,7)=? AND status='pending' LIMIT 1",(period,)).fetchone():
        return 'تسوية تلف أو إعدام مستلزمات تنتظر اعتماد مراجع مالي مستقل'
    if c.execute("SELECT 1 FROM inventory_supplier_payment_requests WHERE status='pending' AND substr(requested_on,1,7)=? LIMIT 1",(period,)).fetchone():
        return 'طلبات صرف موردين تمهيدية قيد المراجعة'
    if c.execute("SELECT 1 FROM inventory_supplier_due_schedules WHERE status='pending' AND substr(scheduled_on,1,7)=? LIMIT 1",(period,)).fetchone():
        return 'جداول استحقاقات الموردين تنتظر اعتماد مراجع مستقل'
    # Before period closure, compare all approved inventory documents up to the month.
    report=reconciliation(c,period)
    return 'مخزون المستلزمات لا يطابق قيوده ومستنداته؛ راجع تقرير المطابقة' if not report['matched'] else None
