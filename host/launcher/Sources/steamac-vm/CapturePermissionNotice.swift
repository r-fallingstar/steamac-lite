import AppKit
import AVFoundation

/// Startup consent for the camera experiment. Permission requests never create a capture session.
final class CapturePermissionNotice: NSObject {
    static let noticeKey = "capturePermissionsNoticeVersion"
    static let cameraKey = "cameraAutomaticCapture"

    struct Selection {
        var microphone: Bool
        var camera: Bool

        init(microphoneStatus: AVAuthorizationStatus, cameraAutomaticCapture: Bool) {
            microphone = microphoneStatus == .authorized || microphoneStatus == .notDetermined
            camera = cameraAutomaticCapture
        }
    }

    static func needsNotice(boot: Int, version: String, lastNotice: String?) -> Bool {
        boot == 1 && lastNotice != version
    }

    /// Injected requests keep the self-check independent of TCC and capture devices.
    static func resolve(_ selection: Selection,
                        status: @escaping (AVMediaType) -> AVAuthorizationStatus = { AVCaptureDevice.authorizationStatus(for: $0) },
                        request: @escaping (AVMediaType, @escaping (Bool) -> Void) -> Void = { AVCaptureDevice.requestAccess(for: $0, completionHandler: $1) },
                        completion: @escaping (Bool) -> Void) {
        func next(_ media: [AVMediaType]) {
            guard let first = media.first else {
                completion(selection.camera && status(.video) == .authorized)
                return
            }
            let remaining = Array(media.dropFirst())
            guard status(first) == .notDetermined else { next(remaining); return }
            request(first) { _ in
                if Thread.isMainThread { next(remaining) }
                else { DispatchQueue.main.async { next(remaining) } }
            }
        }
        next((selection.microphone ? [.audio] : []) + (selection.camera ? [.video] : []))
    }

    private let microphone = NSButton(checkboxWithTitle: String(localized: "Allow microphone access for voice chat"), target: nil, action: nil)
    private let camera = NSButton(checkboxWithTitle: String(localized: "Use camera only when a game requests it"), target: nil, action: nil)
    private let microphoneStatus = NSTextField(wrappingLabelWithString: "")
    private let cameraStatus = NSTextField(wrappingLabelWithString: "")
    private let microphoneSettings = NSButton(title: String(localized: "Open Microphone Settings…"), target: nil, action: nil)
    private let cameraSettings = NSButton(title: String(localized: "Open Camera privacy settings…"), target: nil, action: nil)
    private var observer: NSObjectProtocol?

    private init(selection: Selection) {
        super.init()
        microphone.state = selection.microphone ? .on : .off
        camera.state = selection.camera ? .on : .off
        microphoneSettings.target = self
        microphoneSettings.action = #selector(openMicrophoneSettings)
        cameraSettings.target = self
        cameraSettings.action = #selector(openCameraSettings)
        refresh()
    }

    @objc private func openMicrophoneSettings() { MicrophonePermission.shared.openSettings() }
    @objc private func openCameraSettings() {
        guard let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera") else { return }
        NSWorkspace.shared.open(url)
    }

    private static func blocked(_ status: AVAuthorizationStatus) -> Bool {
        status != .authorized && status != .notDetermined
    }

