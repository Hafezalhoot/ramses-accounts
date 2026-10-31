"""G2K gate: card receipts -> one signed gross/net/fee POS settlement -> bank statement."""
import io
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as d:
        os.environ['RAMSES_DB_PATH']=str(Path(d)/'pos.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='pos_g2k_owner_testing_pw'
        os.environ.pop('GOOGLE_SHEET_ID',None)
        os.environ.pop('GOOGLE_SERVICE_ACCOUNT_JSON',None)
        day=datetime.now(ZoneInfo("Africa/Cairo")).date().isoformat()
        month=day[:7]
        from bootstrap import initialize, connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        import ledger
        owner,clerk,reviewer=(TestClient(app) for _ in range(3))
        def ok(r):
            assert r.status_code==200,(r.status_code,r.text)
            return r.json()
        def denied(r,status):
            assert r.status_code==status,(r.status_code,r.text)
        def login(cli,name,pw):
            return {'X-CSRF-Token':ok(cli.post('/api/login',json={'username':name,'password':pw}))['csrf']}
        oh=login(owner,'owner','pos_g2k_owner_testing_pw')
        for name,role in [('cashier','clerk'),('reviewer','reviewer')]:
            ok(owner.post('/api/users',headers=oh,json={'username':name,'role':role,
                'password':'another_test_passphrase_2026'}))
        ch=login(clerk,'cashier','another_test_passphrase_2026')
        rh=login(reviewer,'reviewer','another_test_passphrase_2026')
        config=ok(owner.get('/api/billing/config'))
        ext=next(x['id'] for x in config['points'] if x['kind']=='external')
        cash=ok(owner.post('/api/funds',headers=oh,json={'code':'g2k_shift_cash','name':'Test cashier G2K','kind':'cash'}))['id']
        clearing=ok(owner.post('/api/funds',headers=oh,json={'code':'bclear_pos_g2k','name':'Test POS clearing','kind':'wallet'}))['id']
        bank=next(x['id'] for x in ok(owner.get('/api/funds')) if x['kind']=='bank')
        ok(owner.post(f'/api/billing/points/{ext}/cash-fund',headers=oh,json={'fund_id':cash}))
        ok(owner.post('/api/billing/channels',headers=oh,json={'method':'card','fund_id':clearing}))
        cashier_id=next(x['id'] for x in ok(owner.get('/api/users')) if x['username']=='cashier')
        ok(owner.post(f'/api/billing/points/{ext}/assign',headers=oh,json={'user_id':cashier_id}))
        ok(clerk.post('/api/shifts/open',headers=ch,json={
           'business_date':day,'shift':'morning','fund_id':cash}))
        patient=ok(clerk.post('/api/billing/patients',headers=ch,json={
            'display_name':'Synthetic Patient G2K','request_id':'g2k_patient_00000001'}))
        case=ok(clerk.post('/api/billing/cases',headers=ch,json={
            'patient_id':patient['id'],'kind':'outpatient','point_id':ext,
            'business_date':day,'request_id':'g2k_case_0000000001'}))
        cid=case['id']
        for i,amt in enumerate(('100','60'),1):
            r=clerk.post(f'/api/billing/cases/{cid}/collect',headers=ch,json={
                'point_id':ext,'parts':[{'method':'card','amount':amt}],
                'request_id':f'g2k_collection_0000000{i}'})
            ok(r)
        outstanding=ok(owner.get('/api/pos/settlements',params={'period':month,'bank_fund_id':bank}))
        assert outstanding['clearing_fund_id']==clearing
        assert len(outstanding['candidates'])==2,outstanding
        parts=[x['id'] for x in outstanding['candidates']]
        denied(clerk.get('/api/pos/settlements',params={'period':month}),403)
        payload={'bank_fund_id':bank,'clearing_fund_id':clearing,
          'settlement_date':day,'payment_part_ids':parts,
          'fee_amount':'2','settlement_ref':'MERCHANT-SET-2026-0818',
          'evidence_note':'Synthetic acquirer settlement proof, no real money',
          'request_key':'g2k_pos_batch_00000001'}
        denied(owner.post('/api/pos/settlements',headers=oh,json={**payload,'fee_amount':'160'}),409)
        s=ok(owner.post('/api/pos/settlements',headers=oh,json=payload))
        sid=s['id']
        assert (s['gross_piasters'],s['fee_piasters'],s['net_piasters'])==(16000,200,15800)
        assert ok(owner.post('/api/pos/settlements',headers=oh,json=payload))['replayed']
        denied(owner.post('/api/pos/settlements',headers=oh,json={**payload,'fee_amount':'3'}),409)
        denied(owner.post('/api/pos/settlements',headers=oh,json={**payload,
           'request_key':'g2k_pos_batch_00000002'}),409)
        denied(owner.post(f'/api/pos/settlements/{sid}/decision',headers=oh,
             json={'decision':'approve','note':'Self approve forbidden'}),403)
        # A reviewer needs scoped bank AND clearing-wallet approval grants.
        denied(reviewer.post(f'/api/pos/settlements/{sid}/decision',headers=rh,
             json={'decision':'approve','note':'Independent synthetic approval'}),403)
        reviewer_id=next(x['id'] for x in ok(owner.get('/api/users')) if x['username']=='reviewer')
        for fund in (clearing,bank):
            ok(owner.post('/api/fund-access',headers=oh,json={
                'user_id':reviewer_id,'fund_id':fund,'can_approve':True,
                'reason':'Test independent G2K POS settlement review'}))
        done=ok(reviewer.post(f'/api/pos/settlements/{sid}/decision',headers=rh,
             json={'decision':'approve','note':'Reviewed synthetic acquirer records'}))
        assert done['status']=='approved' and not done['bank_arrival_confirmed']
        assert done['fee_voucher_id'] and done['transfer_voucher_id']
        denied(reviewer.post(f'/api/pos/settlements/{sid}/decision',headers=rh,
             json={'decision':'approve','note':'Try approve twice'}),409)
        denied(owner.post(f'/api/vouchers/{done["transfer_voucher_id"]}/reverse',headers=oh,
             json={'date':day,'reason':'Try reversing just POS transfer'}),409)
        denied(owner.post(f'/api/vouchers/{done["fee_voucher_id"]}/reverse',headers=oh,
             json={'date':day,'reason':'Try reversing just fee leg'}),409)
        with connect() as c:
            f=lambda fid: c.execute('SELECT opening_piasters+COALESCE((SELECT SUM(amount_piasters) FROM fund_movements WHERE fund_id=?),0) FROM funds WHERE id=?',(fid,fid)).fetchone()[0]
            assert f(clearing)==0 and f(bank)==15800,(f(clearing),f(bank))
            assert c.execute('SELECT status,reviewed_by FROM pos_settlements WHERE id=?',(sid,)).fetchone()['reviewed_by']==reviewer_id
            fee_acc=ledger.account_by_code(c,'5176')
            expense=c.execute('''SELECT SUM(l.debit_piasters-l.credit_piasters) FROM gl_lines l
                JOIN gl_journals j ON j.id=l.journal_id WHERE l.account_id=? AND j.status='posted' ''',(fee_acc,)).fetchone()[0]
            assert expense==200,expense
            cash_vouchers=c.execute('''SELECT COUNT(*) FROM vouchers WHERE id IN (?,?) AND status='approved' ''',
                (done['transfer_voucher_id'],done['fee_voucher_id'])).fetchone()[0]
            assert cash_vouchers==2
            original=c.execute('SELECT COUNT(*) FROM billing_payment_parts WHERE method=\'card\'').fetchone()[0]
            assert original==2
            for sql,arg in [('UPDATE pos_settlements SET fee_piasters=9 WHERE id=?',sid),
                            ('DELETE FROM pos_settlements WHERE id=?',sid),
                            ('DELETE FROM pos_settlement_parts WHERE settlement_id=?',sid)]:
                try:c.execute(sql,(arg,))
                except sqlite3.IntegrityError:pass
                else:raise AssertionError('Approved POS evidence was mutable: '+sql)
        # The bank must STILL independently match its deposited NET amount.
        mismatch=ok(owner.get('/api/accounting/treasury-reconciliation',params={'period':month}))
        assert not mismatch['matched'] and any(x['type']=='bank_not_approved' for x in mismatch['issues'])
        raw=('date,description,amount,reference\n'+day+',Synthetic acquiring deposit,158,MERCHANT-SET-2026-0818\n').encode()
        batch=ok(owner.post('/api/bank-reconciliation/import',headers=oh,
            data={'fund_id':bank,'period':month,'opening_balance':'0','closing_balance':'158'},
            files={'file':('pos_bank_statement.csv',io.BytesIO(raw),'text/csv')}))
        statement=ok(owner.get('/api/bank-reconciliation',params={'period':month,'fund_id':bank}))
        assert statement['unmatched_ledger'][0]['amount_piasters']==15800
        ok(owner.post(f'/api/bank-reconciliation/{batch["batch_id"]}/match',headers=oh,
                 json={'line_id':statement['lines'][0]['id'],
                       'movement_id':statement['unmatched_ledger'][0]['movement_id']}))
        # A second pending POS batch must block the signed bank statement,
        # even while every bank line already matches the net bank voucher.
        ok(clerk.post(f'/api/billing/cases/{cid}/collect',headers=ch,json={
                'point_id':ext,'parts':[{'method':'card','amount':'20'}],
                'request_id':'g2k_collection_pending_0001'}))
        second=ok(owner.get('/api/pos/settlements',params={'period':month,'bank_fund_id':bank}))
        part20=next(x for x in second['candidates'] if x['amount_piasters']==2000)
        pending_payload={**payload,'payment_part_ids':[part20['id']],'fee_amount':'0',
            'settlement_ref':'MERCHANT-PENDING-2026-0818','request_key':'g2k_pos_batch_pending_001'}
        pending=ok(owner.post('/api/pos/settlements',headers=oh,json=pending_payload))
        denied(reviewer.post(f'/api/bank-reconciliation/{batch["batch_id"]}/approve',headers=rh,
                 json={'note':'Bank signoff while another POS batch is pending'}),409)
        denied(owner.post('/api/pos/settlements',headers=oh,json={**pending_payload,
                 'request_key':'g2k_duplicate_open_batch_001'}),409)
        rejection=ok(reviewer.post(f'/api/pos/settlements/{pending["id"]}/decision',headers=rh,
                 json={'decision':'reject','note':'The acquiring report was not yet complete'}))
        assert rejection['status']=='rejected'
        denied(reviewer.post(f'/api/pos/settlements/{pending["id"]}/decision',headers=rh,
                 json={'decision':'approve','note':'Cannot approve rejected report'}),409)
        again=ok(owner.get('/api/pos/settlements',params={'period':month,'bank_fund_id':bank}))
        assert [p['id'] for p in again['candidates']]==[part20['id']],again
        ok(reviewer.post(f'/api/bank-reconciliation/{batch["batch_id"]}/approve',headers=rh,
                 json={'note':'Signed net acquiring deposit, synthetic example'}))
        status=ok(owner.get('/api/accounting/treasury-reconciliation',params={'period':month}))
        assert {x['type'] for x in status['issues']}=={'unclosed_shift'},status
        assert all(f['difference_piasters']==0 for f in status['funds']),status
        latest=ok(owner.get('/api/pos/settlements',params={'period':month,'bank_fund_id':bank}))
        assert len(latest['candidates'])==1 and latest['settlements'][0]['status']=='rejected'
        assert next(x for x in latest['settlements'] if x['status']=='approved')['part_ids']==parts
        # Fee-free POS settlement goes to a separate acquiring bank account.
        # No fake fee voucher may be created just to make a zero expense line.
        otherbank=ok(owner.post('/api/funds',headers=oh,json={
          'code':'g2k_other_settle_bank','name':'POS zero fee synthetic bank','kind':'bank'}))['id']
        ok(owner.post('/api/fund-access',headers=oh,json={'user_id':reviewer_id,
           'fund_id':otherbank,'can_approve':True,'reason':'Second POS bank independent approval'}))
        no_fee={**pending_payload,'bank_fund_id':otherbank,
          'settlement_ref':'MERCHANT-ZERO-FEE-2026-0818',
          'request_key':'g2k_pos_batch_zero_fee_001'}
        check=ok(owner.post('/api/pos/settlements',headers=oh,json=no_fee))
        result=ok(reviewer.post(f'/api/pos/settlements/{check["id"]}/decision',headers=rh,
          json={'decision':'approve','note':'No acquiring fee under this test contract'}))
        assert result['gross_piasters']==2000 and result['fee_piasters']==0
        assert result['net_piasters']==2000 and result['fee_voucher_id'] is None
        with connect() as c:
            wallet_balance=c.execute('''SELECT opening_piasters+
                COALESCE((SELECT SUM(amount_piasters) FROM fund_movements WHERE fund_id=?),0)
                FROM funds WHERE id=?''',(clearing,clearing)).fetchone()[0]
            assert wallet_balance==0,wallet_balance
            assert c.execute('SELECT COUNT(*) FROM pos_settlement_parts WHERE payment_part_id=? AND active=1',
                     (part20['id'],)).fetchone()[0]==1
    print('PASS G2K: 160 gross / 2 fee / 158 bank, rejected batch released, blocked premature bank approval, zero fee')


if __name__=='__main__':run()
