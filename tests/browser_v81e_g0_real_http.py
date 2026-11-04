"""Real FastAPI + Chromium smoke, using only disposable local data and loopback HTTP."""
from browser_helpers import chromium_options
from pathlib import Path
import os,sys,tempfile,subprocess,time,socket,urllib.request
ROOT=Path(__file__).resolve().parents[1]

def run():
 from playwright.sync_api import sync_playwright
 with tempfile.TemporaryDirectory() as tmp:
  env=os.environ.copy()
  env['RAMSES_DB_PATH']=str(Path(tmp)/'smoke.sqlite3')
  env['RAMSES_ADMIN_USER']='owner'
  env['RAMSES_ADMIN_PASSWORD']='local_browser_test_password_2026'
  env['RAMSES_ENVIRONMENT']='staging'
  env['PYTHONPATH']=str(ROOT)
  subprocess.run([sys.executable,'bootstrap.py'],cwd=ROOT,env=env,check=True,capture_output=True)
  # Test fixtures via SQLite directly; never touch the user's live database.
  from sqlite3 import connect
  c=connect(env['RAMSES_DB_PATH'])
  c.execute("INSERT INTO users(username,password_hash,role,created_at) SELECT 'auditor',password_hash,'reviewer',created_at FROM users WHERE role='owner'")
  c.commit();c.close()
  with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
  proc=subprocess.Popen([sys.executable,'-m','uvicorn','app:app','--host','127.0.0.1','--port',str(port),'--log-level','error'],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  try:
   base=f'http://127.0.0.1:{port}'
   for _ in range(55):
    try:
     with urllib.request.urlopen(base+'/health',timeout=1) as resp:
      if resp.status==200:break
    except Exception:time.sleep(.2)
   else:
    raise AssertionError('Local Uvicorn server failed to become ready: '+proc.communicate(timeout=4)[1].decode()[-700:])
   with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,**chromium_options(),args=['--no-sandbox','--disable-dev-shm-usage'])
    try:
     page=browser.new_page(viewport={'width':1200,'height':850})
     errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     page.goto(base+'/',wait_until='domcontentloaded')
     page.locator('#loginForm input[name=username]').fill('owner')
     page.locator('#loginForm input[name=password]').fill(env['RAMSES_ADMIN_PASSWORD'])
     page.locator('#loginForm button[type=submit]').click()
     page.wait_for_selector('#shell:not([hidden])',timeout=15000)
     page.locator('[data-view=admin]').click()
     page.wait_for_selector('[data-user-fund]',timeout=15000)
     page.locator('[data-user-fund]').first.click()
     page.wait_for_selector('#modalFields select[name=permission]',timeout=10000)
     page.locator('#modalFields select[name=permission]').select_option('can_approve')
     page.locator('#modalFields select[name=allowed]').select_option('true')
     page.locator('#modalFields input[name=reason]').fill('Real HTTP integration test for reviewer bank approval')
     page.locator('#modalConfirm').click()
     page.wait_for_function('!document.querySelector("#modal").open',timeout=10000)
     assert not errors,errors
     c=connect(env['RAMSES_DB_PATH']); row=c.execute("SELECT can_approve FROM user_fund_grants WHERE user_id=(SELECT id FROM users WHERE username='auditor')").fetchone();c.close()
     assert row and row[0]==1,'Reviewer bank grant did not persist through real browser POST'
     page.screenshot(path=str(ROOT.parent/'QA_V81E_G0_ADMIN_HTTP_DESKTOP.png'),full_page=True)
     print('PASS REAL Chromium + Uvicorn: owner login, admin page, reviewer bank grant form and persistent server write; no JS page errors')
    finally:browser.close()
  finally:
   proc.terminate()
   try:proc.communicate(timeout=6)
   except subprocess.TimeoutExpired:proc.kill();proc.communicate()
if __name__=='__main__':run()
