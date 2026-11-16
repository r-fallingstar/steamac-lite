import AVFoundation
import Foundation

/// Request only selected, undecided permissions. Never create a capture session.
enum StartupPermissions {
    static func resolve(microphone: Bool, camera: Bool,
                        status: @escaping (AVMediaType) -> AVAuthorizationStatus = { AVCaptureDevice.authorizationStatus(for: $0) },
                        request: @escaping (AVMediaType, @escaping (Bool) -> Void) -> Void = { AVCaptureDevice.requestAccess(for: $0, completionHandler: $1) },
                        completion: @escaping () -> Void) {
        func next(_ remaining: [AVMediaType]) {
            guard let first = remaining.first else { completion(); return }
            let rest = Array(remaining.dropFirst())
            guard status(first) == .notDetermined else { next(rest); return }
            request(first) { _ in
                if Thread.isMainThread { next(rest) }
                else { DispatchQueue.main.async { next(rest) } }
            }
        }
        next((microphone ? [.audio] : []) + (camera ? [.video] : []))
    }
}
