# Japanese, Chinese and Korean input

Lite.7 includes Korean app menus, settings and dialogs, alongside English, Japanese, Simplified Chinese and Russian. Choose a language on first launch, or use Settings… → General → Display language. A display-language change applies after reopening the app. New SteamOS disks also start Steam in that language; existing Steam settings are retained.

The first input setup enables the engines already present in SteamOS:

| Input | Engine | Switch between Latin and native input |
|---|---|---|
| Japanese | IBus Anthy, romaji | Control+Space; JIS Kana/Eisu also work |
| Chinese | IBus Pinyin, Simplified Chinese | Shift |
| Korean | IBus Hangul, 2-set | Control+Space |

Use Control+. to change input methods. The initial method follows the app's display language: Chinese selects Pinyin, Korean selects Hangul, and other languages retain the Japanese input default. Each engine starts in Latin mode. For Chinese, type pinyin and select a candidate with Space. Korean composes Hangul from the 2-set key positions. Return confirms text.

No input-engine or font download is required. Conversion runs inside SteamOS, using its existing IBus engines and CJK fonts. It does not forward converted text from the Mac's input method. Physical US/JIS detection remains independent of the display and input languages.

The update adds missing engines to existing input lists. Subsequent starts keep edits to input order and shortcuts. First-setup settings are recorded in `~/.config/steamac/cjk-input-v1.json`, alongside the existing Japanese setup record. Changing the app language later does not reset an existing input configuration.

The integration checks use dedicated input contexts and inspect the Steam and game Xwayland servers. Game-specific text fields and nested Desktop Mode can behave differently. VRChat chat input is not covered by these automated checks.
