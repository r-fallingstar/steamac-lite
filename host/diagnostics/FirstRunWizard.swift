import AppKit
import AVFoundation
import Foundation

/// An ordinary window, not an NSAlert accessory or a nested modal loop. Its
/// content is laid out before presentation; TCC is queried only after Continue.
final class FirstRunWizard: NSObject, NSWindowDelegate {
    static let versionKey = "liteFirstRunWizardVersion"
    private let ja = Locale.preferredLanguages.first?.hasPrefix("ja") == true
    private let arguments: [String]
    let window: NSWindow
    private let language = NSPopUpButton(frame: .zero)
    private let microphone = NSButton(checkboxWithTitle: "", target: nil, action: nil)
    private let camera = NSButton(checkboxWithTitle: "", target: nil, action: nil)
    private let diagnostics = NSButton(checkboxWithTitle: "", target: nil, action: nil)
    private let next = NSButton(title: "", target: nil, action: nil)
    private let status = NSTextField(labelWithString: "")
    private let codes = ["ja", "en", "ko", "ru", "zh-Hans"]
    private var rowFrames: [NSRect] = []
    private var bodyWidth: CGFloat = 0
    private var document: NSView!
    private var scroll: NSScrollView!

    private final class Form: NSView { override var isFlipped: Bool { true } }

