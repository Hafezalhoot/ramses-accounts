"""V8.1B end-to-end double-entry: invoice, split collection, advance, crosspoint, rollback and protection."""
import os, sqlite3, sys, tempfile
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def run():
    with tempfile.TemporaryDirectory() as d:
        os.environ['RAMSES_DB_PATH']=str(Path(d)/'billing_v81b.db')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='owner_development_password_2026'
        os.environ.pop('GOOGLE_SHEET_ID',None)
        os.environ.pop('GOOGLE_SERVICE_ACCOUNT_JSON',None)
        from bootstrap import initialize,connect
        initialize()
        from fastapi.testclient import TestClient
        from app import app
        owner,clerk,reviewer,other=(TestClient(app) for _ in range(4))
        def login(client,name,password):
            r=client.post('/api/login',json={'username':name,'password':password})
            assert r.status_code==200,r.text
            return {'X-CSRF-Token':r.json()['csrf']}
        oh=login(owner,'owner','owner_development_password_2026')
        for name,role in [('cashier','clerk'),('reviewer','reviewer'),('other','clerk')]:
            r=owner.post('/api/users',headers=oh,json={'username':name,'role':role,'password':'new_staff_test_password_2026'})
            assert r.status_code==200,r.text
        ch=login(clerk,'cashier','new_staff_test_password_2026')
        rh=login(reviewer,'reviewer','new_staff_test_password_2026')
        xh=login(other,'other','new_staff_test_password_2026')
        points=owner.get('/api/billing/config').json()['points']
        ext=next(x['id'] for x in points if x['kind']=='external')
        inner=next(x['id'] for x in points if x['kind']=='internal')
        staff=owner.get('/api/users').json();cashierid=next(u['id'] for u in staff if u['username']=='cashier')
        for point in (ext,inner):
            assert owner.post(f'/api/billing/points/{point}/assign',headers=oh,json={'user_id':cashierid}).status_code==200
        day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        look=owner.get('/api/lookups').json()
        department=next(x['id'] for x in look['departments'] if x['code']=='LAB')
        cash_fund=owner.post('/api/funds',headers=oh,json={'code':'cashout_v81b','name':'خزنة خارجية للتجربة','kind':'cash'})
        assert cash_fund.status_code==200,cash_fund.text
        cashid=cash_fund.json()['id']
        another=owner.post('/api/funds',headers=oh,json={'code':'cashin_v81b','name':'خزنة داخلية للتجربة','kind':'cash'})
        assert another.status_code==200,another.text
        inner_fund=another.json()['id']
        for point,fund in ((ext,cashid),(inner,inner_fund)):
            r=owner.post(f'/api/billing/points/{point}/cash-fund',headers=oh,json={'fund_id':fund})
            assert r.status_code==200,r.text
        assert owner.post(f'/api/billing/points/{inner}/cash-fund',headers=oh,json={'fund_id':cashid}).status_code==409
        clearing=owner.post('/api/funds',headers=oh,json={'code':'bclear_card_demo','name':'مقاصة بطاقات تجريبية','kind':'wallet'})
        assert clearing.status_code==200,clearing.text
        cardid=clearing.json()['id']
        assert owner.post('/api/billing/channels',headers=oh,json={'method':'card','fund_id':cardid}).status_code==200
        assert owner.post('/api/billing/channels',headers=oh,json={'method':'wallet','fund_id':cardid}).status_code==409
        # User must own a currently open shift for cash and non-cash cashier collections.
        shift=clerk.post('/api/shifts/open',headers=ch,json={'business_date':day,'shift':'morning','fund_id':cashid})
        assert shift.status_code==200,shift.text
        shiftid=shift.json()['id']
        assert other.post('/api/shifts/open',headers=xh,json={'business_date':day,'shift':'morning','fund_id':inner_fund}).status_code==403
        patient=clerk.post('/api/billing/patients',headers=ch,json={
            'display_name':'مريض تجريبي بلا بيانات حقيقية','request_id':'patient_v81b_test_key'}).json()
        case=clerk.post('/api/billing/cases',headers=ch,json={'patient_id':patient['id'],
          'kind':'outpatient','point_id':ext,'business_date':day,'request_id':'case_v81b_test_1234'})
        assert case.status_code==200,case.text
        caseid=case.json()['id']
        service=owner.post('/api/billing/services',headers=oh,json={'code':'LAB_V81B','name':'تحليل تجريبي غير حقيقي',
                            'department_id':department,'suggested_point':'either'}).json()['id']
        assert owner.post(f'/api/billing/services/{service}/prices',headers=oh,
                          json={'valid_from':day,'amount':'1500'}).status_code==200
        line=clerk.post(f'/api/billing/cases/{caseid}/services',headers=ch,json={
                         'service_id':service,'quantity':1,'request_id':'service_v81b_test_key'}).json()['id']
        from reviewer_scope_helpers import grant_reviewers_for_test
        grant_reviewers_for_test(owner, oh)
        assert reviewer.post(f'/api/billing/lines/{line}/fulfill',headers=rh).status_code==200
        draft=clerk.post(f'/api/billing/cases/{caseid}/drafts',headers=ch,json={
                         'request_id':'draft_v81b_test_key'})
        assert draft.status_code==200,draft.text
        draftid=draft.json()['id']
        assert clerk.post(f'/api/billing/cases/{caseid}/collect',headers=ch,json={
           'point_id':ext,'invoice_id':999,'parts':[{'method':'cash','amount':'500'}],
           'request_id':'wrong_invoice_test_key'}).status_code==409
        inv=clerk.post(f'/api/billing/drafts/{draftid}/issue',headers=ch,
            json={'request_id':'issue_invoice_v81b_key'})
        assert inv.status_code==200,inv.text
        invoice=inv.json()['id']
        assert inv.json()['due_piasters']==150000
        # G0: a posted patient invoice is earned revenue even BEFORE collection;
        # the managerial GL report must not incorrectly show zero.
        report=owner.get('/api/reports?month='+day[:7]);assert report.status_code==200,report.text
        assert report.json()['recognized_revenue_piasters']==150000,report.json()
        assert report.json()['recognized_cash_service_revenue_piasters']==0

        assert clerk.post(f'/api/billing/drafts/{draftid}/issue',headers=ch,
            json={'request_id':'issue_invoice_v81b_key'}).json()['replayed']
        assert owner.post(f'/api/billing/drafts/{draftid}/issue',headers=oh,
            json={'request_id':'issue_another_v81b_key'}).status_code==409
        # Strictly preserve invoice amount: split across cash and POS clearing.
        split={'point_id':ext,'invoice_id':invoice,
           'parts':[{'method':'cash','amount':'300.25'},{'method':'card','amount':'499.75'}],
           'request_id':'bill_split_v81b_test_key'}
        result=clerk.post(f'/api/billing/cases/{caseid}/collect',headers=ch,json=split)
        assert result.status_code==200,result.text
        assert result.json()['total_piasters']==80000 and result.json()['invoice_due_piasters']==70000
        assert clerk.post(f'/api/billing/cases/{caseid}/collect',headers=ch,json=split).json()['replayed']
        assert clerk.post(f'/api/billing/cases/{caseid}/collect',headers=ch,json={**split,
             'parts':[{'method':'cash','amount':'300'}],'request_id':'bill_split_v81b_test_key'}).status_code==409
        assert clerk.post(f'/api/billing/cases/{caseid}/collect',headers=ch,json={**split,
             'parts':[{'method':'cash','amount':'700.01'}],'request_id':'overpay_v81b_test_key'}).status_code==409
        # An advance is a liability; allocating it to a posted invoice does NOT move cash again.
        adv=clerk.post(f'/api/billing/cases/{caseid}/collect',headers=ch,json={
              'point_id':ext,'parts':[{'method':'cash','amount':'400'}],
              'request_id':'advance_v81b_test_key'})
        assert adv.status_code==200,adv.text
        alloc=clerk.post(f'/api/billing/cases/{caseid}/apply-advance',headers=ch,json={
                'invoice_id':invoice,'amount':'400','request_id':'alloc_advance_v81b_key'})
        assert alloc.status_code==200,alloc.text
        assert alloc.json()['invoice_due_piasters']==30000
        assert clerk.post(f'/api/billing/cases/{caseid}/apply-advance',headers=ch,json={
                'invoice_id':invoice,'amount':'1','request_id':'alloc_second_v81b_key'}).status_code==409
        assert clerk.post(f'/api/billing/cases/{caseid}/collect',headers=ch,json={
                'point_id':ext,'invoice_id':invoice,'parts':[{'method':'cash','amount':'300'}],
                'request_id':'bill_finish_v81b_key'}).status_code==200
        result=clerk.get(f'/api/billing/cases/{caseid}/finance')
        assert result.status_code==200,result.text
        assert result.json()['outstanding_piasters']==0
        assert result.json()['advance_available_piasters']==0
        assert result.json()['total_invoiced_piasters']==150000
        assert other.get(f'/api/billing/cases/{caseid}/finance').status_code==403
        assert reviewer.get(f'/api/billing/cases/{caseid}/finance').status_code==200
        assert other.post(f'/api/billing/cases/{caseid}/collect',headers=xh,json={**split,
                     'request_id':'unauth_cashier_test_key'}).status_code==403
        assert clerk.post('/api/vouchers',headers=ch,json={'date':day,'kind':'receipt','shift':'morning',
              'from_fund_id':cashid,'department_id':department,
              'category_id':next(x['id'] for x in owner.get('/api/lookups').json()['categories'] if x['code']=='billing_invoice_receipt'),
              'amount':'5','description':'محاولة تسجيل تحصيل عبر سند يدوي'}).status_code==403
        from ledger import trial_balance
        with connect() as c:
            tb=trial_balance(c,day[:7]);bycode={x['code']:x for x in tb['accounts']}
            assert tb['balanced'],tb
            assert bycode['4100']['closing_credit_piasters']==150000
            assert bycode['1200']['closing_debit_piasters']==0
            assert bycode['2300']['closing_credit_piasters']==0
            assert bycode[f'F{cashid:05d}']['closing_debit_piasters']==100025  # cash 300.25+400+300
            assert bycode[f'F{cardid:05d}']['closing_debit_piasters']==49975
            assert c.execute('SELECT count(*) FROM billing_collections').fetchone()[0]==3
            assert c.execute('SELECT count(*) FROM billing_invoices').fetchone()[0]==1
            assert c.execute('SELECT count(*) FROM billing_payment_parts').fetchone()[0]==4
            assert c.execute('SELECT count(*) FROM vouchers WHERE status=\'approved\'').fetchone()[0]==4
            assert c.execute('''SELECT count(*) FROM fund_movements WHERE shift_session_id=?''',(shiftid,)).fetchone()[0]==3
            try:c.execute('UPDATE billing_invoices SET total_piasters=1 WHERE id=?',(invoice,))
            except sqlite3.IntegrityError:pass
            else:raise AssertionError('Tampering with an issued invoice must fail')
            try:c.execute('UPDATE billing_invoice_draft_lines SET quantity=4 WHERE draft_id=?',(draftid,))
            except sqlite3.IntegrityError:pass
            else:raise AssertionError('Tampering with billed service lines must fail')
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        # A patient receiving inpatient care may pay at the outpatient cashier.
        # That cashier can read its own receipt, not the private inpatient case file.
        newcase=owner.post('/api/billing/cases',headers=oh,json={
            'patient_id':patient['id'],'kind':'inpatient','point_id':inner,
            'business_date':day,'request_id':'crosscase_new_2026_0001'})
        assert newcase.status_code==200,newcase.text
        inpatient=newcase.json()['id']
        ln=owner.post(f'/api/billing/cases/{inpatient}/services',headers=oh,json={
            'service_id':service,'quantity':1,'request_id':'crosscase_service_0001'})
        assert ln.status_code==200,ln.text
        assert reviewer.post(f"/api/billing/lines/{ln.json()['id']}/fulfill",headers=rh).status_code==200
        draft_internal=owner.post(f'/api/billing/cases/{inpatient}/drafts',headers=oh,
            json={'request_id':'crosscase_internal_draft_01'})
        assert draft_internal.status_code==200,draft_internal.text
        issued_internal=owner.post(f"/api/billing/drafts/{draft_internal.json()['id']}/issue",headers=oh,
            json={'request_id':'crosscase_invoice_issue_01'})
        assert issued_internal.status_code==200,issued_internal.text
        assert owner.post(f'/api/billing/points/{inner}/assign',headers=oh,
            json={'user_id':cashierid,'active':False}).status_code==200
        assert clerk.get(f'/api/billing/cases/{inpatient}').status_code==403
        lookup_cross=clerk.get('/api/billing/crosscase/resolve',params={
            'case_no':newcase.json()['case_no'],'patient_code':patient['code'],'point_id':ext})
        assert lookup_cross.status_code==200,lookup_cross.text
        assert lookup_cross.json()['unpaid_invoices'][0]['id']==issued_internal.json()['id']
        assert clerk.get('/api/billing/crosscase/resolve',params={
            'case_no':newcase.json()['case_no'],'patient_code':'PT-000000000000','point_id':ext}).status_code==404
        cross_coll=clerk.post(f'/api/billing/cases/{inpatient}/collect',headers=ch,json={
            'point_id':ext,'patient_code':patient['code'],'invoice_id':issued_internal.json()['id'],
            'parts':[{'method':'cash','amount':'60'}],'request_id':'crosscase_collection_0001'})
        assert cross_coll.status_code==200,cross_coll.text
        receipt=clerk.get(f"/api/billing/collections/{cross_coll.json()['id']}")
        assert receipt.status_code==200,receipt.text
        assert receipt.json()['total_piasters']==6000
        # No reviewer may guess a receipt ID to bypass cross-point patient scope.
        reviewerid=next(u['id'] for u in staff if u['username']=='reviewer')
        assert owner.post(f'/api/billing/points/{inner}/assign',headers=oh,
            json={'user_id':reviewerid,'active':False}).status_code==200
        assert reviewer.get(f'/api/billing/collections/{cross_coll.json()["id"]}').status_code==403
        assert owner.get(f'/api/billing/collections/{cross_coll.json()["id"]}').status_code==200
        assert all('fund_id' not in part for part in receipt.json()['parts'])
        assert clerk.get(f'/api/billing/cases/{inpatient}/finance').status_code==403
        assert other.get(f"/api/billing/collections/{cross_coll.json()['id']}").status_code==403
        # An issued invoice is never an independent receipt or an extra deposit.
        r=clerk.post(f'/api/shifts/{shiftid}/count',headers=ch,json={'counted_amount':'1060.25','note':'صندوق تجريبي'})
        assert r.status_code==200,r.text
        assert r.json()['variance_piasters']==0
        print('PASS V8.1B: invoice -> AR/revenue, split POS/cash, advance -> liability, allocation, double entry, shifts, security, idempotency')

if __name__=='__main__':run()
