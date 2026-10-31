"""Mixed cash envelope: patient AR + paper-paid expenses + an optional shortage.

No new patient cash collection, no extra fund movement, and no historical
period rewrite. This is an integration test via real API handlers and SQLite.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ['RAMSES_DB_PATH']=str(Path(tmp)/'g2d.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='g2d_owner_secure_password'
        from bootstrap import initialize,connect
        initialize()
        from fastapi.testclient import TestClient
        from app import app
        import billing,ledger
        owner=TestClient(app);reviewer=TestClient(app)
        def call(client,method,path,head=None,data=None):
            return client.request(method,path,headers=head,json=data)
        def ok(r):
            assert r.status_code==200,(r.status_code,r.text)
            return r.json()
        def auth(c,user,pwd):
            return {'X-CSRF-Token':ok(call(c,'POST','/api/login',data={'username':user,'password':pwd}))['csrf']}
        oh=auth(owner,'owner','g2d_owner_secure_password')
        ok(call(owner,'POST','/api/users',oh,{'username':'g2d_reviewer',
            'password':'g2d_reviewer_secure_password','role':'reviewer'}))
        rh=auth(reviewer,'g2d_reviewer','g2d_reviewer_secure_password')
        look=ok(call(owner,'GET','/api/lookups'))
        admin=next(x['id'] for x in look['departments'] if x['code']=='ADMIN')
        dept=next(x['id'] for x in look['departments'] if x['code']=='CLINIC')
        cat=next(x['id'] for x in look['categories'] if x['code']=='late_cash_unallocated')
        main=next(x['id'] for x in look['funds'] if x['code']=='cash_main')
        point=next(x for x in ok(call(owner,'GET','/api/billing/config'))['points'] if x['kind']=='internal')['id']
        ok(call(owner,'POST',f'/api/billing/points/{point}/cash-fund',oh,{'fund_id':main}))
        today=datetime.now(ZoneInfo('Africa/Cairo')).date()
        old_day=(today.replace(day=1)-timedelta(days=1)).isoformat()
        with connect() as db:
            db.execute('UPDATE cashier_schedule_versions SET starts_on=? WHERE point_id=?',(old_day,point))
            db.execute('UPDATE cashier_point_lifecycle SET starts_on=? WHERE point_id=?',(old_day,point))
            uid=db.execute("SELECT id FROM users WHERE username='owner'").fetchone()[0]
            db.execute('INSERT INTO periods(period,closed_by,closed_at) VALUES (?,?,?)',
                       (old_day[:7],uid,datetime.now(ZoneInfo('UTC')).isoformat()))
        service=ok(call(owner,'POST','/api/billing/services',oh,{
            'code':'G2D_SERVICE','name':'Historical internal inpatient test service',
            'department_id':dept,'suggested_point':'either'}))['id']
        ok(call(owner,'POST',f'/api/billing/services/{service}/prices',oh,{'valid_from':old_day,'amount':'500'}))
        ok(call(owner,'POST','/api/shifts/open',oh,{'fund_id':main,'business_date':today.isoformat(),'shift':'treasury'}))

        def build(n,net,expense):
            prefix=f'G2D-{n}'
            incident=ok(call(owner,'POST','/api/late-entries',oh,{
                'request_key':f'g2d_incident_request_{n:04d}',
                'point_id':point,'business_date':old_day,'shift_code':'treasury',
                'incident_reason':'absence','custodian_name':'مراجع عهدة المستشفى',
                'cash_location':'main_safe','counted_cash':str(net),
                'source_register_ref':prefix+'-ENV',
                'note':'ظرف قديم فيه تحصيل مريض ومصروف نقدي مثبت في ورق الوردية'}))['id']
            patient_doc=ok(call(owner,'POST',f'/api/late-entries/{incident}/documents',oh,{
                'paper_ref':prefix+'-PAT','kind':'patient_receipt','amount':'1500','method':'cash'}))['id']
            expense_doc=ok(call(owner,'POST',f'/api/late-entries/{incident}/documents',oh,{
                'paper_ref':prefix+'-EXP','kind':'expense','amount':str(expense),
                'method':'cash','note':'شراء مستلزمات إدارية من نقدية المرضى في الوردية القديمة'}))['id']
            # Known PNG signature with no patient details; mock evidence only.
            response=owner.post(f'/api/late-entries/{incident}/evidence',headers=oh,
                                files={'file':('count-sheet.png',b'\x89PNG\r\n\x1a\nFAKE-QA-IMAGE-'+prefix.encode(),'image/png')})
            ok(response)
            ok(call(owner,'POST',f'/api/late-entries/{incident}/action',oh,
                    {'action':'submit','note':'تم تقديم مستندات وردية قديمة للمراجعة المستقلة'}))
            from reviewer_scope_helpers import grant_reviewers_for_test
            grant_reviewers_for_test(owner, oh)
            ok(call(reviewer,'POST',f'/api/late-entries/{incident}/action',rh,
                    {'action':'triage','note':'اطلعت على الإثباتات وصور الظرف وقيمة الجرد الفعلية'}))
            patient_code=ok(call(owner,'POST','/api/billing/patients',oh,{
                'display_name':f'مريض تجربة ظرف مختلط {n}',
                'request_id':f'g2d_patient_record_{n:05d}'}))['code']
            recovered=ok(call(owner,'POST',f'/api/late-entries/{incident}/documents/{patient_doc}/recover-case',oh,{
                'request_id':f'g2d_recover_patient_{n:06d}',
                'patient_code':patient_code,'kind':'inpatient',
                'note':'المريض حصل على خدمة فعلية في شهر سابق موثقة بكشف الوردية'}))
            case=recovered['id']
            line=ok(call(owner,'POST',f'/api/billing/cases/{case}/services',oh,{
                'service_id':service,'quantity':3,'request_id':f'g2d_service_line_{n:06d}'}))
            ok(call(reviewer,'POST',f'/api/billing/lines/{line["id"]}/fulfill',rh))
            draft=ok(call(owner,'POST',f'/api/billing/cases/{case}/drafts',oh,
                {'request_id':f'g2d_draft_line_{n:08d}'}))
            invoice=ok(call(owner,'POST',f'/api/billing/drafts/{draft["id"]}/issue',oh,
                {'request_id':f'g2d_invoice_issue_{n:05d}'}))['id']
            voucher=ok(call(owner,'POST','/api/vouchers',oh,{
                'date':today.isoformat(),'kind':'receipt','department_id':admin,'category_id':cat,
                'from_fund_id':main,'shift':'central','amount':str(net),
                'description':'صرف عهدة بعد جرد ظرف مختلط مخصص للاستدراك',
                'reference_no':prefix+'-ENV','client_request_id':f'g2d_envelope_voucher_{n:05d}'}))['id']
            ok(call(reviewer,'POST',f'/api/vouchers/{voucher}/decision',rh,
                    {'decision':'approve','reason':'تمت مراجعة سند استلام النقدية الفعلية المودعة'}))
            payload={
                'request_id':f'g2d_clear_mixed_{n:06d}','voucher_id':voucher,
                'patients':[{'document_id':patient_doc,'invoice_id':invoice}],
                'expenses':[{'document_id':expense_doc,'category_code':'hospitality','department_id':admin}],
                'approve_variance':False,
                'note':'تسوية مستقلة لنقدية ظرف تاريخي تشمل إيراد المرضى والمصروف القديم المثبت'
            }
            return incident,invoice,voucher,payload

        incident,invoice,voucher,payload=build(1,1300,200)
        with connect() as c:
            cash_before=c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]
            old_balance=c.execute('SELECT SUM(amount_piasters) FROM fund_movements WHERE fund_id=?',(main,)).fetchone()[0]
        result=ok(call(reviewer,'POST',f'/api/late-entries/{incident}/clear-mixed-envelope',rh,payload))
        assert result['variance_piasters']==0
        assert result['cash_newly_booked_piasters']==0
        assert result['status']=='balanced'
        repeat=ok(call(reviewer,'POST',f'/api/late-entries/{incident}/clear-mixed-envelope',rh,payload))
        assert repeat['replayed'] is True and repeat['id']==result['id']
        assert call(reviewer,'POST',f'/api/late-entries/{incident}/clear-mixed-envelope',rh,
            {**payload,'request_id':'g2d_duplicate_key_new_00001'}).status_code==409
        assert call(owner,'POST',f'/api/vouchers/{voucher}/reverse',oh,
            {'date':today.isoformat(),'reason':'try undo settled source'}).status_code==409
        assert call(owner,'POST',f'/api/accounting/journals/{result["journal_id"]}/reverse',oh,
            {'date':today.isoformat(),'reason':'undo historical mixed cash journal'}).status_code==409
        assert call(owner,'POST',f'/api/billing/cases/{ok(call(owner,"GET",f"/api/late-entries/{incident}"))["recovered_cases"][0]["case_id"]}/credits',oh,
            {'invoice_id':invoice,'amount':'100','reason':'cannot standalone credit for cleared case',
             'request_id':'g2d_bad_credit_request_0001'}).status_code==409
        with connect() as c:
            assert billing.invoice_due(c,invoice)==0
            assert c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]==cash_before
            assert c.execute('SELECT SUM(amount_piasters) FROM fund_movements WHERE fund_id=?',(main,)).fetchone()[0]==old_balance
            rows=c.execute('''SELECT a.code,SUM(l.debit_piasters),SUM(l.credit_piasters)
              FROM gl_lines l JOIN gl_accounts a ON a.id=l.account_id
              WHERE l.journal_id=? GROUP BY a.code''',(result['journal_id'],)).fetchall()
            changes={x[0]:(x[1],x[2]) for x in rows}
            assert changes['2350']==(130000,0),changes
            assert changes['5170']==(20000,0),changes
            assert changes['1200']==(0,150000),changes
        ok(call(reviewer,'POST',f'/api/late-entries/{incident}/action',rh,
                {'action':'resolve','note':'الفاتورة والمصروف والنقدية الصافية تمت مطابقتهم بالكامل'}))
        assert ok(call(owner,'GET',f'/api/late-entries/{incident}'))['incident']['status']=='resolved'

        incident2,invoice2,voucher2,payload2=build(2,1250,200)
        assert call(reviewer,'POST',f'/api/late-entries/{incident2}/clear-mixed-envelope',rh,payload2).status_code==409
        assert call(reviewer,'POST',f'/api/late-entries/{incident2}/clear-mixed-envelope',rh,
                   {**payload2,'approve_variance':True}).status_code==403
        reviewer_id=next(x['user_id'] for x in ok(call(owner,'GET','/api/cashier/variance-permissions',oh))
                         if x['username']=='g2d_reviewer')
        ok(call(owner,'POST','/api/cashier/variance-permissions',oh,{
            'user_id':reviewer_id,'can_approve':True,'reason':'تفويض محاسب مستقل لتسوية الفرق في ظرف اختباري'}))
        payload2={**payload2,'approve_variance':True,
            'note':'اعتماد استثنائي معلل لعجز خمسين جنيه في ظرف قديم مع إبقائه بحساب العجز تحت التسوية'}
        result2=ok(call(reviewer,'POST',f'/api/late-entries/{incident2}/clear-mixed-envelope',rh,payload2))
        assert result2['status']=='exception_approved' and result2['variance_piasters']==-5000
        with connect() as c:
            assert billing.invoice_due(c,invoice2)==0
            assert c.execute('SELECT COALESCE(SUM(debit_piasters),0) FROM gl_lines WHERE journal_id=? AND account_id=?',
                 (result2['journal_id'],ledger.account_by_code(c,'1190'))).fetchone()[0]==5000
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        ok(call(reviewer,'POST',f'/api/late-entries/{incident2}/action',rh,{
            'action':'resolve','note':'تم القبول الاستثنائي لعجز الظرف مع إثبات حساب فروق العهدة'}))
        incident3,invoice3,voucher3,payload3=build(3,1350,200)
        payload3={**payload3,'approve_variance':True,
            'note':'اعتماد استثنائي مسبب لزيادة جرد خمسين جنيه في ظرف قديم مع إبقائها تحت التسوية'}
        result3=ok(call(reviewer,'POST',f'/api/late-entries/{incident3}/clear-mixed-envelope',rh,payload3))
        assert result3['variance_piasters']==5000
        with connect() as c:
            assert billing.invoice_due(c,invoice3)==0
            assert c.execute('SELECT COALESCE(SUM(credit_piasters),0) FROM gl_lines WHERE journal_id=? AND account_id=?',
                 (result3['journal_id'],ledger.account_by_code(c,'2190'))).fetchone()[0]==5000
        ok(call(reviewer,'POST',f'/api/late-entries/{incident3}/action',rh,{
            'action':'resolve','note':'تم قبول زيادة الظرف الاستثنائية في حساب الزيادة تحت التسوية'}))
        summary=ok(call(owner,'GET',f'/api/billing/summary?period={today.isoformat()[:7]}'))
        assert summary['mixed_envelopes_this_month']==3,summary
        assert summary['mixed_envelope_expenses_piasters']==60000,summary
        assert summary['mixed_envelope_shortage_pending_piasters']==5000,summary
        assert summary['mixed_envelope_overage_pending_piasters']==5000,summary
        assert summary['suspense_cash_unallocated_piasters']==0,summary
        assert summary['total_outstanding_receivables_piasters']==0,summary
        print('PASS G2D mixed: gross 4500, paper expenses 600, cash 3900, shortage 50, overage 50, zero duplicate cash')

if __name__=='__main__':
    run()
