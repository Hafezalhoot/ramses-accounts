"""End-to-end V7.6 bank matching without posting from imported statement."""
import io
import os
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as td:
        os.environ['RAMSES_DB_PATH']=str(Path(td)/'bank.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='owner_test_only_very_strong_pw'
        os.environ.pop('RAMSES_REQUIRE_PAYMENT_EVIDENCE',None)
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner,reviewer,clerk,viewer=(TestClient(app) for _ in range(4))
        def login(cli,u,p):
            r=cli.post('/api/login',json={'username':u,'password':p})
            assert r.status_code==200,r.text
            return {'X-CSRF-Token':r.json()['csrf']}
        oh=login(owner,'owner','owner_test_only_very_strong_pw')
        for name,role in [('reviewer','reviewer'),('clerk','clerk'),('viewer','viewer')]:
            r=owner.post('/api/users',headers=oh,json={'username':name,'password':'test_password_123456','role':role})
            assert r.status_code==200,r.text
        rh=login(reviewer,'reviewer','test_password_123456')
        ch=login(clerk,'clerk','test_password_123456')
        vh=login(viewer,'viewer','test_password_123456')
        lk=owner.get('/api/lookups').json()
        bank=next(x['id'] for x in lk['funds'] if x['kind']=='bank')
        wallet=next(x['id'] for x in lk['funds'] if x['kind']=='wallet')
        clerk_id=next(x['id'] for x in owner.get('/api/users').json() if x['username']=='clerk')
        for fund_id in (bank,wallet):
            assert owner.post('/api/fund-access',headers=oh,json={'user_id':clerk_id,'fund_id':fund_id,'can_submit':True,
                'reason':'صلاحية بنكية ومحفظة للاختبارات الرقابية'}).status_code==200
        reviewer_id=next(x['id'] for x in owner.get('/api/users').json() if x['username']=='reviewer')
        for review_fund_id in (bank,wallet):
            assert owner.post('/api/fund-access',headers=oh,json={'user_id':reviewer_id,'fund_id':review_fund_id,
                  'can_approve':True,'can_submit':True,'reason':'تخويل إعداد ومراجعة البنك والمحفظة للاختبارات'}).status_code==200
        dept=lk['departments'][0]['id']
        rev=next(x['id'] for x in lk['categories'] if x['code']=='other_revenue')
        exp=next(x['id'] for x in lk['categories'] if x['code']=='utilities')
        month='2026-08'
        assert owner.post(f'/api/funds/{bank}/opening',headers=oh,json={'amount':'1000'}).status_code==200
        assert owner.post(f'/api/funds/{wallet}/opening',headers=oh,json={'amount':'1000'}).status_code==200
        def make(kind,amount,cat=None,from_id=None,to_id=None):
            r=clerk.post('/api/vouchers',headers=ch,json={
                'date':'2026-08-14','kind':kind,'department_id':dept,'category_id':cat,'shift':'central',
                'from_fund_id':from_id or bank,'to_fund_id':to_id,
                'amount':amount,'description':'حركة بنكية وهمية مطابقة لكشف تجريبي'})
            assert r.status_code==200,r.text
            approved=reviewer.post(f'/api/vouchers/{r.json()["id"]}/decision',headers=rh,json={'decision':'approve'})
            assert approved.status_code==200,approved.text
            return r.json()['id']
        r1=make('receipt','200',rev)
        r2=make('payment','50',exp)
        r3=make('transfer','300',from_id=bank,to_id=wallet)
        funds=owner.get('/api/funds').json()
        assert next(f for f in funds if f['id']==bank)['balance_piasters']==85000
        assert owner.post('/api/periods/close',headers=oh,json={'period':month}).status_code==409
        overview=owner.get('/api/bank-reconciliation?period='+month+'&fund_id='+str(bank))
        assert overview.status_code==200 and overview.json()['batch'] is None
        assert len(overview.json()['unmatched_ledger'])==3
        assert viewer.get('/api/bank-reconciliation?period='+month+'&fund_id='+str(bank)).status_code==403
        assert clerk.get('/api/bank-reconciliation?period='+month+'&fund_id='+str(bank)).status_code==403
        assert TestClient(app).get('/api/bank-reconciliation?period='+month).status_code==401
        assert reviewer.post('/api/bank-reconciliation/import',headers=rh).status_code==422  # missing required form
        raw=('date,description,amount,reference\n'
             '2026-08-14,إيداع اختبار,200.00,DEP-1\n'
             '2026-08-14,مصاريف بنكية,-50.00,FEE-1\n'
             '2026-08-14,تحويل إلى المحفظة,-300.00,TRF-1\n').encode('utf-8-sig')
        def import_sheet(content=raw,opening='1000',closing='850',who=reviewer,headers=rh):
            return who.post('/api/bank-reconciliation/import',headers=headers,data={
                'fund_id':str(bank),'period':month,'opening_balance':opening,'closing_balance':closing},
                files={'file':('august_statement.csv',io.BytesIO(content),'text/csv')})
        assert import_sheet(closing='851').status_code==409
        assert import_sheet(content=b'date,description,amount\n2026-07-01,test,1\n').status_code==400
        assert import_sheet(content=b'date,description,amount\n2026-08-14,bad,1.001\n').status_code==400
        assert import_sheet(content=b'date,description,amount\n2026-08-14,ok,5,too-many\n').status_code==400
        uploaded=import_sheet()
        assert uploaded.status_code==200,uploaded.text
        batch=uploaded.json()['batch_id']
        replay=import_sheet()
        assert replay.status_code==200 and replay.json()['batch_id']==batch and replay.json()['replayed']
        assert import_sheet(closing='851').status_code==409
        assert clerk.post('/api/bank-reconciliation/import',headers=ch,data={
            'fund_id':str(bank),'period':month,'opening_balance':'1000','closing_balance':'850'},
            files={'file':('check.csv',io.BytesIO(raw))}).status_code==403
        assert owner.post(f'/api/funds/{bank}/opening',headers=oh,json={'amount':'2000'}).status_code==409
        report=owner.get(f'/api/bank-reconciliation?period={month}&fund_id={bank}').json()
        assert report['bank_closing_piasters']==85000 and report['ledger_closing_piasters']==85000
        assert report['unmatched_bank_count']==3 and len(report['unmatched_ledger'])==3
        assert 'raw_csv' not in report['batch']
        assert reviewer.get(f'/api/bank-reconciliation/{batch}/source.csv').content==raw
        assert viewer.get(f'/api/bank-reconciliation/{batch}/source.csv').status_code==403
        assert owner.post(f'/api/bank-reconciliation/{batch}/approve',headers=oh,json={}).status_code==409
        assert reviewer.post(f'/api/bank-reconciliation/{batch}/approve',headers=rh,json={}).status_code==403
        lines=report['lines']
        mov=report['unmatched_ledger']
        assert owner.post(f'/api/bank-reconciliation/{batch}/match',headers=oh,json={
            'line_id':lines[0]['id'],'movement_id':mov[1]['movement_id']}).status_code==409
        matched_ids=[]
        for line in lines:
            m=next(x for x in mov if x['amount_piasters']==line['amount_piasters'])
            resp=owner.post(f'/api/bank-reconciliation/{batch}/match',headers=oh,json={
                'line_id':line['id'],'movement_id':m['movement_id'],'note':'مطابقة رقمية مع كشف البنك'})
            assert resp.status_code==200,resp.text
            matched_ids.append(resp.json()['match_id'])
            assert owner.post(f'/api/bank-reconciliation/{batch}/match',headers=oh,json={
                'line_id':line['id'],'movement_id':m['movement_id']}).status_code==409
        assert owner.post(f'/api/bank-reconciliation/{batch}/unmatch',headers=oh,json={
            'match_id':matched_ids[0],'reason':'قصير'}).status_code==400
        res=owner.post(f'/api/bank-reconciliation/{batch}/unmatch',headers=oh,json={
            'match_id':matched_ids[0],'reason':'إعادة مطابقة مرجع السند مع البنك'})
        assert res.status_code==200,res.text
        assert owner.post(f'/api/bank-reconciliation/{batch}/approve',headers=oh,json={}).status_code==409
        line=lines[0];m=next(x for x in mov if x['amount_piasters']==line['amount_piasters'])
        assert owner.post(f'/api/bank-reconciliation/{batch}/match',headers=oh,json={
            'line_id':line['id'],'movement_id':m['movement_id']}).status_code==200
        report=owner.get(f'/api/bank-reconciliation?period={month}&fund_id={bank}').json()
        assert report['matched_count']==3 and not report['unmatched_ledger'] and report['unmatched_bank_count']==0
        assert reviewer.post(f'/api/bank-reconciliation/{batch}/approve',headers=rh,json={}).status_code==403
        signed=owner.post(f'/api/bank-reconciliation/{batch}/approve',headers=oh,json={'note':'اعتماد تجريبي بعد مراجعة الحركات'})
        assert signed.status_code==200,signed.text
        assert owner.post(f'/api/bank-reconciliation/{batch}/approve',headers=oh,json={}).status_code==409
        assert owner.post(f'/api/bank-reconciliation/{batch}/void',headers=oh,json={'reason':'محاولة إلغاء بعد الاعتماد'}).status_code==409
        assert owner.post(f'/api/bank-reconciliation/{batch}/unmatch',headers=oh,json={'match_id':matched_ids[1],'reason':'مراجعة حساب معتمد'}).status_code==409
        assert clerk.post('/api/vouchers',headers=ch,json={
            'date':'2026-08-20','kind':'receipt','department_id':dept,'category_id':rev,'shift':'central',
            'from_fund_id':bank,'amount':'1','description':'محاولة بعد اعتماد كشف البنك'}).status_code==409
        assert owner.post(f'/api/vouchers/{r1}/reverse',headers=oh,json={
            'date':'2026-08-21','reason':'محاولة عكس حركة تمت مطابقتها'}).status_code==409
        audit_events=owner.get('/api/audit').json()
        assert audit_events  # audit recorded elsewhere
        csv_out=owner.get(f'/api/bank-reconciliation/export.csv?period={month}&fund_id={bank}')
        assert csv_out.status_code==200 and 'matched' in csv_out.content.decode('utf-8-sig')
        assert clerk.get(f'/api/bank-reconciliation/export.csv?period={month}&fund_id={bank}').status_code==403
        from opening_test_helpers import approve_all_openings
        approve_all_openings(owner,oh,reviewer,rh,month)
        assert owner.post('/api/periods/close',headers=oh,json={'period':month}).status_code==200
        with connect() as db:
            assert db.execute('SELECT count(*) FROM bank_statement_matches WHERE status="active"').fetchone()[0]==3
            assert db.execute('SELECT count(*) FROM fund_movements WHERE fund_id=?',(bank,)).fetchone()[0]==3
            assert db.execute("SELECT count(*) FROM audit_log WHERE action='approve_bank_reconciliation'").fetchone()[0]==1
            assert db.execute("SELECT count(*) FROM bank_statement_batches WHERE status='approved'").fetchone()[0]==1
        # SQLite online backup must include source bank CSV and match history atomically.
        backup=Path(td)/'bank_snapshot.sqlite3'
        with connect() as source, __import__('sqlite3').connect(backup) as target:
            source.backup(target)
        with __import__('sqlite3').connect(backup) as restored:
            assert restored.execute('SELECT raw_csv FROM bank_statement_batches WHERE id=?',(batch,)).fetchone()[0]==raw
            assert restored.execute('SELECT count(*) FROM bank_statement_matches WHERE status=?',('active',)).fetchone()[0]==3
            assert restored.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        # Independent draft correction in a different open month: retain audit history and allow replacement.
        second=owner.post('/api/bank-reconciliation/import',headers=oh,data={
            'fund_id':str(bank),'period':'2026-09','opening_balance':'850','closing_balance':'855'},
            files={'file':('sept.csv',io.BytesIO(b'date,amount,description\n2026-09-15,5,demo transaction\n'),'text/csv')})
        assert second.status_code==200,second.text
        sid=second.json()['batch_id']
        assert owner.post(f'/api/bank-reconciliation/{sid}/void',headers=oh,json={'reason':'الملف تجريبي وغير مكتمل'}).status_code==200
        replacement=owner.post('/api/bank-reconciliation/import',headers=oh,data={
            'fund_id':str(bank),'period':'2026-09','opening_balance':'850','closing_balance':'850'},
            files={'file':('sept_corrected.csv',io.BytesIO(b'date,amount,description\n2026-09-15,0.10,=HYPERLINK(test)\n2026-09-15,-0.10,demo debit\n'),'text/csv')})
        assert replacement.status_code==200,replacement.text
        assert replacement.json()['batch_id']!=sid
        safe_export=owner.get(f'/api/bank-reconciliation/export.csv?period=2026-09&fund_id={bank}')
        assert safe_export.status_code==200 and "'=HYPERLINK" in safe_export.content.decode('utf-8-sig')
        print('PASS — bank CSV evidence, manual matching and undo audit, two-person approval, immutable posting lock, month close, roles and correction')

if __name__=='__main__':run()
