"""Regression tests for trusted, GitHub-independent QA fallback orchestration."""
import csv
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import qa_fallback


def run():
    sha = 'a' * 40
    pr = {'state': 'open', 'head': {'sha': sha, 'ref': 'feature/valid',
          'repo': {'full_name': qa_fallback.REPO}}, 'user': {'login': 'Hafezalhoot'}}
    assert qa_fallback.validate_pr(pr, {'Hafezalhoot'}) == sha
    for wrong in (
        dict(pr, state='closed'),
        dict(pr, user={'login': 'stranger'}),
        dict(pr, head=dict(pr['head'], repo={'full_name': 'attacker/fork'})),
        dict(pr, head=dict(pr['head'], sha='abc')),
    ):
        try:
            qa_fallback.validate_pr(wrong, {'Hafezalhoot'})
        except ValueError:
            pass
        else:
            raise AssertionError('Untrusted PR accepted')

    args = qa_fallback.docker_command('/tmp/trusted-checkout', ['python', 'app.py'])
    assert '--network' in args and args[args.index('--network') + 1] == 'none'
    assert '--cap-drop' in args and args[args.index('--cap-drop') + 1] == 'ALL'
    assert '--read-only' in args
    assert not any('GH_TOKEN' in x or '.ssh' in x or 'docker.sock' in x for x in args)
    assert qa_fallback.reject_tracked_paths(['.env', 'app.py'])
    assert qa_fallback.reject_tracked_paths(['data/database.db'])
    assert qa_fallback.reject_tracked_paths(['secret.pem'])
    assert not qa_fallback.reject_tracked_paths(['.env.example', 'README.md', 'static/app.js'])

    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        tests = root / 'tests'
        tests.mkdir()
        for name in ('test_one.py', 'test_two.py'):
            (tests / name).write_text('# test\n')
        tsv = root / 'results.tsv'
        def write(rows):
            with tsv.open('w', newline='') as fh:
                writer = csv.writer(fh, delimiter='\t')
                writer.writerow(['name', 'status', 'seconds', 'last_output'])
                writer.writerows(rows)
        write([['test_one.py', 'PASS', 1, 'ok'], ['test_two.py', 'PASS', 1, 'ok']])
        assert qa_fallback.audit_results(tsv, tests, min_scripts=2)['ok']
        write([['test_one.py', 'PASS', 1, 'ok'], ['test_two.py', 'BLOCKED_NO_V80', 1, 'missing']])
        assert not qa_fallback.audit_results(tsv, tests, min_scripts=2)['ok']
        write([['test_one.py', 'PASS', 1, 'ok'], ['test_one.py', 'PASS', 1, 'ok']])
        assert not qa_fallback.audit_results(tsv, tests, min_scripts=2)['ok']
        write([['test_one.py', 'PASS', 1, 'ok'], ['test_two.py', 'SKIP', 1, 'unsanctioned']])
        assert not qa_fallback.audit_results(tsv, tests, min_scripts=2)['ok']
        write([['test_one.py', 'PASS', 1, 'ok']])
        assert not qa_fallback.audit_results(tsv, tests, min_scripts=2)['ok']
    print('PASS portable QA: PR trust, no-host-secrets Docker, strict report audit')


if __name__ == '__main__':
    run()
