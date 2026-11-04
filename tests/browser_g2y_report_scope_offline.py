"""Chromium UI regression: no false financial totals; accounting page respects owner-only treasury.

Fixtures are synthetic. Browser interaction is real, network requests are stubbed.
"""
from browser_helpers import chromium_options
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def run():
    html=(ROOT/'static/index.html').read_text()
    html=html.replace('<link rel="stylesheet" href="/static/styles.css">','')
    html=html.replace('<script src="/static/app.js" defer></script>','').replace('<script src="/static/billing.js" defer></script>','')
    report={'month':'2026-10','scope':'authorized_cash_only','categories':[
        {'category':'Synthetic visible expense','nature':'expense','amount_piasters':3000}],
        'departments':[{'department':'Synthetic admin','earned_cash_in':10000,'operating_cash_out':3000,
                        'non_operating_cash_out':0}],
        'gl_departments':[],'recognized_revenue_piasters':None,'recognized_expenses_piasters':None,
        'provisional_gl_result_piasters':None,'approved_payroll_accruals_piasters':None,
        'rough_margin_piasters':None, 'recognized_cash_service_revenue_piasters':10000,
        'cash_paid_operating_items_piasters':3000,
        'note':'تقرير نقدية مقيد بالسندات المسموح بالاطلاع عليها فقط؛ لا يعرض كامل دفتر الأستاذ أو الرواتب.'}
    trial={'trial_balance':{'accounts':[],'debit_piasters':0,'credit_piasters':0,'balanced':True},
           'coverage':{'unposted_vouchers':0,'unposted_payroll':0,'unposted_allocations':0,
                       'unverified_opening_funds':0,'pending_journals':0,'historical_unverified':0,
                       'readiness_reason':'Synthetic trial balance only'}}
    integrity={'matched':True,'checks':[], 'scope':'Synthetic patient reconciliation'}
    treasury={'matched':True,'funds':[], 'issues':[],'scope':'Synthetic vault reconciliation',
              'opening_review_required':0,'issue_count':0}
    source=(ROOT/'static/app.js').read_text()
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,**chromium_options(),
                                  args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            for role in ('viewer','reviewer','owner'):
                page=browser.new_page(viewport={'width':375 if role=='viewer' else 1440,
                                                'height':820})
                errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.set_content(html)
                page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
                page.evaluate('''({role,report,trial,integrity,treasury})=>{
                  window.__calls=[];
                  window.fetch=async url=>{
                    window.__calls.push(url);
                    let response;
                    if(url==='/api/me')response={id:role==='owner'?1:2,username:'synthetic_'+role,
                                                 role,csrf:'synthetic'};
                    else if(url==='/api/lookups')response={funds:[],employees:[],departments:[],categories:[]};
                    else if(url.startsWith('/api/dashboard?'))response={receipts_piasters:10000,
                     payments_piasters:3000,cash_difference_piasters:7000,pending:0,daily:[],latest:[],legacy_issues:0};
                    else if(url.startsWith('/api/reports?'))response=report;
                    else if(url.startsWith('/api/accounting/trial-balance?'))response=trial;
                    else if(url.startsWith('/api/accounting/journals?'))response={items:[],count:0};
                    else if(url.startsWith('/api/accounting/patient-reconciliation?'))response=integrity;
                    else if(url.startsWith('/api/accounting/treasury-reconciliation?')){
                      if(role!=='owner')return {ok:false,status:403,json:async()=>({detail:'owner only'})};
                      response=treasury;
                    }else if(url.startsWith('/api/reconciliation/variances?'))response={items:[],proposed_count:0,
                       shortage_piasters:0,overage_piasters:0};
                    else return {ok:false,status:404,json:async()=>({detail:'missing fixture: '+url})};
                    return {ok:true,status:200,json:async()=>response};
                  };
                }''', {'role':role,'report':report,'trial':trial,'integrity':integrity,'treasury':treasury})
                page.add_script_tag(content=source)
                page.wait_for_selector('#shell:not([hidden])',timeout=9000)
                if role=='viewer':
                    assert page.locator('#mainNav [data-view=accounting]').is_hidden(), 'Viewer must not be invited into protected GL'
                    page.locator('#showSidebar').click()
                    page.locator('#mainNav [data-view=reports]').click()
                    page.wait_for_selector('.mini-metrics', timeout=8000)
                    content=page.locator('#content').inner_text()
                    assert 'المقبوضات المرئية' in content, content[:500]
                    assert 'إيراد مُثبت بالأستاذ' not in content, 'Viewer report mislabels hidden GL as zero'
                    assert 'Synthetic visible expense' in content
                    assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth+1')
                    assert not any('/api/accounting/treasury-reconciliation' in u for u in page.evaluate('window.__calls'))
                else:
                    page.locator('#mainNav [data-view=accounting]').click()
                    page.wait_for_selector('.accounting-coverage',timeout=8000)
                    if role=='owner':
                        assert page.locator('.treasury-panel').count()==1
                        assert any('/api/accounting/treasury-reconciliation?' in u for u in page.evaluate('window.__calls'))
                        # Same browser after logout/login must never reuse an owner-only DOM.
                        page.evaluate('''async()=>{showLogin();state.me={id:8,username:'viewer_after_owner',role:'viewer',csrf:'synthetic'};await bootstrapUI();}''')
                        page.wait_for_selector('#shell:not([hidden])',timeout=8000)
                        assert page.locator('.treasury-panel').count()==0, 'Owner bank balances remained in DOM after viewer switched roles'
                        assert 'الوضع المالي في لمحة' in page.locator('#content').inner_text(), 'Viewer was stranded on inaccessible accounting route: '+page.locator('#content').inner_text()[:250]
                    else:
                        assert page.locator('.treasury-panel').count()==0
                        assert 'مطابقة الخزن الشاملة للمالك فقط' in page.locator('#content').inner_text()
                        assert not any('/api/accounting/treasury-reconciliation?' in u for u in page.evaluate('window.__calls'))
                assert not errors,(role,errors)
                page.close()
            print('PASS G2Y browser: viewer limited cash report, owner/reviewer accounting, 375px no overflow')
        finally:
            browser.close()

if __name__=='__main__':
    run()
