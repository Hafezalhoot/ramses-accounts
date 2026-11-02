"""S1 operational acceptance, preserving distinct evidence grades.

The ASGI bridge runs production handlers and a temporary SQLite DB, but NOT real HTTP.
"""
import subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CASES=(
 ('BROWSER_MOCK_DATA','browser_s1_inventory_workspaces.py'),
 ('BROWSER_REAL_FASTAPI_SQLITE_NO_HTTP','browser_s1_inventory_asgi_sqlite.py'),
)

def main():
    failed=0
    for grade,script in CASES:
        try:
            result=subprocess.run([sys.executable,str(ROOT/'tests'/script)],cwd=ROOT,
                                  capture_output=True,text=True,timeout=100)
            output=result.stdout+'\n'+result.stderr
            ok=result.returncode==0 and 'PASS S1 ' in output
        except subprocess.TimeoutExpired:
            output='TIMEOUT';ok=False
        print(f'{"PASS" if ok else "FAIL"} | {grade} | {script}',flush=True)
        if not ok:print(output[-2000:],flush=True);failed+=1
    print('NOT_VERIFIED | REAL_NETWORK_BROWSER_HTTP | blocked by Chromium ERR_BLOCKED_BY_ADMINISTRATOR',flush=True)
    print('NOT_VERIFIED | HOSPITAL_24H_MULTI_ROLE_UAT | awaiting real environment and signoff',flush=True)
    return int(failed>0)

if __name__=='__main__':raise SystemExit(main())
