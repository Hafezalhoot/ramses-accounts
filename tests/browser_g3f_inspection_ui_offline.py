"""Chromium 320/375/1440: independent clinical inspection UI, no prices or patient data."""
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
        browser=p.chromium.launch(headless=True,**chromium_options(),
                                args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            for width in (320,375,1440):
                page=browser.new_page(viewport={'width':width,'height':860})
                errors=[]
                page.on('pageerror',lambda exc:errors.append(str(exc)))
                page.set_content(html)
                page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
                page.evaluate('''()=>{
                  window.__decisions=[]; window.__paths=[];
                  window.__inspections=[
                   {return_line_id:41,return_id:21,returned_on:'2026-11-01',
                    department_name:'Synthetic operating room',item_name:'Test sealed surgical tool',
                    item_code:'G3F-TOOL',batch_ref:'SYNTHETIC-LOT-A',quantity:2,expiry_date:'2027-11-01'},
                   {return_line_id:42,return_id:22,returned_on:'2026-11-01',
                    department_name:'Synthetic operating room',item_name:'Test contaminated container',
                    item_code:'G3F-UNIT',batch_ref:'SYNTHETIC-LOT-B',quantity:1,expiry_date:'2027-11-01'}];
                  window.fetch=async(url,options={})=>{
                    window.__paths.push(url);
                    let data;
                    if(url==='/api/me')data={id:8,username:'synthetic_medical_reviewer',role:'clinician',csrf:'test'};
                    else if(url==='/api/billing/clinical/queue')data={items:[]};
                    else if(url==='/api/inventory/inspections/queue')data={items:window.__inspections};
                    else if(url.startsWith('/api/inventory/inspections/')&&url.endsWith('/decision')&&options.method==='POST'){
                      const body=JSON.parse(options.body);window.__decisions.push({url,body});
                      const id=Number(url.split('/')[4]);
                      window.__inspections=window.__inspections.filter(x=>x.return_line_id!==id);
                      data={return_line_id:id,status:body.decision==='release'?'released':'rejected'};
                    }else return {ok:false,status:403,json:async()=>({detail:'No finance API for clinical role'})};
                    return {ok:true,status:200,json:async()=>data};
                  };
                }''')
                page.add_script_tag(content=(ROOT/'static/app.js').read_text())
                page.locator('[data-return-inspect="41:release"]').wait_for(timeout=10000)
                assert page.locator('[data-return-inspect="42:reject"]').count()==1
                assert '/api/lookups' not in page.evaluate('window.__paths')
                assert 'G3F-TOOL' in page.locator('#content').inner_text()
                assert 'ج.م' not in page.locator('#content').inner_text()
                page.locator('[data-return-inspect="41:release"]').click()
                page.locator('dialog input[name="evidence_ref"]').fill('SYNTHETIC-APPROVED-IC-REFERENCE')
                page.locator('dialog input[name="note"]').fill('Synthetic packaging checked and safely handled')
                for name in ('unused_confirmed','packaging_intact','infection_control_clearance'):
                    page.locator(f'dialog select[name="{name}"]').select_option('true')
                page.locator('#modalConfirm').click()
                page.wait_for_function('window.__decisions.length===1',timeout=10000)
                first=page.evaluate('window.__decisions[0]')
                assert first['body']['decision']=='release' and all(first['body'][k] for k in (
                    'unused_confirmed','packaging_intact','infection_control_clearance')),first
                assert first['body']['inspected_on']==page.evaluate(
                    "new Date().toLocaleDateString('sv-SE',{timeZone:'Africa/Cairo'})"),first
                page.locator('[data-return-inspect="42:reject"]').wait_for(timeout=8000)
                page.locator('[data-return-inspect="42:reject"]').click()
                page.locator('dialog input[name="evidence_ref"]').fill('SYNTHETIC-REJECTED-ITEM-REFERENCE')
                page.locator('dialog input[name="note"]').fill('Synthetic damaged protective wrapper; never reuse')
                page.locator('#modalConfirm').click()
                page.wait_for_function('window.__decisions.length===2',timeout=8000)
                assert page.evaluate('window.__decisions[1].body.decision')=='reject'
                page.wait_for_function('document.querySelectorAll("[data-return-inspect]").length===0')
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
                assert not errors,(width,errors)
                page.close()
            print('PASS G3F Chromium clinician quarantine UI 320/375/1440, independent release/reject and no finance endpoints')
        finally:browser.close()

if __name__=='__main__':run()
