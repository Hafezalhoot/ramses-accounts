"""Run the source-owned S8 effective-dated shift test over real local Uvicorn HTTP.

No browser, HTTPS or hospital network claim; disposable synthetic SQLite only.
"""
import os
import runpy
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT),str(ROOT / 'tests')]


def main():
    os.environ['RAMSES_ENVIRONMENT'] = 'staging'
    os.environ['RAMSES_SECURE_COOKIES'] = '0'
    from s3_http_transport import RemoteTestClient, shutdown_server, transport_info
    import fastapi.testclient
    try:
        with patch.object(fastapi.testclient, 'TestClient', RemoteTestClient):
            runpy.run_path(str(ROOT / 'tests/test_s8_historical_shift_identity.py'),
                           run_name='s8_real_http')['run']()
        info = transport_info()
        assert info['http_requests'] >= 11, info
        print(f"PASS S8 real local Uvicorn HTTP: {info['http_requests']} requests, "
              'historical shift identity and authorization checked')
    finally:
        shutdown_server()


if __name__=='__main__':
    main()
