"""G2E browser smoke: staged shortage cash handover and independent review."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT.parent

def run():
    html=(ROOT/'static/index.html').read_text(encoding='utf8')
    for name in ('app.js','cashier_ops_ui.js','financial_corrections_ui.js','billing.js','late_entry_ui.js'):
        html=html.replace(f'<script src="/static/{name}" defer></script>','')
    html=html.replace('<link rel="stylesheet" href="/static/styles.css">','')
    mock={
     '/api/me':{'id':22,'username':'owner','role':'owner','csrf':'test','environment':'staging'},
     '/api/lookups':{'funds':[],'employees':[],'departments':[],'categories':[],'shifts':[]},
     '/api/billing/config':{'points':[{'id':7,'name':'الخزنة الرئيسية','kind':'internal','fund_id':3}]},
     '/api/shifts/coverage?month=2026-10':{'items':[]},
     '/api/late-entries':{'items':[{'id':50,'point_id':7,'point_name':'الخزنة الرئيسية',
       'business_date':'2026-09-28','shift_code':'treasury','incident_reason':'absence',
       'cash_location':'envelope','custodian_name':'مناوب الخزنة','doc_count':2,'linked_count':2,
       'mixed_variance_piasters':-5000,'mixed_recovered_piasters':0,'status':'resolved'}]},
     '/api/late-entries/shortage-open':{'items':[{'clearance_id':11,'incident_id':50,'business_date':'2026-09-28',
       'source_register_ref':'ENV-50','point_name':'الخزنة الرئيسية','point_id':7,
       'original_shortage_piasters':5000,'recovered_piasters':0,'outstanding_piasters':5000}]},
     '/api/late-entries/50':{
       'point_kind':'internal','incident':{'id':50,'point_id':7,'business_date':'2026-09-28',
         'shift_code':'treasury','status':'resolved','opened_by':5,'reviewed_by':23,
         'cash_location':'main_safe','custodian_name':'المناوب','counted_cash_piasters':125000,
         'note':'تم اعتماد ظرف قديم بعجز خمسين جنيهًا مرتبطًا بالمستندات الأصلية'},
       'documents':[{'id':91,'paper_ref':'PAT-91','kind':'patient_receipt','method':'cash',
                     'amount_piasters':150000,'mixed_clearance_id':11,'linked_id':None},
                    {'id':92,'paper_ref':'EXP-92','kind':'expense','method':'cash',
                     'amount_piasters':20000,'mixed_clearance_id':11,'linked_id':None}],
       'recovered_cases':[],'cash_allocations':[],'events':[],'evidence':[],
       'mixed_clearance':{'id':11,'gross_receipts_piasters':150000,'expense_piasters':20000,
                          'actual_cash_piasters':125000,'variance_piasters':-5000,'journal_id':90},
       'mixed_lines':[],'shortage_total_piasters':5000,'shortage_recovered_piasters':0,
       'shortage_outstanding_piasters':5000,'mixed_shortage_recovery_requests':[]}
    }
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',
                                  args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            for width in (1365,375):
                context=browser.new_context(viewport={'width':width,'height':950})
                page=context.new_page();errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.set_content(html)
                page.add_style_tag(content=(ROOT/'static/styles.css').read_text(encoding='utf8'))
                page.evaluate('''mock=>{
                  window.__calls=[];window.__mock=mock;
                  window.fetch=async(url,options={})=>{
                    if(options.method==='POST'&&String(url).includes('/shortage-recoveries')){
                      window.__calls.push({url:String(url),data:JSON.parse(options.body)});
                      return {ok:true,status:200,json:async()=>({id:31,status:'pending',amount_piasters:3000})};
                    }
                    return {ok:!!window.__mock[url],status:window.__mock[url]?200:404,
                      json:async()=>window.__mock[url]||{detail:'missing '+url}};
                  }
                }''',mock)
                for name in ('cashier_ops_ui.js','financial_corrections_ui.js','billing.js','late_entry_ui.js','app.js'):
                    page.add_script_tag(content=(ROOT/'static'/name).read_text(encoding='utf8'))
                page.wait_for_selector('#shell:not([hidden])')
                page.evaluate("navigate('lateEntries')")
                page.locator('[data-late-open="50"]').last.click()
                page.locator('[data-late-recovery-propose]').wait_for()
                assert 'المتبقي تحت التسوية' in page.locator('#content').inner_text()
                assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1')
                page.screenshot(path=str(OUT/f'QA_G2E_SHORTAGE_{width}.png'),full_page=True)
                page.locator('[data-late-recovery-propose]').click()
                page.wait_for_selector('#modal[open]')
                page.locator('#modalFields [name=receipt_ref]').fill('REC-0045-TEST')
                page.locator('#modalFields [name=source_type]').select_option('employee_deposit')
                page.locator('#modalFields [name=payer_name]').fill('مراجع نقدية للاختبار')
                page.locator('#modalFields [name=amount]').fill('30')
                page.locator('#modalFields [name=note]').fill('تم استلام النقدية فعليًا وعدها داخل الخزنة الحالية مع إثبات المرجع')
                page.locator('#modalConfirm').click()
                page.wait_for_function('window.__calls.length===1')
                posted=page.evaluate('window.__calls[0]')
                assert posted['url']=='/api/late-entries/50/shortage-recoveries',posted
                assert posted['data']['amount']=='30' and posted['data']['source_type']=='employee_deposit',posted
                assert posted['data']['request_id'],posted
                assert not errors,errors
                context.close()
            print('PASS browser G2E owner proposes cash recovery / 1365 + 375 / no JS or horizontal overflow')
        finally:browser.close()

if __name__=='__main__':run()
