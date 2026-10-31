"""Real Chromium pilot UI: clinical witness can submit one evidence reference.

All patient labels, auth identities and responses are synthetic; the network is stubbed.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]


def run():
    html=(ROOT/'static/index.html').read_text()
    for tag in ('<link rel="stylesheet" href="/static/styles.css">',
                '<script src="/static/app.js" defer></script>',
                '<script src="/static/billing.js" defer></script>'):
        html=html.replace(tag,'')
    source=(ROOT/'static/app.js').read_text()
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',
                                  args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            for width in (320,375,1440):
                page=browser.new_page(viewport={'width':width,'height':900})
                failures=[]
                page.on('pageerror',lambda exc:failures.append(str(exc)))
                page.set_content(html)
                page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
                page.evaluate('''()=>{
                  window.__attests=[];
                  window.__pending=[{line_id:31,department_id:1,service_name:'Synthetic laboratory test',
                   quantity:1,state:'ordered',service_date:null,case_no:'CASE-SYN-001',patient_code:'PAT-SYN-001'}];
                  window.fetch=async(url,options={})=>{
                    let data;
                    if(url==='/api/me')data={id:8,username:'clinical_synthetic',role:'viewer',csrf:'mock'};
                    else if(url==='/api/lookups')data={departments:[{id:1,name:'Synthetic lab'}],funds:[],employees:[],categories:[]};
                    else if(url==='/api/billing/clinical/queue')data={items:window.__pending};
                    else if(url==='/api/billing/clinical/lines/31/attest' && options.method==='POST'){
                      const payload=JSON.parse(options.body);
                      window.__attests.push(payload);
                      window.__pending=[];
                      data={line_id:31,state:'fulfilled'};
                    }
                    else if(url.startsWith('/api/dashboard?'))data={receipts_piasters:0,payments_piasters:0,cash_difference_piasters:0,pending:0,daily:[],latest:[],legacy_issues:0};
                    else if(url.startsWith('/api/reports?'))data={categories:[],departments:[],gl_departments:[],note:'synthetic',scope:'authorized_cash_only'};
                    else return {ok:false,status:404,json:async()=>({detail:'missing fixture '+url})};
                    return {ok:true,status:200,json:async()=>data};
                  };
                }''')
                page.add_script_tag(content=source)
                page.wait_for_selector('#shell:not([hidden])',timeout=9000)
                if width<=375:page.locator('#showSidebar').click()
                clinical=page.locator('#mainNav [data-view="clinical"]')
                assert clinical.count()==1 and clinical.is_visible(), 'Viewer clinical section missing'
                clinical.click()
                page.wait_for_selector('[data-clinical-attest="31"]',timeout=8000)
                assert 'Synthetic laboratory test' in page.locator('#content').inner_text()
                assert 'ج.م' not in page.locator('#content').inner_text(), 'Clinical list includes financial sums'
                page.locator('[data-clinical-attest="31"]').click()
                page.locator('dialog input[name="evidence_reference"]').fill('SYN-CLINICAL-REFERENCE-0031')
                page.locator('#modalConfirm').click()
                page.wait_for_function('window.__attests.length===1',timeout=9000)
                assert page.evaluate('window.__attests[0].evidence_reference')=='SYN-CLINICAL-REFERENCE-0031'
                assert page.locator('[data-clinical-attest="31"]').count()==0
                assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1')
                assert not failures,(width,failures)
                page.close()
            print('PASS G2Z real Chromium: isolated clinical queue / modal / mobile 320/375 and desktop 1440')
        finally:browser.close()

if __name__=='__main__':run()
