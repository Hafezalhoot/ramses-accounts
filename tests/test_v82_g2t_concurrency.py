"""G2T concurrent independent reviews of same receipt and last warehouse unit."""
import os,sys,tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def run():
 with tempfile.TemporaryDirectory() as td:
  os.environ.update(RAMSES_DB_PATH=str(Path(td)/'concurrent.sqlite'),
                    RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='g2t_concurrent_owner_password')
  os.environ.pop('GOOGLE_SHEET_ID',None)
  from bootstrap import initialize,connect
  initialize()
  from app import app
  from fastapi.testclient import TestClient
  day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
  owner,clerk,r1,r2=[TestClient(app) for _ in range(4)]
  def ok(r):
   assert r.status_code==200,(r.status_code,r.text)
   return r.json()
  oh={'X-CSRF-Token':ok(owner.post('/api/login',json={'username':'owner','password':'g2t_concurrent_owner_password'}))['csrf']}
  for name,role in [('inv_clerk','clerk'),('inv_reviewer_one','reviewer'),('inv_reviewer_two','reviewer')]:
   ok(owner.post('/api/users',headers=oh,json={'username':name,'role':role,'password':'synthetic_test_password_2026'}))
  ch={'X-CSRF-Token':ok(clerk.post('/api/login',json={'username':'inv_clerk','password':'synthetic_test_password_2026'}))['csrf']}
  h1={'X-CSRF-Token':ok(r1.post('/api/login',json={'username':'inv_reviewer_one','password':'synthetic_test_password_2026'}))['csrf']}
  h2={'X-CSRF-Token':ok(r2.post('/api/login',json={'username':'inv_reviewer_two','password':'synthetic_test_password_2026'}))['csrf']}
  ids={r['username']:r['id'] for r in ok(owner.get('/api/users'))}
  for name in ('inv_clerk','inv_reviewer_one','inv_reviewer_two'):
   ok(owner.post('/api/inventory/access',headers=oh,json={'user_id':ids[name],
       'can_prepare':name=='inv_clerk','can_approve':name!='inv_clerk','reason':'Synthetic concurrent inventory reviewer'}))
  vendor=ok(owner.post('/api/inventory/vendors',headers=oh,json={'code':'G2T_CC_VENDOR','name':'Synthetic concurrent supplier'}))['id']
  item=ok(owner.post('/api/inventory/items',headers=oh,json={'code':'G2T_CC_ITEM','name':'Synthetic one-unit consumable'}))['id']
  receipt=ok(clerk.post('/api/inventory/receipts',headers=ch,json={'vendor_id':vendor,'received_on':day,
     'invoice_ref':'SYNTHETIC-CONCURRENT-001','evidence_ref':'SYNTHETIC-GRN-CONCURRENT-001',
     'request_id':'g2t_cc_receipt_0001','lines':[{'item_id':item,'quantity':1,'unit_cost':'17.00'}]}))['id']
  def review(client,header,url):
   return client.post(url,headers=header,json={'decision':'approve','note':'Independent synthetic concurrent review'}).status_code
  with ThreadPoolExecutor(max_workers=2) as ex:
   a=ex.submit(review,r1,h1,f'/api/inventory/receipts/{receipt}/decision')
   b=ex.submit(review,r2,h2,f'/api/inventory/receipts/{receipt}/decision')
   assert sorted([a.result(),b.result()])==[200,409]
  dept=next(x['id'] for x in ok(owner.get('/api/lookups'))['departments'] if x['code']=='IPD')
  issues=[]
  for n in range(2):
   issues.append(ok(clerk.post('/api/inventory/issues',headers=ch,json={
      'department_id':dept,'used_on':day,'evidence_ref':f'SYNTHETIC-ISSUE-NOTE-{n+1}',
      'request_id':f'g2t_cc_issue_00000{n+1}','lines':[{'item_id':item,'quantity':1}]}))['id'])
  with ThreadPoolExecutor(max_workers=2) as ex:
   a=ex.submit(review,r1,h1,f'/api/inventory/issues/{issues[0]}/decision')
   b=ex.submit(review,r2,h2,f'/api/inventory/issues/{issues[1]}/decision')
   assert sorted([a.result(),b.result()])==[200,409]
  with connect() as c:
   assert c.execute("SELECT COUNT(*) FROM inventory_receipts WHERE status='approved'").fetchone()[0]==1
   assert c.execute("SELECT COUNT(*) FROM inventory_issues WHERE status='approved'").fetchone()[0]==1
   assert c.execute('SELECT COALESCE(SUM(quantity),0) FROM inventory_issue_allocations').fetchone()[0]==1
   assert c.execute("SELECT COUNT(*) FROM gl_journals WHERE memo LIKE 'INV:%'").fetchone()[0]==2
  assert ok(owner.get('/api/inventory/overview'))['items'][0]['quantity_on_hand']==0
  print('PASS G2T concurrent review of receipt and last unit: exactly one receipt and one issue GL')

if __name__=='__main__':run()
