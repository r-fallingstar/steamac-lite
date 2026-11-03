SteamAC Lite adds update notifications and in-app downloads from this fork's GitHub releases.

- New releases appear in the app at startup and during the six-hour background check. Numbered Lite experimental releases are included; drafts and other release channels are excluded.
- Choose **Update** to download and verify the DMG. **Install and Relaunch** waits for SteamOS and the launcher to finish before replacing the app.
- The SteamOS disk, installed games and settings are kept. A failed replacement or relaunch restores the previous app.
- Downloads must match the release's exact ARM64 filename, GitHub SHA-256 and size. The app's signature, bundle identity and version are checked before installation.
- Settings include an automatic-check switch. Manual checks, skipping a version and postponing are available.
- New UI text supports English, Japanese, Korean, Simplified Chinese and Russian.

**Lite.8 and older need one manual upgrade to Lite.9 first.** Those versions do not contain the updater. Future releases with newer version numbers can then be installed from the app. Editing the notes or replacing an asset on the same tag does not trigger an update.

This is still an experimental, ad-hoc signed build without Apple notarization. It is not an official Valve or VRChat product. No new VRChat or FPS compatibility claim is made in this release.

Validation: numeric Lite version ordering, release filtering, all-language catalog checks, real DMG staging and signature verification, checksum and size rejection, seven helper tests including a real relaunch and rollback after a simulated relaunch failure. Tests used disposable apps and started no VM or game.

---

GitHub Releaseの新しい版をアプリ内で知らせ、ダウンロード・更新できるようにしました。

「アップデート」でダウンロードと検証を行い、「更新して開き直す」で反映します。実行中のSteamOSが終了してからアプリだけを入れ替えます。SteamOSのディスク・ゲーム・設定は引き継ぎます。

**Lite.8以前は最初の1回だけ、このReleaseのDMGで手動更新してください。** 以降は新しい版番号のReleaseをアプリから更新できます。

設定で自動確認をオフにできます。文言はGemini 3.8 Flash Highで校閲し、韓国語を本体UIの表記に合わせて修正しました。
