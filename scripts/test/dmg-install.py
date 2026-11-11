#!/usr/bin/env python3
"""Test the DMG install transaction using signed bundles and isolated destinations."""
from pathlib import Path
import os, plistlib, shutil, subprocess, tempfile

ROOT = Path(__file__).resolve().parents[2]
ENV = {**os.environ, 'DEVELOPER_DIR': '/Library/Developer/CommandLineTools'}
with tempfile.TemporaryDirectory(prefix='dmg-install-test-', dir=ROOT/'work') as temporary:
    root = Path(temporary)

    def bundle(path, version):
        (path/'Contents/MacOS').mkdir(parents=True)
        executable = path/'Contents/MacOS/steamac-vm'
        shutil.copyfile('/usr/bin/true', executable)
        executable.chmod(0o755)
        (path/'Contents/Info.plist').write_bytes(plistlib.dumps({
            'CFBundleIdentifier': 'local.ryuu.steamac-lite',
            'CFBundleShortVersionString': version, 'CFBundleExecutable': 'steamac-vm',
            'SteamacLiteBuild': True, 'CFBundlePackageType': 'APPL'}))
        for p in [executable, path]:
            subprocess.run(['codesign', '--force', '--sign', '-', str(p)],
                           env=ENV, check=True, capture_output=True)

    bundle(root/'source/SteamAC Lite.app', '1.9.4-lite.12')
    for name, version in [('fresh', None), ('upgrade', '1.9.4-lite.9'),
                          ('same', '1.9.4-lite.12'), ('newer', '1.9.4-lite.13'),
                          ('running', '1.9.4-lite.9'), ('invalid', '1.9.4-lite.9')]:
        d = root/name
        d.mkdir()
        (d/'steamos.img').write_text('keep disk')
        if version:
            bundle(d/'SteamAC Lite.app', version)
    (root/'invalid/SteamAC Lite.app/Contents/MacOS/steamac-vm').write_text('broken signature')
    (root/'linked').symlink_to(root/'fresh', target_is_directory=True)
    main = root/'main.swift'
    main.write_text(r'''import AppKit
import Foundation
// Only satisfy the interactive launch entry point; no test calls it.
enum Supervisor { static let isChild = false }
enum AppBundle { static let resources: String? = nil }
func require(_ value: Bool, _ message: String) { if !value { fatalError(message) };print(message+": PASS") }
let root=URL(fileURLWithPath:CommandLine.arguments[1],isDirectory:true)
let source=root.appendingPathComponent("source/SteamAC Lite.app")
require(DmgInstall.needsInstallation(source,readOnly:true),"read-only mount detected outside /Volumes")
require(DmgInstall.needsInstallation(URL(fileURLWithPath:"/private/var/folders/x/AppTranslocation/id/d/SteamAC Lite.app"),readOnly:false),"translocation detected")
require(!DmgInstall.needsInstallation(URL(fileURLWithPath:"/Applications/SteamAC Lite.app"),readOnly:false),"installed app not prompted")
for (name,expected) in [("fresh","1.9.4-lite.12"),("upgrade","1.9.4-lite.12"),("same","1.9.4-lite.12"),("newer","1.9.4-lite.13")] {
 let target=root.appendingPathComponent(name+"/SteamAC Lite.app")
 require(try DmgInstall.prepare(source:source,target:target)==target,name+" destination")
 require(try InstallerCore.installedVersion(at:target)==expected,name+" verified version")
 require(try String(contentsOf:root.appendingPathComponent(name+"/steamos.img"),encoding:.utf8)=="keep disk",name+" disk retained")
}
for name in ["running","invalid","linked"] {
 let target=root.appendingPathComponent(name+"/SteamAC Lite.app")
 do { _=try DmgInstall.prepare(source:source,target:target,isRunning:{name=="running"});fatalError(name+" accepted") }
 catch {print(name+" refused: PASS")}
}
require(try InstallerCore.installedVersion(at:root.appendingPathComponent("running/SteamAC Lite.app"))=="1.9.4-lite.9","running app unchanged")
let stages=try FileManager.default.subpathsOfDirectory(atPath:root.path).filter{$0.contains(".steamac-update-")}
require(stages.isEmpty,"temporary stages cleaned")
''')
    binary = root/'test'
    sources = ROOT/'host/launcher/Sources/steamac-vm'
    subprocess.run(['swiftc', '-swift-version', '5',
                    *[str(sources/name) for name in ['UpdateInstallSupport.swift', 'InstallerCore.swift', 'DmgInstall.swift']],
                    str(main), '-o', str(binary)], env=ENV, check=True)
    subprocess.run([str(binary), str(root)], env=ENV, check=True)
