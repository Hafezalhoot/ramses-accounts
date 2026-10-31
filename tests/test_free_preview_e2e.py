"""Real localhost HTTP + protected mirror request test using dummy data only."""
from __future__ import annotations
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'scripts'/'free_preview.py'
sys.path.insert(0,str(ROOT))

class Reply:
    content=b'{}'
    def __init__(self, body): self.body=body
    def raise_for_status(self): pass
    def json(self): return self.body

class FakeMirror:
    def __init__(self): self.calls=[]
    def request(self, method, url, **kwargs):
        self.calls.append((method,url,kwargs))
        if method=='GET':
            from google_sync import TABS, PREVIEW_STAGING_SHEET_ID
            return Reply({'spreadsheetId':PREVIEW_STAGING_SHEET_ID,'sheets':[
                {'properties':{'sheetId':100+i,'title':name,
                               'gridProperties':{'rowCount':1000,'columnCount':26}}}
                for i,name in enumerate(TABS)]})
        return Reply({'replies':[{}]*len(kwargs['json']['requests'])})


def run():
    # The real server starts in an isolated copied folder, not the source tree.
    with tempfile.TemporaryDirectory() as temp:
        p=Path(temp)/'ramses_accounts';p.mkdir()
        for f in (*[item.name for item in ROOT.glob('*.py')], 'schema.sql'):
            shutil.copy2(ROOT/f,p/f)
        shutil.copytree(ROOT/'scripts',p/'scripts',ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(ROOT/'static',p/'static',ignore=shutil.ignore_patterns('__pycache__'))
        # Demo setup must not require imported or real financial files.
        (p/'imports').mkdir()
        env=os.environ.copy()
        env.pop('GOOGLE_SHEET_ID',None);env.pop('GOOGLE_SERVICE_ACCOUNT_JSON',None)
        with socket.socket() as port_test:
            port_test.bind(('127.0.0.1',0))
            port = port_test.getsockname()[1]
        proc=subprocess.Popen([sys.executable,str(p/'scripts'/'free_preview.py'),
                              '--local-only','--demo','--port',str(port)],cwd=p,
                              env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                              text=True)
        try:
            def fetch(path,**kwargs):
                rq=urllib.request.Request(f'http://127.0.0.1:{port}'+path,**kwargs)
                try:
                    with urllib.request.urlopen(rq,timeout=2) as r:
                        return (r.status,r.read(),r.headers)
                except urllib.error.HTTPError as e:
                    return (e.code,e.read(),e.headers)
            # Readiness is condition-based; under concurrent test load, ASGI
            # bootstrap can take longer than the former 120 short polls.
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise AssertionError('Preview exited early with code: '+str(proc.returncode)+'\n'+proc.stdout.read()[-2400:])
                try:
                    status,content,headers=fetch('/health')
                    if status==200:
                        break
                except (OSError,TimeoutError):
                    time.sleep(0.1)
            else:
                raise AssertionError('Real HTTP preview did not start within 35 seconds')
            assert b'"status":"ok"' in content and b'G3E' in content, (
                'Preview responded from an unexpected application', content[:220])
            status, body, _ = fetch('/api/vouchers')
            assert status == 401, ('Unauthenticated voucher HTTP status', status, body[:220])
            status, body, _ = fetch('/api/sync-status')
            assert status == 401, ('Unauthenticated sync HTTP status', status, body[:220])
            assert 'nosniff'==headers.get('X-Content-Type-Options')
            assert fetch('/static/app.js')[0]==200
            db=p/'data'/'free-preview.sqlite3'
            assert db.is_file()
            with sqlite3.connect(db) as c:
                assert c.execute('SELECT count(*) FROM vouchers').fetchone()[0]==3
                assert c.execute("SELECT count(*) FROM vouchers WHERE status='approved'").fetchone()[0]==3
                assert c.execute('SELECT count(*) FROM legacy_entries').fetchone()[0]==0
                assert c.execute('SELECT count(*) FROM fund_movements').fetchone()[0]==4
            # Mock just the network layer; the app must create a full 5-tab snapshot.
            import google_sync
            fake=FakeMirror()
            before=dict(os.environ)
            try:
                os.environ['RAMSES_ENVIRONMENT']='free-preview'
                os.environ['GOOGLE_SHEET_ID']=google_sync.PREVIEW_STAGING_SHEET_ID
                with sqlite3.connect(db) as c:
                    c.row_factory=sqlite3.Row
                    with patch.object(google_sync,'get_session',return_value=fake):
                        counts=google_sync.sync_to_google(c)
                assert counts['Ramses_Vouchers']==3
                assert counts['Ramses_Funds']==4
                assert counts['Ramses_Audit']>=3
                assert [method for method,_,_ in fake.calls]==['GET','POST']
                assert fake.calls[1][1].startswith('https://sheets.googleapis.com/v4/spreadsheets/'+google_sync.PREVIEW_STAGING_SHEET_ID)
                reqs=fake.calls[1][2]['json']['requests']
                assert sum('updateCells' in r for r in reqs)==5
                assert all('clear' not in str(r).lower() for r in reqs)
                try:
                    os.environ['GOOGLE_SHEET_ID']='1SJXFAvZ1BBpn9rQDccplpu5tL0yVFGJ1KOeyxDD0Kys'
                    with patch.object(google_sync,'get_session',return_value=fake):
                        with sqlite3.connect(db) as c:
                            google_sync.sync_to_google(c)
                    raise AssertionError('Original ledger must not be a mirror target')
                except ValueError:
                    pass
            finally:
                os.environ.clear();os.environ.update(before)
        finally:
            proc.terminate()
            try:
                output,_=proc.communicate(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill();output,_=proc.communicate(timeout=8)
        assert proc.returncode is not None
        assert 'Traceback' not in output, output[-2000:]
        sys.path.insert(0,str(p/'scripts'))
        from preview_doctor import run as diagnostic
        ok,messages=diagnostic(root=p)
        assert ok, messages
    print('PASS - real preview HTTP, fabricated approved vouchers, private API, 5-tab mock Google snapshot, staging allowlist and diagnostics')

if __name__=='__main__':run()
