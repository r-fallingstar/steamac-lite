# SteamAC Lite 1.9.4-lite.4

初回セットアップに **VRChat向け設定** を追加しました。

- 対応するFEXを同梱。初回のコンパイルやSSH設定は不要です。
- Steamへのログイン後、必要なツールの準備を進め、VRChatだけにProton ExperimentalとEAC用の起動オプションを設定します。
- Steamにインストール確認が出た場合は本人が操作します。設定時にSteamを一度再起動します。VRChatは自動では起動しません。
- 既存の独自設定は確認せずに置き換えず、変更前のファイルを保存します。中断後は再試行できます。
- Gemini 3.8 Flashで日本語UIを校閲し、製品名・容量不足の説明・エラー文・用語の不統一を修正しました。

**ダウンロード:** `SteamAC-Lite-1.9.4-lite.4-macos-arm64.dmg` を開き、SteamAC Lite.appをApplicationsへコピーしてください。「Source code」はアプリではありません。

[はじめての導入手順](https://github.com/r-fallingstar/steamac-lite/blob/main/docs/quick-start.ja.md) · [VRChat向け設定の流れ](https://github.com/r-fallingstar/steamac-lite/blob/main/docs/vrchat-setup.ja.md)

Apple Silicon・macOS 15.5以降・RAM 8 GB以上向けの実験版です。ad-hoc署名で、Appleの公証は受けていません。SteamOSとゲームは別途ダウンロードします。M1・8 GBのテスト用ディスクで追加設定を確認しましたが、この検証ではVRChat自体を起動していません。ツール未導入の新規アカウントでの全ダウンロード過程は未確認です。性能や互換性を保証するものではありません。

---

Adds optional first-run **VRChat setup** with a bundled, pinned FEX runtime, Steam tool installation prompts, per-VRChat Proton Experimental/EAC launch options, original-file backups and resume. Steam sign-in and normal installation confirmations remain user actions. Steam restarts once; no game is launched. Japanese wording was reviewed with Gemini 3.8 Flash and checked against the implementation. Existing Mac-specific profiles, Japanese input, US/JIS detection and 60 Hz defaults are retained.
