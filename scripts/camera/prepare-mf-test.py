#!/usr/bin/env python3
from pathlib import Path
import shutil,subprocess
ROOT=Path(__file__).resolve().parents[2];W=ROOT/'work/camera-experiment';layer=W/'layer'
shutil.copy2(ROOT/'guest/camera/mf-test-runner',layer/'usr/lib/steamac/camera/camera-test-runner')
subprocess.run([str(ROOT/'work/tools/erofs-utils/mkfs/mkfs.erofs'),'-b4096','-zlz4hc','--all-root',str(W/'camera-mf-selftest.img'),str(layer)],check=True,stdout=subprocess.DEVNULL)
