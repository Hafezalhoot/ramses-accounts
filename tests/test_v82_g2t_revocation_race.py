"""Revocation during a pending inventory review must win before posting any GL."""
import os,sys,tempfile
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def run():
 with tempfile.TemporaryDirectory() as tmp:
  os.environ.update(RAMSES_DB_PATH=str(Path(tmp)/'revoke.sqlite'),RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='synthetic_inventory_owner_password')
  from bootstrap import initialize,connect
  initialize()
  from app import app
  import inventory
  from fastapi.testclient import TestClient
  owner,clerk,checker=(TestClient(app) for _ in range(3))
  def ok(resp):
   assert resp.status_code==200,(resp.status_code,resp.text)
   return resp.json()
  oh={'X-CSRF-Token':ok(owner.post('/api/login',json={'username':'owner','password':'synthetic_inventory_owner_password'}))['csrf']}
  for name,role in (('stock_prepare','clerk'),('stock_check','reviewer')):
   ok(owner.post('/api/users',headers=oh,json={'username':name,'role':role,'password':'synthetic_worker_password_2026'}))
  ch={'X-CSRF-Token':ok(clerk.post('/api/login',json={'username':'stock_prepare','password':'synthetic_worker_password_2026'}))['csrf']}
  rh={'X-CSRF-Token':ok(checker.post('/api/login',json={'username':'stock_check','password':'synthetic_worker_password_2026'}))['csrf']}
  ids={x['username']:x['id'] for x in ok(owner.get('/api/users'))}
  ok(owner.post('/api/inventory/access',headers=oh,json={'user_id':ids['stock_prepare'],'can_prepare':True,'reason':'Synthetic prepare grant'}))
  ok(owner.post('/api/inventory/access',headers=oh,json={'user_id':ids['stock_check'],'can_approve':True,'reason':'Synthetic checker grant'}))
  vendor=ok(owner.post('/api/inventory/vendors',headers=oh,json={'code':'REVOC_V','name':'Synthetic revocation vendor'}))['id']
  item=ok(owner.post('/api/inventory/items',headers=oh,json={'code':'REVOC_I','name':'Synthetic revocation item'}))['id']
  day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
  rid=ok(clerk.post('/api/inventory/receipts',headers=ch,json={'vendor_id':vendor,'received_on':day,'invoice_ref':'REVOC-INVOICE-00001','evidence_ref':'REVOC-WAREHOUSE-GRN-001','request_id':'g2t_revoke_receipt_0001','lines':[{'item_id':item,'quantity':1,'unit_cost':'11.00'}]}))['id']
  original=inventory.permission
  first=[True]
  def revoke_in_flight(c,user,ability='read'):
   original(c,user,ability)
   if ability=='approve' and first[0]:
    first[0]=False
    c.execute('UPDATE inventory_access SET can_approve=0 WHERE user_id=?',(user['id'],))
    c.commit()
  with patch.object(inventory,'permission',side_effect=revoke_in_flight):
   decision=checker.post(f'/api/inventory/receipts/{rid}/decision',headers=rh,json={'decision':'approve','note':'Synthetic revoked between authorization and commit'})
  assert decision.status_code==403,(decision.status_code,decision.text)
  with connect() as c:
   assert c.execute('SELECT status,journal_id FROM inventory_receipts WHERE id=?',(rid,)).fetchone()['status']=='pending'
   assert c.execute('SELECT COUNT(*) FROM gl_journals WHERE memo LIKE "INV:%"').fetchone()[0]==0
  print('PASS G2T revoked grant cannot authorize in-flight financial approval')

if __name__=='__main__':run()
