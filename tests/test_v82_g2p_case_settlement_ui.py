"""Chromium-rendered G2P clearance component and actions; synthetic data, no server."""
from browser_helpers import chromium_options
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
SETUP=r'''
window.state={me:{id:2,role:'clerk'},lookups:{departments:[],funds:[]}};
window.$=s=>document.querySelector(s);window.$$=s=>[...document.querySelectorAll(s)];
window.esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
window.ico=()=>'';window.integer=n=>Number(n||0);window.fmt=n=>(Number(n||0)/100).toFixed(2);
window.head=(a,b,c,d)=>`<header><h1>${window.esc(b)}</h1><p>${window.esc(c)}</p>${d||''}</header>`;
window.empty=s=>`<p>${window.esc(s)}</p>`;window.table=(h,rows)=>`<table>${rows}</table>`;
window.toast=(a,b)=>{window.lastToast={a,b}};window.navigate=r=>{window.lastNavigate=r};
window.modal=async(title,description,fields)=>{window.lastModal={title,description};return {
  evidence_reference:'IPD-CLEARANCE-SYN-01',note:'Test financial clearance note with evidence',
  decision:'approve'};};
window.fixtureConfig={points:[{id:11,name:'خزينة الحسابات الداخلية',kind:'internal',fund_id:4,active:true,
  own_open_shift:true,active_shift:{id:9,shift:'treasury',business_date:'2026-10-31',status:'open'}}],
  services:[],payment_channels:[]};
window.fixtureCase={case:{id:7,default_point_id:11,kind:'inpatient',status:'open',
  case_no:'CASE-TEST-00007',patient_code:'PT-ABCDEF123456',patient_name:'Synthetic Patient',business_date:'2026-10-31'},
  services:[],drafts:[],invoices:[],unbilled_piasters:0};
window.fixtureFinance={invoices:[],collections:[],total_invoiced_piasters:0,outstanding_piasters:0,
  advance_available_piasters:0};
window.fixtureSettlement={preflight:{ready:false,case_kind:'inpatient',status:'open',blockers:['هناك مديونية على المريض لم تسدد'],
  invoice_count:1,outstanding_piasters:48000,advance_available_piasters:0},requests:[]};
window.api=async url=>{
 if(url==='/api/billing/config')return window.fixtureConfig;
 if(url==='/api/billing/cases?point_id=11')return {items:[]};
 if(url==='/api/billing/cases/7')return window.fixtureCase;
 if(url==='/api/billing/cases/7/finance')return window.fixtureFinance;
 if(url==='/api/billing/cases/7/adjustments')return {credits:[],refunds:[],credit_refundable_piasters:0,
  advance_refundable_piasters:0};
 if(url==='/api/case-settlement/cases/7')return window.fixtureSettlement;
 return {items:[]};
};
window.post=async(url,payload)=>{window.lastPost={url,payload};return {id:55,status:'pending'}};
'''


def run():
    (ROOT/'qa_screenshots').mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True,**chromium_options(),
                                          args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            for width in (1440,375,320):
                page=browser.new_page(viewport={'width':width,'height':900})
                errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.set_content('<!doctype html><html lang="ar" dir="rtl"><head>'
                  '<meta name="viewport" content="width=device-width, initial-scale=1"></head>'
                  '<body><main id="content"></main></body></html>')
                page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
                page.evaluate(SETUP)
                page.add_script_tag(content=(ROOT/'static/billing.js').read_text())
                page.evaluate('billingState.caseId=7;billingState.pointId=11;renderBilling()')
                page.get_by_text('التصفية المالية للحالة').wait_for()
                assert page.get_by_text('هناك مديونية على المريض لم تسدد').count()==1
                assert page.locator('#billingClearanceRequest').count()==0
                page.evaluate('''window.fixtureSettlement.preflight.ready=true;
                   window.fixtureSettlement.preflight.blockers=[];
                   window.fixtureSettlement.preflight.outstanding_piasters=0;renderBilling()''')
                page.locator('#billingClearanceRequest').wait_for()
                page.locator('#billingClearanceRequest').click()
                page.wait_for_function('window.lastPost?.url?.includes("/case-settlement/cases/7/request")')
                submission=page.evaluate('window.lastPost')
                assert submission['payload']['evidence_reference']=='IPD-CLEARANCE-SYN-01'
                assert len(submission['payload']['request_id'])>=16
                assert submission['payload']['mode']=='settled'
                page.evaluate('''window.state.me={id:3,role:'reviewer'};
                   window.fixtureSettlement.requests=[{id:55,status:'pending',requested_by:2}];
                   window.lastPost=null;renderBilling()''')
                page.locator('[data-clearance-decision=approve]').wait_for()
                page.locator('[data-clearance-decision=approve]').click()
                page.wait_for_function('window.lastPost?.url?.includes("/case-settlement/requests/55/decision")')
                approved=page.evaluate('window.lastPost')
                assert approved['payload']['decision']=='approve',approved
                page.evaluate('''window.fixtureCase.case.status='closed';
                  window.fixtureSettlement.preflight.status='closed';
                  window.fixtureSettlement.requests=[{id:55,status:'approved',closed_on:'2026-10-31',
                    evidence_reference:'IPD-CLEARANCE-SYN-01'}];renderBilling()''')
                assert page.get_by_text('تم إغلاق الملف المالي بعد اعتماد مستقل').count()==1
                assert page.locator('#billingAddLine').count()==0
                assert page.locator('#billingClearanceRequest').count()==0
                # No-charge owner cancellation has a separate action and no fake invoice.
                page.evaluate("""window.state.me={id:1,role:'owner'};
                  window.fixtureCase.case.kind='nicu';window.fixtureCase.case.status='open';
                  window.fixtureSettlement.preflight.status='open';
                  window.fixtureSettlement.preflight.ready=false;
                  window.fixtureSettlement.preflight.no_charge_ready=true;
                  window.fixtureSettlement.preflight.invoice_count=0;
                  window.fixtureSettlement.preflight.blockers=['لا توجد فاتورة صادرة'];
                  window.fixtureSettlement.requests=[];window.lastPost=null;renderBilling()""")
                page.locator('#billingClearanceNoCharge').wait_for()
                assert page.locator('#billingClearanceRequest').count()==0
                page.locator('#billingClearanceNoCharge').click()
                page.wait_for_function('window.lastPost?.payload?.mode==="no_charge"')
                assert 'no_charge'==page.evaluate('window.lastPost.payload.mode')
                # A maker must never see an approval button for their own request.
                page.evaluate("""window.fixtureSettlement.requests=[{id:72,status:'pending',clearance_mode:'no_charge',requested_by:1}];
                  window.lastPost=null;renderBilling()""")
                assert page.locator('[data-clearance-decision=approve]').count()==0
                page.evaluate("""window.state.me={id:3,role:'reviewer'};renderBilling()""")
                assert page.locator('[data-clearance-decision=approve]').count()==1
                assert page.get_by_text('اعتماد إلغاء الحجز').count()==1
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
                assert not errors,errors
                if width==375:
                    page.screenshot(path=str(ROOT/'qa_screenshots/G2P_FINANCIAL_CLEARANCE_375.png'),full_page=True)
                if width==1440:
                    page.screenshot(path=str(ROOT/'qa_screenshots/G2P_FINANCIAL_CLEARANCE_1440.png'),full_page=True)
                page.close()
            print('PASS: G2P readiness, request, review, closed UI at 1440/375/320; no JS errors or horizontal overflow')
        finally:
            browser.close()

if __name__=='__main__':run()
