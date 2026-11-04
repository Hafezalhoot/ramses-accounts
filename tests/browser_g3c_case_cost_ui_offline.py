"""Real Chromium verifies case consumables cost lookup and stale-result removal in RTL."""
from browser_helpers import chromium_options
from pathlib import Path
from playwright.sync_api import sync_playwright
from test_v82_g2t_inventory_ui import BOOT

ROOT=Path(__file__).resolve().parents[1]
CASE_FIXTURE = r'''
const oldCostApi=api;
window.caseCostShouldDeny=false;
window.api=async function(path){
 if(path==='/api/inventory/cases/42/cost'){
   if(window.caseCostShouldDeny)throw Error('Access revoked by source permission');
   return {case_id:42,case_no:'SYN-CASE-42',total_cost_piasters:5600,
     approved_issue_count:1,pending_issue_count:1,source:'approved_fifo_consumables_only',
     lines:[{issue_id:19,used_on:'2026-10-31',department_id:5,
       item_id:1,item_code:'GLOVES',item_name:'SYNTHETIC-DRESSING',quantity:4,cost_piasters:5600}]};
 }
 return oldCostApi(path);
};
'''


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(**chromium_options(),headless=True,
                                  args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            for width in (1440,375,320):
                page=browser.new_page(viewport={'width':width,'height':900})
                errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.set_content('<!doctype html><html lang="ar" dir="rtl"><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><main id="content"></main></body></html>')
                page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
                page.add_script_tag(content=BOOT)
                page.add_script_tag(content=CASE_FIXTURE)
                page.add_script_tag(content=(ROOT/'static/inventory_ui.js').read_text())
                page.evaluate('renderInventory()')
                page.locator('[data-inv-tab="reports"]').click()
                form=page.locator('#invCaseCostForm')
                assert form.count()==1, ('missing cost lookup form',width)
                form.locator('[name="case_id"]').fill('42')
                form.locator('button[type="submit"]').click()
                page.get_by_text('SYNTHETIC-DRESSING').wait_for()
                section=page.locator('#invCaseCostResult')
                assert '56.00' in section.inner_text(),section.inner_text()
                assert '19' in section.inner_text() and '4' in section.inner_text()
                assert not errors,errors
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
                # Revocation on a subsequent request must not leave the prior cost visible.
                page.evaluate('window.caseCostShouldDeny=true')
                form.locator('button[type="submit"]').click()
                page.wait_for_function("document.querySelector('#invCaseCostResult')?.textContent?.includes('Access revoked')")
                assert 'SYNTHETIC-DRESSING' not in section.inner_text(),section.inner_text()
                assert '56.00' not in section.inner_text(),section.inner_text()
                assert not errors,errors
                page.close()
            print('PASS G3C Chromium 1440/375/320 case FIFO cost lookup, denied stale removal, no overflow')
        finally:
            browser.close()


if __name__=='__main__':run()
