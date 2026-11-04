"""Real Chromium layout/interaction QA with anonymous simulated billing data, no network."""
from browser_helpers import chromium_options
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def run():
    from playwright.sync_api import sync_playwright
    html=(ROOT/'static/index.html').read_text().replace('<link rel="stylesheet" href="/static/styles.css">','')
    for src in ('app.js','billing.js'):
        html=html.replace(f'<script src="/static/{src}" defer></script>','')
    fixtures={
        '/api/me':{'id':1,'username':'owner','role':'owner','csrf':'sampletoken','environment':'free-preview'},
        '/api/lookups':{'funds':[],'employees':[],'departments':[{'id':5,'code':'LAB','name':'المعمل'}],'categories':[],'shifts':[]},
        '/api/dashboard?month=2026-10':{'receipts_piasters':0,'payments_piasters':0,'cash_difference_piasters':0,'pending':0,'daily':[],'latest':[],'legacy_issues':0,'note':'تجريبي فقط'},
        '/api/billing/config':{'mode':'BILLING_SANDBOX','payment_channels':[],'points':[{'id':1,'name':'الكاشير الخارجي','kind':'external','fund_id':7,'active_shift':{'shift':'morning','status':'open'},'own_open_shift':True},
               {'id':2,'name':'خزينة الحسابات الداخلية','kind':'internal','fund_id':8,'active_shift':None,'own_open_shift':False}],
          'services':[{'id':3,'code':'LAB_TEST','name':'تحليل معمل افتراضي','department_name':'المعمل','current_price_piasters':45000}]},
        '/api/billing/cases?point_id=1':{'items':[{'id':11,'case_no':'CASE-2026-000011','patient_name':'مريض اختبار خارجي','kind':'outpatient','unbilled_piasters':45000}]},
        '/api/billing/cases?point_id=2':{'items':[{'id':12,'case_no':'CASE-2026-000012','patient_name':'مريض اختبار داخلي','kind':'inpatient','unbilled_piasters':90000}]},
        '/api/billing/cases/11':{'case':{'id':11,'case_no':'CASE-2026-000011','patient_name':'مريض اختبار خارجي','patient_code':'PT-DEMO','kind':'outpatient','business_date':'2026-10-30','default_point_id':1},
          'services':[{'id':9,'service_name_snapshot':'تحليل افتراضي','unit_price_piasters':45000,'quantity':1,'state':'fulfilled'}],
          'drafts':[],'invoices':[],'unbilled_piasters':45000},
        '/api/billing/cases/11/finance':{'invoices':[],'collections':[],'total_invoiced_piasters':0,'outstanding_piasters':0,'advance_available_piasters':0},
        '/api/billing/cases/11/adjustments':{'credits':[],'refunds':[],'credit_refundable_piasters':0,'advance_refundable_piasters':0},
        '/api/billing/cases/12/adjustments':{'credits':[{'id':71,'credit_no':'CR-TEST01','amount_piasters':10000,'status':'pending'}],'refunds':[{'id':72,'refund_no':'RF-TEST01','amount_piasters':2000,'status':'approved','method':'cash'}],'credit_refundable_piasters':0,'advance_refundable_piasters':0},
        '/api/billing/cases/12':{'case':{'id':12,'case_no':'CASE-2026-000012','patient_name':'مريض اختبار داخلي','patient_code':'PT-TEST','kind':'inpatient','business_date':'2026-10-30','default_point_id':2},
          'services':[{'id':10,'service_name_snapshot':'تحليل معمل اتعمل في الدور الأرضي لحالة داخلية','unit_price_piasters':45000,'quantity':2,'state':'fulfilled'}],
          'drafts':[{'id':10,'draft_no':'DRAFT-2026-000010','total_piasters':90000}],
          'invoices':[{'id':3,'invoice_no':'INV-2026-000003','draft_id':10,'total_piasters':90000}], 'unbilled_piasters':0},
        '/api/billing/cases/12/finance':{'invoices':[{'id':3,'invoice_no':'INV-2026-000003','draft_id':10,'total_piasters':90000,'due_piasters':40000}],
            'collections':[{'id':9,'collection_no':'REC-2026-000009','kind':'invoice','business_date':'2026-10-30','total_piasters':50000}],
            'total_invoiced_piasters':90000,'outstanding_piasters':40000,'advance_available_piasters':0},
    }
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,**chromium_options(),args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
            errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
            page.set_content(html)
            page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
            page.evaluate('''obj=>{window.__fx=obj;window.fetch=async url=>({
                ok:!!window.__fx[url],status:window.__fx[url]?200:404,
                json:async()=>window.__fx[url]||{detail:'missing '+url}
            })}''',fixtures)
            page.add_script_tag(content=(ROOT/'static/billing.js').read_text())
            page.add_script_tag(content=(ROOT/'static/app.js').read_text())
            page.wait_for_selector('#shell:not([hidden])')
            page.locator('#mainNav [data-view=billing]').click()
            page.wait_for_selector('.billing-points')
            assert page.locator('.billing-point').count()==2
            assert 'V8.1C' in page.locator('.billing-alert').inner_text()
            page.locator('[data-billing-open-case="11"]').click()
            page.wait_for_selector('.billing-services-list')
            assert '450.00' in page.locator('.billing-stats').first.inner_text()
            page.screenshot(path=str(ROOT.parent/'qa_v81_billing_desktop.png'),full_page=True)
            page.locator('[data-billing-point="2"]').click()
            page.wait_for_selector('[data-billing-open-case="12"]')
            page.locator('[data-billing-open-case="12"]').click()
            page.wait_for_selector('.billing-drafts')
            assert 'الدور الأرضي' in page.locator('.billing-services-list').inner_text()
            assert 'DRAFT-2026-000010' in page.locator('.billing-drafts').inner_text()
            assert 'INV-2026-000003' in page.locator('.billing-invoices').first.inner_text()
            assert page.locator('[data-billing-credit-decision="71"]').count()==2
            assert page.locator('[data-billing-refund-pay="72"]').count()==1
            page.set_viewport_size({'width':375,'height':812})
            page.evaluate("document.documentElement.style.scrollBehavior='auto';window.scrollTo(0,0)")
            page.wait_for_timeout(120)
            assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1'), 'mobile horizontal overflow'
            page.screenshot(path=str(ROOT.parent/'qa_v81_billing_mobile.png'),full_page=True)
            assert page.locator('.billing-point').count()==2
            assert not errors,errors
            print('PASS V8.1B Chromium: both stations, outpatient and internal patient, snapshot invoice draft, RTL 1440/375, zero page errors or overflow')
        finally:
            browser.close()

if __name__=='__main__':run()
