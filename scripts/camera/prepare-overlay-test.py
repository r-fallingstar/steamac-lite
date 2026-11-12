#!/usr/bin/env python3
"""Build the isolated TEST-ONLY PE overlay diagnostic from local verified input."""
from pathlib import Path
import hashlib
import os
import re
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'work/camera-experiment'
LAYER = WORK / 'layer'
ARCHIVE_SHA = 'b52f231a116e9d0f1f9d19f4e870ff84392f35daae02391a6f79fdf9ca583415'
DLL_SHA = 'c891f99919668872a2acc7d8f5843fc1b52b52034c6f066039df9e89fe2e4365'
MEMBER = 'proton-rtsp-11.0-20260609-4/files/lib/wine/x86_64-windows/qcap.dll'


def prepare():
    lib = LAYER / 'usr/lib/steamac/camera'
    unit = LAYER / 'usr/lib/systemd/system/steamac-camera-test.service'
    for path in (lib / 'camera-agent', lib / 'v4l2loopback.ko', unit,
                 WORK / 'dshow-camera-test.exe'):
        if not path.is_file():
            raise SystemExit(f'Missing existing camera test prerequisite: {path}')
    archive = WORK / 'proton-rtsp-11.0-20260609-4.tar.gz'
    # Hash the same open file used by tarfile; never fetch or unpack a tool tree.
    with archive.open('rb') as source:
        if hashlib.file_digest(source, 'sha256').hexdigest() != ARCHIVE_SHA:
            raise SystemExit('RTSP archive SHA256 mismatch; staging unchanged')
        source.seek(0)
        with tarfile.open(fileobj=source, mode='r:gz') as tar:
            matches = [item for item in tar if item.name == MEMBER]
            if len(matches) != 1 or not matches[0].isfile() or matches[0].size > 16 * 1024 * 1024:
                raise SystemExit('Expected exactly one regular qcap.dll archive member')
            with tar.extractfile(matches[0]) as member:
                dll = member.read()
    if hashlib.sha256(dll).hexdigest() != DLL_SHA:
        raise SystemExit('RTSP qcap.dll SHA256 mismatch; staging unchanged')

    # Derived outputs only. Do not change the manual app or its embedded layer.
    target = lib / 'overlay/files/lib/wine/x86_64-windows/qcap.dll'
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix='.qcap-', dir=target.parent, delete=False) as output:
        temporary_dll = Path(output.name)
        output.write(dll)
    try:
        temporary_dll.chmod(0o444)
        temporary_dll.replace(target)
    finally:
        temporary_dll.unlink(missing_ok=True)
    shutil.copy2(ROOT / 'guest/camera/overlay-test-runner', lib / 'camera-test-runner')
    (lib / 'camera-test-runner').chmod(0o755)
    shutil.copy2(WORK / 'dshow-camera-test.exe', lib / 'dshow-camera-test.exe')
    collector = ROOT / 'guest/camera/collect-startup.py'
    if collector.is_file():
        shutil.copy2(collector, lib / collector.name)
    text = unit.read_text()
    if len(re.findall(r'^TimeoutStartSec=.*$', text, flags=re.M)) != 1:
        raise SystemExit('Expected one TimeoutStartSec in the existing test unit')
    unit.write_text(re.sub(r'^TimeoutStartSec=.*$', 'TimeoutStartSec=600', text, flags=re.M))
    image = WORK / 'camera-overlay-selftest.img'
    with tempfile.TemporaryDirectory(prefix='overlay-image-', dir=WORK) as scratch:
        temporary = Path(scratch) / image.name
        subprocess.run([str(ROOT / 'work/tools/erofs-utils/mkfs/mkfs.erofs'),
                        '-b4096', '-zlz4hc', '--all-root', str(temporary), str(LAYER)],
                       env={**os.environ, 'DEVELOPER_DIR': '/Library/Developer/CommandLineTools'},
                       check=True, stdout=subprocess.DEVNULL)
        temporary.replace(image)
    print(f'Ready: {image}; TEST-ONLY, synthetic input, no VM started')


if __name__ == '__main__':
    prepare()
