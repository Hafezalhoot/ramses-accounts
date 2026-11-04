"""Real Chromium UI: source file + reference form and one-way admin policy.

Synthetic network/memory only; the uploaded file is never a real medical doc.
Mutation caught: ref-only UI when policy requires a file, or missing owner confirmation.
"""
from browser_helpers import chromium_options
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]


def run():
    html=(ROOT/'static/index.html').read_text()
    for tag in ('<link rel="stylesheet" href="/static/styles.css">',
                '<script src="/static/app.js" defer></script>',
                '<script src="/static/billing.js" defer></script>'):
        html=html.replace(tag,'')
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,**chromium_options(),args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            for width in (320,375,1440):
                page=browser.new_page(viewport={'width':width,'height':900})
                errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.set_content(html)
                page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
                page.evaluate('''()=>{
                  window.__attests=[];window.__requests=[];
                  window.fetch=async(url,options={})=>{
                    window.__requests.push(url);let data;
                    if(url==='/api/me')data={id:8,role:'clinician',username:'synthetic_clinician',csrf:'synthetic_csrf'};
                    else if(url==='/api/billing/clinical/queue')data={items:[{
                        line_id:31,department_id:7,service_name:'Synthetic clinical service',
                        quantity:1,document_required:1,state:'ordered',service_date:null,
                        case_no:'SYN-CASE-31',patient_code:'SYN-PAT-31'}]};
                    else if(url==='/api/billing/clinical/lines/31/attest-document' && options.method==='POST'){
                      if(!(options.body instanceof FormData))throw Error('File not sent as multipart');
                      const doc=options.body.get('file');
                      window.__attests.push({reference:options.body.get('evidence_reference'),
                       size:doc?.size||0,filename:doc?.name||'',type:doc?.type||''});
                      data={line_id:31,state:'fulfilled',document_sha256:'b'.repeat(64)};
                    }
                    else return {ok:false,status:403,json:async()=>({detail:'not authorized: '+url})};
                    return {ok:true,status:200,json:async()=>data};
                  };
                }''')
                page.add_script_tag(content=(ROOT/'static/app.js').read_text())
                page.wait_for_selector('[data-clinical-attest="31"]',timeout=8000)
                page.locator('[data-clinical-attest="31"]').click()
                required=page.locator('dialog input[name="file"]')
                assert required.count()==1 and required.get_attribute('required') is not None, 'Protected clinical form must require file'
                page.locator('dialog input[name="evidence_reference"]').fill('SYN-G3B-SOURCE-REFERENCE')
                required.set_input_files({'name':'synthetic_report.pdf','mimeType':'application/pdf',
                                          'buffer':b'%PDF-1.4\n%%EOF'})
                page.locator('#modalConfirm').click()
                page.wait_for_function('window.__attests.length===1',timeout=8000)
                found=page.evaluate('window.__attests[0]')
                assert found['reference']=='SYN-G3B-SOURCE-REFERENCE' and found['size']>0,found
                assert '/api/lookups' not in page.evaluate('window.__requests')
                assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1'),width
                assert not errors,(width,errors)
                page.close()
            # Owner setup on phone and desktop.
            for width in (375,1440):
                page=browser.new_page(viewport={'width':width,'height':900})
                errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.set_content(html)
                page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
                page.evaluate('''()=>{
                  window.__requirements=[];
                  window.fetch=async(url,opt={})=>{
                    let data;
                    if(url==='/api/me')data={id:1,username:'synthetic_owner',role:'owner',csrf:'csrf'};
                    else if(url==='/api/lookups')data={departments:[{id:7,name:'Synthetic lab',code:'LAB'}],categories:[],funds:[],employees:[],shifts:[]};
                    else if(url==='/api/inventory/overview')return {ok:false,status:403,json:async()=>({detail:'not needed'})};
                    else if(url==='/api/users')data=[];
                    else if(url==='/api/periods'||url==='/api/audit'||url==='/api/fund-access')data=[];
                    else if(url==='/api/sync-status')data={configured:false,dirty:false};
                    else if(url.startsWith('/api/dashboard?'))data={receipts_piasters:0,payments_piasters:0,cash_difference_piasters:0,pending:0,daily:[],latest:[],legacy_issues:0};
                    else if(url==='/api/billing/clinical/departments/7/require-document'){
                        window.__requirements.push(JSON.parse(opt.body));data={document_required:true};
                    }
                    else return {ok:false,status:403,json:async()=>({detail:'missing mock '+url})};
                    return {ok:true,status:200,json:async()=>data};
                  };
                }''')
                page.add_script_tag(content=(ROOT/'static/app.js').read_text())
                page.wait_for_selector('#shell:not([hidden])',timeout=8000)
                if width==375:page.locator('#showSidebar').click()
                page.locator('[data-view="admin"]').click()
                page.wait_for_selector('#clinicalDocumentSetup',timeout=8000)
                page.locator('#clinicalDocumentSetup').click()
                page.locator('dialog select[name="department_id"]').select_option('7')
                page.locator('dialog input[name="current_password"]').fill('synthetic_g3b_owner_password')
                page.locator('#modalConfirm').click()
                page.wait_for_function('window.__requirements.length===1',timeout=8000)
                assert page.evaluate('window.__requirements[0].current_password')=='synthetic_g3b_owner_password'
                assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1')
                assert not errors,(width,errors)
                page.close()
            print('PASS G3B Chromium source document hash UI and owner one-way opt-in, widths 320/375/1440')
        finally:
            browser.close()
if __name__=='__main__':run()
