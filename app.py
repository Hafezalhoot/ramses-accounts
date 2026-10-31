"""Ramses Accounts V8.1C: shift handoff, patient credits/refunds, provisional ledger.

Financial invariant: all approved vouchers book fund movements atomically;
archived June rows never book movements. No public/anonymous financial API.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import logging
import threading
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field

from bootstrap import DB, connect, hash_password, initialize, now
import ledger
import financial_integrity
import treasury_integrity
import opening_balances
import shift_schedule
import shift_coverage
import cashier_ops

ROOT = Path(__file__).resolve().parent
app = FastAPI(title="Ramses Hospital Accounts", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")
SYNC_LOCK = threading.Lock()
LOG = logging.getLogger("ramses.sync")
SESSION_COOKIE = "ramses_sid"
ROLES = {"owner", "reviewer", "clerk", "viewer"}
SHIFTS = {"morning", "evening", "night", "central"}
MAX_EVIDENCE_BYTES = 6 * 1024 * 1024
MAX_EVIDENCE_PER_VOUCHER = 3
PERIOD_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
PAYROLL_ADDITION_KINDS = {'overtime_premium','paid_leave_credit','bonus','other_addition'}
PAYROLL_DEDUCTION_KINDS = {'lateness_deduction','absence_deduction','other_deduction'}


def fail(msg: str, status: int = 400):
    raise HTTPException(status_code=status, detail=msg)


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def c_piasters(value, *, allow_zero=False):
    try:
        d = Decimal(str(value))
        if not d.is_finite() or d < 0 or (not allow_zero and d == 0):
            fail("المبلغ يجب أن يكون موجبًا")
        cents = d * 100
        if cents != cents.quantize(Decimal("1"), rounding=ROUND_HALF_UP):
            fail("يسمح بحد أقصى رقمين بعد العلامة العشرية")
        if cents > 1000000000000:
            fail("المبلغ يتجاوز الحد المسموح")
        return int(cents)
    except (InvalidOperation, ValueError, TypeError):
        fail("المبلغ غير صالح")


def valid_date(value):
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        fail("التاريخ غير صحيح")


def valid_month(value):
    if not PERIOD_PATTERN.fullmatch(str(value or "")):
        fail("الشهر يجب أن يكون YYYY-MM")
    return value


def current_month():
    return datetime.now(ZoneInfo("Africa/Cairo")).strftime("%Y-%m")


def db():
    c = connect()
    try:
        yield c
    finally:
        c.close()


def verify_password(password, encoded):
    try:
        alg, rounds, salt, digest = encoded.split("$")
        if alg != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt),int(rounds))
        return hmac.compare_digest(candidate,bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False


def get_user(request: Request, c: sqlite3.Connection = Depends(db)):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        fail("مطلوب تسجيل الدخول", 401)
    th = hashlib.sha256(token.encode()).hexdigest()
    row = c.execute("""SELECT users.id,users.username,users.role,users.active,s.csrf
                      FROM sessions s JOIN users ON users.id=s.user_id
                      WHERE s.token_hash=? AND s.expires_at>?""", (th, stamp())).fetchone()
    if not row or not row["active"]:
        fail("انتهت الجلسة؛ سجل الدخول مرة أخرى", 401)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf = request.headers.get("X-CSRF-Token", "")
        if not csrf or not hmac.compare_digest(csrf, row["csrf"]):
            fail("رمز الحماية غير صالح؛ أعد تحميل الصفحة", 403)
    return dict(row)


def require(user, *allowed):
    if user["role"] not in allowed:
        fail("ليست لديك صلاحية لهذه العملية", 403)


def audit(c, actor, action, entity, entity_id, details=None):
    c.execute("INSERT INTO audit_log(actor_id,action,entity,entity_id,details,created_at) VALUES (?,?,?,?,?,?)",
              (actor, action, entity, str(entity_id), json.dumps(details or {},ensure_ascii=False), stamp()))
    c.execute("UPDATE sync_status SET dirty=1,revision=revision+1 WHERE id=1")


def month_open(c, month):
    if c.execute("SELECT 1 FROM periods WHERE period=?", (month,)).fetchone():
        fail("هذا الشهر مغلق؛ لا يمكن تسجيل أو اعتماد حركات فيه", 409)


def authorize_cashbook_fund(c, user, fund_id):
    # Check the current assignment at write time; bank/wallet is opt-in.
    if user['role']=='owner':
        return
    fund=c.execute('SELECT id,kind,active,cash_restricted FROM funds WHERE id=?',(fund_id,)).fetchone()
    if not fund or not fund['active']:
        fail('الخزنة أو الحساب المالي غير متاح',404)
    if fund['kind'] in ('bank','wallet') or (fund['kind']=='cash' and fund['cash_restricted']):
        if not c.execute('''SELECT 1 FROM user_fund_grants g JOIN users u ON u.id=g.user_id
              WHERE g.user_id=? AND g.fund_id=? AND g.can_submit=1 AND u.active=1''',
              (user['id'],fund_id)).fetchone():
            fail('لا تملك تفويضًا لتسجيل سندات على الحساب البنكي/المحفظة المحددة',403)
    if user['role']=='clerk':
        point=c.execute('SELECT id,active FROM billing_points WHERE fund_id=?',(fund_id,)).fetchone()
        if point and (not point['active'] or not c.execute('''SELECT 1 FROM billing_point_access
              WHERE point_id=? AND user_id=? AND active=1''',(point['id'],user['id'])).fetchone()):
            fail('ليس لديك حق استخدام درج نقطة التحصيل هذه',403)


def authorize_bank_review(c, user, fund_id):
    if user['role']=='owner':
        return
    fund=c.execute('SELECT kind,active,cash_restricted FROM funds WHERE id=?',(fund_id,)).fetchone()
    if not fund or not fund['active']:
        fail('الحساب المالي غير متاح',404)
    if fund['kind'] in ('bank','wallet') or (fund['kind']=='cash' and fund['cash_restricted']):
        if not c.execute('''SELECT 1 FROM user_fund_grants
                WHERE user_id=? AND fund_id=? AND can_approve=1''',(user['id'],fund_id)).fetchone():
            fail('المراجع غير مفوّض لاعتماد أو رفض سندات هذا الحساب البنكي/المحفظة',403)


class FundGrantRequest(BaseModel):
    user_id: int = Field(ge=1)
    fund_id: int = Field(ge=1)
    can_submit: bool | None = None
    can_approve: bool | None = None
    reason: str = Field(min_length=8,max_length=400)


@app.get('/api/fund-access')
def fund_access(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    return [dict(r) for r in c.execute('''SELECT g.user_id,u.username,g.fund_id,f.name fund_name,
        f.kind,g.can_submit,g.can_approve,g.changed_at FROM user_fund_grants g
        JOIN users u ON u.id=g.user_id JOIN funds f ON f.id=g.fund_id
        ORDER BY u.username,f.name''')]


@app.post('/api/fund-access')
def set_fund_access(body:FundGrantRequest,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    if body.can_submit is None and body.can_approve is None:
        fail('حدد صلاحية الإنشاء أو الاعتماد المطلوب تغييرها')
    with c:
        c.execute('BEGIN IMMEDIATE')
        target=c.execute('SELECT role,active FROM users WHERE id=?',(body.user_id,)).fetchone()
        fund=c.execute('SELECT id,kind,active FROM funds WHERE id=?',(body.fund_id,)).fetchone()
        if not target or not target['active'] or target['role'] not in ('clerk','reviewer'):
            fail('يمكن منح هذه الصلاحية لموظف أو مراجع نشط فقط',409)
        if body.can_approve and target['role']!='reviewer':
            fail('صلاحية اعتماد السندات مخصصة للمراجعين فقط',403)
        if not fund or not fund['active'] or fund['kind'] not in ('bank','wallet','cash'):
            fail('الحساب المالي غير متاح للتفويض',409)
        old=c.execute('SELECT can_submit,can_approve FROM user_fund_grants WHERE user_id=? AND fund_id=?',
                      (body.user_id,body.fund_id)).fetchone()
        allowed_submit=int(body.can_submit) if body.can_submit is not None else (int(old['can_submit']) if old else 0)
        allowed_approve=int(body.can_approve) if body.can_approve is not None else (int(old['can_approve']) if old else 0)
        c.execute('''INSERT INTO user_fund_grants(user_id,fund_id,can_submit,can_approve,changed_by,changed_at,reason)
            VALUES (?,?,?,?,?,?,?) ON CONFLICT(user_id,fund_id) DO UPDATE SET
            can_submit=excluded.can_submit,can_approve=excluded.can_approve,changed_by=excluded.changed_by,
            changed_at=excluded.changed_at,reason=excluded.reason''',
            (body.user_id,body.fund_id,allowed_submit,allowed_approve,user['id'],stamp(),body.reason.strip()))
        audit(c,user['id'],'change_fund_grant','user',body.user_id,
              {'fund_id':body.fund_id,'can_submit':allowed_submit,'can_approve':allowed_approve,'reason':body.reason.strip()})
    return {'user_id':body.user_id,'fund_id':body.fund_id,'can_submit':bool(allowed_submit),'can_approve':bool(allowed_approve)}


def lookup(c, table, obj_id):
    if obj_id in (None, ""):
        return None
    try:
        row = c.execute(f"SELECT * FROM {table} WHERE id=? AND active=1", (int(obj_id),)).fetchone()
    except (ValueError, TypeError):
        row = None
    if not row:
        fail("اختيار غير صالح: " + table)
    return row


def book_movements(c, voucher, sign=1):
    kind = voucher["kind"]
    amount = int(voucher["amount_piasters"]) * sign
    if kind == "receipt":
        legs = [(voucher["from_fund_id"], amount)]
    elif kind == "payment":
        legs = [(voucher["from_fund_id"], -amount)]
    else:
        legs = [(voucher["from_fund_id"], -amount), (voucher["to_fund_id"], amount)]
    attached_shifts={}
    for fund_id, _ in legs:
        attached_shifts[fund_id]=shift_for_posting(c,fund_id,voucher["date"],voucher["shift"],
                          reversal=voucher["reversal_of_id"] is not None)
    for fund_id, change in legs:
        fund = c.execute("SELECT * FROM funds WHERE id=? AND active=1", (fund_id,)).fetchone()
        if not fund:
            fail("الخزنة غير موجودة أو معطلة")
        balance = fund["opening_piasters"] + c.execute("SELECT coalesce(sum(amount_piasters),0) FROM fund_movements WHERE fund_id=?",(fund_id,)).fetchone()[0]
        if change < 0 and balance+change < 0 and not fund["allow_negative"]:
            fail("الرصيد غير كافٍ في " + fund["name"] + "؛ الرصيد المتاح: " + str(balance/100),409)
        # If a previous shift handed over real cash with a pending shortage,
        # the physical safe amount may be smaller than its GL fund balance.
        linked=attached_shifts[fund_id]
        if change < 0 and linked is not None:
            sh=c.execute('SELECT opening_piasters FROM shift_sessions WHERE id=?',(linked,)).fetchone()
            physically_available=sh['opening_piasters']+c.execute(
                'SELECT COALESCE(SUM(amount_piasters),0) FROM fund_movements WHERE shift_session_id=?',
                (linked,)).fetchone()[0]
            if physically_available+change<0:
                fail('النقدية الفعلية في عهدة الوردية لا تكفي لهذا الصرف',409)
    for fund_id, change in legs:
        c.execute("""INSERT INTO fund_movements(voucher_id,fund_id,amount_piasters,booked_on,shift_session_id)
                  VALUES (?,?,?,?,?)""",
                  (voucher["id"], fund_id, change, voucher["date"], attached_shifts[fund_id]))


def fund_balance(c, fund_id):
    row = c.execute("""SELECT f.opening_piasters + COALESCE(SUM(m.amount_piasters),0) balance
        FROM funds f LEFT JOIN fund_movements m ON m.fund_id=f.id WHERE f.id=? GROUP BY f.id""",
        (fund_id,)).fetchone()
    if row is None:
        fail("الخزنة غير موجودة",404)
    return row["balance"]


def shift_for_posting(c, fund_id, business_date, shift, *, reversal=False):
    """Once a physical fund starts shift tracking, postings require an open shift.

    Central adjustments/reversals belong to the active physical drawer on the
    effective date. An awaiting-review count freezes the whole fund.
    """
    fund=c.execute("SELECT id,kind FROM funds WHERE id=?",(fund_id,)).fetchone()
    if not fund:
        fail("الحساب المالي غير موجود", 404)
    if fund["kind"]=="bank":
        # A signed statement freezes backdated postings, including reversals/transfers.
        if c.execute("""SELECT 1 FROM bank_statement_batches WHERE fund_id=? AND period=?
                          AND status='approved' LIMIT 1""",(fund_id,business_date[:7])).fetchone():
            fail("الحساب البنكي مُطابَق ومُعتمَد لهذا الشهر؛ لا يمكن ترحيل قيد يؤثر عليه",409)
        return None
    if not c.execute("SELECT 1 FROM shift_sessions WHERE fund_id=? LIMIT 1",(fund_id,)).fetchone():
        # A mapped physical cashier drawer requires its first shift before any posting.
        # Unmapped legacy funds preserve their existing migration behavior.
        mapped=c.execute("SELECT 1 FROM billing_points WHERE fund_id=?",(fund_id,)).fetchone()
        if fund["kind"]=="cash" and mapped:
            fail("خزنة الكاشير مرتبطة بنقطة تحصيل؛ افتح وردية قبل أي حركة نقدية",409)
        return None
    active=c.execute("""SELECT * FROM shift_sessions
        WHERE fund_id=? AND status='open'""",(fund_id,)).fetchone()
    if not active or active["status"] != "open" or active["business_date"] != business_date:
        fail("الحساب مربوط بالورديات: افتح وردية اليوم أولًا؛ لا يمكن الترحيل بعد تقديم الجرد",409)
    if not reversal and shift != "central" and active["shift"] != shift:
        fail("وردية السند لا تطابق الوردية المفتوحة لهذا الحساب",409)
    return active["id"]


def voucher_fund_ids(v):
    ids=[v["from_fund_id"]]
    if v["kind"]=="transfer":
        ids.append(v["to_fund_id"])
    return ids


def signed_sql(alias="v"):
    return f"(CASE WHEN {alias}.reversal_of_id IS NOT NULL THEN -1 ELSE 1 END) * {alias}.amount_piasters"


def salary_payments(c, employee_id, period):
    return c.execute(f"""SELECT coalesce(sum({signed_sql('v')}),0) FROM vouchers v
             JOIN categories ca ON ca.id=v.category_id WHERE v.status IN ('approved','reversed')
             AND v.employee_id=? AND v.salary_period=? AND ca.code='salary_payment'""",(employee_id,period)).fetchone()[0]


def outstanding_advance(c, employee_id):
    gross = c.execute(f"""SELECT coalesce(sum({signed_sql('v')}),0) FROM vouchers v
                 JOIN categories ca ON ca.id=v.category_id
                 WHERE v.status IN ('approved','reversed') AND ca.code='salary_advance' AND v.employee_id=?""",(employee_id,)).fetchone()[0]
    allocated = c.execute("SELECT coalesce(sum(amount_piasters),0) FROM advance_allocations WHERE employee_id=?",(employee_id,)).fetchone()[0]
    return gross - allocated


def salary_term_for(c, employee_id, period):
    return c.execute("""SELECT * FROM salary_terms WHERE employee_id=? AND valid_from<=?
        AND (valid_to IS NULL OR valid_to>=?) ORDER BY valid_from DESC,id DESC LIMIT 1""",
        (employee_id,period+'-01',period+'-01')).fetchone()


def hourly_wage(hourly_piasters, minutes):
    # Aggregate minutes for the period, then round ONCE (half up) to the nearest piastre.
    return int((Decimal(hourly_piasters)*Decimal(minutes)/Decimal(60)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))


def work_totals(c, employee_id, period):
    return c.execute("""SELECT
        coalesce(sum(CASE WHEN status='approved' THEN work_minutes ELSE 0 END),0) approved_minutes,
        coalesce(sum(CASE WHEN status='approved' THEN 1 ELSE 0 END),0) approved_count,
        coalesce(sum(CASE WHEN status='pending' THEN 1 ELSE 0 END),0) pending_count
        FROM payroll_work_entries WHERE employee_id=? AND substr(work_date,1,7)=?""",
        (employee_id,period)).fetchone()


def payroll_due(c, employee_id, period):
    accr = c.execute("SELECT net_piasters,signoff_status FROM payroll_accruals WHERE employee_id=? AND period=?",(employee_id,period)).fetchone()
    if not accr or accr['signoff_status'] not in ('approved','legacy'):
        return None
    alloc = c.execute("SELECT coalesce(sum(amount_piasters),0) FROM advance_allocations WHERE employee_id=? AND period=?",(employee_id,period)).fetchone()[0]
    return accr["net_piasters"] - salary_payments(c, employee_id, period) - alloc


class ShiftOpenForm(BaseModel):
    business_date: str
    shift: str
    fund_id: int


class ShiftCountForm(BaseModel):
    counted_amount: str
    note: str = ""
    envelope_present: bool = False


class ShiftReviewForm(BaseModel):
    decision: str
    reason: str = ""

class ShiftScheduleForm(BaseModel):
    starts: dict[str,str]
    enforce_clock: bool = False


class ShiftHandoffForm(BaseModel):
    counted_amount: str
    decision: str = "accept"
    note: str = ""


class VarianceProposal(BaseModel):
    explanation: str


class VarianceResolution(BaseModel):
    decision: str
    reason: str


class LoginForm(BaseModel):
    username: str
    password: str


class VoucherForm(BaseModel):
    date: str
    kind: str
    department_id: int | None = None
    category_id: int | None = None
    from_fund_id: int
    to_fund_id: int | None = None
    shift: str = "central"
    employee_id: int | None = None
    salary_period: str | None = None
    amount: str
    description: str
    reference_no: str = ""
    client_request_id: str | None = None  # stable UUID for safe network retries


class Decision(BaseModel):
    decision: str
    reason: str = ""


class Opening(BaseModel):
    amount: str


class OpeningReviewRequest(BaseModel):
    effective_date: str
    evidence_kind: str
    evidence_reference: str = Field(min_length=6, max_length=140)
    evidence_note: str = Field(min_length=12, max_length=500)
    offset_account_id: int | None = None


class OpeningReviewDecision(BaseModel):
    decision: str
    note: str = Field(min_length=8, max_length=500)


class FundForm(BaseModel):
    code: str
    name: str
    kind: str
    restricted_cash: bool = False  # legacy API callers opt in; the UI defaults to True


class EmployeeForm(BaseModel):
    name: str
    code: str
    job_title: str = ""
    department_id: int | None = None


class SalaryTerm(BaseModel):
    month: str
    pay_type: str = "monthly"
    monthly_salary: str | None = None
    hourly_rate: str | None = None
    note: str = ""


class WorkEntryForm(BaseModel):
    employee_id: int
    work_date: str
    shift: str = "central"
    hours: int = Field(ge=0, le=24)
    minutes: int = Field(ge=0, le=59)
    note: str = ""


class WorkEntryDecision(BaseModel):
    decision: str = ""
    reason: str = ""


class AccrualForm(BaseModel):
    employee_id: int
    period: str
    additions: str = "0"
    deductions: str = "0"


class AccrualCorrection(BaseModel):
    additions: str
    deductions: str
    reason: str


class PayrollAdjustmentForm(BaseModel):
    employee_id: int
    period: str
    kind: str
    amount: str
    note: str


class PayrollDecisionForm(BaseModel):
    decision: str = ""
    reason: str = ""


class AllocationForm(BaseModel):
    employee_id: int
    period: str
    amount: str


class UserForm(BaseModel):
    username: str
    password: str
    role: str


class AccountStatus(BaseModel):
    active: bool


class AccountPassword(BaseModel):
    password: str
    current_password: str = ""


class ClosePeriod(BaseModel):
    period: str


class ReverseForm(BaseModel):
    date: str
    reason: str


@app.get("/")
def homepage():
    return FileResponse(ROOT / "static" / "index.html", headers={"Cache-Control":"no-store"})


@app.get("/health")
def health():
    # Read-only readiness check: never silently create a new empty ledger.
    if not DB.is_file():
        fail("قاعدة البيانات غير متاحة", 503)
    try:
        with sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=2) as c:
            ok = c.execute("SELECT 1 FROM sync_status WHERE id=1").fetchone()
        if not ok:
            fail("قاعدة البيانات غير جاهزة", 503)
    except sqlite3.Error:
        fail("قاعدة البيانات غير جاهزة", 503)
    return {"status":"ok","name":"Ramses Accounts V8.1E G2P Financial Case Clearance - Test Only"}


@app.post("/api/login")
def login(body: LoginForm, response: Response, c: sqlite3.Connection = Depends(db)):
    username = body.username.strip().lower()
    cutoff = (datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat()
    c.execute("DELETE FROM login_attempts WHERE occurred_at<?",(cutoff,))
    cnt = c.execute("SELECT count(*) FROM login_attempts WHERE username=?",(username,)).fetchone()[0]
    if cnt>=5:
        fail("محاولات كثيرة؛ حاول بعد 15 دقيقة",429)
    c.execute("INSERT INTO login_attempts(username,occurred_at) VALUES (?,?)",(username,stamp()))
    row = c.execute("SELECT * FROM users WHERE username=? AND active=1",(username,)).fetchone()
    if not row or not verify_password(body.password, row["password_hash"]):
        fail("اسم المستخدم أو كلمة المرور غير صحيحة",401)
    c.execute("DELETE FROM login_attempts WHERE username=?",(username,))
    token = secrets.token_urlsafe(36)
    csrf = secrets.token_urlsafe(28)
    exp = (datetime.now(timezone.utc)+timedelta(hours=10)).isoformat()
    c.execute("INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES (?,?,?,?)",(hashlib.sha256(token.encode()).hexdigest(),row["id"],csrf,exp))
    response.set_cookie(SESSION_COOKIE,token,httponly=True,secure=os.getenv("RAMSES_SECURE_COOKIES","0")=="1",
                        samesite="strict",max_age=36000,path="/")
    return {"id":row["id"],"username":row["username"],"role":row["role"],"csrf":csrf,"environment":os.getenv("RAMSES_ENVIRONMENT","staging")}


@app.post("/api/logout")
def logout(response: Response, request: Request, user=Depends(get_user), c: sqlite3.Connection=Depends(db)):
    token=request.cookies.get(SESSION_COOKIE,"")
    c.execute("DELETE FROM sessions WHERE token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),))
    response.delete_cookie(SESSION_COOKIE,path="/")
    return {"ok":True}


@app.get("/api/me")
def me(user=Depends(get_user)):
    return {"id":user["id"],"username":user["username"],"role":user["role"],"csrf":user["csrf"],"environment":os.getenv("RAMSES_ENVIRONMENT","staging")}


@app.get("/api/lookups")
def lookups(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    return {"departments":[dict(r) for r in c.execute("SELECT * FROM departments WHERE active=1 ORDER BY id")],
            "categories":[dict(r) for r in c.execute("SELECT * FROM categories WHERE active=1 ORDER BY direction,name")],
            "funds":[dict(r) for r in c.execute("SELECT id,code,name,kind,active FROM funds WHERE active=1 ORDER BY id")],
            "employees":[dict(r) for r in c.execute("SELECT id,code,name,job_title,department_id FROM employees WHERE active=1 ORDER BY name")],
            "shifts":[{"code":a,"name":b} for a,b in (("morning","صباحي"),("evening","مسائي"),("night","سهر"),("central","الحسابات المركزية"))]}


@app.post("/api/vouchers")
def create_voucher(body:VoucherForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner","reviewer","clerk")
    date_value=valid_date(body.date).isoformat(); amt=c_piasters(body.amount)
    if body.kind not in ("receipt","payment","transfer") or body.shift not in SHIFTS:
        fail("نوع الحركة أو الوردية غير صحيح")
    source=lookup(c,"funds",body.from_fund_id)
    if source is None: fail("اختر الخزنة أو الحساب المالي")
    if body.kind=="transfer":
        target=lookup(c,"funds",body.to_fund_id)
        if target is None: fail("اختر حساب التحويل المستلم")
        if source["id"]==target["id"]: fail("الحساب المصدر والوجهة يجب أن يختلفا")
        category_id=None; department_id=None; employee_id=None;salary_period=None
    else:
        dept=lookup(c,"departments",body.department_id)
        cat=lookup(c,"categories",body.category_id)
        if dept is None or cat is None: fail("اختر القسم والتصنيف")
        if cat['code'] in ('billing_invoice_receipt','billing_advance_receipt','billing_credit_refund','billing_advance_refund','cash_shortage_recovery','cash_overage_return','pos_processing_fee'):
            fail('تحصيل فواتير المرضى يتم فقط من شاشة الكاشير المرتبطة بالوردية',403)
        if cat['code']=='late_cash_unallocated':
            if user['role'] not in ('owner','reviewer') or source['kind']!='cash':
                fail('إثبات النقدية غير المخصصة متاح فقط للحسابات المختصة وعلى خزنة نقدية',403)
            if not c.execute('''SELECT 1 FROM billing_points WHERE kind='internal' AND fund_id=? AND active=1''',
                             (source['id'],)).fetchone():
                fail('لا يمكن إثبات النقدية غير المخصصة إلا في الخزنة الرئيسية المرتبطة بالحسابات',409)
            if not body.reference_no.strip():
                fail('رقم الظرف أو كشف الاستلام إلزامي لإثبات النقدية غير المخصصة',409)
            # A suspense receipt is not a shortcut to create fictitious cash.
            # There must already be one independently triaged incident with an
            # EXACT physical count and envelope reference.
            cases=c.execute('''SELECT id FROM late_entry_incidents WHERE
                UPPER(TRIM(source_register_ref))=? AND counted_cash_piasters=?
                AND status='triaged' LIMIT 2''',
                (body.reference_no.strip().upper(),amt)).fetchall()
            if len(cases)!=1:
                fail('إثبات النقدية غير المخصصة يحتاج واقعة واحدة معتمدة للفحص بنفس مرجع الظرف والجرد',409)
        if cat["direction"]!=body.kind:
            fail("التصنيف لا يناسب نوع الحركة")
        category_id=cat["id"];department_id=dept["id"]
        employee_id=None;salary_period=None
        if cat["nature"] in ("payroll_payment","advance"):
            emp=lookup(c,"employees",body.employee_id)
            employee_id=emp["id"]
            if cat["nature"]=="payroll_payment":
                salary_period=valid_month(body.salary_period)
            elif body.salary_period:
                salary_period=valid_month(body.salary_period)
        elif body.employee_id or body.salary_period:
            fail("اختيار الموظف/فترة الراتب متاح فقط للرواتب والسلف")
    description=body.description.strip()
    if len(description)<5 or len(description)>500:
        fail("اكتب بيانًا بين 5 و500 حرف")
    if len(body.reference_no)>100:
        fail("رقم المستند أطول من الحد المسموح")
    request_id = (body.client_request_id or "").strip()
    if request_id and not re.fullmatch(r"[A-Za-z0-9_-]{16,96}", request_id):
        fail("رمز العملية غير صالح")
    target_id = body.to_fund_id if body.kind == "transfer" else None
    fingerprint = hashlib.sha256(json.dumps({
        "date": date_value, "kind": body.kind, "department": department_id,
        "category": category_id, "from": body.from_fund_id, "to": target_id,
        "shift": body.shift, "employee": employee_id, "salary_period": salary_period,
        "amount": amt, "description": description, "reference_no": body.reference_no.strip()
    }, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    with c:
        c.execute("BEGIN IMMEDIATE")
        if request_id:
            previous = c.execute("""SELECT k.payload_hash,k.created_by,v.id,v.voucher_no,v.status
                FROM voucher_request_keys k JOIN vouchers v ON v.id=k.voucher_id
                WHERE k.request_id=?""", (request_id,)).fetchone()
            if previous:
                if previous["created_by"] != user["id"] or previous["payload_hash"] != fingerprint:
                    fail("رمز العملية مستخدم لسند مختلف؛ افتح سندًا جديدًا", 409)
                return {"id":previous["id"],"voucher_no":previous["voucher_no"],
                        "status":previous["status"],"replayed":True}
        if body.kind == 'receipt' and cat['code'] == 'late_cash_unallocated':
            # One physical envelope can enter the cashbook only once. This runs
            # after idempotent replay, inside the same SQLite write transaction.
            duplicate=c.execute('''SELECT v.id FROM vouchers v
                 JOIN funds f ON f.id=v.from_fund_id
                 WHERE v.kind='receipt' AND f.kind='cash'
                   AND v.status IN ('pending','approved')
                   AND UPPER(TRIM(v.reference_no))=? LIMIT 1''',
                   (body.reference_no.strip().upper(),)).fetchone()
            if duplicate:
                fail('هذا الظرف مثبت بالفعل بسند آخر؛ لا يجوز تسجيل النقدية نفسها مرتين',409)
        month_open(c,date_value[:7])
        if c.execute("SELECT 1 FROM billing_payment_channels WHERE method='card' AND fund_id IN (?,?) LIMIT 1",
                     (source['id'],target_id if target_id else -1)).fetchone():
            fail('The POS clearing wallet is reserved for patient card collections and signed POS settlements',409)
        for fund_id in ([source["id"],target_id] if target_id else [source["id"]]):
            authorize_cashbook_fund(c,user,fund_id)
            shift_for_posting(c,fund_id,date_value,body.shift)
        cur=c.execute("""INSERT INTO vouchers(voucher_no,date,kind,department_id,category_id,from_fund_id,to_fund_id,shift,
          employee_id,salary_period,amount_piasters,description,reference_no,status,created_by,created_at)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?,?)""",
          ("PENDING-"+secrets.token_hex(8),date_value,body.kind,department_id,category_id,body.from_fund_id,
           body.to_fund_id if body.kind=="transfer" else None,body.shift,employee_id,salary_period,
           amt,description,body.reference_no.strip(),user["id"],stamp()))
        v_id=cur.lastrowid
        number=f"RAM-{date_value[:4]}-{v_id:06d}"
        c.execute("UPDATE vouchers SET voucher_no=? WHERE id=?",(number,v_id))
        if request_id:
            c.execute("""INSERT INTO voucher_request_keys(request_id,voucher_id,payload_hash,created_by)
                VALUES (?,?,?,?)""", (request_id,v_id,fingerprint,user["id"]))
        audit(c,user["id"],"submit_voucher","voucher",v_id,{"number":number,"amount_piasters":amt,"kind":body.kind})
    return {"id":v_id,"voucher_no":number,"status":"pending"}


def clerk_voucher_scope(alias="v"):
    """Include owner-posted reversals of a clerk's vouchers in the clerk's own ledger.

    Both the original and its reversal are needed for accurate cash totals.
    The caller passes the same user ID for both placeholders.
    """
    return (f"({alias}.created_by=? OR EXISTS (SELECT 1 FROM vouchers original "
            f"WHERE original.id={alias}.reversal_of_id AND original.created_by=?))")


def voucher_filter(c, user, month, department, kind, status, q):
    where=["1=1"];args=[]
    if month:
        valid_month(month);where.append("substr(v.date,1,7)=?");args.append(month)
    if department:
        where.append("v.department_id=?");args.append(int(department))
    if kind:
        if kind not in ("receipt","payment","transfer"): fail("نوع غير صالح")
        where.append("v.kind=?");args.append(kind)
    if status:
        if status not in ("pending","approved","rejected","reversed"): fail("حالة غير صالحة")
        where.append("v.status=?");args.append(status)
    if q:
        where.append("(v.description LIKE ? OR v.voucher_no LIKE ? OR v.reference_no LIKE ?)")
        args.extend(["%"+q[:80]+"%"]*3)
    if user["role"]=="clerk":
        where.append(clerk_voucher_scope());args.extend((user["id"],user["id"]))
    return " AND ".join(where),args


@app.get("/api/vouchers")
def vouchers(month:str="",department:int|None=None,kind:str="",status:str="",q:str="",page:int=1,
             user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    if page<1:fail("صفحة غير صالحة")
    clause,args=voucher_filter(c,user,month,department,kind,status,q)
    base=f"""FROM vouchers v LEFT JOIN departments d ON d.id=v.department_id
       LEFT JOIN categories ca ON ca.id=v.category_id LEFT JOIN employees e ON e.id=v.employee_id
       JOIN funds f ON f.id=v.from_fund_id LEFT JOIN funds tf ON tf.id=v.to_fund_id
       JOIN users u ON u.id=v.created_by WHERE {clause}"""
    count=c.execute("SELECT count(*) "+base,args).fetchone()[0]
    rows=c.execute("""SELECT v.*,d.name department,ca.name category,ca.nature nature,e.name employee,
                f.name from_fund,tf.name to_fund,u.username created_user, (SELECT COUNT(*) FROM voucher_attachments a WHERE a.voucher_id=v.id) attachment_count """+base+" ORDER BY v.date DESC,v.id DESC LIMIT 50 OFFSET ?",args+[(page-1)*50]).fetchall()
    return {"items":[dict(r) for r in rows],"count":count,"page":page,"pages":(count+49)//50}


def attachment_access(c, voucher_id, user):
    require(user, "owner", "reviewer", "clerk")
    v = c.execute("SELECT * FROM vouchers WHERE id=?", (voucher_id,)).fetchone()
    if not v:
        fail("السند غير موجود", 404)
    if user["role"] == "clerk" and v["created_by"] != user["id"]:
        # An owner's reversal is already visible in the original clerk's ledger.
        original=c.execute("SELECT created_by FROM vouchers WHERE id=?",(v["reversal_of_id"],)).fetchone() if v["reversal_of_id"] else None
        if not original or original["created_by"]!=user["id"]:
            fail("ليس لك حق الاطلاع على هذا المستند", 403)
    return v


def checked_evidence(name, data):
    suffix = Path(name).suffix.lower()
    if data.startswith(b"%PDF-") and b"%%EOF" in data[-2048:] and suffix == ".pdf":
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n") and data[-12:-8] == b"\x00\x00\x00\x00" and data[-8:-4] == b"IEND" and suffix == ".png":
        return "image/png"
    if data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9") and suffix in (".jpg", ".jpeg"):
        return "image/jpeg"
    fail("يُقبل PDF أو JPG أو PNG صالح فقط؛ غير مسموح بأنواع الملفات الأخرى")


@app.get("/api/vouchers/{voucher_id}/attachments")
def list_voucher_attachments(voucher_id: int, user=Depends(get_user), c: sqlite3.Connection=Depends(db)):
    attachment_access(c, voucher_id, user)
    return [dict(r) for r in c.execute("""SELECT id,file_name,media_type,file_size,sha256,
        uploaded_by,created_at FROM voucher_attachments WHERE voucher_id=? ORDER BY id""",(voucher_id,))]


@app.post("/api/vouchers/{voucher_id}/attachments")
def upload_voucher_attachment(voucher_id: int, file: UploadFile = File(...),
                                    user=Depends(get_user), c: sqlite3.Connection=Depends(db)):
    # python-multipart/UploadFile provides a streaming spool; read at most the cap +1 byte.
    name=Path((file.filename or "").replace("\\", "/")).name.strip()
    if not name or len(name)>100 or any(ord(ch)<32 for ch in name):
        fail("اسم الملف غير صالح")
    contents=file.file.read(MAX_EVIDENCE_BYTES + 1)
    file.file.close()
    if len(contents)==0 or len(contents)>MAX_EVIDENCE_BYTES:
        fail("الملف فارغ أو حجمه أكبر من 6 ميجابايت",413)
    media=checked_evidence(name, contents)
    digest=hashlib.sha256(contents).hexdigest()
    with c:
        c.execute("BEGIN IMMEDIATE")
        v=attachment_access(c,voucher_id,user)
        if v["created_by"] != user["id"]:
            fail("صاحب السند فقط يرفق المستند الأصلي",403)
        if v["status"] != "pending":
            fail("لا يمكن إضافة مستند إلى سند اتُّخذ فيه قرار",409)
        month_open(c,v["date"][:7])
        if c.execute("SELECT COUNT(*) FROM voucher_attachments WHERE voucher_id=?",(voucher_id,)).fetchone()[0]>=MAX_EVIDENCE_PER_VOUCHER:
            fail("الحد الأقصى ثلاثة مستندات للسند",409)
        try:
            cur=c.execute("""INSERT INTO voucher_attachments
                (voucher_id,file_name,media_type,file_size,sha256,content,uploaded_by,created_at)
                VALUES (?,?,?,?,?,?,?,?)""",(voucher_id,name,media,len(contents),digest,contents,user["id"],stamp()))
        except sqlite3.IntegrityError:
            fail("هذا المستند مرفق بالفعل بالسند",409)
        audit(c,user["id"],"attach_voucher_evidence","voucher",voucher_id,
              {"attachment_id":cur.lastrowid,"sha256":digest,"size":len(contents)})
    return {"id":cur.lastrowid,"file_name":name,"sha256":digest}


@app.get("/api/attachments/{attachment_id}/download")
def download_attachment(attachment_id: int, user=Depends(get_user), c: sqlite3.Connection=Depends(db)):
    doc=c.execute("SELECT * FROM voucher_attachments WHERE id=?",(attachment_id,)).fetchone()
    if not doc:
        fail("المستند غير موجود",404)
    attachment_access(c,doc["voucher_id"],user)
    # Always force download, never render untrusted uploads in the trusted app origin.
    safe_name="evidence-"+str(doc["id"])+Path(doc["file_name"]).suffix.lower()
    return Response(content=doc["content"],media_type="application/octet-stream",headers={
        "Content-Disposition":f'attachment; filename="{safe_name}"',
        "X-Content-Type-Options":"nosniff", "Cache-Control":"no-store",
        "Content-Security-Policy":"sandbox"})


@app.get("/api/reviews")
def reviews(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner","reviewer")
    rows=c.execute("""SELECT v.id,v.voucher_no,v.date,v.kind,v.amount_piasters,v.description,v.created_by,
                 d.name department,ca.name category,u.username created_user, (SELECT COUNT(*) FROM voucher_attachments a WHERE a.voucher_id=v.id) attachment_count
                 FROM vouchers v LEFT JOIN departments d ON d.id=v.department_id
                 LEFT JOIN categories ca ON ca.id=v.category_id JOIN users u ON u.id=v.created_by
                 WHERE v.status='pending' ORDER BY v.created_at,v.id LIMIT 250""").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/vouchers/{voucher_id}/decision")
def decide(voucher_id:int,body:Decision,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner","reviewer")
    if body.decision not in ("approve","reject"): fail("قرار غير صالح")
    if body.decision=="reject" and len(body.reason.strip())<5:
        fail("اذكر سبب الرفض بوضوح")
    with c:
        c.execute("BEGIN IMMEDIATE")
        v=c.execute("SELECT * FROM vouchers WHERE id=?",(voucher_id,)).fetchone()
        if not v: fail("السند غير موجود",404)
        if v["status"]!="pending": fail("السند اتخذ قرارًا بالفعل",409)
        if v["created_by"]==user["id"]: fail("لا يجوز أن يعتمد أو يرفض نفس الشخص السند الذي أدخله",403)
        for fid in (v['from_fund_id'],v['to_fund_id'] if v['kind']=='transfer' else None):
            if fid is not None:
                authorize_bank_review(c,user,fid)
        if c.execute("SELECT 1 FROM billing_payment_channels WHERE method='card' AND fund_id IN (?,?) LIMIT 1",
                     (v['from_fund_id'],v['to_fund_id'] if v['to_fund_id'] else -1)).fetchone():
            fail('A legacy pending voucher cannot bypass the dedicated POS clearing settlement',409)
        month_open(c,v["date"][:7])
        if body.decision=="approve" and v["kind"]=="payment" and os.getenv("RAMSES_REQUIRE_PAYMENT_EVIDENCE", "0")=="1":
            if not c.execute("SELECT 1 FROM voucher_attachments WHERE voucher_id=? LIMIT 1",(voucher_id,)).fetchone():
                fail("يجب إرفاق مستند إثبات قبل اعتماد الصرف",409)
        if body.decision=="approve":
            maker=c.execute('SELECT id,role,active FROM users WHERE id=?',(v['created_by'],)).fetchone()
            if not maker or not maker['active']:
                fail('موظف السند معطل؛ يحتاج مراجعة مالك النظام قبل اعتماده',409)
            for fid in (v['from_fund_id'],v['to_fund_id'] if v['kind']=='transfer' else None):
                if fid is not None:
                    authorize_cashbook_fund(c,dict(maker),fid)
            cat=c.execute("SELECT * FROM categories WHERE id=?",(v["category_id"],)).fetchone() if v["category_id"] else None
            if cat and cat["nature"]=="payroll_payment":
                due=payroll_due(c,v["employee_id"],v["salary_period"])
                if due is None: fail("اعتماد صرف الراتب يحتاج كشف استحقاق معتمد للفترة والموظف",409)
                if v["amount_piasters"]>due: fail("المبلغ يتجاوز المتبقي من الراتب المعتمد",409)
            book_movements(c,v)
            ledger.post_voucher(c,v,user["id"])
        state="approved" if body.decision=="approve" else "rejected"
        c.execute("UPDATE vouchers SET status=?,reviewed_by=?,reviewed_at=?,review_reason=? WHERE id=?",
                  (state,user["id"],stamp(),body.reason.strip(),voucher_id))
        audit(c,user["id"],state,"voucher",voucher_id,{"reason":body.reason.strip()})
    return {"id":voucher_id,"status":state}


@app.post("/api/vouchers/{voucher_id}/reverse")
def reverse(voucher_id:int,body:ReverseForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner")
    effective=valid_date(body.date).isoformat()
    if len(body.reason.strip())<8: fail("سبب التسوية/الإلغاء يجب أن يكون واضحًا")
    with c:
        c.execute("BEGIN IMMEDIATE")
        original=c.execute("SELECT * FROM vouchers WHERE id=?",(voucher_id,)).fetchone()
        if not original or original["status"]!="approved" or original["reversal_of_id"] is not None:
            fail("لا يمكن عكس هذا السند",409)
        # Billing receipts are indivisibly linked to invoices/advance balances.
        # A generic reversal would corrupt AR while leaving the billing receipt unchanged.
        if c.execute('SELECT 1 FROM billing_refund_requests WHERE voucher_id=?',(voucher_id,)).fetchone():
            fail('Use a dedicated billing adjustment to reverse a patient refund',409)
        if c.execute("SELECT 1 FROM pos_settlements WHERE status='approved' AND (transfer_voucher_id=? OR fee_voucher_id=?)", (voucher_id,voucher_id)).fetchone():
            fail('POS transfer and fee belong to one settlement; individual reversal is blocked',409)
        if c.execute('SELECT 1 FROM billing_payment_parts WHERE voucher_id=?',(voucher_id,)).fetchone():
            fail('تحصيل مريض مرتبط بفواتير ومقدمات؛ استخدم دورة رد مخصص بعد اعتمادها',409)
        if c.execute('SELECT 1 FROM late_cash_allocations WHERE voucher_id=?',(voucher_id,)).fetchone():
            fail('السند خُصص لفواتير استدراك؛ لا يجوز عكسه منفردًا بعد تسوية ذمم المرضى',409)
        if c.execute('SELECT 1 FROM late_mixed_clearances WHERE voucher_id=?',(voucher_id,)).fetchone():
            fail('سند الظرف المختلط مستخدم في تسوية ذمم ومصروفات؛ لا يُعكس منفردًا',409)
        if c.execute("SELECT 1 FROM late_mixed_shortage_recovery_requests WHERE voucher_id=? AND status='approved'",
                     (voucher_id,)).fetchone():
            fail('سند سداد عجز ظرف قديم مرتبط بحساب فروق العهدة؛ لا يعكس منفردًا',409)
        if c.execute("SELECT 1 FROM late_mixed_overage_refund_requests WHERE voucher_id=? AND status='approved'",
                     (voucher_id,)).fetchone():
            fail('رد زيادة ظرف قديم مرتبط بتحقيق عهدة؛ لا يعكس منفردًا',409)
        if original["category_id"]:
            nature=c.execute("SELECT nature,code FROM categories WHERE id=?",(original["category_id"],)).fetchone()
            if nature and nature["code"] in ("cash_shortage","cash_overage"):
                fail("قيد فرق الجرد قيد متابعة مستقلة؛ لا يُسمح بعكسه كسند نقدي عادي",409)
            if nature and nature["nature"]=="advance" and outstanding_advance(c,original["employee_id"])<original["amount_piasters"]:
                fail("السلفة سُوّيت جزئيًا أو كليًا مع راتب؛ راجع التسوية أولًا",409)
        month_open(c,effective[:7]);
        from_period=original["date"][:7]
        if effective < original["date"]:fail("تاريخ التسوية لا يسبق تاريخ السند")
        legs=c.execute("SELECT fund_id,amount_piasters FROM fund_movements WHERE voucher_id=?",(voucher_id,)).fetchall()
        if not legs:fail("حركة مالية غير مرحّلة",409)
        shift_map={}
        for leg in legs:
            shift_map[leg["fund_id"]]=shift_for_posting(c,leg["fund_id"],effective,"central",reversal=True)
        for leg in legs:
            if leg["amount_piasters"]>0:
                fund=c.execute("SELECT * FROM funds WHERE id=?",(leg["fund_id"],)).fetchone()
                balance=fund["opening_piasters"]+c.execute("SELECT coalesce(sum(amount_piasters),0) FROM fund_movements WHERE fund_id=?",(leg["fund_id"],)).fetchone()[0]
                if balance-leg["amount_piasters"]<0 and not fund["allow_negative"]:fail("رصيد الخزنة لا يسمح بعكس السند",409)
        cur=c.execute("""INSERT INTO vouchers(voucher_no,date,kind,department_id,category_id,from_fund_id,to_fund_id,shift,
                employee_id,salary_period,amount_piasters,description,reference_no,status,created_by,reviewed_by,created_at,reviewed_at,
                review_reason,reversal_of_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'approved',?,?,?,?,?,?)""",
               ("REV-"+secrets.token_hex(7),effective,original["kind"],original["department_id"],original["category_id"],
                original["from_fund_id"],original["to_fund_id"],"central",original["employee_id"],original["salary_period"],
                original["amount_piasters"],"عكس سند "+original["voucher_no"]+": "+body.reason.strip(),original["voucher_no"],
                user["id"],user["id"],stamp(),stamp(),body.reason.strip(),voucher_id))
        vid=cur.lastrowid
        c.execute("UPDATE vouchers SET voucher_no=? WHERE id=?",(f"REV-{effective[:4]}-{vid:06d}",vid))
        for leg in legs:
            c.execute("""INSERT INTO fund_movements(voucher_id,fund_id,amount_piasters,booked_on,shift_session_id)
                      VALUES (?,?,?,?,?)""",
                      (vid,leg["fund_id"],-leg["amount_piasters"],effective,shift_map[leg["fund_id"]]))
        ledger.post_voucher(c,c.execute("SELECT * FROM vouchers WHERE id=?",(vid,)).fetchone(),user["id"])
        c.execute("UPDATE vouchers SET status='reversed' WHERE id=?",(voucher_id,))
        audit(c,user["id"],"reverse_voucher","voucher",voucher_id,{"reversal_id":vid,"reversal_date":effective,"reason":body.reason.strip()})
    return {"original_id":voucher_id,"reversal_id":vid}


def station_handoff_required(c, sh):
    return c.execute('SELECT id FROM billing_points WHERE fund_id=?',(sh['fund_id'],)).fetchone()


def active_handoff(c, sh):
    return c.execute('''SELECT h.*,u.username receiver_name FROM shift_handoffs h
        JOIN users u ON u.id=h.received_by WHERE h.shift_session_id=? AND h.count_version=?
        ORDER BY h.id DESC LIMIT 1''',(sh['id'],sh['count_version'])).fetchone()


def require_shift_handoff(c, sh, user):
    if not station_handoff_required(c,sh):
        return
    received=active_handoff(c,sh)
    if not received or received['decision']!='accepted':
        fail('A cashier shift needs a second-user cash handover before accounting approval',409)
    if received['received_by']==user['id']:
        fail('The cashier receiver cannot approve their own handover',403)


@app.get('/api/shifts/schedule')
def get_shift_schedule(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    return {'timezone':'Africa/Cairo','windows':shift_schedule.templates(c),
            'suggested':shift_schedule.current_window(c),
            'enforce_clock':bool(c.execute('SELECT enforce_clock FROM shift_settings WHERE id=1').fetchone()[0]),
            'rule':'business_date equals the Cairo date on which the named shift STARTS'}


@app.post('/api/shifts/schedule')
def update_shift_schedule(body:ShiftScheduleForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    if set(body.starts)!=set(shift_schedule.NAMES):
        fail('Provide exactly the 3 named shift start times')
    try:
        starts={k:shift_schedule.minutes(v) for k,v in body.starts.items()}
    except ValueError as exc:
        fail(str(exc))
    if len(set(starts.values()))!=3:
        fail('The three shift start times must differ')
    with c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('''SELECT 1 FROM shift_sessions WHERE status IN ('open','submitted') LIMIT 1''').fetchone():
            fail('Close and approve active shifts before changing the schedule',409)
        for code,minute in starts.items():
            c.execute('UPDATE shift_templates SET start_minute=? WHERE code=?',(minute,code))
        c.execute('UPDATE shift_settings SET enforce_clock=? WHERE id=1',(int(body.enforce_clock),))
        audit(c,user['id'],'update_shift_schedule','shift_settings',1,{'starts':starts,'enforce_clock':body.enforce_clock})
    return get_shift_schedule(user,c)


@app.get("/api/shifts")
def shifts(month:str="", user=Depends(get_user), c:sqlite3.Connection=Depends(db)):
    require(user,"owner","reviewer","clerk")
    month=valid_month(month or current_month())
    where="WHERE substr(s.business_date,1,7)=?"
    args=[month]
    if user["role"]=="clerk":
        where+=""" AND (s.responsible_id=? OR (s.status='submitted' AND EXISTS (
           SELECT 1 FROM billing_points p JOIN billing_point_access a ON a.point_id=p.id
           WHERE p.fund_id=s.fund_id AND a.user_id=? AND a.active=1)))"""
        args.extend([user['id'],user['id']])
    rows=c.execute("""SELECT s.*,f.name fund_name,f.kind fund_kind,u.username responsible_name,
            r.username reviewer_name FROM shift_sessions s JOIN funds f ON f.id=s.fund_id
            JOIN users u ON u.id=s.responsible_id
            LEFT JOIN users r ON r.id=s.reviewed_by """+where+" ORDER BY s.business_date DESC,s.id DESC LIMIT 250",args).fetchall()
    result=[]
    for r in rows:
        item=dict(r)
        case=c.execute("""SELECT id,status,explanation,proposed_by,decision_note,adjustment_voucher_id
              FROM shift_variance_cases WHERE shift_session_id=? ORDER BY id DESC LIMIT 1""",(r["id"],)).fetchone()
        item["variance_case"]=(dict(case) if case and user["role"] in ("owner","reviewer") else
                                 {"status":case["status"]} if case else None)
        item["mine"]=r["responsible_id"]==user["id"]
        station=station_handoff_required(c,r)
        handoff=active_handoff(c,r) if r['count_version'] else None
        item['handoff_required']=bool(station)
        item['handoff_status']=handoff['decision'] if handoff else None
        item['received_by_name']=handoff['receiver_name'] if handoff else None
        can_receive=(bool(station) and r['status']=='submitted' and not item['mine']
             and not handoff and (user['role'] in ('owner','reviewer') or c.execute(
              'SELECT 1 FROM billing_point_access WHERE point_id=? AND user_id=? AND active=1',
              (station['id'],user['id'])).fetchone()))
        item['can_handoff']=bool(can_receive)
        item["can_review"]=user["role"] in ("owner","reviewer") and not item["mine"] and not(
             handoff and handoff['received_by']==user['id'])
        approved_delegate=(user['role']=='reviewer' and c.execute(
            'SELECT COALESCE(can_approve,0) FROM cashier_variance_permissions WHERE user_id=?',
            (user['id'],)).fetchone())
        item['can_variance_decision']=bool(item['can_review'] and case and case['status']=='proposed'
             and (user['role']=='owner' or (approved_delegate and approved_delegate[0]))
             and case['proposed_by']!=user['id'])
        if user['role']=='clerk' and not item['mine']:
            item.pop('opening_piasters',None)
            item.pop('expected_piasters',None)
            item.pop('counted_piasters',None)
            item.pop('variance_piasters',None)
        elif user["role"]=="clerk" and r["status"]=="open":
            # Blind count: cashiers cannot see the expected till balance first.
            item.pop("opening_piasters",None)
            item.pop("expected_piasters",None)
            item.pop("variance_piasters",None)
        elif r["status"]=="open":
            item["expected_piasters"]=fund_balance(c,r["fund_id"])
        result.append(item)
    return {"month":month,"items":result,"schedule":shift_schedule.templates(c),
            "suggested":shift_schedule.current_window(c),
            "enforce_clock":bool(c.execute('SELECT enforce_clock FROM shift_settings WHERE id=1').fetchone()[0]),
            "note":"فرق الجرد لا يُرحّل إلا بعد تحقيق مستقل واقتراح المراجع وموافقة المالك. يُثبت قيد عهدة معلقة لا إيرادًا تشغيليًا."}


@app.get('/api/shifts/coverage')
def shift_coverage_report(month: str = '', user=Depends(get_user),
                          c: sqlite3.Connection = Depends(db)):
    require(user, 'owner', 'reviewer', 'clerk')
    return shift_coverage.report(c, valid_month(month or current_month()), user)


@app.get('/api/shifts/day-summary')
def cashier_day_summary(business_date:str,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    day=valid_date(business_date).isoformat()
    stations=[]
    for sh in c.execute('''SELECT s.id,s.business_date,s.shift,s.status,s.opening_piasters,
              s.counted_piasters,s.variance_piasters,s.responsible_id,
              s.count_version,s.fund_id,p.name point_name,f.name fund_name,u.username responsible_name
              FROM shift_sessions s JOIN funds f ON f.id=s.fund_id
              JOIN users u ON u.id=s.responsible_id
              JOIN billing_points p ON p.fund_id=s.fund_id
              WHERE s.business_date=? ORDER BY p.id,s.id''',(day,)):
        method=[dict(r) for r in c.execute('''SELECT p.method, SUM(p.amount_piasters) total_piasters
            FROM billing_payment_parts p JOIN billing_collections b ON b.id=p.collection_id
            WHERE b.shift_session_id=? GROUP BY p.method''',(sh['id'],))]
        changes=c.execute('''SELECT COALESCE(SUM(CASE WHEN amount_piasters>0 THEN amount_piasters ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN amount_piasters<0 THEN -amount_piasters ELSE 0 END),0)
            FROM fund_movements WHERE shift_session_id=?''',(sh['id'],)).fetchone()
        handoff=active_handoff(c,sh) if sh['count_version'] else None
        stations.append({'id':sh['id'],'point_name':sh['point_name'],'fund_name':sh['fund_name'],
            'shift':sh['shift'],'responsible_name':sh['responsible_name'],'status':sh['status'],
            'opening_piasters':sh['opening_piasters'],'cash_credited_piasters':changes[0],
            'cash_debited_piasters':changes[1],
            'expected_piasters':sh['opening_piasters']+changes[0]-changes[1],
            'counted_piasters':sh['counted_piasters'],'variance_piasters':sh['variance_piasters'],
            'handoff_status':handoff['decision'] if handoff else None,
            'methods':method})
    method_total={}
    for station in stations:
        for item in station['methods']:
            method_total[item['method']]=method_total.get(item['method'],0)+item['total_piasters']
    coverage=shift_coverage.report(c,day[:7],user)
    daily_slots=[x for x in coverage['days'] if x['business_date']==day]
    is_complete=bool(daily_slots) and all(x['status']=='complete' for x in daily_slots)
    return {'business_date':day,'stations':stations,'payment_method_totals_piasters':method_total,
        'pending_accounting_review':sum(x['status']=='submitted' for x in stations),
        'coverage':daily_slots,'shift_coverage_complete':is_complete,'is_provisional':not is_complete,
        'financially_certified':False,
        'notes':'Collections are cash flow, not revenue. Transfers are not new receipts. Excludes legacy unshifted funds. Day summaries are provisional until expected cashier shifts are independently closed.'}


@app.get("/api/shifts/{shift_id}/movements")
def shift_movements(shift_id:int,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner","reviewer")
    session=c.execute("""SELECT s.*, f.name fund_name, u.username responsible_name
           FROM shift_sessions s JOIN funds f ON f.id=s.fund_id
           JOIN users u ON u.id=s.responsible_id WHERE s.id=?""",(shift_id,)).fetchone()
    if not session:fail("الوردية غير موجودة",404)
    lines=[dict(r) for r in c.execute("""SELECT v.voucher_no,v.date,v.kind,v.description,v.reference_no,
            m.amount_piasters,v.status,u.username created_by
            FROM fund_movements m JOIN vouchers v ON v.id=m.voucher_id
            JOIN users u ON u.id=v.created_by
            WHERE m.shift_session_id=? ORDER BY m.id""",(shift_id,))]
    credited=sum(x["amount_piasters"] for x in lines if x["amount_piasters"]>0)
    debited=-sum(x["amount_piasters"] for x in lines if x["amount_piasters"]<0)
    expected=session["opening_piasters"]+credited-debited
    if session["status"]!="open" and expected!=session["expected_piasters"]:
        fail("مخالفة سلامة الحساب: دفتر حركة الوردية لا يطابق الجرد المحفوظ",500)
    return {"shift":dict(session),"credited_piasters":credited,"debited_piasters":debited,
            "expected_piasters":expected,"movements":lines,
            "note":"التسويات العكسية تظهر في وردية تنفيذها ولا تُغيّر جرد وردية أُقفلت سابقًا."}


@app.post("/api/shifts/open")
def shift_open(body:ShiftOpenForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner","reviewer","clerk")
    day=valid_date(body.business_date).isoformat()
    if day>datetime.now(ZoneInfo("Africa/Cairo")).date().isoformat():
        fail("لا يمكن فتح وردية بتاريخ مستقبلي")
    if not cashier_ops.CODE.fullmatch(body.shift) or body.shift == 'central':
        fail('كود الوردية غير صالح')
    with c:
        c.execute("BEGIN IMMEDIATE")
        month_open(c,day[:7])
        fund=lookup(c,"funds",body.fund_id)
        if fund["kind"] not in ("cash","wallet"):
            fail("جرد الورديات مخصص للخزنة النقدية والمحافظ؛ البنك تتم مطابقته بمستندات كشف الحساب")
        # Opening a drawer is custody access, not just permission to post a voucher.
        # A restricted cash fund must reject ungranted staff BEFORE a shift exists.
        if fund['kind']=='wallet' or (fund['kind']=='cash' and fund['cash_restricted']):
            authorize_cashbook_fund(c,user,fund['id'])
        # Cashier station funds can be opened only by assigned station users.
        mapped=c.execute('SELECT id FROM billing_points WHERE fund_id=?',(fund['id'],)).fetchone()
        if mapped and user['role']=='clerk':
            if not c.execute('SELECT 1 FROM billing_point_access WHERE point_id=? AND user_id=? AND active=1',
                             (mapped['id'],user['id'])).fetchone():
                fail('لا يحق لك فتح عهدة نقطة تحصيل غير معينة لحسابك',403)
            rights=c.execute('SELECT allowed_codes FROM cashier_shift_staff_rules WHERE point_id=? AND user_id=?',
                             (mapped['id'],user['id'])).fetchone()
            if rights is not None and body.shift not in rights['allowed_codes'].split(','):
                fail('غير مخوّل لك فتح هذه الوردية تحديدًا',403)
        # Never open an older shift over a balance that already includes later postings.
        last_booked=c.execute("SELECT MAX(booked_on) FROM fund_movements WHERE fund_id=?",(fund["id"],)).fetchone()[0]
        if last_booked and day<last_booked:
            fail("لا يجوز فتح وردية قبل تاريخ آخر حركة مرحّلة على الخزنة",409)

        if mapped:
            slot=next((x for x in cashier_ops.slots_for(c,mapped['id'],day)
                       if x['code']==body.shift),None)
            version=cashier_ops.version_for(c,mapped['id'],day)
            if version and str(valid_date(day).weekday()) not in version['operating_days']:
                fail('هذه النقطة لا تعمل في اليوم المختار وفق الجدول',409)
            if not slot:fail('الوردية غير موجودة في جدول نقطة التحصيل لهذا التاريخ',409)
            planned_start,planned_end=cashier_ops.interval(day,slot)
        else:
            if body.shift not in shift_schedule.NAMES:
                fail('حساب غير مرتبط بنقطة كاشير يتطلب وردية تاريخية معروفة',409)
            planned_start,planned_end=shift_schedule.planned_interval(c,day,body.shift)
        if c.execute('SELECT enforce_clock FROM shift_settings WHERE id=1').fetchone()[0]:
            current=datetime.now(ZoneInfo('Africa/Cairo'))
            if not (datetime.fromisoformat(planned_start)<=current<datetime.fromisoformat(planned_end)):
                fail('الوردية خارج وقت التشغيل المسموح وفق ساعة القاهرة',409)
        prior_exists=c.execute('SELECT 1 FROM shift_sessions WHERE fund_id=? LIMIT 1',(fund['id'],)).fetchone()
        if prior_exists:
            prior=c.execute('''SELECT scheduled_start_at,business_date,shift FROM shift_sessions
                   WHERE fund_id=? ORDER BY COALESCE(scheduled_start_at,
                    business_date || 'T' || CASE shift WHEN 'night' THEN '00:00'
                    WHEN 'morning' THEN '08:00' ELSE '16:00' END) DESC,id DESC LIMIT 1''',
                    (fund['id'],)).fetchone()
            prior_start=(prior['scheduled_start_at'] or
                         prior['business_date']+'T'+{'night':'00:00','morning':'08:00','evening':'16:00'}.get(prior['shift'],'00:00'))[:16]
            if planned_start[:16]<=prior_start:
                fail('Shift dates must follow the actual chronological start, not a fixed shift-name order',409)
        if c.execute("SELECT 1 FROM shift_sessions WHERE fund_id=? AND status='open'",(fund["id"],)).fetchone():
            fail('There is already an open shift for this physical till',409)
        pending=c.execute("SELECT * FROM shift_sessions WHERE fund_id=? AND status='submitted' ORDER BY id DESC LIMIT 1",(fund['id'],)).fetchone()
        if pending:
            handoff=active_handoff(c,pending)
            if (not station_handoff_required(c,pending) or not handoff or
                handoff['decision']!='accepted'):
                fail('الوردية السابقة تحتاج استلام عهدة فعلي مستقل قبل فتح الجديدة',409)
        # After a source till's physically counted cash was moved to the main
        # treasury, the next till must NOT inherit that cash as opening float.
        handover_out=c.execute('SELECT COALESCE(SUM(amount_piasters),0) FROM cashier_treasury_transfers WHERE source_shift_id=?',
                               (pending['id'],)).fetchone()[0] if pending else 0
        opening_cash=(pending['counted_piasters']-handover_out) if pending else fund_balance(c,fund['id'])
        if c.execute("""SELECT 1 FROM vouchers WHERE date=? AND shift=?
               AND (from_fund_id=? OR to_fund_id=?) LIMIT 1""",
               (day,body.shift,fund["id"],fund["id"])).fetchone():
            fail("يوجد سند سابق لهذه الوردية؛ يجب بدء الجرد قبل تسجيل حركاتها",409)
        try:
            cur=c.execute("""INSERT INTO shift_sessions(business_date,shift,fund_id,responsible_id,
                    opened_at,opening_piasters,scheduled_start_at,scheduled_end_at)
                    VALUES (?,?,?,?,?,?,?,?)""",
                (day,body.shift,fund["id"],user["id"],stamp(),opening_cash,planned_start,planned_end))
        except sqlite3.IntegrityError:
            fail("هذه الوردية سُجلت من قبل ولا يمكن فتحها مجددًا",409)
        if mapped:
            c.execute('UPDATE shift_sessions SET point_id=? WHERE id=?',(mapped['id'],cur.lastrowid))
        audit(c,user["id"],"open_shift","shift",cur.lastrowid,
              {"fund_id":fund["id"],"date":day,"shift":body.shift})
    return {"id":cur.lastrowid,"status":"open"}


@app.post("/api/shifts/{shift_id}/count")
def shift_count(shift_id:int,body:ShiftCountForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner","reviewer","clerk")
    counted=c_piasters(body.counted_amount,allow_zero=True)
    note=body.note.strip()
    if len(note)>400: fail("الملاحظة طويلة للغاية")
    with c:
        c.execute("BEGIN IMMEDIATE")
        sh=c.execute("SELECT * FROM shift_sessions WHERE id=?",(shift_id,)).fetchone()
        if not sh:fail("الوردية غير موجودة",404)
        if sh["responsible_id"]!=user["id"]:fail("صاحب العهدة فقط يسلم جرد ورديته",403)
        if sh["status"]!="open":fail("هذه الوردية قُدمت للجرد أو أُغلقت بالفعل",409)
        month_open(c,sh["business_date"][:7])
        if c.execute("""SELECT 1 FROM vouchers WHERE status='pending' AND date=?
              AND (shift=? OR shift='central') AND (from_fund_id=? OR to_fund_id=?) LIMIT 1""",
              (sh["business_date"],sh["shift"],sh["fund_id"],sh["fund_id"])).fetchone():
            fail("لا يمكن تسليم الجرد وهناك سندات مالية معلقة تخص الحساب",409)
        # Optional photographic evidence can be mandated from station policy,
        # but is OFF by default. Envelopes are conditional on actual use.
        point=c.execute('SELECT id FROM billing_points WHERE fund_id=?',(sh['fund_id'],)).fetchone()
        policy=c.execute('SELECT require_shift_image,require_envelope_image FROM cashier_point_policies WHERE point_id=?',
                         (point['id'],)).fetchone() if point else None
        if policy and policy['require_shift_image'] and not c.execute(
            "SELECT 1 FROM cashier_shift_attachments WHERE shift_session_id=? AND kind='report' LIMIT 1",
            (shift_id,)).fetchone():
            fail('سياسة هذه النقطة تتطلب إرفاق كشف الوردية قبل تسليم الجرد',409)
        if policy and policy['require_envelope_image'] and body.envelope_present and not c.execute(
            "SELECT 1 FROM cashier_shift_attachments WHERE shift_session_id=? AND kind='envelope' LIMIT 1",
            (shift_id,)).fetchone():
            fail('تم إثبات وجود ظرف؛ ارفع صورة الظرف أولًا وفق سياسة النقطة',409)
        # Reconcile THIS cashier's physical opening plus only THIS shift's
        # movements. Historical unresolved variances stay separate in GL.
        expected=sh['opening_piasters']+c.execute(
            'SELECT COALESCE(SUM(amount_piasters),0) FROM fund_movements WHERE shift_session_id=?',
            (shift_id,)).fetchone()[0]
        variance=counted-expected
        c.execute("""UPDATE shift_sessions SET status='submitted',counted_piasters=?,
                  expected_piasters=?,variance_piasters=?,submitted_by=?,submitted_at=?,note=?,
                  count_version=count_version+1,envelope_present=? WHERE id=?""",
                  (counted,expected,variance,user["id"],stamp(),note,int(body.envelope_present),shift_id))
        c.execute("""INSERT INTO cashier_count_history(shift_session_id,count_version,actor_id,
            event,counted_piasters,expected_piasters,variance_piasters,reason,recorded_at)
            SELECT id,count_version,?,'submit',counted_piasters,expected_piasters,variance_piasters,?,?
            FROM shift_sessions WHERE id=?""",(user['id'],note,stamp(),shift_id))
        audit(c,user["id"],"submit_shift_count","shift",shift_id,
              {"counted_piasters":counted,"expected_piasters":expected,"variance_piasters":variance})
    return {"id":shift_id,"status":"submitted","variance_piasters":variance}


@app.post('/api/shifts/{shift_id}/handoff')
def shift_handoff(shift_id:int,body:ShiftHandoffForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    if body.decision not in ('accept','reject'):
        fail('Choose accept or reject')
    counted=c_piasters(body.counted_amount,allow_zero=True)
    note=body.note.strip()
    if len(note)>400 or (body.decision=='reject' and len(note)<5):
        fail('Rejected handovers require a useful written explanation')
    with c:
        c.execute('BEGIN IMMEDIATE')
        sh=c.execute('SELECT * FROM shift_sessions WHERE id=?',(shift_id,)).fetchone()
        if not sh or sh['status']!='submitted':
            fail('Shift handover is not currently awaiting receipt',409)
        station=station_handoff_required(c,sh)
        if not station:
            fail('Independent receipt is reserved for assigned cashier drawers',409)
        if sh['responsible_id']==user['id'] or sh['submitted_by']==user['id']:
            fail('The outgoing cashier cannot receive their own till',403)
        if user['role']=='clerk' and not c.execute('''SELECT 1 FROM billing_point_access
             WHERE point_id=? AND user_id=? AND active=1''',(station['id'],user['id'])).fetchone():
            fail('You are not assigned to receive this cashier drawer',403)
        month_open(c,sh['business_date'][:7])
        if active_handoff(c,sh):fail('This counted version has already been acknowledged',409)
        if body.decision=='accept' and counted!=sh['counted_piasters']:
            fail('Receiver count differs: reject and request a fresh count',409)
        c.execute('''INSERT INTO shift_handoffs(shift_session_id,count_version,received_by,
            received_at,counted_piasters,decision,note) VALUES (?,?,?,?,?,?,?)''',
            (shift_id,sh['count_version'],user['id'],stamp(),counted,
             'accepted' if body.decision=='accept' else 'rejected',note))
        if body.decision=='reject':
            c.execute("UPDATE shift_sessions SET status='open' WHERE id=?",(shift_id,))
        audit(c,user['id'],'cash_handoff_'+body.decision,'shift',shift_id,
              {'count_version':sh['count_version'],'receiver_count_piasters':counted})
    return {'id':shift_id,'status':'submitted' if body.decision=='accept' else 'open',
            'handoff_status':'accepted' if body.decision=='accept' else 'rejected'}



@app.get('/api/shifts/{shift_id}/count-history')
def shift_count_history(shift_id:int,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    sh=c.execute('SELECT responsible_id FROM shift_sessions WHERE id=?',(shift_id,)).fetchone()
    if not sh:fail('الوردية غير موجودة',404)
    if user['role']=='clerk' and sh['responsible_id']!=user['id']:
        fail('سجل الجرد متاح لصاحب الوردية والمراجع فقط',403)
    return [dict(r) for r in c.execute(
        'SELECT * FROM cashier_count_history WHERE shift_session_id=? ORDER BY id',(shift_id,))]

@app.get('/api/shifts/{shift_id}/daily-report')
def shift_daily_report(shift_id:int,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    sh=c.execute('''SELECT s.*,f.name fund_name, p.name point_name
        FROM shift_sessions s JOIN funds f ON f.id=s.fund_id
        LEFT JOIN billing_points p ON p.fund_id=s.fund_id WHERE s.id=?''',(shift_id,)).fetchone()
    if not sh:fail('Unknown shift',404)
    if user['role']=='clerk' and sh['responsible_id']!=user['id']:
        fail('Only the shift owner can see their own detailed daily report',403)
    collection_rows=[dict(r) for r in c.execute('''SELECT p.method,COUNT(*) parts, SUM(p.amount_piasters) total_piasters
       FROM billing_payment_parts p JOIN billing_collections b ON b.id=p.collection_id
       WHERE b.shift_session_id=? GROUP BY p.method ORDER BY p.method''',(shift_id,))]
    cash_legs=[dict(r) for r in c.execute('''SELECT v.voucher_no,v.kind,v.description,v.reference_no,m.amount_piasters,
       v.status FROM fund_movements m JOIN vouchers v ON v.id=m.voucher_id
       WHERE m.shift_session_id=? ORDER BY m.id''',(shift_id,))]
    added=sum(x['amount_piasters'] for x in cash_legs if x['amount_piasters']>0)
    removed=-sum(x['amount_piasters'] for x in cash_legs if x['amount_piasters']<0)
    expected=sh['opening_piasters']+added-removed
    reveal=user['role'] in ('owner','reviewer') or sh['status']!='open'
    handoff=active_handoff(c,sh) if sh['count_version'] else None
    return {'id':shift_id,'business_date':sh['business_date'],'shift':sh['shift'],
        'scheduled_start_at':sh['scheduled_start_at'],'scheduled_end_at':sh['scheduled_end_at'],
        'point_name':sh['point_name'],'fund_name':sh['fund_name'],'status':sh['status'],
        'opening_piasters':sh['opening_piasters'] if reveal else None,
        'expected_piasters':expected if reveal else None,
        'counted_piasters':sh['counted_piasters'],
        'cash_credited_piasters':added,'cash_debited_piasters':removed,
        'payment_methods':collection_rows,'cash_movements':cash_legs,
        'handoff_status':handoff['decision'] if handoff else None,
        'handoff_receiver':handoff['receiver_name'] if handoff else None,
        'warning':'POS and digital payments are not physical cash in the till'}


@app.post("/api/shifts/{shift_id}/review")
def shift_review(shift_id:int,body:ShiftReviewForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner","reviewer")
    if body.decision not in ("approve","recount"):fail("قرار المراجعة غير صحيح")
    reason=body.reason.strip()
    if body.decision=="recount" and len(reason)<5:
        fail("سبب إعادة الجرد مطلوب (5 أحرف على الأقل)")
    if len(reason)>400:fail("الملاحظة طويلة للغاية")
    with c:
        c.execute("BEGIN IMMEDIATE")
        sh=c.execute("SELECT * FROM shift_sessions WHERE id=?",(shift_id,)).fetchone()
        if not sh:fail("الوردية غير موجودة",404)
        if sh["status"]!="submitted":fail("الوردية ليست بانتظار الاعتماد",409)
        if user["id"] in (sh["responsible_id"],sh["submitted_by"]):
            fail("لا يجوز اعتماد جردك بنفسك",403)
        month_open(c,sh["business_date"][:7])
        if c.execute("""SELECT 1 FROM shift_variance_cases
             WHERE shift_session_id=? AND status='proposed'""",(shift_id,)).fetchone():
            fail("يوجد تحقيق فرق جرد ينتظر قرار المالك",409)
        if body.decision=="approve":
            require_shift_handoff(c,sh,user)
            if sh["variance_piasters"]!=0:
                fail("هناك فرق جرد: راجعه وسجّل سبب إعادة العد قبل الإقفال",409)
            historical=sh['opening_piasters'] + c.execute(
                 'SELECT COALESCE(SUM(amount_piasters),0) FROM fund_movements WHERE shift_session_id=?',
                 (shift_id,)).fetchone()[0]
            if historical!=sh['expected_piasters']:
                fail('Historic shift movements changed after cashier count',409)
            c.execute("""UPDATE shift_sessions SET status='closed',reviewed_by=?,reviewed_at=?,review_note=?
                      WHERE id=?""",(user["id"],stamp(),reason,shift_id))
            audit(c,user["id"],"approve_shift_close","shift",shift_id,
                  {"counted_piasters":sh["counted_piasters"],"fund_id":sh["fund_id"]})
            status="closed"
        else:
            if c.execute("SELECT 1 FROM shift_sessions WHERE fund_id=? AND status='open' AND id<>?",
                         (sh['fund_id'],shift_id)).fetchone():
                fail('A later shift already opened after the independently accepted handover',409)
            c.execute("""INSERT INTO cashier_count_history(shift_session_id,count_version,actor_id,
                 event,counted_piasters,expected_piasters,variance_piasters,reason,recorded_at)
                 VALUES (?,?,?,?,?,?,?,?,?)""",(shift_id,sh['count_version'],user['id'],
                 'recount_requested',sh['counted_piasters'],sh['expected_piasters'],
                 sh['variance_piasters'],reason,stamp()))
            c.execute("""UPDATE shift_sessions SET status='open',counted_piasters=NULL,
                     expected_piasters=NULL,variance_piasters=NULL,submitted_by=NULL,submitted_at=NULL,
                     reviewed_by=NULL,reviewed_at=NULL,review_note=? WHERE id=?""",(reason,shift_id))
            audit(c,user["id"],"request_shift_recount","shift",shift_id,
                  {"previous_variance_piasters":sh["variance_piasters"],"reason":reason})
            status="open"
    return {"id":shift_id,"status":status}


@app.post("/api/shifts/{shift_id}/variance-propose")
def propose_shift_variance(shift_id:int,body:VarianceProposal,user=Depends(get_user),
                           c:sqlite3.Connection=Depends(db)):
    require(user,"reviewer")  # The owner is the independent final approver.
    reason=body.explanation.strip()
    if len(reason)<12 or len(reason)>800:
        fail("وصف تحقيق فرق الجرد يجب أن يكون بين 12 و800 حرف")
    with c:
        c.execute("BEGIN IMMEDIATE")
        sh=c.execute("SELECT * FROM shift_sessions WHERE id=?",(shift_id,)).fetchone()
        if not sh:fail("الوردية غير موجودة",404)
        if sh["status"]!="submitted" or not sh["variance_piasters"]:
            fail("لا توجد وردية مُقدمة بفرق جرد فعلي",409)
        if user["id"] in (sh["responsible_id"],sh["submitted_by"]):
            fail("لا يجوز لمُسلم الجرد التحقيق فيه لنفسه",403)
        month_open(c,sh["business_date"][:7])
        recorded=sh['opening_piasters']+c.execute(
            'SELECT COALESCE(SUM(amount_piasters),0) FROM fund_movements WHERE shift_session_id=?',
            (shift_id,)).fetchone()[0]
        if recorded!=sh['expected_piasters']:
            fail('حركات الوردية الأصلية تغيرت بعد تقديم الجرد',409)
        if c.execute("""SELECT 1 FROM shift_variance_cases WHERE shift_session_id=?
                    AND status IN ('proposed','approved')""",(shift_id,)).fetchone():
            fail("هناك محضر فرق جرد قائم للوردية",409)
        cur=c.execute("""INSERT INTO shift_variance_cases
          (shift_session_id,variance_piasters,explanation,proposed_by,proposed_at)
          VALUES (?,?,?,?,?)""",(shift_id,sh["variance_piasters"],reason,user["id"],stamp()))
        audit(c,user["id"],"propose_shift_variance","shift",shift_id,
              {"case_id":cur.lastrowid,"variance_piasters":sh["variance_piasters"]})
    return {"case_id":cur.lastrowid,"status":"proposed"}


@app.post("/api/shifts/{shift_id}/variance-decision")
def decide_shift_variance(shift_id:int,body:VarianceResolution,user=Depends(get_user),
                          c:sqlite3.Connection=Depends(db)):
    if user['role']!='owner':
        perm=c.execute('SELECT can_approve FROM cashier_variance_permissions WHERE user_id=?',
                       (user['id'],)).fetchone()
        if user['role']!='reviewer' or not perm or not perm['can_approve']:
            fail('قبول العجز يتطلب تفويضًا صريحًا من المالك',403)
    reason=body.reason.strip()
    if body.decision not in ("approve","reject") or len(reason)<8 or len(reason)>800:
        fail("القرار يجب أن يكون اعتمادًا أو رفضًا مع تعليل لا يقل عن 8 أحرف")
    with c:
        c.execute("BEGIN IMMEDIATE")
        sh=c.execute("SELECT * FROM shift_sessions WHERE id=?",(shift_id,)).fetchone()
        if not sh:fail("الوردية غير موجودة",404)
        case=c.execute("""SELECT * FROM shift_variance_cases WHERE shift_session_id=?
                         AND status='proposed' ORDER BY id DESC LIMIT 1""",(shift_id,)).fetchone()
        if not case or sh["status"]!="submitted":fail("لا يوجد تحقيق مُعلّق للوردية",409)
        if user["id"] in (case["proposed_by"],sh["responsible_id"],sh["submitted_by"]):
            fail("يجب فصل المراجع وصاحب العهدة عن المُعتمد النهائي",403)
        # A later shift may have legitimately opened after receiving the
        # physical cash. Post the late correction in an OPEN accounting month.
        posting_date=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        month_open(c,posting_date[:7])
        historical=sh['opening_piasters']+c.execute(
            'SELECT COALESCE(SUM(amount_piasters),0) FROM fund_movements WHERE shift_session_id=?',
            (shift_id,)).fetchone()[0]
        if case['variance_piasters']!=sh['variance_piasters'] or historical!=sh['expected_piasters']:
            fail('تغيرت حركات الجرد الأصلي أو فرق العهدة',409)
        adj_id=None
        if body.decision=="approve":
            require_shift_handoff(c,sh,user)
            incoming=sh["variance_piasters"]>0
            direction="receipt" if incoming else "payment"
            category_code="cash_overage" if incoming else "cash_shortage"
            cat=c.execute("SELECT id FROM categories WHERE code=?",(category_code,)).fetchone()
            dept=c.execute("SELECT id FROM departments WHERE code='ADMIN'").fetchone()
            if not cat or not dept:fail("فئات حسابات فروق الخزن غير مُهيأة",409)
            vamount=abs(sh["variance_piasters"])
            v=c.execute("""INSERT INTO vouchers(voucher_no,date,kind,department_id,category_id,
                  from_fund_id,shift,amount_piasters,description,reference_no,status,created_by,
                  reviewed_by,created_at,reviewed_at,review_reason)
                  VALUES (?,?,?,?,?,?,'central',?,?,?,'approved',?,?,?,?,?)""",
                 ("ADJ-"+secrets.token_hex(8),posting_date,direction,dept["id"],cat["id"],sh["fund_id"],
                  vamount,"تسوية فرق جرد تحت التحقيق - وردية "+str(shift_id)+"؛ "+case["explanation"][:250],
                  "VAR-"+str(case["id"]),case["proposed_by"],user["id"],stamp(),stamp(),reason))
            adj_id=v.lastrowid
            c.execute("UPDATE vouchers SET voucher_no=? WHERE id=?",(f"ADJ-{sh['business_date'][:4]}-{adj_id:06d}",adj_id))
            c.execute("""INSERT INTO fund_movements(voucher_id,fund_id,amount_piasters,booked_on,shift_session_id)
                         VALUES (?,?,?,?,?)""",(adj_id,sh["fund_id"],sh["variance_piasters"],posting_date,shift_id))
            ledger.post_voucher(c,c.execute("SELECT * FROM vouchers WHERE id=?",(adj_id,)).fetchone(),user["id"])
            reconciled=sh['opening_piasters']+c.execute(
                'SELECT COALESCE(SUM(amount_piasters),0) FROM fund_movements WHERE shift_session_id=?',
                (shift_id,)).fetchone()[0]
            if reconciled!=sh['counted_piasters']:
                fail('التسوية لم تطابق الجرد الأصلي؛ تم إلغاء العملية',409)
            c.execute("""UPDATE shift_sessions SET status='closed',expected_piasters=?,reviewed_by=?,
                     reviewed_at=?,review_note=? WHERE id=?""",
                     (sh["counted_piasters"],user["id"],stamp(),reason,shift_id))
        c.execute("""UPDATE shift_variance_cases SET status=?,decided_by=?,decided_at=?,
               decision_note=?,adjustment_voucher_id=? WHERE id=?""",
               ("approved" if adj_id else "rejected",user["id"],stamp(),reason,adj_id,case["id"]))
        audit(c,user["id"],"approve_shift_variance" if adj_id else "reject_shift_variance",
              "shift",shift_id,{"case_id":case["id"],"adjustment_voucher_id":adj_id,
                                    "variance_piasters":sh["variance_piasters"],"reason":reason})
    return {"case_id":case["id"],"status":"closed" if adj_id else "submitted",
            "adjustment_voucher_id":adj_id}


@app.get("/api/reconciliation/variances")
def unresolved_shift_variances(month:str="",user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner","reviewer")
    month=valid_month(month or current_month())
    records=[dict(r) for r in c.execute("""SELECT vc.id,s.business_date,s.shift,
        f.name fund_name,vc.variance_piasters,vc.explanation,vc.proposed_at,
        vc.status,vc.decision_note,vc.adjustment_voucher_id,u.username proposed_by
        FROM shift_variance_cases vc JOIN shift_sessions s ON s.id=vc.shift_session_id
        JOIN funds f ON f.id=s.fund_id JOIN users u ON u.id=vc.proposed_by
        WHERE substr(s.business_date,1,7)=? ORDER BY vc.id DESC""",(month,))]
    approved=[r for r in records if r["status"]=="approved"]
    return {"month":month,"items":records,
            "proposed_count":sum(r["status"]=="proposed" for r in records),
            "approved_suspense_count":len(approved),
            "shortage_piasters":sum(-r["variance_piasters"] for r in approved if r["variance_piasters"]<0),
            "overage_piasters":sum(r["variance_piasters"] for r in approved if r["variance_piasters"]>0),
            "warning":"عهد فروق الخزن مؤقتة ولا تعد مصروفًا/إيرادًا تشغيليًا. يلزم إجراء محاسبي لاحق لتصفية العهد بعد التحقيق."}



# --- Bank statement reconciliation V7.6 ---
MAX_BANK_CSV = 512 * 1024
MAX_BANK_ROWS = 1500


def signed_bank_amount(value):
    raw=str(value or '').strip()
    if not raw or raw[0] not in '-0123456789' or ',' in raw:
        fail('مبلغ البنك غير صالح؛ استخدم رقمًا موجبًا للإيداع وسالبًا للسحب')
    if raw[0]=='-':
        return -c_piasters(raw[1:])
    return c_piasters(raw)


def bank_fund(c, fund_id):
    f=c.execute('SELECT * FROM funds WHERE id=? AND active=1 AND kind=\'bank\'',(fund_id,)).fetchone()
    if not f: fail('اختر حسابًا بنكيًا فعالًا',404)
    return f


def fund_grant_rights(c, user, fund_id):
    """Return the user's *current* explicit financial account grants.

    These are not patient chart permissions or global accountant role rights.
    Owner can manage both activities; for staff, revocation takes effect on
    the next request even when their browser session remains open.
    """
    if user['role'] == 'owner':
        return {'can_submit': True, 'can_approve': True}
    grant = c.execute("""SELECT g.can_submit,g.can_approve FROM user_fund_grants g
        JOIN users u ON u.id=g.user_id AND u.active=1
        WHERE g.user_id=? AND g.fund_id=?""", (user['id'], fund_id)).fetchone()
    return {'can_submit': bool(grant and grant['can_submit']),
            'can_approve': bool(grant and grant['can_approve'])}


def bank_statement_access(c, user, fund_id, permission='read'):
    """Enforce owner-granted bank scope for every statement read and mutation.

    can_submit controls bank CSV import/match/unmatch; can_approve controls
    signing. Read requires either grant. A reviewer role alone grants none.
    """
    require(user, 'owner', 'reviewer')
    # Authorize before looking up account metadata: unknown and ungranted
    # account IDs must not be distinguishable by an unauthorised reviewer.
    rights = fund_grant_rights(c,user,fund_id)
    if permission == 'read':
        allowed = any(rights.values())
    elif permission in ('submit', 'approve'):
        allowed = rights['can_'+permission]
    else:
        raise ValueError('Unknown bank statement permission')
    if not allowed:
        fail('ليس لديك تفويض لهذا الحساب البنكي أو لهذا الإجراء', 403)
    return bank_fund(c, fund_id)


def accessible_bank_funds(c, user):
    """The bank selector must not reveal ungranted bank statements."""
    require(user, 'owner', 'reviewer')
    if user['role'] == 'owner':
        return [dict(r) for r in c.execute("SELECT id,name,code FROM funds WHERE kind='bank' AND active=1 ORDER BY name")]
    return [dict(r) for r in c.execute('''SELECT f.id,f.name,f.code FROM funds f
        JOIN user_fund_grants g ON g.fund_id=f.id
        WHERE f.kind='bank' AND f.active=1 AND g.user_id=?
        AND (g.can_submit=1 OR g.can_approve=1) ORDER BY f.name''', (user['id'],))]


def bank_ledger_at(c, fund_id, month):
    opening=c.execute("""SELECT opening_piasters +
        (SELECT coalesce(sum(amount_piasters),0) FROM fund_movements WHERE fund_id=? AND booked_on<?)
        FROM funds WHERE id=?""",(fund_id,month+'-01',fund_id)).fetchone()[0]
    changes=c.execute("""SELECT coalesce(sum(amount_piasters),0) FROM fund_movements
                          WHERE fund_id=? AND substr(booked_on,1,7)=?""",(fund_id,month)).fetchone()[0]
    return opening, opening+changes


def bank_batch(c,batch_id, *, editable=False):
    b=c.execute("""SELECT b.*,f.name fund_name FROM bank_statement_batches b
                 JOIN funds f ON f.id=b.fund_id WHERE b.id=?""",(batch_id,)).fetchone()
    if not b or b['status']=='voided': fail('كشف الحساب البنكي غير موجود أو أُلغي',404)
    if editable and b['status']!='draft':fail('المطابقة معتمدة ولا يمكن تعديلها',409)
    return b


class BankMatchForm(BaseModel):
    line_id: int
    movement_id: int
    note: str = ''


class BankUnmatchForm(BaseModel):
    match_id: int
    reason: str


class BankApprovalForm(BaseModel):
    note: str = ''


class BankVoidForm(BaseModel):
    reason: str


@app.post('/api/bank-reconciliation/import')
def import_bank_csv(fund_id: int=Form(...), period: str=Form(...),
                    opening_balance: str=Form(...), closing_balance: str=Form(...),
                    file: UploadFile=File(...), user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    month=valid_month(period)
    bank_statement_access(c,user,fund_id,'submit')
    opening=c_piasters(opening_balance,allow_zero=True)
    closing=c_piasters(closing_balance,allow_zero=True)
    fname=Path(file.filename or '').name
    if not fname.lower().endswith('.csv') or not 1<=len(fname)<=120:
        fail('يجب اختيار كشف CSV باسم ملف صحيح')
    raw=file.file.read(MAX_BANK_CSV+1)
    if len(raw)>MAX_BANK_CSV:fail('حجم الملف يتجاوز 512KB')
    try:
        content=raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        fail('الملف يجب أن يكون CSV بتشفير UTF-8')
    try:
        reader=csv.DictReader(io.StringIO(content,newline=''))
        columns=set(reader.fieldnames or [])
        if len(reader.fieldnames or [])!=len(columns):fail('عناوين أعمدة CSV مكررة')
        if not {'date','amount','description'}<=columns or not columns<={'date','amount','description','reference'}:
            fail('أعمدة الملف المطلوبة: date,amount,description,reference (الأخير اختياري)')
        rows=[]
        for i,row in enumerate(reader,1):
            if i>MAX_BANK_ROWS:fail('الحد الأقصى 1500 حركة في الملف')
            if None in row or any(v is None for v in row.values()):fail('عدد أعمدة غير صحيح في سطر CSV')
            day=valid_date((row['date'] or '').strip()).isoformat()
            if day[:7]!=month:fail('سطر بنك بتاريخ خارج الشهر المحدد: '+day)
            description=(row['description'] or '').strip()
            reference=(row.get('reference') or '').strip()
            if not 3<=len(description)<=300 or len(reference)>100:
                fail('البيان 3-300 حرف والمرجع حتى 100 حرف')
            rows.append((i,day,description,reference,signed_bank_amount(row['amount'])))
    except csv.Error:
        fail('تنسيق CSV غير سليم')
    if not rows: fail('كشف الحساب فارغ')
    if opening+sum(r[4] for r in rows)!=closing:
        fail('الرصيد الافتتاحي + مجموع حركات البنك لا يساوي الرصيد الختامي؛ تأكد من اكتمال كشف الحساب',409)
    digest=hashlib.sha256(raw).hexdigest()
    with c:
        c.execute('BEGIN IMMEDIATE')
        # The owner may revoke an account grant while a CSV is being parsed.
        # Re-check the current grant under the write lock before any change.
        bank_statement_access(c,user,fund_id,'submit')
        month_open(c,month)
        existing=c.execute("""SELECT * FROM bank_statement_batches WHERE fund_id=? AND period=?
                              AND status!='voided' """,(fund_id,month)).fetchone()
        if existing:
            if (existing['sha256']==digest and existing['opening_piasters']==opening
                    and existing['closing_piasters']==closing):
                return {'batch_id':existing['id'],'lines':len(rows),'status':existing['status'],'replayed':True}
            fail('يوجد كشف لهذا البنك والشهر؛ يلزم إلغاء المسودة بسبب موثّق قبل إعادة الاستيراد',409)
        rid=c.execute("""INSERT INTO bank_statement_batches
          (fund_id,period,file_name,sha256,raw_csv,opening_piasters,closing_piasters,imported_by,imported_at)
          VALUES (?,?,?,?,?,?,?,?,?)""",(fund_id,month,fname,digest,raw,opening,closing,user['id'],stamp())).lastrowid
        c.executemany("""INSERT INTO bank_statement_lines
          (batch_id,line_no,tx_date,description,reference,amount_piasters) VALUES (?,?,?,?,?,?)""",
          [(rid,*r) for r in rows])
        audit(c,user['id'],'import_bank_statement','bank_statement',rid,
              {'fund_id':fund_id,'period':month,'rows':len(rows),'sha256':digest})
    return {'batch_id':rid,'lines':len(rows),'status':'draft'}


@app.get('/api/bank-reconciliation')
def bank_reconciliation(period: str='',fund_id: int=0,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    month=valid_month(period or current_month())
    banks=accessible_bank_funds(c,user)
    if fund_id:
        bank_statement_access(c,user,fund_id,'read')
    else:
        fund_id=banks[0]['id'] if banks else 0
    if not fund_id:
        return {'month':month,'banks':[],'batch':None,'lines':[],'unmatched_ledger':[],
                'ledger_opening_piasters':0,'ledger_closing_piasters':0,'pending_vouchers':0,
                'permissions':{'can_submit':False,'can_approve':False}}
    f=bank_fund(c,fund_id)
    rights=fund_grant_rights(c,user,fund_id)
    opening,closing=bank_ledger_at(c,fund_id,month)
    b=c.execute("""SELECT b.id,b.fund_id,b.period,b.file_name,b.sha256,b.opening_piasters,b.closing_piasters,
                   b.imported_by,b.imported_at,b.status,b.approved_by,b.approved_at,b.approval_note,
                   u.username imported_by_name
            FROM bank_statement_batches b JOIN users u ON u.id=b.imported_by
            WHERE b.fund_id=? AND b.period=? AND b.status!='voided' ORDER BY b.id DESC LIMIT 1""",
            (fund_id,month)).fetchone()
    lines=[]
    if b:
        lines=[dict(r) for r in c.execute("""SELECT l.*,ma.id match_id,ma.movement_id,
                  m.booked_on match_date,v.voucher_no,ma.note match_note
                  FROM bank_statement_lines l
                  LEFT JOIN bank_statement_matches ma ON ma.line_id=l.id AND ma.status='active'
                  LEFT JOIN fund_movements m ON m.id=ma.movement_id
                  LEFT JOIN vouchers v ON v.id=m.voucher_id
                  WHERE l.batch_id=? ORDER BY l.tx_date,l.line_no""",(b['id'],)).fetchall()]
    unmatched_ledger=[dict(r) for r in c.execute("""SELECT m.id movement_id,m.booked_on,
                 m.amount_piasters,v.id voucher_id,v.voucher_no,v.description,v.reference_no
                 FROM fund_movements m JOIN vouchers v ON v.id=m.voucher_id
                 LEFT JOIN bank_statement_matches ma ON ma.movement_id=m.id AND ma.status='active'
                 WHERE m.fund_id=? AND substr(m.booked_on,1,7)=? AND ma.id IS NULL
                 ORDER BY m.booked_on,m.id""",(fund_id,month)).fetchall()]
    pending=c.execute("""SELECT count(*) FROM vouchers v WHERE v.status='pending' AND substr(v.date,1,7)=?
                AND (v.from_fund_id=? OR (v.kind='transfer' AND v.to_fund_id=?))""",(month,fund_id,fund_id)).fetchone()[0]
    line_total=sum(x['amount_piasters'] for x in lines)
    statement_closing=b['closing_piasters'] if b else None
    return {'month':month,'banks':banks,'fund':{'id':f['id'],'name':f['name']},
            'permissions':rights,
            'batch':dict(b) if b else None,'lines':lines,'unmatched_ledger':unmatched_ledger,
            'statement_sum_piasters':line_total,'matched_count':sum(1 for x in lines if x['match_id']),
            'unmatched_bank_count':sum(1 for x in lines if not x['match_id']),
            'ledger_opening_piasters':opening,'ledger_closing_piasters':closing,
            'bank_opening_piasters':b['opening_piasters'] if b else None,
            'bank_closing_piasters':statement_closing,
            'balance_difference_piasters':(statement_closing-closing) if b else None,
            'pending_vouchers':pending,'month_closed':bool(c.execute('SELECT 1 FROM periods WHERE period=?',(month,)).fetchone()),
            'warning':'المطابقة لا تنشئ قيودًا ولا تصحح أرصدة تلقائيًا؛ أي اختلاف يتطلب سندًا مستقلًا بمراجعة واعتماد.'}


@app.get('/api/bank-reconciliation/{batch_id}/source.csv')
def download_bank_source(batch_id:int,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    b=bank_batch(c,batch_id)
    bank_statement_access(c,user,b['fund_id'],'read')
    # Avoid putting potentially untrusted source filename into response headers.
    return Response(content=b['raw_csv'],media_type='text/csv; charset=utf-8',headers={
        'Content-Disposition':f'attachment; filename="bank-source-{batch_id}.csv"',
        'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})


@app.post('/api/bank-reconciliation/{batch_id}/match')
def bank_match(batch_id:int,body:BankMatchForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    if len(body.note.strip())>500:fail('الملاحظة أطول من الحد المسموح')
    with c:
        c.execute('BEGIN IMMEDIATE')
        b=bank_batch(c,batch_id,editable=True)
        bank_statement_access(c,user,b['fund_id'],'submit')
        month_open(c,b['period'])
        line=c.execute('SELECT * FROM bank_statement_lines WHERE id=? AND batch_id=?',(body.line_id,batch_id)).fetchone()
        movement=c.execute("""SELECT m.*,v.status FROM fund_movements m JOIN vouchers v ON v.id=m.voucher_id
                        WHERE m.id=?""",(body.movement_id,)).fetchone()
        if not line or not movement:fail('سطر البنك أو حركة الدفتر غير موجود',404)
        if (movement['fund_id']!=b['fund_id'] or movement['booked_on'][:7]!=b['period']
              or movement['amount_piasters']!=line['amount_piasters']
              or movement['status'] not in ('approved','reversed')):
            fail('المطابقة تتطلب نفس الحساب والشهر والقيمة والإشارة وسندًا معتمدًا',409)
        if c.execute("""SELECT 1 FROM bank_statement_matches WHERE status='active'
                        AND (line_id=? OR movement_id=?)""",(body.line_id,body.movement_id)).fetchone():
            fail('السطر أو الحركة البنكية مطابق سابقًا؛ لا يجوز التكرار',409)
        mid=c.execute("""INSERT INTO bank_statement_matches(line_id,movement_id,matched_by,matched_at,note)
                        VALUES (?,?,?,?,?)""",(body.line_id,body.movement_id,user['id'],stamp(),body.note.strip())).lastrowid
        audit(c,user['id'],'bank_match','bank_statement',batch_id,
              {'match_id':mid,'line_id':body.line_id,'movement_id':body.movement_id})
    return {'match_id':mid,'status':'active'}


@app.post('/api/bank-reconciliation/{batch_id}/unmatch')
def bank_unmatch(batch_id:int,body:BankUnmatchForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    reason=body.reason.strip()
    if len(reason)<8 or len(reason)>300:fail('سبب فك المطابقة يجب أن يكون من 8 إلى 300 حرف')
    with c:
        c.execute('BEGIN IMMEDIATE')
        b=bank_batch(c,batch_id,editable=True)
        bank_statement_access(c,user,b['fund_id'],'submit')
        month_open(c,b['period'])
        m=c.execute("""SELECT ma.id FROM bank_statement_matches ma
            JOIN bank_statement_lines l ON l.id=ma.line_id
            WHERE ma.id=? AND l.batch_id=? AND ma.status='active' """,(body.match_id,batch_id)).fetchone()
        if not m:fail('المطابقة غير موجودة أو أُلغيت سابقًا',409)
        c.execute("""UPDATE bank_statement_matches SET status='voided',voided_by=?,voided_at=?,void_reason=?
                     WHERE id=?""",(user['id'],stamp(),reason,body.match_id))
        audit(c,user['id'],'bank_unmatch','bank_statement',batch_id,{'match_id':body.match_id,'reason':reason})
    return {'status':'voided'}


@app.post('/api/bank-reconciliation/{batch_id}/approve')
def bank_approve(batch_id:int,body:BankApprovalForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    if len(body.note.strip())>300:fail('ملاحظة الاعتماد طويلة جدًا')
    with c:
        c.execute('BEGIN IMMEDIATE')
        b=bank_batch(c,batch_id,editable=True)
        bank_statement_access(c,user,b['fund_id'],'approve')
        month_open(c,b['period'])
        if b['imported_by']==user['id']:
            fail('لا يجوز لمستورد كشف البنك اعتماده بنفسه',403)
        if c.execute("SELECT 1 FROM pos_settlements WHERE bank_fund_id=? AND substr(settlement_date,1,7)=? AND status='pending' LIMIT 1",
                     (b['fund_id'],b['period'])).fetchone():
            fail('POS settlement requests are still waiting for independent review',409)
        count=c.execute("""SELECT count(*) FROM bank_statement_lines l LEFT JOIN bank_statement_matches ma
                          ON ma.line_id=l.id AND ma.status='active' WHERE l.batch_id=? AND ma.id IS NULL""",(batch_id,)).fetchone()[0]
        if count:fail('لا يمكن اعتماد كشف البنك مع وجود سطور غير مطابقة',409)
        outside=c.execute("""SELECT count(*) FROM fund_movements m
                           LEFT JOIN bank_statement_matches ma ON ma.movement_id=m.id AND ma.status='active'
                           LEFT JOIN bank_statement_lines l ON l.id=ma.line_id
                           WHERE m.fund_id=? AND substr(m.booked_on,1,7)=?
                             AND (ma.id IS NULL OR l.batch_id!=?)""",(b['fund_id'],b['period'],batch_id)).fetchone()[0]
        if outside:fail('توجد حركات دفتر بنك غير مطابقة لكشف الشهر',409)
        pending=c.execute("""SELECT 1 FROM vouchers v WHERE v.status='pending' AND substr(v.date,1,7)=?
                    AND (v.from_fund_id=? OR v.to_fund_id=?) LIMIT 1""",(b['period'],b['fund_id'],b['fund_id'])).fetchone()
        if pending:fail('توجد سندات بنكية معلقة على نفس الشهر',409)
        start,end=bank_ledger_at(c,b['fund_id'],b['period'])
        if start!=b['opening_piasters'] or end!=b['closing_piasters']:
            fail('الرصيد الافتتاحي أو الختامي للبنك لا يطابق رصيد دفتر الحساب',409)
        c.execute("""UPDATE bank_statement_batches SET status='approved',approved_by=?,approved_at=?,approval_note=?
                     WHERE id=?""",(user['id'],stamp(),body.note.strip(),batch_id))
        audit(c,user['id'],'approve_bank_reconciliation','bank_statement',batch_id,
              {'fund_id':b['fund_id'],'period':b['period'],'opening_piasters':start,'closing_piasters':end})
    return {'batch_id':batch_id,'status':'approved','closing_piasters':end}


@app.post('/api/bank-reconciliation/{batch_id}/void')
def bank_void(batch_id:int,body:BankVoidForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    reason=body.reason.strip()
    if not 8<=len(reason)<=300:fail('يجب تسجيل سبب واضح لإلغاء كشف البنك')
    with c:
        c.execute('BEGIN IMMEDIATE')
        b=bank_batch(c,batch_id,editable=True)
        month_open(c,b['period'])
        c.execute("""UPDATE bank_statement_matches SET status='voided',voided_by=?,voided_at=?,void_reason=?
            WHERE status='active' AND line_id IN (SELECT id FROM bank_statement_lines WHERE batch_id=?)""",
            (user['id'],stamp(),'إلغاء كشف بنكي: '+reason,batch_id))
        c.execute("""UPDATE bank_statement_batches SET status='voided',voided_by=?,voided_at=?,void_reason=?
            WHERE id=?""",(user['id'],stamp(),reason,batch_id))
        audit(c,user['id'],'void_bank_statement','bank_statement',batch_id,{'reason':reason})
    return {'batch_id':batch_id,'status':'voided'}


@app.get('/api/bank-reconciliation/export.csv')
def bank_reconciliation_export(period:str='',fund_id:int=0,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    report=bank_reconciliation(period,fund_id,user,c)
    output=io.StringIO()
    writer=csv.writer(output)
    writer.writerow(['line_id','bank_date','bank_reference','bank_description','bank_amount_piasters',
                     'matched_voucher','matched_date','matched_movement_id','state'])
    for line in report['lines']:
        writer.writerow([line['id'],line['tx_date'],safe_csv_cell(line['reference']),
             safe_csv_cell(line['description']),line['amount_piasters'],
             safe_csv_cell(line['voucher_no'] or ''),line['match_date'] or '',line['movement_id'] or '',
             'matched' if line['match_id'] else 'unmatched'])
    raw='\ufeff'+output.getvalue()
    month=report['month']
    return Response(content=raw,media_type='text/csv; charset=utf-8',headers={
        'Content-Disposition':f'attachment; filename="bank-reconciliation-{month}.csv"',
        'Cache-Control':'no-store'})


@app.get("/api/funds")
def funds(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    rows=c.execute("""SELECT f.*,coalesce(sum(m.amount_piasters),0) movements_piasters,
               f.opening_piasters+coalesce(sum(m.amount_piasters),0) balance_piasters,
               count(m.id) transaction_count FROM funds f LEFT JOIN fund_movements m ON m.fund_id=f.id
               GROUP BY f.id ORDER BY f.id""").fetchall()
    if user["role"]=="clerk":
        return [{k:v for k,v in dict(r).items() if k not in ("balance_piasters","opening_piasters","movements_piasters")} for r in rows]
    return [dict(r) for r in rows]


@app.post("/api/funds")
def create_fund(body:FundForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner")
    code=body.code.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,24}",code) or body.kind not in ("cash","bank","wallet"):
        fail("كود أو نوع حساب غير صالح")
    if len(body.name.strip())<3: fail("اسم الخزنة قصير")
    try:
        with c:
            cur=c.execute("INSERT INTO funds(code,name,kind,cash_restricted) VALUES (?,?,?,?)",
                          (code,body.name.strip(),body.kind,int(body.kind=='cash' and body.restricted_cash)))
            ledger.ensure_fund_account(c,cur.lastrowid)
            audit(c,user["id"],"create_fund","fund",cur.lastrowid)
    except sqlite3.IntegrityError:
        fail("كود أو اسم الخزنة موجود")
    return {"id":cur.lastrowid}



class CashFundAccessPolicy(BaseModel):
    restricted: bool
    reason: str = Field(min_length=8, max_length=400)

@app.post('/api/funds/{fund_id}/access-policy')
def update_cash_fund_access_policy(fund_id:int,body:CashFundAccessPolicy,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    with c:
        c.execute('BEGIN IMMEDIATE')
        fund=c.execute('SELECT id,kind,active,cash_restricted FROM funds WHERE id=?',(fund_id,)).fetchone()
        if not fund or not fund['active'] or fund['kind']!='cash':
            fail('هذا الإعداد مخصص لخزنة نقدية نشطة',409)
        if body.restricted:
            # Don't freeze an in-progress till by toggling permissions under its clerk.
            active=c.execute('''SELECT responsible_id FROM shift_sessions
                WHERE fund_id=? AND status='open' ''',(fund_id,)).fetchone()
            if active and active['responsible_id'] != user['id']:
                granted=c.execute('''SELECT 1 FROM user_fund_grants g JOIN users u ON u.id=g.user_id
                  WHERE g.user_id=? AND g.fund_id=? AND g.can_submit=1 AND u.active=1''',
                  (active['responsible_id'],fund_id)).fetchone()
                if not granted:
                    fail('فوّض المسؤول عن الوردية المفتوحة قبل تفعيل الحماية حتى لا يتوقف التحصيل',409)
        c.execute('UPDATE funds SET cash_restricted=? WHERE id=?',(int(body.restricted),fund_id))
        audit(c,user['id'],'cash_fund_policy','fund',fund_id,
             {'before':bool(fund['cash_restricted']),'after':body.restricted,'reason':body.reason.strip()})
    return {'fund_id':fund_id,'cash_restricted':body.restricted}

@app.post("/api/funds/{fund_id}/opening")
def set_opening(fund_id:int,body:Opening,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner")
    amt=c_piasters(body.amount,allow_zero=True)
    with c:
        c.execute("BEGIN IMMEDIATE")
        fund=lookup(c,"funds",fund_id)
        if (c.execute("SELECT 1 FROM fund_movements WHERE fund_id=? LIMIT 1",(fund_id,)).fetchone()
            or c.execute("SELECT 1 FROM shift_sessions WHERE fund_id=? LIMIT 1",(fund_id,)).fetchone()
            or c.execute("SELECT 1 FROM bank_statement_batches WHERE fund_id=? LIMIT 1",(fund_id,)).fetchone()):
            fail("لا يمكن تغيير الرصيد الافتتاحي بعد تسجيل حركة أو فتح وردية؛ استخدم قيد تسوية معتمدًا",409)
        if c.execute("SELECT 1 FROM fund_opening_reviews WHERE fund_id=? AND status IN ('pending','approved')",(fund_id,)).fetchone():
            fail('رصيد الافتتاح مرتبط بمحضر مراجعة؛ لا يمكن تغييره بعد تقديمه',409)
        c.execute("UPDATE funds SET opening_piasters=? WHERE id=?",(amt,fund_id))
        audit(c,user["id"],"opening_balance","fund",fund_id,{"from":fund["opening_piasters"],"to":amt})
    return {"ok":True,"opening_piasters":amt}


def opening_timeline_guard(c:sqlite3.Connection,fund_id:int,effective_date:str):
    # Recheck on BOTH submission and approval: cashiers can post a backdated
    # movement after the opening request was submitted, before review signoff.
    for earliest in (
        c.execute('SELECT MIN(booked_on) FROM fund_movements WHERE fund_id=?',(fund_id,)).fetchone()[0],
        c.execute('SELECT MIN(business_date) FROM shift_sessions WHERE fund_id=?',(fund_id,)).fetchone()[0],
        c.execute('SELECT MIN(period) FROM bank_statement_batches WHERE fund_id=?',(fund_id,)).fetchone()[0],
    ):
        if earliest and effective_date > (earliest+'-01' if len(earliest)==7 else earliest):
            fail('تاريخ افتتاح الحساب يجب ألا يأتي بعد أول حركة أو وردية أو كشف بنك',409)


@app.get('/api/accounting/opening-reviews')
def fund_opening_reviews(period:str='',user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','viewer')
    month=valid_month(period or current_month())
    reviews=opening_balances.detail(c,month)
    for r in reviews:
        r['can_review']=bool(r['review_status']=='pending' and r['created_by']!=user['id'] and (
            user['role']=='owner' or (user['role']=='reviewer' and c.execute(
                'SELECT 1 FROM user_fund_grants WHERE user_id=? AND fund_id=? AND can_approve=1',
                (user['id'],r['id'])).fetchone())))
    accounts=[dict(r) for r in c.execute('''SELECT id,code,name,class FROM gl_accounts
              WHERE active=1 AND control='' AND class IN ('liability','equity')
              AND code NOT IN ('2300','2310','2350','2190') ORDER BY code''')]
    return {'period':month,'funds':reviews,'offset_accounts':accounts,
            'unverified_count':sum(int(r['review_needed']) for r in reviews),
            'note':'المحضر وحده لا يثبت النقدية الفعلية؛ يلزم عد/كشف أصلي موقّع خارج النظام.'}


@app.post('/api/funds/{fund_id}/opening-review')
def submit_fund_opening_review(fund_id:int,body:OpeningReviewRequest,user=Depends(get_user),
                               c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    effective=valid_date(body.effective_date)
    if effective>datetime.now(ZoneInfo('Africa/Cairo')).date():
        fail('لا يمكن اعتماد بداية مالية بتاريخ مستقبلي',409)
    evidence={'cash':'cash_count','bank':'bank_statement','wallet':'wallet_statement'}
    with c:
        c.execute('BEGIN IMMEDIATE')
        fund=c.execute('SELECT * FROM funds WHERE id=? AND active=1',(fund_id,)).fetchone()
        if not fund:fail('الحساب غير موجود أو معطل',404)
        if body.evidence_kind != evidence[fund['kind']]:
            fail('نوع الإثبات لا يتفق مع نوع الخزنة/البنك',409)
        month_open(c,effective.isoformat()[:7])
        if c.execute("SELECT 1 FROM fund_opening_reviews WHERE fund_id=? AND status IN ('pending','approved')",(fund_id,)).fetchone():
            fail('هناك طلب اعتماد أو محضر افتتاحي معتمد بالفعل لهذه الخزنة',409)
        opening_timeline_guard(c,fund_id,effective.isoformat())
        offset=None
        if fund['opening_piasters']:
            if body.offset_account_id is None:fail('حدد حساب مقابل الافتتاح من حسابات حقوق الملكية/الالتزامات',409)
            offset=c.execute('''SELECT id FROM gl_accounts WHERE id=? AND active=1 AND control=''
                       AND class IN ('equity','liability') AND code NOT IN ('2300','2310','2350','2190')''',
                       (body.offset_account_id,)).fetchone()
            if not offset:fail('الحساب المقابل غير مسموح ضمن القيود الافتتاحية',409)
        elif body.offset_account_id is not None:
            fail('الرصيد الافتتاحي صفر؛ لا يُنشأ قيد افتتاحي وهمي',409)
        cur=c.execute('''INSERT INTO fund_opening_reviews(fund_id,amount_piasters,effective_date,
             evidence_kind,evidence_reference,evidence_note,offset_account_id,created_by,created_at)
             VALUES (?,?,?,?,?,?,?,?,?)''',(
             fund_id,int(fund['opening_piasters']),effective.isoformat(),body.evidence_kind,
             body.evidence_reference.strip(),body.evidence_note.strip(),
             offset['id'] if offset else None,user['id'],stamp()))
        audit(c,user['id'],'fund_opening_proposed','fund',fund_id,
             {'review_id':cur.lastrowid,'amount_piasters':fund['opening_piasters'],
              'date':effective.isoformat(),'reference':body.evidence_reference.strip()})
        return {'id':cur.lastrowid,'status':'pending'}


@app.post('/api/accounting/opening-reviews/{review_id}/decision')
def decide_fund_opening_review(review_id:int,body:OpeningReviewDecision,
                               user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    if body.decision not in ('approve','reject'):fail('قرار المراجعة غير صحيح')
    with c:
        c.execute('BEGIN IMMEDIATE')
        r=c.execute('''SELECT r.*,f.opening_piasters,f.kind,f.active FROM fund_opening_reviews r
              JOIN funds f ON f.id=r.fund_id WHERE r.id=?''',(review_id,)).fetchone()
        if not r:fail('المحضر غير موجود',404)
        if r['status']!='pending':fail('تم البت في المحضر بالفعل',409)
        if r['created_by']==user['id']:fail('لا يجوز اعتماد أو رفض المحضر بواسطة مقدمه',403)
        if not c.execute('SELECT 1 FROM users WHERE id=? AND active=1',(r['created_by'],)).fetchone():
            fail('مقدم الطلب غير نشط؛ يحتاج المحضر إلى إعادة إنشاء مستقلة',409)
        if user['role']!='owner' and not c.execute('''SELECT 1 FROM user_fund_grants
               WHERE user_id=? AND fund_id=? AND can_approve=1''',(user['id'],r['fund_id'])).fetchone():
            fail('المراجع غير مفوض لهذه الخزنة أو البنك',403)
        if r['amount_piasters']!=r['opening_piasters'] or not r['active']:
            fail('بيانات الخزنة تغيرت منذ تقديم المحضر',409)
        month_open(c,r['effective_date'][:7])
        if body.decision=='approve':
            opening_timeline_guard(c,r['fund_id'],r['effective_date'])
        if body.decision=='reject':
            c.execute('''UPDATE fund_opening_reviews SET status='rejected',reviewed_by=?,
                reviewed_at=?,decision_note=? WHERE id=?''',(user['id'],stamp(),body.note.strip(),review_id))
            audit(c,user['id'],'fund_opening_rejected','fund',r['fund_id'],{'review_id':review_id})
            return {'id':review_id,'status':'rejected'}
        amount=int(r['amount_piasters'])
        journal_id=None
        if amount:
            account=c.execute('''SELECT id FROM gl_accounts WHERE id=? AND active=1 AND control=''
               AND class IN ('equity','liability') AND code NOT IN ('2300','2310','2350','2190')''',
               (r['offset_account_id'],)).fetchone()
            if not account:fail('الحساب المقابل توقف أو تغير؛ لا يمكن الاعتماد',409)
            fund_account=ledger.ensure_fund_account(c,r['fund_id'])
            # The historical ledger's origin CHECK cannot accept an added origin
            # without a destructive table rebuild. The source FK and audit make
            # this a source-backed opening, never a reversible freehand journal.
            journal_id=ledger._journal(c,entry_date=r['effective_date'],
                 memo='رصيد افتتاحي موثق لخزنة '+str(r['fund_id'])+' / '+r['evidence_reference'],
                 origin='manual',source_id=review_id,created_by=r['created_by'],
                 reviewed_by=user['id'],lines=[(fund_account,amount,0,None),
                                               (account['id'],0,amount,None)])
        c.execute('''UPDATE fund_opening_reviews SET status='approved',reviewed_by=?,
             reviewed_at=?,decision_note=?,journal_id=? WHERE id=?''',
             (user['id'],stamp(),body.note.strip(),journal_id,review_id))
        audit(c,user['id'],'fund_opening_approved','fund',r['fund_id'],
             {'review_id':review_id,'journal_id':journal_id,'amount_piasters':amount})
        return {'id':review_id,'status':'approved','journal_id':journal_id}


@app.get("/api/dashboard")
def dashboard(month:str="",dept:int|None=None,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    month=valid_month(month or current_month())
    args=[month]
    # Reversal is a distinct posting; count it as negative on its own effective date.
    condition="substr(v.date,1,7)=? AND v.status IN ('approved','reversed')"
    if user["role"]=="clerk":
        condition+=" AND "+clerk_voucher_scope();args.extend((user["id"],user["id"]))
    if dept:
        condition+=" AND v.department_id=?";args.append(dept)
    sums=c.execute(f"""SELECT v.kind,coalesce(sum({signed_sql()}),0) amt
         FROM vouchers v WHERE {condition} GROUP BY v.kind""",args).fetchall()
    amounts={r["kind"]:r["amt"] for r in sums}
    pending_where="substr(date,1,7)=? AND status='pending'";p_args=[month]
    if dept: pending_where+=" AND department_id=?";p_args.append(dept)
    if user["role"]=="clerk":pending_where+=" AND created_by=?";p_args.append(user["id"])
    pending=c.execute("SELECT count(*) FROM vouchers WHERE "+pending_where,p_args).fetchone()[0]
    daily=[dict(r) for r in c.execute(f"""SELECT v.date,v.kind,coalesce(sum({signed_sql()}),0) amount
             FROM vouchers v WHERE {condition} AND v.kind IN ('receipt','payment') GROUP BY v.date,v.kind ORDER BY v.date""",args)]
    latest_where="substr(v.date,1,7)=? AND v.status IN ('approved','reversed','pending')"
    latest_args=[month]
    if user["role"]=="clerk":latest_where+=" AND "+clerk_voucher_scope();latest_args.extend((user["id"],user["id"]))
    latest=[dict(r) for r in c.execute("""SELECT v.id,v.voucher_no,v.date,v.kind,v.amount_piasters,v.status,
                      v.description,d.name department,ca.name category FROM vouchers v
                      LEFT JOIN departments d ON d.id=v.department_id LEFT JOIN categories ca ON ca.id=v.category_id WHERE """+
                      latest_where+" ORDER BY v.created_at DESC,v.id DESC LIMIT 8",latest_args)]
    legacy_count=c.execute("SELECT count(*) FROM legacy_issues WHERE status='open'").fetchone()[0] if user["role"] in ("owner","reviewer") else None
    return {"month":month,"receipts_piasters":amounts.get("receipt",0),"payments_piasters":amounts.get("payment",0),
            "cash_difference_piasters":amounts.get("receipt",0)-amounts.get("payment",0),
            "pending":pending,"daily":daily,"latest":latest,"legacy_issues":legacy_count,
            "note":"حركة النقدية لا تعني الربح المحاسبي. التحويلات الداخلية لا تدخل في الوارد/المنصرف."}


@app.get("/api/reports")
def reports(month:str="",user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner","reviewer","viewer")
    month=valid_month(month or current_month())
    by_dept=[dict(r) for r in c.execute(f"""SELECT coalesce(d.name,'غير موزع') department,
      coalesce(sum(CASE WHEN v.kind='receipt' AND ca.nature='revenue' THEN {signed_sql()} ELSE 0 END),0) earned_cash_in,
      coalesce(sum(CASE WHEN v.kind='payment' AND ca.nature='expense' THEN {signed_sql()} ELSE 0 END),0) operating_cash_out,
      coalesce(sum(CASE WHEN v.kind='payment' AND ca.nature IN ('asset','liability','equity','payroll_payment','advance') THEN {signed_sql()} ELSE 0 END),0) non_operating_cash_out
      FROM vouchers v LEFT JOIN departments d ON d.id=v.department_id LEFT JOIN categories ca ON ca.id=v.category_id
      WHERE substr(v.date,1,7)=? AND v.status IN ('approved','reversed') GROUP BY coalesce(d.name,'غير موزع') ORDER BY earned_cash_in DESC""",(month,))]
    categories=[dict(r) for r in c.execute(f"""SELECT ca.name category,ca.nature,coalesce(sum({signed_sql()}),0) amount_piasters
      FROM vouchers v JOIN categories ca ON ca.id=v.category_id
      WHERE substr(v.date,1,7)=? AND v.status IN ('approved','reversed') AND v.kind='payment'
      GROUP BY ca.id ORDER BY amount_piasters DESC""",(month,))]
    accrued=c.execute("""SELECT coalesce(sum(net_piasters),0) FROM payroll_accruals
         WHERE period=? AND signoff_status IN ('approved','legacy')""",(month,)).fetchone()[0]
    # GL is authoritative for posted revenues/expenses. Cash receipts, advances,
    # refunds and inter-fund transfers MUST NOT be counted twice as earned income.
    gl_by_dept=[dict(r) for r in c.execute("""SELECT COALESCE(d.name,'غير موزع') department,
      COALESCE(SUM(CASE WHEN a.class='revenue' THEN l.credit_piasters-l.debit_piasters ELSE 0 END),0) recognized_revenue_piasters,
      COALESCE(SUM(CASE WHEN a.class='expense' THEN l.debit_piasters-l.credit_piasters ELSE 0 END),0) recognized_expense_piasters
      FROM gl_lines l JOIN gl_journals j ON j.id=l.journal_id
      JOIN gl_accounts a ON a.id=l.account_id
      LEFT JOIN departments d ON d.id=l.department_id
      WHERE substr(j.entry_date,1,7)=? AND j.status='posted' AND a.class IN ('revenue','expense')
      GROUP BY COALESCE(d.name,'غير موزع') ORDER BY recognized_revenue_piasters DESC""",(month,))]
    earned=sum(r['recognized_revenue_piasters'] for r in gl_by_dept)
    costs=sum(r['recognized_expense_piasters'] for r in gl_by_dept)
    receipts=sum(r["earned_cash_in"] for r in by_dept)
    direct_exp=sum(r["operating_cash_out"] for r in by_dept)
    return {"month":month,"departments":by_dept,"categories":categories,
            "gl_departments":gl_by_dept,
            "recognized_revenue_piasters":earned,
            "recognized_expenses_piasters":costs,
            "provisional_gl_result_piasters":earned-costs,
            "recognized_cash_service_revenue_piasters":receipts,
            "cash_paid_operating_items_piasters":direct_exp,
            "approved_payroll_accruals_piasters":accrued,
            "rough_margin_piasters":receipts-direct_exp-accrued,
            "note":"الإيرادات والمصروفات المعروضة من قيود الأستاذ المُرحّلة فقط؛ نتيجة الأستاذ مبدئية وليست صافي ربح معتمدًا قبل إثبات المخزون والاستهلاك والذمم والتسويات. المقبوضات النقدية منفصلة عن الإيراد."}


@app.get("/api/employees")
def employees(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner","reviewer","viewer")
    return [dict(r) for r in c.execute("""SELECT e.id,e.code,e.name,e.job_title,e.department_id,d.name department,e.active
              FROM employees e LEFT JOIN departments d ON d.id=e.department_id ORDER BY e.name""")]


@app.post("/api/employees")
def employee_add(body:EmployeeForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner")
    if not (3<=len(body.name.strip())<=100) or not re.fullmatch(r"[A-Za-z0-9_-]{2,24}",body.code):
        fail("بيانات الموظف أو كوده غير صحيحة")
    if body.department_id:lookup(c,"departments",body.department_id)
    try:
        with c:
            cur=c.execute("INSERT INTO employees(code,name,job_title,department_id) VALUES (?,?,?,?)",
                          (body.code.strip(),body.name.strip(),body.job_title.strip()[:100],body.department_id))
            audit(c,user["id"],"create_employee","employee",cur.lastrowid)
    except sqlite3.IntegrityError:
        fail("كود الموظف موجود بالفعل")
    return {"id":cur.lastrowid}


@app.post("/api/employees/{employee_id}/salary-term")
def employee_salary(employee_id:int,body:SalaryTerm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner")
    period=valid_month(body.month)
    if body.pay_type not in ("monthly","hourly"):
        fail("نوع الأجر يجب أن يكون شهريًا أو بالساعة")
    monthly=c_piasters(body.monthly_salary,allow_zero=True) if body.pay_type=="monthly" else 0
    hourly=c_piasters(body.hourly_rate) if body.pay_type=="hourly" else 0
    if body.pay_type=="monthly" and body.monthly_salary is None:
        fail("أدخل قيمة الراتب الشهري")
    if body.pay_type=="hourly" and body.hourly_rate is None:
        fail("أدخل أجر الساعة")
    if (body.pay_type=="hourly" and body.monthly_salary not in (None,"")) or (body.pay_type=="monthly" and body.hourly_rate not in (None,"")):
        fail("لا يمكن إدخال راتب شهري وأجر بالساعة لنفس التعاقد")
    lookup(c,"employees",employee_id)
    with c:
        c.execute("BEGIN IMMEDIATE")
        month_open(c,period)
        newer=c.execute("SELECT 1 FROM salary_terms WHERE employee_id=? AND valid_from>=?",(employee_id,period+"-01")).fetchone()
        if newer:
            fail("توجد شروط أجر سارية من هذا الشهر أو بعده؛ اختر فترة أحدث",409)
        if c.execute("SELECT 1 FROM payroll_accruals WHERE employee_id=? AND period>=? LIMIT 1",(employee_id,period)).fetchone():
            fail("لا يمكن تغيير نوع الأجر بأثر رجعي على كشف مرتبات معتمد",409)
        if c.execute("""SELECT 1 FROM payroll_adjustments WHERE employee_id=? AND period>=?
            AND status IN ('pending','approved') LIMIT 1""",(employee_id,period)).fetchone():
            fail('هناك إضافات أو خصومات مرتبطة بشروط الأجر القديمة؛ أنه مراجعتها أولًا',409)
        if c.execute("""SELECT 1 FROM payroll_work_entries WHERE employee_id=? AND substr(work_date,1,7)>=?
            AND status IN ('pending','approved') LIMIT 1""",(employee_id,period)).fetchone():
            fail("هناك ساعات عمل معلقة أو معتمدة؛ أنهِ مراجعتها قبل تغيير نظام الأجر",409)
        cur=c.execute("""INSERT INTO salary_terms(employee_id,monthly_piasters,valid_from,note,pay_type,hourly_piasters)
                         VALUES (?,?,?,?,?,?)""",
                      (employee_id,monthly,period+"-01",body.note.strip()[:150],body.pay_type,hourly))
        audit(c,user["id"],"set_salary_terms","employee",employee_id,
              {"effective":period,"pay_type":body.pay_type,"monthly_piasters":monthly,"hourly_piasters":hourly})
    return {"id":cur.lastrowid,"pay_type":body.pay_type}


def approved_adjustment_totals(c, employee_id, period):
    totals=c.execute("""SELECT kind,coalesce(sum(amount_piasters),0) amount FROM payroll_adjustments
           WHERE employee_id=? AND period=? AND status='approved' GROUP BY kind""",
           (employee_id,period)).fetchall()
    additions=sum(r['amount'] for r in totals if r['kind'] in PAYROLL_ADDITION_KINDS)
    deductions=sum(r['amount'] for r in totals if r['kind'] in PAYROLL_DEDUCTION_KINDS)
    pending=c.execute("""SELECT count(*) FROM payroll_adjustments WHERE employee_id=? AND period=?
            AND status='pending'""",(employee_id,period)).fetchone()[0]
    return additions,deductions,pending


@app.get("/api/payroll/adjustments")
def list_payroll_adjustments(period:str='',employee_id:int|None=None,page:int=1,
                             user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    period=valid_month(period or current_month())
    if page<1:fail('رقم الصفحة غير صالح')
    where='a.period=?';args=[period]
    if employee_id is not None:
        where+=' AND a.employee_id=?';args.append(employee_id)
    total=c.execute('SELECT count(*) FROM payroll_adjustments a WHERE '+where,args).fetchone()[0]
    rows=[dict(r) for r in c.execute(f"""SELECT a.*,e.name employee_name,e.code employee_code,
      u.username created_by_name,ru.username reviewed_by_name
      FROM payroll_adjustments a JOIN employees e ON e.id=a.employee_id
      JOIN users u ON u.id=a.created_by LEFT JOIN users ru ON ru.id=a.reviewed_by
      WHERE {where} ORDER BY CASE WHEN a.status='pending' THEN 0 ELSE 1 END,a.id DESC
      LIMIT 60 OFFSET ?""",args+[(page-1)*60])]
    pending=c.execute('SELECT count(*) FROM payroll_adjustments a WHERE '+where+" AND a.status='pending'",args).fetchone()[0]
    return {'period':period,'items':rows,'total':total,'pending_count':pending,
            'page':page,'pages':(total+59)//60,
            'note':'الإضافي والتأخير والغياب والإجازات مبالغ يدوية تستلزم سببًا ومراجعة، لا تُحسب تلقائيًا دون سياسة معتمدة.'}


@app.post("/api/payroll/adjustments")
def create_payroll_adjustment(body:PayrollAdjustmentForm,user=Depends(get_user),
                              c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    period=valid_month(body.period)
    if body.kind not in PAYROLL_ADDITION_KINDS|PAYROLL_DEDUCTION_KINDS:
        fail('نوع التسوية غير صالح')
    amount=c_piasters(body.amount)
    note=body.note.strip()
    if not 8<=len(note)<=400:fail('اشرح سبب الإضافة أو الخصم بوضوح')
    lookup(c,'employees',body.employee_id)
    with c:
        c.execute('BEGIN IMMEDIATE')
        month_open(c,period)
        if c.execute('SELECT 1 FROM payroll_accruals WHERE employee_id=? AND period=?',
                     (body.employee_id,period)).fetchone():
            fail('كشف الاستحقاق تم إعداده بالفعل؛ لا يمكن إضافة بنود جديدة دون دورة تصحيح',409)
        cur=c.execute("""INSERT INTO payroll_adjustments
             (employee_id,period,kind,amount_piasters,note,created_by,created_at)
             VALUES (?,?,?,?,?,?,?)""",
             (body.employee_id,period,body.kind,amount,note,user['id'],stamp()))
        audit(c,user['id'],'create_payroll_adjustment','payroll_adjustment',cur.lastrowid,
              {'period':period,'kind':body.kind,'amount_piasters':amount})
    return {'id':cur.lastrowid,'status':'pending'}


@app.post("/api/payroll/adjustments/{adjustment_id}/decision")
def decide_payroll_adjustment(adjustment_id:int,body:PayrollDecisionForm,
                              user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    if body.decision not in ('approve','reject'):fail('قرار غير صالح')
    reason=body.reason.strip()
    if body.decision=='reject' and not 8<=len(reason)<=400:
        fail('اكتب سبب رفض البند')
    with c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM payroll_adjustments WHERE id=?',(adjustment_id,)).fetchone()
        if not row:fail('البند غير موجود',404)
        month_open(c,row['period'])
        if row['status']!='pending':fail('تمت مراجعة البند بالفعل',409)
        if row['created_by']==user['id']:fail('لا يجوز مراجعة بند أجر أدخلته بنفسك',403)
        if c.execute('SELECT 1 FROM payroll_accruals WHERE employee_id=? AND period=?',
                     (row['employee_id'],row['period'])).fetchone():
            fail('تم إعداد استحقاق الموظف بالفعل',409)
        status='approved' if body.decision=='approve' else 'rejected'
        c.execute('UPDATE payroll_adjustments SET status=?,reviewed_by=?,reviewed_at=?,review_note=? WHERE id=?',
                  (status,user['id'],stamp(),reason,adjustment_id))
        audit(c,user['id'],'review_payroll_adjustment','payroll_adjustment',adjustment_id,
              {'decision':status,'reason':reason})
    return {'id':adjustment_id,'status':status}


@app.post("/api/payroll/adjustments/{adjustment_id}/void")
def void_payroll_adjustment(adjustment_id:int,body:PayrollDecisionForm,
                            user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    reason=body.reason.strip()
    if not 8<=len(reason)<=400:fail('اكتب سبب إلغاء البند المعتمد')
    with c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM payroll_adjustments WHERE id=?',(adjustment_id,)).fetchone()
        if not row:fail('البند غير موجود',404)
        month_open(c,row['period'])
        if row['status']!='approved':fail('يسمح بإلغاء البنود المعتمدة فقط',409)
        if c.execute('SELECT 1 FROM payroll_accruals WHERE employee_id=? AND period=?',
                     (row['employee_id'],row['period'])).fetchone():
            fail('لا يمكن حذف بند دخل في كشف استحقاق؛ يجب تصحيحه ماليًا',409)
        c.execute("UPDATE payroll_adjustments SET status='voided',reviewed_by=?,reviewed_at=?,review_note=? WHERE id=?",
                  (user['id'],stamp(),reason,adjustment_id))
        audit(c,user['id'],'void_payroll_adjustment','payroll_adjustment',adjustment_id,
              {'reason':reason})
    return {'id':adjustment_id,'status':'voided'}


@app.get("/api/payroll/work-entries")
def work_entries(period:str="",employee_id:int|None=None,page:int=1,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner","reviewer")
    period=valid_month(period or current_month())
    if page<1:fail('رقم الصفحة غير صالح')
    where="substr(w.work_date,1,7)=?";args=[period]
    if employee_id is not None:
        where+=' AND w.employee_id=?';args.append(employee_id)
    total=c.execute(f'SELECT count(*) FROM payroll_work_entries w WHERE {where}',args).fetchone()[0]
    stats=c.execute(f"""SELECT count(*) FILTER(WHERE status='pending') pending,
        coalesce(sum(CASE WHEN status='approved' THEN work_minutes ELSE 0 END),0) approved_minutes
        FROM payroll_work_entries w WHERE {where}""",args).fetchone()
    sql=f"""SELECT w.*,e.code employee_code,e.name employee_name,u.username created_by_name,
          ru.username reviewed_by_name FROM payroll_work_entries w
          JOIN employees e ON e.id=w.employee_id JOIN users u ON u.id=w.created_by
          LEFT JOIN users ru ON ru.id=w.reviewed_by WHERE {where}
          ORDER BY CASE WHEN w.status='pending' THEN 0 ELSE 1 END,w.work_date DESC,w.id DESC
          LIMIT 60 OFFSET ?"""
    items=[dict(r) for r in c.execute(sql,args+[(page-1)*60])]
    return {"period":period,"items":items,"page":page,"pages":(total+59)//60,
            "total":total,"pending_count":stats['pending'],
            "approved_minutes":stats['approved_minutes'],
            "note":"الساعات تُسجل يدويًا لا بالبصمة؛ يلزم اعتماد شخص آخر."}


@app.get("/api/payroll/work-entries/export.csv")
def export_work_entries(period:str="",user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    period=valid_month(period or current_month())
    output=io.StringIO();writer=csv.writer(output)
    writer.writerow(['كود الموظف','اسم الموظف','تاريخ العمل','الفترة','الساعات','الدقائق',
                     'الدقائق الإجمالية','حالة المراجعة','مدخل الساعات','المراجع','الوصف','ملاحظة المراجعة'])
    for r in c.execute("""SELECT e.code,e.name,w.work_date,w.shift,w.work_minutes,w.status,
       u.username creator,ru.username reviewer,w.note,w.review_note
       FROM payroll_work_entries w JOIN employees e ON e.id=w.employee_id
       JOIN users u ON u.id=w.created_by LEFT JOIN users ru ON ru.id=w.reviewed_by
       WHERE substr(w.work_date,1,7)=? ORDER BY w.work_date,w.id""",(period,)):
        mins=r['work_minutes']
        vals=[r['code'],r['name'],r['work_date'],r['shift'],mins//60,mins%60,mins,
              r['status'],r['creator'],r['reviewer'],r['note'],r['review_note']]
        writer.writerow([safe_csv_cell(x) if isinstance(x,str) else x for x in vals])
    return Response(content='\ufeff'+output.getvalue(),media_type='text/csv; charset=utf-8',
      headers={'Content-Disposition':f'attachment; filename="ramses_work_hours_{period}.csv"',
               'Cache-Control':'no-store'})


@app.post("/api/payroll/work-entries")
def create_work_entry(body:WorkEntryForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner","reviewer")
    day=valid_date(body.work_date)
    period=day.strftime('%Y-%m')
    if body.shift not in SHIFTS:
        fail("الفترة غير صحيحة")
    minutes=body.hours*60+body.minutes
    if not 0<minutes<=1440:
        fail("الساعات يجب أن تكون أكثر من صفر وبحد أقصى 24 ساعة في السجل")
    if not 3<=len(body.note.strip())<=300:
        fail("اكتب وصفًا مختصرًا للوردية أو طبيعة العمل")
    emp=lookup(c,"employees",body.employee_id)
    with c:
        c.execute("BEGIN IMMEDIATE")
        month_open(c,period)
        term=salary_term_for(c,emp['id'],period)
        if not term or term['pay_type']!='hourly':
            fail("لا يمكن إدخال ساعات قبل تحديد أجر الساعة لهذا الموظف والفترة",409)
        if c.execute("SELECT 1 FROM payroll_accruals WHERE employee_id=? AND period=?",(emp['id'],period)).fetchone():
            fail("تم اعتماد كشف الاستحقاق؛ لا يمكن تغيير ساعات هذا الشهر",409)
        total_day=c.execute("""SELECT coalesce(sum(work_minutes),0) FROM payroll_work_entries
          WHERE employee_id=? AND work_date=? AND status IN ('pending','approved')""",
          (emp['id'],day.isoformat())).fetchone()[0]
        if total_day+minutes>1440:
            fail('إجمالي ساعات نفس الموظف يتجاوز 24 ساعة في اليوم الواحد',409)
        try:
            cur=c.execute("""INSERT INTO payroll_work_entries(employee_id,work_date,shift,work_minutes,note,
                      created_by,created_at) VALUES (?,?,?,?,?,?,?)""",
                  (emp['id'],day.isoformat(),body.shift,minutes,body.note.strip(),user['id'],stamp()))
        except sqlite3.IntegrityError:
            fail("تم تسجيل ساعات لهذه الفترة بالفعل؛ يلزم مراجعتها أولًا",409)
        audit(c,user['id'],'create_work_entry','work_entry',cur.lastrowid,
              {'employee_id':emp['id'],'date':day.isoformat(),'minutes':minutes,'shift':body.shift})
    return {'id':cur.lastrowid,'status':'pending','work_minutes':minutes}


@app.post("/api/payroll/work-entries/{entry_id}/decision")
def review_work_entry(entry_id:int,body:WorkEntryDecision,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner","reviewer")
    if body.decision not in ('approve','reject'):
        fail("قرار المراجعة غير صحيح")
    reason=body.reason.strip()
    if body.decision=='reject' and not 8<=len(reason)<=300:
        fail("يجب توضيح سبب رفض الساعات")
    with c:
        c.execute("BEGIN IMMEDIATE")
        row=c.execute('SELECT * FROM payroll_work_entries WHERE id=?',(entry_id,)).fetchone()
        if not row: fail('سجل الساعات غير موجود',404)
        month_open(c,row['work_date'][:7])
        if row['status']!='pending': fail('تم اتخاذ قرار بشأن الساعات بالفعل',409)
        if row['created_by']==user['id']:fail('لا يجوز اعتماد أو رفض ساعات أدخلتها بنفسك',403)
        if c.execute('SELECT 1 FROM payroll_accruals WHERE employee_id=? AND period=?',
                     (row['employee_id'],row['work_date'][:7])).fetchone():
            fail('كشف المرتبات معتمد بالفعل',409)
        status='approved' if body.decision=='approve' else 'rejected'
        c.execute('UPDATE payroll_work_entries SET status=?,reviewed_by=?,reviewed_at=?,review_note=? WHERE id=?',
                  (status,user['id'],stamp(),reason,entry_id))
        audit(c,user['id'],'review_work_entry','work_entry',entry_id,{'decision':status,'reason':reason})
    return {'id':entry_id,'status':status}


@app.post("/api/payroll/work-entries/{entry_id}/void")
def void_work_entry(entry_id:int,body:WorkEntryDecision,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    reason=body.reason.strip()
    if not 8<=len(reason)<=300:fail('اكتب سبب تصحيح الساعات المعتمدة')
    with c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM payroll_work_entries WHERE id=?',(entry_id,)).fetchone()
        if not row:fail('سجل الساعات غير موجود',404)
        month_open(c,row['work_date'][:7])
        if row['status']!='approved':fail('يمكن إلغاء الساعات المعتمدة فقط',409)
        if c.execute('SELECT 1 FROM payroll_accruals WHERE employee_id=? AND period=?',
                     (row['employee_id'],row['work_date'][:7])).fetchone():
            fail('لا يمكن تعديل ساعات بعد اعتماد كشف المرتبات',409)
        c.execute('UPDATE payroll_work_entries SET status=?,reviewed_by=?,reviewed_at=?,review_note=? WHERE id=?',
                  ('voided',user['id'],stamp(),reason,entry_id))
        audit(c,user['id'],'void_work_entry','work_entry',entry_id,
              {'employee_id':row['employee_id'],'minutes':row['work_minutes'],'reason':reason})
    return {'id':entry_id,'status':'voided'}


@app.get("/api/payroll")
def payroll(period:str="",user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner","reviewer")
    period=valid_month(period or current_month())
    rows=[]
    # Include inactive staff with historical accruals or hours in this month; deactivation must not hide liabilities.
    for emp in c.execute("""SELECT e.*,d.name department FROM employees e
        LEFT JOIN departments d ON d.id=e.department_id WHERE e.active=1
        OR EXISTS(SELECT 1 FROM payroll_accruals pa WHERE pa.employee_id=e.id AND pa.period=?)
        OR EXISTS(SELECT 1 FROM payroll_work_entries pw WHERE pw.employee_id=e.id AND substr(pw.work_date,1,7)=?)
        ORDER BY e.name""",(period,period)).fetchall():
        term=salary_term_for(c,emp['id'],period)
        accr=c.execute('SELECT * FROM payroll_accruals WHERE employee_id=? AND period=?',(emp['id'],period)).fetchone()
        totals=work_totals(c,emp['id'],period)
        adj_add,adj_deduct,adj_pending=approved_adjustment_totals(c,emp['id'],period)
        alloc=c.execute("SELECT coalesce(sum(amount_piasters),0) FROM advance_allocations WHERE employee_id=? AND period=?",(emp['id'],period)).fetchone()[0]
        pay_type=accr['pay_type'] if accr else (term['pay_type'] if term else None)
        rate=accr['hourly_rate_piasters'] if accr and pay_type=='hourly' else (term['hourly_piasters'] if term and pay_type=='hourly' else None)
        paid=salary_payments(c,emp['id'],period)
        d=dict(emp)
        d.update({
            'pay_type':pay_type,
            'monthly_piasters':term['monthly_piasters'] if term and term['pay_type']=='monthly' else None,
            'hourly_rate_piasters':rate,
            'approved_work_minutes':totals['approved_minutes'],
            'pending_work_entries':totals['pending_count'],
            'approved_work_entries':totals['approved_count'],
            'estimated_base_piasters':hourly_wage(rate,totals['approved_minutes']) if rate is not None and not accr else (accr['base_piasters'] if accr else (term['monthly_piasters'] if term else None)),
            'accrual_piasters':accr['net_piasters'] if accr else None,
            'accrual_id':accr['id'] if accr else None,
            'signoff_status':accr['signoff_status'] if accr else None,
            'prepared_by':accr['approved_by'] if accr else None,
            'signed_off_by':accr['signed_off_by'] if accr else None,
            'pending_adjustments':adj_pending,
            'approved_adjustment_additions_piasters':adj_add,
            'approved_adjustment_deductions_piasters':adj_deduct,
            'snapshot_adjustment_additions_piasters':accr['adjustment_additions_piasters'] if accr else None,
            'snapshot_adjustment_deductions_piasters':accr['adjustment_deductions_piasters'] if accr else None,
            'accrual_base_piasters':accr['base_piasters'] if accr else None,
            'accrual_work_minutes':accr['worked_minutes'] if accr else None,
            'can_correct':bool(accr) and alloc==0 and not c.execute("""SELECT 1 FROM vouchers v
                JOIN categories cat ON cat.id=v.category_id
                WHERE v.employee_id=? AND v.salary_period=? AND cat.code='salary_payment'
                AND v.status IN ('pending','approved','reversed') LIMIT 1""",(emp['id'],period)).fetchone(),
            'additions_piasters':accr['additions_piasters'] if accr else None,
            'deductions_piasters':accr['deductions_piasters'] if accr else None,
            'payments_piasters':paid,
            'advances_outstanding_piasters':outstanding_advance(c,emp['id']),
            'allocated_advances_piasters':alloc,
            'due_piasters':payroll_due(c,emp['id'],period)
        })
        rows.append(d)
    return {'period':period,'items':rows,
            'hourly_employees':sum(r['pay_type']=='hourly' for r in rows),
            'monthly_employees':sum(r['pay_type']=='monthly' for r in rows),
            'pending_work_entries':sum(r['pending_work_entries'] for r in rows),
            'accrual_total_piasters':sum(r['accrual_piasters'] or 0 for r in rows),
            'approved_accrual_total_piasters':sum(r['accrual_piasters'] or 0 for r in rows if r['signoff_status'] in ('approved','legacy')),
            'due_total_piasters':sum(r['due_piasters'] or 0 for r in rows),
            'pending_signoffs':sum(r['signoff_status']=='pending' for r in rows),
            'pending_adjustments':sum(r['pending_adjustments'] for r in rows),
            'note':'موظفو الساعة: الدقائق المعتمدة × سعر الساعة. بنود الإضافي والغياب والتأخير والإجازة تدخل كمبالغ موثقة ومعتمدة يدويًا. إعداد الكشف لا يسمح بالصرف قبل توقيع مراجع مختلف.'}


@app.post("/api/payroll/accrual")
def payroll_accrue(body:AccrualForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner")
    period=valid_month(body.period)
    additions=c_piasters(body.additions,allow_zero=True)
    deductions=c_piasters(body.deductions,allow_zero=True)
    emp=lookup(c,"employees",body.employee_id)
    with c:
        c.execute("BEGIN IMMEDIATE")
        month_open(c,period)
        term=salary_term_for(c,emp['id'],period)
        if not term:fail('حدد نوع الأجر وقيمته أولًا',409)
        totals=work_totals(c,emp['id'],period)
        adj_add,adj_deduct,adj_pending=approved_adjustment_totals(c,emp['id'],period)
        if adj_pending:fail('هناك إضافات أو خصومات تنتظر المراجعة؛ لا يمكن إعداد كشف المرتبات',409)
        if term['pay_type']=='hourly':
            if totals['pending_count']:
                fail('هناك ساعات عمل لم تتم مراجعتها؛ لا يمكن اعتماد الراتب',409)
            if totals['approved_count']==0:
                fail('لا توجد ساعات عمل معتمدة للفترة؛ لا يمكن إصدار استحقاق بالساعة',409)
            base=hourly_wage(term['hourly_piasters'],totals['approved_minutes'])
        else:
            base=term['monthly_piasters']
        net=base+additions+adj_add-deductions-adj_deduct
        if net<0:fail('الخصومات المعتمدة تتجاوز المستحق')
        try:
            cur=c.execute("""INSERT INTO payroll_accruals(employee_id,period,base_piasters,additions_piasters,
                deductions_piasters,net_piasters,approved_by,approved_at,pay_type,hourly_rate_piasters,
                worked_minutes,work_entries_count,adjustment_additions_piasters,adjustment_deductions_piasters,
                signoff_status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (emp['id'],period,base,additions,deductions,net,user['id'],stamp(),term['pay_type'],
                 term['hourly_piasters'] if term['pay_type']=='hourly' else 0,
                 totals['approved_minutes'] if term['pay_type']=='hourly' else 0,
                 totals['approved_count'] if term['pay_type']=='hourly' else 0,adj_add,adj_deduct,'pending'))
        except sqlite3.IntegrityError:
            fail('استحقاق هذا الموظف للفترة معتمد بالفعل',409)
        audit(c,user['id'],'prepare_payroll_accrual','payroll',cur.lastrowid,
              {'employee_id':emp['id'],'period':period,'net_piasters':net,'pay_type':term['pay_type'],
               'work_minutes':totals['approved_minutes'] if term['pay_type']=='hourly' else 0})
    return {'id':cur.lastrowid,'net_piasters':net,'base_piasters':base,
            'pay_type':term['pay_type'],'signoff_status':'pending'}


