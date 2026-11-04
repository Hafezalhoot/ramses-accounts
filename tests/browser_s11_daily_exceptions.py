"""Chromium -> real ASGI handlers -> synthetic SQLite, desktop/mobile + Cairo.

Browser requests are fulfilled by TestClient, not network HTTP or TLS.
"""
from pathlib import Path
from urllib.parse import urlsplit

from browser_helpers import chromium_options

ROOT = Path(__file__).resolve().parents[1]


def verify(app, day, report, connect):
    from fastapi.testclient import TestClient
    from playwright.sync_api import sync_playwright
    evidence = ROOT/'docs/project-autopilot/evidence/S11'
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, **chromium_options())
        try:
            for width in (375, 1440):
                session = TestClient(app)
                page = browser.new_page(viewport={'width':width,'height':900})
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                def forward(route):
                    request = route.request
                    parsed = urlsplit(request.url)
                    path = parsed.path+('?' + parsed.query if parsed.query else '')
                    response = session.request(request.method, path,
                        headers={k:v for k,v in request.headers.items() if k.lower() not in ('host','cookie')},
                        content=request.post_data_buffer)
                    route.fulfill(status=response.status_code, body=response.content,
                                  headers={'content-type':response.headers.get('content-type','text/plain')})
                page.route('http://ramses.test/**', forward)
                page.goto('http://ramses.test/')
                page.wait_for_load_state('networkidle')
                page.locator('#loginForm [name=username]').fill('s11_owner')
                page.locator('#loginForm [name=password]').fill('synthetic_s11_owner_password_long')
                page.locator('#loginForm button[type=submit]').click()
                page.locator('#shell').wait_for(state='visible')
                if width < 940:
                    page.locator('#showSidebar').click()
                page.locator('#mainNav [data-view=shifts]').click()
                page.locator('#cashierDaySummary').click()
                page.locator('#modalFields [name=business_date]').fill(day)
                page.locator('#modalConfirm').click()
                page.locator('#cashierDayExceptions').wait_for()
                text = page.locator('#modalText').inner_text()
                assert 'وردية غير مسجلة إلكترونيًا' in text, text
                assert 'بانتظار المراجعة' in text, text
                assert 'ليس اعتمادًا ماليًا' in text, text
                assert page.locator('#cashierDayExceptions tbody tr').count() == 3
                assert page.locator('#cashierDayExceptions tbody').get_by_text('الكاشير الخارجي').count() == 2
                if width < 700:
                    cards = page.locator('#cashierDayExceptions .daily-exception-card:visible')
                    assert cards.count() == 3, 'Every daily exception needs a readable mobile card'
                    assert 'استكمل المراجعة المستقلة' in cards.first.inner_text()
                    assert cards.first.evaluate('(el)=>el.scrollWidth <= el.clientWidth+1')
                assert page.evaluate('document.documentElement.dir') == 'rtl'
                page.evaluate('document.fonts.ready')
                assert page.evaluate("Array.from(document.fonts).some(f=>f.family.includes('Cairo') && f.status==='loaded')")
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                assert page.locator('#modal').evaluate('(el)=>el.scrollWidth <= el.clientWidth+1')
                assert not errors, errors
                page.screenshot(path=str(evidence/f'daily-exceptions-{width}.png'), full_page=True)
                page.close()
                print(f'PASS Chromium S11 {width}px: daily missing/review details, non-certificate notice, RTL, loaded Cairo, no overflow/errors')
        finally:
            browser.close()


if __name__ == '__main__':
    from test_s11_daily_exceptions import run
    run(browser_verify=verify)
