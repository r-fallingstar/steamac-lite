import Carbon.HIToolbox
import Foundation

/// The first guest input method follows the selected Mac input source, never the UI language
/// or the keyboard's US/JIS geometry. Unsupported methods safely start with Latin input.
enum MacInputSource: String {
    case latin, japanese = "ja", chinese = "zh-Hans", korean = "ko"

    static func classify(id: String, languages: [String], asciiCapable: Bool) -> MacInputSource {
        let source = id.lowercased()
        // These identifiers come from Apple's shipped input-method manifests. Do not map
        // every Chinese/Korean source to Pinyin/2-set: Wubi, Zhuyin and 3-set differ.
        if source == "com.apple.inputmethod.scim.itabc" { return .chinese }
        if source == "com.apple.inputmethod.korean.2setkorean" { return .korean }
        if source.hasPrefix("com.apple.inputmethod.scim.")
            || source.hasPrefix("com.apple.inputmethod.tcim.")
            || source.hasPrefix("com.apple.inputmethod.korean.")
            || source.contains("kanatyping") { return .latin }
        if asciiCapable { return .latin }
        let language = languages.first?.lowercased() ?? ""
        if language == "ja" || language.hasPrefix("ja-") { return .japanese }
        if (language == "zh-hans" || language == "zh-cn" || language.hasPrefix("zh-hans-"))
            && source.contains("pinyin") { return .chinese }
        if (language == "ko" || language.hasPrefix("ko-"))
            && (source.contains("2set") || source.contains("dubeol")) { return .korean }
        return .latin
    }

    static var detected: MacInputSource {
        guard let current = TISCopyCurrentKeyboardInputSource() else { return .latin }
        let source = current.takeRetainedValue()
        func property(_ key: CFString) -> AnyObject? {
            guard let pointer = TISGetInputSourceProperty(source, key) else { return nil }
            return Unmanaged<AnyObject>.fromOpaque(pointer).takeUnretainedValue()
        }
        return classify(id: property(kTISPropertyInputSourceID) as? String ?? "",
                        languages: property(kTISPropertyInputSourceLanguages) as? [String] ?? [],
                        asciiCapable: property(kTISPropertyInputSourceIsASCIICapable) as? Bool ?? false)
    }

    static func selfCheck() -> [String] {
        let cases: [(String, [String], Bool, MacInputSource)] = [
            ("com.apple.keylayout.ABC", ["en"], true, .latin),
            ("com.apple.keylayout.US", ["en"], true, .latin),
            ("com.apple.inputmethod.Kotoeri.RomajiTyping.Roman", ["en"], true, .latin),
            ("com.apple.inputmethod.Kotoeri.RomajiTyping.Japanese", ["ja"], false, .japanese),
            ("third.party.japanese", ["ja-JP"], false, .japanese),
            ("com.apple.inputmethod.SCIM.ITABC", ["zh-Hans"], false, .chinese),
            ("third.party.pinyin", ["zh-CN"], false, .chinese),
            ("com.apple.inputmethod.Korean.2SetKorean", ["ko"], false, .korean),
            ("com.apple.inputmethod.Korean.3SetKorean", ["ko"], false, .latin),
            ("com.apple.inputmethod.SCIM.WBX", ["zh-Hans"], false, .latin),
            ("com.apple.inputmethod.TCIM.Zhuyin", ["zh-Hant"], false, .latin),
            ("unknown", ["ru"], false, .latin),
            ("", [], false, .latin),
        ]
        return cases.compactMap { id, languages, ascii, expected in
            classify(id: id, languages: languages, asciiCapable: ascii) == expected
                ? nil : "Mac input source: \(id)"
        }
    }
}
