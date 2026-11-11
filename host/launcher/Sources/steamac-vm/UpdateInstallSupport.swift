import Foundation
import CryptoKit

/// Shared by the app and its detached replacement helper. No VM disk or preferences are touched.
enum UpdateInstallSupport {
    static let bundleID = "local.ryuu.steamac-lite"

    static func run(_ executable: String, _ arguments: [String]) throws -> Data {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = arguments
        let output = Pipe()
        process.standardOutput = output
        // Avoid an undrained stderr pipe blocking disk-image tools.
        process.standardError = FileHandle.nullDevice
        try process.run()
        let data = output.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else { throw Failure.command }
        return data
    }

    static func sha256(_ file: URL) throws -> String {
        let stream = try FileHandle(forReadingFrom: file)
        defer { try? stream.close() }
        var hash = SHA256()
        while let chunk = try stream.read(upToCount: 1024 * 1024), !chunk.isEmpty { hash.update(data: chunk) }
        return hash.finalize().map { String(format: "%02x", $0) }.joined()
    }

    static func validateApp(_ app: URL, version: String) throws {
        let info = try appInfo(app)
        guard app.pathExtension == "app", app.resolvingSymlinksInPath() == app.standardizedFileURL,
              info["CFBundleIdentifier"] as? String == bundleID,
              info["CFBundleShortVersionString"] as? String == version,
              info["SteamacLiteBuild"] as? Bool == true,
              info["CFBundleExecutable"] as? String == "steamac-vm",
              FileManager.default.isExecutableFile(atPath: app.appendingPathComponent("Contents/MacOS/steamac-vm").path) else { throw Failure.identity }
        _ = try run("/usr/bin/codesign", ["--verify", "--deep", "--strict", app.path])
    }

    static func prepare(_ image: URL, version: String, size: Int64, destination: URL) throws -> URL {
        let fm = FileManager.default
        let directory = destination.deletingLastPathComponent().appendingPathComponent(".steamac-update-" + UUID().uuidString, isDirectory: true)
        try fm.createDirectory(at: directory, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
        try JSONEncoder().encode(StageOwner(destination: destination.standardizedFileURL.path, processID: getpid()))
            .write(to: directory.appendingPathComponent("owner.json"), options: .atomic)
        var success = false
        defer { if !success { try? fm.removeItem(at: directory) } }
        let available = try directory.resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey]).volumeAvailableCapacityForImportantUsage ?? 0
        guard available >= max(512 * 1024 * 1024, size * 8) else { throw UpdateInstallSupport.Failure.space }
        let mount = directory.appendingPathComponent("mounted", isDirectory: true)
        try fm.createDirectory(at: mount, withIntermediateDirectories: false)
        let diskImage = directory.appendingPathComponent("update.dmg")
        try fm.moveItem(at: image, to: diskImage)
        _ = try UpdateInstallSupport.run("/usr/bin/hdiutil", ["attach", "-readonly", "-nobrowse", "-noautoopen", "-mountpoint", mount.path, diskImage.path])
        var mounted = true
        defer { if mounted { _ = try? UpdateInstallSupport.run("/usr/bin/hdiutil", ["detach", mount.path]) } }
        let source = mount.appendingPathComponent("SteamAC Lite.app", isDirectory: true)
        try UpdateInstallSupport.validateApp(source, version: version)
        let staged = directory.appendingPathComponent("SteamAC Lite.app", isDirectory: true)
        _ = try UpdateInstallSupport.run("/usr/bin/ditto", [source.path, staged.path])
        try UpdateInstallSupport.validateApp(staged, version: version)
        _ = try UpdateInstallSupport.run("/usr/bin/hdiutil", ["detach", mount.path])
        mounted = false
        try fm.removeItem(at: mount)
        try fm.removeItem(at: diskImage)
        success = true
        return staged
    }

    static func verifyArchive(_ file: URL, digest: String, size: Int64) throws {
        let actual = (try FileManager.default.attributesOfItem(atPath: file.path)[.size] as? NSNumber)?.int64Value
        guard actual == size else { throw Failure.size }
        guard try sha256(file) == digest else { throw Failure.checksum }
    }

    struct StageOwner: Codable { let destination: String; let processID: Int32 }

    static func cleanAbandonedStages(beside app: URL) {
        let fm = FileManager.default
        let parent = app.deletingLastPathComponent()
        guard let entries = try? fm.contentsOfDirectory(at: parent, includingPropertiesForKeys: [.isSymbolicLinkKey]) else { return }
        for directory in entries {
            let prefix = ".steamac-update-"
            guard directory.lastPathComponent.hasPrefix(prefix),
                  UUID(uuidString: String(directory.lastPathComponent.dropFirst(prefix.count))) != nil,
                  (try? directory.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink) != true,
                  (try? fm.attributesOfItem(atPath: directory.path)[.ownerAccountID] as? NSNumber)?.uint32Value == getuid(),
                  let data = try? Data(contentsOf: directory.appendingPathComponent("owner.json")), data.count < 4096,
                  let owner = try? JSONDecoder().decode(StageOwner.self, from: data),
                  owner.destination == app.standardizedFileURL.path, owner.processID > 1,
                  !fm.fileExists(atPath: directory.appendingPathComponent("previous.app").path),
                  kill(owner.processID, 0) == -1, errno == ESRCH else { continue }
            try? fm.removeItem(at: directory)
        }
    }

    static func appInfo(_ app: URL) throws -> [String: Any] {
        let info = app.appendingPathComponent("Contents/Info.plist")
        guard (try info.resourceValues(forKeys: [.isSymbolicLinkKey])).isSymbolicLink != true,
              let value = try PropertyListSerialization.propertyList(from: Data(contentsOf: info), format: nil) as? [String: Any] else { throw Failure.identity }
        return value
    }

    /// Reject disk-image and App Translocation launches; updates never request administrator access.
    static func validateDestination(_ app: URL) throws {
        let path = app.standardizedFileURL.path
        guard app.pathExtension == "app", !path.hasPrefix("/Volumes/"), !path.contains("/AppTranslocation/"),
              app.resolvingSymlinksInPath() == app.standardizedFileURL,
              FileManager.default.isWritableFile(atPath: app.path),
              FileManager.default.isWritableFile(atPath: app.deletingLastPathComponent().path),
              (try appInfo(app))["CFBundleIdentifier"] as? String == bundleID else { throw Failure.destination }
    }

    enum Failure: Error { case command, identity, destination, checksum, size, response, space }
}

struct UpdateInstallPlan: Codable {
    let destination: String
    let stagedApp: String
    let previousVersion: String
    let version: String
    let processIDs: [Int32]
    let failureTitle: String
    let failureMessage: String
    let releasesLabel: String
    let closeLabel: String
}
