#!/usr/bin/env python3
"""Exact-SHA merge helper requiring current Actions checks and strict server rules."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from qa_fallback import REPO, STATUS_CONTEXT, invoke, validate_pr, approved_authors


def preflight(pr: dict, status: dict, comparison: dict, authors: set[str], *, check_runs=None) -> str:
    sha = validate_pr(pr, authors)
    if (pr.get('draft') is not False or pr.get('mergeable') is not True
            or (pr.get('base') or {}).get('ref') != 'main'):
        raise ValueError('PR must be ready, mergeable, and target main')
    if comparison.get('status') != 'ahead':
        raise ValueError('PR head must contain the current main tip; update/retest first')
    if check_runs is not None:
        for name in ('ramses-core-ci', 'ramses-security'):
            values=[c for c in check_runs if c.get('name')==name]
            latest=max(values,key=lambda c:c.get('id',0),default={})
            if (latest.get('head_sha')!=sha or (latest.get('app') or {}).get('id')!=15368
                    or latest.get('status')!='completed' or latest.get('conclusion')!='success'):
                raise ValueError('Latest GitHub Actions check is not successful for exact SHA: '+name)
        return sha
    if status.get('sha') != sha or status.get('state') != 'success':
        raise ValueError('Commit status is not SUCCESS for the exact PR SHA')
    matches = [v for v in status.get('statuses', [])
               if v.get('context') == STATUS_CONTEXT]
    if not matches or matches[0].get('state') != 'success':
        raise ValueError('Verified QA context is not successful on this SHA')
    description = matches[0].get('description') or ''
    if ('SUCCESS' not in description or 'PASS' not in description
            or not re.search(r'\b0 BLOCKED\b', description)):
        raise ValueError('QA status is missing credible non-blocked summary')
    if comparison.get('status') != 'ahead':
        raise ValueError('PR head must contain the current main tip; update/retest first')
    return sha


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--pr', type=int, required=True)
    ap.add_argument('--merge', action='store_true', help='Explicitly merge only after all checks')
    args = ap.parse_args()
    if args.pr < 1:
        ap.error('Invalid PR number')
    root = Path(__file__).resolve().parents[1]
    if invoke(['git', '-C', str(root), 'branch', '--show-current']) != 'main':
        ap.error('Run the checked merge helper from reviewed main')
    if invoke(['git', '-C', str(root), 'status', '--porcelain']):
        ap.error('Trusted main must have a clean working tree')
    authors_path = root / 'tools' / 'qa' / 'trusted_pr_authors.txt'
    authors = {s.strip() for s in authors_path.read_text(encoding='utf-8').splitlines()
               if s.strip() and not s.startswith('#')}

    def current():
        pr = json.loads(invoke(['gh', 'api', f'repos/{REPO}/pulls/{args.pr}'], timeout=60))
        allowed = approved_authors(pr, authors)
        sha = validate_pr(pr, allowed)
        main_head = json.loads(invoke(['gh', 'api', f'repos/{REPO}/branches/main'], timeout=60))['commit']['sha']
        if pr['base']['sha'] != main_head:
            raise ValueError('Base SHA does not match current GitHub main; re-evaluate PR')
        status = json.loads(invoke(['gh', 'api', f'repos/{REPO}/commits/{sha}/status'], timeout=60))
        comparison = json.loads(invoke(['gh', 'api', f'repos/{REPO}/compare/{main_head}...{sha}'], timeout=60))
        checks=json.loads(invoke(['gh','api',f'repos/{REPO}/commits/{sha}/check-runs?per_page=100'],timeout=60))
        return preflight(pr, status, comparison, allowed,check_runs=checks.get('check_runs',[]))

    head_sha = current()
    if not args.merge:
        print(f'PRECHECK PASS: PR #{args.pr} at {head_sha}; rerun with --merge to act')
        return 0
    if current() != head_sha:
        raise ValueError('PR SHA moved during preflight')
    result = json.loads(invoke(['gh', 'api', '-X', 'PUT', f'repos/{REPO}/pulls/{args.pr}/merge',
                                '-f', f'sha={head_sha}', '-f', 'merge_method=merge'], timeout=90))
    if not result.get('merged'):
        raise RuntimeError('GitHub refused merge; no direct push attempted')
    print(f'MERGED: PR #{args.pr}, merge commit {result.get("sha")}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
