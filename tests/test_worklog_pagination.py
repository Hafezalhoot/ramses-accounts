"""Large timesheet months must not hide pending shifts behind a fixed 1000-row limit."""
import os
import sys
import tempfile
from datetime import date,timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def run():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ.update(RAMSES_DB_PATH=str(Path(tmp)/'hours.sqlite3'),
          RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='test_owner_very_long_password')
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        o=TestClient(app)
        lg=o.post('/api/login',json={'username':'owner','password':'test_owner_very_long_password'})
        assert lg.status_code==200
        csrf={'X-CSRF-Token':lg.json()['csrf']}
        eid=o.post('/api/employees',headers=csrf,json={'name':'موظف ساعات اختبار','code':'H61'}).json()['id']
        r=o.post(f'/api/employees/{eid}/salary-term',headers=csrf,
          json={'pay_type':'hourly','month':'2026-10','hourly_rate':'50'})
        assert r.status_code==200,r.text
        shifts=('morning','evening')
        for i in range(62):
            d=(date(2026,10,1)+timedelta(days=i//2)).isoformat()
            r=o.post('/api/payroll/work-entries',headers=csrf,json={'employee_id':eid,'work_date':d,
              'shift':shifts[i%2],'hours':3,'minutes':0,'note':'ساعات دوام للتجربة'})
            assert r.status_code==200,(i,r.status_code,r.text)
        r=o.get('/api/payroll/work-entries?period=2026-10&page=1')
        assert r.status_code==200
        d=r.json();assert d['total']==62 and d['pages']==2 and d['pending_count']==62 and len(d['items'])==60
        q=o.get('/api/payroll/work-entries?period=2026-10&page=2').json()
        assert q['total']==62 and q['pending_count']==62 and len(q['items'])==2
        assert o.get('/api/payroll/work-entries?period=2026-10&page=0').status_code==400
        assert o.post('/api/payroll/accrual',headers=csrf,json={'employee_id':eid,'period':'2026-10'}).status_code==409
        print('PASS — 62 genuine work entries, 60/2 pages, pending count not clipped, accrual stays blocked')

if __name__=='__main__':run()
