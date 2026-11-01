"""G3J Cairo UI font hierarchy and restricted font origin (no font files bundled)."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/'static/index.html').read_text(encoding='utf-8')
css=(ROOT/'static/styles.css').read_text(encoding='utf-8')
app=(ROOT/'app.py').read_text(encoding='utf-8')
js=(ROOT/'static/app.js').read_text(encoding='utf-8')
assert 'family=Cairo:wght@200..1000' in js, 'Cairo variable font not requested after page load'
assert 'display=swap' in js
assert 'window.addEventListener("load"' in js, 'Remote font must load AFTER app load event'
assert 'fonts.googleapis.com' not in html, 'Blocking remote font stylesheet prevents offline shell loading'
assert '--font-ui:' in css and '"Cairo"' in css
assert 'font-family:var(--font-ui)' in css
assert '.metric-number' in css and 'font-variant-numeric:tabular-nums' in css
assert 'https://fonts.googleapis.com' in app and 'https://fonts.gstatic.com' in app
assert 'object-src \'none\'' in app and "frame-ancestors 'none'" in app
print('PASS: G3J Cairo variable font and restricted CSP')
