"""Chromium visual QA of shipped G2I shell at 320/375/620/621/768/1365px.

Local server access is blocked in sandbox. This renders the exact HTML + CSS
without network, and tests the visible UI; backend is covered in G2I API tests.
"""
from browser_helpers import chromium_options
from pathlib import Path
from playwright.sync_api import sync_playwright
import re

ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/'static/index.html').read_text()
html=re.sub(r'<(?:script|link)\b[^>]*(?:src|href)="/static/[^>]*>\s*(?:</script>)?', '', html)
css=(ROOT/'static/styles.css').read_text()
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,**chromium_options(),
        args=['--no-sandbox','--disable-dev-shm-usage'])
    try:
        for width in (320,375,620,621,768,1365):
            page=browser.new_page(viewport={'width':width,'height':850})
            page.set_content(html)
            page.add_style_tag(content=css)
            page.evaluate('document.querySelector("#shell").hidden=false; document.querySelector("#loginPage").hidden=true;')
            assert page.locator('#shell').is_visible()
            assert page.locator('#logoutButton').is_visible(),f'Sign out must be available at {width}px'
            assert page.locator('#mobileLogoutButton').count()==1
            assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+2'),f'Overflow {width}px'
            if width<=940:
                assert page.locator('#showSidebar').is_visible()
                page.evaluate('document.querySelector("#sidebar").classList.add("open")')
                assert page.locator('#mobileLogoutButton').is_visible()
                assert page.locator('#mainNav').get_by_text('الكاشير والتحصيل').count()==1
                assert page.locator('#mainNav').get_by_text('الحسابات والتقارير').count()==1
                page.evaluate('document.querySelector("#sidebar").classList.remove("open")')
            if width in (320,375,1365):
                page.screenshot(path=str(ROOT.parent/f'QA_G2I_SHELL_{width}.png'),full_page=True)
            if width==375:
                page.evaluate('document.querySelector("#shell").hidden=true; document.querySelector("#loginPage").hidden=false')
                assert page.locator('.login-test-note').is_visible()
                assert page.get_by_text('نسخة تجريبية وليست نظامًا ماليًا معتمدًا').is_visible()
                page.screenshot(path=str(ROOT.parent/'QA_G2I_LOGIN_375.png'),full_page=True)
            page.close()
            print('PASS G2I static shell:',width,'px, logout accessible, nav groups, no scroll overflow')
    finally:browser.close()
