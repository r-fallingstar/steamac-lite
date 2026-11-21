import AppKit
import AVFoundation
import CoreVideo
import SwiftUI

// Raw NV12 frames over a dedicated local virtio-console port. No image files or network sockets.
enum CameraWire {
    static let width = 640, height = 480, bytes = 640 * 480 * 3 / 2
    static let nv12: UInt32 = 0x3231564e
    static func encode(_ payload: Data?, sequence: UInt64) -> Data {
        var data = Data("FXCM".utf8)
        func append<T: FixedWidthInteger>(_ n: T) { var le = n.littleEndian; withUnsafeBytes(of: &le) { data.append(contentsOf: $0) } }
        append(UInt16(1)); append(UInt16(payload == nil ? 2 : 1))
        append(UInt32(width)); append(UInt32(height)); append(nv12)
        append(UInt32(payload?.count ?? 0)); append(sequence)
        if let payload { data.append(payload) }
        return data
    }
    static func pattern(_ sequence: UInt64) -> Data {
        var data = Data(repeating: 128, count: bytes)
        data.withUnsafeMutableBytes { (p: UnsafeMutableRawBufferPointer) in
            for row in 0..<height { for col in 0..<width { p[row * width + col] = UInt8((Int(sequence % 200) + col / 80 * 20) % 200 + 20) } }
        }
        return data
    }
    static func selfCheck() -> [String] {
        let stop = encode(nil, sequence: 9), frame = encode(pattern(10), sequence: 10)
        guard stop.count == 32, frame.count == 32 + bytes,
              Array(stop.prefix(8)) == [70,88,67,77,1,0,2,0],
              Array(frame.prefix(8)) == [70,88,67,77,1,0,1,0],
              pattern(10) != pattern(11) else { return ["camera frame encoding"] }
        return []
    }
}

final class CameraPort {
    static let name = "fx.camera"
    let guestInputFd: Int32, guestOutputFd: Int32
    private let writeFd: Int32, readFd: Int32
    private let condition = NSCondition()
    private var pending: Data?
    private var sending = false
    private var sequence: UInt64 = 0
    var onLine: ((String) -> Void)?
    init() throws {
        var toGuest = [Int32](repeating: 0, count: 2), fromGuest = [Int32](repeating: 0, count: 2)
        guard pipe(&toGuest) == 0 else { throw OptionError("camera pipe") }
        guard pipe(&fromGuest) == 0 else { close(toGuest[0]); close(toGuest[1]); throw OptionError("camera pipe") }
        guestInputFd = toGuest[0]; writeFd = toGuest[1]; readFd = fromGuest[0]; guestOutputFd = fromGuest[1]
        for fd in toGuest + fromGuest { _ = fcntl(fd, F_SETFD, FD_CLOEXEC) }
        _ = fcntl(writeFd, F_SETNOSIGPIPE, 1)
        Thread.detachNewThread { [self] in
            while true {
                condition.lock(); while pending == nil { condition.wait() }
                let frame = pending!; pending = nil; condition.unlock()
                let ok = frame.withUnsafeBytes { raw -> Bool in
                    var at = 0
                    while at < raw.count {
                        let n = Darwin.write(writeFd, raw.baseAddress! + at, raw.count - at)
                        if n < 0 && errno == EINTR { continue }
                        if n <= 0 { return false }; at += n
                    }
                    return true
                }
                if !ok { log("camera: guest write closed"); return }
            }
        }
        Thread.detachNewThread { [self] in
            var line = Data(), buf = [UInt8](repeating: 0, count: 1024)
            while true {
                let n = Darwin.read(readFd, &buf, buf.count)
                if n < 0 && errno == EINTR { continue }; if n <= 0 { return }
                for byte in buf.prefix(n) {
                    if byte == 10 { let message = String(decoding: line, as: UTF8.self); line.removeAll(); DispatchQueue.main.async { [weak self] in self?.onLine?(message) } }
                    else if line.count < 4096 { line.append(byte) }
                }
            }
        }
    }
    func enable() { condition.lock(); sending = true; condition.unlock() }
    func stop() {
        condition.lock(); sending = false; pending = CameraWire.encode(nil, sequence: sequence); condition.signal(); condition.unlock()
    }
    func frame(_ payload: Data) {
        guard payload.count == CameraWire.bytes else { return }
        condition.lock(); defer { condition.unlock() }; guard sending else { return }
        sequence &+= 1; pending = CameraWire.encode(payload, sequence: sequence); condition.signal()
    }
}

