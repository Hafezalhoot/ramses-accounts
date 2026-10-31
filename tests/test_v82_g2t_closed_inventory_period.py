"""G2T SQL boundary: a direct status flip cannot bypass sealed month."""
import os,sys,tempfile,sqlite3
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def run():
 with tempfile.TemporaryDirectory() as td:
  os.environ.update(RAMSES_DB_PATH=str(Path(td)/'month.sqlite'),RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='g2t_month_owner_password')
  from bootstrap import initialize,connect
  initialize()
  from app import app
  from fastapi.testclient import TestClient
  day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
  owner,reviewer=TestClient(app),TestClient(app)
  def ok(r):
   assert r.status_code==200,(r.status_code,r.text)
   return r.json()
  oh={'X-CSRF-Token':ok(owner.post('/api/login',json={'username':'owner','password':'g2t_month_owner_password'}))['csrf']}
  ok(owner.post('/api/users',headers=oh,json={'username':'synthetic_inv_auditor','role':'reviewer','password':'synthetic_review_password_2026'}))
  rh={'X-CSRF-Token':ok(reviewer.post('/api/login',json={'username':'synthetic_inv_auditor','password':'synthetic_review_password_2026'}))['csrf']}
  uid=next(u['id'] for u in ok(owner.get('/api/users')) if u['username']=='synthetic_inv_auditor')
  ok(owner.post('/api/inventory/access',headers=oh,json={'user_id':uid,'can_approve':True,'reason':'Synthetic period close signoff'}))
  vendor=ok(owner.post('/api/inventory/vendors',headers=oh,json={'code':'MONTH_V','name':'Month close supplier'}))['id']
  item=ok(owner.post('/api/inventory/items',headers=oh,json={'code':'MONTH_I','name':'Month close consumable'}))['id']
  rid=ok(owner.post('/api/inventory/receipts',headers=oh,json={'vendor_id':vendor,'received_on':day,'invoice_ref':'MONTH-INVOICE-2026-1',
   'evidence_ref':'MONTH-GRN-2026-1','request_id':'g2t_month_receipt_001','lines':[{'item_id':item,'quantity':2,'unit_cost':'3.00'}]}))['id']
  with connect() as c:
   c.execute('INSERT INTO periods(period,closed_by,closed_at) VALUES(?,?,?)',(day[:7],1,day))
   c.commit()
   try:c.execute('UPDATE inventory_receipts SET status="rejected" WHERE id=?',(rid,))
   except sqlite3.IntegrityError:c.rollback()
   else:raise AssertionError('Direct SQL changed receipt decision inside a sealed accounting period')
  denied=reviewer.post(f'/api/inventory/receipts/{rid}/decision',headers=rh,json={'decision':'approve','note':'Review after period closure'})
  assert denied.status_code==409,(denied.status_code,denied.text)
  with connect() as c:
   assert c.execute('SELECT status FROM inventory_receipts WHERE id=?',(rid,)).fetchone()[0]=='pending'
   assert c.execute('SELECT COUNT(*) FROM gl_journals WHERE memo LIKE "INV:%"').fetchone()[0]==0
  print('PASS G2T SQL plus API sealed-month inventory review rejection')

if __name__=='__main__':run()
