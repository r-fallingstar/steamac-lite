#!/usr/bin/env python3
"""Build two private Wine media modules, retaining checked source and evidence.

Local receipts detect stale or changed inputs, not an untrusted build machine.
Only the fixed recipe below can create a receipt; arbitrary DLLs are not blessed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
FILENAMES = ('mfmediaengine.dll', 'winegstreamer.dll')
LICENSES = ('NOTICE', 'COPYING.LIB')
INPUTS = ('guest/media/wine-source.json', 'guest/media/NOTICE',
          'guest/media/COPYING.LIB', 'guest/media/build-runtime.sh',
          'guest/media/patches/0001-mediaengine-playback-and-frame-transfer.patch',
          'guest/media/patches/0002-winegstreamer-nv12-memory-fallback.patch',
          'scripts/lite/record-media-build.py', 'scripts/lite/stage-media.py',
          'guest/media/Dockerfile')
RECIPE = '''#!/bin/sh
set -eu
export LC_ALL=C TZ=UTC SOURCE_DATE_EPOCH=1767225600
dpkg-query -W -f='${Package}\\t${Version}\\t${Architecture}\\n' > /input/evidence/packages.tsv
x86_64-w64-mingw32-gcc --version > /input/evidence/compiler.txt
x86_64-w64-mingw32-strip --version > /input/evidence/strip.txt
cd /input/source
for p in /input/patches/*.patch; do patch --batch --forward -p1 -F0 < "$p"; done
python3 dlls/winevulkan/make_vulkan -x /input/source/dlls/winevulkan/vk.xml -X /input/source/dlls/winevulkan/video.xml
./tools/make_requests
./tools/make_specfiles
# Both patches change existing files only; the archive's tracked Makefile.in
# inventories remain valid and need no git-dependent inventory regeneration.
autoreconf -f
mkdir /input/build
cd /input/build
../source/configure --enable-archs=x86_64 --with-mingw=gcc --without-x --without-wayland \\
    --without-alsa --without-pulse --without-dbus --without-fontconfig --without-freetype \\
    --without-gstreamer --without-v4l2 --without-vulkan --disable-tests --enable-winegstreamer
make -j2 dlls/mfmediaengine/x86_64-windows/mfmediaengine.dll dlls/winegstreamer/x86_64-windows/winegstreamer.dll
for name in mfmediaengine winegstreamer; do
    cp "dlls/$name/x86_64-windows/$name.dll" /input/output/
    x86_64-w64-mingw32-strip --strip-debug "/input/output/$name.dll"
    x86_64-w64-mingw32-objdump -p "/input/output/$name.dll" > "/input/evidence/$name.dll.pe.txt"
done
'''


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def regular(path):
    require(path.is_file() and not path.is_symlink(), 'Expected regular file: ' + str(path))
    return path


def input_hashes(root):
    return {name: digest(regular(root / name)) for name in INPUTS}


def read_pin(root):
    p = json.loads(regular(root / INPUTS[0]).read_text())
    require(p['schema'] == 1 and re.fullmatch(r'[0-9a-f]{40}', p['commit']), 'Invalid Wine source pin')
    require(re.fullmatch(r'[0-9a-f]{64}', p['archive_sha256']), 'Invalid archive checksum')
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', p['builder_image_id']), 'Invalid builder image ID')
    require(set(p['stock_files']) == {'files/lib/wine/x86_64-windows/' + n for n in FILENAMES},
            'Unexpected media module set')
    for name, sha in p['patches'].items():
        require(name in INPUTS and digest(regular(root / name)) == sha, 'Changed pinned patch: ' + name)
    return p


def inspect_pe(path):
    b = regular(path).read_bytes()
    require(256 <= len(b) <= 16 * 1024**2 and b[:2] == b'MZ', 'Invalid media PE size/header')
    offset = struct.unpack_from('<I', b, 0x3c)[0]
    require(offset + 26 <= len(b) and b[offset:offset+4] == b'PE\0\0'
            and struct.unpack_from('<H', b, offset+4)[0] == 0x8664
            and struct.unpack_from('<H', b, offset+24)[0] == 0x20b, 'Media module must be PE32+ x86_64')
    require(b'Wine builtin DLL' in b[64:96], 'Media module is not a Wine builtin')
    require(b'MF_DIAG' not in b and b'WINE_MF_DIAGNOSTICS' not in b, 'Diagnostic module cannot be distributed')


def archive_sources(path, pin, destination=None):
    require(digest(regular(path)) == pin['archive_sha256'], 'Wine source archive mismatch')
    prefix = 'wine-' + pin['commit']
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        require(members and len(members) < 120000, 'Unexpected Wine archive inventory')
        for member in members:
            parts = PurePosixPath(member.name).parts
            require(parts and parts[0] == prefix and '..' not in parts
                    and not member.name.startswith('/'), 'Unsafe Wine archive path')
            require(member.isfile() or member.isdir() or member.issym() or member.islnk(),
                    'Unexpected source archive member')
        for name, expected in pin['source_files'].items():
            member = archive.getmember(prefix + '/' + name)
            require(member.isfile() and hashlib.sha256(archive.extractfile(member).read()).hexdigest()
                    == expected['stock_sha256'], 'Pinned source file mismatch: ' + name)
        if destination is not None:
            archive.extractall(destination, filter='data')
            return destination / prefix


def verify_runtime(runtime, root=ROOT):
    pin = read_pin(root)
    receipt = json.loads(regular(runtime / 'build.json').read_text())
    require(receipt.get('schema') == 1 and receipt.get('source') == pin,
            'Rebuild private media modules for the current source pin')
    require(receipt.get('inputs') == input_hashes(root), 'Media build inputs changed; rebuild required')
    require(regular(runtime / 'recipe.sh').read_text() == RECIPE, 'Media recipe changed')
    require(set(receipt.get('files', {})) == set(FILENAMES), 'Unexpected media payload inventory')
    require(receipt.get('source_version_sha256') == pin['source_version_sha256']
            and receipt.get('stock_files') == pin['stock_files'], 'Unsupported Proton media ABI')
    archive_sources(runtime / 'wine-source.tar.gz', pin)
    for name, sha in pin['patches'].items():
        require(digest(regular(runtime / 'patches' / Path(name).name)) == sha,
                'Retained media patch mismatch: ' + name)
    evidence = receipt.get('evidence', {})
    expected = {'evidence/packages.tsv', 'evidence/compiler.txt', 'evidence/strip.txt',
                *(f'evidence/{name}.pe.txt' for name in FILENAMES)}
    require(set(evidence) == expected, 'Incomplete media build evidence')
    for name, sha in {**receipt['files'], **evidence}.items():
        require(digest(regular(runtime / name)) == sha, 'Media payload/evidence checksum mismatch: ' + name)
    for name in FILENAMES:
        inspect_pe(runtime / name)
        require(receipt['files'][name] != pin['stock_files']['files/lib/wine/x86_64-windows/' + name],
                'Unchanged stock media module')
    for name in LICENSES:
        require(digest(regular(runtime / name)) == digest(root / 'guest/media' / name), 'Media license mismatch')
    require(receipt.get('patched_source_files') == {n: v['patched_sha256'] for n, v in pin['source_files'].items()},
            'Patched source checksums do not match')
    require(receipt.get('builder_image_id') == pin['builder_image_id'], 'Builder identity mismatch')
    return receipt


def build(root=ROOT):
    require(subprocess.run(['pgrep', '-x', 'steamac-vm'], capture_output=True).returncode == 1,
            'Stop the SteamOS VM before building private media modules')
    pin = read_pin(root)
    before = input_hashes(root)
    work = root / 'work/media-release'
    work.mkdir(parents=True, exist_ok=True)
    archive = work / 'wine-source.tar.gz'
    if not archive.exists():
        cached = root / 'work/camera-release/wine-source.tar.gz'
        if cached.exists() and digest(cached) == pin['archive_sha256']:
            shutil.copyfile(cached, archive)
        else:
            urllib.request.urlretrieve('https://codeload.github.com/ValveSoftware/wine/tar.gz/' + pin['commit'], archive)
    image = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', pin['builder_image']], text=True).strip()
    require(image == pin['builder_image_id'], 'Media builder changed; verify SDK and source pins before rebuilding')
    with tempfile.TemporaryDirectory(prefix='build-', dir=work) as tmp:
        run = Path(tmp)
        extracted = archive_sources(archive, pin, run)
        extracted.rename(run / 'source')
        for name in ('patches', 'output', 'evidence'):
            (run / name).mkdir()
        for name in pin['patches']:
            shutil.copyfile(root / name, run / 'patches' / Path(name).name)
        (run / 'recipe.sh').write_text(RECIPE)
        with (work / 'build.log').open('w') as log:
            subprocess.run(['docker', 'run', '--rm', '--network=none', '-v', str(run) + ':/input',
                            image, 'sh', '/input/recipe.sh'], check=True, stdout=log, stderr=subprocess.STDOUT)
        patched = {name: digest(run / 'source' / name) for name in pin['source_files']}
        require(patched == {n: v['patched_sha256'] for n, v in pin['source_files'].items()},
                'Compiled source differs from pinned patch result')
        require(before == input_hashes(root), 'Media inputs changed during build')
        for name in FILENAMES:
            inspect_pe(run / 'output' / name)
        stage = run / 'runtime'
        stage.mkdir()
        for name in FILENAMES:
            shutil.copyfile(run / 'output' / name, stage / name)
        for name in LICENSES:
            shutil.copyfile(root / 'guest/media' / name, stage / name)
        shutil.copyfile(archive, stage / 'wine-source.tar.gz')
        shutil.copyfile(run / 'recipe.sh', stage / 'recipe.sh')
        shutil.copytree(run / 'patches', stage / 'patches')
        shutil.copyfile(root / 'guest/media/Dockerfile', stage / 'Dockerfile')
        shutil.copytree(run / 'evidence', stage / 'evidence')
        receipt = {'schema': 1, 'source': pin, 'inputs': before, 'builder_image_id': image,
                   'source_version_sha256': pin['source_version_sha256'], 'stock_files': pin['stock_files'],
                   'patched_source_files': patched,
                   'files': {name: digest(stage / name) for name in FILENAMES},
                   'evidence': {str(p.relative_to(stage)): digest(p) for p in sorted((stage / 'evidence').iterdir())}}
        (stage / 'build.json').write_text(json.dumps(receipt, indent=2) + '\n')
        verify_runtime(stage, root)
        output = work / 'runtime'
        require(not output.exists(), 'A media runtime already exists; keep it or move it aside before rebuilding')
        os.rename(stage, output)
    print('Built source-verified private Wine media modules: ' + json.dumps(receipt['files']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('build', 'verify'))
    args = parser.parse_args()
    if args.action == 'build':
        build()
    else:
        verify_runtime(ROOT / 'work/media-release/runtime')
        print('Private Wine media build verified')
