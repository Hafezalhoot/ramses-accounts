"""Two concurrent reviewers may never double-post the same fund opening."""
import os
import sys
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def run():
    with tempfile.TemporaryDirectory() as d:
        os.environ['RAMSES_DB_PATH']=str(Path(d)/'race.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='opening_concurrency_owner_pass'
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner=TestClient(app)
        def login(client,username,pwd):
            r=client.post('/api/login',json={'username':username,'password':pwd})
            assert r.status_code==200,r.text
            return {'X-CSRF-Token':r.json()['csrf']}
        oh=login(owner,'owner','opening_concurrency_owner_pass')
        reviewers=[]
        for name in ('reviewer_a','reviewer_b'):
            r=owner.post('/api/users',headers=oh,json={'username':name,'role':'reviewer',
                         'password':'concurrent_opening_test_password'})
            assert r.status_code==200,r.text
            cli=TestClient(app)
            headers=login(cli,name,'concurrent_opening_test_password')
            reviewers.append((cli,headers))
        bank=next(x['id'] for x in owner.get('/api/funds').json() if x['kind']=='bank')
        for user in owner.get('/api/users').json():
            if user['username'].startswith('reviewer_'):
                r=owner.post('/api/fund-access',headers=oh,json={
                    'user_id':user['id'],'fund_id':bank,'can_approve':True,
                    'reason':'Two-person race test isolated database only'})
                assert r.status_code==200,r.text
        r=owner.post(f'/api/funds/{bank}/opening',headers=oh,json={'amount':'250'})
        assert r.status_code==200,r.text
        offset=next(x['id'] for x in owner.get('/api/accounting/opening-reviews').json()['offset_accounts'] if x['code']=='3100')
        submitted=owner.post(f'/api/funds/{bank}/opening-review',headers=oh,json={
            'effective_date':'2026-08-01','evidence_kind':'bank_statement',
            'evidence_reference':'RACE-TEST-SYNTH-2026',
            'evidence_note':'Synthetic bank statement for concurrent review',
            'offset_account_id':offset})
        assert submitted.status_code==200,submitted.text
        rid=submitted.json()['id']
        def decide(pair):
            cli,headers=pair
            return cli.post(f'/api/accounting/opening-reviews/{rid}/decision',headers=headers,
                            json={'decision':'approve','note':'Independent synthetic bank statement review'})
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(decide,reviewers))
        codes=sorted(r.status_code for r in responses)
        assert codes==[200,409],[(r.status_code,r.text) for r in responses]
        with connect() as c:
            assert c.execute("SELECT COUNT(*) FROM fund_opening_reviews WHERE fund_id=? AND status='approved'",(bank,)).fetchone()[0]==1
            journal=c.execute('SELECT journal_id FROM fund_opening_reviews WHERE id=?',(rid,)).fetchone()[0]
            assert c.execute('SELECT COUNT(*) FROM gl_lines WHERE journal_id=?',(journal,)).fetchone()[0]==2
            assert c.execute('SELECT COUNT(*) FROM gl_journals WHERE id=? AND status=?',(journal,'posted')).fetchone()[0]==1
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        print('PASS G2L concurrent opening: one signed journal, second approval rejected, no duplicate GL')

if __name__=='__main__':run()
