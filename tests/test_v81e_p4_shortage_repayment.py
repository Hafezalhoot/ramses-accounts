"""External drawer to internal central treasury: one physical deposit, no double revenue."""
import os,sys,tempfile
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def run():
 with tempfile.TemporaryDirectory() as temp:
    os.environ['RAMSES_DB_PATH']=str(Path(temp)/'ledger.sqlite3')
    os.environ['RAMSES_ADMIN_USER']='owner';os.environ['RAMSES_ADMIN_PASSWORD']='owner_long_secret_2026'
    from bootstrap import initialize,connect
    initialize()
    from app import app
    from fastapi.testclient import TestClient
    o,send,recv,review=(TestClient(app) for _ in range(4))
    def login(c,u,p):
        r=c.post('/api/login',json={'username':u,'password':p});assert r.status_code==200,r.text
        return {'X-CSRF-Token':r.json()['csrf']}
    oh=login(o,'owner','owner_long_secret_2026')
    for u,role in [('sender','clerk'),('receiver','clerk'),('reviewer','reviewer')]:
        assert o.post('/api/users',headers=oh,json={'username':u,'password':'worker_long_secret_2026','role':role}).status_code==200
    sh=login(send,'sender','worker_long_secret_2026')
    rh=login(recv,'receiver','worker_long_secret_2026')
    vh=login(review,'reviewer','worker_long_secret_2026')
    ids={u['username']:u['id'] for u in o.get('/api/users').json()}
    pts=o.get('/api/cashier/plans').json()['points'];external=next(p for p in pts if p['kind']=='external');internal=next(p for p in pts if p['kind']=='internal')
    funds={x['code']:x['id'] for x in o.get('/api/funds').json()}
    cash_main=funds['cash_main'];cash_sub=funds['cash_sub']
    for point,fund in [(external,cash_sub),(internal,cash_main)]:
        r=o.post(f'/api/billing/points/{point["id"]}/cash-fund',headers=oh,json={'fund_id':fund});assert r.status_code==200,r.text
    for point,user in [(external,'sender'),(external,'receiver'),(internal,'receiver')]:
        r=o.post(f'/api/billing/points/{point["id"]}/assign',headers=oh,json={'user_id':ids[user]});assert r.status_code==200,r.text
    r=o.post(f'/api/funds/{cash_sub}/opening',headers=oh,json={'amount':'1000'});assert r.status_code==200,r.text
    day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
    main=recv.post('/api/shifts/open',headers=rh,json={'business_date':day,'shift':'treasury','fund_id':cash_main})
    assert main.status_code==200,main.text
    main_id=main.json()['id']
    external_shift=send.post('/api/shifts/open',headers=sh,json={'business_date':day,'shift':'morning','fund_id':cash_sub})
    assert external_shift.status_code==200,external_shift.text
    external_id=external_shift.json()['id']
    cnt=send.post(f'/api/shifts/{external_id}/count',headers=sh,json={'counted_amount':'990','note':'تم العثور على عجز عشرة جنيهات'})
    assert cnt.status_code==200,cnt.text
    h=recv.post(f'/api/shifts/{external_id}/handoff',headers=rh,json={'counted_amount':'990','decision':'accept','note':'تم استلام مبلغ 990 فعليًا'})
    assert h.status_code==200,h.text
    dep=recv.post('/api/cashier/treasury-deposits',headers=rh,json={
        'source_shift_id':external_id,'amount':'990','note':'توريد صباحي بموجب محضر التسليم'})
    assert dep.status_code==200,dep.text
    assert dep.json()['amount_piasters']==99000
    # Can't receive more physical cash than independently counted.
    dup=recv.post('/api/cashier/treasury-deposits',headers=rh,json={
        'source_shift_id':external_id,'amount':'1','note':'توريد مكرر ممنوع'})
    assert dup.status_code==409,dup.text
    details=o.get(f'/api/shifts/{main_id}/daily-report').json()
    assert details['cash_credited_piasters']==99000,details
    # Subsequent external shift starts with 0 remaining in that till.
    later=recv.post('/api/shifts/open',headers=rh,json={'business_date':day,'shift':'evening','fund_id':cash_sub})
    assert later.status_code==200,later.text
    later_id=later.json()['id']
    with connect() as c:
        assert c.execute('SELECT opening_piasters FROM shift_sessions WHERE id=?',(later_id,)).fetchone()[0]==0
    # Hospital expenses belong to the central treasury's current shift.
    look=o.get('/api/lookups').json();dept=next(x['id'] for x in look['departments'] if x['code']=='ADMIN')
    category=next(x['id'] for x in look['categories'] if x['code']=='utilities')
    v=recv.post('/api/vouchers',headers=rh,json={'date':day,'kind':'payment','department_id':dept,
         'category_id':category,'from_fund_id':cash_main,'shift':'central','amount':'100',
         'description':'اختبار مصروف مرافق من الخزنة الرئيسية'})
    assert v.status_code==200,v.text
    ok=review.post(f'/api/vouchers/{v.json()["id"]}/decision',headers=vh,json={'decision':'approve','reason':'مستند مصروف تجريبي'})
    assert ok.status_code==200,ok.text
    assert o.get(f'/api/shifts/{main_id}/daily-report').json()['cash_debited_piasters']==10000
    # Original shortage is resolved in current period; source balances match.
    prop=review.post(f'/api/shifts/{external_id}/variance-propose',headers=vh,json={
        'explanation':'عجز عشرة جنيهات اكتشف عند نهاية وردية الكاشير الخارجي'})
    assert prop.status_code==200,prop.text
    appr=o.post(f'/api/shifts/{external_id}/variance-decision',headers=oh,json={
        'decision':'approve','reason':'اعتماد فرق العهدة قيد التسوية بمعرفة المالك'})
    assert appr.status_code==200,appr.text
    with connect() as c:
        fund_amount=lambda fid:c.execute('SELECT opening_piasters+(SELECT COALESCE(SUM(amount_piasters),0) FROM fund_movements WHERE fund_id=?) FROM funds WHERE id=?',(fid,fid)).fetchone()[0]
        assert fund_amount(cash_sub)==0, fund_amount(cash_sub)
        assert fund_amount(cash_main)==89000,fund_amount(cash_main)
        transfer=c.execute('SELECT * FROM vouchers WHERE id=?',(dep.json()['voucher_id'],)).fetchone()
        assert transfer['kind']=='transfer' and transfer['status']=='approved'
        journal=c.execute('SELECT id FROM gl_journals WHERE origin=\'voucher\' AND source_id=?',(transfer['id'],)).fetchone()
        assert journal and c.execute('SELECT SUM(debit_piasters)-SUM(credit_piasters) FROM gl_lines WHERE journal_id=?',(journal[0],)).fetchone()[0]==0
        movements=c.execute('SELECT fund_id,shift_session_id,amount_piasters FROM fund_movements WHERE voucher_id=?',(transfer['id'],)).fetchall()
        assert sorted((r['fund_id'],r['shift_session_id'],r['amount_piasters']) for r in movements)==sorted([(cash_sub,None,-99000),(cash_main,main_id,99000)])
    case_id=prop.json()['case_id']
    path='/api/cashier/shortage-repayments'
    def receipt(amt,key,who=recv,headers=rh):
        return who.post(path,headers=headers,json={'variance_case_id':case_id,'amount':amt,
            'receipt_key':key,'evidence_note':'استلام نقدية من موظف لتسوية عجز العهدة بناء على إقرار طوعي'})
    first=receipt('6','ramses_recovery_00000001')
    assert first.status_code==200,first.text
    assert first.json()['remaining_piasters']==400
    again=receipt('6','ramses_recovery_00000001')
    assert again.status_code==200 and again.json()['replayed'],again.text
    bad=receipt('5','ramses_recovery_00000002')
    assert bad.status_code==409,bad.text
    selfpay=receipt('4','ramses_recovery_00000003',send,sh)
    assert selfpay.status_code==403,selfpay.text
    rest=receipt('4','ramses_recovery_00000004')
    assert rest.status_code==200 and rest.json()['remaining_piasters']==0,rest.text
    with connect() as c:
        balance=c.execute('SELECT opening_piasters+(SELECT COALESCE(SUM(amount_piasters),0) FROM fund_movements WHERE fund_id=?) FROM funds WHERE id=?',(cash_main,cash_main)).fetchone()[0]
        assert balance==90000,balance
        account=c.execute('SELECT id FROM gl_accounts WHERE code=?',('1190',)).fetchone()[0]
        dr,cr=c.execute("SELECT SUM(l.debit_piasters),SUM(l.credit_piasters) FROM gl_lines l JOIN gl_journals j ON j.id=l.journal_id WHERE l.account_id=? AND j.status='posted'",(account,)).fetchone()
        assert (dr,cr)==(1000,1000),(dr,cr)
        assert c.execute('SELECT COUNT(*) FROM cashier_shortage_repayments').fetchone()[0]==2
        assert c.execute("SELECT COUNT(*) FROM gl_journals WHERE status='posted' AND origin='voucher'").fetchone()[0]==5
        row=c.execute('SELECT id FROM cashier_shortage_repayments LIMIT 1').fetchone()[0]
        try:c.execute('UPDATE cashier_shortage_repayments SET amount_piasters=1 WHERE id=?',(row,))
        except Exception:pass
        else:raise AssertionError('Audit row update allowed')
    overview=o.get(path)
    assert overview.status_code==200 and overview.json()['cases'][0]['outstanding_piasters']==0
    print('PASS P4 repayments: 6+4 settled, no overpay, immutable rows, suspense 1190 cleared, GL balanced')
    print('PASS P3 treasury: 990 physical transfer after source count, central expense 100, shortage 10 adjusted, external next opening 0, balanced GL, no revenue duplicate')
if __name__=='__main__':run()
