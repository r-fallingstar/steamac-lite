#!/usr/bin/env python3
"""Add a synthetic-only test runner to a separate copy of the packaged layer."""
from pathlib import Path
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'work/camera-experiment'
LAYER = ROOT / 'work/camera-release/test-layer'
APP = ROOT / 'work/out/SteamAC Lite.app'
assert not subprocess.run(['pgrep','-x','steamac-vm'],capture_output=True).stdout.strip()
if LAYER.exists():
    assert (LAYER/'.production-camera-test').is_file() and not LAYER.is_symlink()
    shutil.rmtree(LAYER)
subprocess.run([str(ROOT/'work/tools/erofs-utils/fsck/fsck.erofs'), '--extract='+str(LAYER),
                '--no-preserve-owner',str(APP/'Contents/Resources/steamac-layer.img')],check=True,stdout=subprocess.DEVNULL)
(LAYER/'.production-camera-test').touch()
lib=LAYER/'usr/lib/steamac/camera'
shutil.copyfile(ROOT/'guest/camera/production-test-runner',lib/'camera-test-runner')
(lib/'camera-test-runner').chmod(0o755)
shutil.copyfile(WORK/'dshow-camera-test.exe',lib/'dshow-camera-test.exe')
units=LAYER/'usr/lib/systemd/system'
(units/'steamac-camera-test.service').write_text('''[Unit]
Description=Synthetic camera release verification (clone only)
After=steamac-camera.service
[Service]
Type=oneshot
ExecStart=/usr/lib/steamac/camera/camera-test-runner
TimeoutStartSec=540
StandardOutput=journal+console
StandardError=journal+console
[Install]
WantedBy=multi-user.target
''')
(units/'multi-user.target.wants/steamac-camera-test.service').symlink_to('../steamac-camera-test.service')
subprocess.run([str(ROOT/'work/tools/erofs-utils/mkfs/mkfs.erofs'),'-b4096','-zlz4hc','--all-root',
                str(WORK/'camera-production-selftest.img'),str(LAYER)],
               env={**os.environ,'DEVELOPER_DIR':'/Library/Developer/CommandLineTools'},check=True,stdout=subprocess.DEVNULL)
