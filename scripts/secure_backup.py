"""Encrypted, authenticated off-device-capable SQLite snapshot and safe restore.

A consistent SQLite backup is made in a private temporary directory, then
AES-256-GCM encrypted with a scrypt-derived passphrase. Restore never overwrites
any destination. Backups only become valid after an isolated integrity check.

A plaintext temporary snapshot exists briefly on disk. For real hospital data,
run this only on an encrypted disk / volume, and copy the encrypted output to
independently controlled off-device storage. This is not automatic off-site sync.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import secrets
import sqlite3
import struct
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"RAMSES-SQLITE-AESGCM-V1\n"
TAG_BYTES = 16
CHUNK_BYTES = 1024 * 1024
MAX_HEADER_BYTES = 4096
KDF_N = 2**15
KDF_R = 8
KDF_P = 1


def _password(confirm=False):
    file_path = os.environ.get('RAMSES_BACKUP_PASSPHRASE_FILE', '').strip()
    if file_path:
        p = Path(file_path).expanduser().resolve(strict=True)
        if os.name == 'posix' and p.stat().st_mode & 0o077:
            raise ValueError('Passphrase file must have owner-only permissions (chmod 600)')
        raw = p.read_bytes()
        if not raw or len(raw) > 4096:
            raise ValueError('Invalid passphrase file size')
        password = raw.rstrip(b'\r\n')
    elif os.environ.get('RAMSES_BACKUP_PASSPHRASE') is not None:
        # For controlled non-interactive tests only; prefer a private passphrase file.
        password = os.environ['RAMSES_BACKUP_PASSPHRASE'].encode('utf-8')
    elif sys.stdin.isatty():
        password = getpass.getpass('Backup passphrase: ').encode('utf-8')
        if confirm and password != getpass.getpass('Confirm passphrase: ').encode('utf-8'):
            raise ValueError('Passphrases did not match')
    else:
        raise ValueError('Configure a chmod 600 RAMSES_BACKUP_PASSPHRASE_FILE for unattended use')
    if len(password) < 16:
        raise ValueError('Backup passphrase must contain at least 16 UTF-8 bytes')
    return password


def _key(password, salt, n=KDF_N, r=KDF_R, p=KDF_P):
    return Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(password)


def _sql_uri(path):
    # pathlib URI encodes reserved filename characters safely.
    return path.resolve().as_uri() + '?mode=ro'


def _verify_sqlite(path, *, legacy=False):
    if not path.is_file() or path.stat().st_size < 100:
        raise ValueError('Missing or empty SQLite snapshot')
    with sqlite3.connect(_sql_uri(path), uri=True, timeout=15) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite integrity_check failed')
        fk = db.execute('PRAGMA foreign_key_check').fetchone()
        if fk is not None:
            raise ValueError('SQLite foreign_key_check failed')
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {'users', 'vouchers', 'fund_movements'}
        if not legacy:
            required.update({'gl_journals', 'gl_lines', 'audit_log'})
        if not required.issubset(tables):
            raise ValueError('This is not a complete Ramses accounting database')
        return {table: db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] if table in tables else 0
                for table in ('users', 'vouchers', 'fund_movements', 'gl_journals')}


def _private_dir(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == 'posix' and path.stat().st_mode & 0o077:
        raise ValueError('Backup destination directory must be private (chmod 700)')
    return path


def _write_encrypted(snapshot, encrypted_path, password, *, purpose="database"):
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    checksum = hashlib.sha256()
    with snapshot.open('rb') as src:
        for chunk in iter(lambda: src.read(CHUNK_BYTES), b''):
            checksum.update(chunk)
    hdr = {'version': 1, 'purpose': purpose, 'created_utc': datetime.now(timezone.utc).isoformat(),
           'algorithm': 'AES-256-GCM', 'kdf': 'scrypt', 'kdf_n': KDF_N,
           'kdf_r': KDF_R, 'kdf_p': KDF_P, 'salt': salt.hex(),
           'nonce': nonce.hex(), 'sha256': checksum.hexdigest()}
    raw = json.dumps(hdr, separators=(',', ':'), sort_keys=True).encode('utf-8')
    prefix = MAGIC + struct.pack('>I', len(raw)) + raw
    key = _key(password, salt)
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(prefix)
    with snapshot.open('rb') as src, encrypted_path.open('xb') as dest:
        os.chmod(encrypted_path, 0o600)
        dest.write(prefix)
        for chunk in iter(lambda: src.read(CHUNK_BYTES), b''):
            dest.write(encryptor.update(chunk))
        dest.write(encryptor.finalize())
        dest.write(encryptor.tag)
        dest.flush()
        os.fsync(dest.fileno())


def _read_header(src):
    magic = src.read(len(MAGIC))
    if magic != MAGIC:
        raise ValueError('Not a Ramses encrypted backup')
    length_raw = src.read(4)
    if len(length_raw) != 4:
        raise ValueError('Backup header truncated')
    length = struct.unpack('>I', length_raw)[0]
    if length > MAX_HEADER_BYTES or length < 80:
        raise ValueError('Invalid backup header length')
    data = src.read(length)
    if len(data) != length:
        raise ValueError('Backup header truncated')
    hdr = json.loads(data)
    if (hdr.get('version') != 1 or hdr.get('algorithm') != 'AES-256-GCM'
        or hdr.get('kdf') != 'scrypt' or hdr.get('purpose', 'database') not in ('database', 'pre_upgrade')
        or (hdr.get('kdf_n'), hdr.get('kdf_r'), hdr.get('kdf_p')) != (KDF_N,KDF_R,KDF_P)):
        raise ValueError('Unsupported encrypted backup parameters')
    salt, nonce = bytes.fromhex(hdr['salt']), bytes.fromhex(hdr['nonce'])
    if len(salt) != 16 or len(nonce) != 12 or len(hdr['sha256']) != 64:
        raise ValueError('Invalid backup metadata')
    return MAGIC + length_raw + data, hdr, salt, nonce


def _decrypt(archive, snapshot, password):
    with archive.open('rb') as src:
        prefix, hdr, salt, nonce = _read_header(src)
        pos = src.tell()
        total = archive.stat().st_size
        if total <= pos + TAG_BYTES + 100:
            raise ValueError('Encrypted backup is empty or truncated')
        src.seek(-TAG_BYTES, os.SEEK_END)
        tag = src.read(TAG_BYTES)
        src.seek(pos)
        length = total - pos - TAG_BYTES
        decryptor = Cipher(algorithms.AES(_key(password, salt)), modes.GCM(nonce,tag)).decryptor()
        decryptor.authenticate_additional_data(prefix)
        checksum = hashlib.sha256()
        with snapshot.open('xb') as dest:
            os.chmod(snapshot, 0o600)
            while length:
                chunk = src.read(min(CHUNK_BYTES, length))
                if not chunk:
                    raise ValueError('Encrypted backup is truncated')
                plain = decryptor.update(chunk)
                dest.write(plain)
                checksum.update(plain)
                length -= len(chunk)
            final = decryptor.finalize()  # authenticates the entire ciphertext and header
            if final:
                dest.write(final)
                checksum.update(final)
            dest.flush()
            os.fsync(dest.fileno())
        if not secrets.compare_digest(checksum.hexdigest(), hdr['sha256']):
            raise ValueError('SQLite snapshot checksum mismatch')
        return hdr.get('purpose', 'database')


def create_preupgrade(connection, output_dir, name):
    """Create and verify a one-time encrypted rollback for a *connected* old schema.

    A temporary plaintext SQLite snapshot is confined to a private directory,
    then removed. Operators must use an encrypted volume for real hospital data.
    No migration may proceed if encryption or verification fails.
    """
    if Path(name).name != name or not name.endswith('.rbe'):
        raise ValueError('Invalid encrypted backup filename')
    password = _password()  # Before creating any durable file; fail closed.
    output_dir = _private_dir(Path(output_dir).expanduser().resolve())
    with tempfile.TemporaryDirectory(prefix='.ramses-upgrade-', dir=output_dir) as work:
        snapshot = Path(work)/'snapshot.sqlite3'
        with sqlite3.connect(snapshot) as copy:
            connection.backup(copy)  # Consistent also when source uses WAL.
        os.chmod(snapshot, 0o600)
        before = _verify_sqlite(snapshot, legacy=True)
        archive = Path(work)/'backup.rbe'
        _write_encrypted(snapshot, archive, password, purpose='pre_upgrade')
        check = Path(work)/'verified.sqlite3'
        if _decrypt(archive, check, password) != 'pre_upgrade':
            raise ValueError('Invalid upgrade archive purpose')
        if _verify_sqlite(check, legacy=True) != before:
            raise ValueError('Upgrade backup content mismatch')
        target = output_dir/name
        os.link(archive, target)  # O_EXCL-like publication; cannot clobber.
        os.chmod(target, 0o600)
        return target


def create(source, output_dir):
    source = source.expanduser().resolve(strict=True)
    output_dir = _private_dir(output_dir.expanduser().resolve())
    password = _password(confirm=True)
    if not source.is_file():
        raise ValueError('Source SQLite database not found')
    with tempfile.TemporaryDirectory(prefix='.ramses-backup-',dir=output_dir) as work:
        snapshot = Path(work)/'snapshot.sqlite3'
        with sqlite3.connect(_sql_uri(source), uri=True, timeout=30) as db, sqlite3.connect(snapshot) as copy:
            db.backup(copy)
        os.chmod(snapshot,0o600)
        before = _verify_sqlite(snapshot)
        name = 'ramses-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + secrets.token_hex(4) + '.rbe'
        tmp = Path(work)/'backup.rbe'
        _write_encrypted(snapshot,tmp,password)
        # Validate the actual encrypted bytes *before* publishing an archive.
        check = Path(work)/'verified.sqlite3'
        _decrypt(tmp,check,password)
        assert _verify_sqlite(check) == before
        destination = output_dir/name
        os.link(tmp,destination)  # no overwrite, same-volume atomic publication
        os.chmod(destination,0o600)
        return destination


def verify_or_restore(archive, output_file=None):
    archive = archive.expanduser().resolve(strict=True)
    password = _password()
    target = output_file.expanduser().absolute() if output_file else None
    if target is not None and target.exists():
        raise ValueError('Refusing to overwrite an existing database; choose a new destination')
    parent = target.parent if target else None
    if parent and not parent.is_dir():
        raise ValueError('Restore destination directory does not exist')
    with tempfile.TemporaryDirectory(prefix='.ramses-restore-',dir=parent) as work:
        snapshot = Path(work)/'restored.sqlite3'
        purpose = _decrypt(archive,snapshot,password)
        summary = _verify_sqlite(snapshot, legacy=(purpose == 'pre_upgrade'))
        if target:
            # Atomic, no-clobber publish. Never replace a live or historical DB.
            os.link(snapshot,target)
            os.chmod(target,0o600)
        return summary


def cli(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    make = sub.add_parser('create', help='Create a verified encrypted SQLite backup')
    make.add_argument('--db', type=Path, help='SQLite source (defaults to RAMSES_DB_PATH)')
    make.add_argument('--output-dir', required=True, type=Path, help='Private destination; copy the resulting file off-device')
    verify = sub.add_parser('verify', help='Decrypt and integrity-check in temporary isolation')
    verify.add_argument('--input', required=True, type=Path)
    restore = sub.add_parser('restore', help='Restore only to a new, nonexistent SQLite file')
    restore.add_argument('--input', required=True, type=Path)
    restore.add_argument('--output-file', required=True, type=Path)
    args=p.parse_args(argv)
    try:
        if args.command=='create':
            if args.db is None:
                sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
                from bootstrap import DB
                args.db=DB
            path=create(args.db,args.output_dir)
            print('PASS encrypted backup created and verified:',path)
            print('NEXT: Copy this .rbe file to secured off-device storage and rehearse restore regularly.')
        else:
            summary=verify_or_restore(args.input, args.output_file if args.command=='restore' else None)
            print('PASS authenticated '+('restore' if args.command=='restore' else 'verification')+': '+json.dumps(summary,sort_keys=True))
            if args.command=='restore':
                print('Restored to a new path:',args.output_file)
    except (ValueError, OSError, sqlite3.Error, InvalidTag, json.JSONDecodeError) as error:
        # Do not log passwords, patient info, raw SQL or original binary data.
        if isinstance(error, InvalidTag):
            print('FAIL: Wrong passphrase or tampered encrypted backup',file=sys.stderr)
        else:
            print('FAIL: '+str(error),file=sys.stderr)
        return 1
    return 0

if __name__=='__main__':
    raise SystemExit(cli())
