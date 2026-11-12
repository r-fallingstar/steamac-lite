#!/usr/bin/env python3
"""Stage the production camera bridge, without test services or original-Proton overlays."""
from pathlib import Path
import hashlib
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / 'work/camera-release/runtime'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def stage(layer, app):
    receipt = json.loads((INPUT / 'build.json').read_text())
    for name, expected in receipt['files'].items():
        if digest(INPUT / name) != expected:
            raise ValueError('Camera artifact mismatch: ' + name)
    for name, expected in receipt['sources'].items():
        if digest(ROOT / name) != expected:
            raise ValueError('Rebuild the camera artifact for source: ' + name)
    if digest(app / 'Contents/Resources/Image') != receipt['kernel_image_sha256']:
        raise ValueError('Camera module requires the pinned kernel')
    pins = json.loads((ROOT / 'guest/camera/proton-camera.json').read_text())
    if digest(INPUT / 'proton/qcap.dll') != pins['patched_pe_sha256']:
        raise ValueError('Camera DLL does not match its source manifest')
    lib = layer / 'usr/lib/steamac/camera'
    lib.mkdir(parents=True, exist_ok=True)
    for name in ('camera-agent', 'v4l2loopback.ko', 'proton/qcap.dll'):
        target = lib / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(INPUT / name, target)
        target.chmod(0o755 if name == 'camera-agent' else 0o644)
    for name in ('start-camera', 'prepare-proton.py', 'init-home.py', 'proton-camera.json', 'video-launcher.json'):
        target = lib / name
        shutil.copyfile(ROOT / 'guest/camera' / name, target)
        target.chmod(0o644 if name.endswith('.json') else 0o755)
    units = layer / 'usr/lib/systemd/system'
    (units / 'steamac-camera.service').write_text('''[Unit]
Description=steamac built-in camera bridge
After=local-fs.target systemd-udevd.service
Before=user@1000.service
[Service]
Environment="STEAMAC_CAMERA_LABEL=steamac Camera"
ExecStartPre=/usr/bin/python3 /usr/lib/steamac/camera/init-home.py
ExecStart=/usr/lib/steamac/camera/start-camera
Restart=on-failure
RestartSec=3
StandardOutput=journal
StandardError=journal
[Install]
WantedBy=multi-user.target
''')
    wants = units / 'multi-user.target.wants'
    wants.mkdir(parents=True, exist_ok=True)
    (wants / 'steamac-camera.service').symlink_to('../steamac-camera.service')
    dropin = layer / 'usr/lib/systemd/user/steam.service.d/90-steamac-camera.conf'
    dropin.parent.mkdir(parents=True, exist_ok=True)
    dropin.write_text('[Service]\nExecStartPre=-/usr/bin/python3 /usr/lib/steamac/camera/prepare-proton.py --auto\n')
    # Read-only provenance contains hashes and public pins, never local disk paths.
    receipt['proton'] = pins
    receipt['deployment'] = 'private independent Proton tool; installed Steam Proton is untouched'
    (app / 'Contents/Resources/steamac-camera-build.json').write_text(json.dumps(receipt, indent=2) + '\n')
    licenses = app / 'Contents/Resources/licenses/Camera'
    licenses.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / 'guest/camera/NOTICE', licenses / 'NOTICE')
    shutil.copyfile(ROOT / 'work/camera-release/wine-source/COPYING.LIB', licenses / 'Wine-LGPL-2.1.txt')
    shutil.copyfile(ROOT / 'work/camera-experiment/v4l2loopback/COPYING', licenses / 'v4l2loopback-GPL-2.0.txt')
    for source, name in (('glibc-COPYING', 'glibc-COPYING.txt'), ('gcc-COPYING', 'GCC-runtime-COPYING.txt')):
        shutil.copyfile(ROOT / 'work/camera-release' / source, licenses / name)
    print('Staged camera bridge and isolated Proton support; no test observer or original-file overlay')


if __name__ == '__main__':
    stage(*map(Path, sys.argv[1:]))
