"""Synthetic self-test for the GitHub Actions full-QA report policy."""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ci_audit_gate import evaluate, write_summary

REQUIRED = {
    'test_s14_service_fees.py', 'test_s14_pricing.py',
    'test_s14_split_payments.py', 'test_s14_upgrade.py',
    'test_ci_audit_gate.py', 'test_billing_upgrade_v81.py',
}
SKIPS = {
    'test_free_preview.py', 'test_preview_modes.py',
    'test_v81e_g2j_schema_upgrade.py', 'test_v81e_g2k_upgrade.py',
    'test_v81e_g2l_schema_upgrade.py',
}


def records():
    base = {name: 'PASS' for name in REQUIRED | SKIPS}
    for i in range(160 - len(base)):
        base[f'test_synthetic_{i:03}.py'] = 'PASS'
    for name in SKIPS:
        base[name] = 'SKIP'
    base['test_billing_upgrade_v81.py'] = 'BLOCKED_NO_V80'
    return [{'name': name, 'status': value, 'seconds': '0.1', 'last_output': ''}
            for name, value in base.items()]


class AuditGate(unittest.TestCase):
    def test_allows_only_known_fixture_gaps_without_calling_it_certified(self):
        result = evaluate(records())
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['counts']['PASS'], 154)
        self.assertEqual(result['counts']['SKIP'], 5)
        self.assertEqual(result['counts']['BLOCKED_NO_V80'], 1)
        self.assertFalse(result['production_certified'])
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'summary.md'
            write_summary(result, output)
            self.assertIn('NOT PRODUCTION CERTIFIED', output.read_text())
            self.assertNotIn('last_output', output.read_text())

    def test_unexpected_skip_is_rejected(self):
        r = records()
        r[0]['status'] = 'SKIP' if r[0]['name'] not in SKIPS else 'PASS'
        if r[0]['status'] == 'PASS':
            next(x for x in r if x['name'].startswith('test_synthetic_'))['status'] = 'SKIP'
        self.assertFalse(evaluate(r)['ok'])

    def test_unexpected_blocked_is_rejected(self):
        r = records()
        next(x for x in r if x['name'].startswith('test_synthetic_'))['status'] = 'BLOCKED_NO_V80'
        self.assertFalse(evaluate(r)['ok'])

    def test_missing_required_test_is_rejected_even_if_count_unchanged(self):
        r = records()
        r = [x for x in r if x['name'] != 'test_s14_service_fees.py']
        r.append({'name': 'test_padding_999.py', 'status': 'PASS'})
        self.assertFalse(evaluate(r)['ok'])

    def test_duplicate_row_is_rejected(self):
        r = records()
        r.append(r[-1].copy())
        self.assertFalse(evaluate(r)['ok'])

    def test_failure_status_is_rejected(self):
        r = records()
        next(x for x in r if x['name'].startswith('test_synthetic_'))['status'] = 'TIMEOUT'
        self.assertFalse(evaluate(r)['ok'])

    def test_empty_and_short_report_are_rejected(self):
        self.assertFalse(evaluate([])['ok'])
        self.assertFalse(evaluate(records()[:15])['ok'])

    def test_strict_fixture_policy_does_not_allow_known_gaps(self):
        self.assertFalse(evaluate(records(), strict_fixtures=True)['ok'])

    def test_clean_fixtures_can_pass_strict_if_all_tests_pass(self):
        r = records()
        for x in r:
            x['status'] = 'PASS'
        self.assertTrue(evaluate(r, strict_fixtures=True)['ok'])


if __name__ == '__main__':
    unittest.main()
