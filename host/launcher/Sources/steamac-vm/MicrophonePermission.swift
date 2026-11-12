import AppKit
import AVFoundation
import Combine

/// TCC identifies ad-hoc builds by their code hash, which changes on update. Never infer
/// access from a saved preference (or the switch displayed by System Settings).
final class MicrophonePermission: ObservableObject {
    enum State: String, CaseIterable {
        case notDetermined, authorized, denied, restricted

        var description: String {
            switch self {
            case .notDetermined: return String(localized: "Microphone access has not been requested.")
            case .authorized: return String(localized: "Microphone access is allowed.")
            case .denied: return String(localized: "Microphone access is not allowed. Check Microphone in System Settings.")
            case .restricted: return String(localized: "Microphone access is restricted by this Mac's settings or administrator.")
            }
        }
    }

    static let shared = MicrophonePermission()
    private static let noticeKey = "microphoneNoticeVersion"
    private static let authorizedKey = "microphoneWasAuthorized"
    private static let selectedKey = "microphonePermissionSelected"
    @Published private(set) var state: State
    @Published private(set) var requesting = false
    private let readStatus: () -> State
    private let request: (@escaping (Bool) -> Void) -> Void
    private var pending: [() -> Void] = []
    private var observer: NSObjectProtocol?
    private var historyDefaults: UserDefaults?

    init(readStatus: @escaping () -> State = MicrophonePermission.systemStatus,
         request: @escaping (@escaping (Bool) -> Void) -> Void = { AVCaptureDevice.requestAccess(for: .audio, completionHandler: $0) },
         observeChanges: Bool = true) {
        self.readStatus = readStatus
        self.request = request
        state = readStatus()
        if observeChanges {
            observer = NotificationCenter.default.addObserver(forName: NSApplication.didBecomeActiveNotification,
                                                               object: nil, queue: .main) { [weak self] _ in
                self?.refresh()
            }
        }
    }

    deinit { if let observer { NotificationCenter.default.removeObserver(observer) } }

