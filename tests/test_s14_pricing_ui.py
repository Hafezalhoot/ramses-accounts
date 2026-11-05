"""Synthetic browser acceptance for S14 forms; never opens deployment or user data."""
from pathlib import Path
from playwright.sync_api import sync_playwright
from browser_helpers import chromium_options

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = r'''
state.me={id:1,role:'owner'};state.lookups={departments:[{id:1,name:'قسم تجريبي'}]};
window.posts=[];window.staleOrder=false;window.stalePackage=false;window.quoteNo=0;
window.catalog={lists:[{id:1,code:'CASH',name:'قائمة تجريبية',active:true}],
 locations:[{id:1,code:'LAB',name:'معمل تجريبي',department_id:1,active:true}],
 services:[{id:1,code:'OXY',name:'خدمة تجريبية',department_id:1,department_name:'قسم تجريبي',unit:'ساعة',managed_pricing:true}],
 people:[{id:1,code:'DR1',name:'منفذ تجريبي',category:'doctor',active:true},{id:2,code:'DR2',name:'منفذ ثان',category:'doctor',active:true}],
 rates:[{id:1,price_list_id:1,location_id:1,service_id:1,valid_from:'2026-01-01',price_piasters:20000,estimated_cost_piasters:null,rules:[]}],
 packages:[{id:11,package_id:1,code:'PK1',name:'باقة تجريبية',price_list_id:1,valid_from:'2026-01-01',gross_piasters:40000,net_piasters:36000,items:[{service_id:1,location_id:1,quantity:2}]}]};
api=async path=>{
 if(path==='/api/pricing/catalog')return structuredClone(window.catalog);
 if(path==='/api/service-fees/queue')return {items:[{line_id:31,occurrence_no:1,rule_index:0,person_id:1,person_name:'منفذ تجريبي',invoice_id:12,invoice_no:'INV-TEST',case_no:'CASE-TEST',service_name:'خدمة تجريبية',kind:'fixed',amount_piasters:2500,collected_piasters:0,calculation_hash:'fee-hash'}]};
 if(path==='/api/service-fees/balances')return {items:[{person_id:1,person_name:'منفذ تجريبي',amount_piasters:2500}],decisions:[{id:8,line_id:30,occurrence_no:1,rule_index:0,person_id:1,person_name:'منفذ تجريبي',invoice_no:'INV-OLD',case_no:'CASE-OLD',service_name:'خدمة تجريبية',amount_piasters:2500,decision:'approved',reason:'اختبار',decided_at:'2026-01-01',reversed:false}]};
 throw Error('Unexpected GET '+path);
};
post=async(path,data)=>{
 window.posts.push({path,data:structuredClone(data)});
 if(path==='/api/pricing/package-preview')return {preview_hash:data.final_amount==='350.00'?'b'.repeat(64):'a'.repeat(64),gross_piasters:40000,net_piasters:36000,discount_piasters:4000,cost_complete:false,estimated_cost_piasters:null,known_cost_piasters:0,lines:[]};
 if(path==='/api/pricing/packages'&&window.stalePackage){window.stalePackage=false;const e=Error('تغيرت تعريفة مكونات الباقة؛ أعد المعاينة');e.status=409;throw e;}
 if(path==='/api/pricing/quote')return {quote_hash:'quote-'+(++window.quoteNo),gross_piasters:40000,net_piasters:36000,discount_piasters:4000,...(state.me.role==='owner'?{cost_complete:true,estimated_cost_piasters:30000}:{}),lines:[{service_id:1,service_name:'خدمة تجريبية',location_id:1,location_name:'معمل تجريبي',quantity:2,unit_price_piasters:20000,gross_piasters:40000,net_piasters:36000,...(state.me.role==='owner'?{commission_preview:[{person_id:1,person_name:'منفذ تجريبي',amount_piasters:10000,projection_only:true}]}:{})}]};
 if(path==='/api/pricing/orders'&&window.staleOrder){window.staleOrder=false;throw Error('تغير السعر، اطلب معاينة جديدة');}
 return {id:9};
};
navigate=async view=>{window.lastNavigate=view};
toast=(message,bad=false)=>{window.lastToast={message,bad}};
'''


