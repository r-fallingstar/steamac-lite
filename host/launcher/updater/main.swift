import AppKit
import Darwin
import Foundation

// This executable is copied outside the running bundle before launch. It has no VM, networking,
// administrator privileges or access to the user's SteamOS image in its installation plan.
let fm = FileManager.default
var plan: UpdateInstallPlan?
var directory: URL?
var backup: URL?
var movedPrevious = false
var destination: URL?
do {
    guard CommandLine.arguments.count == 2 else { throw UpdateInstallSupport.Failure.identity }
    let planURL = URL(fileURLWithPath: CommandLine.arguments[1]).standardizedFileURL
    let decoded = try JSONDecoder().decode(UpdateInstallPlan.self, from: Data(contentsOf: planURL))
    plan = decoded
    let target = URL(fileURLWithPath: decoded.destination).standardizedFileURL
    let staged = URL(fileURLWithPath: decoded.stagedApp).standardizedFileURL
    let work = planURL.deletingLastPathComponent()
    guard work.lastPathComponent.hasPrefix(".steamac-update-"),
          work.deletingLastPathComponent() == target.deletingLastPathComponent(),
          staged.deletingLastPathComponent() == work, staged.lastPathComponent == "SteamAC Lite.app",
          work.resolvingSymlinksInPath() == work, !decoded.processIDs.isEmpty,
          decoded.processIDs.allSatisfy({ $0 > 1 && $0 != getpid() }) else { throw UpdateInstallSupport.Failure.identity }
    directory = work
    destination = target
    try JSONEncoder().encode(UpdateInstallSupport.StageOwner(destination: target.path, processID: getpid()))
        .write(to: work.appendingPathComponent("owner.json"), options: .atomic)
    let lockURL = target.deletingLastPathComponent().appendingPathComponent(".steamac-update.lock")
    let lock = open(lockURL.path, O_CREAT | O_RDWR | O_NOFOLLOW, 0o600)
    guard lock >= 0 else { throw UpdateInstallSupport.Failure.destination }
    defer { close(lock) }
    guard flock(lock, LOCK_EX | LOCK_NB) == 0 else { throw UpdateInstallSupport.Failure.destination }
    try UpdateInstallSupport.validateDestination(target)
    try UpdateInstallSupport.validateApp(target, version: decoded.previousVersion)
    try UpdateInstallSupport.validateApp(staged, version: decoded.version)
    // A cancelled Quit, another open copy, or a slow shutdown never becomes a forced shutdown.
    #if UPDATE_INSTALL_TESTING
    let deadline = Date().addingTimeInterval(1)
    #else
    let deadline = Date().addingTimeInterval(10 * 60)
    #endif
    while true {
        let alive = decoded.processIDs.contains { kill($0, 0) == 0 || errno == EPERM }
        let running = NSRunningApplication.runningApplications(withBundleIdentifier: UpdateInstallSupport.bundleID)
            .contains { $0.bundleURL?.standardizedFileURL == target }
        if !alive && !running { break }
        guard Date() < deadline else { throw UpdateInstallSupport.Failure.destination }
        Thread.sleep(forTimeInterval: 0.25)
    }
    try UpdateInstallSupport.validateDestination(target)
    try UpdateInstallSupport.validateApp(target, version: decoded.previousVersion)
    try UpdateInstallSupport.validateApp(staged, version: decoded.version)
    let old = target.deletingLastPathComponent().appendingPathComponent(".steamac-previous-" + UUID().uuidString + ".app")
    backup = old
    try fm.moveItem(at: target, to: old)
    movedPrevious = true
    try fm.moveItem(at: staged, to: target)
    try UpdateInstallSupport.validateApp(target, version: decoded.version)
    // LaunchServices acknowledges launching the new app before we remove the previous copy.
    #if UPDATE_INSTALL_TESTING
    if ProcessInfo.processInfo.environment["UPDATE_TEST_LAUNCH_FAIL"] == "1" { throw UpdateInstallSupport.Failure.command }
    #else
    var launchResult: Result<Void, Error>?
    NSWorkspace.shared.openApplication(at: target, configuration: NSWorkspace.OpenConfiguration()) { application, error in
        DispatchQueue.main.async {
            if let error { launchResult = .failure(error) }
            else if application != nil { launchResult = .success(()) }
            else { launchResult = .failure(UpdateInstallSupport.Failure.command) }
        }
    }
    let launchDeadline = Date().addingTimeInterval(30)
    while launchResult == nil && Date() < launchDeadline {
        RunLoop.current.run(until: Date().addingTimeInterval(0.1))
    }
    guard let launchResult else { throw UpdateInstallSupport.Failure.command }
    try launchResult.get()
    #endif
    try? fm.removeItem(at: old)
    try? fm.removeItem(at: work)
    exit(0)
} catch {
    // Never remove the previous copy unless replacement and relaunch both succeeded.
    if movedPrevious, let target = destination, let old = backup, fm.fileExists(atPath: old.path) {
        if fm.fileExists(atPath: target.path) {
            // Only remove the exact staged app we installed, never a concurrent replacement.
            if let p = plan, (try? UpdateInstallSupport.validateApp(target, version: p.version)) != nil {
                try? fm.moveItem(at: target, to: directory!.appendingPathComponent("failed.app"))
            }
        }
        if !fm.fileExists(atPath: target.path) { try? fm.moveItem(at: old, to: target) }
    }
    // Fail closed. Cleanup owns only the private staging directory, never the VM or preferences.
    if let directory { try? fm.removeItem(at: directory) }
    #if !UPDATE_INSTALL_TESTING
    if let plan {
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        let alert = NSAlert()
        alert.messageText = plan.failureTitle
        alert.informativeText = plan.failureMessage
        alert.addButton(withTitle: plan.releasesLabel)
        alert.addButton(withTitle: plan.closeLabel)
        app.activate()
        if alert.runModal() == .alertFirstButtonReturn {
            NSWorkspace.shared.open(URL(string: "https://github.com/r-fallingstar/steamac-lite/releases")!)
        }
    }
    #endif
    exit(1)
}
