"""Read-only smoke check for the Render staging site. No credentials and no writes."""
from __future__ import annotations

import json
import sys
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def inspect(base: str) -> None:
    url = urlparse(base.rstrip('/'))
    if url.scheme != 'https' or not url.netloc or url.username or url.password:
        raise SystemExit('Use an HTTPS staging URL without credentials')

    def get(path):
        try:
            with urlopen(Request(base.rstrip('/') + path, headers={'User-Agent': 'Ramses-Staging-Smoke/1'}), timeout=10) as response:
                return response.status, response.headers, response.read(12000)
        except HTTPError as error:
            return error.code, error.headers, error.read(12000)

    status, headers, body = get('/health')
    assert status == 200, f'Health endpoint not ready: HTTP {status}'
    assert json.loads(body)['status'] == 'ok', 'Unexpected health response'
    assert headers.get('Strict-Transport-Security'), 'HSTS is missing'
    assert headers.get('X-Frame-Options') == 'DENY', 'Framing protection missing'
    assert 'frame-ancestors' in headers.get('Content-Security-Policy', ''), 'CSP is missing'
    status, _, _ = get('/api/vouchers')
    assert status == 401, f'Unauthenticated ledger access: HTTP {status}'
    status, _, _ = get('/api/sync-status')
    assert status == 401, f'Unauthenticated sync access: HTTP {status}'
    print('PASS: HTTPS, ledger readiness, security headers and private APIs')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python smoke_test.py https://service.onrender.com')
    inspect(sys.argv[1])
