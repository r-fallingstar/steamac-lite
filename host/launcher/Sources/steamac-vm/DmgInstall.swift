import AppKit
import Foundation

/// Runs before first-launch preferences or VM setup. Uses the online installer's verified,
/// same-volume replacement transaction; no download, administrator prompt, or disk reset.
@MainActor
enum DmgInstall {
    nonisolated static func needsInstallation(_ app: URL, readOnly: Bool) -> Bool {
        readOnly || app.path.contains("/AppTranslocation/")
    }

    static func runIfNeeded(_ argv: [String]) {
        let review = argv.contains("--selftest-dmg-install")
        guard !Supervisor.isChild, AppBundle.resources != nil,
              review || !argv.dropFirst().contains(where: {
                  $0.hasPrefix("--selftest") || ["--preview-update", "--headless", "--ssh-password",
                  "--create-disk", "--grow-disk", "--help", "-h"].contains($0)
              }) else { return }
        let source = Bundle.main.bundleURL.standardizedFileURL
        let readOnly = (try? source.resourceValues(forKeys: [.volumeIsReadOnlyKey]))?.volumeIsReadOnly == true
        guard review || needsInstallation(source, readOnly: readOnly) else { return }

        let target: URL
        if review {
            target = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true).resolvingSymlinksInPath()
                .appendingPathComponent("steamac-dmg-install-review-" + UUID().uuidString, isDirectory: true)
                .appendingPathComponent("Applications/SteamAC Lite.app", isDirectory: true)
            print("dmg-install-review-target: " + target.path)
            fflush(stdout)
        } else { target = InstallerCore.defaultDestination() }
        let app = NSApplication.shared
        app.setActivationPolicy(.regular)
        // Retain only our own Quit menu, so the DMG instance cannot start a VM from a menu.
        let menu = NSMenu()
        let item = NSMenuItem()
        let applicationMenu = NSMenu()
        applicationMenu.autoenablesItems = false
        applicationMenu.addItem(withTitle: String(localized: "Quit"), action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        item.submenu = applicationMenu
        menu.addItem(item)
        app.mainMenu = menu
        DispatchQueue.main.async { present(source: source, target: target, review: review) }
        app.run()
        exit(0)
    }

    private static func present(source: URL, target: URL, review: Bool) {
        NSApp.activate()
        let alert = NSAlert()
        alert.messageText = String(localized: "Install steamac Lite on this Mac")
        alert.informativeText = String(localized: "Choose Install and Open to copy the app to Applications and open it. Your SteamOS disk and settings are kept.")
            + "\n\n" + target.deletingLastPathComponent().path
        alert.addButton(withTitle: String(localized: "Install and Open"))
        alert.addButton(withTitle: String(localized: "Quit"))
        guard alert.runModal() == .alertFirstButtonReturn else { NSApp.terminate(nil); return }

        let progress = NSAlert()
        progress.messageText = String(localized: "Installing steamac Lite…")
        progress.informativeText = String(localized: "The installed app will open when the copy is complete.")
        let spinner = NSProgressIndicator(frame: NSRect(x: 0, y: 0, width: 280, height: 16))
        spinner.style = .bar
        spinner.isIndeterminate = true
        spinner.startAnimation(nil)
        progress.accessoryView = spinner
        let button = progress.addButton(withTitle: String(localized: "Quit"))
        button.isEnabled = false
        NSApp.mainMenu?.items.first?.submenu?.items.first?.isEnabled = false
        progress.window.standardWindowButton(.closeButton)?.isEnabled = false
        progress.window.makeKeyAndOrderFront(nil)
        // Copying and signature verification never block the UI thread.
        DispatchQueue.global(qos: .userInitiated).async {
            do {
                let installed = try prepare(source: source, target: target)
                DispatchQueue.main.async {
                    progress.window.orderOut(nil)
                    open(installed, review: review)
                }
            } catch {
                DispatchQueue.main.async {
                    progress.window.orderOut(nil)
                    NSApp.mainMenu?.items.first?.submenu?.items.first?.isEnabled = true
                    showFailure(error, source: source, target: target, review: review)
                }
            }
        }
    }