private final class CameraFrameSink: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    let port: CameraPort
    let diagnostics: Bool
    private var loggedFormat = false
    init(port: CameraPort, diagnostics: Bool) { self.port = port; self.diagnostics = diagnostics }
    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        guard let pixel = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        if diagnostics && !loggedFormat {
            loggedFormat = true
            log("camera capture: \(CVPixelBufferGetWidth(pixel))x\(CVPixelBufferGetHeight(pixel)) format=\(String(CVPixelBufferGetPixelFormatType(pixel), radix: 16)) planes=\(CVPixelBufferGetPlaneCount(pixel))")
        }
        guard
              CVPixelBufferGetWidth(pixel) == CameraWire.width, CVPixelBufferGetHeight(pixel) == CameraWire.height,
              CVPixelBufferGetPixelFormatType(pixel) == kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange,
              CVPixelBufferGetPlaneCount(pixel) == 2 else { return }
        guard CVPixelBufferLockBaseAddress(pixel, .readOnly) == kCVReturnSuccess else { return }
        defer { CVPixelBufferUnlockBaseAddress(pixel, .readOnly) }
        var bytes = Data(capacity: CameraWire.bytes)
        for plane in 0..<2 {
            guard let base = CVPixelBufferGetBaseAddressOfPlane(pixel, plane) else { return }
            let stride = CVPixelBufferGetBytesPerRowOfPlane(pixel, plane), rows = plane == 0 ? CameraWire.height : CameraWire.height / 2
            for row in 0..<rows { bytes.append(base.advanced(by: row * stride).assumingMemoryBound(to: UInt8.self), count: CameraWire.width) }
        }
        port.frame(bytes)
    }
}

enum CameraCapturePolicy {
    static func requested(ready: Bool, preview: Bool, automatic: Bool, demand: Bool,
                          foreground: Bool = true, paused: Bool = false) -> Bool {
        ready && foreground && !paused && (preview || (automatic && demand))
    }
    /// A game's request (automatic mode) asks macOS once while access is undecided: otherwise a
    /// permission lost or never granted for this version (the startup notice shows once per version,
    /// or the camera was turned on later in Settings) leaves the game without a camera and no prompt.
    /// The manual preview asks in `start()`; a pending request is not repeated.
    static func asksOnDemand(_ status: AVAuthorizationStatus, preview: Bool, pending: Bool) -> Bool {
        status == .notDetermined && !preview && !pending
    }
    static func describe(_ status: AVAuthorizationStatus) -> String {
        switch status {
        case .authorized: return "allowed"
        case .denied: return "denied"
        case .restricted: return "restricted"
        case .notDetermined: return "not requested yet"
        @unknown default: return "unknown (\(status.rawValue))"
        }
    }
    static func selfCheck() -> [String] {
        let cases: [(Bool, Bool, Bool, Bool, Bool)] = [
            (true, false, true, false, false), // Permission/automatic mode alone never captures.
            (true, false, true, true, true),
            (true, false, false, true, false),
            (true, true, false, false, true),
            (false, true, true, true, false),
            (true, false, false, false, false)
        ]
        var failures = cases.enumerated().compactMap { index, item in
            requested(ready: item.0, preview: item.1, automatic: item.2, demand: item.3) == item.4 ? nil : "camera demand policy \(index)"
        }
        for preview in [false, true] {
            if requested(ready: true, preview: preview, automatic: true, demand: true, paused: true) {
                failures.append("camera captured while VM paused")
            }
            if requested(ready: true, preview: preview, automatic: true, demand: true, foreground: false) {
                failures.append("camera captured while another app was active")
            }
        }
        let asks: [(AVAuthorizationStatus, Bool, Bool, Bool)] = [
            (.notDetermined, false, false, true),   // a game's request asks once
            (.notDetermined, false, true, false),   // never while a request is pending
            (.notDetermined, true, false, false),   // the manual preview asks in start()
            (.denied, false, false, false),         // a refusal is never asked again
            (.restricted, false, false, false),
            (.authorized, false, false, false)
        ]
        for (index, item) in asks.enumerated()
        where asksOnDemand(item.0, preview: item.1, pending: item.2) != item.3 {
            failures.append("camera on-demand permission policy \(index)")
        }
        return failures
    }
}

