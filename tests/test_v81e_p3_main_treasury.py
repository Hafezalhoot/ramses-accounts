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
    # G2A: the paper receipt for a PHYSICAL external handover matches the
    # original source shift, even though its voucher was posted by the treasury.
    late=send.post('/api/late-entries',headers=sh,json={
      'request_key':'treasury_paper_incident_2026','point_id':external['id'],
      'business_date':day,'shift_code':'morning','incident_reason':'other',
      'custodian_name':'المستلم الفعلي للخزنة الرئيسية','cash_location':'main_safe',
      'counted_cash':'990','note':'إثبات ورقي قديم لتوريدة الكاشير الخارجي إلى الخزنة الرئيسية'})
    assert late.status_code==200,late.text
    incident_id=late.json()['id']
    paper=send.post(f'/api/late-entries/{incident_id}/documents',headers=sh,json={
      'paper_ref':'PAPER-TRANSFER-990','kind':'transfer','amount':'990',
      'method':'cash','note':'محضر تسليم النقدية'})
    assert paper.status_code==200,paper.text
    assert send.post(f'/api/late-entries/{incident_id}/action',headers=sh,json={
      'action':'submit','note':'تم تقديم محضر التوريدة للمطابقة'}).status_code==200
    with connect() as c:
        j_before=c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0]
        mov_before=c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]
    from reviewer_scope_helpers import grant_reviewers_for_test
    grant_reviewers_for_test(o, oh)
    link=review.post(f'/api/late-entries/{incident_id}/documents/{paper.json()["id"]}/link',headers=vh,json={
      'source_type':'voucher','source_id':dep.json()['voucher_id'],
      'note':'محضر الصباحي يطابق توريدة النقدية الأصلية من هذه الوردية'})
    assert link.status_code==200,link.text
    resolved=review.post(f'/api/late-entries/{incident_id}/action',headers=vh,json={
      'action':'resolve','note':'تمت مطابقة أصل محضر التوريد مع الحركة الإلكترونية الموجودة'})
    assert resolved.status_code==200,resolved.text
    with connect() as c:
        assert c.execute('SELECT COUNT(*) FROM gl_journals').fetchone()[0]==j_before
        assert c.execute('SELECT COUNT(*) FROM fund_movements').fetchone()[0]==mov_before
    print('PASS G2A treasury evidence: source shift matched to existing approved main-safe deposit, no double posting')
    print('PASS P3 treasury: 990 physical transfer after source count, central expense 100, shortage 10 adjusted, external next opening 0, balanced GL, no revenue duplicate')
if __name__=='__main__':run()
