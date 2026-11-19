import Foundation
import Darwin

/// Keep wait status and shell status distinct: exit(137) and SIGKILL both return 137 to the caller.
struct LauncherExit {
    static let forceQuitStatus: Int32 = 3
    static let startupRejectedStatus: Int32 = 4
    static let terminationSignals: Set<Int32> = [SIGTERM, SIGINT, SIGHUP]

    let code: Int32
    let signal: Int32
    var status: Int32 { signal == 0 ? code : 128 + signal }

    init(code: Int32, signal: Int32 = 0) {
        self.code = code
        self.signal = signal
    }

    init(waitStatus: Int32) {
        // WEXITSTATUS and WTERMSIG are C macros, unavailable in Swift.
        self.init(code: (waitStatus >> 8) & 0xff, signal: waitStatus & 0x7f)
    }

    func isUnexpected(userRequested: Bool, killedForMemory: Bool = false) -> Bool {
        if signal != 0 {
            if Self.terminationSignals.contains(signal) || signal == SIGPIPE { return false }
            return signal != SIGKILL || !userRequested || killedForMemory
        }
        return code != 0 && code != Self.forceQuitStatus && code != Self.startupRejectedStatus && !userRequested
    }
}

/// Shared by the tiny bootstrap and the runtime. Automatic reports are an
/// allowlisted JSON record, never a log, environment dump, screenshot or disk.
enum LiteDiagnostics {
    static let consentVersion = 1
    static let consentKey = "liteDiagnosticsConsentVersion"
    static let enabledKey = "sendCrashReports"
    static let domain = ProcessInfo.processInfo.environment["STEAMAC_DEFAULTS_DOMAIN"]
        ?? (Bundle.main.object(forInfoDictionaryKey: "SteamacPreferencesDomain") as? String ?? "local.ryuu.steamac-lite")
    static var defaults: UserDefaults {
        domain == Bundle.main.bundleIdentifier ? .standard : (UserDefaults(suiteName: domain) ?? .standard)
    }
    static var isLite: Bool { Bundle.main.object(forInfoDictionaryKey: "SteamacLiteBuild") as? Bool == true }
    static var allowed: Bool {
        let d = defaults
        d.synchronize()
        return d.integer(forKey: consentKey) == consentVersion && d.bool(forKey: enabledKey)
            && ProcessInfo.processInfo.environment["STEAMAC_SENTRY"] != "0"
            && !CommandLine.arguments.contains("--no-crash-reports")
    }
    static func consent(_ enabled: Bool) {
        let d = defaults
        d.set(consentVersion, forKey: consentKey); d.set(enabled, forKey: enabledKey); d.synchronize()
        if !enabled {
            clearQueue()
            for directory in (try? FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)) ?? []
                where directory.lastPathComponent.hasPrefix("session-") {
                try? Data().write(to: directory.appendingPathComponent("revoked"), options: .atomic)
            }
        }
    }
    static var endpoint: URL? {
        guard let s = Bundle.main.object(forInfoDictionaryKey: "SteamacDiagnosticsURL") as? String,
              let u = URL(string: s), u.scheme == "https", u.user == nil, u.password == nil,
              u.query == nil, u.fragment == nil, u.path == "/reports", u.port == nil else { return nil }
        return u
    }
    static var root: URL {
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/" + domain + "/diagnostics", isDirectory: true)
    }
    static func privateDirectory(_ url: URL) throws {
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let a = try FileManager.default.attributesOfItem(atPath: url.path)
        guard a[.type] as? FileAttributeType == .typeDirectory,
              (a[.ownerAccountID] as? NSNumber)?.uint32Value == getuid(),
              url.standardizedFileURL == url.resolvingSymlinksInPath().standardizedFileURL else { throw CocoaError(.fileWriteNoPermission) }
    }
    struct State: Codable {
        var stage: String; var uptime: Double; var waiting: Bool; var pid: Int32
    }
    static let stages: Set<String> = ["launcher", "main", "install", "language", "settings", "options", "metal-cache",
        "crash-reporting", "supervisor", "first-run", "vm-setup", "window", "permission", "vm-start",
        "vm", "provision", "kernel", "init", "system", "systemd", "graphical", "session", "steam", "steam-check",
        "steam-download", "steam-install", "steam-start", "ready", "shutdown"]
    static var session: URL? {
        ProcessInfo.processInfo.environment["STEAMAC_DIAGNOSTIC_SESSION"].map { URL(fileURLWithPath: $0, isDirectory: true) }
    }
    static func sessionAllowsReporting(_ directory: URL) -> Bool {
        allowed && !FileManager.default.fileExists(atPath: directory.appendingPathComponent("revoked").path)
    }
    static func readState(in directory: URL) -> State? {
        (try? Data(contentsOf: directory.appendingPathComponent("state.json")))
            .flatMap { try? JSONDecoder().decode(State.self, from: $0) }
    }
    // The supervisor classified the VM exit and will return this status to its caller.
    // Only an ordinary exit with the matching status can use this handoff.
    static func markVMExitHandled(status: Int32) {
        guard isLite, let session else { return }
        try? String(status).write(to: session.appendingPathComponent("vm-exit-status"), atomically: true, encoding: .utf8)
    }
    static func vmExitWasHandled(_ outcome: LauncherExit, in directory: URL) -> Bool {
        guard outcome.signal == 0,
              let value = try? String(contentsOf: directory.appendingPathComponent("vm-exit-status"), encoding: .utf8)
        else { return false }
        return Int32(value) == outcome.code
    }
    static func checkpoint(_ stage: String, waiting: Bool = false) {
        guard isLite, let session, stages.contains(stage), sessionAllowsReporting(session) else { return }
        let state = State(stage: stage, uptime: ProcessInfo.processInfo.systemUptime, waiting: waiting, pid: getpid())
        try? JSONEncoder().encode(state).write(to: session.appendingPathComponent("state.json"), options: .atomic)
    }
    nonisolated(unsafe) private static var heartbeat: DispatchSourceTimer?
    static func startHeartbeat() {
        guard isLite, session != nil, allowed, heartbeat == nil else { return }
        let timer = DispatchSource.makeTimerSource(queue: .main)
        timer.schedule(deadline: .now(), repeating: 5, leeway: .seconds(1))
        timer.setEventHandler {
            guard allowed, let session else { return }
            try? String(ProcessInfo.processInfo.systemUptime).write(to: session.appendingPathComponent("heartbeat"), atomically: true, encoding: .utf8)
        }
        timer.resume(); heartbeat = timer
    }
    struct Feedback: Codable { var message: String; var email: String; var launcher_log: String }
    enum KillReason: String, Codable {
        case memory, decryption, unspecified, unavailable
        case codeSigning = "code-signing"

        init(exitDetail: UInt32?) {
            guard let detail = exitDetail else { self = .unavailable; return }
            if detail & UInt32(NOTE_EXIT_MEMORY) != 0 { self = .memory }
            else if detail & UInt32(NOTE_EXIT_CSERROR) != 0 { self = .codeSigning }
            else if detail & UInt32(NOTE_EXIT_DECRYPTFAIL) != 0 { self = .decryption }
            else { self = .unspecified }
        }
    }
    struct Report: Codable {
        var schema = 1; var id = UUID().uuidString.lowercased(); var kind: String
        var version: String; var commit: String; var macos: String; var model: String; var chip: String
        var ram_gb: Int; var stage: String; var elapsed_s: Int
        var exit_code: Int?; var signal: Int?; var feedback: Feedback?
        var kill_reason: KillReason?
    }
    static func matches(_ text: String, _ pattern: String) -> Bool { text.range(of: pattern, options: .regularExpression) != nil }
    static func sysctlString(_ key: String) -> String {
        var size = 0
        guard sysctlbyname(key, nil, &size, nil, 0) == 0, size > 0, size < 4096 else { return "unknown" }
        var chars = [CChar](repeating: 0, count: size)
        guard sysctlbyname(key, &chars, &size, nil, 0) == 0 else { return "unknown" }
        return String(cString: chars)
    }
    static func report(kind: String, stage: String = "launcher", elapsed: Double = 0,
                       outcome: LauncherExit? = nil, killReason: KillReason? = nil) -> Report {
        let p = Bundle.main.infoDictionary ?? [:], v = ProcessInfo.processInfo.operatingSystemVersion
        let model = sysctlString("hw.model"), chip = sysctlString("machdep.cpu.brand_string")
        let version = p["CFBundleShortVersionString"] as? String ?? ""
        let commit = p["SteamacGitCommit"] as? String ?? ""
        return Report(kind: kind,
            version: matches(version, #"^\d+\.\d+\.\d+-lite\.\d+$"#) ? version : "0.0.0-lite.0",
            commit: matches(commit, "^[a-f0-9]{7,40}$") ? commit : "0000000",
            macos: "\(v.majorVersion).\(v.minorVersion).\(v.patchVersion)",
            model: matches(model, #"^Mac(?:Book(?:Air|Pro)?|mini|Pro|Studio)?\d+,\d+$"#) ? model : "unknown",
            chip: matches(chip, #"^Apple M\d+(?: (?:Pro|Max|Ultra))?$"#) ? chip : "unknown",
            ram_gb: max(1, Int(ProcessInfo.processInfo.physicalMemory >> 30)),
            stage: stages.contains(stage) ? stage : "launcher", elapsed_s: min(604800, max(0, Int(elapsed))),
            exit_code: outcome.flatMap { $0.signal == 0 ? Int($0.code) : nil },
            signal: outcome.flatMap { $0.signal != 0 ? Int($0.signal) : nil },
            kill_reason: killReason)
    }
    static var queue: URL { root.appendingPathComponent("pending", isDirectory: true) }
    static func clearQueue() { try? FileManager.default.removeItem(at: queue) }
    static func pending() -> [URL] {
        ((try? FileManager.default.contentsOfDirectory(at: queue, includingPropertiesForKeys: [.creationDateKey])) ?? [])
            .filter { $0.pathExtension == "json" }.sorted { $0.lastPathComponent < $1.lastPathComponent }
    }
    static func enqueue(_ report: Report) {
        guard allowed else { return }
        do {
            try privateDirectory(root); try privateDirectory(queue)
            // A cross-process lock bounds disk use and report volume, including crash loops.
            let lock = open(root.appendingPathComponent("queue.lock").path, O_CREAT | O_RDWR | O_NOFOLLOW | O_CLOEXEC, 0o600)
            guard lock >= 0 else { return }; defer { close(lock) }
            guard flock(lock, LOCK_EX | LOCK_NB) == 0 else { return }; defer { flock(lock, LOCK_UN) }
            guard allowed, pending().count < 10 else { return }
            let day = Int(Date().timeIntervalSince1970 / 86400)
            let budgetFile = root.appendingPathComponent("budget.json")
            let old = (try? Data(contentsOf: budgetFile)).flatMap { try? JSONDecoder().decode([Int].self, from: $0) } ?? []
            let count = old.count == 2 && old[0] == day ? old[1] : 0
            guard count < 4 else { return }
            try JSONEncoder().encode(report).write(to: queue.appendingPathComponent(report.id + ".json"), options: .atomic)
            try JSONEncoder().encode([day, count + 1]).write(to: budgetFile, options: .atomic)
        } catch { /* Diagnostics never prevent the application starting. */ }
    }
    final class NoRedirect: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
        func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                        newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }
    }
    static func send(_ report: Report, automatic: Bool) async throws {
        guard !automatic || allowed else { throw CocoaError(.userCancelled) }
        guard let endpoint else { throw CocoaError(.fileNoSuchFile) }
        let config = URLSessionConfiguration.ephemeral
        config.httpCookieStorage = nil; config.urlCredentialStorage = nil; config.urlCache = nil
        config.timeoutIntervalForRequest = 12; config.timeoutIntervalForResource = 15
        let session = URLSession(configuration: config, delegate: NoRedirect(), delegateQueue: nil)
        defer { session.invalidateAndCancel() }
        var request = URLRequest(url: endpoint); request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("steamac-Lite-Diagnostics/1", forHTTPHeaderField: "User-Agent")
        request.httpBody = try JSONEncoder().encode(report)
        // Re-check immediately before handing off to URLSession; future queued sends stop on opt-out.
        guard !automatic || allowed else { throw CocoaError(.userCancelled) }
        let (data, response) = try await session.data(for: request)
        guard (response as? HTTPURLResponse)?.statusCode == 202,
              let receipt = try? JSONSerialization.jsonObject(with: data) as? [String: String],
              receipt["id"] == report.id, receipt["status"] == "accepted" else { throw URLError(.badServerResponse) }
    }
    static func flush() async {
        guard allowed else { clearQueue(); return }
        for path in pending().prefix(4) {
            guard allowed else { clearQueue(); return }
            do {
                let values = try path.resourceValues(forKeys: [.creationDateKey])
                if let created = values.creationDate, Date().timeIntervalSince(created) > 7 * 86400 {
                    try? FileManager.default.removeItem(at: path); continue
                }
                let report = try JSONDecoder().decode(Report.self, from: Data(contentsOf: path))
                try await send(report, automatic: true)
                try? FileManager.default.removeItem(at: path)
            } catch { return }
        }
    }
    struct Watch {
        var stage = "launcher"; var since: Double; var previousTick: Double
        var lastStateUptime: Double?
        var alreadyReported = false
        init(now: Double) { since = now; previousTick = now }
        mutating func tick(now: Double, state: State?, heartbeat: Double?) -> String? {
            // Sleep, host scheduling gaps, user dialogs and new boot stages get a fresh grace period.
            if now - previousTick > 20 { since = now }
            previousTick = now
            if let state {
                if state.stage != stage || lastStateUptime != state.uptime { stage = state.stage; since = now }
                lastStateUptime = state.uptime
                if state.waiting || state.stage == "shutdown" { since = now; return nil }
            }
            if alreadyReported { return nil }
            let stalled: Bool
            if stage == "ready" { stalled = heartbeat.map { now - $0 >= 180 && now - since >= 180 } ?? (now - since >= 180) }
            else { stalled = now - since >= 180 }
            guard stalled else { return nil }
            alreadyReported = true
            return stage == "ready" ? "app-unresponsive" : "startup-stalled"
        }
    }
}
