"""Physical cash handover vs accounting finalization; all data synthetic."""
import os,sys,tempfile
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def run():
    with tempfile.TemporaryDirectory() as temp:
        os.environ['RAMSES_DB_PATH']=str(Path(temp)/'hospital.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='owner_long_password_2026'
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner,first,second,reviewer,auditor=(TestClient(app) for i in range(5))
        def login(client,name,pw):
            r=client.post('/api/login',json={'username':name,'password':pw})
            assert r.status_code==200,r.text
            return {'X-CSRF-Token':r.json()['csrf']}
        oh=login(owner,'owner','owner_long_password_2026')
        for name,role in [('first','clerk'),('second','clerk'),('reviewer','reviewer'),('auditor','reviewer')]:
            r=owner.post('/api/users',headers=oh,json={'username':name,'password':'staff_long_password_2026','role':role})
            assert r.status_code==200,r.text
        ah=login(first,'first','staff_long_password_2026')
        bh=login(second,'second','staff_long_password_2026')
        rh=login(reviewer,'reviewer','staff_long_password_2026')
        vh=login(auditor,'auditor','staff_long_password_2026')
        ids={x['username']:x['id'] for x in owner.get('/api/users').json()}
        points=owner.get('/api/cashier/plans').json()['points']
        ext=next(x for x in points if x['kind']=='external')
        fund=next(x['id'] for x in owner.get('/api/funds').json() if x['code']=='cash_sub')
        assert owner.post(f'/api/billing/points/{ext["id"]}/cash-fund',headers=oh,json={'fund_id':fund}).status_code==200
        for username in ('first','second'):
            r=owner.post(f'/api/billing/points/{ext["id"]}/assign',headers=oh,json={'user_id':ids[username]})
            assert r.status_code==200,r.text
        assert owner.post(f'/api/funds/{fund}/opening',headers=oh,json={'amount':'1000'}).status_code==200
        day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        r=first.post('/api/shifts/open',headers=ah,json={'fund_id':fund,'business_date':day,'shift':'morning'})
        assert r.status_code==200,r.text
        sid=r.json()['id']
        counted=first.post(f'/api/shifts/{sid}/count',headers=ah,json={'counted_amount':'990','note':'نقص عشرة جنيهات تحت التحقيق'})
        assert counted.status_code==200 and counted.json()['variance_piasters']==-1000,counted.text
        # A second person's verified receipt allows the next worker to start.
        accepted=second.post(f'/api/shifts/{sid}/handoff',headers=bh,json={'decision':'accept','counted_amount':'990','note':'تم استلام النقد الفعلي فقط'})
        assert accepted.status_code==200,accepted.text
        r=second.post('/api/shifts/open',headers=bh,json={'fund_id':fund,'business_date':day,'shift':'evening'})
        assert r.status_code==200,r.text
        next_sid=r.json()['id']
        with connect() as c:
            assert c.execute('SELECT opening_piasters FROM shift_sessions WHERE id=?',(next_sid,)).fetchone()[0]==99000
            # Source shift not marked financially complete by receiving the notes.
            assert c.execute('SELECT status FROM shift_sessions WHERE id=?',(sid,)).fetchone()[0]=='submitted'
        policy=owner.get('/api/cashier/variance-permissions')
        assert policy.status_code==200 and all(not x['can_approve'] for x in policy.json())
        assert reviewer.post(f'/api/shifts/{sid}/variance-decision',headers=rh,
               json={'decision':'approve','reason':'هذا القرار غير مصرح له'}).status_code==403
        allowed=owner.post('/api/cashier/variance-permissions',headers=oh,json={
            'user_id':ids['auditor'],'can_approve':True,'reason':'تفويض مراجعة مستقل لتسويات العهدة'})
        assert allowed.status_code==200,allowed.text
        assert auditor.get('/api/cashier/variance-permissions').status_code==403
        pr=reviewer.post(f'/api/shifts/{sid}/variance-propose',headers=rh,
            json={'explanation':'تم التأكد من عجز عشرة جنيهات حسب المحضر والجرد المستقل'})
        assert pr.status_code==200,pr.text
        # The investigator cannot approve their own investigation, even if delegated.
        assert owner.post('/api/cashier/variance-permissions',headers=oh,json={
            'user_id':ids['reviewer'],'can_approve':True,'reason':'تجربة فصل التحقيق عن الاعتماد'}).status_code==200
        forbidden=reviewer.post(f'/api/shifts/{sid}/variance-decision',headers=rh,
            json={'decision':'approve','reason':'اختبار عدم الاعتماد الذاتي'})
        assert forbidden.status_code==403,forbidden.text
        approved=auditor.post(f'/api/shifts/{sid}/variance-decision',headers=vh,
            json={'decision':'approve','reason':'موافقة مستقلة بعجز مؤقت تحت التحقيق'})
        assert approved.status_code==200,approved.text
        assert approved.json()['status']=='closed'
        with connect() as c:
            prev=c.execute('SELECT * FROM shift_sessions WHERE id=?',(sid,)).fetchone()
            newer=c.execute('SELECT * FROM shift_sessions WHERE id=?',(next_sid,)).fetchone()
            assert prev['variance_piasters']==-1000 and prev['status']=='closed'
            assert newer['opening_piasters']==99000 and newer['status']=='open'
            money=c.execute('SELECT opening_piasters+(SELECT COALESCE(SUM(amount_piasters),0) FROM fund_movements WHERE fund_id=?) FROM funds WHERE id=?',(fund,fund)).fetchone()[0]
            assert money==99000,money
            history=c.execute('SELECT event,count_version FROM cashier_count_history WHERE shift_session_id=?',(sid,)).fetchall()
            assert [(x['event'],x['count_version']) for x in history]==[('submit',1)]
            journals=c.execute('SELECT COUNT(*) FROM gl_journals WHERE origin=\'voucher\'').fetchone()[0]
            assert journals==1,journals
        repeat=auditor.post(f'/api/shifts/{sid}/variance-decision',headers=vh,
            json={'decision':'approve','reason':'تكرار اعتماد ممنوع'})
        assert repeat.status_code==409,repeat.text
        revoke=owner.post('/api/cashier/variance-permissions',headers=oh,json={
            'user_id':ids['auditor'],'can_approve':False,'reason':'انتهت فترة التفويض الخاصة بالمراجعة'})
        assert revoke.status_code==200,revoke.text
        print('PASS P3: provisional cash accepted independently, next shift runs physically counted, shortage adjusted once, history immutable, owner grants/revokes, no self-approval')
if __name__=='__main__':run()
