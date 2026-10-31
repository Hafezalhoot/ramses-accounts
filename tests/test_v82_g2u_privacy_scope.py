"""G2U: authenticated role is not permission to browse staff, banks or approvals.

All identities and amounts are synthetic. Verification via actual TestClient API.
"""
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def run():
    with tempfile.TemporaryDirectory() as folder:
        os.environ.update(RAMSES_DB_PATH=str(Path(folder)/'scope.sqlite3'),
                          RAMSES_ADMIN_USER='owner',
                          RAMSES_ADMIN_PASSWORD='synthetic_g2u_security_owner_password')
        from bootstrap import initialize
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner,reviewer,viewer=(TestClient(app) for _ in range(3))

        def check(response, code=200):
            assert response.status_code==code,(code,response.status_code,response.text)
            return response.json() if code==200 else None

        def login(client,name,password):
            return {'X-CSRF-Token':check(client.post('/api/login',json={
                'username':name,'password':password}))['csrf']}

        oh=login(owner,'owner','synthetic_g2u_security_owner_password')
        rid=check(owner.post('/api/users',headers=oh,json={
            'username':'scope_reviewer','role':'reviewer',
            'password':'synthetic_reviewer_secret_password'}))['id']
        check(owner.post('/api/users',headers=oh,json={
            'username':'scope_viewer','role':'viewer',
            'password':'synthetic_viewer_secret_password'}))
        login(reviewer,'scope_reviewer','synthetic_reviewer_secret_password')
        login(viewer,'scope_viewer','synthetic_viewer_secret_password')
        check(owner.post('/api/employees',headers=oh,json={
            'name':'Synthetic private employee','code':'G2U_EMP','job_title':'Private role'}))
        assert check(viewer.get('/api/lookups'))['employees']==[]
        check(viewer.get('/api/employees'),403)
        check(owner.get('/api/employees'))
        check(viewer.get('/api/accounting/treasury-reconciliation'),403)
        check(viewer.get('/api/accounting/treasury-reconciliation.csv'),403)
        check(viewer.get('/api/accounting/opening-reviews'),403)
        check(reviewer.get('/api/accounting/treasury-reconciliation'),403)
        assert check(owner.get('/api/accounting/treasury-reconciliation'))['funds']

        bank=check(owner.post('/api/funds',headers=oh,json={
            'code':'g2u_private_bank','name':'Synthetic confidential bank','kind':'bank'}))['id']
        view_funds=check(viewer.get('/api/funds'))
        assert all(not any(field in f for field in (
            'balance_piasters','opening_piasters','movements_piasters')) for f in view_funds),view_funds
        assert bank not in [f['id'] for f in check(reviewer.get('/api/funds'))], 'Ungrant reviewer sees bank metadata'
        lookups=check(owner.get('/api/lookups'))
        dept=next(x['id'] for x in lookups['departments'] if x['code']=='ADMIN')
        cat=next(x['id'] for x in lookups['categories'] if x['code']=='other_revenue')
        voucher=check(owner.post('/api/vouchers',headers=oh,json={
            'date':datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat(),
            'kind':'receipt','shift':'central','from_fund_id':bank,
            'department_id':dept,'category_id':cat,
            'amount':'25','description':'Synthetic bank voucher requiring restricted review'}))['id']
        assert voucher in [v['id'] for v in check(owner.get('/api/reviews'))]
        assert voucher not in [v['id'] for v in check(reviewer.get('/api/reviews'))], 'Ungrant reviewer sees pending bank voucher'
        assert voucher not in [v['id'] for v in check(reviewer.get('/api/vouchers'))['items']], 'List bypasses protected account'
        assert voucher not in [v['id'] for v in check(viewer.get('/api/vouchers'))['items']], 'Viewer exposes protected bank'
        assert 'Synthetic bank voucher requiring restricted review' not in reviewer.get('/api/export/vouchers.csv').text
        check(reviewer.get(f'/api/vouchers/{voucher}/attachments'),403)
        assert check(viewer.get('/api/dashboard'))['pending']==0
        assert check(reviewer.get('/api/dashboard'))['pending']==0

        def grant(allowed):
            return check(owner.post('/api/fund-access',headers=oh,json={
                'user_id':rid,'fund_id':bank,'can_approve':allowed,
                'reason':'Security scope permission test for current session'}))

        grant(True)
        assert bank in [f['id'] for f in check(reviewer.get('/api/funds'))]
        assert voucher in [v['id'] for v in check(reviewer.get('/api/reviews'))]
        assert voucher in [v['id'] for v in check(reviewer.get('/api/vouchers'))['items']]
        check(reviewer.get(f'/api/vouchers/{voucher}/attachments'))
        grant(False)
        assert bank not in [f['id'] for f in check(reviewer.get('/api/funds'))]
        assert voucher not in [v['id'] for v in check(reviewer.get('/api/reviews'))]
        assert voucher not in [v['id'] for v in check(reviewer.get('/api/vouchers'))['items']]
        check(reviewer.get(f'/api/vouchers/{voucher}/attachments'),403)
        print('PASS G2U read scope: staff/private funds/global reports/voucher export/evidence/review queue/instant revoke')

if __name__=='__main__':run()
