import AppKit
import AVFoundation
import Darwin
import Foundation
import os

// CFBundleExecutable stays steamac-vm for compatibility with Lite.9's updater.
// The old executable moves to steamac-runtime. This tiny executable never links
// libkrun, Metal, drivers or Sentry, so its timer survives a runtime dyld/main hang.
let runtime = Bundle.main.bundleURL.appendingPathComponent("Contents/MacOS/steamac-runtime")
let arguments = Array(CommandLine.arguments.dropFirst())
func execRuntime() -> Never {
    let argv = ([runtime.path] + arguments).map { strdup($0) } + [nil]
    execv(runtime.path, argv)
    _ = "steamac Lite: cannot start runtime (errno \(errno))\n".withCString { write(STDERR_FILENO, $0, strlen($0)) }
    exit(127)
}
if arguments.contains("--selftest-dmg-install") {
    MainActor.assumeIsolated { DmgInstall.runIfNeeded(review: true) }
    exit(2)
}
if arguments.contains("--selftest-wizard-layout") {
    _ = NSApplication.shared
    let wizard = FirstRunWizard(arguments: [])
    let failures = wizard.layoutFailures()
    if let index = arguments.firstIndex(of: "--selftest-out"), index + 1 < arguments.count {
        let directory = URL(fileURLWithPath: arguments[index + 1], isDirectory: true)
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            let data = try JSONSerialization.data(withJSONObject: ["passed": failures.isEmpty, "failures": failures,
                "window_width": wizard.window.frame.width, "window_height": wizard.window.frame.height], options: [.prettyPrinted])
            try data.write(to: directory.appendingPathComponent("layout-validation.json"), options: .atomic)
        } catch { print("wizard-layout: FAIL \(error)"); exit(1) }
    }
    print(failures.isEmpty ? "wizard-layout: PASS" : "wizard-layout: FAIL " + failures.joined(separator: "; "))
    exit(failures.isEmpty ? 0 : 1)
}
let utility = arguments.contains { $0.hasPrefix("--selftest") || $0.hasPrefix("--sentry-test") ||
    ["--help", "-h", "--headless", "--preview-update", "--ssh-password", "--create-disk", "--grow-disk"].contains($0) }
if utility || ProcessInfo.processInfo.environment["STEAMAC_VM_CHILD"] == "1" { execRuntime() }
// macOS stores these fixed markers locally. They also work before any consent
// decision, and are collected only when the user runs the support script.
let startupLog = Logger(subsystem: "local.ryuu.steamac-lite.startup", category: "bootstrap")
startupLog.notice("bootstrap-entered")
// Preserve Finder-launch error dialogs when the real runtime's parent is now
// this bootstrap rather than launchd. Command-line utilities keep terminal errors.
if getppid() == 1 { setenv("STEAMAC_GUI_LAUNCH", "1", 1) }

// The installer runs before the wizard, which relaunches the bundle after saving its settings.
MainActor.assumeIsolated { DmgInstall.runIfNeeded() }

let needsWizard = LiteDiagnostics.defaults.integer(forKey: LiteDiagnostics.consentKey) != LiteDiagnostics.consentVersion
    || LiteDiagnostics.defaults.integer(forKey: FirstRunWizard.versionKey) != 1
startupLog.notice("preferences-read")
if needsWizard {
    startupLog.notice("appkit-starting")
    let app = NSApplication.shared
    app.setActivationPolicy(.regular)
    startupLog.notice("appkit-ready")
    let wizard = FirstRunWizard(arguments: arguments)
    startupLog.notice("wizard-created")
    DispatchQueue.main.async {
        startupLog.notice("wizard-showing")
        wizard.show()
        startupLog.notice("wizard-presented")
    }
    withExtendedLifetime(wizard) { app.run() }
    exit(0)
}

guard LiteDiagnostics.allowed else {
    LiteDiagnostics.clearQueue()
    startupLog.notice("runtime-exec")
    execRuntime()
}

// An OS reboot or killing the whole process group may also kill the monitor.
// On the next opt-in launch, report only a demonstrably abandoned session, and
// label the cause unknown rather than calling a force-quit a native crash.
for old in (try? FileManager.default.contentsOfDirectory(at: LiteDiagnostics.root, includingPropertiesForKeys: nil)) ?? []
    where old.lastPathComponent.hasPrefix("session-") {
    guard let ownerText = try? String(contentsOf: old.appendingPathComponent("owner"), encoding: .utf8),
          let owner = Int32(ownerText), owner > 1, kill(owner, 0) == -1, errno == ESRCH,
          let state = LiteDiagnostics.readState(in: old),
          state.pid > 1, kill(state.pid, 0) == -1, errno == ESRCH else { continue }
    if !state.waiting && state.stage != "shutdown" && !FileManager.default.fileExists(atPath: old.appendingPathComponent("revoked").path) {
        LiteDiagnostics.enqueue(LiteDiagnostics.report(kind: "previous-session-incomplete", stage: state.stage))
    }
    try? FileManager.default.removeItem(at: old)
}