    init(arguments: [String]) {
        self.arguments = arguments
        let available = NSScreen.main?.visibleFrame.height ?? 800
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 600, height: min(640, max(480, available - 80))),
                          styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        super.init()
        window.title = ja ? "steamac Lite — 初回設定" : "steamac Lite — First-run setup"
        window.isReleasedWhenClosed = false
        window.delegate = self
        build()
    }

    private func text(_ ja: String, _ en: String) -> String { self.ja ? ja : en }

    private func build() {
        guard let content = window.contentView else { return }
        let h = content.bounds.height
        let icon = NSImageView(frame: NSRect(x: 24, y: h - 76, width: 48, height: 48))
        icon.image = NSApp.applicationIconImage; content.addSubview(icon)
        let title = NSTextField(labelWithString: "steamac Lite")
        title.font = .systemFont(ofSize: 22, weight: .semibold)
        title.frame = NSRect(x: 88, y: h - 53, width: 480, height: 30); content.addSubview(title)
        let subtitle = NSTextField(labelWithString: text("はじめの設定", "First-run setup"))
        subtitle.font = .systemFont(ofSize: 14)
        subtitle.textColor = .secondaryLabelColor
        subtitle.frame = NSRect(x: 88, y: h - 76, width: 480, height: 20); content.addSubview(subtitle)

        scroll = NSScrollView(frame: NSRect(x: 24, y: 92, width: 552, height: h - 190))
        scroll.hasVerticalScroller = true; scroll.autohidesScrollers = true
        scroll.drawsBackground = false
        bodyWidth = scroll.contentSize.width - 16
        document = Form(frame: NSRect(x: 0, y: 0, width: scroll.contentSize.width, height: 1))
        scroll.documentView = document; content.addSubview(scroll)
        var y: CGFloat = 0
        func paragraph(_ value: String, small: Bool = false) {
            let font = NSFont.systemFont(ofSize: small ? 12 : 13)
            let bounds = (value as NSString).boundingRect(with: NSSize(width: bodyWidth, height: 10000),
                options: [.usesLineFragmentOrigin, .usesFontLeading], attributes: [.font: font])
            let height = ceil(bounds.height) + 8
            let label = NSTextField(wrappingLabelWithString: value)
            label.font = font; label.textColor = small ? .secondaryLabelColor : .labelColor
            label.frame = NSRect(x: 0, y: y, width: bodyWidth, height: height)
            document.addSubview(label); rowFrames.append(label.frame)
            y += height + 16
        }
        paragraph(text("表示言語と使用する機能を選んでください。マイク・カメラの確認は「続ける」のあとに行います。許可を取るだけでは撮影・録音を始めません。",
                       "Choose a language and optional features. Selected microphone/camera access is requested after Continue. Permission alone does not start capture."))
        let label = NSTextField(labelWithString: "表示言語 / Language")
        label.font = .systemFont(ofSize: 13, weight: .medium)
        label.frame = NSRect(x: 0, y: y + 4, width: 145, height: 22)
        language.frame = NSRect(x: 155, y: y, width: 230, height: 28)
        language.addItems(withTitles: ["日本語", "English", "한국어", "Русский", "简体中文"])
        language.setAccessibilityLabel("表示言語 / Language")
        let d = LiteDiagnostics.defaults
        let preferred = d.string(forKey: "applicationLanguage") ?? Locale.preferredLanguages.first ?? "en"
        language.selectItem(at: codes.firstIndex(where: { preferred.hasPrefix($0 == "zh-Hans" ? "zh" : $0) }) ?? 1)
        document.addSubview(label); document.addSubview(language)
        rowFrames.append(NSRect(x: 0, y: y, width: bodyWidth, height: 28)); y += 48
        for (button, value) in [
            (microphone, text("マイクの使用許可を確認する（ボイスチャット用）", "Request microphone access for voice chat")),
            (camera, text("ゲームで使うカメラの使用許可を確認する", "Request camera access for games"))] {
            button.title = value; button.frame = NSRect(x: 0, y: y, width: bodyWidth, height: 26)
            document.addSubview(button); rowFrames.append(button.frame); y += 34
        }
        // No synchronous TCC calls while constructing or painting the window.
        microphone.state = d.object(forKey: "microphonePermissionSelected") == nil || d.bool(forKey: "microphonePermissionSelected") ? .on : .off
        camera.state = d.object(forKey: "cameraAutomaticCapture") == nil || d.bool(forKey: "cameraAutomaticCapture") ? .on : .off
        let micSettings = NSButton(title: text("マイクの設定…", "Microphone Settings…"), target: self, action: #selector(openMicrophone))
        let cameraSettings = NSButton(title: text("カメラの設定…", "Camera Settings…"), target: self, action: #selector(openCamera))
        micSettings.frame = NSRect(x: 0, y: y, width: 180, height: 28)
        cameraSettings.frame = NSRect(x: 192, y: y, width: 180, height: 28)
        document.addSubview(micSettings); document.addSubview(cameraSettings)
        rowFrames.append(NSRect(x: 0, y: y, width: bodyWidth, height: 28)); y += 36
        paragraph(text("拒否済みの権限やmacOSの許可の解除は、上の設定ボタンから変更できます。",
                       "Use the settings buttons to change access previously denied or to revoke macOS permissions."), small: true)
        diagnostics.title = text("クラッシュレポートと診断を送信する（任意）", "Send crash reports and diagnostics (optional)")
        diagnostics.state = d.integer(forKey: LiteDiagnostics.consentKey) == LiteDiagnostics.consentVersion && d.bool(forKey: LiteDiagnostics.enabledKey) ? .on : .off
        diagnostics.frame = NSRect(x: 0, y: y, width: bodyWidth, height: 26)
        document.addSubview(diagnostics); rowFrames.append(diagnostics.frame); y += 34
        paragraph(text("3分以上進まない起動や異常終了の情報を作者の非公開GitHubに送信します。版番号、Macの型番・チップ・メモリ、起動段階、終了理由を含みます。名前、アカウント、画面、ファイル内容、ログ全文は自動送信しません。解除は「設定 → 一般」から行えます。",
                       "Sends startup stalls lasting over 3 minutes and abnormal exits to the author's private GitHub: versions, Mac model/chip/RAM, startup stage and exit reason. Names, accounts, screens, file contents and full logs are not sent automatically. Turn off in Settings > General."), small: true)
        document.frame.size.height = y
        scroll.contentView.scroll(to: .zero)

        status.frame = NSRect(x: 24, y: 62, width: 552, height: 20)
        status.font = .systemFont(ofSize: 12); status.textColor = .secondaryLabelColor
        content.addSubview(status)
        let quit = NSButton(title: text("終了", "Quit"), target: self, action: #selector(close))
        quit.frame = NSRect(x: 352, y: 20, width: 106, height: 32)
        quit.keyEquivalent = "\u{1b}"; content.addSubview(quit)
        next.title = text("続ける", "Continue"); next.target = self; next.action = #selector(continueSetup)
        next.frame = NSRect(x: 470, y: 20, width: 106, height: 32)
        next.keyEquivalent = "\r"; content.addSubview(next)
        window.initialFirstResponder = language
    }

    func show() { window.center(); window.makeKeyAndOrderFront(nil); NSApp.activate() }
    @objc private func close() { NSApp.terminate(nil) }
    func windowWillClose(_ notification: Notification) { NSApp.terminate(nil) }
    @objc private func openMicrophone() { NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone")!) }
    @objc private func openCamera() { NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera")!) }

    @objc private func continueSetup() {
        next.isEnabled = false
        let audio = microphone.state == .on, video = camera.state == .on
        language.isEnabled = false; microphone.isEnabled = false; camera.isEnabled = false; diagnostics.isEnabled = false
        status.stringValue = text("macOSの使用許可を確認しています…", "Checking macOS permissions…")
        let d = LiteDiagnostics.defaults
        let selected = codes[language.indexOfSelectedItem]
        d.set(selected, forKey: "applicationLanguage"); d.set([selected], forKey: "AppleLanguages")
        d.set(audio, forKey: "microphonePermissionSelected"); d.set(video, forKey: "cameraAutomaticCapture")
        LiteDiagnostics.consent(diagnostics.state == .on)
        // TCC may be slow on a cold start. Keep the painted window and its Quit
        // action responsive while the system resolves the request.
        DispatchQueue.global(qos: .userInitiated).async { [self] in
            StartupPermissions.resolve(microphone: audio, camera: video) {
                DispatchQueue.main.async { self.finish(microphone: audio, camera: video) }
            }
        }
    }

    private func finish(microphone: Bool, camera: Bool) {
        let d = LiteDiagnostics.defaults
        d.set(1, forKey: Self.versionKey)
        d.set(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "development", forKey: "capturePermissionsNoticeVersion")
        d.set(microphone && AVCaptureDevice.authorizationStatus(for: .audio) == .authorized, forKey: "microphoneWasAuthorized")
        d.set(camera && AVCaptureDevice.authorizationStatus(for: .video) == .authorized, forKey: "cameraCaptureWasAuthorized")
        d.synchronize()
        status.stringValue = text("初回設定を保存しました。起動しています…", "Setup saved. Opening steamac Lite…")
        let config = NSWorkspace.OpenConfiguration()
        config.createsNewApplicationInstance = true; config.activates = true
        config.arguments = arguments; config.environment = ProcessInfo.processInfo.environment
        NSWorkspace.shared.openApplication(at: Bundle.main.bundleURL, configuration: config) { _, error in exit(error == nil ? 0 : 1) }
    }

    func layoutFailures() -> [String] {
        var failures: [String] = []
        for (i, frame) in rowFrames.enumerated() {
            if frame.minX < 0 || frame.maxX > bodyWidth + 1 || frame.minY < 0 || frame.maxY > document.bounds.height + 1 { failures.append("row \(i) outside document") }
            if i > 0 && rowFrames[i - 1].maxY > frame.minY { failures.append("rows \(i - 1)/\(i) overlap") }
        }
        if scroll.frame.maxY > window.contentView!.bounds.height - 90 || scroll.frame.minY < status.frame.maxY { failures.append("header/footer overlap") }
        return failures
    }

}
