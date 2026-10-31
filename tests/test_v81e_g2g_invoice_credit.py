"""G2G: corrected issued invoice via credit note, NO cash, NO prior-month rewrite.
Run: python3 tests/test_v81e_g2g_invoice_credit.py
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
        os.environ['RAMSES_DB_PATH']=str(Path(tmp)/'correction.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='owner_secure_g2g_2026'
        from bootstrap import initialize, connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        import ledger,billing

        owner,clerk,reviewer=(TestClient(app) for _ in range(3))
        def call(client,verb,url,headers=None,data=None):
            return client.request(verb,url,headers=headers,json=data)
        def ok(response):
            assert response.status_code==200,(response.status_code,response.text)
            return response.json()
        def login(client,name,pw):
            return {'X-CSRF-Token':ok(call(client,'POST','/api/login',data={'username':name,'password':pw}))['csrf']}
        oh=login(owner,'owner','owner_secure_g2g_2026')
        ok(call(owner,'POST','/api/users',oh,{'username':'clerk_g2g','password':'clerk_secure_g2g_2026','role':'clerk'}))
        ok(call(owner,'POST','/api/users',oh,{'username':'reviewer_g2g','password':'reviewer_secure_g2g_2026','role':'reviewer'}))
        ch=login(clerk,'clerk_g2g','clerk_secure_g2g_2026')
        rh=login(reviewer,'reviewer_g2g','reviewer_secure_g2g_2026')
        people=ok(call(owner,'GET','/api/users'))
        cid=next(x['id'] for x in people if x['username']=='clerk_g2g')
        point=next(x for x in ok(call(owner,'GET','/api/billing/config'))['points'] if x['kind']=='external')['id']
        ok(call(owner,'POST',f'/api/billing/points/{point}/assign',oh,{'user_id':cid}))
        fund=ok(call(owner,'POST','/api/funds',oh,{'code':'g2g_cash','name':'درج تجربة تصحيح G2G','kind':'cash'}))['id']
        ok(call(owner,'POST',f'/api/billing/points/{point}/cash-fund',oh,{'fund_id':fund}))
        day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        ok(call(clerk,'POST','/api/shifts/open',ch,{'business_date':day,'shift':'night','fund_id':fund}))
        department=next(x['id'] for x in ok(call(owner,'GET','/api/lookups'))['departments'] if x['code']=='LAB')
        service=ok(call(owner,'POST','/api/billing/services',oh,{'code':'G2G_LAB_SERVICE','name':'Medical test invoice correction','department_id':department}))['id']
        ok(call(owner,'POST',f'/api/billing/services/{service}/prices',oh,{'valid_from':day,'amount':'500'}))

        def make_invoice(n):
            patient=ok(call(clerk,'POST','/api/billing/patients',ch,
                {'display_name':f'Test patient {n} correction','request_id':f'g2g_patient_request_{n:05d}'}))
            case=ok(call(clerk,'POST','/api/billing/cases',ch,
                {'patient_id':patient['id'],'kind':'outpatient','point_id':point,'business_date':day,
                 'request_id':f'g2g_case_request_{n:06d}'}))
            line=ok(call(clerk,'POST',f'/api/billing/cases/{case["id"]}/services',ch,
                 {'service_id':service,'quantity':1,'request_id':f'g2g_service_request_{n:05d}'}))
            from reviewer_scope_helpers import grant_reviewers_for_test
            grant_reviewers_for_test(owner, oh)
            ok(call(reviewer,'POST',f'/api/billing/lines/{line["id"]}/fulfill',rh))
            draft=ok(call(clerk,'POST',f'/api/billing/cases/{case["id"]}/drafts',ch,
                 {'request_id':f'g2g_draft_request_{n:05d}'}))
            invoice=ok(call(clerk,'POST',f'/api/billing/drafts/{draft["id"]}/issue',ch,
                 {'request_id':f'g2g_issue_request_{n:05d}'}))
            return patient,case,invoice

        def make_ticket(n,invoice,issue='wrong_amount'):
            body={'source_type':'invoice','source_id':invoice['id'],'issue_type':issue,
              'reason':'المبلغ الموجود في الفاتورة الأصلية أكثر من المبلغ المستحق وفق المستند الطبي',
              'proposed_resolution':'مراجعة المستند وخفض الذمة دون إعادة قبض نقدي أو تغيير أصل الفاتورة',
              'request_key':f'g2g_correction_ticket_{n:05d}'}
            ticket=ok(call(clerk,'POST','/api/corrections',ch,body))['id']
            assert call(clerk,'POST',f'/api/corrections/{ticket}/execute-invoice-credit',ch,
                {'amount':'100','expected_due_piasters':50000,'evidence_reference':'G2G-DOC-2026-100',
                'decision_note':'اعتماد تعديل مستقل بسند الخدمة الصحيح','request_key':'g2g_clerk_attempt_100'}).status_code==403
            ok(call(reviewer,'POST',f'/api/corrections/{ticket}/review',rh,
                {'decision':'triage','note':'تحققت من أصل كشف الخدمة وبداية فاتورة المريض'}))
            return ticket

        pat,case,inv=make_invoice(1)
        ticket=make_ticket(1,inv)
        with connect() as c:
            journal=c.execute('SELECT journal_id FROM billing_invoices WHERE id=?',(inv['id'],)).fetchone()['journal_id']
            count_movements=c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]
            before_tb=ledger.trial_balance(c,day[:7]); assert before_tb['balanced']
            source_journal=c.execute('SELECT * FROM gl_journals WHERE id=?',(journal,)).fetchone()
            assert source_journal['status']=='posted'
        preview=ok(call(reviewer,'GET',f'/api/corrections/{ticket}/invoice-credit-preview'))
        assert preview['eligible'] and preview['before_due_piasters']==50000,preview
        body={'amount':'100','expected_due_piasters':50000,'evidence_reference':'G2G-DOC-2026-100',
              'decision_note':'تم التأكد من المستند الأصلي وقيمة التخفيض المستحقة للمريض',
              'request_key':'g2g_execute_credit_00001'}
        assert call(reviewer,'POST',f'/api/corrections/{ticket}/execute-invoice-credit',rh,
           {**body,'amount':'600'}).status_code==409
        assert call(reviewer,'POST',f'/api/corrections/{ticket}/execute-invoice-credit',rh,
           {**body,'expected_due_piasters':49000}).status_code==409
        result=ok(call(reviewer,'POST',f'/api/corrections/{ticket}/execute-invoice-credit',rh,body))
        assert result['new_due_piasters']==40000 and not result['cash_movement_created']
        assert ok(call(reviewer,'POST',f'/api/corrections/{ticket}/execute-invoice-credit',rh,body))['replayed']
        assert call(reviewer,'POST',f'/api/corrections/{ticket}/execute-invoice-credit',rh,
            {**body,'request_key':'g2g_try_duplicate_credit_002'}).status_code==409
        assert call(reviewer,'POST',f'/api/corrections/{ticket}/execute-invoice-credit',rh,
            {**body,'amount':'50'}).status_code==409
        assert not ok(call(reviewer,'GET',f'/api/corrections/{ticket}/invoice-credit-preview'))['eligible']
        history=ok(call(clerk,'GET',f'/api/corrections/{ticket}/history'))
        assert history['financial_execution']['journal_id']==result['journal_id']
        assert any('G2G' in v['note'] for v in history['events'])
        assert call(owner,'POST',f'/api/accounting/journals/{result["journal_id"]}/reverse',oh,
            {'date':day,'reason':'Must not reverse attached credit without controlled refund'}).status_code==409
        with connect() as c:
            assert c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]==count_movements
            invoice=c.execute('SELECT total_piasters,journal_id FROM billing_invoices WHERE id=?',(inv['id'],)).fetchone()
            assert invoice['total_piasters']==50000 and invoice['journal_id']==journal
            assert billing.invoice_due(c,inv['id'])==40000
            journal=c.execute('SELECT * FROM gl_journals WHERE id=?',(result['journal_id'],)).fetchone()
            assert journal['status']=='posted' and journal['entry_date']==day
            lines=c.execute('''SELECT a.code,l.debit_piasters,l.credit_piasters
                 FROM gl_lines l JOIN gl_accounts a ON a.id=l.account_id WHERE l.journal_id=?''',
                 (journal['id'],)).fetchall()
            assert {(r['code'],r['debit_piasters'],r['credit_piasters']) for r in lines}=={
                 ('4195',10000,0),('1200',0,10000)}
            assert ledger.trial_balance(c,day[:7])['balanced']
            assert c.execute('SELECT COUNT(*) FROM billing_credit_requests WHERE invoice_id=?',(inv['id'],)).fetchone()[0]==1
            for sql in ["UPDATE financial_invoice_credit_fixes SET amount_piasters=2 WHERE ticket_id=?",
                        "DELETE FROM financial_invoice_credit_fixes WHERE ticket_id=?"]:
                try:c.execute(sql,(ticket,))
                except Exception:pass
                else:raise AssertionError('G2G correction is mutable')
        # Second fully-paid invoice must not be adjusted by this conservative correction route.
        patient2,case2,inv2=make_invoice(2)
        ticket2=make_ticket(2,inv2)
        amount=ok(call(clerk,'POST',f'/api/billing/cases/{case2["id"]}/collect',ch,
           {'request_id':'g2g_payment_request_20001','point_id':point,'invoice_id':inv2['id'],
             'patient_code':patient2['code'],'parts':[{'method':'cash','amount':'50'}]}))
        assert amount['total_piasters']==5000
        bad_preview=ok(call(reviewer,'GET',f'/api/corrections/{ticket2}/invoice-credit-preview'))
        assert not bad_preview['eligible']
        assert call(reviewer,'POST',f'/api/corrections/{ticket2}/execute-invoice-credit',rh,
           {**body,'request_key':'g2g_paid_invoice_denied_0001'}).status_code==409
        with connect() as c:
            assert billing.invoice_due(c,inv2['id'])==45000
            assert c.execute('SELECT COUNT(*) FROM financial_invoice_credit_fixes').fetchone()[0]==1
        # Invoice issued during a previous period can be corrected in a NEW open month;
        # its original GL/issued date stay untouched, and the closed period stays closed.
        patient3,case3,inv3=make_invoice(3)
        ticket3=make_ticket(3,inv3)
        future=(date.fromisoformat(day)+timedelta(days=40)).isoformat()
        assert future[:7]!=day[:7]
        from app import stamp
        with connect() as c:
            owner_id=c.execute("SELECT id FROM users WHERE username='owner'").fetchone()['id']
            c.execute('INSERT INTO periods(period,closed_by,closed_at) VALUES (?,?,?)',
                      (day[:7],owner_id,stamp()))
        import financial_corrections
        actual_today=financial_corrections.cairo_today
        financial_corrections.cairo_today=lambda:future
        try:
            older=ok(call(reviewer,'POST',f'/api/corrections/{ticket3}/execute-invoice-credit',rh,
               {**body,'request_key':'g2g_closed_source_open_post_01'}))
            assert older['new_due_piasters']==40000
            with connect() as c:
                original=c.execute('SELECT issued_date FROM billing_invoices WHERE id=?',(inv3['id'],)).fetchone()
                correction=c.execute('SELECT entry_date FROM gl_journals WHERE id=?',(older['journal_id'],)).fetchone()
                assert original['issued_date']==day and correction['entry_date']==future
                assert c.execute('SELECT 1 FROM periods WHERE period=?',(day[:7],)).fetchone()
        finally:
            financial_corrections.cairo_today=actual_today
        print('PASS G2G invoice credit: independent review, balanced GL, no cash, replay protection, paid invoice guard, closed-origin/open-post')

if __name__=='__main__':run()
