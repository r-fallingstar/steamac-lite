#!/usr/bin/env python3
"""Create only the isolated DirectShow test layer, never the manual app layer."""
from pathlib import Path
import os, shutil, subprocess
root=Path(__file__).resolve().parents[2];work=root/'work/camera-experiment';layer=work/'layer'
lib=layer/'usr/lib/steamac/camera'
assert (lib/'camera-agent').is_file()
shutil.copy2(root/'guest/camera/dshow-test-runner',lib/'camera-test-runner')
(lib/'camera-test-runner').chmod(0o755)
shutil.copy2(work/'dshow-camera-test.exe',lib/'dshow-camera-test.exe')
if '--compare-rtsp' in __import__('sys').argv:
    import hashlib
    archive=work/'proton-rtsp-11.0-20260609-4.tar.gz'
    assert hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()=='b52f231a116e9d0f1f9d19f4e870ff84392f35daae02391a6f79fdf9ca583415'
    shutil.copy2(archive,lib/archive.name)
unit=layer/'usr/lib/systemd/system/steamac-camera-test.service'
unit.write_text(unit.read_text().replace('TimeoutStartSec=110','TimeoutStartSec=220'))
subprocess.run([str(root/'work/tools/erofs-utils/mkfs/mkfs.erofs'),'-b4096','-zlz4hc','--all-root',str(work/'camera-dshow-selftest.img'),str(layer)],
    env={**os.environ,'DEVELOPER_DIR':'/Library/Developer/CommandLineTools'},check=True,stdout=subprocess.DEVNULL)
