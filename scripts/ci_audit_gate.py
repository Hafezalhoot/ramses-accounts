"""Evaluate the isolated full-QA TSV without treating fixture gaps as successes.

Only known archive/workbook omissions may be exempted from the *source regression*
check.  Neither an exempted omission nor an all-PASS report certifies production.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

KNOWN_SKIPS = frozenset({
    'test_free_preview.py',
    'test_preview_modes.py',
    'test_v81e_g2j_schema_upgrade.py',
    'test_v81e_g2k_upgrade.py',
    'test_v81e_g2l_schema_upgrade.py',
})
KNOWN_BLOCKED = frozenset({'test_billing_upgrade_v81.py'})
SKIP_REASONS = {
    'test_free_preview.py': 'private June historical workbook intentionally excluded',
    'test_preview_modes.py': 'private June historical workbook intentionally excluded',
    'test_v81e_g2j_schema_upgrade.py': 'original preceding source checkout unavailable',
    'test_v81e_g2k_upgrade.py': 'G2J source checkout not packaged',
    'test_v81e_g2l_schema_upgrade.py': 'G2K source checkout not available',
}
BLOCKED_REASONS = {'test_billing_upgrade_v81.py': 'Original V8.0 ZIP not found'}
MUST_REPORT = frozenset({
    'test_s14_service_fees.py',
    'test_s14_pricing.py',
    'test_s14_split_payments.py',
    'test_s14_upgrade.py',
    'test_ci_audit_gate.py',
}) | KNOWN_SKIPS | KNOWN_BLOCKED
STATES = frozenset({'PASS', 'SKIP', 'BLOCKED_NO_V80', 'FAIL', 'TIMEOUT'})
MIN_TESTS = 160  # 159 baseline scripts at S14 plus this guard's own regression.


def evaluate(rows: list[dict], *, strict_fixtures: bool = False) -> dict:
    counts = Counter()
    names = set()
    errors: list[str] = []
    missing = MUST_REPORT - {r.get('name', '') for r in rows}
    if len(rows) < MIN_TESTS:
        errors.append(f'Only {len(rows)} scripts were reported; expected at least {MIN_TESTS}.')
    if missing:
        errors.append('Required test scripts absent: ' + ', '.join(sorted(missing)))
    for item in rows:
        name = item.get('name', '')
        state = item.get('status', '')
        if not name.startswith('test_') or not name.endswith('.py'):
            errors.append('Invalid test name in report')
        if name in names:
            errors.append('Duplicate result: ' + name)
        names.add(name)
        counts[state] += 1
        if state not in STATES:
            errors.append(f'Unrecognized test status for {name}: {state}')
        elif state in ('FAIL', 'TIMEOUT'):
            errors.append(f'{state}: {name}')
        elif state == 'SKIP':
            if strict_fixtures or name not in KNOWN_SKIPS:
                errors.append('Unapproved SKIP: ' + name)
            elif SKIP_REASONS[name] not in item.get('last_output', ''):
                errors.append('Unverified SKIP reason: ' + name)
        elif state == 'BLOCKED_NO_V80':
            if strict_fixtures or name not in KNOWN_BLOCKED:
                errors.append('Unapproved BLOCKED: ' + name)
            elif BLOCKED_REASONS[name] not in item.get('last_output', ''):
                errors.append('Unverified BLOCKED reason: ' + name)
    return {
        'ok': not errors,
        'counts': {key: counts[key] for key in ('PASS', 'SKIP', 'BLOCKED_NO_V80', 'FAIL', 'TIMEOUT')},
        'total': len(rows),
        'expected_skip_names': sorted(r['name'] for r in rows if r.get('status') == 'SKIP'),
        'expected_blocked_names': sorted(r['name'] for r in rows if r.get('status') == 'BLOCKED_NO_V80'),
        'errors': errors,
        'production_certified': False,
    }


def write_summary(result: dict, path: Path) -> None:
    counts = result['counts']
    state = 'PASS (source regression only)' if result['ok'] else 'FAIL'
    lines = [
        '# Ramses isolated full QA — ' + state,
        '',
        '**NOT PRODUCTION CERTIFIED.** Test results are synthetic; no hospital acceptance,',
        'real-device restore, source-of-truth balance sign-off, or live migration was run.',
        '',
        '| Status | Count |',
        '|---|---:|',
    ]
    for key in ('PASS', 'SKIP', 'BLOCKED_NO_V80', 'FAIL', 'TIMEOUT'):
        lines.append(f'| {key} | {counts[key]} |')
    lines += [f'| **Total** | **{result["total"]}** |', '']
    if result['expected_skip_names']:
        lines.append('**SKIP (NOT PASS):** ' + ', '.join(result['expected_skip_names']))
    if result['expected_blocked_names']:
        lines.append('**BLOCKED (NOT PASS):** ' + ', '.join(result['expected_blocked_names']))
    if result['errors']:
        lines += ['', '**Failed audit gates:**', *('- ' + e for e in result['errors'])]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--strict-fixtures', action='store_true',
                        help='Treat every SKIP/BLOCKED as a hard failure')
    parser.add_argument('--summary-file', type=Path, default=Path('ci_quality_summary.md'))
    args = parser.parse_args()
    try:
        with args.report.open(newline='', encoding='utf-8') as fh:
            reader = csv.DictReader(fh, delimiter='\t')
            if not reader.fieldnames or not {'name', 'status'} <= set(reader.fieldnames):
                raise ValueError('QA TSV lacks name/status headers')
            rows = list(reader)
        result = evaluate(rows, strict_fixtures=args.strict_fixtures)
    except (OSError, csv.Error, ValueError) as error:
        result = evaluate([])
        result['errors'].insert(0, 'QA report cannot be trusted: ' + str(error))
        result['ok'] = False
    write_summary(result, args.summary_file)
    print(args.summary_file.read_text(encoding='utf-8'))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
