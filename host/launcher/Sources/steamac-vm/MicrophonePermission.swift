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
    @Published private(set) var state: State
    @Published private(set) var requesting = false
    private let readStatus: () -> State
    private let request: (@escaping (Bool) -> Void) -> Void
    private var pending: [() -> Void] = []
    private var observer: NSObjectProtocol?

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

    func refresh() { state = readStatus() }

    /// Only a user action requests OS permission. Already decided states never re-prompt.
    func requestAccess(completion: @escaping () -> Void = {}) {
        refresh()
        if requesting { pending.append(completion); return }
        guard state == .notDetermined else { completion(); return }
        pending.append(completion)
        requesting = true
        request { [weak self] _ in
            let finish = {
                self?.refresh()
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

    static func needsNotice(state: State, enabled: Bool, boot: Int, version: String, lastNotice: String?) -> Bool {
        enabled && boot == 1 && state != .authorized && lastNotice != version
    }

    /// Before the first VM boot, so a permission alert cannot make the guest's capture
    /// request time out. A dismissed notice is not repeated for every VM restart.
    func prepareForBoot(on window: NSWindow, enabled: Bool, boot: Int, defaults: UserDefaults,
                        version: String, completion: @escaping () -> Void) {
        refresh()
        log("microphone: macOS authorization \(state.rawValue)")
        guard Self.needsNotice(state: state, enabled: enabled, boot: boot, version: version,
                               lastNotice: defaults.string(forKey: Self.noticeKey)) else { completion(); return }
        defaults.set(version, forKey: Self.noticeKey)
        let alert = NSAlert()
        alert.messageText = String(localized: "Microphone access")
        if state == .notDetermined {
            alert.informativeText = String(localized: "Allow microphone access for voice chat in SteamOS games? macOS will ask you to confirm. After an app update, permission may be needed again.")
            alert.addButton(withTitle: String(localized: "Allow Microphone…"))
        } else {
            alert.informativeText = state.description + "\n\n" + (state == .denied
                ? String(localized: "If the microphone stopped working after an update, turn this app's microphone switch off and on again in System Settings. You can also check access in Settings → Sound.")
                : String(localized: "You can use SteamOS without a microphone. To allow it later, open Settings → Sound."))
            alert.addButton(withTitle: String(localized: "Open Microphone Settings…"))
        }
        alert.addButton(withTitle: String(localized: "Continue Without Microphone"))
        alert.beginSheetModal(for: window) { [self] response in
            guard response == .alertFirstButtonReturn else { completion(); return }
            if state == .notDetermined {
                requestAccess {
                    if self.state == .denied || self.state == .restricted {
                        let denied = NSAlert()
                        denied.messageText = String(localized: "Microphone access")
                        denied.informativeText = self.state.description + "\n\n" + String(localized: "You can use SteamOS without a microphone. To allow it later, open Settings → Sound.")
                        denied.addButton(withTitle: String(localized: "Continue"))
                        denied.beginSheetModal(for: window) { _ in completion() }
                    } else { completion() }
                }
            } else {
                if state != .authorized { openSettings() }
                completion()
            }
        }
    }

    /// Exercises real state transitions with an injected OS, without opening a microphone
    /// or reading/changing the user's TCC decisions.
    static func selfCheck() -> [String] {
        var failures: [String] = []
        for state in State.allCases {
            let expected = state != .authorized
            if needsNotice(state: state, enabled: true, boot: 1, version: "new", lastNotice: "old") != expected {
                failures.append("update notice: \(state)")
            }
            for (enabled, boot, last) in [(false, 1, "old"), (true, 2, "old"), (true, 1, "new")] {
                if needsNotice(state: state, enabled: enabled, boot: boot, version: "new", lastNotice: last) {
                    failures.append("unexpected notice: \(state)")
                }
            }
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
        return failures
    }
}
