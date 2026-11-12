#!/usr/bin/env python3
"""Use a synthetic camera on a protected clone; never request camera permission."""
from pathlib import Path
import json,os,signal,subprocess,time,sys
ROOT=Path(__file__).resolve().parents[2];W=ROOT/'work/camera-experiment';APP=W/'steamac Lite Camera Test.app';DISK=W/'steamos-camera.img'
MF='--mf' in sys.argv
LAYOUT='--layout' in sys.argv
DSHOW='--dshow' in sys.argv
ENV={**os.environ,'DEVELOPER_DIR':'/Library/Developer/CommandLineTools','STEAMAC_DEFAULTS_DOMAIN':'local.ryuu.steamac-lite.camera-synthetic-test','STEAMAC_GAME_STATS_FILE':str(W/'synthetic-stats.json'),'STEAMAC_SENTRY':'0','STEAMAC_CAMERA_PATTERN_SECONDS':'0' if MF or DSHOW else '9'}
assert not subprocess.run(['pgrep','-x','steamac-vm'],capture_output=True).stdout.strip(),'Stop other SteamOS VMs first'
assert subprocess.run(['/usr/local/bin/docker','info'],capture_output=True).returncode!=0,'Stop Docker Desktop first'
for domain in ['local.ryuu.steamac-lite','es.fxgam.steamac']:
 original=Path.home()/'Library/Application Support'/domain/'steamos.img'
 if original.exists():assert not os.path.samefile(DISK,original)
assert not subprocess.run(['lsof','-t',str(DISK)],capture_output=True).stdout.strip()
subprocess.run(['defaults','write',ENV['STEAMAC_DEFAULTS_DOMAIN'],'checkForUpdates','-bool','false'],check=True)
layer='camera-dshow-selftest.img' if DSHOW else 'camera-layout-selftest.img' if LAYOUT else ('camera-mf-selftest.img' if MF else 'camera-selftest.img')
cmd=[str(APP/'Contents/MacOS/steamac-vm'),'--headless','--no-sound','--no-ssh','--no-vr','--no-crash-reports','--camera-test-pattern','--disk',str(DISK),'--disk',str(W/layer)+':ro','--cmdline','console=hvc0 loglevel=4 rootwait virtio_snd.msg_timeout_ms=10000 steamac.vrchat_setup=0'+(' systemd.unit=multi-user.target' if LAYOUT else '')]
log=W/('dshow-console.log' if DSHOW else ('layout-console.log' if LAYOUT else ('mf-console.log' if MF else 'synthetic-console.log')));started=time.monotonic();forced=False
with log.open('w') as out:
 process=subprocess.Popen(cmd,stdout=out,stderr=subprocess.STDOUT,env=ENV,start_new_session=True)
 try:
  while time.monotonic()-started<(230 if MF or DSHOW else 145):
   if process.poll() is not None:break
   time.sleep(.5)
 finally:
  if process.poll() is None:process.terminate()
  try:process.wait(timeout=50)
  except subprocess.TimeoutExpired:forced=True;os.killpg(process.pid,signal.SIGKILL);process.wait()
s=log.read_text(errors='replace');passed=('VIDEO_LAYOUT_EXIT=0' if LAYOUT else 'CAMERA_TEST_EXIT=0') in s and process.returncode==0 and not forced and (not MF or 'MF_CAMERA_PASS' in s)
record={'passed':passed,'camera_hardware_opened':False,'real_camera_permission_requested':False,'exit_code':process.returncode,'forced_shutdown':forced,'elapsed_seconds':round(time.monotonic()-started,1),'checks':[line for line in s.splitlines() if any(k in line for k in ['CAMERA_TEST','CAMERA_PROBE','MF_CAMERA','CAMERA_MF','camera guest:','camera: synthetic'])]}
(W/('dshow-validation.json' if DSHOW else ('layout-validation.json' if LAYOUT else ('mf-validation.json' if MF else 'synthetic-validation.json')))).write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2));raise SystemExit(0 if passed else 1)
