"""Offline Chromium G3G warehouse-only partial writeoff and independent review at 320/375/1440."""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from test_v82_g2t_inventory_ui import BOOT


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,
                                  args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            for width in (320,375,1440):
                page=browser.new_page(viewport={'width':width,'height':860})
                errors=[];page.on('pageerror',lambda exc:errors.append(str(exc)))
                page.set_content('<!doctype html><html dir="rtl" lang="ar"><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><main id="content"></main></body></html>')
                page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
                page.add_script_tag(content=BOOT)
                page.evaluate('''()=>{
                  inventoryFixture.writeoff_candidates=[{return_line_id:41,returned_on:'2026-10-31',
                    inspected_on:'2026-11-01',item_code:'SYN-G3G-ITEM',item_name:'Synthetic rejected supply',
                    batch_ref:'SYN-BATCH-1',quantity:3,remaining_quantity:2,unit_cost_piasters:1725}];
                  inventoryFixture.writeoffs=[{id:62,return_line_id:41,quantity:1,
                    disposed_on:'2026-11-01',reason:'damaged',evidence_ref:'SYN-DAMAGE-62',
                    status:'pending',created_by:8,cost_piasters:0}];
                  inventoryFixture.items[0].quantity_on_hand=3;
                  inventoryFixture.items[0].quarantined_quantity=3;
                  inventoryFixture.items[0].available_quantity=0;
                  inventoryFixture.items[0].value_piasters=5175;
                }''')
                page.add_script_tag(content=(ROOT/'static/inventory_ui.js').read_text())
                page.evaluate('renderInventory()')
                page.locator('#invWriteoffForm').wait_for(timeout=5000)
                assert 'Synthetic rejected supply' in page.locator('#content').inner_text()
                assert page.locator('[data-inv-decision="writeoffs:62:approve"]').count()==1
                assert 'patient_name' not in page.locator('#content').inner_text()
                page.locator('#invWriteoffForm select[name="return_line_id"]').select_option('41')
                page.locator('#invWriteoffForm input[name="quantity"]').fill('2')
                page.locator('#invWriteoffForm input[name="evidence_ref"]').fill('SYNTHETIC-PHYSICAL-DISPOSAL-REF')
                page.locator('#invWriteoffForm select[name="reason"]').select_option('damaged')
                page.locator('#invWriteoffForm input[name="physical_disposal_confirmed"]').check()
                page.locator('#invWriteoffForm button[type="submit"]').click()
                page.wait_for_function('lastRequest?.path==="/api/inventory/writeoffs"')
                result=page.evaluate('lastRequest.data')
                assert result['quantity']==2 and result['return_line_id']==41 and result['physical_disposal_confirmed'] is True,result
                assert result['disposed_on']==page.evaluate("new Date().toLocaleDateString('sv-SE',{timeZone:'Africa/Cairo'})"),result
                page.evaluate('lastRequest=null;state.me={id:9,role:"reviewer"};inventoryFixture.grants={can_prepare:0,can_approve:1};renderInventory()')
                page.locator('[data-inv-decision="writeoffs:62:approve"]').click()
                page.wait_for_function('lastRequest?.path==="/api/inventory/writeoffs/62/decision"')
                assert page.evaluate('lastRequest.data.decision')=='approve'
                assert page.locator('#invWriteoffForm').count()==0
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
                assert not errors,(width,errors)
                page.close()
            print('PASS G3G Chromium 320/375/1440: rejected stock writeoff form, independent reviewer, Cairo date, no overflow')
        finally:browser.close()

if __name__=='__main__':run()
