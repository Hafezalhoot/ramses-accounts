"""Public CI must preserve isolation, honest historical evidence and SHA checks."""
import inspect
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import qa_fallback as qa
import qa_checked_merge as merge


class PublicCITests(unittest.TestCase):
    def test_other_ai_identity_requires_server_confirmed_write_permission(self):
        self.assertTrue(hasattr(qa,'approved_authors'))
        pr={'user':{'login':'authorized-helper'}}
        for role in ('read','triage','none'):
            with patch.object(qa,'invoke',return_value='{"permission":"'+role+'"}'):
                with self.assertRaises(ValueError):qa.approved_authors(pr,{'Hafezalhoot'})
        with patch.object(qa,'invoke',return_value='{"permission":"write"}'):
            self.assertIn('authorized-helper',qa.approved_authors(pr,{'Hafezalhoot'}))

    def test_docker_uses_only_disposable_volume_and_pinned_image(self):
        self.assertIn('image_ref', inspect.signature(qa.docker_command).parameters)
        image = 'sha256:' + 'b' * 64
        args = qa.docker_command('ramses-fallback-work-' + 'a' * 32, ['python', '-V'], image_ref=image)
        self.assertIn(image, args)
        self.assertFalse(any('type=bind' in x for x in args))
        self.assertIn('--read-only', args)

    def test_nested_private_environment_is_refused(self):
        self.assertTrue(qa.reject_tracked_paths(['docs/.env.local']))

    def test_report_symlink_cannot_be_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td);(p/'tests').mkdir();(p/'tests/test_one.py').touch()
            (p/'outside.tsv').write_text('name\tstatus\tlast_output\ntest_one.py\tPASS\tok\n')
            (p/'result.tsv').symlink_to(p/'outside.tsv')
            self.assertFalse(qa.audit_results(p/'result.tsv',p/'tests',1)['ok'])

    def test_cloud_core_reports_only_exact_missing_archive_as_external(self):
        self.assertIn('allow_missing_v80', inspect.signature(qa.audit_results).parameters)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);(p/'tests').mkdir();(p/'tests/test_billing_upgrade_v81.py').touch()
            report=p/'r.tsv'
            report.write_text('name\tstatus\tlast_output\ntest_billing_upgrade_v81.py\tBLOCKED_NO_V80\tOriginal V8.0 ZIP not found\n')
            self.assertFalse(qa.audit_results(report,p/'tests',1)['ok'])
            result=qa.audit_results(report,p/'tests',1,allow_missing_v80=True)
            self.assertTrue(result['ok']);self.assertEqual(result['counts']['PASS'],0)
            self.assertEqual(result['counts']['BLOCKED_NO_V80'],1)
            report.write_text('name\tstatus\tlast_output\ntest_billing_upgrade_v81.py\tBLOCKED_NO_V80\tUnexpected failure\n')
            self.assertFalse(qa.audit_results(report,p/'tests',1,allow_missing_v80=True)['ok'])

    def test_merge_requires_latest_exact_sha_success_from_actions_app(self):
        self.assertIn('check_runs',inspect.signature(merge.preflight).parameters)
        sha='a'*40
        pr={'state':'open','draft':False,'mergeable':True,'base':{'ref':'main'},
            'head':{'sha':sha,'repo':{'full_name':qa.REPO}},'user':{'login':'Hafezalhoot'}}
        status={'sha':sha,'state':'pending','statuses':[]}
        checks=[{'id':i,'name':n,'head_sha':sha,'status':'completed','conclusion':'success','app':{'id':15368}}
                for i,n in enumerate(('ramses-core-ci','ramses-security'),1)]
        self.assertEqual(merge.preflight(pr,status,{'status':'ahead'},{'Hafezalhoot'},check_runs=checks),sha)
        for changed in ([dict(checks[0],head_sha='b'*40),checks[1]],
                        [dict(checks[0],app={'id':1}),checks[1]],
                        [*checks,dict(checks[0],id=9,conclusion='failure')]):
            with self.assertRaises(ValueError):
                merge.preflight(pr,status,{'status':'ahead'},{'Hafezalhoot'},check_runs=changed)


def run():
    result=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(PublicCITests))
    if not result.wasSuccessful():raise SystemExit(1)
    print('PASS public CI isolation, historical evidence and SHA-bound checks')

if __name__=='__main__':run()