    /// A shared core also used by command-line fixture tests. Cleanup removes only this run's
    /// private stage. If rollback failed, keep the recovery files beside the destination.
    nonisolated static func prepare(source: URL, target: URL, isRunning: (() -> Bool)? = nil) throws -> URL {
        let fm = FileManager.default
        let info = try UpdateInstallSupport.appInfo(source)
        guard let version = info["CFBundleShortVersionString"] as? String,
              let numbers = InstallerCore.version(version) else { throw InstallerCore.Failure.destination }
        try UpdateInstallSupport.validateApp(source, version: version)
        let release = InstallerCore.Release(version: version, numbers: numbers, url: source, sha256: "", size: 0)
        let parent = target.deletingLastPathComponent()
        try fm.createDirectory(at: parent, withIntermediateDirectories: true)
        guard parent.standardizedFileURL == parent.resolvingSymlinksInPath(),
              fm.isWritableFile(atPath: parent.path) else { throw InstallerCore.Failure.destination }
        // A matching or newer installed version opens directly; it is never downgraded.
        if try InstallerCore.alreadyCurrent(target, release: release) != nil { return target }
        let running = isRunning ?? {
            NSRunningApplication.runningApplications(withBundleIdentifier: UpdateInstallSupport.bundleID)
                .contains { $0.processIdentifier != getpid() && $0.bundleURL?.standardizedFileURL == target.standardizedFileURL }
        }
        guard !running() else { throw InstallerCore.Failure.running }
        let directory = parent.appendingPathComponent(".steamac-update-" + UUID().uuidString, isDirectory: true)
        try fm.createDirectory(at: directory, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        try JSONEncoder().encode(UpdateInstallSupport.StageOwner(destination: target.standardizedFileURL.path, processID: getpid()))
            .write(to: directory.appendingPathComponent("owner.json"), options: .atomic)
        defer {
            // previous.app remains only when a rollback failed; never discard the old app then.
            if !fm.fileExists(atPath: directory.appendingPathComponent("previous.app").path) {
                try? fm.removeItem(at: directory)
            }
        }
        let available = try directory.resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey])
            .volumeAvailableCapacityForImportantUsage ?? 0
        guard available >= 512 * 1024 * 1024 else { throw UpdateInstallSupport.Failure.space }
        let staged = directory.appendingPathComponent("SteamAC Lite.app", isDirectory: true)
        _ = try UpdateInstallSupport.run("/usr/bin/ditto", [source.path, staged.path])
        _ = try InstallerCore.install(staged: staged, to: target, release: release, isRunning: running)
        return target
    }

    private static func open(_ target: URL, review: Bool) {
        if let running = NSRunningApplication.runningApplications(withBundleIdentifier: UpdateInstallSupport.bundleID)
            .first(where: { $0.processIdentifier != getpid() && $0.bundleURL?.standardizedFileURL == target.standardizedFileURL }) {
            running.activate()
            NSApp.terminate(nil)
            return
        }
        let configuration = NSWorkspace.OpenConfiguration()
        configuration.createsNewApplicationInstance = true
        configuration.activates = true
        if review {
            configuration.arguments = ["--selftest-settings", "-AppleLanguages", "(" + (Locale.preferredLanguages.first ?? "en") + ")"]
            configuration.environment = ["STEAMAC_SENTRY": "0", "STEAMAC_SETTINGS_REVIEW": "1",
                "STEAMAC_DEFAULTS_DOMAIN": "steamac.dmg-install-review." + UUID().uuidString]
        }
        NSWorkspace.shared.openApplication(at: target, configuration: configuration) { _, error in
            DispatchQueue.main.async {
                if error != nil {
                    let alert = NSAlert()
                    alert.messageText = String(localized: "Installed. Open steamac Lite from Applications.")
                    alert.informativeText = String(localized: "The app was copied successfully. Open it from Finder to continue.")
                    alert.addButton(withTitle: String(localized: "Show in Finder"))
                    alert.addButton(withTitle: String(localized: "Quit"))
                    if alert.runModal() == .alertFirstButtonReturn {
                        NSWorkspace.shared.activateFileViewerSelecting([target])
                    }
                }
                NSApp.terminate(nil)
            }
        }
    }

    private static func showFailure(_ error: Error, source: URL, target: URL, review: Bool) {
        let alert = NSAlert()
        alert.messageText = String(localized: "steamac Lite could not be installed")
        if case InstallerCore.Failure.running = error {
            alert.informativeText = String(localized: "Quit the copy of steamac Lite already running from Applications, then try again.")
        } else if case UpdateInstallSupport.Failure.space = error {
            alert.informativeText = String(localized: "At least 512 MB of free space is needed to install the app.")
        } else {
            alert.informativeText = String(localized: "Check the free space and write permission for Applications. You can also drag the app into Applications in Finder.")
        }
        alert.addButton(withTitle: String(localized: "Try Again"))
        alert.addButton(withTitle: String(localized: "Show in Finder"))
        alert.addButton(withTitle: String(localized: "Quit"))
        switch alert.runModal() {
        case .alertFirstButtonReturn: present(source: source, target: target, review: review)
        case .alertSecondButtonReturn:
            NSWorkspace.shared.activateFileViewerSelecting([source])
            NSApp.terminate(nil)
        default: NSApp.terminate(nil)
        }
    }
}
