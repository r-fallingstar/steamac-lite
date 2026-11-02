import Foundation

enum FirstRunScheduling {
    /// Finish AppKit launch without holding a main-queue item across runModal.
    /// DiskCreator posts progress/completion to that queue; a nested modal loop
    /// cannot run them while its enclosing DispatchQueue.main block is active.
    static func schedule(_ body: @escaping @Sendable () -> Void) {
        RunLoop.main.perform(inModes: [.default], block: body)
    }
}
