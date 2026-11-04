"""G2O isolated Chromium smoke: per-point grant UX and revoked-reviewer empty state.

This is synthetic HTML/JS verification, NOT a live server or patient test.
"""
from browser_helpers import chromium_options
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
SETUP=r'''
window.state={me:{id:1,role:'owner'},lookups:{departments:[],funds:[]}};
window.$=s=>document.querySelector(s);
window.$$=s=>[...document.querySelectorAll(s)];
window.esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
window.ico=()=>'';
window.head=(a,b,c,d)=>`<header><h1>${window.esc(b)}</h1><p>${window.esc(c)}</p>${d||''}</header>`;
window.empty=s=>`<p class="empty">${window.esc(s)}</p>`;
window.fmt=n=>(Number(n||0)/100).toFixed(2);
window.integer=n=>Number(n||0);
window.table=(h,rows)=>`<table><tbody>${rows}</tbody></table>`;
window.toast=(a,b)=>{window.lastToast={a,b}};
window.navigate=route=>{window.lastNavigate=route};
window.modal=async(title,description,fields)=>{
  window.modalView={title,description,fields};
  return {user_id:'2',point_id:'11',active:'false'};
};
window.api=async url=>{
 if(url==='/api/users')return [{id:2,username:'auditor_ext',role:'reviewer',active:1},
                                   {id:3,username:'outpatient_cashier',role:'clerk',active:1}];
 if(url==='/api/billing/config')return window.fixtureConfig;
 if(url==='/api/billing/cases?point_id=11')return {items:[]};
 return {items:[]};
};
window.post=async(url,payload)=>{window.lastPost={url,payload};return {ok:true};};
window.fixtureConfig={points:[{id:11,name:'الخارجي التجريبي',kind:'external',fund_id:0,active:true}],
                      services:[],payment_channels:[]};
'''


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,**chromium_options(),
                                  args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            for width in (1440,375,320):
                page=browser.new_page(viewport={'width':width,'height':850})
                errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.set_content('<!doctype html><html lang="ar" dir="rtl"><head><meta name="viewport" '
                                 'content="width=device-width, initial-scale=1"></head><body>'
                                 '<main id="content"></main></body></html>')
                page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
                page.evaluate(SETUP)
                page.add_script_tag(content=(ROOT/'static/billing.js').read_text())
                page.evaluate('renderBilling()')
                page.locator('#billingAssign').wait_for()
                page.locator('#billingAssign').click()
                page.wait_for_function('!!window.lastPost')
                result=page.evaluate('({modal:window.modalView,post:window.lastPost})')
                assert result['post']['url']=='/api/billing/points/11/assign',result
                assert result['post']['payload']=={'user_id':2,'active':False},result
                assert 'مراجع' in str(result['modal']['fields']),result
                assert 'سحب التصريح' in str(result['modal']['fields']),result
                # Revoked staff sees the denial state, without case names or stale controls.
                page.evaluate("window.state.me={id:2,role:'reviewer'};window.fixtureConfig.points=[];billingState.caseId=null")
                page.evaluate('renderBilling()')
                page.get_by_text('لا توجد نقطة تحصيل مخصصة لحسابك').wait_for()
                assert page.locator('.billing-case-item').count()==0
                assert page.locator('#billingAssign').count()==0
                assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+2'),width
                assert not errors,errors
                if width==375:
                    page.screenshot(path=str(ROOT/'qa_screenshots/G2O_PATIENT_PERMISSIONS_375.png'),full_page=True)
                page.close()
            print('PASS G2O Chromium reviewer grant/revoke modal and denied empty state, 1440/375/320, no page errors/overflow')
        finally:
            browser.close()

if __name__=='__main__':run()
