"""Chromium visual and interaction smoke for bank matching with synthetic data only."""
from browser_helpers import chromium_options
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def run():
    from playwright.sync_api import sync_playwright
    html=(ROOT/'static/index.html').read_text().replace('<link rel="stylesheet" href="/static/styles.css">','').replace('<script src="/static/app.js" defer></script>','').replace('<script src="/static/billing.js" defer></script>','')
    overview={
      'month':'2026-10','banks':[{'id':4,'name':'البنك الرئيسي - تجريبي','code':'bank'}],
      'fund':{'id':4,'name':'البنك الرئيسي - تجريبي'},
      'batch':{'id':22,'fund_id':4,'period':'2026-10','status':'draft','file_name':'test-only.csv',
               'opening_piasters':500000,'closing_piasters':515000},
      'lines':[
        {'id':1,'line_no':1,'tx_date':'2026-10-13','description':'تحويل داخلي تجريبي','reference':'T-12',
         'amount_piasters':20000,'match_id':5,'movement_id':1,'voucher_no':'RAM-2026-000001','match_date':'2026-10-13'},
        {'id':2,'line_no':2,'tx_date':'2026-10-14','description':'مصروف خدمات تجريبي','reference':'T-13',
         'amount_piasters':-5000,'match_id':None,'movement_id':None,'voucher_no':None,'match_date':None}],
      'unmatched_ledger':[{'movement_id':2,'booked_on':'2026-10-14','amount_piasters':-5000,
                           'voucher_no':'RAM-2026-000002','description':'سداد خدمات وهمية'}],
      'statement_sum_piasters':15000,'matched_count':1,'unmatched_bank_count':1,
      'ledger_opening_piasters':500000,'ledger_closing_piasters':515000,
      'bank_opening_piasters':500000,'bank_closing_piasters':515000,
      'balance_difference_piasters':0,'pending_vouchers':0,'month_closed':False,
      'warning':'يجب التحقق من كل الحركات البنكية أولًا.'}
    fixtures={
       '/api/me':{'id':1,'username':'owner','role':'owner','csrf':'fake','environment':'staging'},
       '/api/lookups':{'funds':[{'id':4,'code':'bank','name':'البنك الرئيسي - تجريبي','kind':'bank'}],
                       'employees':[],'departments':[],'categories':[],'shifts':[]},
       '/api/dashboard?month=2026-10':{'receipts_piasters':0,'payments_piasters':0,'cash_difference_piasters':0,
                                       'pending':0,'daily':[],'latest':[],'legacy_issues':0},
       '/api/bank-reconciliation?period=2026-10':overview,
       '/api/bank-reconciliation?period=2026-10&fund_id=4':overview,
    }
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,**chromium_options(),args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            page=browser.new_page(viewport={'width':1440,'height':920})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.set_content(html)
            page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
            page.evaluate('''obj=>{window.__fixtures=obj;window.fetch=async url=>({
                ok:!!window.__fixtures[url],status:window.__fixtures[url]?200:404,
                json:async()=>window.__fixtures[url]||{detail:'missing '+url}
            })}''',fixtures)
            page.add_script_tag(content=(ROOT/'static/app.js').read_text())
            page.wait_for_selector('#shell:not([hidden])')
            page.locator('#mainNav [data-view=bank]').click()
            page.wait_for_selector('.bank-line')
            assert page.locator('.bank-line').count()==2
            assert page.locator('[data-bank-match="2"]').count()==1
            assert page.locator('[data-bank-unmatch="5"]').count()==1
            assert page.locator('#bankApprove').count()==1
            assert page.locator('a[href="/api/bank-reconciliation/22/source.csv"]').count()==1
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1')
            page.screenshot(path=str(ROOT.parent/'qa_bank_desktop.png'),full_page=True)
            page.locator('[data-bank-unmatch="5"]').click()
            assert page.locator('#modal [name="reason"]').count()==1
            page.locator('#modalCancel').click()
            page.locator('#bankApprove').click()
            assert 'نهائي' in page.locator('#modalTitle').inner_text()
            page.locator('#modalCancel').click()
            page.set_viewport_size({'width':390,'height':844})
            page.evaluate("document.documentElement.style.scrollBehavior='auto';window.scrollTo(0,0)")
            page.wait_for_timeout(250)
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1')
            assert page.locator('.bank-line').count()==2
            page.screenshot(path=str(ROOT.parent/'qa_bank_mobile.png'),full_page=True)
            page.locator('[data-bank-unmatch="5"]').click()
            assert page.locator('#modal').is_visible()
            page.locator('#modalCancel').click()
            assert not errors,errors
            print('PASS — bank reconciliation desktop/mobile, matching controls, audit modals, no JS errors/overflow')
        finally:
            browser.close()

if __name__=='__main__':run()
