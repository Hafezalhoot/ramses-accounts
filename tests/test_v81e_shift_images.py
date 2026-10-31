"""Evidence files optional unless explicitly required. Test files synthetic."""
import os,tempfile,sys,sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def run():
 with tempfile.TemporaryDirectory() as tmp:
    os.environ['RAMSES_DB_PATH']=str(Path(tmp)/'cash.sqlite3')
    os.environ['RAMSES_ADMIN_USER']='owner';os.environ['RAMSES_ADMIN_PASSWORD']='owner_password_long_2026'
    from bootstrap import initialize,connect
    initialize()
    from fastapi.testclient import TestClient
    from app import app
    owner,clerk,viewer=(TestClient(app) for _ in range(3))
    def login(c,name,pw):
        r=c.post('/api/login',json={'username':name,'password':pw});assert r.status_code==200,r.text
        return {'X-CSRF-Token':r.json()['csrf']}
    oh=login(owner,'owner','owner_password_long_2026')
    for name,role in [('clerk','clerk'),('viewer','viewer')]:
        assert owner.post('/api/users',headers=oh,json={'username':name,'password':'worker_password_long_2026','role':role}).status_code==200
    ch=login(clerk,'clerk','worker_password_long_2026');vh=login(viewer,'viewer','worker_password_long_2026')
    p=next(x for x in owner.get('/api/cashier/plans').json()['points'] if x['kind']=='external')
    f=next(x['id'] for x in owner.get('/api/funds').json() if x['code']=='cash_sub')
    ids={u['username']:u['id'] for u in owner.get('/api/users').json()}
    assert owner.post(f'/api/billing/points/{p["id"]}/cash-fund',headers=oh,json={'fund_id':f}).status_code==200
    assert owner.post(f'/api/billing/points/{p["id"]}/assign',headers=oh,json={'user_id':ids['clerk']}).status_code==200
    day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
    sh=clerk.post('/api/shifts/open',headers=ch,json={'fund_id':f,'business_date':day,'shift':'morning'})
    assert sh.status_code==200,sh.text
    sid=sh.json()['id']
    # Toggle OFF: photos optional; exercise envelope-present path under ON.
    assert owner.post(f'/api/cashier/points/{p["id"]}/policy',headers=oh,json={
        'grace_minutes':120,'require_shift_image':True,'require_envelope_image':True}).status_code==200
    no=clerk.post(f'/api/shifts/{sid}/count',headers=ch,json={'counted_amount':'0','envelope_present':True})
    assert no.status_code==409,no.text
    invalid=clerk.post(f'/api/cashier/shifts/{sid}/attachments/report',files={
        'file':('malware.exe',b'Evil','application/pdf')},headers=ch)
    assert invalid.status_code==400,invalid.text
    doc=b'%PDF-1.7\n1 0 obj <<>> endobj\n%%EOF\n'
    img=clerk.post(f'/api/cashier/shifts/{sid}/attachments/report',files={
        'file':('report.pdf',doc,'application/pdf')},headers=ch)
    assert img.status_code==200,img.text
    att=img.json()['id']
    assert viewer.get(f'/api/cashier/shift-attachments/{att}/download').status_code==403
    assert owner.get(f'/api/cashier/shift-attachments/{att}/download').content==doc
    assert clerk.post(f'/api/cashier/shifts/{sid}/attachments/report',files={
        'file':('same.pdf',doc,'application/pdf')},headers=ch).status_code==409
    noenv=clerk.post(f'/api/shifts/{sid}/count',headers=ch,json={'counted_amount':'0','envelope_present':True})
    assert noenv.status_code==409,noenv.text
    proof=clerk.post(f'/api/cashier/shifts/{sid}/attachments/envelope',files={
        'file':('envelope.pdf',doc,'application/pdf')},headers=ch)
    assert proof.status_code==200,proof.text
    submit=clerk.post(f'/api/shifts/{sid}/count',headers=ch,json={'counted_amount':'0','envelope_present':True})
    assert submit.status_code==200,submit.text
    with connect() as c:
        assert c.execute('SELECT envelope_present FROM shift_sessions WHERE id=?',(sid,)).fetchone()[0]==1
        assert c.execute('SELECT COUNT(*) FROM cashier_shift_attachments WHERE shift_session_id=?',(sid,)).fetchone()[0]==2
        try:
            c.execute('UPDATE cashier_shift_attachments SET file_name=\'tampered.pdf\' WHERE id=?',(att,))
        except sqlite3.IntegrityError:pass
        else:assert False,'Evidence update should be blocked by DB trigger'
    print('PASS optional/required evidence: upload, PDF validation, duplicate, authorization, conditional envelope, immutable BLOB')
if __name__=='__main__':run()
