import Foundation

enum PerformanceMode: String, CaseIterable, Identifiable {
    case automatic = "auto", lowMemory = "low-memory", manual
    var id: String { rawValue }
    static var defaultMode: PerformanceMode {
        if Bundle.main.object(forInfoDictionaryKey: "SteamacAdaptiveDefaults") as? Bool == true { return .automatic }
        if Bundle.main.object(forInfoDictionaryKey: "SteamacLowMemoryDefaults") as? Bool == true { return .lowMemory }
        return .manual
    }
    var title: String {
        switch self {
        case .automatic: return String(localized: "Automatic (this Mac)")
        case .lowMemory: return String(localized: "Low memory (8 GB)")
        case .manual: return String(localized: "Manual")
        }
    }
}

/// Conservative starting points, not benchmarks or automatic frame-rate tuning.
enum PerformanceProfile {
    struct Plan {
        let vmMiB: Int, cpus: Int, width: Int, height: Int
        let renderScale: Double
        let diskSwap: Bool

        var guestSize: (Int, Int) {
            WindowController.guestSize(points: CGSize(width: width, height: height), scale: renderScale)
        }

        func fitting(_ available: (Int, Int)?) -> Plan {
            guard let (w, h) = available else { return self }
            let ratio = min(1, Double(max(800, w)) / Double(width), Double(max(500, h)) / Double(height))
            return Plan(vmMiB: vmMiB, cpus: cpus,
                        width: max(800, Int(Double(width) * ratio) & ~1),
                        height: max(500, Int(Double(height) * ratio) & ~1),
                        renderScale: renderScale, diskSwap: diskSwap)
        }

        var description: String {
            String(localized: "\(vmMiB / 1024) GiB VM, \(cpus) vCPUs, \(String(guestSize.0)) × \(String(guestSize.1)), 60 Hz")
                + (diskSwap ? String(localized: ", 4 GiB guest swap") : "")
        }
    }

    static let displayKeys: Set<LauncherSettings.Key> = [.windowWidth, .windowHeight, .windowSizePreset,
                                                         .retinaResolution, .renderScale, .refreshRate]
    static let customKeys = displayKeys.union([.cpus, .memMiB, .wmtr, .wmtrLibrary, .graphicsPath])

    static func plan(host: VMSizing.Host, mode: PerformanceMode) -> Plan? {
        guard mode != .manual else { return nil }
        let mib = host.memBytes >> 20
        let cpus = VMSizing.autoCPUs(host)
        if mode == .lowMemory || mib <= 8192 {
            return Plan(vmMiB: 3072, cpus: min(4, cpus), width: 1280, height: 800,
                        renderScale: 0.75, diskSwap: true)
        }
        if mib <= 12288 {
            return Plan(vmMiB: 4096, cpus: cpus, width: 1280, height: 800, renderScale: 1, diskSwap: false)
        }
        if mib < 24576 {
            return Plan(vmMiB: 6144, cpus: cpus, width: 1440, height: 900, renderScale: 1, diskSwap: false)
        }
        if mib < 32768 {
            return Plan(vmMiB: 8192, cpus: cpus, width: 1600, height: 1000, renderScale: 1, diskSwap: false)
        }
        return Plan(vmMiB: mib < 49152 ? 12288 : 16384, cpus: cpus,
                    width: 1920, height: 1200, renderScale: 1, diskSwap: false)
    }

