"""G3J typography retained; S13 serves licensed Cairo without external fonts."""
from pathlib import Path
from html.parser import HTMLParser
import re
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
html=(ROOT/'static/index.html').read_text(encoding='utf-8')
css=(ROOT/'static/styles.css').read_text(encoding='utf-8')
app=(ROOT/'app.py').read_text(encoding='utf-8')
js=(ROOT/'static/app.js').read_text(encoding='utf-8')
from app import app as application
from fastapi.testclient import TestClient
client=TestClient(application)
class Styles(HTMLParser):
    links=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='link' and attrs.get('rel')=='stylesheet':self.links.append(attrs['href'])
page=client.get('/')
assert page.status_code==200
parser=Styles();parser.feed(page.text)
assert parser.links and all(link.startswith('/static/') for link in parser.links)
font_css='\n'.join(client.get(link).text for link in parser.links)
fonts=re.findall(r"url\(['\"]?(\./Cairo-[^)'\"]+)",font_css)
assert len(fonts)==3,'The app must link its local Cairo font faces'
for font in fonts:
    response=client.get('/static/fonts/'+font.removeprefix('./'))
    assert response.status_code==200 and response.content[:4]==b'\x00\x01\x00\x00',font
license=client.get('/static/fonts/OFL-Cairo.txt')
assert license.status_code==200 and 'SIL OPEN FONT LICENSE' in license.text
assert '--font-ui:' in css and '"Cairo"' in css
assert 'font-family:var(--font-ui)' in css
assert '.metric-number' in css and 'font-variant-numeric:tabular-nums' in css
assert 'https://fonts.googleapis.com' in app and 'https://fonts.gstatic.com' in app
assert 'object-src \'none\'' in app and "frame-ancestors 'none'" in app
print('PASS: G3J/S13 typography hierarchy, same-origin licensed Cairo assets and restricted CSP')
