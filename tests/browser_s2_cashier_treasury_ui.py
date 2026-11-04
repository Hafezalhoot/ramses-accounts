"""S2 synthetic cashier UI -> authentic FastAPI TestClient -> SQLite.

Only the browser-to-ASGI transport is bridged (loopback HTTP unavailable here).
Neither real API handlers nor SQLite accounting results are mocked.
"""
from browser_helpers import chromium_options
import re
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def verify_cashier_ui(app, source_shift_id, connect):
    with sync_playwright() as pw:
        for width, amount in ((375, '30'), (1440, '20')):
            session = TestClient(app)
            browser = pw.chromium.launch(headless=True, **chromium_options(),
                args=['--no-sandbox', '--disable-dev-shm-usage'])
            try:
                page = browser.new_page(viewport={'width': width, 'height': 850})
                errors = []
                calls = []
                page.on('pageerror', lambda error: errors.append(str(error)))

                def forward(_source, info):
                    path = info['path']
                    assert path.startswith('/api/'), path
                    method = info.get('method', 'GET')
                    data = info.get('body')
                    r = session.request(method, path, headers=info.get('headers') or {},
                                        content=data.encode() if isinstance(data, str) else None)
                    calls.append((method, path, r.status_code))
                    return {'status': r.status_code, 'text': r.text,
                            'content_type': r.headers.get('content-type', 'application/json')}
                page.expose_binding('__s2_asgi', forward)
                html = (ROOT / 'static/index.html').read_text(encoding='utf8')
                html = re.sub(r'<script src="/static/[^\"]+" defer></script>', '', html)
                html = html.replace('<link rel="stylesheet" href="/static/styles.css">', '')
                page.set_content(html)
                page.add_style_tag(content=(ROOT / 'static/styles.css').read_text(encoding='utf8'))
                page.add_script_tag(content='''
                  window.fetch=async (path,opts={})=>{
                    const data=await window.__s2_asgi({path:String(path),method:opts.method||'GET',
                      headers:opts.headers||{},body:typeof opts.body==='string'?opts.body:null});
                    return new Response(data.text,{status:data.status,
                      headers:{'content-type':data.content_type}});
                  };
                ''')
                for js in ('inventory_ui.js', 'billing.js', 'pos_settlements_ui.js',
                           'cashier_ops_ui.js', 'financial_corrections_ui.js',
                           'late_entry_ui.js', 'app.js'):
                    page.add_script_tag(content=(ROOT / 'static' / js).read_text(encoding='utf8'))
                page.locator('#loginForm [name="username"]').fill('receiver')
                page.locator('#loginForm [name="password"]').fill('synthetic_s2_retry_staff_password')
                page.locator('#loginForm button[type="submit"]').click()
                page.locator('#shell').wait_for(state='visible', timeout=15000)
                if width < 940:
                    page.locator('#showSidebar').click()
                    page.locator('#sidebar.open [data-view="shifts"]').click()
                else:
                    page.locator('#mainNav [data-view="shifts"]').click()
                page.locator('#content .info-box').filter(has_text='مواعيد الورديات قابلة للتغيير').wait_for(timeout=12000)
                assert 'undefined' not in page.locator('#content').inner_text(), 'A shift label or start/end clock was rendered as undefined'
                action = page.locator(f'[data-shift-action="treasury-deposit"][data-shift-id="{source_shift_id}"]:visible')
                action.wait_for(timeout=8000)
                action.click()
                page.locator('#modalFields [name="amount"]').fill(amount)
                page.locator('#modalFields [name="note"]').fill(f'S2 sealed treasury envelope desktop {width}')
                page.locator('#modalConfirm').click()
                page.locator('#toast').get_by_text('تم إثبات التوريدة').wait_for(timeout=15000)
                assert ('POST', '/api/cashier/treasury-deposits', 200) in calls, calls[-15:]
                with connect() as c:
                    assert c.execute('SELECT COUNT(*) FROM cashier_treasury_transfers WHERE source_shift_id=?',
                                     (source_shift_id,)).fetchone()[0] == (2 if width == 375 else 3)
                assert not errors, errors
                no_overflow = page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1')
                assert no_overflow, width
                screenshot = ROOT.parent / 's2_browser_evidence' / f'cashier_treasury_{width}.png'
                screenshot.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshot), full_page=False)
                print(f'PASS S2 browser {width}px: cashier receive -> real ASGI -> SQLite, no UI errors/overflow', flush=True)
            finally:
                browser.close()


if __name__ == '__main__':
    from test_s2_treasury_retry import run
    run(browser_verify=verify_cashier_ui)
