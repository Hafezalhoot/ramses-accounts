"""G3M actual Chromium: maker/checker evidence before reattribution of historic GL."""
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
                page.on('pageerror',lambda x:errors.append(str(x)))
                page.set_content('<!doctype html><html lang="ar" dir="rtl"><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><main id="content"></main></body></html>')
                page.add_style_tag(content=(ROOT/'static/styles.css').read_text(encoding='utf8'))
                page.add_script_tag(content=BOOT)
                page.evaluate('''()=>{
                  state.me={id:2,role:'clerk'};inventoryFixture.grants={can_prepare:1,can_approve:0};
                  inventoryFixture.supplier_control_ledger={as_of:'2026-11-01',control_account:'2200',
                    control_2200_piasters:12550,attributed_2200_piasters:0,unattributed_2200_piasters:12550,
                    reconciled:false,vendor_count:0,vendors:[],anomalies:[],
                    unattributed_journals:[{journal_id:93,entry_date:'2026-10-28',origin:'manual',ap_delta_piasters:12550},
                    {journal_id:94,entry_date:'2026-10-29',origin:'manual',ap_delta_piasters:3000}],
                    scope:'لا ينشأ قيد جديد؛ نسب تاريخي بعد موافقة مستقلة'};
                  inventoryFixture.supplier_attribution_documents=[{
                    id:5,gl_journal_id:93,vendor_id:1,vendor_name:'مورد تجريبي',status:'pending',
                    evidence_ref:'SIGNED-HISTORIC-GL-EVIDENCE-REF-001',reason:'Signed AP verification for archived supplier source',
                    entry_date:'2026-10-28',ap_delta_piasters:12550,created_by:2,original_creator:1,original_reviewer:1
                  }];
                }''')
                page.add_script_tag(content=(ROOT/'static/inventory_ui.js').read_text(encoding='utf8'))
                page.evaluate('renderInventory()')
                page.locator('[data-inv-tab="suppliers"]').click()
                maker=page.locator('#invSupplierAttributionForm')
                maker.wait_for(timeout=8000)
                assert 'القيد' in page.locator('#invSupplierAttributionPanel').inner_text()
                maker.locator('[name="journal_id"]').select_option('94')
                maker.locator('[name="vendor_id"]').select_option('1')
                maker.locator('[name="evidence_ref"]').fill('SIGNED-HISTORIC-GL-EVIDENCE-REF-001')
                maker.locator('[name="reason"]').fill('Signed AP verification for archived supplier source')
                maker.locator('button[type="submit"]').click()
                page.wait_for_function("lastRequest?.path==='/api/inventory/supplier-attributions'")
                assert page.evaluate('lastRequest.data.journal_id')==94
                assert page.locator('[data-inv-attribution-decision]').count()==0
                page.evaluate("state.me={id:3,role:'reviewer'};inventoryFixture.grants={can_prepare:0,can_approve:1};lastRequest=null;renderInventory()")
                reviewer=page.locator('#invSupplierAttributionPanel')
                reviewer.wait_for(timeout=8000)
                assert reviewer.get_by_text('SIGNED-HISTORIC-GL-EVIDENCE-REF-001').count()>=1
                assert reviewer.locator('[data-inv-attribution-decision="5:approve"]').count()==1
                reviewer.locator('[data-inv-attribution-decision="5:approve"]').click()
                page.wait_for_function("lastRequest?.path==='/api/inventory/supplier-attributions/5/decision'")
                assert page.evaluate('lastRequest.data.decision')=='approve'
                assert page.evaluate("getComputedStyle(document.body).fontFamily.includes('Cairo')"),width
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
                assert not errors,(width,errors)
                page.close()
            print('PASS G3M Chromium 320/375/1440 Cairo GL source proof, separated maker/reviewer, no horizontal overflow')
        finally:browser.close()
if __name__=='__main__':run()
