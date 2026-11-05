"""Zero-GitHub-Actions, commit-pinned Ramses synthetic QA runner.

Run from a clean, full-history clone in Work or on a developer machine.
Checks a detached temporary worktree, never a live or working SQLite database.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLOCKED_ENV = ('RAMSES_DB_PATH', 'GOOGLE_SHEET_ID', 'GOOGLE_SERVICE_ACCOUNT_JSON',
               'GOOGLE_SHEET_TARGET')
SAFE_ENV = ('PATH', 'HOME', 'TMPDIR', 'TEMP', 'USER', 'LANG', 'LC_ALL', 'VIRTUAL_ENV',
            'SYSTEMROOT', 'WINDIR', 'SSL_CERT_FILE', 'REQUESTS_CA_BUNDLE')


def git(*args: str) -> str:
    return subprocess.run(['git', '-C', str(ROOT), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def run_step(name: str, commands: list[list[str]], cwd: Path,
             env: dict[str, str], report: Path, timeout: int = 1800) -> int:
    path = report / (name + '.log')
    with path.open('w', encoding='utf-8') as log:
        for command in commands:
            log.write('$ ' + ' '.join(command) + '\n')
            log.flush()
            try:
                result = subprocess.run(command, cwd=cwd, env=env, stdout=log,
                                        stderr=subprocess.STDOUT, timeout=timeout,
                                        check=False)
                if result.returncode:
                    log.write(f'EXIT {result.returncode}\n')
                    return result.returncode
            except subprocess.TimeoutExpired:
                log.write('TIMEOUT\n')
                return 124
            except OSError as error:
                log.write(f'EXECUTION ERROR: {error}\n')
                return 127
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full', action='store_true', help='Also run complete synthetic QA and audit')
    parser.add_argument('--strict-fixtures', action='store_true',
                        help='Fail on known missing historic fixtures as well as unexpected ones')
    parser.add_argument('--v80-archive', type=Path,
                        help='Explicit original V8.0 *source* ZIP; never pass a hospital database')
    parser.add_argument('--report-dir', type=Path,
                        help='Evidence directory (defaults beside the repository, outside Git)')
    args = parser.parse_args()

    if sys.version_info[:2] != (3, 13):
        parser.error('Python 3.13 is required for this S14/S15 regression baseline')
    unsafe = [key for key in BLOCKED_ENV if os.environ.get(key)]
    if unsafe:
        parser.error('Refusing active financial/external environment: ' + ', '.join(unsafe))
    if args.v80_archive and (not args.v80_archive.is_file()
                             or args.v80_archive.suffix.lower() != '.zip'):
        parser.error('The specified original V8.0 source ZIP does not exist')
    if shutil.which('git') is None or shutil.which('node') is None:
        parser.error('This runner requires git and Node.js for source/syntax checks')
    try:
        if Path(git('rev-parse', '--show-toplevel')).resolve() != ROOT:
            parser.error('Run this script from the intended Ramses Git checkout')
        if git('rev-parse', '--is-shallow-repository') != 'false':
            parser.error('Full Git ancestry required: fetch --unshallow before testing')
        if git('status', '--porcelain'):
            parser.error('Source contains uncommitted changes; commit and rerun so results match a SHA')
        sha = git('rev-parse', 'HEAD')
    except subprocess.CalledProcessError:
        parser.error('A complete, accessible Git checkout is required')

    now = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    report = (args.report_dir or (ROOT.parent / 'ramses-local-qa' / f'{sha[:12]}-{now}')).resolve()
    if report == ROOT or ROOT in report.parents:
        parser.error('QA evidence folder must be outside the source checkout')
    report.mkdir(parents=True, exist_ok=True)
    env = {key: os.environ[key] for key in SAFE_ENV if os.environ.get(key)}
    env.update(CI='true', PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
    if args.v80_archive:
        env['RAMSES_V80_ARCHIVE'] = str(args.v80_archive.resolve())
    steps: dict[str, int] = {}
    worktree: Path | None = None
    with tempfile.TemporaryDirectory(prefix='ramses-qa-worktree-') as folder:
        worktree = Path(folder) / 'checkout'
        try:
            subprocess.run(['git', '-C', str(ROOT), 'worktree', 'add', '--detach',
                            str(worktree), sha], check=True, capture_output=True)
            steps['source_integrity'] = run_step(
                'source_integrity', [['git', 'fsck', '--full', '--no-reflogs']],
                worktree, env, report)
            if steps['source_integrity'] == 0:
                js = sorted(str(path.relative_to(worktree))
                            for path in (worktree / 'static').glob('*.js'))
                syntax = [[sys.executable, '-m', 'compileall', '-q', 'app.py',
                           'bootstrap.py', 'scripts', 'tests']]
                syntax += [['node', '--check', f] for f in js]
                steps['syntax'] = run_step('syntax', syntax, worktree, env, report)
            if not any(steps.values()):
                steps['smoke'] = run_step('smoke', [[sys.executable, '-u',
                    'scripts/ci_smoke.py']], worktree, env, report, timeout=3600)
            if args.full and not any(steps.values()):
                steps['full'] = run_step('full', [[sys.executable, '-u',
                    'scripts/qa_g2t_full.py']], worktree, env, report, timeout=3600)
                results = worktree / 'QA_G2T_TEST_RESULTS.tsv'
                if results.is_file():
                    shutil.copyfile(results, report / results.name)
                    audit = [sys.executable, 'scripts/ci_audit_gate.py',
                             str(results), '--summary-file', str(report / 'audit.md')]
                    if args.strict_fixtures:
                        audit.append('--strict-fixtures')
                    steps['audit'] = run_step('audit', [audit], worktree, env, report)
                else:
                    steps['audit'] = 2
                    (report / 'audit.md').write_text('Full QA did not produce a report.\n', encoding='utf-8')
        except subprocess.CalledProcessError as error:
            steps['worktree'] = error.returncode or 1
        finally:
            if worktree.exists():
                subprocess.run(['git', '-C', str(ROOT), 'worktree', 'remove',
                                '--force', str(worktree)], capture_output=True)

    status = 'PASS' if steps and all(rc == 0 for rc in steps.values()) else 'FAIL'
    manifest = {'commit_sha': sha, 'utc': now, 'mode': 'full' if args.full else 'smoke',
                'status': status, 'steps': steps, 'production_certified': False,
                'github_actions_used': False}
    (report / 'run.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)
                                     + '\n', encoding='utf-8')
    print(f'{status}: {sha[:12]} | {steps} | report: {report}')
    return 0 if status == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
