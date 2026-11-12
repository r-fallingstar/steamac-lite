#!/usr/bin/env python3
"""Open the opt-in camera experiment on its existing disk clone through LaunchServices."""
from pathlib import Path
import hashlib
import json
import os
import plistlib
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'work/camera-experiment'
APP = WORK / 'steamac Lite Camera Test.app'
DOMAIN = 'local.ryuu.steamac-lite.camera-experiment'
env = {**os.environ, 'DEVELOPER_DIR': '/Library/Developer/CommandLineTools'}

def run(args, **kwargs):
    return subprocess.run(args, env=env, **kwargs)

def require(condition, message):
    if not condition:
        raise SystemExit(message)

baseline = json.loads((WORK / 'protected-environment.json').read_text())
original = Path(baseline['original_disk'])
disk = Path(baseline['test_disk'])
require(APP.is_dir() and disk.is_file(), 'Prepare the camera app and cloned disk first.')
require(not os.path.samefile(disk, original), 'The camera disk must be a separate clone.')
require(not run(['pgrep', '-x', 'steamac-vm'], capture_output=True).stdout.strip(), 'Close the running SteamOS VM first.')
require(run(['/usr/local/bin/docker', 'info'], capture_output=True).returncode != 0, 'Stop Docker Desktop first.')
for path in (original, disk):
    require(not run(['lsof', '-t', str(path)], capture_output=True).stdout.strip(), 'A SteamOS disk is already open.')
info = plistlib.loads((APP / 'Contents/Info.plist').read_bytes())
require(info['CFBundleIdentifier'] == DOMAIN, 'The app must have its experimental identity.')
run(['codesign', '--verify', '--deep', '--strict', str(APP)], check=True)
stat = original.stat()
prefs = Path.home() / 'Library/Preferences/local.ryuu.steamac-lite.plist'
protected = {
    'disk_unchanged': stat.st_ino == baseline['inode'] and stat.st_size == baseline['size'] and stat.st_mtime_ns == baseline['mtime_ns'],
    'preferences_unchanged': hashlib.sha256(prefs.read_bytes()).hexdigest() == baseline['preferences_sha256'],
    'experimental_app': str(APP), 'experimental_disk': str(disk),
}
(WORK / 'manual-preflight.json').write_text(json.dumps(protected, indent=2) + '\n')
print(json.dumps(protected, indent=2))
if '--check-only' in sys.argv:
    raise SystemExit(0)

# Import preferences only once. Subsequent camera/display choices stay in this separate domain.
marker = WORK / 'manual-preferences-initialized'
if not marker.exists():
    run(['defaults', 'import', DOMAIN, str(WORK / 'preferences-before-test.plist')], check=True)
    marker.write_text('Imported production preferences once; later edits are experiment-only.\n')
for key in ['checkForUpdates', 'shareGameStats', 'sshEnabled', 'vrEnabled', 'sendCrashReports', 'vrchatSetup']:
    run(['defaults', 'write', DOMAIN, key, '-bool', 'false'], check=True)
run(['defaults', 'write', DOMAIN, 'diskImage', '-string', str(disk)], check=True)
log = WORK / 'manual-camera.log'
args = ['open', '-n', '--stdout', str(log), '--stderr', str(log),
        '--env', 'STEAMAC_GAME_STATS_FILE=' + str(WORK / 'manual-stats.json'),
        '--env', 'STEAMAC_SENTRY=0', str(APP), '--args',
        '--experimental-camera', '--no-ssh', '--no-vr', '--no-crash-reports',
        '--disk', str(disk), '--disk', str(APP / 'Contents/Resources/steamac-layer.img') + ':ro',
        '--cmdline', 'console=hvc0 loglevel=4 rootwait virtio_snd.msg_timeout_ms=10000 steamac.vrchat_setup=0 steamac.camera_debug=1']
run(args, check=True)
print('Opened the camera experiment. Start the camera from Settings > Camera.')
