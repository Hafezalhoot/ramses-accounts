"""Offline Chromium smoke test of mixed payroll desktop/mobile and modal actions (not live HTTP)."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def run():
    from playwright.sync_api import sync_playwright
    html=(ROOT/'static/index.html').read_text()
    html=html.replace('<link rel="stylesheet" href="/static/styles.css">','')
    html=html.replace('<script src="/static/app.js" defer></script>','').replace('<script src="/static/billing.js" defer></script>','')
    fixtures={
      '/api/me':{'id':1,'username':'owner','role':'owner','csrf':'demo-csrf','environment':'staging'},
      '/api/lookups':{'funds':[],'employees':[],'departments':[{'id':1,'name':'المعمل'}], 'categories':[], 'shifts':[]},
      '/api/payroll?period=2026-10':{'period':'2026-10','hourly_employees':1,'monthly_employees':1,'pending_work_entries':1,'accrual_total_piasters':510000,'due_total_piasters':510000,
       'items':[
         {'id':1,'name':'ممرض تجريبي بالساعة','department':'التمريض','pay_type':'hourly','hourly_rate_piasters':7555,'monthly_piasters':None,'approved_work_minutes':510,'approved_work_entries':1,'pending_work_entries':1,'estimated_base_piasters':64218,'accrual_piasters':None,'accrual_id':None,'pending_adjustments':0,'due_piasters':None,'advances_outstanding_piasters':0},
         {'id':2,'name':'موظف تجريبي شهري','department':'الإدارة','pay_type':'monthly','hourly_rate_piasters':None,'monthly_piasters':430000,'approved_work_minutes':0,'approved_work_entries':0,'pending_work_entries':0,'estimated_base_piasters':430000,'accrual_piasters':440000,'accrual_id':22,'pending_adjustments':0,'signoff_status':'approved','prepared_by':1,'can_correct':True,'additions_piasters':15000,'deductions_piasters':5000,'due_piasters':440000,'advances_outstanding_piasters':0,'department_id':1},
         {'id':3,'name':'موظف لم يحدد عقده','department':'المعمل','pay_type':None,'monthly_piasters':None,'approved_work_minutes':0,'approved_work_entries':0,'pending_work_entries':0,'estimated_base_piasters':None,'accrual_piasters':None,'accrual_id':None,'pending_adjustments':0,'due_piasters':None,'advances_outstanding_piasters':0}],
       'note':'عينة افتراضية لمراجعة تصميم النظام المختلط'},
      '/api/payroll/adjustments?period=2026-10&page=1':{'period':'2026-10','page':1,'pages':1,'total':2,'pending_count':1,
       'items':[{'id':10,'employee_id':2,'employee_name':'موظف تجريبي شهري','kind':'bonus','amount_piasters':15000,'status':'approved','note':'مكافأة تجريبية معتمدة من الإدارة','created_by_name':'reviewer','reviewed_by_name':'owner'},
                {'id':11,'employee_id':1,'employee_name':'ممرض تجريبي بالساعة','kind':'overtime_premium','amount_piasters':2800,'status':'pending','note':'إضافي تجريبي بانتظار المراجعة','created_by_name':'reviewer'}]},
      '/api/payroll/work-entries?period=2026-10&page=1':{'period':'2026-10','page':1,'pages':1,'total':2,'pending_count':1,
       'items':[{'id':77,'employee_id':1,'employee_name':'ممرض تجريبي بالساعة','work_date':'2026-10-27','shift':'night','work_minutes':480,'created_by_name':'reviewer','status':'pending'},
                {'id':78,'employee_id':1,'employee_name':'ممرض تجريبي بالساعة','work_date':'2026-10-26','shift':'morning','work_minutes':510,'created_by_name':'reviewer','status':'approved'}]},
      '/api/dashboard?month=2026-10':{'month':'2026-10','receipts_piasters':0,'payments_piasters':0,'cash_difference_piasters':0,'pending':0,'daily':[],'latest':[],'legacy_issues':0},
      '/api/reports?month=2026-10':{'month':'2026-10','categories':[],'departments':[],'recognized_cash_service_revenue_piasters':0,'cash_paid_operating_items_piasters':0,'approved_payroll_accruals_piasters':0,'rough_margin_piasters':0,'note':'اختبار'}
    }
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            page=browser.new_page(viewport={'width':1440,'height':900})
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.set_content(html)
            page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
            page.evaluate("""fixtures=>{window.__fixtures=fixtures;window.fetch=async url=>({
               ok:!!window.__fixtures[url],status:window.__fixtures[url]?200:404,
               json:async()=>window.__fixtures[url]??{detail:'missing: '+url}
            });}""",fixtures)
            page.add_script_tag(content=(ROOT/'static/app.js').read_text())
            page.wait_for_selector('#shell:not([hidden])',timeout=8000)
            page.locator('#mainNav [data-view=payroll]').click()
            page.wait_for_selector('[data-hour]',timeout=8000)
            assert 'بالساعة' in page.locator('#content').inner_text()
            assert page.locator('[data-salary]').count()==6  # all employees have change-contract control in both layouts
            assert page.locator('[data-work-decision="approve"]').count()==2
            assert page.locator('.payroll-desktop-only tr').count()==4
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1')
            page.screenshot(path=str(ROOT.parent/'qa_payroll_v74_desktop.png'),full_page=True)
            page.locator('.payroll-desktop-only [data-hour]').first.click()
            assert page.locator('#modal [name=hours]').count()==1
            assert page.locator('#modal [name=minutes]').count()==1
            page.locator('#modalCancel').click()
            page.locator('.work-log-desktop [data-work-decision="approve"]').click()
            assert page.locator('#modal').is_visible()
            page.locator('#modalCancel').click()
            page.locator('.payroll-desktop-only [data-salary]').last.click()
            page.locator('#modal [name=pay_type]').select_option('hourly')
            page.locator('#modalCancel').click()
            page.set_viewport_size({'width':390,'height':844})
            page.evaluate('window.scrollTo(0,0)')
            page.wait_for_timeout(150)
            assert page.locator('.payroll-mobile-only .payroll-card').count()==3
            assert page.locator('.work-log-mobile .payroll-time-card').count()==2
            assert page.locator('.payroll-desktop-only').is_hidden()
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1')
            page.screenshot(path=str(ROOT.parent/'qa_payroll_v74_mobile.png'),full_page=True)
            page.locator('.payroll-mobile-only [data-hour]').click()
            assert page.locator('#modal [name=hours]').count()==1
            page.locator('#modalCancel').click()
            assert not errors,errors
            print('PASS — offline Chromium mixed monthly/hourly payroll, independent approval buttons, modals, mobile cards, no horizontal overflow or JS errors')
        finally:browser.close()

if __name__=='__main__':run()
