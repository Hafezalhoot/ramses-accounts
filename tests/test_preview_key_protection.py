"""Local preview never loads a world-readable Google service-account key."""
import os
import stat
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import free_preview


def run():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        (root/'secrets').mkdir()
        (root/'data').mkdir()
        (root/'.env').write_text('RAMSES_ADMIN_USER=owner\nRAMSES_ADMIN_PASSWORD=test_initial_very_strong_password\n')
        (root/'.env').chmod(0o600)
        key=root/'secrets'/'service-account.json'
        key.write_text('{"test":"dummy"}')
        with patch.object(free_preview,'ROOT',root):
            if os.name != 'nt':
                key.chmod(0o644)
                try:
                    free_preview.preview_environment(local_only=True)
                    raise AssertionError('World-readable key must be refused')
                except RuntimeError as e:
                    assert 'chmod 600' in str(e)
            key.chmod(0o600)
            env=free_preview.preview_environment(local_only=True)
            assert env['GOOGLE_SHEET_ID']==free_preview.STAGING_ID
            assert env['GOOGLE_SERVICE_ACCOUNT_JSON']==str(key)
            assert env['RAMSES_DB_PATH']==str(root/'data'/'free-preview.sqlite3')
            assert env['RAMSES_SECURE_COOKIES']=='0'
            arch=free_preview.preview_environment(local_only=False,archive_mode=True)
            assert arch['RAMSES_SECURE_COOKIES']=='1'
            assert arch['RAMSES_DB_PATH']==str(root/'data'/'free-preview-archive.sqlite3')
    print('PASS - insecure service-account permission refused, fixed staging only, archive separate, secure tunnel cookie')

if __name__=='__main__':run()