final class CameraBridge: ObservableObject {
    let port: CameraPort
    let diagnostics: Bool
    let session = AVCaptureSession()
    private let sessionQueue = DispatchQueue(label: "steamac.camera.capture")
    private let frameQueue = DispatchQueue(label: "steamac.camera.frames")
    private let sink: CameraFrameSink
    struct Choice: Identifiable { let id: String; let name: String }
    @Published private(set) var devices: [Choice] = []
    @Published var selectedDeviceID = ""
    private var appActive = true
    private var activationObservers: [NSObjectProtocol] = []
    private var availabilityObserver: NSKeyValueObservation?
    private var startWork: DispatchWorkItem?
    private var captureGeneration: UInt64 = 0
    private var permissionRequestPending = false
    private var wanted = false
    private var manualPreview = false
    private var guestDemand = false
    /// The current request was already logged as lacking camera access (once per request).
    private var loggedNoAccess = false
    private var paused = false
    @Published var automaticCaptureEnabled = true {
        didSet {
            guard !syntheticOnly else { return }
            LauncherSettings.shared.defaults.set(automaticCaptureEnabled, forKey: "cameraAutomaticCapture")
            if !automaticCaptureEnabled || AVCaptureDevice.authorizationStatus(for: .video) == .authorized {
                LauncherSettings.shared.defaults.set(automaticCaptureEnabled, forKey: CapturePermissionNotice.cameraGrantedKey)
            }
            reconcileCapture()
        }
    }
    private var patternTimer: DispatchSourceTimer?
    private var patternWanted = false
    private var syntheticOnly = false
    @Published private(set) var ready = false
    @Published private(set) var running = false
    @Published private(set) var busy = false
    @Published private(set) var deviceName = ""
    @Published private(set) var received = "0"
    @Published private(set) var message = String(localized: "Waiting for the SteamOS camera bridge.")
    var canStop: Bool { running || busy || availabilityObserver != nil }
    init(port: CameraPort, diagnostics: Bool = false, syntheticOnly: Bool = false) {
        self.port = port; self.diagnostics = diagnostics; self.syntheticOnly = syntheticOnly
        sink = CameraFrameSink(port: port, diagnostics: diagnostics)
        port.onLine = { [weak self] line in
            guard let self else { return }
            if diagnostics { log("camera guest: " + line) }
            if line.hasPrefix("READY ") {
                ready = true; message = String(localized: "Camera is off. SteamOS receives a black picture.")
                if patternWanted { beginPattern() } else { reconcileCapture() }
            } else if diagnostics && line.hasPrefix("FRAMES ") { received = String(line.dropFirst(7)) }
            else if line == "DEMAND 1" || line == "DEMAND 0" {
                guestDemand = line == "DEMAND 1"
                reconcileCapture()
            }
        }
    }
    func applyBootPermissions() {
        guard !syntheticOnly else { return }
        automaticCaptureEnabled = CapturePermissionNotice.automaticCaptureDefault(in: LauncherSettings.shared.defaults)
    }
    func followApplicationActivation(_ app: NSApplication) {
        guard !syntheticOnly else { return }
        let center = NotificationCenter.default
        activationObservers = [
            center.addObserver(forName: NSApplication.didResignActiveNotification, object: app, queue: .main) { [weak self] _ in
                self?.setAppActive(false)
            },
            center.addObserver(forName: NSApplication.didBecomeActiveNotification, object: app, queue: .main) { [weak self] _ in
                self?.setAppActive(true)
            },
        ]
        setAppActive(app.isActive)
    }
    deinit { activationObservers.forEach(NotificationCenter.default.removeObserver) }

