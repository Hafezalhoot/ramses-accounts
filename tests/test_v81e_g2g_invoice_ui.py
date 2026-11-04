"""Isolated Chromium smoke for G2G financial correction UI, no live hospital data."""
from browser_helpers import chromium_options
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
window.modal=async(title,description,fields)=>{window.modalInfo={title,description,fields};return {amount:'100',evidence_reference:'G2G-LAB-00537',decision_note:'راجع المراجع كشف الخدمة وتأكد من انخفاض الفاتورة بمئة جنيه'}};
window.api=async url=>{
 if(url==='/api/corrections')return {tickets:[
  {id:7,source_type:'invoice',source_id:12,source_ref:'INV-12',issue_type:'wrong_amount',status:'triaged',opened_by:1,opened_by_name:'clerk',reason:'المبلغ مختلف عن المستند الطبي',resolved_credit_id:null},
  {id:8,source_type:'invoice',source_id:11,source_ref:'INV-11',issue_type:'wrong_amount',status:'triaged',opened_by:1,opened_by_name:'clerk',resolved_credit_id:9,resolved_amount_piasters:10000}
 ]};
 if(url==='/api/corrections/7/invoice-credit-preview')return {eligible:true,invoice_no:'INV-12',before_due_piasters:50000,max_reduction_piasters:50000};
 return {ticket:{source_ref:'INV-12',status:'triaged',reason:'مبلغ زائد'},events:[]};
};
window.post=async(url,data)=>{window.lastPost={url,data};return {new_due_piasters:40000}};
'''
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,**chromium_options(),args=['--no-sandbox','--disable-dev-shm-usage'])
 for width,height in ((1365,900),(375,812)):
  page=browser.new_page(viewport={'width':width,'height':height})
  page.set_content('<!doctype html><html lang="ar" dir="rtl"><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><main id="content"></main></body></html>')
  page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
  page.evaluate(setup)
  page.add_script_tag(content=(ROOT/'static/financial_corrections_ui.js').read_text())
  page.evaluate('renderFinancialCorrections()')
  page.wait_for_timeout(90)
  assert page.locator('[data-correction-credit]').count()==1
  assert page.get_by_text('تخفيض معتمد').count()==1
  page.locator('[data-correction-credit]').click()
  page.wait_for_timeout(90)
  post=page.evaluate('window.lastPost')
  assert post and post['url']=='/api/corrections/7/execute-invoice-credit',post
  assert post['data']['amount']=='100' and post['data']['expected_due_piasters']==50000
  assert post['data']['evidence_reference']=='G2G-LAB-00537'
  assert len(post['data']['request_key'])>=16
  assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth+2'),width
  out=ROOT.parent/f'QA_G2G_CORRECTION_{width}.png'
  page.screenshot(path=str(out),full_page=True)
  print('PASS G2G UI',width,'saved',out)
  page.close()
 browser.close()
