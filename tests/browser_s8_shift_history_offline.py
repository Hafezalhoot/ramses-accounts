"""S8 offline Chromium: historical shift labels survive a future renaming.

Test fixtures are artificial; HTTP navigation is not asserted in this test.
"""
from browser_helpers import chromium_options
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def run():
    from playwright.sync_api import sync_playwright
    day = datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
    month = day[:7]
    old_name, new_name = 'وردية الاستقبال التاريخية', 'اسم الوردية بعد التعديل'
    html = (ROOT / 'static/index.html').read_text(encoding='utf-8')
    for file in ('app.js', 'billing.js'):
        html = html.replace(f'<script src="/static/{file}" defer></script>', '')
    html = html.replace('<link rel="stylesheet" href="/static/styles.css">', '')
    row = {'id':41, 'point_id':7, 'business_date':day, 'shift':'desk',
           'shift_name':old_name, 'fund_id':2, 'fund_name':'خزنة اختبار',
           'responsible_name':'synthetic_staff', 'status':'closed',
           'mine':False, 'can_review':False, 'counted_piasters':0,
           'expected_piasters':0, 'variance_piasters':0}
    fixtures = {
        '/api/me': {'id':1, 'username':'owner', 'role':'owner', 'csrf':'synthetic_csrf', 'environment':'staging'},
        '/api/lookups': {'funds':[{'id':2,'code':'synthetic_fund','name':'خزنة اختبار','kind':'cash'}],
                         'employees':[], 'departments':[], 'categories':[], 'shifts':[]},
        f'/api/dashboard?month={month}': {'daily':[], 'latest':[], 'pending':0},
        f'/api/shifts?month={month}': {
            'month':month, 'items':[row], 'schedule':[{'code':'desk','start':'00:00','end':'00:00'}],
            'suggested':{'business_date':day,'shift':'desk'}},
        '/api/cashier/plans': {'points':[{'id':7,'fund_id':2,'kind':'external',
           'versions':[{'effective_from':day,'slots':[{'code':'desk','name':old_name,'start':'00:00'}]},
                       {'effective_from':'2030-01-01','slots':[{'code':'desk','name':new_name,'start':'00:00'}]}]}]},
        f'/api/shifts/coverage?month={month}': {'month':month,'summary':{},'items':[], 'days':[], 'points':[]},
        '/api/shifts/41/daily-report': {'id':41, 'business_date':day,
            'shift':'desk', 'shift_name':old_name, 'fund_name':'خزنة اختبار', 'status':'closed',
            'opening_piasters':0, 'expected_piasters':0, 'cash_credited_piasters':0,
            'cash_debited_piasters':0, 'payment_methods':[], 'cash_movements':[]},
        f'/api/shifts/day-summary?business_date={day}': {'stations':[
            {'id':41, 'point_name':'نقطة اختبار', 'shift':'desk', 'shift_name':old_name,
             'responsible_name':'synthetic_staff','status':'closed',
             'cash_credited_piasters':0,'cash_debited_piasters':0}],
            'is_provisional':True, 'payment_method_totals_piasters':{},
            'pending_accounting_review':0}
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, **chromium_options(),
                                             args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            page = browser.new_page(viewport={'width':1280,'height':800})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.set_content(html)
            page.add_style_tag(content=(ROOT / 'static/styles.css').read_text(encoding='utf-8'))
            page.evaluate('''fixtures => {
                window.__s8Fixtures=fixtures;
                window.fetch=async url=>({ok:Object.hasOwn(window.__s8Fixtures,url),
                    status:Object.hasOwn(window.__s8Fixtures,url)?200:404,
                    json:async()=>window.__s8Fixtures[url]??{detail:'unknown synthetic fixture '+url}});
            }''', fixtures)
            page.add_script_tag(content=(ROOT / 'static/app.js').read_text(encoding='utf-8'))
            page.wait_for_selector('#shell:not([hidden])',timeout=10000)
            page.locator('#mainNav [data-view=shifts]').click()
            page.wait_for_selector('.shift-desktop-only tbody tr',timeout=10000)
            assert old_name in page.locator('.shift-desktop-only tbody tr').inner_text(), 'Desktop used new plan instead of shift date'
            assert new_name not in page.locator('.shift-desktop-only tbody tr').inner_text()
            page.set_viewport_size({'width':375,'height':812})
            assert old_name in page.locator('.shift-mobile-card').inner_text(), 'Mobile used new plan instead of shift date'
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth+1')
            page.locator('#cashierDaySummary').click()
            page.locator('#modalConfirm').click()
            page.wait_for_function('''() => document.querySelector('#modalTitle')?.textContent.includes('يومية الكاشير -')''')
            modal_text = page.locator('#modalText').inner_text()
            assert old_name in modal_text and new_name not in modal_text, 'Cash day report changed old shift name'
            page.locator('#modalCancel').click()
            page.locator('.shift-mobile-card [data-shift-action=daily]').click()
            page.wait_for_function('''() => document.querySelector('#modalTitle')?.textContent.includes('يومية الوردية')''')
            assert old_name in page.locator('#modalText').inner_text(), 'Individual shift report used current name'
            assert not errors, errors
            print('PASS S8 Chromium: historical shift identity in desktop/mobile/daily modal at 375px, no JS errors')
        finally:
            browser.close()


if __name__=='__main__':
    run()
