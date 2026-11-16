# steamac Lite v1.9.8-lite.6

## 日本語

DXMTのゲーム画面がウインドウ全体を覆っている間、背後のSteamOS画面の描画・GPU転送を省き、ランチャーのCPU負荷を減らしました。ゲーム画面を閉じたときは、蓄積した変更を反映して最新のSteamOS画面を表示します。部分更新の転送範囲も改善しました。

カメラの自動使用が有効で、macOSのカメラ権限がまだ未確定の場合は、SteamOS起動前に権限の案内を表示します。設定で後から有効にした場合も、ゲームから最初に要求されたときに一度だけ確認します。許可しただけでは撮影を開始せず、ゲームで使用中または手動プレビュー中のみ起動します。

開発時にM1・8GBのMacと検証用のディスクコピーで、VRChatへの入室、ゲームからの要求によるカメラ起動、カメラトラッキングをオフにした状態でのYamaPlayerの動画再生を確認しています。同じ検証では、ゲーム中のランチャーのメインスレッドCPU使用率が約1%から0.1〜0.2%になりました。これはランチャーの測定値で、ゲーム全体のCPU使用率やFPSの改善を保証するものではありません。

既存のSteamOSディスク・ゲーム・設定は引き継ぎます。アプリ内の「アップデートを確認…」、またはDMGの「インストールして開く」で更新できます。BOOTHのネットインストーラーも最新版を取得します。

M3でウインドウが表示される前に起動が停止するという報告は引き続き調査中です。今回の軽量化で解消したと確認できたものではありません。

## English

While an opaque DXMT game layer fills the window, the launcher skips rendering and uploading the hidden SteamOS picture. Pending changes are applied when that picture becomes visible again. Partial GPU uploads also cover less data.

If automatic camera use is enabled and macOS camera access is undecided, the permission notice appears before SteamOS starts. If enabled later in Settings, the first game request asks once. Granting access alone does not start capture; capture runs only for a game request or manual preview.

Development checks on an M1 Mac with 8 GB RAM and a cloned disk covered VRChat world entry, camera activation on a game request, and YamaPlayer video playback with camera tracking off. Launcher main-thread CPU use in that check fell from about 1% to 0.1–0.2%. This measures the launcher and does not promise a particular game CPU or FPS improvement.

Existing disks, games and settings are retained. Use Check for Updates… or Install and Open in the DMG. The BOOTH online installer also selects the latest version.

The reported M3 startup hang before any window appears remains under investigation; this release has not been verified to fix it.
