"""Independent per-test process suite, records SKIP/BLOCKED separately from PASS."""
import csv,os,subprocess,sys,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
files=sorted((ROOT/'tests').glob('test_*.py'))
ENV=os.environ.copy()
for key in ('GOOGLE_SHEET_ID','GOOGLE_SERVICE_ACCOUNT_JSON','GOOGLE_SHEET_TARGET','RAMSES_DB_PATH'):
 ENV.pop(key,None)

def one(path):
 started=time.monotonic()
 try:
  result=subprocess.run([sys.executable,str(path)],env=ENV,cwd=ROOT,text=True,capture_output=True,timeout=110)
  output=(result.stdout+'\n'+result.stderr).strip()
  if result.returncode==0:
   status='SKIP' if ('SKIP ' in output or '\nSKIP' in output) else 'PASS'
  elif path.name=='test_billing_upgrade_v81.py' and 'Ramses_Accounts_V8_0' in output:
   status='BLOCKED_NO_V80'
  else:status='FAIL'
 except subprocess.TimeoutExpired as e:
  status='TIMEOUT';output=str(e)
 return path.name,status,round(time.monotonic()-started,2),output[-6000:]


def main():
 rows=[]
 with ThreadPoolExecutor(max_workers=5) as executor:
  futures=[executor.submit(one,f) for f in files]
  for f in as_completed(futures):
   name,status,duration,output=f.result()
   rows.append((name,status,duration,output))
   print(f'{status:16s} {name} ({duration:.1f}s)',flush=True)
   if status in ('FAIL','TIMEOUT'):
    print('FAIL DETAIL:',output[-1900:],flush=True)
 rows.sort()
 with (ROOT/'QA_G2T_TEST_RESULTS.tsv').open('w',newline='',encoding='utf-8') as report:
  w=csv.writer(report,delimiter='\t');w.writerow(('name','status','seconds','last_output'))
  w.writerows(rows)
 counts={s:sum(1 for x in rows if x[1]==s) for s in sorted({r[1] for r in rows})}
 print('SUMMARY',counts,'TOTAL',len(files),flush=True)
 return 1 if any(r[1] in ('FAIL','TIMEOUT') for r in rows) else 0

if __name__=='__main__':raise SystemExit(main())
