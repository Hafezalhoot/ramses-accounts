"""Station-specific, date-effective planning (read-only to cash ledger)."""
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
import sqlite3
import cashier_ops
from app import db, get_user, require, fail, audit, valid_date

router=APIRouter(prefix='/api/cashier',tags=['Cashier operations'])

class Slot(BaseModel):
    code: str
    name: str
    start: str

class PlanRequest(BaseModel):
    point_id: int
    effective_from: str
    slots: list[Slot] = Field(min_length=1,max_length=24)
    operating_days: list[int] = Field(default_factory=lambda:list(range(7)))
    reason: str = ''

class PolicyRequest(BaseModel):
    grace_minutes: int = Field(ge=0,le=10080)
    require_shift_image: bool = False
    require_envelope_image: bool = False

class PointStatusRequest(BaseModel):
    effective_from: str
    enabled: bool
    reason: str = ''

class NewCashierPoint(BaseModel):
    code: str
    name: str
    fund_id: int | None = None
    slots: list[Slot] = Field(min_length=1,max_length=24)
    operating_days: list[int] = Field(default_factory=lambda:list(range(7)))
    reason: str


@router.post('/points')
def create_cashier_point(body:NewCashierPoint,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    """A satellite till can be introduced without rewriting past schedules.

    The unique internal central treasury remains the destination of external
    deposits; adding a second 'central' treasury requires a separate design.
    """
    import re
    require(user,'owner')
    code=body.code.strip().upper()
    name=body.name.strip()
    if not re.fullmatch(r'[A-Z][A-Z0-9_]{2,31}',code):fail('كود نقطة الكاشير غير صالح')
    if not 3<=len(name)<=100 or any(ord(x)<32 for x in name):fail('اسم نقطة الكاشير غير صالح')
    if len(body.reason.strip())<8 or len(body.reason)>250:fail('سبب إنشاء النقطة مطلوب')
    if not body.operating_days or len(set(body.operating_days))!=len(body.operating_days) or any(d not in range(7) for d in body.operating_days):
        fail('أيام التشغيل غير صحيحة')
    try:slots=cashier_ops.validate_slots([r.model_dump() for r in body.slots])
    except (ValueError,KeyError) as e:fail(str(e))
    day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
    with c:
        c.execute('BEGIN IMMEDIATE')
        if body.fund_id is not None:
            fund=c.execute('SELECT id,kind,active FROM funds WHERE id=?',(body.fund_id,)).fetchone()
            if not fund or fund['kind']!='cash' or not fund['active']:
                fail('نقطة الكاشير يجب أن ترتبط بخزنة نقدية نشطة',409)
            if c.execute('SELECT 1 FROM billing_points WHERE fund_id=?',(body.fund_id,)).fetchone():
                fail('هذه الخزنة مستخدمة بالفعل في نقطة تحصيل أخرى',409)
            if c.execute('SELECT 1 FROM fund_movements WHERE fund_id=?',(body.fund_id,)).fetchone() or c.execute('SELECT 1 FROM shift_sessions WHERE fund_id=?',(body.fund_id,)).fetchone():
                fail('الخزنة لها سجل مالي سابق؛ يلزم ترحيل عهدة مصرح بدل الربط المباشر',409)
        enabled=body.fund_id is not None
        try:
            cur=c.execute('INSERT INTO billing_points(code,name,kind,fund_id,active) VALUES (?,?,?,?,?)',
                          (code,name,'external',body.fund_id,int(enabled)))
        except sqlite3.IntegrityError:fail('الكود أو الاسم مسجل لنقطة أخرى',409)
        pid=cur.lastrowid
        version=cashier_ops.add_version(c,pid,day,slots,user['id'],body.reason.strip())
        c.execute('UPDATE cashier_schedule_versions SET operating_days=? WHERE id=?',
                  (''.join(map(str,sorted(body.operating_days))),version))
        c.execute('INSERT INTO cashier_point_lifecycle(point_id,starts_on,enabled) VALUES (?,?,?)',
                  (pid,day,int(enabled)))
        c.execute('INSERT INTO cashier_point_policies(point_id) VALUES (?)',(pid,))
        audit(c,user['id'],'cashier_point_created','billing_point',pid,
              {'code':code,'name':name,'fund_id':body.fund_id,'enabled':enabled,
               'slots':slots,'reason':body.reason.strip()})
    return {'id':pid,'code':code,'name':name,'fund_id':body.fund_id,
            'status':'active' if enabled else 'inactive_until_fund_assigned',
            'schedule_version_id':version}


@router.get('/plans')
def plans(user=Depends(get_user), c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    from app import reviewer_shift_scope_sql
    scoped,scope_args=reviewer_shift_scope_sql(user,'p')
    points=[]
    for p in c.execute('SELECT p.* FROM billing_points p WHERE '+scoped+' ORDER BY p.id',scope_args):
        if user['role']=='clerk' and not c.execute('SELECT 1 FROM billing_point_access WHERE user_id=? AND point_id=? AND active=1',(user['id'],p['id'])).fetchone():
            continue
        policies=c.execute('SELECT * FROM cashier_point_policies WHERE point_id=?',(p['id'],)).fetchone()
        versions=[]
        for v in c.execute('SELECT * FROM cashier_schedule_versions WHERE point_id=? ORDER BY starts_on',(p['id'],)):
            slots=[{'code':x['code'],'name':x['name'],'start':f"{x['start_minute']//60:02d}:{x['start_minute']%60:02d}"}
                  for x in c.execute('SELECT * FROM cashier_schedule_slots WHERE version_id=? ORDER BY start_minute',(v['id'],))]
            versions.append({'id':v['id'],'effective_from':v['starts_on'],'operating_days':[int(d) for d in v['operating_days']], 'slots':slots,'reason':v['reason']})
        lifecycle=[{'effective_from':r['starts_on'],'enabled':bool(r['enabled'])} for r in c.execute(
            'SELECT * FROM cashier_point_lifecycle WHERE point_id=? ORDER BY starts_on',(p['id'],))]
        points.append({'id':p['id'],'code':p['code'],'name':p['name'],'kind':p['kind'],
                       'fund_id':p['fund_id'],'active':cashier_ops.point_enabled(c,p['id'],datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()),
                       'policy':dict(policies) if policies else None,'versions':versions,'lifecycle':lifecycle})
    return {'points':points,'current_date':datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat(),
            'rules':'A new effective date cannot change existing sessions or historic missing alerts.'}

@router.post('/plans')
def put_plan(body:PlanRequest,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    when=valid_date(body.effective_from).isoformat()
    today=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
    if when<today:fail('لا يمكن تعديل الجدول بأثر رجعي')
    if len(body.reason.strip())<5 or len(body.reason)>250:fail('سبب تغيير الجدول مطلوب (5 أحرف على الأقل)')
    if not body.operating_days or len(set(body.operating_days))!=len(body.operating_days) or any(d<0 or d>6 for d in body.operating_days):
        fail('أيام التشغيل يجب أن تكون أرقام 0–6 دون تكرار')
    try: cleaned=cashier_ops.validate_slots([s.model_dump() for s in body.slots])
    except (ValueError,KeyError) as e:fail(str(e))
    with c:
        c.execute('BEGIN IMMEDIATE')
        point=c.execute('SELECT * FROM billing_points WHERE id=?',(body.point_id,)).fetchone()
        if not point:fail('نقطة التحصيل غير موجودة',404)
        latest=c.execute('SELECT MAX(starts_on) FROM cashier_schedule_versions WHERE point_id=?',(body.point_id,)).fetchone()[0]
        if latest and when<=latest:fail('اختر تاريخ سريان أحدث من آخر إصدار محفوظ للجدول',409)
        if c.execute('SELECT 1 FROM shift_sessions WHERE point_id=? AND business_date>=? LIMIT 1',(point['id'],when)).fetchone():
            fail('توجد ورديات مسجلة تبدأ من التاريخ المطلوب؛ لا يمكن تغيير جدولها',409)
        if not cashier_ops.point_enabled(c,point['id'],when):
            fail('النقطة متوقفة في تاريخ السريان؛ شغّلها أولاً',409)
        version=cashier_ops.add_version(c,point['id'],when,cleaned,user['id'],body.reason.strip())
        c.execute('UPDATE cashier_schedule_versions SET operating_days=? WHERE id=?',(''.join(map(str,sorted(body.operating_days))),version))
        audit(c,user['id'],'cashier_schedule_effective','billing_point',point['id'],
              {'version_id':version,'effective_from':when,'slots':cleaned,'operating_days':body.operating_days,'reason':body.reason.strip()})
    return {'version_id':version,'point_id':body.point_id,'effective_from':when,'slots':len(cleaned)}

@router.post('/points/{point_id}/policy')
def point_policy(point_id:int,body:PolicyRequest,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    with c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM billing_points WHERE id=?',(point_id,)).fetchone():fail('نقطة التحصيل غير موجودة',404)
        c.execute('''INSERT INTO cashier_point_policies(point_id,grace_minutes,require_shift_image,require_envelope_image)
                     VALUES (?,?,?,?) ON CONFLICT(point_id) DO UPDATE SET grace_minutes=excluded.grace_minutes,
                     require_shift_image=excluded.require_shift_image,require_envelope_image=excluded.require_envelope_image''',
                  (point_id,body.grace_minutes,int(body.require_shift_image),int(body.require_envelope_image)))
        audit(c,user['id'],'cashier_policy_changed','billing_point',point_id,body.model_dump())
    return {'ok':True}

@router.post('/points/{point_id}/status')
def point_status(point_id:int,body:PointStatusRequest,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    when=valid_date(body.effective_from).isoformat()
    today=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
    if when<today:fail('لا يمكن تغيير التشغيل بأثر رجعي')
    if len(body.reason.strip())<5:fail('سبب تغيير حالة النقطة مطلوب')
    with c:
        c.execute('BEGIN IMMEDIATE')
        point=c.execute('SELECT * FROM billing_points WHERE id=?',(point_id,)).fetchone()
        if not point:fail('نقطة التحصيل غير موجودة',404)
        if body.enabled:
            fund=c.execute('SELECT kind,active FROM funds WHERE id=?',(point['fund_id'],)).fetchone() if point['fund_id'] else None
            if not fund or fund['kind']!='cash' or not fund['active']:
                fail('لا يمكن تشغيل نقطة تحصيل بلا خزنة نقدية نشطة مخصصة لها',409)
        last=c.execute('SELECT MAX(starts_on) FROM cashier_point_lifecycle WHERE point_id=?',(point_id,)).fetchone()[0]
        if last and when<=last:fail('تاريخ الحالة الجديدة يجب أن يلي آخر تاريخ معتمد',409)
        # Historical submitted shifts remain visible and reviewable after future deactivation;
        # only a physically open shift makes a new shutdown unsafe.
        if not body.enabled and c.execute("""SELECT 1 FROM shift_sessions WHERE point_id=? AND status='open'
            AND (business_date>=? OR substr(COALESCE(scheduled_end_at,''),1,10)>?) LIMIT 1""",
            (point_id,when,when)).fetchone():
            fail('لا يمكن إيقاف نقطة إذا كان هناك شيفت مفتوح متداخل مع تاريخ الإيقاف؛ سلّم العهدة أولًا',409)
        c.execute('INSERT INTO cashier_point_lifecycle(point_id,starts_on,enabled) VALUES (?,?,?)',(point_id,when,int(body.enabled)))
        if when==today:c.execute('UPDATE billing_points SET active=? WHERE id=?',(int(body.enabled),point_id))
        audit(c,user['id'],'cashier_point_status','billing_point',point_id,{'effective_from':when,'enabled':body.enabled,'reason':body.reason.strip()})
    return {'ok':True}

class VariancePermissionRequest(BaseModel):
    user_id: int
    can_approve: bool
    reason: str

@router.get('/variance-permissions')
def variance_permissions(user=Depends(get_user), c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    return [dict(r) for r in c.execute('''SELECT u.id user_id,u.username,u.role,u.active,
            COALESCE(p.can_approve,0) can_approve,p.changed_at
            FROM users u LEFT JOIN cashier_variance_permissions p ON p.user_id=u.id
            WHERE u.role='reviewer' ORDER BY u.id''')]

@router.post('/variance-permissions')
def set_variance_permission(body:VariancePermissionRequest,user=Depends(get_user),
                            c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    if not 8<=len(body.reason.strip())<=400:
        fail('اكتب سبب التفويض أو سحبه بوضوح')
    with c:
        c.execute('BEGIN IMMEDIATE')
        target=c.execute('SELECT id,role,active FROM users WHERE id=?',(body.user_id,)).fetchone()
        if not target or target['role']!='reviewer' or not target['active']:
            fail('التفويض المالي الحساس متاح للمراجع المحاسبي النشط فقط',400)
        c.execute('''INSERT INTO cashier_variance_permissions(user_id,can_approve,changed_by,changed_at)
                     VALUES (?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
                     can_approve=excluded.can_approve,changed_by=excluded.changed_by,
                     changed_at=excluded.changed_at''',
                  (body.user_id,int(body.can_approve),user['id'],datetime.now(ZoneInfo('UTC')).isoformat()))
        audit(c,user['id'],'cashier_variance_permission','user',body.user_id,
              {'can_approve':body.can_approve,'reason':body.reason.strip()})
    return {'user_id':body.user_id,'can_approve':body.can_approve}

class TreasuryDepositRequest(BaseModel):
    source_shift_id: int
    amount: str
    note: str = ''

@router.get('/treasury-deposits')
def list_treasury_deposits(month:str='',user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    from app import valid_month, current_month, reviewer_shift_scope_sql
    month=valid_month(month or current_month())
    where='substr(v.date,1,7)=?';args=[month]
    if user['role']=='clerk':where+=' AND t.received_by=?';args.append(user['id'])
    elif user['role']=='reviewer':
        scoped,scope_args=reviewer_shift_scope_sql(user)
        where+=' AND '+scoped
        args.extend(scope_args)
    return [dict(r) for r in c.execute('''SELECT t.id,t.source_shift_id,t.target_shift_id,
         t.amount_piasters,t.voucher_id,t.received_by,t.received_at,t.note,v.voucher_no,
         s.business_date source_day,s.shift source_shift
         FROM cashier_treasury_transfers t JOIN vouchers v ON v.id=t.voucher_id
         JOIN shift_sessions s ON s.id=t.source_shift_id
         WHERE '''+where+' ORDER BY t.id DESC LIMIT 100',args)]

@router.post('/treasury-deposits')
def treasury_deposit(body:TreasuryDepositRequest,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    """Receive cash already independently counted/accepted from an external till.

    Does NOT issue a patient receipt, does NOT amend the sealed source shift count.
    The actual central-treasury cashier records the real physical acceptance.
    """
    require(user,'owner','reviewer','clerk')
    from app import c_piasters, month_open, stamp, fund_balance
    import secrets
    import ledger
    amt=c_piasters(body.amount)
    note=body.note.strip()
    if not 8<=len(note)<=400:fail('اكتب مرجع التوريدة أو محضر التسليم')
    now_cairo=datetime.now(ZoneInfo('Africa/Cairo'))
    day=now_cairo.date().isoformat()
    with c:
        c.execute('BEGIN IMMEDIATE')
        month_open(c,day[:7])
        source=c.execute('''SELECT s.*,p.id point_id,p.kind point_kind
                  FROM shift_sessions s JOIN billing_points p ON p.fund_id=s.fund_id
                  WHERE s.id=?''',(body.source_shift_id,)).fetchone()
        if not source or source['point_kind']!='external' or source['status'] not in ('submitted','closed'):
            fail('التوريدة تتطلب جردًا سابقًا مثبتًا لكاشير خارجي',409)
        if user['role']=='reviewer':
            from app import require_reviewer_shift_fund
            require_reviewer_shift_fund(c,user,source['fund_id'])
        handoff=c.execute('''SELECT * FROM shift_handoffs
                WHERE shift_session_id=? AND count_version=? AND decision='accepted' ORDER BY id DESC LIMIT 1''',
                (source['id'],source['count_version'])).fetchone()
        if not handoff or handoff['received_by']!=user['id']:
            fail('لا يحق توريد النقدية إلا للمستلم الفعلي الذي أقر الجرد المستقل',403)
        # Receipt must belong to the current open treasury shift, not a past period.
        destination=c.execute('''SELECT s.*,p.id point_id,p.kind point_kind
             FROM shift_sessions s JOIN billing_points p ON p.fund_id=s.fund_id
             WHERE p.kind='internal' AND s.status='open' AND s.business_date=?
             ORDER BY s.id DESC LIMIT 1''',(day,)).fetchone()
        if not destination or destination['responsible_id']!=user['id']:
            fail('مستلم التوريدة لازم يكون صاحب وردية الخزنة الرئيسية المفتوحة اليوم',403)
        if destination['fund_id']==source['fund_id']:fail('يجب أن تكون الخزنتان مستقلتين',409)
        # A later external shift means its owner now holds the drawer. We cannot
        # retrospectively move the earlier person's money on their behalf.
        if c.execute('''SELECT 1 FROM shift_sessions WHERE fund_id=? AND id>?
                LIMIT 1''',(source['fund_id'],source['id'])).fetchone():
            fail('توجد وردية خارجية لاحقة؛ استخدم دورة توريد عهدتها الحالية',409)
        transferred=c.execute('''SELECT COALESCE(SUM(amount_piasters),0) FROM cashier_treasury_transfers
                  WHERE source_shift_id=?''',(source['id'],)).fetchone()[0]
        if transferred+amt>source['counted_piasters']:
            fail('قيمة التوريدة تتجاوز المبلغ الفعلي المستلم بعد الجرد',409)
        if fund_balance(c,source['fund_id'])<amt:
            fail('رصيد النقدية الخارجية المحاسبي لا يكفي للتوريدة',409)
        if source['submitted_by']==user['id']:
            fail('المستلم لا يجوز أن يكون مسلّم الوردية نفسها',403)
        from app import stamp
        cur=c.execute('''INSERT INTO vouchers(voucher_no,date,kind,from_fund_id,to_fund_id,
              shift,amount_piasters,description,reference_no,status,created_by,
              reviewed_by,created_at,reviewed_at,review_reason)
              VALUES (?,?,?,?,?,'central',?,?,?,'approved',?,?,?,?,?)''',
            ('PENDING-'+secrets.token_hex(6),day,'transfer',source['fund_id'],destination['fund_id'],
             amt,'توريدة كاشير خارجي إلى الخزنة العامة؛ '+note,
             'CASH-SHIFT-'+str(source['id']),source['submitted_by'],user['id'],stamp(),stamp(),note))
        v_id=cur.lastrowid
        c.execute('UPDATE vouchers SET voucher_no=? WHERE id=?',(f'CASH-{day[:4]}-{v_id:06d}',v_id))
        c.execute('''INSERT INTO fund_movements(voucher_id,fund_id,amount_piasters,booked_on,shift_session_id)
                     VALUES (?,?,?,?,NULL)''',(v_id,source['fund_id'],-amt,day))
        c.execute('''INSERT INTO fund_movements(voucher_id,fund_id,amount_piasters,booked_on,shift_session_id)
                     VALUES (?,?,?,?,?)''',(v_id,destination['fund_id'],amt,day,destination['id']))
        ledger.post_voucher(c,c.execute('SELECT * FROM vouchers WHERE id=?',(v_id,)).fetchone(),user['id'])
        c.execute('''INSERT INTO cashier_treasury_transfers(source_shift_id,target_shift_id,
                    handoff_id,amount_piasters,voucher_id,received_by,received_at,note)
                    VALUES (?,?,?,?,?,?,?,?)''',
                  (source['id'],destination['id'],handoff['id'],amt,v_id,user['id'],stamp(),note))
        audit(c,user['id'],'cashier_treasury_received','shift',source['id'],
              {'central_shift_id':destination['id'],'amount_piasters':amt,'voucher_id':v_id})
    return {'status':'received','voucher_id':v_id,'amount_piasters':amt,
            'source_shift_id':source['id'],'central_shift_id':destination['id']}

# Evidence is kept inside the same SQLite backup as its financial records.
# A report/envelope photo never changes the patient's bill or booked cash.
from fastapi import UploadFile,File
from fastapi.responses import Response
from pathlib import Path
from hashlib import sha256
from urllib.parse import quote


def attachment_shift_scope(c,shift_id,user,for_upload=False):
    row=c.execute('SELECT * FROM shift_sessions WHERE id=?',(shift_id,)).fetchone()
    if not row:fail('الوردية غير موجودة',404)
    if user['role']=='viewer' or (user['role']=='clerk' and row['responsible_id']!=user['id']):
        fail('مرفقات الجرد لصاحب الوردية والمراجع المخول فقط',403)
    if user['role']=='reviewer':
        from app import require_reviewer_shift_fund
        require_reviewer_shift_fund(c,user,row['fund_id'])
    if for_upload and row['status']=='closed':fail('لا يمكن تغيير إثباتات وردية أُقفلت',409)
    return row

@router.get('/shifts/{shift_id}/attachments')
def shift_attachments(shift_id:int,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    attachment_shift_scope(c,shift_id,user)
    return [dict(r) for r in c.execute('''SELECT id,kind,file_name,media_type,file_size,sha256,
        uploaded_by,created_at FROM cashier_shift_attachments WHERE shift_session_id=? ORDER BY id''',(shift_id,))]

@router.post('/shifts/{shift_id}/attachments/{kind}')
def upload_shift_attachment(shift_id:int,kind:str,file:UploadFile=File(...),
                            user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    if kind not in ('report','envelope'):fail('نوع المرفق غير معروف')
    from app import checked_evidence,MAX_EVIDENCE_BYTES,stamp
    name=Path((file.filename or '').replace('\\','/')).name.strip()
    if not name or len(name)>100 or any(ord(ch)<32 for ch in name):fail('اسم الملف غير صالح')
    data=file.file.read(MAX_EVIDENCE_BYTES+1)
    file.file.close()
    if not data or len(data)>MAX_EVIDENCE_BYTES:fail('حجم المرفق غير صالح أو يتجاوز 6 ميجابايت',413)
    media=checked_evidence(name,data)
    digest=sha256(data).hexdigest()
    with c:
        c.execute('BEGIN IMMEDIATE')
        attachment_shift_scope(c,shift_id,user,for_upload=True)
        if c.execute('SELECT COUNT(*) FROM cashier_shift_attachments WHERE shift_session_id=? AND kind=?',
                     (shift_id,kind)).fetchone()[0]>=4:
            fail('وصلت للحد الأقصى من صور هذا النوع',409)
        if c.execute('''SELECT 1 FROM cashier_shift_attachments WHERE shift_session_id=?
                         AND kind=? AND sha256=?''',(shift_id,kind,digest)).fetchone():
            fail('المرفق مكرر بالفعل',409)
        cur=c.execute('''INSERT INTO cashier_shift_attachments(shift_session_id,kind,file_name,
             media_type,file_size,sha256,content,uploaded_by,created_at) VALUES (?,?,?,?,?,?,?,?,?)''',
             (shift_id,kind,name,media,len(data),digest,data,user['id'],stamp()))
        audit(c,user['id'],'cashier_shift_evidence','shift',shift_id,
              {'attachment_id':cur.lastrowid,'kind':kind,'sha256':digest})
    return {'id':cur.lastrowid,'kind':kind,'size':len(data)}

@router.get('/shift-attachments/{attachment_id}/download')
def download_shift_attachment(attachment_id:int,user=Depends(get_user),
                              c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    r=c.execute('SELECT * FROM cashier_shift_attachments WHERE id=?',(attachment_id,)).fetchone()
    if not r:fail('المرفق غير موجود',404)
    attachment_shift_scope(c,r['shift_session_id'],user)
    return Response(content=r['content'],media_type='application/octet-stream',
         headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(r['file_name']),
                  'X-Content-Type-Options':'nosniff'})

class StaffShiftRule(BaseModel):
    point_id: int
    user_id: int
    allowed_codes: list[str]
    reason: str

@router.get('/staff-access')
def cashier_staff_access(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    records=[]
    for r in c.execute('''SELECT a.point_id,a.user_id,u.username,u.active,
                  COALESCE(r.allowed_codes,NULL) allowed_codes
             FROM billing_point_access a JOIN users u ON u.id=a.user_id
             LEFT JOIN cashier_shift_staff_rules r ON r.point_id=a.point_id AND r.user_id=a.user_id
             WHERE a.active=1 AND u.role='clerk' ORDER BY a.point_id,u.username'''):
        records.append({'point_id':r['point_id'],'user_id':r['user_id'],'username':r['username'],
                        'active':bool(r['active']),
                        'allowed_codes':r['allowed_codes'].split(',') if r['allowed_codes'] is not None else None})
    return records

@router.post('/staff-access')
def update_cashier_staff_rule(body:StaffShiftRule,user=Depends(get_user),
                              c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    if not 8<=len(body.reason.strip())<=400:fail('سبب تعديل صلاحيات الورديات مطلوب')
    if len(body.allowed_codes)>24 or len(body.allowed_codes)!=len(set(body.allowed_codes)):
        fail('أسماء الورديات المحددة مكررة أو كثيرة')
    now=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
    with c:
        c.execute('BEGIN IMMEDIATE')
        r=c.execute('''SELECT 1 FROM billing_point_access a JOIN users u ON u.id=a.user_id
              WHERE a.point_id=? AND a.user_id=? AND a.active=1 AND u.active=1 AND u.role='clerk' ''',
              (body.point_id,body.user_id)).fetchone()
        if not r:fail('اربط الموظف بنقطة الكاشير أولًا من صلاحيات التحصيل',409)
        version=c.execute('''SELECT id FROM cashier_schedule_versions WHERE point_id=?
                  ORDER BY starts_on DESC,id DESC LIMIT 1''',(body.point_id,)).fetchone()
        if not version:fail('جدول النقطة غير موجود',409)
        codes={r[0] for r in c.execute('SELECT code FROM cashier_schedule_slots WHERE version_id=?',(version['id'],))}
        if set(body.allowed_codes)-codes:fail('واحدة أو أكثر من الورديات ليست موجودة في جدول النقطة الأخير',409)
        previous=c.execute('SELECT allowed_codes FROM cashier_shift_staff_rules WHERE point_id=? AND user_id=?',
                           (body.point_id,body.user_id)).fetchone()
        c.execute('''INSERT INTO cashier_shift_staff_rules(point_id,user_id,allowed_codes,changed_by,changed_at)
                 VALUES (?,?,?,?,?) ON CONFLICT(point_id,user_id) DO UPDATE SET
                  allowed_codes=excluded.allowed_codes,changed_by=excluded.changed_by,changed_at=excluded.changed_at''',
                 (body.point_id,body.user_id,','.join(sorted(body.allowed_codes)),user['id'],datetime.now(ZoneInfo('UTC')).isoformat()))
        audit(c,user['id'],'cashier_staff_shift_rights','user',body.user_id,
              {'point_id':body.point_id,'before':previous['allowed_codes'] if previous else None,
               'after':body.allowed_codes,'reason':body.reason.strip()})
    return {'point_id':body.point_id,'user_id':body.user_id,'allowed_codes':body.allowed_codes}


# P4: a cash repayment is a NEW physical cash receipt, NOT patient revenue.
# An approved shortage already placed the discrepancy in GL suspense 1190.
# This receipt clears only that suspense, and is linked to the CURRENT central till.
class ShortageRepaymentForm(BaseModel):
    variance_case_id: int
    amount: str
    receipt_key: str
    evidence_note: str


@router.get('/shortage-repayments')
def shortage_repayments(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    from app import reviewer_shift_scope_sql
    if user['role']=='clerk':
        # The current central-treasury receiver needs to locate the approved
        # shortage by case ID before their first receipt, not only afterwards.
        central=c.execute("""SELECT 1 FROM shift_sessions s JOIN billing_points p ON p.fund_id=s.fund_id
             WHERE s.responsible_id=? AND s.status='open' AND p.kind='internal'
             AND s.business_date=?""",(user['id'],datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat())).fetchone()
        clause='' if central else " AND (s.responsible_id=? OR EXISTS (SELECT 1 FROM cashier_shortage_repayments rp WHERE rp.variance_case_id=vc.id AND rp.recorded_by=?))"
        args=[] if central else [user['id'],user['id']]
    else:
        clause='';args=[]
    if user['role']=='reviewer':
        scoped,scope_args=reviewer_shift_scope_sql(user)
        clause+=' AND '+scoped
        args.extend(scope_args)
    cases=[]
    for r in c.execute('''SELECT vc.id case_id,vc.shift_session_id,vc.status,vc.variance_piasters,
           s.responsible_id,s.business_date,s.shift,
           COALESCE(SUM(rp.amount_piasters),0) repaid_piasters
           FROM shift_variance_cases vc JOIN shift_sessions s ON s.id=vc.shift_session_id
           LEFT JOIN cashier_shortage_repayments rp ON rp.variance_case_id=vc.id
           WHERE vc.variance_piasters<0 AND vc.status='approved' '''+clause+'''
           GROUP BY vc.id ORDER BY vc.id DESC''',args):
        row=dict(r);row['outstanding_piasters']=-r['variance_piasters']-r['repaid_piasters']
        cases.append(row)
    scoped,scope_args=reviewer_shift_scope_sql(user)
    paid=[dict(r) for r in c.execute('''SELECT rp.id,rp.variance_case_id,rp.amount_piasters,
       rp.payer_user_id,rp.central_shift_id,rp.recorded_by,rp.recorded_at,
       rp.voucher_id,v.voucher_no
       FROM cashier_shortage_repayments rp JOIN vouchers v ON v.id=rp.voucher_id
       JOIN shift_variance_cases vc ON vc.id=rp.variance_case_id
       JOIN shift_sessions s ON s.id=vc.shift_session_id
       WHERE '''+scoped+' ORDER BY rp.id DESC LIMIT 100',scope_args)]
    if user['role']=='clerk':
        paid=[r for r in paid if r['recorded_by']==user['id'] or any(x['case_id']==r['variance_case_id'] for x in cases)]
    return {'cases':cases,'receipts':paid,
            'notice':'السداد النقدي لا يعتبر إيراد مرضى ولا ينشئ مديونية على موظف تلقائيًا.'}


@router.post('/shortage-repayments')
def record_shortage_repayment(body:ShortageRepaymentForm,user=Depends(get_user),
                             c:sqlite3.Connection=Depends(db)):
    require(user,'owner','clerk')
    import re,secrets,ledger
    from app import c_piasters,month_open,stamp
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,96}',body.receipt_key):
        fail('رمز الحفظ الآمن غير صحيح')
    amount=c_piasters(body.amount)
    note=body.evidence_note.strip()
    if len(note)<12 or len(note)>500:fail('بيان استلام النقدية يجب أن يكون من 12 إلى 500 حرف')
    now=datetime.now(ZoneInfo('Africa/Cairo'))
    day=now.date().isoformat()
    with c:
        c.execute('BEGIN IMMEDIATE')
        already=c.execute('SELECT * FROM cashier_shortage_repayments WHERE receipt_key=?',(body.receipt_key,)).fetchone()
        if already:
            if (already['recorded_by']!=user['id'] or already['variance_case_id']!=body.variance_case_id or
                already['amount_piasters']!=amount or already['evidence_note']!=note):
                fail('رمز السداد مرتبط بمعاملة مختلفة',409)
            return {'id':already['id'],'voucher_id':already['voucher_id'],'replayed':True}
        case=c.execute('''SELECT vc.*,s.responsible_id FROM shift_variance_cases vc
             JOIN shift_sessions s ON s.id=vc.shift_session_id WHERE vc.id=?''',(body.variance_case_id,)).fetchone()
        if not case or case['status']!='approved' or case['variance_piasters']>=0 or not case['adjustment_voucher_id']:
            fail('يلزم وجود عجز معتمد ومرحّل لحساب العهدة قبل تسجيل السداد',409)
        if case['responsible_id']==user['id']:
            fail('صاحب فرق العهدة لا يجوز له إثبات سداد لنفسه',403)
        paid=c.execute('''SELECT COALESCE(SUM(amount_piasters),0) FROM cashier_shortage_repayments
                          WHERE variance_case_id=?''',(case['id'],)).fetchone()[0]
        if amount> -case['variance_piasters']-paid:
            fail('قيمة السداد تتجاوز العجز المتبقي',409)
        central=c.execute('''SELECT s.*,p.kind AS point_kind FROM shift_sessions s
             JOIN billing_points p ON p.fund_id=s.fund_id
             WHERE p.kind='internal' AND s.status='open' AND s.responsible_id=?
               AND s.business_date=? ORDER BY s.id DESC LIMIT 1''',(user['id'],day)).fetchone()
        if not central or not cashier_ops.point_enabled(c,c.execute('SELECT id FROM billing_points WHERE fund_id=?',(central['fund_id'],)).fetchone()['id'],day):
            fail('يجب أن يُسجل استلام السداد من صاحب وردية الخزنة الرئيسية المفتوحة اليوم',409)
        month_open(c,day[:7])
        cat=c.execute('SELECT id FROM categories WHERE code=? AND active=1',('cash_shortage_recovery',)).fetchone()
        admin=c.execute('SELECT id FROM departments WHERE code=?',('ADMIN',)).fetchone()
        if not cat or not admin:fail('حساب تسوية عجز الخزنة غير مهيأ',409)
        cur=c.execute('''INSERT INTO vouchers(voucher_no,date,kind,department_id,category_id,
              from_fund_id,shift,amount_piasters,description,reference_no,status,
              created_by,reviewed_by,created_at,reviewed_at,review_reason)
              VALUES (?,?,?,?,? ,?,'central',?,?,?,'approved',?,?,?,?,?)''',
           ('PENDING-'+secrets.token_hex(8),day,'receipt',admin['id'],cat['id'],central['fund_id'],
            amount,'سداد نقدي لعجز معتمد محضر '+str(case['id'])+' - '+note,
            'SHORTAGE-'+str(case['id']),user['id'],user['id'],stamp(),stamp(),'تحصيل نقدي فعلي مرتبط بفرق معتمد سابقًا؛ المراجع الأصلي ليس مراجع الإيصال'))
        vid=cur.lastrowid
        c.execute('UPDATE vouchers SET voucher_no=? WHERE id=?',(f'REPAY-{day[:4]}-{vid:06d}',vid))
        c.execute('''INSERT INTO fund_movements(voucher_id,fund_id,amount_piasters,booked_on,shift_session_id)
                     VALUES (?,?,?,?,?)''',(vid,central['fund_id'],amount,day,central['id']))
        ledger.post_voucher(c,c.execute('SELECT * FROM vouchers WHERE id=?',(vid,)).fetchone(),case['decided_by'])
        cur=c.execute('''INSERT INTO cashier_shortage_repayments(variance_case_id,central_shift_id,
             payer_user_id,amount_piasters,receipt_key,evidence_note,recorded_by,recorded_at,voucher_id)
             VALUES (?,?,?,?,?,?,?,?,?)''',
             (case['id'],central['id'],case['responsible_id'],amount,body.receipt_key,note,user['id'],stamp(),vid))
        audit(c,user['id'],'cashier_shortage_repaid','shift_variance_case',case['id'],
              {'repayment_id':cur.lastrowid,'voucher_id':vid,'amount_piasters':amount,
               'central_shift_id':central['id'],'payer_user_id':case['responsible_id']})
        return {'id':cur.lastrowid,'voucher_id':vid,'amount_piasters':amount,
                'remaining_piasters':-case['variance_piasters']-paid-amount,'status':'recorded'}
