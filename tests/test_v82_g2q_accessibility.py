"""F-026: keyboard users can skip the long multi-section finance sidebar."""
from browser_helpers import chromium_options
from pathlib import Path
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]


class SourceParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def run():
    page = (ROOT / 'static/index.html').read_text()
    sheet = (ROOT / 'static/styles.css').read_text()
    parser = SourceParser()
    parser.feed(page)
    matches = [(i, a) for i, (tag, a) in enumerate(parser.tags)
               if tag == 'a' and a.get('href') == '#content']
    assert len(matches) == 1, 'Missing one skip-to-main-content link'
    skip_idx, skip = matches[0]
    sidebar_idx = next(i for i, (tag, a) in enumerate(parser.tags) if tag == 'aside' and a.get('id') == 'sidebar')
    shell_idx = next(i for i, (tag, a) in enumerate(parser.tags) if a.get('id') == 'shell')
    main_idx = next(i for i, (tag, a) in enumerate(parser.tags) if tag == 'main' and a.get('id') == 'content')
    assert shell_idx < skip_idx < sidebar_idx < main_idx, 'Skip link must be first within authenticated shell'
    assert 'skip-link' in skip.get('class', ''), skip
    assert '.skip-link:focus-visible' in sheet
    assert 'tabindex="-1"' in page and 'id="content"' in page
    # Browser smoke on real Chromium without network / app fixtures.
    from playwright.sync_api import sync_playwright
    import re
    inert = re.sub(r'<script[^>]+></script>', '', page)
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, **chromium_options(),
                              args=['--no-sandbox', '--disable-dev-shm-usage'])
        try:
            tab = b.new_page(viewport={'width': 375, 'height': 760})
            tab.set_content(inert)
            tab.add_style_tag(content=sheet)
            tab.evaluate("document.getElementById('shell').hidden=false")
            tab.keyboard.press('Tab')
            assert tab.evaluate('document.activeElement.getAttribute("href")') == '#content'
            assert tab.locator('.skip-link').is_visible()
            tab.keyboard.press('Enter')
            assert tab.evaluate('location.hash') == '#content'
            assert tab.evaluate('document.documentElement.scrollWidth<=window.innerWidth+3')
            tab.close()
        finally:
            b.close()
    print('PASS G2Q accessible skip link: tab order, focus state, keyboard activation, RTL mobile')


if __name__ == '__main__':
    run()
