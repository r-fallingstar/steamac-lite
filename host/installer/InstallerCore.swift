import Foundation

/// The installer accepts only numbered Lite releases and the exact ARM64 DMG from this repository.
/// No credentials, app settings or SteamOS disk path are needed.
enum InstallerCore {
    static let feedURL = URL(string: "https://api.github.com/repos/r-fallingstar/steamac-lite/releases?per_page=30")!
    static let releasesURL = URL(string: "https://github.com/r-fallingstar/steamac-lite/releases")!
    static let installerVersion = "1.0.1"

    struct Release {
        let version: String
        let numbers: [Int]
        let url: URL
        let sha256: String
        let size: Int64
    }
    enum Failure: Error { case release, network, destination, running, cancelled }

    static func version(_ input: String) -> [Int]? {
        let text = input.hasPrefix("v") ? String(input.dropFirst()) : input
        let parts = text.components(separatedBy: "-lite.")
        guard parts.count == 2 else { return nil }
        let values = parts[0].components(separatedBy: ".") + [parts[1]]
        guard values.count == 4 else { return nil }
        var numbers: [Int] = []
        for value in values {
            guard !value.isEmpty, value.count <= 9,
                  value.allSatisfy({ $0.isASCII && $0.isNumber }), let number = Int(value) else { return nil }
            numbers.append(number)
        }
        return numbers
    }

    static func compare(_ a: [Int], _ b: [Int]) -> ComparisonResult {
        for (x, y) in zip(a, b) where x != y { return x < y ? .orderedAscending : .orderedDescending }
        return .orderedSame
    }

    static func latest(_ data: Data) throws -> Release {
        guard let objects = (try? JSONSerialization.jsonObject(with: data)) as? [[String: Any]] else { throw Failure.release }
        let releases: [Release] = objects.compactMap { object in
            guard object["draft"] as? Bool != true,
                  let tag = object["tag_name"] as? String, let numbers = version(tag) else { return nil }
            let versionText = tag.hasPrefix("v") ? String(tag.dropFirst()) : tag
            let filename = "SteamAC-Lite-\(versionText)-macos-arm64.dmg"
            guard let assets = object["assets"] as? [[String: Any]],
                  let asset = assets.first(where: { $0["name"] as? String == filename }),
                  asset["state"] as? String == "uploaded",
                  let urlString = asset["browser_download_url"] as? String, let url = URL(string: urlString),
                  url.scheme == "https", url.host == "github.com", url.user == nil, url.password == nil,
                  url.port == nil, url.query == nil, url.fragment == nil,
                  url.path == "/r-fallingstar/steamac-lite/releases/download/\(tag)/\(filename)",
                  let digest = asset["digest"] as? String, digest.hasPrefix("sha256:") else { return nil }
            let hash = String(digest.dropFirst(7)).lowercased()
            let size = (asset["size"] as? NSNumber)?.int64Value ?? 0
            guard hash.count == 64, hash.allSatisfy({ $0.isASCII && $0.isHexDigit }), size > 0, size < 1024 * 1024 * 1024 else { return nil }
            return Release(version: versionText, numbers: numbers, url: url, sha256: hash, size: size)
        }
        guard let newest = releases.max(by: { compare($0.numbers, $1.numbers) == .orderedAscending }) else { throw Failure.release }
        return newest
    }

    static func defaultDestination() -> URL {
        let system = URL(fileURLWithPath: "/Applications", isDirectory: true)
        if FileManager.default.isWritableFile(atPath: system.path) { return system.appendingPathComponent("SteamAC Lite.app", isDirectory: true) }
        return FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Applications/SteamAC Lite.app", isDirectory: true)
    }

    /// Returns an installed version only after verifying its identity and signature.
    static func installedVersion(at app: URL) throws -> String? {
        guard FileManager.default.fileExists(atPath: app.path) else { return nil }
        guard let text = try UpdateInstallSupport.appInfo(app)["CFBundleShortVersionString"] as? String,
              version(text) != nil else { throw Failure.destination }
        do { try UpdateInstallSupport.validateApp(app, version: text) }
        catch { throw Failure.destination }
        return text
    }

    static func alreadyCurrent(_ app: URL, release: Release) throws -> String? {
        guard let installed = try installedVersion(at: app), let numbers = version(installed),
              compare(numbers, release.numbers) != .orderedAscending else { return nil }
        return installed
    }

    /// Installs only a verified app, using same-volume renames. A running app is never stopped.
    /// The stage/backup is retained if rollback itself fails, so the previous app is not lost.
    static func install(staged: URL, to target: URL, release: Release, isRunning: () -> Bool,
                        verify: (URL, String) throws -> Void = UpdateInstallSupport.validateApp) throws -> String {
        let fm = FileManager.default
        let directory = staged.deletingLastPathComponent()
        guard directory.deletingLastPathComponent() == target.deletingLastPathComponent(),
              directory.lastPathComponent.hasPrefix(".steamac-update-"),
              target.lastPathComponent == "SteamAC Lite.app",
              target.standardizedFileURL == target.resolvingSymlinksInPath(),
              fm.isWritableFile(atPath: target.deletingLastPathComponent().path) else { throw Failure.destination }
        if isRunning() { throw Failure.running }
        if let current = try alreadyCurrent(target, release: release) { return current }
        try verify(staged, release.version)
        let oldVersion = try installedVersion(at: target)
        let backup = directory.appendingPathComponent("previous.app", isDirectory: true)
        var moved = false
        var installedNew = false
        do {
            if oldVersion != nil { try fm.moveItem(at: target, to: backup); moved = true }
            try fm.moveItem(at: staged, to: target)
            installedNew = true
            try verify(target, release.version)
            if moved { try? fm.removeItem(at: backup) }
            return release.version
        } catch {
            if installedNew {
                try? fm.moveItem(at: target, to: directory.appendingPathComponent("failed.app"))
            }
            if moved, !fm.fileExists(atPath: target.path) { try? fm.moveItem(at: backup, to: target) }
            throw error
        }
    }
}
