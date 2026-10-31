"""QA status must not count deliberately omitted historical inputs as PASS."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import qa_g2t_full


def run():
    for output in ('SKIP: private historical workbook missing',
                   'SKIP G2L source archive unavailable',
                   'PASS preliminary checks\nSKIP: another historical gate'):
        assert qa_g2t_full.success_status(output) == 'SKIP', output
    assert qa_g2t_full.success_status('PASS all local checks') == 'PASS'
    print('PASS QA runner distinguishes skipped source dependencies from PASS')


if __name__ == '__main__':
    run()
