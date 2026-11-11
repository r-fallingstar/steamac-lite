#!/usr/bin/env python3
"""Exercise installer release selection, localization and real filesystem replacement."""
from pathlib import Path
import os,plistlib,shutil,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[2]
ENV={**os.environ,'DEVELOPER_DIR':'/Library/Developer/CommandLineTools'}
with tempfile.TemporaryDirectory(prefix='network-installer-test-',dir=ROOT/'work') as temporary:
 root=Path(temporary)
 def bundle(path,version):
  (path/'Contents/MacOS').mkdir(parents=True)
  executable=path/'Contents/MacOS/steamac-vm';shutil.copyfile('/usr/bin/true',executable);executable.chmod(0o755)
  (path/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'local.ryuu.steamac-lite','CFBundleShortVersionString':version,'CFBundleExecutable':'steamac-vm','SteamacLiteBuild':True,'CFBundlePackageType':'APPL'}))
  for p in [executable,path]:subprocess.run(['codesign','--force','--sign','-',str(p)],env=ENV,check=True,capture_output=True)
 for name,old in [('fresh',None),('upgrade','1.9.4-lite.7'),('running','1.9.4-lite.7'),('newer','1.9.4-lite.9'),('rollback','1.9.4-lite.7')]:
  d=root/name;d.mkdir();stage=d/'.steamac-update-fixture';stage.mkdir();bundle(stage/'SteamAC Lite.app','1.9.4-lite.8')
  if old:bundle(d/'SteamAC Lite.app',old)
  (d/'steamos.img').write_text('unchanged disk sentinel')
 main=root/'main.swift'
 main.write_text(r'''import Foundation
func require(_ value: Bool, _ name: String) { if !value { fatalError(name) }; print(name + ": PASS") }
func fixture(_ number: Int) -> [String: Any] {
 let v="1.9.4-lite.\(number)";let tag="v"+v;let name="SteamAC-Lite-\(v)-macos-arm64.dmg"
 return ["tag_name":tag,"draft":false,"prerelease":true,"assets":[["name":name,"state":"uploaded","size":100,"digest":"sha256:"+String(repeating:"a",count:64),"browser_download_url":"https://github.com/r-fallingstar/steamac-lite/releases/download/\(tag)/\(name)"]]]
}
func selected(_ objects: [[String:Any]]) throws -> InstallerCore.Release { try InstallerCore.latest(JSONSerialization.data(withJSONObject:objects)) }
let release=try selected([fixture(8)])
require(try selected([fixture(9),fixture(10)]).version=="1.9.4-lite.10","numeric latest release")
var draft=fixture(99);draft["draft"]=true
var foreign=fixture(98);foreign["tag_name"]="v1.9.4-eac.99"
require(try selected([draft,foreign,fixture(8)]).version==release.version,"draft and other channels excluded")
for field in ["name","state","size","digest","browser_download_url"] {
 var damaged=fixture(8);var asset=(damaged["assets"] as! [[String:Any]])[0]
 asset[field]=field=="size" ? 0 : "invalid";damaged["assets"]=[asset]
 do { _=try selected([damaged]);fatalError("invalid asset accepted") } catch { print("invalid asset \(field): PASS") }
}
for invalid in ["v1.9-lite.8","v1.9.4-lite.8-rc1","nightly","v1.9.4-lite.-1"] {require(InstallerCore.version(invalid)==nil,"invalid version "+invalid)}
require(InstallerText.values.count==InstallerText.allCases.count,"all UI keys supplied")
for key in InstallerText.allCases {
 let row=InstallerText.values[key]!
 require(row.count==5 && row.allSatisfy{!$0.isEmpty},"five languages "+key.rawValue)
 require(Set(row.map{$0.components(separatedBy:"%@").count}).count==1,"format arguments "+key.rawValue)
}
let root=URL(fileURLWithPath:CommandLine.arguments[1])
for name in ["fresh","upgrade","running","newer","rollback"] {
 let directory=root.appendingPathComponent(name);let target=directory.appendingPathComponent("SteamAC Lite.app");let staged=directory.appendingPathComponent(".steamac-update-fixture/SteamAC Lite.app")
 let before=try? Data(contentsOf:target.appendingPathComponent("Contents/Info.plist"))
 do {
  let installed=try InstallerCore.install(staged:staged,to:target,release:release,isRunning:{name=="running"},verify:{ app,version in
   try UpdateInstallSupport.validateApp(app,version:version)
   if name=="rollback" && app==target { throw InstallerCore.Failure.destination }
  })
  require(name != "running" && name != "rollback","unexpected success check "+name)
  require(installed==(name=="newer" ? "1.9.4-lite.9":"1.9.4-lite.8"),"installed version "+name)
 } catch {
  require(name=="running" || name=="rollback","expected failure "+name)
  require(try Data(contentsOf:target.appendingPathComponent("Contents/Info.plist"))==before,"original app preserved "+name)
 }
 require(try String(contentsOf:directory.appendingPathComponent("steamos.img"),encoding:.utf8)=="unchanged disk sentinel","disk preserved "+name)
}
print("network installer: PASS; no app or VM launched")
'''.replace('\\(', '\\('))
 binary=root/'tests'
 subprocess.run(['swiftc',str(ROOT/'host/launcher/Sources/steamac-vm/UpdateInstallSupport.swift'),str(ROOT/'host/launcher/Sources/steamac-vm/InstallerCore.swift'),str(ROOT/'host/installer/InstallerStrings.swift'),str(main),'-o',str(binary)],env=ENV,check=True)
 subprocess.run([str(binary),str(root)],env=ENV,check=True)
