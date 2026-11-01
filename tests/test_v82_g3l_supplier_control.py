"""G3L: 2200 cannot be assigned to a vendor without immutable source evidence."""
import os
import sys
import tempfile
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory(prefix='ramses-g3l-control-') as td:
        os.environ.update(RAMSES_DB_PATH=str(Path(td)/'synthetic.sqlite3'),
            RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='g3l-synthetic-owner-secret')
        for key in ('GOOGLE_SHEET_ID','GOOGLE_SERVICE_ACCOUNT_JSON','GOOGLE_SHEET_TARGET'):
            os.environ.pop(key,None)
        from bootstrap import connect,initialize
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        with TestClient(app) as client:
            login=client.post('/api/login',json={'username':'owner','password':'g3l-synthetic-owner-secret'})
            assert login.status_code==200,login.text
            auth={'X-CSRF-Token':login.json()['csrf']}
            day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
            r=client.get('/api/inventory/supplier-control-ledger',params={'as_of':day})
            assert r.status_code==200,r.text
            assert r.json()['control_2200_piasters']==0 and r.json()['reconciled'],r.text
            future=(datetime.now(ZoneInfo('Africa/Cairo')).date()+timedelta(days=1)).isoformat()
            assert client.get('/api/inventory/supplier-control-ledger',params={'as_of':future}).status_code==409
            assert client.get('/api/inventory/supplier-control-ledger',params={'as_of':'2026-02-30'}).status_code==400
            # Unrelated manual 2200 journal posts into the GL but cannot be
            # assigned to any supplier without receipt/voucher source linkage.
            with connect() as c:
                import ledger
                jid=ledger._journal(c,entry_date=day,memo='Synthetic AP source unknown',
                  origin='manual',source_id=None,created_by=1,reviewed_by=1,
                  lines=[(ledger.account_by_code(c,'1100'),1234,0,None),
                         (ledger.account_by_code(c,'2200'),0,1234,None)])
            report=client.get('/api/inventory/supplier-control-ledger',params={'as_of':day})
            assert report.status_code==200,report.text
            payload=report.json()
            assert payload['control_2200_piasters']==1234,payload
            assert payload['attributed_2200_piasters']==0 and payload['unattributed_2200_piasters']==1234,payload
            assert payload['vendors']==[] and not payload['reconciled'],payload
            assert payload['unattributed_journals'][0]['journal_id']==jid,payload
            client.post('/api/users',headers=auth,json={
                'username':'g3l_other_user','password':'g3l-synthetic-other-secret','role':'clerk'})
        with TestClient(app) as another:
            login2=another.post('/api/login',json={'username':'g3l_other_user','password':'g3l-synthetic-other-secret'})
            assert login2.status_code==200
            assert another.get('/api/inventory/supplier-control-ledger').status_code==403
            assert another.get('/api/inventory/overview').status_code==403
        print('PASS G3L source-attributed AP 2200, unexplained posted GL, as-of date and live access restriction')

if __name__=='__main__':run()
