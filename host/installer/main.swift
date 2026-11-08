import AppKit
import Combine
import SwiftUI

final class InstallerModel: NSObject, ObservableObject, URLSessionDownloadDelegate {
    enum Phase {
        case checking, ready, downloading, verifying, installing
        case done(String, already: Bool), failed(InstallerText)
    }
    @Published var language = InstallerLanguage.preferred
    @Published var phase: Phase = .checking
    @Published var fraction = 0.0
    @Published var target = InstallerCore.defaultDestination()
    private(set) var release: InstallerCore.Release?
    private var task: URLSessionTask?
    private let lock = NSLock()
    private var cancelledValue = false
    private var quitPending = false
    private var cancelled: Bool {
        get { lock.lock(); defer { lock.unlock() }; return cancelledValue }
        set { lock.lock(); cancelledValue = newValue; lock.unlock() }
    }
    private lazy var session: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.urlCache = nil
        config.httpCookieStorage = nil
        config.httpShouldSetCookies = false
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 3600
        return URLSession(configuration: config, delegate: self, delegateQueue: nil)
    }()

    override init() {
        super.init()
        #if INSTALLER_TESTING
        if let value = ProcessInfo.processInfo.environment["STEAMAC_INSTALLER_TEST_DESTINATION"] {
            target = URL(fileURLWithPath: value).standardizedFileURL
        }
        #endif
    }
    var busy: Bool {
        switch phase { case .checking, .downloading, .verifying, .installing: return true; default: return false }
    }
    func t(_ key: InstallerText, _ value: String? = nil) -> String {
        if let value { return key.text(language, value) }
        return key.text(language)
    }
    private func update(_ action: @escaping () -> Void) { DispatchQueue.main.async(execute: action) }
    private func idle(_ phase: Phase) {
        self.phase = phase
        task = nil
        if quitPending { NSApp.reply(toApplicationShouldTerminate: true) }
    }
    private func isRunning() -> Bool {
        NSRunningApplication.runningApplications(withBundleIdentifier: UpdateInstallSupport.bundleID)
            .contains { $0.bundleURL?.standardizedFileURL == self.target.standardizedFileURL }
    }
    private func request(_ url: URL) -> URLRequest {
        var request = URLRequest(url: url)
        request.setValue("SteamAC-Lite-Installer/" + InstallerCore.installerVersion, forHTTPHeaderField: "User-Agent")
        request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        return request
    }
    func check() {
        cancelled = false
        phase = .checking
        var feed = InstallerCore.feedURL
        #if INSTALLER_TESTING
        if let value = ProcessInfo.processInfo.environment["STEAMAC_INSTALLER_TEST_FEED"], let url = URL(string: value) { feed = url }
        #endif
        task = session.dataTask(with: request(feed)) { [weak self] data, response, error in
            guard let self else { return }
            do {
                if self.cancelled { throw InstallerCore.Failure.cancelled }
                guard error == nil, let data, (response as? HTTPURLResponse)?.statusCode == 200 else { throw InstallerCore.Failure.network }
                let release = try InstallerCore.latest(data)
                let installed = try InstallerCore.alreadyCurrent(self.target, release: release)
                self.update {
                    self.release = release
                    if self.cancelled { self.idle(.failed(.cancelled)) }
                    else if let installed { self.idle(.done(installed, already: true)) }
                    else { self.idle(.ready) }
                }
            } catch { self.update { self.idle(.failed(self.message(error))) } }
        }
        task?.resume()
    }
    func chooseFolder() {
        guard !busy else { return }
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.canCreateDirectories = true
        panel.allowsMultipleSelection = false
        panel.message = t(.destination)
        if panel.runModal() == .OK, let directory = panel.url {
            target = directory.appendingPathComponent("SteamAC Lite.app", isDirectory: true).standardizedFileURL
            check()
        }
    }
    func install() {
        guard !busy, let release else { return }
        if isRunning() { idle(.failed(.runningError)); return }
        do {
            if let installed = try InstallerCore.alreadyCurrent(target, release: release) { idle(.done(installed, already: true)); return }
            let parent = target.deletingLastPathComponent()
            try FileManager.default.createDirectory(at: parent, withIntermediateDirectories: true)
            guard parent.resolvingSymlinksInPath() == parent.standardizedFileURL,
                  FileManager.default.isWritableFile(atPath: parent.path) else { throw InstallerCore.Failure.destination }
        } catch { idle(.failed(.destinationError)); return }
        cancelled = false
        fraction = 0
        phase = .downloading
        task = session.downloadTask(with: request(release.url))
        task?.resume()
    }
    func cancel() {
        if case .installing = phase { return }
        cancelled = true
        task?.cancel()
    }
    func shouldQuit() -> NSApplication.TerminateReply {
        if !busy { return .terminateNow }
        quitPending = true
        cancel()
        return .terminateLater
    }
    private func message(_ error: Error) -> InstallerText {
        if cancelled { return .cancelled }
        switch error {
        case InstallerCore.Failure.network: return .networkError
        case InstallerCore.Failure.release: return .releaseError
        case InstallerCore.Failure.destination: return .destinationError
        case InstallerCore.Failure.running: return .runningError
        case InstallerCore.Failure.cancelled: return .cancelled
        case UpdateInstallSupport.Failure.checksum, UpdateInstallSupport.Failure.size,
             UpdateInstallSupport.Failure.identity, UpdateInstallSupport.Failure.response: return .verificationError
        default: return .installError
        }
    }
    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didWriteData bytesWritten: Int64,
                    totalBytesWritten: Int64, totalBytesExpectedToWrite: Int64) {
        guard let release else { return }
        update { if case .downloading = self.phase { self.fraction = min(1, Double(totalBytesWritten) / Double(release.size)) } }
    }
    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didFinishDownloadingTo location: URL) {
        guard let release else { return }
        var stage: URL?
        let result: Phase
        do {
            if cancelled { throw InstallerCore.Failure.cancelled }
            guard let response = downloadTask.response as? HTTPURLResponse, response.statusCode == 200,
                  response.url?.scheme == "https" else { throw InstallerCore.Failure.network }
            update { self.phase = .verifying }
            try UpdateInstallSupport.verifyArchive(location, digest: release.sha256, size: release.size)
            stage = try UpdateInstallSupport.prepare(location, version: release.version, size: release.size, destination: target)
            if cancelled { throw InstallerCore.Failure.cancelled }
            let proceed = DispatchQueue.main.sync { () -> Bool in
                guard !self.cancelled else { return false }
                self.phase = .installing
                return true
            }
            if !proceed { throw InstallerCore.Failure.cancelled }
            let installed = try InstallerCore.install(staged: stage!, to: target, release: release, isRunning: self.isRunning)
            result = .done(installed, already: false)
        } catch { result = .failed(message(error)) }
        if let stage {
            let directory = stage.deletingLastPathComponent()
            // A failed rollback keeps the previous app available for recovery.
            if !FileManager.default.fileExists(atPath: directory.appendingPathComponent("previous.app").path) {
                try? FileManager.default.removeItem(at: directory)
            }
        }
        update { self.idle(result) }
    }
    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        guard task is URLSessionDownloadTask, error != nil else { return }
        update { self.idle(.failed(self.cancelled ? .cancelled : .networkError)) }
    }
    func openApp() {
        #if INSTALLER_TESTING
        try? Data("open suppressed in installer tests".utf8).write(to: target.deletingLastPathComponent().appendingPathComponent("open-suppressed.txt"))
        #else
        NSWorkspace.shared.openApplication(at: target, configuration: NSWorkspace.OpenConfiguration()) { _, _ in }
        #endif
    }
}

