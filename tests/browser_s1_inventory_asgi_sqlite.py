"""S1 full-stack *in-process* acceptance: Chromium UI -> FastAPI TestClient -> temporary SQLite.

Browser navigation over loopback is blocked by this environment (ERR_BLOCKED_BY_ADMINISTRATOR).
The only replacement is the transport adapter below: browser fetch is forwarded to the
REAL FastAPI app with per-browser TestClient session cookies. NO business API is mocked.
This DOES NOT prove reverse proxy, real HTTP, CSP, TLS, or real hospital network behavior.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
ADMIN_PASSWORD='synthetic-s1-password-never-for-hospital-use'
STAFF_PASSWORD='synthetic-s1-staff-password-for-ephemeral-tests'


def expect(resp,status=200):
    assert resp.status_code==status,(status,resp.status_code,resp.text[:850])
    return resp.json() if status==200 else None


def run():
    with tempfile.TemporaryDirectory(prefix='ramses-s1-e2e-') as folder:
        os.environ.update(RAMSES_DB_PATH=str(Path(folder)/'synthetic.sqlite3'),
                          RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD=ADMIN_PASSWORD,
                          RAMSES_ENVIRONMENT='staging', RAMSES_SECURE_COOKIES='0')
        for key in ('GOOGLE_SERVICE_ACCOUNT_JSON','GOOGLE_SHEET_ID','GOOGLE_SHEET_TARGET'):
            os.environ.pop(key,None)
        sys.path.insert(0,str(ROOT))
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner=TestClient(app)
        owner_csrf=expect(owner.post('/api/login',json={'username':'owner','password':ADMIN_PASSWORD}))['csrf']
        owner_auth={'X-CSRF-Token':owner_csrf}
        users={}
        for name,role in (('s1_clerk','clerk'),('s1_reviewer','reviewer'),('s1_outsider','clerk')):
            users[name]=expect(owner.post('/api/users',headers=owner_auth,json={
                'username':name,'password':STAFF_PASSWORD,'role':role}))['id']
        for name,prepare,approve in (('s1_clerk',True,False),('s1_reviewer',False,True)):
            expect(owner.post('/api/inventory/access',headers=owner_auth,json={
                'user_id':users[name],'can_prepare':prepare,'can_approve':approve,
                'reason':'S1 full-stack synthetic independent role acceptance'}))
        vendor=expect(owner.post('/api/inventory/vendors',headers=owner_auth,json={
            'code':'S1-VENDOR','name':'مورد تجربة التشغيل المتصل'}))['id']
        item=expect(owner.post('/api/inventory/items',headers=owner_auth,json={
            'code':'S1-CONSUMABLE','name':'ضماد صناعي غير دوائي','unit':'piece'}))['id']
        with connect() as c:
            before_gl=c.execute('SELECT COUNT(*) FROM gl_lines').fetchone()[0]
            before_qty=c.execute('SELECT COUNT(*) FROM inventory_receipts').fetchone()[0]
        # Always use authentic FastAPI sessions; each virtual browser has its own jar.
        bridge_calls=[]
        def virtual_browser(pw,login_user,area):
            session=TestClient(app)
            browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',
              args=['--no-sandbox','--disable-dev-shm-usage'])
            page=browser.new_page(viewport={'width':375,'height':800})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            def forward(source,args):
                path=args['path']
                assert path.startswith('/api/'),path
                raw=args.get('body')
                r=session.request(args.get('method','GET'),path,headers=args.get('headers') or {},
                                  content=raw.encode('utf8') if raw is not None else None)
                bridge_calls.append((login_user,args.get('method','GET'),path,r.status_code))
                return {'status':r.status_code,'body':r.text,'content_type':r.headers.get('content-type','application/json')}
            page.expose_binding('__ramses_asgi',forward)
            # Load the actual HTML, CSS and all shipped JS; browser fetch uses real ASGI handlers + SQLite.
            html=(ROOT/'static/index.html').read_text(encoding='utf8')
            html=re.sub(r'<script src="/static/[^\"]+" defer></script>','',html)
            html=html.replace('<link rel="stylesheet" href="/static/styles.css">','')
            page.set_content(html)
            page.add_style_tag(content=(ROOT/'static/styles.css').read_text(encoding='utf8'))
            page.add_script_tag(content='''
              window.__s1_pending=0;
              window.fetch=async (path,opts={})=>{
                window.__s1_pending++;
                try {
                  const result=await window.__ramses_asgi({path:String(path),method:opts.method||'GET',
                    headers:opts.headers||{},body:typeof opts.body==='string'?opts.body:null});
                  return new Response(result.body,{status:result.status,
                    headers:{'content-type':result.content_type}});
                } finally { window.__s1_pending--; }
              };
            ''')
            for js in ('inventory_ui.js','billing.js','pos_settlements_ui.js','cashier_ops_ui.js',
                       'financial_corrections_ui.js','late_entry_ui.js','app.js'):
                page.add_script_tag(content=(ROOT/'static'/js).read_text(encoding='utf8'))
            page.locator('#loginPage').wait_for(state='visible',timeout=14000)
            page.locator('#loginForm [name="username"]').fill(login_user)
            page.locator('#loginForm [name="password"]').fill(STAFF_PASSWORD)
            page.locator('#loginForm button[type="submit"]').click()
            page.locator('#shell').wait_for(state='visible',timeout=15000)
            page.locator('#showSidebar').click()
            page.locator('#sidebar.open [data-view="inventory"]').click()
            page.locator('[data-inv-tab]').first.wait_for(timeout=15000)
            page.locator(f'[data-inv-tab="{area}"]').click()
            return browser,page,errors,session
        with sync_playwright() as pw:
            clerk_browser,clerk_page,clerk_errors,clerk_session=virtual_browser(pw,'s1_clerk','stock')
            try:
                receipt=clerk_page.locator('#invReceiptForm')
                receipt.wait_for(state='visible')
                receipt.locator('[name="vendor_id"]').select_option(str(vendor))
                receipt.locator('[name="item_id"]').select_option(str(item))
                receipt.locator('[name="invoice_ref"]').fill('S1-GRN-ORIGINAL-SYNTHETIC')
                receipt.locator('[name="evidence_ref"]').fill('S1-GRN-DOCK-SIGNED-SYNTHETIC')
                receipt.locator('[name="quantity"]').fill('3')
                receipt.locator('[name="unit_cost"]').fill('15.00')
                receipt.locator('button[type="submit"]').click()
                clerk_page.get_by_text('تم إرسال محضر الاستلام للمراجعة').wait_for(timeout=15000)
                with connect() as c:
                    row=c.execute("SELECT id,status,created_by FROM inventory_receipts WHERE invoice_ref='S1-GRN-ORIGINAL-SYNTHETIC'").fetchone()
                    assert row and row['status']=='pending' and row['created_by']==users['s1_clerk'],dict(row) if row else None
                    receipt_id=row['id']
                    assert c.execute('SELECT COUNT(*) FROM gl_lines').fetchone()[0]==before_gl
                assert clerk_page.locator('[data-inv-tab="stock"]').get_attribute('aria-selected')=='true'
                reviewer_browser,reviewer_page,reviewer_errors,reviewer_session=virtual_browser(pw,'s1_reviewer','stock')
                try:
                    assert reviewer_page.locator('#invReceiptForm').count()==0
                    reviewer_page.locator(f'[data-inv-decision="receipts:{receipt_id}:approve"]').click()
                    reviewer_page.locator('#modalFields [name="note"]').fill('S1 independent physical GRN verified in temporary data')
                    reviewer_page.locator('#modalConfirm').click()
                    reviewer_page.get_by_text('تم تسجيل قرار المراجعة').wait_for(timeout=15000)
                    with connect() as c:
                        row=c.execute('SELECT status FROM inventory_receipts WHERE id=?',(receipt_id,)).fetchone()
                        assert row['status']=='approved',row
                        assert c.execute('SELECT COUNT(*) FROM gl_lines').fetchone()[0]>before_gl
                    data=expect(reviewer_session.get('/api/inventory/overview'))
                    stock=next(x for x in data['items'] if x['id']==item)
                    assert stock['quantity_on_hand']==3,stock
                    detail=expect(reviewer_session.get('/api/inventory/supplier-control-ledger'))
                    assert detail['control_2200_piasters']>=4500,detail
                    # Live server-enforced denial: independent user's role but no current inventory grant.
                    outsider=TestClient(app)
                    expect(outsider.post('/api/login',json={'username':'s1_outsider','password':STAFF_PASSWORD}))
                    expect(outsider.get('/api/inventory/overview'),403)
                    assert not clerk_errors and not reviewer_errors,(clerk_errors,reviewer_errors)
                    assert any('POST'==method and '/api/inventory/receipts/' in path and status==200
                               for _,method,path,status in bridge_calls),bridge_calls[-18:]
                    print('PASS S1 real Chromium UI -> in-process FastAPI TestClient -> temp SQLite: clerk GRN, independent reviewer, GL 1100/2200, FIFO stock, unauthorized denial')
                    print('LIMITATION: Browser->ASGI binding bypasses loopback HTTP; not a live network/reverse-proxy test.')
                finally:
                    reviewer_page.wait_for_function('window.__s1_pending===0',timeout=5000)
                    reviewer_browser.close()
            finally:
                clerk_page.wait_for_function('window.__s1_pending===0',timeout=5000)
                clerk_browser.close()

if __name__=='__main__':run()
