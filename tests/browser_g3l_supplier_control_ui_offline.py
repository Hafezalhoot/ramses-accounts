"""G3L actual Chromium: Cairo RTL supplier 2200 control reconciliation, no hidden gaps."""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from test_v82_g2t_inventory_ui import BOOT


def run():
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,
            args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            for width in (320,375,1440):
                page=browser.new_page(viewport={'width':width,'height':900})
                page.set_default_timeout(5500)
                errors=[]
                page.on('pageerror',lambda x: errors.append(str(x)))
                page.set_content('<!doctype html><html lang="ar" dir="rtl"><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><main id="content"></main></body></html>')
                page.add_style_tag(content=(ROOT/'static/styles.css').read_text(encoding='utf8'))
                page.add_script_tag(content=BOOT.replace(
                    " throw Error('Missing fixture '+path);",
                    " if(path.startsWith('/api/inventory/supplier-control-ledger')) {window.g3lFetchCount=(window.g3lFetchCount||0)+1;return {...inventoryFixture.supplier_control_ledger,as_of:path.split('as_of=')[1]||'2026-11-01'};} throw Error('Missing fixture '+path);"))
                page.evaluate('''()=>{
                  state.me={id:1,role:'owner'};
                  inventoryFixture.supplier_control_ledger={as_of:'2026-11-01',control_account:'2200',
                    control_2200_piasters:11500,attributed_2200_piasters:11000,
                    unattributed_2200_piasters:500,reconciled:false,vendor_count:2,
                    vendors:[
                      {vendor_id:11,vendor_name:'مورد المستلزمات الطبية التجريبي ذو الاسم الطويل',vendor_code:'G3L-A',
                       accrued_piasters:10000,net_payments_piasters:2000,balance_piasters:8000,
                       approved_grn_count:2,approved_unmatched_grn_count:1},
                      {vendor_id:12,vendor_name:'مورد أدوات جراحية تجريبي',vendor_code:'G3L-B',
                       accrued_piasters:3000,net_payments_piasters:0,balance_piasters:3000,
                       approved_grn_count:1,approved_unmatched_grn_count:0}],
                    anomalies:[],unattributed_journals:[{journal_id:99,entry_date:'2026-11-01',origin:'manual',ap_delta_piasters:500}],
                    scope:'دفتر المخزون المعتمد فقط، لا يشمل الأرصدة الافتتاحية والضرائب'};
                }''')
                page.add_script_tag(content=(ROOT/'static/inventory_ui.js').read_text(encoding='utf8'))
                page.evaluate('renderInventory()')
                page.locator('[data-inv-tab="suppliers"]').click()
                panel=page.locator('#invSupplierControlPanel')
                panel.wait_for(timeout=9000)
                assert '2200' in panel.inner_text()
                assert 'غير منسوب' in panel.inner_text()
                assert 'مورد المستلزمات' in panel.inner_text()
                assert '5.00' in panel.inner_text()
                # Date selector must truly fetch the server's as-of projection.
                panel.locator('input[name="as_of"]').fill('2026-10-31')
                panel.locator('button[type="submit"]').click()
                page.wait_for_function("window.g3lFetchCount===1 && document.querySelector('#invSupplierControlPanel input[name=as_of]')?.value==='2026-10-31'")
                assert page.locator('#invSupplierControlPanel input[name="as_of"]').input_value()=='2026-10-31'

                assert page.evaluate("getComputedStyle(document.body).fontFamily.includes('Cairo')"),width
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
                assert not errors,(width,errors)
                page.close()
            print('PASS G3L Chromium Cairo RTL vendor control reconciliation and unassigned GL journals at 320/375/1440')
        finally:
            browser.close()

if __name__=='__main__':run()
