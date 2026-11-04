"""Offline Chromium for V7.5 maker/checker payroll and adjustment mobile UI."""
from browser_helpers import chromium_options
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def run():
    from playwright.sync_api import sync_playwright
    html=(ROOT/'static/index.html').read_text().replace('<link rel="stylesheet" href="/static/styles.css">','').replace('<script src="/static/app.js" defer></script>','').replace('<script src="/static/billing.js" defer></script>','')
    fixture={
      '/api/me':{'id':2,'username':'reviewer','role':'reviewer','csrf':'test-only-csrf','environment':'staging'},
      '/api/lookups':{'funds':[],'employees':[],'departments':[],'categories':[],'shifts':[]},
      '/api/dashboard?month=2026-10':{'receipts_piasters':0,'payments_piasters':0,'cash_difference_piasters':0,'pending':0,'daily':[],'latest':[],'legacy_issues':0},
      '/api/reports?month=2026-10':{'categories':[],'departments':[],'recognized_cash_service_revenue_piasters':0,'cash_paid_operating_items_piasters':0,'approved_payroll_accruals_piasters':0,'note':'اختبار'},
      '/api/payroll?period=2026-10':{'period':'2026-10','hourly_employees':0,'monthly_employees':1,'pending_work_entries':0,
        'pending_adjustments':1,'pending_signoffs':1,'accrual_total_piasters':418000,'due_total_piasters':0,
        'items':[{'id':7,'code':'EMP07','name':'موظف اختباري','department':'الإدارة',
                 'department_id':1,'pay_type':'monthly','monthly_piasters':400000,
                 'approved_work_minutes':0,'approved_work_entries':0,'pending_work_entries':0,
                 'approved_adjustment_additions_piasters':28000,'approved_adjustment_deductions_piasters':10000,
                 'pending_adjustments':0,'estimated_base_piasters':400000,'accrual_piasters':418000,
                 'accrual_id':11,'signoff_status':'pending','prepared_by':1,
                 'additions_piasters':0,'deductions_piasters':0,'can_correct':True,
                 'due_piasters':None,'advances_outstanding_piasters':0}],
        'note':'بيانات اختبار وهمية'},
      '/api/payroll/work-entries?period=2026-10&page=1':{'period':'2026-10','page':1,'pages':0,'total':0,'items':[]},
      '/api/payroll/adjustments?period=2026-10&page=1':{'period':'2026-10','page':1,'pages':1,'total':2,'pending_count':1,'items':[
         {'id':12,'employee_id':7,'employee_name':'موظف اختباري','kind':'lateness_deduction','amount_piasters':10000,'status':'pending',
          'created_by_name':'owner','reviewed_by_name':None,'note':'خصم تأخير تجريبي ولم يعتمد بعد'},
         {'id':13,'employee_id':7,'employee_name':'موظف اختباري','kind':'bonus','amount_piasters':28000,'status':'approved',
          'created_by_name':'owner','reviewed_by_name':'reviewer','note':'مكافأة تجريبية تمت مراجعتها'}]}
    }
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,**chromium_options(),args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            page=browser.new_page(viewport={'width':1440,'height':900})
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.set_content(html)
            page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
            page.evaluate('''data=>{window.__fixtures=data;window.fetch=async url=>({
               ok:!!window.__fixtures[url],status:window.__fixtures[url]?200:404,
               json:async()=>window.__fixtures[url]||{detail:'missing mock: '+url}
              })}''',fixture)
            page.add_script_tag(content=(ROOT/'static/app.js').read_text())
            page.wait_for_selector('#shell:not([hidden])')
            page.locator('#mainNav [data-view=payroll]').click()
            page.wait_for_selector('.payroll-adj-desktop tr')
            assert page.locator('.payroll-desktop-only [data-signoff="11"][data-decision="approve"]').count()==1
            assert page.locator('.payroll-adj-desktop [data-adjust-decision="approve"]').count()==1
            assert page.locator('[data-pay]').count()==0
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1')
            page.screenshot(path=str(ROOT.parent/'qa_payroll_review_desktop.png'),full_page=True)
            page.locator('.payroll-desktop-only [data-signoff="11"][data-decision="approve"]').click()
            assert 'الاعتماد النهائي' in page.locator('#modalTitle').inner_text()
            page.locator('#modalCancel').click()
            page.locator('.payroll-adj-desktop [data-adjust-decision="reject"]').click()
            assert page.locator('#modal [name=reason]').count()==1
            page.locator('#modalCancel').click()
            page.set_viewport_size({'width':390,'height':844})
            page.evaluate("document.documentElement.style.scrollBehavior='auto';window.scrollTo(0,0)")
            page.wait_for_timeout(330)
            assert page.locator('.payroll-mobile-only .payroll-card').count()==1
            assert page.locator('.payroll-adj-mobile .payroll-time-card').count()==2
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1')
            page.screenshot(path=str(ROOT.parent/'qa_payroll_review_mobile.png'),full_page=True)
            page.locator('.payroll-mobile-only [data-signoff="11"][data-decision="approve"]').click()
            assert page.locator('#modal').is_visible()
            page.locator('#modalCancel').click()
            assert not errors,errors
            print('PASS - V7.5 reviewer signoff/adjustment cards, desktop/mobile, modals, no JS errors or viewport overflow')
        finally:
            browser.close()

if __name__=='__main__':run()