    private func setAppActive(_ active: Bool) {
        guard appActive != active else { return }
        appActive = active
        reconcileCapture()
    }

    private func reconcileCapture() {
        guard !syntheticOnly else { return }
        let requested = CameraCapturePolicy.requested(ready: ready, preview: manualPreview,
            automatic: automaticCaptureEnabled, demand: guestDemand, foreground: appActive, paused: paused)
        guard requested else {
            loggedNoAccess = false
            if wanted || running { stopCapture() }
            if ready && appActive && !paused && automaticCaptureEnabled && AVCaptureDevice.authorizationStatus(for: .video) == .authorized {
                message = String(localized: "Camera is allowed and waiting for a game.")
            }
            return
        }
        let status = AVCaptureDevice.authorizationStatus(for: .video)
        guard status == .authorized else {
            if wanted || running { stopCapture() }
            if CameraCapturePolicy.asksOnDemand(status, preview: manualPreview, pending: permissionRequestPending) {
                permissionRequestPending = true; busy = true
                log("camera: a game requested the camera; asking macOS for camera access")
                AVCaptureDevice.requestAccess(for: .video) { granted in DispatchQueue.main.async { [weak self] in
                    guard let self else { return }
                    self.permissionRequestPending = false; self.busy = false
                    log("camera: macOS camera access \(granted ? "allowed" : "not allowed")")
                    self.reconcileCapture()
                } }
                return
            }
            if !permissionRequestPending {
                if !loggedNoAccess {
                    loggedNoAccess = true
                    log("camera: a game requested the camera, but camera access is \(CameraCapturePolicy.describe(status))")
                }
                message = String(localized: "Camera access is not allowed. Check macOS Camera settings.")
            }
            return
        }
        wanted = true
        if !busy && !running { startAuthorized() }
    }
    func startPattern() { syntheticOnly = true; patternWanted = true; if ready && !paused { beginPattern() } }
    private func beginPattern() {
        guard patternTimer == nil, !paused else { return }; port.enable()
        let timer = DispatchSource.makeTimerSource(queue: frameQueue); var sequence: UInt64 = 0
        timer.schedule(deadline: .now(), repeating: 1.0 / 15)
        timer.setEventHandler { [port] in sequence &+= 1; port.frame(CameraWire.pattern(sequence)) }
        patternTimer = timer; timer.resume()
        if let seconds = ProcessInfo.processInfo.environment["STEAMAC_CAMERA_PATTERN_SECONDS"].flatMap(Double.init), seconds > 0 {
            DispatchQueue.main.asyncAfter(deadline: .now() + seconds) { [weak self] in self?.stop(); log("camera: synthetic pattern stopped") }
        }
        log("camera: synthetic pattern only (no capture device)")
    }
    func refreshDevices() {
        guard !syntheticOnly else { return }
        let found = Self.builtInDevices()
        devices = found.map { Choice(id: $0.uniqueID, name: $0.localizedName) }
        if !devices.contains(where: { $0.id == selectedDeviceID }) { selectedDeviceID = devices.first?.id ?? "" }
    }
    func start() {
        guard !syntheticOnly, ready, appActive, !paused, !busy, !permissionRequestPending, !running else { return }
        manualPreview = true; wanted = true
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized: startAuthorized()
        case .notDetermined:
            busy = true; permissionRequestPending = true
            AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in DispatchQueue.main.async {
                guard let self else { return }; self.permissionRequestPending = false; self.busy = false
                if granted { self.reconcileCapture() }
                else { self.manualPreview = false; self.wanted = false; self.message = String(localized: "Camera access is not allowed. Check macOS Camera settings.") }
            } }
        default: manualPreview = false; wanted = false; message = String(localized: "Camera access is not allowed. Check macOS Camera settings.")
        }
    }
    private static func builtInDevices() -> [AVCaptureDevice] {
        // Continuity cameras can masquerade as builtInWideAngleCamera without an Info.plist opt-in.
        AVCaptureDevice.DiscoverySession(deviceTypes: [.builtInWideAngleCamera], mediaType: .video, position: .unspecified)
            .devices.filter { !$0.isContinuityCamera }
    }
    private func startAuthorized() {
        let devices = Self.builtInDevices()
        guard let device = devices.first(where: { $0.uniqueID == selectedDeviceID }) ?? devices.first else {
            wanted = false; manualPreview = false
            message = String(localized: "No built-in camera is available on this Mac.")
            return
        }
        if device.isInUseByAnotherApplication {
            availabilityObserver = device.observe(\.isInUseByAnotherApplication, options: [.new]) { [weak self] _, change in
                guard change.newValue == false else { return }
                DispatchQueue.main.async { [weak self] in self?.reconcileCapture() }
            }
            // Recheck after subscribing so a release between the initial check and observation is not lost.
            if device.isInUseByAnotherApplication {
                message = String(localized: "Waiting for the other app to release the camera.")
                return
            }
        }
        availabilityObserver = nil
        captureGeneration &+= 1
        let generation = captureGeneration
        busy = true; message = String(localized: "Starting the built-in camera…")
        let work = DispatchWorkItem { [weak self] in
            guard let self else { return }
            do {
                try self.configureCapture(device)
                self.session.startRunning()
                guard self.session.isRunning else { throw OptionError("Camera session did not start") }
                DispatchQueue.main.async { [self] in
                    guard self.captureGeneration == generation else { return }
                    self.startWork = nil; self.busy = false
                    if self.wanted {
                        self.deviceName = device.localizedName
                        self.port.enable(); self.running = true
                        if self.automaticCaptureEnabled {
                            LauncherSettings.shared.defaults.set(true, forKey: CapturePermissionNotice.cameraGrantedKey)
                        }
                        self.message = String(localized: "Sending the built-in camera to SteamOS.")
                    }
                    else { self.stopCapture() }
                }
            } catch {
                log("camera: \(error)")
                self.releaseCaptureHardware()
                self.port.stop()
                DispatchQueue.main.async { [self] in
                    guard self.captureGeneration == generation else { return }
                    self.startWork = nil; self.busy = false
                    if device.isInUseByAnotherApplication {
                        self.reconcileCapture()
                        return
                    }
                    self.wanted = false; self.manualPreview = false
                    self.message = (error as? OptionError)?.localized
                        ?? String(localized: "The built-in camera could not start. Check camera access and try again.")
                }
            }
        }
        startWork = work
        sessionQueue.async(execute: work)
    }
    private func configureCapture(_ device: AVCaptureDevice) throws {
        let input = try AVCaptureDeviceInput(device: device)
        session.beginConfiguration()
        defer { session.commitConfiguration() }
        guard session.canSetSessionPreset(.vga640x480), session.canAddInput(input) else {
            throw OptionError("640x480 camera input is unavailable", localized: String(localized: "The built-in camera cannot provide 640 × 480 video."))
        }
        session.sessionPreset = .vga640x480; session.addInput(input)
        let output = AVCaptureVideoDataOutput(); output.alwaysDiscardsLateVideoFrames = true
        output.setSampleBufferDelegate(sink, queue: frameQueue)
        guard session.canAddOutput(output) else {
            throw OptionError("Camera output is unavailable", localized: String(localized: "The built-in camera output is unavailable."))
        }
        session.addOutput(output)
        // Pin the delivered buffers as well as the preset: changing the frame rate can select another format.
        output.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange,
                                kCVPixelBufferWidthKey as String: CameraWire.width,
                                kCVPixelBufferHeightKey as String: CameraWire.height]
        try device.lockForConfiguration()
        defer { device.unlockForConfiguration() }
        if device.activeFormat.videoSupportedFrameRateRanges.contains(where: { $0.minFrameRate <= 15 && $0.maxFrameRate >= 15 }) {
            device.activeVideoMinFrameDuration = CMTime(value: 1, timescale: 15)
            device.activeVideoMaxFrameDuration = CMTime(value: 1, timescale: 15)
        }
    }
    private func releaseCaptureHardware() {
        if session.isRunning { session.stopRunning() }
        session.beginConfiguration()
        session.outputs.forEach(session.removeOutput)
        session.inputs.forEach(session.removeInput)
        session.commitConfiguration()
        frameQueue.sync {}
    }
    func vmPaused(_ paused: Bool) {
        self.paused = paused
        if paused { stop() }
        else { reconcileCapture() }
    }
    func stop() {
        manualPreview = false; patternWanted = false; patternTimer?.cancel(); patternTimer = nil
        stopCapture()
    }
    func shutdown() {
        activationObservers.forEach(NotificationCenter.default.removeObserver)
        activationObservers.removeAll()
        appActive = false
        stop()
    }
    func stopByUser() {
        manualPreview = false
        automaticCaptureEnabled = false
        stop()
    }
    func stopPreview() {
        manualPreview = false
        reconcileCapture()
    }
    private func stopCapture() {
        availabilityObserver = nil
        startWork?.cancel(); startWork = nil
        captureGeneration &+= 1
        let generation = captureGeneration
        wanted = false
        port.stop(); running = false; busy = true
        message = String(localized: "Camera is off. SteamOS receives a black picture.")
        sessionQueue.async { [self] in
            releaseCaptureHardware()
            DispatchQueue.main.async { [self] in
                guard captureGeneration == generation else { return }
                busy = permissionRequestPending
                // A new demand may arrive while stopRunning is in progress. Restart only after it finishes.
                if wanted { reconcileCapture() }
            }
        }
    }
    static func activationSelfCheck() -> [String] {
        var failures: [String] = []
        for support in [false, true] {
            for headless in [false, true] {
                for diagnostic in [false, true] {
                    var options = Options()
                    options.headless = headless; options.experimentalCamera = diagnostic
                    if options.cameraEnabled(bundleSupport: support) != (diagnostic || (support && !headless)) {
                        failures.append("camera bundle/diagnostic activation")
                    }
                    options.selftestRenderPixels = true
                    if options.cameraEnabled(bundleSupport: support) { failures.append("camera enabled during rendering self-test") }
                }
            }
        }
        do {
            let pattern = try Options.parse(["steamac-vm", "--camera-test-pattern"])
            if !pattern.cameraTestPattern || !pattern.experimentalCamera || !pattern.cameraEnabled(bundleSupport: false) {
                failures.append("synthetic diagnostic activation")
            }
            for flag in ["--selftest-camera", "--selftest-camera-ui", "--selftest-display", "--selftest-settings"] {
                let test = try Options.parse(["steamac-vm", flag, "--experimental-camera"])
                if test.cameraEnabled(bundleSupport: true) { failures.append("capture enabled during " + flag) }
            }
        } catch { failures.append("camera diagnostic options: \(error)") }
        return failures
    }
    static func snapshotSelfTest(to directory: String) -> Never {
        let app = NSApplication.shared; app.setActivationPolicy(.regular); MainMenu.installMinimal()
        let bridge: CameraBridge
        do { bridge = CameraBridge(port: try CameraPort(), syntheticOnly: true) } catch { print(error); exit(1) }
        DispatchQueue.main.async {
            let context = SettingsContext(settings: LauncherSettings.shared, sound: nil, restart: nil, vmHasPad: false, vmHasSound: false)
            context.camera = bridge
            let settings = SettingsWindowController(context: context)
            settings.show(tab: .camera)
            DispatchQueue.main.asyncAfter(deadline: .now() + 1) {
                let window = settings.window
                guard let visible = window.screen?.visibleFrame, visible.contains(window.frame),
                      let rep = SettingsWindowController.snapshot(window),
                      let png = rep.representation(using: .png, properties: [:]) else { print("camera-ui: FAIL"); exit(1) }
                do {
                    try FileManager.default.createDirectory(atPath: directory, withIntermediateDirectories: true)
                    try png.write(to: URL(fileURLWithPath: directory).appendingPathComponent("camera-settings.png"))
                    print("camera-ui: PASS (no device opened)"); exit(0)
                } catch { print(error); exit(1) }
            }
        }
        app.run(); exit(1)
    }

}

