"""Actual local Chromium: G3N Cairo RTL supplier statement maker/checker on three viewports."""
from browser_helpers import chromium_options
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from test_v82_g2t_inventory_ui import BOOT

def run():
    with sync_playwright() as pw:
        browser=pw.chromium.launch(**chromium_options(),headless=True,
            args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            for width in (320,375,1440):
                page=browser.new_page(viewport={'width':width,'height':900})
                page.set_default_timeout(5500)
                errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.set_content('<!doctype html><html lang="ar" dir="rtl"><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><main id="content"></main></body></html>')
                page.add_style_tag(content=(ROOT/'static/styles.css').read_text(encoding='utf8'))
                page.add_script_tag(content=BOOT)
                page.evaluate('''()=>{
                  state.me={id:2,role:'clerk'};
                  inventoryFixture.grants={can_prepare:1,can_approve:0};
                  inventoryFixture.supplier_opening_statements=[{
                    id:8, vendor_id:1, vendor_name:'مورد تجريبي',vendor_code:'V-001',vendor_active:1,
                    as_of:'2026-10-31',statement_piasters:4250,ledger_piasters:4250,
                    current_ledger_piasters:4250,source_changed:false,review_blocked:false,
                    evidence_ref:'SIGNED-SUPPLIER-PDF-0042',reason:'External statement compared against exact GL value',
                    created_by:2,status:'pending'}];
                }''')
                page.add_script_tag(content=(ROOT/'static/inventory_ui.js').read_text(encoding='utf8'))
                page.evaluate('renderInventory()')
                page.locator('[data-inv-tab="suppliers"]').click()
                form=page.locator('#invOpeningForm')
                form.wait_for(timeout=12000)
                assert 'مطابقة كشوف أرصدة الموردين' in page.locator('#invOpeningPanel').inner_text()
                form.locator('[name="vendor_id"]').select_option('1')
                form.locator('[name="statement_balance"]').fill('42.50')
                form.locator('[name="evidence_ref"]').fill('SIGNED-OPENING-SOURCE-042')
                form.locator('[name="reason"]').fill('Verified supplier statement against last month full control')
                form.locator('button[type="submit"]').click()
                page.wait_for_function("lastRequest?.path==='/api/inventory/supplier-opening-statements'")
                assert page.evaluate('lastRequest.data.statement_balance')=='42.50'
                assert page.locator('[data-inv-opening-decision]').count()==0
                page.evaluate("state.me={id:3,role:'reviewer'};inventoryFixture.grants={can_prepare:0,can_approve:1};lastRequest=null;renderInventory()")
                panel=page.locator('#invOpeningPanel')
                panel.get_by_text('SIGNED-SUPPLIER-PDF-0042').wait_for(timeout=10000)
                assert panel.locator('[data-inv-opening-decision="8:approve"]').count()==1
                assert panel.locator('#invOpeningForm').count()==0
                panel.locator('[data-inv-opening-decision="8:approve"]').click()
                page.wait_for_function("lastRequest?.path==='/api/inventory/supplier-opening-statements/8/decision'")
                assert page.evaluate('lastRequest.data.decision')=='approve'
                assert page.evaluate("getComputedStyle(document.body).fontFamily.includes('Cairo')"),width
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
                assert not errors,(width,errors)
                # Stale/mismatched documents permit REJECTION only.
                page.evaluate("inventoryFixture.supplier_opening_statements[0].review_blocked=true;lastRequest=null;renderInventory()")
                assert page.locator('[data-inv-opening-decision="8:approve"]').count()==0
                assert page.locator('[data-inv-opening-decision="8:reject"]').count()==1
                page.close()
            print('PASS G3N Chromium 320/375/1440 Cairo RTL statement evidence, reviewer isolation, blocked approve, no overflow')
        finally:browser.close()

if __name__=='__main__':run()
