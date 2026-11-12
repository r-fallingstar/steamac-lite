#!/usr/bin/env python3
"""Build and record private FFmpeg libraries as one checked transaction.

Receipts detect stale/mutated local inputs; they are not signed attestations of an
untrusted build machine. No CLI accepts arbitrary trees or libraries to bless.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import struct
import subprocess
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
SONAMES = ('libavcodec.so.58', 'libavformat.so.58',
           'libavfilter.so.7', 'libavutil.so.56')
LICENSES = ('COPYING.LGPLv2.1', 'COPYING.GPLv2', 'LICENSE.md', 'NOTICE')
INPUTS = ('guest/video/ffmpeg-source.json', 'guest/video/NOTICE',
          'guest/video/build-codecs.sh', 'scripts/lite/record-video-build.py',
          'scripts/lite/stage-video.py')
# One canonical component list drives configure, evidence checks and receipts.
DECODERS = (
    'h264', 'hevc', 'aac', 'mp3', 'flac', 'alac', 'vorbis', 'gif', 'apng',
    'mjpeg', 'pcm_s16le', 'pcm_s16be', 'pcm_f32le', 'pcm_u8',
    'vp8', 'vp9', 'opus', 'theora', 'mpeg1video', 'mpeg2video', 'mpeg4',
    'vc1', 'wmv3', 'wmav1', 'wmav2',
)
PARSERS = ('h264', 'hevc', 'aac', 'mpegaudio', 'flac', 'vorbis',
           'vp8', 'vp9', 'opus', 'mpegvideo', 'mpeg4video', 'vc1', 'mjpeg')
DEMUXERS = ('mov', 'matroska', 'aac', 'mp3', 'flac', 'ogg', 'wav', 'ivf',
            'asf', 'flv', 'avi', 'mpegps', 'mpegts', 'mpegvideo', 'h264',
            'hevc', 'm4v', 'vc1')
CONFIGURE = (
    '--prefix=/usr', '--libdir=/usr/lib/x86_64-linux-gnu',
    '--enable-shared', '--enable-static', '--enable-pic', '--disable-autodetect',
    '--enable-zlib',  # Existing APNG support needs the pinned SDK's zlib; no external codec libraries.
    '--disable-programs', '--disable-doc', '--disable-avdevice',
    '--disable-postproc', '--disable-swscale', '--enable-swresample',
    '--disable-everything', '--enable-decoder=' + ','.join(DECODERS),
    '--enable-parser=' + ','.join(PARSERS),
    '--enable-demuxer=' + ','.join(DEMUXERS), '--enable-protocol=file',
)
# Built-in Opus requires swresample. Embed its PIC static archive in avcodec
# rather than adding/replacing a fifth shared library in the private tool.
# These make overrides preserve FFmpeg's built-in avutil + system dependencies.
MAKE_OVERRIDES = (
    'avcodec_FFLIBS=avutil',
    'EXTRALIBS-avcodec=/build/libswresample/libswresample.a -pthread -lm -latomic -lz',
)
DYNAMIC_EVIDENCE = tuple(name + '.dynamic.txt' for name in SONAMES)

ENVIRONMENT = ('PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
               'HOME=/tmp', 'LC_ALL=C', 'TZ=UTC', 'DEBIAN_FRONTEND=noninteractive')
EVIDENCE = ('config.h', 'config.mak', 'packages.tsv', 'compiler.txt',
            'linker.txt', 'strip.txt', 'nasm.txt', 'machine.txt', 'libraries.sha256',
            'libswresample.a', *DYNAMIC_EVIDENCE)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    checksum = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            checksum.update(chunk)
    return checksum.hexdigest()


def object_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def regular(path):
    require(path.is_file() and not path.is_symlink(),
            'Expected a regular file: ' + str(path))
    return path


def pins(root):
    pin = json.loads(regular(root / INPUTS[0]).read_text())
    require(tuple(pin['sonames']) == SONAMES, 'Unexpected private codec SONAMEs')
    require(re.fullmatch(r'[0-9a-f]{40}', pin['commit']), 'Invalid source commit')
    require(re.fullmatch(r'[0-9a-f]{64}', pin['archive_sha256']), 'Invalid source digest')
    require(re.fullmatch(r'[^\s]+@sha256:[0-9a-f]{64}', pin['sdk_image']),
            'SDK must be pinned by immutable digest')
    require(re.fullmatch(r'[0-9A-Za-z.+:~\-]+', pin['nasm_package']), 'Invalid nasm pin')
    return pin


def input_hashes(root):
    return {name: digest(regular(root / name)) for name in INPUTS}


def recipe(pin):
    """The exact executed recipe is also retained and checked by the stager."""
    return '''#!/bin/sh
set -eu
umask 022
apt-get update -qq
apt-get install -y --no-install-recommends nasm=%s
test "$(dpkg-query -W -f='${Version}' nasm)" = %s
dpkg-query -W -f='${Package}\\t${Version}\\t${Architecture}\\n' > /evidence/packages.tsv
gcc --version > /evidence/compiler.txt
ld --version > /evidence/linker.txt
strip --version > /evidence/strip.txt
nasm -v > /evidence/nasm.txt
gcc -dumpmachine > /evidence/machine.txt
cd /build
/source/configure %s
make -j2 libswresample/libswresample.a
make -j2 %s
make DESTDIR=/install STRIP=true %s install
# Strip AFTER the final make, so dependency mtimes cannot trigger a relink.
# Process both copies, then require byte equality on the host before recording.
for name in %s; do
 strip "/build/${name%%%%.*}/$name" "$(readlink -f "/install/usr/lib/x86_64-linux-gnu/$name")"
 readelf -d "/install/usr/lib/x86_64-linux-gnu/$name" > "/evidence/$name.dynamic.txt"
done
cp libswresample/libswresample.a /evidence/libswresample.a
cp config.h /evidence/config.h
cp ffbuild/config.mak /evidence/config.mak
cd /install/usr/lib/x86_64-linux-gnu
sha256sum %s > /evidence/libraries.sha256
''' % (shlex.quote(pin['nasm_package']), shlex.quote(pin['nasm_package']),
       shlex.join(CONFIGURE), shlex.join(MAKE_OVERRIDES),
       shlex.join(MAKE_OVERRIDES), shlex.join(SONAMES), shlex.join(SONAMES))


def archive_inventory(archive, pin, destination=None):
    """Check archive identity and safe members; optionally extract into a NEW tree."""
    require(digest(regular(archive)) == pin['archive_sha256'], 'Source archive checksum mismatch')
    if destination is not None:
        # No reuse of an existing extracted or generated source tree, even empty.
        destination.mkdir()
    prefix = 'FFmpeg-' + pin['commit']
    entries = {}
    total = 0
    with tarfile.open(archive, 'r:gz') as stream:
        for member in stream:
            parts = PurePosixPath(member.name).parts
            require(parts and parts[0] == prefix and '..' not in parts and
                    not member.name.startswith('/') and '\\' not in member.name,
                    'Unsafe source archive path')
            require(member.isfile() or member.isdir(), 'Source archive contains a link/special file')
            if len(parts) == 1:
                require(member.isdir(), 'Invalid archive root')
                continue
            name = '/'.join(parts[1:])
            require(name not in entries and len(entries) < 100000, 'Duplicate/excessive archive members')
            mode = member.mode & 0o777
            require(not member.mode & 0o7000, 'Unexpected special source mode')
            entry = {'kind': 'directory' if member.isdir() else 'file', 'mode': mode}
            total += member.size
            require(total <= 1024 ** 3, 'Source archive is too large')
            target = destination / name if destination is not None else None
            if member.isdir():
                if target is not None:
                    target.mkdir(parents=True, exist_ok=True)
                    target.chmod(mode)
            else:
                data = stream.extractfile(member)
                require(data is not None, 'Missing source archive member')
                checksum = hashlib.sha256()
                if target is not None:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open('xb') as out:
                        while chunk := data.read(1024 * 1024):
                            checksum.update(chunk)
                            out.write(chunk)
                    target.chmod(mode)
                else:
                    while chunk := data.read(1024 * 1024):
                        checksum.update(chunk)
                entry['sha256'] = checksum.hexdigest()
            entries[name] = entry
    require('configure' in entries and entries['configure']['kind'] == 'file',
            'Missing FFmpeg configure script')
    require(digest(archive) == pin['archive_sha256'], 'Source archive changed during verification')
    return entries


def tree_inventory(source):
    require(source.is_dir() and not source.is_symlink(), 'Invalid extracted source directory')
    entries = {}
    for path in sorted(source.rglob('*')):
        require(not path.is_symlink(), 'Extracted source contains a symlink')
        require(path.is_file() or path.is_dir(), 'Extracted source contains a special file')
        item = {'kind': 'directory' if path.is_dir() else 'file',
                'mode': path.stat().st_mode & 0o777}
        if path.is_file():
            item['sha256'] = digest(path)
        entries[path.relative_to(source).as_posix()] = item
    return entries


def check_elf(path):
    regular(path)
    with path.open('rb') as stream:
        header = stream.read(20)
    require(len(header) == 20 and header[:6] == b'\x7fELF\x02\x01' and
            struct.unpack_from('<H', header, 18)[0] == 62,
            'Not an x86_64 little-endian ELF library: ' + str(path))


def check_configuration(evidence):
    header = regular(evidence / 'config.h').read_text()
    def macro(name):
        matches = re.findall(r'^#define ' + re.escape(name) + r' (.+)$', header, re.M)
        require(len(matches) == 1, 'Missing/ambiguous build configuration: ' + name)
        return matches[0]
    require(shlex.split(json.loads(macro('FFMPEG_CONFIGURATION'))) == list(CONFIGURE),
            'Actual configure arguments differ from the build recipe')
    for name in ('CONFIG_GPL', 'CONFIG_NONFREE', 'CONFIG_VERSION3', 'CONFIG_GPLV3'):
        require(macro(name) == '0', 'Unexpected FFmpeg license configuration: ' + name)
    # The label is emitted only after checking the actual generated configuration.
    require(json.loads(macro('FFMPEG_LICENSE')) == 'LGPL version 2.1 or later',
            'Unexpected FFmpeg license')
    for suffix, components in (('DECODER', DECODERS), ('PARSER', PARSERS), ('DEMUXER', DEMUXERS)):
        for name in components:
            require(macro('CONFIG_' + name.upper() + '_' + suffix) == '1',
                    'Requested built-in component was disabled: ' + name + '_' + suffix)
    require(macro('CONFIG_SWRESAMPLE') == '1' and macro('CONFIG_STATIC') == '1' and
            macro('CONFIG_SHARED') == '1', 'Missing static Opus dependency build')
    mak = regular(evidence / 'config.mak').read_text()
    values = re.findall(r'^FFMPEG_CONFIGURATION=(.*)$', mak, re.M)
    require(len(values) == 1 and shlex.split(values[0]) == list(CONFIGURE),
            'Generated config.mak does not match the recipe')
    return 'LGPL-2.1-or-later'


def check_evidence(evidence, pin, files):
    for name in EVIDENCE:
        require(regular(evidence / name).stat().st_size > 0, 'Empty build evidence: ' + name)
    require((evidence / 'machine.txt').read_text().strip() == 'x86_64-linux-gnu',
            'Compiler target does not match the private runtime')
    packages = [line.split('\t') for line in (evidence / 'packages.tsv').read_text().splitlines()]
    nasm = [row for row in packages if row[0] == 'nasm']
    require(nasm == [['nasm', pin['nasm_package'], 'amd64']], 'Actual nasm package does not match pin')
    rows = (evidence / 'libraries.sha256').read_text().splitlines()
    require(len(rows) == len(SONAMES), 'Incomplete build output checksums')
    recorded = {}
    for row in rows:
        match = re.fullmatch(r'([0-9a-f]{64})  (lib[^/\s]+)', row)
        require(match is not None and match[2] not in recorded, 'Invalid build output checksum')
        recorded[match[2]] = match[1]
    require(recorded == files, 'Installed libraries differ from completed build outputs')
    require(regular(evidence / 'libswresample.a').read_bytes()[:8] == b'!<arch>\n',
            'Missing built-in Opus static dependency')
    allowed = set(SONAMES) | {'libm.so.6', 'libc.so.6', 'libpthread.so.0',
                             'libatomic.so.1', 'libgcc_s.so.1', 'librt.so.1',
                             'libdl.so.2', 'libz.so.1', 'ld-linux-x86-64.so.2'}
    for name in DYNAMIC_EVIDENCE:
        dynamic = regular(evidence / name).read_text()
        needed = re.findall(r'\(NEEDED\).*\[([^\]]+)\]', dynamic)
        require(needed and set(needed) <= allowed,
                'Unexpected shared dependency (private payload must remain four libraries): ' + name)
    return check_configuration(evidence)


def verify_runtime(runtime, root=ROOT):
    """Fail closed on legacy receipts, stale recipes, or mutated runtime evidence."""
    pin = pins(root)
    receipt = json.loads(regular(runtime / 'build.json').read_text())
    require(receipt.get('schema') == 2, 'Video runtime needs a fresh verified build (schema 2)')
    require(receipt.get('source') == pin, 'Video source pins have changed')
    require(receipt.get('inputs') == input_hashes(root), 'Video build inputs/recipe have changed; rebuild required')
    require(receipt.get('configure') == list(CONFIGURE) and
            receipt.get('environment') == list(ENVIRONMENT) and
            receipt.get('make_overrides') == list(MAKE_OVERRIDES), 'Unexpected build recipe/environment')
    require(regular(runtime / 'recipe.sh').read_text() == recipe(pin), 'Executed recipe does not match current recipe')
    entries = archive_inventory(runtime / 'ffmpeg-source.tar.gz', pin)
    require(receipt.get('source_tree_sha256') == object_digest(entries), 'Source tree identity mismatch')
    expected = {*SONAMES, *LICENSES, 'recipe.sh', 'ffmpeg-source.tar.gz',
                *('evidence/' + name for name in EVIDENCE)}
    hashes = receipt.get('artifacts', {})
    require(set(hashes) == expected, 'Incomplete/unexpected video build artifacts')
    actual_paths = {p.relative_to(runtime).as_posix() for p in runtime.rglob('*') if not p.is_dir()}
    require(actual_paths == expected | {'build.json'}, 'Unexpected runtime payload files')
    for path in runtime.rglob('*'):
        require(not path.is_symlink(), 'Runtime must not contain symlinks')
    for name, sha in hashes.items():
        require(digest(regular(runtime / name)) == sha, 'Video build artifact changed: ' + name)
    files = {name: hashes[name] for name in SONAMES}
    require(receipt.get('files') == files, 'Video payload receipt mismatch')
    for name in SONAMES:
        check_elf(runtime / name)
    license_name = check_evidence(runtime / 'evidence', pin, files)
    require(receipt.get('license') == license_name and
            receipt.get('architecture') == 'x86_64-linux-gnu', 'Invalid build identity')
    # License copies must come from the verified archive, not arbitrary local files.
    for name in LICENSES[:-1]:
        require(hashes[name] == entries[name]['sha256'], 'License differs from verified source: ' + name)
    require(hashes['NOTICE'] == digest(root / 'guest/video/NOTICE'), 'Video notice changed')
    return receipt


def download_archive(path, pin):
    if path.exists():
        require(digest(regular(path)) == pin['archive_sha256'], 'Cached source archive checksum mismatch')
        return
    fd, name = tempfile.mkstemp(prefix='.download-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out, urllib.request.urlopen(
                'https://codeload.github.com/FFmpeg/FFmpeg/tar.gz/' + pin['commit'], timeout=60) as response:
            shutil.copyfileobj(response, out)
        require(digest(Path(name)) == pin['archive_sha256'], 'Downloaded source checksum mismatch')
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def build(root=ROOT):
    work = root / 'work/video-release'
    work.mkdir(parents=True, exist_ok=True)
    # Serialize publication/download without sharing any previous build tree.
    fd = os.open(work / '.build.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'r+') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('Another video codec build is already running') from error
        return _build(root, work)


def _build(root, work):
    pin = pins(root)
    before = input_hashes(root)
    archive = work / 'ffmpeg-source.tar.gz'
    download_archive(archive, pin)
    # Neither source, build nor install trees are ever reused. Failed runs retain
    # evidence for inspection, but no runtime receipt is published from them.
    run = Path(tempfile.mkdtemp(prefix='build-', dir=work))
    print('Building in fresh workspace:', run, flush=True)
    shutil.copyfile(archive, run / 'ffmpeg-source.tar.gz')
    inventory = archive_inventory(run / 'ffmpeg-source.tar.gz', pin, run / 'source')
    require(tree_inventory(run / 'source') == inventory, 'Extracted source differs from verified archive')
    for name in ('build', 'install', 'evidence'):
        (run / name).mkdir()
    (run / 'recipe.sh').write_text(recipe(pin))
    command = ['docker', 'run', '--rm', '--platform', 'linux/amd64', '--user', '0',
               '--network', 'bridge',
               '--mount', f'type=bind,src={run / "source"},dst=/source,readonly',
               '--mount', f'type=bind,src={run / "recipe.sh"},dst=/recipe.sh,readonly']
    for name in ('build', 'install', 'evidence'):
        command += ['--mount', f'type=bind,src={run / name},dst=/{name}']
    command += [pin['sdk_image'], 'env', '-i', *ENVIRONMENT, '/bin/sh', '/recipe.sh']
    subprocess.run(command, check=True)
    require(input_hashes(root) == before, 'Build inputs changed during compilation; discard this build')
    require((run / 'recipe.sh').read_text() == recipe(pin), 'Recipe changed during compilation')
    require(tree_inventory(run / 'source') == inventory, 'Source changed during compilation; discard this build')
    require(archive_inventory(run / 'ffmpeg-source.tar.gz', pin) == inventory, 'Archive changed during compilation')
    files = {}
    installed = run / 'install/usr/lib/x86_64-linux-gnu'
    for name in SONAMES:
        resolved = (installed / name).resolve(strict=True)
        require(resolved.is_relative_to(installed.resolve()), 'Installed library escapes build output')
        check_elf(resolved)
        # install must copy this run's freshly linked library, not an unrelated ELF.
        linked = (run / 'build' / name.split('.')[0] / name).resolve(strict=True)
        require(linked.is_relative_to((run / 'build').resolve()), 'Linked library escapes build workspace')
        check_elf(linked)
        require(digest(resolved) == digest(linked), 'Installed and linked output differ: ' + name)
        files[name] = digest(resolved)
    require(digest(regular(run / 'build/libswresample/libswresample.a')) ==
            digest(regular(run / 'evidence/libswresample.a')),
            'Opus static archive differs from this build')
    license_name = check_evidence(run / 'evidence', pin, files)
    output = run / 'runtime'
    output.mkdir()
    for name in SONAMES:
        shutil.copyfile((installed / name).resolve(), output / name)
        (output / name).chmod(0o644)
    for name in LICENSES[:-1]:
        shutil.copyfile(run / 'source' / name, output / name)
    shutil.copyfile(root / 'guest/video/NOTICE', output / 'NOTICE')
    shutil.copyfile(run / 'recipe.sh', output / 'recipe.sh')
    shutil.copyfile(run / 'ffmpeg-source.tar.gz', output / 'ffmpeg-source.tar.gz')
    shutil.copytree(run / 'evidence', output / 'evidence')
    artifacts = {p.relative_to(output).as_posix(): digest(regular(p))
                 for p in output.rglob('*') if p.is_file()}
    receipt = {'schema': 2, 'source': pin, 'inputs': before,
               'source_tree_sha256': object_digest(inventory),
               'configure': list(CONFIGURE), 'environment': list(ENVIRONMENT),
               'make_overrides': list(MAKE_OVERRIDES),
               'architecture': 'x86_64-linux-gnu', 'license': license_name,
               'files': files, 'artifacts': artifacts}
    (output / 'build.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    verify_runtime(output, root)
    # Publish only a fully checked run. Keep any preceding runtime on failure.
    target = work / 'runtime'
    backup = run / 'previous-runtime'
    had_target = target.exists()
    if had_target:
        target.rename(backup)
    try:
        output.rename(target)
    except BaseException:
        if had_target:
            backup.rename(target)
        raise
    print('Recorded verified private video libraries:', ', '.join(files))
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build'])
    parser.parse_args()
    build()
