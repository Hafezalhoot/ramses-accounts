"""Real API cashier cycle: safe print documents, current authorization, blind counts."""
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory(prefix='ramses-s13-') as folder:
        os.environ.update(RAMSES_DB_PATH=str(Path(folder)/'test.sqlite3'),
                          RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='synthetic_s13_owner_password')
        for k in ('GOOGLE_SHEET_ID','GOOGLE_SERVICE_ACCOUNT_JSON','RAMSES_SECURE_COOKIES'):
            os.environ.pop(k,None)
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner=TestClient(app)
        oh={'X-CSRF-Token':owner.post('/api/login',json={'username':'owner','password':'synthetic_s13_owner_password'}).json()['csrf']}
        def ok(r):
            assert r.status_code==200,(r.status_code,r.text[:700])
            return r.json()
        def post(client,headers,path,body=None):
            return ok(client.post(path,headers=headers,json=body))
        clients={}; headers={}; ids={}
        for name,role in (('cashier','clerk'),('other','clerk'),('treasury','clerk'),('reviewer','reviewer')):
            ids[name]=post(owner,oh,'/api/users',{'username':name,'password':'synthetic_s13_staff_password','role':role})['id']
            clients[name]=TestClient(app)
            headers[name]={'X-CSRF-Token':ok(clients[name].post('/api/login',json={'username':name,'password':'synthetic_s13_staff_password'}))['csrf']}
        cashier=clients['cashier']; ch=headers['cashier']
        points=ok(owner.get('/api/billing/config'))['points']
        ext=next(x['id'] for x in points if x['kind']=='external')
        internal=next(x['id'] for x in points if x['kind']=='internal')
        funds={x['code']:x['id'] for x in ok(owner.get('/api/funds'))}
        for point,fund,names in ((ext,funds['cash_sub'],('cashier','reviewer','treasury')),
                                 (internal,funds['cash_main'],('treasury',))):
            post(owner,oh,f'/api/billing/points/{point}/cash-fund',{'fund_id':fund})
            for name in names:post(owner,oh,f'/api/billing/points/{point}/assign',{'user_id':ids[name]})
        day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        shift=post(cashier,ch,'/api/shifts/open',{'business_date':day,'shift':'night','fund_id':funds['cash_sub']})['id']
        post(clients['treasury'],headers['treasury'],'/api/shifts/open',{'business_date':day,'shift':'treasury','fund_id':funds['cash_main']})
        patient=post(cashier,ch,'/api/billing/patients',{'display_name':'مريض وهمي <script>alert(1)</script>','request_id':'s13_patient_00000001'})
        case=post(cashier,ch,'/api/billing/cases',{'patient_id':patient['id'],'point_id':ext,'kind':'outpatient','business_date':day,'request_id':'s13_case_0000000001'})['id']
        dept=next(x['id'] for x in ok(owner.get('/api/lookups'))['departments'] if x['code']=='CLINIC')
        service=post(owner,oh,'/api/billing/services',{'code':'S13_TEST','name':'كشف تجريبي <img src=x onerror=alert(1)>','department_id':dept,'suggested_point':'external'})['id']
        post(owner,oh,f'/api/billing/services/{service}/prices',{'valid_from':day,'amount':'150.25'})
        line=post(cashier,ch,f'/api/billing/cases/{case}/services',{'service_id':service,'quantity':2,'request_id':'s13_service_00000001'})['id']
        post(owner,oh,f'/api/billing/lines/{line}/fulfill')
        draft=post(cashier,ch,f'/api/billing/cases/{case}/drafts',{'request_id':'s13_draft_000000001'})['id']
        invoice=post(cashier,ch,f'/api/billing/drafts/{draft}/issue',{'request_id':'s13_invoice_0000001'})
        receipt=post(cashier,ch,f'/api/billing/cases/{case}/collect',{'point_id':ext,'invoice_id':invoice['id'],'parts':[{'method':'cash','amount':'300.50'}],'request_id':'s13_collect_0000001'})
        paths=[f'/api/billing/invoices/{invoice["id"]}/print',f'/api/billing/collections/{receipt["id"]}/print',f'/api/shifts/{shift}/daily-report/print']
        def snapshot():
            with connect() as c:
                return {t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in
                        ('audit_log','gl_journals','fund_movements','vouchers','billing_collections','billing_invoices')}
        before=snapshot()
        for path in paths:
            r=cashier.get(path)
            assert r.status_code==200,(path,r.status_code,r.text[:400])
            assert r.headers['content-type'].startswith('text/html')
            assert r.headers['cache-control']=='no-store'
            assert 'dir="rtl"' in r.text and 'نسخة اختبار' in r.text
            assert '<script>alert(1)</script>' not in r.text and '<img src=x' not in r.text
            assert TestClient(app).get(path).status_code==401
            assert clients['other'].get(path).status_code==403
            assert cashier.get(path+'?paper=80mm').status_code==200
        html=cashier.get(paths[0]).text
        assert '300.50' in html and '&lt;img src=x onerror=alert(1)&gt;' in html
        assert invoice['invoice_no'] in html and 'المتبقي الحالي' in html
        html=cashier.get(paths[1]).text
        assert receipt['collection_no'] in html and '300.50' in html and 'نقدي' in html
        assert invoice['invoice_no'] in html and 'cashier' in html,'Patient receipt must identify its invoice and cashier'
        html=cashier.get(paths[2]).text
        assert 'محجوب حتى إرسال الجرد' in html and 'data-field="expected">300.50' not in html
        assert snapshot()==before,'Printing changed accounting or audit records'
        post(cashier,ch,f'/api/shifts/{shift}/count',{'counted_amount':'300.50','note':'جرد تجريبي مستقل عن التقرير'})
        assert 'بانتظار الاستلام والاعتماد' in cashier.get(paths[2]).text
        assert cashier.post(f'/api/shifts/{shift}/handoff',headers=ch,json={'counted_amount':'300.50'}).status_code==403
        post(clients['treasury'],headers['treasury'],f'/api/shifts/{shift}/handoff',{'counted_amount':'300.50','decision':'accept','note':'استلام فعلي تجريبي مستقل'})
        assert 'تم الاستلام' in cashier.get(paths[2]).text,'Accepted independent handover must print as received'
        post(clients['treasury'],headers['treasury'],'/api/cashier/treasury-deposits',{'source_shift_id':shift,'amount':'300.50','note':'توريد تجريبي للخزينة الرئيسية'})
        post(clients['reviewer'],headers['reviewer'],f'/api/shifts/{shift}/review',{'decision':'approve'})
        assert 'مقفلة ومعتمدة' in cashier.get(paths[2]).text
        assert 'data-field="expected">300.50' in cashier.get(paths[2]).text
        # The same current object grants govern print and its JSON reader.
        for path in paths[:2]:assert clients['reviewer'].get(path).status_code==200
        post(owner,oh,f'/api/billing/points/{ext}/assign',{'user_id':ids['reviewer'],'active':False})
        for path in paths[:2]:assert clients['reviewer'].get(path).status_code==403
        post(owner,oh,f'/api/billing/points/{ext}/assign',{'user_id':ids['reviewer'],'active':True})
        post(owner,oh,f'/api/funds/{funds["cash_sub"]}/access-policy',{'restricted':True,'reason':'اختبار نطاق طباعة وردية مقيدة'})
        assert clients['reviewer'].get(paths[2]).status_code==403
        for allowed in (True,False):
            post(owner,oh,'/api/fund-access',{'user_id':ids['reviewer'],'fund_id':funds['cash_sub'],
                 'can_approve':allowed,'can_submit':False,'reason':'اختبار منح وسحب تفويض التقرير'})
            assert clients['reviewer'].get(paths[2]).status_code==(200 if allowed else 403)
        # A rejected handover must never print as accepted or absent.
        for name in ('cashier','treasury'):
            post(owner,oh,'/api/fund-access',{'user_id':ids[name],'fund_id':funds['cash_sub'],
                 'can_submit':True,'reason':'تفويض جرد تجريبي للخزنة المقيدة'})
        second=post(cashier,ch,'/api/shifts/open',{'business_date':day,'shift':'morning','fund_id':funds['cash_sub']})['id']
        post(cashier,ch,f'/api/shifts/{second}/count',{'counted_amount':'0','note':'وردية تجريبية دون حركة'})
        post(clients['treasury'],headers['treasury'],f'/api/shifts/{second}/handoff',{
             'counted_amount':'0','decision':'reject','note':'رفض استلام تجريبي لإعادة الجرد'})
        assert 'أُعيد الجرد' in cashier.get(f'/api/shifts/{second}/daily-report/print').text
        # Current authorization, not the document creator's former assignment.
        post(owner,oh,f'/api/billing/points/{ext}/assign',{'user_id':ids['cashier'],'active':False})
        for path in paths[:2]:assert cashier.get(path).status_code==403
        for prefix in ('/api/billing/invoices/','/api/billing/collections/'):
            assert owner.get(prefix+'999999/print').status_code==404
        with connect() as c:
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
            assert c.execute('SELECT COALESCE(SUM(debit_piasters-credit_piasters),0) FROM gl_lines').fetchone()[0]==0
        print('PASS S13 cashier print: issued invoice, receipt, blind count, independent close, escaped Arabic, current access, read-only GET')


if __name__=='__main__':run()
