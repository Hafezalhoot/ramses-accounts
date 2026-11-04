"""Offline Chromium G3K payer and independent settlement review, including Cairo."""
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
                errors=[];page.on('pageerror',lambda exc: errors.append(str(exc)))
                page.set_content('<!doctype html><html lang="ar" dir="rtl"><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><main id="content"></main></body></html>')
                page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
                page.add_script_tag(content=BOOT)
                page.evaluate('''()=>{
                    state.me={id:8,role:'clerk'};
                    state.lookups.funds=[{id:4,kind:'bank',name:'حساب بنك تجريبي'}];
                    inventoryFixture.grants={can_prepare:1,can_approve:0};
                    inventoryFixture.supplier_payment_requests=[{id:122,status:'approved',created_by:2,
                       amount_piasters:6000,installment_piasters:7000,invoice_ref:'G3K-INV-01',
                       vendor_name:'مورد مستلزمات تجريبي',vendor_active:1,due_on:'2026-12-21'}];
                    inventoryFixture.supplier_settlements={supplier_invoice_total_piasters:10000,
                     supplier_booked_piasters:6000,bank_confirmed_piasters:0,
                     supplier_outstanding_book_piasters:4000,
                     supplier_outstanding_confirmed_piasters:10000,
                     items:[{payment_request_id:99,amount_piasters:6000,vendor_name:'مورد مستلزمات تجريبي',
                          invoice_ref:'G3K-INV-01',voucher_no:'RAM-2026-123',booked_piasters:6000,
                          bank_matched_piasters:0,bank_confirmed_piasters:0,voucher_status:'approved'}]};
                }''')
                page.add_script_tag(content=(ROOT/'static/inventory_ui.js').read_text())
                page.evaluate('renderInventory()')
                page.locator('[data-inv-tab="suppliers"]').click()
                form=page.locator('#invSupplierBankVoucherForm');form.wait_for(timeout=9000)
                assert 'Cairo' in page.evaluate('getComputedStyle(document.body).fontFamily')
                form.locator('select[name="payment_request_id"]').select_option('122')
                form.locator('select[name="bank_fund_id"]').select_option('4')
                form.locator('input[name="bank_reference"]').fill('SYN-G3K-BANK-REFERENCE')
                form.locator('button[type="submit"]').click()
                page.wait_for_function('lastRequest?.path==="/api/inventory/supplier-payment-requests/122/bank-voucher"')
                assert page.evaluate('lastRequest.data.bank_fund_id')==4
                assert page.evaluate('lastRequest.data.bank_reference')=='SYN-G3K-BANK-REFERENCE'
                assert 'المؤكد بنكيًا' in page.locator('#content').inner_text()
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
                assert not errors,(width,errors)
                page.close()
            print('PASS G3K Chromium 320/375/1440 Cairo + protected supplier bank voucher form and evidence states')
        finally:browser.close()

if __name__=='__main__':run()
