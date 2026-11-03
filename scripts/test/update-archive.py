#!/usr/bin/env python3
"""Verify and stage a real release DMG in a disposable directory, without installing or booting."""
from pathlib import Path
import hashlib,os,shutil,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[2]
image=Path(sys.argv[1]).resolve()
ENV={**os.environ,'DEVELOPER_DIR':'/Library/Developer/CommandLineTools'}
sha=hashlib.file_digest(image.open('rb'),'sha256').hexdigest()
with tempfile.TemporaryDirectory(prefix='steamac-archive-test-',dir=ROOT/'work') as temporary:
 d=Path(temporary); main=d/'main.swift'; binary=d/'test'
 main.write_text('''import Foundation
let image=URL(fileURLWithPath:CommandLine.arguments[1])
let size=Int64(CommandLine.arguments[2])!
let digest=CommandLine.arguments[3]
let version=CommandLine.arguments[4]
try UpdateInstallSupport.verifyArchive(image,digest:digest,size:size)
print("matching SHA-256 and size: PASS")
do {
 try UpdateInstallSupport.verifyArchive(image,digest:String(repeating:"0",count:64),size:size)
 fatalError("wrong digest accepted")
} catch UpdateInstallSupport.Failure.checksum { print("wrong SHA-256 rejected: PASS") }
do {
 try UpdateInstallSupport.verifyArchive(image,digest:digest,size:size+1)
 fatalError("wrong size accepted")
} catch UpdateInstallSupport.Failure.size { print("wrong size rejected: PASS") }
let target=image.deletingLastPathComponent().appendingPathComponent("test.app")
let staged=try UpdateInstallSupport.prepare(image,version:version,size:size,destination:target)
defer { try? FileManager.default.removeItem(at:staged.deletingLastPathComponent()) }
try UpdateInstallSupport.validateApp(staged,version:version)
print("read-only mount, copied app identity and signature, detach: PASS")
''')
 subprocess.run(['swiftc',str(ROOT/'host/launcher/Sources/steamac-vm/UpdateInstallSupport.swift'),str(main),'-o',str(binary)],env=ENV,check=True)
 copy=d/'download.dmg';shutil.copyfile(image,copy)
 version=sys.argv[2] if len(sys.argv)>2 else '1.9.4-lite.8'
 subprocess.run([str(binary),str(copy),str(image.stat().st_size),sha,version],env=ENV,check=True)
 assert hashlib.file_digest(image.open('rb'),'sha256').hexdigest()==sha
print('update archive: PASS; original DMG unchanged; no VM started')
