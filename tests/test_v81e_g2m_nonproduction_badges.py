"""Non-approved release never labels itself production-safe in the UI."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def run():
    js=(ROOT/'static/app.js').read_text()
    html=(ROOT/'static/index.html').read_text()
    api=(ROOT/'app.py').read_text()
    assert 'V8.1E-G2R' in js and 'V8.1E-G2R' in html
    assert 'Ramses Accounts V8.1E G2R Bed-Stay Development - Test Only' in api
    assert 'const trial=true;' in js
    assert 'eLabel.textContent="' in js
    assert 'تشغيل فعلي محمي' not in js
    assert 'G2R' in (ROOT/'START_Ramses_Mac.command').read_text()
    print('PASS G2M: unapproved environment cannot display false production-approved status')


if __name__=='__main__':run()
