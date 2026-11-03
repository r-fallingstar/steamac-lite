import AppKit
import Darwin
import Foundation

enum ApplicationLanguage: String, CaseIterable, Identifiable {
    case system, japanese = "ja", english = "en", korean = "ko", russian = "ru", chinese = "zh-Hans"
    var id: String { rawValue }
    var title: String {
        switch self {
        case .system: return String(localized: "Follow system language")
        case .japanese: return "日本語"
        case .english: return "English"
        case .korean: return "한국어"
        case .russian: return "Русский"
        case .chinese: return "简体中文"
        }
    }

    static func preferred(_ languages: [String]) -> ApplicationLanguage {
        for language in languages {
            if language.hasPrefix("ja") { return .japanese }
            if language.hasPrefix("en") { return .english }
            if language.hasPrefix("ko") { return .korean }
            if language.hasPrefix("ru") { return .russian }
            if language.hasPrefix("zh") { return .chinese }
        }
        return .english
    }

    func save(into defaults: UserDefaults) {
        defaults.set(rawValue, forKey: LauncherSettings.Key.applicationLanguage.rawValue)
        if self == .system { defaults.removeObject(forKey: "AppleLanguages") }
        else { defaults.set([rawValue], forKey: "AppleLanguages") }
        defaults.synchronize()
    }

    /// Only normal interactive app starts. Utilities and test VMs never open this dialog.
    @MainActor
    static func chooseOnFirstLaunch(_ argv: [String]) {
        guard AppBundle.resources != nil, !Supervisor.isChild,
              !argv.dropFirst().contains(where: {
                  $0.hasPrefix("--selftest") || $0 == "--preview-update" || $0 == "--headless" || $0 == "--ssh-password"
                      || $0 == "--create-disk" || $0 == "--grow-disk" || $0 == "--help" || $0 == "-h"
              }) else { return }
        let domain = LauncherSettings.domain
        let defaults = domain == Bundle.main.bundleIdentifier ? UserDefaults.standard : UserDefaults(suiteName: domain)!
        guard defaults.string(forKey: LauncherSettings.Key.applicationLanguage.rawValue) == nil else { return }
        let app = NSApplication.shared
        app.setActivationPolicy(.regular)
        let alert = NSAlert()
        // This dialog precedes localization; native language names remain readable in any locale.
        alert.messageText = "表示言語を選択 / Choose a language"
        alert.informativeText = "あとから設定で変更できます。 / You can change this later in Settings."
        let languages = ApplicationLanguage.allCases.filter { $0 != .system }
        let menu = NSPopUpButton(frame: NSRect(x: 0, y: 0, width: 320, height: 28))
        menu.addItems(withTitles: languages.map(\.title))
        menu.selectItem(at: languages.firstIndex(of: preferred(Locale.preferredLanguages)) ?? 0)
        menu.setAccessibilityLabel("Language / 言語")
        alert.accessoryView = menu
        alert.addButton(withTitle: "続ける / Continue")
        alert.addButton(withTitle: "終了 / Quit")
        DispatchQueue.main.async {
            app.activate()
            guard alert.runModal() == .alertFirstButtonReturn else { exit(0) }
            languages[menu.indexOfSelectedItem].save(into: defaults)
            // Foundation caches localization. Start a fresh instance through Launch Services,
            // rather than exec() after AppKit registration, so Dock/Accessibility remain valid.
            let configuration = NSWorkspace.OpenConfiguration()
            configuration.createsNewApplicationInstance = true
            configuration.activates = true
            configuration.arguments = Array(argv.dropFirst())
            configuration.environment = ProcessInfo.processInfo.environment
            NSWorkspace.shared.openApplication(at: Bundle.main.bundleURL, configuration: configuration) { _, error in
                if let error { FileHandle.standardError.write(("Language restart: " + error.localizedDescription + "\n").data(using: .utf8)!) }
                exit(error == nil ? 0 : 1)
            }
        }
        // Finish the normal AppKit launch before presenting a modal window. Besides activation,
        // this makes the initial language controls available to accessibility clients.
        app.run()
        exit(0)
    }

    static func selfCheck() -> [String] {
        var failures: [String] = []
        if preferred(["ja-JP"]) != .japanese || preferred(["en-GB"]) != .english
            || preferred(["ko-KR"]) != .korean || preferred(["zh-TW"]) != .chinese || preferred(["de-DE"]) != .english {
            failures.append("preferred language")
        }
        let domain = "steamac.language-test." + UUID().uuidString
        let defaults = UserDefaults(suiteName: domain)!
        defer { defaults.removePersistentDomain(forName: domain) }
        ApplicationLanguage.japanese.save(into: defaults)
        if defaults.stringArray(forKey: "AppleLanguages") != ["ja"] { failures.append("language persistence") }
        ApplicationLanguage.system.save(into: defaults)
        if defaults.persistentDomain(forName: domain)?["AppleLanguages"] != nil { failures.append("system language reset") }
        if Bundle.main.path(forResource: "Localizable", ofType: "strings", inDirectory: nil, forLocalization: "ja") == nil {
            failures.append("Japanese catalog missing")
        }
        if let path = Bundle.main.path(forResource: "ja", ofType: "lproj"), let japanese = Bundle(path: path) {
            for (key, expected) in [("Settings…", "設定…"), ("Display", "画面"), ("General", "一般"),
                                    ("Use recommended settings", "推奨設定に戻す")] {
                if japanese.localizedString(forKey: key, value: nil, table: nil) != expected {
                    failures.append("Japanese lookup: " + key)
                }
            }
        }
        if let path = Bundle.main.path(forResource: "ko", ofType: "lproj"), let korean = Bundle(path: path) {
            for key in ["Settings…", "Display", "General", "VRChat setup"] {
                if korean.localizedString(forKey: key, value: nil, table: nil) == key {
                    failures.append("Korean lookup: " + key)
                }
            }
        } else {
            failures.append("Korean catalog missing")
        }
        return failures
    }
}