struct InstallerView: View {
    @ObservedObject var model: InstallerModel
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .top, spacing: 16) {
                Image(nsImage: NSApp.applicationIconImage).resizable().frame(width: 64, height: 64)
                VStack(alignment: .leading, spacing: 6) {
                    Text(model.t(.title)).font(.title2.weight(.semibold))
                    Text(model.t(.introduction)).font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                }
            }
            HStack {
                Picker("Language / 言語", selection: $model.language) {
                    ForEach(InstallerLanguage.allCases, id: \.self) { Text($0.title).tag($0) }
                }.frame(width: 255).disabled(model.busy)
                Spacer()
            }
            Divider()
            switch model.phase {
            case .checking: progress(.checking)
            case .ready:
                Text(model.t(.available, model.release?.version ?? "")).font(.headline)
            case .downloading:
                Text(model.t(.downloading)).font(.headline)
                ProgressView(value: model.fraction)
            case .verifying: progress(.verifying)
            case .installing: progress(.installing)
            case .done(let version, let already):
                Text(model.t(already ? .current : .completed, version)).font(.headline)
            case .failed(let message):
                Text(model.t(message)).fixedSize(horizontal: false, vertical: true)
            }
            VStack(alignment: .leading, spacing: 6) {
                Text(model.t(.destination)).font(.caption).foregroundStyle(.secondary)
                HStack {
                    Text(verbatim: (model.target.path as NSString).abbreviatingWithTildeInPath).font(.callout).textSelection(.enabled).lineLimit(2)
                    Spacer()
                    Button(model.t(.choose)) { model.chooseFolder() }.disabled(model.busy)
                }
            }
            HStack {
                if case .failed = model.phase {
                    Button(model.t(.manual)) { NSWorkspace.shared.open(InstallerCore.releasesURL) }
                }
                Spacer()
                switch model.phase {
                case .ready:
                    Button(model.t(.close)) { NSApp.terminate(nil) }.keyboardShortcut(.cancelAction)
                    Button(model.t(.install)) { model.install() }.keyboardShortcut(.defaultAction)
                case .done:
                    Button(model.t(.open)) { model.openApp() }
                    Button(model.t(.close)) { NSApp.terminate(nil) }.keyboardShortcut(.defaultAction)
                case .failed:
                    Button(model.t(.close)) { NSApp.terminate(nil) }.keyboardShortcut(.cancelAction)
                    Button(model.t(.retry)) { model.check() }.keyboardShortcut(.defaultAction)
                case .installing:
                    EmptyView()
                default:
                    Button(model.t(.cancel)) { model.cancel() }.keyboardShortcut(.cancelAction)
                }
            }
        }
        .padding(24).frame(width: 570, alignment: .leading)
    }
    private func progress(_ text: InstallerText) -> some View {
        VStack(alignment: .leading, spacing: 10) { Text(model.t(text)).font(.headline); ProgressView().progressViewStyle(.linear) }
    }
}

