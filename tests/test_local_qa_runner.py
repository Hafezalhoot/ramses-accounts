"""Synthetic validation of the offline, no-GitHub-Actions QA entry point."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[1] / 'scripts' / 'run_local_qa.py'


def git(root: Path, *args: str) -> str:
    result = subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def make_project() -> Path:
    folder = Path(tempfile.mkdtemp(prefix='ramses-offline-fixture-'))
    (folder / 'scripts').mkdir()
    (folder / 'static').mkdir()
    shutil.copy2(RUNNER, folder / 'scripts' / 'run_local_qa.py')
    (folder / 'scripts' / 'ci_smoke.py').write_text('print("PASS synthetic smoke")\n', encoding='utf-8')
    (folder / 'scripts' / 'qa_g2t_full.py').write_text('''\nfrom pathlib import Path\nPath('QA_G2T_TEST_RESULTS.tsv').write_text('name\\tstatus\\tlast_output\\n' + 'test_fake.py\\tPASS\\tSynthetic pass\\n')\nprint('PASS synthetic full qa')\n''', encoding='utf-8')
    (folder / 'scripts' / 'ci_audit_gate.py').write_text('''\nimport sys\nfrom pathlib import Path\nassert Path(sys.argv[1]).is_file()\nPath(sys.argv[sys.argv.index('--summary-file')+1]).write_text('Synthetic QA audit passed')\n''', encoding='utf-8')
    (folder / 'app.py').write_text('APP = 1\n', encoding='utf-8')
    (folder / 'bootstrap.py').write_text('BOOTSTRAP = 1\n', encoding='utf-8')
    (folder / 'static' / 'app.js').write_text('const synthetic = true;\n', encoding='utf-8')
    git(folder, 'init', '-q')
    git(folder, 'config', 'user.email', 'test@example.invalid')
    git(folder, 'config', 'user.name', 'Synthetic QA')
    git(folder, 'add', '.')
    git(folder, 'commit', '-qm', 'synthetic test fixture')
    return folder


def invoke(root: Path, *args: str, env: dict | None = None):
    return subprocess.run([sys.executable, str(root / 'scripts' / 'run_local_qa.py'), *args],
                          cwd=root, env=env or os.environ.copy(), text=True, capture_output=True, timeout=90)


def test_clean_checkout_smoke_and_full():
    root = make_project()
    try:
        evidence = root.parent / (root.name + '-evidence')
        completed = invoke(root, '--full', '--report-dir', str(evidence))
        assert completed.returncode == 0, completed.stdout + completed.stderr
        manifest = json.loads((evidence / 'run.json').read_text(encoding='utf-8'))
        assert manifest['commit_sha'] == git(root, 'rev-parse', 'HEAD')
        assert manifest['status'] == 'PASS'
        assert manifest['steps']['smoke'] == 0 and manifest['steps']['full'] == 0
        assert manifest['steps']['audit'] == 0
        assert (evidence / 'QA_G2T_TEST_RESULTS.tsv').is_file()
        assert not (root / 'QA_G2T_TEST_RESULTS.tsv').exists(), 'Reports must not mutate working checkout'
        assert git(root, 'status', '--porcelain') == ''
    finally:
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(evidence, ignore_errors=True)


def test_refuses_financial_database_environment():
    root = make_project()
    try:
        env = os.environ.copy()
        env['RAMSES_DB_PATH'] = '/tmp/example-operational-data.sqlite3'
        blocked = invoke(root, env=env)
        assert blocked.returncode != 0
        assert 'RAMSES_DB_PATH' in blocked.stderr
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_refuses_uncommitted_source():
    root = make_project()
    try:
        (root / 'app.py').write_text('APP = 2\n', encoding='utf-8')
        blocked = invoke(root)
        assert blocked.returncode != 0
        assert 'uncommitted' in blocked.stderr.lower()
    finally:
        shutil.rmtree(root, ignore_errors=True)



def test_refuses_report_folder_inside_source_checkout():
    root = make_project()
    try:
        blocked = invoke(root, '--report-dir', str(root / 'docs' / 'QA-logs'))
        assert blocked.returncode != 0
        assert 'outside' in blocked.stderr.lower()
    finally:
        shutil.rmtree(root, ignore_errors=True)

if __name__ == '__main__':
    test_clean_checkout_smoke_and_full()
    test_refuses_financial_database_environment()
    test_refuses_uncommitted_source()
    test_refuses_report_folder_inside_source_checkout()
    print('PASS 4 offline runner tests')
