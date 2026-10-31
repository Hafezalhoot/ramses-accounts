"""G2K: aggregated POS card settlements, signed by an independent reviewer.

Patient card receipts stay in a clearing wallet at full gross. At approval,
one atomic transaction posts NET to the bank and the acquiring fee to expense.
Never invent a bank statement or mark a bank match: existing bank signoff is
separate evidence of actual arrival. No production money without bank review.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import secrets
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import ledger
from app import (audit, authorize_bank_review, authorize_cashbook_fund,
                 accessible_bank_funds, bank_statement_access, fund_grant_rights,
                 book_movements, c_piasters, db, fail, get_user, month_open,
                 require, shift_for_posting, stamp, valid_date, valid_month)

router = APIRouter(prefix='/api/pos', tags=['POS settlement'])


class POSRequest(BaseModel):
    bank_fund_id: int = Field(ge=1)
    clearing_fund_id: int = Field(ge=1)
    settlement_date: str
    payment_part_ids: List[int] = Field(min_length=1, max_length=200)
    fee_amount: str
    settlement_ref: str = Field(min_length=6, max_length=100)
    evidence_note: str = Field(min_length=12, max_length=500)
    request_key: str = Field(min_length=16, max_length=96)


class POSDecision(BaseModel):
    decision: str
    note: str = Field(min_length=8, max_length=500)


def channel(c, fund_id):
    row = c.execute('''SELECT f.id,f.name FROM billing_payment_channels ch
        JOIN funds f ON f.id=ch.fund_id
        WHERE ch.method='card' AND ch.fund_id=? AND f.kind='wallet' AND f.active=1''', (fund_id,)).fetchone()
    if not row:
        fail('Select the active card-clearing wallet configured for patient card payments',409)
    return row


def bank(c, fund_id):
    row = c.execute("SELECT id,name FROM funds WHERE id=? AND kind='bank' AND active=1", (fund_id,)).fetchone()
    if not row:fail('Select an active bank account',409)
    return row


def selectable_parts(c, ids, fund_id, max_period=None):
    if not ids or len(set(ids))!=len(ids) or any(not isinstance(i,int) or isinstance(i,bool) or i<1 for i in ids):
        fail('Select different, valid card receipts',400)
    marks=','.join('?'*len(ids))
    rows=list(c.execute(f'''SELECT p.id,p.amount_piasters,p.fund_id,p.voucher_id,
        b.collection_no,b.business_date,v.status voucher_status,v.from_fund_id,
        v.kind,v.amount_piasters voucher_amount
        FROM billing_payment_parts p JOIN billing_collections b ON b.id=p.collection_id
        JOIN vouchers v ON v.id=p.voucher_id
        WHERE p.id IN ({marks}) AND p.method='card' ''',tuple(ids)))
    if len(rows)!=len(ids):fail('A card payment part no longer exists',409)
    for p in rows:
        if (p['fund_id']!=fund_id or p['voucher_status']!='approved'
            or p['from_fund_id']!=fund_id or p['kind']!='receipt'
            or p['amount_piasters']!=p['voucher_amount']
            or (max_period and p['business_date']>max_period)):
            fail('Card receipt is not eligible for this settlement',409)
    if c.execute(f'''SELECT 1 FROM pos_settlement_parts p
        WHERE p.active=1 AND p.payment_part_id IN ({marks}) LIMIT 1''',tuple(ids)).fetchone():
        fail('A selected card receipt is already in a pending or approved settlement',409)
    return rows


@router.get('/settlements')
def list_settlements(period:str,bank_fund_id:int=0,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    month=valid_month(period)
    banks=accessible_bank_funds(c,user)
    if bank_fund_id:bank_statement_access(c,user,bank_fund_id,'read')
    selected=bank_fund_id or (banks[0]['id'] if banks else 0)
    clear=c.execute('''SELECT ch.fund_id,f.name FROM billing_payment_channels ch
        JOIN funds f ON f.id=ch.fund_id WHERE ch.method='card' AND f.kind='wallet' AND f.active=1''').fetchone()
    fund_id=clear['fund_id'] if clear else None
    bank_rights=fund_grant_rights(c,user,selected) if selected else {'can_submit':False,'can_approve':False}
    wallet_rights=fund_grant_rights(c,user,fund_id) if fund_id else {'can_submit':False,'can_approve':False}
    rights={k:bank_rights[k] and wallet_rights[k] for k in ('can_submit','can_approve')}
    if user['role']!='owner' and (not selected or not any(wallet_rights.values())):
        # Bank-only reviewers must still access their bank reconciliation screen.
        # Never expose clearing-wallet receipts or POS settlement history to them.
        return {'period':month,'bank_fund_id':selected,'banks':banks,
                'bank_sealed':False,'period_closed':False,'clearing_fund_id':None,
                'clearing_name':None,'candidates':[],'candidate_limit_reached':False,
                'settlements':[],'permissions':{'can_submit':False,'can_approve':False},
                'note':('لا يوجد تفويض على أي حساب بنكي؛ اطلب من المالك تحديد الحساب.'
                        if not selected else 'تحتاج تسويات POS إلى تفويض مستقل على محفظة مقاصة البطاقات.')}
    candidates=[]
    if fund_id:
        candidates=[dict(r) for r in c.execute('''SELECT p.id,p.amount_piasters,b.collection_no,
             b.business_date, p.voucher_id FROM billing_payment_parts p
             JOIN billing_collections b ON b.id=p.collection_id
             JOIN vouchers v ON v.id=p.voucher_id
             WHERE p.method='card' AND p.fund_id=? AND v.status='approved'
               AND v.kind='receipt' AND v.from_fund_id=?
               AND v.amount_piasters=p.amount_piasters
               AND substr(b.business_date,1,7)<=?
               AND NOT EXISTS(SELECT 1 FROM pos_settlement_parts sp
                              WHERE sp.payment_part_id=p.id AND sp.active=1)
             ORDER BY b.business_date,p.id LIMIT 201''',(fund_id,fund_id,month))]
    q='''SELECT s.*,u.username maker,r.username reviewer
         FROM pos_settlements s JOIN users u ON u.id=s.created_by
         LEFT JOIN users r ON r.id=s.reviewed_by
         WHERE substr(s.settlement_date,1,7)=?'''
    args=[month]
    if selected:q+=' AND s.bank_fund_id=?';args.append(selected)
    q+=' ORDER BY s.id DESC LIMIT 100'
    bank_sealed=bool(selected and c.execute("SELECT 1 FROM bank_statement_batches WHERE fund_id=? AND period=? AND status='approved' LIMIT 1",(selected,month)).fetchone())
    period_closed=bool(c.execute('SELECT 1 FROM periods WHERE period=?',(month,)).fetchone())
    rows=[]
    for r in c.execute(q,args):
        data=dict(r)
        data.pop('request_hash',None);data.pop('request_key',None)
        data['part_ids']=[x[0] for x in c.execute('''SELECT payment_part_id FROM pos_settlement_parts
                            WHERE settlement_id=? ORDER BY id''',(r['id'],))]
        rows.append(data)
    return {'period':month,'bank_fund_id':selected,'banks':banks,
            'bank_sealed':bank_sealed,'period_closed':period_closed,
            'permissions':rights,
            'clearing_fund_id':fund_id,'clearing_name':clear['name'] if clear else None,
            'candidates':candidates[:200],'candidate_limit_reached':len(candidates)>200,
            'settlements':rows,'note':'تسوية POS لا تثبت وصول المال للبنك؛ يلزم كشف بنكي شهري معتمد بشكل مستقل.'}


@router.post('/settlements')
def create_settlement(body:POSRequest,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    date=valid_date(body.settlement_date).isoformat()
    ref=body.settlement_ref.strip().upper()
    note=body.evidence_note.strip()
    key=body.request_key.strip()
    if not re.fullmatch('[A-Za-z0-9_-]{16,96}',key):fail('Invalid idempotency key')
    if not 6<=len(ref)<=90 or not 12<=len(note)<=500:fail('Reference and acquiring statement evidence are required')
    if body.clearing_fund_id==body.bank_fund_id:fail('The bank and the clearing wallet must differ')
    fee=c_piasters(body.fee_amount,allow_zero=True)
    ids=body.payment_part_ids
    if len(set(ids))!=len(ids):fail('The same receipt cannot be added twice',409)
    payload={'clearing_fund_id':body.clearing_fund_id,'bank_fund_id':body.bank_fund_id,
             'date':date,'ids':sorted(ids),'fee_piasters':fee,'ref':ref,'note':note}
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    with c:
        c.execute('BEGIN IMMEDIATE')
        previous=c.execute('SELECT id,created_by,request_hash,status FROM pos_settlements WHERE request_key=?',(key,)).fetchone()
        if previous:
            if previous['created_by']!=user['id'] or previous['request_hash']!=digest:
                fail('Idempotency key belongs to a different settlement',409)
            return {'id':previous['id'],'status':previous['status'],'replayed':True}
        month_open(c,date[:7])
        if c.execute("SELECT 1 FROM bank_statement_batches WHERE fund_id=? AND period=? AND status='approved' LIMIT 1",
                     (body.bank_fund_id,date[:7])).fetchone():
            fail('Bank statement for this month is already approved; settlement must be completed before bank signoff',409)
        channel(c,body.clearing_fund_id);bank(c,body.bank_fund_id)
        for fid in (body.clearing_fund_id,body.bank_fund_id):authorize_cashbook_fund(c,user,fid)
        parts=selectable_parts(c,ids,body.clearing_fund_id,date)
        gross=sum(r['amount_piasters'] for r in parts)
        if gross>10**12 or fee>=gross:fail('Fee must be less than the positive total of the card receipts',409)
        if c.execute('''SELECT 1 FROM pos_settlements WHERE clearing_fund_id=? AND settlement_ref=?
               AND status IN ('pending','approved')''',(body.clearing_fund_id,ref)).fetchone():
            fail('This POS settlement reference is already recorded',409)
        cur=c.execute('''INSERT INTO pos_settlements(clearing_fund_id,bank_fund_id,settlement_date,
            settlement_ref,evidence_note,gross_piasters,fee_piasters,net_piasters,request_key,request_hash,
            created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
            (body.clearing_fund_id,body.bank_fund_id,date,ref,note,gross,fee,gross-fee,key,digest,user['id'],stamp()))
        for part in parts:
            c.execute('INSERT INTO pos_settlement_parts(settlement_id,payment_part_id,amount_piasters) VALUES (?,?,?)',
                (cur.lastrowid,part['id'],part['amount_piasters']))
        audit(c,user['id'],'pos_settlement_submit','pos_settlement',cur.lastrowid,
              {'gross_piasters':gross,'fee_piasters':fee,'bank_fund_id':body.bank_fund_id})
    return {'id':cur.lastrowid,'status':'pending','gross_piasters':gross,
            'fee_piasters':fee,'net_piasters':gross-fee}


def _post_settlement_voucher(c,settlement,reviewer,kind,amount,category_id=None,department_id=None):
    label='POS NET transfer' if kind=='transfer' else 'POS acquiring fee'
    cur=c.execute('''INSERT INTO vouchers(voucher_no,date,kind,department_id,category_id,
        from_fund_id,to_fund_id,shift,amount_piasters,description,reference_no,status,
        created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,'pending',?,?)''',
        ('POS-PENDING-'+secrets.token_hex(6),settlement['settlement_date'],kind,department_id,category_id,
         settlement['clearing_fund_id'],settlement['bank_fund_id'] if kind=='transfer' else None,
         'central',amount,f'{label} / #{settlement["id"]} / {settlement["settlement_ref"]}',
         settlement['settlement_ref'],settlement['created_by'],stamp()))
    vid=cur.lastrowid
    c.execute('UPDATE vouchers SET voucher_no=? WHERE id=?',(f'POS-{settlement["settlement_date"][:4]}-{vid:06d}',vid))
    v=c.execute('SELECT * FROM vouchers WHERE id=?',(vid,)).fetchone()
    book_movements(c,v)
    ledger.post_voucher(c,v,reviewer['id'])
    c.execute("UPDATE vouchers SET status='approved',reviewed_by=?,reviewed_at=?,review_reason=? WHERE id=?",
              (reviewer['id'],stamp(),f'Signed POS settlement #{settlement["id"]}',vid))
    return vid


@router.post('/settlements/{settlement_id}/decision')
def decide_settlement(settlement_id:int,body:POSDecision,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    if body.decision not in ('approve','reject'):fail('Decision must be approve or reject')
    if len(body.note.strip())<8:fail('Record your approval/rejection justification')
    with c:
        c.execute('BEGIN IMMEDIATE')
        s=c.execute('SELECT * FROM pos_settlements WHERE id=?',(settlement_id,)).fetchone()
        if not s:fail('POS settlement not found',404)
        if s['status']!='pending':fail('POS settlement has already been reviewed',409)
        if s['created_by']==user['id']:fail('The proposer cannot review their own POS settlement',403)
        for fid in (s['clearing_fund_id'],s['bank_fund_id']):
            authorize_bank_review(c,user,fid)
        if body.decision=='reject':
            c.execute('UPDATE pos_settlement_parts SET active=0 WHERE settlement_id=?',(settlement_id,))
            c.execute("UPDATE pos_settlements SET status='rejected',reviewed_by=?,reviewed_at=?,decision_note=? WHERE id=?",
                      (user['id'],stamp(),body.note.strip(),settlement_id))
            audit(c,user['id'],'pos_settlement_reject','pos_settlement',settlement_id,{'note':body.note.strip()})
            return {'id':settlement_id,'status':'rejected'}
        month_open(c,s['settlement_date'][:7]);bank(c,s['bank_fund_id']);channel(c,s['clearing_fund_id'])
        maker=c.execute('SELECT id,role,active FROM users WHERE id=?',(s['created_by'],)).fetchone()
        if not maker or not maker['active']:fail('The proposer is disabled',409)
        for fid in (s['clearing_fund_id'],s['bank_fund_id']):
            authorize_cashbook_fund(c,dict(maker),fid)
            authorize_bank_review(c,user,fid)
            shift_for_posting(c,fid,s['settlement_date'],'central')
        stored=list(c.execute('SELECT payment_part_id,amount_piasters,active FROM pos_settlement_parts WHERE settlement_id=?',(settlement_id,)))
        if not stored or any(not r['active'] for r in stored):fail('Settlement receipt lines have changed',409)
        marks=','.join('?'*len(stored))
        fresh=list(c.execute(f'''SELECT p.id,p.amount_piasters,p.fund_id,p.voucher_id,
          b.business_date,v.status,v.kind,v.from_fund_id,v.amount_piasters voucher_amount
          FROM billing_payment_parts p JOIN billing_collections b ON b.id=p.collection_id
          JOIN vouchers v ON v.id=p.voucher_id WHERE p.id IN ({marks}) AND p.method='card' ''',
          tuple(x['payment_part_id'] for x in stored)))
        if (len(fresh)!=len(stored) or sum(x['amount_piasters'] for x in fresh)!=s['gross_piasters']
            or sum(x['amount_piasters'] for x in stored)!=s['gross_piasters']):
            fail('The POS receipts no longer total the proposed gross',409)
        details={p['id']:p for p in fresh}
        for p in stored:
            x=details.get(p['payment_part_id'])
            if (not x or x['amount_piasters']!=p['amount_piasters'] or x['fund_id']!=s['clearing_fund_id']
                or x['from_fund_id']!=s['clearing_fund_id'] or x['kind']!='receipt'
                or x['status']!='approved' or x['voucher_amount']!=x['amount_piasters']
                or x['business_date']>s['settlement_date']):
                fail('The source receipt does not match the settlement request',409)
        if s['gross_piasters']-s['fee_piasters']!=s['net_piasters']:
            fail('POS net amount does not match gross minus acquiring fee',409)
        transfer=_post_settlement_voucher(c,s,user,'transfer',s['net_piasters'])
        fee_vid=None
        if s['fee_piasters']:
            cat=c.execute("SELECT id FROM categories WHERE code='pos_processing_fee' AND active=1",()).fetchone()
            dept=c.execute("SELECT id FROM departments WHERE code='ADMIN' AND active=1",()).fetchone()
            if not cat or not dept:fail('POS acquiring fee accounting category is missing',409)
            fee_vid=_post_settlement_voucher(c,s,user,'payment',s['fee_piasters'],cat['id'],dept['id'])
        c.execute('''UPDATE pos_settlements SET status='approved',reviewed_by=?,reviewed_at=?,
          decision_note=?,transfer_voucher_id=?,fee_voucher_id=? WHERE id=?''',
          (user['id'],stamp(),body.note.strip(),transfer,fee_vid,settlement_id))
        audit(c,user['id'],'pos_settlement_approve','pos_settlement',settlement_id,
              {'transfer_voucher_id':transfer,'fee_voucher_id':fee_vid,'gross_piasters':s['gross_piasters'],
               'fee_piasters':s['fee_piasters'],'net_piasters':s['net_piasters']})
    return {'id':settlement_id,'status':'approved','transfer_voucher_id':transfer,
            'fee_voucher_id':fee_vid,'gross_piasters':s['gross_piasters'],
            'fee_piasters':s['fee_piasters'],'net_piasters':s['net_piasters'],
            'bank_arrival_confirmed':False}
