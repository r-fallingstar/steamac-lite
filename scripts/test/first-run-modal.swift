import AppKit
import Foundation

/// Compile with the production FirstRunScheduling.swift; no VM, downloads or account.
/// A run-loop timer closes the modal even if a regression blocks the main queue.
@main
struct FirstRunModalTest {
    final class Probe: @unchecked Sendable { var delivered = false }

    @MainActor
    static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        let probe = Probe()
        FirstRunScheduling.schedule {
            MainActor.assumeIsolated {
                let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 240, height: 80),
                                      styleMask: [.titled], backing: .buffered, defer: false)
                window.isReleasedWhenClosed = false
                window.title = "SteamAC modal progress regression test"
                let watchdog = Timer(timeInterval: 5, repeats: false) { _ in
                    MainActor.assumeIsolated { app.abortModal() }
                }
                RunLoop.main.add(watchdog, forMode: .modalPanel)
                DispatchQueue.global().async {
                    // Same delivery path as CreateDiskModel's worker progress and result.
                    DispatchQueue.main.async {
                        probe.delivered = true
                        app.stopModal(withCode: .OK)
                    }
                }
                let result = app.runModal(for: window)
                watchdog.invalidate()
                window.orderOut(nil)
                let ok = probe.delivered && result == .OK
                print(ok ? "first-run-modal: PASS (worker completion reached modal UI)"
                         : "first-run-modal: FAIL (main queue blocked during modal)")
                exit(ok ? 0 : 1)
            }
        }
        app.run()
    }
}
