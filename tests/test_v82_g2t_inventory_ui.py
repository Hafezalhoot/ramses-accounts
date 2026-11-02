"""Offline Chromium: G2T stock UI owner/reviewer and small screens; no real hospital data."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
BOOT=r'''
const state={me:{id:1,role:'owner'},month:'2026-10',lookups:{departments:[{id:5,name:'داخلي - تجريبي'}]}};
const $=(s,root=document)=>root.querySelector(s);
const $$=(s,root=document)=>[...root.querySelectorAll(s)];
const esc=(v)=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
const fmt=(v)=>(Number(v||0)/100).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
const integer=(v)=>Number(v||0).toLocaleString('en-US');
const ico=(n)=>'';
const empty=(s)=>`<div class="empty">${esc(s)}</div>`;
const table=(cols,rows)=>`<div class="table-wrap"><table class="data-table"><thead><tr>${cols.map(x=>`<th>${esc(x)}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div>`;
const head=(tag,title,desc,actions='')=>`<div class="page-heading"><div><span>${esc(tag)}</span><h1>${esc(title)}</h1><p>${esc(desc)}</p></div>${actions}</div>`;
let lastRequest=null, lastToast=null;
const toast=(msg,bad=false)=>{lastToast={msg,bad};};
const errorView=(msg)=>{$('#content').innerHTML=`<p role="alert">${esc(msg)}</p>`;};
let inventoryFixture={
  vendors:[{id:1,code:'V-001',name:'مورد تجريبي'}],
  items:[{id:1,code:'GLOVES',name:'قفازات فحص تجريبية',unit:'piece',quantity_on_hand:4,value_piasters:8000}],
  receipts:[{id:1,invoice_ref:'SYNTHETIC-INVOICE-0001',received_on:'2026-10-31',status:'pending',created_by:2,total_piasters:13600,vendor_name:'مورد تجريبي'}],
  issues:[{id:2,evidence_ref:'SYN-ISSUE-0001',used_on:'2026-10-31',status:'approved',created_by:2,cost_piasters:5600}],
  grants:{can_prepare:0,can_approve:0},role:'owner'
};
const recFixture={matched:true,period:'2026-10',value_piasters:8000,inventory_gl_piasters:8000,errors:[]};
async function api(path){
 if(state.me.role==='viewer')throw Error('لا توجد صلاحية');
 if(path.startsWith('/api/inventory/overview'))return inventoryFixture;
 if(path.startsWith('/api/inventory/reconciliation'))return recFixture;
 if(path==='/api/users')return [{id:2,username:'synthetic_clerk',role:'clerk',active:1}];
 throw Error('Missing fixture '+path);
}
async function post(path,data){lastRequest={path,data};return {ok:true};}
async function modal(title,message,fields){return {code:'TEST001',name:'مورد تجريبي آخر',unit:'piece',note:'Independent reviewed stock evidence'};}
const roleLabels={clerk:'مدخل بيانات'};
'''


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            for width in (1440,375,320):
                page=browser.new_page(viewport={'width':width,'height':900},device_scale_factor=1)
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.set_content('<!doctype html><html lang="ar" dir="rtl"><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><main id="content"></main></body></html>')
                page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
                page.add_script_tag(content=BOOT)
                page.add_script_tag(content=(ROOT/'static/inventory_ui.js').read_text())
                page.evaluate('renderInventory()')
                page.locator('[data-inv-tab="stock"]').click()
                assert page.get_by_text('المخزن المركزي للمستلزمات').count()==1
                assert page.get_by_text('قفازات فحص تجريبية').count()>=1
                assert page.get_by_text('80.00').count()>=1
                assert page.locator('#invReceiptForm').count()==1
                assert page.locator('[data-inv-decision]').count()==2
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2'),width
                # Owner can add a vendor and submit an inventory receipt.
                page.locator('#invVendor').click()
                page.wait_for_function('lastRequest !== null')
                assert page.evaluate('lastRequest.path')=='/api/inventory/vendors'
                page.evaluate('lastRequest = null')
                page.locator('#invReceiptForm [name="vendor_id"]').select_option('1')
                page.locator('#invReceiptForm [name="invoice_ref"]').fill('SYNTHETIC-INVOICE-0002')
                page.locator('#invReceiptForm [name="evidence_ref"]').fill('SYNTHETIC-WAREHOUSE-GRN-2')
                page.locator('#invReceiptForm [name="item_id"]').select_option('1')
                page.locator('#invReceiptForm [name="quantity"]').fill('2')
                page.locator('#invReceiptForm [name="unit_cost"]').fill('10.50')
                page.locator('#invReceiptForm button[type="submit"]').click()
                page.wait_for_function('lastRequest?.path==="/api/inventory/receipts"')
                assert page.evaluate('lastRequest.data.lines[0].quantity')==2
                assert page.evaluate('lastRequest.data.lines[0].unit_cost')=='10.50'
                # A reviewer without preparation grant sees review only.
                page.evaluate("state.me={id:3,role:'reviewer'};inventoryFixture.grants={can_prepare:0,can_approve:1};renderInventory()")
                page.locator('[data-inv-decision]').first.wait_for()
                assert page.locator('#invReceiptForm').count()==0
                assert page.locator('#invVendor').count()==0
                assert not errors,errors
                if width in (1440,375):
                    (ROOT/'qa_screenshots').mkdir(exist_ok=True)
                    page.screenshot(path=str(ROOT/f'qa_screenshots/G2T_INVENTORY_{width}.png'),full_page=True)
                page.close()
            print('PASS G2T Chromium 1440/375/320: Arabic owner/reviewer, forms, approval gates, no horizontal overflow or JS errors')
        finally:browser.close()

if __name__=='__main__':run()
