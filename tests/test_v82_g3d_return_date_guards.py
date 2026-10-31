"""G3D negative cases: expiry, backdating and sealed financial periods are fail-closed."""
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory(prefix='g3d-return-guards-') as tmp:
        os.environ.update(RAMSES_DB_PATH=str(Path(tmp)/'synthetic.sqlite3'),
                          RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='synthetic_g3d_guard_owner')
        os.environ.pop('GOOGLE_SHEET_ID',None)
        os.environ.pop('GOOGLE_SERVICE_ACCOUNT_JSON',None)
        from bootstrap import initialize,connect
        initialize()
        from app import app,stamp
        from inventory import ledger_post,return_cost
        from fastapi.testclient import TestClient
        owner,clerk,reviewer=[TestClient(app) for _ in range(3)]
        def ok(r):
            assert r.status_code==200,(r.status_code,r.text)
            return r.json()
        def auth(client,u,pw):
            return {'X-CSRF-Token':ok(client.post('/api/login',json={'username':u,'password':pw}))['csrf']}
        oh=auth(owner,'owner','synthetic_g3d_guard_owner')
        ids={}
        for name,role in (('g3d_guard_clerk','clerk'),('g3d_guard_reviewer','reviewer')):
            ids[name]=ok(owner.post('/api/users',headers=oh,json={
                'username':name,'role':role,'password':'synthetic_g3d_guard_staff_pw'}))['id']
        ch=auth(clerk,'g3d_guard_clerk','synthetic_g3d_guard_staff_pw')
        rh=auth(reviewer,'g3d_guard_reviewer','synthetic_g3d_guard_staff_pw')
        for name in ids:
            ok(owner.post('/api/inventory/access',headers=oh,json={
                'user_id':ids[name], 'can_prepare':name.endswith('clerk'),
                'can_approve':name.endswith('reviewer'),
                'reason':'Synthetic date and lifetime guard test'}))
        now=datetime.now(ZoneInfo('Africa/Cairo')).date()
        day=now.isoformat()
        old=(now-timedelta(days=5)).isoformat()
        used=(now-timedelta(days=4)).isoformat()
        retro=(now-timedelta(days=3)).isoformat()
        yesterday=(now-timedelta(days=1)).isoformat()
        dept=next(x['id'] for x in ok(owner.get('/api/lookups'))['departments'] if x['code']=='IPD')
        vendor=ok(owner.post('/api/inventory/vendors',headers=oh,json={
            'code':'G3D_GUARD_VENDOR','name':'Synthetic date guard supplier'}))['id']

        def stock_item(label,expiry=None):
            item=ok(owner.post('/api/inventory/items',headers=oh,json={
                'code':label,'name':'Synthetic '+label+' dressing'}))['id']
            receipt=ok(clerk.post('/api/inventory/receipts',headers=ch,json={
                'vendor_id':vendor,'received_on':old,
                'invoice_ref':f'G3D-INVOICE-{label}',
                'evidence_ref':f'G3D-GRN-{label}-SIGNED',
                'request_id':f'g3d_return_receipt_{label}_01',
                'lines':[{'item_id':item,'quantity':5,'unit_cost':'4.00','expiry_date':expiry}]}))['id']
            ok(reviewer.post(f'/api/inventory/receipts/{receipt}/decision',headers=rh,json={
                'decision':'approve','note':'Independently verified synthetic lot'}))
            return item

        def issue(item,d,seq,qty=1):
            iid=ok(clerk.post('/api/inventory/issues',headers=ch,json={
                'department_id':dept,'used_on':d,
                'evidence_ref':f'G3D-SYNTH-GUARD-ISSUE-{seq}',
                'request_id':f'g3d_return_issue_guard_{seq}',
                'lines':[{'item_id':item,'quantity':qty}]}))['id']
            ok(reviewer.post(f'/api/inventory/issues/{iid}/decision',headers=rh,json={
                'decision':'approve','note':'Independent synthetic issue authorization'}))
            return iid

        item=stock_item('G3D_CHRONOLOGICAL')
        original=issue(item,used,'old')
        later=issue(item,day,'later')
        allocation=ok(clerk.get(f'/api/inventory/issues/{original}/returnable',headers=ch))['allocations'][0]['issue_allocation_id']
        payload={'issue_id':original,'returned_on':retro,
                 'evidence_ref':'G3D-SYNTH-DATED-RETURN',
                 'request_id':'g3d_return_guard_chrono01',
                 'lines':[{'issue_allocation_id':allocation,'quantity':1}]}
        result=clerk.post('/api/inventory/returns',headers=ch,json=payload)
        assert result.status_code==409,(result.status_code,result.text)
        with connect() as c:
            baseline=(c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0],
                      c.execute('SELECT COUNT(*) FROM inventory_issue_returns').fetchone()[0])
            c.execute('BEGIN IMMEDIATE')
            try:
                c.execute('INSERT INTO inventory_issue_returns(issue_id,returned_on,evidence_ref,created_by,created_at) VALUES(?,?,?,?,?)',
                          (original,retro,'G3D-SYNTH-SQL-BYPASS',ids['g3d_guard_clerk'],stamp()))
                badid=c.execute('SELECT max(id) FROM inventory_issue_returns').fetchone()[0]
                c.execute('INSERT INTO inventory_return_lines(return_id,issue_allocation_id,quantity) VALUES(?,?,1)',
                          (badid,allocation))
                cost=return_cost(c,badid)
                jid=ledger_post(c,retro,'RETURN',badid,ids['g3d_guard_clerk'],ids['g3d_guard_reviewer'],
                                '1100','5100',cost,dept)
                try:
                    c.execute('''UPDATE inventory_issue_returns SET status='approved',reviewed_by=?,reviewed_at=?,review_note=?,cost_piasters=?,journal_id=? WHERE id=?''',
                              (ids['g3d_guard_reviewer'],stamp(),'Synthetic forced backdated approval',cost,jid,badid))
                except sqlite3.IntegrityError:pass
                else:raise AssertionError('Direct SQLite backdated return bypassed approval guard')
            finally:
                c.rollback()
            assert baseline==(c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0],
                              c.execute('SELECT COUNT(*) FROM inventory_issue_returns').fetchone()[0])

        expired_item=stock_item('G3D_EXPIRY_CHECK',expiry=yesterday)
        expired_source=issue(expired_item,used,'expires')
        expired_alloc=ok(clerk.get(f'/api/inventory/issues/{expired_source}/returnable',headers=ch))['allocations'][0]['issue_allocation_id']
        expired=clerk.post('/api/inventory/returns',headers=ch,json={
            **payload,'issue_id':expired_source,'returned_on':day,
            'request_id':'g3d_return_guard_expiry01',
            'lines':[{'issue_allocation_id':expired_alloc,'quantity':1}]})
        assert expired.status_code==409,(expired.status_code,expired.text)

        # Raw SQL cannot invent more physical returns than originally issued.
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                c.execute('INSERT INTO inventory_issue_returns(issue_id,returned_on,evidence_ref,created_by,created_at) VALUES(?,?,?,?,?)',
                          (original,day,'G3D-SYNTH-OVERSIZE-RETURN',ids['g3d_guard_clerk'],stamp()))
                rid=c.execute('SELECT max(id) FROM inventory_issue_returns').fetchone()[0]
                try:c.execute('INSERT INTO inventory_return_lines(return_id,issue_allocation_id,quantity) VALUES(?,?,2)',
                              (rid,allocation))
                except sqlite3.IntegrityError:pass
                else:raise AssertionError('Over-returning source allocation bypassed SQLite')
            finally:c.rollback()

        # A return dated TODAY cannot provide physical stock to an issue dated BEFORE
        # the return. Original source and remaining stock were fully issued earlier.
        future_item=stock_item('G3D_FUTURE_RETURN')
        future_source=issue(future_item,used,'return_future_source')
        issue(future_item,used,'return_future_sweep',qty=4)
        future_allocation=ok(clerk.get(f'/api/inventory/issues/{future_source}/returnable',headers=ch))['allocations'][0]['issue_allocation_id']
        future_return=ok(clerk.post('/api/inventory/returns',headers=ch,json={
            **payload,'issue_id':future_source,'returned_on':day,
            'request_id':'g3d_future_stock_return_01',
            'lines':[{'issue_allocation_id':future_allocation,'quantity':1}]}))['id']
        ok(reviewer.post(f'/api/inventory/returns/{future_return}/decision',headers=rh,json={
            'decision':'approve','note':'Synthetic independently verified later physical return'}))
        retro_issue=ok(clerk.post('/api/inventory/issues',headers=ch,json={
            'department_id':dept,'used_on':retro,
            'evidence_ref':'G3D-BACKDATED-AFTER-RETURN',
            'request_id':'g3d_backdated_after_return_01',
            'lines':[{'item_id':future_item,'quantity':1}]}))['id']
        response=reviewer.post(f'/api/inventory/issues/{retro_issue}/decision',headers=rh,json={
            'decision':'approve','note':'Future return must not fund a past consumption'})
        assert response.status_code==409,(response.status_code,response.text)
        with connect() as c:
            assert c.execute('SELECT status FROM inventory_issues WHERE id=?',(retro_issue,)).fetchone()[0]=='pending'
            assert c.execute('SELECT COUNT(*) FROM inventory_issue_allocations WHERE issue_id=?',(retro_issue,)).fetchone()[0]==0
        ok(reviewer.post(f'/api/inventory/issues/{retro_issue}/decision',headers=rh,json={
            'decision':'reject','note':'Rejected past consumption after later physical return'}))

        valid=ok(clerk.post('/api/inventory/returns',headers=ch,json={
            **payload,'returned_on':day,'request_id':'g3d_return_guard_valid01'}))['id']
        with connect() as c:
            c.execute('INSERT INTO periods(period,closed_by,closed_at) VALUES(?,?,?)',(day[:7],1,day))
            c.commit()
        denied=reviewer.post(f'/api/inventory/returns/{valid}/decision',headers=rh,json={
            'decision':'approve','note':'Cannot approve in sealed financial period'})
        assert denied.status_code==409,(denied.status_code,denied.text)
        with connect() as c:
            assert c.execute('SELECT status FROM inventory_issue_returns WHERE id=?',(valid,)).fetchone()[0]=='pending'
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
        print('PASS G3D expiry, dated FIFO return, raw SQL quantity/date guards and sealed-month approval all fail closed')


if __name__=='__main__':run()
