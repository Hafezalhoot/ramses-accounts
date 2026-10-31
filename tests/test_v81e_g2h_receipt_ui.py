"""Playwright isolated browser test: G2H full-receipt correction desktop + mobile."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
setup=r'''
window.state={me:{id:2,role:'reviewer'}};
window.$=s=>document.querySelector(s);window.$$=s=>[...document.querySelectorAll(s)];
window.esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
window.integer=x=>Number(x||0);window.ico=x=>'';
window.head=(a,b,c,d)=>`<header><h1>${window.esc(b)}</h1><p>${window.esc(c)}</p>${d||''}</header>`;
window.toast=(a,b)=>{window.lastToast={a,b}};
window.navigate=route=>{window.lastNavigate=route};
window.modals=[];
window.modal=async(title,description,fields)=>{
 window.modals.push({title,description,fields});
 if(window.modals.length===1)return {target_invoice_id:'59',target_patient_code:'PT-AABBCCDDEEFF'};
 return {confirm:'yes',evidence_reference:'HOSP-G2H-CASE-0059',decision_note:'تأكد المراجع المستقل من كود المريض ومن مستندات الإيصال الأصلي'};
};
window.api=async url=>{
 if(url==='/api/corrections')return {tickets:[
  {id:17,source_type:'collection',source_id:21,source_ref:'REC-21',issue_type:'wrong_patient',status:'triaged',opened_by:1,opened_by_name:'clerk',reason:'القبض على المريض الغلط'},
  {id:18,source_type:'collection',source_id:22,source_ref:'REC-22',issue_type:'wrong_patient',status:'triaged',opened_by:1,opened_by_name:'clerk',resolved_reallocation_id:9},
 ]};
 return {};
};
window.post=async(url,data)=>{
 window.posts.push({url,data});
 if(url==='/api/corrections/17/collection-reassign-preview')return {
  eligible:true,source_receipt_no:'REC-21',target_invoice_no:'INV-59',target_case_no:'CASE-2026-000059',
  amount_piasters:10000,before_source_due_piasters:40000,before_target_due_piasters:50000};
 return {after_source_due_piasters:50000,after_target_due_piasters:40000};
};
window.posts=[];
'''
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',
       args=['--no-sandbox','--disable-dev-shm-usage'])
    for width,height in ((1365,900),(375,812)):
        page=browser.new_page(viewport={'width':width,'height':height})
        page.set_content('<html lang="ar" dir="rtl"><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><main id="content"></main></body></html>')
        page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
        page.evaluate(setup)
        page.add_script_tag(content=(ROOT/'static/financial_corrections_ui.js').read_text())
        page.evaluate('renderFinancialCorrections()')
        page.wait_for_timeout(85)
        assert page.locator('[data-correction-reassign]').count()==1
        assert page.get_by_text('إعادة تخصيص معتمدة').count()==1
        page.locator('[data-correction-reassign]').click()
        page.wait_for_timeout(100)
        posted=page.evaluate('window.posts')
        assert len(posted)==2,posted
        assert posted[0]['url']=='/api/corrections/17/collection-reassign-preview'
        assert posted[1]['url']=='/api/corrections/17/execute-collection-reassign'
        assert posted[1]['data']['expected_source_due_piasters']==40000
        assert posted[1]['data']['expected_target_due_piasters']==50000
        assert posted[1]['data']['evidence_reference']=='HOSP-G2H-CASE-0059'
        assert len(posted[1]['data']['request_key'])>=16
        assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+2'),width
        page.screenshot(path=str(ROOT.parent/f'QA_G2H_CORRECTION_{width}.png'),full_page=True)
        print('PASS G2H corrected receipt UI',width)
        page.close()
    browser.close()
