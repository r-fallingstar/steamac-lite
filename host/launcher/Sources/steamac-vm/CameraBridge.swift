import AppKit
import AVFoundation
import CoreVideo
import SwiftUI

// Experimental raw NV12 frames over a dedicated local virtio-console port. No image files or network sockets.
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
    private var loggedFormat = false
    init(port: CameraPort) { self.port = port }
    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        guard let pixel = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        if !loggedFormat {
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
    static func requested(ready: Bool, preview: Bool, automatic: Bool, demand: Bool) -> Bool {
        ready && (preview || (automatic && demand))
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
        return cases.enumerated().compactMap { index, item in
            requested(ready: item.0, preview: item.1, automatic: item.2, demand: item.3) == item.4 ? nil : "camera demand policy \(index)"
        }
    }
}

final class CameraBridge: ObservableObject {
    let port: CameraPort
    let session = AVCaptureSession()
    private let sessionQueue = DispatchQueue(label: "steamac.camera.capture")
    private let frameQueue = DispatchQueue(label: "steamac.camera.frames")
    private let sink: CameraFrameSink
    struct Choice: Identifiable { let id: String; let name: String }
    @Published private(set) var devices: [Choice] = []
    @Published var selectedDeviceID = ""
    private var configured = false
    private var wanted = false
    private var manualPreview = false
    private var guestDemand = false
    @Published var automaticCaptureEnabled = true {
        didSet {
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
    init(port: CameraPort) {
        self.port = port; sink = CameraFrameSink(port: port)
        port.onLine = { [weak self] line in
            guard let self else { return }; log("camera guest: " + line)
            if line.hasPrefix("READY ") {
                ready = true; message = String(localized: "Camera is off. SteamOS receives a black picture.")
                if patternWanted { beginPattern() } else { reconcileCapture() }
            } else if line.hasPrefix("FRAMES ") { received = String(line.dropFirst(7)) }
            else if line == "DEMAND 1" || line == "DEMAND 0" {
                guestDemand = line == "DEMAND 1"
                reconcileCapture()
            }
        }
    }
    func applyBootPermissions() {
        automaticCaptureEnabled = CapturePermissionNotice.automaticCaptureDefault(in: LauncherSettings.shared.defaults)
    }
    private func reconcileCapture() {
        guard !syntheticOnly else { return }
        let requested = CameraCapturePolicy.requested(ready: ready, preview: manualPreview,
            automatic: automaticCaptureEnabled, demand: guestDemand)
        guard requested else {
            if wanted || running { stopCapture() }
            if automaticCaptureEnabled && AVCaptureDevice.authorizationStatus(for: .video) == .authorized {
                message = String(localized: "Camera is allowed and waiting for a game.")
            }
            return
        }
        guard AVCaptureDevice.authorizationStatus(for: .video) == .authorized else {
            if wanted || running { stopCapture() }
            message = String(localized: "Camera access is not allowed. Check macOS Camera settings.")
            return
        }
        wanted = true
        if !busy && !running { startAuthorized() }
    }
    func startPattern() { syntheticOnly = true; patternWanted = true; if ready { beginPattern() } }
    private func beginPattern() {
        guard patternTimer == nil else { return }; port.enable()
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
        let found = AVCaptureDevice.DiscoverySession(deviceTypes: [.builtInWideAngleCamera], mediaType: .video, position: .unspecified).devices
        devices = found.map { Choice(id: $0.uniqueID, name: $0.localizedName) }
        if !devices.contains(where: { $0.id == selectedDeviceID }) { selectedDeviceID = devices.first?.id ?? "" }
    }
    func start() {
        guard !syntheticOnly, ready, !busy, !running else { return }; manualPreview = true; wanted = true
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized: startAuthorized()
        case .notDetermined:
            busy = true
            AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in DispatchQueue.main.async {
                guard let self else { return }; self.busy = false
                if granted && self.wanted { self.startAuthorized() }
                else { self.wanted = false; self.message = String(localized: "Camera access is not allowed. Check macOS Camera settings.") }
            } }
        default: wanted = false; message = String(localized: "Camera access is not allowed. Check macOS Camera settings.")
        }
    }
    private func startAuthorized() {
        busy = true; message = String(localized: "Starting the built-in camera…")
        let selected = selectedDeviceID
        sessionQueue.async { [self] in
            do {
                if !configured {
                    let discovery = AVCaptureDevice.DiscoverySession(deviceTypes: [.builtInWideAngleCamera], mediaType: .video, position: .unspecified)
                    guard let device = discovery.devices.first(where: { $0.uniqueID == selected }) ?? discovery.devices.first else { throw OptionError("No built-in camera") }
                    let input = try AVCaptureDeviceInput(device: device)
                    session.beginConfiguration(); defer {
                        if !configured { session.inputs.forEach(session.removeInput); session.outputs.forEach(session.removeOutput) }
                        session.commitConfiguration()
                    }
                    guard session.canSetSessionPreset(.vga640x480), session.canAddInput(input) else { throw OptionError("640x480 camera input is unavailable") }
                    session.sessionPreset = .vga640x480; session.addInput(input)
                    let output = AVCaptureVideoDataOutput(); output.alwaysDiscardsLateVideoFrames = true
                    output.setSampleBufferDelegate(sink, queue: frameQueue)
                    guard session.canAddOutput(output) else { throw OptionError("Camera output is unavailable") }; session.addOutput(output)
                    // Frame-duration changes can select a different device format on macOS.
                    // Pin the delivered buffers as well as the session's preview preset.
                    output.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange,
                                            kCVPixelBufferWidthKey as String: CameraWire.width,
                                            kCVPixelBufferHeightKey as String: CameraWire.height]
                    try device.lockForConfiguration()
                    if device.activeFormat.videoSupportedFrameRateRanges.contains(where: { $0.minFrameRate <= 15 && $0.maxFrameRate >= 15 }) {
                        device.activeVideoMinFrameDuration = CMTime(value: 1, timescale: 15)
                        device.activeVideoMaxFrameDuration = CMTime(value: 1, timescale: 15)
                    }
                    device.unlockForConfiguration(); configured = true
                    DispatchQueue.main.async { self.deviceName = device.localizedName }
                }
                port.enable(); session.startRunning()
                DispatchQueue.main.async { [self] in
                    busy = false
                    if wanted { running = true; message = String(localized: "Sending the built-in camera to SteamOS.") }
                    else { stopCapture() }
                }
            } catch {
                port.stop(); DispatchQueue.main.async { [self] in busy = false; wanted = false; message = String(describing: error) }
            }
        }
    }
    func stop() {
        manualPreview = false; patternWanted = false; patternTimer?.cancel(); patternTimer = nil
        stopCapture()
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
        wanted = false
        port.stop(); running = false; message = String(localized: "Camera is off. SteamOS receives a black picture.")
        sessionQueue.async { [session] in if session.isRunning { session.stopRunning() } }
    }
    static func snapshotSelfTest(to directory: String) -> Never {
        let app = NSApplication.shared; app.setActivationPolicy(.regular); MainMenu.installMinimal()
        let bridge: CameraBridge
        do { bridge = CameraBridge(port: try CameraPort()) } catch { print(error); exit(1) }
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
            Text("Built-in camera (experimental)").font(.title2.bold())
            Toggle("Use camera only when a game requests it", isOn: $bridge.automaticCaptureEnabled)
            Picker("Camera", selection: $bridge.selectedDeviceID) {
                if bridge.devices.isEmpty { Text("Built-in camera").tag("") }
                ForEach(bridge.devices) { Text(verbatim: $0.name).tag($0.id) }
            }.disabled(bridge.running || bridge.busy)
            CameraPreview(session: bridge.session).frame(height: 260).background(.black)
            Text(verbatim: bridge.message)
            if !bridge.deviceName.isEmpty { Text(verbatim: bridge.deviceName).font(.caption) }
            Text(verbatim: "640 × 480 · 15 fps").font(.caption).foregroundStyle(.secondary)
            Text("Frames received by SteamOS: \(bridge.received)").font(.caption).monospacedDigit()
            HStack {
                Button("Allow and start camera") { bridge.start() }.disabled(!bridge.ready || bridge.running || bridge.busy)
                Button("Stop camera") { bridge.stopByUser() }.disabled(!bridge.running && !bridge.busy)
            }
            Button("Open Camera privacy settings…") { NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera")!) }
            Text("Camera permission alone does not start capture. Games start and stop it automatically. Start can be used for a preview.").font(.caption).foregroundStyle(.secondary)
        }.padding(20).frame(maxWidth: .infinity, alignment: .leading)
        }.frame(minWidth: 480, minHeight: 420).onAppear { bridge.refreshDevices() }
    }
}
