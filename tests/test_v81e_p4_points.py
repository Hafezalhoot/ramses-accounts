"""New till is independent, historical fund rebinding is forbidden; synthetic."""
import os,sys,tempfile
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def run():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ['RAMSES_DB_PATH']=str(Path(tmp)/'test.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='long_owner_password_2026'
        from bootstrap import initialize, connect
        initialize()
        from fastapi.testclient import TestClient
        from app import app
        o=TestClient(app);clerk=TestClient(app)
        def login(c,u,p):
            r=c.post('/api/login',json={'username':u,'password':p});assert r.status_code==200,r.text
            return {'X-CSRF-Token':r.json()['csrf']}
        h=login(o,'owner','long_owner_password_2026')
        assert o.post('/api/users',headers=h,json={'username':'worker','password':'long_worker_password_2026','role':'clerk'}).status_code==200
        ch=login(clerk,'worker','long_worker_password_2026')
        new_fund=o.post('/api/funds',headers=h,json={'code':'till_new_4','name':'خزنة نقطة تجريبية جديدة','kind':'cash'})
        assert new_fund.status_code==200,new_fund.text
        fid=new_fund.json()['id']
        data={'code':'SAT_04','name':'نقطة تحصيل تجريبية مستقلة','fund_id':fid,
              'slots':[{'code':'first','name':'وردية اثنتا عشرة ساعة','start':'08:00'},
                       {'code':'second','name':'وردية ثانية','start':'20:00'}],
              'operating_days':[0,1,2,3,4,5,6],'reason':'إضافة نقطة تجريبية لحركة الخزن'}
        assert clerk.post('/api/cashier/points',json=data,headers=ch).status_code==403
        r=o.post('/api/cashier/points',headers=h,json=data)
        assert r.status_code==200,r.text
        assert r.json()['fund_id']==fid
        assert o.post('/api/cashier/points',headers=h,json=data).status_code==409
        assert o.post('/api/cashier/points',headers=h,json={**data,'code':'SAT_05','name':'نقطة أخرى'}).status_code==409
        point_id=r.json()['id'];today=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        plan=o.get('/api/cashier/plans').json()
        new=next(p for p in plan['points'] if p['id']==point_id)
        assert [x['code'] for x in new['versions'][0]['slots']]==['first','second']
        day=o.get('/api/shifts/coverage',params={'month':today[:7]}).json()
        assert any(x['point_id']==point_id and x['business_date']==today for x in day['items'])
        # Once a custody shift exists, rebinding must fail even without a patient collection.
        sh=o.post('/api/shifts/open',headers=h,json={'business_date':today,'fund_id':fid,'shift':'first'})
        assert sh.status_code==200,sh.text
        second_fund=o.post('/api/funds',headers=h,json={'code':'till_new_5','name':'خزنة خامسة أخرى','kind':'cash'})
        assert second_fund.status_code==200,second_fund.text
        moving=o.post(f'/api/billing/points/{point_id}/cash-fund',headers=h,json={'fund_id':second_fund.json()['id']})
        assert moving.status_code==409,moving.text
        with connect() as c:
            assert c.execute('SELECT fund_id FROM billing_points WHERE id=?',(point_id,)).fetchone()[0]==fid
        # Future changes must not delete actual shifts or expected historic slots.
        tomorrow=(datetime.now(ZoneInfo('Africa/Cairo')).date()+timedelta(days=1)).isoformat()
        after=(datetime.now(ZoneInfo('Africa/Cairo')).date()+timedelta(days=2)).isoformat()
        paused=o.post(f'/api/cashier/points/{point_id}/status',headers=h,json={
            'effective_from':tomorrow,'enabled':False,'reason':'إيقاف مؤقت للمراجعة الفنية'})
        assert paused.status_code==200,paused.text
        old=o.get('/api/shifts/coverage',params={'month':today[:7]}).json()
        assert any(x['point_id']==point_id and x['business_date']==today and x['shift']=='second' for x in old['items'])
        with connect() as c:
            import cashier_ops
            assert len(cashier_ops.slots_for(c,point_id,today))==2
            assert not cashier_ops.slots_for(c,point_id,tomorrow)
            assert c.execute('SELECT COUNT(*) FROM shift_sessions WHERE point_id=?',(point_id,)).fetchone()[0]==1
        resumed=o.post(f'/api/cashier/points/{point_id}/status',headers=h,json={
            'effective_from':after,'enabled':True,'reason':'عودة النقطة إلى جدول التشغيل المعتمد'})
        assert resumed.status_code==200,resumed.text
        duplicate=o.post(f'/api/cashier/points/{point_id}/status',headers=h,json={
            'effective_from':after,'enabled':False,'reason':'تاريخ مكرر غير مسموح به'})
        assert duplicate.status_code==409,duplicate.text
        with connect() as c:
            assert len(cashier_ops.slots_for(c,point_id,after))==2
            assert c.execute('SELECT COUNT(*) FROM shift_sessions WHERE point_id=?',(point_id,)).fetchone()[0]==1
        assert clerk.post(f'/api/cashier/points/{point_id}/status',headers=ch,json={
            'effective_from':after,'enabled':False,'reason':'تعديل بدون صلاحية إدارية'}).status_code==403
        # A proposed point without a physical drawer is a draft, not a phantom shift with missing cash.
        draft=o.post('/api/cashier/points',headers=h,json={**data,'code':'SAT_UNBOUND',
                  'name':'نقطة تجريبية بلا درج','fund_id':None,'reason':'تجهيز مستقبل لنقطة تحصيل من دون خزنة'})
        assert draft.status_code==200 and draft.json()['status']=='inactive_until_fund_assigned',draft.text
        draft_id=draft.json()['id']
        planned=o.get('/api/shifts/coverage',params={'month':today[:7]}).json()
        assert not any(x['point_id']==draft_id for x in planned['items'])
        cannot_enable=o.post(f'/api/cashier/points/{draft_id}/status',headers=h,json={
            'effective_from':tomorrow,'enabled':True,'reason':'لا يوجد درج نقدية بعد'})
        assert cannot_enable.status_code==409,cannot_enable.text
        print('PASS P4 points: immutable historical tills; effective pause/resume; unbound drafts produce NO fake missing alerts')

if __name__=='__main__':run()
