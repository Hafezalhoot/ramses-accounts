"""Regression for independently reproduced G2H audit findings FIN-001..FIN-005.
Isolated throwaway SQLite only; no financial production records.
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
        os.environ['RAMSES_DB_PATH']=str(Path(tmp)/'g2i.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='owner_secure_g2i_2026_test'
        from bootstrap import connect,initialize
        initialize()
        from fastapi.testclient import TestClient
        from app import app
        import ledger,financial_integrity
        owner,reviewer,clerk=(TestClient(app) for _ in range(3))

        def ok(r):
            assert r.status_code==200,(r.status_code,r.text)
            return r.json()
        def login(client,username,pw):
            return {'X-CSRF-Token':ok(client.post('/api/login',json={
                'username':username,'password':pw}))['csrf']}

        oh=login(owner,'owner','owner_secure_g2i_2026_test')
        ok(owner.post('/api/users',headers=oh,json={'username':'reviewer_g2i',
            'password':'reviewer_g2i_2026_secure','role':'reviewer'}))
        ok(owner.post('/api/users',headers=oh,json={'username':'clerk_g2i',
            'password':'clerk_g2i_2026_secure','role':'clerk'}))
        rh=login(reviewer,'reviewer_g2i','reviewer_g2i_2026_secure')
        ch=login(clerk,'clerk_g2i','clerk_g2i_2026_secure')
        users=ok(owner.get('/api/users'))
        clerk_id=next(x['id'] for x in users if x['username']=='clerk_g2i')
        point=next(x for x in ok(owner.get('/api/billing/config'))['points'] if x['kind']=='external')['id']
        ok(owner.post(f'/api/billing/points/{point}/assign',headers=oh,json={'user_id':clerk_id}))
        cash=ok(owner.post('/api/funds',headers=oh,json={'code':'g2i_cash',
            'name':'Cash test drawer G2I','kind':'cash'}))['id']
        ok(owner.post(f'/api/billing/points/{point}/cash-fund',headers=oh,json={'fund_id':cash}))
        day=datetime.now(ZoneInfo('Africa/Cairo')).date()
        month=day.strftime('%Y-%m')
        previous=(day.replace(day=1)-timedelta(days=1)).strftime('%Y-%m')
        ok(clerk.post('/api/shifts/open',headers=ch,json={'business_date':day.isoformat(),
            'shift':'night','fund_id':cash}))
        dept=next(x['id'] for x in ok(owner.get('/api/lookups'))['departments'] if x['code']=='LAB')
        srv=ok(owner.post('/api/billing/services',headers=oh,json={'code':'G2I_FIN_SAFE',
            'name':'Fictional financial test medical service','department_id':dept}))['id']
        ok(owner.post(f'/api/billing/services/{srv}/prices',headers=oh,json={
            'valid_from':day.isoformat(),'amount':'500'}))
        pt=ok(clerk.post('/api/billing/patients',headers=ch,json={'display_name':'مريض تجريبي لاختبار السلامة',
            'request_id':'g2i_patient_test_001'}))
        case=ok(clerk.post('/api/billing/cases',headers=ch,json={'patient_id':pt['id'],
            'kind':'outpatient','point_id':point,'business_date':day.isoformat(),
            'request_id':'g2i_case_test_001'}))
        line=ok(clerk.post(f'/api/billing/cases/{case["id"]}/services',headers=ch,json={
            'service_id':srv,'quantity':1,'request_id':'g2i_line_test_001'}))
        from reviewer_scope_helpers import grant_reviewers_for_test
        grant_reviewers_for_test(owner, oh)
        ok(reviewer.post(f'/api/billing/lines/{line["id"]}/fulfill',headers=rh))
        draft=ok(clerk.post(f'/api/billing/cases/{case["id"]}/drafts',headers=ch,json={
            'request_id':'g2i_draft_test_001'}))
        invoice=ok(clerk.post(f'/api/billing/drafts/{draft["id"]}/issue',headers=ch,json={
            'request_id':'g2i_invoice_test_001'}))
        with connect() as c:
            doc=c.execute('SELECT * FROM billing_invoices WHERE id=?',(invoice['id'],)).fetchone()
            invoice_journal=doc['journal_id']
            assert financial_integrity.journal_source(c,invoice_journal)=='billing_invoices'
        blocked=reviewer.post(f'/api/accounting/journals/{invoice_journal}/reverse',headers=rh,
            json={'date':day.isoformat(),'reason':'Independent fraudulent reversal test'})
        assert blocked.status_code==409,blocked.text
        # Record a legitimate advance and an allocation, neither moves cash twice.
        ok(clerk.post(f'/api/billing/cases/{case["id"]}/collect',headers=ch,json={
            'request_id':'g2i_advance_test_001','point_id':point,'invoice_id':None,
            'parts':[{'method':'cash','amount':'100'}]}))
        ok(clerk.post(f'/api/billing/cases/{case["id"]}/apply-advance',headers=ch,json={
            'request_id':'g2i_apply_advance_test_001','invoice_id':invoice['id'],'amount':'100'}))
        with connect() as c:
            advance_journal=c.execute('SELECT journal_id FROM billing_advance_allocations').fetchone()[0]
            assert financial_integrity.journal_source(c,advance_journal)=='billing_advance_allocations'
        assert reviewer.post(f'/api/accounting/journals/{advance_journal}/reverse',headers=rh,
            json={'date':day.isoformat(),'reason':'Independent advance reversal test'}).status_code==409

        # A free manual journal cannot inflate patient receivables or bypass them via approval.
        with connect() as c:
            ar=ledger.account_by_code(c,'1200');revenue=ledger.account_by_code(c,'4100')
            other=ledger.account_by_code(c,'4190')
        denied=owner.post('/api/accounting/journals',headers=oh,json={
            'date':day.isoformat(),'memo':'Fake patient receivable manual entry',
            'lines':[{'account_id':ar,'debit':'123','credit':'0'},
                     {'account_id':other,'debit':'0','credit':'123'}]})
        assert denied.status_code==409,denied.text
        good=ok(owner.get('/api/accounting/patient-reconciliation',params={'period':month}))
        assert good['matched'],good
        assert {r['code'] for r in good['checks']}=={'1200','2300','2310'}
        # A cashier must not access an institution-wide patient balance report.
        assert clerk.get('/api/accounting/patient-reconciliation',
            params={'period':month}).status_code==403

        # Old pending manual control postings (created before the upgrade)
        # are also rejected during independent approval, not just at creation.
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            old_pending=ledger._journal(c,entry_date=day.isoformat(),
                memo='Historical pending invalid control-account entry',
                origin='manual',source_id=None,created_by=clerk_id,
                lines=[(ar,12300,0,None),(other,0,12300,None)])
            c.commit()
        assert reviewer.post(f'/api/accounting/journals/{old_pending}/decision',
            headers=rh,json={'decision':'approve','reason':'Unsafe historical approval attempt'}).status_code==409

        # Legacy pending reversal created before upgrade must not be approved.
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            lines=[(r['account_id'],r['credit_piasters'],r['debit_piasters'],r['department_id'])
                for r in c.execute('SELECT * FROM gl_lines WHERE journal_id=?',(invoice_journal,))]
            pending_reverse=ledger._journal(c,entry_date=day.isoformat(),
                memo='Historical pending reversal no longer permissible',origin='manual_reversal',
                source_id=None,reversal_of=invoice_journal,created_by=clerk_id,lines=lines)
            c.commit()
        result=reviewer.post(f'/api/accounting/journals/{pending_reverse}/decision',headers=rh,
            json={'decision':'approve','reason':'Attempt to approve unsafe legacy reversal'})
        assert result.status_code==409,result.text

        # Simulate a historically approved control-account entry: old data is
        # preserved, but the mismatch must block closure with a useful reason.
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            injected=ledger._journal(c,entry_date=previous+'-01',
                memo='Legacy unlinked receivable from old database',origin='manual',source_id=None,
                created_by=clerk_id,reviewed_by=users[0]['id'],
                lines=[(ar,12300,0,None),(other,0,12300,None)])
            c.commit()
            mismatch=financial_integrity.patient_reconciliation(c,previous)
            assert not mismatch['matched'] and mismatch['checks'][0]['difference_piasters']==12300,mismatch
        # No shift needed in prior month, avoid historical scheduling fixtures.
        preflight=ok(owner.get('/api/periods/preflight',params={'period':previous}))
        assert not preflight['ready'] and 'ذمم' in preflight['reason'],preflight
        assert owner.post('/api/periods/close',headers=oh,json={'period':previous}).status_code==409
        future=(day.replace(year=day.year+1)).strftime('%Y-%m')
        assert not ok(owner.get('/api/periods/preflight',params={'period':future}))['ready']
        assert owner.post('/api/periods/close',headers=oh,json={'period':future}).status_code==409
        assert owner.post('/api/periods/close',headers=oh,json={'period':month}).status_code==409
        print('PASS G2I: auto-journal reversals blocked; manual control account blocked; pending bypass blocked; AR/advance/refund matched; historical mismatch and future close rejected')

if __name__=='__main__':run()
