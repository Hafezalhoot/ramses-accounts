"""Exercise S12 upload and missing-storage gates over real loopback HTTP.

Stream instrumentation inside the upload regression remains an in-process
ASGI probe; ordinary upload/auth/readiness requests use genuine TCP HTTP.
"""
import argparse
import os
from pathlib import Path
import runpy
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TESTS = ('test_s12_request_limits.py', 'test_s12_runtime_database.py')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test', choices=TESTS)
    args = parser.parse_args()
    if not args.test:
        for test in TESTS:
            subprocess.run([sys.executable, str(Path(__file__).resolve()), '--test', test],
                           cwd=ROOT, check=True, timeout=110)
        return
    sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
    os.environ.update(RAMSES_ENVIRONMENT='staging', RAMSES_SECURE_COOKIES='0')
    from s3_http_transport import RemoteTestClient, shutdown_server, transport_info
    import fastapi.testclient
    try:
        with patch.object(fastapi.testclient, 'TestClient', RemoteTestClient):
            runpy.run_path(str(ROOT/'tests'/args.test), run_name='s12_real_http')['run']()
        info = transport_info()
        assert info['http_requests'] > 0, info
        print('PASS S12 local Uvicorn HTTP:', args.test, info, flush=True)
    finally:
        shutdown_server()


if __name__ == '__main__':
    main()
