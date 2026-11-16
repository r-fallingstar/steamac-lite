#!/usr/bin/env python3
"""Test the real core/bootstrap with disposable preferences and a fake runtime; no VM/network."""
from pathlib import Path
import json
import os
import plistlib
import shutil
import signal
import subprocess
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
env = {**os.environ, 'DEVELOPER_DIR': '/Library/Developer/CommandLineTools',
       'STEAMAC_DEFAULTS_DOMAIN': 'local.ryuu.steamac-lite.diag-test.' + uuid.uuid4().hex}
core = ROOT / 'host/launcher/Sources/steamac-vm/LiteDiagnostics.swift'
permissions = ROOT / 'host/diagnostics/StartupPermissions.swift'
with tempfile.TemporaryDirectory(prefix='diag-test-', dir=ROOT / 'work') as directory:
    d = Path(directory)
    main = d / 'main.swift'
    main.write_text(r'''
import Foundation
import Darwin
import AVFoundation
let mode = CommandLine.arguments.last!
if mode == "on" || mode == "off" { LiteDiagnostics.consent(mode == "on"); LiteDiagnostics.defaults.set(1, forKey: "liteFirstRunWizardVersion"); LiteDiagnostics.defaults.synchronize(); exit(0) }
var checks = 0
func check(_ ok: Bool) { precondition(ok); checks += 1 }
for audio in [false, true] {
    for video in [false, true] {
        var asked: [AVMediaType] = [], completed = 0
        StartupPermissions.resolve(microphone: audio, camera: video, status: { _ in .notDetermined },
            request: { media, done in asked.append(media); done(false) }, completion: { completed += 1 })
        check(asked == (audio ? [.audio] : []) + (video ? [.video] : []))
        check(completed == 1)
    }
}
for status: AVAuthorizationStatus in [.authorized, .denied, .restricted] {
    var asked = false, completed = false
    StartupPermissions.resolve(microphone: true, camera: true, status: { _ in status },
        request: { _, done in asked = true; done(true) }, completion: { completed = true })
    check(!asked && completed)
}
LiteDiagnostics.defaults.removePersistentDomain(forName: LiteDiagnostics.domain)
LiteDiagnostics.defaults.set(true, forKey: LiteDiagnostics.enabledKey)
check(!LiteDiagnostics.allowed) // old recipient consent is not enough
LiteDiagnostics.enqueue(LiteDiagnostics.report(kind: "startup-stalled"))
check(LiteDiagnostics.pending().isEmpty)
LiteDiagnostics.consent(true)
check(LiteDiagnostics.allowed)
for _ in 0..<6 { LiteDiagnostics.enqueue(LiteDiagnostics.report(kind: "startup-stalled")) }
check(LiteDiagnostics.pending().count == 4) // persistent daily cap
LiteDiagnostics.consent(false)
check(!LiteDiagnostics.allowed && LiteDiagnostics.pending().isEmpty)
var w = LiteDiagnostics.Watch(now: 0)
for i in stride(from: 5.0, through: 175, by: 5) { check(w.tick(now: i, state: nil, heartbeat: nil) == nil) }
check(w.tick(now: 180, state: nil, heartbeat: nil) == "startup-stalled")
check(w.tick(now: 185, state: nil, heartbeat: nil) == nil)
w = LiteDiagnostics.Watch(now: 0)
for i in stride(from: 5.0, through: 600, by: 5) {
    check(w.tick(now: i, state: .init(stage: "language", uptime: 0, waiting: true, pid: 1), heartbeat: nil) == nil)
}
w = LiteDiagnostics.Watch(now: 0)
for i in stride(from: 5.0, through: 600, by: 5) {
    check(w.tick(now: i, state: .init(stage: "steam-download", uptime: floor(i / 60) * 60, waiting: false, pid: 1), heartbeat: i) == nil)
}
w = LiteDiagnostics.Watch(now: 0)
check(w.tick(now: 5000, state: nil, heartbeat: nil) == nil) // sleep/scheduling gap
for i in stride(from: 5005.0, through: 5175, by: 5) { check(w.tick(now: i, state: nil, heartbeat: nil) == nil) }
check(w.tick(now: 5180, state: nil, heartbeat: nil) == "startup-stalled")
w = LiteDiagnostics.Watch(now: 0)
for i in stride(from: 5.0, through: 600, by: 5) {
    check(w.tick(now: i, state: .init(stage: "ready", uptime: 0, waiting: false, pid: 1), heartbeat: i) == nil)
}
for i in stride(from: 605.0, through: 775, by: 5) { check(w.tick(now: i, state: .init(stage: "ready", uptime: 0, waiting: false, pid: 1), heartbeat: 600) == nil) }
check(w.tick(now: 780, state: .init(stage: "ready", uptime: 0, waiting: false, pid: 1), heartbeat: 600) == "app-unresponsive")
try JSONEncoder().encode(LiteDiagnostics.report(kind: "startup-stalled")).write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
print("diagnostics-core: PASS (\(checks) assertions)")
''')
    helper = d / 'core-check'
    subprocess.run(['xcrun', 'swiftc', '-swift-version', '5', str(core), str(permissions), str(main), '-o', str(helper)], env=env, check=True)
    subprocess.run([str(helper), str(d / 'report.json'), 'test'], env=env, check=True)
    subprocess.run([str(helper), 'off'], env=env, check=True)
    # Swift's emitted JSON must pass the actual receiver's allowlist.
    subprocess.run(['node', '--input-type=module', '-e',
        "import {validate} from './services/diagnostics/src/index.js'; import fs from 'node:fs'; validate(JSON.parse(fs.readFileSync(process.argv[1])));", str(d / 'report.json')], cwd=ROOT, check=True)
    test_support = Path.home() / 'Library/Application Support' / env['STEAMAC_DEFAULTS_DOMAIN']
    shutil.rmtree(test_support / 'diagnostics')
    app = d / 'Diagnostic Fixture.app'
    binary = app / 'Contents/MacOS'
    binary.mkdir(parents=True)
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({
        'CFBundleIdentifier': env['STEAMAC_DEFAULTS_DOMAIN'], 'CFBundleExecutable': 'steamac-vm',
        'CFBundlePackageType': 'APPL', 'CFBundleShortVersionString': '1.9.8-lite.7',
        'SteamacLiteBuild': True, 'SteamacGitCommit': 'abcdef1234', 'LSUIElement': True}))
    subprocess.run(['xcrun', 'swiftc', '-swift-version', '5', str(core), str(permissions), str(ROOT / 'host/diagnostics/FirstRunWizard.swift'), str(ROOT / 'host/diagnostics/main.swift'),
                    '-o', str(binary / 'steamac-vm')], env=env, check=True)
    runtime = d / 'runtime.c'
    runtime.write_text('''#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
int main(int n, char **v) {
 if (n>1 && !strcmp(v[1],"--selftest-fixture")) return 23;
 if (n>1 && !strcmp(v[1],"crash")) { raise(SIGKILL); return 0; }
 if (n>1 && !strcmp(v[1],"hold")) { while(1) pause(); }
 return 0;
}
''')
    subprocess.run(['xcrun', 'clang', str(runtime), '-o', str(binary / 'steamac-runtime')], env=env, check=True)
    wrapper = binary / 'steamac-vm'
    for lang in ['ja', 'en']:
        subprocess.run([str(wrapper), '--selftest-wizard-layout', '--selftest-out', str(d/lang), '-AppleLanguages', '('+lang+')'], env=env, check=True)
    assert subprocess.run([str(wrapper), '--selftest-fixture'], env=env).returncode == 23
    assert subprocess.run([str(wrapper)], env=env).returncode == 0  # opt-out exec path
    subprocess.run([str(helper), 'on'], env=env, check=True)
    assert subprocess.run([str(wrapper), 'crash'], env=env, timeout=10).returncode == 128 + signal.SIGKILL
    root = Path.home() / 'Library/Application Support' / env['STEAMAC_DEFAULTS_DOMAIN'] / 'diagnostics'
    reports = [json.loads(p.read_text()) for p in (root / 'pending').glob('*.json')]
    assert any(r.get('signal') == signal.SIGKILL and r['kind'] == 'launcher-crashed' for r in reports)
    subprocess.run([str(helper), 'off'], env=env, check=True)
    assert not (root / 'pending').exists()
    subprocess.run([str(helper), 'on'], env=env, check=True)
    process = subprocess.Popen([str(wrapper), 'hold'], env=env)
    time.sleep(0.5)
    process.terminate()
    assert process.wait(timeout=10) == 128 + signal.SIGTERM
    assert not list((root / 'pending').glob('*.json'))  # requested quit is not a crash
    subprocess.run([str(helper), 'off'], env=env, check=True)
    shutil.rmtree(root.parent)
    subprocess.run(['/usr/bin/defaults', 'delete', env['STEAMAC_DEFAULTS_DOMAIN']], capture_output=True)
    print('diagnostics-bootstrap: PASS (utility, opt-out, crash capture, user quit, queue deletion)')
