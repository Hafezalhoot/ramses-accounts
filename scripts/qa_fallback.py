#!/usr/bin/env python3
"""Trusted-main, Docker-isolated fallback for GitHub PR synthetic QA (no Actions)."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

REPO = 'Hafezalhoot/ramses-accounts'
STATUS_CONTEXT = 'ramses/mac-local-qa'  # Existing check; also served by trusted fallback.
IMAGE = 'ramses-qa-fallback:v1'
MIN_SCRIPTS = 159
SKIP_REASONS = {
    'test_free_preview.py': 'private June historical workbook intentionally excluded',
    'test_preview_modes.py': 'private June historical workbook intentionally excluded',
    'test_v81e_g2j_schema_upgrade.py': 'original preceding source checkout unavailable',
    'test_v81e_g2k_upgrade.py': 'G2J source checkout not packaged',
    'test_v81e_g2l_schema_upgrade.py': 'G2K source checkout not available',
}
BLOCKED_ENV = ('RAMSES_DB_PATH', 'GOOGLE_SHEET_ID', 'GOOGLE_SERVICE_ACCOUNT_JSON',
               'GOOGLE_SHEET_TARGET')


def validate_pr(data: dict, allowed_authors: set[str]) -> str:
    head = data.get('head') or {}
    sha = head.get('sha')
    if (data.get('state') != 'open'
            or (head.get('repo') or {}).get('full_name') != REPO
            or (data.get('user') or {}).get('login') not in allowed_authors
            or not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{40}', sha)):
        raise ValueError('PR must be open, from the same repository, and authored by an approved account')
    return sha


def reject_tracked_paths(paths: list[str]) -> bool:
    for raw in paths:
        p = Path(raw)
        if (raw.startswith('.env') and raw != '.env.example'
                or p.name.lower().endswith(('.db', '.sqlite', '.sqlite3', '.pem', '.p12', '.rbe'))
                or p.parts and p.parts[0] in {'private', 'secrets', 'backups', 'data'}):
            return True
    return False


def docker_command(checkout: str | Path, command: list[str], archive: Path | None = None) -> list[str]:
    cmd = ['docker', 'run', '--rm', '--init', '--network', 'none', '--read-only',
           '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
           '--pids-limit', '256', '--memory', '4g', '--cpus', '3', '--shm-size', '256m',
           '--tmpfs', '/tmp:rw,nosuid,size=512m',
           '--user', f'{os.getuid()}:{os.getgid()}',
           '--mount', f'type=bind,src={Path(checkout).resolve()},dst=/work',
           '--workdir', '/work', '-e', 'CI=true', '-e', 'HOME=/tmp',
           '-e', 'PYTHONUNBUFFERED=1', '-e', 'PYTHONDONTWRITEBYTECODE=1']
    if archive:
        cmd.extend(['--mount', f'type=bind,src={archive.resolve()},dst=/fixtures/v80.zip,readonly',
                    '-e', 'RAMSES_V80_ARCHIVE=/fixtures/v80.zip'])
    return cmd + [IMAGE] + command


def audit_results(tsv: Path, tests: Path, min_scripts: int = MIN_SCRIPTS) -> dict:
    expected = {p.name for p in tests.glob('test_*.py')}
    counts = {key: 0 for key in ('PASS', 'SKIP', 'FAIL', 'TIMEOUT', 'BLOCKED_NO_V80')}
    problems: list[str] = []
    if len(expected) < min_scripts:
        problems.append('Test inventory is smaller than expected baseline')
    try:
        with tsv.open(encoding='utf-8', newline='') as fh:
            rows = list(csv.DictReader(fh, delimiter='\t'))
    except (OSError, UnicodeError, csv.Error):
        return {'ok': False, 'counts': counts, 'problems': ['Missing or unreadable test report']}
    seen: set[str] = set()
    for row in rows:
        name, status = row.get('name', ''), row.get('status', '')
        if name not in expected or name in seen:
            problems.append('Duplicate or unknown test filename')
        seen.add(name)
        if status not in counts:
            problems.append('Unknown test status')
            continue
        counts[status] += 1
        if status in ('FAIL', 'TIMEOUT', 'BLOCKED_NO_V80'):
            problems.append('Unsuccessful test: ' + name[:100])
        if status == 'SKIP' and (name not in SKIP_REASONS or SKIP_REASONS[name] not in row.get('last_output', '')):
            problems.append('Unverified SKIP: ' + name[:100])
    if len(rows) != len(expected) or seen != expected:
        problems.append('Missing, additional, or duplicate test rows')
    return {'ok': not problems, 'counts': counts, 'problems': problems[:30]}


def invoke(args: list[str], *, cwd: Path | None = None, timeout: int = 120) -> str:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed, exit={result.returncode} (output redacted)')
    return result.stdout.strip()


def run_logged(args: list[str], logfile: Path, timeout: int, cwd: Path | None = None) -> int:
    with logfile.open('w', encoding='utf-8') as log:
        log.write('$ ' + args[0] + ' [arguments redacted in log]\n')
        log.flush()
        try:
            result = subprocess.run(args, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            log.write('TIMEOUT\n')
            return 124
        except OSError as error:
            log.write('EXECUTION ERROR: ' + type(error).__name__ + '\n')
            return 127
        return result.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--pr', required=True, type=int, help='Same-repository Pull Request number')
    ap.add_argument('--v80-archive', type=Path, help='Original historical V8.0 source ZIP, never a hospital DB')
    ap.add_argument('--publish', action='store_true', help='Post tested SHA status and sanitized PR comment')
    ap.add_argument('--report-dir', type=Path, help='Local reports directory, outside the checkout')
    args = ap.parse_args()
    if sys.version_info[:2] != (3, 13):
        ap.error('Python 3.13 required on the trusted host')
    if args.pr < 1:
        ap.error('Invalid PR')
    if any(os.environ.get(k) for k in BLOCKED_ENV):
        ap.error('Refusing host financial/external environment variables')
    if args.v80_archive and (not args.v80_archive.is_file()
                             or args.v80_archive.suffix.lower() != '.zip'):
        ap.error('Original V8.0 source ZIP required at a real readable path')
    if any(shutil.which(binary) is None for binary in ('gh', 'git', 'docker')):
        ap.error('gh, git, and docker are required')
    root = Path(__file__).resolve().parents[1]
    if Path(invoke(['git', '-C', str(root), 'rev-parse', '--show-toplevel'])).resolve() != root:
        ap.error('Runner must be inside the trusted Ramses source checkout')
    if invoke(['git', '-C', str(root), 'branch', '--show-current']) != 'main':
        ap.error('Run the trusted runner from main, not from PR-controlled code')
    if invoke(['git', '-C', str(root), 'status', '--porcelain']):
        ap.error('Trusted main checkout has uncommitted changes')
    if invoke(['git', '-C', str(root), 'rev-parse', '--is-shallow-repository']) != 'false':
        ap.error('Full Git history is required')
    origin = invoke(['git', '-C', str(root), 'remote', 'get-url', 'origin'])
    allowed_remotes = {f'https://github.com/{REPO}', f'https://github.com/{REPO}.git',
                       f'git@github.com:{REPO}.git', f'ssh://git@github.com/{REPO}.git'}
    if origin not in allowed_remotes:
        ap.error('Unexpected origin: require the canonical Ramses GitHub repository')
    authors_path = root / 'tools' / 'qa' / 'trusted_pr_authors.txt'
    authors = {line.strip() for line in authors_path.read_text(encoding='utf-8').splitlines()
               if line.strip() and not line.lstrip().startswith('#')}
    pr = json.loads(invoke(['gh', 'api', f'repos/{REPO}/pulls/{args.pr}'], timeout=60))
    sha = validate_pr(pr, authors)
    # Use only the trusted, up-to-date main tooling. The PR code runs inside Docker only.
    invoke(['git', '-C', str(root), 'fetch', 'origin', 'main'], timeout=240)
    if invoke(['git', '-C', str(root), 'rev-parse', 'HEAD']) != invoke(
            ['git', '-C', str(root), 'rev-parse', 'refs/remotes/origin/main']):
        ap.error('Update your trusted local main first, then retry')
    invoke(['git', '-C', str(root), 'fetch', 'origin',
            f'+refs/pull/{args.pr}/head:refs/remotes/origin/qa-fallback-{args.pr}'], timeout=240)
    if invoke(['git', '-C', str(root), 'rev-parse', f'refs/remotes/origin/qa-fallback-{args.pr}']) != sha:
        ap.error('PR HEAD changed during fetch; retry rather than testing stale source')
    if reject_tracked_paths(invoke(['git', '-C', str(root), 'ls-files', '-z']).split('\0')):
        ap.error('Tracked sensitive files in trusted source; refusing QA')
    reports = (args.report_dir or (root.parent / 'ramses-qa-fallback-reports')).resolve()
    if root == reports or root in reports.parents:
        ap.error('Reports must be outside Git source')
    report = reports / f'pr-{args.pr}-{sha[:12]}-{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}'
    report.mkdir(parents=True, mode=0o700, exist_ok=False)
    if run_logged(['docker', 'build', '--file', str(root / 'tools/qa/Dockerfile'),
                   '--tag', IMAGE, str(root / 'tools/qa')], report / 'docker-build.log', 1800):
        print(f'FAIL: Docker build; report {report}')
        return 2
    with tempfile.TemporaryDirectory(prefix='ramses-fallback-') as td:
        checkout = Path(td) / 'checkout'
        invoke(['git', 'clone', '--quiet', '--local', '--no-hardlinks', str(root), str(checkout)], timeout=240)
        invoke(['git', '-C', str(checkout), 'checkout', '--detach', sha])
        invoke(['git', '-C', str(checkout), 'remote', 'set-url', 'origin',
                f'https://github.com/{REPO}.git'])
        if reject_tracked_paths(invoke(['git', '-C', str(checkout), 'ls-files', '-z']).split('\0')):
            ap.error('PR tracks sensitive source; refusing to execute')
        commands = {
            'syntax': ['sh', '-ec', 'python -m compileall -q app.py bootstrap.py scripts tests; '
                       'for f in static/*.js; do [ -f "$f" ] || continue; node --check "$f"; done'],
            'smoke': ['python', '-u', 'scripts/ci_smoke.py'],
            'full': ['python', '-u', 'scripts/qa_g2t_full.py'],
        }
        steps: dict[str, int] = {}
        for name, command in commands.items():
            steps[name] = run_logged(docker_command(checkout, command, args.v80_archive),
                                     report / (name + '.log'), 4200)
        tsv = checkout / 'QA_G2T_TEST_RESULTS.tsv'
        audit = audit_results(tsv, checkout / 'tests')
        if tsv.is_file():
            shutil.copy2(tsv, report / 'QA_G2T_TEST_RESULTS.tsv')
        ok = audit['ok'] and all(v == 0 for v in steps.values())
    result = {'sha': sha, 'pr': args.pr, 'status': 'success' if ok else 'failure',
              'steps': steps, 'counts': audit['counts'], 'problems': audit['problems'],
              'runner': IMAGE, 'production_certified': False, 'github_actions_used': False}
    (report / 'run.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    if args.publish:
        current = json.loads(invoke(['gh', 'api', f'repos/{REPO}/pulls/{args.pr}'], timeout=60))
        if validate_pr(current, authors) != sha:
            raise RuntimeError('PR head moved after tests; refusing stale publication')
        counts = audit['counts']
        summary = (f'fallback Docker {result["status"].upper()}: '
                   f'{counts["PASS"]} PASS, {counts["SKIP"]} SKIP, '
                   f'{counts["BLOCKED_NO_V80"]} BLOCKED; TEST ONLY')
        invoke(['gh', 'api', '-X', 'POST', f'repos/{REPO}/statuses/{sha}',
                '-f', 'state=' + result['status'], '-f', 'context=' + STATUS_CONTEXT,
                '-f', 'description=' + summary[:140]], timeout=60)
        comment = (f'<!-- ramses-fallback-qa {sha} -->\n'
                   f'**Ramses trusted Docker fallback QA: {result["status"].upper()}** '
                   f'for SHA {sha}. {summary}. No raw logs, no live data, no GitHub Actions. '
                   'Not a production approval.')
        invoke(['gh', 'api', '-X', 'POST', f'repos/{REPO}/issues/{args.pr}/comments',
                '-f', 'body=' + comment], timeout=60)
    print(f'{result["status"].upper()}: PR #{args.pr} {sha[:12]}; reports: {report}')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
