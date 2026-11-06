"""Disposable Docker API transport, adapted from the verified Mac QA v2.4.

No host binds, tokens or Docker socket enter the test containers.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import re
import subprocess
import uuid

LABEL = 'com.ramses.fallback=isolated-test'


def call(args, timeout=30):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError('Docker transport failed; raw output kept private')
    return p.stdout.strip()


def name():
    return 'ramses-fallback-' + uuid.uuid4().hex


def command(volume, args, *, image_ref='ramses-qa-fallback:v1', container_name=None):
    if not re.fullmatch(r'ramses-fallback-work-[a-f0-9]{32}', str(volume)):
        raise ValueError('Only a disposable QA volume is allowed')
    result = ['docker', 'run', '--rm', '--init', '--network', 'none', '--read-only',
              '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
              '--pids-limit', '256', '--memory', '4g', '--cpus', '3', '--shm-size', '256m',
              '--tmpfs', '/tmp:rw,nosuid,size=512m',
              '--tmpfs', f'/work:rw,nosuid,size=512m,uid={os.getuid()},gid={os.getgid()},mode=0700',
              '--user', f'{os.getuid()}:{os.getgid()}',
              '--mount', f'type=volume,src={volume},dst=/work/source',
              '--workdir', '/work/source', '-e', 'CI=true', '-e', 'HOME=/tmp',
              '-e', 'PYTHONUNBUFFERED=1', '-e', 'PYTHONDONTWRITEBYTECODE=1']
    if container_name:
        if not re.fullmatch(r'ramses-fallback-[a-f0-9]{32}', container_name):
            raise ValueError('Invalid owned container')
        result += ['--name', container_name, '--label', LABEL]
    return [*result, image_ref, *args]


def remove_container(container):
    if not re.fullmatch(r'ramses-fallback-[a-f0-9]{32}', container):
        raise ValueError('Refusing unrelated container cleanup')
    try:
        call(['docker', 'rm', '--force', container])
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        pass


@contextmanager
def workspace(checkout: Path, image_ref: str):
    volume = 'ramses-fallback-work-' + uuid.uuid4().hex
    keeper = name()
    try:
        call(['docker', 'volume', 'create', '--label', LABEL, '--driver', 'local',
              '--opt', 'type=tmpfs', '--opt', 'device=tmpfs', '--opt',
              f'o=size=1g,uid={os.getuid()},gid={os.getgid()},mode=0700', volume])
        args = command(volume, ['python', '-c', 'import time; time.sleep(15000)'],
                       image_ref=image_ref, container_name=keeper)
        call([*args[:2], '--detach', *args[2:]])
        call(['docker', 'cp', '--archive', str(checkout) + '/.', keeper + ':/work/source/'], 180)
        yield volume, keeper
    finally:
        remove_container(keeper)
        try:
            call(['docker', 'volume', 'rm', volume])
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            pass


def export_report(keeper, destination):
    destination.unlink(missing_ok=True)
    code = ('from pathlib import Path; import stat; p=Path("/work/source/QA_G2T_TEST_RESULTS.tsv"); '
            'assert not p.is_symlink() and p.is_file(); '
            'assert stat.S_ISREG(p.stat().st_mode) and p.stat().st_size<=2097152')
    try:
        call(['docker', 'exec', keeper, 'python', '-c', code])
        call(['docker', 'cp', keeper + ':/work/source/QA_G2T_TEST_RESULTS.tsv', str(destination)])
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        destination.unlink(missing_ok=True)
