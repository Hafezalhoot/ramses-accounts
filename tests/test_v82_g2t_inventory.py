"""G2T test first: actual source-backed supplier inventory and FIFO consumption."""
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def run():
    with tempfile.TemporaryDirectory() as td:
        os.environ.update(RAMSES_DB_PATH=str(Path(td)/'inventory.sqlite3'),
                          RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='g2t_synthetic_owner_password')
        os.environ.pop('GOOGLE_SHEET_ID',None)
        os.environ.pop('GOOGLE_SERVICE_ACCOUNT_JSON',None)
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        today=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        owner,clerk,reviewer,stranger=[TestClient(app) for _ in range(4)]
        def ok(r, status=200):
            assert r.status_code==status,(r.status_code,r.text,status)
            return r.json() if status==200 else None
        def login(client,name,pw):
            return {'X-CSRF-Token':ok(client.post('/api/login',json={'username':name,'password':pw}))['csrf']}
        oh=login(owner,'owner','g2t_synthetic_owner_password')
        for username,role in [('g2t_stock_clerk','clerk'),('g2t_stock_reviewer','reviewer'),('g2t_stock_stranger','reviewer')]:
            ok(owner.post('/api/users',headers=oh,json={'username':username,'role':role,'password':'g2t_synthetic_worker_password'}))
        ch=login(clerk,'g2t_stock_clerk','g2t_synthetic_worker_password')
        rh=login(reviewer,'g2t_stock_reviewer','g2t_synthetic_worker_password')
        sh=login(stranger,'g2t_stock_stranger','g2t_synthetic_worker_password')
        ids={u['username']:u['id'] for u in ok(owner.get('/api/users'))}
        assert stranger.get('/api/inventory/overview').status_code==403
        assert reviewer.get('/api/inventory/overview').status_code==403
        ok(owner.post('/api/inventory/access',headers=oh,json={'user_id':ids['g2t_stock_clerk'],'can_prepare':True,'can_approve':False,'reason':'Synthetic central store clerk'}))
        ok(owner.post('/api/inventory/access',headers=oh,json={'user_id':ids['g2t_stock_reviewer'],'can_prepare':False,'can_approve':True,'reason':'Synthetic second reviewer'}))
        assert reviewer.get('/api/inventory/overview').status_code==200
        assert stranger.get('/api/inventory/overview').status_code==403
        v=ok(owner.post('/api/inventory/vendors',headers=oh,json={'code':'SUP_G2T','name':'Synthetic consumables vendor'}))['id']
        item=ok(owner.post('/api/inventory/items',headers=oh,json={'code':'G2T_GLOVES','name':'Synthetic examination gloves','unit':'piece'}))['id']
        assert clerk.post('/api/inventory/vendors',headers=ch,json={'code':'DENIED','name':'Not allowed vendor'}).status_code==403
        receipt={'vendor_id':v,'received_on':today,'invoice_ref':'SYNTHETIC-INVOICE-0001',
                 'evidence_ref':'SYNTHETIC-WAREHOUSE-GRN-0001','request_id':'g2t_receive_00000001',
                 'lines':[{'item_id':item,'quantity':3,'unit_cost':'12.00'}]}
        draft=ok(clerk.post('/api/inventory/receipts',headers=ch,json=receipt))
        rid=draft['id']
        assert ok(clerk.post('/api/inventory/receipts',headers=ch,json=receipt))['replayed']
        assert clerk.post('/api/inventory/receipts',headers=ch,json={**receipt,'request_id':'g2t_receive_00000002'}).status_code==409
        assert clerk.post('/api/inventory/receipts',headers=ch,json={**receipt,'lines':[{'item_id':item,'quantity':4,'unit_cost':'12.00'}]}).status_code==409
        assert clerk.post(f'/api/inventory/receipts/{rid}/decision',headers=ch,json={'decision':'approve','note':'Self approval attempted'}).status_code==403
        assert stranger.post(f'/api/inventory/receipts/{rid}/decision',headers=sh,json={'decision':'approve','note':'Unauthorized reviewer attempt'}).status_code==403
        assert ok(owner.get('/api/inventory/overview'))['items'][0]['quantity_on_hand']==0
        approved=ok(reviewer.post(f'/api/inventory/receipts/{rid}/decision',headers=rh,json={'decision':'approve','note':'Independent synthetic invoice checked'}))
        assert approved['status']=='approved' and approved['journal_id']
        assert reviewer.post(f'/api/inventory/receipts/{rid}/decision',headers=rh,json={'decision':'approve','note':'double approval'}).status_code==409
        second={**receipt,'invoice_ref':'SYNTHETIC-INVOICE-0002','evidence_ref':'SYNTHETIC-WAREHOUSE-GRN-0002','request_id':'g2t_receive_00000003','lines':[{'item_id':item,'quantity':5,'unit_cost':'20.00'}]}
        rid2=ok(clerk.post('/api/inventory/receipts',headers=ch,json=second))['id']
        ok(reviewer.post(f'/api/inventory/receipts/{rid2}/decision',headers=rh,json={'decision':'approve','note':'Independent synthetic second invoice'}))
        inv=ok(owner.get('/api/inventory/overview'))
        assert inv['items'][0]['quantity_on_hand']==8,inv
        assert inv['items'][0]['value_piasters']==13600,inv # 3*1200+5*2000
        dept=next(x['id'] for x in ok(owner.get('/api/lookups'))['departments'] if x['code']=='IPD')
        issue={'department_id':dept,'used_on':today,'evidence_ref':'SYNTHETIC-ISSUE-NOTE-001',
               'request_id':'g2t_issue_000000001','lines':[{'item_id':item,'quantity':4}]}
        iid=ok(clerk.post('/api/inventory/issues',headers=ch,json=issue))['id']
        assert ok(clerk.post('/api/inventory/issues',headers=ch,json=issue))['replayed']
        assert ok(owner.get('/api/inventory/overview'))['items'][0]['quantity_on_hand']==8
        assert clerk.post(f'/api/inventory/issues/{iid}/decision',headers=ch,json={'decision':'approve','note':'Self approval attempted'}).status_code==403
        approved_issue=ok(reviewer.post(f'/api/inventory/issues/{iid}/decision',headers=rh,json={'decision':'approve','note':'Synthetic ward issue checked'}))
        assert approved_issue['cost_piasters']==5600,approved_issue # 3*1200+1*2000
        assert ok(owner.get('/api/inventory/overview'))['items'][0]['quantity_on_hand']==4
        assert ok(owner.get('/api/inventory/overview'))['items'][0]['value_piasters']==8000
        too_much={**issue,'request_id':'g2t_issue_000000002','lines':[{'item_id':item,'quantity':5}]}
        excessive=ok(clerk.post('/api/inventory/issues',headers=ch,json=too_much))['id']
        assert reviewer.post(f'/api/inventory/issues/{excessive}/decision',headers=rh,json={'decision':'approve','note':'Cannot issue negative units'}).status_code==409
        with connect() as c:
            assert c.execute('SELECT status FROM inventory_issues WHERE id=?',(excessive,)).fetchone()[0]=='pending'
            assert c.execute('SELECT COUNT(*) FROM inventory_issue_allocations WHERE issue_id=?',(excessive,)).fetchone()[0]==0
            assert c.execute('SELECT COUNT(*) FROM gl_journals WHERE status="posted" AND memo LIKE "INV:%"').fetchone()[0]==3
            assert c.execute('SELECT sum(debit_piasters-credit_piasters) FROM gl_lines l JOIN gl_journals j ON j.id=l.journal_id WHERE j.memo LIKE "INV:%"').fetchone()[0]==0
            for table,doc_id in [('inventory_receipts',rid),('inventory_issues',iid)]:
                try: c.execute(f'DELETE FROM {table} WHERE id=?',(doc_id,))
                except Exception: c.rollback()
                else: raise AssertionError('Final inventory evidence deletable')
            try: c.execute('UPDATE inventory_receipt_lines SET unit_cost_piasters=1 WHERE receipt_id=?',(rid,))
            except Exception: c.rollback()
            else: raise AssertionError('Approved supplier unit cost mutable')
        reconcile=ok(owner.get('/api/inventory/reconciliation',params={'period':today[:7]}))
        assert reconcile['matched'],reconcile
        assert reconcile['quantity_on_hand']==4 and reconcile['value_piasters']==8000,reconcile
        assert stranger.get('/api/inventory/reconciliation',params={'period':today[:7]}).status_code==403
        from inventory import month_close_inventory_issue
        with connect() as c:
            assert month_close_inventory_issue(c,today[:7]) == 'أذون صرف مستلزمات تنتظر اعتماد مراجع مستقل'
        ok(reviewer.post(f'/api/inventory/issues/{excessive}/decision',headers=rh,json={'decision':'reject','note':'Rejected insufficient physical units'}))
        with connect() as c:
            assert month_close_inventory_issue(c,today[:7]) is None
        # Grants are checked on every request, not merely at login.
        ok(owner.post('/api/inventory/access',headers=oh,json={'user_id':ids['g2t_stock_reviewer'],'can_prepare':False,'can_approve':False,'reason':'Synthetic immediate access revocation'}))
        assert reviewer.get('/api/inventory/overview').status_code==403
        assert reviewer.post(f'/api/inventory/issues/{iid}/decision',headers=rh,json={'decision':'approve','note':'Now revoked'}).status_code==403
        assert owner.post('/api/accounting/journals/'+str(approved['journal_id'])+'/reverse',headers=oh,json={'date':today,'reason':'Try to alter stock AP journal'}).status_code==409
        print('PASS G2T receipt and FIFO medical consumables: maker/checker, GL 1100/2200/5100, immutable evidence, no negative stock, reconciliation')

if __name__=='__main__':run()
