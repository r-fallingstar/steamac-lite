import AppKit
import Foundation

/// Downloads into a private temporary directory, verifies GitHub's SHA-256 and the app signature,
/// then stages a complete replacement beside the installed app. The helper waits for both the VM
/// and its supervisor to exit before replacing anything, and rolls back a failed replacement.
final class LiteUpdater {
    private var task: URLSessionDownloadTask?
    private var observation: NSKeyValueObservation?
    private var session: URLSession?
    private let lock = NSLock()
    private var cancelledValue = false
    private var receivingValue = false
    private var cancelled: Bool {
        get { lock.lock(); defer { lock.unlock() }; return cancelledValue }
        set { lock.lock(); cancelledValue = newValue; lock.unlock() }
    }
    private var receiving: Bool {
        get { lock.lock(); defer { lock.unlock() }; return receivingValue }
        set { lock.lock(); receivingValue = newValue; lock.unlock() }
    }
    private var installing = false
    private var stage: URL?
    var changed: (UpdatePanel.State) -> Void = { _ in }

    func cancel() {
        guard !installing else { return }
        cancelled = true
        task?.cancel()
        if let stage {
            self.stage = nil
            DispatchQueue.global(qos: .utility).async { try? FileManager.default.removeItem(at: stage.deletingLastPathComponent()) }
        }
    }

    func download(_ release: UpdateChecker.Release) {
        guard task == nil, !installing else { return }
        cancelled = false
        let destination = Bundle.main.bundleURL.standardizedFileURL
        do {
            try UpdateInstallSupport.validateDestination(destination)
            UpdateInstallSupport.cleanAbandonedStages(beside: destination)
        }
        catch { changed(.failedUpdate(String(localized: "Move SteamAC Lite to a writable Applications folder, then try updating again."))); return }
        guard let url = release.dmg, let digest = release.sha256, release.size > 0 else {
            changed(.failedUpdate(String(localized: "This release has no verified app download. Open the releases page to update manually.")))
            return
        }
        if let stage { try? FileManager.default.removeItem(at: stage.deletingLastPathComponent()); self.stage = nil }
        receiving = true
        changed(.downloading(0))
        let configuration = URLSessionConfiguration.ephemeral
        configuration.httpShouldSetCookies = false
        configuration.httpCookieStorage = nil
        configuration.urlCache = nil
        configuration.timeoutIntervalForRequest = 60
        configuration.timeoutIntervalForResource = 3600
        let session = URLSession(configuration: configuration)
        self.session = session
        var request = URLRequest(url: url)
        request.setValue("SteamAC-Lite/\(UpdateChecker.currentVersion)", forHTTPHeaderField: "User-Agent")
        let task = session.downloadTask(with: request) { [weak self] temporary, response, error in
            guard let self else { return }
            defer {
                self.receiving = false
                self.session?.finishTasksAndInvalidate()
                self.session = nil
                DispatchQueue.main.async { self.observation = nil; self.task = nil }
            }
            do {
                if self.cancelled { throw CancellationError() }
                if let error { throw error }
                guard let temporary, let http = response as? HTTPURLResponse, http.statusCode == 200,
                      http.url?.scheme == "https" else { throw UpdateInstallSupport.Failure.response }
                self.receiving = false
                DispatchQueue.main.async { self.changed(.preparing) }
                try UpdateInstallSupport.verifyArchive(temporary, digest: digest, size: release.size)
                let staged = try UpdateInstallSupport.prepare(temporary, version: release.versionString, size: release.size, destination: destination)
                if self.cancelled { try? FileManager.default.removeItem(at: staged.deletingLastPathComponent()); throw CancellationError() }
                DispatchQueue.main.async {
                    if self.cancelled { try? FileManager.default.removeItem(at: staged.deletingLastPathComponent()); return }
                    self.stage = staged
                    self.changed(.ready(release))
                }
            } catch {
                DispatchQueue.main.async {
                    if self.cancelled { self.changed(.available(release, current: UpdateChecker.currentVersion)) }
                    else {
                        log("update: preparation failed: \(error)")
                        self.changed(.failedUpdate(String(localized: "The update could not be downloaded or verified. Your app has not been changed. Try again or open the releases page.")))
                    }
                }
            }
        }
        self.task = task
        observation = task.progress.observe(\.fractionCompleted, options: [.new]) { [weak self] progress, _ in
            DispatchQueue.main.async {
                guard let self, !self.cancelled, self.receiving else { return }
                self.changed(.downloading(max(0, min(1, progress.fractionCompleted))))
            }
        }
        task.resume()
    }

    func install(_ release: UpdateChecker.Release) {
        guard !installing, let stage else { return }
        do {
            try UpdateInstallSupport.validateDestination(Bundle.main.bundleURL)
            try UpdateInstallSupport.validateApp(stage, version: release.versionString)
            guard let resources = Bundle.main.resourceURL else { throw UpdateInstallSupport.Failure.identity }
            let helper = stage.deletingLastPathComponent().appendingPathComponent("steamac-updater")
            try FileManager.default.copyItem(at: resources.appendingPathComponent("steamac-updater"), to: helper)
            let plan = UpdateInstallPlan(destination: Bundle.main.bundleURL.standardizedFileURL.path, stagedApp: stage.path,
                previousVersion: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "",
                version: release.versionString, processIDs: Supervisor.isChild ? [getpid(), getppid()] : [getpid()],
                failureTitle: String(localized: "SteamAC Lite could not be updated"),
                failureMessage: String(localized: "The update could not finish. Your SteamOS disk and settings have not been changed. Open the releases page to update manually."),
                releasesLabel: String(localized: "Open Releases Page"), closeLabel: String(localized: "Close"))
            let planURL = stage.deletingLastPathComponent().appendingPathComponent("install.json")
            try JSONEncoder().encode(plan).write(to: planURL, options: .atomic)
            let process = Process()
            process.executableURL = helper
            process.arguments = [planURL.path]
            process.standardOutput = FileHandle.nullDevice
            process.standardError = FileHandle.nullDevice
            try process.run()
            installing = true
            changed(.installing)
            // Uses the normal graceful shutdown path, including the suspended-VM confirmation.
            // If the user cancels quitting, the helper times out without changing the app.
            NSApp.terminate(nil)
        } catch {
            log("update: install could not start: \(error)")
            changed(.failedUpdate(String(localized: "The update could not start. Your app has not been changed. Open the releases page to update manually.")))
        }
    }

    deinit {
        task?.cancel()
        if !installing, let stage { try? FileManager.default.removeItem(at: stage.deletingLastPathComponent()) }
    }
}
