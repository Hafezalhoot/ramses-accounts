"""V8.1E calendar/settings responsive smoke tests using fake network responses."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]

def run():
    from playwright.sync_api import sync_playwright
    today=datetime.now(ZoneInfo('Africa/Cairo')).strftime('%Y-%m-%d')
    month=today[:7]
    html=(ROOT/'static/index.html').read_text()
    for res in ('app.js','cashier_ops_ui.js','financial_corrections_ui.js','billing.js'):
        html=html.replace(f'<script src="/static/{res}" defer></script>','')
    html=html.replace('<link rel="stylesheet" href="/static/styles.css">','')
    versions=lambda start,slots:[{'id':1,'effective_from':start,'operating_days':list(range(7)),'slots':slots,'reason':'test'}]
    points=[{'id':1,'name':'الكاشير الخارجي','code':'OUTPATIENT','kind':'external','fund_id':2,'active':True,
             'versions':versions(today,[{'code':'night','name':'السهر','start':'00:00'},{'code':'morning','name':'الصباحي','start':'08:00'},{'code':'evening','name':'المسائي','start':'16:00'}]),
             'policy':{'grace_minutes':120,'require_shift_image':0,'require_envelope_image':0}, 'lifecycle':[{'effective_from':today,'enabled':True}]},
            {'id':2,'name':'الخزنة الرئيسية','code':'INPATIENT','kind':'internal','fund_id':1,'active':True,
             'versions':versions(today,[{'code':'treasury','name':'الخزنة العامة / الداخلية','start':'00:00'}]),
             'policy':{'grace_minutes':120,'require_shift_image':0,'require_envelope_image':0}, 'lifecycle':[{'effective_from':today,'enabled':True}]}]
    shifts=[]
    for point in points:
        for slot in point['versions'][0]['slots']:
            shifts.append({'business_date':today,'point_id':point['id'],'point_name':point['name'],
             'shift':slot['code'],'shift_name':slot['name'],'status':'missing' if slot['code']=='evening' else 'closed',
             'session_id':None if slot['code']=='evening' else 3,'fund_id':point['fund_id']})
    coverage={'month':month,'points':points,'items':shifts,
          'summary':{'missing':1,'closed':3,'unclosed':0,'awaiting_review':0,'variance':0},
          'days':[{'point_id':1,'business_date':today,'expected_shifts':3,'closed_shifts':2,'missing_shifts':1},
                  {'point_id':2,'business_date':today,'expected_shifts':1,'closed_shifts':1,'missing_shifts':0}]}
    fixtures={
      '/api/me':{'id':1,'username':'owner','role':'owner','csrf':'offline','environment':'staging'},
      '/api/lookups':{'funds':[{'id':1,'name':'الخزنة الرئيسية','kind':'cash'},{'id':2,'name':'الخزنة الخارجية','kind':'cash'}],
                      'employees':[],'departments':[],'categories':[],'shifts':[]},
      f'/api/dashboard?month={month}':{'month':month,'receipts_piasters':0,'payments_piasters':0,
                      'cash_difference_piasters':0,'pending':0,'daily':[],'latest':[],'legacy_issues':0},
      f'/api/reports?month={month}':{'categories':[]},
      f'/api/shifts/coverage?month={month}':coverage,
      '/api/cashier/plans':{'points':points,'current_date':today},
      '/api/funds':[{'id':1,'code':'cash_main','name':'الخزنة الرئيسية','kind':'cash','active':1},{'id':2,'code':'cash_sub','name':'خزنة خارجي','kind':'cash','active':1},{'id':4,'code':'test_safe','name':'درج إضافي تجريبي','kind':'cash','active':1}],
      '/api/cashier/shortage-repayments':{'cases':[{'case_id':12,'business_date':today,'variance_piasters':-1000,'repaid_piasters':600,'outstanding_piasters':400}], 'receipts':[]},
      '/api/corrections':{'tickets':[{'id':9,'source_type':'invoice','source_id':12,'source_ref':'INV-00012',
                 'issue_type':'wrong_patient','reason':'مريض غير صحيح على الفاتورة','status':'open',
                 'opened_by':6,'opened_by_name':'موظف تجربة'}]},
      '/api/cashier/variance-permissions':[{'user_id':5,'username':'المحاسب','can_approve':0}],
      '/api/cashier/staff-access':[{'point_id':1,'user_id':6,'username':'كاشير خارجي','active':True,'allowed_codes':['morning']}],
    }
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            page=browser.new_page(viewport={'width':1365,'height':900})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.set_content(html)
            page.add_style_tag(content=(ROOT/'static/styles.css').read_text(encoding='utf8'))
            page.evaluate('''data=>{window.fetch=async(url,opt)=>({ok:!!data[url],status:data[url]?200:404,
                     json:async()=>data[url]||{detail:'missing '+url}})}''',fixtures)
            page.add_script_tag(content=(ROOT/'static/cashier_ops_ui.js').read_text(encoding='utf8'))
            page.add_script_tag(content=(ROOT/'static/financial_corrections_ui.js').read_text(encoding='utf8'))
            page.add_script_tag(content=(ROOT/'static/app.js').read_text(encoding='utf8'))
            page.wait_for_selector('#shell:not([hidden])')
            page.locator('#mainNav [data-view=calendar]').click()
            page.wait_for_selector('.cashier-calendar-grid .cashier-calendar-chip')
            today_cell=page.locator(f'[data-calendar-day="{today}"]')
            assert today_cell.locator('.cashier-calendar-chip').count()==4
            assert 'الخزنة العامة' in today_cell.inner_text()
            assert 'غير مسجلة' in today_cell.inner_text()
            page.locator('#cashierCalendarMode').select_option('day')
            page.locator('#cashierFocusDate').fill(today)
            assert page.locator('.cashier-calendar-day:visible').count()==1
            page.locator('#cashierCalendarMode').select_option('week')
            assert 1<=page.locator('.cashier-calendar-day:visible').count()<=7
            page.locator('#cashierCalendarMode').select_option('month')
            assert not errors,errors
            page.screenshot(path=str(ROOT.parent/'QA_V81E_CALENDAR_DESKTOP.png'),full_page=True)
            page.evaluate("navigate('cashierSettings')")
            page.wait_for_selector('.cashier-config-card')
            assert page.locator('.cashier-config-card').count()==2
            assert page.locator('#cashierPermissionsPanel').is_visible()
            assert page.locator('#cashierStaffPanel').is_visible()
            assert page.locator('#cashierCreatePoint details').is_visible()
            assert not page.locator('#newCashierPoint').is_visible()
            page.locator('#cashierCreatePoint summary').click()
            assert page.locator('#newCashierPoint').is_visible()
            assert page.locator('[data-cashier-status]').count()==2
            assert page.locator('#newCashierPoint [data-operating-day]:checked').count()==7
            assert page.locator('.cashier-config-card').first.locator('[data-operating-day]:checked').count()==7
            assert page.locator('#newCashierPoint select[name=fund_id] option').count()==2
            assert page.locator('#cashierStaffPanel [data-staff-slot]:checked').count()==1
            assert not page.locator('input[name="require_shift_image"]').first.is_checked()
            assert page.locator('input[name="effective_from"]').first.input_value()>today
            page.evaluate("navigate('cashierRecoveries')")
            page.wait_for_selector('#shortageRepayment')
            assert page.locator('#shortageRepayment select[name=variance_case_id] option').count()==1
            page.screenshot(path=str(ROOT.parent/'QA_V81E_REPAYMENTS_DESKTOP.png'),full_page=True)
            page.evaluate("navigate('cashierCorrections')")
            page.wait_for_selector('#financialCorrectionForm')
            assert page.locator('[data-correction-review]').count()==1
            assert page.locator('[data-correction-history]').count()==1
            page.screenshot(path=str(ROOT.parent/'QA_V81E_CORRECTIONS_DESKTOP.png'),full_page=True)
            page.evaluate("navigate('cashierSettings')")
            page.wait_for_selector('#newCashierPoint',state='attached')
            page.locator('#cashierCreatePoint summary').click()
            page.screenshot(path=str(ROOT.parent/'QA_V81E_SETTINGS_DESKTOP.png'),full_page=True)
            page.set_viewport_size({'width':375,'height':820})
            page.wait_for_timeout(150)
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth+1'),page.evaluate('document.documentElement.scrollWidth')
            page.screenshot(path=str(ROOT.parent/'QA_V81E_SETTINGS_MOBILE.png'),full_page=True)
            page.locator('#showSidebar').click()
            page.locator('#mainNav [data-view=calendar]').click()
            page.wait_for_selector('.cashier-calendar-grid .cashier-calendar-chip')
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth+1')
            page.screenshot(path=str(ROOT.parent/'QA_V81E_CALENDAR_MOBILE.png'),full_page=True)
            page.evaluate("navigate('cashierCorrections')")
            page.wait_for_selector('#financialCorrectionForm')
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth+1')
            page.screenshot(path=str(ROOT.parent/'QA_V81E_CORRECTIONS_MOBILE.png'),full_page=True)
            assert not errors,errors
            print('PASS Chromium V8.1E: 3 external + 1 treasury calendar, status chips, owner settings, delegated variance, evidence OFF, 375px RTL without overflow')
        finally:browser.close()
if __name__=='__main__':run()
