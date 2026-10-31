"""G2D desktop/mobile UI happy-path with synthetic backend; no real patients."""
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
       '/api/me':{'id':22,'username':'reviewer','role':'reviewer','csrf':'test','environment':'staging'},
       '/api/lookups':{'funds':[], 'employees':[],
          'departments':[{'id':1,'code':'ADMIN','name':'الحسابات والإدارة'}],
          'categories':[{'id':9,'code':'hospitality','name':'مصروفات ضيافة','direction':'payment'}],
          'shifts':[]},
       '/api/billing/config':{'points':[{'id':7,'name':'الخزنة الرئيسية','kind':'internal','fund_id':3}]},
       '/api/shifts/coverage?month=2026-10':{'items':[]},
      '/api/late-entries/shortage-open':{'items':[]},
       '/api/late-entries':{'items':[{'id':50,'point_id':7,'point_name':'الخزنة الرئيسية',
            'business_date':'2026-09-28','shift_code':'treasury','incident_reason':'absence',
            'cash_location':'envelope','custodian_name':'الموظف المناوب',
            'doc_count':2,'linked_count':0,'status':'triaged'}]},
       '/api/late-entries/50':{'point_kind':'internal',
          'incident':{'id':50,'point_id':7,'business_date':'2026-09-28','shift_code':'treasury',
                     'status':'triaged','opened_by':5,'reviewed_by':22,
                     'cash_location':'main_safe','custodian_name':'الموظف المناوب',
                     'counted_cash_piasters':130000,
                     'note':'ظرف قديم يضم تحصيل مرضى ومصروفًا تم من نفس النقدية'},
          'documents':[{'id':91,'paper_ref':'ENV-PAT-91','kind':'patient_receipt','method':'cash',
                        'amount_piasters':150000,'linked_id':None,'cash_clearance_id':None,
                        'mixed_clearance_id':None},
                       {'id':92,'paper_ref':'ENV-EXP-92','kind':'expense','method':'cash',
                        'amount_piasters':20000,'linked_id':None,'cash_clearance_id':None,
                        'mixed_clearance_id':None}],
          'recovered_cases':[{'case_id':11,'paper_document_id':91,'case_no':'CASE-2026-000011',
                             'original_business_date':'2026-09-28',
                             'issued_invoice_no':'INV-2026-000021','issued_invoice_id':21}],
          'cash_allocations':[],'mixed_clearance':None,'mixed_lines':[],
          'evidence':[{'id':4,'filename':'envelope.png'}],
          'events':[{'username':'reviewer','created_at':'2026-10-30','note':'فحص مستقل'}]}
    }
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',
                                  args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            for width in (1365,375):
                ctx=browser.new_context(viewport={'width':width,'height':900})
                page=ctx.new_page()
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.set_content(html)
                page.add_style_tag(content=(ROOT/'static/styles.css').read_text(encoding='utf8'))
                page.evaluate('''mock=>{
                 window.__mixed=[];
                 window.fetch=async(url,opt)=>{
                   if(String(url).includes('/clear-mixed-envelope')){
                      window.__mixed.push(JSON.parse(opt.body));
                      return {ok:true,status:200,json:async()=>({id:1,variance_piasters:0,cash_newly_booked_piasters:0})};
                   }
                   return {ok:!!mock[url],status:mock[url]?200:404,
                          json:async()=>mock[url]||{detail:'missing '+url}};
                 };
                }''',mock)
                for name in ('cashier_ops_ui.js','financial_corrections_ui.js','billing.js','late_entry_ui.js','app.js'):
                    page.add_script_tag(content=(ROOT/'static'/name).read_text(encoding='utf8'))
                page.wait_for_selector('#shell:not([hidden])')
                page.evaluate("navigate('lateEntries')")
                page.locator('[data-late-open="50"]').click()
                b=page.locator('[data-late-mixed="50"]');b.wait_for()
                assert 'الظرف المختلط' in page.locator('#content').inner_text()
                assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1')
                page.screenshot(path=str(OUT/f'QA_G2D_MIXED_{width}.png'),full_page=True)
                b.click()
                page.wait_for_selector('#modal[open]')
                page.locator('#modalFields [name=voucher_id]').fill('88')
                page.locator('#modalFields [name=approve_variance]').select_option('no')
                page.locator('#modalFields [name=note]').fill('مراجعة مستقلة موثقة لظرف مختلط وتحويله إلى الأستاذ دون تكرار قبض')
                page.locator('#modalConfirm').click()
                page.wait_for_selector('#modal[open]')
                page.locator('#modalFields [name=category_code]').select_option('hospitality')
                page.locator('#modalFields [name=department_id]').select_option('1')
                page.locator('#modalConfirm').click()
                page.wait_for_function('window.__mixed.length===1')
                data=page.evaluate('window.__mixed[0]')
                assert data['patients']==[{'document_id':91,'invoice_id':21}],data
                assert data['expenses']==[{'document_id':92,'category_code':'hospitality','department_id':1}],data
                assert data['voucher_id']==88 and data['approve_variance'] is False and data['request_id'],data
                assert not errors,errors
                ctx.close()
            print('PASS browser G2D mixed: reviewer flow / expense category / 1365px + 375px')
        finally:
            browser.close()
if __name__=='__main__':run()
