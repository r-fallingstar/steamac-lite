#!/usr/bin/python3
"""Boot-only x64 camera prototype; keep the installed stock Proton files intact."""
from pathlib import Path
import hashlib, json, subprocess

HERE = Path(__file__).resolve().parent
STOCK = Path('/home/steamos/.local/share/Steam/steamapps/common/Proton - Experimental')
PIN = {
    'version':'503c72483de03a9c63dda987ba1374002bfca48fb24858d5793db0c05f3342f8',
    'files/lib/wine/x86_64-windows/qcap.dll':'e2e95abf6567edabdfc9756ee8c1cd54101c5102bd556eb1d01df86f279c246c',
    'files/lib/wine/x86_64-unix/qcap.so':'b9090cf3952a4adcb3ce6a9fe8e155d52ec59f0aa405bbaf923386230a5847b3',
}
PATCHED = 'c891f99919668872a2acc7d8f5843fc1b52b52034c6f066039df9e89fe2e4365'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    if 'steamac.camera_stock_overlay=1' not in Path('/proc/cmdline').read_text().split():
        return
    source = HERE/'overlay/files/lib/wine/x86_64-windows/qcap.dll'
    target = STOCK/'files/lib/wine/x86_64-windows/qcap.dll'
    marker = Path('/run/steamac-camera-stock-overlay.json')
    if marker.exists():
        if digest(target) != PATCHED:
            raise ValueError('camera overlay changed after setup')
        return
    if digest(source) != PATCHED:
        raise ValueError('camera prototype source mismatch')
    for name, expected in PIN.items():
        path = STOCK/name
        path.resolve().relative_to(STOCK.resolve())
        if digest(path) != expected:
            raise ValueError('stock Proton revision mismatch: '+name)
    if subprocess.run(['pgrep','-x','steam|wine|wineserver|FEX'],stdout=subprocess.DEVNULL).returncode == 0:
        raise ValueError('Steam or a game is already running')
    subprocess.run(['mount','--bind',str(source),str(target)],check=True)
    try:
        subprocess.run(['mount','-o','remount,bind,ro',str(target)],check=True)
        flags = subprocess.check_output(['findmnt','-n','-o','VFS-OPTIONS','--target',str(target)],text=True)
        if 'ro' not in flags.strip().split(',') or digest(target) != PATCHED:
            raise ValueError('camera prototype read-only mount verification failed')
        marker.write_text(json.dumps({'mode':'test-only x64 PE camera module','stock_version_sha256':PIN['version'],
                                     'pe_sha256':PATCHED,'stock_unix_sha256':PIN['files/lib/wine/x86_64-unix/qcap.so']})+'\n')
        print('CAMERA_STOCK_OVERLAY active: stock Proton retained; camera PE only, read-only for this boot',flush=True)
    except BaseException:
        subprocess.run(['umount',str(target)],check=True)
        raise


if __name__ == '__main__':
    main()
