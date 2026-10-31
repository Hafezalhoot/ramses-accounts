"""G2B additive migration: an existing G2A ledger survives adding case provenance."""
import os
import sys
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as folder:
        os.environ['RAMSES_DB_PATH'] = str(Path(folder) / 'existing_ramses.sqlite3')
        os.environ['RAMSES_ADMIN_USER'] = 'upgrade_owner'
        os.environ['RAMSES_ADMIN_PASSWORD'] = 'upgrade_owner_secure_password'
        from bootstrap import connect, initialize
        initialize()
        with connect() as c:
            old_counts = {
                table: c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                for table in ('users', 'funds', 'billing_points', 'cashier_schedule_versions')
            }
            # Emulate a G2A database where this table did not yet exist.
            c.execute('DROP TABLE billing_late_cases')
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='billing_late_cases'").fetchone()
            c.execute("INSERT INTO billing_patients(code,display_name,created_by,created_at) "
                      "VALUES ('PT-G2B-UPGRADE','مريض محفوظ من إصدار قديم',1,datetime('now'))")
            assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        initialize()
        with connect() as c:
            for table, count in old_counts.items():
                assert c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == count, table
            assert c.execute("SELECT display_name FROM billing_patients WHERE code='PT-G2B-UPGRADE'").fetchone()[0]
            assert c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='billing_late_cases'").fetchone()
            assert c.execute('PRAGMA foreign_key_check').fetchall() == []
            assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        print('PASS G2B schema: old ledger, users, funds, schedules, and patient retained')


if __name__ == '__main__':
    run()
