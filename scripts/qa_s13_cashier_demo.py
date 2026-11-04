"""Opt-in real HTTPS cashier exercise on the configured synthetic preview only.

Requires private/S13_CASHIER.json prepared for this preview. Creates one clearly
fabricated patient/receipt, independently closes that sample shift, and leaves
the next shift open for the user's practice. Never part of unattended CI.
"""
import argparse,json,os,tempfile
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exercise-synthetic-cashier',action='store_true',required=True)
    parser.add_argument('--evidence-dir',type=Path,default=ROOT/'private/s13-browser')
    args=parser.parse_args()
    from playwright.sync_api import sync_playwright
    from browser_helpers import chromium_options
    import requests
    path=ROOT/'private/S13_CASHIER.json';data=json.loads(path.read_text())
    state=json.loads((ROOT/'private/mobile-gateway/processes.json').read_text())
    gate=json.loads((ROOT/'private/mobile-gateway/access.json').read_text())
    url=state['url'];parsed=urlsplit(url)
    assert parsed.scheme=='https' and parsed.hostname.endswith('.trycloudflare.com') and data['url']==url
    args.evidence_dir.mkdir(parents=True,exist_ok=True)
    def save():
        # Preserve the preceding checkpoint even if the process stops mid-write.
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,delete=False) as checkpoint:
            json.dump(data,checkpoint,ensure_ascii=False,indent=2)
            checkpoint.flush();os.fsync(checkpoint.fileno())
        os.replace(checkpoint.name,path)
    clients={}
    for name,account in data['accounts'].items():
        s=requests.Session();s.auth=(gate['username'],gate['password'])
        r=s.post(url+'/api/login',json={'username':name,'password':account['password']},timeout=30);r.raise_for_status()
        s.headers['X-CSRF-Token']=r.json()['csrf']
        me=s.get(url+'/api/me',timeout=30).json();assert me['environment']=='free-preview'
        clients[name]=s
    def post(name,path,body=None):
        r=clients[name].post(url+path,json=body,timeout=30)
        assert r.status_code==200,(path,r.status_code,r.text[:500]);return r.json()
    def login(context):
        page=context.new_page();page.goto(url,wait_until='networkidle',timeout=45000)
        page.locator('#loginForm [name=username]').fill('cashier_external')
        page.locator('#loginForm [name=password]').fill(data['accounts']['cashier_external']['password'])
        page.locator('#loginForm button[type=submit]').click();page.locator('#shell').wait_for(state='visible')
        return page
    def commit_click(page,selector,path):
        with page.expect_response(lambda r:r.request.method=='POST' and urlsplit(r.url).path==path,timeout=30000) as pending:
            page.locator(selector).click()
        r=pending.value;assert r.status==200,(path,r.status,r.text());return r.json()
    credentials={'username':gate['username'],'password':gate['password'],'origin':url}
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,**chromium_options())
        try:
            context=browser.new_context(viewport={'width':1440,'height':1000},http_credentials=credentials)
            page=login(context);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.locator('#mainNav [data-view=billing]').click();page.locator('#billingNewCase').wait_for()
            if not data.get('demo_complete'):
                # A failed UI action is diagnosed and resumed from private checkpoints.
                demo=data.setdefault('demo',{});save()
                if not demo.get('shift'):
                    page.locator('#billingOpenShift').click()
                    page.locator('#modalForm [name=shift]').select_option('night')
                    demo['shift']=commit_click(page,'#modalConfirm','/api/shifts/open')['id'];save()
                if not demo.get('case'):
                    page.locator('#billingNewCase').click()
                    page.locator('#modalForm [name=patient]').fill('مريض توضيح دورة الكاشير — وهمي بالكامل')
                    page.locator('#modalForm [name=kind]').select_option('outpatient')
                    demo['case']=commit_click(page,'#modalConfirm','/api/billing/cases')['id'];save()
                page.locator(f'[data-billing-open-case="{demo["case"]}"]').click()
                if not demo.get('line'):
                    page.locator('#billingAddLine').click()
                    page.locator('#modalForm [name=service_id]').select_option(str(data['services']['DEMO_FOLLOWUP_150']))
                    demo['line']=commit_click(page,'#modalConfirm',f'/api/billing/cases/{demo["case"]}/services')['id'];save()
                if not demo.get('attested'):
                    evidence=clients['demo_clinician'].get(url+f'/api/billing/clinical/lines/{demo["line"]}/evidence',timeout=30)
                    if evidence.status_code==404:
                        post('demo_clinician',f'/api/billing/clinical/lines/{demo["line"]}/attest',{'evidence_reference':'SYNTHETIC-S13-BROWSER-ATTEST-0001'})
                    else:assert evidence.status_code==200,evidence.text
                    demo['attested']=True;save()
                page.evaluate("navigate('billing')")
                if not demo.get('draft'):
                    page.locator('#billingDraft:not([disabled])').wait_for()
                    demo['draft']=commit_click(page,'#billingDraft',f'/api/billing/cases/{demo["case"]}/drafts')['id'];save()
                if not demo.get('invoice'):
                    invoice=commit_click(page,f'[data-billing-issue="{demo["draft"]}"]',f'/api/billing/drafts/{demo["draft"]}/issue')
                    demo['invoice']=invoice['id'];save()
                if not demo.get('receipt'):
                    page.locator(f'[data-billing-collect="{demo["invoice"]}"]').click()
                    page.locator('#modalForm [name=method_1]').select_option('cash')
                    page.locator('#modalForm [name=amount_1]').fill('150.00')
                    demo['receipt']=commit_click(page,'#modalConfirm',f'/api/billing/cases/{demo["case"]}/collect')['id'];save()
                    page.locator('#modalText a[href$="/print"]').wait_for()
                    page.locator('#modalClose').click()
                page.evaluate("navigate('billing')");page.locator(f'a[href="/api/billing/invoices/{demo["invoice"]}/print"]').wait_for()
                page.screenshot(path=str(args.evidence_dir/'cashier-invoice-desktop.png'),full_page=True)
                page.locator('#mainNav [data-view=shifts]').click()
                selector=f'[data-shift-action=count][data-shift-id="{demo["shift"]}"]:visible'
                if not demo.get('counted'):
                    page.locator(selector).click();page.locator('#modalForm [name=counted_amount]').fill('150.00')
                    page.locator('#modalForm [name=note]').fill('جرد تجريبي — عد فعلي 150 جنيه')
                    commit_click(page,'#modalConfirm',f'/api/shifts/{demo["shift"]}/count');demo['counted']=True;save()
                if not demo.get('received'):
                    if not data.get('treasury_shift'):
                        treasury=post('cashier_treasury','/api/shifts/open',{'business_date':data['day'],'shift':'treasury','fund_id':data['treasury_fund']})
                        data['treasury_shift']=treasury['id'];save()
                    post('cashier_treasury',f'/api/shifts/{demo["shift"]}/handoff',{'counted_amount':'150.00','decision':'accept','note':'استلام مستقل لتجربة الكاشير'})
                    demo['received']=True;save()
                if not demo.get('deposited'):
                    post('cashier_treasury','/api/cashier/treasury-deposits',{'source_shift_id':demo['shift'],'amount':'150.00','note':'توريد وهمي موثق إلى الخزينة التجريبية','client_request_id':'s13_browser_demo_treasury_0001'})
                    demo['deposited']=True;save()
                if not demo.get('closed'):
                    post('cashier_reviewer',f'/api/shifts/{demo["shift"]}/review',{'decision':'approve','reason':'جرد واستلام مستقلان — اختبار فقط'})
                    demo['closed']=True;save()
                data['practice_shift']=post('cashier_external','/api/shifts/open',{'business_date':data['day'],'shift':'morning','fund_id':data['external_fund']})['id']
                data['demo_complete']=True;save()
                print('PASS real HTTPS cashier UI: open shift, new patient, service order, independent clinical API proof, draft, issue, cash collection, count; independent treasury/reviewer APIs close sample shift',flush=True)
            assert not errors,errors
            context.close()
            demo=data['demo'];screens=[]
            for width in (375,1440):
                context=browser.new_context(viewport={'width':width,'height':1000},http_credentials=credentials)
                page=login(context);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.evaluate("navigate('billing')");page.locator('#billingNewCase').wait_for()
                page.locator(f'[data-billing-open-case="{demo["case"]}"]').click()
                invoice_link=page.locator(f'a[href="/api/billing/invoices/{demo["invoice"]}/print"]');invoice_link.wait_for()
                with context.expect_page() as opened:invoice_link.click()
                printed=opened.value;printed.wait_for_load_state('networkidle');assert '150.00' in printed.locator('main').inner_text();printed.close()
                page.locator(f'[data-billing-receipt="{demo["receipt"]}"]').click()
                page.locator('#modalText a[href$="/print"]').wait_for();page.locator('#modalClose').click()
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                page.screenshot(path=str(args.evidence_dir/f'cashier-invoice-{width}.png'),full_page=True)
                for kind,path,query in (
                    ('invoice',f'/api/billing/invoices/{demo["invoice"]}/print',''),
                    ('receipt',f'/api/billing/collections/{demo["receipt"]}/print','?paper=80mm'),
                    ('shift',f'/api/shifts/{demo["shift"]}/daily-report/print','')):
                    page.goto(url+path+query,wait_until='networkidle',timeout=45000)
                    page.evaluate('document.fonts.ready')
                    assert page.evaluate("Array.from(document.fonts).some(f=>f.family==='Cairo'&&f.status==='loaded')")
                    assert page.evaluate('document.documentElement.dir')=='rtl'
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    if kind=='shift':assert 'مقفلة ومعتمدة' in page.locator('main').inner_text()
                    page.evaluate('window.print=()=>{window.__printInvoked=true}')
                    page.locator('#printDocument').click();assert page.evaluate('window.__printInvoked===true')
                    page.screenshot(path=str(args.evidence_dir/f'{kind}-print-{width}.png'),full_page=True)
                    if width==1440:
                        options={'format':'A4'} if kind!='receipt' else {'width':'80mm','height':'240mm','margin':{'top':'4mm','bottom':'4mm','left':'4mm','right':'4mm'}}
                        page.pdf(path=str(args.evidence_dir/f'sample-{kind}.pdf'),print_background=True,**options)
                assert not errors,errors
                print(f'PASS real HTTPS Chrome {width}: cashier login, invoice/receipt links, three RTL print views, local Cairo, no overflow/JS errors',flush=True)
                context.close()
        finally:browser.close()


if __name__=='__main__':main()
