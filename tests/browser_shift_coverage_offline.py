"""Offline Chromium: missing shift alerts, filtering and mobile layout."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def run():
    from playwright.sync_api import sync_playwright
    html=(ROOT/'static/index.html').read_text(encoding='utf-8')
    for item in ('app.js','billing.js'):
        html=html.replace(f'<script src="/static/{item}" defer></script>','')
    html=html.replace('<link rel="stylesheet" href="/static/styles.css">','')
    rec={'point_id':1,'point_name':'Internal cash desk','fund_id':1,'business_date':'2026-10-29'}
    slots=[dict(rec,shift=code,status=status,session_id=number,starts_at='2026-10-29T08:00:00+02:00',ends_at='2026-10-29T16:00:00+02:00') for code,status,number in [('night','closed',11),('morning','awaiting_review',12),('evening','missing',None)]]
    coverage={'month':'2026-10','points':[{'id':1,'name':'Internal cash desk','fund_id':1,'monitored_from':'2026-10-29'}],
              'summary':{'missing':1,'unclosed':0,'awaiting_review':1},'items':slots,
              'days':[{'point_id':1,'point_name':'Internal cash desk','business_date':'2026-10-29',
                       'status':'incomplete','closed_shifts':1,'expected_shifts':3,'missing_shifts':1}]}
    fixtures={
      '/api/me':{'id':1,'username':'owner','role':'owner','csrf':'testonly','environment':'staging'},
      '/api/lookups':{'funds':[{'id':1,'code':'cash_main','name':'Internal fund','kind':'cash'}],
                     'employees':[],'departments':[],'categories':[],'shifts':[]},
      '/api/dashboard?month=2026-10':{'month':'2026-10','receipts_piasters':0,'payments_piasters':0,'pending':0,'daily':[],'latest':[],'legacy_issues':0},
      '/api/shifts?month=2026-10':{'month':'2026-10','items':[],
                                  'schedule':[{'code':'night','start':'00:00','end':'08:00'},
                                  {'code':'morning','start':'08:00','end':'16:00'},
                                  {'code':'evening','start':'16:00','end':'00:00'}],
                                  'suggested':{'business_date':'2026-10-29','shift':'morning'}},
      '/api/reports?month=2026-10':{'categories':[]},
      '/api/shifts/coverage?month=2026-10':coverage,
    }
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            page=browser.new_page(viewport={'width':1280,'height':800})
            errors=[]
            page.on('pageerror',lambda err: errors.append(str(err)))
            page.set_content(html)
            page.add_style_tag(content=(ROOT/'static/styles.css').read_text(encoding='utf-8'))
            page.evaluate('''obj=>{window.__fx=obj; window.fetch=async url=>({ok:!!window.__fx[url],status:window.__fx[url]?200:404,json:async()=>window.__fx[url]||{detail:'not mocked'}})}''',fixtures)
            page.add_script_tag(content=(ROOT/'static/app.js').read_text(encoding='utf-8'))
            page.wait_for_selector('#shell:not([hidden])')
            page.wait_for_selector('#dashboardCoverageAlert .warning')
            page.locator('#mainNav [data-view=shifts]').click()
            page.wait_for_selector('#coverageRows .data-table')
            assert '2026-10-29' in page.locator('#coverageRows').inner_text()
            assert 'Internal cash desk' in page.locator('#coverageRows').inner_text()
            assert 'غير مسجلة' in page.locator('#coverageRows').inner_text()
            assert page.locator('#coverageRows .data-table tbody tr').count()==1
            page.screenshot(path=str(ROOT.parent/'QA_SHIFT_COVERAGE_DESKTOP.png'),full_page=True)
            page.locator('#coverageStatus').select_option('complete')
            assert 'لا توجد' in page.locator('#coverageRows').inner_text()
            page.locator('#coverageStatus').select_option('attention')
            page.locator('#coverageSlotStatus').select_option('missing')
            page.locator('#coverageShift').select_option('evening')
            assert page.locator('#coverageRows .data-table tbody tr').count()==1
            page.locator('#coverageShift').select_option('night')
            assert 'لا توجد' in page.locator('#coverageRows').inner_text()
            page.locator('#coverageShift').select_option('evening')
            page.set_viewport_size({'width':375,'height':812})
            page.wait_for_timeout(100)
            assert page.locator('.shift-coverage-mobile .shift-coverage-card').is_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth+1')
            page.screenshot(path=str(ROOT.parent/'QA_SHIFT_COVERAGE_MOBILE.png'),full_page=True)
            assert not errors,errors
            print('PASS Chromium shift coverage: missing evening slot, review state, filters, RTL mobile width and no JS errors')
        finally:
            browser.close()


if __name__=='__main__':run()
