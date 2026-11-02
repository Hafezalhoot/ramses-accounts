"""S5: anonymous-free, synthetic-only stress probe for cashier assignment HTTP 500.

Starts a real Uvicorn worker with a disposable SQLite file. Each worker has
its own requests.Session and the server log is retained on failure. No
hospital data or server deployment is used.
"""
import concurrent.futures
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def available_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def run():
    with tempfile.TemporaryDirectory(prefix='ramses-s5-http-') as d:
        db_path = Path(d) / 's5.sqlite3'
        env = {**os.environ,
               'RAMSES_DB_PATH': str(db_path),
               'RAMSES_ADMIN_USER': 'owner',
               'RAMSES_ADMIN_PASSWORD': 's5_test_owner_local_password',
               'RAMSES_ENVIRONMENT': 'staging',
               'RAMSES_SECURE_COOKIES': '0'}
        for k in ('GOOGLE_SERVICE_ACCOUNT_JSON','GOOGLE_SHEET_ID','GOOGLE_SHEET_TARGET'):
            env.pop(k, None)
        os.environ.update({k: v for k, v in env.items() if k.startswith('RAMSES_')})
        from bootstrap import initialize, connect
        initialize()
        url = f'http://127.0.0.1:{available_port()}'
        trace = Path(d) / 'uvicorn-stderr.log'
        with trace.open('w+', encoding='utf-8') as stream:
            server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app:app',
                                      '--host','127.0.0.1','--port',url.rsplit(':',1)[-1],
                                      '--log-level','error','--no-access-log'],
                                      cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
            try:
                owner = requests.Session()
                owner.trust_env = False
                for _ in range(100):
                    if server.poll() is not None:
                        raise RuntimeError('Uvicorn terminated before readiness')
                    try:
                        if owner.get(url + '/health', timeout=.6).status_code == 200:
                            break
                    except requests.RequestException:
                        pass
                    time.sleep(.1)
                else:
                    raise AssertionError('Uvicorn not ready')
                login = owner.post(url + '/api/login', json={
                    'username':'owner', 'password':'s5_test_owner_local_password'},timeout=15)
                assert login.status_code == 200, (login.status_code,login.text[:200])
                csrf = login.json()['csrf']
                headers = {'X-CSRF-Token': csrf}
                staff = []
                for i in range(12):
                    res = owner.post(url + '/api/users', headers=headers, json={
                        'username':f's5_staff_{i}', 'role':'clerk',
                        'password':'s5_test_staff_local_password'},timeout=15)
                    assert res.status_code == 200, (res.status_code, res.text[:200])
                staff = [row['id'] for row in owner.get(url+'/api/users',timeout=15).json()
                         if row['username'].startswith('s5_staff_')]
                points = owner.get(url+'/api/cashier/plans', timeout=15).json()['points']
                point_id = next(row['id'] for row in points if row['kind']=='external')
                assert len(staff) == 12
                local = threading.local()
                results = []

                def make_request(task_id):
                    if not hasattr(local, 'session'):
                        local.session = requests.Session()
                        local.session.trust_env = False
                        local.session.cookies.update(owner.cookies.get_dict())
                    staff_id = staff[task_id % len(staff)]
                    start = time.monotonic()
                    try:
                        response = local.session.post(
                            url+f'/api/billing/points/{point_id}/assign',
                            headers=headers, json={'user_id':staff_id,'active':True},
                            timeout=35)
                        return (response.status_code,round(time.monotonic()-start,3),
                                response.text[:120] if response.status_code!=200 else '')
                    except Exception as exc:
                        return ('network:'+type(exc).__name__,round(time.monotonic()-start,3),'')

                total = int(os.getenv('S5_STRESS_REQUESTS','240'))
                workers = int(os.getenv('S5_STRESS_WORKERS','24'))
                with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
                    results=list(ex.map(make_request, range(total)))
                status_counts = {}
                for status,_,_ in results:
                    status_counts[str(status)] = status_counts.get(str(status),0)+1
                times = sorted(x[1] for x in results)
                with connect() as c:
                    active = c.execute('SELECT COUNT(*) FROM billing_point_access WHERE point_id=? AND active=1 AND user_id IN ('+
                                       ','.join('?' * len(staff))+')', [point_id,*staff]).fetchone()[0]
                    audits = c.execute("SELECT COUNT(*) FROM audit_log WHERE action='billing_point_access'").fetchone()[0]
                    check = c.execute('PRAGMA integrity_check').fetchone()[0]
                    fk = c.execute('PRAGMA foreign_key_check').fetchall()
                    lock_wait_ms = c.execute('PRAGMA busy_timeout').fetchone()[0]
                # A cashier must not inherit owner-only point administration.
                clerk = requests.Session()
                clerk.trust_env = False
                clerk_login = clerk.post(url+'/api/login', json={
                    'username':'s5_staff_0', 'password':'s5_test_staff_local_password'},timeout=15)
                assert clerk_login.status_code == 200
                denied = clerk.post(url+f'/api/billing/points/{point_id}/assign',
                                    headers={'X-CSRF-Token':clerk_login.json()['csrf']},
                                    json={'user_id':staff[-1],'active':False},timeout=15)
                assert denied.status_code == 403, denied.status_code
                with connect() as c:
                    after_denied = c.execute(
                        "SELECT COUNT(*) FROM audit_log WHERE action='billing_point_access'").fetchone()[0]
                assert after_denied == audits
                print('S5_CONCURRENT_HTTP '+json.dumps({
                    'workers':workers,'requests':total,'statuses':status_counts,
                    'p50_seconds':times[len(times)//2],
                    'p95_seconds':times[min(len(times)-1,int(len(times)*.95))],
                    'worst_seconds':times[-1],
                    'active_assignments':active,'audit_entries':audits,
                    'sqlite_integrity':check,'foreign_key_violations':len(fk),
                    'sqlite_busy_timeout_ms':lock_wait_ms, 'unauthorized_assignment_status':denied.status_code
                },sort_keys=True),flush=True)
                assert status_counts == {'200':total}, [x for x in results if x[0]!=200][:6]
                assert active==len(staff) and audits==total and check=='ok' and not fk
                assert lock_wait_ms==30000
                print('PASS S5 cashier HTTP contention: all committed and independently reconcilable',flush=True)
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=10)
                stream.flush()
                trace_text=trace.read_text(encoding='utf-8')
                if trace_text:
                    print('S5_SERVER_TRACE_BEGIN\n'+trace_text[-9000:]+'\nS5_SERVER_TRACE_END',flush=True)


if __name__=='__main__':
    run()