    static func systemStatus() -> State {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .notDetermined: return .notDetermined
        case .authorized: return .authorized
        case .denied: return .denied
        case .restricted: return .restricted
        @unknown default: return .restricted
        }
    }

    /// Register only after startup has compared the saved grant baseline.
    func trackAuthorization(in defaults: UserDefaults) { historyDefaults = defaults }

    func refresh() {
        state = readStatus()
        if state == .authorized { historyDefaults?.set(true, forKey: Self.authorizedKey) }
    }

    /// Only a user action requests OS permission. Already decided states never re-prompt.
    func requestAccess(completion: @escaping () -> Void = {}) {
        refresh()
        if state == .authorized { historyDefaults?.set(true, forKey: Self.selectedKey) }
        if requesting { pending.append(completion); return }
        guard state == .notDetermined else { completion(); return }
        pending.append(completion)
        requesting = true
        request { [weak self] _ in
            let finish = {
                self?.refresh()
                if self?.state == .authorized { self?.historyDefaults?.set(true, forKey: Self.selectedKey) }
                self?.requesting = false
                let completions = self?.pending ?? []
                self?.pending.removeAll()
                completions.forEach { $0() }
            }
            if Thread.isMainThread { finish() } else { DispatchQueue.main.async(execute: finish) }
        }
    }

    func openSettings() {
        // This opens the pane; only the user can change the permission.
        guard let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone") else { return }
        NSWorkspace.shared.open(url)
    }

    static func needsNotice(boot: Int, version: String, lastNotice: String?,
                            wasAuthorized: Bool?, selected: Bool, state: State) -> Bool {
        guard boot == 1, lastNotice != version, selected else { return false }
        // An already authorized installation needs only a baseline, even without history.
        guard state != .authorized else { return false }
        if lastNotice == nil { return true }
        return wasAuthorized == true
    }

    /// Quiet checks still advance the version and snapshot actual OS access. Missing
    /// selection history defaults to enabled; missing grant history never implies a grant.
    private func reviewForBoot(boot: Int, defaults: UserDefaults, version: String) -> Bool {
        guard boot == 1 else { return false }
        // Read without tracking: the saved baseline belongs to the previous check.
        state = readStatus()
        let selected = defaults.object(forKey: Self.selectedKey) == nil || defaults.bool(forKey: Self.selectedKey)
        let show = Self.needsNotice(boot: boot, version: version,
            lastNotice: defaults.string(forKey: Self.noticeKey),
            wasAuthorized: defaults.object(forKey: Self.authorizedKey) as? Bool,
            selected: selected, state: state)
        if !show { recordReview(defaults: defaults, version: version, selected: selected) }
        return show
    }

    private func recordReview(defaults: UserDefaults, version: String, selected: Bool) {
        refresh()
        defaults.set(version, forKey: Self.noticeKey)
        defaults.set(state == .authorized, forKey: Self.authorizedKey)
        defaults.set(selected, forKey: Self.selectedKey)
    }

    /// Before the first VM boot, so a permission alert cannot make the guest's capture
    /// request time out. A dismissed notice is not repeated for every VM restart.
    func prepareForBoot(on window: NSWindow, boot: Int, defaults: UserDefaults,
                        version: String, completion: @escaping () -> Void) {
        state = readStatus()
        log("microphone: macOS authorization \(state.rawValue)")
        let show = reviewForBoot(boot: boot, defaults: defaults, version: version)
        trackAuthorization(in: defaults)
        guard show else { completion(); return }
        let finish = { (selected: Bool) in
            self.recordReview(defaults: defaults, version: version, selected: selected)
            completion()
        }
        let displayedState = state
        let alert = NSAlert()
        alert.messageText = String(localized: "Microphone access")
        if state == .authorized {
            alert.informativeText = state.description + "\n\n" + String(localized: "Microphone access is checked after every app update. You can review it in Settings → Sound.")
            alert.addButton(withTitle: String(localized: "Continue"))
            alert.addButton(withTitle: String(localized: "Open Microphone Settings…"))
        } else if state == .notDetermined {
            alert.informativeText = String(localized: "Allow microphone access for voice chat in SteamOS games? macOS will ask you to confirm. After an app update, permission may be needed again.")
            alert.addButton(withTitle: String(localized: "Allow Microphone…"))
        } else {
            alert.informativeText = state.description + "\n\n" + (state == .denied
                ? String(localized: "If the microphone stopped working after an update, turn this app's microphone switch off and on again in System Settings. You can also check access in Settings → Sound.")
                : String(localized: "You can use SteamOS without a microphone. To allow it later, open Settings → Sound."))
            alert.addButton(withTitle: String(localized: "Open Microphone Settings…"))
        }
        if state != .authorized { alert.addButton(withTitle: String(localized: "Later")) }
        alert.beginSheetModal(for: window) { [self] response in
            if displayedState == .authorized {
                if response == .alertSecondButtonReturn { openSettings() }
                finish(response == .alertFirstButtonReturn || response == .alertSecondButtonReturn)
                return
            }
            guard response == .alertFirstButtonReturn else { finish(false); return }
            if displayedState == .notDetermined {
                requestAccess {
                    if self.state == .denied || self.state == .restricted {
                        let denied = NSAlert()
                        denied.messageText = String(localized: "Microphone access")
                        denied.informativeText = self.state.description + "\n\n" + String(localized: "You can use SteamOS without a microphone. To allow it later, open Settings → Sound.")
                        denied.addButton(withTitle: String(localized: "Continue"))
                        denied.beginSheetModal(for: window) { _ in finish(true) }
                    } else { finish(true) }
                }
            } else {
                if state != .authorized { openSettings() }
                finish(true)
            }
        }
    }

    /// Show the production startup notice without booting a VM or remembering its dismissal.
    static func preview() -> Never {
        let app = NSApplication.shared
        app.setActivationPolicy(.regular)
        MainMenu.installMinimal()
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 600, height: 180),
                              styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "steamac Lite"
        window.isReleasedWhenClosed = false
        let domain = "steamac.microphone-preview." + UUID().uuidString
        let defaults = UserDefaults(suiteName: domain)!
        DispatchQueue.main.async {
            window.center(); window.makeKeyAndOrderFront(nil); app.activate()
            shared.prepareForBoot(on: window, boot: 1, defaults: defaults, version: "preview") {
                defaults.removePersistentDomain(forName: domain)
                exit(0)
            }
        }
        withExtendedLifetime(window) { app.run() }
        exit(0)
    }

    /// Exercises real state transitions with an injected OS, without opening a microphone
    /// or reading/changing the user's TCC decisions.
    static func selfCheck() -> [String] {
        var failures: [String] = []
        let domain = "steamac.microphone-history-test." + UUID().uuidString
        let defaults = UserDefaults(suiteName: domain)!
        defer { defaults.removePersistentDomain(forName: domain) }
        func checkReview(_ name: String, state: State, boot: Int = 1, lastVersion: String? = "old",
                         wasAuthorized: Bool? = true, selected: Bool? = true, expected: Bool) {
            defaults.removePersistentDomain(forName: domain)
            if let lastVersion { defaults.set(lastVersion, forKey: noticeKey) }
            if let wasAuthorized { defaults.set(wasAuthorized, forKey: authorizedKey) }
            if let selected { defaults.set(selected, forKey: selectedKey) }
            let before = defaults.persistentDomain(forName: domain) ?? [:]
            let permission = MicrophonePermission(readStatus: { state }, request: { _ in
                failures.append("\(name): unexpected OS request")
            }, observeChanges: false)
            if permission.reviewForBoot(boot: boot, defaults: defaults, version: "new") != expected {
                failures.append("\(name): notice decision")
            }
            if boot != 1 || expected {
                if !NSDictionary(dictionary: before).isEqual(NSDictionary(dictionary: defaults.persistentDomain(forName: domain) ?? [:])) {
                    failures.append("\(name): history changed before review")
                }
            } else if defaults.string(forKey: noticeKey) != "new"
                || (defaults.object(forKey: authorizedKey) as? Bool) != (state == .authorized)
                || (defaults.object(forKey: selectedKey) as? Bool) != (selected ?? true) {
                failures.append("\(name): quiet baseline not saved")
            }
        }
        for state in State.allCases {
            checkReview("first startup: \(state)", state: state, lastVersion: nil,
                        wasAuthorized: nil, selected: nil, expected: state != .authorized)
            checkReview("update retained/lost: \(state)", state: state, expected: state != .authorized)
            checkReview("previous denial: \(state)", state: state, wasAuthorized: false, expected: false)
            checkReview("opt-out: \(state)", state: state, selected: false, expected: false)
            checkReview("legacy without grant history: \(state)", state: state,
                        wasAuthorized: nil, selected: nil, expected: false)
            checkReview("same version: \(state)", state: state, lastVersion: "new", expected: false)
            checkReview("VM restart: \(state)", state: state, boot: 2, expected: false)
            checkReview("VM restart without history: \(state)", state: state, boot: 2,
                        lastVersion: nil, wasAuthorized: nil, selected: nil, expected: false)
            var osState = state
            var requests = 0
            var callback: ((Bool) -> Void)?
            let permission = MicrophonePermission(readStatus: { osState }, request: { requests += 1; callback = $0 }, observeChanges: false)
            var completed = 0
            permission.requestAccess { completed += 1 }
            if state == .notDetermined {
                if requests != 1 || !permission.requesting || completed != 0 { failures.append("pending request") }
                permission.requestAccess()
                if requests != 1 { failures.append("duplicate OS request") }
                osState = .authorized
                callback?(true)
                if permission.state != .authorized || permission.requesting || completed != 1 { failures.append("grant result") }
                permission.requestAccess()
                if requests != 1 { failures.append("prompt after grant") }
            } else if requests != 0 || completed != 1 { failures.append("request after decision: \(state)") }
            osState = .denied
            permission.refresh()
            if permission.state != .denied { failures.append("permission revoked while away") }
        }
        var denied: State = .notDetermined
        let permission = MicrophonePermission(readStatus: { denied }, request: { done in denied = .denied; done(false) }, observeChanges: false)
        permission.requestAccess()
        if permission.state != .denied || permission.requesting { failures.append("denial result") }

        // Later remains an opt-out even if access happens to be authorized; an OS denial
        // after choosing Allow records intent but cannot become a prior-grant baseline.
        for selected in [false, true] {
            var osState: State = .authorized
            let permission = MicrophonePermission(readStatus: { osState }, request: { _ in
                failures.append("history must not request OS access")
            }, observeChanges: false)
            permission.recordReview(defaults: defaults, version: "first", selected: selected)
            osState = .notDetermined
            if permission.reviewForBoot(boot: 1, defaults: defaults, version: "second") != selected {
                failures.append("Later/Allow selection on update")
            }
            permission.recordReview(defaults: defaults, version: "second", selected: selected)
            if permission.reviewForBoot(boot: 1, defaults: defaults, version: "third") {
                failures.append("repeated notice after loss or opt-out")
            }
        }
        permission.recordReview(defaults: defaults, version: "denied", selected: true)
        if defaults.bool(forKey: authorizedKey)
            || permission.reviewForBoot(boot: 1, defaults: defaults, version: "after-denial") {
            failures.append("denial inferred as a previous grant")
        }

        defaults.removePersistentDomain(forName: domain)
        defaults.set(false, forKey: authorizedKey)
        defaults.set(false, forKey: selectedKey)
        var manualState: State = .authorized
        var manualRequests = 0
        let manual = MicrophonePermission(readStatus: { manualState }, request: { done in
            manualRequests += 1; manualState = .authorized; done(true)
        }, observeChanges: false)
        manual.trackAuthorization(in: defaults)
        if defaults.bool(forKey: authorizedKey) { failures.append("tracking changed the prior baseline") }
        manual.refresh()
        if !defaults.bool(forKey: authorizedKey) || defaults.bool(forKey: selectedKey) {
            failures.append("refresh did not track only the grant")
        }
        manualState = .denied
        manual.refresh()
        if !defaults.bool(forKey: authorizedKey) { failures.append("revocation erased the prior grant") }
        manualState = .notDetermined
        manual.requestAccess()
        if manualRequests != 1 || !defaults.bool(forKey: authorizedKey) || !defaults.bool(forKey: selectedKey) {
            failures.append("manual Sound permission did not record grant and selection")
        }
        defaults.set("manual-grant", forKey: noticeKey)
        manualState = .restricted
        if !manual.reviewForBoot(boot: 1, defaults: defaults, version: "after-manual-grant") {
            failures.append("manual grant loss not detected on update")
        }
        return failures
    }
}
