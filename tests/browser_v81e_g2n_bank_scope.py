"""Offline Chromium DOM smoke for G2N bank permissions (no network or patient data)."""
from browser_helpers import chromium_options
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def run():
    from playwright.sync_api import sync_playwright
    html=(ROOT/'static/index.html').read_text(encoding='utf8')
    for script in ('app.js','billing.js','cashier_ops_ui.js','financial_corrections_ui.js',
                   'late_entry_ui.js','pos_settlements_ui.js'):
        html=html.replace(f'<script src="/static/{script}" defer></script>','')
    html=html.replace('<link rel="stylesheet" href="/static/styles.css">','')
    period='2026-08'
    bank=51
    report={'month':period,'banks':[{'id':bank,'name':'Synthetic test bank','code':'SCOPE'}],
       'fund':{'id':bank,'name':'Synthetic test bank'},
       'permissions':{'can_submit':False,'can_approve':True},
       'batch':{'id':100,'fund_id':bank,'status':'draft','imported_by':1,
                'opening_piasters':0,'closing_piasters':1000},
       'lines':[{'id':201,'tx_date':'2026-08-14','line_no':1,'description':'Synthetic bank receipt',
                 'reference':'SCOPE-1','amount_piasters':1000,'match_id':None}],
       'unmatched_ledger':[{'movement_id':300,'booked_on':'2026-08-14',
                             'amount_piasters':1000,'voucher_no':'SCOPE-300','description':'Synthetic journal'}],
       'ledger_opening_piasters':0,'ledger_closing_piasters':1000,'pending_vouchers':0,
       'unmatched_bank_count':1,'matched_count':0,'bank_opening_piasters':0,
       'bank_closing_piasters':1000,'balance_difference_piasters':0,'month_closed':False,
       'warning':'Test-only reconciliation; not a real bank statement.'}
    pos={'period':period,'bank_fund_id':bank,'banks':report['banks'],
         'clearing_fund_id':None,'clearing_name':None,'bank_sealed':False,
         'period_closed':False,'candidates':[],'settlements':[],
         'permissions':{'can_submit':False,'can_approve':False},
         'note':'تحتاج تسويات POS إلى تفويض مستقل على محفظة مقاصة البطاقات.'}
    fixtures={
      '/api/me':{'id':2,'username':'test_reviewer','role':'reviewer','csrf':'test-csrf','environment':'staging'},
      '/api/lookups':{'funds':[],'employees':[],'departments':[],'categories':[],'shifts':[]},
      '/api/dashboard?month=2026-10':{'receipts_piasters':0,'payments_piasters':0,'cash_difference_piasters':0,'pending':0,'daily':[],'latest':[],'legacy_issues':0},
      '/api/bank-reconciliation?period=2026-08':report,
      '/api/bank-reconciliation?period=2026-08&fund_id=51':report,
      '/api/pos/settlements?period=2026-08&bank_fund_id=51':pos,
    }
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,**chromium_options(),
                                  args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            page=browser.new_page(viewport={'width':1440,'height':900})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.set_content(html)
            page.add_style_tag(content=(ROOT/'static/styles.css').read_text(encoding='utf8'))
            page.evaluate('''obj=>{window.__g2nfixtures=obj;window.fetch=async url=>({
               ok:!!window.__g2nfixtures[url],
               status:window.__g2nfixtures[url]?200:404,
               json:async()=>window.__g2nfixtures[url]||{detail:'Unmocked: '+url}
            })}''',fixtures)
            page.add_script_tag(content=(ROOT/'static/app.js').read_text(encoding='utf8'))
            page.add_script_tag(content=(ROOT/'static/pos_settlements_ui.js').read_text(encoding='utf8'))
            page.wait_for_selector('#shell:not([hidden])',timeout=15000)
            page.evaluate("state.bankMonth='2026-08';state.bankFundId=null;void navigate('bank')")
            page.wait_for_selector('.bank-toolbar',timeout=15000)
            page.wait_for_selector('#posSettlementPanel .pos-panel',timeout=10000)
            assert page.locator('#bankFundFilter option').count()==1
            assert page.locator('#bankImportForm').count()==0
            assert page.locator('[data-bank-match]').count()==0
            assert page.locator('#bankApprove').count()==0
            assert 'الاعتماد متاح' in page.locator('.bank-toolbar').inner_text()
            assert 'استكمال مطابقة' in page.locator('.bank-final').inner_text()
            assert 'تحتاج تسويات POS إلى تفويض مستقل' in page.locator('#posSettlementPanel').inner_text()
            assert not errors,errors
            page.screenshot(path='/mnt/data/QA_G2N_BANK_1440.png',full_page=True)
            page.set_viewport_size({'width':375,'height':812})
            page.wait_for_timeout(150)
            assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1'), 'mobile overflow'
            page.screenshot(path='/mnt/data/QA_G2N_BANK_375.png',full_page=True)
            # Alter only synthetic fixture: preparer has submit but cannot approve.
            page.evaluate('''()=>{const r=window.__g2nfixtures['/api/bank-reconciliation?period=2026-08'];
                 r.permissions={can_submit:true,can_approve:false};void navigate('bank')}''')
            page.wait_for_selector('[data-bank-match]',timeout=10000)
            assert page.locator('#bankApprove').count()==0
            assert 'الاعتماد غير مفوض' in page.locator('.bank-toolbar').inner_text()
            assert not errors,errors
            # Full grant removal must yield a clear empty-state, with no action buttons.
            page.evaluate('''()=>{state.bankFundId=null;
                window.__g2nfixtures['/api/bank-reconciliation?period=2026-08']={
                    month:'2026-08',banks:[],batch:null,lines:[],unmatched_ledger:[],
                    permissions:{can_submit:false,can_approve:false}};
                void navigate('bank')}''')
            page.wait_for_function("document.querySelector('#content')?.textContent.includes('لم تُمنح صلاحية مراجعة أي حساب بنكي')")
            assert page.locator('#bankApprove').count()==0
            assert page.locator('#bankImportForm').count()==0
            assert not errors,errors
            print('PASS G2N OFFLINE Chromium 1440/375: bank role-grants, empty state, POS warning, no JS errors/overflow')
        finally:browser.close()

if __name__=='__main__':run()
