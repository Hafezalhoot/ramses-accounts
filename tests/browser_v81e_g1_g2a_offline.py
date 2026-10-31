"""Chromium regression: Arabic emergency shift register and RTL responsiveness.
All network and patient data are synthetic; no real server or financial posting.
"""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT.parent


def run():
    from playwright.sync_api import sync_playwright
    today=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
    month=today[:7]
    html=(ROOT/'static/index.html').read_text(encoding='utf-8')
    for name in ('app.js','cashier_ops_ui.js','financial_corrections_ui.js',
                 'billing.js','late_entry_ui.js'):
        html=html.replace(f'<script src="/static/{name}" defer></script>','')
    html=html.replace('<link rel="stylesheet" href="/static/styles.css">','')
    points=[{'id':1,'name':'الكاشير الخارجي','code':'OUT','kind':'external','fund_id':2},
            {'id':2,'name':'الخزنة الداخلية / الرئيسية','code':'MAIN','kind':'internal','fund_id':1}]
    fixtures={
      '/api/me':{'id':1,'username':'owner','role':'owner','csrf':'demo','environment':'staging'},
      '/api/lookups':{'funds':[],'employees':[],'departments':[],'categories':[],'shifts':[]},
      f'/api/dashboard?month={month}':{'month':month,'receipts_piasters':0,'payments_piasters':0,
                           'cash_difference_piasters':0,'pending':0,'daily':[],'latest':[],
                           'legacy_issues':0,'note':'بيانات اختبار'},
      f'/api/reports?month={month}':{'categories':[]},
      '/api/billing/config':{'points':points},
      f'/api/shifts/coverage?month={month}':{'items':[
                {'point_id':1,'shift':'night','shift_name':'السهر'},
                {'point_id':1,'shift':'morning','shift_name':'الصباحي'},
                {'point_id':1,'shift':'evening','shift_name':'المسائي'},
                {'point_id':2,'shift':'treasury','shift_name':'الخزنة العامة / الداخلية'}],
                                             'summary':{'missing':0}},
      '/api/late-entries/shortage-open':{'items':[]},
      '/api/late-entries':{'items':[
          {'id':41,'point_id':1,'point_name':'الكاشير الخارجي',
           'business_date':today,'shift_code':'evening','incident_reason':'outage',
           'cash_location':'envelope','custodian_name':'مسؤول اختبار','doc_count':1,
           'linked_count':0,'status':'submitted'},
          {'id':42,'point_id':2,'point_name':'الخزنة الرئيسية',
           'business_date':today,'shift_code':'treasury','incident_reason':'absence',
           'cash_location':'drawer','custodian_name':'موظف آخر','doc_count':0,
           'linked_count':0,'status':'draft'}]},
      '/api/late-entries/41':{'incident':{
          'id':41,'point_id':1,'business_date':today,'shift_code':'evening',
          'note':'تم تحصيل النقدية ووضعها في ظرف مختوم للتسليم عند عودة النظام',
          'custodian_name':'مسؤول اختبار','cash_location':'envelope','counted_cash_piasters':150000,
          'status':'submitted','opened_by':5},
          'documents':[{'id':88,'paper_ref':'PAPER-REC-001','kind':'patient_receipt',
                        'method':'cash','amount_piasters':150000,'linked_id':None}],
          'evidence':[{'id':2,'filename':'scan-of-envelope.png'}],
          'events':[{'username':'موظف اختبار','created_at':today,'note':'تم تسجيل الظرف ولا توجد حركة مالية جديدة'}]},
    }
    fixtures[f'/api/late-entries?month={month}']=fixtures['/api/late-entries']
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',
                args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            ctx=browser.new_context(viewport={'width':1365,'height':900},timezone_id='Africa/Cairo')
            page=ctx.new_page();errors=[];console_errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('console',lambda m:console_errors.append(m.text) if m.type=='error' else None)
            page.set_content(html)
            page.add_style_tag(content=(ROOT/'static/styles.css').read_text(encoding='utf-8'))
            page.evaluate('''data=>{window.fetch=async(url,opt)=>({ok:!!data[url],status:data[url]?200:404,
               json:async()=>data[url]||{detail:'missing fixture '+url}})}''',fixtures)
            for name in ('cashier_ops_ui.js','financial_corrections_ui.js','billing.js',
                         'late_entry_ui.js','app.js'):
                page.add_script_tag(content=(ROOT/'static'/name).read_text(encoding='utf-8'))
            page.wait_for_selector('#shell:not([hidden])')
            page.evaluate("navigate('dashboard')")
            page.wait_for_selector('#dashboardLateEntriesAlert .info-box')
            assert '2 واقعة استدراك' in page.locator('#dashboardLateEntriesAlert').inner_text()
            page.evaluate("navigate('lateEntries')")
            page.wait_for_selector('#lateIncidentForm')
            assert page.locator('#lateIncidentForm [name=shift_code]').count()==1
            assert page.locator('[data-late-open]').count()==2
            assert 'لا يُنشئ' in page.locator('#content').inner_text()
            page.screenshot(path=str(OUT/'QA_V81E_G2A_LATE_ENTRIES_DESKTOP.png'),full_page=True)
            page.locator('[data-late-open="41"]').click()
            page.wait_for_selector('[data-late-link="88"]')
            assert page.locator('[data-late-proof="2"]').count()==1
            assert 'لا ترحيل مالي' in page.locator('#content').inner_text()
            page.screenshot(path=str(OUT/'QA_V81E_G2A_LATE_DETAIL_DESKTOP.png'),full_page=True)
            page.set_viewport_size({'width':375,'height':820})
            page.wait_for_timeout(180)
            assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1'),page.evaluate('document.documentElement.scrollWidth')
            page.screenshot(path=str(OUT/'QA_V81E_G2A_LATE_DETAIL_MOBILE.png'),full_page=True)
            page.evaluate("navigate('lateEntries')")
            page.wait_for_selector('#lateIncidentForm')
            assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1'),page.evaluate('document.documentElement.scrollWidth')
            page.screenshot(path=str(OUT/'QA_V81E_G2A_LATE_ENTRIES_MOBILE.png'),full_page=True)
            assert not errors,errors
            assert not console_errors,console_errors
            print('PASS browser G2A: incident intake, matching details, RTL desktop+375px mobile no overflow/errors')
        finally:
            browser.close()

if __name__=='__main__':run()