let directory = LiteDiagnostics.root.appendingPathComponent("session-" + UUID().uuidString, isDirectory: true)
do { try LiteDiagnostics.privateDirectory(LiteDiagnostics.root); try LiteDiagnostics.privateDirectory(directory) }
catch { execRuntime() }
try? String(getpid()).write(to: directory.appendingPathComponent("owner"), atomically: true, encoding: .utf8)
setenv("STEAMAC_DIAGNOSTIC_SESSION", directory.path, 1)
LiteDiagnostics.checkpoint("launcher")

let child = Process()
child.executableURL = runtime; child.arguments = arguments
child.environment = ProcessInfo.processInfo.environment
let started = ProcessInfo.processInfo.systemUptime
var watch = LiteDiagnostics.Watch(now: started)
var stopping = false
var uploadRunning = false
let events = DispatchQueue(label: "steamac.diagnostics.watch")
var signals: [DispatchSourceSignal] = []
for sig in [SIGTERM, SIGINT, SIGHUP, SIGUSR1] {
    signal(sig, SIG_IGN)
    let source = DispatchSource.makeSignalSource(signal: sig, queue: events)
    source.setEventHandler {
        if sig != SIGUSR1 { stopping = true }
        if child.isRunning { kill(child.processIdentifier, sig) }
    }
    source.resume(); signals.append(source)
}
func flushSoon() {
    guard !uploadRunning else { return }; uploadRunning = true
    Task {
        await LiteDiagnostics.flush()
        events.async { uploadRunning = false }
    }
}
let timer = DispatchSource.makeTimerSource(queue: events)
timer.schedule(deadline: .now() + 5, repeating: 5, leeway: .seconds(1))
timer.setEventHandler {
    guard LiteDiagnostics.sessionAllowsReporting(directory) else { return }
    let state = LiteDiagnostics.readState(in: directory)
    let heartbeat = (try? String(contentsOf: directory.appendingPathComponent("heartbeat"), encoding: .utf8)).flatMap(Double.init)
    let now = ProcessInfo.processInfo.systemUptime
    if !stopping, let kind = watch.tick(now: now, state: state, heartbeat: heartbeat) {
        LiteDiagnostics.enqueue(LiteDiagnostics.report(kind: kind, stage: watch.stage, elapsed: now - started))
    }
    flushSoon()
}
child.terminationHandler = { process in
    events.async {
        timer.cancel()
        let status = process.terminationStatus
        let outcome = process.terminationReason == .uncaughtSignal
            ? LauncherExit(code: 0, signal: status) : LauncherExit(code: status)
        if LiteDiagnostics.sessionAllowsReporting(directory), outcome.isUnexpected(userRequested: stopping),
           !LiteDiagnostics.vmExitWasHandled(outcome, in: directory) {
            let stage = LiteDiagnostics.readState(in: directory)?.stage ?? watch.stage
            LiteDiagnostics.enqueue(LiteDiagnostics.report(kind: "launcher-crashed", stage: stage,
                elapsed: ProcessInfo.processInfo.systemUptime - started, outcome: outcome))
        }
        try? FileManager.default.removeItem(at: directory)
        Task {
            await LiteDiagnostics.flush()
            exit(outcome.status)
        }
    }
}
// posix_spawn itself can wait in macOS policy evaluation. Arm the independent
// queue before Process.run(), not after the runtime's spawn has returned.
timer.resume()
events.async { flushSoon() }
startupLog.notice("runtime-spawning")
do {
    try child.run()
    startupLog.notice("runtime-spawned")
}
catch {
    startupLog.notice("runtime-spawn-failed")
    if LiteDiagnostics.sessionAllowsReporting(directory) {
        LiteDiagnostics.enqueue(LiteDiagnostics.report(kind: "launcher-crashed", stage: "launcher"))
    }
    try? FileManager.default.removeItem(at: directory)
    Task { await LiteDiagnostics.flush(); exit(127) }
}
dispatchMain()
