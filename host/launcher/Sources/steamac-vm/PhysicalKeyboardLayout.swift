import Carbon.HIToolbox

/// Physical geometry, independent of the currently selected macOS input method.
enum KeyboardLayout: String {
    case us, jis, iso

    static func fromCarbon(_ type: OSType) -> KeyboardLayout {
        if type == OSType(kKeyboardJIS) { return .jis }
        if type == OSType(kKeyboardISO) { return .iso }
        return .us
    }

    static var detected: KeyboardLayout {
        fromCarbon(OSType(KBGetLayoutType(Int16(LMGetKbdType()))))
    }

    static func selfCheck() -> [String] {
        var failures = MacInputSource.selfCheck()
        for (carbon, want) in [(kKeyboardJIS, KeyboardLayout.jis), (kKeyboardANSI, .us), (kKeyboardISO, .iso)] {
            if fromCarbon(OSType(carbon)) != want { failures.append("Carbon geometry \(want)") }
        }
        for layout in [KeyboardLayout.us, .jis, .iso] {
            if Keymap.linuxKey(UInt16(kVK_JIS_Eisu), layout: layout) != KEY.MUHENKAN { failures.append("Eisu") }
            if Keymap.linuxKey(UInt16(kVK_JIS_Kana), layout: layout) != KEY.HIRAGANA { failures.append("Kana") }
            if Keymap.linuxKey(UInt16(kVK_ANSI_Grave), layout: layout) != (layout == .iso ? KEY._102ND : KEY.GRAVE) {
                failures.append("grave position \(layout)")
            }
        }
        for code in [KEY.MUHENKAN, KEY.HIRAGANA, KEY.YEN, KEY.RO] where !Keymap.allCodes.contains(code) {
            failures.append("unadvertised JIS key \(code)")
        }
        do {
            let manual = try Options.parse(["steamac-vm", "--keyboard-layout", "us"])
            if manual.keyboardLayout != .us { failures.append("manual override") }
            let auto = try Options.parse(["steamac-vm", "--keyboard-layout", "auto"])
            if auto.keyboardLayout != nil { failures.append("auto override") }
        } catch { failures.append("parse: \(error)") }
        return failures
    }
}
