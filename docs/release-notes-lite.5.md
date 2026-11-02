# SteamAC Lite 1.9.4-lite.5

新しいSteamOSディスクでVRChat向け設定を検証し、初回セットアップを修正しました。

- ディスク作成時に進捗と完了が画面へ届かず、「起動中…」のままになる問題を修正しました。
- 新しいディスクでは、Steamも初回に選んだ言語で起動します。日本語のログイン画面を実機で確認しました。既存ディスクのSteamの言語は変更しません。
- ツールがない状態から、FEX・Proton Experimental・EACランタイムのダウンロードとVRChat向け設定の完了を確認しました。検証用ディスクを分け、検証前の利用環境は保持しました。
- Steamへのログインとインストール確認は本人の操作が必要です。VRChatは自動では起動しません。

**ダウンロード:** `SteamAC-Lite-1.9.4-lite.5-macos-arm64.dmg` を開き、SteamAC Lite.appをApplicationsへコピーしてください。「Source code」はアプリではありません。

[はじめての導入手順](https://github.com/r-fallingstar/steamac-lite/blob/main/docs/quick-start.ja.md) · [VRChat向け設定](https://github.com/r-fallingstar/steamac-lite/blob/main/docs/vrchat-setup.ja.md) · [検証結果と制限](https://github.com/r-fallingstar/steamac-lite/blob/main/docs/validation-lite.5.md)

Apple Silicon・macOS 15.5以降・RAM 8 GB以上向けの実験版です。ad-hoc署名で、Appleの公証は受けていません。SteamOSとゲームは別途ダウンロードします。M1・8 GBの新規ディスクで確認しており、この検証ではVRChatを起動していません。性能や互換性を保証するものではありません。

---

Fixes first-run disk creation progress/completion being blocked by a modal setup window. New SteamOS disks seed Steam's UI language from the launcher selection once; existing Steam settings are preserved. A fresh-disk test completed all FEX, x86_64 Proton Experimental and EAC downloads, then the automatic per-VRChat configuration. Steam sign-in, installation confirmations and onboarding remain manual. SSH remained off and no game was launched.
