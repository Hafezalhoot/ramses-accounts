"""Manually verify the protected synthetic preview through real HTTPS/Chromium.

Secrets stay in ignored local files. This is not a hospital production probe.
"""
import argparse
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-dir',type=Path,default=ROOT/'private/external-preview-check')
    args=parser.parse_args()
    from browser_helpers import chromium_options
    from playwright.sync_api import sync_playwright
    state=json.loads((ROOT/'private/mobile-gateway/processes.json').read_text())
    gate=json.loads((ROOT/'private/mobile-gateway/access.json').read_text())
    config={}
    for line in (ROOT/'.env').read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k,v=line.split('=',1);config[k]=v
    url=state['url']
    parsed=urlsplit(url)
    if parsed.scheme!='https' or not (parsed.hostname or '').endswith('.trycloudflare.com') or parsed.username:
        raise ValueError('Only the explicitly configured HTTPS test tunnel is permitted')
    args.evidence_dir.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,**chromium_options())
        try:
            for width in (375,1440):
                context=browser.new_context(viewport={'width':width,'height':900},
                    http_credentials={'username':gate['username'],'password':gate['password'],
                                      'origin':f'{parsed.scheme}://{parsed.netloc}'})
                try:
                    page=context.new_page();errors=[]
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(url,wait_until='networkidle',timeout=45000)
                    page.locator('#loginForm [name=username]').fill(config['RAMSES_ADMIN_USER'])
                    page.locator('#loginForm [name=password]').fill(config['RAMSES_ADMIN_PASSWORD'])
                    page.locator('#loginForm button[type=submit]').click()
                    page.locator('#shell').wait_for(state='visible',timeout=20000)
                    assert page.evaluate("async()=> (await (await fetch('/api/me')).json()).environment")=='free-preview'
                    assert page.evaluate('document.documentElement.dir')=='rtl'
                    page.evaluate('document.fonts.ready')
                    assert page.evaluate("Array.from(document.fonts).some(f=>f.family.includes('Cairo') && f.status==='loaded')")
                    page.reload(wait_until='networkidle')
                    page.locator('#shell').wait_for(state='visible')
                    page.wait_for_timeout(6500)
                    assert page.evaluate("async()=> (await fetch('/api/me')).status")==200
                    assert any(c['name']=='ramses_sid' and c['secure'] and c['httpOnly'] for c in context.cookies())
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    assert not errors,errors
                    page.screenshot(path=str(args.evidence_dir/f'external-preview-{width}.png'),full_page=True)
                    print(f'PASS external HTTPS Chrome {width}: protected gateway, application login/reload/session200, Secure cookie, RTL/Cairo, no overflow/JS errors',flush=True)
                finally:
                    context.close()
        finally:
            browser.close()


if __name__=='__main__':
    main()
