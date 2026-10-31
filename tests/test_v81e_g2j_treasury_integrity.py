"""G2J release gate: cashbook/GL/physical shift/bank signed-evidence agreement.
All records synthetic and confined to a throwaway SQLite database.
"""
import io
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as td:
        os.environ['RAMSES_DB_PATH']=str(Path(td)/'treasury.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='g2j_owner_test_secure_pw'
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        import ledger
        owner,reviewer,clerk,viewer=(TestClient(app) for _ in range(4))

        def login(cli, username, password):
            r=cli.post('/api/login',json={'username':username,'password':password})
            assert r.status_code==200,(r.status_code,r.text)
            return {'X-CSRF-Token':r.json()['csrf']}
        def ok(r):
            assert r.status_code==200,(r.status_code,r.text)
            return r.json()
        oh=login(owner,'owner','g2j_owner_test_secure_pw')
        for name,role in [('reviewer','reviewer'),('clerk','clerk'),('viewer','viewer')]:
            ok(owner.post('/api/users',headers=oh,json={'username':name,'role':role,
                'password':'secure_test_password_1234'}))
        rh=login(reviewer,'reviewer','secure_test_password_1234')
        login(clerk,'clerk','secure_test_password_1234')
        login(viewer,'viewer','secure_test_password_1234')
        fund_list=ok(owner.get('/api/funds'))
        wallet=next(f['id'] for f in fund_list if f['kind']=='wallet')
        bank=next(f['id'] for f in fund_list if f['kind']=='bank')
        cash=next(f['id'] for f in fund_list if f['kind']=='cash')
        users=ok(owner.get('/api/users'))
        reviewer_id=next(u['id'] for u in users if u['username']=='reviewer')
        for fund in (wallet,bank):
            ok(owner.post('/api/fund-access',headers=oh,json={'user_id':reviewer_id,
                'fund_id':fund,'can_approve':True,
                'reason':'Independent bank/wallet review for G2J test'}))
        lk=ok(owner.get('/api/lookups'))
        dept=lk['departments'][0]['id']
        rev=next(x['id'] for x in lk['categories'] if x['code']=='other_revenue')
        month='2026-08'
        r=ok(owner.get('/api/accounting/treasury-reconciliation',params={'period':month}))
        assert r['matched'] and r['issue_count']==0,r
        assert clerk.get('/api/accounting/treasury-reconciliation',params={'period':month}).status_code==403
        assert viewer.get('/api/accounting/treasury-reconciliation',params={'period':month}).status_code==200
        assert clerk.get('/api/accounting/treasury-reconciliation.csv',params={'period':month}).status_code==403
        assert owner.get('/api/accounting/treasury-reconciliation.csv',params={'period':month}).status_code==200
        assert owner.get('/api/accounting/treasury-reconciliation',params={'period':'2026-13'}).status_code==400

        def voucher(kind,amount,source,target=None,category=None):
            body={'date':'2026-08-14','kind':kind,'department_id':dept,'category_id':category,
                  'shift':'central','from_fund_id':source,'to_fund_id':target,
                  'amount':str(amount),'description':'G2J synthetic bank/cashbook transaction'}
            v=ok(owner.post('/api/vouchers',headers=oh,json=body))
            ok(reviewer.post(f'/api/vouchers/{v["id"]}/decision',headers=rh,
                             json={'decision':'approve'}))
            return v['id']

        receipt=voucher('receipt',200,wallet,category=rev)
        assert ok(owner.get('/api/accounting/treasury-reconciliation',params={'period':month}))['matched']
        transfer=voucher('transfer',50,wallet,target=bank)
        need_bank=ok(owner.get('/api/accounting/treasury-reconciliation',params={'period':month}))
        assert not need_bank['matched'] and any(x['type']=='bank_not_approved' for x in need_bank['issues']),need_bank
        assert owner.post('/api/periods/close',headers=oh,json={'period':month}).status_code==409

        raw=b'date,description,amount,reference\n2026-08-14,G2J synthetic incoming,50,TEST-1\n'
        b=ok(owner.post('/api/bank-reconciliation/import',headers=oh,
              data={'fund_id':bank,'period':month,'opening_balance':'0','closing_balance':'50'},
              files={'file':('synthetic_statement.csv',io.BytesIO(raw),'text/csv')}))
        bank_report=ok(owner.get('/api/bank-reconciliation',params={'period':month,'fund_id':bank}))
        ok(owner.post(f'/api/bank-reconciliation/{b["batch_id"]}/match',headers=oh,json={
            'line_id':bank_report['lines'][0]['id'],
            'movement_id':bank_report['unmatched_ledger'][0]['movement_id']}))
        ok(reviewer.post(f'/api/bank-reconciliation/{b["batch_id"]}/approve',headers=rh,
                         json={'note':'Independently signed synthetic bank record'}))
        report=ok(owner.get('/api/accounting/treasury-reconciliation',params={'period':month}))
        assert report['matched'] and report['issue_count']==0,report
        assert sum(f['movement_piasters'] for f in report['funds'])==20000,report  # transfer nets to zero
        assert all(f['difference_piasters']==0 for f in report['funds'])

        # A posted cashbook leg and a signed bank statement are append-only at DB level.
        with connect() as c:
            movement_id=c.execute('SELECT id FROM fund_movements WHERE voucher_id=?',(receipt,)).fetchone()[0]
            for query,arg in [
               ('UPDATE fund_movements SET amount_piasters=99 WHERE id=?',movement_id),
               ('DELETE FROM fund_movements WHERE id=?',movement_id),
               ('UPDATE bank_statement_batches SET closing_piasters=1 WHERE id=?',b['batch_id']),
               ('UPDATE bank_statement_lines SET amount_piasters=1 WHERE batch_id=?',b['batch_id']),
               ('DELETE FROM bank_statement_matches WHERE line_id=?',bank_report['lines'][0]['id']),
            ]:
                try:
                    c.execute(query,(arg,))
                except sqlite3.IntegrityError:
                    pass
                else:
                    raise AssertionError('Immutable financial evidence could be modified: '+query)

        # Reproduce historic non-source-linked fund GL posting; a balanced trial
        # balance is NOT sufficient to let the hospital close its month.
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            fa=ledger.ensure_fund_account(c,wallet)
            other=ledger.account_by_code(c,'4190')
            ledger._journal(c,entry_date='2026-08-15',memo='Synthetic legacy invalid manual fund posting',
                 origin='manual',source_id=None,created_by=users[0]['id'],reviewed_by=reviewer_id,
                 lines=[(fa,1100,0,None),(other,0,1100,None)])
            c.commit()
        bad=ok(owner.get('/api/accounting/treasury-reconciliation',params={'period':month}))
        assert not bad['matched'],bad
        assert any(x['type']=='orphan_gl' for x in bad['issues']),bad
        wallet_row=next(x for x in bad['funds'] if x['id']==wallet)
        assert wallet_row['difference_piasters']==1100,bad
        assert not ok(owner.get('/api/periods/preflight',params={'period':month}))['ready']
        assert owner.post('/api/periods/close',headers=oh,json={'period':month}).status_code==409

        # Physical proof is separate from balanced GL. A corrupt old closed
        # shift cannot be treated as an independently reconciled till.
        with connect() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('DELETE FROM gl_journals WHERE 1=0')  # no ledger deletion
            c.execute('''INSERT INTO shift_sessions(business_date,shift,fund_id,responsible_id,
                 opened_at,opening_piasters,status,counted_piasters,expected_piasters,
                 reviewed_by,reviewed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
               ('2026-08-30','morning',cash,users[0]['id'],'2026-08-30T08:00:00Z',0,
                'closed',1200,1200,reviewer_id,'2026-08-30T16:00:00Z'))
            c.commit()
        physical=ok(owner.get('/api/accounting/treasury-reconciliation',params={'period':month}))
        assert any(x['type']=='shift_count' for x in physical['issues']),physical
        print('PASS G2J: source-voucher GL agreement, signed bank evidence, legacy phantom GL, independent physical count, close-block and roles')


if __name__=='__main__':
    run()
