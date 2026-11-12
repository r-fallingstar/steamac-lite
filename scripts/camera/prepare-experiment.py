#!/usr/bin/env python3
"""Assemble an isolated camera app and synthetic-test layer. Never install it."""
from pathlib import Path
import hashlib,json,os,plistlib,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[2];WORK=ROOT/'work/camera-experiment';APP=WORK/'steamac Lite Camera Test.app';LAYER=WORK/'layer'
ENV={**os.environ,'DEVELOPER_DIR':'/Library/Developer/CommandLineTools'}
FSCK=ROOT/'work/tools/erofs-utils/fsck/fsck.erofs';MKFS=ROOT/'work/tools/erofs-utils/mkfs/mkfs.erofs'
if LAYER.exists():
 if '--refresh' not in sys.argv:raise SystemExit('Use --refresh to replace the generated layer staging directory.')
 assert not LAYER.is_symlink() and (LAYER/'usr/lib/steamac/camera/camera-agent').is_file()
 shutil.rmtree(LAYER)
subprocess.run([str(FSCK),'--extract='+str(LAYER),'--no-preserve-owner',str(ROOT/'work/out/SteamAC Lite.app/Contents/Resources/steamac-layer.img')],check=True,stdout=subprocess.DEVNULL)
lib=LAYER/'usr/lib/steamac/camera';lib.mkdir(parents=True,exist_ok=True)
for name in ['camera-agent','mf-camera-test.exe','v4l2loopback.ko']:shutil.copy2(WORK/name,lib/name)
shutil.copy2(ROOT/'guest/camera/start-camera',lib/'start-camera')
shutil.copy2(ROOT/'guest/camera/observe-runtime.py',lib/'observe-runtime.py')
units=LAYER/'usr/lib/systemd/system';shutil.copy2(ROOT/'guest/camera/steamac-camera.service',units/'steamac-camera.service')
(units/'multi-user.target.wants/steamac-camera.service').symlink_to('../steamac-camera.service')
(units/'steamac-camera-runtime-observer.service').write_text('''[Unit]
Description=Local camera runtime metadata (diagnostic clone only)
ConditionKernelCommandLine=steamac.camera_debug=1
After=steamac-camera.service
[Service]
ExecStart=/usr/bin/python3 /usr/lib/steamac/camera/observe-runtime.py
TimeoutStartSec=610
StandardOutput=journal+console
StandardError=journal+console
[Install]
WantedBy=multi-user.target
''')
(units/'multi-user.target.wants/steamac-camera-runtime-observer.service').symlink_to('../steamac-camera-runtime-observer.service')
def image(target):subprocess.run([str(MKFS),'-b4096','-zlz4hc','--all-root',str(target),str(LAYER)],check=True,stdout=subprocess.DEVNULL)
image(APP/'Contents/Resources/steamac-layer.img')
runner=lib/'camera-test-runner';runner.write_text('''#!/bin/bash
exec 2>&1
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
echo CAMERA_TEST_BEGIN
uname -r
for ((i=0;i<60;i++)); do [[ ! -f /run/steamac-camera-device ]] || break; sleep 1; done
device=$(cat /run/steamac-camera-device)
label=$(cat /sys/class/video4linux/${device##*/}/name)
echo "CAMERA_DEVICE $device label=$label"
[[ $device =~ ^/dev/video[0-9]$ && $label == 'steamac Built-in Camera Test' ]]
enumerable=$?
sleep 2
/usr/lib/steamac/camera/camera-agent --probe "$device"
live=$?
/usr/lib/steamac/camera/camera-agent --probe-read "$device"
readable=$?
sleep 12
/usr/lib/steamac/camera/camera-agent --probe-black "$device"
black=$?
echo CAMERA_TEST_RESULT live=$live black=$black enumerable=$enumerable readable=$readable
journalctl -b --no-pager -u steamac-camera.service -n30
if ((live==0 && black==0 && enumerable==0 && readable==0)); then echo CAMERA_TEST_EXIT=0; else echo CAMERA_TEST_EXIT=1; fi
systemctl poweroff
''');runner.chmod(0o755)
(units/'steamac-camera-test.service').write_text('''[Unit]
Description=Camera synthetic integration check (test clone only)
After=steamac-camera.service
[Service]
Type=oneshot
ExecStart=/usr/lib/steamac/camera/camera-test-runner
TimeoutStartSec=110
StandardOutput=journal+console
StandardError=journal+console
[Install]
WantedBy=multi-user.target
''')
(units/'multi-user.target.wants/steamac-camera-test.service').symlink_to('../steamac-camera-test.service')
image(WORK/'camera-selftest.img')
info=plistlib.loads((APP/'Contents/Info.plist').read_bytes());info.update(CFBundleIdentifier='local.ryuu.steamac-lite.camera-experiment',CFBundleName='steamac Lite カメラ実験版',CFBundleDisplayName='steamac Lite カメラ実験版',CFBundleShortVersionString='1.9.8-camera.2',CFBundleVersion='198102',SteamacPreferencesDomain='local.ryuu.steamac-lite.camera-experiment',NSCameraUsageDescription='内蔵カメラの映像を、このMac上のSteamOSとVRChatへ渡す実験に使用します。ボタンを押したときだけ撮影し、映像は保存しません。')
(APP/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
for strings in (APP/'Contents/Resources').glob('*.lproj/InfoPlist.strings'):
 local=plistlib.loads(subprocess.check_output(['plutil','-convert','xml1','-o','-',str(strings)],env=ENV))
 local['CFBundleName']='steamac Lite Camera Test';local['CFBundleDisplayName']='steamac Lite カメラ実験版'
 local['NSCameraUsageDescription']=info['NSCameraUsageDescription']
 strings.write_bytes(plistlib.dumps(local))

entitlements=plistlib.loads((ROOT/'host/launcher/steamac-vm.entitlements').read_bytes());entitlements['com.apple.security.device.camera']=True;(WORK/'camera.entitlements').write_bytes(plistlib.dumps(entitlements))
metadata={'source_commit':json.loads((APP/'Contents/Resources/steamac-lite-provenance.json').read_text())['source_commit'],'version':'1.9.8-camera.2','default_camera_enabled':False,'camera':'built-in only','width':320,'height':240,'capture_width':640,'capture_height':480,'fps':15,'frame_storage':'none','wire_format':'NV12','guest_format':'BGR24','guest_source_sha256':{name:hashlib.file_digest((ROOT/'guest/camera'/name).open('rb'),'sha256').hexdigest() for name in ['camera-agent.c','camera-colors.h','start-camera']},'kernel_image_sha256':hashlib.file_digest((APP/'Contents/Resources/Image').open('rb'),'sha256').hexdigest(),'kernel_config_sha256':hashlib.file_digest((WORK/'kernel.config').open('rb'),'sha256').hexdigest(),'module_config_sha256':hashlib.file_digest((WORK/'module-kernel.config').open('rb'),'sha256').hexdigest(),'module_source':json.loads((ROOT/'guest/camera/loopback-source.json').read_text()),'files':{name:hashlib.file_digest((lib/name).open('rb'),'sha256').hexdigest() for name in ['camera-agent','mf-camera-test.exe','v4l2loopback.ko']}}
(APP/'Contents/Resources/steamac-camera-build.json').write_text(json.dumps(metadata,indent=2)+'\n')
subprocess.run(['codesign','--force','--sign','-','--entitlements',str(WORK/'camera.entitlements'),str(APP/'Contents/MacOS/steamac-vm')],check=True)
subprocess.run(['codesign','--force','--sign','-','--entitlements',str(WORK/'camera.entitlements'),str(APP)],check=True)
subprocess.run(['codesign','--verify','--deep','--strict',str(APP)],check=True)
print('Prepared separate camera app and synthetic-only test layer.')
