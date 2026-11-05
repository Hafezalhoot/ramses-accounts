"""Several payment methods/receipts and advances never turn unpaid AR into cash."""
import os,sys,tempfile
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory(prefix='s14-payments-') as folder:
        os.environ.update(RAMSES_DB_PATH=str(Path(folder)/'test.sqlite3'),RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='s14_synthetic_owner_password')
        for key in ('GOOGLE_SHEET_ID','GOOGLE_SERVICE_ACCOUNT_JSON','RAMSES_SECURE_COOKIES'):os.environ.pop(key,None)
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner=TestClient(app);clerk=TestClient(app)
        def ok(r,status=200):
            assert r.status_code==status,(r.status_code,r.text[:600]);return r.json() if status==200 else None
        oh={'X-CSRF-Token':ok(owner.post('/api/login',json={'username':'owner','password':'s14_synthetic_owner_password'}))['csrf']}
        def post(path,body=None,client=owner,headers=oh,status=200):return ok(client.post(path,headers=headers,json=body),status)
        uid=post('/api/users',{'username':'cashier','password':'s14_synthetic_cashier_password','role':'clerk'})['id']
        ch={'X-CSRF-Token':ok(clerk.post('/api/login',json={'username':'cashier','password':'s14_synthetic_cashier_password'}))['csrf']}
        point=next(p['id'] for p in ok(owner.get('/api/billing/config'))['points'] if p['kind']=='external')
        fund=next(f['id'] for f in ok(owner.get('/api/funds')) if f['code']=='cash_sub')
        post(f'/api/billing/points/{point}/cash-fund',{'fund_id':fund});post(f'/api/billing/points/{point}/assign',{'user_id':uid})
        for method in ('card','wallet','instapay','transfer'):
            clearing=post('/api/funds',{'code':'bclear_'+method,'name':'مقاصة تجريبية '+method,'kind':'wallet'})['id']
            post('/api/billing/channels',{'method':method,'fund_id':clearing})
        day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        shift=post('/api/shifts/open',{'business_date':day,'shift':'night','fund_id':fund},clerk,ch)['id']
        patient=post('/api/billing/patients',{'display_name':'مريض دفعات متعددة وهمي','request_id':'s14_pay_patient_0001'},clerk,ch)
        case=post('/api/billing/cases',{'patient_id':patient['id'],'kind':'outpatient','point_id':point,'business_date':day,'request_id':'s14_pay_case_000001'},clerk,ch)['id']
        advance=post(f'/api/billing/cases/{case}/collect',{'point_id':point,'parts':[{'method':'cash','amount':'50'},{'method':'wallet','amount':'150'}],'request_id':'s14_pay_advance_001'},clerk,ch)
        dept=next(d['id'] for d in ok(owner.get('/api/lookups'))['departments'] if d['code']=='CLINIC')
        service=post('/api/billing/services',{'code':'MULTI_PAY','name':'خدمة ألف جنيه وهمية','department_id':dept,'suggested_point':'either'})['id']
        post(f'/api/billing/services/{service}/prices',{'valid_from':day,'amount':'1000'})
        line=post(f'/api/billing/cases/{case}/services',{'service_id':service,'quantity':1,'request_id':'s14_pay_line_000001'},clerk,ch)['id']
        post(f'/api/billing/lines/{line}/fulfill')
        draft=post(f'/api/billing/cases/{case}/drafts',{'request_id':'s14_pay_draft_00001'},clerk,ch)['id']
        inv=post(f'/api/billing/drafts/{draft}/issue',{'request_id':'s14_pay_invoice_001'},clerk,ch)['id']
        with connect() as c:before=c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]
        post(f'/api/billing/cases/{case}/apply-advance',{'invoice_id':inv,'amount':'200','request_id':'s14_pay_apply_00001'},clerk,ch)
        with connect() as c:assert c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]==before
        split={'point_id':point,'invoice_id':inv,'parts':[{'method':method,'amount':'100'} for method in ('cash','card','wallet','instapay','transfer')],'request_id':'s14_pay_split_00001'}
        first=post(f'/api/billing/cases/{case}/collect',split,clerk,ch)
        repeat=post(f'/api/billing/cases/{case}/collect',split,clerk,ch);assert repeat['id']==first['id'] and repeat['replayed']
        last=post(f'/api/billing/cases/{case}/collect',{'point_id':point,'invoice_id':inv,'parts':[{'method':'cash','amount':'100'}],'request_id':'s14_pay_last_000001'},clerk,ch)
        for method in ('insurance','credit'):
            post(f'/api/billing/cases/{case}/collect',{'point_id':point,'invoice_id':inv,'parts':[{'method':method,'amount':'200'}],'request_id':'s14_pay_fake_'+method+'0001'},clerk,ch,status=422)
        finance=ok(clerk.get(f'/api/billing/cases/{case}/finance'))
        assert finance['outstanding_piasters']==20000 and finance['advance_available_piasters']==0
        assert len(finance['collections'])==3 and len({x['collection_no'] for x in finance['collections']})==3
        receipt=ok(clerk.get(f'/api/billing/collections/{first["id"]}'));assert len(receipt['parts'])==5 and receipt['total_piasters']==50000
        daily=ok(owner.get(f'/api/shifts/{shift}/daily-report'));assert daily['expected_piasters']==25000
        ways={x['method']:x['total_piasters'] for x in daily['payment_methods']}
        assert ways=={'cash':25000,'card':10000,'wallet':25000,'instapay':10000,'transfer':10000}
        for document in (advance,first,last):
            html=clerk.get(f'/api/billing/collections/{document["id"]}/print');assert html.status_code==200 and document['collection_no'] in html.text
        with connect() as c:
            assert c.execute('SELECT SUM(debit_piasters-credit_piasters) FROM gl_lines').fetchone()[0]==0
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
        print('PASS S14 payment cycle: advance200, allocation without new cash, five-method receipt500, separate receipt100, unpaidAR200, physical till250, replay-safe and no fake insurance/credit cash')


if __name__=='__main__':run()
