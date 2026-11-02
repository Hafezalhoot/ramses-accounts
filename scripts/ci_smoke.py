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
    'test_v82_g3n_supplier_opening.py',
    'test_v82_g3n_upgrade.py',
    'test_v82_g3m_supplier_attribution.py',
    'test_v82_g3m_upgrade.py',
    'test_v82_g3l_supplier_control.py',
    'test_v82_g3k_supplier_bank_settlement.py',
    'test_v82_g3k_upgrade.py',
    'test_v82_g3j_cairo_typography.py',
    'test_v82_g3j_supplier_payment_requests.py',
    'test_v82_g3j_upgrade.py',
    'test_v82_g3i_supplier_maturity.py',
    'test_v82_g3i_upgrade.py',
    'test_v82_g3h_purchasing.py',
    'test_v82_g3h_upgrade.py',
    'test_v82_g3h_closed_period.py',
    'test_v82_g3g_return_writeoffs.py',
    'test_v82_g3g_upgrade.py',
    'test_v82_g3f_return_quarantine.py',
    'test_v82_g3f_upgrade.py',
    'test_v82_g3e_inventory_privacy.py',
    'test_qa_skip_reporting.py',
    'test_v82_g3d_inventory_returns.py',
    'test_v82_g3d_return_date_guards.py',
    'test_v82_g3d_upgrade.py',
    'test_v82_g3c_case_consumables_cost.py',
    'test_v82_g3c_fifo_date_guard.py',
    'test_v82_g3c_upgrade.py',
    'test_v82_g3b_clinical_document_hash.py',
    'test_v82_g3b_upgrade.py',
    'test_v82_g3a_clinician_identity.py',
    'test_v82_g3a_role_upgrade.py',
    'test_v82_g2z_release_label.py',
    'test_v82_g2z_clinical_attestation.py',
    'test_v82_g2z_upgrade.py',
    'test_v82_g2y_report_scope.py',
    'test_v82_g2w_shift_fund_scope.py',
    'test_v82_g2w_gl_viewer_scope.py',
    'test_v82_g2v_encrypted_upgrade.py',
    'test_v82_g2u_cross_month_billing.py',
    'test_v82_g2u_privacy_scope.py',
    'test_v82_g2u_upgrade.py',
    'test_v82_g2t_inventory.py',
    'test_v82_g2t_revocation_race.py',
    'test_v82_g2t_upgrade.py',
    'test_v82_g2t_closed_inventory_period.py',
    'test_v82_g2t_concurrency.py',
    'test_v82_g2s_bed_transfers.py',
    'test_v82_g2s_month_end.py',
    'test_v82_g2s_month_end_ledger_date.py',
    'test_v82_g2s_closed_bed_period.py',
    'test_v82_g2s_tariff_integrity.py',
    'test_v82_g2s_upgrade.py',
    'test_v82_g2s_preview_archive_guard.py',
    'test_v82_g2r_bed_stays.py',
    'test_v82_g2r_upgrade.py',
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
    'test_s6_backup_financial_integrity.py',
    'test_s7_recovery_drill.py',
    'test_s8_historical_shift_identity.py',
    'test_s9_shift_open_options.py',
    'test_s10_daily_coverage_certificate.py',
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
