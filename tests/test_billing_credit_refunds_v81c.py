"""Credit notes, independent reviewer, constrained refund source/method and double-entry."""
import os,sqlite3,sys,tempfile
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def run():
    with tempfile.TemporaryDirectory() as d:
        os.environ['RAMSES_DB_PATH']=str(Path(d)/'credits.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='owner_development_password_2026'
        os.environ.pop('GOOGLE_SHEET_ID',None)
        os.environ.pop('GOOGLE_SERVICE_ACCOUNT_JSON',None)
        from bootstrap import initialize,connect
        initialize()
        from fastapi.testclient import TestClient
        from app import app
        from ledger import trial_balance
        owner, clerk, reviewer, stranger=(TestClient(app) for _ in range(4))
        def login(cl,name,pw):
            r=cl.post('/api/login',json={'username':name,'password':pw})
            assert r.status_code==200,r.text
            return {'X-CSRF-Token':r.json()['csrf']}
        oh=login(owner,'owner','owner_development_password_2026')
        for name,role in [('cashier','clerk'),('reviewer','reviewer'),('outsider','clerk')]:
            assert owner.post('/api/users',headers=oh,json={'username':name,'role':role,'password':'new_staff_test_password_2026'}).status_code==200
        ch=login(clerk,'cashier','new_staff_test_password_2026')
        rh=login(reviewer,'reviewer','new_staff_test_password_2026')
        xh=login(stranger,'outsider','new_staff_test_password_2026')
        cfg=owner.get('/api/billing/config').json()
        ext=next(x['id'] for x in cfg['points'] if x['kind']=='external')
        cid=next(x['id'] for x in owner.get('/api/users').json() if x['username']=='cashier')
        assert owner.post(f'/api/billing/points/{ext}/assign',headers=oh,json={'user_id':cid}).status_code==200
        cash=owner.post('/api/funds',headers=oh,json={'code':'refund_cash','name':'Refund test cash','kind':'cash'}).json()['id']
        assert owner.post(f'/api/billing/points/{ext}/cash-fund',headers=oh,json={'fund_id':cash}).status_code==200
        day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        shift=clerk.post('/api/shifts/open',headers=ch,json={'business_date':day,'shift':'night','fund_id':cash})
        assert shift.status_code==200,shift.text
        dept=next(x['id'] for x in owner.get('/api/lookups').json()['departments'] if x['code']=='LAB')
        patient=clerk.post('/api/billing/patients',headers=ch,json={'display_name':'Simulation Only Patient',
                'request_id':'patient_credit_test_key'}).json()
        newcase=clerk.post('/api/billing/cases',headers=ch,json={'patient_id':patient['id'],'kind':'outpatient',
                        'point_id':ext,'business_date':day,'request_id':'case_credit_test_key_01'})
        assert newcase.status_code==200,newcase.text
        case=newcase.json()['id']
        service=owner.post('/api/billing/services',headers=oh,json={'code':'TESTCRED01',
                 'name':'Sample service provided','department_id':dept}).json()['id']
        assert owner.post(f'/api/billing/services/{service}/prices',headers=oh,
                 json={'valid_from':day,'amount':'1500'}).status_code==200
        ln=clerk.post(f'/api/billing/cases/{case}/services',headers=ch,
           json={'service_id':service,'quantity':1,'request_id':'line_credit_test_key_01'}).json()['id']
        from reviewer_scope_helpers import grant_reviewers_for_test
        grant_reviewers_for_test(owner, oh)
        assert reviewer.post(f'/api/billing/lines/{ln}/fulfill',headers=rh).status_code==200
        draft=clerk.post(f'/api/billing/cases/{case}/drafts',headers=ch,
             json={'request_id':'draft_credit_test_key'}).json()['id']
        invoice=clerk.post(f'/api/billing/drafts/{draft}/issue',headers=ch,
           json={'request_id':'issue_credit_test_key'}).json()['id']
        received=clerk.post(f'/api/billing/cases/{case}/collect',headers=ch,json={
          'point_id':ext,'invoice_id':invoice,'parts':[{'method':'cash','amount':'800'}],
          'request_id':'cash_credit_test_key'})
        assert received.status_code==200,received.text
        assert clerk.post(f'/api/billing/cases/{case}/credits',headers=ch,json={
           'invoice_id':invoice,'amount':'1600','reason':'Invalid amount requested',
           'request_id':'overcredit_credit_key'}).status_code==409
        credit=clerk.post(f'/api/billing/cases/{case}/credits',headers=ch,json={
           'invoice_id':invoice,'amount':'900','reason':'Clinical service correction approved for trial',
           'request_id':'credit_request_first'} )
        assert credit.status_code==200,credit.text
        creditid=credit.json()['id']
        assert clerk.post(f'/api/billing/credits/{creditid}/decision',headers=ch,json={'decision':'approve'}).status_code==403
        reviewed=reviewer.post(f'/api/billing/credits/{creditid}/decision',headers=rh,json={'decision':'approve'})
        assert reviewed.status_code==200,reviewed.text
        assert reviewed.json()['refundable_credit_piasters']==20000
        assert reviewer.post(f'/api/billing/credits/{creditid}/decision',headers=rh,json={'decision':'approve'}).status_code==409
        finance=clerk.get(f'/api/billing/cases/{case}/finance').json()
        assert finance['outstanding_piasters']==0 and finance['credit_refundable_piasters']==20000,finance
        # The credit is an accounting liability, not automatically a cash payment.
        with connect() as c:
            bycode={r['code']:r for r in trial_balance(c,day[:7])['accounts']}
            assert bycode['4195']['closing_debit_piasters']==90000
            assert bycode['2310']['closing_credit_piasters']==20000
            assert bycode['1200']['closing_debit_piasters']==0
            from financial_integrity import patient_reconciliation
            assert patient_reconciliation(c,day[:7])['matched']
            assert bycode[f'F{cash:05d}']['closing_debit_piasters']==80000
        over=clerk.post(f'/api/billing/cases/{case}/refunds',headers=ch,json={
         'point_id':ext,'source':'credit','method':'cash','amount':'201',
         'reason':'Excess credit refund invalid', 'request_id':'excess_refund_credit_key'})
        assert over.status_code==409,over.text
        assert stranger.get(f'/api/billing/cases/{case}/adjustments').status_code==403
        req=clerk.post(f'/api/billing/cases/{case}/refunds',headers=ch,json={
          'point_id':ext,'source':'credit','method':'cash','amount':'200',
          'reason':'Approved partial reimbursement to patient',
          'request_id':'ref_request_first_key'})
        assert req.status_code==200,req.text
        rid=req.json()['id']
        assert clerk.post(f'/api/billing/refunds/{rid}/pay',headers=ch,json={
           'request_id':'pay_refund_before_approval'}).status_code==409
        assert reviewer.post(f'/api/billing/refunds/{rid}/pay',headers=rh,json={
           'request_id':'refund_wrong_actor'}).status_code==403
        assert reviewer.post(f'/api/billing/refunds/{rid}/decision',headers=rh,json={
           'decision':'approve'}).status_code==200
        assert clerk.post(f'/api/billing/cases/{case}/refunds',headers=ch,json={
          'point_id':ext,'source':'credit','method':'cash','amount':'1',
          'reason':'Second refund exceeds reserve',
          'request_id':'credit_double_refund_key'}).status_code==409
        paid=clerk.post(f'/api/billing/refunds/{rid}/pay',headers=ch,json={
           'request_id':'pay_credit_refund_key'})
        assert paid.status_code==200,paid.text
        assert clerk.post(f'/api/billing/refunds/{rid}/pay',headers=ch,json={
           'request_id':'pay_credit_refund_key'}).json()['replayed']
        assert clerk.post(f'/api/billing/refunds/{rid}/pay',headers=ch,json={
           'request_id':'new_key_prevent_double'}).status_code==409
        assert owner.post(f'/api/vouchers/{paid.json()["voucher_id"]}/reverse',headers=oh,
              json={'date':day,'reason':'Do not permit uncoupled refund reversal'}).status_code==409
        with connect() as c:
            tb=trial_balance(c,day[:7]); assert tb['balanced']
            bycode={r['code']:r for r in tb['accounts']}
            assert bycode['2310']['closing_credit_piasters']==0
            assert bycode[f'F{cash:05d}']['closing_debit_piasters']==60000
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            try:c.execute('DELETE FROM billing_refund_requests WHERE id=?',(rid,))
            except sqlite3.IntegrityError:pass
            else:raise AssertionError('Patient refund trail must be immutable')
        # Cash advance: refund unallocated balance after separate approval.
        adv=clerk.post(f'/api/billing/cases/{case}/collect',headers=ch,json={
             'point_id':ext,'parts':[{'method':'cash','amount':'400'}],
             'request_id':'second_cash_advance_key'})
        assert adv.status_code==200,adv.text
        r=clerk.post(f'/api/billing/cases/{case}/refunds',headers=ch,json={
           'point_id':ext,'source':'advance','method':'cash','amount':'100',
           'reason':'Return unused advance to patient',
           'request_id':'adv_refund_request_key'})
        assert r.status_code==200,r.text
        advrid=r.json()['id']
        assert reviewer.post(f'/api/billing/refunds/{advrid}/decision',headers=rh,
           json={'decision':'approve'}).status_code==200
        assert clerk.post(f'/api/billing/refunds/{advrid}/pay',headers=ch,
           json={'request_id':'adv_refund_payment_key'}).status_code==200
        finance=clerk.get(f'/api/billing/cases/{case}/finance').json()
        assert finance['advance_available_piasters']==30000,finance
        with connect() as c:
            tb=trial_balance(c,day[:7]); assert tb['balanced']
            bycode={r['code']:r for r in tb['accounts']}
            assert bycode['2300']['closing_credit_piasters']==30000
            assert bycode['2310']['closing_credit_piasters']==0
            from financial_integrity import patient_reconciliation
            assert patient_reconciliation(c,day[:7])['matched']
        monthly=owner.get('/api/billing/summary',params={'period':day[:7]})
        assert monthly.status_code==200,monthly.text
        assert monthly.json()['total_outstanding_receivables_piasters']==0
        assert monthly.json()['approved_credits_this_month_piasters']==90000
        assert monthly.json()['paid_refunds_this_month_piasters']==30000
        assert monthly.json()['total_unapplied_advances_piasters']==30000
        print('PASS V8.1C credit notes, AR, contra revenue, approved patient refund, protected reversal, unused advance, trial balance')

if __name__=='__main__':run()
