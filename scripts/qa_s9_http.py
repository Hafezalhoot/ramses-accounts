"""Execute S9 cashier shift-date test over real loopback Uvicorn HTTP.

All requests use synthetic single-use SQLite; never hospital LAN or TLS.
"""
import os
import runpy
import sys
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]


def main():
    os.environ['RAMSES_ENVIRONMENT']='staging'
    os.environ['RAMSES_SECURE_COOKIES']='0'
    from s3_http_transport import RemoteTestClient, shutdown_server, transport_info
    import fastapi.testclient
    try:
        with patch.object(fastapi.testclient,'TestClient',RemoteTestClient):
            runpy.run_path(str(ROOT/'tests/test_s9_shift_open_options.py'),
                           run_name='s9_real_http')['run']()
        info=transport_info()
        assert info['http_requests']>=20,info
        print('PASS S9 real local Uvicorn HTTP:',info['http_requests'],'requests')
    finally:
        shutdown_server()


if __name__=='__main__':
    main()
