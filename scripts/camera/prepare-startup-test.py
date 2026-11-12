#!/usr/bin/env python3
"""Prepare a short read-only evidence boot; never starts a game."""
from pathlib import Path
import os, shutil, subprocess
root=Path(__file__).resolve().parents[2];work=root/'work/camera-experiment';layer=work/'layer'
lib=layer/'usr/lib/steamac/camera'
assert (lib/'camera-agent').is_file()
shutil.copy2(root/'guest/camera/collect-startup.py',lib/'collect-startup.py')
(lib/'camera-test-runner').write_text('''#!/bin/bash
set -u
python3 /usr/lib/steamac/camera/collect-startup.py
result=$?
echo CAMERA_TEST_EXIT=$result
systemctl poweroff
''')
(lib/'camera-test-runner').chmod(0o755)
subprocess.run([str(root/'work/tools/erofs-utils/mkfs/mkfs.erofs'),'-b4096','-zlz4hc','--all-root',str(work/'camera-startup-selftest.img'),str(layer)],env={**os.environ,'DEVELOPER_DIR':'/Library/Developer/CommandLineTools'},check=True,stdout=subprocess.DEVNULL)
