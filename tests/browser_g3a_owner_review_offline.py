"""Chromium owner UI checks medical identity review without real identities or network."""
from browser_helpers import chromium_options
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]


def run():
    html=(ROOT/'static/index.html').read_text()
    for asset in ('<link rel="stylesheet" href="/static/styles.css">',
                  '<script src="/static/app.js" defer></script>',
                  '<script src="/static/billing.js" defer></script>'):
        html=html.replace(asset,'')
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,**chromium_options(),
                                  args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            for width in (375,1440):
                page=browser.new_page(viewport={'width':width,'height':900})
                errors=[]
                page.on('pageerror',lambda ex:errors.append(str(ex)))
                page.set_content(html)
                page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
                page.evaluate('''()=>{
                    window.__reviews=[];window.__requests=[];
                    window.fetch=async(url,options={})=>{
                      window.__requests.push(url);
                      let data;
                      if(url==='/api/me')data={id:1,role:'owner',username:'synthetic_owner',csrf:'synthetic-csrf'};
                      else if(url==='/api/lookups')data={departments:[{id:7,name:'Synthetic laboratory',code:'LAB'}],
                                  categories:[],funds:[],employees:[],shifts:[]};
                      else if(url==='/api/inventory/overview')return {ok:false,status:403,json:async()=>({detail:'not needed in admin test'})};
                      else if(url==='/api/dashboard?month='+new Date().toLocaleDateString('sv-SE').slice(0,7))
                          data={receipts_piasters:0,payments_piasters:0,cash_difference_piasters:0,pending:0,daily:[],latest:[],legacy_issues:0};
                      else if(url.startsWith('/api/dashboard?'))
                          data={receipts_piasters:0,payments_piasters:0,cash_difference_piasters:0,pending:0,daily:[],latest:[],legacy_issues:0};
                      else if(url.startsWith('/api/shifts/coverage'))data={summary:{}};
                      else if(url==='/api/users')data=[
                          {id:1,username:'synthetic_owner',role:'owner',active:1},
                          {id:8,username:'synthetic_clinician',role:'clinician',active:1}];
                      else if(url==='/api/periods')data=[];
                      else if(url==='/api/audit')data=[];
                      else if(url==='/api/sync-status')data={configured:false,dirty:false};
                      else if(url==='/api/fund-access')data=[];
                      else if(url==='/api/billing/clinical/identity-review'&&options.method==='POST'){
                        window.__reviews.push(JSON.parse(options.body));data={user_id:8,approved:true};
                      }
                      else return {ok:false,status:404,json:async()=>({detail:'Missing synthetic '+url})};
                      return {ok:true,status:200,json:async()=>data};
                    };
                }''')
                page.add_script_tag(content=(ROOT/'static/app.js').read_text())
                page.wait_for_selector('#shell:not([hidden])',timeout=10000)
                if width==375:page.locator('#showSidebar').click()
                page.locator('[data-view="admin"]').click()
                page.wait_for_selector('#clinicalIdentitySetup',timeout=8000)
                page.locator('#clinicalIdentitySetup').click()
                page.wait_for_selector('dialog select[name="user_id"]',timeout=8000)
                page.locator('dialog select[name="user_id"]').select_option('8')
                page.locator('dialog input[name="professional_name"]').fill('Synthetic Clinician Identity')
                page.locator('dialog input[name="registration_reference"]').fill('SYN-LICENSE-2026-00008')
                page.locator('dialog input[name="review_note"]').fill('Manual simulated credential review only')
                page.locator('dialog select[name="approved"]').select_option('true')
                page.locator('dialog input[name="current_password"]').fill('synthetic_test_owner_password')
                page.locator('#modalConfirm').click()
                page.wait_for_function('window.__reviews.length===1',timeout=8000)
                item=page.evaluate('window.__reviews[0]')
                assert item['approved'] is True and item['user_id']==8,item
                assert item['current_password']=='synthetic_test_owner_password'
                assert not errors,(width,errors)
                assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1'),width
                page.close()
            print('PASS G3A owner medical review modal in Chromium 375/1440; synthetic payload and owner confirmation')
        finally:
            browser.close()


if __name__=='__main__':run()
