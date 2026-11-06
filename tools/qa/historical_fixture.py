"""Pinned, user-supplied historical source; never extract or run it on macOS."""
from __future__ import annotations

import hashlib
import io
from pathlib import Path, PurePosixPath
import stat
import zipfile

ARCHIVE_NAME = 'Ramses_Accounts_V8_0_Double_Entry_Decision_Foundation.zip'
ARCHIVE_SHA256 = '4a4db9de12b3f21b93310248cfa0b3c000c750d8bcf13561db3a361924fa62cb'
SCHEMA_SHA256 = 'b5d8dc311941178163668e525ed21c51dca1afe219814ad523a7e3d0ec6eb3c6'
MAX_BYTES = 4 * 1024 * 1024


def validated_archive(path: Path) -> tuple[bytes, dict]:
    if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('Original V8.0 fixture must be a regular non-symlink file')
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('Original V8.0 archive exceeds the bounded fixture size')
    with path.open('rb') as stream:
        payload = stream.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES or hashlib.sha256(payload).hexdigest() != ARCHIVE_SHA256:
        raise ValueError('Original V8.0 archive SHA256 mismatch')
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            entries = archive.infolist()
            if len(entries) > 2048 or sum(i.file_size for i in entries) > 16 * 1024 * 1024:
                raise ValueError('Historical fixture ZIP exceeds its expanded limits')
            schemas = []
            for entry in entries:
                member = PurePosixPath(entry.filename)
                if (member.is_absolute() or '..' in member.parts or '\\' in entry.filename
                        or stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1
                        or member.suffix.lower() in {'.db', '.sqlite', '.sqlite3', '.rbe', '.pem', '.p12'}
                        or member.name.startswith('.env') and member.name != '.env.example'
                        or any(part.lower() in {'private', 'secrets', 'backups', 'data'} for part in member.parts)):
                    raise ValueError('Unsafe or private member in historical source ZIP')
                if member.name == 'schema.sql':
                    schemas.append(entry)
            if len(schemas) != 1 or archive.testzip() is not None:
                raise ValueError('Historical source must contain exactly one intact schema.sql')
            schema_hash = hashlib.sha256(archive.read(schemas[0])).hexdigest()
            if schema_hash != SCHEMA_SHA256:
                raise ValueError('Original V8.0 schema SHA256 mismatch')
    except zipfile.BadZipFile as exc:
        raise ValueError('Invalid historical source ZIP') from exc
    return payload, {'archive_name': ARCHIVE_NAME, 'archive_sha256': ARCHIVE_SHA256,
                     'schema_sha256': SCHEMA_SHA256, 'bytes': len(payload), 'entries': len(entries)}


def stage_archive(checkout: Path, archive: Path) -> dict:
    payload, metadata = validated_archive(archive)
    directory = checkout / 'tests' / 'fixtures'
    if (checkout / 'tests').is_symlink() or directory.is_symlink():
        raise ValueError('Refusing a symlink fixture destination')
    destination = directory / ARCHIVE_NAME
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Existing project fixture must not be overwritten')
    directory.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as stream:
        stream.write(payload)
    destination.chmod(0o600)
    return metadata
