#!/usr/bin/env python3
"""Stage verified private Proton media DLLs and their provenance/notices."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / 'work/media-release/runtime'
DLLS = ('mfmediaengine.dll', 'winegstreamer.dll')
WINE = 'files/lib/wine/x86_64-windows/'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    checksum = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            checksum.update(chunk)
    return checksum.hexdigest()


def checked_path(base, relative='', *, directory=False):
    """Reject symlinks/special files throughout the owned part of a path."""
    path = base
    parts = PurePosixPath(relative).parts if relative else ()
    for index, part in enumerate(('', *parts)):
        if part:
            path = path / part
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            continue
        is_directory = index < len(parts) or directory
        require(stat.S_ISDIR(mode) if is_directory else stat.S_ISREG(mode),
                'Expected a real directory or regular file (no symlinks): ' + str(path))
    return path


def regular(base, relative):
    path = checked_path(base, relative)
    require(path.is_file(), 'Missing regular media file: ' + str(path))
    return path


def sha256(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def validate_receipt(receipt):
    require(isinstance(receipt, dict) and type(receipt.get('schema')) is int and
            receipt['schema'] == 1, 'Expected media build receipt schema 1')
    require(sha256(receipt.get('source_version_sha256')), 'Invalid media source version digest')
    files, stock = receipt.get('files'), receipt.get('stock_files')
    require(isinstance(files, dict) and set(files) == set(DLLS),
            'Unexpected media payload files; exactly two DLL basenames are required')
    require(isinstance(stock, dict) and set(stock) == {WINE + name for name in DLLS},
            'Unexpected media stock file paths')
    for name in DLLS:
        require(sha256(files[name]) and sha256(stock[WINE + name]) and
                files[name] != stock[WINE + name], 'Invalid media payload/stock digests: ' + name)


def load_protocol():
    spec = importlib.util.spec_from_file_location(
        'media_build_protocol', Path(__file__).with_name('record-media-build.py'))
    protocol = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(protocol)
    return protocol


def license_names(protocol):
    names = getattr(protocol, 'LICENSES', ())
    require(isinstance(names, (tuple, list)), 'Invalid media LICENSES contract')
    seen = set()
    for name in names:
        require(isinstance(name, str) and name and '\\' not in name and
                not PurePosixPath(name).is_absolute() and
                all(part not in ('', '.', '..') for part in name.split('/')),
                'Unsafe media license path')
        require(name not in seen, 'Duplicate media license path')
        seen.add(name)
    all_names = seen | {'NOTICE', 'COPYING.LIB'}
    require(all(not any(parent.as_posix() in all_names for parent in PurePosixPath(name).parents)
                for name in all_names), 'Conflicting media license paths')
    return names


def copy_checked(source, destination, expected, base):
    relative = destination.relative_to(base).as_posix()
    checked_path(base, relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Replace a directory entry, never write through an existing hard link.
    fd, temporary = tempfile.mkstemp(prefix='.media-', dir=destination.parent)
    os.close(fd)
    temporary = Path(temporary)
    try:
        shutil.copyfile(source, temporary)
        require(digest(temporary) == expected, 'Media file changed while staging: ' + str(source))
        temporary.chmod(0o644)
        checked_path(base, relative)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(destination, value, base):
    checked_path(base, destination.relative_to(base).as_posix())
    fd, temporary = tempfile.mkstemp(prefix='.media-', dir=destination.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(json.dumps(value, indent=2, sort_keys=True) + '\n')
        temporary.chmod(0o644)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def stage(layer, app, *, root=ROOT, runtime=None, _protocol=None):
    root, layer, app = Path(root), Path(layer), Path(app)
    runtime = root / 'work/media-release/runtime' if runtime is None else Path(runtime)
    protocol = load_protocol() if _protocol is None else _protocol
    # No mkdir, temporary file, copy, chmod or publication before verification.
    receipt = json.loads(json.dumps(protocol.verify_runtime(runtime, root)))
    validate_receipt(receipt)
    camera = layer / 'usr/lib/steamac/camera'
    payload = camera / 'proton-media'
    resources = app / 'Contents/Resources'
    notices = resources / 'licenses/Media'
    manifest_path = camera / 'proton-media.json'
    receipt_path = resources / 'steamac-media-build.json'
    checked_path(layer, payload.relative_to(layer).as_posix(), directory=True)
    checked_path(app, notices.relative_to(app).as_posix(), directory=True)
    checked_path(layer, manifest_path.relative_to(layer).as_posix())
    checked_path(app, receipt_path.relative_to(app).as_posix())
    if payload.exists():
        require({path.name for path in payload.iterdir()} <= set(DLLS),
                'Unexpected existing media payload files')

    copies = []
    manifest = {'schema': 1, 'source_version_sha256': receipt['source_version_sha256'], 'files': {}}
    for name in DLLS:
        source = regular(runtime, name)
        expected = receipt['files'][name]
        require(digest(source) == expected, 'Media payload checksum mismatch: ' + name)
        copies.append((source, payload / name, expected, layer))
        manifest['files'][WINE + name] = {
            'stock_sha256': receipt['stock_files'][WINE + name], 'patched_sha256': expected}

    licenses = {}
    for name in ('NOTICE', 'COPYING.LIB'):
        source = regular(root, 'guest/media/' + name)
        licenses[name] = (source, digest(source))
    for name in license_names(protocol):
        source = regular(runtime, name)
        expected = digest(source)
        require(name not in licenses or licenses[name][1] == expected,
                'Runtime license differs from guest/media: ' + name)
        licenses[name] = (source, expected)
    copies.extend((source, notices / name, expected, app)
                  for name, (source, expected) in licenses.items())
    # Preflight every destination before changing even the first one.
    for _, destination, _, base in copies:
        checked_path(base, destination.relative_to(base).as_posix())
    for source, destination, expected, base in copies:
        copy_checked(source, destination, expected, base)

    # Recheck inputs/evidence as well as payloads before publishing either JSON.
    require(protocol.verify_runtime(runtime, root) == receipt,
            'Media build receipt changed while staging')
    for _, destination, expected, base in copies:
        regular(base, destination.relative_to(base).as_posix())
        require(digest(destination) == expected, 'Staged media checksum mismatch: ' + str(destination))
    write_json(manifest_path, manifest, layer)
    write_json(receipt_path, receipt, app)
    print('Staged verified private Proton media DLLs and notices')


if __name__ == '__main__':
    stage(*map(Path, sys.argv[1:]))
