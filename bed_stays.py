"""G2R physical bed occupancy and dated nightly service orders (development only).

Policy ceiling: a night is a calendar-date interval [start, end); same-day
admissions have no complete night. Medical discharge and real tariff/payer
policies must be signed off separately. No automatic invoice or GL posting.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app import audit, db, fail, get_user, month_open, require, stamp, valid_date
from billing import (can_point, case_scope, cairo_today, remember, repeat,
                     request_key, trim, CODE_PATTERN)

router=APIRouter(prefix='/api/beds',tags=['bed-stays'])


class BedForm(BaseModel):
    code:str=Field(min_length=3,max_length=36)
    name:str=Field(min_length=3,max_length=100)
    kind:Literal['inpatient','nicu']
    service_id:int


class AdmitForm(BaseModel):
    bed_id:int
    start_date:str
    evidence_reference:str=Field(min_length=8,max_length=180)
    request_id:str


class ReleaseForm(BaseModel):
    end_date:str
    evidence_reference:str=Field(min_length=8,max_length=180)


class ChargeForm(BaseModel):
    through_date:str
    request_id:str


def check_day(value, max_date=None):
    d=valid_date(value)
    if max_date and d>max_date:
        fail('لا يمكن إثبات إشغال أو ليلة مستقبلية',409)
    return d


def nights_preview(c,stay,through_date):
    """Produce unposted missing nights; fee comes from the rate valid THAT night."""
    start=date.fromisoformat(stay['start_date'])
    end=min(through_date,date.fromisoformat(stay['end_date'])) if stay['end_date'] else through_date
    if end<start:
        fail('تاريخ النهاية يسبق بداية الإقامة',409)
    if (end-start).days>366:
        fail('قسّم الحصر إلى فترات لا تتجاوز سنة واحدة',409)
    bed=c.execute('SELECT * FROM bed_catalog WHERE id=?',(stay['bed_id'],)).fetchone()
    recorded={r[0] for r in c.execute('SELECT night_date FROM bed_night_charges WHERE stay_id=?',(stay['id'],))}
    new=[]
    day=start
    while day<end:
        d=day.isoformat()
        if d not in recorded:
            tariff=c.execute('''SELECT * FROM billing_service_prices WHERE service_id=? AND valid_from<=?
                ORDER BY valid_from DESC LIMIT 1''',(bed['service_id'],d)).fetchone()
            new.append({'night_date':d,'price_version_id':tariff['id'] if tariff else None,
                        'amount_piasters':tariff['price_piasters'] if tariff else None})
        day+=timedelta(days=1)
    return new


def bed_case_data(c,case_id,through_date):
    stays=[dict(r) for r in c.execute('''SELECT s.*,b.name bed_name,b.code bed_code,
        b.kind bed_kind FROM bed_stays s JOIN bed_catalog b ON b.id=s.bed_id
        WHERE s.case_id=? ORDER BY s.start_date,s.id''',(case_id,))]
    previews=[]
    recorded=[]
    for stay in stays:
        plan=nights_preview(c,stay,through_date)
        previews.extend([{'stay_id':stay['id'],'bed_name':stay['bed_name'],**p} for p in plan])
        recorded.extend([dict(x) for x in c.execute('''SELECT n.*,l.state FROM bed_night_charges n
            JOIN billing_case_lines l ON l.id=n.case_line_id WHERE n.stay_id=? ORDER BY n.night_date''',(stay['id'],))])
    transfers=[dict(r) for r in c.execute('''SELECT t.*,b1.name from_bed_name,b2.name to_bed_name
        FROM bed_transfers t JOIN bed_stays s1 ON s1.id=t.from_stay_id
        JOIN bed_stays s2 ON s2.id=t.to_stay_id
        JOIN bed_catalog b1 ON b1.id=s1.bed_id JOIN bed_catalog b2 ON b2.id=s2.bed_id
        WHERE s1.case_id=? ORDER BY t.transfer_date,t.id''',(case_id,))]
    return {'transfers':transfers,'stays':stays,'active_stay':next((x for x in stays if x['end_date'] is None),None),
        'unbilled_preview':previews,'unbilled_nights':len(previews),
        'missing_rate_nights':sum(1 for p in previews if p['amount_piasters'] is None),
        'preview_total_piasters':sum(p['amount_piasters'] or 0 for p in previews),
        'night_charges':recorded,'through_date':through_date.isoformat(),
        'notice':'تقدير ليالٍ تقويمي للتجربة؛ لا ينشئ إيرادًا أو تحصيلًا أو إذن خروج طبي.'}


@router.get('/catalog')
def catalog(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    return {'items':[dict(r) for r in c.execute('''SELECT b.*,s.name service_name,
        (SELECT COUNT(*) FROM bed_stays t WHERE t.bed_id=b.id AND t.end_date IS NULL) occupied
        FROM bed_catalog b JOIN billing_services s ON s.id=b.service_id ORDER BY b.id''')]}


@router.post('/catalog')
def create_bed(body:BedForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    code=body.code.strip().upper()
    if not CODE_PATTERN.fullmatch(code):fail('كود السرير غير صالح')
    name=trim(body.name,'اسم السرير',3,100)
    with c:
        c.execute('BEGIN IMMEDIATE')
        srv=c.execute('''SELECT s.*,d.code department_code FROM billing_services s
            JOIN departments d ON d.id=s.department_id WHERE s.id=? AND s.active=1''',
            (body.service_id,)).fetchone()
        if not srv or srv['department_code'] not in ('IPD','NICU'):
            fail('اختر خدمة إقامة من قسم الداخلي أو الحضانة',409)
        if (body.kind=='nicu')!=(srv['department_code']=='NICU'):
            fail('قسم خدمة الإقامة لا يطابق نوع السرير',409)
        if c.execute('SELECT 1 FROM bed_catalog WHERE code=?',(code,)).fetchone():
            fail('كود السرير مستخدم بالفعل',409)
        cur=c.execute('''INSERT INTO bed_catalog(code,name,kind,service_id,created_by,created_at)
            VALUES(?,?,?,?,?,?)''',(code,name,body.kind,body.service_id,user['id'],stamp()))
        audit(c,user['id'],'bed_catalog_created','bed',cur.lastrowid,
              {'code':code,'kind':body.kind,'service_id':body.service_id})
    return {'id':cur.lastrowid,'code':code}


@router.get('/cases/{case_id}')
def case_beds(case_id:int,through_date:str|None=None,user=Depends(get_user),
              c:sqlite3.Connection=Depends(db)):
    require(user,'owner','clerk','reviewer')
    case=case_scope(c,user,case_id)
    until=check_day(through_date,date.fromisoformat(cairo_today())) if through_date else date.fromisoformat(cairo_today())
    return bed_case_data(c,case_id,until)


@router.post('/cases/{case_id}/admit')
def admit(case_id:int,body:AdmitForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    # Without a clinical occupancy role, only the owner may declare bed occupancy.
    require(user,'owner')
    key=request_key(body.request_id)
    day=check_day(body.start_date,date.fromisoformat(cairo_today())).isoformat()
    evidence=trim(body.evidence_reference,'مرجع إثبات الإشغال',8,180)
    payload={'case_id':case_id,'bed_id':body.bed_id,'start_date':day,'evidence':evidence}
    with c:
        c.execute('BEGIN IMMEDIATE')
        prior,digest=repeat(c,key,'bed_admission',user['id'],payload)
        if prior:return {'id':prior,'replayed':True}
        case=case_scope(c,user,case_id)
        if case['kind'] not in ('inpatient','nicu','operation') or case['status']!='open':
            fail('إشغال الأسرة للحالات الداخلية والحضانات والعمليات المفتوحة فقط',409)
        if day<case['business_date']:fail('لا يبدأ إشغال السرير قبل فتح الحالة',409)
        month_open(c,day[:7])
        bed=c.execute('SELECT * FROM bed_catalog WHERE id=?',(body.bed_id,)).fetchone()
        if not bed:fail('السرير غير موجود',404)
        if case['kind']=='nicu' and bed['kind']!='nicu':fail('الحضانة تتطلب سرير حضانة',409)
        if case['kind']!='nicu' and bed['kind']!='inpatient':fail('الداخلي والعمليات تتطلب سرير داخلي',409)
        # Conflict check also runs inside SQL triggers, including legacy mutation paths.
        if c.execute('''SELECT 1 FROM bed_stays WHERE (bed_id=? OR case_id=?) AND
            (end_date IS NULL OR end_date>?)''',(body.bed_id,case_id,day)).fetchone():
            fail('السرير أو الحالة لديه فترة إشغال متعارضة',409)
        cur=c.execute('''INSERT INTO bed_stays
            (bed_id,case_id,start_date,admission_evidence,recorded_by,recorded_at)
            VALUES (?,?,?,?,?,?)''',(body.bed_id,case_id,day,evidence,user['id'],stamp()))
        remember(c,key,'bed_admission',user['id'],digest,cur.lastrowid)
        audit(c,user['id'],'bed_admission','billing_case',case_id,
              {'bed_id':body.bed_id,'stay_id':cur.lastrowid,'start_date':day,'evidence_reference':evidence})
    return {'id':cur.lastrowid,'start_date':day}


@router.post('/stays/{stay_id}/release')
def release(stay_id:int,body:ReleaseForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    end=check_day(body.end_date,date.fromisoformat(cairo_today())).isoformat()
    evidence=trim(body.evidence_reference,'مرجع تحرير الإشغال',8,180)
    with c:
        c.execute('BEGIN IMMEDIATE')
        stay=c.execute('SELECT * FROM bed_stays WHERE id=?',(stay_id,)).fetchone()
        if not stay:fail('الإقامة غير موجودة',404)
        case=case_scope(c,user,stay['case_id'])
        if case['status']!='open' or stay['end_date'] is not None:fail('الإقامة محررة أو الحالة مغلقة',409)
        if end<stay['start_date']:fail('لا يمكن تحرير السرير قبل بداية الإقامة',409)
        month_open(c,end[:7])
        if c.execute('SELECT 1 FROM bed_night_charges WHERE stay_id=? AND night_date>=?',
                     (stay_id,end)).fetchone():
            fail('تاريخ التحرير يتعارض مع ليالٍ موثقة بالفعل',409)
        c.execute('''UPDATE bed_stays SET end_date=?,release_evidence=?,released_by=?,released_at=?
            WHERE id=? AND end_date IS NULL''',(end,evidence,user['id'],stamp(),stay_id))
        audit(c,user['id'],'bed_release','billing_case',stay['case_id'],
              {'stay_id':stay_id,'end_date':end,'evidence_reference':evidence})
    return {'id':stay_id,'end_date':end,'notice':'تحرير إشغال إداري لا يعتبر خروجًا طبيًا'}


@router.post('/stays/{stay_id}/charge')
def charge_nights(stay_id:int,body:ChargeForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    key=request_key(body.request_id)
    until=check_day(body.through_date,date.fromisoformat(cairo_today()))
    with c:
        c.execute('BEGIN IMMEDIATE')
        stay=c.execute('SELECT * FROM bed_stays WHERE id=?',(stay_id,)).fetchone()
        if not stay:fail('الإقامة غير موجودة',404)
        prior,digest=repeat(c,key,'bed_nights',user['id'],{'stay_id':stay_id,'through_date':until.isoformat()})
        if prior:return {'id':prior,'replayed':True}
        case=case_scope(c,user,stay['case_id'])
        if case['status']!='open':fail('الحالة مغلقة',409)
        items=nights_preview(c,stay,until)
        if not items:fail('لا توجد ليالٍ جديدة لإضافتها',409)
        if any(i['amount_piasters'] is None for i in items):fail('توجد ليالٍ بلا تعريفة سارية؛ سجل الأسعار أولًا',409)
        bed=c.execute('SELECT * FROM bed_catalog WHERE id=?',(stay['bed_id'],)).fetchone()
        total=0
        first=None
        for item in items:
            month_open(c,item['night_date'][:7])
            tariff=c.execute('SELECT * FROM billing_service_prices WHERE id=?',(item['price_version_id'],)).fetchone()
            line=c.execute('''INSERT INTO billing_case_lines
                (case_id,service_id,price_version_id,service_name_snapshot,department_id,
                 unit_price_piasters,quantity,added_by,added_at)
                SELECT ?,s.id,?,?,s.department_id,?,1,?,?
                FROM billing_services s WHERE s.id=?''',
                (stay['case_id'],tariff['id'],bed['name']+' - ليلة '+item['night_date'],
                 item['amount_piasters'],user['id'],stamp(),bed['service_id']))
            c.execute('''INSERT INTO bed_night_charges
                (stay_id,night_date,case_line_id,price_version_id,amount_piasters,ordered_by,ordered_at)
                VALUES (?,?,?,?,?,?,?)''',
                (stay_id,item['night_date'],line.lastrowid,tariff['id'],item['amount_piasters'],user['id'],stamp()))
            first=first or line.lastrowid
            total+=item['amount_piasters']
        remember(c,key,'bed_nights',user['id'],digest,first)
        audit(c,user['id'],'bed_nights_ordered','billing_case',stay['case_id'],
              {'stay_id':stay_id,'created_nights':len(items),'amount_piasters':total,
               'through_date':until.isoformat()})
    return {'id':first,'created_nights':len(items),'total_piasters':total,
            'state':'ordered','notice':'هذه خدمات مطلوبة، وليست فاتورة أو إيرادًا مُرحّلاً.'}

class TransferForm(BaseModel):
    to_bed_id:int
    transfer_date:str
    evidence_reference:str=Field(min_length=8,max_length=180)
    request_id:str


@router.post('/stays/{stay_id}/transfer')
def transfer_bed(stay_id:int,body:TransferForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    """Atomic dated bed handoff. The target owns the night of transfer.

    A transfer is not a medical discharge or an accounting voucher. Both bed
    records and the signed transfer event are saved in one transaction.
    """
    require(user,'owner')
    key=request_key(body.request_id)
    day=check_day(body.transfer_date,date.fromisoformat(cairo_today())).isoformat()
    evidence=trim(body.evidence_reference,'\u0645\u0631\u062c\u0639 \u0646\u0642\u0644 \u0627\u0644\u0633\u0631\u064a\u0631',8,180)
    payload={'from_stay_id':stay_id,'to_bed_id':body.to_bed_id,'transfer_date':day,'evidence':evidence}
    with c:
        c.execute('BEGIN IMMEDIATE')
        prior,digest=repeat(c,key,'bed_transfer',user['id'],payload)
        if prior:
            old=c.execute('SELECT * FROM bed_transfers WHERE id=?',(prior,)).fetchone()
            if not old:fail('\u0645\u0631\u062c\u0639 \u0627\u0644\u0646\u0642\u0644 \u0645\u0641\u0642\u0648\u062f',409)
            return {'id':prior,'from_stay_id':old['from_stay_id'],
                    'to_stay_id':old['to_stay_id'],'replayed':True}
        source=c.execute('SELECT * FROM bed_stays WHERE id=?',(stay_id,)).fetchone()
        if not source:fail('\u0627\u0644\u0625\u0642\u0627\u0645\u0629 \u063a\u064a\u0631 \u0645\u0648\u062c\u0648\u062f\u0629',404)
        case=case_scope(c,user,source['case_id'])
        if case['status']!='open' or source['end_date'] is not None:
            fail('\u0644\u0627 \u064a\u0645\u0643\u0646 \u0646\u0642\u0644 \u062d\u0627\u0644\u0629 \u0645\u063a\u0644\u0642\u0629 \u0623\u0648 \u0633\u0631\u064a\u0631 \u0645\u062d\u0631\u0631',409)
        if day<source['start_date']:
            fail('\u062a\u0627\u0631\u064a\u062e \u0627\u0644\u0646\u0642\u0644 \u064a\u0633\u0628\u0642 \u062f\u062e\u0648\u0644 \u0627\u0644\u0633\u0631\u064a\u0631',409)
        month_open(c,day[:7])
        if body.to_bed_id==source['bed_id']:
            fail('\u0627\u062e\u062a\u0631 \u0633\u0631\u064a\u0631\u064b\u0627 \u0622\u062e\u0631 \u0644\u0644\u0646\u0642\u0644',409)
        target=c.execute('SELECT * FROM bed_catalog WHERE id=?',(body.to_bed_id,)).fetchone()
        if not target:fail('\u0627\u0644\u0633\u0631\u064a\u0631 \u0627\u0644\u062c\u062f\u064a\u062f \u063a\u064a\u0631 \u0645\u0648\u062c\u0648\u062f',404)
        kind='nicu' if case['kind']=='nicu' else 'inpatient'
        if target['kind']!=kind:
            fail('\u0646\u0648\u0639 \u0627\u0644\u0633\u0631\u064a\u0631 \u0627\u0644\u062c\u062f\u064a\u062f \u0644\u0627 \u064a\u0637\u0627\u0628\u0642 \u0627\u0644\u062d\u0627\u0644\u0629',409)
        if c.execute('SELECT 1 FROM bed_night_charges WHERE stay_id=? AND night_date>=? LIMIT 1',
                     (stay_id,day)).fetchone():
            fail('\u0644\u064a\u0627\u0644\u064d \u0633\u0627\u0628\u0642\u0629 \u062a\u062a\u0639\u0627\u0631\u0636 \u0645\u0639 \u062a\u0627\u0631\u064a\u062e \u0627\u0644\u0646\u0642\u0644',409)
        if c.execute("SELECT 1 FROM bed_stays WHERE bed_id=? AND COALESCE(end_date,'9999-12-31')>? LIMIT 1",
                     (body.to_bed_id,day)).fetchone():
            fail('\u0627\u0644\u0633\u0631\u064a\u0631 \u0627\u0644\u062c\u062f\u064a\u062f \u0645\u0634\u063a\u0648\u0644 \u0641\u064a \u062a\u0627\u0631\u064a\u062e \u0627\u0644\u0646\u0642\u0644',409)
        when=stamp()
        c.execute('''UPDATE bed_stays SET end_date=?,release_evidence=?,released_by=?,released_at=?
            WHERE id=? AND end_date IS NULL''',(day,evidence,user['id'],when,stay_id))
        new=c.execute('''INSERT INTO bed_stays
            (bed_id,case_id,start_date,admission_evidence,recorded_by,recorded_at)
            VALUES(?,?,?,?,?,?)''',(body.to_bed_id,source['case_id'],day,evidence,user['id'],when))
        cur=c.execute('''INSERT INTO bed_transfers
            (from_stay_id,to_stay_id,transfer_date,evidence_reference,transferred_by,transferred_at)
            VALUES(?,?,?,?,?,?)''',(stay_id,new.lastrowid,day,evidence,user['id'],when))
        remember(c,key,'bed_transfer',user['id'],digest,cur.lastrowid)
        audit(c,user['id'],'bed_transfer','billing_case',source['case_id'],
              {'transfer_id':cur.lastrowid,'from_stay_id':stay_id,'to_stay_id':new.lastrowid,
               'transfer_date':day,'evidence_reference':evidence})
    return {'id':cur.lastrowid,'from_stay_id':stay_id,'to_stay_id':new.lastrowid,
            'notice':'\u0646\u0642\u0644 \u0625\u0634\u063a\u0627\u0644 \u0625\u062f\u0627\u0631\u064a\u060c \u0644\u064a\u0633 \u0625\u0630\u0646 \u062e\u0631\u0648\u062c \u0637\u0628\u064a'}


def month_close_bed_issue(c,period):
    """First unresolved night in PERIOD, never derived from case opening date."""
    start=date.fromisoformat(period+'-01')
    stop=(start.replace(day=28)+timedelta(days=4)).replace(day=1)
    first=start.isoformat()
    end=stop.isoformat()
    stays=c.execute('''SELECT id,case_id,start_date,end_date FROM bed_stays
        WHERE start_date<? AND COALESCE(end_date,'9999-12-31')>? ORDER BY id''',(end,first)).fetchall()
    for stay in stays:
        begun=max(start,date.fromisoformat(stay['start_date']))
        finished=min(stop,date.fromisoformat(stay['end_date'])) if stay['end_date'] else stop
        expected=max(0,(finished-begun).days)
        count=c.execute('''SELECT count(*) FROM bed_night_charges
            WHERE stay_id=? AND night_date>=? AND night_date<?''',(stay['id'],first,end)).fetchone()[0]
        if count!=expected:
            return {'kind':'missing_nights','stay_id':stay['id'],'case_id':stay['case_id'],
                    'missing':expected-count,'period':period}
    unbilled=c.execute('''SELECT n.stay_id,st.case_id,n.night_date FROM bed_night_charges n
        JOIN bed_stays st ON st.id=n.stay_id
        WHERE n.night_date>=? AND n.night_date<? AND NOT EXISTS (
           SELECT 1 FROM billing_invoice_draft_lines dl
           JOIN billing_invoices i ON i.draft_id=dl.draft_id
           JOIN gl_journals j ON j.id=i.journal_id
           WHERE dl.case_line_id=n.case_line_id AND i.issued_date<?
             AND j.status='posted' AND j.entry_date>=? AND j.entry_date<?
        ) ORDER BY n.night_date,n.id LIMIT 1''',(first,end,end,first,end)).fetchone()
    if unbilled:
        return {'kind':'not_invoiced','stay_id':unbilled['stay_id'],
                'case_id':unbilled['case_id'],'night_date':unbilled['night_date'],'period':period}
    return None
