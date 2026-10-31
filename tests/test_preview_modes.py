"""Archived June and fabricated transactions stay in different SQLite databases."""
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def launch(root, flag):
    with socket.socket() as check:
        check.bind(('127.0.0.1',0)); port=check.getsockname()[1]
    p=subprocess.Popen([sys.executable,str(root/'scripts/free_preview.py'),
                        '--local-only',flag,'--port',str(port)],cwd=root,
                       stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    try:
        for _ in range(120):
            if p.poll() is not None:
                raise RuntimeError('Preview exited on '+flag+' with '+str(p.returncode)+'\n'+p.stdout.read()[-2400:])
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=1) as r:
                    if r.status==200:return p
            except (TimeoutError,OSError):
                time.sleep(0.1)
        raise RuntimeError('Preview readiness failure on '+flag)
    except BaseException:
        p.terminate()
        try:p.communicate(timeout=5)
        except subprocess.TimeoutExpired:p.kill();p.communicate(timeout=5)
        raise


def stop(p):
    p.terminate()
    try:out,_=p.communicate(timeout=8)
    except subprocess.TimeoutExpired:
        p.kill();out,_=p.communicate(timeout=5)
        raise AssertionError('Preview process did not stop on SIGTERM')
    assert 'Traceback' not in out, out[-1500:]


def run():
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)/'ramses_accounts';root.mkdir()
        for f in (*[item.name for item in ROOT.glob('*.py')], 'schema.sql'):
            shutil.copy2(ROOT/f,root/f)
        for folder in ('static','scripts'):
            shutil.copytree(ROOT/folder,root/folder,ignore=shutil.ignore_patterns('__pycache__'))
        (root/'imports').mkdir()
        shutil.copy2(ROOT/'imports/REDACTED_JUNE_2026_PREVIEW.xlsx',root/'imports/REDACTED_JUNE_2026_PREVIEW.xlsx')
        archive=launch(root,'--archive')
        stop(archive)
        with sqlite3.connect(root/'data/free-preview-archive.sqlite3') as c:
            assert c.execute('SELECT count(*) FROM legacy_entries').fetchone()[0]==618
            assert c.execute('SELECT count(*) FROM vouchers').fetchone()[0]==0
        demo=launch(root,'--demo')
        stop(demo)
        with sqlite3.connect(root/'data/free-preview.sqlite3') as c:
            assert c.execute('SELECT count(*) FROM legacy_entries').fetchone()[0]==0
            assert c.execute('SELECT count(*) FROM vouchers').fetchone()[0]==3
        with sqlite3.connect(root/'data/free-preview-archive.sqlite3') as c:
            assert c.execute('SELECT count(*) FROM vouchers').fetchone()[0]==0
        sys.path.insert(0,str(root/'scripts'))
        from preview_doctor import run as doctor
        ok,issues=doctor(root=root)
        assert ok,issues
    print('PASS - 618 anonymized June entries and 3 dummy vouchers stay isolated across first-run modes')

if __name__=='__main__':run()
