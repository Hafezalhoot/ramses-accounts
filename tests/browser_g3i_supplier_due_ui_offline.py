"""G3I offline Chromium regression: gross due timing and reviewer installment evidence."""
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
                page=browser.new_page(viewport={'width':width,'height':850})
                errors=[];page.on('pageerror',lambda x:errors.append(str(x)))
                page.set_content('<!doctype html><html lang="ar" dir="rtl"><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><main id="content"></main></body></html>')
                page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
                page.add_script_tag(content=BOOT)
                page.evaluate('''()=>{
                  state.me={id:8,role:'clerk'};inventoryFixture.grants={can_prepare:1,can_approve:0};
                  inventoryFixture.supplier_due_eligible_invoices=[{id:51,invoice_ref:'G3I-INV-51',
                    invoice_date:'2026-10-20',amount_piasters:10000,vendor_name:'Synthetic Vendor'}];
                  inventoryFixture.supplier_due_schedules=[{id:91,invoice_ref:'G3I-INV-91',
                    invoice_date:'2026-11-01',scheduled_on:'2026-11-01',terms_ref:'SIGNED-SYN-91',
                    status:'pending',created_by:8,invoice_creator:7,receipt_creator:7,amount_piasters:10000}];
                  inventoryFixture.supplier_due_lines=[{schedule_id:91,line_no:1,due_on:'2026-12-05',amount_piasters:4000},
                    {schedule_id:91,line_no:2,due_on:'2027-01-15',amount_piasters:6000}];
                  inventoryFixture.supplier_aging={approved_invoice_total_piasters:10000,
                    scheduled_total_piasters:0,unscheduled_total_piasters:10000,
                    future_piasters:0,due_today_piasters:0,over_1_30_piasters:0,
                    over_31_60_piasters:0,over_61_90_piasters:0,over_90_piasters:0,
                    vendors:[],payment_posted_piasters:0};
                }''')
                page.add_script_tag(content=(ROOT/'static/inventory_ui.js').read_text())
                page.evaluate('renderInventory()')
                page.locator('#invDueScheduleForm').wait_for(timeout=7000)
                assert 'قبل السداد' in page.locator('#content').inner_text()
                page.locator('#invDueScheduleForm select[name="invoice_match_id"]').select_option('51')
                assert page.locator('#invDueScheduleForm [name="due_on"]').first.get_attribute('min')=='2026-10-20'
                page.locator('#invDueScheduleForm [name="terms_ref"]').fill('SIGNED-TERMS-SYN-51')
                page.locator('#invDueScheduleForm [name="due_on"]').first.fill('2026-12-05')
                page.locator('#invDueScheduleForm [name="amount"]').first.fill('40.00')
                page.locator('#invAddInstallment').click()
                assert page.locator('#invDueScheduleForm [name="amount"]').count()==2
                page.locator('#invDueScheduleForm [name="due_on"]').nth(1).fill('2027-01-15')
                page.locator('#invDueScheduleForm [name="amount"]').nth(1).fill('60.00')
                page.locator('#invDueScheduleForm button[type="submit"]').click()
                page.wait_for_function('lastRequest?.path==="/api/inventory/supplier-due-schedules"')
                assert page.evaluate('lastRequest.data.lines.length')==2
                assert page.evaluate('lastRequest.data.invoice_match_id')==51
                assert page.evaluate('lastRequest.data.scheduled_on')==page.evaluate("new Date().toLocaleDateString('sv-SE',{timeZone:'Africa/Cairo'})")
                page.evaluate('lastRequest=null;state.me={id:9,role:"reviewer"};inventoryFixture.grants={can_prepare:0,can_approve:1};renderInventory()')
                page.locator('[data-inv-due-decision="91:approve"]').wait_for(timeout=7000)
                details=page.locator('[data-inv-due-schedule="91"]').inner_text()
                assert '2026-12-05' in details and '2027-01-15' in details and '40.00' in details
                page.locator('[data-inv-due-decision="91:approve"]').click()
                page.wait_for_function('lastRequest?.path==="/api/inventory/supplier-due-schedules/91/decision"')
                page.evaluate('lastRequest=null;inventoryFixture.supplier_due_lines=[];renderInventory()')
                assert page.locator('[data-inv-due-decision="91:approve"]').count()==0
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
                assert not errors,(width,errors)
                page.close()
            print('PASS G3I Chromium 320/375/1440: installment form, approved due review details, Cairo date, no overflow')
        finally:browser.close()

if __name__=='__main__':run()
