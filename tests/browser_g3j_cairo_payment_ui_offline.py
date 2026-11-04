"""Real Chromium offline: Cairo CSS stack + G3J non-paying supplier request and independent review."""
from browser_helpers import chromium_options
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from test_v82_g2t_inventory_ui import BOOT


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(**chromium_options(),headless=True,
             args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            for width in (320,375,1440):
                page=browser.new_page(viewport={'width':width,'height':900})
                page.set_default_timeout(5500)
                errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
                page.set_content('<!doctype html><html lang="ar" dir="rtl"><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><main id="content"></main></body></html>')
                page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
                page.add_script_tag(content=BOOT)
                page.evaluate('''()=>{
                  state.me={id:11,role:'clerk'};
                  inventoryFixture.grants={can_prepare:1,can_approve:0};
                  inventoryFixture.supplier_payment_eligible_lines=[{id:201,
                    due_on:'2026-12-20',line_no:1,amount_piasters:7000,reserved_piasters:1000,
                    available_to_request_piasters:6000,invoice_ref:'SYN-G3J-INV-002',vendor_name:'مورد تجريبي'}];
                  inventoryFixture.supplier_payment_requests=[{id:307,status:'pending',created_by:11,
                    schedule_creator:10,invoice_creator:10,receipt_creator:10,installment_piasters:7000,amount_piasters:6000,
                    due_line_id:201,requested_on:'2026-11-01',due_on:'2026-12-20',
                    invoice_ref:'SYN-G3J-INV-002',vendor_name:'مورد تجريبي',vendor_active:1,
                    evidence_ref:'SYNTH-SUPPLIER-REQUEST-307'}];
                }''')
                page.add_script_tag(content=(ROOT/'static/inventory_ui.js').read_text())
                page.evaluate('renderInventory()')
                page.locator('[data-inv-tab="suppliers"]').click()
                page.locator('#invPaymentRequestForm').wait_for(timeout=7000)
                font=page.evaluate('getComputedStyle(document.body).fontFamily')
                assert 'Cairo' in font,(width,font)
                body_weight=page.evaluate('getComputedStyle(document.body).fontWeight')
                heading_weight=page.evaluate('getComputedStyle(document.querySelector("#content h2")).fontWeight')
                assert int(body_weight)==400 and int(heading_weight)>=700,(width,body_weight,heading_weight)
                label=page.locator('#invPaymentRequestForm').inner_text()
                assert 'طلب' in label and 'ليس' in page.locator('#content').inner_text()
                page.locator('#invPaymentRequestForm select[name="due_line_id"]').select_option('201')
                page.locator('#invPaymentRequestForm [name="amount"]').fill('55.00')
                page.locator('#invPaymentRequestForm [name="evidence_ref"]').fill('G3J-SYNTHETIC-AUTH-REFERENCE')
                page.locator('#invPaymentRequestForm button[type="submit"]').click()
                page.wait_for_function('lastRequest?.path==="/api/inventory/supplier-payment-requests"')
                assert page.evaluate('lastRequest.data.due_line_id')==201
                assert page.evaluate('lastRequest.data.amount')=='55.00'
                # Reviewer sees the exact installment, invoice, and amount BEFORE approval.
                page.evaluate('''()=>{lastRequest=null;state.me={id:13,role:'reviewer'};
                  inventoryFixture.grants={can_prepare:0,can_approve:1};renderInventory();}''')
                page.locator('[data-inv-payment-decision="307:approve"]').wait_for(timeout=7000)
                page.evaluate("inventoryFixture.supplier_payment_requests[0].vendor_active=0;renderInventory()")
                assert page.locator('[data-inv-payment-decision="307:approve"]').count()==0,'Inactive vendor was offered approval'
                assert page.locator('[data-inv-payment-decision="307:reject"]').count()==1,'Inactive vendor request cannot be rejected'
                page.evaluate("inventoryFixture.supplier_payment_requests[0].vendor_active=1;renderInventory()")
                page.locator('[data-inv-payment-decision="307:approve"]').wait_for(timeout=7000)
                detail=page.locator('[data-inv-payment-id="307"]').inner_text()
                assert 'SYN-G3J-INV-002' in detail and '2026-12-20' in detail and '60.00' in detail,detail
                page.locator('[data-inv-payment-decision="307:approve"]').click()
                page.wait_for_function('lastRequest?.path==="/api/inventory/supplier-payment-requests/307/decision"')
                # Source invoice creator must never see a review button.
                page.evaluate('''()=>{state.me={id:10,role:'reviewer'};renderInventory();}''')
                assert page.locator('[data-inv-payment-decision="307:approve"]').count()==0
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
                assert not errors,(width,errors)
                page.close()
            print('PASS G3J Chromium 320/375/1440: Cairo CSS family, pre-payment form, independent visible review, no overflow')
        finally:browser.close()


if __name__=='__main__':run()
