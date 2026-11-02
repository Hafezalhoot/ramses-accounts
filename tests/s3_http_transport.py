"""Test-only TestClient-compatible transport to a genuine Uvicorn HTTP server.

Financial test code stays unchanged; SQLite is disposable and initialized
by each existing test before constructing a client. No TLS/browser claim.
"""
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from threading import Lock

import requests

ROOT = Path(__file__).resolve().parents[1]
_guard = Lock()
_process = None
_base_url = None
_log = None
_counts = {'http_requests': 0}


def _start_server():
    global _process, _base_url, _log
    with _guard:
        if _process is not None:
            assert _process.poll() is None, 'Uvicorn child unexpectedly stopped'
            return
        path = os.getenv('RAMSES_DB_PATH', '')
        assert path and Path(path).is_file(), 'The synthetic DB must exist before local HTTP boot'
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        _base_url = f'http://127.0.0.1:{port}'
        env = os.environ.copy()
        env['RAMSES_ENVIRONMENT'] = 'staging'
        env['RAMSES_SECURE_COOKIES'] = '0'  # browser/TLS gate remains open
        _log = tempfile.TemporaryFile(mode='w+t', encoding='utf-8')
        _process = subprocess.Popen(
            [sys.executable, '-m', 'uvicorn', 'app:app', '--host', '127.0.0.1',
             '--port', str(port), '--log-level', 'warning', '--no-access-log'],
            cwd=ROOT, env=env, stdout=_log, stderr=subprocess.STDOUT)
        probe = requests.Session()
        probe.trust_env = False
        for _ in range(120):
            if _process.poll() is not None:
                break
            try:
                response = probe.get(_base_url + '/health', timeout=.5)
                if response.status_code == 200:
                    print(f'S3 HTTP Uvicorn subprocess={_process.pid} ready on 127.0.0.1', flush=True)
                    return
            except requests.RequestException:
                pass
            time.sleep(.1)
        _log.seek(0)
        trace = _log.read()[-1600:]
        raise RuntimeError(f'HTTP Uvicorn readiness failure; child exit={_process.poll()}; {trace}')


class RemoteTestClient(requests.Session):
    """Translate source TestClient get/post/request to real network requests."""

    def __init__(self, _app=None, **_ignored):
        super().__init__()
        self.trust_env = False  # avoid accidental corporate proxy for loopback
        _start_server()

    def request(self, method, url, **kwargs):
        if url.startswith('/'):
            url = _base_url + url
        elif not url.startswith(_base_url + '/'):
            raise ValueError('S3 test transport must stay on its local Uvicorn host')
        _counts['http_requests'] += 1
        kwargs.setdefault('timeout', 25)
        verbose = os.getenv('S3_HTTP_TRACE') == '1'
        t0 = time.monotonic()
        if verbose:
            print(f'S3_HTTP_START {_counts["http_requests"]} {method} {url.split("127.0.0.1:",1)[-1].split("/",1)[-1]}', flush=True)
        try:
            response = super().request(method, url, **kwargs)
            if verbose:
                print(f'S3_HTTP_END {_counts["http_requests"]} {response.status_code} {time.monotonic()-t0:.3f}s', flush=True)
            return response
        except Exception as exc:
            if verbose:
                print(f'S3_HTTP_ERROR {type(exc).__name__} {time.monotonic()-t0:.3f}s', flush=True)
            raise


def transport_info():
    return {'http_requests': _counts['http_requests'],
            'server_process': _process.pid if _process is not None else None,
            'server_exit': _process.poll() if _process is not None else None,
            'transport': 'requests.Session real TCP HTTP to Uvicorn',
            'tls': False, 'chromium_http': False, 'synthetic_database': True}


def shutdown_server():
    global _process, _base_url, _log
    with _guard:
        if _process is not None:
            if _process.poll() is None:
                _process.terminate()
                try:
                    _process.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    _process.kill()
                    _process.wait(timeout=6)
            _process = None
            _base_url = None
        if _log is not None:
            _log.close()
            _log = None
