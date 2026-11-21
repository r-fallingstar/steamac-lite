import AppKit
import Combine
import Foundation

/// Minimum seconds between a DXMT game's presents, read by libwmtr_host on every present
/// (`present_floor` in wmtr_host.m; 0 = no cap). An aligned 64-bit load/store is single-copy atomic
/// on arm64, so the executor threads read it without a lock.
nonisolated(unsafe) private var gamePresentInterval: Double = 0

@_cdecl("steamac_game_present_interval")
public func steamacGamePresentInterval() -> Double { gamePresentInterval }

/// Frame caps for DXMT games, applied on the host by pacing the game layer's presents
/// (Metal's presentDrawable:afterMinimumDuration:): the game waits for its next drawable instead of
/// rendering frames that are never shown. Nothing in the guest, Proton or the game changes, so EAC,
/// network and audio keep running; a change applies at the next present.
///
/// - Settings > Display "Game frame rate limit" (`gameFrameLimit`, 0 = off).
/// - Settings > General "Lower the game's frame rate" while steamac Lite is in the background
///   (`backgroundFrameLimit`, 0 = off): applies while another app is active; while the window is
///   fully covered or minimized nothing is visible and the cap drops to `hiddenFPS`.
///
/// Not applied with a VR link (the headset's pacing is the VR exporter's) nor on the Vulkan path.
final class GameFrameCap {
    /// Whole fractions of 60 and 120 Hz only: Metal shows a paced drawable on the next refresh, so
    /// on a 60 Hz panel a 45 fps cap (22.2 ms) ran at 30 fps (M1, VRChat, 2026-11-21).
    static let gameChoices = [0, 30, 60]
    static let backgroundChoices = [0, 30, 15]
    static let hiddenFPS = 10

    private weak var window: NSWindow?
    private var appActive = NSApp.isActive
    private var gameLimit: Int
    private var backgroundLimit: Int
    private var observers: [NSObjectProtocol] = []
    private var subscriptions: [AnyCancellable] = []
    private var lastLogged: Int?

    init(settings: LauncherSettings, window: NSWindow) {
        self.window = window
        gameLimit = settings.gameFrameLimit
        backgroundLimit = settings.backgroundFrameLimit
        let nc = NotificationCenter.default
        let changed: (Notification) -> Void = { [weak self] n in
            if n.name == NSApplication.didResignActiveNotification { self?.appActive = false }
            if n.name == NSApplication.didBecomeActiveNotification { self?.appActive = true }
            self?.update()
        }
        observers = [
            nc.addObserver(forName: NSApplication.didResignActiveNotification, object: nil, queue: .main, using: changed),
            nc.addObserver(forName: NSApplication.didBecomeActiveNotification, object: nil, queue: .main, using: changed),
            nc.addObserver(forName: NSWindow.didChangeOcclusionStateNotification, object: window, queue: .main, using: changed),
            nc.addObserver(forName: NSWindow.didMiniaturizeNotification, object: window, queue: .main, using: changed),
            nc.addObserver(forName: NSWindow.didDeminiaturizeNotification, object: window, queue: .main, using: changed),
        ]
        // @Published emits the new value before it is stored: use the emitted value.
        subscriptions = [
            settings.$gameFrameLimit.dropFirst().removeDuplicates().sink { [weak self] v in self?.gameLimit = v; self?.update() },
            settings.$backgroundFrameLimit.dropFirst().removeDuplicates().sink { [weak self] v in self?.backgroundLimit = v; self?.update() },
        ]
        update()
    }

    deinit {
        for o in observers { NotificationCenter.default.removeObserver(o) }
        gamePresentInterval = 0
    }

    /// Frames per second in effect (0 = no cap).
    static func effectiveFPS(game: Int, background: Int, appActive: Bool, hidden: Bool) -> Int {
        var caps = [game].filter { $0 > 0 }
        if background > 0 && !appActive { caps.append(background) }
        if background > 0 && hidden { caps.append(hiddenFPS) }
        return caps.min() ?? 0
    }

    private func update() {
        let hidden = window.map { $0.isMiniaturized || !$0.occlusionState.contains(.visible) } ?? false
        let fps = Self.effectiveFPS(game: gameLimit, background: backgroundLimit, appActive: appActive, hidden: hidden)
        gamePresentInterval = fps > 0 ? 1 / Double(fps) : 0
        guard fps != lastLogged else { return }
        lastLogged = fps
        log("frame cap: \(fps > 0 ? "\(fps) fps" : "off") (setting \(gameLimit), background \(backgroundLimit), "
            + "active \(appActive), hidden \(hidden))")
    }

    static func selfTest() -> [String] {
        var failures: [String] = []
        let cases: [(Int, Int, Bool, Bool, Int)] = [
            (0, 0, true, false, 0), (0, 0, false, true, 0), (60, 0, false, true, 60),
            (0, 30, true, false, 0), (0, 30, false, false, 30), (45, 30, false, false, 30),
            (30, 30, true, true, 10), (0, 15, false, true, 10), (60, 15, true, false, 60),
        ]
        for (g, b, a, h, want) in cases where effectiveFPS(game: g, background: b, appActive: a, hidden: h) != want {
            failures.append("frame cap: game \(g) background \(b) active \(a) hidden \(h) != \(want)")
        }
        return failures
    }
}
