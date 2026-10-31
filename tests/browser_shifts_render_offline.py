"""Render the new shifts screen in Chromium without network navigation (offline mock).

This validates DOM, forms, keyboard buttons and desktop/mobile overflow, but is
NOT a real HTTP/browser integration test (the sandbox blocks navigation).
"""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def run():
    from playwright.sync_api import sync_playwright
    html=(ROOT/'static/index.html').read_text()
    html=html.replace('<link rel="stylesheet" href="/static/styles.css">','')
    html=html.replace('<script src="/static/app.js" defer></script>','').replace('<script src="/static/billing.js" defer></script>','')
    fixtures={
      '/api/me': {'id':1,'username':'owner','role':'owner','csrf':'staging_only_csrf','environment':'staging'},
      '/api/lookups':{'funds':[{'id':1,'code':'cash_main','name':'الخزنة الرئيسية','kind':'cash'},
                               {'id':2,'code':'vodafone','name':'فودافون كاش','kind':'wallet'}],
                      'employees':[],'departments':[],'categories':[],'shifts':[]},
      '/api/dashboard?month=2026-10': {'month':'2026-10','receipts_piasters':0,'payments_piasters':0,'cash_difference_piasters':0,'pending':0,'daily':[],'latest':[],'legacy_issues':0},
      '/api/shifts?month=2026-10': {'month':'2026-10','items':[
        {'id':1,'business_date':'2026-10-29','shift':'morning','fund_id':1,'fund_name':'الخزنة الرئيسية','responsible_name':'testclerk','responsible_id':2,'status':'submitted','mine':False,'can_review':True,'counted_piasters':125000,'expected_piasters':125000,'variance_piasters':0},
        {'id':2,'business_date':'2026-10-28','shift':'evening','fund_id':2,'fund_name':'فودافون كاش','responsible_name':'testclerk','responsible_id':2,'status':'closed','mine':False,'can_review':True,'counted_piasters':45000,'expected_piasters':45000,'variance_piasters':0},
        {'id':3,'business_date':'2026-10-27','shift':'night','fund_id':1,'fund_name':'الخزنة الرئيسية','responsible_name':'testclerk','responsible_id':2,'status':'submitted','mine':False,'can_review':True,'counted_piasters':118000,'expected_piasters':120000,'variance_piasters':-2000,'can_variance_decision':True,'variance_case':{'id':3,'status':'proposed','explanation':'فارق في عهدة الموظف يحتاج اعتماد المالك'}},
      ]},
      '/api/vouchers?month=2026-10&page=1':{'items':[{'id':10,'voucher_no':'RAM-2026-000010','date':'2026-10-25','kind':'payment','department':'الإدارة','category':'المرافق','amount_piasters':2500,'description':'مصروف اختبار مدعوم بفاتورة','status':'approved','created_user':'cashier','attachment_count':1}], 'count':1, 'page':1,'pages':1},
      '/api/vouchers/10/attachments':[{'id':33,'file_name':'فاتورة اختبار.pdf','file_size':1700,'sha256':'abc','media_type':'application/pdf'}],
      '/api/payroll/adjustments?period=2026-10&page=1':{'period':'2026-10','page':1,'pages':0,'total':0,'pending_count':0,'items':[]},
      '/api/payroll/work-entries?period=2026-10&page=1':{'period':'2026-10','page':1,'pages':0,'total':0,'pending_count':0,'items':[]},
      '/api/payroll?period=2026-10':{'period':'2026-10','items':[{'id':5,'code':'EMP05','name':'موظف تجريبي','department':'الإدارة','pay_type':'monthly','hourly_rate_piasters':None,'approved_work_minutes':0,'approved_work_entries':0,'pending_work_entries':0,'estimated_base_piasters':300000,'monthly_piasters':300000,'accrual_piasters':320000,'accrual_id':55,'signoff_status':'approved','prepared_by':1,'pending_adjustments':0,'can_correct':True,'additions_piasters':25000,'deductions_piasters':5000,'payments_piasters':0,'allocated_advances_piasters':0,'due_piasters':320000,'advances_outstanding_piasters':0}], 'hourly_employees':0,'monthly_employees':1,'pending_work_entries':0,'accrual_total_piasters':320000,'due_total_piasters':320000,'note':'اختبار فقط'},
    }
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            page=browser.new_page(viewport={'width':1280,'height':800},device_scale_factor=1)
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.set_content(html)
            page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
            page.evaluate("""fixtures=>{
                window.__fixtures=fixtures;
                window.fetch=async url=>({ok:!!window.__fixtures[url],status:window.__fixtures[url]?200:404,
                   json:async()=>window.__fixtures[url]??{detail:'missing fixture: '+url}});
            }""",fixtures)
            page.add_script_tag(content=(ROOT/'static/app.js').read_text())
            page.wait_for_selector('#shell:not([hidden])',timeout=6000)
            page.locator('#mainNav [data-view=shifts]').click()
            page.wait_for_selector('#newShift',timeout=6000)
            assert 'الورديات والجرد' in page.locator('#content h1').first.inner_text()
            assert page.locator('[data-shift-action=approve]').count()==2
            assert page.locator('[data-shift-action=recount]').count()==2
            assert page.locator('[data-shift-action=variance-approve]').count()==2
            assert page.locator('[data-shift-action=variance-reject]').count()==2
            assert not errors,errors
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth+1')
            page.screenshot(path=str(ROOT.parent/'qa_shifts_desktop.png'),full_page=True)
            page.locator('[data-shift-action=variance-approve]').first.click()
            assert page.locator('#modal [name=reason]').count()==1
            page.locator('#modalCancel').click()
            page.locator('#newShift').click()
            assert page.locator('#modal').is_visible()
            assert page.locator('#modal [name=fund_id]').count()==1
            page.locator('#modalCancel').click()
            page.set_viewport_size({'width':390,'height':844})
            page.wait_for_timeout(250)
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth+1')
            page.screenshot(path=str(ROOT.parent/'qa_shifts_mobile.png'),full_page=True)
            # Evidence download must never embed the PDF inline in the financial app.
            page.locator('#showSidebar').click()
            page.locator('#mainNav [data-view=ledger]').click()
            page.wait_for_selector('[data-evidence]')
            page.locator('[data-evidence]').click()
            page.wait_for_selector('a.evidence-link')
            assert page.locator('a.evidence-link').get_attribute('href')=='/api/attachments/33/download'
            page.locator('#modalCancel').click()
            page.locator('#showSidebar').click()
            page.locator('#mainNav [data-view=payroll]').click()
            page.wait_for_selector('.payroll-mobile-only [data-correct]')
            page.locator('.payroll-mobile-only [data-correct]').click()
            assert page.locator('#modal [name=reason]').count()==1
            page.locator('#modalCancel').click()
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth+1')
            assert not errors,errors
            print('PASS — offline Chromium shift variance, attachment dialog, payroll correction, responsive and no JS errors')
        finally:
            browser.close()


if __name__=='__main__':run()
