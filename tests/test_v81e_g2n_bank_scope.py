"""G2N security gate: bank evidence and mutations require fund-scoped grants.

Uses only an isolated, synthetic SQLite DB and real HTTP API requests; verifies
immediate revocation, account-ID guessing, preparer/approver separation and
no list/export/download bypass.
"""
import io
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def run():
    with tempfile.TemporaryDirectory() as td:
        os.environ['RAMSES_DB_PATH']=str(Path(td)/'bank_scope.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='owner_g2n_testing_very_long_pw'
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner,preparer,signer,outsider=(TestClient(app) for _ in range(4))
        def check(r,code=200):
            assert r.status_code==code,(code,r.status_code,r.text)
            return r.json() if code==200 else None
        def signin(client,name,pw):
            return {'X-CSRF-Token':check(client.post('/api/login',json={'username':name,'password':pw}))['csrf']}
        oh=signin(owner,'owner','owner_g2n_testing_very_long_pw')
        users={}
        for n in ('preparer','signer','outsider'):
            users[n]=check(owner.post('/api/users',headers=oh,json={
                'username':n,'role':'reviewer','password':'shared_test_only_long_password'}))['id']
        ph=signin(preparer,'preparer','shared_test_only_long_password')
        sh=signin(signer,'signer','shared_test_only_long_password')
        xh=signin(outsider,'outsider','shared_test_only_long_password')
        bank1=check(owner.post('/api/funds',headers=oh,json={
            'code':'test_bank_g2n_a','name':'Synthetic test bank A','kind':'bank'}))['id']
        bank2=check(owner.post('/api/funds',headers=oh,json={
            'code':'test_bank_g2n_b','name':'Synthetic test bank B','kind':'bank'}))['id']
        def grant(username,bank,submit=None,approve=None):
            payload={'user_id':users[username],'fund_id':bank,'reason':'Owner approved bank access security test'}
            if submit is not None:payload['can_submit']=submit
            if approve is not None:payload['can_approve']=approve
            return check(owner.post('/api/fund-access',headers=oh,json=payload))
        grant('preparer',bank1,submit=True)
        grant('signer',bank1,approve=True)
        month='2026-08'
        url=f'/api/bank-reconciliation?period={month}&fund_id={bank1}'
        check(outsider.get(url),403)
        check(preparer.get(f'/api/bank-reconciliation?period={month}&fund_id={bank2}'),403)
        check(preparer.get(f'/api/bank-reconciliation?period={month}&fund_id=999999'),403)
        assert not check(outsider.get('/api/bank-reconciliation?period='+month))['banks']
        banks=check(preparer.get('/api/bank-reconciliation?period='+month))['banks']
        assert [b['id'] for b in banks]==[bank1],banks
        assert [b['id'] for b in check(signer.get('/api/bank-reconciliation?period='+month))['banks']]==[bank1]
        assert check(preparer.get(url))['permissions']=={'can_submit':True,'can_approve':False}
        assert check(signer.get(url))['permissions']=={'can_submit':False,'can_approve':True}
        assert check(owner.get(url))['permissions']=={'can_submit':True,'can_approve':True}
        check(preparer.get(f'/api/bank-reconciliation/export.csv?period={month}&fund_id={bank2}'),403)
        raw=b'date,description,amount,reference\n2026-08-14,synthetic transfer,10.00,SCOPE-1\n'
        def imp(client,headers,bank):
            return client.post('/api/bank-reconciliation/import',headers=headers,data={
                'fund_id':str(bank),'period':month,'opening_balance':'0','closing_balance':'10'},
                files={'file':('synthetic.csv',io.BytesIO(raw),'text/csv')})
        check(outsider.post('/api/bank-reconciliation/import',headers=xh,data={
            'fund_id':str(bank1),'period':month,'opening_balance':'0','closing_balance':'10'},
            files={'file':('synthetic.csv',io.BytesIO(raw))}),403)
        check(imp(signer,sh,bank1),403) # approve-only cannot import
        check(imp(preparer,ph,bank2),403)
        batch=check(imp(preparer,ph,bank1))['batch_id']
        assert signer.get(f'/api/bank-reconciliation/{batch}/source.csv').content==raw
        check(outsider.get(f'/api/bank-reconciliation/{batch}/source.csv'),403)
        check(signer.post(f'/api/bank-reconciliation/{batch}/match',headers=sh,
             json={'line_id':1,'movement_id':1}),403)
        check(signer.post(f'/api/bank-reconciliation/{batch}/unmatch',headers=sh,
             json={'match_id':1,'reason':'Unauthorized change attempt'}),403)
        check(preparer.post(f'/api/bank-reconciliation/{batch}/approve',headers=ph,json={}),403)
        check(outsider.post(f'/api/bank-reconciliation/{batch}/approve',headers=xh,json={}),403)
        # Synthetic voucher produces the bank-side cashbook movement. Signer can
        # approve vouchers but cannot author or match a bank statement.
        lookup=check(owner.get('/api/lookups'))
        rev=next(x['id'] for x in lookup['categories'] if x['code']=='other_revenue')
        dept=lookup['departments'][0]['id']
        voucher=check(owner.post('/api/vouchers',headers=oh,json={
            'date':'2026-08-14','kind':'receipt','department_id':dept,
            'category_id':rev,'shift':'central','from_fund_id':bank1,
            'amount':'10','description':'Synthetic bank scoped reconciliation receipt'}))['id']
        check(signer.post(f'/api/vouchers/{voucher}/decision',headers=sh,
             json={'decision':'approve','reason':'Synthetic independent review'}))
        report=check(preparer.get(url))
        line=report['lines'][0]['id']
        move=report['unmatched_ledger'][0]['movement_id']
        check(preparer.post(f'/api/bank-reconciliation/{batch}/match',headers=ph,
             json={'line_id':line,'movement_id':move}))
        # Reviewer with approval scope signs independently; owner visibility remains intact.
        approved=check(signer.post(f'/api/bank-reconciliation/{batch}/approve',headers=sh,
             json={'note':'Verified synthetic bank entries'}))
        assert approved['status']=='approved'
        # Revoke grants during existing session: no fresh login should be required.
        grant('preparer',bank1,submit=False)
        check(preparer.get(url),403)
        check(preparer.get(f'/api/bank-reconciliation/{batch}/source.csv'),403)
        check(preparer.get(f'/api/bank-reconciliation/export.csv?period={month}&fund_id={bank1}'),403)
        assert check(preparer.get('/api/bank-reconciliation?period='+month))['banks']==[]
        assert check(owner.get(url))['matched_count']==1
        assert check(signer.get(url))['matched_count']==1
        # POS case reads are NOT a loophole to list bank data for the ungranted reviewer.
        check(preparer.get(f'/api/pos/settlements?period={month}&bank_fund_id={bank1}'),403)
        check(outsider.get(f'/api/pos/settlements?period={month}&bank_fund_id={bank1}'),403)
        # Bank-only approval must NOT disclose card receipt candidates or POS history.
        missing_wallet=check(signer.get(f'/api/pos/settlements?period={month}&bank_fund_id={bank1}'))
        assert not missing_wallet['candidates'] and not missing_wallet['settlements']
        assert missing_wallet['permissions']=={'can_submit':False,'can_approve':False}
        # Wallet grant unlocks the dedicated POS review scope, not authoring.
        wallet=check(owner.post('/api/funds',headers=oh,json={'code':'bclear_scope_g2n','name':'Synthetic POS clearing wallet G2N','kind':'wallet'}))['id']
        check(owner.post('/api/billing/channels',headers=oh,json={'method':'card','fund_id':wallet}))
        missing_wallet=check(signer.get(f'/api/pos/settlements?period={month}&bank_fund_id={bank1}'))
        assert missing_wallet['clearing_fund_id'] is None
        grant('signer',wallet,approve=True)
        allowed_wallet=check(signer.get(f'/api/pos/settlements?period={month}&bank_fund_id={bank1}'))
        assert allowed_wallet['clearing_fund_id']==wallet
        assert allowed_wallet['permissions']=={'can_submit':False,'can_approve':True}
        # Holding only the POS clearing-wallet grant must not open POS history
        # or patient-card receipts when all bank account grants are revoked.
        grant('signer',bank1,approve=False)
        wallet_only=check(signer.get(f'/api/pos/settlements?period={month}'))
        assert wallet_only['banks']==[] and wallet_only['settlements']==[]
        assert wallet_only['candidates']==[] and wallet_only['clearing_fund_id'] is None
        assert wallet_only['permissions']=={'can_submit':False,'can_approve':False}
        with connect() as c:
            assert c.execute("SELECT COUNT(*) FROM audit_log WHERE action='change_fund_grant'").fetchone()[0]>=3
            assert c.execute("SELECT COUNT(*) FROM bank_statement_batches WHERE status='approved'").fetchone()[0]==1
        print('PASS G2N bank fund-scoped read/import/match/approve/revoke and POS IDOR safety')

if __name__=='__main__': run()
