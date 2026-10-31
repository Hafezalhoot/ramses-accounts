"""G2L financial release gate: opening evidence, source-linked GL and reviewer separation."""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as d:
        os.environ['RAMSES_DB_PATH']=str(Path(d)/'opening.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='g2l_owner_opening_test_pass'
        os.environ.pop('GOOGLE_SHEET_ID',None)
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        import ledger
        from treasury_integrity import treasury_reconciliation
        owner,reviewer,viewer=(TestClient(app) for _ in range(3))
        def ok(response):
            assert response.status_code==200,(response.status_code,response.text)
            return response.json()
        def deny(response,code):
            assert response.status_code==code,(response.status_code,response.text)
        oh={'X-CSRF-Token':ok(owner.post('/api/login',json={'username':'owner','password':'g2l_owner_opening_test_pass'}))['csrf']}
        for name,role in (('reviewer','reviewer'),('viewer','viewer')):
            ok(owner.post('/api/users',headers=oh,json={'username':name,'role':role,'password':'opening_test_password_long'}))
        rh={'X-CSRF-Token':ok(reviewer.post('/api/login',json={'username':'reviewer','password':'opening_test_password_long'}))['csrf']}
        ok(viewer.post('/api/login',json={'username':'viewer','password':'opening_test_password_long'}))
        funds=ok(owner.get('/api/funds'))
        bank=next(x['id'] for x in funds if x['kind']=='bank')
        cash=next(x['id'] for x in funds if x['kind']=='cash')
        ok(owner.post(f'/api/funds/{bank}/opening',headers=oh,json={'amount':'1500.00'}))
        before=ok(owner.get('/api/accounting/treasury-reconciliation',params={'period':'2026-08'}))
        assert not before['matched'] and any(x['type']=='opening_unverified' for x in before['issues']),before
        assert not ok(owner.get('/api/periods/preflight',params={'period':'2026-08'}))['ready']
        assert ok(owner.get('/api/accounting/opening-reviews',params={'period':'2026-08'}))['unverified_count']==1
        opening=ok(owner.get('/api/accounting/opening-reviews'))
        offset=next(x['id'] for x in opening['offset_accounts'] if x['code']=='3100')
        body={'effective_date':'2026-08-01','evidence_kind':'bank_statement',
              'evidence_reference':'BANK-OPEN-TEST-2026-08',
              'evidence_note':'Signed synthetic bank opening statement and reference',
              'offset_account_id':offset}
        deny(owner.post(f'/api/funds/{bank}/opening-review',headers=oh,json={**body,'evidence_kind':'cash_count'}),409)
        deny(owner.post(f'/api/funds/{bank}/opening-review',headers=oh,json={**body,'offset_account_id':-1}),409)
        item=ok(owner.post(f'/api/funds/{bank}/opening-review',headers=oh,json=body))
        assert item['status']=='pending'
        item_id=item['id']
        deny(owner.post(f'/api/funds/{bank}/opening-review',headers=oh,json=body),409)
        deny(owner.post(f'/api/funds/{bank}/opening',headers=oh,json={'amount':'5000'}),409)
        deny(owner.post(f'/api/accounting/opening-reviews/{item_id}/decision',headers=oh,
                        json={'decision':'approve','note':'Owner cannot self-approve'}),403)
        deny(reviewer.post(f'/api/accounting/opening-reviews/{item_id}/decision',headers=rh,
                        json={'decision':'approve','note':'No fund approval grant'}),403)
        review_id=next(x['id'] for x in ok(owner.get('/api/users')) if x['username']=='reviewer')
        ok(owner.post('/api/fund-access',headers=oh,json={'user_id':review_id,'fund_id':bank,
            'can_approve':True,'reason':'Independent opening statement signoff test'}))
        posted=ok(reviewer.post(f'/api/accounting/opening-reviews/{item_id}/decision',headers=rh,
                    json={'decision':'approve','note':'Independent physical bank statement verification'}))
        assert posted['journal_id'] and posted['status']=='approved'
        deny(reviewer.post(f'/api/accounting/opening-reviews/{item_id}/decision',headers=rh,
                    json={'decision':'approve','note':'Second duplicate approval'}),409)
        deny(owner.post(f'/api/funds/{bank}/opening',headers=oh,json={'amount':'2000'}),409)
        with connect() as c:
            review=c.execute('SELECT * FROM fund_opening_reviews WHERE id=?',(item_id,)).fetchone()
            assert review['created_by']!=review['reviewed_by']
            j=c.execute('SELECT * FROM gl_journals WHERE id=?',(posted['journal_id'],)).fetchone()
            assert j['status']=='posted' and j['entry_date']=='2026-08-01'
            lines=c.execute('SELECT account_id,debit_piasters,credit_piasters FROM gl_lines WHERE journal_id=?',(j['id'],)).fetchall()
            f_acc=ledger.ensure_fund_account(c,bank)
            assert len(lines)==2
            assert any(x['account_id']==f_acc and x['debit_piasters']==150000 for x in lines)
            assert any(x['account_id']==offset and x['credit_piasters']==150000 for x in lines)
            assert c.execute('SELECT opening_piasters FROM funds WHERE id=?',(bank,)).fetchone()[0]==150000
            report=treasury_reconciliation(c,'2026-08')
            assert report['matched'] and report['issue_count']==0,report
            assert next(x for x in report['funds'] if x['id']==bank)['gl_opening_piasters']==150000
            assert ledger.trial_balance(c,'2026-08')['balanced']
            assert ledger.coverage(c,'2026-08')['unverified_opening_funds']==0
            for sql,args in (
                ('UPDATE funds SET opening_piasters=1 WHERE id=?',(bank,)),
                ('DELETE FROM fund_opening_reviews WHERE id=?',(item_id,)),
                ("UPDATE fund_opening_reviews SET evidence_reference='altered' WHERE id=?",(item_id,)),
                ('DELETE FROM gl_lines WHERE journal_id=?',(j['id'],)),
            ):
                try:c.execute(sql,args)
                except sqlite3.IntegrityError: pass
                else:raise AssertionError('Approved financial evidence can be modified: '+sql)
        # A second fund has a zero opening; no fake debit/credit journal allowed.
        zero={'effective_date':'2026-08-01','evidence_kind':'cash_count',
              'evidence_reference':'COUNT-ZERO-2026-08',
              'evidence_note':'Physically counted zero synthetic cash',
              'offset_account_id':None}
        z=ok(owner.post(f'/api/funds/{cash}/opening-review',headers=oh,json=zero))
        deny(reviewer.post(f'/api/accounting/opening-reviews/{z["id"]}/decision',headers=rh,
                    json={'decision':'approve','note':'No cash reviewer grant'}),403)
        ok(owner.post('/api/fund-access',headers=oh,json={'user_id':review_id,'fund_id':cash,
            'can_approve':True,'reason':'Independent physical cash count opening verification'}))
        zdone=ok(reviewer.post(f'/api/accounting/opening-reviews/{z["id"]}/decision',headers=rh,
                    json={'decision':'approve','note':'Physically confirmed no opening cash'}))
        assert zdone['journal_id'] is None
        # A rejected review permits a new submission, preserving the rejected history.
        wallet=next(x['id'] for x in funds if x['kind']=='wallet')
        w=ok(owner.post(f'/api/funds/{wallet}/opening-review',headers=oh,json={
            **zero,'evidence_kind':'wallet_statement','evidence_reference':'WALLET-ZERO-2026-08'}))
        ok(owner.post('/api/fund-access',headers=oh,json={'user_id':review_id,'fund_id':wallet,
            'can_approve':True,'reason':'Independent wallet statement opening verification'}))
        ok(reviewer.post(f'/api/accounting/opening-reviews/{w["id"]}/decision',headers=rh,
             json={'decision':'reject','note':'No supporting wallet statement provided'}))
        with connect() as c:
            try:
                c.execute("UPDATE fund_opening_reviews SET evidence_note='tampered' WHERE id=?",(w['id'],))
            except sqlite3.IntegrityError:
                pass
            else:
                raise AssertionError('Rejected opening record can be rewritten')
        ok(owner.post(f'/api/funds/{wallet}/opening-review',headers=oh,json={
            **zero,'evidence_kind':'wallet_statement','evidence_reference':'WALLET-ZERO-2026-08'}))
        # Time-of-check/time-of-use: the cashier books a backdated movement
        # AFTER proposal. The reviewer must not certify an opening later than it.
        new_fund=ok(owner.post('/api/funds',headers=oh,json={
            'code':'bank_late_synth','name':'Isolated delayed bank','kind':'bank','restricted_cash':False}))
        late_bank=new_fund['id']
        ok(owner.post(f'/api/funds/{late_bank}/opening',headers=oh,json={'amount':'100'}))
        late_review=ok(owner.post(f'/api/funds/{late_bank}/opening-review',headers=oh,json={
            **body,'evidence_reference':'BANK-LATE-OPEN-2026-08'}))
        ok(owner.post('/api/fund-access',headers=oh,json={'user_id':review_id,
            'fund_id':late_bank,'can_approve':True,'reason':'Independent synthetic late movement testing'}))
        lookup=ok(owner.get('/api/lookups'))
        category=next(x['id'] for x in lookup['categories'] if x['code']=='other_revenue')
        voucher=ok(owner.post('/api/vouchers',headers=oh,json={
            'date':'2026-07-10','kind':'receipt','department_id':lookup['departments'][0]['id'],
            'category_id':category,'shift':'central','from_fund_id':late_bank,
            'amount':'10','description':'Backdated voucher after opening proposal'}))
        ok(reviewer.post(f'/api/vouchers/{voucher["id"]}/decision',headers=rh,
             json={'decision':'approve','reason':'Independent synthetic voucher approval'}))
        deny(reviewer.post(f'/api/accounting/opening-reviews/{late_review["id"]}/decision',headers=rh,
                    json={'decision':'approve','note':'Cannot approve opening after older voucher'}),409)
        # Lower-level financial import modules must also be unable to insert
        # dated cash legs before an already approved opening.
        with connect() as c:
            try:
                c.execute('''INSERT INTO fund_movements(voucher_id,fund_id,amount_piasters,booked_on)
                    VALUES (?,?,?,?)''',(voucher['id'],bank,1000,'2026-07-10'))
            except sqlite3.IntegrityError:
                pass
            else:
                raise AssertionError('Fund movement before signed opening was accepted')
        assert viewer.get('/api/accounting/opening-reviews').status_code==200
        assert owner.get('/api/accounting/treasury-reconciliation.csv',params={'period':'2026-08'}).status_code==200
        with connect() as c:
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
        print('PASS G2L independent openings: posted GL, cashbook unchanged, no self-approval, no retry/DB tampering, rejection and zero case')


if __name__=='__main__':run()
