#!/usr/bin/env python3
"""Use a synthetic camera on a protected clone; never request camera permission."""
from pathlib import Path
import json,os,signal,subprocess,time,sys
ROOT=Path(__file__).resolve().parents[2];W=ROOT/'work/camera-experiment';APP=W/'steamac Lite Camera Test.app';DISK=W/'steamos-camera.img'
MF='--mf' in sys.argv
LAYOUT='--layout' in sys.argv
DSHOW='--dshow' in sys.argv
CONTAINER='--container' in sys.argv
PRODUCTION='--production' in sys.argv
OVERLAY='--overlay' in sys.argv
STARTUP_OVERLAY='--startup-overlay' in sys.argv
STARTUP='--startup' in sys.argv or STARTUP_OVERLAY
if PRODUCTION and (MF or LAYOUT or DSHOW or CONTAINER or OVERLAY or STARTUP):
 raise SystemExit('--production is a separate packaged camera diagnostic')
if STARTUP and (MF or LAYOUT or DSHOW or CONTAINER or OVERLAY):
 raise SystemExit('--startup is a separate read-only log collection diagnostic')
if OVERLAY and (MF or LAYOUT or DSHOW or CONTAINER):
 raise SystemExit('--overlay is a separate TEST-ONLY diagnostic; do not combine test modes')
if CONTAINER or OVERLAY or PRODUCTION: DSHOW=True
if PRODUCTION: APP=ROOT/'work/out/SteamAC Lite.app'
ENV={**os.environ,'DEVELOPER_DIR':'/Library/Developer/CommandLineTools','STEAMAC_DEFAULTS_DOMAIN':'local.ryuu.steamac-lite.camera-synthetic-test','STEAMAC_GAME_STATS_FILE':str(W/'synthetic-stats.json'),'STEAMAC_SENTRY':'0','STEAMAC_CAMERA_PATTERN_SECONDS':'0' if MF or DSHOW else '9'}
assert not subprocess.run(['pgrep','-x','steamac-vm'],capture_output=True).stdout.strip(),'Stop other SteamOS VMs first'
assert subprocess.run(['/usr/local/bin/docker','info'],capture_output=True).returncode!=0,'Stop Docker Desktop first'
for domain in ['local.ryuu.steamac-lite','es.fxgam.steamac']:
 original=Path.home()/'Library/Application Support'/domain/'steamos.img'
 if original.exists():assert not os.path.samefile(DISK,original)
assert not subprocess.run(['lsof','-t',str(DISK)],capture_output=True).stdout.strip()
subprocess.run(['defaults','write',ENV['STEAMAC_DEFAULTS_DOMAIN'],'checkForUpdates','-bool','false'],check=True)
layer='camera-dshow-selftest.img' if DSHOW else 'camera-layout-selftest.img' if LAYOUT else ('camera-mf-selftest.img' if MF else 'camera-selftest.img')
if CONTAINER: layer='camera-container-selftest.img'
if OVERLAY: layer='camera-overlay-selftest.img'
if STARTUP: layer='camera-startup-selftest.img'
if PRODUCTION: layer='camera-production-selftest.img'
cmd=[str(APP/'Contents/MacOS/steamac-vm'),'--headless','--no-sound','--no-ssh','--no-vr','--no-crash-reports','--camera-test-pattern','--disk',str(DISK),'--disk',str(W/layer)+':ro','--cmdline','console=hvc0 loglevel=4 rootwait virtio_snd.msg_timeout_ms=10000 steamac.vrchat_setup=0'+(' systemd.unit=multi-user.target' if LAYOUT or OVERLAY or STARTUP or PRODUCTION else '')+(' steamac.camera_stock_overlay=1' if STARTUP_OVERLAY else '')]
log=W/('dshow-console.log' if DSHOW else ('layout-console.log' if LAYOUT else ('mf-console.log' if MF else 'synthetic-console.log')));started=time.monotonic();forced=False
if CONTAINER: log=W/'container-console.log'
if OVERLAY: log=W/'overlay-console.log'
if STARTUP: log=W/'startup-console.log'
if PRODUCTION: log=W/'production-console.log'
with log.open('w') as out:
 process=subprocess.Popen(cmd,stdout=out,stderr=subprocess.STDOUT,env=ENV,start_new_session=True)
 try:
  while time.monotonic()-started<(550 if OVERLAY or PRODUCTION else (380 if CONTAINER else (230 if MF or DSHOW else 145))):
   if process.poll() is not None:break
   time.sleep(.5)
 finally:
  if process.poll() is None:
   forced=True
   process.terminate()
  try:process.wait(timeout=40 if OVERLAY else 50)
  except subprocess.TimeoutExpired:forced=True;os.killpg(process.pid,signal.SIGKILL);process.wait()
s=log.read_text(errors='replace');passed=('VIDEO_LAYOUT_EXIT=0' if LAYOUT else 'CAMERA_TEST_EXIT=0') in s and process.returncode==0 and not forced and (not MF or 'MF_CAMERA_PASS' in s) and (not DSHOW or PRODUCTION or 'DS_CAMERA_CAPTURE_PASS' in s)
if PRODUCTION:
 passed=passed and all('CAMERA_PRODUCTION_CASE_RESULT '+name+' passed=1' in s for name in ('stock-preview-rgb32','capture-rgb24','preview-rgb24','preview-rgb32','second-filter')) and 'CAMERA_PRODUCTION_ORIGINAL_UNCHANGED' in s
if STARTUP:
 passed=passed and '"kind": "end"' in s
 if STARTUP_OVERLAY: passed=passed and 'CAMERA_STOCK_OVERLAY active:' in s
if OVERLAY:
 expected_cases=['A1-capture-rgb24','A1-preview-rgb32']+[f'B{i}-{name}' for i in (1,2) for name in ('capture-rgb24','preview-any','preview-rgb24','preview-rgb32')]+['A2-preview-rgb32','A2-capture-rgb24']
 passed=passed and all(f'CAMERA_OVERLAY_CASE_RESULT {label} passed=1 ' in s for label in expected_cases) and all(marker in s for marker in ('CAMERA_OVERLAY_BIND_READONLY','CAMERA_OVERLAY_RESTORED','CAMERA_OVERLAY_ABA_RESULT=0','CAMERA_OVERLAY_EXIT=0'))
record={'passed':passed,'camera_hardware_opened':False,'real_camera_permission_requested':False,'exit_code':process.returncode,'forced_shutdown':forced,'elapsed_seconds':round(time.monotonic()-started,1),'checks':[line for line in s.splitlines() if any(k in line for k in ['CAMERA_TEST','CAMERA_PROBE','CAMERA_READ_PROBE','MF_CAMERA','CAMERA_MF','DS_CAMERA','CAMERA_DSHOW','CAMERA_CONTAINER','CAMERA_OVERLAY','CAMERA_PRODUCTION','camera guest:','camera: synthetic'])]}
if OVERLAY: record.update(diagnostic='TEST-ONLY PE-bind A/B/A',synthetic_only=True,expected_cases=expected_cases)
target='startup-validation.json' if STARTUP else ('overlay-validation.json' if OVERLAY else ('container-validation.json' if CONTAINER else ('dshow-validation.json' if DSHOW else ('layout-validation.json' if LAYOUT else ('mf-validation.json' if MF else 'synthetic-validation.json')))))
if PRODUCTION: target='production-validation.json'
(W/target).write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2));raise SystemExit(0 if passed else 1)
