"""G3M TDD: independently reviewed attribution of ONE historic 2200 journal, never new money."""
import os
import sqlite3
import sys
import tempfile
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory(prefix='ramses-g3m-') as td:
        os.environ.update(RAMSES_DB_PATH=str(Path(td)/'synthetic.sqlite3'),
                          RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='g3m-fake-owner-secret')
        for key in ('GOOGLE_SHEET_ID','GOOGLE_SERVICE_ACCOUNT_JSON','GOOGLE_SHEET_TARGET'):
            os.environ.pop(key,None)
        from bootstrap import initialize,connect
        import ledger
        from app import app
        from fastapi.testclient import TestClient
        initialize()
        clients={key:TestClient(app) for key in ('owner','maker','checker','outsider')}
        def expect(resp,status=200):
            assert resp.status_code==status,(status,resp.status_code,resp.text[:1200])
            return resp.json() if status==200 else {}
        auth={'owner':{'X-CSRF-Token':expect(clients['owner'].post('/api/login',json={
            'username':'owner','password':'g3m-fake-owner-secret'}))['csrf']}}
        ids={}
        for k,role in [('maker','clerk'),('checker','reviewer'),('outsider','clerk')]:
            ids[k]=expect(clients['owner'].post('/api/users',headers=auth['owner'],json={
                'username':'g3m_'+k,'password':'g3m-fake-actor-secret','role':role}))['id']
            auth[k]={'X-CSRF-Token':expect(clients[k].post('/api/login',json={
                'username':'g3m_'+k,'password':'g3m-fake-actor-secret'}))['csrf']}
        for k,p,a in [('maker',True,False),('checker',False,True)]:
            expect(clients['owner'].post('/api/inventory/access',headers=auth['owner'],json={
                'user_id':ids[k],'can_prepare':p,'can_approve':a,
                'reason':'G3M synthetic GL attribution separation'}))
        vendor=expect(clients['owner'].post('/api/inventory/vendors',headers=auth['owner'],json={
            'code':'LEGACY-G3M','name':'مورد تاريخي اصطناعي'}))['id']
        second_vendor=expect(clients['owner'].post('/api/inventory/vendors',headers=auth['owner'],json={
            'code':'LEGACY-G3M-OTHER','name':'مورد مختلف تجريبي'}))['id']
        now=datetime.now(ZoneInfo('Africa/Cairo')).date()
        today=now.isoformat();yesterday=(now-timedelta(days=1)).isoformat()
        with connect() as c:
            jid=ledger._journal(c,entry_date=yesterday,memo='Synthetic historic AP unassigned',
               origin='manual',source_id=None,created_by=1,reviewed_by=1,
               lines=[(ledger.account_by_code(c,'1100'),13579,0,None),
                      (ledger.account_by_code(c,'2200'),0,13579,None)])
            base_journal_count=c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0]
            balances=c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]
        params={'journal_id':jid,'vendor_id':vendor,'evidence_ref':'ARCHIVE-PAYABLE-SIGNED-001',
                'reason':'Signed source document for historical payable to this supplier',
                'request_id':'g3m-synthetic-link-001'}
        expect(clients['outsider'].get('/api/inventory/supplier-attributions'),403)
        expect(clients['outsider'].post('/api/inventory/supplier-attributions',headers=auth['outsider'],json=params),403)
        pre_report=expect(clients['owner'].get('/api/inventory/supplier-control-ledger',params={'as_of':today}))
        assert pre_report['unattributed_2200_piasters']==13579 and not pre_report['reconciled']
        doc=expect(clients['maker'].post('/api/inventory/supplier-attributions',headers=auth['maker'],json=params))
        doc_id=doc['id']
        assert expect(clients['maker'].post('/api/inventory/supplier-attributions',headers=auth['maker'],json=params))['id']==doc_id
        expect(clients['maker'].post('/api/inventory/supplier-attributions',headers=auth['maker'],json={
            **params,'request_id':'g3m-another-request'}),409)
        expect(clients['maker'].post(f'/api/inventory/supplier-attributions/{doc_id}/decision',headers=auth['maker'],json={
            'decision':'approve','note':'Approver must be independent'}),403)
        with connect() as c:
            try:c.execute('UPDATE supplier_journal_attributions SET status=?,reviewed_by=?,reviewed_at=?,review_note=? WHERE id=?',
                          ('approved',1,datetime.now().isoformat(),'Owner created original GL',doc_id))
            except sqlite3.IntegrityError:c.rollback()
            else:raise AssertionError('Direct SQLite forged approval by original GL maker')
            try:c.execute('UPDATE supplier_journal_attributions SET vendor_id=? WHERE id=?',(second_vendor,doc_id))
            except sqlite3.IntegrityError:c.rollback()
            else:raise AssertionError('Direct SQLite changed submitted vendor')
        pending=expect(clients['checker'].get('/api/inventory/supplier-attributions'))
        assert any(x['id']==doc_id and x['status']=='pending' and x['evidence_ref']==params['evidence_ref'] for x in pending['documents'])
        expect(clients['checker'].post(f'/api/inventory/supplier-attributions/{doc_id}/decision',headers=auth['checker'],json={
            'decision':'approve','note':'Two-person reconciliation to signed archive evidence'}))
        current=expect(clients['owner'].get('/api/inventory/supplier-control-ledger',params={'as_of':today}))
        assert current['control_2200_piasters']==13579 and current['attributed_2200_piasters']==13579,current
        assert current['unattributed_2200_piasters']==0 and current['reconciled'],current
        assert current['vendors'][0]['balance_piasters']==13579,current
        assert current['vendors'][0]['legacy_attributed_piasters']==13579,current
        assert current['events'][0]['kind']=='historical_attribution',current
        assert expect(clients['maker'].post('/api/inventory/supplier-attributions',headers=auth['maker'],json=params))['status']=='approved'
        old=expect(clients['owner'].get('/api/inventory/supplier-control-ledger',params={'as_of':yesterday}))
        assert old['control_2200_piasters']==13579 and old['unattributed_2200_piasters']==13579,old
        with connect() as c:
            assert c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0]==base_journal_count
            assert c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]==balances
            try:c.execute('DELETE FROM supplier_journal_attributions WHERE id=?',(doc_id,))
            except sqlite3.IntegrityError:c.rollback()
            else:raise AssertionError('SQL erased signed attribution history')
        # Revocation and rejected-document retry never erase the rejected audit trail.
        with connect() as c:
            second_journal=ledger._journal(c,entry_date=yesterday,memo='Second old synthetic AP',
               origin='manual',source_id=None,created_by=1,reviewed_by=1,
               lines=[(ledger.account_by_code(c,'1100'),2468,0,None),
                      (ledger.account_by_code(c,'2200'),0,2468,None)])
        params2={**params,'journal_id':second_journal,'request_id':'g3m-second-historic-link-001'}
        pending2=expect(clients['maker'].post('/api/inventory/supplier-attributions',headers=auth['maker'],json=params2))['id']
        expect(clients['owner'].post('/api/inventory/access',headers=auth['owner'],json={
            'user_id':ids['checker'],'can_prepare':False,'can_approve':False,
            'reason':'Synthetic G3M immediate revocation of reviewer grant'}))
        expect(clients['checker'].post(f'/api/inventory/supplier-attributions/{pending2}/decision',
            headers=auth['checker'],json={'decision':'approve','note':'Cannot approve after grant revoked'}),403)
        expect(clients['owner'].post('/api/inventory/access',headers=auth['owner'],json={
            'user_id':ids['checker'],'can_prepare':False,'can_approve':True,
            'reason':'Synthetic G3M reauthorized independent reviewer'}))
        expect(clients['checker'].post(f'/api/inventory/supplier-attributions/{pending2}/decision',
            headers=auth['checker'],json={'decision':'reject','note':'Rejected evidence is incomplete'}))
        replacement=expect(clients['maker'].post('/api/inventory/supplier-attributions',headers=auth['maker'],json={
            **params2,'evidence_ref':'REPLACED-SIGNED-DOCUMENT-G3M-002',
            'request_id':'g3m-replaced-historic-link-002'}))['id']
        assert replacement!=pending2
        with connect() as c:
            assert c.execute('SELECT status FROM supplier_journal_attributions WHERE id=?',(pending2,)).fetchone()[0]=='rejected'
            try:c.execute('UPDATE supplier_journal_attributions SET reviewed_by=? WHERE id=?',(ids['checker'],replacement))
            except sqlite3.IntegrityError:c.rollback()
            else:raise AssertionError('Direct SQLite could alter submitted reviewer fields without a status decision')
        print('PASS G3M GL 2200 historic attribution: independent review, SQL guards, as-of, no ledger/cash mutation')

if __name__=='__main__':run()
