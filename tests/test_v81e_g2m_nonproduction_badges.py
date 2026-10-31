"""Non-approved release never labels itself production-safe in the UI."""
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def run():
    js=(ROOT/'static/app.js').read_text()
    html=(ROOT/'static/index.html').read_text()
    api=(ROOT/'app.py').read_text()
    version=re.search(r'V8\.1E-G2[A-Z]',html)
    assert version, 'Release label missing'
    version=version.group(0)
    assert version in js and version in html
    assert version.replace('-', ' ') in api and 'Test Only' in api
    assert 'const trial=true;' in js
    assert 'eLabel.textContent="' in js
    assert 'تشغيل فعلي محمي' not in js
    assert version in (ROOT/'START_Ramses_Mac.command').read_text()
    print('PASS G2M: unapproved environment cannot display false production-approved status')


if __name__=='__main__':run()
