# SteamAC Lite: experimental 8 GB profile

Apple Silicon・RAM 8 GB向けの試作です。**VRChatが快適に動作する、重いワールドを利用できる、という保証はありません。** 上流の最低要件は16 GBです。

## 変更内容

| 項目 | 上流の8 GB Macでの自動設定 | Liteの初期設定 |
|---|---|---|
| VM RAM | 4 GiB | 3 GiB |
| GPUの報告予算 | 1 GiB | 2 GiB |
| macOS・ドライバの予算 | 3 GiB | 3 GiB |
| 初期描画 | 1280×800、60 Hz | 960×600、60 Hz、Retinaなし |
| 追加ディスクスワップ | なし | ゲストのext4 `/home` に4 GiB |
| 描画経路 | 設定による | DXMTを優先、利用できなければVulkan |

GPU予算は報告値で、物理RAMを予約・保証する機構ではありません。解像度の値は初期ウインドウ時の値です。ウインドウサイズを変えると描画サイズも変わります。60 Hzは表示更新頻度であり、ゲームが60 fpsを出すという意味ではありません。Lite.1の30 HzからLite.2で60 Hzへ変更しました。[日本語入力とUS/JIS判別](japanese-input.md)もLite.2で追加しています。

ゲストの匿名メモリをSSDへ退避することで、RAM不足による終了を減らせる可能性があります。ディスクスワップは物理RAMやGPUメモリの代わりにはならず、頻繁なページ入れ替えでは大きく遅くなります。macOSのスワップ設定や上限は変更しません。既存のzram・スワップも置き換えません。

Steam UIのソフトウェア描画と、起動150秒後のページキャッシュ解放は上流に既にある機能を利用します。継続的な`drop_caches`、メモリ容量の偽装、強制的なovercommit、アンチチートの変更は追加していません。

## 起動と戻し方

`SteamAC Lite.app`は別のbundle ID・設定領域・ログ領域を使います。上流アプリを上書きしません。試すときは停止したSteamOSディスクをAPFS cloneして、コピーしたディスクを指定してください。ディスクの同時利用は避けてください。

Lite.3からは[Mac別の自動設定](performance-profiles.md)が既定になり、8 GB Macでは軽量初期値を選びます。`--low-memory`で他のMacでも軽量モード、`--no-low-memory`または`--profile manual`で自動プロファイルを無効にできます。CLIだけでなく設定画面で保存した手動値も自動初期値より優先します。Retinaは既定OFFで、手動でONにすることもできます。

追加スワップは`steamac.low_memory=1`の起動だけで有効になります。ファイルは`/home/.steamac-low-memory/swapfile`で、初回に4 GiBを実際に割り当てます。ゲストとMacのディスクには、それぞれ最低8 GiBの空きが必要です。既に作成済みのファイルをゲストで再利用する場合は追加割り当てしません。ext4以外、空き不足、所有者や権限が不適切な既存ファイルの場合は作成を中止し、ログへ理由を出します。作成失敗でもSteam起動を強制停止する構成にはしていません。

通常版へ戻すと追加スワップは自動で有効になりません。ファイルの4 GiB分はコピーしたゲストディスクに残ります。必要ならゲストを停止して、その試作用ディスク全体を削除できます。元のディスクには影響しません。

## ビルド

基点は`StonkGuy/steamac`の`v1.9.4-eac.1`、commit `c5437da7a4fdef5bd0b79546eab4a2a8a6689546`です。

このMac用の開発ビルドでは、元の署名付きアプリからカーネル・DXMT・Mesa等を再利用し、変更したSwiftランチャーをコンパイルして、ゲストレイヤーへスワップ・配列設定・日本語入力のサービスを追加します。全コンポーネントをソースから再ビルドする上流のリリース手順とは異なります。元のライセンスとnoticeを保持し、変更したレイヤーには別のprovenanceを保存します。

必要なもの: macOS用Swift 6、SDK、Rust 1.90.0、Git、Python 3、erofs-utils（`fsck.erofs`と`mkfs.erofs`）、導入済みのFX Steam Launcher 1.9.4-eac.1。初回はSwiftPM依存関係とlibkrunヘッダー用ソースをダウンロードします。

```sh
python3 scripts/test/low-memory-swap.py
python3 scripts/test/keyboard-setup.py
BASE_APP="/Applications/FX Steam Launcher.app" bash scripts/lite/build-audio-library.sh
LIBKRUN_OVERRIDE="$PWD/work/out/host/lib/libkrun.1.dylib" bash scripts/lite/build-app.sh
```

`BASE_APP`、`DEVELOPER_DIR`、`SDK`、`JOBS`、`FSCK_EROFS`、`MKFS_EROFS`を指定できます。標準のCommand Line Tools SDK 26.5があれば使用します。新しいSDKでSwiftUIマクロのプラグインが必要な場合は、対応するXcode一式が必要です。

## 確認する範囲

`--selftest-low-memory`はメモリ配分、無効化、CLIの優先順位をVMなしで確認します。Pythonテストはスワップ作成・再利用、容量不足、非対応ファイルシステム、リンク拒否、失敗時の処理を模擬環境で確認します。

2026-11-02にApple M1・RAM 8 GiB・macOS 27.2で、コピーした既存のSteamOSディスクを使って確認しました。`scripts/lite/smoke-test.py`によるheadless起動で、VM 3 GiB、GPU報告予算2 GiB、追加ディスクスワップ4 GiBの有効化、`Steam is ready`、正常シャットダウンを確認済みです。音声・SSH・VRはこのテストでは無効です。テストは既存のスワップファイルを再利用する実経路も通っています。初回のファイル割り当て・`mkswap`は、情報表示オプションの互換性エラーを修正する前の試行で完了していました。

**Steam起動とVRChatのゲーム内動作確認は別です。** 初回の自動テストではVRChatを起動していません。その後、ユーザーからこの8 GB MacでVRChatが動作したとの報告があり、SteamのGUI表示も確認しました。FPS、ワールド・アバター別の互換性、メモリ圧迫、フレーム時間、長時間安定性は測定していません。

```sh
python3 scripts/lite/smoke-test.py --disk /path/to/stopped-test-copy.img
```

テストは指定したコピー上でVMを起動して、終了時に正常シャットダウンを要求します。元アプリの既定のディスクや、使用中のディスクは拒否します。結果とコンソールログはGit管理外の`work/`に保存されます。
