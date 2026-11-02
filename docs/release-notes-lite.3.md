# SteamAC Lite 1.9.4-lite.3（実験版）

**[Mac用アプリをダウンロード（DMG）](https://github.com/r-fallingstar/steamac-lite/releases/download/v1.9.4-lite.3/SteamAC-Lite-1.9.4-lite.3-macos-arm64.dmg)**

M1以降のApple Silicon Mac用です。DMGを開いて **SteamAC Lite.appをApplicationsへコピー**してください。「Source code」ではなく上のDMGを選びます。自分でビルドする必要はありません。

## はじめて使う場合

1. アプリを開き、最初の画面で **日本語**などの表示言語を選びます。
2. **新しいディスクを作成…**でSteamOSをセットアップし、自分のSteamアカウントへログインします。
3. ゲームをインストールします。既存のSteamOSディスクを持っている場合は、そのコピーを指定することもできます。

**[日本語の導入ガイド](https://github.com/r-fallingstar/steamac-lite/blob/main/docs/quick-start.ja.md)**を用意しています。DMG内と、このReleaseの`Quick-Start-ja.txt`にも同じ案内を同梱しています。

## 追加した機能

- **初回の言語選択と日本語表示**：設定、メニュー、説明文、ディスク作成などの案内を日本語化。あとから「設定… > 一般 > 表示言語」で変更できます。
- **Macに合う自動設定**：8 GBは960×600・VM 3 GiB、16/18 GBは1440×900・6 GiB、24 GBは1600×1000・8 GiB、32 GB以上は1920×1200を目安に、画面へ収まる大きさに調整します。32/36 GBのVMは12 GiB、48 GB以上は16 GiBです。手動設定を優先します。
- **日本語入力とUS/JIS判別**：物理キーボードを起動時に判別。Anthyでローマ字・漢字変換、Control＋Space、JISのかな・英数に対応します。
- **60 Hzと8 GB向けスワップ**：画面更新は既定60 Hz。8 GB向けにはゲスト用スワップ4 GiBを追加します。

## 対応環境と確認範囲

Apple Silicon、RAM 8 GB以上、macOS 15.5以降向けです。実機確認はM1・8 GiB・macOS 27.2です。大容量Macの自動設定は模擬テストで確認しており、各機種のゲーム性能を測定した値ではありません。60 Hzはゲーム内60 fpsの保証ではありません。

この実験版はad-hoc署名でApple未公証です。初回に開発元に関する表示が出る場合は、導入ガイドからAppleの案内を参照してください。ダウンロードの確認用に`SHA256SUMS.txt`を添付しています。

アプリ本体だけを配布します。SteamOSディスク・ゲーム・アカウント情報は同梱しません。**VRChatにはProton Experimental、Proton EasyAntiCheat Runtime、対応FEX、起動オプションの手動設定が別途必要**です。既存環境でVRChatが動作したユーザー報告はありますが、新規導入時にこれらの準備が自動で終わる版ではありません。

StonkGuy/steamac v1.9.4-eac.1を基に、未変更の同梱コンポーネントを再利用し、ランチャー・ゲスト設定を変更したビルドです。ライセンスをアプリ内に保持し、ソースと配布物の検証情報を公開しています。
