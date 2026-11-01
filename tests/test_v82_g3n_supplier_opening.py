"""G3N TDD: evidence-only supplier balance confirmations at a PRIOR month-end."""
import os,sqlite3,sys,tempfile
from datetime import date,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory(prefix='ramses-g3n-') as folder:
        os.environ.update(RAMSES_DB_PATH=str(Path(folder)/'synthetic.sqlite3'),
            RAMSES_ADMIN_USER='owner', RAMSES_ADMIN_PASSWORD='g3n-owner-synthetic-password')
        for name in ('GOOGLE_SHEET_ID','GOOGLE_SERVICE_ACCOUNT_JSON','GOOGLE_SHEET_TARGET'):
            os.environ.pop(name,None)
        from bootstrap import initialize,connect
        from app import app
        from fastapi.testclient import TestClient
        import ledger
        initialize()
        clients={name:TestClient(app) for name in ('owner','maker','reviewer','outsider')}
        def expect(resp,status=200):
            assert resp.status_code==status,(status,resp.status_code,resp.text[:900])
            return resp.json() if status==200 else None
        auth={'owner':{'X-CSRF-Token':expect(clients['owner'].post('/api/login',json={
           'username':'owner','password':'g3n-owner-synthetic-password'}))['csrf']}}
        users={}
        for name,role in [('maker','clerk'),('reviewer','reviewer'),('outsider','clerk')]:
            users[name]=expect(clients['owner'].post('/api/users',headers=auth['owner'],json={
              'username':'g3n_'+name,'password':'g3n-synthetic-actor-password','role':role}))['id']
            auth[name]={'X-CSRF-Token':expect(clients[name].post('/api/login',json={
              'username':'g3n_'+name,'password':'g3n-synthetic-actor-password'}))['csrf']}
        for name,prepare,approve in [('maker',True,False),('reviewer',False,True)]:
            expect(clients['owner'].post('/api/inventory/access',headers=auth['owner'],json={
              'user_id':users[name],'can_prepare':prepare,'can_approve':approve,
              'reason':'G3N synthetic separation of opening evidence reviewer'}))
        vendor=expect(clients['owner'].post('/api/inventory/vendors',headers=auth['owner'],json={
           'code':'G3N-OPEN-01','name':'Synthetic opening vendor'}))['id']
        item=expect(clients['owner'].post('/api/inventory/items',headers=auth['owner'],json={
           'code':'G3N-STOCK','name':'Synthetic test gauze','unit':'piece'}))['id']
        today=datetime.now(ZoneInfo('Africa/Cairo')).date()
        prior_last=today.replace(day=1)-timedelta(days=1)
        cutoff=prior_last.isoformat()
        before=(prior_last-timedelta(days=1)).isoformat()
        def approve_receipt(ref,quantity):
            receipt=expect(clients['maker'].post('/api/inventory/receipts',headers=auth['maker'],json={
               'vendor_id':vendor,'received_on':before,'invoice_ref':ref,
               'evidence_ref':'G3N-GOODS-SIGNED-DOCK-REF',
               'lines':[{'item_id':item,'quantity':quantity,'unit_cost':'10.00'}],
               'request_id':ref+'-receipt'}))['id']
            expect(clients['reviewer'].post(f'/api/inventory/receipts/{receipt}/decision',
              headers=auth['reviewer'],json={'decision':'approve','note':'Independent synthetic goods receipt approval'}))
        approve_receipt('G3N-INV-01',3)
        url='/api/inventory/supplier-opening-statements'
        payload={'vendor_id':vendor,'as_of':cutoff,'statement_balance':'30.00',
          'evidence_ref':'SIGNED-VENDOR-STATEMENT-202610',
          'reason':'Independent vendor statement confirmation at closed prior month end',
          'request_id':'g3n-statement-original-01'}
        expect(clients['outsider'].get(url),403)
        expect(clients['outsider'].post(url,headers=auth['outsider'],json=payload),403)
        old=expect(clients['owner'].get('/api/inventory/supplier-control-ledger',params={'as_of':cutoff}))
        assert old['control_2200_piasters']==3000 and old['reconciled'],old
        with connect() as c:
            gl_count=c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0]
            money_count=c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]
        doc=expect(clients['maker'].post(url,headers=auth['maker'],json=payload))
        doc_id=doc['id']
        assert doc['status']=='pending' and doc['money_moved'] is False
        assert expect(clients['maker'].post(url,headers=auth['maker'],json=payload))['id']==doc_id
        expect(clients['maker'].post(url,headers=auth['maker'],json={**payload,'request_id':'g3n-duplicate-002'}),409)
        expect(clients['maker'].post(url,headers=auth['maker'],json={**payload,'as_of':today.isoformat(),
            'request_id':'g3n-current-month-003'}),409)
        expect(clients['maker'].post(url,headers=auth['maker'],json={**payload,
            'as_of':before,'request_id':'g3n-non-month-end-004'}),409)
        expect(clients['maker'].post(url,headers=auth['maker'],json={**payload,
            'statement_balance':'-5','request_id':'g3n-negative-005'}),400)
        expect(clients['maker'].post(url,headers=auth['maker'],json={**payload,
            'statement_balance':'50','request_id':'g3n-mismatch-006'}),409)
        vendor2=expect(clients['owner'].post('/api/inventory/vendors',headers=auth['owner'],json={
            'code':'G3N-OTHER-02','name':'Other synthetic supplier'}))['id']
        bad=expect(clients['maker'].post(url,headers=auth['maker'],json={
            **payload,'vendor_id':vendor2,'statement_balance':'25.00',
            'request_id':'g3n-unmatched-statement-vendor-02'}))['id']
        expect(clients['reviewer'].post(f'{url}/{bad}/decision',headers=auth['reviewer'],json={
            'decision':'approve','note':'Mismatch must not be approved'}),409)
        expect(clients['reviewer'].post(f'{url}/{bad}/decision',headers=auth['reviewer'],json={
            'decision':'reject','note':'Supplier external statement differs from ledger'}))
        expect(clients['maker'].post(f'{url}/{doc_id}/decision',headers=auth['maker'],json={
            'decision':'approve','note':'This person prepared the statement'}),403)
        with connect() as c:
            try:
                c.execute("""INSERT INTO supplier_opening_statements
                    (vendor_id,as_of,statement_piasters,ledger_piasters,control_piasters,
                     attributed_piasters,unattributed_count,anomaly_count,source_digest,
                     evidence_ref,reason,created_by,created_at)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (vendor,'2026-13-31',3000,3000,3000,3000,0,0,'a'*64,
                     'INVALID-SIGNED-STMT-REF','Invalid calendar date direct insertion',
                     users['maker'],datetime.now(ZoneInfo('Africa/Cairo')).isoformat()))
            except sqlite3.IntegrityError:c.rollback()
            else:
                c.rollback()
                raise AssertionError('Direct SQLite accepted impossible calendar date')
        with connect() as c:
            try:c.execute("UPDATE supplier_opening_statements SET status='approved',reviewed_by=?,reviewed_at='2026-10-31T00:00:00+00:00',review_note='Forged' WHERE id=?",(users['maker'],doc_id))
            except sqlite3.IntegrityError:c.rollback()
            else:raise AssertionError('Direct SQL bypassed maker/checker')
            try:c.execute('UPDATE supplier_opening_statements SET statement_piasters=900 WHERE id=?',(doc_id,))
            except sqlite3.IntegrityError:c.rollback()
            else:raise AssertionError('Direct SQL changed signed vendor amount')
        docs=expect(clients['reviewer'].get(url))['documents']
        assert any(x['id']==doc_id and x['statement_piasters']==3000 and x['ledger_piasters']==3000 and x['evidence_ref']==payload['evidence_ref'] for x in docs),docs
        expect(clients['owner'].post('/api/inventory/access',headers=auth['owner'],json={
            'user_id':users['reviewer'],'can_prepare':False,'can_approve':False,
            'reason':'G3N revoked reviewer should not approve'}))
        expect(clients['reviewer'].post(f'{url}/{doc_id}/decision',headers=auth['reviewer'],json={
            'decision':'approve','note':'Reviewer grant was revoked'}),403)
        expect(clients['owner'].post('/api/inventory/access',headers=auth['owner'],json={
            'user_id':users['reviewer'],'can_prepare':False,'can_approve':True,
            'reason':'G3N restored synthetic review role'}))
        # A later posting backdated to the cutoff invalidates the prepared digest.
        approve_receipt('G3N-INV-02',1)
        expect(clients['reviewer'].post(f'{url}/{doc_id}/decision',headers=auth['reviewer'],json={
            'decision':'approve','note':'Cannot approve stale source ledger evidence'}),409)
        with connect() as c:
            try:c.execute("""UPDATE supplier_opening_statements
                 SET status='approved',reviewed_by=?,reviewed_at=?,review_note='Reviewed source journal values'
                 WHERE id=?""",(users['reviewer'],datetime.now(ZoneInfo('Africa/Cairo')).isoformat(),doc_id))
            except sqlite3.IntegrityError:c.rollback()
            else:raise AssertionError('Direct SQLite bypassed stale 2200 control and approved outdated statement')
        expect(clients['reviewer'].post(f'{url}/{doc_id}/decision',headers=auth['reviewer'],json={
            'decision':'reject','note':'Stale control after another receipt'}))
        after={**payload,'statement_balance':'40.00','request_id':'g3n-replacement-007'}
        doc2=expect(clients['maker'].post(url,headers=auth['maker'],json=after))['id']
        expect(clients['reviewer'].post(f'{url}/{doc2}/decision',headers=auth['reviewer'],json={
            'decision':'approve','note':'Reviewed matching closed month vendor statement and full GL sources'}))
        assert expect(clients['reviewer'].get(url))['documents'][0]['status']=='approved'
        expect(clients['reviewer'].post(f'{url}/{doc2}/decision',headers=auth['reviewer'],json={
            'decision':'approve','note':'Cannot approve final twice'}),409)
        with connect() as c:
            assert c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0]==gl_count+1
            assert c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]==money_count
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            try:c.execute('DELETE FROM supplier_opening_statements WHERE id=?',(doc2,))
            except sqlite3.IntegrityError:c.rollback()
            else:raise AssertionError('Direct SQL deleted immutable opening statement')
        # Unattributed 2200 source must not be hidden by a signed vendor statement.
        prior_month=(prior_last.replace(day=1)-timedelta(days=1)).isoformat()
        with connect() as c:
            ledger._journal(c,entry_date=prior_month,memo='G3N unattributed old AP entry',origin='manual',source_id=None,
                created_by=1,reviewed_by=1,lines=[(ledger.account_by_code(c,'1100'),0,1500,None),
                 (ledger.account_by_code(c,'2200'),1500,0,None)])
        blocked=expect(clients['maker'].post(url,headers=auth['maker'],json={
            **payload,'as_of':prior_month,'statement_balance':'0',
            'request_id':'g3n-unattributed-008'}))
        expect(clients['reviewer'].post(f'{url}/{blocked["id"]}/decision',headers=auth['reviewer'],json={
            'decision':'approve','note':'Cannot sign off unexplained 2200 source'}),409)
        print('PASS G3N prior month-end opening statement: source freeze, signed amount, revoked reviewer, no GL/cash entry')

if __name__=='__main__':run()
