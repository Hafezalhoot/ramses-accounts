"""G2C: one existing envelope receipt may clear multiple old patient invoices.

Financial invariant: no second cash movement or patient collection at allocation.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as root:
        os.environ['RAMSES_DB_PATH'] = str(Path(root) / 'cash-g2c.sqlite3')
        os.environ['RAMSES_ADMIN_USER'] = 'owner'
        os.environ['RAMSES_ADMIN_PASSWORD'] = 'owner_cash_g2c_secure_password'
        from bootstrap import initialize, connect
        initialize()
        from fastapi.testclient import TestClient
        from app import app
        import billing
        owner, reviewer = TestClient(app), TestClient(app)

        def call(client, method, path, headers=None, data=None):
            response = client.request(method, path, headers=headers, json=data)
            return response

        def ok(response):
            assert response.status_code == 200, response.text
            return response.json()

        def login(client, username, password):
            result = ok(call(client, 'POST', '/api/login', data={'username': username, 'password': password}))
            return {'X-CSRF-Token': result['csrf']}

        oh = login(owner, 'owner', 'owner_cash_g2c_secure_password')
        ok(call(owner, 'POST', '/api/users', oh, {'username':'g2c_reviewer',
                'password':'reviewer_g2c_secure_password', 'role':'reviewer'}))
        rh = login(reviewer, 'g2c_reviewer', 'reviewer_g2c_secure_password')
        pts = ok(call(owner, 'GET', '/api/billing/config'))['points']
        point = next(p for p in pts if p['kind'] == 'external')['id']
        main = next(p for p in pts if p['kind'] == 'internal')['id']
        funds = {f['code']:f['id'] for f in ok(call(owner, 'GET', '/api/funds'))}
        cash_main = funds['cash_main']
        ok(call(owner, 'POST', f'/api/billing/points/{main}/cash-fund', oh, {'fund_id':cash_main}))
        today = datetime.now(ZoneInfo('Africa/Cairo')).date()
        old_day = (today.replace(day=1) - timedelta(days=1)).isoformat()
        with connect() as c:
            c.execute('UPDATE cashier_schedule_versions SET starts_on=? WHERE point_id=?', (old_day,point))
            c.execute('UPDATE cashier_point_lifecycle SET starts_on=? WHERE point_id=?', (old_day,point))
            uid = c.execute("SELECT id FROM users WHERE username='owner'").fetchone()[0]
            c.execute('INSERT INTO periods(period,closed_by,closed_at) VALUES (?,?,?)',
                      (old_day[:7],uid,datetime.now(ZoneInfo('UTC')).isoformat()))
        incident = ok(call(owner,'POST','/api/late-entries',oh,{
            'request_key':'g2c_envelope_incident_001','point_id':point,
            'business_date':old_day,'shift_code':'night',
            'incident_reason':'outage','custodian_name':'موظف حفظ ظرف الاختبار',
            'cash_location':'main_safe','counted_cash':'1500',
            'source_register_ref':'G2C-ENV-001','note':'ظرف وهمي يضم إيصالين من وردية قديمة لم تسجل في يوم حدوثها'}))['id']
        docs=[]
        for n, amount in enumerate((900,600), 1):
            docs.append(ok(call(owner,'POST',f'/api/late-entries/{incident}/documents',oh,{
                'paper_ref':f'G2C-PAPER-{n:03d}','kind':'patient_receipt',
                'amount':str(amount),'method':'cash'}))['id'])
        ok(call(owner,'POST',f'/api/late-entries/{incident}/action',oh,
                {'action':'submit','note':'عرض محضر الظرف والمستندات على المراجع المستقل'}))
        from reviewer_scope_helpers import grant_reviewers_for_test
        grant_reviewers_for_test(owner, oh)
        ok(call(reviewer,'POST',f'/api/late-entries/{incident}/action',rh,
                {'action':'triage','note':'تمت مراجعة أصل محضر الظرف وقيمة الجرد ومستندات المرضى'}))
        patient_ids=[]
        for n in (1,2):
            patient_ids.append(ok(call(owner,'POST','/api/billing/patients',oh,{
                'display_name':f'مريض اختبار تسوية نقدية رقم {n}',
                'request_id':f'g2c_patient_0000000{n}'}))['code'])
        look=ok(call(owner,'GET','/api/lookups'))
        dept=next(x['id'] for x in look['departments'] if x['code']=='CLINIC')
        service=ok(call(owner,'POST','/api/billing/services',oh,{
            'code':'G2C_TEST_SERVICE','name':'خدمة قديمة تجريبية',
            'department_id':dept,'suggested_point':'either'}))['id']
        ok(call(owner,'POST',f'/api/billing/services/{service}/prices',oh,
            {'valid_from':old_day,'amount':'300'}))
        invoices=[]
        for n, (doc, patient_code, units) in enumerate(zip(docs,patient_ids,(3,2)),1):
            recovered=ok(call(owner,'POST',f'/api/late-entries/{incident}/documents/{doc}/recover-case',oh,{
                'request_id':f'g2c_recovered_case_{n:04d}',
                'patient_code':patient_code,'kind':'outpatient',
                'note':'تسجيل الخدمة القديمة بعد مطابقة المستند مع سجل الاستدراك'}))
            case = recovered['id']
            line=ok(call(owner,'POST',f'/api/billing/cases/{case}/services',oh,{
                'service_id':service,'quantity':units,'request_id':f'g2c_old_line_{n:05d}'}))
            ok(call(reviewer,'POST',f'/api/billing/lines/{line["id"]}/fulfill',rh))
            draft=ok(call(owner,'POST',f'/api/billing/cases/{case}/drafts',oh,
                {'request_id':f'g2c_old_draft_{n:05d}'}))
            invoice=ok(call(owner,'POST',f'/api/billing/drafts/{draft["id"]}/issue',oh,
                {'request_id':f'g2c_old_invoice_{n:05d}'}))
            invoices.append(invoice['id'])
            assert invoice['amount_piasters']==units*30000
        categories=look['categories']
        cat=next(x['id'] for x in categories if x['code']=='late_cash_unallocated')
        admin=next(x['id'] for x in look['departments'] if x['code']=='ADMIN')
        current=today.isoformat()
        # Restrict suspense to a documented, independently triaged envelope.
        main_shift=ok(call(owner,'POST','/api/shifts/open',oh,
            {'fund_id':cash_main,'business_date':current,'shift':'treasury'}))['id']
        source={'date':current,'kind':'receipt','department_id':admin,
            'category_id':cat,'from_fund_id':cash_main,'shift':'central','amount':'1500',
            'description':'استلام ظرف مُعدود ومطابق للبلاغ المعتمد رقابيًا',
            'reference_no':'G2C-ENV-001','client_request_id':'g2c_source_receipt_0001'}
        assert call(owner,'POST','/api/vouchers',oh,{**source,'amount':'1700',
               'client_request_id':'g2c_bad_amount_key_01'}).status_code==409
        assert call(owner,'POST','/api/vouchers',oh,{**source,'reference_no':'WRONG',
               'client_request_id':'g2c_bad_ref_key_001'}).status_code==409
        voucher=ok(call(owner,'POST','/api/vouchers',oh,source))['id']
        # Same envelope, different retry key: reject duplicate physical cash.
        assert call(owner,'POST','/api/vouchers',oh,{**source,
            'client_request_id':'g2c_duplicate_envelope_0002'}).status_code==409
        assert ok(call(owner,'POST','/api/vouchers',oh,source))['replayed']
        ok(call(reviewer,'POST',f'/api/vouchers/{voucher}/decision',rh,
                {'decision':'approve','reason':'اعتماد استلام المبلغ الفعلي بعد جرد الظرف'}))
        with connect() as c:
            funds_before=c.execute('SELECT COUNT(*),SUM(amount_piasters) FROM fund_movements').fetchone()
            gl_before=c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0]
            assert funds_before[1]==150000
            assert billing.invoice_due(c,invoices[0])==90000
        payload={'voucher_id':voucher,'invoice_id':invoices[0],
            'request_id':'g2c_cash_clearance_key_01',
            'note':'مطابقة إيصال المريض مع سند الظرف المعتمد ونقل ذمته فقط'}
        path=f'/api/late-entries/{incident}/documents/{docs[0]}/clear-booked-cash'
        assert call(owner,'POST',path,oh,payload).status_code==403
        assert call(reviewer,'POST',path,rh,{**payload,'voucher_id':voucher+999}).status_code==409
        cleared=ok(call(reviewer,'POST',path,rh,payload))
        assert cleared['cash_newly_booked_piasters']==0 and cleared['amount_piasters']==90000
        assert ok(call(reviewer,'POST',path,rh,payload))['replayed']
        assert call(reviewer,'POST',path,rh,{**payload,'request_id':'g2c_duplicate_reentry_01'}).status_code==409
        assert call(reviewer,'POST',f'/api/late-entries/{incident}/action',rh,
                    {'action':'resolve','note':'محاولة إقفال الظرف قبل تخصيص إيصال المريض الثاني'}).status_code==409
        payload2={'voucher_id':voucher,'invoice_id':invoices[1],
            'request_id':'g2c_cash_clearance_key_02',
            'note':'استكمال توزيع ظرف التحصيل المعتمد على فاتورة المريض الثاني'}
        ok(call(reviewer,'POST',f'/api/late-entries/{incident}/documents/{docs[1]}/clear-booked-cash',rh,payload2))
        assert call(owner,'POST',f'/api/vouchers/{voucher}/reverse',oh,{
            'date':current,'reason':'محاولة عكس سند استُخدم لتسوية فاتورتين'}).status_code==409
        with connect() as c:
            paid_case=c.execute('SELECT case_id FROM billing_invoices WHERE id=?',
                 (invoices[0],)).fetchone()[0]
        assert call(owner,'POST',f'/api/billing/cases/{paid_case}/credits',oh,{
            'invoice_id':invoices[0],'amount':'5',
            'reason':'طلب اختبار إشعار دائن على فاتورة سُددت من ظرف',
            'request_id':'g2c_credit_block_test_0001'}).status_code==409
        status=ok(call(reviewer,'POST',f'/api/late-entries/{incident}/action',rh,
                 {'action':'resolve','note':'تمت تسوية مستندَي الظرف دون تسجيل قبض نقدي إضافي'}))
        assert status['status']=='resolved'
        assert call(reviewer,'POST',f'/api/late-entries/{incident}/action',rh,
            {'action':'needs_evidence','note':'محاولة إرجاع بلاغ تمت تسويته نهائيًا'}).status_code==409
        summary=ok(call(owner,'GET',f'/api/billing/summary?period={today.strftime("%Y-%m")}'))
        assert summary['late_service_revenue_this_month_piasters']==150000
        assert summary['total_outstanding_receivables_piasters']==0
        assert summary['collections_this_month_piasters']==0
        assert summary['late_cash_cleared_this_month_piasters']==150000
        assert summary['late_cash_cleared_invoice_count_this_month']==2
        assert summary['suspense_cash_unallocated_piasters']==0
        with connect() as c:
            funds_after=c.execute('SELECT COUNT(*),SUM(amount_piasters) FROM fund_movements').fetchone()
            assert tuple(funds_after)==tuple(funds_before)
            assert c.execute('SELECT COUNT(*) FROM billing_collections').fetchone()[0]==0
            assert c.execute('SELECT COUNT(*) FROM late_cash_allocations').fetchone()[0]==2
            assert c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0]==gl_before+2
            a=lambda code:c.execute('''SELECT COALESCE(SUM(l.debit_piasters-l.credit_piasters),0)
                FROM gl_lines l JOIN gl_accounts a ON a.id=l.account_id
                JOIN gl_journals j ON j.id=l.journal_id
                WHERE a.code=? AND j.status='posted' ''',(code,)).fetchone()[0]
            assert a('2350')==0, a('2350')
            assert a('1200')==0, a('1200')
            assert a('4100')==-150000, a('4100')
            assert c.execute('SELECT COUNT(*) FROM periods WHERE period=?',(old_day[:7],)).fetchone()[0]==1
            assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            try:
                c.execute('UPDATE late_cash_allocations SET amount_piasters=1 WHERE id=?',(cleared['id'],))
            except Exception:
                pass
            else:
                raise AssertionError('Late cash allocation unexpectedly editable')
        assert ok(call(owner,'GET',f'/api/late-entries/{incident}'))['cash_reallocated_piasters']==150000
        assert main_shift>0
        print('PASS G2C: 2 old invoices, one approved 1500 EGP suspense voucher, zero new cash, immutable allocations')

if __name__=='__main__':
    run()
