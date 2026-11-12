import Foundation

struct RenderPixels: Equatable {
    let width: Int
    let height: Int
    var size: (Int, Int) { (width, height) }
    var id: String { "\(width)x\(height)" }
    var title: String { "\(width) × \(height) px" }
    static let automatic = "auto", custom = "custom"
    static let presets: [RenderPixels] = [(640,400),(800,500),(854,480),(960,540),(960,600),(1024,640),
        (1280,720),(1280,800),(1440,900),(1600,900),(1600,1000),(1920,1080),(1920,1200),
        (2560,1440),(2560,1600),(3840,2160)].map { RenderPixels(width: $0.0, height: $0.1) }
    static func normalized(width: Int, height: Int) -> Self {
        .init(width: min(4094, max(320, width)) & ~1, height: min(4094, max(200, height)) & ~1)
    }
    static func parse(_ text: String) -> Self? {
        let parts = text.lowercased().split(separator: "x", omittingEmptySubsequences: false)
        guard parts.count == 2, let width = Int(parts[0]), let height = Int(parts[1]),
              (320...4094).contains(width), (200...4094).contains(height), width % 2 == 0, height % 2 == 0 else { return nil }
        return .init(width: width, height: height)
    }
    static func selfCheck() -> [String] {
        var failures: [String] = []
        func check(_ value: Bool, _ message: String) { if !value { failures.append(message) } }
        check(parse("1280x720") == RenderPixels(width: 1280, height: 720), "pixel size parsing")
        for bad in ["0x0","319x200","320x199","4096x2160","1281x720","1280x","1x2x3"] {
            check(parse(bad) == nil, "invalid pixel size accepted: " + bad)
        }
        check(normalized(width: 99999, height: 1).size == (4094,200), "pixel bounds")
        let domain = "steamac.lite.render-pixels-test." + UUID().uuidString
        let defaults = UserDefaults(suiteName: domain)!; defer { defaults.removePersistentDomain(forName: domain) }
        let settings = LauncherSettings(defaults: defaults)
        settings.performanceMode = .manual; settings.windowWidth = 1280; settings.windowHeight = 800; settings.renderScale = 0.75
        var legacy = Options(); legacy.headless = true; _ = legacy.applySettings(settings)
        check(legacy.guestSize == (960,600), "legacy scale changed")
        settings.renderWidth = 1920; settings.renderHeight = 1080; settings.renderResolutionPreset = "1920x1080"
        var fixed = Options(); fixed.headless = true; _ = fixed.applySettings(LauncherSettings(defaults: defaults))
        check(fixed.guestSize == (1920,1080), "saved pixel dimensions not applied")
        fixed.displayWidth = 800; fixed.displayHeight = 500; fixed.pixelScale = 2; fixed.renderScale = 0.25
        check(fixed.guestSize == (1920,1080), "fixed pixels changed with window or Retina scale")
        do {
            var cli = try Options.parse(["steamac-vm","--render-size","1280x720","--headless"])
            _ = cli.applySettings(settings); check(cli.guestSize == (1280,720), "CLI pixel override")
            var scale = try Options.parse(["steamac-vm","--render-scale","0.5","--headless"])
            _ = scale.applySettings(settings); check(scale.renderPixels == nil && scale.guestSize == (640,400), "CLI scale override")
        } catch { failures.append("pixel CLI parse: \(error)") }
        settings.noteBoot(overrides: [:], autoCapture: nil)
        settings.useRecommendedPerformance()
        check(settings.renderResolutionPreset == automatic && settings.fixedRenderPixels == nil, "recommended profile retained fixed pixels")
        check(settings.restartPending, "render resolution change not tracked for restart")
        return failures
    }
}
