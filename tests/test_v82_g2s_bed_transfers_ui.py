"""G2S standalone Chromium browser test: owner bed flow and restricted views."""
from pathlib import Path
from playwright.sync_api import sync_playwright
from test_v82_g2p_case_settlement_ui import SETUP
ROOT=Path(__file__).resolve().parents[1]
EXTRA=r'''
window.state.me={id:1,role:'owner'};
window.fixtureConfig.services=[{id:7,code:'STAY-IPD',name:'إقامة داخلية للتجربة',department_name:'داخلي',department_id:5,current_price_piasters:42000}];
window.fixtureCase.services=[{id:101,service_name_snapshot:'ليلة سرير موثقة',state:'ordered',unit_price_piasters:42000,quantity:1,is_bed_night:1}];
window.fixtureBeds={items:[{id:3,code:'IPD-001',name:'سرير داخلي تجريبي',kind:'inpatient',service_id:7,occupied:1}, {id:4,code:'IPD-002',name:'Second available bed',kind:'inpatient',service_id:7,occupied:0}]};
window.fixtureBedCase={active_stay:{id:8,bed_id:3,bed_name:'سرير داخلي تجريبي',bed_code:'IPD-001',start_date:'2026-10-29',end_date:null},
  stays:[{id:8,bed_id:3,bed_name:'سرير داخلي تجريبي',bed_code:'IPD-001',start_date:'2026-10-29',end_date:null}],
  transfers:[{id:9,transfer_date:"2026-10-29",from_bed_name:"Previous bed",to_bed_name:"Current bed"}],
  unbilled_preview:[{stay_id:8,night_date:'2026-10-29',amount_piasters:35000},
    {stay_id:8,night_date:'2026-10-30',amount_piasters:42000}],
  unbilled_nights:2,missing_rate_nights:0,preview_total_piasters:77000,night_charges:[]};
window.baseApi=window.api;
window.api=async url=>{
 if(url==='/api/beds/catalog')return window.fixtureBeds;
 if(url.startsWith('/api/beds/cases/7'))return window.fixtureBedCase;
 return window.baseApi(url);
};
window.modal=async(title,description,fields)=>{
 window.lastModalTitle=title;
 return {code:'IPD-002',name:'سرير داخلي آخر للتجربة',kind:'inpatient',service_id:'7',
 bed_id:'3',to_bed_id:'4',transfer_date:'2026-10-30',start_date:'2026-10-29',evidence_reference:'SYN-ADMIN-ADMISSION-0001',
 end_date:'2026-10-31',through_date:'2026-10-31'};
};
window.fixtureSettlement.preflight.open_bed_stays=1;
window.fixtureSettlement.preflight.uncharged_bed_nights=2;
window.fixtureSettlement.preflight.blockers=['هناك سرير مشغول لهذه الحالة'];
'''


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            for width in (1440,375,320):
                page=browser.new_page(viewport={'width':width,'height':900})
                errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
                page.set_content('<!doctype html><html lang="ar" dir="rtl"><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body><main id="content"></main></body></html>')
                page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
                page.evaluate(SETUP+EXTRA)
                page.add_script_tag(content=(ROOT/'static/billing.js').read_text())
                page.evaluate('billingState.caseId=7;billingState.pointId=11;renderBilling()')
                page.get_by_text('إشغال السرير وليالي الإقامة').wait_for()
                assert page.get_by_text('سرير داخلي تجريبي').count()>=1
                assert page.locator('[data-billing-cancel]').count()==0
                assert page.get_by_text('770.00 ج.م').count()>=1
                page.locator('#billingBedManage').click()
                page.wait_for_function('window.lastPost?.url==="/api/beds/catalog"')
                assert page.evaluate('window.lastPost.payload.code')=='IPD-002'
                page.evaluate('window.lastPost=null')
                page.locator('#bedCharge').click()
                page.wait_for_function('window.lastPost?.url==="/api/beds/stays/8/charge"')
                assert page.evaluate('window.lastPost.payload.through_date')=='2026-10-31'
                page.evaluate('window.lastPost=null')
                assert page.locator('#bedTransfer').count()==1
                page.locator('#bedTransfer').click()
                page.wait_for_function('window.lastPost?.url==="/api/beds/stays/8/transfer"')
                assert page.evaluate('window.lastPost.payload.to_bed_id')==4
                page.evaluate('window.lastPost=null')
                page.locator('#bedRelease').click()
                page.wait_for_function('window.lastPost?.url==="/api/beds/stays/8/release"')
                page.evaluate("window.state.me={id:2,role:'clerk'};window.lastPost=null;renderBilling()")
                assert page.locator('#bedRelease').count()==0
                assert page.locator('#bedTransfer').count()==0
                assert page.locator('#billingBedManage').count()==0
                assert page.get_by_text('إشغال السرير وليالي الإقامة').count()==1
                assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+2'),width
                assert not errors,errors
                if width in (1440,375):page.screenshot(path=str(ROOT/f'qa_screenshots/G2S_BED_TRANSFERS_{width}.png'),full_page=True)
                page.close()
            print('PASS G2S browser 1440/375/320; priced-night overview, owner controls, clerk scopes, RTL and no errors')
        finally:browser.close()

if __name__=='__main__':run()