    private static func cameraDescription() -> String {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized: return String(localized: "Camera access is allowed.")
        case .notDetermined: return String(localized: "Camera access has not been requested.")
        case .denied: return String(localized: "Camera access is not allowed. Check macOS Camera settings.")
        default: return String(localized: "Camera access is restricted by this Mac's settings or administrator.")
        }
    }

    private func refresh() {
        MicrophonePermission.shared.refresh()
        microphoneStatus.stringValue = MicrophonePermission.shared.state.description
        cameraStatus.stringValue = Self.cameraDescription()
        let microphoneBlocked = Self.blocked(AVCaptureDevice.authorizationStatus(for: .audio))
        let cameraBlocked = Self.blocked(AVCaptureDevice.authorizationStatus(for: .video))
        microphone.isEnabled = !microphoneBlocked
        camera.isEnabled = !cameraBlocked
        microphoneSettings.isHidden = !microphoneBlocked
        cameraSettings.isHidden = !cameraBlocked
    }

    static func prepareForBoot(on window: NSWindow, boot: Int, defaults: UserDefaults,
                               version: String, completion: @escaping () -> Void) {
        guard needsNotice(boot: boot, version: version, lastNotice: defaults.string(forKey: noticeKey)) else {
            completion()
            return
        }
        let notice = CapturePermissionNotice(selection: Selection(
            microphoneStatus: AVCaptureDevice.authorizationStatus(for: .audio),
            cameraAutomaticCapture: defaults.bool(forKey: cameraKey)))
        let alert = NSAlert()
        alert.messageText = String(localized: "Microphone and camera access")
        alert.informativeText = String(localized: "Choose which access to allow. macOS will ask for confirmation if needed. Camera permission alone does not start capture.")
        alert.addButton(withTitle: String(localized: "Continue"))
        let stack = NSStackView(views: [notice.microphone, notice.microphoneStatus, notice.microphoneSettings,
                                        notice.camera, notice.cameraStatus, notice.cameraSettings])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 8
        stack.setCustomSpacing(20, after: notice.microphoneSettings)
        for label in [notice.microphoneStatus, notice.cameraStatus] {
            label.font = .systemFont(ofSize: NSFont.smallSystemFontSize)
            label.textColor = .secondaryLabelColor
            label.widthAnchor.constraint(equalToConstant: 440).isActive = true
        }
        stack.widthAnchor.constraint(equalToConstant: 440).isActive = true
        stack.layoutSubtreeIfNeeded()
        stack.setFrameSize(stack.fittingSize)
        alert.accessoryView = stack
        notice.observer = NotificationCenter.default.addObserver(forName: NSApplication.didBecomeActiveNotification,
            object: nil, queue: .main) { [weak notice] _ in notice?.refresh() }
        alert.beginSheetModal(for: window) { [notice] response in
            if let observer = notice.observer { NotificationCenter.default.removeObserver(observer) }
            notice.observer = nil
            guard response == .alertFirstButtonReturn else { completion(); return }
            var selection = Selection(microphoneStatus: .notDetermined, cameraAutomaticCapture: false)
            selection.microphone = notice.microphone.state == .on
            selection.camera = notice.camera.state == .on
            resolve(selection) { automaticCamera in
                defaults.set(automaticCamera, forKey: cameraKey)
                defaults.set(version, forKey: noticeKey)
                notice.refresh()
                // A decided denial cannot trigger another system prompt. Offer the real settings pane.
                let microphoneBlocked = selection.microphone && blocked(AVCaptureDevice.authorizationStatus(for: .audio))
                let cameraBlocked = selection.camera && blocked(AVCaptureDevice.authorizationStatus(for: .video))
                guard microphoneBlocked || cameraBlocked else { completion(); return }
                let denied = NSAlert()
                denied.messageText = String(localized: "Microphone and camera access")
                denied.informativeText = [microphoneBlocked ? notice.microphoneStatus.stringValue : nil,
                                          cameraBlocked ? notice.cameraStatus.stringValue : nil].compactMap { $0 }.joined(separator: "\n\n")
                denied.addButton(withTitle: String(localized: "Continue"))
                if microphoneBlocked { denied.addButton(withTitle: String(localized: "Open Microphone Settings…")) }
                if cameraBlocked { denied.addButton(withTitle: String(localized: "Open Camera privacy settings…")) }
                denied.beginSheetModal(for: window) { response in
                    if response == .alertSecondButtonReturn {
                        if microphoneBlocked { notice.openMicrophoneSettings() } else { notice.openCameraSettings() }
                    } else if response == .alertThirdButtonReturn { notice.openCameraSettings() }
                    completion()
                }
            }
        }
    }

    /// No windows, capture sessions, OS requests, or production preferences.
    static func selfCheck() -> [String] {
        var failures: [String] = []
        if !needsNotice(boot: 1, version: "new", lastNotice: "old")
            || !needsNotice(boot: 1, version: "new", lastNotice: nil)
            || needsNotice(boot: 2, version: "new", lastNotice: "old")
            || needsNotice(boot: 1, version: "new", lastNotice: "new") { failures.append("capture notice version") }
        let states: [AVAuthorizationStatus] = [.notDetermined, .authorized, .denied, .restricted]
        for microphoneState in states {
            for cameraState in states {
                for saved in [false, true] {
                    let selection = Selection(microphoneStatus: microphoneState, cameraAutomaticCapture: saved)
                    if selection.microphone != (microphoneState == .authorized || microphoneState == .notDetermined)
                        || selection.camera != saved { failures.append("capture defaults") }
                    var audio = microphoneState, video = cameraState
                    var requested: [AVMediaType] = []
                    var callbacks: [(Bool) -> Void] = []
                    var result: Bool?
                    resolve(selection, status: { $0 == .audio ? audio : video }, request: { media, done in
                        requested.append(media); callbacks.append(done)
                    }, completion: { result = $0 })
                    if microphoneState == .notDetermined {
                        if requested != [.audio] || result != nil { failures.append("audio must resolve first") }
                        audio = .authorized
                        callbacks.removeFirst()(true)
                    }
                    if saved && cameraState == .notDetermined {
                        if requested.last != .video || result != nil { failures.append("pending video permission") }
                        video = .denied
                        callbacks.removeFirst()(false)
                    }
                    let expectedRequests: [AVMediaType] = (microphoneState == .notDetermined ? [.audio] : [])
                        + (saved && cameraState == .notDetermined ? [.video] : [])
                    if requested != expectedRequests || result != (saved && video == .authorized) {
                        failures.append("capture request or authorization result")
                    }
                }
            }
        }
        var off = Selection(microphoneStatus: .authorized, cameraAutomaticCapture: true)
        off.microphone = false; off.camera = false
        resolve(off, status: { _ in .authorized }, request: { _, _ in failures.append("request while unchecked") },
                completion: { if $0 { failures.append("automatic camera while unchecked") } })
        // Declining the microphone must still allow the camera decision, and callback
        // booleans must never substitute for the actual authorization status.
        let both = Selection(microphoneStatus: .notDetermined, cameraAutomaticCapture: true)
        var audio: AVAuthorizationStatus = .notDetermined, video: AVAuthorizationStatus = .notDetermined
        var order: [AVMediaType] = []
        var completed = 0
        resolve(both, status: { $0 == .audio ? audio : video }, request: { media, done in
            order.append(media)
            if media == .audio { audio = .denied; done(false) }
            else { video = .authorized; done(true) }
        }, completion: { allowed in
            completed += 1
            if !allowed { failures.append("camera grant after microphone denial") }
        })
        if order != [.audio, .video] || completed != 1 { failures.append("sequential capture decisions") }
        resolve(both, status: { _ in .denied }, request: { _, _ in failures.append("request after denial") },
                completion: { if $0 { failures.append("automatic camera after revocation") } })
        return failures
    }
}