final class InstallerDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    let model = InstallerModel()
    var window: NSWindow!
    var view: NSHostingView<InstallerView>!
    var observation: AnyCancellable?
    func applicationDidFinishLaunching(_ notification: Notification) {
        let menu = NSMenu()
        let application = NSMenuItem(); menu.addItem(application)
        let submenu = NSMenu()
        submenu.addItem(withTitle: InstallerText.close.text(model.language), action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        application.submenu = submenu
        NSApp.mainMenu = menu
        view = NSHostingView(rootView: InstallerView(model: model))
        let size = view.fittingSize
        window = NSWindow(contentRect: NSRect(origin: .zero, size: size), styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        window.title = "steamac Lite Installer"
        window.contentView = view
        window.isReleasedWhenClosed = false
        window.delegate = self
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        observation = model.objectWillChange.sink { [weak self] in
            DispatchQueue.main.async {
                guard let self else { return }
                self.window.title = self.model.t(.title)
                NSApp.mainMenu?.items.first?.submenu?.items.first?.title = self.model.t(.close)
                self.view.layoutSubtreeIfNeeded()
                let top = self.window.frame.maxY
                self.window.setContentSize(self.view.fittingSize)
                var frame = self.window.frame
                frame.origin.y = top - frame.height
                self.window.setFrame(frame, display: true)
            }
        }
        model.check()
    }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply { model.shouldQuit() }
    func windowShouldClose(_ sender: NSWindow) -> Bool { NSApp.terminate(nil); return false }
}

let application = NSApplication.shared
let delegate = InstallerDelegate()
application.setActivationPolicy(.regular)
application.delegate = delegate
application.run()
