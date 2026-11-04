"""Optional real-Chromium isolated UI smoke; does not use live hospital data."""
from browser_helpers import chromium_options
from pathlib import Path
import json
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
mock={
 'items':[{'id':7,'point_id':2,'business_date':'2026-10-24','shift_code':'treasury',
  'incident_reason':'absence','cash_location':'envelope','custodian_name':'المسؤول المختص',
  'point_name':'الخزنة الرئيسية','status':'resolved','doc_count':2,'linked_count':2,
  'mixed_variance_piasters':5000}],
 'open':[{'incident_id':7,'business_date':'2026-10-24','source_register_ref':'ENV-777',
  'point_name':'الخزنة الرئيسية','original_overage_piasters':5000,'refunded_piasters':2000,
  'outstanding_piasters':3000}],
 'incident':{'id':7,'point_id':2,'business_date':'2026-10-24','shift_code':'treasury',
   'opened_by':1,'status':'resolved','custodian_name':'المسؤول المختص',
   'cash_location':'envelope','counted_cash_piasters':135000,'note':'تمت المطابقة المحاسبية الموثقة'},
 'evidence':[{'id':51,'filename':'ownership-proof.png'},
             {'id':52,'filename':'signed-claimant-receipt.png'}],
 'refund':[{'id':42,'claim_ref':'CLAIM-400','claimant_name':'صاحب حق موثق',
   'evidence_id':51,'amount_piasters':3000,'status':'pending','proposed_by':1}],
}
setup='''
const mock=JSON.parse(document.getElementById('mock').textContent);
window.state={me:{id:2,role:'reviewer'},shiftMonth:'2026-10'};
window.$=s=>document.querySelector(s); window.$$=s=>[...document.querySelectorAll(s)];
window.esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
window.fmt=x=>(Number(x||0)/100).toLocaleString('en-US',{maximumFractionDigits:2});
window.integer=x=>Number(x||0); window.ico=_=>'';
window.opt=(id,label)=>`<option value="${window.esc(id)}">${window.esc(label)}</option>`;
window.head=(a,b,c,d='')=>`<header class="page-header"><p>${window.esc(a)}</p><h1>${window.esc(b)}</h1><p>${window.esc(c)}</p>${d}</header>`;
window.table=(cols,rows)=>`<div class="table-wrap"><table class="data-table"><thead><tr>${cols.map(x=>'<th>'+x+'</th>').join('')}</tr></thead><tbody>${rows}</tbody></table></div>`;
window.toast=(s,b)=>{window.lastToast=s};
window.modal=async()=>({decision:'approve',counted_amount:'30',receipt_evidence_id:'52',recipient_receipt_verified:'true',
  reason:'تمت مراجعة إيصال صاحب الحق وتوقيعه واعتماد استرداد الفارق النقدي'});
window.post=async(url,data)=>{window.lastPost={url,data};return {status:'approved',cash_paid_piasters:3000}};
window.api=async url=>{
 if(url==='/api/late-entries')return {items:mock.items};
 if(url==='/api/late-entries/shortage-open')return {items:[]};
 if(url==='/api/late-entries/overage-open')return {items:mock.open};
 if(url==='/api/billing/config')return {points:[{id:2,name:'الخزنة الرئيسية',fund_id:1}]};
 if(url.startsWith('/api/shifts/coverage'))return {items:[{point_id:2,shift:'treasury',shift_name:'الخزنة العامة'}]};
 if(url==='/api/late-entries/7')return {
   incident:mock.incident,point_kind:'internal',documents:[],events:[],
   evidence:mock.evidence,recovered_cases:[],cash_allocations:[],
   mixed_clearance:{id:3,journal_id:5,gross_receipts_piasters:150000,expense_piasters:20000,
      actual_cash_piasters:135000,variance_piasters:5000},
   mixed_shortage_recovery_requests:[],overage_total_piasters:5000,
   overage_refunded_piasters:2000,overage_outstanding_piasters:3000,
   mixed_overage_refund_requests:mock.refund
 };return {items:[]};
};
'''
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,**chromium_options(),args=['--no-sandbox','--disable-dev-shm-usage'])
 for width,height in [(1365,900),(375,812)]:
  page=browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1)
  page.set_content('<!DOCTYPE html><html dir="rtl" lang="ar"><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><main id="content"></main><script id="mock" type="application/json">'+json.dumps(mock,ensure_ascii=False)+'</script></body></html>')
  page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
  page.evaluate(setup+"\n0;")
  page.add_script_tag(content=(ROOT/'static/late_entry_ui.js').read_text())
  page.evaluate('renderLateEntries()')
  page.wait_for_timeout(70)
  assert page.get_by_text('زيادات الأظرف تحت التحقيق').count()>0
  page.evaluate('openLateEntry(7)')
  page.wait_for_timeout(70)
  assert page.get_by_text('المتبقي 30 ج').count()>0
  assert page.locator('[data-late-overage-decision]').count()==1
  assert page.locator('#lateEvidenceFile').count()==1
  page.locator('[data-late-overage-decision]').click()
  page.wait_for_timeout(75)
  submitted=page.evaluate('window.lastPost')
  assert submitted['url']=='/api/late-entries/7/overage-refunds/42/decision'
  assert submitted['data']['receipt_evidence_id']==52
  assert submitted['data']['recipient_receipt_verified'] is True
  assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth+2'),width
  out=ROOT.parent/f'QA_G2F_OVERAGE_{width}.png'
  page.screenshot(path=str(out),full_page=True)
  print('PASS G2F UI',width,'screenshot',out.name)
  page.close()
 browser.close()
