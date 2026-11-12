#!/usr/bin/env python3
"""Create a read-only runtime layout test layer, leaving the manual camera app intact."""
from pathlib import Path
import os, shutil, subprocess

root = Path(__file__).resolve().parents[2]
work = root / 'work/camera-experiment'
layer = work / 'layer'
lib = layer / 'usr/lib/steamac/camera'
assert lib.is_dir() and (lib / 'camera-test-runner').is_file()
shutil.copy2(root / 'guest/diagnostics/video-test-runner', lib / 'video-test-runner')
(lib / 'layout-test.py').write_text('''#!/usr/bin/python3
import base64, gzip, subprocess
print("VIDEO_LAYOUT_BEGIN", flush=True)
result = subprocess.run(['setpriv', '--reuid=1000', '--regid=1000', '--init-groups',
    'env', 'HOME=/home/steamos', 'USER=steamos', 'LOGNAME=steamos',
    'python3', '/usr/lib/steamac/camera/video-test-runner', '--collect',
    '--steam-root', '/home/steamos/.local/share/Steam'], capture_output=True)
if result.returncode == 0:
    encoded = base64.b64encode(gzip.compress(result.stdout)).decode()
    for i in range(0, len(encoded), 800):
        print('VIDEO_LAYOUT_DATA ' + encoded[i:i+800], flush=True)
else:
    print(result.stderr.decode(errors='replace'), flush=True)
print('VIDEO_LAYOUT_EXIT=' + str(result.returncode), flush=True)
subprocess.run(['systemctl', 'poweroff'])
''')
(lib / 'camera-test-runner').write_text('#!/bin/bash\nexec /usr/bin/python3 /usr/lib/steamac/camera/layout-test.py\n')
(lib / 'camera-test-runner').chmod(0o755)
env = {**os.environ, 'DEVELOPER_DIR': '/Library/Developer/CommandLineTools'}
subprocess.run([str(root/'work/tools/erofs-utils/mkfs/mkfs.erofs'), '-b4096', '-zlz4hc', '--all-root',
    str(work/'camera-layout-selftest.img'), str(layer)], env=env, check=True, stdout=subprocess.DEVNULL)
print('Prepared layout-only diagnostic layer; manual app unchanged.')
