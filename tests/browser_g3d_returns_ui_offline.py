"""G3D real Chromium: return lookup, lot-level form, independent review, stale access denial."""
from browser_helpers import chromium_options
from pathlib import Path
from playwright.sync_api import sync_playwright
from test_v82_g2t_inventory_ui import BOOT
ROOT=Path(__file__).resolve().parents[1]
FIXTURE=r'''
let returnLookupRevoked=false;
let originalApi=api;
window.api=async function(path){
 if(path==='/api/inventory/issues/2/returnable'){
   if(returnLookupRevoked)throw Error('Return access revoked');
   return {issue_id:2,case_id:42,used_on:'2026-10-31',allocations:[
      {issue_allocation_id:7,quantity_issued:3,returnable_quantity:2,
       item_code:'SYN-DRESSING',item_name:'Synthetic wound dressing',unit_cost_piasters:1200},
      {issue_allocation_id:8,quantity_issued:1,returnable_quantity:0,
       item_code:'SYN-DRESSING',item_name:'Synthetic wound dressing',unit_cost_piasters:2000}
   ]};
 }
 return originalApi(path);
};
inventoryFixture.returns=[{id:18,issue_id:2,returned_on:'2026-10-31',
  evidence_ref:'SYNTHETIC-RETURN-00001',status:'pending',created_by:2,cost_piasters:0}];
recFixture.approved_returns=0;
'''


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(**chromium_options(),headless=True,
             args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            for width in (1440,375,320):
                page=browser.new_page(viewport={'width':width,'height':900})
                page.set_default_timeout(5500)
                errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.set_content('<!doctype html><html lang="ar" dir="rtl"><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><main id="content"></main></body></html>')
                page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
                page.add_script_tag(content=BOOT)
                page.add_script_tag(content=FIXTURE)
                page.add_script_tag(content=(ROOT/'static/inventory_ui.js').read_text())
                page.evaluate('renderInventory()')
                page.locator('[data-inv-tab="returns"]').click()
                assert page.get_by_text('مرتجعات مستلزمات').count()>=1
                assert page.locator('[data-inv-decision="returns:18:approve"]').count()==1
                lookup=page.locator('#invReturnLookupForm')
                assert lookup.count()==1,('return lookup missing',width)
                lookup.locator('[name="issue_id"]').fill('2')
                lookup.locator('button[type="submit"]').click()
                form=page.locator('#invReturnForm')
                form.wait_for()
                assert page.get_by_text('Synthetic wound dressing').count()>=1
                assert form.locator('select[name="issue_allocation_id"] option[value="8"]').count()==0
                form.locator('select[name="issue_allocation_id"]').select_option('7')
                form.locator('[name="quantity"]').fill('2')
                form.locator('[name="evidence_ref"]').fill('SYNTHETIC-UNUSED-STERILE-RETURN')
                form.locator('button[type="submit"]').click()
                page.wait_for_function('lastRequest?.path==="/api/inventory/returns"')
                values=page.evaluate('lastRequest.data')
                assert values['issue_id']==2 and values['lines']==[{'issue_allocation_id':7,'quantity':2}],values
                assert values['evidence_ref']=='SYNTHETIC-UNUSED-STERILE-RETURN',values
                page.evaluate("lastRequest=null;inventoryFixture.grants={can_prepare:0,can_approve:1};state.me={id:3,role:'reviewer'};renderInventory()")
                page.locator('[data-inv-decision="returns:18:approve"]').click()
                page.wait_for_function('lastRequest?.path==="/api/inventory/returns/18/decision"')
                assert page.evaluate('lastRequest.data.decision')=='approve'
                assert page.locator('#invReturnLookupForm').count()==0
                page.evaluate("state.me={id:1,role:'owner'};inventoryFixture.grants={can_prepare:1,can_approve:1};renderInventory()")
                lookup=page.locator('#invReturnLookupForm')
                lookup.locator('[name="issue_id"]').fill('2')
                lookup.locator('button[type="submit"]').click()
                form.wait_for()
                page.evaluate('returnLookupRevoked=true')
                lookup.locator('button[type="submit"]').click()
                page.get_by_text('Return access revoked').wait_for()
                assert page.locator('#invReturnForm').count()==0,'stale protected return source remained visible'
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+2'),width
                assert not errors,errors
                page.close()
            print('PASS G3D Chromium 1440/375/320 original-lot return workflow, reviewer approval and stale denial clearing')
        finally:
            browser.close()


if __name__=='__main__':run()
