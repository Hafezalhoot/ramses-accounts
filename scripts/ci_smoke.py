"""Run self-contained, source-owned account/permissions/ledger regression scripts.

The historical-archive upgrade tests remain a separate, explicitly blocked gate.
CI is a fast gate, not a replacement for the entire test suite or hospital UAT.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    'test_v82_g2q_security.py',
    'test_v82_g2q_upgrade.py',
    'test_v82_g2q_google_privacy.py',
    'test_user_lifecycle.py',
    'test_v81e_g2i_financial_safety.py',
    'test_v81e_g2j_treasury_integrity.py',
    'test_v81e_g2m_secure_backup.py',
    'test_v81e_g2n_bank_scope.py',
    'test_v81e_g2o_patient_scopes.py',
    'test_v82_g2p_case_settlement.py',
    'test_payroll_review_workflow.py',
)


def main():
    env = os.environ.copy()
    # This suite must never write to external or production financial mirrors.
    for key in ('GOOGLE_SHEET_ID', 'GOOGLE_SERVICE_ACCOUNT_JSON', 'GOOGLE_SHEET_TARGET'):
        env.pop(key, None)
    failed = []
    for name in TESTS:
        try:
            result = subprocess.run([sys.executable, str(ROOT / 'tests' / name)],
                                    cwd=ROOT, env=env, capture_output=True,
                                    text=True, timeout=110)
            print(f'{"PASS" if result.returncode == 0 else "FAIL"}: {name}', flush=True)
            if result.returncode:
                failed.append(name)
                print((result.stdout + result.stderr)[-2500:], file=sys.stderr)
        except subprocess.TimeoutExpired:
            failed.append(name)
            print('TIMEOUT: ' + name, file=sys.stderr)
    print(f'CI smoke summary: {len(TESTS)-len(failed)}/{len(TESTS)} passed; historical-archive migrations NOT tested')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
