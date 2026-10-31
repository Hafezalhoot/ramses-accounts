"""Headless Chromium opening review UX (real shipped assets; synthetic API fixture)."""
from pathlib import Path
import re
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]

def main():
    html=re.sub(r'<(?:script|link)\b[^>]*(?:src|href)="/static/[^>]*>\s*(?:</script>)?', '',
                (ROOT/'static/index.html').read_text())
    month='2026-10'
    bank={'id':4,'code':'bank','name':'حساب بنك تجريبي','kind':'bank','active':1,
          'balance_piasters':150000,'opening_piasters':150000,'transaction_count':0}
    cash={'id':1,'code':'cash_main','name':'خزنة تجريبية','kind':'cash','active':1,
          'balance_piasters':0,'opening_piasters':0,'transaction_count':0}
    reviews={'period':month,'funds':[
          {**bank,'review_status':'pending','review_id':33,'review_needed':True,
           'review_issue':'قيد المراجعة','evidence_reference':'BANK-TEST-001','created_by':5,
           'can_review':True,'verified_as_of_period':False},
          {**cash,'review_status':None,'review_id':None,'review_needed':False,
           'review_issue':'','evidence_reference':None,'can_review':False,
           'verified_as_of_period':False}],
          'offset_accounts':[{'id':31,'code':'3100','name':'رأس المال','class':'equity'}],
          'unverified_count':1}
    fixture={
       '/api/me':{'id':1,'username':'owner','role':'owner','csrf':'fake','environment':'staging'},
       '/api/lookups':{'funds':[bank,cash],'employees':[],'departments':[],'categories':[],'shifts':[]},
       '/api/funds':[bank,cash],
       '/api/accounting/opening-reviews?period='+month:reviews,
       '/api/dashboard?month='+month:{'receipts_piasters':0,'payments_piasters':0,
                'cash_difference_piasters':0,'pending':0,'daily':[],'latest':[],'legacy_issues':0}
    }
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',
                        args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            page=browser.new_page(viewport={'width':1440,'height':920})
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.set_content(html)
            page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
            page.evaluate('''obj=>{window.__f=obj;window.fetch=async u=>({ok:!!window.__f[u],
                     status:window.__f[u]?200:404,
                     json:async()=>window.__f[u]||{detail:'No fixture '+u}})}''',fixture)
            page.add_script_tag(content=(ROOT/'static/app.js').read_text())
            page.wait_for_selector('#shell:not([hidden])')
            page.evaluate('state.month="2026-10"')
            page.locator('#mainNav [data-view=funds]').click()
            page.wait_for_selector('.fund-opening-review')
            assert page.locator('.fund-opening-review').count()==2
            assert page.locator('[data-opening-decision="33"]').count()==2
            assert page.locator('[data-opening-submit="1"]').count()==1
            assert page.locator('[data-opening-submit="4"]').count()==0
            page.screenshot(path=str(ROOT.parent/'QA_G2L_OPENING_1440.png'),full_page=True)
            page.locator('[data-opening-decision="33"][data-result="approve"]').click()
            assert page.locator('#modal').is_visible()
            assert page.get_by_text('راجع المستند الأصلي قبل القرار',exact=False).count()>=1
            page.locator('#modalCancel').click()
            for width in (375,320):
                page.set_viewport_size({'width':width,'height':850})
                page.wait_for_timeout(120)
                assert page.locator('.fund-card').count()==2
                assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+2'),width
                assert page.locator('[data-opening-decision="33"]').first.is_visible()
                page.screenshot(path=str(ROOT.parent/f'QA_G2L_OPENING_{width}.png'),full_page=True)
            assert not errors,errors
            print('PASS G2L opening review UI: 1440, 375, 320; zero/candidate/reviewer states, modal, no overflow or console errors')
        finally:browser.close()

if __name__=='__main__':main()