@app.post("/api/payroll/accrual/{accrual_id}/decision")
def decide_payroll_accrual(accrual_id:int,body:PayrollDecisionForm,user=Depends(get_user),
                           c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    if body.decision not in ('approve','reject'):fail('قرار غير صالح')
    reason=body.reason.strip()
    if body.decision=='reject' and not 8<=len(reason)<=400:fail('وضح سبب رفض كشف المرتبات')
    with c:
        c.execute('BEGIN IMMEDIATE')
        accr=c.execute('SELECT * FROM payroll_accruals WHERE id=?',(accrual_id,)).fetchone()
        if not accr:fail('كشف الاستحقاق غير موجود',404)
        month_open(c,accr['period'])
        if accr['signoff_status']!='pending':fail('تم اتخاذ قرار بشأن الكشف بالفعل',409)
        if accr['approved_by']==user['id']:fail('لا يمكن اعتماد كشف الاستحقاق الذي أعددته بنفسك',403)
        if body.decision=='approve':
            ledger.post_payroll(c,accr,user['id'])
        status='approved' if body.decision=='approve' else 'rejected'
        c.execute("""UPDATE payroll_accruals SET signoff_status=?,signed_off_by=?,
                    signed_off_at=?,signoff_note=? WHERE id=?""",
                  (status,user['id'],stamp(),reason,accrual_id))
        audit(c,user['id'],'payroll_signoff','payroll',accrual_id,
              {'decision':status,'net_piasters':accr['net_piasters'],'reason':reason})
    return {'id':accrual_id,'signoff_status':status}


@app.post("/api/payroll/accrual/{accrual_id}/resubmit")
def resubmit_payroll_accrual(accrual_id:int,body:PayrollDecisionForm,user=Depends(get_user),
                            c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    reason=body.reason.strip()
    if not 8<=len(reason)<=400:fail('وضح سبب إعادة تقديم كشف المرتبات')
    with c:
        c.execute('BEGIN IMMEDIATE')
        accr=c.execute('SELECT * FROM payroll_accruals WHERE id=?',(accrual_id,)).fetchone()
        if not accr:fail('كشف الاستحقاق غير موجود',404)
        month_open(c,accr['period'])
        if accr['signoff_status']!='rejected':fail('الكشف ليس مرفوضًا',409)
        c.execute("""UPDATE payroll_accruals SET signoff_status='pending',
                    signed_off_by=NULL,signed_off_at=NULL,signoff_note='' WHERE id=?""",(accrual_id,))
        audit(c,user['id'],'resubmit_payroll','payroll',accrual_id,{'reason':reason})
    return {'id':accrual_id,'signoff_status':'pending'}


@app.post("/api/payroll/accrual/{accrual_id}/correct")
def correct_payroll_accrual(accrual_id:int,body:AccrualCorrection,
                            user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner")
    additions=c_piasters(body.additions,allow_zero=True)
    deductions=c_piasters(body.deductions,allow_zero=True)
    reason=body.reason.strip()
    if len(reason)<8 or len(reason)>400:fail("يجب توضيح سبب تصحيح كشف الاستحقاق")
    with c:
        c.execute("BEGIN IMMEDIATE")
        old=c.execute("SELECT * FROM payroll_accruals WHERE id=?",(accrual_id,)).fetchone()
        if not old:fail("كشف الاستحقاق غير موجود",404)
        month_open(c,old["period"])
        if old['signoff_status']=='approved':
            fail('كشف المرتبات معتمد ومرحّل إلى دفتر الأستاذ؛ التصحيح يحتاج مستند تسوية مستقل',409)
        if c.execute("""SELECT 1 FROM vouchers v JOIN categories cat ON cat.id=v.category_id
            WHERE v.employee_id=? AND v.salary_period=? AND cat.code='salary_payment'
            AND v.status IN ('pending','approved','reversed') LIMIT 1""",
            (old["employee_id"],old["period"])).fetchone():
            fail("لا يمكن تعديل الاستحقاق بعد إصدار سند صرف راتب؛ استخدم دورة تصحيح مالية مستقلة",409)
        if c.execute("""SELECT 1 FROM advance_allocations
            WHERE employee_id=? AND period=? LIMIT 1""",(old["employee_id"],old["period"])).fetchone():
            fail("لا يمكن تعديل استحقاق تمت تسوية سلفة عليه",409)
        net=old["base_piasters"]+additions+old['adjustment_additions_piasters']-deductions-old['adjustment_deductions_piasters']
        if net<0:fail("الخصومات تتجاوز صافي الاستحقاق")
        if additions==old["additions_piasters"] and deductions==old["deductions_piasters"]:
            fail("لم تتغير قيم الاستحقاق",409)
        c.execute("""UPDATE payroll_accruals SET additions_piasters=?,deductions_piasters=?,net_piasters=?,
            signoff_status='pending',signed_off_by=NULL,signed_off_at=NULL,signoff_note=''
          WHERE id=?""",(additions,deductions,net,accrual_id))
        c.execute("""INSERT INTO payroll_accrual_corrections
          (accrual_id,old_additions,old_deductions,old_net,new_additions,new_deductions,new_net,
            reason,actor_id,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
          (accrual_id,old["additions_piasters"],old["deductions_piasters"],old["net_piasters"],
           additions,deductions,net,reason,user["id"],stamp()))
        audit(c,user["id"],"correct_payroll_accrual","payroll",accrual_id,
              {"previous_piasters":old["net_piasters"],"new_piasters":net,"reason":reason})
    return {"id":accrual_id,"net_piasters":net}


@app.get("/api/payroll/export.csv")
def export_payroll(period:str="",user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner","reviewer")
    period=valid_month(period or current_month())
    output=io.StringIO();writer=csv.writer(output)
    writer.writerow(["كود الموظف","الموظف","شهر الاستحقاق","الأساسي قرش","الإضافات قرش",
                     "الخصومات قرش","المستحق قرش","المدفوع قرش","السلف المسواة قرش","المتبقي قرش",
                     "نوع الأجر","سعر الساعة قرش","دقائق معتمدة","عدد سجلات الساعات",
                     "إضافات بنود معتمدة قرش","خصومات بنود معتمدة قرش","حالة اعتماد الكشف"])
    for r in c.execute("""SELECT e.id,e.code,e.name,p.base_piasters,p.additions_piasters,
       p.deductions_piasters,p.net_piasters,p.pay_type,p.hourly_rate_piasters,p.worked_minutes,
       p.work_entries_count,p.adjustment_additions_piasters,p.adjustment_deductions_piasters,p.signoff_status FROM payroll_accruals p
       JOIN employees e ON e.id=p.employee_id WHERE p.period=? ORDER BY e.code""",(period,)):
        allocated=c.execute("SELECT coalesce(sum(amount_piasters),0) FROM advance_allocations WHERE employee_id=? AND period=?",(r["id"],period)).fetchone()[0]
        paid=salary_payments(c,r["id"],period)
        row=[r["code"],r["name"],period,r["base_piasters"],r["additions_piasters"],
             r["deductions_piasters"],r["net_piasters"],paid,allocated,r["net_piasters"]-paid-allocated,
             r["pay_type"],r["hourly_rate_piasters"],r["worked_minutes"],r["work_entries_count"],
             r['adjustment_additions_piasters'],r['adjustment_deductions_piasters'],r['signoff_status']]
        writer.writerow([safe_csv_cell(value) if isinstance(value,str) else value for value in row])
    return Response(content="\ufeff"+output.getvalue(),media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":f'attachment; filename="ramses_payroll_{period}.csv"',
                 "Cache-Control":"no-store"})


@app.post("/api/payroll/allocate-advance")
def allocate(body:AllocationForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner")
    period=valid_month(body.period);amount=c_piasters(body.amount)
    lookup(c,"employees",body.employee_id)
    with c:
        c.execute("BEGIN IMMEDIATE")
        month_open(c,period)
        if outstanding_advance(c,body.employee_id)<amount:fail("السلف غير المسوّاة لا تكفي",409)
        due=payroll_due(c,body.employee_id,period)
        if due is None or due<amount:fail("لا يوجد استحقاق راتب كافٍ لتسوية السلفة",409)
        cur=c.execute("INSERT INTO advance_allocations(employee_id,period,amount_piasters,actor_id,created_at) VALUES (?,?,?,?,?)",
                      (body.employee_id,period,amount,user["id"],stamp()))
        ledger.post_allocation(c,cur.lastrowid,body.employee_id,period,amount,user["id"])
        audit(c,user["id"],"allocate_advance","allocation",cur.lastrowid,{"employee":body.employee_id,"period":period,"amount":amount})
    return {"id":cur.lastrowid}


@app.get("/api/legacy")
def legacy(page:int=1,issues_only:bool=False,q:str="",user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner","reviewer")
    if page<1: fail("صفحة غير صالحة")
    where="1=1";args=[]
    if issues_only:
        where+=" AND EXISTS (SELECT 1 FROM legacy_issues i WHERE i.source_row=l.source_row AND i.status='open')"
    if q:
        where+=" AND (l.description LIKE ? OR l.reference_no LIKE ? OR l.employee_raw LIKE ?)";args.extend(["%"+q[:60]+"%"]*3)
    total=c.execute("SELECT count(*) FROM legacy_entries l WHERE "+where,args).fetchone()[0]
    rows=[dict(r) for r in c.execute("SELECT l.* FROM legacy_entries l WHERE "+where+" ORDER BY l.source_row LIMIT 50 OFFSET ?",args+[(page-1)*50])]
    issues=[dict(r) for r in c.execute("SELECT * FROM legacy_issues WHERE status='open' ORDER BY source_row LIMIT 100")]
    if user["role"]=="reviewer":
        # Raw historical descriptions can contain patient names. Owner sees originals only.
        for row in rows:
            row["description"]="البيان التاريخي محجوب؛ اطلب مراجعته من مالك النظام"
            row["employee_raw"]=""
        for issue in issues:
            issue["details"]="مراجعة المستند الأصلي بواسطة المالك"
    metrics=[dict(r) for r in c.execute("""SELECT kind,count(*) count,coalesce(sum(total_piasters),0) amount_piasters
                  FROM legacy_entries WHERE transaction_date IS NOT NULL GROUP BY kind""")]
    return {"count":total,"items":rows,"issues":issues,"metrics":metrics,"page":page,"pages":(total+49)//50,
            "disclaimer":"أرشيف تاريخي غير مرحّل للخزن ولا يدخل تقارير التشغيل حتى يتم اعتماده وتسويته."}


@app.get("/api/audit")
def audit_events(page:int=1,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner")
    if page<1:fail("صفحة غير صالحة")
    return [dict(r) for r in c.execute("""SELECT a.*,u.username FROM audit_log a LEFT JOIN users u ON u.id=a.actor_id
              ORDER BY a.id DESC LIMIT 100 OFFSET ?""",((page-1)*100,))]


class JournalLineForm(BaseModel):
    account_id: int
    debit: str = '0'
    credit: str = '0'
    department_id: int | None = None


class ManualJournalForm(BaseModel):
    date: str
    memo: str
    lines: list[JournalLineForm]


class JournalReverseForm(BaseModel):
    date: str
    reason: str


@app.get('/api/accounting/trial-balance')
def accounting_trial_balance(period:str='',user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','viewer')
    month=valid_month(period or current_month())
    return {'trial_balance':ledger.trial_balance(c,month),'coverage':ledger.coverage(c,month)}


@app.get('/api/accounting/trial-balance.csv')
def accounting_trial_balance_csv(period:str='',user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','viewer')
    month=valid_month(period or current_month())
    result=ledger.trial_balance(c,month)
    output=io.StringIO();writer=csv.writer(output)
    writer.writerow(['ميزان مراجعة تجريبي غير مكتمل - لا يستخدم كقائمة مالية نهائية'])
    writer.writerow(['الشهر','كود الحساب','الحساب','الفئة','رصيد مدين قرش','رصيد دائن قرش'])
    for a in result['accounts']:
        if not (a['debit_total'] or a['credit_total']):continue
        writer.writerow([safe_csv_cell(v) for v in (month,a['code'],a['name'],a['class'],
                        a['closing_debit_piasters'],a['closing_credit_piasters'])])
    writer.writerow(['إجمالي','','','',result['debit_piasters'],result['credit_piasters']])
    return Response(content='\ufeff'+output.getvalue(),media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition':f'attachment; filename="ramses_trial_balance_{month}.csv"',
                             'Cache-Control':'no-store'})


@app.get('/api/accounting/journals')
def accounting_journals(period:str='',status:str='',page:int=1,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','viewer')
    month=valid_month(period or current_month())
    if status not in ('','pending','posted','rejected') or not 1<=page<=2000:fail('فلتر غير صحيح')
    where="substr(entry_date,1,7)=?"+(' AND status=?' if status else '')
    args=[month]+([status] if status else [])
    total=c.execute('SELECT count(*) FROM gl_journals WHERE '+where,args).fetchone()[0]
    rows=[dict(x) for x in c.execute('SELECT * FROM gl_journals WHERE '+where+
                ' ORDER BY id DESC LIMIT 30 OFFSET ?',args+[(page-1)*30])]
    for row in rows:
        row['lines']=[dict(x) for x in c.execute('''SELECT l.account_id,a.code,a.name,l.department_id,
                l.debit_piasters,l.credit_piasters FROM gl_lines l JOIN gl_accounts a ON a.id=l.account_id
                WHERE l.journal_id=? ORDER BY l.id''',(row['id'],))]
    return {'month':month,'count':total,'page':page,'items':rows}


@app.post('/api/accounting/journals')
def accounting_create_journal(body:ManualJournalForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    entry_date=valid_date(body.date).isoformat()
    memo=body.memo.strip()
    if not 8<=len(memo)<=500 or not 2<=len(body.lines)<=30:fail('البيان أو عدد أطراف القيد غير صحيح')
    lines=[]
    for x in body.lines:
        debit=c_piasters(x.debit,allow_zero=True)
        credit=c_piasters(x.credit,allow_zero=True)
        if (debit>0)==(credit>0):fail('كل طرف يجب أن يكون مدينًا أو دائنًا فقط')
        lines.append((x.account_id,debit,credit,x.department_id))
    if sum(x[1] for x in lines)!=sum(x[2] for x in lines):fail('القيد غير متوازن؛ يجب تساوي المدين والدائن')
    with c:
        c.execute('BEGIN IMMEDIATE')
        month_open(c,entry_date[:7])
        for account,debit,credit,dept in lines:
            a=c.execute('SELECT id,control,code FROM gl_accounts WHERE id=? AND active=1',(account,)).fetchone()
            if not a:fail('حساب غير موجود أو معطل')
            if a['control']=='fund':fail('لا يجوز إدخال قيد يدوي على خزنة/بنك؛ استخدم السندات',409)
            if a['code'] in financial_integrity.PROTECTED_CODES:
                fail('حساب رقابي أو إيراد طبي محمي؛ استخدم مستند التشغيل أو دورة التسوية المعتمدة',409)
            if dept is not None:lookup(c,'departments',dept)
        jid=ledger._journal(c,entry_date=entry_date,memo=memo,origin='manual',source_id=None,
                             created_by=user['id'],lines=lines)
        audit(c,user['id'],'create_manual_journal','gl_journal',jid)
    return {'id':jid,'status':'pending'}


@app.post('/api/accounting/journals/{journal_id}/decision')
def accounting_decision(journal_id:int,body:Decision,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    if body.decision not in ('approve','reject'):fail('قرار غير صالح')
    reason=body.reason.strip()
    if body.decision=='reject' and len(reason)<8:fail('اذكر سبب رفض القيد')
    with c:
        c.execute('BEGIN IMMEDIATE')
        j=c.execute('SELECT * FROM gl_journals WHERE id=?',(journal_id,)).fetchone()
        if not j:fail('القيد غير موجود',404)
        if j['origin'] not in ('manual','manual_reversal') or j['status']!='pending':fail('لا يوجد قيد قابل للمراجعة',409)
        if j['created_by']==user['id']:fail('لا يمكن اعتماد القيد من مُدخله',403)
        if body.decision=='approve':
            rows=c.execute('SELECT account_id FROM gl_lines WHERE journal_id=?',(journal_id,)).fetchall()
            if j['origin']=='manual':
                if financial_integrity.journal_source(c,journal_id):
                    fail('هذا قيد تلقائي مرتبط بمستند؛ لا يعتمد عبر مراجعة القيود اليدوية',409)
                if financial_integrity.forbidden_manual_lines(c,[(x['account_id'],) for x in rows]):
                    fail('يحتوي القيد على حساب رقابي محمي؛ لا يمكن اعتماده يدويًا',409)
            else:
                error=financial_integrity.reversal_guard(c,j['reversal_of_id'])
                if error:fail(error,409)
        month_open(c,j['entry_date'][:7])
        status='posted' if body.decision=='approve' else 'rejected'
        c.execute('''UPDATE gl_journals SET status=?,reviewed_by=?,reviewed_at=?,review_reason=? WHERE id=?''',
                  (status,user['id'],stamp(),reason,journal_id))
        audit(c,user['id'],'gl_journal_'+status,'gl_journal',journal_id,{'reason':reason})
    return {'id':journal_id,'status':status}


@app.post('/api/accounting/journals/{journal_id}/reverse')
def accounting_reverse(journal_id:int,body:JournalReverseForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer')
    entry_date=valid_date(body.date).isoformat()
    reason=body.reason.strip()
    if not 8<=len(reason)<=500:fail('اشرح سبب عكس القيد')
    with c:
        c.execute('BEGIN IMMEDIATE')
        original=c.execute('SELECT * FROM gl_journals WHERE id=?',(journal_id,)).fetchone()
        error=financial_integrity.reversal_guard(c,journal_id)
        if error:fail(error,409)
        if entry_date<original['entry_date']:fail('تاريخ العكس لا يسبق أصل القيد')
        month_open(c,entry_date[:7])
        if c.execute("SELECT 1 FROM gl_journals WHERE reversal_of_id=? AND status!='rejected'",(journal_id,)).fetchone():
            fail('سبق إعداد عكس لهذا القيد',409)
        lines=[(r['account_id'],r['credit_piasters'],r['debit_piasters'],r['department_id']) for r in
               c.execute('SELECT * FROM gl_lines WHERE journal_id=? ORDER BY id',(journal_id,))]
        jid=ledger._journal(c,entry_date=entry_date,memo='عكس '+str(journal_id)+': '+reason,
                          origin='manual_reversal',source_id=None,reversal_of=journal_id,
                          created_by=user['id'],lines=lines)
        audit(c,user['id'],'request_gl_reversal','gl_journal',jid,{'reversal_of':journal_id})
    return {'id':jid,'status':'pending','reversal_of_id':journal_id}


@app.get("/api/periods")
def periods(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner","reviewer","viewer")
    return [dict(r) for r in c.execute("SELECT * FROM periods ORDER BY period DESC")]


def check_period_close_ready(c,period,user):
    """Single authoritative month-close gate shared by preview and posting."""
    if c.execute("SELECT count(*) FROM vouchers WHERE substr(date,1,7)=? AND status='pending'",(period,)).fetchone()[0]:
        fail("لا يمكن إقفال شهر به سندات معلقة",409)
    # The recorded shift list alone cannot detect a shift which was never opened.
    # Effective-dated station schedules are the authoritative expected population.
    coverage = shift_coverage.report(c,period,{'role':'owner','id':user['id']})
    pending_slots = [slot for slot in coverage['items'] if slot['status']!='closed']
    if pending_slots:
        first=pending_slots[0]
        fail(f"لا يمكن إقفال الشهر: {len(pending_slots)} وردية مطلوبة لم تُعتمد. "
             f"أولها {first['business_date']} - {first['point_name']} - {first['shift_name']} "
             f"({first['status']})",409)
    # Paper/outage recovery is a real unresolved accounting exception. Review the
    # original transactions, not merely the existence of their scanned envelopes.
    pending_late=c.execute('''SELECT id,business_date,shift_code,status FROM late_entry_incidents
        WHERE substr(business_date,1,7)=? AND status!='resolved' ORDER BY id LIMIT 1''',
        (period,)).fetchone()
    if pending_late:
        fail(f"استدراك وردية قديمة #{pending_late['id']} بتاريخ {pending_late['business_date']} "
             f"لم يكتمل ربط مستنداته بالمحاسبة ({pending_late['status']})",409)
    if c.execute('''SELECT 1 FROM late_mixed_shortage_recovery_requests r
       JOIN shift_sessions s ON s.id=r.central_shift_id
       WHERE r.status='pending' AND substr(s.business_date,1,7)=? LIMIT 1''',
                 (period,)).fetchone():
        fail('يوجد محضر استلام نقدية لسداد عجز ظرف لم يراجع بعد؛ يجب اعتماده أو رفضه أولًا',409)
    if c.execute('''SELECT 1 FROM late_mixed_overage_refund_requests r
       JOIN shift_sessions s ON s.id=r.central_shift_id
       WHERE r.status='pending' AND substr(s.business_date,1,7)=? LIMIT 1''',
                 (period,)).fetchone():
        fail('يوجد طلب رد زيادة نقدية من ظرف قديم لم يراجع بعد؛ يجب اعتماده أو رفضه أولًا',409)
    # A newly issued invoice for an old cashier incident must not let today's
    # month close while the historical cash evidence is still unmatched. The
    # original month may already be sealed, so checking ONLY its date is unsafe.
    outstanding_late=c.execute('''SELECT l.case_id,l.incident_id FROM billing_late_cases l
       JOIN late_entry_incidents i ON i.id=l.incident_id
       WHERE (substr(l.recorded_accounting_date,1,7)=?
          OR EXISTS (SELECT 1 FROM billing_invoices b
            WHERE b.case_id=l.case_id AND substr(b.issued_date,1,7)=?))
         AND (i.status!='resolved' OR NOT EXISTS
            (SELECT 1 FROM billing_invoices b WHERE b.case_id=l.case_id)) LIMIT 1''',
         (period,period)).fetchone()
    if outstanding_late:
        fail('لا يمكن إقفال الشهر: فاتورة مستدركة لم تُطابق نقديتها التاريخية (بلاغ #'+
             str(outstanding_late['incident_id'])+')',409)
    # Old unscheduled sessions must also block closure, including detached funds.
    if c.execute("SELECT 1 FROM shift_sessions WHERE substr(business_date,1,7)=? AND status!='closed' LIMIT 1",(period,)).fetchone():
        fail("لا يمكن إقفال شهر قبل اعتماد وإغلاق جميع الورديات المسجلة",409)
    if c.execute("SELECT 1 FROM payroll_accruals WHERE period=? AND signoff_status IN ('pending','rejected') LIMIT 1",(period,)).fetchone():
        fail('لا يمكن إقفال الشهر مع كشوف رواتب لم تعتمد نهائيًا',409)
    if c.execute("SELECT 1 FROM payroll_adjustments WHERE period=? AND status='pending' LIMIT 1",(period,)).fetchone():
        fail('لا يمكن إقفال الشهر مع إضافات أو خصومات تنتظر الاعتماد',409)
    if c.execute("""SELECT 1 FROM payroll_adjustments a LEFT JOIN payroll_accruals p
      ON p.employee_id=a.employee_id AND p.period=a.period
      WHERE a.period=? AND a.status='approved' AND p.id IS NULL LIMIT 1""",(period,)).fetchone():
        fail('هناك بنود أجر معتمدة لم يصدر لها كشف استحقاق',409)
    if c.execute("SELECT 1 FROM payroll_work_entries WHERE substr(work_date,1,7)=? AND status='pending' LIMIT 1",(period,)).fetchone():
        fail("لا يمكن إقفال الشهر مع وجود ساعات عمل تنتظر الاعتماد",409)
    if c.execute("""SELECT 1 FROM payroll_work_entries w
      LEFT JOIN payroll_accruals p ON p.employee_id=w.employee_id AND p.period=substr(w.work_date,1,7)
      WHERE substr(w.work_date,1,7)=? AND w.status='approved' AND p.id IS NULL LIMIT 1""",(period,)).fetchone():
        fail("ساعات عمل معتمدة لم يصدر لها كشف استحقاق بعد",409)
    if c.execute("SELECT 1 FROM pos_settlements WHERE substr(settlement_date,1,7)=? AND status='pending' LIMIT 1", (period,)).fetchone():
        fail('A POS settlement is awaiting independent approval',409)
    # No month close with bank movements or imported statements lacking independent signoff.
    if c.execute("""SELECT 1 FROM funds f WHERE f.kind='bank' AND f.active=1
       AND (EXISTS (SELECT 1 FROM fund_movements m WHERE m.fund_id=f.id AND substr(m.booked_on,1,7)=?)
         OR EXISTS (SELECT 1 FROM bank_statement_batches b WHERE b.fund_id=f.id AND b.period=? AND b.status!='voided'))
       AND NOT EXISTS (SELECT 1 FROM bank_statement_batches b WHERE b.fund_id=f.id AND b.period=? AND b.status='approved')
       LIMIT 1""",(period,period,period)).fetchone():
        fail("لا يمكن إقفال شهر به حركة بنكية قبل إتمام مطابقة البنك واعتمادها",409)
    if c.execute("""SELECT 1 FROM vouchers v WHERE substr(v.date,1,7)=? AND
       v.status IN ('approved','reversed') AND NOT EXISTS
       (SELECT 1 FROM gl_journals j WHERE j.origin='voucher' AND j.source_id=v.id AND j.status='posted')
       LIMIT 1""",(period,)).fetchone():
        fail("لا يمكن إقفال الشهر مع سندات لم تُرحّل إلى دفتر الأستاذ",409)
    if c.execute("""SELECT 1 FROM gl_journals WHERE substr(entry_date,1,7)=? AND status='pending' LIMIT 1""",
                (period,)).fetchone():
        fail("لا يمكن إقفال شهر فيه قيود محاسبية تنتظر الاعتماد",409)
    # Patients may remain admitted for several months: an open CASE is not
    # an unposted invoice. Only actual billable evidence may block closure.
    if c.execute("""SELECT 1 FROM billing_invoice_drafts d
       JOIN billing_cases b ON b.id=d.case_id
       WHERE substr(b.business_date,1,7)=? AND NOT EXISTS
       (SELECT 1 FROM billing_invoices i WHERE i.draft_id=d.id) LIMIT 1""",(period,)).fetchone():
        fail("توجد مسودات فواتير لم تُصدر بعد؛ راجع حالات المرضى",409)
    if c.execute("""SELECT 1 FROM billing_case_lines l
       JOIN billing_cases b ON b.id=l.case_id
       WHERE substr(b.business_date,1,7)=? AND l.state='fulfilled'
       AND NOT EXISTS (SELECT 1 FROM billing_invoice_draft_lines dl
          JOIN billing_invoices i ON i.draft_id=dl.draft_id WHERE dl.case_line_id=l.id)
       LIMIT 1""",(period,)).fetchone():
        fail("توجد خدمات مرضى منفذة لم تُفوتر؛ راجع الحالات قبل إقفال الشهر",409)
    if c.execute("""SELECT 1 FROM billing_invoices i JOIN gl_journals j ON j.id=i.journal_id
       WHERE substr(i.issued_date,1,7)=? AND j.status!='posted' LIMIT 1""",(period,)).fetchone():
        fail("هناك فواتير مرضى لم تُرحّل إلى دفتر الأستاذ",409)
    unapproved_openings=opening_balances.outstanding(c,period)
    if unapproved_openings:
        f=unapproved_openings[0]
        fail(f"لا يمكن إقفال الفترة: افتتاح الخزنة {f['name']} لم يُعتمد بقيد افتتاحي سليم. "
             f"السبب: {f['review_issue']}",409)
    reconciliation=financial_integrity.patient_reconciliation(c,period)
    if not reconciliation['matched']:
        first=next((r for r in reconciliation['checks'] if not r['matched']),None)
        label=first['name'] if first else 'تخصيصات المرضى'
        difference=first['difference_piasters'] if first else 0
        fail(f'فشل تطابق الأستاذ مع دفتر {label}؛ الفرق {difference} قرش. افتح تقرير مطابقة حسابات المرضى.',409)
    treasury=treasury_integrity.treasury_reconciliation(c,period)
    if not treasury['matched']:
        first=treasury['issues'][0]
        fail(f"فشلت مطابقة الخزن والبنوك مع دفتر الأستاذ: {treasury['issue_count']} فرق أو نقص. "
             f"أول ملاحظة: {first['message']}. افتح تقرير مطابقة الخزن والحسابات.",409)
    # Historical auto-posted entries can have legacy origin=manual; only an
    # actual linked source document authorizes posting into protected accounts.
    posted=c.execute("SELECT id,origin FROM gl_journals WHERE status='posted' AND origin IN ('manual','manual_reversal') AND substr(entry_date,1,7)<=?",(period,)).fetchall()
    for j in posted:
        account_ids=[(r['account_id'],) for r in c.execute('SELECT account_id FROM gl_lines WHERE journal_id=?',(j['id'],))]
        if financial_integrity.forbidden_manual_lines(c,account_ids) and not financial_integrity.journal_source(c,j['id']):
            fail(f'القيد #{j["id"]} يؤثر على حساب رقابي دون مستند تشغيلي مرتبط؛ راجع أصل القيد قبل الإقفال',409)
    # Still block current/future months when all other evidence is ready.
    if period>=current_month():
        fail('لا يمكن إقفال الشهر الجاري أو أي شهر مستقبلي قبل انتهائه بتوقيت القاهرة',409)

@app.get('/api/accounting/treasury-reconciliation')
def treasury_reconciliation(period:str='',user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','viewer')
    return treasury_integrity.treasury_reconciliation(c,valid_month(period or current_month()))


@app.get('/api/accounting/treasury-reconciliation.csv')
def treasury_reconciliation_csv(period:str='',user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','viewer')
    result=treasury_integrity.treasury_reconciliation(c,valid_month(period or current_month()))
    out=io.StringIO()
    writer=csv.writer(out)
    writer.writerow(['period','fund_id','code','name','kind','opening_piasters','opening_review_status',
                     'gl_opening_piasters','book_movements_piasters','gl_posted_piasters','delta_piasters',
                     'book_balance_piasters','issue_count','matched'])
    for fund in result['funds']:
        writer.writerow([result['period'],fund['id'],safe_csv_cell(fund['code']),
            safe_csv_cell(fund['name']),fund['kind'],fund['opening_piasters'],
            fund['opening_review_status'],fund['gl_opening_piasters'],fund['movement_piasters'],fund['gl_posted_piasters'],fund['difference_piasters'],
            fund['book_balance_piasters'],fund['issue_count'],fund['matched']])
    writer.writerow([])
    writer.writerow(['issue_type','fund_id','reference','message'])
    for issue in result['issues']:
        writer.writerow([issue['type'],issue['fund_id'] or '',issue['reference'] or '',
                         safe_csv_cell(issue['message'])])
    writer.writerow(['scope',safe_csv_cell(result['scope'])])
    return Response(content='\ufeff'+out.getvalue(),media_type='text/csv; charset=utf-8',
         headers={'Content-Disposition':f'attachment; filename="treasury-integrity-{result["period"]}.csv"',
                  'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})


@app.get('/api/accounting/patient-reconciliation')
def patient_reconciliation(period:str='',user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','viewer')
    return financial_integrity.patient_reconciliation(c,valid_month(period or current_month()))

@app.get('/api/periods/preflight')
def period_preflight(period:str,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    month=valid_month(period)
    try:
        month_open(c,month)
        check_period_close_ready(c,month,user)
    except HTTPException as error:
        return {'period':month,'ready':False,'reason':error.detail}
    return {'period':month,'ready':True,'reason':'كل موانع الإقفال المحددة في النظام تمت مراجعتها'}


@app.post("/api/periods/close")
def close_period(body:ClosePeriod,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner")
    period=valid_month(body.period)
    with c:
        c.execute("BEGIN IMMEDIATE")
        month_open(c,period)
        check_period_close_ready(c,period,user)
        c.execute("INSERT INTO periods(period,closed_by,closed_at) VALUES (?,?,?)",(period,user["id"],stamp()))
        audit(c,user["id"],"close_period","period",period)
    return {"closed":period}


@app.get("/api/users")
def users(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner")
    return [dict(r) for r in c.execute("SELECT id,username,role,active,created_at FROM users ORDER BY id")]


@app.post("/api/users")
def add_user(body:UserForm,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner")
    name=body.username.strip().lower()
    if not re.fullmatch(r"[a-z0-9_.-]{3,40}",name) or len(body.password)<12 or body.role not in ROLES:
        fail("اسم المستخدم يجب أن يكون إنجليزي 3-40 حرفًا وكلمة المرور 12 حرفًا على الأقل")
    try:
        with c:
            cur=c.execute("INSERT INTO users(username,password_hash,role,created_at) VALUES (?,?,?,?)",
                          (name,hash_password(body.password),body.role,stamp()))
            audit(c,user["id"],"create_user","user",cur.lastrowid,{"role":body.role})
    except sqlite3.IntegrityError:
        fail("اسم المستخدم مستخدم بالفعل")
    return {"id":cur.lastrowid}


@app.post("/api/users/{user_id}/status")
def user_status(user_id:int,body:AccountStatus,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner")
    if user_id==user["id"] and not body.active:
        fail("لا يمكنك تعطيل حسابك الذي تستخدمه",403)
    with c:
        c.execute("BEGIN IMMEDIATE")
        target=c.execute("SELECT id,active FROM users WHERE id=?",(user_id,)).fetchone()
        if not target: fail("المستخدم غير موجود",404)
        if bool(target["active"])==body.active:
            return {"id":user_id,"active":body.active}
        c.execute("UPDATE users SET active=? WHERE id=?",(int(body.active),user_id))
        if not body.active:
            c.execute("DELETE FROM sessions WHERE user_id=?",(user_id,))
        audit(c,user["id"],"activate_user" if body.active else "disable_user","user",user_id)
    return {"id":user_id,"active":body.active}


@app.post("/api/users/{user_id}/password")
def user_password(user_id:int,body:AccountPassword,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner")
    if not 12<=len(body.password)<=256:
        fail("كلمة المرور الجديدة يجب أن تكون بين 12 و256 حرفًا")
    with c:
        c.execute("BEGIN IMMEDIATE")
        target=c.execute("SELECT id,password_hash FROM users WHERE id=?",(user_id,)).fetchone()
        if not target: fail("المستخدم غير موجود",404)
        owner_password=c.execute("SELECT password_hash FROM users WHERE id=?",(user["id"],)).fetchone()
        if not owner_password or not verify_password(body.current_password,owner_password["password_hash"]):
            fail("تأكيد كلمة مرور المدير الحالية مطلوب لتغيير أي كلمة مرور",403)
        c.execute("UPDATE users SET password_hash=? WHERE id=?",(hash_password(body.password),user_id))
        c.execute("DELETE FROM sessions WHERE user_id=?",(user_id,))
        audit(c,user["id"],"reset_user_password","user",user_id)
    return {"ok":True,"session_revoked":user_id==user["id"]}


def safe_csv_cell(v):
    txt=str(v or "")
    if txt and txt.lstrip()[:1] in ("=","+","-","@"):
        return "'"+txt
    return txt


@app.get("/api/export/vouchers.csv")
def export_vouchers(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner","reviewer")
    output=io.StringIO();writer=csv.writer(output)
    writer.writerow(["رقم السند","التاريخ","النوع","القسم","التصنيف","الخزنة","المبلغ بالقروش","الحالة","الملاحظات"])
    for r in c.execute("""SELECT v.voucher_no,v.date,v.kind,d.name,ca.name,f.name,v.amount_piasters,v.status,v.description
           FROM vouchers v LEFT JOIN departments d ON d.id=v.department_id LEFT JOIN categories ca ON ca.id=v.category_id
           JOIN funds f ON f.id=v.from_fund_id ORDER BY v.id"""):
        writer.writerow([safe_csv_cell(v) for v in r])
    return Response(content="\ufeff"+output.getvalue(),media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition":"attachment; filename=ramses_vouchers.csv"})


@app.get("/api/sync-status")
def sync_status(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner")
    row=dict(c.execute("SELECT * FROM sync_status WHERE id=1").fetchone())
    row["configured"]=bool(os.getenv("GOOGLE_SHEET_ID") and Path(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")).is_file())
    return row


def sync_dirty(force=False):
    """Snapshot owner-only tabs; revision check prevents racing writes being marked synced."""
    if not (os.getenv("GOOGLE_SHEET_ID") and os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")):
        if force: fail("لم يتم إعداد Google Sheets على الخادم",409)
        return {"skipped":"not configured"}
    from google_sync import sync_to_google
    with SYNC_LOCK:
        c=connect()
        try:
            state=c.execute("SELECT revision,dirty FROM sync_status WHERE id=1").fetchone()
            if not force and not state["dirty"]:
                return {"skipped":"unchanged"}
            revision=state["revision"]
            try:
                counts=sync_to_google(c)
            except Exception as exc:
                c.execute("UPDATE sync_status SET last_error=? WHERE id=1",(type(exc).__name__,))
                LOG.exception("Google Sheets mirror failed")
                if force:fail("تعذر المزامنة. راجع إعدادات Google Sheets وسجلات الخادم",503)
                return {"error":type(exc).__name__}
            c.execute("""UPDATE sync_status SET synced_revision=?,dirty=(CASE WHEN revision=? THEN 0 ELSE 1 END),
                         last_synced_at=?,last_error=NULL WHERE id=1""",(revision,revision,stamp()))
            return counts
        finally:
            c.close()


@app.middleware("http")
async def mirror_after_success(request:Request,call_next):
    response=await call_next(request)
    response.headers["X-Content-Type-Options"]="nosniff"
    if os.getenv("RAMSES_SECURE_COOKIES","0")=="1":
        response.headers["Strict-Transport-Security"]="max-age=31536000; includeSubDomains"
    response.headers["X-Frame-Options"]="DENY"
    response.headers["Referrer-Policy"]="no-referrer"
    response.headers["Content-Security-Policy"]=(
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; "
        "base-uri 'self'; form-action 'self'"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"]="no-store"
    if (request.method=="POST" and request.url.path.startswith("/api/")
        and request.url.path not in ("/api/login","/api/logout","/api/sync-google")
        and 200<=response.status_code<300
        and os.getenv("GOOGLE_SHEET_ID") and os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")):
        # ponytail: in-process background queue; for high write volume use durable queue / Postgres.
        response.background=BackgroundTask(sync_dirty)
    return response


@app.post("/api/sync-google")
def sync_google(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,"owner")
    if not (os.getenv("GOOGLE_SHEET_ID") and os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")):
        fail("لم يتم إعداد Google Sheets على الخادم",409)
    audit(c,user["id"],"manual_google_sync","google_sheet","owner_mirror")
    counts=sync_dirty(force=True)
    return {"ok":True,"counts":counts}


if __name__ == "__main__":
    import uvicorn
    if not DB.exists():
        initialize(os.getenv("RAMSES_LEGACY_FILE") or None)
    uvicorn.run("app:app",host="127.0.0.1",port=int(os.getenv("PORT","8000")))

# V8.1A: intentionally isolated cashier billing domain, reusing auth/audit/SQLite.
from billing import router as billing_router
app.include_router(billing_router)
from cashier_api import router as cashier_router
app.include_router(cashier_router)

from financial_corrections import router as financial_corrections_router
app.include_router(financial_corrections_router)
from late_entry_api import router as late_entry_router
app.include_router(late_entry_router)

from pos_settlements import router as pos_settlements_router
app.include_router(pos_settlements_router)
from case_settlement import router as case_settlement_router
app.include_router(case_settlement_router)