    static func selfCheck() -> [String] {
        var failures: [String] = []
        func check(_ ok: Bool, _ what: String) { if !ok { failures.append(what) } }
        func host(_ gb: UInt64, _ p: Int = 4) -> VMSizing.Host {
            .init(memBytes: gb << 30, perfCores: p, cores: p + 4)
        }
        let cases: [(UInt64, Int, Int, Int)] = [(8, 3072, 960, 600), (12, 4096, 1280, 800),
            (16, 6144, 1440, 900), (18, 6144, 1440, 900), (24, 8192, 1600, 1000),
            (32, 12288, 1920, 1200), (36, 12288, 1920, 1200), (48, 16384, 1920, 1200),
            (64, 16384, 1920, 1200), (128, 16384, 1920, 1200)]
        for (gb, memory, width, height) in cases {
            var o = Options()
            o.performanceMode = .automatic
            var overrides: [LauncherSettings.Key: String] = [:]
            o.applyPerformanceProfile(overrides: &overrides, host: host(gb), available: nil)
            check(o.memMiB == memory && o.guestSize == (width, height), "\(gb) GB profile")
            check(o.refreshRate == 60 && o.pixelScale == 1, "\(gb) GB display")
            check(o.lowMemory == (gb <= 8), "\(gb) GB swap")
            check(o.memSource == .profile && overrides.isEmpty, "\(gb) GB editable settings")
            check(VMSizing.gpuBudgetMiB(memMiB: memory, host: host(gb)) >= 2048, "\(gb) GB GPU headroom")
        }
        check(plan(host: host(32, 12), mode: .automatic)?.cpus == 8, "fast-core CPU cap")
        check(plan(host: host(32, 4), mode: .automatic)?.cpus == 4, "RAM does not add CPU cores")
        check(plan(host: host(64), mode: .lowMemory)!.guestSize == (960, 600), "forced low profile")
        let fitted = plan(host: host(32), mode: .automatic)!.fitting((1200, 750))
        check(fitted.guestSize == (1200, 750), "small screen fit")
        check(plan(host: host(8), mode: .automatic)!.fitting((2560, 1600)).guestSize == (960, 600),
              "large screen does not upscale an 8 GB default")
        do {
            var flags = try Options.parse(["steamac-vm", "--profile", "auto", "--mem", "2560",
                                           "--cpus", "2", "--display", "1024x640", "--render-scale", "1", "--refresh", "40"])
            var overrides: [LauncherSettings.Key: String] = [:]
            flags.applyPerformanceProfile(overrides: &overrides, host: host(32), available: nil)
            check(flags.memMiB == 2560 && flags.cpus == 2 && flags.refreshRate == 40 && flags.guestSize == (1024, 640),
                  "explicit CLI priority")
            var saved = Options()
            saved.performanceMode = .automatic
            saved.savedPerformanceKeys = customKeys
            saved.memSource = .settings; saved.cpusSource = .settings
            saved.memMiB = 5120; saved.cpus = 2
            saved.displayWidth = 1024; saved.displayHeight = 640; saved.renderScale = 0.5
            saved.refreshRate = 75; saved.pixelScale = 2; saved.wmtrLibrary = nil
            saved.applyPerformanceProfile(overrides: &overrides, host: host(32), available: nil)
            check(saved.memMiB == 5120 && saved.cpus == 2 && saved.refreshRate == 75 && saved.pixelScale == 2
                  && saved.guestSize == (1024, 640) && saved.wmtrLibrary == nil, "saved settings priority")
            check(try Options.parse(["steamac-vm", "--low-memory", "--no-low-memory"]).performanceMode == .manual,
                  "legacy opt-out")
            check(try Options.parse(["steamac-vm", "--no-low-memory", "--profile", "auto"]).performanceMode == .automatic,
                  "last mode flag wins")
        } catch { failures.append("parse: \(error)") }
        var manual = Options()
        manual.performanceMode = .manual
        manual.memMiB = 4096; manual.pixelScale = 2
        var overrides: [LauncherSettings.Key: String] = [:]
        manual.applyPerformanceProfile(overrides: &overrides, host: host(8), available: nil)
        check(manual.memMiB == 4096 && manual.pixelScale == 2 && !manual.lowMemory, "manual mode")
        let domain = "steamac.performance-test." + UUID().uuidString
        let defaults = UserDefaults(suiteName: domain)!
        defer { defaults.removePersistentDomain(forName: domain) }
        let settings = LauncherSettings(defaults: defaults)
        settings.performanceMode = .automatic
        check(PerformanceProfile.customKeys.allSatisfy { defaults.object(forKey: $0.rawValue) == nil },
              "automatic values must not become saved manual choices")
        settings.windowWidth = 1024; settings.windowHeight = 640; settings.windowSizePreset = "custom"
        settings.renderScale = 1; settings.refreshRate = 75; settings.memMiB = 5120; settings.cpus = 2
        var resolved = Options()
        _ = resolved.applySettings(LauncherSettings(defaults: defaults))
        resolved.applyPerformanceProfile(overrides: &overrides, host: host(32), available: nil)
        check(resolved.memMiB == 5120 && resolved.guestSize == (1024, 640) && resolved.refreshRate == 75,
              "saved UI settings survive reload and a different Mac")
        settings.noteBoot(overrides: [:], autoCapture: nil)
        settings.useRecommendedPerformance()
        check(settings.restartPending, "reset to recommended requires restart")
        check(PerformanceProfile.customKeys.allSatisfy { defaults.object(forKey: $0.rawValue) == nil },
              "reset to recommended removes manual choices")
        return failures
    }
}

extension Options {
    mutating func applyPerformanceProfile(overrides: inout [LauncherSettings.Key: String],
                                          host: VMSizing.Host = .current, available: (Int, Int)?) {
        guard let plan = PerformanceProfile.plan(host: host, mode: performanceMode)?.fitting(available) else {
            lowMemory = false
            return
        }
        lowMemory = plan.diskSwap
        if !explicit.contains("--mem") && memSource != .settings {
            memMiB = plan.vmMiB; memSource = .profile
        }
        if !explicit.contains("--cpus") && cpusSource != .settings {
            cpus = plan.cpus; cpusSource = .profile
        }
        if !savedPerformanceKeys.contains(.retinaResolution) { pixelScale = 1 }
        if !explicit.contains("--display") && savedPerformanceKeys.isDisjoint(with: [.windowWidth, .windowHeight, .windowSizePreset]) {
            displayWidth = plan.width; displayHeight = plan.height
        }
        if !explicit.contains("--render-scale") && !savedPerformanceKeys.contains(.renderScale) { renderScale = plan.renderScale }
        if !explicit.contains("--refresh") && !savedPerformanceKeys.contains(.refreshRate) { refreshRate = 60 }
        if !explicit.contains("--wmtr-lib") && !explicit.contains("--no-wmtr") && !explicit.contains("--graphics-path")
            && savedPerformanceKeys.isDisjoint(with: [.wmtr, .wmtrLibrary, .graphicsPath]) {
            wmtrLibrary = LauncherSettings.Wmtr.path(for: "")
        }
    }
}
