"""Headless Chromium POS settlement UI smoke; synthetic fixture, no network/backend."""
from browser_helpers import chromium_options
from pathlib import Path
from playwright.sync_api import sync_playwright
import re

ROOT=Path(__file__).resolve().parents[1]

def run():
    html=re.sub(r'<(?:script|link)\b[^>]*(?:src|href)="/static/[^>]*>\s*(?:</script>)?','',(ROOT/'static/index.html').read_text())
    month='2026-10'
    bank={'month':month,'banks':[{'id':4,'name':'Synthetic bank','code':'SYN'}],
        'fund':{'id':4,'name':'Synthetic bank'},'permissions':{'can_submit':True,'can_approve':True},'batch':None,'lines':[],
        'unmatched_ledger':[],'statement_sum_piasters':0,'matched_count':0,'unmatched_bank_count':0,
        'ledger_opening_piasters':0,'ledger_closing_piasters':0,
        'bank_opening_piasters':0,'bank_closing_piasters':0,'balance_difference_piasters':0,
        'pending_vouchers':0,'month_closed':False,'warning':'Synthetic demonstration only'}
    pos={'period':month,'bank_fund_id':4,'banks':[{'id':4,'name':'Synthetic bank'}],
         'bank_sealed':False,'period_closed':False,'permissions':{'can_submit':True,'can_approve':True},'clearing_fund_id':8,
         'clearing_name':'POS clearing test wallet','candidate_limit_reached':False,
         'candidates':[{'id':31,'amount_piasters':10000,'collection_no':'C-TEST-1',
                        'business_date':'2026-10-30','voucher_id':19},
                       {'id':32,'amount_piasters':6000,'collection_no':'C-TEST-2',
                        'business_date':'2026-10-30','voucher_id':20}],
         'settlements':[{'id':12,'settlement_ref':'SET-TEST-REF','settlement_date':'2026-10-30',
             'maker':'reviewer','reviewer':None,'status':'pending',
             'gross_piasters':10000,'fee_piasters':100,'net_piasters':9900,
             'part_ids':[9],'evidence_note':'Synthetic acquirer document only','reviewed_at':None}]}
    fixture={
     '/api/me':{'id':1,'username':'owner','role':'owner','csrf':'fake','environment':'staging'},
     '/api/lookups':{'funds':[{'id':4,'code':'bank','name':'Synthetic bank','kind':'bank'}],
                     'employees':[],'departments':[],'categories':[],'shifts':[]},
     '/api/dashboard?month='+month:{'receipts_piasters':0,'payments_piasters':0,
            'cash_difference_piasters':0,'pending':0,'daily':[],'latest':[],'legacy_issues':0},
     '/api/bank-reconciliation?period='+month:bank,
     '/api/bank-reconciliation?period='+month+'&fund_id=4':bank,
     '/api/pos/settlements?period='+month+'&bank_fund_id=4':pos,
    }
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,**chromium_options(),args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            page=browser.new_page(viewport={'width':1440,'height':920})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.set_content(html)
            page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
            page.evaluate('''obj=>{window.__fixtures=obj;window.fetch=async url=>({
              ok:!!window.__fixtures[url],status:window.__fixtures[url]?200:404,
              json:async()=>window.__fixtures[url]||{detail:'Missing test fixture '+url}})}''',fixture)
            page.add_script_tag(content=(ROOT/'static/app.js').read_text())
            page.add_script_tag(content=(ROOT/'static/pos_settlements_ui.js').read_text())
            page.wait_for_selector('#shell:not([hidden])')
            page.evaluate('state.bankMonth="2026-10"')
            page.locator('#mainNav [data-view=bank]').click()
            page.wait_for_selector('#posSettlementPanel #posSettlementForm')
            assert page.locator('[data-pospart]').count()==2
            assert page.locator('[data-posdecision="approve"]').count()==1
            assert page.locator('[data-posdecision="reject"]').count()==1
            page.locator('[data-pospart]').first.check()
            page.locator('[data-pospart]').last.check()
            page.locator('#posFee').fill('2')
            assert page.locator('#posGross').inner_text()=='160.00'
            assert page.locator('#posNet').inner_text()=='158.00'
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth+2')
            page.screenshot(path=str(ROOT.parent/'QA_G2K_POS_1440.png'),full_page=True)
            page.locator('[data-posdecision="approve"]').click()
            assert page.locator('#modal').is_visible()
            page.locator('#modalCancel').click()
            for width in (375,320):
                page.set_viewport_size({'width':width,'height':850})
                page.evaluate('document.documentElement.style.scrollBehavior="auto";window.scrollTo(0,0)')
                page.wait_for_timeout(100)
                assert page.locator('#posSettlementPanel').is_visible()
                assert page.locator('#posSettlementForm').is_visible()
                assert page.locator('[data-pospart]').count()==2
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth+2'),width
                page.screenshot(path=str(ROOT.parent/f'QA_G2K_POS_{width}.png'),full_page=True)
            assert not errors,errors
            print('PASS G2K POS UI: 1440/375/320, 160 - 2 = 158, review controls, no console errors/overflow')
        finally:browser.close()

if __name__=='__main__':run()
