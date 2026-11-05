"""Opt-in synthetic S14 exercise through the configured protected HTTPS preview.

Uses private local credentials, never production. Creates a clearly fake bundle,
case, advance and receipts; approves one fake fee and rejects another. A repeat
uses saved checkpoints. Unknown request outcomes require state reconciliation.
"""
import argparse,json,os,sys,tempfile
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tests'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exercise-synthetic-pricing',action='store_true',required=True)
    parser.add_argument('--evidence-dir',type=Path,default=ROOT/'private/s14-browser')
    args=parser.parse_args();args.evidence_dir.mkdir(parents=True,exist_ok=True)
    import requests
    from playwright.sync_api import sync_playwright
    from browser_helpers import chromium_options
    path=ROOT/'private/S14_PRICING.json';d=json.loads(path.read_text())
    s13=json.loads((ROOT/'private/S13_CASHIER.json').read_text());gate=json.loads((ROOT/'private/mobile-gateway/access.json').read_text())
    state=json.loads((ROOT/'private/mobile-gateway/processes.json').read_text());url=d['url'];parsed=urlsplit(url)
    assert url==state['url']==s13['url'] and parsed.scheme=='https' and parsed.hostname.endswith('.trycloudflare.com')
    env=dict(x.split('=',1) for x in (ROOT/'.env').read_text().splitlines() if '=' in x and not x.startswith('#'))
    credentials={**s13['accounts'],'owner':{'password':env['RAMSES_ADMIN_PASSWORD']}}
    def save():
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,delete=False) as f:
            json.dump(d,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(f.name,path)
    sessions={}
    for name in ('owner','cashier_external','cashier_reviewer','demo_clinician'):
        session=requests.Session();session.auth=(gate['username'],gate['password'])
        r=session.post(url+'/api/login',json={'username':env['RAMSES_ADMIN_USER'] if name=='owner' else name,'password':credentials[name]['password']},timeout=30);r.raise_for_status()
        session.headers['X-CSRF-Token']=r.json()['csrf']
        me=session.get(url+'/api/me',timeout=30).json();assert me['environment']=='free-preview';sessions[name]=session
    def api(who,method,path,body=None):
        r=sessions[who].request(method,url+path,json=body,timeout=30)
        assert r.status_code==200,(method,path,r.status_code,r.text[:500]);return r.json()
    def click(page,selector,path):
        with page.expect_response(lambda r:r.request.method=='POST' and urlsplit(r.url).path==path,timeout=35000) as result:page.locator(selector).click()
        r=result.value;assert r.status==200,(path,r.status,r.text());return r.json()
    http_credentials={'username':gate['username'],'password':gate['password'],'origin':url}
    def login(browser,who,width):
        context=browser.new_context(viewport={'width':width,'height':1000},http_credentials=http_credentials)
        page=context.new_page();page.goto(url,wait_until='networkidle',timeout=45000)
        page.locator('#loginForm [name=username]').fill(env['RAMSES_ADMIN_USER'] if who=='owner' else who)
        page.locator('#loginForm [name=password]').fill(credentials[who]['password'])
        page.locator('#loginForm button[type=submit]').click();page.locator('#shell').wait_for(state='visible')
        return context,page
    demo=d.setdefault('browser',{});save()
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,**chromium_options())
        try:
            if not demo.get('package'):
                context,page=login(browser,'owner',1440)
                page.evaluate("navigate('pricing')");page.locator('#pricingListFilter').wait_for()
                page.locator('#pricingListFilter').select_option(str(d['cash_list']))
                page.locator('[data-pricing-tab=packages]').click();page.locator('#pricingNewPackage').click()
                form=page.locator('#pricingDialogForm');form.locator('[name=code]').fill('DEMO_OXY_PACKAGE')
                form.locator('[name=name]').fill('باقة أكسجين — تجربة داخلية وعمليات')
                row=form.locator('.pricing-package-item').first
                row.locator('[name=service_id]').select_option(str(d['service']));row.locator('[name=location_id]').select_option(str(d['ipd']));row.locator('[name=quantity]').fill('2')
                form.locator('[data-add-item]').click();row=form.locator('.pricing-package-item').nth(1)
                row.locator('[name=service_id]').select_option(str(d['service']));row.locator('[name=location_id]').select_option(str(d['theatre']));row.locator('[name=quantity]').fill('1')
                form.locator('[name=package_amount]').fill('450.00')
                preview=click(page,'[data-package-preview]','/api/pricing/package-preview')
                assert (preview['gross_piasters'],preview['net_piasters'],preview['estimated_cost_piasters'])==(50000,45000,14500)
                page.screenshot(path=str(args.evidence_dir/'owner-package-preview-1440.png'),full_page=True)
                demo['package']=click(page,'#pricingDialogSave','/api/pricing/packages')['id'];save();context.close()
            if not demo.get('complete'):
                context,page=login(browser,'cashier_external',1440)
                page.evaluate("navigate('billing')");page.locator('#billingNewCase').wait_for()
                if not demo.get('case'):
                    page.locator('#billingNewCase').click();page.locator('#modalForm [name=patient]').fill('مريض باقة ودفعات وأتعاب S14 — وهمي')
                    page.locator('#modalForm [name=kind]').select_option('outpatient')
                    demo['case']=click(page,'#modalConfirm','/api/billing/cases')['id'];save()
                page.locator(f'[data-billing-open-case="{demo["case"]}"]').click()
                cfg=api('cashier_external','GET','/api/billing/config');point=next(p for p in cfg['points'] if p['kind']=='external')
                assert point['own_open_shift'],'Keep the assigned cashier practice shift open for this exercise'
                demo.setdefault('shift',point['active_shift']['id'])
                if 'cash_before' not in demo:
                    demo['cash_before']=api('owner','GET',f'/api/shifts/{demo["shift"]}/daily-report')['expected_piasters'];save()
                if not demo.get('order'):
                    page.locator('#billingPricedOrder').click();form=page.locator('#pricingDialogForm')
                    form.locator('[name=price_list_id]').select_option(str(d['cash_list']));form.locator('[name=order_type]').select_option('package')
                    form.locator('[name=package_version_id]').select_option(str(demo['package']))
                    first=form.locator('[data-performer-block]').first
                    first.locator('[data-same-performers]').uncheck()
                    first.locator('[data-occurrence-no="1"]').select_option([str(d['people'][k]) for k in ('doctor_a','nurse_a','nurse_b')])
                    first.locator('[data-occurrence-no="2"]').select_option([str(d['people'][k]) for k in ('doctor_b','nurse_a')])
                    form.locator('[data-performer-block]').nth(1).locator('select').select_option(str(d['people']['doctor_b']))
                    quote=click(page,'[data-order-preview]','/api/pricing/quote');assert quote['net_piasters']==45000 and 'estimated_cost_piasters' not in quote
                    order=click(page,'#pricingDialogSave','/api/pricing/orders');demo['order']=order['id'];demo['line_ids']=order['line_ids'];save()
                    page.locator(f'[data-pricing-cancel-order="{demo["order"]}"]').wait_for()
                if not demo.get('attested'):
                    for ident in demo['line_ids']:
                        existing=sessions['demo_clinician'].get(url+f'/api/billing/clinical/lines/{ident}/evidence',timeout=30)
                        if existing.status_code==404:api('demo_clinician','POST',f'/api/billing/clinical/lines/{ident}/attest',{'evidence_reference':f'SYNTHETIC-S14-CASE-{demo["case"]}-LINE-{ident}'})
                        else:assert existing.status_code==200
                    demo['attested']=True;save()
                page.evaluate("navigate('billing')");page.locator('#billingPricedOrder').wait_for()
                if not demo.get('advance'):
                    page.locator('#billingAdvance').click();page.locator('#modalForm [name=method_1]').select_option('cash');page.locator('#modalForm [name=amount_1]').fill('50')
                    page.locator('#modalForm [name=method_2]').select_option('wallet');page.locator('#modalForm [name=amount_2]').fill('50')
                    demo['advance']=click(page,'#modalConfirm',f'/api/billing/cases/{demo["case"]}/collect')['id'];save();page.locator('#modalText a[href$="/print"]').wait_for();page.locator('#modalClose').click()
                page.evaluate("navigate('billing')")
                if not demo.get('draft'):demo['draft']=click(page,'#billingDraft',f'/api/billing/cases/{demo["case"]}/drafts')['id'];save()
                if not demo.get('invoice'):demo['invoice']=click(page,f'[data-billing-issue="{demo["draft"]}"]',f'/api/billing/drafts/{demo["draft"]}/issue')['id'];save()
                if not demo.get('advance_applied'):
                    page.locator(f'[data-billing-apply="{demo["invoice"]}"]').click();page.locator('#modalForm [name=amount]').fill('100')
                    click(page,'#modalConfirm',f'/api/billing/cases/{demo["case"]}/apply-advance');demo['advance_applied']=True;save()
                for key,methods,amounts in (('mixed',['cash','card','wallet','instapay','transfer'],['50']*5),('last',['cash'],['50'])):
                    if demo.get(key):continue
                    page.locator(f'[data-billing-collect="{demo["invoice"]}"]').click()
                    for i,(method,amount) in enumerate(zip(methods,amounts),1):
                        page.locator(f'#modalForm [name=method_{i}]').select_option(method);page.locator(f'#modalForm [name=amount_{i}]').fill(amount)
                    demo[key]=click(page,'#modalConfirm',f'/api/billing/cases/{demo["case"]}/collect')['id'];save()
                    page.locator('#modalText a[href$="/print"]').wait_for();page.locator('#modalClose').click()
                context.close()
                queue=api('cashier_reviewer','GET','/api/service-fees/queue')['items']
                proposals=[x for x in queue if x['invoice_id']==demo['invoice'] and x['line_id']==demo['line_ids'][0] and x['rule_index']==0]
                assert len(proposals)==2
                context,page=login(browser,'cashier_reviewer',1440);page.evaluate("navigate('serviceFees')")
                for proposal in proposals:
                    decision='approve' if proposal['occurrence_no']==1 else 'reject'
                    card=page.locator('.pricing-fee-card').filter(has_text=proposal['person_name']).filter(has_text='المرة '+str(proposal['occurrence_no'])).filter(has_text=proposal['invoice_no']).first
                    card.locator(f'[data-fee-decision={decision}]').click();page.get_by_label('سبب القرار',exact=True).fill('تجربة مراجعة مستقلة — قبول مرة ورفض الأخرى حسب الاتفاق')
                    click(page,'#pricingDialogSave','/api/service-fees/decisions')
                demo['complete']=True;save();context.close()
                print('PASS real HTTPS S14: owner UI publishes450 bundle from500/cost145; cashier UI selects distinct teams, independent clinical API proof, invoice, advance100, five-method receipt250 plusreceipt50; reviewer UI approves one fixed100 occurrence/rejects another',flush=True)
            finance=api('cashier_external','GET',f'/api/billing/cases/{demo["case"]}/finance')
            assert next(i for i in finance['invoices'] if i['id']==demo['invoice'])['due_piasters']==5000
            daily=api('owner','GET',f'/api/shifts/{demo["shift"]}/daily-report');assert daily['expected_piasters']==demo['cash_before']+15000
            balance=api('cashier_reviewer','GET','/api/service-fees/balances')['items'];assert sum(x['amount_piasters'] for x in balance)==10000
            if not demo.get('cancel_checked'):
                patient=api('cashier_external','POST','/api/billing/patients',{'display_name':'مريض إلغاء باقة — وهمي','request_id':'s14_cancel_patient_001'})
                case=api('cashier_external','POST','/api/billing/cases',{'patient_id':patient['id'],'point_id':s13['external_point'],
                     'kind':'outpatient','business_date':d['day'],'request_id':'s14_cancel_case_0001'})['id']
                body={'case_id':case,'price_list_id':d['cash_list'],'package_version_id':demo['package']}
                quote=api('cashier_external','POST','/api/pricing/quote',body)
                order=api('cashier_external','POST','/api/pricing/orders',{**body,'quote_hash':quote['quote_hash'],'request_id':'s14_cancel_order_001'})
                context,page=login(browser,'cashier_external',1440);page.evaluate("navigate('billing')")
                page.locator(f'[data-billing-open-case="{case}"]').click()
                page.locator(f'[data-pricing-cancel-order="{order["id"]}"]').click();page.locator('#modalForm [name=reason]').fill('إلغاء تجريبي كامل قبل تنفيذ أي جزء من الباقة')
                click(page,'#modalConfirm',f'/api/pricing/orders/{order["id"]}/cancel')
                detail=api('cashier_external','GET',f'/api/billing/cases/{case}')
                assert detail['services'] and all(x['state']=='cancelled' for x in detail['services']) and not detail['invoices']
                demo['cancel_checked']=True;save();context.close()
                print('PASS real cashier UI cancels whole unexecuted package; no service remains ordered and no invoice created',flush=True)
            for width in (375,1440):
                for who,view in (('owner','pricing'),('cashier_reviewer','serviceFees'),('cashier_external','billing')):
                    context,page=login(browser,who,width);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.evaluate('(v)=>navigate(v)',view)
                    if view=='pricing':page.locator('#pricingListFilter').wait_for()
                    elif view=='serviceFees':page.locator('#serviceFeesRefresh').wait_for()
                    else:
                        page.locator(f'[data-billing-open-case="{demo["case"]}"]').click();page.locator(f'a[href="/api/billing/invoices/{demo["invoice"]}/print"]').wait_for()
                        assert not page.locator('[data-pricing-cancel-order]').count()
                    page.evaluate('document.fonts.ready');assert page.evaluate('document.documentElement.dir')=='rtl'
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    page.screenshot(path=str(args.evidence_dir/f'{view}-{width}.png'),full_page=True)
                    if who=='cashier_external':
                        page.goto(url+f'/api/billing/invoices/{demo["invoice"]}/print',wait_until='networkidle')
                        assert '450.00' in page.locator('main').inner_text() and '50.00' in page.locator('main').inner_text()
                        assert 'غرفة داخلي' in page.locator('main').inner_text() and 'غرفة عمليات' in page.locator('main').inner_text()
                        page.screenshot(path=str(args.evidence_dir/f'pricing-invoice-{width}.png'),full_page=True)
                        if width==1440:page.pdf(path=str(args.evidence_dir/'sample-priced-invoice.pdf'),format='A4',print_background=True)
                    assert not errors,errors;context.close()
                print(f'PASS actual HTTPS Chrome{width}: owner pricing, scoped reviewer proposals/balance, cashier invoice remaining50, RTL/Cairo, no overflow/JS errors; physical cash increases150 only',flush=True)
        finally:browser.close()


if __name__=='__main__':main()