private final class CameraPreviewView: NSView {
    let preview = AVCaptureVideoPreviewLayer()
    override init(frame: NSRect) { super.init(frame: frame); wantsLayer = true; preview.videoGravity = .resizeAspect; layer?.addSublayer(preview) }
    required init?(coder: NSCoder) { fatalError() }
    override func layout() { super.layout(); preview.frame = bounds }
}
private struct CameraPreview: NSViewRepresentable {
    let session: AVCaptureSession
    func makeNSView(context: Context) -> CameraPreviewView { let view = CameraPreviewView(); view.preview.session = session; return view }
    func updateNSView(_ view: CameraPreviewView, context: Context) {}
}
struct CameraSettingsView: View {
    @ObservedObject var bridge: CameraBridge
    var body: some View {
        ScrollView {
        VStack(alignment: .leading, spacing: 14) {
            Text("Built-in camera").font(.title2.bold())
            Toggle("Use camera only when a game requests it", isOn: $bridge.automaticCaptureEnabled)
            Picker("Camera", selection: $bridge.selectedDeviceID) {
                if bridge.devices.isEmpty { Text("Built-in camera").tag("") }
                ForEach(bridge.devices) { Text(verbatim: $0.name).tag($0.id) }
            }.disabled(bridge.running || bridge.busy)
            CameraPreview(session: bridge.session).frame(height: 260).background(.black)
            Text(verbatim: bridge.message)
            if !bridge.deviceName.isEmpty { Text(verbatim: bridge.deviceName).font(.caption) }
            Text(verbatim: "640 × 480 · 15 fps").font(.caption).foregroundStyle(.secondary)
            if bridge.diagnostics {
                Text("Frames received by SteamOS: \(bridge.received)").font(.caption).monospacedDigit()
            }
            HStack {
                Button("Allow and start camera") { bridge.start() }.disabled(!bridge.ready || bridge.running || bridge.busy)
                Button("Stop camera") { bridge.stopByUser() }.disabled(!bridge.canStop)
            }
            Button("Open Camera privacy settings…") { NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera")!) }
            Text("Camera permission alone does not start capture. Games start and stop it automatically. Start can be used for a preview.").font(.caption).foregroundStyle(.secondary)
            Text("Only this Mac’s built-in camera is supported.").font(.caption).foregroundStyle(.secondary)
        }.padding(20).frame(maxWidth: .infinity, alignment: .leading)
        }.frame(minWidth: 480, minHeight: 420).onAppear { bridge.refreshDevices() }
            .onDisappear { bridge.stopPreview() }
    }
}
