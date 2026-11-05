"""V8.1C: financial cases, invoices, advances, credits, refunds and settlements.

Development-only until clinical signoff, fiscal rules and shift handoff are accepted.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo
import ledger
import shift_schedule

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

from app import (MAX_EVIDENCE_BYTES, audit, book_movements, c_piasters, checked_evidence, current_month, db, fail, get_user,
                 lookup, month_open, require, stamp, valid_date, valid_month,
                 verify_password)

router = APIRouter(prefix="/api/billing", tags=["billing"])

KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,96}$")
CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,36}$")
POINT_DEFAULTS = {'outpatient': 'external', 'inpatient': 'internal', 'operation': 'internal', 'nicu': 'internal'}


def trim(text: str, field: str, min_len=1, max_len=200) -> str:
    value=(text or '').strip()
    if not (min_len <= len(value) <= max_len) or any(ord(ch)<32 for ch in value):
        fail(field+': طول/نص غير صالح')
    return value


def request_key(value: str):
    if not KEY_PATTERN.fullmatch(value or ''):
        fail('رمز حفظ العملية غير صالح')
    return value


def repeat(c, key, action, actor, payload):
    fingerprint=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    row=c.execute('SELECT * FROM billing_request_keys WHERE request_id=?',(key,)).fetchone()
    if row:
        if row['created_by']!=actor or row['action']!=action or row['payload_hash']!=fingerprint:
            fail('رمز العملية مستخدم في طلب مختلف؛ أعد المحاولة من شاشة جديدة',409)
        return row['entity_id'],fingerprint
    return None,fingerprint


def remember(c,key,action,actor,fingerprint,entity_id):
    c.execute('''INSERT INTO billing_request_keys(request_id,action,entity_id,payload_hash,created_by,created_at)
                 VALUES (?,?,?,?,?,?)''',(key,action,entity_id,fingerprint,actor,stamp()))


def can_point(c,user,point_id,write=False):
    import cashier_ops
    if user['role']=='owner':
        pass
    elif user['role']=='reviewer':
        if write:fail('موظف المراجعة لا ينشئ عملية كاشير',403)
        # Reviewer patient-file access is granted per billing point, not by role.
        if not c.execute('''SELECT 1 FROM billing_point_access a JOIN users u ON u.id=a.user_id
              WHERE a.user_id=? AND a.point_id=? AND a.active=1 AND u.active=1''',
              (user['id'],point_id)).fetchone():
            fail('لا تملك تفويضًا للاطلاع على ملفات هذه النقطة',403)
    elif user['role']=='clerk':
        found=c.execute('''SELECT 1 FROM billing_point_access
            WHERE user_id=? AND point_id=? AND active=1''',(user['id'],point_id)).fetchone()
        if not found:fail('هذا المستخدم غير معين لنقطة التحصيل',403)
    else:fail('مطلوب تصريح دخول إلى نقطة التحصيل',403)
    if write and not cashier_ops.point_enabled(c,point_id,cairo_today()):
        fail('نقطة التحصيل متوقفة في تاريخ التشغيل الحالي',409)
    return True


def visible_points(c,user):
    import cashier_ops
    if user['role']=='owner':
        points=c.execute('SELECT * FROM billing_points ORDER BY id').fetchall()
    elif user['role'] in ('clerk','reviewer'):
        points=c.execute('''SELECT p.* FROM billing_points p JOIN billing_point_access a
           ON a.point_id=p.id WHERE a.user_id=? AND a.active=1 ORDER BY p.id''',(user['id'],)).fetchall()
    else:fail('ليست لك صلاحية رؤية الحالات المالية',403)
    # Keep historical patient cases of an inactive point visible to authorized staff.
    # All mutation paths still call can_point(write=True), which enforces the active schedule.
    return [{**dict(p), 'active':int(cashier_ops.point_enabled(c,p['id'],cairo_today()))} for p in points]


def case_scope(c,user,case_id,write=False):
    row=c.execute('''SELECT b.*,p.code patient_code,p.display_name patient_name,
          t.name point_name,t.kind point_kind
          FROM billing_cases b JOIN billing_patients p ON p.id=b.patient_id
          JOIN billing_points t ON t.id=b.default_point_id WHERE b.id=?''',(case_id,)).fetchone()
    if not row:fail('الحالة غير موجودة',404)
    can_point(c,user,row['default_point_id'],write)
    return row


class AssignPoint(BaseModel):
    user_id:int
    active:bool=True

class ServiceForm(BaseModel):
    code:str=Field(min_length=3,max_length=36)
    name:str=Field(min_length=3,max_length=120)
    department_id:int
    suggested_point:Literal['external','internal','either']='either'

class PriceForm(BaseModel):
    valid_from:str
    amount:str

class PatientForm(BaseModel):
    display_name:str=Field(min_length=3,max_length=120)
    request_id:str

class CaseForm(BaseModel):
    patient_id:int
    patient_code:str=''  # required when clerk opens a case for a patient created by someone else
    kind:Literal['outpatient','inpatient','operation','nicu']
    point_id:int
    business_date:str
    routing_reason:str=''
    request_id:str

class LineForm(BaseModel):
    service_id:int
    quantity:int=Field(ge=1,le=10000)
    request_id:str

class LineDecision(BaseModel):
    reason:str=''

class DraftForm(BaseModel):
    request_id:str


class ClinicalGrantForm(BaseModel):
    user_id:int
    department_id:int
    active:bool=True


class ClinicalEvidenceForm(BaseModel):
    evidence_reference:str=Field(min_length=8,max_length=180)


class ClinicalDocumentRequirementForm(BaseModel):
    current_password:str


class ClinicalIdentityReviewForm(BaseModel):
    user_id:int=Field(ge=1)
    professional_name:str=Field(min_length=3,max_length=120)
    registration_reference:str=Field(min_length=8,max_length=100)
    review_note:str=Field(min_length=12,max_length=400)
    approved:bool
    current_password:str


def clinical_required(c, department_id):
    return bool(c.execute('SELECT 1 FROM billing_clinical_policies WHERE department_id=?',
                          (department_id,)).fetchone())


def require_clinical_grant(c, user, department_id):
    # A financial owner/reviewer/cashier/viewer cannot self-certify a medical
    # service. Manual owner review is only an internal pilot permission record.
    if user['role']!='clinician' or not c.execute('''SELECT 1 FROM billing_clinical_grants g
        JOIN users u ON u.id=g.user_id WHERE g.department_id=? AND g.user_id=?
        AND g.active=1 AND u.active=1 AND u.role='clinician'
        AND EXISTS (SELECT 1 FROM billing_clinical_identity_reviews i
                    WHERE i.user_id=u.id AND i.approved=1) ''',
        (department_id,user['id'])).fetchone():
        fail('لا تملك تفويض إثبات طبي مستقل لهذا القسم',403)


def require_invoice_clinical_evidence(c, lines):
    # Always re-check at ISSUE, including drafts created before policy activation.
    for line in lines:
        if clinical_required(c,line['department_id']) and not c.execute(
                '''SELECT 1 FROM billing_clinical_attestations a
                   JOIN users u ON u.id=a.attested_by AND u.role='clinician'
                   WHERE a.case_line_id=? AND
                     (NOT EXISTS(SELECT 1 FROM billing_clinical_document_requirements d
                                  WHERE d.department_id=a.department_id)
                      OR a.document_sha256 IS NOT NULL)''',
                (line['case_line_id'] if 'case_line_id' in line.keys() else line['id'],)).fetchone():
            fail('خدمة في هذه الفاتورة تحتاج إثبات تنفيذ طبي مستقل قبل الإصدار',409)


@router.post('/clinical/identity-review')
def review_clinician_identity(body:ClinicalIdentityReviewForm,user=Depends(get_user),
                              c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    name=trim(body.professional_name,'الاسم المهني',3,120)
    reference=trim(body.registration_reference,'مرجع القيد المهني',8,100)
    note=trim(body.review_note,'مبرر المراجعة',12,400)
    with c:
        c.execute('BEGIN IMMEDIATE')
        owner=c.execute('SELECT password_hash FROM users WHERE id=?',(user['id'],)).fetchone()
        if not owner or not verify_password(body.current_password,owner['password_hash']):
            fail('يجب تأكيد كلمة مرور المالك قبل مراجعة هوية الحساب الطبي',403)
        staff=c.execute('SELECT id,role,active FROM users WHERE id=?',(body.user_id,)).fetchone()
        if not staff or not staff['active'] or staff['role']!='clinician':
            fail('المراجعة متاحة لحساب طبي نشط فقط',400)
        c.execute('''INSERT INTO billing_clinical_identity_reviews
            (user_id,professional_name,registration_reference,approved,reviewed_by,reviewed_at,review_note)
            VALUES (?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
            professional_name=excluded.professional_name,
            registration_reference=excluded.registration_reference,
            approved=excluded.approved,reviewed_by=excluded.reviewed_by,
            reviewed_at=excluded.reviewed_at,review_note=excluded.review_note''',
            (body.user_id,name,reference,int(body.approved),user['id'],stamp(),note))
        # Do not copy a medical registration reference or private review note
        # to general accounting/audit exports.
        audit(c,user['id'],'clinical_identity_review','user',body.user_id,
              {'approved':body.approved,'manual_review_only':True})
    return {'user_id':body.user_id,'approved':body.approved,'manual_review_only':True}


@router.get('/clinical/identities')
def clinician_identities(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    # Neither personal registration references nor notes leave this endpoint.
    return {'items':[dict(r) for r in c.execute('''SELECT u.id user_id,u.username,u.active,
        coalesce(i.approved,0) approved,i.reviewed_at
        FROM users u LEFT JOIN billing_clinical_identity_reviews i ON i.user_id=u.id
        WHERE u.role='clinician' ORDER BY u.username''')]}


@router.post('/clinical/grants')
def clinical_grant(body:ClinicalGrantForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    with c:
        c.execute('BEGIN IMMEDIATE')
        department=c.execute('SELECT id FROM departments WHERE id=? AND active=1',
                             (body.department_id,)).fetchone()
        staff=c.execute('SELECT id,role,active FROM users WHERE id=?',(body.user_id,)).fetchone()
        if not department:fail('القسم غير موجود أو غير نشط',404)
        if not staff or not staff['active'] or staff['role']!='clinician':
            fail('التفويض الطبي لا يقبل سوى حساب طبي نشط ومنفصل عن المالية',400)
        if body.active and not c.execute('''SELECT 1 FROM billing_clinical_identity_reviews
              WHERE user_id=? AND approved=1''',(staff['id'],)).fetchone():
            fail('يجب اعتماد مراجعة الهوية المهنية يدويًا قبل التفويض',409)
        c.execute('''INSERT INTO billing_clinical_grants(department_id,user_id,active,assigned_by,assigned_at)
          VALUES (?,?,?,?,?) ON CONFLICT(department_id,user_id) DO UPDATE SET
          active=excluded.active,assigned_by=excluded.assigned_by,assigned_at=excluded.assigned_at''',
          (department['id'],staff['id'],int(body.active),user['id'],stamp()))
        audit(c,user['id'],'clinical_grant','department',body.department_id,
              {'user_id':body.user_id,'active':body.active})
    return {'user_id':body.user_id,'department_id':body.department_id,'active':body.active}


@router.post('/clinical/departments/{department_id}/activate')
def activate_clinical_policy(department_id:int,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    with c:
        c.execute('BEGIN IMMEDIATE')
        if clinical_required(c,department_id):fail('القسم مفعل بالفعل ولا يمكن التراجع صامتًا',409)
        if not c.execute('SELECT 1 FROM departments WHERE id=? AND active=1',(department_id,)).fetchone():
            fail('القسم غير موجود أو غير نشط',404)
        if not c.execute('''SELECT 1 FROM billing_clinical_grants g JOIN users u ON u.id=g.user_id
          WHERE g.department_id=? AND g.active=1 AND u.active=1 AND u.role='clinician'
            AND EXISTS (SELECT 1 FROM billing_clinical_identity_reviews i
                        WHERE i.user_id=u.id AND i.approved=1) ''',
          (department_id,)).fetchone():
            fail('لا يمكن تفعيل الإثبات الطبي قبل تحديد مُثبت مستقل ومفوض لهذا القسم',409)
        c.execute('INSERT INTO billing_clinical_policies(department_id,activated_by,activated_at) VALUES (?,?,?)',
                  (department_id,user['id'],stamp()))
        audit(c,user['id'],'clinical_policy_activated','department',department_id)
    return {'department_id':department_id,'enforced':True}


@router.post('/clinical/departments/{department_id}/require-document')
def require_source_document(department_id:int,body:ClinicalDocumentRequirementForm,
                            user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    with c:
        c.execute('BEGIN IMMEDIATE')
        owner=c.execute('SELECT password_hash FROM users WHERE id=?',(user['id'],)).fetchone()
        if not owner or not verify_password(body.current_password,owner['password_hash']):
            fail('يجب تأكيد كلمة مرور المالك قبل إلزام المستند الأصلي',403)
        if not clinical_required(c,department_id):
            fail('فعّل أولًا شرط الإثبات الطبي المستقل لهذا القسم',409)
        if c.execute('SELECT 1 FROM billing_clinical_document_requirements WHERE department_id=?',
                     (department_id,)).fetchone():
            fail('بصمة المستند إلزامية بالفعل ولا يمكن إلغاؤها صامتًا',409)
        # A new source rule cannot strand existing unbilled G3A witness rows
        # whose immutable, reference-only statements cannot be edited.
        if c.execute('''SELECT 1 FROM billing_clinical_attestations a
            WHERE a.department_id=? AND a.document_sha256 IS NULL
            AND NOT EXISTS (SELECT 1 FROM billing_invoice_draft_lines dl
                            JOIN billing_invoices i ON i.draft_id=dl.draft_id
                            WHERE dl.case_line_id=a.case_line_id) LIMIT 1''',
                     (department_id,)).fetchone():
            fail('توجد خدمات موثقة سابقًا ولم تفوتر؛ يلزم تسوية معتمدة قبل تشديد السياسة',409)
        c.execute('''INSERT INTO billing_clinical_document_requirements
             (department_id,activated_by,activated_at) VALUES (?,?,?)''',
             (department_id,user['id'],stamp()))
        audit(c,user['id'],'clinical_document_requirement_activated','department',department_id)
    return {'department_id':department_id,'document_required':True}


@router.get('/clinical/policy')
def clinical_policy(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    return {'departments':[dict(x) for x in c.execute(
        'SELECT department_id,activated_by,activated_at FROM billing_clinical_policies ORDER BY department_id')],
        'document_requirements':[dict(x) for x in c.execute(
        'SELECT department_id,activated_by,activated_at FROM billing_clinical_document_requirements ORDER BY department_id')]}


@router.get('/clinical/queue')
def clinical_queue(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'clinician')
    if not c.execute('''SELECT 1 FROM billing_clinical_identity_reviews
         WHERE user_id=? AND approved=1''',(user['id'],)).fetchone():
        fail('الحساب الطبي يحتاج مراجعة هوية مهنية يدوية سارية',403)
    # No prices, payer identity, clinical history or unrestricted patient lists.
    rows=c.execute('''SELECT l.id line_id,l.department_id,l.service_name_snapshot service_name,
        l.quantity,l.state,l.service_date,b.case_no,p.code patient_code,
        CASE WHEN dr.department_id IS NULL THEN 0 ELSE 1 END document_required
        FROM billing_case_lines l
        JOIN billing_cases b ON b.id=l.case_id
        JOIN billing_patients p ON p.id=b.patient_id
        JOIN billing_clinical_policies policy ON policy.department_id=l.department_id
        LEFT JOIN billing_clinical_document_requirements dr ON dr.department_id=l.department_id
        JOIN billing_clinical_grants g ON g.department_id=l.department_id
          AND g.user_id=? AND g.active=1
        WHERE b.status='open' AND l.state IN ('ordered','fulfilled')
          AND NOT EXISTS(SELECT 1 FROM billing_clinical_attestations a WHERE a.case_line_id=l.id)
        ORDER BY l.id LIMIT 100''',(user['id'],)).fetchall()
    return {'items':[dict(r) for r in rows], 'notice':'TEST ONLY — Evidence reference is not a licensed clinical signature'}


@router.get('/clinical/lines/{line_id}/evidence')
def clinical_evidence(line_id:int,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    line=c.execute('''SELECT a.*,l.case_id,l.department_id FROM billing_clinical_attestations a
        JOIN billing_case_lines l ON l.id=a.case_line_id WHERE a.case_line_id=?''',(line_id,)).fetchone()
    if not line:fail('لا يوجد إثبات طبي مسجل لهذا البند',404)
    if user['role']=='clinician':require_clinical_grant(c,user,line['department_id'])
    else:
        require(user,'owner','reviewer')
        case_scope(c,user,line['case_id'])
    return {k:line[k] for k in ('case_line_id','department_id','service_date','evidence_reference',
                              'attested_by','attested_at','document_sha256','document_size','document_media_type')}


def complete_line(c,line,actor):
    """Single dated fulfillment path: identical for financial legacy and medical witness."""
    night=c.execute('SELECT night_date FROM bed_night_charges WHERE case_line_id=?',(line['id'],)).fetchone()
    late=c.execute('SELECT original_business_date FROM billing_late_cases WHERE case_id=?',
                   (line['case_id'],)).fetchone()
    service_day=(night['night_date'] if night else
                 (late['original_business_date'] if late else cairo_today()))
    month_open(c,(cairo_today() if late else service_day)[:7])
    agreed=c.execute('SELECT 1 FROM pricing_line_terms WHERE case_line_id=?',(line['id'],)).fetchone()
    if agreed:
        c.execute("UPDATE billing_case_lines SET state='fulfilled',service_date=?,fulfilled_by=?,fulfilled_at=? WHERE id=?",
                  (service_day,actor,stamp(),line['id']))
    elif night:
        c.execute("UPDATE billing_case_lines SET state='fulfilled',service_date=?,fulfilled_by=?,fulfilled_at=? WHERE id=?",
                  (service_day,actor,stamp(),line['id']))
    else:
        price=c.execute('''SELECT * FROM billing_service_prices WHERE service_id=? AND valid_from<=?
               ORDER BY valid_from DESC LIMIT 1''',(line['service_id'],service_day)).fetchone()
        if not price:fail('لا توجد تعريفة معتمدة بتاريخ تنفيذ الخدمة',409)
        c.execute('''UPDATE billing_case_lines SET state='fulfilled',service_date=?,price_version_id=?,
             unit_price_piasters=?,fulfilled_by=?,fulfilled_at=? WHERE id=?''',
             (service_day,price['id'],price['price_piasters'],actor,stamp(),line['id']))
    return service_day


def _read_clinical_source(file:UploadFile):
    # Medical *content* is deliberately discarded after local hashing; the
    # original source stays in the authorized clinical record system.
    name=Path((file.filename or '').replace('\\','/')).name.strip()
    if not name or len(name)>100 or any(ord(ch)<32 for ch in name):
        fail('اسم ملف المصدر الطبي غير صالح')
    contents=file.file.read(MAX_EVIDENCE_BYTES+1)
    file.file.close()
    if not contents or len(contents)>MAX_EVIDENCE_BYTES:
        fail('مستند فارغ أو أكبر من 6 ميجابايت',413)
    media=checked_evidence(name,contents)
    return (hashlib.sha256(contents).hexdigest(),len(contents),media)


def _record_clinical_line(c,line_id,evidence,user,source=None):
    with c:
        c.execute('BEGIN IMMEDIATE')
        line=c.execute('SELECT * FROM billing_case_lines WHERE id=?',(line_id,)).fetchone()
        if not line:fail('بند الخدمة غير موجود',404)
        require_clinical_grant(c,user,line['department_id'])
        if not clinical_required(c,line['department_id']):
            fail('يجب تفعيل سياسة الإثبات الطبي لهذا القسم قبل التوثيق',409)
        if source is None and c.execute(
                'SELECT 1 FROM billing_clinical_document_requirements WHERE department_id=?',
                (line['department_id'],)).fetchone():
            fail('هذا القسم يلزم بصمة ملف المصدر الطبي قبل توثيق الخدمة',409)
        case=c.execute('SELECT id,status FROM billing_cases WHERE id=?',(line['case_id'],)).fetchone()
        if not case or case['status']!='open' or line['state']=='cancelled':
            fail('لا يمكن إثبات خدمة لحالة مغلقة أو بند ملغى',409)
        if c.execute('SELECT 1 FROM billing_clinical_attestations WHERE case_line_id=?',
                     (line_id,)).fetchone():fail('هذه الخدمة موثقة طبيًا بالفعل',409)
        if c.execute('''SELECT 1 FROM billing_invoice_draft_lines dl JOIN billing_invoices i
            ON i.draft_id=dl.draft_id WHERE dl.case_line_id=?''',(line_id,)).fetchone():
            fail('لا يمكن إضافة إثبات طبي بأثر رجعي لفاتورة صادرة',409)
        day=(complete_line(c,line,user['id']) if line['state']=='ordered' else line['service_date'])
        if not day:fail('تاريخ تنفيذ الخدمة التاريخية غير مثبت؛ لا يمكن اعتمادها',409)
        fingerprint=source or (None,None,None)
        c.execute('''INSERT INTO billing_clinical_attestations(case_line_id,department_id,service_date,
             evidence_reference,attested_by,attested_at,document_sha256,document_size,document_media_type)
             VALUES (?,?,?,?,?,?,?,?,?)''',
             (line_id,line['department_id'],day,evidence,user['id'],stamp(),*fingerprint))
        audit(c,user['id'],'clinical_service_attested','billing_case_line',line_id,
              {'case_id':line['case_id'],'department_id':line['department_id'],
               'service_date':day,'source_fingerprint_recorded':source is not None})
    return {'line_id':line_id,'state':'fulfilled','attested_by':user['id'],
            'service_date':day,'evidence_reference':evidence,
            'document_sha256':fingerprint[0],'document_size':fingerprint[1],
            'document_media_type':fingerprint[2]}


@router.post('/clinical/lines/{line_id}/attest')
def attest_clinical_line(line_id:int,body:ClinicalEvidenceForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    evidence=trim(body.evidence_reference,'مرجع الإثبات الطبي',8,180)
    return _record_clinical_line(c,line_id,evidence,user)


@router.post('/clinical/lines/{line_id}/attest-document')
def attest_clinical_document(line_id:int,evidence_reference:str=Form(...),
                             file:UploadFile=File(...),user=Depends(get_user),
                             c:sqlite3.Connection=Depends(db)):
    require(user,'clinician')
    evidence=trim(evidence_reference,'مرجع الإثبات الطبي',8,180)
    return _record_clinical_line(c,line_id,evidence,user,_read_clinical_source(file))


@router.post('/clinical/lines/{line_id}/verify-document')
def verify_clinical_document(line_id:int,file:UploadFile=File(...),
                             user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'clinician')
    proof=c.execute('''SELECT a.document_sha256,a.department_id
        FROM billing_clinical_attestations a WHERE a.case_line_id=?''',(line_id,)).fetchone()
    if not proof:fail('لا يوجد إثبات طبي لهذه الخدمة',404)
    require_clinical_grant(c,user,proof['department_id'])
    if not proof['document_sha256']:
        fail('الإثبات التاريخي لا يحتوي بصمة مصدر موثقة',409)
    return {'matches':secrets.compare_digest(_read_clinical_source(file)[0],proof['document_sha256'])}


@router.get('/config')
def config(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    points=visible_points(c,user)
    for p in points:
        sh=c.execute("SELECT id,shift,business_date,status,responsible_id FROM shift_sessions "
            "WHERE fund_id=? AND status='open' LIMIT 1",(p['fund_id'],)).fetchone() if p['fund_id'] else None
        p['active_shift']=dict(sh) if sh else None
        p['own_open_shift']=bool(sh and sh['responsible_id']==user['id'])
    services=[dict(r) for r in c.execute('''SELECT s.id,s.code,s.name,s.department_id,s.suggested_point,
       EXISTS(SELECT 1 FROM pricing_rate_versions pr WHERE pr.service_id=s.id) managed_pricing,
       d.name department_name, (SELECT p.price_piasters FROM billing_service_prices p
       WHERE p.service_id=s.id AND p.valid_from<=? ORDER BY p.valid_from DESC LIMIT 1) current_price_piasters
       FROM billing_services s JOIN departments d ON d.id=s.department_id WHERE s.active=1 ORDER BY s.id''',
       (cairo_today(),))]
    channels=[dict(r) for r in c.execute('''SELECT ch.method,ch.fund_id,f.name fund_name
              FROM billing_payment_channels ch JOIN funds f ON f.id=ch.fund_id ORDER BY ch.method''')]
    if user['role']!='owner':
        # Cashiers need the payment-method label, not the clearing wallet ID/name.
        channels=[{'method':r['method']} for r in channels]
    return {'points':points,'services':services,'mode':'BILLING_SANDBOX',
            'shift_schedule':shift_schedule.templates(c),'suggested_shift':shift_schedule.current_window(c),
            'payment_channels':channels,
            'notice':'V8.1C: الفواتير والتحصيل محاسبيًا للتجربة فقط، دون بيانات مرضى أو نقدية حقيقية.'}


@router.post('/points/{point_id}/assign')
def assign_point(point_id:int,body:AssignPoint,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    with c:
        c.execute('BEGIN IMMEDIATE')
        point=lookup(c,'billing_points',point_id)
        staff=c.execute('SELECT id,role,active FROM users WHERE id=?',(body.user_id,)).fetchone()
        if not staff or staff['role'] not in ('clerk','reviewer') or not staff['active']:
            fail('عيّن كاشيرًا أو مراجعًا نشطًا لإدارة صلاحية هذه النقطة',400)
        c.execute('''INSERT INTO billing_point_access(point_id,user_id,assigned_by,assigned_at,active)
           VALUES (?,?,?,?,?) ON CONFLICT(point_id,user_id) DO UPDATE SET
           assigned_by=excluded.assigned_by,assigned_at=excluded.assigned_at,active=excluded.active''',
           (point['id'],staff['id'],user['id'],stamp(),int(body.active)))
        audit(c,user['id'],'billing_point_access','billing_point',point_id,
              {'user_id':staff['id'],'active':body.active})
    return {'point_id':point_id,'user_id':body.user_id,'active':body.active}


@router.post('/services')
def create_service(body:ServiceForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    code=body.code.strip().upper()
    if not CODE_PATTERN.fullmatch(code):fail('رمز الخدمة غير صالح')
    name=trim(body.name,'اسم الخدمة',3,120)
    with c:
        c.execute('BEGIN IMMEDIATE')
        lookup(c,'departments',body.department_id)
        try:
            cur=c.execute('''INSERT INTO billing_services(code,name,department_id,suggested_point,created_by,created_at)
                             VALUES (?,?,?,?,?,?)''',
                (code,name,body.department_id,body.suggested_point,user['id'],stamp()))
        except sqlite3.IntegrityError:fail('رمز الخدمة مسجل بالفعل',409)
        audit(c,user['id'],'billing_create_service','billing_service',cur.lastrowid,{'code':code})
    return {'id':cur.lastrowid,'code':code}


@router.post('/services/{service_id}/prices')
def create_price(service_id:int,body:PriceForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    day=valid_date(body.valid_from).isoformat()
    cents=c_piasters(body.amount)
    with c:
        c.execute('BEGIN IMMEDIATE')
        lookup(c,'billing_services',service_id)
        # Price history is append-only, past prices are never rewritten.
        try:
            cur=c.execute('''INSERT INTO billing_service_prices(service_id,valid_from,price_piasters,created_by,created_at)
                             VALUES (?,?,?,?,?)''',(service_id,day,cents,user['id'],stamp()))
        except sqlite3.IntegrityError:fail('تم تسجيل سعر لهذه الخدمة بتاريخ السريان نفسه',409)
        audit(c,user['id'],'billing_new_price','billing_service',service_id,
              {'price_version_id':cur.lastrowid,'valid_from':day,'price_piasters':cents})
    return {'id':cur.lastrowid,'valid_from':day,'price_piasters':cents}


@router.post('/patients')
def create_patient(body:PatientForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','clerk')
    if user['role']=='clerk' and not visible_points(c,user):fail('لا توجد نقطة تحصيل معينة لحسابك',403)
    name=trim(body.display_name,'اسم المريض للفوترة',3,120)
    key=request_key(body.request_id)
    payload={'name':name}
    with c:
        c.execute('BEGIN IMMEDIATE')
        previous,fingerprint=repeat(c,key,'patient',user['id'],payload)
        if previous:return {'id':previous,'replayed':True}
        cur=c.execute('''INSERT INTO billing_patients(code,display_name,created_by,created_at)
                         VALUES (?,?,?,?)''',
                      ('PT-'+secrets.token_hex(6).upper(),name,user['id'],stamp()))
        remember(c,key,'patient',user['id'],fingerprint,cur.lastrowid)
        audit(c,user['id'],'billing_new_patient','billing_patient',cur.lastrowid)
    return {'id':cur.lastrowid,'code':c.execute('SELECT code FROM billing_patients WHERE id=?',(cur.lastrowid,)).fetchone()[0]}


@router.get('/patients')
def patients(q:str='',user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    q=q.strip()
    if len(q)<3: return {'items':[]}
    if user['role']=='clerk':
        # Clerk sees a minimal exact-code match; no broad name-based patient search.
        if not re.fullmatch(r'PT-[A-F0-9]{12}',q.upper()):return {'items':[]}
        rows=c.execute('SELECT id,code,display_name FROM billing_patients WHERE code=?',(q.upper(),))
    elif user['role']=='reviewer':
        rows=c.execute('''SELECT p.id,p.code,p.display_name FROM billing_patients p
            WHERE (p.code=? OR p.display_name LIKE ?) AND EXISTS (
                SELECT 1 FROM billing_cases b JOIN billing_point_access a
                  ON a.point_id=b.default_point_id
                WHERE b.patient_id=p.id AND a.user_id=? AND a.active=1)
            ORDER BY p.id DESC LIMIT 30''',(q.upper(),'%'+q[:60]+'%',user['id']))
    else:
        rows=c.execute('''SELECT id,code,display_name FROM billing_patients
                     WHERE code=? OR display_name LIKE ? ORDER BY id DESC LIMIT 30''',
                     (q.upper(),'%'+q[:60]+'%'))
    return {'items':[dict(x) for x in rows]}


@router.post('/cases')
def create_case(body:CaseForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','clerk')
    day=valid_date(body.business_date).isoformat()
    key=request_key(body.request_id)
    reason=body.routing_reason.strip()
    if len(reason)>300:fail('سبب الاستثناء طويل')
    payload={'patient_id':body.patient_id,'patient_code':body.patient_code.strip().upper(),'kind':body.kind,'point_id':body.point_id,
             'day':day,'reason':reason}
    with c:
        c.execute('BEGIN IMMEDIATE')
        previous,fingerprint=repeat(c,key,'case',user['id'],payload)
        if previous:return {'id':previous,'replayed':True}
        month_open(c,day[:7])
        point=lookup(c,'billing_points',body.point_id)
        can_point(c,user,point['id'],write=True)
        if point['kind'] != POINT_DEFAULTS[body.kind] and (user['role']!='owner' or len(reason)<10):
            fail('تغيير نقطة التحصيل الافتراضية يتطلب موافقة المالك وسببًا واضحًا',403)
        patient=c.execute('SELECT id,code,created_by FROM billing_patients WHERE id=?',(body.patient_id,)).fetchone()
        if not patient:fail('ملف المريض غير موجود',404)
        if user['role']=='clerk' and patient['created_by']!=user['id'] and body.patient_code.strip().upper()!=patient['code']:
            fail('استخدم كود المريض الكامل لتأكيد فتح حالة جديدة لملف موجود',403)
        cur=c.execute('''INSERT INTO billing_cases(case_no,patient_id,kind,default_point_id,business_date,
                opened_by,opened_at,notes) VALUES (?,?,?,?,?,?,?,?)''',
                ('OPEN-'+secrets.token_hex(6),body.patient_id,body.kind,body.point_id,day,
                 user['id'],stamp(),reason))
        case_id=cur.lastrowid
        number=f'CASE-{day[:4]}-{case_id:06d}'
        c.execute('UPDATE billing_cases SET case_no=? WHERE id=?',(number,case_id))
        remember(c,key,'case',user['id'],fingerprint,case_id)
        audit(c,user['id'],'billing_open_case','billing_case',case_id,
              {'kind':body.kind,'point_id':body.point_id,'reason':reason})
    return {'id':case_id,'case_no':number}


@router.get('/cases')
def cases(point_id:int=0,limit:int=50,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    if limit<1 or limit>100:fail('العدد المطلوب غير صالح')
    points=visible_points(c,user)
    allowed={p['id'] for p in points}
    if point_id and point_id not in allowed:fail('لا صلاحية لهذه النقطة',403)
    if not allowed:return {'items':[]}
    filters=['b.default_point_id IN ('+','.join('?'*len(allowed))+')']
    args=list(sorted(allowed))
    if point_id:filters+=['b.default_point_id=?'];args.append(point_id)
    q='''SELECT b.*, p.code patient_code,p.display_name patient_name, t.name point_name,
          (SELECT COUNT(*) FROM billing_case_lines l WHERE l.case_id=b.id AND l.state='fulfilled') fulfilled_count,
          (SELECT COALESCE(SUM(COALESCE((SELECT net_piasters FROM pricing_line_terms pt WHERE pt.case_line_id=l.id),l.unit_price_piasters*l.quantity)),0) FROM billing_case_lines l
            WHERE l.case_id=b.id AND l.state='fulfilled' AND NOT EXISTS
            (SELECT 1 FROM billing_invoice_draft_lines dl WHERE dl.case_line_id=l.id)) unbilled_piasters
          FROM billing_cases b JOIN billing_patients p ON p.id=b.patient_id
          JOIN billing_points t ON t.id=b.default_point_id WHERE '''+' AND '.join(filters)+ ' ORDER BY b.id DESC LIMIT ?'
    return {'items':[dict(r) for r in c.execute(q,args+[limit])],'mode':'BILLING_SANDBOX'}


@router.get('/cases/{case_id}')
def case_detail(case_id:int,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    case=case_scope(c,user,case_id)
    lines=[dict(r) for r in c.execute('''SELECT l.*,s.code service_code,
              EXISTS(SELECT 1 FROM bed_night_charges n WHERE n.case_line_id=l.id) is_bed_night
              FROM billing_case_lines l
              JOIN billing_services s ON s.id=l.service_id WHERE l.case_id=? ORDER BY l.id''',(case_id,))]
    from pricing import line_net
    for line in lines:
        line['line_total_piasters']=line_net(c,line)
        priced=c.execute('''SELECT t.order_id,o.package_version_id,json_extract(t.terms_json,'$.location_name') location_name
           FROM pricing_line_terms t JOIN pricing_orders o ON o.id=t.order_id WHERE t.case_line_id=?''',(line['id'],)).fetchone()
        if priced:line.update({'pricing_order_id':priced['order_id'],'package_version_id':priced['package_version_id'],'location_name':priced['location_name']})
    drafts=[dict(r) for r in c.execute('''SELECT id,draft_no,total_piasters,status,created_at
              FROM billing_invoice_drafts WHERE case_id=? ORDER BY id DESC''',(case_id,))]
    issued=[dict(r) for r in c.execute('SELECT id,invoice_no,draft_id,issued_date,total_piasters FROM billing_invoices WHERE case_id=? ORDER BY id DESC',(case_id,))]
    return {'case':dict(case),'services':lines,'drafts':drafts,'invoices':issued,
            'unbilled_piasters':sum(x['line_total_piasters'] for x in lines
                      if x['state']=='fulfilled' and not c.execute(
                      'SELECT 1 FROM billing_invoice_draft_lines WHERE case_line_id=?',(x['id'],)).fetchone()),
            'notice':'الخدمات المطلوبة لا ترحل، والفواتير الصادرة فقط تُثبت ذممًا وإيرادًا تجريبيًا.'}


@router.post('/cases/{case_id}/services')
def add_case_service(case_id:int,body:LineForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','clerk')
    key=request_key(body.request_id)
    payload={'case_id':case_id,'service_id':body.service_id,'quantity':body.quantity}
    with c:
        c.execute('BEGIN IMMEDIATE')
        previous,fingerprint=repeat(c,key,'service_line',user['id'],payload)
        if previous:return {'id':previous,'replayed':True}
        case=case_scope(c,user,case_id,write=True)
        if case['status']!='open':fail('الحالة مقفلة',409)
        # A triaged historical paper receipt must retain its original price date.
        # Entry and GL remain in the currently open period; no old cash is rebooked.
        late=c.execute('SELECT original_business_date FROM billing_late_cases WHERE case_id=?',
                       (case_id,)).fetchone()
        service_day=late['original_business_date'] if late else cairo_today()
        require_case_document_period(c,case,cairo_today())
        if c.execute('SELECT 1 FROM pricing_rate_versions WHERE service_id=?',(body.service_id,)).fetchone():
            fail('هذه الخدمة لها قائمة ومكان؛ أضفها من عرض التسعير المعتمد',409)
        service=c.execute('SELECT * FROM billing_services WHERE id=? AND active=1',(body.service_id,)).fetchone()
        if not service:fail('الخدمة غير موجودة أو غير نشطة',404)
        price=c.execute('''SELECT * FROM billing_service_prices WHERE service_id=? AND valid_from<=?
                 ORDER BY valid_from DESC LIMIT 1''',(service['id'],service_day)).fetchone()
        if not price:fail('لا يوجد سعر معتمد لهذه الخدمة في تاريخ الطلب',409)
        cur=c.execute('''INSERT INTO billing_case_lines(case_id,service_id,price_version_id,
            service_name_snapshot,department_id,unit_price_piasters,quantity,added_by,added_at)
            VALUES (?,?,?,?,?,?,?,?,?)''',(case_id,service['id'],price['id'],service['name'],
                                  service['department_id'],price['price_piasters'],body.quantity,user['id'],stamp()))
        remember(c,key,'service_line',user['id'],fingerprint,cur.lastrowid)
        audit(c,user['id'],'billing_order_service','billing_case',case_id,
              {'line_id':cur.lastrowid,'service_id':body.service_id,'quantity':body.quantity,
               'price_version_id':price['id']})
    return {'id':cur.lastrowid,'state':'ordered','unit_price_piasters':price['price_piasters']}


@router.post('/lines/{line_id}/fulfill')
def fulfill_line(line_id:int,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    # No proof from a cashier is enough to book earned medical revenue.
    # Dedicated clinical fulfillment role must be added before real operation.
    require(user,'owner','reviewer')
    with c:
        c.execute('BEGIN IMMEDIATE')
        line=c.execute('SELECT * FROM billing_case_lines WHERE id=?',(line_id,)).fetchone()
        if not line:fail('الخدمة غير موجودة',404)
        case=case_scope(c,user,line['case_id'])
        if case['status']!='open' or line['state']!='ordered':fail('الخدمة ليست قيد الانتظار',409)
        if clinical_required(c,line['department_id']):
            fail('تم تفعيل الإثبات الطبي المستقل؛ المراجع المالي لا يثبت تنفيذ هذه الخدمة',403)
        service_day=complete_line(c,line,user['id'])
        audit(c,user['id'],'billing_fulfill_service','billing_case',line['case_id'],
              {'line_id':line_id,'service_date':service_day})
    return {'id':line_id,'state':'fulfilled'}


@router.post('/lines/{line_id}/cancel')
def cancel_line(line_id:int,body:LineDecision,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','clerk')
    reason=trim(body.reason,'سبب إلغاء الخدمة',8,300)
    with c:
        c.execute('BEGIN IMMEDIATE')
        line=c.execute('SELECT * FROM billing_case_lines WHERE id=?',(line_id,)).fetchone()
        if not line:fail('الخدمة غير موجودة',404)
        case=case_scope(c,user,line['case_id'],write=True)
        if case['status']!='open' or line['state']!='ordered':
            fail('لا يمكن إلغاء خدمة منفذة أو مفوترة؛ استخدم إشعارًا دائنًا عند تفعيله',409)
        if c.execute('''SELECT 1 FROM pricing_line_terms t JOIN pricing_orders o ON o.id=t.order_id
              WHERE t.case_line_id=? AND o.package_version_id IS NOT NULL''',(line_id,)).fetchone():
            fail('لا يُلغى مكون باقة منفردًا؛ ألغِ طلب الباقة كله قبل التنفيذ',409)
        if c.execute('SELECT 1 FROM bed_night_charges WHERE case_line_id=?',(line_id,)).fetchone():
            fail('ليلة السرير موثقة بالفعل؛ لا تُلغى من شاشة الخدمات، بل بمسار تصحيح مالي مستقل',409)
        require_case_document_period(c,case)
        c.execute("UPDATE billing_case_lines SET state='cancelled',cancelled_by=?,cancelled_at=?,reason=? WHERE id=?",
                  (user['id'],stamp(),reason,line_id))
        audit(c,user['id'],'billing_cancel_order','billing_case',line['case_id'],{'line_id':line_id,'reason':reason})
    return {'id':line_id,'state':'cancelled'}


@router.post('/cases/{case_id}/drafts')
def create_draft(case_id:int,body:DraftForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','clerk')
    key=request_key(body.request_id)
    with c:
        c.execute('BEGIN IMMEDIATE')
        previous,fingerprint=repeat(c,key,'invoice_draft',user['id'],{'case_id':case_id})
        if previous:return {'id':previous,'replayed':True}
        case=case_scope(c,user,case_id,write=True)
        if case['status']!='open':fail('الحالة مقفلة',409)
        day=cairo_today()
        require_case_document_period(c,case,day)
        late=c.execute('SELECT original_business_date FROM billing_late_cases WHERE case_id=?',
                       (case_id,)).fetchone()
        # Only independently triaged historical cases may carry an old service
        # date into a new-period invoice. Normal admissions are period-scoped.
        allowed_periods=[day[:7]]
        if late:allowed_periods.append(late['original_business_date'][:7])
        rows=c.execute('''SELECT l.* FROM billing_case_lines l
              LEFT JOIN bed_night_charges n ON n.case_line_id=l.id
              WHERE l.case_id=? AND l.state='fulfilled'
              AND substr(COALESCE(n.night_date,l.service_date,?),1,7) IN ('''+
              ','.join('?' for _ in allowed_periods)+''')
              AND NOT EXISTS (SELECT 1 FROM billing_invoice_draft_lines d
                              WHERE d.case_line_id=l.id) ORDER BY l.id''',
              (case_id,case['business_date'],*allowed_periods)).fetchall()
        if not rows:fail('لا توجد خدمات منفذة غير مضافة لمسودة سابقة',409)
        require_invoice_clinical_evidence(c,rows)
        from pricing import line_net,require_complete_packages
        require_complete_packages(c,rows)
        total=sum(line_net(c,r) for r in rows)
        cur=c.execute('''INSERT INTO billing_invoice_drafts(draft_no,case_id,point_id,total_piasters,
                      created_by,created_at) VALUES (?,?,?,?,?,?)''',
                      ('DRAFT-'+secrets.token_hex(6),case_id,case['default_point_id'],total,user['id'],stamp()))
        draft_id=cur.lastrowid
        num=f'DRAFT-{day[:4]}-{draft_id:06d}'
        c.execute('UPDATE billing_invoice_drafts SET draft_no=? WHERE id=?',(num,draft_id))
        for row in rows:
            c.execute('''INSERT INTO billing_invoice_draft_lines(draft_id,case_line_id,
                         unit_price_piasters,quantity,total_piasters) VALUES (?,?,?,?,?)''',
                      (draft_id,row['id'],row['unit_price_piasters'],row['quantity'],
                       line_net(c,row)))
        remember(c,key,'invoice_draft',user['id'],fingerprint,draft_id)
        audit(c,user['id'],'billing_draft_invoice','billing_case',case_id,
              {'draft_id':draft_id,'total_piasters':total,'line_count':len(rows)})
    return {'id':draft_id,'draft_no':num,'total_piasters':total,'status':'draft','accounting_posted':False}


@router.get('/drafts/{draft_id}')
def draft_detail(draft_id:int,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    d=c.execute('SELECT * FROM billing_invoice_drafts WHERE id=?',(draft_id,)).fetchone()
    if not d:fail('المسودة غير موجودة',404)
    case=case_scope(c,user,d['case_id'])
    lines=[dict(r) for r in c.execute('''SELECT dl.*,l.service_name_snapshot,l.department_id,
       json_extract(t.terms_json,'$.location_name') location_name,json_extract(t.terms_json,'$.unit') unit,
       json_extract(t.terms_json,'$.price_list_name') price_list_name
       FROM billing_invoice_draft_lines dl JOIN billing_case_lines l ON l.id=dl.case_line_id
       LEFT JOIN pricing_line_terms t ON t.case_line_id=l.id
       WHERE dl.draft_id=? ORDER BY dl.id''',(draft_id,))]
    if sum(x['total_piasters'] for x in lines)!=d['total_piasters']:
        fail('خلل في سلامة مبالغ المسودة',500)
    return {'draft':dict(d),'case_no':case['case_no'],'patient_code':case['patient_code'],
            'patient_name':case['patient_name'],'lines':lines,
            'watermark':'مسودة تجريبية — لا تصلح كفاتورة أو إيصال أو مستند تحصيل'}


# ------------ V8.1B: accounting documents / cashier collections ------------
PAYMENT_METHODS=('cash','card','instapay','wallet','transfer')


class BindCashFund(BaseModel):
    fund_id:int


class BindChannel(BaseModel):
    method:Literal['card','instapay','wallet','transfer']
    fund_id:int


class IssueInvoice(BaseModel):
    request_id:str


class PaymentPart(BaseModel):
    method:Literal['cash','card','instapay','wallet','transfer']
    amount:str


class CollectPayment(BaseModel):
    point_id:int
    invoice_id:int|None=None
    patient_code:str=''  # mandatory for cross-point cashier collections
    parts:list[PaymentPart]=Field(min_length=1,max_length=5)
    request_id:str


class ApplyAdvance(BaseModel):
    invoice_id:int
    amount:str
    request_id:str


def cairo_today():
    return datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()


def invoice_receipted(c,invoice_id):
    """Current subsidiary AR assignment; NEVER rewrites the original receipt."""
    return c.execute('''SELECT COALESCE(SUM(p.amount_piasters),0)
       FROM billing_collections b JOIN billing_payment_parts p ON p.collection_id=b.id
       LEFT JOIN financial_collection_reallocations r ON r.collection_id=b.id
       WHERE b.kind='invoice' AND COALESCE(r.to_invoice_id,b.invoice_id)=?''',
       (invoice_id,)).fetchone()[0]


def invoice_due(c,invoice_id):
    invoice=c.execute('SELECT * FROM billing_invoices WHERE id=?',(invoice_id,)).fetchone()
    if not invoice:fail('Invoice not found',404)
    paid=invoice_receipted(c,invoice_id)
    allocated=c.execute('''SELECT COALESCE(SUM(amount_piasters),0) FROM billing_advance_allocations
       WHERE invoice_id=?''',(invoice_id,)).fetchone()[0]
    late_settled=c.execute('''SELECT COALESCE(SUM(amount_piasters),0) FROM late_cash_allocations
       WHERE invoice_id=?''',(invoice_id,)).fetchone()[0]
    late_settled+=c.execute('''SELECT COALESCE(SUM(amount_piasters),0) FROM late_mixed_clearance_lines
       WHERE line_kind='patient_receipt' AND invoice_id=?''',(invoice_id,)).fetchone()[0]
    credit=c.execute("SELECT COALESCE(SUM(amount_piasters),0) FROM billing_credit_requests WHERE invoice_id=? AND status='approved'",(invoice_id,)).fetchone()[0]
    if credit>invoice['total_piasters']:fail('Invoice credits exceed original charge',500)
    # Overcollection due to a later credit becomes a separately tracked liability (2310).
    return max(0,invoice['total_piasters']-credit-paid-allocated-late_settled)


def require_case_document_period(c,case,day=None):
    """Authorize the service/document period; admission month is immutable history.

    Triaged G2B late cases retain independent approval and current-period posting.
    """
    link=c.execute("""SELECT l.incident_id,i.status,i.business_date
        FROM billing_late_cases l JOIN late_entry_incidents i ON i.id=l.incident_id
        WHERE l.case_id=?""",(case['id'],)).fetchone()
    if link:
        if link['status'] not in ('triaged','resolved') or link['business_date']!=case['business_date']:
            fail('بلاغ الاستدراك ليس معتمدًا لتسجيل خدمات قديمة',409)
        month_open(c,(day or cairo_today())[:7])
    else:
        month_open(c,(day or cairo_today())[:7])


def available_advance(c,case_id):
    paid=c.execute('''SELECT COALESCE(SUM(p.amount_piasters),0)
      FROM billing_collections b JOIN billing_payment_parts p ON p.collection_id=b.id
      WHERE b.kind='advance' AND b.case_id=?''',(case_id,)).fetchone()[0]
    allocated=c.execute('''SELECT COALESCE(SUM(amount_piasters),0) FROM billing_advance_allocations
      WHERE case_id=?''',(case_id,)).fetchone()[0]
    refunded=c.execute("SELECT COALESCE(SUM(amount_piasters),0) FROM billing_refund_requests WHERE case_id=? AND source='advance' AND status='paid'",(case_id,)).fetchone()[0]
    balance=paid-allocated-refunded
    if balance<0:fail('Advance refund ledger imbalance',500)
    return balance


def refundable_credit(c,case_id):
    invoices=c.execute('SELECT id,total_piasters FROM billing_invoices WHERE case_id=?',(case_id,)).fetchall()
    total=0
    for invoice in invoices:
        credited=c.execute("SELECT COALESCE(SUM(amount_piasters),0) FROM billing_credit_requests WHERE invoice_id=? AND status='approved'",(invoice['id'],)).fetchone()[0]
        received=invoice_receipted(c,invoice['id'])
        allocated=c.execute('SELECT COALESCE(SUM(amount_piasters),0) FROM billing_advance_allocations WHERE invoice_id=?',(invoice['id'],)).fetchone()[0]
        total+=max(0,received+allocated+credited-invoice['total_piasters'])
    refunded=c.execute("SELECT COALESCE(SUM(amount_piasters),0) FROM billing_refund_requests WHERE case_id=? AND source='credit' AND status='paid'",(case_id,)).fetchone()[0]
    if total<refunded:fail('Patient credit refund ledger imbalance',500)
    return total-refunded


def refund_capacity(c,case_id,source,method):
    # Never pay a method that was not used to fund this patient's balance.
    # Advances already allocated to invoices are conservatively excluded for
    # method-specific advance refunds; a manual review can resolve mixed allocations.
    kind='advance' if source=='advance' else None
    rows=c.execute('''SELECT b.kind,p.amount_piasters FROM billing_collections b
         JOIN billing_payment_parts p ON p.collection_id=b.id
         LEFT JOIN financial_collection_reallocations r ON r.collection_id=b.id
         WHERE (CASE WHEN b.kind='invoice' THEN COALESCE(r.to_case_id,b.case_id)
                ELSE b.case_id END)=? AND p.method=?''',(case_id,method)).fetchall()
    receipts=sum(r['amount_piasters'] for r in rows if kind is None or r['kind']==kind)
    prior=c.execute("SELECT COALESCE(SUM(amount_piasters),0) FROM billing_refund_requests WHERE case_id=? AND method=? AND status='paid'",(case_id,method)).fetchone()[0]
    if source=='advance':
        allocated=c.execute('SELECT COALESCE(SUM(amount_piasters),0) FROM billing_advance_allocations WHERE case_id=?',(case_id,)).fetchone()[0]
        receipts-=allocated
    return max(0,receipts-prior)


@router.post('/points/{point_id}/cash-fund')
def bind_point_cash(point_id:int,body:BindCashFund,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    with c:
        c.execute('BEGIN IMMEDIATE')
        point=lookup(c,'billing_points',point_id)
        fund=lookup(c,'funds',body.fund_id)
        if fund['kind']!='cash':fail('اربط نقطة التحصيل بخزنة نقدية، لا بحساب بنك أو محفظة')
        if c.execute('SELECT 1 FROM billing_points WHERE fund_id=? AND id<>?',(fund['id'],point_id)).fetchone():
            fail('الخزنة مربوطة بنقطة أخرى',409)
        if c.execute('SELECT 1 FROM billing_collections WHERE point_id=? LIMIT 1',(point_id,)).fetchone():
            fail('بعد أول تحصيل، لا يمكن تغيير الخزنة دون دورة تسليم عهدة رسمية',409)
        # Even a shift with zero patient collections is an auditable custody event.
        # Rebinding its till would silently rewrite the source fund of history.
        if c.execute('SELECT 1 FROM shift_sessions WHERE point_id=? LIMIT 1',(point_id,)).fetchone() or (point['fund_id'] and c.execute('SELECT 1 FROM shift_sessions WHERE fund_id=? LIMIT 1',(point['fund_id'],)).fetchone()):
            fail('لا يمكن تغيير خزنة نقطة لها وردية تاريخية؛ استخدم إنشاء نقطة جديدة وتحويل عهدة',409)
        if c.execute('SELECT 1 FROM fund_movements WHERE fund_id=? LIMIT 1',(fund['id'],)).fetchone() or c.execute('SELECT 1 FROM shift_sessions WHERE fund_id=? LIMIT 1',(fund['id'],)).fetchone():
            fail('الخزنة الجديدة لها حركة تاريخية؛ يجب تحويل عهدتها رسميًا أولًا',409)
        if c.execute('SELECT 1 FROM shift_sessions WHERE fund_id=? AND status IN (\'open\',\'submitted\')',(point['fund_id'],)).fetchone() if point['fund_id'] else False:
            fail('أقفل وردية الخزنة السابقة قبل تعديل الربط',409)
        c.execute('UPDATE billing_points SET fund_id=? WHERE id=?',(fund['id'],point_id))
        audit(c,user['id'],'billing_cash_fund','billing_point',point_id,{'fund_id':fund['id']})
    return {'point_id':point_id,'fund_id':body.fund_id}


@router.post('/channels')
def bind_payment_channel(body:BindChannel,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    with c:
        c.execute('BEGIN IMMEDIATE')
        fund=lookup(c,'funds',body.fund_id)
        if fund['kind']!='wallet' or not fund['code'].startswith('bclear_'):
            fail('التحصيل الإلكتروني يجب أن يذهب إلى حساب مقاصة مستقل من نوع محفظة وكوده يبدأ bclear_')
        if c.execute('SELECT 1 FROM billing_points WHERE fund_id=?',(fund['id'],)).fetchone():
            fail('لا يمكن استخدام عهدة نقدية كحساب تسويات إلكترونية',409)
        other=c.execute('SELECT method FROM billing_payment_channels WHERE fund_id=? AND method<>?',(fund['id'],body.method)).fetchone()
        if other:fail('كل طريقة إلكترونية تتطلب حساب مقاصة مستقلًا',409)
        existing=c.execute('SELECT fund_id FROM billing_payment_channels WHERE method=?',(body.method,)).fetchone()
        if existing and existing['fund_id']!=fund['id'] and c.execute('''SELECT 1 FROM billing_payment_parts
             WHERE method=? LIMIT 1''',(body.method,)).fetchone():
            fail('حساب المقاصة مستخدم بالفعل؛ تحتاج لتسوية ومراجعة قبل تغييره',409)
        c.execute('''INSERT INTO billing_payment_channels(method,fund_id,configured_by,configured_at)
           VALUES (?,?,?,?) ON CONFLICT(method) DO UPDATE SET fund_id=excluded.fund_id,
           configured_by=excluded.configured_by,configured_at=excluded.configured_at''',
           (body.method,fund['id'],user['id'],stamp()))
        audit(c,user['id'],'billing_channel_map','billing_channel',body.method,{'fund_id':fund['id']})
    return {'method':body.method,'fund_id':body.fund_id}


@router.post('/drafts/{draft_id}/issue')
def issue_invoice(draft_id:int,body:IssueInvoice,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','clerk')
    key=request_key(body.request_id)
    with c:
        c.execute('BEGIN IMMEDIATE')
        previous,fingerprint=repeat(c,key,'issue_invoice',user['id'],{'draft_id':draft_id})
        if previous:return {'id':previous,'replayed':True}
        draft=c.execute('SELECT * FROM billing_invoice_drafts WHERE id=?',(draft_id,)).fetchone()
        if not draft:fail('المسودة غير موجودة',404)
        case=case_scope(c,user,draft['case_id'],write=True)
        if case['status']!='open':fail('الحالة مقفلة',409)
        if c.execute('SELECT 1 FROM billing_invoices WHERE draft_id=?',(draft_id,)).fetchone():
            fail('هذه المسودة أُصدرت بالفعل؛ لا يمكن إصدارها مرة ثانية',409)
        day=cairo_today();month_open(c,day[:7])
        rows=c.execute('''SELECT dl.*,l.service_name_snapshot,l.department_id,l.state,
              substr(COALESCE(n.night_date,l.service_date,bc.business_date),1,7) service_period
          FROM billing_invoice_draft_lines dl JOIN billing_case_lines l ON l.id=dl.case_line_id
          JOIN billing_cases bc ON bc.id=l.case_id
          LEFT JOIN bed_night_charges n ON n.case_line_id=l.id
          WHERE dl.draft_id=? ORDER BY dl.id''',(draft_id,)).fetchall()
        if not rows or any(r['state']!='fulfilled' for r in rows) or sum(r['total_piasters'] for r in rows)!=draft['total_piasters']:
            fail('المسودة تغيرت أو تحتوي على خدمة غير منفذة',409)
        require_invoice_clinical_evidence(c,rows)
        late_origin=c.execute('''SELECT incident_id,original_business_date
            FROM billing_late_cases WHERE case_id=?''',(case['id'],)).fetchone()
        allowed_periods={day[:7]}
        if late_origin:
            # Clearance may be withdrawn after draft creation; recheck first.
            require_case_document_period(c,case,day)
            allowed_periods.add(late_origin['original_business_date'][:7])
        if any(r['service_period'] not in allowed_periods for r in rows):
            fail('المسودة تشمل خدمات من فترة مختلفة؛ يلزم تصحيح مستندي قبل الإصدار',409)
        # Revenue is posted once at invoicing after service fulfillment verification;
        # long admissions spanning periods need a separately approved accrual policy.
        gl_lines=[(ledger.account_by_code(c,'1200'),draft['total_piasters'],0,None)]
        gl_lines += [(ledger.account_by_code(c,'4100'),0,r['total_piasters'],r['department_id']) for r in rows]
        memo=('فاتورة استدراك خدمات يوم '+late_origin['original_business_date']+
              ' / بلاغ #'+str(late_origin['incident_id'])+' / '+case['case_no']) if late_origin else (
              'إثبات إيراد خدمات الحالة '+case['case_no'])
        journal=ledger._journal(c,entry_date=day,memo=memo,
            origin='manual',source_id=None,created_by=user['id'],reviewed_by=user['id'],lines=gl_lines)
        next_id=c.execute('SELECT COALESCE(MAX(id),0)+1 FROM billing_invoices').fetchone()[0]
        num=f'INV-{day[:4]}-{next_id:06d}'
        cur=c.execute('''INSERT INTO billing_invoices(id,invoice_no,draft_id,case_id,issued_date,total_piasters,
           issued_by,issued_at,journal_id) VALUES (?,?,?,?,?,?,?,?,?)''',
           (next_id,num,draft_id,case['id'],day,draft['total_piasters'],user['id'],stamp(),journal))
        remember(c,key,'issue_invoice',user['id'],fingerprint,cur.lastrowid)
        audit(c,user['id'],'billing_issue_invoice','billing_invoice',cur.lastrowid,
            {'invoice_no':num,'case_id':case['id'],'amount_piasters':draft['total_piasters'],'journal_id':journal,'late_incident_id':late_origin['incident_id'] if late_origin else None})
    return {'id':cur.lastrowid,'invoice_no':num,'amount_piasters':draft['total_piasters'],
            'due_piasters':draft['total_piasters'],'status':'issued'}


def current_point_shift(c,point_id,user):
    can_point(c,user,point_id,write=True)
    point=c.execute('SELECT * FROM billing_points WHERE id=?',(point_id,)).fetchone()
    if not point or not point['fund_id']:fail('يجب على المالك ربط هذه النقطة بخزنتها النقدية أولًا',409)
    from app import authorize_cashbook_fund
    authorize_cashbook_fund(c,user,point['fund_id'])
    sh=c.execute('''SELECT * FROM shift_sessions WHERE fund_id=? AND status='open' ''',(point['fund_id'],)).fetchone()
    if not sh:
        fail('No cashier shift open for this station',409)
    import cashier_ops
    if not cashier_ops.point_enabled(c,point_id,sh['business_date']):
        fail('نقطة التحصيل متوقفة وفق جدول التشغيل الساري',409)
    setting=c.execute('SELECT enforce_clock FROM shift_settings WHERE id=1').fetchone()
    if setting and setting[0]:
        actual=datetime.now(ZoneInfo('Africa/Cairo'))
        if not (sh['scheduled_start_at'] and sh['scheduled_end_at'] and
                datetime.fromisoformat(sh['scheduled_start_at'])<=actual<datetime.fromisoformat(sh['scheduled_end_at'])):
            fail('Outside the station actual Cairo shift window',409)
    elif sh['business_date']!=cairo_today():
        from datetime import datetime as dt
        actual=dt.now(ZoneInfo('Africa/Cairo'))
        if not (sh['scheduled_start_at'] and sh['scheduled_end_at'] and
                sh['scheduled_start_at'][:16]<=actual.strftime('%Y-%m-%dT%H:%M')<sh['scheduled_end_at'][:16]):
            fail('No shift exists for the current Cairo working day',409)
    if sh['responsible_id']!=user['id']:
        fail('صاحب الوردية فقط يحق له تحصيل مدفوعات باسمها',403)
    if user['role']=='clerk':
        rights=c.execute('SELECT allowed_codes FROM cashier_shift_staff_rules WHERE point_id=? AND user_id=?',
                         (point_id,user['id'])).fetchone()
        if rights is not None and sh['shift'] not in rights['allowed_codes'].split(','):
            fail('صلاحية تحصيل هذه الوردية سُحبت من الموظف',403)
    return point,sh


@router.post('/cases/{case_id}/collect')
def collect_case(case_id:int,body:CollectPayment,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','clerk')
    key=request_key(body.request_id)
    if len(body.parts)>5:fail('الحد الأقصى خمس وسائل دفع للمعاملة')
    amounts=[c_piasters(p.amount) for p in body.parts]
    total=sum(amounts)
    if total>10**12:fail('التحصيل يتجاوز الحد المسموح')
    payload={'case_id':case_id,'point_id':body.point_id,'invoice_id':body.invoice_id,
             'patient_code':body.patient_code.strip().upper(),
             'parts':[{'method':p.method,'amount_piasters':a} for p,a in zip(body.parts,amounts)]}
    with c:
        c.execute('BEGIN IMMEDIATE')
        previous,fingerprint=repeat(c,key,'collect',user['id'],payload)
        if previous:return {'id':previous,'replayed':True}
        case=c.execute('''SELECT b.*,p.code patient_code FROM billing_cases b
              JOIN billing_patients p ON p.id=b.patient_id WHERE b.id=?''',(case_id,)).fetchone()
        if not case:fail('الحالة غير موجودة',404)
        point,shift=current_point_shift(c,body.point_id,user)
        # G2B: pre-existing envelopes may already be deposited. Never let a
        # current-shift collection turn historical cash into a second receipt.
        if c.execute('SELECT 1 FROM billing_late_cases WHERE case_id=?',(case_id,)).fetchone():
            fail('لا يجوز تحصيل حالة الاستدراك من شاشة القبض العادية قبل مطابقة النقدية التاريخية؛ راجع مركز الاستدراك',409)
        if case['status']!='open':fail('لا يمكن التحصيل لحالة مقفلة',409)
        if point['id']!=case['default_point_id'] and user['role']!='owner':
            if payload['patient_code']!=case['patient_code']:
                fail('تحصيل لحالة تابعة لنقطة أخرى يتطلب كود المريض الكامل',403)
        day=shift['business_date'];month_open(c,day[:7])
        invoice_id=body.invoice_id
        if invoice_id is not None:
            invoice=c.execute('SELECT * FROM billing_invoices WHERE id=?',(invoice_id,)).fetchone()
            if not invoice or invoice['case_id']!=case_id:fail('الفاتورة لا تتبع هذه الحالة',409)
            if total>invoice_due(c,invoice_id):fail('التحصيل أكبر من رصيد الفاتورة المتبقي',409)
            kind='invoice'
        else:kind='advance'
        coll_id=c.execute('SELECT COALESCE(MAX(id),0)+1 FROM billing_collections').fetchone()[0]
        num=f'REC-{day[:4]}-{coll_id:06d}'
        cur=c.execute('''INSERT INTO billing_collections(id,collection_no,case_id,invoice_id,point_id,
          shift_session_id,kind,business_date,total_piasters,created_by,created_at)
          VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
          (coll_id,num,case_id,invoice_id,point['id'],shift['id'],kind,day,total,user['id'],stamp()))
        category_code='billing_invoice_receipt' if kind=='invoice' else 'billing_advance_receipt'
        category=c.execute('SELECT id FROM categories WHERE code=?',(category_code,)).fetchone()
        if not category:fail('تصنيف تحصيل المرضى غير مهيأ',500)
        for idx,(part,amount) in enumerate(zip(body.parts,amounts)):
            if part.method=='cash': fund_id=point['fund_id']
            else:
                channel=c.execute('''SELECT f.id FROM billing_payment_channels ch
                 JOIN funds f ON f.id=ch.fund_id WHERE ch.method=? AND f.active=1''',(part.method,)).fetchone()
                if not channel:fail('طريقة الدفع غير مهيأة بحساب مقاصة: '+part.method,409)
                fund_id=channel['id']
            label='تحصيل فاتورة' if kind=='invoice' else 'مقدم حالة'
            cur_v=c.execute('''INSERT INTO vouchers(voucher_no,date,kind,department_id,category_id,
              from_fund_id,shift,amount_piasters,description,reference_no,status,
              created_by,reviewed_by,created_at,reviewed_at)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (f'BR-{secrets.token_hex(8)}',day,'receipt',None,category['id'],fund_id,
               'central',amount,label+' '+case['case_no']+' '+num, num,'pending',
               user['id'],user['id'],stamp(),stamp()))
            vr=c.execute('SELECT * FROM vouchers WHERE id=?',(cur_v.lastrowid,)).fetchone()
            book_movements(c,vr)
            ledger.post_voucher(c,vr,user['id'])
            c.execute("UPDATE vouchers SET status='approved' WHERE id=?",(vr['id'],))
            c.execute('''INSERT INTO billing_payment_parts(collection_id,method,fund_id,voucher_id,amount_piasters)
              VALUES (?,?,?,?,?)''',(coll_id,part.method,fund_id,vr['id'],amount))
        remember(c,key,'collect',user['id'],fingerprint,coll_id)
        audit(c,user['id'],'billing_collect','billing_collection',coll_id,
              {'kind':kind,'case_id':case_id,'invoice_id':invoice_id,'point_id':point['id'],
               'shift_session_id':shift['id'],'total_piasters':total,
               'parts':[{'method':p.method,'amount_piasters':a} for p,a in zip(body.parts,amounts)]})
    return {'id':coll_id,'collection_no':num,'total_piasters':total,'kind':kind,
            'invoice_due_piasters':invoice_due(c,invoice_id) if invoice_id else None}


@router.post('/cases/{case_id}/apply-advance')
def apply_advance(case_id:int,body:ApplyAdvance,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','clerk')
    amount=c_piasters(body.amount);key=request_key(body.request_id)
    with c:
        c.execute('BEGIN IMMEDIATE')
        previous,fingerprint=repeat(c,key,'apply_advance',user['id'],
              {'case_id':case_id,'invoice_id':body.invoice_id,'amount':amount})
        if previous:return {'id':previous,'replayed':True}
        case=case_scope(c,user,case_id,write=True)
        if case['status']!='open':fail('الحالة مصفاة ماليًا؛ أي تعديل يحتاج مسار تصحيح بعد الإغلاق',409)
        invoice=c.execute('SELECT * FROM billing_invoices WHERE id=?',(body.invoice_id,)).fetchone()
        if not invoice or invoice['case_id']!=case_id:fail('الفاتورة لا تتبع ملف الحالة',409)
        month_open(c,cairo_today()[:7])
        if amount>available_advance(c,case_id):fail('المقدم المتاح لا يغطي المبلغ',409)
        if amount>invoice_due(c,body.invoice_id):fail('مبلغ التخصيص أكبر من باقي الفاتورة',409)
        journal=ledger._journal(c,entry_date=cairo_today(),
            memo='تخصيص مقدم حالة '+case['case_no']+' إلى '+invoice['invoice_no'],
            origin='manual',source_id=None,created_by=user['id'],reviewed_by=user['id'],
            lines=[(ledger.account_by_code(c,'2300'),amount,0,None),
                   (ledger.account_by_code(c,'1200'),0,amount,None)])
        cur=c.execute('''INSERT INTO billing_advance_allocations(case_id,invoice_id,amount_piasters,
            allocated_by,allocated_at,journal_id) VALUES (?,?,?,?,?,?)''',
            (case_id,body.invoice_id,amount,user['id'],stamp(),journal))
        remember(c,key,'apply_advance',user['id'],fingerprint,cur.lastrowid)
        audit(c,user['id'],'billing_apply_advance','billing_advance_allocation',cur.lastrowid,
              {'case_id':case_id,'invoice_id':body.invoice_id,'amount_piasters':amount,'journal_id':journal})
    return {'id':cur.lastrowid,'amount_piasters':amount,'invoice_due_piasters':invoice_due(c,body.invoice_id)}


@router.get('/cases/{case_id}/finance')
def case_finance(case_id:int,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    case=case_scope(c,user,case_id)
    invoices=[dict(x) for x in c.execute('''SELECT id,invoice_no,draft_id,issued_date,total_piasters,status
       FROM billing_invoices WHERE case_id=? ORDER BY id DESC''',(case_id,))]
    for i in invoices:
        i['due_piasters']=invoice_due(c,i['id'])
        i['credited_piasters']=c.execute("SELECT COALESCE(SUM(amount_piasters),0) FROM billing_credit_requests WHERE invoice_id=? AND status='approved'",(i['id'],)).fetchone()[0]
    collections=[dict(x) for x in c.execute('''SELECT b.id,b.collection_no,b.invoice_id,b.point_id,b.kind,
       b.business_date,b.total_piasters,b.created_at,b.case_id AS original_case_id,
       COALESCE(r.to_case_id,b.case_id) AS effective_case_id,
       COALESCE(r.to_invoice_id,b.invoice_id) AS effective_invoice_id,
       r.id AS reallocation_id, r.effective_date AS reallocated_date
       FROM billing_collections b LEFT JOIN financial_collection_reallocations r ON r.collection_id=b.id
       WHERE b.case_id=? OR r.to_case_id=? ORDER BY b.id DESC''',(case_id,case_id))]
    late=c.execute('''SELECT l.incident_id,l.original_business_date,l.paper_document_id,
        i.status incident_status,d.amount_piasters evidence_cash_piasters
        FROM billing_late_cases l JOIN late_entry_incidents i ON i.id=l.incident_id
        JOIN late_entry_documents d ON d.id=l.paper_document_id
        WHERE l.case_id=?''',(case_id,)).fetchone()
    late_cash=c.execute('''SELECT COALESCE(SUM(amount_piasters),0) settled_piasters,
       COUNT(*) allocation_count FROM (
       SELECT amount_piasters FROM late_cash_allocations WHERE case_id=?
       UNION ALL SELECT amount_piasters FROM late_mixed_clearance_lines
       WHERE line_kind='patient_receipt' AND case_id=?)''',(case_id,case_id)).fetchone()
    return {'late_recovery':dict(late) if late else None,
            'late_cash_settlement':dict(late_cash),
            'cash_collection_blocked':bool(late),
            'case_no':case['case_no'],'invoices':invoices,'collections':collections,
            'total_invoiced_piasters':sum(i['total_piasters'] for i in invoices),
            'outstanding_piasters':sum(i['due_piasters'] for i in invoices),
            'advance_available_piasters':available_advance(c,case_id),
            'credit_refundable_piasters':refundable_credit(c,case_id),
            'notice':'الأرقام تجريبية حتى اعتماد ورقابة الورديات والتسويات الرسمية.'}


@router.get('/collections/{collection_id}')
def collection_receipt(collection_id:int,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    col=c.execute('SELECT * FROM billing_collections WHERE id=?',(collection_id,)).fetchone()
    if not col:fail('إيصال التحصيل غير موجود',404)
    # The collection point and patient-file point can differ. Reviewer needs both.
    # Own-receipt cashiers keep their limited cross-point receipt workflow.
    if user['role']=='reviewer':
        can_point(c,user,col['point_id'])
        case_scope(c,user,col['case_id'])
    elif user['role']=='clerk':
        if col['created_by']!=user['id']:
            case_scope(c,user,col['case_id'])
        else:
            can_point(c,user,col['point_id'])
    case=c.execute('''SELECT b.case_no,p.code patient_code FROM billing_cases b
       JOIN billing_patients p ON p.id=b.patient_id WHERE b.id=?''',(col['case_id'],)).fetchone()
    parts=[dict(r) for r in c.execute('''SELECT method,amount_piasters,fund_id
          FROM billing_payment_parts WHERE collection_id=? ORDER BY id''',(collection_id,))]
    if user['role']!='owner':
        # Patient receipts do not require internal clearing bank/wallet identifiers.
        parts=[{'method':r['method'],'amount_piasters':r['amount_piasters']} for r in parts]
    reallocation=c.execute('''SELECT id,effective_date,to_invoice_id,to_case_id
       FROM financial_collection_reallocations WHERE collection_id=?''',(collection_id,)).fetchone()
    return {'collection_no':col['collection_no'],'case_no':case['case_no'],
            'patient_code':case['patient_code'],'point_id':col['point_id'],
            'kind':col['kind'],'invoice_id':col['invoice_id'],'date':col['business_date'],
            'total_piasters':col['total_piasters'],'parts':parts,
            'allocation_corrected':bool(reallocation),
            'correction_id':reallocation['id'] if reallocation else None,
            'watermark':'نسخة اختبار؛ ليست إيصال تحصيل نهائيًا أو مستندًا ضريبيًا.'}


@router.get('/crosscase/resolve')
def resolve_crosspoint(case_no:str,patient_code:str,point_id:int,
                       user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','clerk')
    can_point(c,user,point_id,write=True)
    if not re.fullmatch(r'CASE-[0-9]{4}-[0-9]{6}',case_no or '') or \
       not re.fullmatch(r'PT-[A-F0-9]{12}',(patient_code or '').upper()):
        fail('أدخل رقم الحالة وكود المريض كاملين',400)
    case=c.execute('''SELECT b.id,b.case_no,b.default_point_id FROM billing_cases b
         JOIN billing_patients p ON p.id=b.patient_id WHERE b.case_no=? AND p.code=?''',
        (case_no,patient_code.upper())).fetchone()
    if not case:fail('البيانات غير متطابقة',404)
    unpaid=[]
    for row in c.execute('SELECT id,invoice_no FROM billing_invoices WHERE case_id=?',(case['id'],)):
        due=invoice_due(c,row['id'])
        if due:unpaid.append({'id':row['id'],'invoice_no':row['invoice_no'],'due_piasters':due})
    return {'case_id':case['id'],'case_no':case_no,'unpaid_invoices':unpaid,
            'advance_available_piasters':available_advance(c,case['id']),
            'can_collect_here':point_id!=case['default_point_id']}


@router.get('/summary')
def billing_summary(period:str='',user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    # This includes hospital-wide shortages and receivables, not per-point totals.
    require(user,'owner')
    month=valid_month(period or current_month())
    invoices=c.execute('''SELECT COUNT(*) n,COALESCE(SUM(total_piasters),0) total
       FROM billing_invoices WHERE substr(issued_date,1,7)=?''',(month,)).fetchone()
    late_invoices=c.execute('''SELECT COUNT(*) n,COALESCE(SUM(i.total_piasters),0) total
       FROM billing_invoices i JOIN billing_late_cases l ON l.case_id=i.case_id
       WHERE substr(i.issued_date,1,7)=?''',(month,)).fetchone()
    receipts=c.execute('''SELECT COUNT(*) n,COALESCE(SUM(total_piasters),0) total
       FROM billing_collections WHERE substr(business_date,1,7)=?''',(month,)).fetchone()
    method=[dict(x) for x in c.execute('''SELECT p.method,COALESCE(SUM(p.amount_piasters),0) total_piasters
       FROM billing_payment_parts p JOIN billing_collections b ON b.id=p.collection_id
       WHERE substr(b.business_date,1,7)=? GROUP BY p.method ORDER BY p.method''',(month,))]
    # Liability-correct summary, not a paid-cash-minus-invoices shortcut.
    all_invoices=c.execute('SELECT id FROM billing_invoices').fetchall()
    uncollected=sum(invoice_due(c,r['id']) for r in all_invoices)
    all_cases=c.execute('SELECT id FROM billing_cases').fetchall()
    deposits=sum(available_advance(c,r['id']) for r in all_cases)
    credit_liability=sum(refundable_credit(c,r['id']) for r in all_cases)
    # A historical suspense allocation reduces patient receivables but is NOT a
    # fresh receipt. Keep it visible separately in manager reporting.
    late_cash_cleared=c.execute('''SELECT COUNT(*) AS n,COALESCE(SUM(a.amount_piasters),0) AS total
       FROM late_cash_allocations a JOIN gl_journals j ON j.id=a.journal_id
       WHERE j.status='posted' AND substr(j.entry_date,1,7)=?''',(month,)).fetchone()
    suspense_unallocated=c.execute('''SELECT COALESCE(SUM(v.amount_piasters),0)
       FROM vouchers v JOIN categories ca ON ca.id=v.category_id
       WHERE ca.code='late_cash_unallocated' AND v.status='approved' ''').fetchone()[0]
    suspense_unallocated-=c.execute('''SELECT COALESCE(SUM(amount_piasters),0)
       FROM late_cash_allocations''').fetchone()[0]
    suspense_unallocated-=c.execute('''SELECT COALESCE(SUM(actual_cash_piasters),0)
       FROM late_mixed_clearances''').fetchone()[0]
    mixed=c.execute('''SELECT COUNT(*) n,
      COALESCE(SUM(c.gross_receipts_piasters),0) gross,
      COALESCE(SUM(c.expense_piasters),0) expenses,
      COALESCE(SUM(c.actual_cash_piasters),0) cash,
      COALESCE(SUM(CASE WHEN c.variance_piasters<0 THEN -c.variance_piasters ELSE 0 END),0) short,
      COALESCE(SUM(CASE WHEN c.variance_piasters>0 THEN c.variance_piasters ELSE 0 END),0) over
      FROM late_mixed_clearances c JOIN gl_journals j ON j.id=c.journal_id
      WHERE j.status='posted' AND substr(j.entry_date,1,7)=?''',(month,)).fetchone()
    mixed_recovered=c.execute('''SELECT COALESCE(SUM(r.amount_piasters),0) total
      FROM late_mixed_shortage_recovery_requests r JOIN vouchers v ON v.id=r.voucher_id
      WHERE r.status='approved' AND v.status='approved' ''').fetchone()['total']
    mixed_recovered_this_month=c.execute('''SELECT COALESCE(SUM(r.amount_piasters),0) total
      FROM late_mixed_shortage_recovery_requests r JOIN vouchers v ON v.id=r.voucher_id
      WHERE r.status='approved' AND v.status='approved' AND substr(v.date,1,7)=?''',(month,)).fetchone()['total']
    original_shortages=c.execute('''SELECT COALESCE(SUM(-variance_piasters),0) FROM late_mixed_clearances
      WHERE variance_piasters<0''').fetchone()[0]
    refunded_overage_total=c.execute('''SELECT COALESCE(SUM(amount_piasters),0)
      FROM late_mixed_overage_refund_requests WHERE status='approved' ''').fetchone()[0]
    refunded_overage_month=c.execute('''SELECT COALESCE(SUM(r.amount_piasters),0)
      FROM late_mixed_overage_refund_requests r JOIN vouchers v ON v.id=r.voucher_id
      WHERE r.status='approved' AND v.status='approved' AND substr(v.date,1,7)=?''',(month,)).fetchone()[0]
    original_overage_total=c.execute('''SELECT COALESCE(SUM(variance_piasters),0)
      FROM late_mixed_clearances WHERE variance_piasters>0''').fetchone()[0]
    refunded_for_origin_month=c.execute('''SELECT COALESCE(SUM(r.amount_piasters),0)
      FROM late_mixed_overage_refund_requests r JOIN late_mixed_clearances mc ON mc.id=r.clearance_id
      JOIN gl_journals j ON j.id=mc.journal_id
      WHERE r.status='approved' AND j.status='posted' AND substr(j.entry_date,1,7)=?''',(month,)).fetchone()[0]
    mixed_invoices=c.execute('''SELECT COUNT(*) FROM late_mixed_clearance_lines ml
      JOIN late_mixed_clearances mc ON mc.id=ml.clearance_id
      JOIN gl_journals j ON j.id=mc.journal_id
      WHERE ml.line_kind='patient_receipt' AND j.status='posted'
      AND substr(j.entry_date,1,7)=?''',(month,)).fetchone()[0]
    credits_this_month=c.execute("SELECT COALESCE(SUM(b.amount_piasters),0) FROM billing_credit_requests b JOIN gl_journals j ON j.id=b.journal_id WHERE b.status='approved' AND substr(j.entry_date,1,7)=?",(month,)).fetchone()[0]
    refunds_this_month=c.execute("SELECT COALESCE(SUM(r.amount_piasters),0) FROM billing_refund_requests r JOIN shift_sessions s ON s.id=r.paid_shift_id WHERE r.status='paid' AND substr(s.business_date,1,7)=?",(month,)).fetchone()[0]
    return {'period':month,'issued_invoices':invoices['n'],
            'invoiced_this_month_piasters':invoices['total'],
            'late_service_invoices_this_month':late_invoices['n'],
            'late_service_revenue_this_month_piasters':late_invoices['total'],
            'late_cash_cleared_this_month_piasters':late_cash_cleared['total']+mixed['gross'],
            'mixed_envelopes_this_month':mixed['n'],
            'mixed_envelope_ar_cleared_piasters':mixed['gross'],
            'mixed_envelope_expenses_piasters':mixed['expenses'],
            'mixed_envelope_cash_already_booked_piasters':mixed['cash'],
            'mixed_envelope_shortage_pending_piasters':mixed['short'],
            'mixed_envelope_shortage_recovered_this_month_piasters':mixed_recovered_this_month,
            'mixed_envelope_shortage_remaining_all_piasters':original_shortages-mixed_recovered,
            'mixed_envelope_shortage_recovered_all_piasters':mixed_recovered,
            'mixed_envelope_overage_pending_piasters':mixed['over']-refunded_for_origin_month,
            'mixed_envelope_overage_refunded_this_month_piasters':refunded_overage_month,
            'mixed_envelope_overage_refunded_all_piasters':refunded_overage_total,
            'mixed_envelope_overage_remaining_all_piasters':original_overage_total-refunded_overage_total,
            'late_cash_cleared_invoice_count_this_month':late_cash_cleared['n']+mixed_invoices,
            'suspense_cash_unallocated_piasters':suspense_unallocated,
            'collections_this_month_piasters':receipts['total'],
            'collection_count':receipts['n'],'methods':method,
            'total_outstanding_receivables_piasters':uncollected,
            'total_unapplied_advances_piasters':deposits,
            'patient_credit_refundable_piasters':credit_liability,
            'approved_credits_this_month_piasters':credits_this_month,
            'paid_refunds_this_month_piasters':refunds_this_month,
            'note':'التحصيل ليس إيراد الفترة، والأرقام حتى الآن تجريبية وغير مُعتمدة كقوائم مالية.'}

# V8.1C correction workflow: an approved credit is a separate journal; an
# approved refund is a separate cashbook payment. Originals stay immutable.
class CreditRequestForm(BaseModel):
    invoice_id:int
    amount:str
    reason:str=Field(min_length=8,max_length=500)
    request_id:str

class CreditDecisionForm(BaseModel):
    decision:Literal['approve','reject']
    note:str=Field(default='',max_length=500)

class RefundRequestForm(BaseModel):
    point_id:int
    source:Literal['credit','advance']
    method:Literal['cash','card','instapay','wallet','transfer']
    amount:str
    reason:str=Field(min_length=8,max_length=500)
    request_id:str

class RefundDecisionForm(BaseModel):
    decision:Literal['approve','reject']
    note:str=Field(default='',max_length=500)

class RefundPayForm(BaseModel):
    request_id:str


def refund_available(c,case_id,source):
    return refundable_credit(c,case_id) if source=='credit' else available_advance(c,case_id)


def pending_refunds(c,case_id,source,method=None):
    q="SELECT COALESCE(SUM(amount_piasters),0) FROM billing_refund_requests WHERE case_id=? AND source=? AND status='approved'"
    args=[case_id,source]
    if method:
        q+=' AND method=?';args.append(method)
    return c.execute(q,args).fetchone()[0]


@router.post('/cases/{case_id}/credits')
def request_credit(case_id:int,body:CreditRequestForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','clerk')
    key=request_key(body.request_id)
    amount=c_piasters(body.amount)
    reason=trim(body.reason,'reason',8,500)
    payload={'case_id':case_id,'invoice_id':body.invoice_id,'amount_piasters':amount,'reason':reason}
    with c:
        c.execute('BEGIN IMMEDIATE')
        previous,fingerprint=repeat(c,key,'credit_request',user['id'],payload)
        if previous:return {'id':previous,'replayed':True}
        case=case_scope(c,user,case_id,write=True)
        if case['status']!='open':fail('الحالة مصفاة ماليًا؛ يمنع إنشاء إشعار دائن بالطريقة العادية',409)
        invoice=c.execute('SELECT * FROM billing_invoices WHERE id=? AND case_id=?',(body.invoice_id,case_id)).fetchone()
        if not invoice:fail('Invoice not in case',404)
        if (c.execute('SELECT 1 FROM late_cash_allocations WHERE invoice_id=?',(body.invoice_id,)).fetchone() or
            c.execute('SELECT 1 FROM late_mixed_clearance_lines WHERE invoice_id=?',(body.invoice_id,)).fetchone()):
            fail('فاتورة الاستدراك تمت تسويتها من ظرف نقدية؛ التصحيح يحتاج مسارًا ماليًا مخصصًا يحافظ على العهدة',409)
        credits=c.execute("SELECT COALESCE(SUM(amount_piasters),0) FROM billing_credit_requests WHERE invoice_id=? AND status='approved'",(body.invoice_id,)).fetchone()[0]
        if amount>invoice['total_piasters']-credits:fail('Credit exceeds remaining invoiced services',409)
        cur=c.execute('''INSERT INTO billing_credit_requests(credit_no,invoice_id,case_id,amount_piasters,
             reason,requested_by,requested_at) VALUES (?,?,?,?,?,?,?)''',
             ('CR-'+secrets.token_hex(8),body.invoice_id,case_id,amount,reason,user['id'],stamp()))
        remember(c,key,'credit_request',user['id'],fingerprint,cur.lastrowid)
        audit(c,user['id'],'billing_credit_requested','billing_credit',cur.lastrowid,{'amount':amount})
    return {'id':cur.lastrowid,'status':'pending','amount_piasters':amount}


@router.post('/credits/{credit_id}/decision')
def credit_decision(credit_id:int,body:CreditDecisionForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    with c:
        c.execute('BEGIN IMMEDIATE')
        note=trim(body.note,'note',0,500)
        credit=c.execute('SELECT * FROM billing_credit_requests WHERE id=?',(credit_id,)).fetchone()
        if not credit:fail('Credit request not found',404)
        case=case_scope(c,user,credit['case_id'])
        if case['status']!='open':fail('الحالة مصفاة ماليًا؛ لا يمكن تغيير ذممها',409)
        if credit['status']!='pending':fail('Already decided',409)
        if credit['requested_by']==user['id']:fail('Requester cannot approve own credit',403)
        if body.decision=='reject':
            c.execute("UPDATE billing_credit_requests SET status='rejected',decided_by=?,decided_at=?,decision_note=? WHERE id=?",
                      (user['id'],stamp(),note,credit_id))
            audit(c,user['id'],'billing_credit_rejected','billing_credit',credit_id,{'reason':note})
            return {'id':credit_id,'status':'rejected'}
        if (c.execute('SELECT 1 FROM late_cash_allocations WHERE invoice_id=?',(credit['invoice_id'],)).fetchone() or
            c.execute('SELECT 1 FROM late_mixed_clearance_lines WHERE invoice_id=?',(credit['invoice_id'],)).fetchone()):
            fail('فاتورة مستدركة سُوّيت من الظرف؛ لا تعتمد إشعارًا دائنًا قبل مسار استرداد النقدية المخصصة',409)
        day=cairo_today();month_open(c,day[:7])
        invoice=c.execute('SELECT * FROM billing_invoices WHERE id=?',(credit['invoice_id'],)).fetchone()
        from service_fees import has_active_approvals
        if has_active_approvals(c,invoice['id']):
            fail('اعكس الأتعاب المعتمدة المرتبطة بالفاتورة قبل تخفيضها، ثم راجع الاستحقاقات من جديد',409)
        old_credits=c.execute("SELECT COALESCE(SUM(amount_piasters),0) FROM billing_credit_requests WHERE invoice_id=? AND status='approved'",(invoice['id'],)).fetchone()[0]
        amount=credit['amount_piasters']
        if amount>invoice['total_piasters']-old_credits:fail('Approved credits already use up the invoice',409)
        due=invoice_due(c,invoice['id'])
        ar_part=min(amount,due)
        owed_part=amount-ar_part
        lines=[(ledger.account_by_code(c,'4195'),amount,0,None)]
        if ar_part:lines.append((ledger.account_by_code(c,'1200'),0,ar_part,None))
        if owed_part:lines.append((ledger.account_by_code(c,'2310'),0,owed_part,None))
        journal=ledger._journal(c,entry_date=day,memo='Credit note '+credit['credit_no'],
          origin='manual',source_id=None,created_by=credit['requested_by'],reviewed_by=user['id'],lines=lines)
        c.execute("UPDATE billing_credit_requests SET status='approved',decided_by=?,decided_at=?,decision_note=?,journal_id=? WHERE id=?",
                  (user['id'],stamp(),note,journal,credit_id))
        audit(c,user['id'],'billing_credit_approved','billing_credit',credit_id,
              {'journal_id':journal,'ar_reversed_piasters':ar_part,'refundable_piasters':owed_part})
    return {'id':credit_id,'status':'approved','journal_id':journal,
            'new_invoice_due_piasters':invoice_due(c,invoice['id']),
            'refundable_credit_piasters':refundable_credit(c,credit['case_id'])}


@router.post('/cases/{case_id}/refunds')
def request_refund(case_id:int,body:RefundRequestForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','clerk')
    amount=c_piasters(body.amount)
    key=request_key(body.request_id)
    reason=trim(body.reason,'reason',8,500)
    payload={'case_id':case_id,'point_id':body.point_id,'source':body.source,
             'method':body.method,'amount':amount,'reason':reason}
    with c:
        c.execute('BEGIN IMMEDIATE')
        previous,fingerprint=repeat(c,key,'refund_request',user['id'],payload)
        if previous:return {'id':previous,'replayed':True}
        case=case_scope(c,user,case_id,write=True)
        if case['status']!='open':fail('الحالة مصفاة ماليًا؛ يمنع طلب استرداد جديد بالطريقة العادية',409)
        if body.point_id!=case['default_point_id']:fail('Refund at another station needs a central review workflow',403)
        can_point(c,user,body.point_id,write=True)
        if amount>refund_available(c,case_id,body.source)-pending_refunds(c,case_id,body.source):
            fail('Refund exceeds free refundable balance',409)
        if amount>refund_capacity(c,case_id,body.source,body.method)-pending_refunds(c,case_id,body.source,body.method):
            fail('Refund method exceeds original patient receipts',409)
        cur=c.execute('''INSERT INTO billing_refund_requests(refund_no,case_id,point_id,source,method,
               amount_piasters,reason,requested_by,requested_at) VALUES (?,?,?,?,?,?,?,?,?)''',
             ('RF-'+secrets.token_hex(8),case_id,body.point_id,body.source,body.method,
              amount,reason,user['id'],stamp()))
        remember(c,key,'refund_request',user['id'],fingerprint,cur.lastrowid)
        audit(c,user['id'],'billing_refund_requested','billing_refund',cur.lastrowid,{'amount':amount})
    return {'id':cur.lastrowid,'status':'pending','amount_piasters':amount}


@router.post('/refunds/{refund_id}/decision')
def refund_decision(refund_id:int,body:RefundDecisionForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    with c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM billing_refund_requests WHERE id=?',(refund_id,)).fetchone()
        if not row:fail('Refund request not found',404)
        case=case_scope(c,user,row['case_id'])
        if case['status']!='open':fail('الحالة مصفاة ماليًا؛ لا يمكن اعتماد رد جديد',409)
        if row['status']!='pending':fail('Already decided',409)
        if row['requested_by']==user['id']:fail('Requester cannot approve own refund',403)
        note=trim(body.note,'note',0,500)
        if body.decision=='approve':
            reserve=pending_refunds(c,row['case_id'],row['source'])
            methodreserve=pending_refunds(c,row['case_id'],row['source'],row['method'])
            if row['amount_piasters']>refund_available(c,row['case_id'],row['source'])-reserve:
                fail('Insufficient unreserved refundable balance',409)
            if row['amount_piasters']>refund_capacity(c,row['case_id'],row['source'],row['method'])-methodreserve:
                fail('Refund request over allowed payment method',409)
        c.execute('''UPDATE billing_refund_requests SET status=?,decided_by=?,decided_at=?,decision_note=? WHERE id=?''',
                  ('approved' if body.decision=='approve' else 'rejected',user['id'],stamp(),note,refund_id))
        audit(c,user['id'],'billing_refund_'+body.decision,'billing_refund',refund_id,{'note':note})
    return {'id':refund_id,'status':'approved' if body.decision=='approve' else 'rejected'}


@router.post('/refunds/{refund_id}/pay')
def pay_refund(refund_id:int,body:RefundPayForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','clerk')
    key=request_key(body.request_id)
    with c:
        c.execute('BEGIN IMMEDIATE')
        previous,fingerprint=repeat(c,key,'refund_pay',user['id'],{'refund_id':refund_id})
        if previous:return {'id':previous,'replayed':True}
        req=c.execute('SELECT * FROM billing_refund_requests WHERE id=?',(refund_id,)).fetchone()
        if not req:fail('Refund not found',404)
        if req['status']!='approved':fail('Refund not approved or was already paid',409)
        if c.execute('SELECT status FROM billing_cases WHERE id=?',(req['case_id'],)).fetchone()[0]!='open':
            fail('الحالة مصفاة ماليًا؛ يمنع الصرف خارج مسار التصحيح',409)
        if req['decided_by']==user['id']:
            fail('Refund payer cannot approve own refund',403)
        point,shift=current_point_shift(c,req['point_id'],user)
        day=shift['business_date'];month_open(c,day[:7]);amount=req['amount_piasters']
        if amount>refund_available(c,req['case_id'],req['source']):
            fail('Refundable balance was used by another operation',409)
        if amount>refund_capacity(c,req['case_id'],req['source'],req['method']):
            fail('Payment method refundable amount was exhausted',409)
        if req['method']=='cash':fund_id=point['fund_id']
        else:
            row=c.execute('SELECT fund_id FROM billing_payment_channels WHERE method=?',(req['method'],)).fetchone()
            if not row:fail('Clearing account is not configured for refund',409)
            fund_id=row['fund_id']
        catcode='billing_credit_refund' if req['source']=='credit' else 'billing_advance_refund'
        category=c.execute('SELECT id FROM categories WHERE code=?',(catcode,)).fetchone()
        if not category:fail('Refund category not configured',500)
        voucher_no='RFV-'+secrets.token_hex(8)
        cur=c.execute('''INSERT INTO vouchers(voucher_no,date,kind,category_id,from_fund_id,
              shift,amount_piasters,description,reference_no,status,created_by,reviewed_by,created_at,reviewed_at)
              VALUES (?,?, 'payment',?,?,?,?,?,?, 'pending',?,?,?,?)''',
              (voucher_no,day,category['id'],fund_id,'central',amount,
               'Approved patient refund '+req['refund_no'],req['refund_no'],user['id'],req['decided_by'],stamp(),stamp()))
        v=c.execute('SELECT * FROM vouchers WHERE id=?',(cur.lastrowid,)).fetchone()
        book_movements(c,v)
        ledger.post_voucher(c,v,req['decided_by'])
        c.execute("UPDATE vouchers SET status='approved' WHERE id=?",(v['id'],))
        c.execute('''UPDATE billing_refund_requests SET status='paid',paid_by=?,paid_at=?,paid_shift_id=?,voucher_id=?
            WHERE id=?''',(user['id'],stamp(),shift['id'],v['id'],refund_id))
        remember(c,key,'refund_pay',user['id'],fingerprint,refund_id)
        audit(c,user['id'],'billing_refund_paid','billing_refund',refund_id,
              {'voucher_id':v['id'],'shift_id':shift['id'],'amount_piasters':amount})
    return {'id':refund_id,'status':'paid','voucher_id':v['id'],'amount_piasters':amount}


@router.get('/cases/{case_id}/adjustments')
def case_adjustments(case_id:int,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    case_scope(c,user,case_id)
    credits=[dict(x) for x in c.execute('''SELECT id,credit_no,invoice_id,amount_piasters,reason,status,
        requested_by,decided_by,requested_at FROM billing_credit_requests WHERE case_id=? ORDER BY id DESC''',(case_id,))]
    refunds=[dict(x) for x in c.execute('''SELECT id,refund_no,source,method,amount_piasters,reason,status,
        requested_by,decided_by,paid_by FROM billing_refund_requests WHERE case_id=? ORDER BY id DESC''',(case_id,))]
    return {'credits':credits,'refunds':refunds,
            'credit_refundable_piasters':refundable_credit(c,case_id),
            'advance_refundable_piasters':available_advance(c,case_id),
            'notice':'TEST ONLY. No regulatory invoice or insurance payout status.'}
