"""A cash fund assigned to a cashier station must always post inside an open shift."""
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as temp:
        os.environ['RAMSES_DB_PATH']=str(Path(temp)/'shift_guard.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='qa_owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='qa_temporary_owner_password_2026'
        os.environ.pop('GOOGLE_SHEET_ID',None)
        os.environ.pop('GOOGLE_SERVICE_ACCOUNT_JSON',None)
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner=TestClient(app)
        reviewer=TestClient(app)

        def login(client,username,password):
            r=client.post('/api/login',json={'username':username,'password':password})
            assert r.status_code==200,r.text
            return {'X-CSRF-Token':r.json()['csrf']}
        oh=login(owner,'qa_owner','qa_temporary_owner_password_2026')
        res=owner.post('/api/users',headers=oh,json={'username':'qa_reviewer','role':'reviewer',
                         'password':'qa_temporary_reviewer_2026'})
        assert res.status_code==200,res.text
        rh=login(reviewer,'qa_reviewer','qa_temporary_reviewer_2026')
        assert owner.post('/api/billing/points/1/cash-fund',headers=oh,json={'fund_id':1}).status_code==200
        today=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        body={'date':today,'kind':'receipt','department_id':1,'category_id':1,
              'from_fund_id':1,'shift':'central','amount':'25.00','description':'QA dummy receipt only',
              'client_request_id':'guard_dummy_cash_12345678'}
        res=owner.post('/api/vouchers',headers=oh,json=body)
        assert res.status_code==409,('Untracked cashier station movement accepted without shift',res.status_code,res.text)

        opened=owner.post('/api/shifts/open',headers=oh,json={'business_date':today,'shift':'morning','fund_id':1})
        assert opened.status_code==200,opened.text
        res=owner.post('/api/vouchers',headers=oh,json=body)
        assert res.status_code==200,res.text
        voucher_id=res.json()['id']
        decision=reviewer.post(f'/api/vouchers/{voucher_id}/decision',headers=rh,json={'decision':'approve'})
        assert decision.status_code==200,decision.text
        with connect() as c:
            mv=c.execute('SELECT shift_session_id FROM fund_movements WHERE voucher_id=?',(voucher_id,)).fetchone()
            assert mv and mv['shift_session_id']==opened.json()['id'],(mv,opened.json())
        print('PASS - mapped cash fund rejects untracked voucher; linked movement accepted only under open shift')

if __name__=='__main__':run()
