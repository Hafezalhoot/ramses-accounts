"""G2C RTL desktop/mobile interaction test using synthetic browser API fixtures."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT.parent

def run():
    html=(ROOT/'static/index.html').read_text(encoding='utf-8')
    for name in ('app.js','cashier_ops_ui.js','financial_corrections_ui.js','billing.js','late_entry_ui.js'):
        html=html.replace(f'<script src="/static/{name}" defer></script>','')
    html=html.replace('<link rel="stylesheet" href="/static/styles.css">','')
    points=[{'id':1,'name':'الكاشير الخارجي','code':'OUT','kind':'external','fund_id':2}]
    data={
      '/api/me':{'id':22,'username':'accountant','role':'reviewer','csrf':'test','environment':'staging'},
      '/api/lookups':{'funds':[],'employees':[],'departments':[],'categories':[],'shifts':[]},
      '/api/billing/config':{'points':points},
      '/api/late-entries/shortage-open':{'items':[]},
      '/api/late-entries':{'items':[{'id':41,'point_id':1,'point_name':'الكاشير الخارجي',
        'business_date':'2026-09-29','shift_code':'night','incident_reason':'outage',
        'cash_location':'envelope','custodian_name':'موظف اختبار','doc_count':1,
        'linked_count':0,'status':'triaged'}]},
      '/api/late-entries/41':{'incident':{'id':41,'business_date':'2026-09-29',
         'point_id':1,'shift_code':'night','note':'إيصالات متأخرة موثقة بمستندات الخزنة الرئيسية',
         'custodian_name':'موظف اختبار','cash_location':'envelope',
         'counted_cash_piasters':90000,'status':'triaged','opened_by':5,'reviewed_by':22},
         'documents':[{'id':88,'paper_ref':'PAPER-88','kind':'patient_receipt',
           'method':'cash','amount_piasters':90000,'linked_id':None,'cash_clearance_id':None}],
         'recovered_cases':[{'case_id':12,'paper_document_id':88,'case_no':'CASE-2026-000012',
           'original_business_date':'2026-09-29','issued_invoice_no':'INV-2026-000017',
           'issued_invoice_id':17}],
         'cash_allocations':[],'evidence':[],
         'events':[{'username':'accountant','created_at':'2026-10-30','note':'قبول للمطابقة'}]}
    }
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',
              args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            for size in (1365,375):
                ctx=browser.new_context(viewport={'width':size,'height':900})
                page=ctx.new_page();errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.set_content(html)
                page.add_style_tag(content=(ROOT/'static/styles.css').read_text(encoding='utf-8'))
                page.evaluate('''source=>{
                  window.__cashCalls=[];
                  window.fetch=async(url,opt)=>{
                    if(String(url).includes('/clear-booked-cash')){
                      window.__cashCalls.push({url,body:JSON.parse(opt.body)});
                      return {ok:true,status:200,json:async()=>({id:1,amount_piasters:90000,cash_newly_booked_piasters:0})};
                    }
                    return {ok:!!source[url],status:source[url]?200:404,
                      json:async()=>source[url]||{detail:'missing '+url}};
                  };
                }''',data)
                for name in ('cashier_ops_ui.js','financial_corrections_ui.js','billing.js',
                             'late_entry_ui.js','app.js'):
                    page.add_script_tag(content=(ROOT/'static'/name).read_text(encoding='utf-8'))
                page.wait_for_selector('#shell:not([hidden])')
                page.evaluate("navigate('lateEntries')")
                page.wait_for_selector('[data-late-open="41"]')
                page.locator('[data-late-open="41"]').click()
                button=page.locator('[data-late-clear="88"]')
                button.wait_for()
                assert 'تسوية من النقدية المثبتة' in button.inner_text()
                assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1')
                page.screenshot(path=str(OUT/f'QA_V81E_G2C_CLEAR_{size}.png'),full_page=True)
                button.click()
                page.wait_for_selector('#modal[open]')
                page.locator('#modalFields [name=voucher_id]').fill('99')
                page.locator('#modalFields [name=note]').fill('مراجعة السند والظرف والفاتورة من خلال محضر التسوية المعتمد')
                page.locator('#modalConfirm').click()
                page.wait_for_function('window.__cashCalls.length===1')
                request=page.evaluate('window.__cashCalls[0]')
                assert request['body']['voucher_id']==99 and request['body']['invoice_id']==17
                assert request['body']['request_id']
                assert not errors,errors
                ctx.close()
            print('PASS browser G2C: reviewer action, invoice/voucher binding, RTL 1365px + 375px no overflow')
        finally:
            browser.close()

if __name__=='__main__':run()
