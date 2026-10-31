"""End-to-end account disable/reactivate/password rotation security regression."""
import os
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as d:
        os.environ['RAMSES_DB_PATH']=str(Path(d)/'test.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='initial_very_long_password_1'
        os.environ.pop('GOOGLE_SHEET_ID',None)
        os.environ.pop('GOOGLE_SERVICE_ACCOUNT_JSON',None)
        from bootstrap import initialize, connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner=TestClient(app); staff=TestClient(app); reviewer=TestClient(app)
        def login(client,name,password):
            r=client.post('/api/login',json={'username':name,'password':password})
            assert r.status_code==200,r.text
            return {'X-CSRF-Token':r.json()['csrf']}
        oh=login(owner,'owner','initial_very_long_password_1')
        created=owner.post('/api/users',headers=oh,json={'username':'clerkstaff','role':'clerk','password':'long_clerk_password_1'})
        assert created.status_code==200,created.text
        staff_id=created.json()['id']
        ch=login(staff,'clerkstaff','long_clerk_password_1')
        assert staff.get('/api/me').status_code==200
        assert owner.post('/api/users/1/status',headers=oh,json={'active':False}).status_code==403
        assert staff.post(f'/api/users/{staff_id}/status',headers=ch,json={'active':False}).status_code==403
        disabled=owner.post(f'/api/users/{staff_id}/status',headers=oh,json={'active':False})
        assert disabled.status_code==200,disabled.text
        assert staff.get('/api/me').status_code==401
        assert staff.post('/api/login',json={'username':'clerkstaff','password':'long_clerk_password_1'}).status_code==401
        assert owner.post(f'/api/users/{staff_id}/status',headers=oh,json={'active':True}).status_code==200
        ch=login(staff,'clerkstaff','long_clerk_password_1')
        assert owner.post(f'/api/users/{staff_id}/password',headers=oh,json={'password':'short'}).status_code==400
        assert owner.post(f'/api/users/{staff_id}/password',headers=oh,json={'password':'new_long_clerk_password_2'}).status_code==403
        assert owner.post(f'/api/users/{staff_id}/password',headers=oh,json={
            'password':'new_long_clerk_password_2','current_password':'initial_very_long_password_1'}).status_code==200
        assert staff.get('/api/me').status_code==401
        assert staff.post('/api/login',json={'username':'clerkstaff','password':'long_clerk_password_1'}).status_code==401
        ch=login(staff,'clerkstaff','new_long_clerk_password_2')
        # Owner must prove knowledge of the existing password to rotate their own.
        assert owner.post('/api/users/1/password',headers=oh,json={'password':'replacement_owner_password_1'}).status_code==403
        assert owner.get('/api/me').status_code==200
        ok=owner.post('/api/users/1/password',headers=oh,json={'password':'replacement_owner_password_1','current_password':'initial_very_long_password_1'})
        assert ok.status_code==200,ok.text
        assert owner.get('/api/me').status_code==401
        oh=login(owner,'owner','replacement_owner_password_1')
        with connect() as c:
            actions=[r[0] for r in c.execute("SELECT action FROM audit_log WHERE entity='user'")]
            assert all(x in actions for x in ['disable_user','activate_user','reset_user_password']),actions
        print('PASS - account disable/reactivate, session revocation, password reset and owner confirmation')


if __name__=='__main__':run()
