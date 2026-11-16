import AppKit
import AVFoundation
import Darwin
import Foundation

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
// Preserve Finder-launch error dialogs when the real runtime's parent is now
// this bootstrap rather than launchd. Command-line utilities keep terminal errors.
if getppid() == 1 { setenv("STEAMAC_GUI_LAUNCH", "1", 1) }

if LiteDiagnostics.defaults.integer(forKey: LiteDiagnostics.consentKey) != LiteDiagnostics.consentVersion
    || LiteDiagnostics.defaults.integer(forKey: FirstRunWizard.versionKey) != 1 {
    let app = NSApplication.shared
    app.setActivationPolicy(.regular)
    let wizard = FirstRunWizard(arguments: arguments)
    DispatchQueue.main.async { wizard.show() }
    withExtendedLifetime(wizard) { app.run() }
    exit(0)
}

guard LiteDiagnostics.allowed else { LiteDiagnostics.clearQueue(); execRuntime() }

// An OS reboot or killing the whole process group may also kill the monitor.
// On the next opt-in launch, report only a demonstrably abandoned session, and
// label the cause unknown rather than calling a force-quit a native crash.
for old in (try? FileManager.default.contentsOfDirectory(at: LiteDiagnostics.root, includingPropertiesForKeys: nil)) ?? []
    where old.lastPathComponent.hasPrefix("session-") {
    guard let ownerText = try? String(contentsOf: old.appendingPathComponent("owner"), encoding: .utf8),
          let owner = Int32(ownerText), owner > 1, kill(owner, 0) == -1, errno == ESRCH,
          let data = try? Data(contentsOf: old.appendingPathComponent("state.json")),
          let state = try? JSONDecoder().decode(LiteDiagnostics.State.self, from: data),
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
    guard !FileManager.default.fileExists(atPath: directory.appendingPathComponent("revoked").path) else { return }
    guard LiteDiagnostics.allowed else { LiteDiagnostics.clearQueue(); return }
    let state = (try? Data(contentsOf: directory.appendingPathComponent("state.json")))
        .flatMap { try? JSONDecoder().decode(LiteDiagnostics.State.self, from: $0) }
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
        if !stopping && LiteDiagnostics.allowed && (process.terminationReason == .uncaughtSignal || status != 0) {
            // SIGKILL can mean force-quit or memory pressure. Report the signal,
            // not a fabricated native crash reason. Normal requested quits are skipped.
            var report = LiteDiagnostics.report(kind: process.terminationReason == .uncaughtSignal ? "launcher-crashed" : "vm-exited-unexpectedly",
                                                stage: watch.stage, elapsed: ProcessInfo.processInfo.systemUptime - started)
            if process.terminationReason == .uncaughtSignal { report.signal = Int(status) }
            else { report.exit_code = Int(status) }
            LiteDiagnostics.enqueue(report)
        }
        try? FileManager.default.removeItem(at: directory)
        Task {
            await LiteDiagnostics.flush()
            exit(process.terminationReason == .exit ? status : 128 + status)
        }
    }
}
// posix_spawn itself can wait in macOS policy evaluation. Arm the independent
// queue before Process.run(), not after the runtime's spawn has returned.
timer.resume()
events.async { flushSoon() }
do { try child.run() }
catch {
    LiteDiagnostics.enqueue(LiteDiagnostics.report(kind: "launcher-crashed", stage: "launcher"))
    try? FileManager.default.removeItem(at: directory)
    Task { await LiteDiagnostics.flush(); exit(127) }
}
dispatchMain()
