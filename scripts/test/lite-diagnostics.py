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
let code137 = LauncherExit(waitStatus: 137 << 8)
let killed = LauncherExit(waitStatus: SIGKILL)
check(code137.code == 137 && code137.signal == 0 && code137.status == killed.status)
check(killed.signal == SIGKILL && killed.isUnexpected(userRequested: false))
check(!killed.isUnexpected(userRequested: true))
check(killed.isUnexpected(userRequested: true, killedForMemory: true))
typealias KillReason = LiteDiagnostics.KillReason
check(KillReason(exitDetail: nil) == .unavailable)
check(KillReason(exitDetail: 0) == .unspecified)
check(KillReason(exitDetail: UInt32(NOTE_EXIT_MEMORY)) == .memory)
check(KillReason(exitDetail: UInt32(NOTE_EXIT_CSERROR)) == .codeSigning)
check(KillReason(exitDetail: UInt32(NOTE_EXIT_DECRYPTFAIL)) == .decryption)
check(KillReason(exitDetail: UInt32(NOTE_EXIT_MEMORY) | UInt32(NOTE_EXIT_CSERROR)) == .memory)
let vmReport = LiteDiagnostics.report(kind: "vm-killed", stage: "ready", elapsed: 12, outcome: killed, killReason: .memory)
check(vmReport.exit_code == nil && vmReport.signal == Int(SIGKILL) && vmReport.elapsed_s == 12)
check(vmReport.kill_reason == .memory)
let legacy = LiteDiagnostics.report(kind: "vm-killed", stage: "ready", outcome: killed)
let legacyData = try JSONEncoder().encode(legacy)
check(try JSONDecoder().decode(LiteDiagnostics.Report.self, from: legacyData).kill_reason == nil)
try JSONEncoder().encode(vmReport).write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
print("diagnostics-core: PASS (\(checks) assertions)")
''')
    helper = d / 'core-check'
    subprocess.run(['xcrun', 'swiftc', '-swift-version', '5', str(core), str(permissions), str(main), '-o', str(helper)], env=env, check=True)
    subprocess.run([str(helper), str(d / 'report.json'), 'test'], env=env, check=True)
    subprocess.run([str(helper), 'off'], env=env, check=True)
    # Swift's emitted JSON must pass the actual receiver's allowlist.
    subprocess.run(['node', '--input-type=module', '-e',
        "import assert from 'node:assert/strict'; import {validate} from './services/diagnostics/src/index.js'; import fs from 'node:fs'; assert.equal(validate(JSON.parse(fs.readFileSync(process.argv[1]))).kill_reason, 'memory');", str(d / 'report.json')], cwd=ROOT, check=True)
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
                    *(str(core.parent / name) for name in ('DmgInstall.swift', 'InstallerCore.swift', 'UpdateInstallSupport.swift')),
                    '-o', str(binary / 'steamac-vm')], env=env, check=True)
    main.write_text(r'''
import Darwin
import Foundation

switch CommandLine.arguments.last {
case "--selftest-fixture":
    exit(23)
case "force-quit":
    exit(LauncherExit.forceQuitStatus)
case "startup-refused":
    exit(LauncherExit.startupRejectedStatus)
case "requested-shutdown":
    LiteDiagnostics.checkpoint("shutdown")
    LiteDiagnostics.markVMExitHandled(status: 128 + SIGKILL)
    exit(128 + SIGKILL)
case "vm-killed":
    LiteDiagnostics.checkpoint("ready")
    let outcome = LauncherExit(code: 0, signal: SIGKILL)
    LiteDiagnostics.enqueue(LiteDiagnostics.report(kind: "vm-killed", stage: "ready", elapsed: 12, outcome: outcome))
    LiteDiagnostics.checkpoint("ready", waiting: true)
    LiteDiagnostics.markVMExitHandled(status: outcome.status)
    exit(outcome.status)
case "launcher-killed":
    LiteDiagnostics.checkpoint("vm-setup")
    LiteDiagnostics.markVMExitHandled(status: 128 + SIGKILL)
    raise(SIGKILL)
case "launcher-code-137":
    LiteDiagnostics.checkpoint("options")
    LiteDiagnostics.markVMExitHandled(status: 1)
    exit(137)
case "revoked":
    LiteDiagnostics.consent(false)
    LiteDiagnostics.consent(true)
    exit(1)
case "hold":
    LiteDiagnostics.checkpoint("ready")
    while true { pause() }
default:
    break
}
''')
    subprocess.run(['xcrun', 'swiftc', '-swift-version', '5', str(core), str(main), '-o', str(binary / 'steamac-runtime')], env=env, check=True)
    wrapper = binary / 'steamac-vm'
    for lang in ['ja', 'en']:
        subprocess.run([str(wrapper), '--selftest-wizard-layout', '--selftest-out', str(d/lang), '-AppleLanguages', '('+lang+')'], env=env, check=True)
    assert subprocess.run([str(wrapper), '--selftest-fixture'], env=env).returncode == 23
    assert subprocess.run([str(wrapper)], env=env).returncode == 0  # opt-out exec path
    subprocess.run([str(helper), 'on'], env=env, check=True)
    root = Path.home() / 'Library/Application Support' / env['STEAMAC_DEFAULTS_DOMAIN'] / 'diagnostics'
    def run_runtime(mode, status):
        previous = set((root / 'pending').glob('*.json'))
        assert subprocess.run([str(wrapper), mode], env=env, timeout=10).returncode == status
        return [json.loads(p.read_text()) for p in set((root / 'pending').glob('*.json')) - previous]

    killed_status = 128 + signal.SIGKILL
    assert not run_runtime('force-quit', 3)
    assert not run_runtime('startup-refused', 4)
    assert not run_runtime('requested-shutdown', killed_status)
    report, = run_runtime('vm-killed', killed_status)
    assert report['kind'] == 'vm-killed' and report['stage'] == 'ready' and report['elapsed_s'] == 12
    assert report['signal'] == signal.SIGKILL and 'exit_code' not in report
    report, = run_runtime('launcher-killed', killed_status)
    assert report['kind'] == 'launcher-crashed' and report['stage'] == 'vm-setup'
    assert report['signal'] == signal.SIGKILL and 'exit_code' not in report
    report, = run_runtime('launcher-code-137', 137)
    assert report['kind'] == 'launcher-crashed' and report['stage'] == 'options'
    assert report['exit_code'] == 137 and 'signal' not in report
    assert not run_runtime('revoked', 1)
    assert not list((root / 'pending').glob('*.json'))
    subprocess.run([str(helper), 'off'], env=env, check=True)
    assert not (root / 'pending').exists()
    subprocess.run([str(helper), 'on'], env=env, check=True)
    process = subprocess.Popen([str(wrapper), 'hold'], env=env)
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if any(json.loads(p.read_text())['stage'] == 'ready' for p in root.glob('session-*/state.json')):
                break
            time.sleep(0.05)
        else:
            raise AssertionError('diagnostics runtime did not start')
        process.terminate()
        assert process.wait(timeout=10) == 128 + signal.SIGTERM
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
    assert not list((root / 'pending').glob('*.json'))  # requested quit is not a crash
    subprocess.run([str(helper), 'off'], env=env, check=True)
    shutil.rmtree(root.parent)
    subprocess.run(['/usr/bin/defaults', 'delete', env['STEAMAC_DEFAULTS_DOMAIN']], capture_output=True)
    print('diagnostics-bootstrap: PASS (utility, opt-out, VM exit handoff, launcher exit, user quit, consent revocation)')
