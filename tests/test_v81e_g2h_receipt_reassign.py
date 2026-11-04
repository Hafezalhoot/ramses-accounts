"""G2H integration: full wrong-patient receipt reallocation, no double cash or GL.
Run: python3 tests/test_v81e_g2h_receipt_reassign.py
"""
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ['RAMSES_DB_PATH']=str(Path(tmp)/'g2h.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='owner_secure_g2h_2026'
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        import billing,ledger,financial_corrections
        owner,clerk,reviewer=(TestClient(app) for _ in range(3))

        def call(client,verb,path,headers=None,data=None):
            return client.request(verb,path,headers=headers,json=data)
        def ok(res):
            assert res.status_code==200,(res.status_code,res.text)
            return res.json()
        def login(client,user,pw):
            return {'X-CSRF-Token':ok(call(client,'POST','/api/login',data={
                'username':user,'password':pw}))['csrf']}

        oh=login(owner,'owner','owner_secure_g2h_2026')
        ok(call(owner,'POST','/api/users',oh,{'username':'clerk_g2h',
            'password':'clerk_secure_g2h_2026','role':'clerk'}))
        ok(call(owner,'POST','/api/users',oh,{'username':'reviewer_g2h',
            'password':'reviewer_secure_g2h_2026','role':'reviewer'}))
        ch=login(clerk,'clerk_g2h','clerk_secure_g2h_2026')
        rh=login(reviewer,'reviewer_g2h','reviewer_secure_g2h_2026')
        people=ok(call(owner,'GET','/api/users'))
        clerk_id=next(x['id'] for x in people if x['username']=='clerk_g2h')
        point=next(x for x in ok(call(owner,'GET','/api/billing/config'))['points']
                   if x['kind']=='external')['id']
        ok(call(owner,'POST',f'/api/billing/points/{point}/assign',oh,{'user_id':clerk_id}))
        fund=ok(call(owner,'POST','/api/funds',oh,{'code':'g2h_cash',
             'name':'Test correction till G2H','kind':'cash'}))['id']
        ok(call(owner,'POST',f'/api/billing/points/{point}/cash-fund',oh,{'fund_id':fund}))
        card=ok(call(owner,'POST','/api/funds',oh,{'code':'bclear_card',
             'name':'Test card clearing G2H','kind':'wallet'}))['id']
        ok(call(owner,'POST','/api/billing/channels',oh,{'method':'card','fund_id':card}))
        day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        ok(call(clerk,'POST','/api/shifts/open',ch,{'business_date':day,
            'shift':'night','fund_id':fund}))
        department=next(x['id'] for x in ok(call(owner,'GET','/api/lookups'))['departments']
                        if x['code']=='LAB')
        service=ok(call(owner,'POST','/api/billing/services',oh,{'code':'G2H_MEDICAL_TEST',
            'name':'G2H demo medical laboratory test','department_id':department}))['id']
        ok(call(owner,'POST',f'/api/billing/services/{service}/prices',oh,
                {'valid_from':day,'amount':'500'}))

        def invoice(n):
            patient=ok(call(clerk,'POST','/api/billing/patients',ch,{
                'display_name':f'G2H fictional patient {n}',
                'request_id':f'g2h_patient_request_{n:06d}'}))
            case=ok(call(clerk,'POST','/api/billing/cases',ch,{
                'patient_id':patient['id'],'kind':'outpatient','point_id':point,
                'business_date':day,'request_id':f'g2h_case_request_{n:06d}'}))
            line=ok(call(clerk,'POST',f'/api/billing/cases/{case["id"]}/services',ch,{
                'service_id':service,'quantity':1,'request_id':f'g2h_line_request_{n:06d}'}))
            from reviewer_scope_helpers import grant_reviewers_for_test
            grant_reviewers_for_test(owner, oh)
            ok(call(reviewer,'POST',f'/api/billing/lines/{line["id"]}/fulfill',rh))
            draft=ok(call(clerk,'POST',f'/api/billing/cases/{case["id"]}/drafts',ch,{
                'request_id':f'g2h_draft_request_{n:06d}'}))
            inv=ok(call(clerk,'POST',f'/api/billing/drafts/{draft["id"]}/issue',ch,{
                'request_id':f'g2h_issue_request_{n:06d}'}))
            return patient,case,inv

        def collect(n,patient,case,inv,parts):
            return ok(call(clerk,'POST',f'/api/billing/cases/{case["id"]}/collect',ch,{
                'request_id':f'g2h_pay_request_{n:06d}',
                'point_id':point,'invoice_id':inv['id'],
                'patient_code':patient['code'],'parts':parts}))

        def ticket(n,collection):
            opened=ok(call(clerk,'POST','/api/corrections',ch,{
                'source_type':'collection','source_id':collection['id'],
                'issue_type':'wrong_patient',
                'reason':'الإيصال رُبط خطأ بملف مريض آخر رغم أن النقدية سُلّمت ومرحّلة بالفعل',
                'proposed_resolution':'نقل مديونية الإيصال بالكامل إلى فاتورة المريض الصحيح بمستند إثبات',
                'request_key':f'g2h_ticket_request_{n:07d}'}))
            tid=opened['id']
            ok(call(reviewer,'POST',f'/api/corrections/{tid}/review',rh,{
                'decision':'triage','note':'مراجعة مستقلة لهوية المريض ولإيصال القبض الأصلي'}))
            return tid

        patient_a,case_a,invoice_a=invoice(1)
        patient_b,case_b,invoice_b=invoice(2)
        collected=collect(1,patient_a,case_a,invoice_a,[
            {'method':'cash','amount':'60'},{'method':'card','amount':'40'}])
        tid=ticket(1,collected)
        inspect={'target_invoice_id':invoice_b['id'],
                 'target_patient_code':patient_b['code']}
        bad=ok(call(reviewer,'POST',f'/api/corrections/{tid}/collection-reassign-preview',rh,
                    {**inspect,'target_patient_code':patient_a['code']}))
        assert not bad['eligible']
        denied=call(clerk,'POST',f'/api/corrections/{tid}/collection-reassign-preview',ch,inspect)
        assert denied.status_code==403
        denied=ok(call(reviewer,'POST',f'/api/corrections/{tid}/collection-reassign-preview',rh,
                       {'target_invoice_id':invoice_a['id'],'target_patient_code':patient_a['code']}))
        assert not denied['eligible']
        preview=ok(call(reviewer,'POST',f'/api/corrections/{tid}/collection-reassign-preview',rh,inspect))
        assert preview['eligible'] and preview['amount_piasters']==10000
        assert (preview['before_source_due_piasters'],preview['before_target_due_piasters'])==(40000,50000)
        body={**inspect,'expected_source_due_piasters':40000,'expected_target_due_piasters':50000,
              'evidence_reference':'G2H-TRANSFER-CASE-1024',
              'decision_note':'اعتمدت نقل المبلغ كاملًا بعد مطابقة هوية المريض والمستندات',
              'request_key':'g2h_execution_request_00001'}
        with connect() as c:
            cash_count=c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]
            voucher_count=c.execute('SELECT COUNT(*) FROM vouchers').fetchone()[0]
            gl_count=c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0]
            ledger_before=ledger.trial_balance(c,day[:7]);assert ledger_before['balanced']
            original=c.execute('SELECT * FROM billing_collections WHERE id=?',(collected['id'],)).fetchone()
            source_shift=original['shift_session_id']
        assert call(reviewer,'POST',f'/api/corrections/{tid}/execute-collection-reassign',rh,
                    {**body,'expected_target_due_piasters':49000}).status_code==409
        assert call(reviewer,'POST',f'/api/corrections/{tid}/execute-collection-reassign',rh,
                    {**body,'target_patient_code':patient_a['code']}).status_code==409
        done=ok(call(reviewer,'POST',f'/api/corrections/{tid}/execute-collection-reassign',rh,body))
        assert not done['replayed'] and not done['cash_movement_created']
        assert (done['after_source_due_piasters'],done['after_target_due_piasters'])==(50000,40000)
        assert ok(call(reviewer,'POST',f'/api/corrections/{tid}/execute-collection-reassign',rh,body))['replayed']
        assert call(reviewer,'POST',f'/api/corrections/{tid}/execute-collection-reassign',rh,
                    {**body,'request_key':'g2h_duplicate_request_0002'}).status_code==409
        history=ok(call(reviewer,'GET',f'/api/corrections/{tid}/history'))
        assert history['collection_reallocation']['to_invoice_id']==invoice_b['id']
        assert any('G2H' in e['note'] for e in history['events'])
        assert ok(call(reviewer,'GET','/api/corrections'))['tickets'][0]['resolved_reallocation_id']
        old_receipt=ok(call(clerk,'GET',f'/api/billing/collections/{collected["id"]}'))
        assert old_receipt['case_no']==case_a['case_no'] and old_receipt['allocation_corrected']
        printed=call(clerk,'GET',f'/api/billing/collections/{collected["id"]}/print')
        assert printed.status_code==200,printed.text
        assert case_a['case_no'] in printed.text and invoice_a['invoice_no'] in printed.text
        assert case_b['case_no'] not in printed.text and invoice_b['invoice_no'] not in printed.text
        assert '100.00' in printed.text and 'نقدي' in printed.text and 'بطاقة POS' in printed.text
        assert 'تغير تخصيصه بتصحيح مستقل' in printed.text
        old_case=ok(call(clerk,'GET',f'/api/billing/cases/{case_a["id"]}/finance'))
        new_case=ok(call(clerk,'GET',f'/api/billing/cases/{case_b["id"]}/finance'))
        assert old_case['outstanding_piasters']==50000
        assert new_case['outstanding_piasters']==40000
        assert old_case['collections'][0]['reallocation_id']==done['id']
        assert new_case['collections'][0]['effective_case_id']==case_b['id']
        with connect() as c:
            assert c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]==cash_count
            assert c.execute('SELECT COUNT(*) FROM vouchers').fetchone()[0]==voucher_count
            assert c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0]==gl_count
            assert ledger.trial_balance(c,day[:7])==ledger_before
            col=c.execute('SELECT * FROM billing_collections WHERE id=?',(collected['id'],)).fetchone()
            assert col['case_id']==case_a['id'] and col['invoice_id']==invoice_a['id']
            assert col['shift_session_id']==source_shift
            assert c.execute('SELECT COUNT(*) FROM billing_payment_parts WHERE collection_id=?',
                             (collected['id'],)).fetchone()[0]==2
            assert billing.invoice_due(c,invoice_a['id'])==50000
            assert billing.invoice_due(c,invoice_b['id'])==40000
            assert billing.invoice_receipted(c,invoice_a['id'])==0
            assert billing.invoice_receipted(c,invoice_b['id'])==10000
            assert billing.refund_capacity(c,case_a['id'],'credit','cash')==0
            assert billing.refund_capacity(c,case_b['id'],'credit','cash')==6000
            for sql in ['UPDATE financial_collection_reallocations SET amount_piasters=4 WHERE id=?',
                        'DELETE FROM financial_collection_reallocations WHERE id=?']:
                try:c.execute(sql,(done['id'],))
                except Exception:pass
                else:raise AssertionError('G2H entry can be altered directly')
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert c.execute('PRAGMA foreign_key_check').fetchall()==[]

        # New source + target, but a target that has only 50 EGP remaining.
        patient_c,case_c,invoice_c=invoice(3)
        patient_d,case_d,invoice_d=invoice(4)
        wrong2=collect(2,patient_c,case_c,invoice_c,[{'method':'cash','amount':'100'}])
        ok( call(clerk,'POST',f'/api/billing/cases/{case_d["id"]}/collect',ch,{
            'request_id':'g2h_target_paid_00001','point_id':point,'invoice_id':invoice_d['id'],
            'patient_code':patient_d['code'],'parts':[{'method':'cash','amount':'450'}]}))
        ticket2=ticket(2,wrong2)
        limited=ok(call(reviewer,'POST',f'/api/corrections/{ticket2}/collection-reassign-preview',rh,
               {'target_invoice_id':invoice_d['id'],'target_patient_code':patient_d['code']}))
        assert not limited['eligible'] and 'أكبر' in limited['reason']

        # Competing approvals must never allocate the same receipt twice.
        # Separate sessions simulate two fast reviewers hitting the same triaged ticket.
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        patient_g,case_g,invoice_g=invoice(7)
        patient_h,case_h,invoice_h=invoice(8)
        wrong4=collect(4,patient_g,case_g,invoice_g,[{'method':'cash','amount':'90'}])
        ticket4=ticket(4,wrong4)
        check4=ok(call(reviewer,'POST',f'/api/corrections/{ticket4}/collection-reassign-preview',rh,
                   {'target_invoice_id':invoice_h['id'],'target_patient_code':patient_h['code']}))
        assert check4['eligible']
        gate=Barrier(2)
        def concurrent_approve(which):
            peer=TestClient(app)
            h=login(peer,'reviewer_g2h','reviewer_secure_g2h_2026')
            body={'target_invoice_id':invoice_h['id'],'target_patient_code':patient_h['code'],
                  'expected_source_due_piasters':check4['before_source_due_piasters'],
                  'expected_target_due_piasters':check4['before_target_due_piasters'],
                  'evidence_reference':f'G2H-CONCURRENT-{which:04d}',
                  'decision_note':'مراجعة مستقلة ورصد تنازع طلبين لمنع اعتماد الإيصال مرتين',
                  'request_key':f'g2h_concurrent_request_{which:08d}'}
            gate.wait(timeout=10)
            return call(peer,'POST',f'/api/corrections/{ticket4}/execute-collection-reassign',h,body).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=sorted(pool.map(concurrent_approve,(1,2)))
        assert results==[200,409],results
        with connect() as c:
            assert c.execute('SELECT COUNT(*) FROM financial_collection_reallocations WHERE collection_id=?',
                             (wrong4['id'],)).fetchone()[0]==1
            assert billing.invoice_due(c,invoice_g['id'])==50000
            assert billing.invoice_due(c,invoice_h['id'])==41000

        # Later correction on an old/closed origin month is dated in a NEW open month.
        patient_e,case_e,invoice_e=invoice(5)
        patient_f,case_f,invoice_f=invoice(6)
        wrong3=collect(3,patient_e,case_e,invoice_e,[{'method':'cash','amount':'75'}])
        ticket3=ticket(3,wrong3)
        future=(date.fromisoformat(day)+timedelta(days=40)).isoformat()
        assert future[:7]!=day[:7]
        with connect() as c:
            owner_id=c.execute("SELECT id FROM users WHERE username='owner'").fetchone()['id']
            c.execute('INSERT INTO periods(period,closed_by,closed_at) VALUES (?,?,?)',
                      (day[:7],owner_id,datetime.now().isoformat()))
        actual_today=financial_corrections.cairo_today
        financial_corrections.cairo_today=lambda:future
        try:
            preview3=ok(call(reviewer,'POST',f'/api/corrections/{ticket3}/collection-reassign-preview',rh,
                       {'target_invoice_id':invoice_f['id'],'target_patient_code':patient_f['code']}))
            assert preview3['eligible']
            result3=ok(call(reviewer,'POST',f'/api/corrections/{ticket3}/execute-collection-reassign',rh,{
                'target_invoice_id':invoice_f['id'],'target_patient_code':patient_f['code'],
                'expected_source_due_piasters':42500,'expected_target_due_piasters':50000,
                'evidence_reference':'G2H-CLOSED-ORIGIN-2026',
                'decision_note':'اعتماد مراجع مستقل لخطأ تاريخي دون فتح الفترة المالية السابقة',
                'request_key':'g2h_closed_origin_request_00001'}))
            assert result3['after_target_due_piasters']==42500
            with connect() as c:
                correction=c.execute('SELECT effective_date FROM financial_collection_reallocations WHERE id=?',
                                     (result3['id'],)).fetchone()
                orig=c.execute('SELECT business_date FROM billing_collections WHERE id=?',
                               (wrong3['id'],)).fetchone()
                assert correction['effective_date']==future and orig['business_date']==day
                assert c.execute('SELECT 1 FROM periods WHERE period=?',(day[:7],)).fetchone()
        finally:
            financial_corrections.cairo_today=actual_today
        print('PASS G2H: wrong-patient FULL mixed receipt; no new cash/GL; case AR; immutable audit; replay; stale/identity guards; closed origin/new effective date')

if __name__=='__main__':run()
