"""V8.0 essential accounting invariants through HTTP + direct SQL tamper attempts."""
import os
import sqlite3
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ['RAMSES_DB_PATH']=str(Path(tmp)/'ledger.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='safe_owner_password_16plus'
        os.environ.pop('GOOGLE_SHEET_ID',None)
        os.environ.pop('GOOGLE_SERVICE_ACCOUNT_JSON',None)
        from bootstrap import initialize,connect
        initialize()
        # A direct SQL caller must not create a posted journal without pending review.
        with connect() as check:
            try:
                check.execute("INSERT INTO gl_journals(entry_date,memo,origin,status,created_by,created_at) VALUES ('2026-10-01','Direct SQL invalid','manual','posted',1,'2026-10-01')")
            except sqlite3.IntegrityError:
                pass
            else:
                raise AssertionError('Direct SQL inserted an unreviewed posted journal')
        from app import app
        from fastapi.testclient import TestClient
        owner,reviewer,clerk,viewer=(TestClient(app) for _ in range(4))
        def sign(client,name,pw):
            r=client.post('/api/login',json={'username':name,'password':pw})
            assert r.status_code==200,r.text
            return {'X-CSRF-Token':r.json()['csrf']}
        oh=sign(owner,'owner','safe_owner_password_16plus')
        for name,role in [('reviewer','reviewer'),('clerk','clerk'),('viewer','viewer')]:
            r=owner.post('/api/users',headers=oh,json={'username':name,'password':'second_user_password_16plus','role':role})
            assert r.status_code==200,r.text
        rh=sign(reviewer,'reviewer','second_user_password_16plus')
        ch=sign(clerk,'clerk','second_user_password_16plus')
        vh=sign(viewer,'viewer','second_user_password_16plus')
        dateval=date.today().isoformat()
        period=dateval[:7]
        look=owner.get('/api/lookups').json()
        fund=look['funds'][0]['id']
        other=look['funds'][2]['id']
        clerk_id=next(x['id'] for x in owner.get('/api/users').json() if x['username']=='clerk')
        assert owner.post('/api/fund-access',headers=oh,json={'user_id':clerk_id,'fund_id':other,'can_submit':True,
               'reason':'صلاحية محفظة تجريبية للترحيل المزدوج'}).status_code==200
        reviewer_id=next(x['id'] for x in owner.get('/api/users').json() if x['username']=='reviewer')
        assert owner.post('/api/fund-access',headers=oh,json={'user_id':reviewer_id,'fund_id':other,'can_approve':True,
               'reason':'تفويض مراجعة المحفظة بصورة منفصلة'}).status_code==200
        dept=look['departments'][0]['id']
        revenue=next(x['id'] for x in look['categories'] if x['code']=='medical_revenue')
        utilities=next(x['id'] for x in look['categories'] if x['code']=='utilities')
        def new_voucher(kind,amount,category=None,to=None,actor=clerk,headers=ch,**extra):
            args={'date':dateval,'kind':kind,'from_fund_id':fund,'to_fund_id':to,
                  'category_id':category,'department_id':dept,'shift':'central','amount':amount,
                  'description':'سند اختبار للترحيل المحاسبي المزدوج',**extra}
            r=actor.post('/api/vouchers',json=args,headers=headers)
            assert r.status_code==200,r.text
            return r.json()['id']
        assert owner.post(f'/api/funds/{fund}/opening',json={'amount':'2000'},headers=oh).status_code==200
        first=new_voucher('receipt','100',revenue)
        assert reviewer.post(f'/api/vouchers/{first}/decision',headers=rh,json={'decision':'approve'}).status_code==200
        tr=new_voucher('transfer','35',to=other)
        assert reviewer.post(f'/api/vouchers/{tr}/decision',headers=rh,json={'decision':'approve'}).status_code==200
        pay=new_voucher('payment','25',utilities,actor=reviewer,headers=rh)
        assert owner.post(f'/api/vouchers/{pay}/decision',headers=oh,json={'decision':'approve'}).status_code==200
        t=owner.get('/api/accounting/trial-balance?period='+period)
        assert t.status_code==200,t.text
        data=t.json();b=data['trial_balance']
        assert b['balanced'] and b['debit_piasters']==b['credit_piasters']
        account={x['code']:x for x in b['accounts']}
        assert account['4100']['closing_credit_piasters']==10000
        assert account['5140']['closing_debit_piasters']==2500
        assert account[f'F{fund:05d}']['debit_total']==10000
        assert account[f'F{fund:05d}']['credit_total']==6000
        assert account[f'F{other:05d}']['closing_debit_piasters']==3500
        assert data['coverage']['unverified_opening_funds']==1
        assert data['coverage']['not_final'] is True
        assert clerk.get('/api/accounting/trial-balance?period='+period).status_code==403
        assert viewer.get('/api/accounting/trial-balance?period='+period).status_code==200
        export=viewer.get('/api/accounting/trial-balance.csv?period='+period)
        assert export.status_code==200 and 'غير مكتمل' in export.text and '4100' in export.text
        assert clerk.get('/api/accounting/trial-balance.csv?period='+period).status_code==403
        assert TestClient(app).get('/api/accounting/trial-balance?period='+period).status_code==401
        # Owner reversal mirrors cancellation without destroying original journal.
        rev=owner.post(f'/api/vouchers/{first}/reverse',headers=oh,
            json={'date':dateval,'reason':'إلغاء سند تجريبي بعد اكتشاف تكرار الإيراد'})
        assert rev.status_code==200,rev.text
        b=owner.get('/api/accounting/trial-balance?period='+period).json()['trial_balance']
        assert next(x for x in b['accounts'] if x['code']=='4100')['closing_credit_piasters']==0
        assert b['balanced']
        # Manual accrual: no cashbook fund account can be touched manually.
        accounts={x['code']:x['id'] for x in b['accounts']}
        invoice={'date':dateval,'memo':'فاتورة شراء مستلزمات غير مسددة للمورد',
                 'lines':[{'account_id':accounts['1100'],'debit':'50','credit':'0'},
                          {'account_id':accounts['2200'],'debit':'0','credit':'50'}]}
        assert owner.post('/api/accounting/journals',headers=oh,json={**invoice,
               'lines':[invoice['lines'][0],{**invoice['lines'][1],'credit':'40'}]}).status_code==400
        assert owner.post('/api/accounting/journals',headers=oh,json={**invoice,
               'lines':[{'account_id':accounts[f'F{fund:05d}'],'debit':'50','credit':'0'},invoice['lines'][1]]}).status_code==409
        j=reviewer.post('/api/accounting/journals',headers=rh,json=invoice)
        assert j.status_code==200,j.text
        jid=j.json()['id']
        assert reviewer.post(f'/api/accounting/journals/{jid}/decision',headers=rh,json={'decision':'approve'}).status_code==403
        assert owner.post(f'/api/accounting/journals/{jid}/decision',headers=oh,json={'decision':'approve'}).status_code==200
        assert owner.post(f'/api/accounting/journals/{jid}/decision',headers=oh,json={'decision':'approve'}).status_code==409
        with connect() as c:
            assert c.execute('SELECT status FROM gl_journals WHERE id=?',(jid,)).fetchone()[0]=='posted'
            for sql,params in [
                ("UPDATE gl_lines SET debit_piasters=1 WHERE journal_id=?",(jid,)),
                ("DELETE FROM gl_journals WHERE id=?",(jid,)),
                ("UPDATE gl_journals SET memo='tampered' WHERE id=?",(jid,)),
            ]:
                try:c.execute(sql,params)
                except sqlite3.IntegrityError:pass
                else:raise AssertionError('Posted journal is editable: '+sql)
        request=reviewer.post(f'/api/accounting/journals/{jid}/reverse',headers=rh,
            json={'date':dateval,'reason':'قيد فاتورة تم إلغاؤها بعد المراجعة'})
        assert request.status_code==200,request.text
        reversal_id=request.json()['id']
        assert reviewer.post(f'/api/accounting/journals/{jid}/reverse',headers=rh,
            json={'date':dateval,'reason':'محاولة عكس مكرر على نفس القيد'}).status_code==409
        assert owner.post(f'/api/accounting/journals/{reversal_id}/decision',headers=oh,json={'decision':'approve'}).status_code==200
        after=owner.get('/api/accounting/trial-balance?period='+period).json()['trial_balance']
        assert after['balanced']
        assert next(x for x in after['accounts'] if x['code']=='2200')['closing_credit_piasters']==0
        # Approved payroll produces expense + liability (not cash movement).
        person=owner.post('/api/employees',headers=oh,json={'name':'موظف محاسبي تجريبي','code':'TEST_GL_EMP'})
        assert person.status_code==200,person.text
        emp=person.json()['id']
        assert owner.post(f'/api/employees/{emp}/salary-term',headers=oh,
                          json={'month':period,'monthly_salary':'1200'}).status_code==200
        a=owner.post('/api/payroll/accrual',headers=oh,json={'employee_id':emp,'period':period})
        assert a.status_code==200,a.text
        aid=a.json()['id']
        assert reviewer.post(f'/api/payroll/accrual/{aid}/decision',headers=rh,json={'decision':'approve'}).status_code==200
        assert owner.post(f'/api/payroll/accrual/{aid}/correct',headers=oh,json={
            'additions':'10','deductions':'0','reason':'لا تعدل القيود المرحلة'}).status_code==409
        wage=owner.get('/api/accounting/trial-balance?period='+period).json()['trial_balance']
        codes={x['code']:x for x in wage['accounts']}
        assert codes['5180']['closing_debit_piasters']==120000
        assert codes['2110']['closing_credit_piasters']==120000
        paid=new_voucher('payment','200',next(x['id'] for x in look['categories'] if x['code']=='salary_payment'),
               employee_id=emp,salary_period=period)
        assert reviewer.post(f'/api/vouchers/{paid}/decision',headers=rh,json={'decision':'approve'}).status_code==200
        final=owner.get('/api/accounting/trial-balance?period='+period).json()['trial_balance']
        assert next(x for x in final['accounts'] if x['code']=='2110')['closing_credit_piasters']==100000
        assert next(x for x in final['accounts'] if x['code']=='5180')['closing_debit_piasters']==120000
        assert final['balanced']
        print('PASS V8: balanced journal, cashbook mapping, double-entry reversal, invoice accrual, frozen postings, payroll liability and security')

if __name__=='__main__':
    run()
