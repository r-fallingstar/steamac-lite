#!/usr/bin/env python3
"""Exercise the real replacement helper on disposable signed apps, without launching a VM."""
import hashlib,json,os,plistlib,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
ENV={**os.environ,'DEVELOPER_DIR':'/Library/Developer/CommandLineTools'}

def run(args,**kw):
 return subprocess.run(list(map(str,args)),env=kw.pop('env',ENV),check=True,capture_output=True,**kw)

with tempfile.TemporaryDirectory(prefix='steamac-update-test-',dir=ROOT/'work') as td:
 root=Path(td)
 helper=root/'updater'
 run(['swiftc','-DUPDATE_INSTALL_TESTING',ROOT/'host/launcher/Sources/steamac-vm/UpdateInstallSupport.swift',ROOT/'host/launcher/updater/main.swift','-o',helper])
 production_helper=root/'updater-production'
 run(['swiftc',ROOT/'host/launcher/Sources/steamac-vm/UpdateInstallSupport.swift',ROOT/'host/launcher/updater/main.swift','-o',production_helper])
 stub_source=root/'stub.swift'
 stub_source.write_text('import AppKit\nlet app=NSApplication.shared\napp.setActivationPolicy(.accessory)\nDispatchQueue.main.asyncAfter(deadline: .now()+2) { app.terminate(nil) }\napp.run()\n')
 stub=root/'stub'
 run(['swiftc',stub_source,'-o',stub])
 def app(path,version,gui=False):
  (path/'Contents/MacOS').mkdir(parents=True)
  shutil.copyfile(stub if gui else '/usr/bin/true',path/'Contents/MacOS/steamac-vm')
  (path/'Contents/MacOS/steamac-vm').chmod(0o755)
  (path/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'local.ryuu.steamac-lite','CFBundleShortVersionString':version,'CFBundleExecutable':'steamac-vm','CFBundlePackageType':'APPL','SteamacLiteBuild':True}))
  run(['codesign','--force','--sign','-',path/'Contents/MacOS/steamac-vm'])
  run(['codesign','--force','--sign','-',path])
 def case(name,*,expected=0,damage=None,alive=False,launch_fail=False,production=False):
  base=root/name;base.mkdir();target=base/'SteamAC Lite.app';stage=base/'.steamac-update-test';stage.mkdir();new=stage/'SteamAC Lite.app'
  app(target,'1.9.4-lite.7',production);app(new,'1.9.4-lite.8',production)
  original=(target/'Contents/Info.plist').read_bytes()
  sentinel=base/'steamos.img';sentinel.write_bytes(b'user SteamOS disk must not change')
  digest=hashlib.sha256(sentinel.read_bytes()).hexdigest()
  if damage=='signature': (new/'Contents/MacOS/steamac-vm').write_bytes(b'corrupt')
  if damage=='version':
   info=plistlib.loads((new/'Contents/Info.plist').read_bytes());info['CFBundleShortVersionString']='1.9.4-lite.99';(new/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
   run(['codesign','--force','--sign','-',new])
  waiter=subprocess.Popen(['/bin/sleep','30']) if alive else None
  plan={'destination':str(target),'stagedApp':str(new),'previousVersion':'1.9.4-lite.7','version':'1.9.4-lite.8','processIDs':[waiter.pid if waiter else 999999],'failureTitle':'test','failureMessage':'test','releasesLabel':'releases','closeLabel':'close'}
  if damage=='path':plan['stagedApp']=str(target)
  p=stage/'install.json';p.write_text(json.dumps(plan))
  env={**ENV,'UPDATE_TEST_LAUNCH_FAIL':'1' if launch_fail else '0'}
  try:r=subprocess.run([production_helper if production else helper,p],env=env,capture_output=True,timeout=15)
  finally:
   if waiter:waiter.terminate();waiter.wait()
  assert r.returncode==expected,(name,r.returncode,r.stderr)
  actual=plistlib.loads((target/'Contents/Info.plist').read_bytes())['CFBundleShortVersionString']
  assert actual==('1.9.4-lite.8' if expected==0 else '1.9.4-lite.7'),(name,actual)
  if expected:assert (target/'Contents/Info.plist').read_bytes()==original,name
  assert hashlib.sha256(sentinel.read_bytes()).hexdigest()==digest,name
  run(['codesign','--verify','--deep','--strict',target])
  print(name+': PASS')
 case('replace')
 case('real-relaunch',production=True)
 case('signature-rejected',expected=1,damage='signature')
 case('version-rejected',expected=1,damage='version')
 case('path-rejected',expected=1,damage='path')
 case('running-process-waits',expected=1,alive=True)
 case('relaunch-failure-rolls-back',expected=1,launch_fail=True)
print('in-app update helper: PASS (7 cases; no VM started)')
