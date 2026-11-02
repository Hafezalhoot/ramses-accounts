"""G3H offline Chromium: PO, linked partial GRN, supplier invoice match, grants, RTL responsive."""
from pathlib import Path
import sys
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
                  state.me={id:7,role:'clerk'};inventoryFixture.grants={can_prepare:1,can_approve:0};
                  inventoryFixture.purchase_orders=[{id:17,vendor_id:1,ordered_on:'2026-10-31',
                    order_ref:'PO-SYN-17',status:'approved',created_by:8,total_piasters:6250}];
                  inventoryFixture.purchase_receipts=[{id:21,vendor_id:1,invoice_ref:'INV-SYN-21',
                    received_on:'2026-10-31',purchase_order_id:17,total_piasters:2500}];
                  inventoryFixture.supplier_invoice_matches=[{id:44,invoice_ref:'INV-SYN-44',
                    invoice_date:'2026-10-31',status:'pending',created_by:8,amount_piasters:2500}];
                  inventoryFixture.purchase_receipt_lines=[{receipt_id:21,item_id:1,
                    item_code:'GLOVES',item_name:'Synthetic non-drug supply',
                    quantity:2,unit_cost_piasters:1250}];
                  inventoryFixture.supplier_summary={total_grn_accrued_piasters:6250,
                    confirmed_piasters:0,unmatched_piasters:6250};
                }''')
                page.add_script_tag(content=(ROOT/'static/inventory_ui.js').read_text())
                page.evaluate('renderInventory()')
                page.locator('[data-inv-tab="purchasing"]').click()
                page.locator('#invPurchaseOrderForm').wait_for(timeout=6000)
                assert page.locator('#invSupplierInvoiceForm').count()==1
                assert page.locator('#invReceiptForm select[name="purchase_order_id"]').count()==1
                assert '6250' not in page.locator('#content').inner_text() # Currency is 62.50, not raw piasters.
                page.locator('#invPurchaseOrderForm [name="vendor_id"]').select_option('1')
                page.locator('#invPurchaseOrderForm [name="order_ref"]').fill('NEW-PO-SYN-001')
                page.locator('#invPurchaseOrderForm [name="evidence_ref"]').fill('SIGNED-PURCHASE-DOCUMENT')
                page.locator('#invPurchaseOrderForm [name="item_id"]').select_option('1')
                page.locator('#invPurchaseOrderForm [name="quantity"]').fill('5')
                page.locator('#invPurchaseOrderForm [name="unit_cost"]').fill('12.50')
                page.locator('#invPurchaseOrderForm button[type="submit"]').click()
                page.wait_for_function('lastRequest?.path==="/api/inventory/purchase-orders"')
                assert page.evaluate('lastRequest.data.lines[0].quantity')==5
                assert page.evaluate('lastRequest.data.ordered_on')==page.evaluate("new Date().toLocaleDateString('sv-SE',{timeZone:'Africa/Cairo'})")
                page.evaluate('lastRequest=null')
                page.locator('[data-inv-tab="stock"]').click()
                page.locator('#invReceiptForm select[name="purchase_order_id"]').select_option('17')
                page.locator('#invReceiptForm select[name="vendor_id"]').select_option('1')
                page.locator('#invReceiptForm [name="invoice_ref"]').fill('NEW-INV-003')
                page.locator('#invReceiptForm [name="evidence_ref"]').fill('GRN-SYN-003')
                page.locator('#invReceiptForm select[name="item_id"]').select_option('1')
                page.locator('#invReceiptForm [name="quantity"]').fill('2')
                page.locator('#invReceiptForm [name="unit_cost"]').fill('12.50')
                page.locator('#invReceiptForm button[type="submit"]').click()
                page.wait_for_function('lastRequest?.path==="/api/inventory/receipts"')
                assert page.evaluate('lastRequest.data.purchase_order_id')==17
                page.evaluate('lastRequest=null')
                page.locator('[data-inv-tab="purchasing"]').click()
                page.locator('#invSupplierInvoiceForm select[name="receipt_id"]').select_option('21')
                assert page.locator('#invInvoiceLines .inv-match-row').count()==1
                page.locator('#invInvoiceLines .inv-match-row [name="quantity"]').fill('2')
                page.locator('#invInvoiceLines .inv-match-row [name="unit_cost"]').fill('12.50')
                page.locator('#invSupplierInvoiceForm [name="amount"]').fill('25.00')
                page.locator('#invSupplierInvoiceForm [name="evidence_ref"]').fill('SIGNED-SUPPLIER-PDF-21')
                page.locator('#invSupplierInvoiceForm button[type="submit"]').click()
                page.wait_for_function('lastRequest?.path==="/api/inventory/supplier-invoices"')
                assert page.evaluate('lastRequest.data.amount')=='25.00'
                assert page.evaluate('lastRequest.data.invoice_ref')=='INV-SYN-21'
                assert page.evaluate('lastRequest.data.lines[0].item_id')==1
                assert page.evaluate('lastRequest.data.lines[0].quantity')==2
                page.evaluate('lastRequest=null;state.me={id:9,role:"reviewer"};inventoryFixture.grants={can_prepare:0,can_approve:1};renderInventory()')
                page.locator('[data-inv-decision="supplier-invoices:44:approve"]').click()
                page.wait_for_function('lastRequest?.path==="/api/inventory/supplier-invoices/44/decision"')
                assert page.locator('#invPurchaseOrderForm').count()==0
                assert page.locator('#invSupplierInvoiceForm').count()==0
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
                assert not errors,(width,errors)
                page.close()
            print('PASS G3H Chromium 320/375/1440: PO, linked GRN, invoice matching, separate reviewer, Cairo date, RTL')
        finally:browser.close()

if __name__=='__main__':run()
