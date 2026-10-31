"""Visual smoke test: owner administration controls and mobile responsive layout."""
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def run():
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory() as d:
        env=os.environ.copy()
        env.update({
            'RAMSES_DB_PATH':str(Path(d)/'test.sqlite3'),
            'RAMSES_ADMIN_USER':'owner',
            'RAMSES_ADMIN_PASSWORD':'test_very_long_password_admin',
            'RAMSES_ENVIRONMENT':'staging',
            'RAMSES_SECURE_COOKIES':'0',
        })
        env.pop('GOOGLE_SHEET_ID',None)
        env.pop('GOOGLE_SERVICE_ACCOUNT_JSON',None)
        subprocess.run([sys.executable,'-c','from bootstrap import initialize; initialize()'],cwd=ROOT,env=env,check=True,capture_output=True)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        proc=subprocess.Popen([sys.executable,'-m','uvicorn','app:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            for _ in range(40):
                if proc.poll() is not None: raise RuntimeError('server exited unexpectedly')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=1) as resp:
                        if resp.status==200:break
                except Exception:time.sleep(0.25)
            else:raise RuntimeError('local server failed health')
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
                try:
                    page=browser.new_page(viewport={'width':1280,'height':800},device_scale_factor=1)
                    errors=[];page.on('pageerror',lambda x:errors.append(str(x)))
                    page.goto(f'http://127.0.0.1:{port}',wait_until='domcontentloaded')
                    page.locator('input[name=username]').fill('owner')
                    page.locator('input[name=password]').fill('test_very_long_password_admin')
                    page.locator('#loginForm button[type=submit]').click()
                    page.wait_for_selector('#shell:not([hidden])',timeout=5000)
                    page.locator('#mainNav [data-view=admin]').click()
                    page.wait_for_selector('#newUser',timeout=5000)
                    page.locator('#newUser').click()
                    page.locator('#modal [name=username]').fill('stafftester')
                    page.locator('#modal [name=password]').fill('staff_password_123456')
                    page.locator('#modal [name=role]').select_option('clerk')
                    page.locator('#modalForm button[type=submit]').click()
                    page.wait_for_selector('[data-user-name=stafftester][data-user-toggle]',timeout=5000)
                    page.locator('[data-user-name=stafftester][data-user-toggle]').click()
                    page.locator('#modal [name=confirm]').select_option('yes')
                    page.locator('#modalForm button[type=submit]').click()
                    page.wait_for_selector('[data-user-name=stafftester][data-new-status="1"]',timeout=5000)
                    page.locator('[data-user-name=stafftester][data-user-password]').click()
                    page.locator('#modal [name=current_password]').fill('test_very_long_password_admin')
                    page.locator('#modal [name=password]').fill('changed_staff_password_12')
                    page.locator('#modal [name=confirm_password]').fill('changed_staff_password_12')
                    page.locator('#modalForm button[type=submit]').click()
                    page.wait_for_timeout(250)
                    assert not errors,errors
                    assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1')
                    page.set_viewport_size({'width':390,'height':844})
                    page.wait_for_timeout(350)
                    assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1')
                    print('PASS - browser admin create, disable, rotate password, desktop and mobile overflow')
                finally:browser.close()
        finally:
            proc.terminate()
            try:proc.wait(timeout=3)
            except subprocess.TimeoutExpired:proc.kill()


if __name__=='__main__':run()
