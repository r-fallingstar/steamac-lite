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
subprocess.run([str(root/'work/tools/erofs-utils/mkfs/mkfs.erofs'),'-b4096','-zlz4hc','--all-root',str(work/'camera-dshow-selftest.img'),str(layer)],
    env={**os.environ,'DEVELOPER_DIR':'/Library/Developer/CommandLineTools'},check=True,stdout=subprocess.DEVNULL)
