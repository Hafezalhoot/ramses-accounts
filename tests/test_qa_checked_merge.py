"""A merge check must reject stale or untested changes before invoking gh."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import qa_checked_merge


def run():
    sha = 'a' * 40
    main = 'b' * 40
    pr = {'state': 'open', 'draft': False, 'mergeable': True,
          'user': {'login': 'Hafezalhoot'},
          'base': {'ref': 'main', 'sha': main},
          'head': {'sha': sha, 'repo': {'full_name': 'Hafezalhoot/ramses-accounts'}}}
    statuses = {'state': 'success', 'sha': sha, 'statuses': [
        {'context': 'ramses/mac-local-qa', 'state': 'success',
         'description': 'SUCCESS 156 PASS, 5 SKIP, 0 BLOCKED; NOT production'}]}
    compare = {'status': 'ahead'}
    assert qa_checked_merge.preflight(pr, statuses, compare, {'Hafezalhoot'}) == sha
    cases = [
        (dict(pr, draft=True), statuses, compare),
        (dict(pr, mergeable=False), statuses, compare),
        (dict(pr, user={'login': 'untrusted'}), statuses, compare),
        (dict(pr, base={'ref': 'staging', 'sha': main}), statuses, compare),
        (pr, dict(statuses, sha='c' * 40), compare),
        (pr, dict(statuses, statuses=[]), compare),
        (pr, dict(statuses, statuses=[dict(statuses['statuses'][0], description='0 PASS, 1 BLOCKED')]), compare),
        (pr, statuses, {'status': 'diverged'}),
    ]
    for fake_pr, fake_status, fake_compare in cases:
        try:
            qa_checked_merge.preflight(fake_pr, fake_status, fake_compare, {'Hafezalhoot'})
        except ValueError:
            pass
        else:
            raise AssertionError('Unsafe merge preflight was accepted')
    print('PASS checked merge: exact SHA, QA status, author, base, clean/up-to-date PR')


if __name__ == '__main__':
    run()
