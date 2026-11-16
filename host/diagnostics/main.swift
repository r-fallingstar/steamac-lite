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
let utility = arguments.contains { $0.hasPrefix("--selftest") || $0.hasPrefix("--sentry-test") ||
    ["--help", "-h", "--headless", "--preview-update", "--ssh-password", "--create-disk", "--grow-disk"].contains($0) }
if utility || ProcessInfo.processInfo.environment["STEAMAC_VM_CHILD"] == "1" { execRuntime() }

let ja = Locale.preferredLanguages.first?.hasPrefix("ja") == true
let wizardKey = "liteFirstRunWizardVersion"
final class PrivacySettings: NSObject {
    @objc func microphone() { NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone")!) }
    @objc func camera() { NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera")!) }
}
if LiteDiagnostics.defaults.integer(forKey: LiteDiagnostics.consentKey) != LiteDiagnostics.consentVersion
    || LiteDiagnostics.defaults.integer(forKey: wizardKey) != 1 {
    let app = NSApplication.shared
    app.setActivationPolicy(.regular)
    DispatchQueue.main.async {
        let d = LiteDiagnostics.defaults
        let alert = NSAlert()
        alert.messageText = ja ? "steamac Liteの初回設定" : "Welcome to steamac Lite"
        alert.informativeText = ja
            ? "表示言語と、使用する機能を選んでください。マイク・カメラを選ぶとmacOSの許可を確認します。許可だけでは撮影・録音を始めません。あとからアプリの設定で変更できます。macOSで拒否済みの権限は、下の設定ボタンから変更してください。"
            : "Choose a language and optional features. Selected microphone/camera access is requested from macOS; permission alone does not start capture. Change choices later in Settings. If macOS previously denied access, use the privacy settings buttons below."
        let names = ["日本語", "English", "한국어", "Русский", "简体中文"]
        let codes = ["ja", "en", "ko", "ru", "zh-Hans"]
        let language = NSPopUpButton(frame: NSRect(x: 0, y: 0, width: 420, height: 28))
        language.addItems(withTitles: names)
        let preferred = d.string(forKey: "applicationLanguage") ?? Locale.preferredLanguages.first ?? "en"
        language.selectItem(at: codes.firstIndex(where: { preferred.hasPrefix($0 == "zh-Hans" ? "zh" : $0) }) ?? 1)
        language.setAccessibilityLabel("表示言語 / Language")
        let microphone = NSButton(checkboxWithTitle: ja ? "マイクの使用許可を確認する（ボイスチャット用）" : "Request microphone access for voice chat", target: nil, action: nil)
        let camera = NSButton(checkboxWithTitle: ja ? "ゲームで使うカメラの使用許可を確認する" : "Request camera access for games", target: nil, action: nil)
        let diagnostics = NSButton(checkboxWithTitle: ja ? "クラッシュレポートと診断を送信する（任意）" : "Send crash reports and diagnostics (optional)", target: nil, action: nil)
        diagnostics.state = .off
        let audioStatus = AVCaptureDevice.authorizationStatus(for: .audio)
        let videoStatus = AVCaptureDevice.authorizationStatus(for: .video)
        microphone.state = (audioStatus == .authorized || audioStatus == .notDetermined) ? .on : .off
        camera.state = (d.object(forKey: "cameraAutomaticCapture") == nil || d.bool(forKey: "cameraAutomaticCapture")) ? .on : .off
        let privacy = PrivacySettings()
        let buttons = NSStackView()
        buttons.orientation = .horizontal; buttons.spacing = 12
        for (title, selector) in [(ja ? "マイクの設定…" : "Microphone Settings…", #selector(PrivacySettings.microphone)),
                                  (ja ? "カメラの設定…" : "Camera Settings…", #selector(PrivacySettings.camera))] {
            buttons.addArrangedSubview(NSButton(title: title, target: privacy, action: selector))
        }
        let detail = NSTextField(wrappingLabelWithString: ja
            ? "診断を有効にすると、3分以上進まない起動や異常終了の情報を作者の非公開GitHubへ送信します。版番号、Macの型番・チップ・メモリ、起動段階、終了理由を含みます。名前、アカウント、画面、ファイル内容、ログ全文は自動送信しません。解除は「設定 → 一般」から。"
            : "If enabled, stalls over 3 minutes and abnormal exits are sent to the author's private GitHub: versions, Mac model/chip/RAM, startup stage and exit reason. Names, accounts, screens, file contents and full logs are not sent automatically. Turn off in Settings > General.")
        detail.font = .systemFont(ofSize: NSFont.smallSystemFontSize)
        let stack = NSStackView(views: [NSTextField(labelWithString: "表示言語 / Language"), language,
            microphone, camera, buttons, diagnostics, detail])
        stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 10
        stack.translatesAutoresizingMaskIntoConstraints = false
        stack.widthAnchor.constraint(equalToConstant: 420).isActive = true
        detail.widthAnchor.constraint(equalToConstant: 420).isActive = true
        stack.frame.size = stack.fittingSize
        alert.accessoryView = stack
        alert.addButton(withTitle: ja ? "続ける" : "Continue")
        alert.addButton(withTitle: ja ? "終了" : "Quit")
        app.activate()
        guard alert.runModal() == .alertFirstButtonReturn else { exit(0) }
        let selected = codes[language.indexOfSelectedItem]
        d.set(selected, forKey: "applicationLanguage"); d.set([selected], forKey: "AppleLanguages")
        let useMicrophone = microphone.state == .on, useCamera = camera.state == .on
        d.set(useMicrophone, forKey: "microphonePermissionSelected")
        d.set(useCamera, forKey: "cameraAutomaticCapture")
        LiteDiagnostics.consent(diagnostics.state == .on)
        func finish() {
            d.set(1, forKey: wizardKey)
            d.set(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "development", forKey: "capturePermissionsNoticeVersion")
            d.set(useMicrophone && AVCaptureDevice.authorizationStatus(for: .audio) == .authorized, forKey: "microphoneWasAuthorized")
            d.set(useCamera && AVCaptureDevice.authorizationStatus(for: .video) == .authorized, forKey: "cameraCaptureWasAuthorized")
            d.synchronize()
            let config = NSWorkspace.OpenConfiguration()
            config.createsNewApplicationInstance = true; config.activates = true
            config.arguments = arguments; config.environment = ProcessInfo.processInfo.environment
            NSWorkspace.shared.openApplication(at: Bundle.main.bundleURL, configuration: config) { _, error in exit(error == nil ? 0 : 1) }
        }
        StartupPermissions.resolve(microphone: useMicrophone, camera: useCamera, completion: finish)
        withExtendedLifetime(privacy) {}
    }
    app.run(); exit(0)
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