def run():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, **chromium_options())
        try:
            for width in (1440, 375):
                page = browser.new_page(viewport={"width": width, "height": 900})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.set_content('<html lang="ar" dir="rtl"><body><main id="content"></main></body></html>')
                page.add_style_tag(content=(ROOT / "static/styles.css").read_text())
                app = (ROOT / "static/app.js").read_text().replace('initializeEvents();loadSession();', '')
                page.add_script_tag(content=app)
                page.add_script_tag(content=(ROOT / "static/billing.js").read_text())
                page.evaluate(FIXTURE)
                source = ROOT / 'static/pricing_ui.js'
                if source.exists():
                    page.add_script_tag(content=source.read_text())
                assert page.evaluate("typeof window.renderPricing==='function'"), 'S14 owner pricing workspace is missing'
                page.add_style_tag(content=(ROOT / 'static/pricing_ui.css').read_text())
                page.evaluate('renderPricing()')
                if width == 375:
                    mobile_rates = page.locator('.pricing-mobile-rates')
                    assert mobile_rates.is_visible(), 'Phone pricing requires readable rate cards'
                    price = mobile_rates.locator('.pricing-rate-price').first
                    assert '200.00' in price.inner_text()
                    box = price.bounding_box()
                    assert box['x'] >= 0 and box['x'] + box['width'] <= width
                    assert not page.locator('.pricing-desktop-rates').is_visible()
                else:
                    assert page.locator('.pricing-desktop-rates').is_visible()
                    assert not page.locator('.pricing-mobile-rates').is_visible()
                page.locator('#pricingNewRate').click()
                page.get_by_label('سعر الخدمة (ج.م)', exact=True).fill('200.00')
                page.locator('[data-add-rule]').click()
                page.get_by_label('نوع الحصة', exact=True).select_option('fixed')
                page.get_by_label('قيمة الحصة', exact=True).fill('20.00')
                page.locator('#pricingDialogForm').evaluate('(f)=>f.requestSubmit()')
                page.wait_for_function("posts.some(x=>x.path==='/api/pricing/rates')")
                rate = page.evaluate("posts.find(x=>x.path==='/api/pricing/rates').data")
                assert rate['rules'][0]['fixed_amount'] == '20.00'
                assert rate['rules'][0]['discount_affects'] is False
                assert rate['rules'][0]['basis'] == 'collected'
                assert rate['rules'][0]['distribution'] == 'shared'

                page.locator('[data-pricing-tab="packages"]').click()
                if width == 375:
                    cards = page.locator('.pricing-mobile-packages')
                    assert cards.is_visible()
                    assert '360.00' in cards.locator('.pricing-package-net').first.inner_text()
                    assert '40.00' in cards.locator('.pricing-package-discount').first.inner_text()
                else:
                    assert page.locator('.pricing-desktop-packages').is_visible()
                page.locator('#pricingNewPackage').click()
                page.get_by_label('كود الباقة', exact=True).fill('PK2')
                page.get_by_label('اسم الباقة', exact=True).fill('باقة ثانية')
                page.get_by_label('القيمة النهائية (ج.م)', exact=True).fill('360.00')
                page.locator('[data-package-preview]').click()
                page.get_by_text('التكلفة غير مكتملة', exact=False).wait_for()
                assert page.locator('#pricingDialogSave').is_enabled()
                page.get_by_label('القيمة النهائية (ج.م)', exact=True).fill('350.00')
                assert page.locator('#pricingDialogSave').is_disabled(), 'Edited preview must be invalidated'
                page.locator('[data-package-preview]').click()
                page.evaluate('window.stalePackage=true')
                page.locator('#pricingDialogSave').click()
                page.wait_for_function("posts.some(x=>x.path==='/api/pricing/packages')")
                page.locator('#pricingDialogError').get_by_text('تغيرت تعريفة مكونات الباقة؛ أعد المعاينة', exact=True).wait_for()
                assert page.locator('#pricingDialogSave').is_disabled(), 'Stale server preview must disable package save'
                assert page.evaluate("posts.filter(x=>x.path==='/api/pricing/package-preview').length") == 2, '409 must not automatically preview or save again'
                assert page.evaluate("posts.find(x=>x.path==='/api/pricing/packages').data.preview_hash") == 'b' * 64
                page.locator('[data-package-preview]').click()
                page.locator('#pricingDialogSave').click()
                page.wait_for_function("posts.filter(x=>x.path==='/api/pricing/packages').length===2")
                package = page.evaluate("posts.find(x=>x.path==='/api/pricing/packages').data")
                assert package['final_amount'] == '350.00'
                assert package['preview_hash'] == 'b' * 64
                assert package['items'] == [{'service_id':1,'location_id':1,'quantity':1}]

                page.locator('[data-pricing-tab="directory"]').click()
                page.locator('#pricingNewService').click()
                page.get_by_label('كود الخدمة', exact=True).fill('NEW1')
                page.get_by_label('اسم الخدمة', exact=True).fill('خدمة وهمية جديدة')
                page.get_by_label('وحدة الخدمة', exact=True).fill('ساعة')
                page.locator('#pricingDialogSave').click()
                page.wait_for_function("posts.some(x=>x.path==='/api/pricing/services/9/details')")
                service = page.evaluate("posts.find(x=>x.path==='/api/billing/services').data")
                assert service == {'code':'NEW1','name':'خدمة وهمية جديدة','department_id':1,'suggested_point':'either'}
                assert page.evaluate("posts.find(x=>x.path==='/api/pricing/services/9/details').data.unit") == 'ساعة'

                page.evaluate("state.me.role='clerk';window.staleOrder=true;pricingOrderForCase(7)")
                page.get_by_label('نوع الطلب', exact=True).select_option('package')
                page.get_by_label('منفذون مقترحون — خدمة تجريبية / معمل تجريبي', exact=True).select_option('1')
                page.locator('[data-order-preview]').click()
                page.locator('#pricingDialogSave').click()
                page.wait_for_function('quoteNo===2')
                assert page.evaluate("posts.filter(x=>x.path==='/api/pricing/orders').length") == 1
                assert page.locator('#pricingDialogSave').is_enabled()
                page.locator('#pricingDialogSave').click()
                page.wait_for_function("window.lastNavigate==='billing'")
                orders = page.evaluate("posts.filter(x=>x.path==='/api/pricing/orders')")
                assert len(orders) == 2
                assert orders[1]['data']['quote_hash'] == 'quote-2'
                assert orders[1]['data']['performers'] == [{'service_id':1,'location_id':1,'person_ids':[1]}]
                assert len(orders[1]['data']['request_id']) >= 16
                assert page.locator('dialog[open]').count() == 0
                page.locator('#pricingDialog').wait_for(state='detached')
                page.evaluate('pricingOrderForCase(7)')
                page.get_by_label('نوع الطلب', exact=True).select_option('package')
                same = page.get_by_label('نفس المنفذين لكل مرات التنفيذ — خدمة تجريبية / معمل تجريبي', exact=True)
                same.wait_for(timeout=2500)
                same.uncheck()
                page.get_by_label('منفذون مقترحون — خدمة تجريبية / معمل تجريبي — المرة 1', exact=True).select_option('1')
                page.get_by_label('منفذون مقترحون — خدمة تجريبية / معمل تجريبي — المرة 2', exact=True).select_option('2')
                page.locator('[data-order-preview]').click()
                page.locator('#pricingDialogSave').click()
                page.wait_for_function("posts.filter(x=>x.path==='/api/pricing/orders').length===3")
                split = page.evaluate("posts.filter(x=>x.path==='/api/pricing/orders')[2].data.performers")
                assert split == [{'service_id':1,'location_id':1,'person_ids':[], 'occurrence_performers':[{'occurrence_no':1,'person_ids':[1]},{'occurrence_no':2,'person_ids':[2]}]}]
                page.locator('#pricingDialog').wait_for(state='detached')
                page.evaluate('pricingOrderForCase(7)')
                page.get_by_label('الكمية', exact=True).fill('2')
                page.get_by_label('نفس المنفذين لكل مرات التنفيذ — خدمة تجريبية / معمل تجريبي', exact=True).uncheck()
                page.get_by_label('منفذون مقترحون — خدمة تجريبية / معمل تجريبي — المرة 1', exact=True).select_option('1')
                page.get_by_label('منفذون مقترحون — خدمة تجريبية / معمل تجريبي — المرة 2', exact=True).select_option('2')
                page.locator('[data-order-preview]').click()
                assert page.locator('#pricingDialogSave').is_enabled()
                page.get_by_label('الكمية', exact=True).fill('3')
                assert page.locator('#pricingDialogSave').is_disabled()
                assert page.get_by_label('منفذون مقترحون — خدمة تجريبية / معمل تجريبي — المرة 2', exact=True).evaluate('(s)=>s.selectedOptions[0].value') == '2'
                page.get_by_label('منفذون مقترحون — خدمة تجريبية / معمل تجريبي — المرة 3', exact=True).select_option('1')
                page.locator('[data-order-preview]').click()
                assert page.locator('#pricingDialog').get_by_text('التكلفة الاسترشادية', exact=True).count() == 0
                page.locator('#pricingDialogSave').click()
                page.wait_for_function("posts.filter(x=>x.path==='/api/pricing/orders').length===4")
                single = page.evaluate("posts.filter(x=>x.path==='/api/pricing/orders')[3].data.lines")
                assert single == [{'service_id':1,'quantity':3,'performer_ids':[], 'occurrence_performers':[{'occurrence_no':1,'person_ids':[1]},{'occurrence_no':2,'person_ids':[2]},{'occurrence_no':3,'person_ids':[1]}]}]
                page.locator('#pricingDialog').wait_for(state='detached')
                page.evaluate("state.me.role='owner';pricingOrderForCase(7)")
                page.locator('[data-order-preview]').click()
                page.get_by_text('الفرق التقديري سالب', exact=False).wait_for()
                assert page.locator('#pricingDialogSave').is_enabled(), 'Negative projection should warn without blocking a valid tariff'
                page.locator('[data-dialog-close]').first.click()
                page.evaluate("state.me.role='clerk'")
                page.evaluate('renderPricing()')
                assert page.locator('#pricingNewRate').count() == 0

                page.evaluate("state.me.role='reviewer';renderServiceFees()")
                page.locator('.pricing-fee-card').get_by_text('مبلغ ثابت', exact=False).wait_for(timeout=2500)
                page.locator('[data-fee-decision="approve"]').click()
                page.get_by_label('سبب القرار', exact=True).fill('تمت المراجعة المستقلة')
                page.locator('#pricingDialogSave').click()
                page.wait_for_function("posts.some(x=>x.path==='/api/service-fees/decisions')")
                decision = page.evaluate("posts.find(x=>x.path==='/api/service-fees/decisions').data")
                assert decision['expected_amount_piasters'] == 2500
                assert decision['calculation_hash'] == 'fee-hash'
                assert decision['occurrence_no'] == 1
                assert decision['person_id'] == 1
                assert decision['decision'] == 'approve'
                page.locator('[data-fee-reverse="8"]').click()
                page.get_by_label('سبب العكس', exact=True).fill('تصحيح موثق للقرار التجريبي')
                page.locator('#pricingDialogSave').click()
                page.wait_for_function("posts.some(x=>x.path==='/api/service-fees/decisions/8/reverse')")
                # A late privileged response must not replace a new cashier session.
                page.locator('#pricingDialog').wait_for(state='detached')
                page.evaluate("""() => {
                  window.originalApi=api;
                  api=path=>path==='/api/pricing/catalog'?new Promise(resolve=>window.finishOldPricing=resolve):originalApi(path);
                  state.me={id:1,role:'owner'};window.oldPricingTask=renderPricing();
                  state.me={id:77,role:'clerk'};document.querySelector('#content').innerHTML='<p id="cashierNewSession">جلسة كاشير جديدة</p>';
                  finishOldPricing(structuredClone(catalog));
                }""")
                page.evaluate('oldPricingTask')
                assert page.locator('#cashierNewSession').is_visible()
                assert page.locator('#pricingNewRate').count()==0
                page.evaluate('() => {api=originalApi;}')
                assert not errors, errors
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'), width
                page.close()
                print('PASS S14 synthetic UI', width)
        finally:
            browser.close()


if __name__ == '__main__':
    run()
