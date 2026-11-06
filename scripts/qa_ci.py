#!/usr/bin/env python3
"""Public core CI: no private fixtures/secrets; external history remains explicit."""
import argparse
import json
import os
from pathlib import Path
import re
import signal

from qa_fallback import IMAGE, execute_checkout, invoke


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-dir',type=Path,required=True)
    parser.add_argument('--v80-archive',type=Path)
    parser.add_argument('--image',default=IMAGE)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    report=args.report_dir.resolve()
    if root==report or root in report.parents:parser.error('Reports must stay outside Git source')
    report.mkdir(parents=True,mode=0o700,exist_ok=True)
    def stop(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    result=execute_checkout(root,root,report,archive=args.v80_archive,
                            allow_missing_v80=not args.v80_archive,image_ref=args.image)
    result.update(sha=invoke(['git','-C',str(root),'rev-parse','HEAD']),
                  github_actions_used=os.environ.get('GITHUB_ACTIONS')=='true')
    (report/'run.json').write_text(json.dumps(result,indent=2)+'\n')
    public={k:result[k] for k in ('sha','status','counts','steps','image_id','gate_scope','production_certified')}
    public['historical_notice']='V8.0 original source is external; BLOCKED is not PASS. Five historical/private-workbook SKIPs remain explicit.'
    public['failed_tests']=[m.group(0) for p in result['problems']
                            if (m:=re.search(r'\btest_[A-Za-z0-9_]+\.py\b',p))]
    (report/'public-summary.json').write_text(json.dumps(public,indent=2)+'\n')
    summary=('## Ramses public core CI\n\n'
             f'SHA: `{result["sha"]}`\n\nStatus: **{result["status"].upper()}** (public core gate).\n\n'
             f'Counts: `{json.dumps(result["counts"],sort_keys=True)}`\n\n'
             +public['historical_notice']+'\n\nTEST ONLY / PRODUCTION NO-GO.\n')
    (report/'public-summary.md').write_text(summary)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as output:output.write(summary)
    print(summary)
    return 0 if result['status']=='success' else 1


if __name__=='__main__':raise SystemExit(main())
