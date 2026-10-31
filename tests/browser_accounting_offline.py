"""Real Chromium DOM smoke using synthetic API responses, no sensitive data or network."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def run():
    from playwright.sync_api import sync_playwright
    html=(ROOT/'static/index.html').read_text().replace('<link rel="stylesheet" href="/static/styles.css">','').replace('<script src="/static/app.js" defer></script>','').replace('<script src="/static/billing.js" defer></script>','')
    period='2026-10'
    accounts=[
        {'id':1,'code':'1100','name':'المخزون والمستلزمات','class':'asset','control':'','debit_total':5000,'credit_total':0,'closing_debit_piasters':5000,'closing_credit_piasters':0},
        {'id':2,'code':'2200','name':'مستحقات الموردين','class':'liability','control':'','debit_total':0,'credit_total':5000,'closing_debit_piasters':0,'closing_credit_piasters':5000},
        {'id':3,'code':'F00001','name':'خزنة رمسيس - اختبار','class':'asset','control':'fund','debit_total':10000,'credit_total':0,'closing_debit_piasters':10000,'closing_credit_piasters':0},
        {'id':4,'code':'4100','name':'إيرادات خدمات طبية محصلة','class':'revenue','control':'','debit_total':0,'credit_total':10000,'closing_debit_piasters':0,'closing_credit_piasters':10000},
        {'id':5,'code':'5180','name':'تكلفة مرتبات مستحقة','class':'expense','control':'','debit_total':0,'credit_total':0,'closing_debit_piasters':0,'closing_credit_piasters':0}]
    fixtures={
     '/api/me':{'id':1,'username':'owner','role':'owner','csrf':'fake','environment':'free-preview'},
     '/api/lookups':{'funds':[],'employees':[],'departments':[],'categories':[],'shifts':[]},
     '/api/dashboard?month=2026-10':{'receipts_piasters':0,'payments_piasters':0,'cash_difference_piasters':0,'pending':0,'daily':[],'latest':[],'legacy_issues':0},
     '/api/accounting/trial-balance?period=2026-10':{
      'trial_balance':{'period':period,'accounts':accounts,'debit_piasters':15000,'credit_piasters':15000,'balanced':True},
      'coverage':{'unposted_vouchers':2,'unposted_payroll':0,'unposted_allocations':0,
                  'unverified_opening_funds':1,'pending_journals':1,'historical_unverified':618,
                  'readiness_reason':'الميزان غير معتمد: يوجد أرصدة افتتاحية وسندات ناقصة','not_final':True}},
     '/api/accounting/patient-reconciliation?period=2026-10':{
       'period':period,'matched':True,'checks':[
         {'code':'1200','name':'ذمم المرضى','expected_piasters':0,'ledger_piasters':0,'difference_piasters':0,'matched':True},
         {'code':'2300','name':'مقدمات المرضى','expected_piasters':0,'ledger_piasters':0,'difference_piasters':0,'matched':True},
         {'code':'2310','name':'التزامات رد المرضى','expected_piasters':0,'ledger_piasters':0,'difference_piasters':0,'matched':True}],
       'scope':'مطابقة جزئية لدفاتر المرضى فقط'},
     '/api/accounting/treasury-reconciliation?period=2026-10':{
       'period':period,'matched':False,'issue_count':1,'opening_review_required':1,
       'issues':[{'type':'fund_delta','fund_id':3,'reference':42,'message':'حركة خزنة لا تطابق القيد المرتبط'}],
       'funds':[{'id':3,'code':'SAFE3','name':'الخزنة الرئيسية','kind':'cash','opening_piasters':0,
          'book_balance_piasters':20000,'movement_piasters':20000,'gl_posted_piasters':20000,
          'difference_piasters':0,'matched':True,'issue_count':0},
         {'id':7,'code':'BANK7','name':'حساب البنك','kind':'bank','opening_piasters':10000,
          'book_balance_piasters':40000,'movement_piasters':30000,'gl_posted_piasters':30000,
          'difference_piasters':0,'matched':False,'issue_count':1}],
       'scope':'مطابقة حركات السندات مع حسابات الخزن في الأستاذ، والأرصدة الافتتاحية تتطلب أدلة مستقلة'},
     '/api/accounting/journals?period=2026-10':{'month':period,'count':1,'page':1,
       'items':[{'id':42,'entry_date':period+'-05','origin':'manual','created_by':2,'status':'pending','memo':'فاتورة غير مدفوعة للتجربة','lines':[]}]},
    }
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            page=browser.new_page(viewport={'width':1440,'height':940})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.set_content(html)
            page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
            page.evaluate('''obj=>{window.__fixtures=obj;window.fetch=async url=>({
                ok:!!window.__fixtures[url],status:window.__fixtures[url]?200:404,
                json:async()=>window.__fixtures[url]||{detail:'missing '+url}
            })}''',fixtures)
            page.add_script_tag(content=(ROOT/'static/app.js').read_text())
            page.wait_for_selector('#shell:not([hidden])')
            page.locator('#mainNav [data-view=accounting]').click()
            page.wait_for_selector('.accounting-coverage')
            assert page.locator('.accounting-coverage [role=listitem]').count()==6
            assert page.locator('.treasury-row').count()==2
            assert page.locator('.treasury-issues li').count()==1
            assert page.locator('.accounting-journal').count()==1
            assert 'غير معتمد' in page.locator('.accounting-warning').inner_text()
            assert page.locator('[data-gl-approve="42"]').count()==1
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth+1')
            page.screenshot(path=str(ROOT.parent/'QA_G2J_ACCOUNTING_DESKTOP.png'),full_page=True)
            page.locator('#newJournal').click()
            assert page.locator('#modal [name=debit_account_id] option').count()==4  # first blank + three non-control/protected
            assert 'خزنة' not in page.locator('#modal [name=debit_account_id]').inner_text()
            page.locator('#modalCancel').click()
            page.locator('[data-gl-approve="42"]').click()
            assert 'اعتماد قيد' in page.locator('#modalTitle').inner_text()
            page.locator('#modalCancel').click()
            page.set_viewport_size({'width':375,'height':812})
            page.evaluate("document.documentElement.style.scrollBehavior='auto';window.scrollTo(0,0)")
            page.wait_for_timeout(130)
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth+1'), 'mobile horizontal scroll'
            assert page.locator('.accounting-coverage [role=listitem]').count()==6
            assert page.locator('.treasury-row').count()==2
            assert page.locator('.treasury-issues li').count()==1
            page.screenshot(path=str(ROOT.parent/'QA_G2J_ACCOUNTING_MOBILE.png'),full_page=True)
            assert not errors,errors
            print('PASS - V8 accounting tab desktop 1440px + mobile 375px, permissions, GL approvals, draft form, no JS/overflow')
        finally:
            browser.close()

if __name__=='__main__':run()
