import Foundation

/// An experimental budget for 8 GiB unified-memory Macs, not a claim of game compatibility.
/// Swap belongs to the guest; GPU allocations still need real unified memory on the Mac.
enum LowMemoryProfile {
    static let vmMiB = 3072
    static let swapMiB = 4096

    static func selfCheck() -> [String] {
        var failures: [String] = []
        let host = VMSizing.Host(memBytes: 8 << 30, perfCores: 4, cores: 8)
        var defaults = Options()
        defaults.lowMemory = true
        defaults.pixelScale = 2
        defaults.memMiB = 6144 // stale saved values must not defeat the profile
        var overrides: [LauncherSettings.Key: String] = [:]
        defaults.applyLowMemoryProfile(overrides: &overrides, host: host)
        if defaults.memMiB != vmMiB { failures.append("VM budget") }
        if VMSizing.gpuBudgetMiB(memMiB: defaults.memMiB, host: host) != 2048 { failures.append("GPU headroom") }
        if defaults.guestSize != (960, 600) || defaults.refreshRate != 30 { failures.append("display budget") }
        if defaults.memSource != .profile { failures.append("settings source") }
        if overrides[.retinaResolution] == nil { failures.append("Retina override not shown") }
        do {
            var explicit = try Options.parse(["steamac-vm", "--low-memory", "--mem", "2560", "--refresh", "40",
                                              "--display", "1024x640", "--render-scale", "1"])
            explicit.applyLowMemoryProfile(overrides: &overrides, host: host)
            if explicit.memMiB != 2560 || explicit.refreshRate != 40 || explicit.guestSize != (1024, 640) {
                failures.append("explicit CLI values were overwritten")
            }
            if try Options.parse(["steamac-vm", "--low-memory", "--no-low-memory"]).lowMemory {
                failures.append("opt-out")
            }
        } catch { failures.append("parse: \(error)") }
        var off = Options()
        off.lowMemory = false
        off.memMiB = 4096
        off.pixelScale = 2
        off.applyLowMemoryProfile(overrides: &overrides, host: host)
        if off.memMiB != 4096 || off.pixelScale != 2 { failures.append("disabled profile changed options") }
        return failures
    }
}

extension Options {
    mutating func applyLowMemoryProfile(overrides: inout [LauncherSettings.Key: String],
                                       host: VMSizing.Host = .current) {
        guard lowMemory else { return }
        let why = "--low-memory (experimental 8 GB profile)"
        if !explicit.contains("--mem") {
            memMiB = LowMemoryProfile.vmMiB
            memSource = .profile
            overrides[.memMiB] = why
        }
        // Four performance cores keep Steam responsive; never add cores to an 8 GB Mac.
        if !explicit.contains("--cpus") {
            cpus = min(4, VMSizing.autoCPUs(host))
            cpusSource = .profile
            overrides[.cpus] = why
        }
        pixelScale = 1
        overrides[.retinaResolution] = why
        if !explicit.contains("--display") {
            displayWidth = 1280; displayHeight = 800
            overrides[.windowWidth] = why; overrides[.windowHeight] = why; overrides[.windowSizePreset] = why
        }
        if !explicit.contains("--render-scale") {
            renderScale = min(renderScale, 0.75)
            overrides[.renderScale] = why
        }
        if !explicit.contains("--refresh") {
            refreshRate = 30
            overrides[.refreshRate] = why
        }
        if !explicit.contains("--wmtr-lib") && !explicit.contains("--no-wmtr") && !explicit.contains("--graphics-path") {
            // resolve() checks the bundled executor and falls back to Vulkan when absent.
            wmtrLibrary = LauncherSettings.Wmtr.path(for: "")
            overrides[.wmtr] = why
        }
    }
}
