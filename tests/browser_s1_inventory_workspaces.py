"""S1 operational screen: real Chromium DOM, fake data only for visual/navigation checks.

This is NOT the live API integration test; see test_s1_real_workflow.py.
"""
from browser_helpers import chromium_options
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from test_v82_g2t_inventory_ui import BOOT

AREAS = ('overview', 'stock', 'purchasing', 'suppliers', 'returns', 'reports')


def run():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**chromium_options(), headless=True,
                                     args=['--no-sandbox', '--disable-dev-shm-usage'])
        try:
            for width in (320, 375, 1440):
                page = browser.new_page(viewport={'width': width, 'height': 900})
                errors = []
                page.on('pageerror', lambda exc: errors.append(str(exc)))
                page.set_content('<!doctype html><html lang="ar" dir="rtl"><head>'
                                 '<meta name="viewport" content="width=device-width,initial-scale=1">'
                                 '</head><body><main id="content"></main></body></html>')
                page.add_style_tag(content=(ROOT / 'static/styles.css').read_text(encoding='utf8'))
                page.add_script_tag(content=BOOT)
                page.add_script_tag(content=(ROOT / 'static/inventory_ui.js').read_text(encoding='utf8'))
                page.evaluate('renderInventory()')
                page.locator('[data-inv-tab]').first.wait_for(timeout=12000)
                assert page.locator('[data-inv-tab]').count() == len(AREAS)
                assert page.locator('[data-inv-tab="overview"]').get_attribute('aria-selected') == 'true'
                assert page.locator('#invReceiptForm').count() == 1, 'Existing operation must remain in DOM'
                assert not page.locator('#invReceiptForm').is_visible(), 'Non-active workflows must be hidden'
                assert page.locator('[data-inv-workspace]:visible').count() == 1
                assert page.locator('[data-inv-tab="stock"]').inner_text().strip()
                if width in (375, 1440):
                    page.screenshot(path=str(ROOT.parent / f'QA_S1_INVENTORY_OVERVIEW_{width}.png'),full_page=True)
                page.locator('[data-inv-tab="stock"]').click()
                page.locator('#invReceiptForm').wait_for(state='visible')
                assert page.locator('[data-inv-tab="stock"]').get_attribute('aria-selected') == 'true'
                assert page.locator('#invSupplierAttributionPanel').count() == 1
                assert not page.locator('#invSupplierAttributionPanel').is_visible()
                assert page.locator('[data-inv-workspace]:visible').count() == 1
                page.locator('#invReceiptForm [name="vendor_id"]').select_option('1')
                page.locator('#invReceiptForm [name="invoice_ref"]').fill('S1-SYNTHETIC-INVOICE')
                page.locator('#invReceiptForm [name="evidence_ref"]').fill('S1-WAREHOUSE-SIGNED-GRN')
                page.locator('#invReceiptForm [name="item_id"]').select_option('1')
                page.locator('#invReceiptForm [name="quantity"]').fill('2')
                page.locator('#invReceiptForm [name="unit_cost"]').fill('10.00')
                page.locator('#invReceiptForm button[type="submit"]').click()
                page.wait_for_function('lastRequest?.path==="/api/inventory/receipts"')
                page.wait_for_function('document.querySelector("[data-inv-tab=stock]")?.getAttribute("aria-selected")==="true"')
                assert page.locator('#invReceiptForm').is_visible(), 'After submission, keep the task area open'
                page.locator('[data-inv-tab="purchasing"]').click()
                assert page.locator('[data-inv-workspace]:visible').count() == 1
                assert page.locator('#invSupplierAttributionPanel').count() == 1
                page.locator('[data-inv-tab="suppliers"]').click()
                assert page.locator('#invSupplierAttributionPanel').is_visible()
                page.locator('[data-inv-tab="returns"]').click()
                assert page.locator('[data-inv-workspace]:visible').count() == 1
                page.locator('[data-inv-tab="reports"]').click()
                assert page.locator('#invCaseCostForm').is_visible()
                page.locator('[data-inv-tab="stock"]').focus()
                page.keyboard.press('ArrowRight')
                assert page.locator('[data-inv-tab="overview"]').get_attribute('aria-selected') == 'true', 'RTL keyboard right should select preceding tab'
                # Independent reviewer: read/review permitted, preparer inputs stay absent.
                page.evaluate("state.me={id:3,role:'reviewer'};inventoryFixture.grants={can_prepare:0,can_approve:1};renderInventory()")
                page.locator('[data-inv-tab]').first.wait_for()
                assert page.locator('#invReceiptForm').count() == 0
                page.locator('[data-inv-tab="stock"]').click()
                assert page.locator('[data-inv-decision]').count() >= 2
                assert page.locator('[data-inv-workspace]:visible').count() == 1
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2'), width
                assert not errors, (width, errors)
                if width in (375, 1440):
                    path=ROOT.parent / f'QA_S1_INVENTORY_WORKSPACE_{width}.png'
                    page.screenshot(path=str(path),full_page=True)
                page.close()
            print('PASS S1 Chromium 320/375/1440: task areas, preserved receipt flow, RTL keyboard, reviewer gates, no overflow')
        finally:
            browser.close()


if __name__ == '__main__':
    run()
